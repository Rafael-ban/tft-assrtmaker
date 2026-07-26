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
> ffmpeg 查找顺序：**exe 同级目录（打包内置）→ `ffmpeg/` 子目录 → `imageio-ffmpeg` 自带 → 系统 PATH**。前两级复刻框架 `core/video_processor.py:30-49`（"仅限应用自带，避免多版本冲突"）。视频探测/校验统一走 PyAV，无需 ffprobe。

## 构建 exe（GitHub Actions 自动构建）
推送到 `main` 或打 `v*` tag 自动触发 `.github/workflows/build.yml`；也可在 Actions 页手动 `workflow_dispatch`。
流程：Windows runner → 装依赖 → 从 **BtbN FFmpeg-Builds** 下载含 libx264 的 ffmpeg → `python build.py`（cx-Freeze）→ 校验产物 → offscreen 冒烟测试 → 打包 zip 上传 artifact（打 tag 时另发 Release）。

构建配方参考 `Rafael-ban/neo-assetmaker-dev` 的 `build.py` / `build-app.yml`：
- `base="gui"` —— cx_Freeze 7.0+ 已用 `"gui"` 取代 `"Win32GUI"`
- **`av` 必须排除在 `packages` 之外**，改用 `include_files` 手动复制 `av`→`lib/av`、`av.libs`→`lib/av.libs`。框架注释指出 cx_Freeze 7.2.10 的 `PathFinder.find_spec` 无法定位 PyAV 17+ 的 abi3 C 扩展；本项目正是 cx_Freeze 7.2.10 + PyAV 18，必然命中此坑
- `ffmpeg.exe` 打进产物根目录，运行时由 `get_app_dir()`（`sys.frozen` → `dirname(sys.executable)`）定位

## 导出参数（为何必须固定 x264 参数）
| | 旧写法（不传 `-x264-params`） | 新写法 | 参考 `loop.mp4` |
|---|---|---|---|
| level_idc | **21 (L2.1)** | 13 (L1.3) | 13 (L1.3) |
| max_num_ref_frames | **16** | 1 | 1 |
| max_dec_frame_buffering | **16** | 1 | 1 |
| ctts（B帧重排序） | 有 | 无 | 无 |

x264 在 `-preset veryslow` 下默认 `ref=16/bframes=8/b-pyramid`，320×192 需 16×240=3840 MB 的 DPB，超出 L1.3 上限（2376）而被迫升到 L2.1。TFT 硬件解码器帧缓冲池在**输出第 8~16 帧**时耗尽 → 播 ~10 帧卡死。
现固定 `-level:v 1.3 -x264-params ref=1:bframes=0:keyint=90:…`（画质档沿用框架 `X264_PARAMS`），导出 SPS 与参考文件逐项一致。
> 注：直接照抄框架 `X264_PARAMS` 并不够——其 `bframes=16:b-adapt=2` 实测得 `max_dec_frame_buffering=4` 且仍产生 `ctts`，只修好 level、修不好重排序。
