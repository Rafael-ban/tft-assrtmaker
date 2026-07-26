"""常量与分辨率规格。

结构参考框架 `config/constants.py`（neo-assetmaker-dev v2.1.4）的
`RESOLUTION_SPECS` / `get_resolution_spec`，为 1.9 寸 TFT 新增 320x192 目标。
"""
from typing import Dict, Any

APP_NAME = "1.9寸TFT素材编辑器"
APP_VERSION = "0.1.0"

# ── 输出文件名 ─────────────────────────────────────────────
DEFAULT_OUTPUT_NAME = "loop.mp4"

# ── 电子通行证原始 x264 预设（逐字摘自框架真实源码，作引用/对比用）──
# 来源: core/video_processor.py:17-27 (momovlink/neo-assetmaker-dev v2.1.4)
# 说明: 该预设含 partitions=all（隐含 i8x8/8x8dct，属 High profile 特性），
#       框架 core/export_service.py:395 因此配 `-profile:v high`。
#       ⚠ 本项目目标机 1.9" TFT 实测 loop.mp4 为 Main@L1.3（见下 profile="main"），
#       故 TFT 预设改用 -profile:v main（High-only 特性由 x264 自动剔除）。
X264_PARAMS_EPASS = (
    "partitions=all"
    ":rc-lookahead=150"
    ":bframes=16:b-adapt=2"
    ":me=umh:subme=9:merange=48"
    ":no-fast-pskip=1:direct=auto:no-weightb=0"
    ":keyint=300:min-keyint=5:ref=3"
    ":chroma-qp-offset=-3"
    ":aq-mode=1:aq-strength=0.6:trellis=2"
    ":deblock=1,1:psy-rd=0.4,0"
)

# ── 分辨率规格 ────────────────────────────────────────────
# 沿用框架 spec 字典结构（width/height/padded_*/padding_side/rotate_180/description），
# 新增本项目主目标 320x192。
RESOLUTION_SPECS: Dict[str, Dict[str, Any]] = {
    # 1.9 寸 TFT：物理可视 320x170，硬件解码器最小高度 192 → 编码 320x192，
    # 底部 22px 为 padding（设备忽略）。320 与 192 均已 32 像素对齐，无需额外 pad。
    "320x192": {
        "width": 320,            # 缩放/编码目标宽
        "height": 192,           # 缩放/编码目标高（= 硬件解码器最小高度）
        "visible_width": 320,
        "visible_height": 170,   # 物理可视高度；下方 22px 不显示
        "padded_width": 0,       # 已 32 对齐，无需 pad（0 表示不加黑边）
        "padded_height": 0,
        "padding_side": None,
        "padding_amount": 0,
        "rotate_180": False,
        # 编码目标：对齐实测 loop.mp4（H.264 Main@L1.3, yuv420p, 30fps CFR）
        "profile": "main",
        "preset": "veryslow",    # 沿用框架质量档 core/export_service.py:377
        "crf": 26,               # 沿用框架 core/export_service.py:376
        "pix_fmt": "yuv420p",
        "aspect_w": 320,
        "aspect_h": 192,
        "description": "1.9寸TFT (可视320x170, 编码320x192, 底部22px padding, Main@L1.3)",
    },
}

DEFAULT_RESOLUTION = "320x192"

# ── 支持的输入视频格式 ─────────────────────────────────────
SUPPORTED_VIDEO_FORMATS = (".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv")


def get_resolution_spec(resolution: str) -> Dict[str, Any]:
    """获取分辨率规格（参考 config/constants.py:get_resolution_spec）。"""
    return RESOLUTION_SPECS.get(resolution, RESOLUTION_SPECS[DEFAULT_RESOLUTION])


def safe_area_ratio(resolution: str = DEFAULT_RESOLUTION) -> float:
    """可视安全区占编码高度的比例（如 170/192 = 0.8854）。"""
    spec = get_resolution_spec(resolution)
    h = spec.get("height", 1)
    vh = spec.get("visible_height", h)
    return (vh / h) if h else 1.0


def frame_to_timecode(frame: int, fps: float) -> str:
    """帧号 -> mm:ss:ff 时码（ff 为该秒内帧序）。"""
    if fps <= 0:
        return "00:00:00"
    total_seconds = int(frame // fps)
    ff = int(round(frame - total_seconds * fps))
    mm = total_seconds // 60
    ss = total_seconds % 60
    return f"{mm:02d}:{ss:02d}:{ff:02d}"
