"""导出：PyAV 解码 → cv2 旋转/裁剪/缩放 → PNG 序列 → ffmpeg libx264 编码。

流程与参数复刻框架真实源码：
- 解码+逐帧处理+写 PNG:  core/export_service.py:206-356 (_export_video)
- ffmpeg PNG 序列编码:   core/export_service.py:358-401 (_run_ffmpeg_crf)
  框架：-c:v libx264 -preset veryslow -crf 26 -profile:v high -pix_fmt yuv420p
        -x264-params <X264_PARAMS> -an
  本项目（1.9"TFT）：改 -profile:v main（对齐实测 loop.mp4 = Main@L1.3；
  High 的 8x8dct/i8x8 受限 TFT 解码器未必支持），保留 veryslow/crf26/yuv420p/-an。

注意：PyAV 容器非线程安全，本 QThread 内新开独立 VideoSource。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from typing import Tuple

try:
    import cv2
    HAS_CV2 = True
except ImportError:  # pragma: no cover
    HAS_CV2 = False

from PyQt6.QtCore import QThread, pyqtSignal

from . import frame_ops
from .constants import get_resolution_spec
from .video_source import VideoSource


class ExportWorker(QThread):
    progress = pyqtSignal(int, str)     # 0-100, 状态文本
    completed = pyqtSignal(str)         # 输出路径
    failed = pyqtSignal(str)            # 错误信息

    def __init__(self, video_path: str, output_path: str,
                 cropbox: Tuple[int, int, int, int], start_frame: int,
                 end_frame: int, fps: float, rotation: int,
                 resolution: str, ffmpeg_path: str, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.output_path = output_path
        self.cropbox = cropbox          # 旋转后坐标系
        self.start_frame = start_frame
        self.end_frame = end_frame      # 独占（= 出点 + 1）
        self.fps = fps
        self.rotation = rotation
        self.resolution = resolution
        self.ffmpeg_path = ffmpeg_path
        self._cancelled = False
        self._proc = None

    def cancel(self):
        self._cancelled = True
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def run(self):
        if not self.ffmpeg_path:
            self.failed.emit("未找到 ffmpeg（含 libx264），无法导出")
            return
        if not HAS_CV2:
            self.failed.emit("未安装 opencv-python，无法处理视频")
            return

        spec = get_resolution_spec(self.resolution)
        tw, th = spec["width"], spec["height"]
        total = max(1, self.end_frame - self.start_frame)
        temp_dir = tempfile.mkdtemp(prefix="tft_export_")
        src = VideoSource()
        try:
            src.open(self.video_path)
            written = 0
            for _idx, frame in src.iter_frames(self.start_frame, self.end_frame):
                if self._cancelled:
                    self.failed.emit("导出已取消")
                    return
                rotated = frame_ops.apply_rotation(frame, self.rotation)
                out = frame_ops.crop_and_resize(rotated, self.cropbox, tw, th)
                ok, buf = cv2.imencode(".png", out)
                if ok:
                    with open(os.path.join(temp_dir, f"frame_{written:06d}.png"),
                              "wb") as f:
                        f.write(buf.tobytes())
                    written += 1
                if written % 10 == 0:
                    self.progress.emit(
                        int(written / total * 60), f"处理帧 {written}/{total}")
            src.close()

            if written == 0:
                self.failed.emit("没有成功写入任何帧（请检查入/出点）")
                return

            self.progress.emit(65, "正在用 libx264 编码...")
            self._encode(temp_dir, spec, tw, th)
            if self._cancelled:
                self.failed.emit("导出已取消")
                return
            self.progress.emit(100, "导出完成")
            self.completed.emit(self.output_path)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"导出失败: {e}")
        finally:
            src.close()
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _encode(self, temp_dir: str, spec: dict, tw: int, th: int):
        pattern = os.path.join(temp_dir, "frame_%06d.png")
        fps_str = f"{self.fps:g}"
        cmd = [
            self.ffmpeg_path, "-hide_banner", "-y",
            "-framerate", fps_str,
            "-i", pattern,
            "-c:v", "libx264",
            "-profile:v", spec.get("profile", "main"),     # main（对齐 loop.mp4）
            "-preset", spec.get("preset", "veryslow"),      # export_service.py:377
            "-crf", str(spec.get("crf", 26)),               # export_service.py:376
            "-pix_fmt", spec.get("pix_fmt", "yuv420p"),
            "-r", fps_str,                                   # 输出 CFR
            "-an",                                           # 剥离音频
            "-movflags", "+faststart",
            self.output_path,
        ]
        # padded_* 非零时补黑边（本项目 320×192 已 32 对齐，通常无需）
        pw, ph = spec.get("padded_width", 0), spec.get("padded_height", 0)
        if pw and ph:
            cmd[cmd.index("-c:v"):cmd.index("-c:v")] = [
                "-vf", f"pad={pw}:{ph}:0:0:black"]

        kwargs = dict(stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                      encoding="utf-8", errors="replace")
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        self._proc = subprocess.Popen(cmd, **kwargs)
        _out, err = self._proc.communicate()
        if self._proc.returncode != 0 and not self._cancelled:
            raise RuntimeError(f"ffmpeg 编码失败: {(err or '')[-800:]}")
