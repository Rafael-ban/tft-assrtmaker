# 1.9寸 TFT 素材编辑器
把原始视频加工成明日方舟「电子通行证」**1.9 寸 TFT 屏**（可视 320×170 / 编码 **320×192**）可用的循环素材 `loop.mp4`。

参考 `momovlink/neo-assetmaker-dev` **v2.1.4** 的「素材编辑」功能，抽取为**仅含视频素材编辑**的精简版（去掉固件烧录 / 论坛 / SSH / 模拟器 / 更新等）。

## 功能
- **等比缩放裁剪框**：宽高比锁定 **5:3 (320:192)**，可移动 / 等比缩放 / 四角 handle / 框外压暗，双读数「当前框选大小 / 目标 320×192」。
- **单帧选结束位置**：帧级精度出点（`< >` 步进 / ←→ 方向键 / 时间轴拖动 / 时码显示）。
- **实时预览**：320×192 WYSIWYG，含 **170px 安全区线** 与「屏外 padding 遮罩」开关。
- **旋转**（可选）：90° 档位（竖屏源 → 横屏目标常用）。
- **导出**：`loop.mp4`，H.264 / **Main@L1.3** / yuv420p / 320×192 / 30fps / 无音频，对齐参考 `loop.mp4`。

## 安装与运行
```bash
# 已在 .venv 安装：PyQt6 / av(PyAV) / opencv-python / numpy / pillow / imageio-ffmpeg
.venv\Scripts\python.exe -m pip install -r requirements.txt   # 如需重装
.venv\Scripts\python.exe main.py
```
> ffmpeg：优先用系统 PATH 的 ffmpeg（含 libx264+ffprobe）；若无，则自动回退到 `imageio-ffmpeg` 自带的 ffmpeg（含 libx264）。视频探测/校验统一走 PyAV，无需 ffprobe。
