"""一括処理パネル"""

from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QPushButton, QFileDialog, QTableWidget,
    QTableWidgetItem, QHeaderView, QProgressBar,
    QMessageBox, QCheckBox, QAbstractItemView
)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QColor


@dataclass
class BatchJob:
    """バッチジョブ"""
    pdf_path: Path
    status: str = "待機中"  # 待機中, 処理中, 完了, エラー
    year: int | None = None
    term: str | None = None
    week: int | None = None
    class_name: str | None = None
    page_count: int = 0
    graded_count: int = 0
    error_message: str = ""


class BatchPanel(QWidget):
    """一括処理パネル"""

    batch_started = pyqtSignal()
    batch_finished = pyqtSignal(list)  # 処理結果リスト
    job_selected = pyqtSignal(str)  # 選択されたPDFパス

    def __init__(self):
        super().__init__()
        self._jobs: list[BatchJob] = []
        self._is_processing = False
        self._setup_ui()

    def _setup_ui(self):
        """UI構築"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # タイトル
        title = QLabel("一括処理")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #37352f;")
        layout.addWidget(title)

        # 説明
        desc = QLabel(
            "複数のPDFをまとめて処理できます。"
            "QRコードからクラス・週を自動判別して振り分けます。"
        )
        desc.setStyleSheet("color: #6b6b6b; font-size: 13px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # ファイル追加エリア
        file_group = QGroupBox("処理ファイル")
        file_layout = QVBoxLayout(file_group)

        # ボタン行
        btn_layout = QHBoxLayout()

        self.add_files_btn = QPushButton("ファイルを追加...")
        self.add_files_btn.clicked.connect(self._add_files)
        self.add_files_btn.setStyleSheet("""
            QPushButton {
                background-color: #2eaadc;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #2496c4; }
        """)
        btn_layout.addWidget(self.add_files_btn)

        self.add_folder_btn = QPushButton("フォルダを追加...")
        self.add_folder_btn.clicked.connect(self._add_folder)
        self.add_folder_btn.setStyleSheet("""
            QPushButton {
                background-color: #5c5c5c;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
        """)
        btn_layout.addWidget(self.add_folder_btn)

        self.clear_btn = QPushButton("クリア")
        self.clear_btn.clicked.connect(self._clear_jobs)
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff6b6b;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
            }
            QPushButton:hover { background-color: #ee5a5a; }
        """)
        btn_layout.addWidget(self.clear_btn)

        btn_layout.addStretch()
        file_layout.addLayout(btn_layout)

        # ファイルテーブル
        self.job_table = QTableWidget()
        self.job_table.setColumnCount(7)
        self.job_table.setHorizontalHeaderLabels([
            "ファイル名", "ステータス", "年度", "クラス", "学期", "週", "進捗"
        ])
        self.job_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.job_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.job_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.job_table.setAlternatingRowColors(True)
        self.job_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                background-color: white;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QTableWidget::item:selected {
                background-color: #e8f4fc;
            }
        """)
        file_layout.addWidget(self.job_table)

        layout.addWidget(file_group)

        # オプション
        options_group = QGroupBox("処理オプション")
        options_layout = QVBoxLayout(options_group)

        self.auto_grade_check = QCheckBox("QRコード読み取り後、自動で採点を開始")
        self.auto_grade_check.setChecked(False)
        options_layout.addWidget(self.auto_grade_check)

        self.auto_export_check = QCheckBox("採点完了後、自動でPDF出力")
        self.auto_export_check.setChecked(False)
        options_layout.addWidget(self.auto_export_check)

        layout.addWidget(options_group)

        # 全体プログレス
        progress_group = QGroupBox("処理進捗")
        progress_layout = QVBoxLayout(progress_group)

        self.overall_progress = QProgressBar()
        self.overall_progress.setMinimum(0)
        self.overall_progress.setMaximum(100)
        self.overall_progress.setValue(0)
        self.overall_progress.setStyleSheet("""
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
        progress_layout.addWidget(self.overall_progress)

        self.status_label = QLabel("待機中")
        self.status_label.setStyleSheet("color: #6b6b6b;")
        progress_layout.addWidget(self.status_label)

        layout.addWidget(progress_group)

        # 実行ボタン
        action_layout = QHBoxLayout()
        action_layout.addStretch()

        self.scan_btn = QPushButton("QRコード読み取り")
        self.scan_btn.setEnabled(False)
        self.scan_btn.clicked.connect(self._start_scan)
        self.scan_btn.setStyleSheet("""
            QPushButton {
                background-color: #5c5c5c;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:disabled { background-color: #ccc; }
        """)
        action_layout.addWidget(self.scan_btn)

        self.start_btn = QPushButton("一括採点開始")
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._start_batch)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #00a86b;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #009060; }
            QPushButton:disabled { background-color: #ccc; }
        """)
        action_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_batch)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff6b6b;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #ee5a5a; }
            QPushButton:disabled { background-color: #ccc; }
        """)
        action_layout.addWidget(self.stop_btn)

        layout.addLayout(action_layout)

    def _add_files(self):
        """ファイルを追加"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "PDFファイルを選択",
            str(Path.home() / "Desktop"),
            "PDF Files (*.pdf)"
        )

        for path in file_paths:
            self._add_job(Path(path))

        self._update_table()
        self._update_buttons()

    def _add_folder(self):
        """フォルダ内のPDFを追加"""
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "フォルダを選択",
            str(Path.home() / "Desktop")
        )

        if folder_path:
            folder = Path(folder_path)
            for pdf_file in folder.glob("*.pdf"):
                self._add_job(pdf_file)

        self._update_table()
        self._update_buttons()

    def _add_job(self, pdf_path: Path):
        """ジョブを追加"""
        # 重複チェック
        for job in self._jobs:
            if job.pdf_path == pdf_path:
                return

        job = BatchJob(pdf_path=pdf_path)
        self._jobs.append(job)

    def _clear_jobs(self):
        """ジョブをクリア"""
        if self._is_processing:
            QMessageBox.warning(self, "クリア", "処理中はクリアできません")
            return

        self._jobs.clear()
        self._update_table()
        self._update_buttons()

    def _update_table(self):
        """テーブルを更新"""
        self.job_table.setRowCount(len(self._jobs))

        for row, job in enumerate(self._jobs):
            # ファイル名
            name_item = QTableWidgetItem(job.pdf_path.name)
            name_item.setToolTip(str(job.pdf_path))
            self.job_table.setItem(row, 0, name_item)

            # ステータス
            status_item = QTableWidgetItem(job.status)
            status_color = {
                "待機中": QColor("#6b6b6b"),
                "処理中": QColor("#2eaadc"),
                "完了": QColor("#00a86b"),
                "エラー": QColor("#ff6b6b"),
            }.get(job.status, QColor("#6b6b6b"))
            status_item.setForeground(status_color)
            self.job_table.setItem(row, 1, status_item)

            # 年度
            year_item = QTableWidgetItem(
                f"{job.year}年度" if job.year else "-"
            )
            self.job_table.setItem(row, 2, year_item)

            # クラス
            class_item = QTableWidgetItem(
                f"高2英語{job.class_name}" if job.class_name else "-"
            )
            self.job_table.setItem(row, 3, class_item)

            # 学期
            term_item = QTableWidgetItem(job.term or "-")
            self.job_table.setItem(row, 4, term_item)

            # 週
            week_item = QTableWidgetItem(
                f"第{job.week}週" if job.week else "-"
            )
            self.job_table.setItem(row, 5, week_item)

            # 進捗
            if job.page_count > 0:
                progress_text = f"{job.graded_count}/{job.page_count}"
            else:
                progress_text = "-"
            progress_item = QTableWidgetItem(progress_text)
            self.job_table.setItem(row, 6, progress_item)

    def _update_buttons(self):
        """ボタン状態を更新"""
        has_jobs = len(self._jobs) > 0

        if self._is_processing:
            self.add_files_btn.setEnabled(False)
            self.add_folder_btn.setEnabled(False)
            self.clear_btn.setEnabled(False)
            self.scan_btn.setEnabled(False)
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
        else:
            self.add_files_btn.setEnabled(True)
            self.add_folder_btn.setEnabled(True)
            self.clear_btn.setEnabled(has_jobs)
            self.scan_btn.setEnabled(has_jobs)

            # 採点開始はQRスキャン完了後のみ
            has_scanned = any(job.class_name for job in self._jobs)
            self.start_btn.setEnabled(has_jobs and has_scanned)
            self.stop_btn.setEnabled(False)

    def _start_scan(self):
        """QRコード読み取り開始"""
        self._is_processing = True
        self._update_buttons()
        self.status_label.setText("QRコード読み取り中...")
        self.batch_started.emit()

        # BatchScanWorkerを使って処理
        from app.workers.batch_worker import BatchScanWorker
        self._scan_worker = BatchScanWorker([job.pdf_path for job in self._jobs])
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.job_scanned.connect(self._on_job_scanned)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()

    def _on_scan_progress(self, current: int, total: int, message: str):
        """スキャン進捗"""
        progress = int(current / total * 100) if total > 0 else 0
        self.overall_progress.setValue(progress)
        self.status_label.setText(message)

    def _on_job_scanned(self, index: int, student_info: dict):
        """ジョブスキャン完了"""
        if index < len(self._jobs):
            job = self._jobs[index]
            job.status = "完了"
            job.year = student_info.get("year")
            job.term = student_info.get("term")
            job.week = student_info.get("week")
            job.class_name = student_info.get("class_name")
            job.page_count = student_info.get("page_count", 0)
            self._update_table()

    def _on_scan_finished(self):
        """スキャン完了"""
        self._is_processing = False
        self._update_buttons()
        self.overall_progress.setValue(100)
        self.status_label.setText("QRコード読み取り完了")

        # 自動採点が有効なら開始
        if self.auto_grade_check.isChecked():
            self._start_batch()

    def _on_scan_error(self, error: str):
        """スキャンエラー"""
        self._is_processing = False
        self._update_buttons()
        self.status_label.setText(f"エラー: {error}")
        QMessageBox.critical(self, "スキャンエラー", error)

    def _start_batch(self):
        """一括採点開始"""
        self._is_processing = True
        self._update_buttons()
        self.status_label.setText("一括採点中...")
        self.batch_started.emit()

        # BatchGradeWorkerを使って処理
        from app.workers.batch_worker import BatchGradeWorker
        jobs_data = [
            {
                "pdf_path": str(job.pdf_path),
                "year": job.year,
                "term": job.term,
                "week": job.week,
                "class_name": job.class_name,
            }
            for job in self._jobs
            if job.class_name  # QRスキャン済みのみ
        ]
        self._grade_worker = BatchGradeWorker(jobs_data)
        self._grade_worker.progress.connect(self._on_grade_progress)
        self._grade_worker.job_progress.connect(self._on_job_grade_progress)
        self._grade_worker.job_finished.connect(self._on_job_finished)
        self._grade_worker.finished.connect(self._on_batch_finished)
        self._grade_worker.error.connect(self._on_batch_error)
        self._grade_worker.start()

    def _on_grade_progress(self, current: int, total: int, message: str):
        """採点進捗"""
        progress = int(current / total * 100) if total > 0 else 0
        self.overall_progress.setValue(progress)
        self.status_label.setText(message)

    def _on_job_grade_progress(self, job_index: int, page: int, total: int):
        """ジョブ内の採点進捗"""
        if job_index < len(self._jobs):
            job = self._jobs[job_index]
            job.status = "処理中"
            job.graded_count = page
            job.page_count = total
            self._update_table()

    def _on_job_finished(self, job_index: int, results: list):
        """ジョブ完了"""
        if job_index < len(self._jobs):
            job = self._jobs[job_index]
            job.status = "完了"
            job.graded_count = len(results)
            self._update_table()

    def _on_batch_finished(self, all_results: list):
        """一括処理完了"""
        self._is_processing = False
        self._update_buttons()
        self.overall_progress.setValue(100)
        self.status_label.setText("一括採点完了")
        self.batch_finished.emit(all_results)

        QMessageBox.information(
            self, "完了",
            f"一括採点が完了しました。\n{len(all_results)} ファイルを処理しました。"
        )

    def _on_batch_error(self, error: str):
        """一括処理エラー"""
        self._is_processing = False
        self._update_buttons()
        self.status_label.setText(f"エラー: {error}")
        QMessageBox.critical(self, "採点エラー", error)

    def _stop_batch(self):
        """一括処理停止"""
        if hasattr(self, '_scan_worker') and self._scan_worker.isRunning():
            self._scan_worker.cancel()
        if hasattr(self, '_grade_worker') and self._grade_worker.isRunning():
            self._grade_worker.cancel()

        self._is_processing = False
        self._update_buttons()
        self.status_label.setText("停止しました")

    def get_jobs(self) -> list[BatchJob]:
        """ジョブリストを取得"""
        return self._jobs.copy()
