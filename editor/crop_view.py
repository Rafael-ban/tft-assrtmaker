"""裁剪视图：在源帧上叠加一个 5:3 等比锁定、可移动/等比缩放的裁剪框。

裁剪框逻辑复刻框架真实源码 gui/widgets/video_preview.py（v2.1.4）：
- cropbox = [x, y, w, h]（旋转后坐标系）             video_preview.py:80
- _init_cropbox：初始化为最大 5:3 框的 75%，居中留移动空间
  （框架注释明确记录：旧写法=初始化为最大尺寸→无移动空间[无效]；
    新写法=75%[有效]）                                video_preview.py:466-493
- _bound_cropbox：夹取到视频范围、保持宽高比、最小尺寸   video_preview.py:495-512
- 等比锁定 resize：new_h = int(new_w / aspect)          video_preview.py:1171-1187
- _get_drag_mode / _display_to_rotated_coords           video_preview.py:1114-1148
- cv2.rectangle 画框 + 角 handle                         video_preview.py:589-599

本精简版用原生 PyQt6 QLabel 显示（不含框架的 GL/后台线程/叠加UI），
并新增：框外压暗、170px 安全区分界线、双尺寸读数（对齐截图参考.png）。
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:  # pragma: no cover
    HAS_CV2 = False

from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QImage, QPixmap, QMouseEvent, QKeyEvent

from . import frame_ops


class CropView(QWidget):
    """5:3 等比锁定裁剪框视图。"""

    cropbox_changed = pyqtSignal(int, int, int, int)  # x, y, w, h（旋转后坐标）

    DRAG_NONE = 0
    DRAG_MOVE = 1
    DRAG_RESIZE_TL = 2
    DRAG_RESIZE_TR = 3
    DRAG_RESIZE_BL = 4
    DRAG_RESIZE_BR = 5

    def __init__(self, target_w: int = 320, target_h: int = 192,
                 safe_ratio: float = 170 / 192, parent=None):
        super().__init__(parent)
        self.target_width = target_w
        self.target_height = target_h
        self.target_aspect_ratio = target_w / target_h
        self.safe_ratio = safe_ratio

        self.current_frame: Optional[np.ndarray] = None  # 原始 BGR 帧
        self.video_width = 0
        self.video_height = 0
        self._rotation = 0
        self.cropbox = [0, 0, target_w, target_h]

        self.display_scale = 1.0
        self.display_offset_x = 0
        self.display_offset_y = 0

        self.drag_mode = self.DRAG_NONE
        self.drag_start_pos: Optional[QPoint] = None
        self.drag_start_cropbox: list = []
        self.handle_size = 15

        self._setup_ui()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.video_label = QLabel("未加载视频")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setMinimumSize(360, 240)
        self.video_label.setStyleSheet(
            "background-color:#141414; color:#888; border-radius:6px;")
        self.video_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video_label.setMouseTracking(True)
        layout.addWidget(self.video_label)

        # 左上角双尺寸读数（对齐 截图参考.png 的两行绿字）
        self.readout = QLabel(self.video_label)
        self.readout.setStyleSheet(
            "color:#4dff4d; background:transparent; font-size:13px;"
            "font-weight:600; padding:2px;")
        self.readout.move(10, 8)
        self.readout.setText("")

    # ── 帧 / 旋转 ──
    def set_frame(self, frame: Optional[np.ndarray], reset_box: bool = False):
        """设置当前显示帧（原始 BGR）。reset_box=True 时重置裁剪框。"""
        if frame is None:
            return
        new_size = (frame.shape[1], frame.shape[0])
        size_changed = (new_size != (self.video_width, self.video_height))
        self.current_frame = frame
        self.video_width, self.video_height = new_size
        if reset_box or size_changed or self.cropbox[2] <= 0:
            self._init_cropbox()
        self._refresh()

    def set_rotation(self, degrees: int):
        degrees %= 360
        if degrees == self._rotation:
            return
        self._rotation = degrees
        if self.video_width and self.video_height:
            self._init_cropbox()  # 精简版：旋转后重置裁剪框（旋转为可选功能）
        self._refresh()

    def get_rotation(self) -> int:
        return self._rotation

    def get_cropbox_in_rotated_space(self) -> Tuple[int, int, int, int]:
        """导出用裁剪框（旋转后坐标系，无需坐标变换）。

        同 video_preview.get_cropbox_in_rotated_space()：视频导出直接用旋转空间坐标。
        """
        return tuple(self.cropbox)

    # ── 裁剪框数学（复刻 video_preview.py）──
    def _rotated_video_size(self) -> Tuple[int, int]:
        return frame_ops.rotated_size(
            self.video_width, self.video_height, self._rotation)

    def _init_cropbox(self):
        """初始化为最大 5:3 框的 75%，居中。见 video_preview.py:466-493。"""
        rw, rh = self._rotated_video_size()
        if rw <= 0 or rh <= 0:
            return
        ar = self.target_aspect_ratio
        if rw / rh > ar:
            max_h = rh
            max_w = int(max_h * ar)
        else:
            max_w = rw
            max_h = int(max_w / ar)
        crop_w = int(max_w * 0.75)
        crop_h = int(crop_w / ar)
        x = (rw - crop_w) // 2
        y = (rh - crop_h) // 2
        self.cropbox = [x, y, crop_w, crop_h]
        self._emit_changed()

    def _bound_cropbox(self):
        """夹取到旋转后视频范围、保持宽高比、最小尺寸。见 video_preview.py:495-512。"""
        rw, rh = self._rotated_video_size()
        x, y, w, h = self.cropbox
        if w > rw:
            w = rw
            h = int(w / self.target_aspect_ratio)
        if h > rh:
            h = rh
            w = int(h * self.target_aspect_ratio)
        w = max(w, 90)
        h = max(h, int(90 / self.target_aspect_ratio))
        x = max(0, min(x, rw - w))
        y = max(0, min(y, rh - h))
        self.cropbox = [x, y, w, h]

    def _emit_changed(self):
        x, y, w, h = self.cropbox
        self.cropbox_changed.emit(x, y, w, h)
        self.readout.setText(
            f"当前框选大小：{w}×{h}\n"
            f"最终目标大小：{self.target_width}×{self.target_height}\n"
            f"虚线以下为屏外padding(不显示)"
        )
        self.readout.adjustSize()

    # ── 显示 ──
    def _refresh(self):
        if self.current_frame is None or not HAS_CV2:
            return
        rotated = frame_ops.apply_rotation(self.current_frame, self._rotation)
        x, y, w, h = self.cropbox

        # 框外压暗（同截图外区域变暗的视觉；框内保持原亮度）
        disp = cv2.convertScaleAbs(rotated, alpha=0.45, beta=0)
        disp[y:y + h, x:x + w] = rotated[y:y + h, x:x + w]

        # 绿色裁剪框（video_preview.py:589）
        cv2.rectangle(disp, (x, y), (x + w, y + h), (0, 255, 0), 2)
        # 四角 handle（video_preview.py:592-599）
        hs = 8
        for px, py in [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]:
            cv2.rectangle(disp, (px - hs, py - hs), (px + hs, py + hs),
                          (0, 200, 255), -1)
        # 170px 安全区分界线（虚线；下方 22px 为设备不显示的 padding）
        sy = y + int(h * self.safe_ratio)
        for seg_x in range(x, x + w, 12):
            cv2.line(disp, (seg_x, sy), (min(seg_x + 6, x + w), sy),
                     (0, 180, 255), 1)

        rgb = cv2.cvtColor(disp, cv2.COLOR_BGR2RGB)
        fh, fw, ch = rgb.shape
        qimg = QImage(rgb.data, fw, fh, ch * fw, QImage.Format.Format_RGB888)
        label_size = self.video_label.size()
        pixmap = QPixmap.fromImage(qimg).scaled(
            label_size, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)

        rw, _ = self._rotated_video_size()
        self.display_scale = pixmap.width() / rw if rw > 0 else 1.0
        self.display_offset_x = (label_size.width() - pixmap.width()) // 2
        self.display_offset_y = (label_size.height() - pixmap.height()) // 2
        self.video_label.setPixmap(pixmap)

    # ── 鼠标坐标 → 旋转后视频坐标（video_preview.py:1114-1131）──
    def _display_to_rotated_coords(self, pos: QPoint) -> Tuple[int, int]:
        label_pos = self.video_label.mapFrom(self, pos)
        if self.display_scale <= 0:
            return (0, 0)
        rx = int((label_pos.x() - self.display_offset_x) / self.display_scale)
        ry = int((label_pos.y() - self.display_offset_y) / self.display_scale)
        return (rx, ry)

    def _get_drag_mode(self, vx: int, vy: int) -> int:
        x, y, w, h = self.cropbox
        hs = self.handle_size
        if abs(vx - x) < hs and abs(vy - y) < hs:
            return self.DRAG_RESIZE_TL
        if abs(vx - (x + w)) < hs and abs(vy - y) < hs:
            return self.DRAG_RESIZE_TR
        if abs(vx - x) < hs and abs(vy - (y + h)) < hs:
            return self.DRAG_RESIZE_BL
        if abs(vx - (x + w)) < hs and abs(vy - (y + h)) < hs:
            return self.DRAG_RESIZE_BR
        if x <= vx <= x + w and y <= vy <= y + h:
            return self.DRAG_MOVE
        return self.DRAG_NONE

    def mousePressEvent(self, event: QMouseEvent):
        if (event.button() == Qt.MouseButton.LeftButton
                and self.current_frame is not None):
            rx, ry = self._display_to_rotated_coords(event.pos())
            self.drag_mode = self._get_drag_mode(rx, ry)
            if self.drag_mode != self.DRAG_NONE:
                self.drag_start_pos = event.pos()
                self.drag_start_cropbox = self.cropbox.copy()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.drag_mode != self.DRAG_NONE and self.drag_start_pos is not None:
            crx, cry = self._display_to_rotated_coords(event.pos())
            srx, sry = self._display_to_rotated_coords(self.drag_start_pos)
            dx, dy = crx - srx, cry - sry
            sx, sy, sw, sh = self.drag_start_cropbox
            ar = self.target_aspect_ratio
            # 等比锁定 resize：宽驱动，高由宽高比推出（video_preview.py:1171-1187）
            if self.drag_mode == self.DRAG_MOVE:
                self.cropbox = [sx + dx, sy + dy, sw, sh]
            elif self.drag_mode == self.DRAG_RESIZE_BR:
                new_w = sw + dx
                self.cropbox = [sx, sy, new_w, int(new_w / ar)]
            elif self.drag_mode == self.DRAG_RESIZE_TL:
                new_w = sw - dx
                new_h = int(new_w / ar)
                self.cropbox = [sx + (sw - new_w), sy + (sh - new_h), new_w, new_h]
            elif self.drag_mode == self.DRAG_RESIZE_TR:
                new_w = sw + dx
                new_h = int(new_w / ar)
                self.cropbox = [sx, sy + (sh - new_h), new_w, new_h]
            elif self.drag_mode == self.DRAG_RESIZE_BL:
                new_w = sw - dx
                new_h = int(new_w / ar)
                self.cropbox = [sx + (sw - new_w), sy, new_w, new_h]
            self._bound_cropbox()
            self._emit_changed()
            self._refresh()
        elif self.current_frame is not None:
            rx, ry = self._display_to_rotated_coords(event.pos())
            mode = self._get_drag_mode(rx, ry)
            cursors = {
                self.DRAG_RESIZE_TL: Qt.CursorShape.SizeFDiagCursor,
                self.DRAG_RESIZE_BR: Qt.CursorShape.SizeFDiagCursor,
                self.DRAG_RESIZE_TR: Qt.CursorShape.SizeBDiagCursor,
                self.DRAG_RESIZE_BL: Qt.CursorShape.SizeBDiagCursor,
                self.DRAG_MOVE: Qt.CursorShape.SizeAllCursor,
            }
            self.setCursor(cursors.get(mode, Qt.CursorShape.ArrowCursor))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_mode = self.DRAG_NONE
            self.drag_start_pos = None
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        """WASD 微调裁剪框位置（同 video_preview.py:1244-1251）。"""
        if self.current_frame is None:
            super().keyPressEvent(event)
            return
        step = 10
        key = event.key()
        if key == Qt.Key.Key_W:
            self.cropbox[1] -= step
        elif key == Qt.Key.Key_S:
            self.cropbox[1] += step
        elif key == Qt.Key.Key_A:
            self.cropbox[0] -= step
        elif key == Qt.Key.Key_D:
            self.cropbox[0] += step
        else:
            super().keyPressEvent(event)
            return
        self._bound_cropbox()
        self._emit_changed()
        self._refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.current_frame is not None:
            self._refresh()
