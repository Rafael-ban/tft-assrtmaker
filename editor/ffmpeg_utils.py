"""ffmpeg 定位、编码器能力检测，以及基于 PyAV 的视频探测。

- ffmpeg 定位参考框架 `core/video_processor.py:find_ffmpeg`（优先自带二进制），
  本项目扩展为「系统 PATH → imageio-ffmpeg 自带二进制」两级回退。
- 探测参考框架 `core/optimized_processor.py:get_video_info`（PyAV，
  替代 cv2.VideoCapture）。当前环境无系统 ffprobe，故校验统一走 PyAV。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

try:
    import av  # PyAV
    HAS_AV = True
except ImportError:  # pragma: no cover
    HAS_AV = False


# ── ffmpeg / ffprobe 二进制定位 ─────────────────────────────
def find_ffmpeg() -> str:
    """返回可用的 ffmpeg 可执行文件路径（含 libx264 优先）。

    顺序：系统 PATH → imageio-ffmpeg 自带二进制（含 libx264）。
    """
    sys_ff = shutil.which("ffmpeg")
    if sys_ff:
        return sys_ff
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return ""


def find_ffprobe() -> str:
    """返回系统 ffprobe 路径（imageio-ffmpeg 不含 ffprobe，可能为空）。"""
    return shutil.which("ffprobe") or ""


def ffmpeg_has_encoder(ffmpeg_path: str, encoder: str = "libx264") -> bool:
    """检测指定 ffmpeg 是否含某编码器（默认 libx264）。"""
    if not ffmpeg_path:
        return False
    try:
        kwargs = dict(capture_output=True, text=True, timeout=15)
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        out = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-encoders"], **kwargs
        )
        return encoder in (out.stdout or "")
    except Exception:
        return False


# ── 视频探测（PyAV） ───────────────────────────────────────
@dataclass
class VideoInfo:
    width: int
    height: int
    fps: float
    total_frames: int
    duration: float
    codec: str
    profile: str
    pix_fmt: str


def probe_video(path: str, count_frames: bool = False) -> Optional[VideoInfo]:
    """用 PyAV 探测视频信息（替代 ffprobe）。

    Args:
        path: 视频路径
        count_frames: True 时精确遍历解码计帧（用于导出校验），
                      False 时优先用容器元数据 stream.frames。
    """
    if not HAS_AV:
        return None
    try:
        container = av.open(path)
        stream = container.streams.video[0]
        cc = stream.codec_context

        fps = float(stream.average_rate) if stream.average_rate else 0.0
        width = stream.width
        height = stream.height
        total = stream.frames or 0

        if count_frames or total == 0:
            total = sum(1 for _ in container.decode(stream))
            container.close()
            container = av.open(path)
            stream = container.streams.video[0]

        if total > 0 and fps > 0:
            duration = total / fps
        elif stream.duration and stream.time_base:
            duration = float(stream.duration * stream.time_base)
        else:
            duration = 0.0

        info = VideoInfo(
            width=width,
            height=height,
            fps=fps,
            total_frames=total,
            duration=duration,
            codec=(cc.name or ""),
            profile=(cc.profile or ""),
            pix_fmt=(cc.pix_fmt or ""),
        )
        container.close()
        return info
    except Exception:
        return None


# ── 环境自检 ───────────────────────────────────────────────
@dataclass
class EnvReport:
    has_av: bool
    has_cv2: bool
    ffmpeg_path: str
    ffmpeg_has_x264: bool
    ffprobe_path: str

    @property
    def ok(self) -> bool:
        """能否完成解码+编码（校验可退化到 PyAV，故不强制 ffprobe）。"""
        return self.has_av and self.has_cv2 and bool(self.ffmpeg_path) \
            and self.ffmpeg_has_x264

    def describe(self) -> str:
        lines = [
            f"PyAV(av):        {'OK' if self.has_av else '缺失 (pip install av)'}",
            f"OpenCV(cv2):     {'OK' if self.has_cv2 else '缺失 (pip install opencv-python)'}",
            f"ffmpeg:          {self.ffmpeg_path or '未找到'}",
            f"  └ libx264:     {'OK' if self.ffmpeg_has_x264 else '不支持（无法编码）'}",
            f"ffprobe:         {self.ffprobe_path or '无（校验回退 PyAV）'}",
        ]
        return "\n".join(lines)


def check_environment() -> EnvReport:
    try:
        import cv2  # noqa: F401
        has_cv2 = True
    except ImportError:
        has_cv2 = False
    ff = find_ffmpeg()
    return EnvReport(
        has_av=HAS_AV,
        has_cv2=has_cv2,
        ffmpeg_path=ff,
        ffmpeg_has_x264=ffmpeg_has_encoder(ff, "libx264"),
        ffprobe_path=find_ffprobe(),
    )
