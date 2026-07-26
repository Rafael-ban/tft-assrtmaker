"""主窗口：装配裁剪视图 + 预览 + 时间轴，仅含「素材编辑」功能。

对应框架 gui/main_window.py 的「素材制作」页（ConfigPanel），但剥离了
固件烧录/论坛/SSH/模拟器/更新等脚手架，只保留视频素材编辑与导出。
"""
from __future__ import annotations

import os
from typing import Optional

import numpy as np

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QProgressDialog, QApplication,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QShortcut, QKeySequence

from .constants import (
    APP_NAME, APP_VERSION, DEFAULT_RESOLUTION, DEFAULT_OUTPUT_NAME,
    get_resolution_spec, safe_area_ratio,
)
from .crop_view import CropView
from .preview import PreviewPane
from .timeline import TimelineWidget
from .exporter import ExportWorker
from .ffmpeg_utils import check_environment
from .video_source import VideoSource


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1180, 760)

        self.resolution = DEFAULT_RESOLUTION
        spec = get_resolution_spec(self.resolution)
        self._src = VideoSource()
        self._video_path = ""
        self._index = 0
        self._cur_frame: Optional[np.ndarray] = None
        self._playing = False
        self._play_gen = None
        self._loop_bounds = (0, 0)
        self._worker: Optional[ExportWorker] = None
        self._progress: Optional[QProgressDialog] = None

        self.env = check_environment()

        self._build_ui(spec)
        self._wire()

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._play_tick)

        if not self.env.ok:
            self._warn_env()

    # ── UI ──
    def _build_ui(self, spec):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        top = QHBoxLayout()
        self.btn_open = QPushButton("打开视频…")
        self.btn_export = QPushButton("导出 loop.mp4…")
        self.btn_export.setEnabled(False)
        self.lbl_src = QLabel("未加载")
        self.lbl_src.setStyleSheet("color:#888;")
        top.addWidget(self.btn_open)
        top.addWidget(self.btn_export)
        top.addWidget(self.lbl_src, 1)
        env_ok = "✓ ffmpeg/libx264 就绪" if self.env.ok else "⚠ 环境不全"
        self.lbl_env = QLabel(env_ok)
        self.lbl_env.setStyleSheet(
            f"color:{'#4caf50' if self.env.ok else '#e0a030'};")
        top.addWidget(self.lbl_env)
        root.addLayout(top)

        mid = QHBoxLayout()
        self.crop = CropView(
            target_w=spec["width"], target_h=spec["height"],
            safe_ratio=safe_area_ratio(self.resolution))
        self.preview = PreviewPane(
            target_w=spec["width"], target_h=spec["height"],
            visible_h=spec["visible_height"], zoom=2)
        mid.addWidget(self.crop, 3)
        mid.addWidget(self.preview, 2)
        root.addLayout(mid, 1)

        self.timeline = TimelineWidget()
        root.addWidget(self.timeline)

    def _wire(self):
        self.btn_open.clicked.connect(self._open)
        self.btn_export.clicked.connect(self._export)
        self.crop.cropbox_changed.connect(self._on_cropbox)
        tl = self.timeline
        tl.play_pause_clicked.connect(self._toggle_play)
        tl.seek_requested.connect(self._seek)
        tl.prev_frame_clicked.connect(lambda: self._step(-1))
        tl.next_frame_clicked.connect(lambda: self._step(1))
        tl.goto_start_clicked.connect(lambda: self._seek(0))
        tl.goto_end_clicked.connect(
            lambda: self._seek(self._src.total_frames - 1))
        tl.set_in_point_clicked.connect(tl.set_in_point_to_current)
        tl.set_out_point_clicked.connect(tl.set_out_point_to_current)
        tl.rotation_value_changed.connect(self._on_rotation)

        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self._toggle_play)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, lambda: self._step(-1))
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, lambda: self._step(1))

    # ── 视频加载 ──
    def _open(self):
        start_dir = os.path.dirname(self._video_path) or os.getcwd()
        path, _ = QFileDialog.getOpenFileName(
            self, "选择源视频", start_dir,
            "视频 (*.mp4 *.mov *.mkv *.avi *.webm *.flv);;所有文件 (*.*)")
        if not path:
            return
        try:
            info = self._src.open(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "打开失败", f"无法解码视频：\n{e}")
            return
        self._video_path = path
        self._index = 0
        self.lbl_src.setText(
            f"{os.path.basename(path)}  {info.width}×{info.height}  "
            f"{info.fps:.2f}fps  {info.total_frames}帧")
        self.timeline.set_fps(info.fps)
        self.timeline.set_total_frames(info.total_frames)
        self.timeline.set_in_point(0)
        self.timeline.set_out_point(info.total_frames - 1)
        self.timeline.set_rotation(0)
        self.crop.set_rotation(0)
        self.btn_export.setEnabled(True)
        self._show_frame(0, reset_box=True)

    # ── 帧显示 ──
    def _show_frame(self, index: int, reset_box: bool = False):
        frame = self._src.get_frame(index)
        if frame is None:
            return
        self._index = index
        self._cur_frame = frame
        self.crop.set_frame(frame, reset_box=reset_box)
        self.preview.render(frame, self.crop.get_rotation(),
                            tuple(self.crop.cropbox))
        self.timeline.set_current_frame(index)

    def _seek(self, index: int):
        self._stop_play()
        index = max(0, min(index, max(0, self._src.total_frames - 1)))
        self._show_frame(index)

    def _step(self, delta: int):
        self._stop_play()
        self._show_frame(self._index + delta)

    def _on_cropbox(self, x: int, y: int, w: int, h: int):
        if self._cur_frame is not None:
            self.preview.render(self._cur_frame, self.crop.get_rotation(),
                                (x, y, w, h))

    def _on_rotation(self, degrees: int):
        self._stop_play()
        self.crop.set_rotation(degrees)
        if self._cur_frame is not None:
            self.preview.render(self._cur_frame, degrees,
                                tuple(self.crop.cropbox))

    # ── 播放（顺序解码，循环 [入点, 出点]）──
    def _toggle_play(self):
        if self._src.total_frames <= 0:
            return
        self._stop_play() if self._playing else self._start_play()

    def _start_play(self):
        inp, out = self.timeline.get_in_point(), self.timeline.get_out_point()
        self._loop_bounds = (inp, out)
        start = self._index if inp <= self._index < out else inp
        self._play_gen = self._src.iter_frames(start, out + 1)
        self._playing = True
        self.timeline.set_playing(True)
        self._timer.start(max(1, round(1000 / max(1.0, self._src.fps))))

    def _stop_play(self):
        if self._timer.isActive():
            self._timer.stop()
        self._playing = False
        self._play_gen = None
        self.timeline.set_playing(False)

    def _play_tick(self):
        if self._play_gen is None:
            return
        try:
            idx, frame = next(self._play_gen)
        except StopIteration:
            inp, out = self._loop_bounds       # 循环回到入点
            self._play_gen = self._src.iter_frames(inp, out + 1)
            try:
                idx, frame = next(self._play_gen)
            except StopIteration:
                self._stop_play()
                return
        self._index = idx
        self._cur_frame = frame
        self.crop.set_frame(frame)
        self.preview.render(frame, self.crop.get_rotation(),
                            tuple(self.crop.cropbox))
        self.timeline.set_current_frame(idx)

    # ── 导出 ──
    def _export(self):
        if not self._video_path:
            return
        if not self.env.ok:
            self._warn_env()
            return
        self._stop_play()
        out_dir = os.path.dirname(self._video_path) or os.getcwd()
        path, _ = QFileDialog.getSaveFileName(
            self, "导出为", os.path.join(out_dir, DEFAULT_OUTPUT_NAME),
            "MP4 (*.mp4)")
        if not path:
            return

        inp = self.timeline.get_in_point()
        out = self.timeline.get_out_point()
        if out < inp:
            QMessageBox.warning(self, "范围无效", "出点必须不小于入点")
            return

        self._worker = ExportWorker(
            video_path=self._video_path,
            output_path=path,
            cropbox=self.crop.get_cropbox_in_rotated_space(),
            start_frame=inp,
            end_frame=out + 1,                 # 出点为「最后一帧」，故 +1（独占）
            fps=self._src.fps,
            rotation=self.crop.get_rotation(),
            resolution=self.resolution,
            ffmpeg_path=self.env.ffmpeg_path,
        )
        self._progress = QProgressDialog("正在导出…", "取消", 0, 100, self)
        self._progress.setWindowTitle("导出 loop.mp4")
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setAutoClose(True)
        self._progress.canceled.connect(self._worker.cancel)
        self._worker.progress.connect(self._on_export_progress)
        self._worker.completed.connect(self._on_export_done)
        self._worker.failed.connect(self._on_export_failed)
        self._worker.start()
        self._progress.show()

    def _on_export_progress(self, pct: int, msg: str):
        if self._progress:
            self._progress.setValue(pct)
            self._progress.setLabelText(msg)

    def _on_export_done(self, path: str):
        if self._progress:
            self._progress.setValue(100)
        QMessageBox.information(self, "完成", f"已导出：\n{path}")

    def _on_export_failed(self, err: str):
        if self._progress:
            self._progress.cancel()
        QMessageBox.critical(self, "导出失败", err)

    # ── 环境 ──
    def _warn_env(self):
        QMessageBox.warning(
            self, "环境检查",
            "以下依赖不完整，导出可能不可用：\n\n"
            + self.env.describe()
            + "\n\n建议：pip install av opencv-python numpy pillow imageio-ffmpeg")

    def closeEvent(self, event):
        self._stop_play()
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)
        self._src.close()
        super().closeEvent(event)
