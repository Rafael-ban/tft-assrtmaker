"""1.9寸 TFT 素材编辑器（精简版）入口。

用法：
    python main.py

参考 momovlink/neo-assetmaker-dev v2.1.4 的「素材编辑」功能，抽取为仅含
视频素材编辑（等比裁剪 / 单帧trim / 预览 / 90°旋转 / 导出 320×192 h264）的精简版。
"""
import sys

from PyQt6.QtWidgets import QApplication

from editor.app import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("1.9寸TFT素材编辑器")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
