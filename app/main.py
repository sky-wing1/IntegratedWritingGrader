"""IntegratedWritingGrader - メインエントリーポイント"""

import logging
import sys
from pathlib import Path

# アプリケーションパスを追加
app_path = Path(__file__).parent
sys.path.insert(0, str(app_path.parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer
from app.main_window import MainWindow
from app.utils.updater import UpdateChecker
from app.widgets.update_dialog import UpdateDialog

logger = logging.getLogger(__name__)


def check_for_updates(app: QApplication, window: MainWindow) -> None:
    """起動時にアップデートをチェック"""
    try:
        checker = UpdateChecker()
        release = checker.check_for_updates()

        if release:
            logger.info(f"New version available: {release.version}")
            dialog = UpdateDialog(checker, release, window)
            dialog.exec()
    except Exception as e:
        logger.warning(f"Update check failed: {e}")


def main():
    """アプリケーション起動"""
    # ロギング設定
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    app = QApplication(sys.argv)
    app.setApplicationName("IntegratedWritingGrader")
    app.setOrganizationName("Tsubasa")

    # ハイDPI対応
    app.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    window = MainWindow()
    window.show()

    # 起動後にアップデートチェック（UIが表示されてから）
    QTimer.singleShot(1000, lambda: check_for_updates(app, window))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
