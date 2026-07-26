"""时间轴：帧滑块 + 单帧步进 + 入/出点 + 旋转控件（纯 PyQt6）。

复刻框架 gui/widgets/timeline.py（v2.1.4）的 TimelineSlider / TimelineWidget，
将其 qfluentwidgets 控件替换为原生 PyQt6，功能一致：
- 入点/出点三角标记 + 选区高亮 + 当前帧游标   timeline.py:108-163
- seek 节流（33ms）                            timeline.py:29-34,171-196
- |< < 播放 > >| / 设入点 / 设出点 / 旋转       timeline.py:233-307
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSpinBox,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QMouseEvent

from .constants import frame_to_timecode


class TimelineSlider(QWidget):
    """自定义时间轴滑块（入/出点 + 当前帧）。"""

    seek_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._total_frames = 1
        self._current_frame = 0
        self._in_point = 0
        self._out_point = 0
        self._dragging = False

        # 拖拽节流，避免每像素触发昂贵 seek（timeline.py:29-34）
        self._pending_seek_frame = -1
        self._seek_timer = QTimer(self)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.setInterval(33)
        self._seek_timer.timeout.connect(self._emit_pending_seek)

        self._margin = 12
        self._track_height = 26
        self.setMinimumHeight(52)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    @property
    def _divisor(self) -> int:
        return max(1, self._total_frames - 1)

    def set_total_frames(self, count: int):
        self._total_frames = max(1, count)
        m = max(0, self._total_frames - 1)
        self._out_point = m if self._out_point == 0 else min(self._out_point, m)
        self._in_point = min(self._in_point, m)
        self._current_frame = min(self._current_frame, m)
        self.update()

    def set_current_frame(self, index: int):
        self._current_frame = max(0, min(index, self._total_frames - 1))
        self.update()

    def set_in_point(self, frame: int):
        self._in_point = max(0, min(frame, self._total_frames - 1))
        if self._in_point > self._out_point:
            self._out_point = self._in_point
        self.update()

    def set_out_point(self, frame: int):
        self._out_point = max(0, min(frame, self._total_frames - 1))
        if self._out_point < self._in_point:
            self._in_point = self._out_point
        self.update()

    def get_in_point(self) -> int:
        return self._in_point

    def get_out_point(self) -> int:
        return self._out_point

    def _frame_to_x(self, frame: int) -> int:
        tw = self.width() - 2 * self._margin
        return int(self._margin + (frame / self._divisor) * tw)

    def _x_to_frame(self, x: int) -> int:
        tw = self.width() - 2 * self._margin
        if tw <= 0:
            return 0
        ratio = max(0.0, min(1.0, (x - self._margin) / tw))
        return int(round(ratio * self._divisor))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        track_y = (h - self._track_height) // 2
        tw = w - 2 * self._margin

        p.fillRect(0, 0, w, h, QColor(30, 30, 30))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(48, 48, 48)))
        p.drawRoundedRect(QRect(self._margin, track_y, tw, self._track_height), 4, 4)

        in_x = self._frame_to_x(self._in_point)
        out_x = self._frame_to_x(self._out_point)
        if out_x > in_x:
            p.setBrush(QBrush(QColor(66, 133, 244, 150)))
            p.drawRoundedRect(QRect(in_x, track_y, out_x - in_x, self._track_height), 4, 4)

        # 入点三角（绿，向上）
        p.setBrush(QBrush(QColor(86, 185, 90)))
        p.drawPolygon([QPoint(in_x - 8, track_y - 8),
                       QPoint(in_x + 8, track_y - 8), QPoint(in_x, track_y)])
        # 出点三角（红，向下）
        by = track_y + self._track_height
        p.setBrush(QBrush(QColor(254, 77, 64)))
        p.drawPolygon([QPoint(out_x - 8, by + 8),
                       QPoint(out_x + 8, by + 8), QPoint(out_x, by)])

        # 当前帧游标（白线 + 圆点）
        cx = self._frame_to_x(self._current_frame)
        cy = track_y + self._track_height // 2
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.drawLine(cx, track_y - 10, cx, track_y + self._track_height + 10)
        p.setBrush(QBrush(QColor(255, 255, 255)))
        p.setPen(QPen(QColor(86, 154, 243), 2))
        p.drawEllipse(QPoint(cx, cy), 6, 6)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self.seek_requested.emit(self._x_to_frame(int(event.position().x())))

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging:
            frame = self._x_to_frame(int(event.position().x()))
            self._current_frame = max(0, min(frame, self._total_frames - 1))
            self.update()
            self._pending_seek_frame = self._current_frame
            if not self._seek_timer.isActive():
                self._seek_timer.start()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._seek_timer.stop()
            if self._pending_seek_frame >= 0:
                self.seek_requested.emit(self._pending_seek_frame)
                self._pending_seek_frame = -1

    def _emit_pending_seek(self):
        if self._pending_seek_frame >= 0:
            self.seek_requested.emit(self._pending_seek_frame)
            self._pending_seek_frame = -1


class TimelineWidget(QWidget):
    """播放控制 + 时间轴 + 旋转。"""

    play_pause_clicked = pyqtSignal()
    seek_requested = pyqtSignal(int)
    prev_frame_clicked = pyqtSignal()
    next_frame_clicked = pyqtSignal()
    goto_start_clicked = pyqtSignal()
    goto_end_clicked = pyqtSignal()
    set_in_point_clicked = pyqtSignal()
    set_out_point_clicked = pyqtSignal()
    rotation_value_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._total_frames = 1
        self._current_frame = 0
        self._fps = 30.0
        self._init_ui()
        self._connect()

    def _init_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(6, 6, 6, 6)
        main.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(6)

        def btn(text, width, tip):
            b = QPushButton(text)
            b.setFixedWidth(width)
            b.setToolTip(tip)
            return b

        self.btn_goto_start = btn("|<", 36, "跳到开始")
        self.btn_prev_frame = btn("<", 36, "上一帧 (←)")
        self.btn_play_pause = btn("播放", 56, "播放/暂停 (Space)")
        self.btn_next_frame = btn(">", 36, "下一帧 (→)")
        self.btn_goto_end = btn(">|", 36, "跳到结束")
        self.btn_set_in = btn("[ 入点", 60, "设置入点为当前帧")
        self.btn_set_out = btn("] 出点", 60, "设置出点为当前帧（单帧选结束位置）")
        for b in (self.btn_goto_start, self.btn_prev_frame, self.btn_play_pause,
                  self.btn_next_frame, self.btn_goto_end):
            row.addWidget(b)
        row.addSpacing(8)
        row.addWidget(self.btn_set_in)
        row.addWidget(self.btn_set_out)
        row.addSpacing(8)

        self.label_frame = QLabel("0 / 0")
        self.label_frame.setMinimumWidth(90)
        self.label_tc = QLabel("00:00:00")
        self.label_tc.setMinimumWidth(72)
        self.label_fps = QLabel("30.0 fps")
        row.addWidget(self.label_frame)
        row.addWidget(self.label_tc)
        row.addWidget(self.label_fps)
        row.addStretch()

        self.btn_rot_ccw = btn("↺", 34, "逆时针旋转 90°")
        self.spin_rot = QSpinBox()
        self.spin_rot.setRange(0, 359)
        self.spin_rot.setSingleStep(90)
        self.spin_rot.setSuffix("°")
        self.spin_rot.setWrapping(True)
        self.spin_rot.setFixedWidth(84)
        self.spin_rot.setKeyboardTracking(False)
        self.spin_rot.setToolTip("旋转角度（0/90/180/270）")
        self.btn_rot_cw = btn("↻", 34, "顺时针旋转 90°")
        row.addWidget(self.btn_rot_ccw)
        row.addWidget(self.spin_rot)
        row.addWidget(self.btn_rot_cw)

        self.slider = TimelineSlider()
        main.addLayout(row)
        main.addWidget(self.slider)
        self.setMinimumHeight(96)
        self.setMaximumHeight(140)

    def _connect(self):
        self.btn_goto_start.clicked.connect(self.goto_start_clicked.emit)
        self.btn_prev_frame.clicked.connect(self.prev_frame_clicked.emit)
        self.btn_play_pause.clicked.connect(self.play_pause_clicked.emit)
        self.btn_next_frame.clicked.connect(self.next_frame_clicked.emit)
        self.btn_goto_end.clicked.connect(self.goto_end_clicked.emit)
        self.btn_set_in.clicked.connect(self.set_in_point_clicked.emit)
        self.btn_set_out.clicked.connect(self.set_out_point_clicked.emit)
        self.slider.seek_requested.connect(self.seek_requested.emit)
        self.btn_rot_ccw.clicked.connect(lambda: self._step_rot(-90))
        self.btn_rot_cw.clicked.connect(lambda: self._step_rot(90))
        self.spin_rot.valueChanged.connect(self.rotation_value_changed.emit)

    # ── 对外 API ──
    def set_total_frames(self, count: int):
        self._total_frames = max(1, count)
        self.slider.set_total_frames(count)
        self._update_label()

    def set_current_frame(self, index: int):
        self._current_frame = max(0, min(index, self._total_frames - 1))
        self.slider.set_current_frame(index)
        self._update_label()

    def set_in_point(self, frame: int):
        self.slider.set_in_point(frame)

    def set_out_point(self, frame: int):
        self.slider.set_out_point(frame)

    def set_in_point_to_current(self):
        self.slider.set_in_point(self._current_frame)

    def set_out_point_to_current(self):
        self.slider.set_out_point(self._current_frame)

    def get_in_point(self) -> int:
        return self.slider.get_in_point()

    def get_out_point(self) -> int:
        return self.slider.get_out_point()

    def set_fps(self, fps: float):
        self._fps = fps
        self.label_fps.setText(f"{fps:.1f} fps")
        self._update_label()

    def set_playing(self, is_playing: bool):
        self.btn_play_pause.setText("暂停" if is_playing else "播放")

    def set_rotation(self, degrees: int):
        self.spin_rot.blockSignals(True)
        self.spin_rot.setValue(degrees % 360)
        self.spin_rot.blockSignals(False)

    def _step_rot(self, delta: int):
        self.spin_rot.setValue((self.spin_rot.value() + delta) % 360)

    def _update_label(self):
        self.label_frame.setText(f"{self._current_frame} / {self._total_frames}")
        self.label_tc.setText(frame_to_timecode(self._current_frame, self._fps))
