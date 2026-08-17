"""模型切片工具 - PySide6 主界面"""
import os

import numpy as np
import trimesh

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGroupBox, QLabel, QLineEdit, QPushButton, QRadioButton,
    QComboBox, QProgressBar, QFileDialog, QMessageBox, QSpacerItem,
    QSizePolicy,QFrame,QListView,QGridLayout,QMenu,QDialog,QDialogButtonBox
)
from PySide6.QtCore import Qt, QThread, QSize
from PySide6.QtGui import QFont, QIcon, QPainterPath, QRegion, QMouseEvent, QCursor
from PySide6.QtCore import QRectF

from slicing_worker import SlicingWorker
from model_viewer import ModelViewer

from style import (btnStyle,titleFrameStyle,titleBtnStyle,titleOperateBtnClose,titleOperateBtnMini,
                  paraFrameStyle,paraLabelStyle,groupTitleStyle,lineStyle,comboStyle,radiobtnStyle,
                   barStyle,statusStyle)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MicroSlicer")
        self.resize(1440, 900)
        self.setWindowFlags(Qt.FramelessWindowHint)       #设置窗口无边框
        self.setAttribute(Qt.WA_TranslucentBackground)    #窗口透明（圆角需要）

        self._worker: SlicingWorker | None = None
        self._model_viewer: ModelViewer | None = None
        self._mesh_path = ""

        self._setup_ui()
        self._connect_signals()
        self._update_saturation_controls()

    # ────────────────── UI 布局 ──────────────────

    def _setup_ui(self):
        #设置边框圆角
        central = QWidget()
        central.setObjectName("centralPanel")
        central.setAttribute(Qt.WA_StyledBackground,True)
        central.setStyleSheet("""
            #centralPanel {
                background: #FFFFFF;        
                border-radius: 15px;
            }
        """)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)                   #总布局
        root.setContentsMargins(0, 0, 0, 5)
        root.setSpacing(0)

        #标题栏，图标、关闭、缩小--------------------------
        title_frame = QFrame()
        title_frame.setFixedHeight(35)
        title_frame.setStyleSheet(titleFrameStyle)

        title_layout = QHBoxLayout(title_frame)
        title_layout.setContentsMargins(5, 0, 0, 0)
        title_icon = QPushButton(QIcon("Title.png"),"MicroSlicer")
        title_icon.setIconSize(QSize(24, 24))
        title_icon.setFixedSize(120,40)
        title_icon.setStyleSheet(titleBtnStyle)
        title_layout.addWidget(title_icon)
        title_layout.addStretch()

        btn_close = QPushButton(QIcon("close.png"),"")
        btn_mini = QPushButton(QIcon("mini.png"),"")
        btn_close.setIconSize(QSize(25, 25))
        btn_mini.setIconSize(QSize(25, 25))
        btn_close.setFixedSize(40,40)
        btn_mini.setFixedSize(40, 40)
        btn_close.setStyleSheet(titleOperateBtnClose)
        btn_mini.setStyleSheet(titleOperateBtnMini)
        title_layout.addWidget(btn_mini)
        title_layout.addWidget(btn_close)

        btn_close.clicked.connect(self.close)             #关闭按键连接
        btn_mini.clicked.connect(self.showMinimized)      #缩小按键连接

        root.addWidget(title_frame)

        #左侧参数面板-------------------------------------------------
        para_frame = QFrame()
        para_frame.setFixedWidth(300)
        para_frame.setStyleSheet(paraFrameStyle)
        #para_frame.setFixedHeight(640)

        # ════ 中间区域：左右分栏 ════
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(para_frame)

        # 右侧：3D 模型预览
        self.model_viewer = ModelViewer()
        splitter.addWidget(self.model_viewer)

        # 左侧：参数面板
        para_panel = QVBoxLayout(para_frame)
        para_panel.setSpacing(10)

        # ── 基本参数 ──
        topGap = QSpacerItem(10, 10)
        intertopGap = QSpacerItem(10, 15)          #通用弹簧，控制group与内部内容间距
        para_panel.addSpacerItem(topGap)
        gb_basic = QGroupBox("切片设置")
        gb_basic.setStyleSheet(groupTitleStyle)
        lay_basic = QVBoxLayout(gb_basic)
        lay_basic.addSpacerItem(intertopGap)

        for text, default, attr in [
            ("层厚(mm)", "0.1", "edit_layer_height"),
            ("边距比例", "0.05", "edit_margin"),
            ("输出文件", "slices", "edit_zip_name"),
        ]:
            row = QHBoxLayout()
            para_label = QLabel()
            para_label.setFixedWidth(85)
            para_label.setStyleSheet(paraLabelStyle)
            para_label.setText(text)
            row.addWidget(para_label)
            edit = QLineEdit(default)
            edit.setStyleSheet(lineStyle)
            setattr(self, attr, edit)
            row.addWidget(edit)
            if attr == "edit_zip_name":
                row.addWidget(QLabel(".zip"))
            lay_basic.addLayout(row)

        # DPI 下拉选择
        dpi_row = QHBoxLayout()
        dpi_label = QLabel("输出DPI")
        dpi_label.setFixedWidth(85)
        dpi_label.setFixedHeight(25)
        dpi_label.setStyleSheet(paraLabelStyle)
        dpi_row.addWidget(dpi_label)
        self.combo_dpi = QComboBox()
        self.combo_dpi.setView(QListView())
        self.combo_dpi.addItems(["400", "800", "1200"])
        self.combo_dpi.setCurrentText("400")
        self.combo_dpi.setStyleSheet(comboStyle)
        dpi_row.addWidget(self.combo_dpi)
        dpi_row.addStretch()
        lay_basic.addLayout(dpi_row)

        # 底面选择
        face_row = QHBoxLayout()
        face_label = QLabel("切片底面")
        face_label.setFixedWidth(85)
        face_label.setFixedHeight(25)
        face_label.setStyleSheet(paraLabelStyle)
        face_row.addWidget(face_label)
        self.combo_face = QComboBox()
        self.combo_face.setView(QListView())
        self.combo_face.addItems(["底", "顶", "前", "后", "左", "右"])
        self.combo_face.setCurrentText("底")
        self.combo_face.setStyleSheet(comboStyle)
        face_row.addWidget(self.combo_face)
        face_row.addStretch()
        lay_basic.addLayout(face_row)

        # 图片格式选择
        fmt_row = QHBoxLayout()
        format_select = QLabel()
        format_select.setFixedWidth(85)
        format_select.setFixedHeight(25)
        format_select.setText("输出格式")
        format_select.setStyleSheet(paraLabelStyle)
        fmt_row.addWidget(format_select)
        self.combo_format = QComboBox()
        self.combo_format.setView(QListView())
        self.combo_format.addItems(["PNG", "TIFF", "BMP", "JPEG"])
        self.combo_format.setCurrentText("TIFF")
        self.combo_format.setStyleSheet(comboStyle)
        fmt_row.addWidget(self.combo_format)
        fmt_row.addStretch()
        lay_basic.addLayout(fmt_row)

        para_panel.addWidget(gb_basic)

        # ── 饱和度模式 ──                    即灰度
        gb_sat = QGroupBox("灰度设置")
        gb_sat.setStyleSheet(groupTitleStyle)
        lay_sat = QVBoxLayout(gb_sat)
        lay_sat.addSpacerItem(intertopGap)

        mode_row = QHBoxLayout()
        self.radio_binary = QRadioButton("二值")
        self.radio_shell = QRadioButton("灰度")
        self.radio_shell.setChecked(True)
        self.radio_binary.setStyleSheet(radiobtnStyle)
        self.radio_shell.setStyleSheet(radiobtnStyle)
        mode_row.addWidget(self.radio_binary)
        mode_row.addWidget(self.radio_shell)
        mode_row.setSpacing(30)
        mode_row.addStretch()
        lay_sat.addLayout(mode_row)

        # 壳体参数
        shell_params = QGridLayout()
        marginWlabel = QLabel("边缘宽度 (mm)")
        marginWlabel.setFixedWidth(125)
        marginWlabel.setFixedHeight(25)
        marginWlabel.setStyleSheet(paraLabelStyle)
        shell_params.addWidget(marginWlabel,0,0)
        self.edit_shell_width = QLineEdit("1.0")
        self.edit_shell_width.setStyleSheet(lineStyle)
        self.edit_shell_width.setFixedWidth(130)
        shell_params.addWidget(self.edit_shell_width,0,1)
        graylabel = QLabel("内部灰度 (0~255)")
        graylabel.setFixedWidth(125)
        graylabel.setFixedHeight(25)
        graylabel.setStyleSheet(paraLabelStyle)
        shell_params.addWidget(graylabel,1,0)
        self.edit_base_sat = QLineEdit("128")
        self.edit_base_sat.setStyleSheet(lineStyle)
        self.edit_base_sat.setFixedWidth(130)
        shell_params.addWidget(self.edit_base_sat,1,1)
        #shell_params.setColumnStretch(2, 1)
        self._shell_params_layout = shell_params
        lay_sat.addLayout(shell_params)

        para_panel.addWidget(gb_sat)
        #splitter.addWidget(right_panel)
        splitter.setSizes([580, 360])

        root.addWidget(splitter, stretch=1)

        # ── 进度条 ──
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(5, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet(barStyle)
        root.addWidget(self.progress_bar)

        # ── 导入、开始、取消按钮 ──
        btn_row = QGridLayout()

        # 1.导入模型按钮
        self.btn_browse = QPushButton("导入模型")
        self.btn_browse.setStyleSheet(btnStyle)
        self.btn_browse.setFixedSize(120, 30)
        self.btn_browse.clicked.connect(self._on_browse)

        #2.开始、取消按钮
        self.btn_start = QPushButton("开始切片")
        self.btn_start.setFixedSize(120, 30)
        self.btn_start.setStyleSheet(btnStyle)
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setStyleSheet(btnStyle)
        self.btn_stop.setFixedSize(120, 30)
        self.btn_stop.setEnabled(False)

        btn_row.addWidget(self.btn_browse,0,0)
        btn_row.addWidget(self.btn_start,1,0)
        btn_row.addWidget(self.btn_stop,1,1)

        para_panel.addSpacerItem(QSpacerItem(10, 40))
        para_panel.addLayout(btn_row)
        para_panel.addStretch()

        # ── 状态标签 ──
        self.label_status = QLabel("就绪")
        self.label_status.setStyleSheet(statusStyle)
        para_panel.addWidget(self.label_status)

    # ────────────────── 信号连接 ──────────────────

    def _connect_signals(self):
        self.btn_start.clicked.connect(self._on_start)
        self.btn_stop.clicked.connect(self._on_stop)
        self.radio_binary.toggled.connect(self._update_saturation_controls)
        self.radio_shell.toggled.connect(self._update_saturation_controls)
        self.combo_face.currentTextChanged.connect(self._on_face_changed)
        self.model_viewer.right_clicked.connect(self._on_model_right_clicked)

    def _on_face_changed(self, face: str):
        """切换切片底面，同步旋转显示模型"""
        if self.model_viewer is not None:
            self.model_viewer.set_bottom_face(face)

    def _on_model_right_clicked(self):
        menu = QMenu(self)
        act_array = menu.addAction("阵列复制")
        act_drop = menu.addAction("贴合底面")
        act_rotate = menu.addAction("旋转90°")
        act_delete = menu.addAction("删除")
        chosen = menu.exec(QCursor.pos())
        if chosen == act_array:
            self._show_array_dialog()
        elif chosen == act_drop:
            self.model_viewer.drop_to_plate()
        elif chosen == act_rotate:
            self.model_viewer.rotate_z_90()
        elif chosen == act_delete:
            self.model_viewer.delete_selected()

    def _show_array_dialog(self):
        """弹出阵列复制参数对话框"""
        dlg = QDialog(self)
        dlg.setWindowTitle("阵列复制")
        layout = QGridLayout(dlg)

        layout.addWidget(QLabel("X方向数量"), 0, 0)
        edit_nx = QLineEdit("2")
        layout.addWidget(edit_nx, 0, 1)
        layout.addWidget(QLabel("X方向间距(mm)"), 0, 2)
        edit_gx = QLineEdit("")
        layout.addWidget(edit_gx, 0, 3)

        layout.addWidget(QLabel("Y方向数量"), 1, 0)
        edit_ny = QLineEdit("2")
        layout.addWidget(edit_ny, 1, 1)
        layout.addWidget(QLabel("Y方向间距(mm)"), 1, 2)
        edit_gy = QLineEdit("")
        layout.addWidget(edit_gy, 1, 3)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons, 2, 0, 1, 4)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            nx = int(edit_nx.text())
            ny = int(edit_ny.text())
            gx = float(edit_gx.text()) if edit_gx.text().strip() else None
            gy = float(edit_gy.text()) if edit_gy.text().strip() else None
        except ValueError:
            QMessageBox.warning(self, "参数错误", "请检查阵列参数格式")
            return

        if nx < 1 or ny < 1:
            QMessageBox.warning(self, "参数错误", "阵列数量需 ≥ 1")
            return

        # 间距默认：模型尺寸的1.1倍（由 viewer 内部计算）
        if gx is None or gy is None:
            default = self.model_viewer.get_default_spacing()
            if gx is None:
                gx = default
            if gy is None:
                gy = default

        self.model_viewer.array_copy(nx, gx, ny, gy)

    def _update_saturation_controls(self):
        """根据选中模式显示/隐藏壳体参数"""
        shell_mode = self.radio_shell.isChecked()
        for i in range(self._shell_params_layout.count()):
            widget = self._shell_params_layout.itemAt(i).widget()
            if widget:
                widget.setVisible(shell_mode)

    # ────────────────── 槽函数 ──────────────────

    def _on_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择模型文件", "", "STL 文件 (*.stl);;所有文件 (*)"
        )
        if path:
            self._mesh_path = path
            self._load_model_3d(path)

    def _load_model_3d(self, mesh_path: str):
        """加载 3D 模型到预览视图"""
        try:
            self.model_viewer.add_model(mesh_path)
            self.label_status.setText("就绪")
        except Exception as e:
            self.label_status.setText(f"3D 预览失败: {e}")

    def _on_start(self):
        if not self._mesh_path:
            QMessageBox.warning(self, "错误", "请先导入模型文件")
            return
        if not os.path.exists(self._mesh_path):
            QMessageBox.warning(self, "错误", f"模型文件不存在:\n{self._mesh_path}")
            return

        try:
            layer_height = float(self.edit_layer_height.text())
            target_dpi = int(self.combo_dpi.currentText())
            margin_ratio = float(self.edit_margin.text())
            zip_base = self.edit_zip_name.text().strip() or "slices"
            output_zip = f"{zip_base}.zip"

            saturation_mode = "shell" if self.radio_shell.isChecked() else "binary"
            shell_width_mm = float(self.edit_shell_width.text())
            base_saturation = int(self.edit_base_sat.text())
        except ValueError as e:
            QMessageBox.warning(self, "参数错误", f"请检查输入格式:\n{e}")
            return

        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, "提示", "切片正在进行中")
            return

        # ── 内存预估弹窗 ──
        try:
            instances = self.model_viewer.get_instances()
            if not instances:
                raise ValueError("场景中没有模型")
            all_min = np.array([np.inf, np.inf, np.inf])
            all_max = np.array([-np.inf, -np.inf, -np.inf])
            for inst in instances:
                m = trimesh.load(inst["source_path"])
                rot = np.array(inst["rotation"], dtype=np.float64)
                if not np.allclose(rot, np.eye(4)):
                    m.apply_transform(rot)
                m.apply_translation([float(inst["offset"][0]),
                                     float(inst["offset"][1]),
                                     float(inst["offset"][2])])
                all_min = np.minimum(all_min, m.bounds[0])
                all_max = np.maximum(all_max, m.bounds[1])
            z_min, z_max = float(all_min[2]), float(all_max[2])
            bb_w = all_max[0] - all_min[0]
            bb_h = all_max[1] - all_min[1]
            scale = target_dpi / 25.4
            ox = int(np.ceil(bb_w * scale))
            oy = int(np.ceil(bb_h * scale))
            num_layers_est = int(np.ceil((z_max - z_min) / layer_height))

            multiplier = 5 if saturation_mode == "shell" else 2
            mem_mb = ox * oy * multiplier / (1024 * 1024)
            mem_str = f"{mem_mb:.0f} MB" if mem_mb < 1024 else f"{mem_mb / 1024:.1f} GB"

            reply = QMessageBox.question(
                self, "开始切片？",
                f"输出分辨率: {ox}×{oy} px  ({target_dpi} dpi)\n"
                f"预计每层内存: ~{mem_str}\n"
                f"共 {num_layers_est} 层（层厚 {layer_height}mm）\n\n"
                f"确认执行切片？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        except Exception as e:
            QMessageBox.warning(self, "预估失败", f"无法预估内存:\n{e}")
            return

        # ── 选择保存位置 ──
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存切片文件",
            zip_base + ".zip",
            "ZIP 文件 (*.zip)",
        )
        if not save_path:
            return
        output_zip = save_path

        params = {
            "mesh_path": self._mesh_path,
            "layer_height": layer_height,
            "target_dpi": target_dpi,
            "margin_ratio": margin_ratio,
            "saturation_mode": saturation_mode,
            "shell_width_mm": shell_width_mm,
            "base_saturation": base_saturation,
            "output_zip": output_zip,
            "image_format": self.combo_format.currentText(),
            "instances": self.model_viewer.get_instances(),
        }

        # 启动后台切片
        self._worker = SlicingWorker(params)
        self._worker.progress.connect(self.progress_bar.setValue)
        self._worker.layer_done.connect(self._on_layer_done)
        self._worker.finished.connect(self._on_finished)
        self._worker.error_occurred.connect(self._on_error)

        self._worker.start()

        # 切换 UI 状态
        self._set_running(True)

    def _on_stop(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self.label_status.setText("正在停止...")

    def _on_layer_done(self, idx: int):
        self.label_status.setText(f"已处理: 第 {idx + 1} 层")

    def _on_finished(self, zip_path: str):
        self._set_running(False)
        QMessageBox.information(self, "完成", f"切片已完成!\n输出: {zip_path}")
        self.progress_bar.reset()

    def _on_error(self, err_msg: str):
        self._set_running(False)
        QMessageBox.critical(self, "错误", f"切片过程出错:\n{err_msg}")

    def _set_running(self, running: bool):
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.btn_browse.setEnabled(not running)
        self.edit_layer_height.setEnabled(not running)
        self.combo_dpi.setEnabled(not running)
        self.combo_face.setEnabled(not running)
        self.edit_margin.setEnabled(not running)
        self.edit_zip_name.setEnabled(not running)
        self.radio_binary.setEnabled(not running)
        self.radio_shell.setEnabled(not running)
        self.edit_shell_width.setEnabled(not running)
        self.edit_base_sat.setEnabled(not running)
        self.combo_format.setEnabled(not running)

        if not running:
            self.progress_bar.reset()
            self.label_status.setText("就绪")

    #重写鼠标事件（仅标题栏区域可拖拽）
    def mousePressEvent(self, event):
        if event.position().y() <= 35:
            self._dragging = True
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if getattr(self, '_dragging', False):
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self._dragging = False

    #重写关闭窗口，缩小窗口事件
    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            reply = QMessageBox.question(
                self, "确认退出", "切片正在进行中，确定退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            self._worker.stop()
        event.accept()

if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 9))
    app.setWindowIcon(QIcon("Title.png"))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())