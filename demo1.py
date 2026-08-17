import io
import zipfile

import trimesh
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_erosion


def slice_mesh_to_bitmaps(
    mesh_path="model.stl",
    layer_height=0.1,
    target_dpi=400,
    margin_ratio=0.05,
    first_layer_offset=0.5,
    saturation_mode="shell",
    shell_width_mm=1.0,
    base_saturation=128,
    output_zip="slices.zip",
    image_format="PNG",
    progress_callback=None,
    layer_callback=None,
    cancel_check=None,
    rotation=None,
    copy_offsets=None,
    instances=None,
):
    """
    将STL三维模型按层切片，输出每层的灰度位图，打包为ZIP文件。

    参数
    ----------
    mesh_path : str
        模型文件的路径。
    layer_height : float
        层高（毫米）。
    target_dpi : int
        目标DPI分辨率，如400、800、1200。输出像素尺寸自动匹配包围盒物理尺寸。
    margin_ratio : float
        模型尺寸之外保留的边距比例（相对于模型尺寸）。
    first_layer_offset : float
        第一层的高度偏移量（层高的倍数）。0.5表示第一层在z_min + 0.5*layer_height处。
    saturation_mode : str
        饱和度模式。可选 "binary"（二值）或 "shell"（壳体高饱和+内部统一低饱和）。
    shell_width_mm : float
        壳体边缘宽度（毫米）。仅在 saturation_mode="shell" 时生效。
    base_saturation : int
        内部统一饱和度灰度值（0~255）。仅在 saturation_mode="shell" 时生效。
    output_zip : str or None
        ZIP 输出路径。为 None 时保持逐张保存到磁盘的旧行为。
    image_format : str
        图片格式，如 "PNG"、"TIFF"、"BMP"。PIL 支持的格式均可。
    progress_callback : callable or None
        进度回调，签名为 func(percent: int)。
    layer_callback : callable or None
        每层完成回调，签名为 func(layer_index: int)。
    cancel_check : callable or None
        取消检查回调，签名为 func() -> bool。返回 True 表示请求取消。
    rotation : array-like or None
        4×4 旋转矩阵，加载后应用到模型（用于切换底面切片方向）。
    copy_offsets : list or None
        副本偏移列表 [(dx,dy,dz), ...]，把模型复制多份后合并切片（用于阵列复制）。
    """
    # 1. 加载模型
    mesh = trimesh.load(mesh_path)
    if mesh.is_empty:
        raise ValueError(f"模型 {mesh_path} 为空或无法加载")

    if instances:
        copies = []
        for inst in instances:
            m = trimesh.load(inst["source_path"])
            rot = np.array(inst["rotation"], dtype=np.float64)
            if not np.allclose(rot, np.eye(4)):
                m.apply_transform(rot)
            dx = float(inst["offset"][0])
            dy = float(inst["offset"][1])
            dz = float(inst["offset"][2])
            if dx or dy or dz:
                m.apply_translation([dx, dy, dz])
            copies.append(m)
        mesh = trimesh.util.concatenate(copies)
    else:
        if rotation is not None:
            mesh.apply_transform(np.array(rotation, dtype=np.float64))
        if copy_offsets:
            copies = []
            for off in copy_offsets:
                dx = float(off[0]); dy = float(off[1]); dz = float(off[2])
                m = mesh.copy()
                if dx or dy or dz:
                    m.apply_translation([dx, dy, dz])
                copies.append(m)
            mesh = trimesh.util.concatenate(copies)
    z_min, z_max = mesh.bounds[0][2], mesh.bounds[1][2]
    num_layers = int(np.ceil((z_max - z_min) / layer_height))
    print(f"总层数: {num_layers}")
    print(f"模型整体范围: X[{mesh.bounds[0][0]:.2f}, {mesh.bounds[1][0]:.2f}] "
          f"Y[{mesh.bounds[0][1]:.2f}, {mesh.bounds[1][1]:.2f}] "
          f"Z[{z_min:.2f}, {z_max:.2f}]")

    # ---- 第一遍：收集所有层截面的实际XY范围 ----
    all_sec_x_min, all_sec_x_max = float("inf"), float("-inf")
    all_sec_y_min, all_sec_y_max = float("inf"), float("-inf")
    sections_data = []  # 存储每层的截面数据

    for i in range(num_layers):
        z = z_min + first_layer_offset * layer_height + i * layer_height
        if z > z_max:
            break

        section = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
        if section is not None:
            planar, _to_2d = section.to_2D()
            # 收集这层所有顶点的坐标范围
            layer_polys = []
            for entity in planar.polygons_full:
                pts = np.array(entity.exterior.coords)
                layer_polys.append((pts, [np.array(h.coords) for h in entity.interiors]))
                all_sec_x_min = min(all_sec_x_min, pts[:, 0].min())
                all_sec_x_max = max(all_sec_x_max, pts[:, 0].max())
                all_sec_y_min = min(all_sec_y_min, pts[:, 1].min())
                all_sec_y_max = max(all_sec_y_max, pts[:, 1].max())
            sections_data.append((z, layer_polys))
        else:
            sections_data.append((z, []))

    # 用所有截面的实际范围计算包围盒（加边距）
    if all_sec_x_min == float("inf"):
        raise ValueError("所有层切片均为空，模型可能没有实体截面")

    margin_x = (all_sec_x_max - all_sec_x_min) * margin_ratio
    margin_y = (all_sec_y_max - all_sec_y_min) * margin_ratio
    bb_x_min = all_sec_x_min - margin_x
    bb_x_max = all_sec_x_max + margin_x
    bb_y_min = all_sec_y_min - margin_y
    bb_y_max = all_sec_y_max + margin_y

    bb_width = bb_x_max - bb_x_min
    bb_height = bb_y_max - bb_y_min
    scale = target_dpi / 25.4  # px/mm，由目标DPI决定
    dpi = target_dpi
    output_x = int(np.ceil(bb_width * scale))
    output_y = int(np.ceil(bb_height * scale))

    print(f"截面实际XY范围: X[{all_sec_x_min:.2f}, {all_sec_x_max:.2f}] "
          f"Y[{all_sec_y_min:.2f}, {all_sec_y_max:.2f}]")
    print(f"渲染包围盒: X[{bb_x_min:.2f}, {bb_x_max:.2f}] "
          f"Y[{bb_y_min:.2f}, {bb_y_max:.2f}]")
    print(f"缩放比例: {scale:.2f} px/mm  (目标DPI: {target_dpi})")
    print(f"输出像素尺寸: {output_x}×{output_y} px")

    # ---- 壳体模式预处理 ----
    if saturation_mode == "shell":
        shell_width_px = max(1, int(shell_width_mm * scale))
        print(f"饱和度模式: shell, 壳体宽度: {shell_width_mm}mm ≈ {shell_width_px}px, "
              f"内部饱和度: {base_saturation}")
    else:
        print(f"饱和度模式: binary（二值）")

    # ---- 第二遍：用统一的包围盒渲染所有层 ----
    total_layers = len(sections_data)
    slices_buffer = []  # 存储 (文件名, PNG字节数据)

    for idx, (z, layer_polys) in enumerate(sections_data):
        # 检查是否请求取消
        if cancel_check and cancel_check():
            print("切片已取消")
            return len(sections_data)

        img = Image.new("L", (output_x, output_y), 0)
        draw = ImageDraw.Draw(img)

        # 绘制二值掩膜
        for pts, interiors in layer_polys:
            pixels = []
            for pt in pts:
                px = int((pt[0] - bb_x_min) * scale)
                py = int((pt[1] - bb_y_min) * scale)
                py = output_y - py  # 翻转Y轴（图像坐标Y向下）
                pixels.append((px, py))

            if len(pixels) >= 3:
                draw.polygon(pixels, fill=255)

                for hole_pts in interiors:
                    hole_pixels = []
                    for pt in hole_pts:
                        px = int((pt[0] - bb_x_min) * scale)
                        py = int((pt[1] - bb_y_min) * scale)
                        py = output_y - py
                        hole_pixels.append((px, py))
                    if len(hole_pixels) >= 3:
                        draw.polygon(hole_pixels, fill=0)

        # ---- 饱和度处理 ----
        if saturation_mode == "shell":
            # 转为numpy布尔数组（True=实体区域）
            mask = np.array(img, dtype=bool)

            # 形态学腐蚀得到内部区域（腐蚀 shell_width_px 次）
            interior = mask.copy()
            for _ in range(shell_width_px):
                interior = binary_erosion(interior)
                # 如果内部全部消失则停止
                if not interior.any():
                    break

            # 壳体 = 原掩膜 - 内部
            shell = mask & (~interior)

            # 构建灰度图：壳体=255，内部=base_saturation，背景=0
            gray = np.zeros((output_y, output_x), dtype=np.uint8)
            gray[shell] = 255
            gray[interior] = base_saturation

            img = Image.fromarray(gray, mode="L")
            # 如果内部已全部腐蚀消失，整个实体都是壳体=纯白255
            if not interior.any() and mask.any():
                img = Image.fromarray(mask.astype(np.uint8) * 255, mode="L")

        # 保存图片到内存缓冲区
        ext = image_format.lower()
        buf = io.BytesIO()
        img.save(buf, format=image_format, dpi=(dpi, dpi))
        name = f"layer_{idx:04d}.{ext}"
        slices_buffer.append((name, buf.getvalue()))
        print(f"已渲染: {name} (高度 z={z:.3f} mm)")

        # 进度回调
        if layer_callback:
            layer_callback(idx)
        if progress_callback:
            progress_callback(int((idx + 1) / total_layers * 100))

    # ---- 写入ZIP文件 ----
    if output_zip is not None:
        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in slices_buffer:
                zf.writestr(name, data)
        zip_count = len(slices_buffer)
        print(f"已打包: {output_zip} ({zip_count} 张图片)")
    else:
        # 向后兼容：逐张写入磁盘
        for name, data in slices_buffer:
            with open(name, "wb") as f:
                f.write(data)

    print("所有切片完成！")
    return len(sections_data)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="STL 模型分层切片工具 — 输出灰度位图 ZIP",
    )
    parser.add_argument(
        "mesh", nargs="?", default="model.stl",
        help="STL 模型文件路径（默认: model.stl）",
    )
    parser.add_argument(
        "--height", type=float, default=0.1,
        help="层高，单位 mm（默认: 0.1）",
    )
    parser.add_argument(
        "--dpi", type=int, default=400,
        help="输出DPI（默认: 400）",
    )
    parser.add_argument(
        "--margin", type=float, default=0.05,
        help="包围盒边距比例（默认: 0.05）",
    )
    parser.add_argument(
        "--offset", type=float, default=0.5,
        help="第一层偏移量，层高的倍数（默认: 0.5）",
    )
    parser.add_argument(
        "--mode", choices=["binary", "shell"], default="shell",
        help="饱和度模式（默认: shell）",
    )
    parser.add_argument(
        "--shell-width", type=float, default=1.0,
        help="壳体宽度，单位 mm（默认: 1.0）",
    )
    parser.add_argument(
        "--base-sat", type=int, default=128,
        help="内部灰度值 0~255（默认: 128）",
    )
    parser.add_argument(
        "--format", dest="fmt", choices=["PNG", "TIFF", "BMP", "JPEG"], default="TIFF",
        help="输出图片格式（默认: TIFF）",
    )
    parser.add_argument(
        "--zip", dest="zip_name", default="slices.zip",
        help="输出 ZIP 文件名（默认: slices.zip）",
    )
    parser.add_argument(
        "--no-zip", action="store_true",
        help="不打包 ZIP，逐张保存图片到磁盘",
    )

    args = parser.parse_args()

    try:
        slice_mesh_to_bitmaps(
            mesh_path=args.mesh,
            layer_height=args.height,
            target_dpi=args.dpi,
            margin_ratio=args.margin,
            first_layer_offset=args.offset,
            saturation_mode=args.mode,
            shell_width_mm=args.shell_width,
            base_saturation=args.base_sat,
            output_zip=None if args.no_zip else args.zip_name,
            image_format=args.fmt,
        )
    except FileNotFoundError:
        print(f"错误：找不到模型文件 {args.mesh}")
    except Exception as e:
        print(f"运行出错: {e}")
