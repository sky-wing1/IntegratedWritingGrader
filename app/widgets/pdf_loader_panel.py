"""PDF読み込みパネル（QRコードから自動判定）"""

from __future__ import annotations
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QPushButton, QFileDialog, QTextEdit,
    QProgressBar, QMessageBox, QFrame, QGridLayout
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

from app.utils.config import Config
from app.workers.pipeline_worker import PipelineWorker


class DropArea(QFrame):
    """ドラッグ＆ドロップエリア"""

    file_dropped = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setMinimumHeight(150)
        self.setStyleSheet("""
            QFrame {
                border: 2px dashed #ccc;
                border-radius: 12px;
                background-color: #fafafa;
            }
            QFrame:hover {
                border-color: #2eaadc;
                background-color: #f0f8ff;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_label = QLabel("📄")
        icon_label.setStyleSheet("font-size: 48px;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        text_label = QLabel("PDFをドロップ\nまたはクリックして選択")
        text_label.setStyleSheet("color: #6b6b6b; font-size: 14px;")
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(text_label)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith('.pdf'):
                    event.acceptProposedAction()
                    self.setStyleSheet("""
                        QFrame {
                            border: 2px solid #2eaadc;
                            border-radius: 12px;
                            background-color: #e8f4fc;
                        }
                    """)
                    return

    def dragLeaveEvent(self, event):
        self.setStyleSheet("""
            QFrame {
                border: 2px dashed #ccc;
                border-radius: 12px;
                background-color: #fafafa;
            }
        """)

    def dropEvent(self, event: QDropEvent):
        self.setStyleSheet("""
            QFrame {
                border: 2px dashed #ccc;
                border-radius: 12px;
                background-color: #fafafa;
            }
        """)
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith('.pdf'):
                self.file_dropped.emit(file_path)
                break

    def mousePressEvent(self, event):
        # クリックでファイル選択ダイアログ
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "PDFファイルを選択",
            str(Path.home() / "Desktop"),
            "PDF Files (*.pdf)"
        )
        if file_path:
            self.file_dropped.emit(file_path)


class PdfLoaderPanel(QWidget):
    """PDF読み込みパネル"""

    pdf_loaded = pyqtSignal(str, dict)  # (PDFパス, 検出された情報)

    def __init__(self):
        super().__init__()
        self._current_pdf_path: str | None = None
        self._pipeline_worker: PipelineWorker | None = None
        self._detected_info: dict = {}
        self._setup_ui()

    def _setup_ui(self):
        """UI構築"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # タイトル
        title = QLabel("PDF読み込み")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #37352f;")
        layout.addWidget(title)

        # 説明
        desc = QLabel(
            "スキャン済みPDFをドロップまたは選択してください。\n"
            "QRコードから年度・学期・週・クラスを自動判定します。"
        )
        desc.setStyleSheet("color: #6b6b6b; font-size: 13px;")
        layout.addWidget(desc)

        # ドロップエリア
        self.drop_area = DropArea()
        self.drop_area.file_dropped.connect(self._on_file_selected)
        layout.addWidget(self.drop_area)

        # 検出情報表示
        self.info_group = QGroupBox("検出情報")
        self.info_group.setVisible(False)
        info_layout = QGridLayout(self.info_group)

        self.info_labels = {}
        info_items = [
            ("file", "ファイル", 0, 0),
            ("year", "年度", 1, 0),
            ("term", "学期", 1, 2),
            ("week", "週", 2, 0),
            ("class", "クラス", 2, 2),
            ("pages", "ページ数", 3, 0),
        ]

        for key, label_text, row, col in info_items:
            label = QLabel(f"{label_text}:")
            label.setStyleSheet("font-weight: bold; color: #37352f;")
            info_layout.addWidget(label, row, col)

            value_label = QLabel("-")
            value_label.setStyleSheet("color: #6b6b6b;")
            self.info_labels[key] = value_label
            info_layout.addWidget(value_label, row, col + 1)

        layout.addWidget(self.info_group)

        # プログレス
        self.progress_group = QGroupBox("処理中")
        self.progress_group.setVisible(False)
        progress_layout = QVBoxLayout(self.progress_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                text-align: center;
                height: 24px;
            }
            QProgressBar::chunk {
                background-color: #2eaadc;
                border-radius: 3px;
            }
        """)
        progress_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #6b6b6b;")
        progress_layout.addWidget(self.status_label)

        layout.addWidget(self.progress_group)

        # プロンプト表示
        self.prompt_group = QGroupBox("採点プロンプト")
        self.prompt_group.setVisible(False)
        prompt_layout = QVBoxLayout(self.prompt_group)

        self.prompt_display = QTextEdit()
        self.prompt_display.setReadOnly(True)
        self.prompt_display.setMaximumHeight(200)
        self.prompt_display.setStyleSheet("""
            QTextEdit {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                font-family: monospace;
                font-size: 12px;
            }
        """)
        prompt_layout.addWidget(self.prompt_display)

        layout.addWidget(self.prompt_group)

        # 採点開始ボタン
        self.start_btn = QPushButton("採点画面へ進む →")
        self.start_btn.setVisible(False)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #00a86b;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 14px 32px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #009060; }
        """)
        self.start_btn.clicked.connect(self._on_start_clicked)
        layout.addWidget(self.start_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()

    def _on_file_selected(self, file_path: str):
        """ファイル選択時"""
        self._current_pdf_path = file_path
        self._start_processing()

    def _start_processing(self):
        """PDF処理開始"""
        if not self._current_pdf_path:
            return

        # UI更新
        self.drop_area.setVisible(False)
        self.info_group.setVisible(False)
        self.prompt_group.setVisible(False)
        self.start_btn.setVisible(False)
        self.progress_group.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("処理開始...")

        # ワーカー開始
        self._pipeline_worker = PipelineWorker(self._current_pdf_path)
        self._pipeline_worker.progress.connect(self._on_progress)
        self._pipeline_worker.students_found.connect(self._on_students_found)
        self._pipeline_worker.finished.connect(self._on_finished)
        self._pipeline_worker.error.connect(self._on_error)
        self._pipeline_worker.start()

    def _on_progress(self, current: int, total: int, message: str):
        """進捗更新"""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(message)

    def _on_students_found(self, students: list):
        """生徒情報検出"""
        if students:
            first = students[0]
            self._detected_info = {
                "year": first.get("year"),
                "term": first.get("term"),
                "week": first.get("week"),
                "class_name": first.get("class_name"),
                "page_count": len(students),
                "students": students,
            }

    def _on_finished(self, pdf_path: str):
        """処理完了"""
        self.progress_group.setVisible(False)
        self.drop_area.setVisible(True)
        self.info_group.setVisible(True)

        # 検出情報を表示
        self.info_labels["file"].setText(Path(pdf_path).name)

        if self._detected_info:
            year = self._detected_info.get("year")
            term = self._detected_info.get("term")
            week = self._detected_info.get("week")
            class_name = self._detected_info.get("class_name")
            page_count = self._detected_info.get("page_count", 0)

            self.info_labels["year"].setText(
                f"{year}年度" if year else "未検出"
            )
            self.info_labels["term"].setText(term or "未検出")
            self.info_labels["week"].setText(
                f"第{week}週" if week else "未検出"
            )
            self.info_labels["class"].setText(
                f"高2英語{class_name}" if class_name else "未検出"
            )
            self.info_labels["pages"].setText(f"{page_count}ページ")

            # プロンプト読み込み
            self._load_prompt()

            self.prompt_group.setVisible(True)
            self.start_btn.setVisible(True)
        else:
            # QRコードが検出できなかった場合
            for key in ["year", "term", "week", "class", "pages"]:
                self.info_labels[key].setText("未検出")

            QMessageBox.warning(
                self, "QRコード未検出",
                "QRコードが検出できませんでした。\n"
                "手動で設定するか、PDFを確認してください。"
            )

    def _on_error(self, error: str):
        """エラー"""
        self.progress_group.setVisible(False)
        self.drop_area.setVisible(True)
        self.status_label.setText(f"エラー: {error}")
        QMessageBox.critical(self, "処理エラー", error)

    def _load_prompt(self):
        """プロンプト読み込み"""
        term = self._detected_info.get("term")
        week = self._detected_info.get("week")

        if not term or not week:
            self.prompt_display.setText("プロンプトを読み込めません（週情報なし）")
            return

        week_path = Config.get_week_path(term, week)
        prompt_file = week_path / "prompt.txt"

        if prompt_file.exists():
            with open(prompt_file, "r", encoding="utf-8") as f:
                self.prompt_display.setText(f.read())
        else:
            self.prompt_display.setText(
                f"プロンプトファイルが見つかりません:\n{prompt_file}\n\n"
                "「週管理」から週を追加してプロンプトを設定してください。"
            )

    def _on_start_clicked(self):
        """採点開始ボタン"""
        if self._current_pdf_path:
            self.pdf_loaded.emit(self._current_pdf_path, self._detected_info)

    def reset(self):
        """リセット"""
        self._current_pdf_path = None
        self._detected_info = {}

        self.drop_area.setVisible(True)
        self.info_group.setVisible(False)
        self.prompt_group.setVisible(False)
        self.progress_group.setVisible(False)
        self.start_btn.setVisible(False)

        for label in self.info_labels.values():
            label.setText("-")

    def open_pdf_dialog(self):
        """PDFファイル選択ダイアログを開く"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "PDFファイルを選択",
            str(Path.home() / "Desktop"),
            "PDF Files (*.pdf)"
        )
        if file_path:
            self._on_file_selected(file_path)
