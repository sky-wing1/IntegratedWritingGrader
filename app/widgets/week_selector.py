"""週選択ウィジェット"""

from __future__ import annotations
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QFileDialog, QGroupBox,
    QTextEdit, QSpinBox, QProgressBar, QMessageBox
)
from PyQt6.QtCore import pyqtSignal, Qt

from app.utils.config import Config
from app.workers.pipeline_worker import PipelineWorker


class WeekSelectorWidget(QWidget):
    """週選択とPDF読み込みウィジェット"""

    pdf_loaded = pyqtSignal(str)  # PDF読み込み完了シグナル
    processing_started = pyqtSignal()  # 処理開始シグナル
    processing_finished = pyqtSignal(str)  # 処理完了シグナル（クロップ済みPDFパス）

    def __init__(self):
        super().__init__()
        self._current_pdf_path: str | None = None
        self._pipeline_worker: PipelineWorker | None = None
        self._setup_ui()
        self._load_current_week()

    def _setup_ui(self):
        """UI構築"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # タイトル
        title = QLabel("週選択とPDF読み込み")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #37352f;")
        layout.addWidget(title)

        # 週選択グループ
        week_group = QGroupBox("週を選択")
        week_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 12px;
                padding: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 16px;
                padding: 0 8px;
            }
        """)
        week_layout = QHBoxLayout(week_group)

        # 学期選択
        week_layout.addWidget(QLabel("学期:"))
        self.term_combo = QComboBox()
        self.term_combo.addItems(["前期", "後期"])
        self.term_combo.currentTextChanged.connect(self._on_term_changed)
        week_layout.addWidget(self.term_combo)

        week_layout.addSpacing(20)

        # 週番号
        week_layout.addWidget(QLabel("第"))
        self.week_spin = QSpinBox()
        self.week_spin.setRange(1, 20)
        self.week_spin.setValue(1)
        week_layout.addWidget(self.week_spin)
        week_layout.addWidget(QLabel("週"))

        week_layout.addStretch()

        # 適用ボタン
        apply_btn = QPushButton("適用")
        apply_btn.clicked.connect(self._apply_week)
        week_layout.addWidget(apply_btn)

        layout.addWidget(week_group)

        # プロンプト表示
        prompt_group = QGroupBox("問題プロンプト")
        prompt_layout = QVBoxLayout(prompt_group)

        self.prompt_display = QTextEdit()
        self.prompt_display.setReadOnly(True)
        self.prompt_display.setMinimumHeight(200)
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

        layout.addWidget(prompt_group)

        # PDF読み込みグループ
        pdf_group = QGroupBox("PDF読み込み")
        pdf_layout = QVBoxLayout(pdf_group)

        # ファイル選択行
        file_row = QHBoxLayout()
        self.file_label = QLabel("ファイル未選択")
        self.file_label.setStyleSheet("color: #9b9a97;")
        file_row.addWidget(self.file_label, 1)

        browse_btn = QPushButton("PDFを選択...")
        browse_btn.clicked.connect(self.open_pdf_dialog)
        file_row.addWidget(browse_btn)

        pdf_layout.addLayout(file_row)

        # 処理開始ボタン
        self.process_btn = QPushButton("DyNAMiKS処理 → クロップ → 読み込み")
        self.process_btn.setEnabled(False)
        self.process_btn.setStyleSheet("""
            QPushButton {
                background-color: #2eaadc;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2496c4;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        self.process_btn.clicked.connect(self._start_processing)
        pdf_layout.addWidget(self.process_btn)

        # 進捗表示
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        pdf_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #9b9a97; font-size: 12px;")
        pdf_layout.addWidget(self.status_label)

        layout.addWidget(pdf_group)
        layout.addStretch()

    def _load_current_week(self):
        """現在の週を読み込み"""
        current = Config.get_current_week()
        if current:
            term = current.get("term", "前期")
            week = current.get("week", 1)
            self.term_combo.setCurrentText(term)
            self.week_spin.setValue(week)
            self._load_prompt()

    def _on_term_changed(self, term: str):
        """学期変更"""
        self._load_prompt()

    def _apply_week(self):
        """週設定を適用"""
        term = self.term_combo.currentText()
        week = self.week_spin.value()
        Config.set_current_week(term, week)
        self._load_prompt()

    def _load_prompt(self):
        """プロンプト読み込み"""
        term = self.term_combo.currentText()
        week = self.week_spin.value()
        week_path = Config.get_week_path(term, week)
        prompt_file = week_path / "prompt.txt"

        if prompt_file.exists():
            with open(prompt_file, "r", encoding="utf-8") as f:
                self.prompt_display.setText(f.read())
        else:
            self.prompt_display.setText(f"プロンプトファイルが見つかりません:\n{prompt_file}")

    def open_pdf_dialog(self):
        """PDFファイル選択ダイアログ"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "スキャンPDFを選択",
            str(Path.home() / "Desktop"),
            "PDF Files (*.pdf)"
        )
        if file_path:
            self._current_pdf_path = file_path
            self.file_label.setText(Path(file_path).name)
            self.file_label.setStyleSheet("color: #37352f;")
            self.process_btn.setEnabled(True)

    def _start_processing(self):
        """DyNAMiKS処理開始"""
        if not self._current_pdf_path:
            return

        # UI更新
        self.process_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(3)
        self.progress_bar.setValue(0)
        self.status_label.setText("処理開始...")
        self.processing_started.emit()

        # ワーカー開始
        self._pipeline_worker = PipelineWorker(self._current_pdf_path)
        self._pipeline_worker.progress.connect(self._on_progress)
        self._pipeline_worker.finished.connect(self._on_finished)
        self._pipeline_worker.error.connect(self._on_error)
        self._pipeline_worker.start()

    def _on_progress(self, current: int, total: int, message: str):
        """進捗更新"""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(message)

    def _on_finished(self, pdf_path: str):
        """処理完了"""
        self.progress_bar.setVisible(False)
        self.process_btn.setEnabled(True)
        self.status_label.setText("処理完了！")
        self.processing_finished.emit(pdf_path)
        self.pdf_loaded.emit(pdf_path)

    def _on_error(self, error: str):
        """エラー"""
        self.progress_bar.setVisible(False)
        self.process_btn.setEnabled(True)
        self.status_label.setText(f"エラー: {error}")
        QMessageBox.critical(self, "処理エラー", error)
