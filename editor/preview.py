"""320×192 实时预览面板（WYSIWYG）。

复刻框架 video_preview.py:636-643 (_render_preview_frame) 的裁剪→缩放语义，
共用 frame_ops.crop_and_resize，确保「预览 == 导出」。
额外提供 170px 安全线与「屏外 padding 遮罩」开关（本项目专属）。
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:  # pragma: no cover
    HAS_CV2 = False

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QCheckBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap

from . import frame_ops


class PreviewPane(QWidget):
    """展示裁剪+缩放后的 320×192 结果（默认放大 2× 便于观看）。"""

    def __init__(self, target_w: int = 320, target_h: int = 192,
                 visible_h: int = 170, zoom: int = 2, parent=None):
        super().__init__(parent)
        self.target_w = target_w
        self.target_h = target_h
        self.visible_h = visible_h
        self.zoom = zoom
        self._last: Optional[Tuple[np.ndarray, int, Tuple[int, int, int, int]]] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        title = QLabel(f"预览（{target_w}×{target_h}，实际输出）")
        title.setStyleSheet("color:#aaa; font-size:12px;")
        layout.addWidget(title)

        self.image = QLabel("无预览")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setFixedSize(target_w * zoom, target_h * zoom)
        self.image.setStyleSheet("background:#000; border-radius:4px; color:#666;")
        layout.addWidget(self.image, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.chk_mask = QCheckBox(f"屏外 padding 遮罩（仅看可视 {target_w}×{visible_h}）")
        self.chk_mask.setStyleSheet("color:#aaa; font-size:12px;")
        self.chk_mask.toggled.connect(lambda _=False: self._repaint())
        layout.addWidget(self.chk_mask)
        layout.addStretch()

    def render(self, source_frame: Optional[np.ndarray], rotation: int,
               cropbox: Tuple[int, int, int, int]):
        """根据源帧 + 旋转 + 裁剪框刷新预览。"""
        if source_frame is None or not HAS_CV2:
            return
        self._last = (source_frame, rotation, cropbox)
        self._repaint()

    def _repaint(self):
        if self._last is None or not HAS_CV2:
            return
        source_frame, rotation, cropbox = self._last
        rotated = frame_ops.apply_rotation(source_frame, rotation)
        out = frame_ops.crop_and_resize(
            rotated, cropbox, self.target_w, self.target_h)  # 320×192 BGR

        disp = out.copy()
        # 屏外 padding 遮罩：压暗底部 [visible_h, target_h) 区域
        if self.chk_mask.isChecked() and self.visible_h < self.target_h:
            band = disp[self.visible_h:self.target_h, :]
            disp[self.visible_h:self.target_h, :] = cv2.convertScaleAbs(
                band, alpha=0.28)
        # 170 安全线（红色虚线）
        for seg_x in range(0, self.target_w, 12):
            cv2.line(disp, (seg_x, self.visible_h),
                     (min(seg_x + 6, self.target_w - 1), self.visible_h),
                     (0, 0, 255), 1)

        rgb = cv2.cvtColor(disp, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg).scaled(
            self.target_w * self.zoom, self.target_h * self.zoom,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation)
        self.image.setPixmap(pixmap)
