"""后台切片线程 — 不阻塞 UI"""
from PySide6.QtCore import QThread, Signal
from demo1 import slice_mesh_to_bitmaps


class SlicingWorker(QThread):
    """在 QThread 中执行切片，通过信号通知 UI"""

    # 信号定义
    progress = Signal(int)            # 当前进度百分比 0~100
    layer_done = Signal(int)          # 刚完成第几层
    finished = Signal(str)            # 完成 → ZIP 文件路径
    error_occurred = Signal(str)      # 出错 → 错误信息

    def __init__(self, params: dict):
        super().__init__()
        self.params = params
        self._stopped = False

    def run(self):
        """入口：在后台线程中执行切片"""
        try:
            result = slice_mesh_to_bitmaps(
                mesh_path=self.params["mesh_path"],
                layer_height=self.params.get("layer_height", 0.1),
                target_dpi=self.params.get("target_dpi", 400),
                margin_ratio=self.params.get("margin_ratio", 0.05),
                first_layer_offset=self.params.get("first_layer_offset", 0.5),
                saturation_mode=self.params.get("saturation_mode", "shell"),
                shell_width_mm=self.params.get("shell_width_mm", 1.0),
                base_saturation=self.params.get("base_saturation", 128),
                output_zip=self.params.get("output_zip", "slices.zip"),
                image_format=self.params.get("image_format", "PNG"),
                progress_callback=self._on_progress,
                layer_callback=self._on_layer,
                cancel_check=self._is_stopped,
                rotation=self.params.get("rotation", None),
                copy_offsets=self.params.get("copy_offsets", None),
                instances=self.params.get("instances", None),
            )
            if not self._stopped:
                self.finished.emit(self.params.get("output_zip", "slices.zip"))
        except Exception as e:
            self.error_occurred.emit(str(e))

    def stop(self):
        """请求停止切片"""
        self._stopped = True

    def _is_stopped(self) -> bool:
        return self._stopped

    def _on_progress(self, percent: int):
        self.progress.emit(percent)

    def _on_layer(self, idx: int):
        self.layer_done.emit(idx)