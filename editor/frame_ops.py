"""共享帧处理：旋转、旋转后尺寸、裁剪+缩放。

被 crop_view / preview / exporter 三处共用，确保「预览所见 == 导出所得」。
逻辑复刻框架真实源码：
- 旋转: gui/widgets/video_preview.py:1039-1074 (_apply_rotation / _get_rotated_video_size)
- 裁剪+缩放: video_preview.py:636-643 (_render_preview_frame) 与
             core/export_service.py:311-312 (frame[ry:ry+rh, rx:rx+rw] + cv2.resize)
"""
from __future__ import annotations

from typing import Tuple

import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:  # pragma: no cover
    HAS_CV2 = False


def apply_rotation(frame: np.ndarray, degrees: int) -> np.ndarray:
    """对帧应用旋转（本精简版仅支持 0/90/180/270 正交角）。

    正交角用 cv2.rotate（比 warpAffine 快约 10 倍），同 video_preview._apply_rotation。
    """
    degrees %= 360
    if degrees == 0:
        return frame
    if degrees == 90:
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    if degrees == 180:
        return cv2.rotate(frame, cv2.ROTATE_180)
    if degrees == 270:
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return frame  # 非正交角不支持


def rotated_size(width: int, height: int, degrees: int) -> Tuple[int, int]:
    """旋转后的 (宽, 高)。同 video_preview._get_rotated_video_size。"""
    if degrees % 180 == 0:
        return (width, height)
    return (height, width)  # 90 / 270


def crop_and_resize(
    rotated_frame: np.ndarray,
    cropbox: Tuple[int, int, int, int],
    target_w: int,
    target_h: int,
) -> np.ndarray:
    """在（已旋转的）帧上按 cropbox 裁剪并缩放到目标尺寸。

    同 export_service.py:311-312 与 video_preview._render_preview_frame。
    cropbox 为旋转后坐标系下的 (x, y, w, h)。
    """
    x, y, w, h = cropbox
    hh, ww = rotated_frame.shape[:2]
    x = max(0, min(x, ww - 1))
    y = max(0, min(y, hh - 1))
    w = max(1, min(w, ww - x))
    h = max(1, min(h, hh - y))
    cropped = rotated_frame[y:y + h, x:x + w]
    return cv2.resize(cropped, (target_w, target_h), interpolation=cv2.INTER_AREA)
