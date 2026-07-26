"""基于 PyAV 的帧精确视频源。

核心 seek+decode 逻辑复刻框架真实实现（frame-accurate，替代 cv2.VideoCapture
的不精确随机 seek）：
- core/optimized_processor.py:117-152 (extract_single_frame)
- core/export_service.py:268-296 (导出解码循环)

要点：`container.seek(target_pts, backward=True)` 先定位到目标帧之前的关键帧，
再解码前进，用 `round(pts*time_base*fps)` 判定帧号直到 >= 目标帧。
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Iterator, Optional, Tuple

import numpy as np

try:
    import av  # PyAV
    HAS_AV = True
except ImportError:  # pragma: no cover
    HAS_AV = False


@dataclass
class SourceInfo:
    width: int
    height: int
    fps: float
    total_frames: int
    duration: float


class VideoSource:
    """持有一个 PyAV 容器，提供帧精确读取与顺序遍历。"""

    def __init__(self, cache_size: int = 64):
        self._container = None
        self._stream = None
        self._fps: float = 30.0
        self._time_base = None
        self.info: Optional[SourceInfo] = None
        self._cache: "OrderedDict[int, np.ndarray]" = OrderedDict()
        self._cache_size = cache_size

    # ── 生命周期 ──
    def open(self, path: str) -> SourceInfo:
        if not HAS_AV:
            raise RuntimeError("未安装 PyAV，无法解码视频")
        self.close()
        self._container = av.open(path)
        self._stream = self._container.streams.video[0]
        # 多线程解码（参考 optimized_processor.py:189 / export_service.py:244）
        self._stream.thread_type = "AUTO"

        self._fps = (float(self._stream.average_rate)
                     if self._stream.average_rate else 30.0)
        self._time_base = self._stream.time_base
        total = self._stream.frames or 0
        if total == 0 and self._stream.duration and self._time_base:
            total = round(float(self._stream.duration * self._time_base)
                          * self._fps)
        width = self._stream.width
        height = self._stream.height
        duration = (total / self._fps) if (total and self._fps) else 0.0

        self.info = SourceInfo(width, height, self._fps, total, duration)
        self._cache.clear()
        return self.info

    def close(self):
        if self._container is not None:
            try:
                self._container.close()
            except Exception:
                pass
        self._container = None
        self._stream = None
        self._cache.clear()

    # ── 属性 ──
    @property
    def fps(self) -> float:
        return self._fps

    @property
    def total_frames(self) -> int:
        return self.info.total_frames if self.info else 0

    @property
    def size(self) -> Tuple[int, int]:
        return (self.info.width, self.info.height) if self.info else (0, 0)

    # ── 帧读取 ──
    def _cache_put(self, index: int, frame: np.ndarray):
        self._cache[index] = frame
        self._cache.move_to_end(index)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    def get_frame(self, index: int) -> Optional[np.ndarray]:
        """返回指定帧的 BGR ndarray（帧精确）。

        实现同 optimized_processor.extract_single_frame：seek 到目标前关键帧，
        解码前进直到 round(pts*time_base*fps) >= index。
        """
        if self._container is None or self._stream is None or self.info is None:
            return None
        index = max(0, min(index, max(0, self.info.total_frames - 1)))
        if index in self._cache:
            self._cache.move_to_end(index)
            return self._cache[index]

        tb = self._time_base
        fps = self._fps
        try:
            if tb and fps > 0:
                target_pts = round((index / fps) / tb)
                self._container.seek(target_pts, stream=self._stream,
                                     backward=True)
            for av_frame in self._container.decode(self._stream):
                if av_frame.pts is not None and tb and fps > 0:
                    cur = round(float(av_frame.pts * tb) * fps)
                else:
                    cur = index
                if cur < index:
                    continue
                frame = av_frame.to_ndarray(format="bgr24")
                self._cache_put(cur, frame)
                return frame
        except Exception:
            return None
        return None

    def iter_frames(self, start: int, end: int) -> Iterator[Tuple[int, np.ndarray]]:
        """顺序产出 [start, end) 帧的 (帧号, BGR ndarray)，用于导出。

        复刻 export_service._export_video 解码循环（268-296）。
        """
        if self._container is None or self._stream is None or self.info is None:
            return
        tb = self._time_base
        fps = self._fps
        # 为导出使用独立解码位置：seek 到 start 前关键帧
        if start > 0 and tb and fps > 0:
            target_pts = round((start / fps) / tb)
            self._container.seek(target_pts, stream=self._stream, backward=True)
        idx_fallback = 0
        for av_frame in self._container.decode(self._stream):
            if av_frame.pts is not None and tb and fps > 0:
                cur = round(float(av_frame.pts * tb) * fps)
            else:
                cur = idx_fallback
            idx_fallback += 1
            if cur < start:
                continue
            if cur >= end:
                break
            yield cur, av_frame.to_ndarray(format="bgr24")
