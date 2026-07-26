"""常量与分辨率规格。

结构参考框架 `config/constants.py`（neo-assetmaker-dev v2.1.4）的
`RESOLUTION_SPECS` / `get_resolution_spec`，为 1.9 寸 TFT 新增 320x192 目标。
"""
from typing import Dict, Any

APP_NAME = "1.9寸TFT素材编辑器"
APP_VERSION = "0.1.0"

# ── 输出文件名 ─────────────────────────────────────────────
DEFAULT_OUTPUT_NAME = "loop.mp4"

# ── 电子通行证原始 x264 预设（逐字摘自框架真实源码，作引用/对比基线）──
# 来源: core/video_processor.py:17-27 (momovlink/neo-assetmaker-dev v2.1.4)
# 框架 core/export_service.py:391-401 配 `-profile:v high -preset veryslow -crf 26`。
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

# ── 1.9"TFT 实用预设（以上面框架预设为基底，按设备实测收紧 DPB）──
#
# 【为何必须改：旧写法无效的实证】
#   旧写法 = 不传 -x264-params。x264 遂用 veryslow 默认 ref=16/bframes=8/
#   b-pyramid=normal，实测导出 SPS: level_idc=21(L2.1)、max_num_ref_frames=16、
#   **max_dec_frame_buffering=16**；DPB 占用模拟显示输出第 8~16 帧即超出小解码器
#   帧缓冲 → 设备播 ~10 帧卡死（用户实际症状）。
#
# 【为何这样改：新写法有效的实证】
#   设备能正常播放的参考 loop.mp4，其 SPS 实测为：level_idc=13(L1.3)、
#   pic_order_cnt_type=2、max_num_ref_frames=1、**max_dec_frame_buffering=1**、
#   无 ctts（严格 IPPP，显示序=解码序）。本预设导出的 SPS 与之逐项一致。
#
# 【与框架预设的差异及原因】（框架 X264_PARAMS 实测 max_dec_frame_buffering=4，
#   仍带 b_pyramid=2 与 ctts，只修好 level、修不好重排序，故不能照抄）
#   - ref=3      -> ref=1       ：对齐参考文件，DPB 降到 1
#   - bframes=16 -> bframes=0   ：去除 B 帧重排序，消除 ctts，PTS==DTS
#   - keyint=300 -> keyint=90   ：对齐参考文件的 IDR 间隔（5 个同步样本/414 帧）
#   - 去掉 partitions=all（i8x8 属 High profile，Main 下本就被 x264 剔除）
#   - 去掉 direct=auto / no-weightb=0 / b-adapt（均为 B 帧相关，bframes=0 后无意义）
#   - rc-lookahead 150 -> 60    ：无 B 帧时过长前瞻无收益
#   其余画质档（me/subme/merange/no-fast-pskip/aq/trellis/deblock/psy-rd/
#   chroma-qp-offset）逐字沿用框架预设。
X264_PARAMS_TFT = (
    "ref=1:bframes=0"
    ":keyint=90:min-keyint=30:scenecut=0"
    ":rc-lookahead=60"
    ":me=umh:subme=9:merange=48:no-fast-pskip=1"
    ":aq-mode=1:aq-strength=0.6:trellis=2"
    ":deblock=1,1:psy-rd=0.4,0:chroma-qp-offset=-3"
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
        "level": "1.3",          # 对齐参考 loop.mp4 的 level_idc=13
        "preset": "veryslow",    # 沿用框架质量档 core/export_service.py:377
        "crf": 26,               # 沿用框架 core/export_service.py:376
        "pix_fmt": "yuv420p",
        "x264_params": X264_PARAMS_TFT,   # ★ 关键：不传会退化到 ref=16/L2.1，设备播 ~10 帧卡死
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
