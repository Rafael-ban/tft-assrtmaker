"""cx-Freeze 打包脚本：生成内置 ffmpeg 的 Windows exe。

构建方法参考框架真实源码 `Rafael-ban/neo-assetmaker-dev` 的 `build.py`：
- 用 cx_Freeze，手写 build.py 驱动 setup(..., script_args=["build"])
- base = "gui"（cx_Freeze 7.0+ 已用 "gui" 取代旧的 "Win32GUI"）      build.py:629
- build_exe 选项：packages/includes/excludes/include_files/optimize=2/build_exe/path
- **PyAV 必须排除在 packages 之外、改用 include_files 手动复制**：
      site-packages/av      -> lib/av
      site-packages/av.libs -> lib/av.libs        （FFmpeg DLL，delvewheel 打包）
  框架原注释（build.py:420-422）：
      "av (PyAV) 不放在 packages 中 — cx_Freeze 7.2.10 的 PathFinder.find_spec
       无法定位 PyAV 17+ 的 abi3 C 扩展包（finder.py:383 返回 None）。
       改为通过 include_files 手动复制 av/ 和 av.libs/ 目录。"
- ffmpeg.exe 放到冻结输出根目录，运行时由 editor/ffmpeg_utils.py:get_app_dir()
  + find_ffmpeg() 定位（复刻框架 utils/file_utils.py:191-201 与
  core/video_processor.py:30-49）。
- 框架 CI 从 BtbN FFmpeg-Builds 下载 ffmpeg.exe 到仓库根目录；本项目若根目录
  没有 ffmpeg.exe，则自动复用 imageio-ffmpeg 自带的二进制（同样含 libx264）。

用法：
    .venv\\Scripts\\python.exe -m pip install cx_Freeze
    .venv\\Scripts\\python.exe build.py            # 构建
    .venv\\Scripts\\python.exe build.py --clean    # 先清理再构建
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import sysconfig

PROJECT_NAME = "TFTAssetMaker"
VERSION = "0.1.0"
MAIN_SCRIPT = "main.py"
BUILD_DIR = PROJECT_NAME            # 扁平输出目录（框架同款：覆盖 build/exe.win-...）
ICON_FILE = "resources/icon.ico"    # 可选，不存在则忽略

SOURCE_ROOT = os.path.dirname(os.path.abspath(__file__))


def _site_packages() -> str:
    """定位当前解释器的 site-packages。"""
    for key in ("platlib", "purelib"):
        p = sysconfig.get_path(key)
        if p and os.path.isdir(p):
            return p
    raise RuntimeError("找不到 site-packages")


def prepare_ffmpeg() -> str:
    """确保仓库根目录存在 ffmpeg.exe，返回其路径（找不到则返回空串）。

    优先用根目录已有的 ffmpeg.exe（等同框架 CI 从 BtbN 下载的落点）；
    否则复制 imageio-ffmpeg 自带的二进制（已验证含 libx264）。
    """
    exe_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    root_ffmpeg = os.path.join(SOURCE_ROOT, exe_name)
    if os.path.isfile(root_ffmpeg):
        print(f"  [ffmpeg] 使用根目录已有: {root_ffmpeg}")
        return root_ffmpeg
    try:
        import imageio_ffmpeg
        src = imageio_ffmpeg.get_ffmpeg_exe()
        if src and os.path.isfile(src):
            shutil.copy2(src, root_ffmpeg)
            print(f"  [ffmpeg] 已从 imageio-ffmpeg 复制: {src}\n"
                  f"           -> {root_ffmpeg}")
            return root_ffmpeg
    except Exception as e:  # noqa: BLE001
        print(f"  [ffmpeg] imageio-ffmpeg 不可用: {e}")
    print("  [ffmpeg] 警告：未找到 ffmpeg.exe，打包产物将无法导出视频！")
    return ""


def verify_ffmpeg_x264(path: str) -> bool:
    """校验待打包的 ffmpeg 确实含 libx264（否则导出必失败）。"""
    if not path:
        return False
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        out = subprocess.run(
            [path, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=20,
            creationflags=creationflags,
        )
        ok = "libx264" in (out.stdout or "")
        print(f"  [ffmpeg] libx264 支持: {'OK' if ok else '缺失!'}")
        return ok
    except Exception as e:  # noqa: BLE001
        print(f"  [ffmpeg] 校验失败: {e}")
        return False


def build_include_files(site_packages: str,
                        ffmpeg_path: str) -> "list[tuple[str, str]]":
    include_files: "list[tuple[str, str]]" = []

    # ── 内置 ffmpeg：放到冻结输出根目录（find_ffmpeg 第 1 顺位）──
    if ffmpeg_path:
        include_files.append((ffmpeg_path, os.path.basename(ffmpeg_path)))
    ffprobe = os.path.join(SOURCE_ROOT,
                           "ffprobe.exe" if sys.platform == "win32" else "ffprobe")
    if os.path.isfile(ffprobe):
        include_files.append((ffprobe, os.path.basename(ffprobe)))

    # ── PyAV：手动复制，绕过 cx_Freeze PathFinder（见模块 docstring）──
    av_dir = os.path.join(site_packages, "av")
    if os.path.isdir(av_dir):
        include_files.append((av_dir, "lib/av"))
        print(f"  [av] 包含: {av_dir} -> lib/av")
    else:
        print("  [av] 警告：未找到 av 包！")
    av_libs = os.path.join(site_packages, "av.libs")
    if os.path.isdir(av_libs):
        include_files.append((av_libs, "lib/av.libs"))
        print(f"  [av] 包含 FFmpeg DLL: {av_libs} -> lib/av.libs")
    else:
        print("  [av] 警告：未找到 av.libs（PyAV 将无法加载 FFmpeg DLL）！")

    # ── PyQt6 插件：platforms 必需，否则 exe 起不来 ──
    plugins = os.path.join(site_packages, "PyQt6", "Qt6", "plugins")
    if os.path.isdir(plugins):
        for name in ("platforms", "imageformats", "styles"):
            p = os.path.join(plugins, name)
            if os.path.isdir(p):
                include_files.append((p, f"lib/PyQt6/Qt6/plugins/{name}"))

    return include_files


def main() -> int:
    if "--clean" in sys.argv:
        for d in (BUILD_DIR, "build", "dist"):
            path = os.path.join(SOURCE_ROOT, d)
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
                print(f"  [clean] 已删除 {d}/")

    try:
        from cx_Freeze import Executable, setup
    except ImportError:
        print("错误：未安装 cx_Freeze。请先运行：\n"
              "    .venv\\Scripts\\python.exe -m pip install cx_Freeze")
        return 1

    site_packages = _site_packages()
    print(f"== 打包 {PROJECT_NAME} v{VERSION} ==")
    print(f"  site-packages: {site_packages}")

    ffmpeg_path = prepare_ffmpeg()
    verify_ffmpeg_x264(ffmpeg_path)
    include_files = build_include_files(site_packages, ffmpeg_path)

    packages = [
        "editor",          # 本项目
        "PyQt6", "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets",
        "cv2", "numpy",
        # 注意：不要把 "av" 放进来（见模块 docstring 的框架注释）
    ]
    includes = ["editor.app", "editor.exporter", "editor.video_source"]
    excludes = [
        "tkinter", "unittest", "test", "pytest", "IPython",
        "torch", "torchvision", "torchaudio", "sympy", "scipy",
        "matplotlib", "pandas",
        # PySide6 会被某些 Qt 生态包间接拖入，务必排除
        "PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
        "PyQt5",
    ]

    # cx_Freeze 只用 importlib.machinery.PathFinder，不走 sys.meta_path，
    # 在 uv/venv 下需显式注入 site-packages（框架 build.py:413-419 同款）
    search_paths = [SOURCE_ROOT] + list(sys.path)
    for extra in (sysconfig.get_path("purelib"), sysconfig.get_path("platlib")):
        if extra and os.path.isdir(extra) and extra not in search_paths:
            search_paths.insert(1, extra)

    build_options = {
        "packages": packages,
        "includes": includes,
        "excludes": excludes,
        "include_files": include_files,
        "optimize": 2,
        "build_exe": BUILD_DIR,
        "path": search_paths,
    }

    base = "gui" if sys.platform == "win32" else None   # cx_Freeze 7.0+
    icon = ICON_FILE if os.path.exists(os.path.join(SOURCE_ROOT, ICON_FILE)) else None

    setup(
        name=PROJECT_NAME,
        version=VERSION,
        description="1.9寸TFT素材编辑器（精简版）",
        options={"build_exe": build_options},
        executables=[Executable(
            script=os.path.join(SOURCE_ROOT, MAIN_SCRIPT),
            base=base,
            target_name=f"{PROJECT_NAME}.exe",
            icon=icon,
        )],
        script_args=["build"],
    )

    out = os.path.join(SOURCE_ROOT, BUILD_DIR)
    print(f"\n== 构建完成 ==\n  输出目录: {out}\n"
          f"  可执行文件: {os.path.join(out, PROJECT_NAME + '.exe')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
