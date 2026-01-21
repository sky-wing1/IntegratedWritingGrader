"""IntegratedWritingGrader - メインエントリーポイント"""

import sys
from pathlib import Path

# アプリケーションパスを追加
app_path = Path(__file__).parent
sys.path.insert(0, str(app_path.parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from app.main_window import MainWindow


def main():
    """アプリケーション起動"""
    app = QApplication(sys.argv)
    app.setApplicationName("IntegratedWritingGrader")
    app.setOrganizationName("Tsubasa")

    # ハイDPI対応
    app.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
