"""進捗表示パネル"""

from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QComboBox, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer


class ProgressPanel(QWidget):
    """採点進捗パネル"""

    grading_started = pyqtSignal(str)  # 採点方法（"cli" or "import"）
    grading_stopped = pyqtSignal()
    json_imported = pyqtSignal(str)  # JSONファイルパス
    save_requested = pyqtSignal()  # 保存リクエスト
    load_saved_requested = pyqtSignal()  # 保存済み結果読み込みリクエスト

    def __init__(self):
        super().__init__()
        self._is_running = False
        self._setup_ui()

    def _setup_ui(self):
        """UI構築"""
        self.setFixedHeight(100)
        self.setStyleSheet("""
            QWidget {
                background-color: #f7f6f3;
                border-bottom: 1px solid #e0e0e0;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(8)

        # 上段: 採点方法選択
        top_row = QHBoxLayout()

        top_row.addWidget(QLabel("採点方法:"))

        self.method_combo = QComboBox()
        self.method_combo.addItems([
            "Claude Code CLI",
            "結果JSONインポート",
            "保存済み結果を読み込み"
        ])
        self.method_combo.setFixedWidth(180)
        self.method_combo.currentIndexChanged.connect(self._on_method_changed)
        top_row.addWidget(self.method_combo)

        top_row.addSpacing(16)

        # ステータス
        self.status_label = QLabel("待機中")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #37352f;")
        top_row.addWidget(self.status_label)

        top_row.addStretch()

        layout.addLayout(top_row)

        # 下段: 進捗 + ボタン
        bottom_row = QHBoxLayout()

        self.detail_label = QLabel("PDFを読み込んで採点を開始してください")
        self.detail_label.setStyleSheet("font-size: 12px; color: #9b9a97;")
        bottom_row.addWidget(self.detail_label, 1)

        # プログレスバー
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(250)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                text-align: center;
                background-color: #fff;
            }
            QProgressBar::chunk {
                background-color: #2eaadc;
                border-radius: 3px;
            }
        """)
        bottom_row.addWidget(self.progress_bar)

        bottom_row.addSpacing(16)

        # アクションボタン
        self.action_btn = QPushButton("採点開始")
        self.action_btn.setFixedWidth(120)
        self.action_btn.setStyleSheet("""
            QPushButton {
                background-color: #2eaadc;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2496c4;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        self.action_btn.clicked.connect(self._on_action_clicked)
        bottom_row.addWidget(self.action_btn)

        # 保存ボタン
        self.save_btn = QPushButton("結果を保存")
        self.save_btn.setFixedWidth(120)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #0f7b0f;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0d6b0d;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        self.save_btn.setEnabled(False)  # 初期状態は無効
        self.save_btn.clicked.connect(self._on_save_clicked)
        bottom_row.addWidget(self.save_btn)

        layout.addLayout(bottom_row)

    def _on_method_changed(self, index: int):
        """採点方法変更"""
        if index == 0:  # CLI
            self.action_btn.setText("採点開始")
            self.detail_label.setText("Claude Code CLIで採点します")
        elif index == 1:  # JSONインポート
            self.action_btn.setText("JSONを選択")
            self.detail_label.setText("採点結果のJSONファイルを選択してください")
        else:  # 保存済み結果
            self.action_btn.setText("結果を選択")
            self.detail_label.setText("保存済みの採点結果を読み込みます")

    def _on_action_clicked(self):
        """アクションボタンクリック"""
        method_index = self.method_combo.currentIndex()

        if method_index == 1:  # JSONインポート
            self._import_json()
        elif method_index == 2:  # 保存済み結果
            self.load_saved_requested.emit()
        else:  # CLI
            if self._is_running:
                self.stop_grading()
            else:
                self.start_grading()

    def _import_json(self):
        """JSONインポート"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "採点結果JSONを選択",
            "",
            "JSON Files (*.json)"
        )
        if file_path:
            self.json_imported.emit(file_path)

    def _on_save_clicked(self):
        """保存ボタンクリック"""
        self.save_requested.emit()

    def start_grading(self):
        """採点開始"""
        self._is_running = True
        self.action_btn.setText("停止")
        self.action_btn.setStyleSheet("""
            QPushButton {
                background-color: #eb5757;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #d64545;
            }
        """)
        self.status_label.setText("採点中...")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #37352f;")
        self.method_combo.setEnabled(False)

        method = "cli" if self.method_combo.currentIndex() == 0 else "import"
        self.grading_started.emit(method)

    def stop_grading(self):
        """採点停止"""
        self._is_running = False
        self.action_btn.setText("採点開始")
        self.action_btn.setStyleSheet("""
            QPushButton {
                background-color: #2eaadc;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2496c4;
            }
        """)
        self.status_label.setText("停止")
        self.method_combo.setEnabled(True)
        self.grading_stopped.emit()

    def update_progress(self, current: int, total: int, detail: str = ""):
        """進捗更新"""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

        if detail:
            self.detail_label.setText(detail)
        else:
            self.detail_label.setText(f"{current}/{total} 完了")

    def set_complete(self):
        """完了状態に設定"""
        self._is_running = False
        self._on_method_changed(self.method_combo.currentIndex())
        self.method_combo.setEnabled(True)
        self.status_label.setText("完了")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #0f7b0f;")
        self.detail_label.setText("すべての採点が完了しました")
        self.save_btn.setEnabled(True)  # 保存ボタンを有効化

    def set_error(self, message: str):
        """エラー状態に設定"""
        self._is_running = False
        self.action_btn.setText("再試行")
        self.method_combo.setEnabled(True)
        self.status_label.setText("エラー")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #eb5757;")
        self.detail_label.setText(message)

    def set_saved(self, path: str):
        """保存完了状態に設定"""
        self.status_label.setText("保存済み")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #0f7b0f;")
        self.detail_label.setText(f"保存先: {path}")

        # 保存ボタンを一時的に「保存しました」に変更
        self.save_btn.setText("保存しました")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #0f7b0f;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
        """)

        # 2秒後に元に戻す
        QTimer.singleShot(2000, self._reset_save_btn)

    def _reset_save_btn(self):
        """保存ボタンを元に戻す"""
        self.save_btn.setText("結果を保存")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #0f7b0f;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0d6b0d;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
