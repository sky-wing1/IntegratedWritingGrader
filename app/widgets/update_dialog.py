"""アップデートダイアログ"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QMessageBox,
)

if TYPE_CHECKING:
    from app.utils.updater import ReleaseInfo, UpdateChecker

logger = logging.getLogger(__name__)


class DownloadWorker(QThread):
    """ダウンロードワーカー"""

    progress = pyqtSignal(int, int)  # downloaded, total
    finished = pyqtSignal(object)  # zip_path or None
    error = pyqtSignal(str)

    def __init__(self, checker: "UpdateChecker", release: "ReleaseInfo"):
        super().__init__()
        self.checker = checker
        self.release = release

    def run(self):
        try:
            zip_path = self.checker.download_update(
                self.release,
                progress_callback=lambda d, t: self.progress.emit(d, t)
            )
            self.finished.emit(zip_path)
        except Exception as e:
            logger.error(f"Download failed: {e}")
            self.error.emit(str(e))


class UpdateDialog(QDialog):
    """アップデート確認ダイアログ"""

    def __init__(self, checker: "UpdateChecker", release: "ReleaseInfo", parent=None):
        super().__init__(parent)
        self.checker = checker
        self.release = release
        self._download_worker: DownloadWorker | None = None

        self.setWindowTitle("アップデート")
        self.setMinimumWidth(450)
        self.setModal(True)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # タイトル
        title = QLabel(f"新バージョン v{self.release.version} が利用可能です")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # 現在のバージョン
        current_label = QLabel(f"現在のバージョン: v{self.checker.current_version}")
        current_label.setStyleSheet("color: #666;")
        layout.addWidget(current_label)

        # リリースノート
        if self.release.release_notes:
            notes_label = QLabel("更新内容:")
            notes_label.setStyleSheet("font-weight: bold; margin-top: 8px;")
            layout.addWidget(notes_label)

            notes_text = QTextEdit()
            notes_text.setReadOnly(True)
            notes_text.setPlainText(self.release.release_notes)
            notes_text.setMaximumHeight(150)
            notes_text.setStyleSheet("""
                QTextEdit {
                    background-color: #f5f5f5;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    padding: 8px;
                }
            """)
            layout.addWidget(notes_text)

        # プログレスバー（初期は非表示）
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("ダウンロード中... %p%")
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # ステータスラベル
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666;")
        self.status_label.hide()
        layout.addWidget(self.status_label)

        # ボタン
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.later_btn = QPushButton("後で")
        self.later_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.later_btn)

        self.update_btn = QPushButton("今すぐ更新")
        self.update_btn.setDefault(True)
        self.update_btn.setStyleSheet("""
            QPushButton {
                background-color: #0066cc;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0052a3;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        self.update_btn.clicked.connect(self._start_update)
        button_layout.addWidget(self.update_btn)

        layout.addLayout(button_layout)

    def _start_update(self):
        """アップデート開始"""
        self.update_btn.setEnabled(False)
        self.later_btn.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        self.status_label.show()
        self.status_label.setText("ダウンロード中...")

        self._download_worker = DownloadWorker(self.checker, self.release)
        self._download_worker.progress.connect(self._on_progress)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.error.connect(self._on_error)
        self._download_worker.start()

    def _on_progress(self, downloaded: int, total: int):
        """ダウンロード進捗"""
        if total > 0:
            percent = int(downloaded / total * 100)
            self.progress_bar.setValue(percent)
            mb_downloaded = downloaded / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            self.status_label.setText(f"ダウンロード中... {mb_downloaded:.1f} / {mb_total:.1f} MB")

    def _on_download_finished(self, zip_path):
        """ダウンロード完了"""
        if not zip_path:
            self._on_error("ダウンロードに失敗しました")
            return

        self.status_label.setText("インストール中...")
        self.progress_bar.setFormat("インストール中...")
        self.progress_bar.setValue(100)

        # インストール実行
        if self.checker.install_update(zip_path):
            self.status_label.setText("インストール完了！再起動します...")
            QMessageBox.information(
                self,
                "アップデート完了",
                "アップデートが完了しました。アプリを再起動します。"
            )
            self.checker.restart_app()
        else:
            self._on_error("インストールに失敗しました")

    def _on_error(self, error: str):
        """エラー発生"""
        self.progress_bar.hide()
        self.status_label.setText(f"エラー: {error}")
        self.status_label.setStyleSheet("color: red;")
        self.update_btn.setEnabled(True)
        self.later_btn.setEnabled(True)
        QMessageBox.critical(self, "アップデートエラー", error)
