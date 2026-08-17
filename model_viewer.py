"""3D 模型预览组件 — 基于 pyqtgraph OpenGL"""
import numpy as np
import trimesh
import pyqtgraph.opengl as gl
from PySide6.QtCore import Qt, Signal
import pyqtgraph as pg
from trimesh.transformations import rotation_matrix as _rot_mat


class ModelViewer(gl.GLViewWidget):
    """内嵌 3D STL 模型查看器，支持鼠标旋转/缩放/平移、模型拾取与阵列复制"""

    # 右键点击信号（在模型上右键触发）
    right_clicked = Signal()
    # 6个面 → (旋转轴, 角度)，把该面转到朝下(-Z)
    _FACE_ROTATIONS = {
        "底": None,              # -Z 面，无需旋转
        "顶": ([1, 0, 0], 180),  # +Z 面朝下
        "前": ([1, 0, 0], -90),  # +Y 面朝下
        "后": ([1, 0, 0], 90),   # -Y 面朝下
        "右": ([0, 1, 0], 90),   # +X 面朝下
        "左": ([0, 1, 0], -90),  # -X 面朝下
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackgroundColor((240, 240, 240, 255))
        self.setCameraPosition(distance=80, elevation=30, azimuth=-45)      #初始相机视角
        self._mesh_item = None
        self._slice_plane = None
        self._model_offset = np.zeros(3, dtype=np.float64)
        self._dragging_model = False
        self._dragging_instance_index = None
        self._drag_model_screen = None
        self._drag_model_z = 0.0
        self._drag_mouse_pos = None
        self._press_pos = None
        # 模型源列表：每个元素 {"path", "vertices", "faces"}
        self._sources = []
        # 实例列表：每个元素 {"source_idx", "offset", "rotation", "item"}
        self._instances = []
        self._selected_index = None
        self._grid = gl.GLGridItem()
        self._grid.setSize(200, 200)
        self._grid.setSpacing(10, 10)
        self._grid.setColor((100, 100, 100, 255))
        self.addItem(self._grid)

    def add_model(self, mesh_path: str):
        """从 STL 文件加载模型并追加为新的模型源"""
        mesh = trimesh.load(mesh_path)
        if mesh.is_empty:
            return
        vertices = np.array(mesh.vertices, dtype=np.float32)
        faces = np.array(mesh.faces, dtype=np.uint32)
        self._sources.append({"path": mesh_path, "vertices": vertices, "faces": faces})
        source_idx = len(self._sources) - 1
        self._instances.append(
            self._make_instance(source_idx, np.zeros(3, dtype=np.float64), np.eye(4)))
        self._mesh_item = self._instances[-1]["item"]
        self._update_scene()
        print(f"loaded: {mesh_path} v={len(vertices)}")

    def load_stl(self, mesh_path: str):
        """兼容旧接口：清除并加载单个模型"""
        self._clear_model()
        self.add_model(mesh_path)

    def _source_verts(self, inst):
        return self._sources[inst["source_idx"]]["vertices"]

    def _source_faces(self, inst):
        return self._sources[inst["source_idx"]]["faces"]

    def show_slice_plane(self, z: float, color=(255, 100, 100, 128)):
        """在指定高度显示切片参考平面"""
        self._remove_slice_plane()
        gz = gl.GLGridItem()
        gz.setSize(self._grid_size, self._grid_size)
        gz.setSpacing(self._grid_size, self._grid_size)
        gz.translate(0, 0, z)
        gz.setColor(color)
        self._slice_plane = gz
        self.addItem(self._slice_plane)

    def hide_slice_plane(self):
        self._remove_slice_plane()

    def reset_view(self):
        self.setCameraPosition(distance=80, elevation=20, azimuth=-45)

    def _clear_model(self):
        for inst in self._instances:
            if inst["item"] is not None:
                self.removeItem(inst["item"])
        self._instances = []
        self._sources = []
        self._selected_index = None
        self._mesh_item = None
        self._model_offset = np.zeros(3, dtype=np.float64)

    def reset_model_position(self):
        """复位模型到拖拽前位置"""
        for inst in self._instances:
            inst["item"].translate(
                -self._model_offset[0], -self._model_offset[1], -self._model_offset[2])
            inst["offset"] = inst["offset"] - self._model_offset
        self._model_offset = np.zeros(3, dtype=np.float64)

    def _apply_matrix(self, vertices, matrix):
        """对顶点应用4×4齐次矩阵，返回旋转后的(N,3)数组"""
        v_h = np.hstack([vertices, np.ones((vertices.shape[0], 1))])
        return (matrix @ v_h.T).T[:, :3].astype(np.float32)

    def _make_instance(self, source_idx, offset, rotation=None):
        """创建一个模型实例（引用指定源，带平移与旋转）"""
        rot = np.eye(4) if rotation is None else rotation
        src = self._sources[source_idx]
        vertices = src["vertices"]
        faces = src["faces"]
        face_color = np.array([0.30, 0.70, 0.80, 0.95], dtype=np.float32)
        colors = np.tile(face_color, (len(faces), 1))
        rotated = self._apply_matrix(vertices, rot)
        item = gl.GLMeshItem(
            vertexes=rotated,
            faces=faces,
            faceColors=colors,
            edgeColor=(1.0, 0.0, 0.0, 1.0),
            drawEdges=False,
            smooth=False,
            glOptions="translucent",
            shader="shaded",
        )
        if offset.any():
            item.translate(offset[0], offset[1], offset[2])
        self.addItem(item)
        return {"source_idx": source_idx, "offset": offset, "rotation": rot, "item": item}

    def _rebuild_instances(self):
        """按各实例的源/偏移/旋转重建所有实例"""
        if not self._instances:
            return
        data = [(inst["source_idx"], inst["offset"], inst["rotation"])
                for inst in self._instances]
        for inst in self._instances:
            self.removeItem(inst["item"])
        self._instances = [self._make_instance(si, off, rot)
                           for si, off, rot in data]
        self._mesh_item = self._instances[0]["item"] if self._instances else None
        if self._selected_index is not None:
            self._apply_selection_highlight()

    def _update_scene(self):
        """根据所有实例的联合包围盒更新网格与相机"""
        if not self._instances:
            return
        mins, maxs = [], []
        for inst in self._instances:
            rotated = self._apply_matrix(self._source_verts(inst), inst["rotation"])
            off = inst["offset"]
            mins.append(rotated.min(axis=0) + off)
            maxs.append(rotated.max(axis=0) + off)
        mn = np.min(mins, axis=0)
        mx = np.max(maxs, axis=0)
        extent = np.linalg.norm(mx - mn)
        center = (mn + mx) / 2
        self.opts["center"] = pg.Vector(*center)
        self.setCameraPosition(distance=extent * 1.5)
        grid_size = extent * 1.5
        self._grid.resetTransform()
        self._grid.setSize(grid_size, grid_size)
        self._grid.setSpacing(grid_size / 10, grid_size / 10)
        self._grid.translate(0, 0, mn[2])
        self._grid_size = grid_size
        self.update()

    def set_bottom_face(self, face: str):
        """切换底面：仅旋转选中实例使指定面朝下(-Z)"""
        if self._selected_index is None or not self._instances:
            return
        if face not in self._FACE_ROTATIONS:
            return
        spec = self._FACE_ROTATIONS[face]
        inst = self._instances[self._selected_index]
        center = self._source_verts(inst).mean(axis=0)
        if spec is None:
            rot = np.eye(4)
        else:
            axis, angle_deg = spec
            rot = _rot_mat(np.radians(angle_deg), axis, point=center)
        inst["rotation"] = rot
        self._rebuild_instances()
        self._update_scene()

    def get_instances(self):
        """返回所有实例的 source_path/offset/rotation（供切片器使用）"""
        return [{"source_path": self._sources[inst["source_idx"]]["path"],
                 "offset": inst["offset"],
                 "rotation": inst["rotation"]}
                for inst in self._instances]

    def get_default_spacing(self):
        """返回默认阵列间隙（模型X/Y尺寸的0.1倍）"""
        if not self._instances:
            return 10.0
        idx = self._selected_index if self._selected_index is not None else 0
        inst = self._instances[idx]
        rotated = self._apply_matrix(self._source_verts(inst), inst["rotation"])
        mn = rotated.min(axis=0)
        mx = rotated.max(axis=0)
        return max(mx[0] - mn[0], mx[1] - mn[1]) * 0.1

    def drop_to_plate(self):
        """使选中模型底面贴合网格平面（联合 min Z）"""
        if self._selected_index is None or not self._instances:
            return
        all_min_z = []
        for inst in self._instances:
            rotated = self._apply_matrix(self._source_verts(inst), inst["rotation"])
            all_min_z.append(rotated[:, 2].min() + inst["offset"][2])
        plate_z = min(all_min_z)
        inst = self._instances[self._selected_index]
        rotated = self._apply_matrix(self._source_verts(inst), inst["rotation"])
        cur_min_z = rotated[:, 2].min() + inst["offset"][2]
        dz = plate_z - cur_min_z
        if abs(dz) < 1e-6:
            return
        inst["item"].translate(0, 0, dz)
        inst["offset"][2] += dz
        self._update_scene()

    def delete_selected(self):
        """删除选中的实例"""
        if self._selected_index is None or not self._instances:
            return
        inst = self._instances.pop(self._selected_index)
        self.removeItem(inst["item"])
        self._selected_index = None
        self._mesh_item = self._instances[0]["item"] if self._instances else None
        self._update_scene()

    def rotate_z_90(self):
        """绕Z轴旋转选中模型90度（绕模型自身中心）"""
        if self._selected_index is None or not self._instances:
            return
        inst = self._instances[self._selected_index]
        center = self._source_verts(inst).mean(axis=0)
        rotated_center = np.array(inst["rotation"] @ np.append(center, 1.0))[:3]
        rot_z = _rot_mat(np.radians(90), [0, 0, 1], point=rotated_center)
        inst["rotation"] = rot_z @ inst["rotation"]
        self._rebuild_instances()
        self._update_scene()

    def pick_instance(self, pos):
        """用实例包围盒的屏幕投影拾取（不依赖 GL_SELECT）"""
        if not self._instances:
            return None
        best_idx, best_depth = None, float("inf")
        for i, inst in enumerate(self._instances):
            rotated = self._apply_matrix(self._source_verts(inst), inst["rotation"])
            off = inst["offset"]
            mn = rotated.min(axis=0) + off
            mx = rotated.max(axis=0) + off
            corners = np.array([
                [mn[0], mn[1], mn[2]], [mx[0], mn[1], mn[2]],
                [mn[0], mx[1], mn[2]], [mx[0], mx[1], mn[2]],
                [mn[0], mn[1], mx[2]], [mx[0], mn[1], mx[2]],
                [mn[0], mx[1], mx[2]], [mx[0], mx[1], mx[2]],
            ])
            screens = np.array([self._world_to_screen(c) for c in corners])
            if (screens[:, 0].min() <= pos.x() <= screens[:, 0].max()
                    and screens[:, 1].min() <= pos.y() <= screens[:, 1].max()):
                depth = screens[:, 2].mean()
                if depth < best_depth:
                    best_depth, best_idx = depth, i
        return best_idx

    def _apply_selection_highlight(self):
        """刷新选中高亮（用 faceColors 换色）"""
        base = np.array([0.30, 0.70, 0.80, 0.95], dtype=np.float32)
        selected = np.array([1.0, 0.85, 0.0, 0.95], dtype=np.float32)
        for i, inst in enumerate(self._instances):
            c = selected if i == self._selected_index else base
            verts = self._source_verts(inst)
            faces = self._source_faces(inst)
            rotated = self._apply_matrix(verts, inst["rotation"])
            inst["item"].setMeshData(
                vertexes=rotated,
                faces=faces,
                faceColors=np.tile(c, (len(faces), 1)),
            )
            inst["item"].update()

    def select_instance(self, idx):
        """选中实例并高亮；传 None 取消选中"""
        if idx is not None and (idx < 0 or idx >= len(self._instances)):
            return
        self._selected_index = idx
        self._apply_selection_highlight()

    def array_copy(self, nx, gap_x, ny, gap_y):
        """对选中实例做 nx×ny 阵列复制，选中实例成为阵列第一个"""
        if self._selected_index is None or not self._instances:
            return
        anchor_inst = self._instances[self._selected_index]
        anchor = anchor_inst["offset"]
        anchor_rot = anchor_inst["rotation"]
        anchor_src = anchor_inst["source_idx"]
        rotated = self._apply_matrix(self._source_verts(anchor_inst), anchor_rot)
        model_w = rotated[:, 0].max() - rotated[:, 0].min()
        model_d = rotated[:, 1].max() - rotated[:, 1].min()
        step_x = gap_x + model_w
        step_y = gap_y + model_d
        new_offsets = []
        for j in range(ny):
            for i in range(nx):
                off = anchor + np.array([i * step_x, j * step_y, 0.0])
                new_offsets.append(off)
        for inst in self._instances:
            self.removeItem(inst["item"])
        self._instances = [self._make_instance(anchor_src, off, anchor_rot)
                           for off in new_offsets]
        self._mesh_item = self._instances[0]["item"] if self._instances else None
        self._selected_index = None
        self._update_scene()

    def _world_to_screen(self, world_pos):
        """世界坐标 → 屏幕像素坐标"""
        vp = self.getViewport()
        view_np = np.array(self.viewMatrix().data()).reshape(4, 4).T
        proj_np = np.array(self.projectionMatrix(region=vp, viewport=vp).data()).reshape(4, 4).T
        mvp = proj_np @ view_np
        clip = mvp @ np.append(world_pos, 1.0)
        ndc = clip[:3] / clip[3]
        sx = (ndc[0] + 1.0) * 0.5 * vp[2] + vp[0]
        sy = (1.0 - ndc[1]) * 0.5 * vp[3] + vp[1]
        return np.array([sx, sy, ndc[2]])

    def _screen_to_xy_plane(self, screen_xy, z_plane):
        """屏幕坐标 + 目标Z → 世界坐标（射线与Z=z_plane平面交点）"""
        vp = self.getViewport()
        ndc_x = (screen_xy[0] - vp[0]) / vp[2] * 2.0 - 1.0
        ndc_y = 1.0 - (screen_xy[1] - vp[1]) / vp[3] * 2.0
        view_np = np.array(self.viewMatrix().data()).reshape(4, 4).T
        proj_np = np.array(self.projectionMatrix(region=vp, viewport=vp).data()).reshape(4, 4).T
        mvp = proj_np @ view_np
        inv_mvp = np.linalg.inv(mvp)

        def unproject(ndc_x, ndc_y, ndc_z):
            clip = np.array([ndc_x, ndc_y, ndc_z, 1.0])
            world = inv_mvp @ clip
            return world[:3] / world[3]

        near = unproject(ndc_x, ndc_y, -1.0)
        far = unproject(ndc_x, ndc_y, 1.0)
        ray = far - near
        t = (z_plane - near[2]) / ray[2]
        return near + t * ray

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            # 右键：命中模型则选中并发信号
            idx = self.pick_instance(event.pos())
            if idx is not None:
                self.select_instance(idx)
                self.right_clicked.emit()
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.pos()

        if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                and self._mesh_item is not None
                and event.button() == Qt.MouseButton.LeftButton):
            idx = self.pick_instance(event.pos())
            if idx is None:
                super().mousePressEvent(event)
                return
            self._dragging_instance_index = idx
            self.select_instance(idx)
            try:
                tr = self._instances[idx]["item"].transform()
                model_world = np.array([tr[0, 3], tr[1, 3], tr[2, 3]])
                self._drag_model_screen = self._world_to_screen(model_world)
                self._drag_model_z = model_world[2]
                self._drag_mouse_pos = event.pos()
                self._dragging_model = True
            except Exception:
                import traceback
                traceback.print_exc()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging_model and self._dragging_instance_index is not None and self._drag_model_screen is not None:
            delta = np.array([event.pos().x() - self._drag_mouse_pos.x(),
                              event.pos().y() - self._drag_mouse_pos.y()])
            target_screen = self._drag_model_screen[:2] + delta
            new_world = self._screen_to_xy_plane(target_screen, self._drag_model_z)
            inst = self._instances[self._dragging_instance_index]
            tr = inst["item"].transform()
            cur = np.array([tr[0, 3], tr[1, 3], tr[2, 3]])
            diff = new_world - cur
            inst["item"].translate(diff[0], diff[1], diff[2])
            inst["offset"] = inst["offset"] + diff
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging_model:
            self._dragging_model = False
            self._dragging_instance_index = None
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and self._press_pos is not None:
            delta = event.pos() - self._press_pos
            if abs(delta.x()) < 3 and abs(delta.y()) < 3:
                # 单击：拾取选择模型
                idx = self.pick_instance(event.pos())
                if idx is not None:
                    self.select_instance(idx)
                else:
                    self.select_instance(None)
            self._press_pos = None
        super().mouseReleaseEvent(event)

    def _remove_slice_plane(self):
        if self._slice_plane is not None:
            self.removeItem(self._slice_plane)
            self._slice_plane = None
