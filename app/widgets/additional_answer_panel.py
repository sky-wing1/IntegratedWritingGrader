"""追加答案専用パネル（採点・編集・PDF出力を統合）"""

from __future__ import annotations
import json
import re
import subprocess
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QLabel, QPushButton,
    QGroupBox, QCheckBox, QProgressBar, QFileDialog,
    QMessageBox, QComboBox, QSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QShortcut, QKeySequence

from app.widgets.pdf_preview import PDFPreviewWidget
from app.widgets.feedback_editor import FeedbackEditorWidget
from app.utils.config import Config
from app.utils.criteria_parser import GradingCriteria, _default_criteria
from app.utils.additional_answer_manager import AdditionalAnswerItem
from app.workers.grading_worker import GradingWorker, _find_gemini_command
from app.workers.ocr_worker import OcrWorker

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False


class AdditionalAnswerPanel(QWidget):
    """追加答案専用パネル

    追加答案の採点・編集・PDF出力を1つのタブで完結させる。
    """

    status_message = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._results: list[dict] = []
        self._additional_dir: Path | None = None
        self._additional_items: list[AdditionalAnswerItem] = []
        self._source_pdf: str | None = None
        self._criteria: GradingCriteria = _default_criteria()
        self._prompt_file: Path | None = None
        self._grading_worker: GradingWorker | None = None
        self._ocr_worker: OcrWorker | None = None
        self._pending_image_files: list | None = None
        self._current_index = -1
        self._is_grading = False
        self._setup_ui()
        self._setup_shortcuts()

    def _setup_shortcuts(self):
        save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        save_shortcut.activated.connect(self._save_results)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ヘッダー
        self._header = QWidget()
        self._header.setStyleSheet("""
            QWidget {
                background-color: #fff3cd;
                border-bottom: 1px solid #ffc107;
            }
        """)
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(16, 8, 16, 8)

        self._header_label = QLabel("追加答案")
        self._header_label.setStyleSheet("font-weight: bold; color: #856404; font-size: 14px;")
        header_layout.addWidget(self._header_label)
        header_layout.addStretch()

        self._clear_btn = QPushButton("クリア")
        self._clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #856404; color: white;
                border: none; border-radius: 4px; padding: 4px 12px;
            }
            QPushButton:hover { background-color: #6c5303; }
        """)
        self._clear_btn.clicked.connect(self.clear)
        header_layout.addWidget(self._clear_btn)

        layout.addWidget(self._header)

        # 進捗バー
        self._progress_widget = QWidget()
        self._progress_widget.setFixedHeight(80)
        self._progress_widget.setStyleSheet("""
            QWidget {
                background-color: #f7f6f3;
                border-bottom: 1px solid #e0e0e0;
            }
        """)
        prog_layout = QVBoxLayout(self._progress_widget)
        prog_layout.setContentsMargins(16, 8, 16, 8)
        prog_layout.setSpacing(6)

        prog_top = QHBoxLayout()
        self._status_label = QLabel("待機中")
        self._status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #37352f;")
        prog_top.addWidget(self._status_label)
        prog_top.addStretch()
        prog_layout.addLayout(prog_top)

        prog_bottom = QHBoxLayout()
        self._detail_label = QLabel("追加答案を読み込んでください")
        self._detail_label.setStyleSheet("font-size: 12px; color: #9b9a97;")
        prog_bottom.addWidget(self._detail_label, 1)

        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedWidth(250)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #e0e0e0; border-radius: 4px;
                text-align: center; background-color: #fff;
            }
            QProgressBar::chunk {
                background-color: #f0ad4e; border-radius: 3px;
            }
        """)
        prog_bottom.addWidget(self._progress_bar)
        prog_bottom.addSpacing(16)

        self._grade_btn = QPushButton("採点開始")
        self._grade_btn.setFixedWidth(100)
        self._grade_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0ad4e; color: white;
                border: none; border-radius: 6px; padding: 8px 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #ec971f; }
            QPushButton:disabled { background-color: #ccc; }
        """)
        self._grade_btn.clicked.connect(self._toggle_grading)
        self._grade_btn.setEnabled(False)
        prog_bottom.addWidget(self._grade_btn)

        self._save_btn = QPushButton("保存")
        self._save_btn.setFixedWidth(80)
        self._save_btn.setStyleSheet("""
            QPushButton {
                background-color: #0f7b0f; color: white;
                border: none; border-radius: 6px; padding: 8px 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #0d6b0d; }
            QPushButton:disabled { background-color: #ccc; }
        """)
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save_results)
        prog_bottom.addWidget(self._save_btn)

        prog_layout.addLayout(prog_bottom)
        layout.addWidget(self._progress_widget)

        # メイン: 左右分割
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左側: プレビュー + リスト
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self._preview = PDFPreviewWidget()
        left_layout.addWidget(self._preview, 1)

        list_container = QWidget()
        list_container.setStyleSheet("background-color: #f7f6f3; border-top: 1px solid #e0e0e0;")
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(8, 8, 8, 8)
        list_layout.setSpacing(4)

        list_header = QLabel("追加答案一覧")
        list_header.setStyleSheet("font-size: 12px; font-weight: bold; color: #37352f;")
        list_layout.addWidget(list_header)

        self._page_list = QListWidget()
        self._page_list.setMaximumHeight(150)
        self._page_list.setStyleSheet("""
            QListWidget {
                background-color: white; border: 1px solid #e0e0e0; border-radius: 4px;
            }
            QListWidget::item {
                padding: 6px 8px; border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:selected {
                background-color: #fff3cd; color: #37352f;
            }
            QListWidget::item:hover:!selected {
                background-color: #f5f5f5;
            }
        """)
        self._page_list.currentRowChanged.connect(self._on_list_selection_changed)
        list_layout.addWidget(self._page_list)

        left_layout.addWidget(list_container)
        splitter.addWidget(left_widget)

        # 右側: フィードバック編集 + 出力
        right_widget = QWidget()
        right_widget.setStyleSheet("background-color: #fafafa;")
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self._feedback_editor = FeedbackEditorWidget()
        self._feedback_editor.data_changed.connect(self._on_data_changed)
        right_layout.addWidget(self._feedback_editor, 1)

        # PDF出力セクション
        export_container = QWidget()
        export_container.setStyleSheet("""
            QWidget { background-color: #f7f6f3; border-top: 1px solid #e0e0e0; }
        """)
        export_layout = QVBoxLayout(export_container)
        export_layout.setContentsMargins(12, 8, 12, 8)
        export_layout.setSpacing(6)

        export_header = QLabel("PDF出力")
        export_header.setStyleSheet("font-size: 12px; font-weight: bold; color: #37352f;")
        export_layout.addWidget(export_header)

        # チェックボックス
        cb_row = QHBoxLayout()
        self._cb_scores = QCheckBox("得点")
        self._cb_scores.setChecked(True)
        cb_row.addWidget(self._cb_scores)
        self._cb_comments = QCheckBox("コメント")
        self._cb_comments.setChecked(True)
        cb_row.addWidget(self._cb_comments)
        self._cb_corrected = QCheckBox("添削")
        self._cb_corrected.setChecked(True)
        cb_row.addWidget(self._cb_corrected)
        self._cb_stamp = QCheckBox("スタンプ")
        self._cb_stamp.setChecked(True)
        cb_row.addWidget(self._cb_stamp)
        cb_row.addStretch()
        export_layout.addLayout(cb_row)

        # 出力ボタン行
        export_btn_row = QHBoxLayout()

        self._export_progress = QProgressBar()
        self._export_progress.setFixedWidth(200)
        self._export_progress.setVisible(False)
        export_btn_row.addWidget(self._export_progress)
        export_btn_row.addStretch()

        self._export_btn = QPushButton("PDFを出力")
        self._export_btn.setStyleSheet("""
            QPushButton {
                background-color: #2eaadc; color: white;
                border: none; border-radius: 4px; padding: 8px 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2496c4; }
            QPushButton:disabled { background-color: #ccc; }
        """)
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._export_pdf)
        export_btn_row.addWidget(self._export_btn)

        export_layout.addLayout(export_btn_row)
        right_layout.addWidget(export_container)

        splitter.addWidget(right_widget)
        splitter.setSizes([600, 400])

        layout.addWidget(splitter, 1)

        # 初期状態: 空の案内表示
        self._empty_label = QLabel("PDF読み込みタブで追加答案を検出し、\n「選択した答案を採点」で採点を開始します。")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("font-size: 14px; color: #9b9a97; padding: 40px;")
        layout.addWidget(self._empty_label)

        # メイン部分を初期非表示
        self._header.setVisible(False)
        self._progress_widget.setVisible(False)
        splitter.setVisible(False)
        self._splitter = splitter

    # ---- Public API ----

    def load_additional_answers(
        self,
        additional_dir: Path,
        items: list[AdditionalAnswerItem],
        criteria: GradingCriteria,
        source_pdf: str | None,
        prompt_file: Path | None = None,
    ):
        """追加答案を読み込み、採点準備をする"""
        self._additional_dir = Path(additional_dir)
        self._additional_items = items
        self._criteria = criteria
        self._prompt_file = prompt_file
        self._source_pdf = source_pdf

        # UIを表示
        self._empty_label.setVisible(False)
        self._header.setVisible(True)
        self._progress_widget.setVisible(True)
        self._splitter.setVisible(True)

        # ヘッダー更新
        first = items[0] if items else None
        if first:
            self._header_label.setText(
                f"追加答案 - 第{first.target_week:02d}週 ({len(items)}件)"
            )

        # 採点基準をエディターに設定
        self._feedback_editor.set_criteria(criteria)

        # 結果リスト初期化
        self._results = []
        for i, item in enumerate(items):
            image_path = self._additional_dir / item.filename
            self._results.append({
                "page": i + 1,
                "student_name": item.student_name,
                "attendance_no": item.attendance_no,
                "image_path": str(image_path),
                "original_page": item.original_page,
                "total_score": None,
                "content_score": None,
                "expression_deduction": None,
                "content_comment": "",
                "expression_comment": "",
                "corrected_text": "",
                "revision_points": "",
            })

        # 既存の採点結果があれば読み込み
        self._load_existing_results()

        self._update_page_list()
        if self._results:
            self._select_page(0)

        self._grade_btn.setEnabled(True)
        self._status_label.setText("待機中")
        self._detail_label.setText(f"{len(items)}件の追加答案を読み込みました")
        if first:
            self.status_message.emit(f"追加答案: 第{first.target_week}週 ({len(items)}件)")
        else:
            self.status_message.emit("追加答案を読み込みました")

    def clear(self):
        """状態をクリア"""
        # ワーカー停止
        self._stop_grading_workers()

        self._results = []
        self._additional_dir = None
        self._additional_items = []
        self._source_pdf = None
        self._current_index = -1
        self._is_grading = False

        self._page_list.clear()
        self._feedback_editor.clear()
        self._preview.clear() if hasattr(self._preview, 'clear') else None

        # UI非表示
        self._header.setVisible(False)
        self._progress_widget.setVisible(False)
        self._splitter.setVisible(False)
        self._empty_label.setVisible(True)

        self._grade_btn.setEnabled(False)
        self._grade_btn.setText("採点開始")
        self._save_btn.setEnabled(False)
        self._export_btn.setEnabled(False)
        self._status_label.setText("待機中")
        self._detail_label.setText("追加答案を読み込んでください")
        self._progress_bar.setValue(0)

        self.status_message.emit("追加答案をクリアしました")

    def has_data(self) -> bool:
        """データがあるか"""
        return len(self._results) > 0

    # ---- 既存結果の読み込み ----

    def _load_existing_results(self):
        """additional_results.json から既存の採点結果を読み込み"""
        if not self._additional_dir:
            return

        results_path = self._additional_dir / "additional_results.json"
        if not results_path.exists():
            return

        try:
            with open(results_path, "r", encoding="utf-8") as f:
                saved = json.load(f)

            if not isinstance(saved, list) or len(saved) != len(self._results):
                return

            # 既存結果をマージ（画像パスなどは保持）
            for i, saved_result in enumerate(saved):
                for key in ("total_score", "content_score", "expression_deduction",
                            "content_comment", "expression_comment",
                            "corrected_text", "revision_points", "original_text"):
                    if key in saved_result:
                        self._results[i][key] = saved_result[key]
                # criterion キーもコピー
                for key in saved_result:
                    if key.startswith("criterion"):
                        self._results[i][key] = saved_result[key]

            self._save_btn.setEnabled(True)
            self._export_btn.setEnabled(True)
            self._status_label.setText("完了")
            self._status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #0f7b0f;")
            self._detail_label.setText("保存済みの採点結果を読み込みました")

        except (json.JSONDecodeError, KeyError, TypeError):
            pass  # 読み込み失敗は無視

    # ---- ページ選択 ----

    def _on_list_selection_changed(self, index: int):
        if index >= 0:
            self._select_page(index)

    def _select_page(self, index: int, sync_preview: bool = True):
        if index < 0 or index >= len(self._results):
            return

        self._current_index = index
        result = self._results[index]

        display_result = result.copy()
        display_result["display_page"] = index + 1
        self._feedback_editor.set_data(display_result)

        if sync_preview and result.get("image_path"):
            self._preview.load_image(result["image_path"])

        self._page_list.blockSignals(True)
        self._page_list.setCurrentRow(index)
        self._page_list.blockSignals(False)

    def _on_data_changed(self, data: dict):
        if self._current_index < 0 or self._current_index >= len(self._results):
            return
        self._results[self._current_index].update(data)
        self._update_list_item(self._current_index)

    def _update_page_list(self):
        self._page_list.clear()
        for i, result in enumerate(self._results):
            display_num = i + 1
            score = result.get("total_score")
            score_text = f"{score}点" if score is not None else "未採点"
            student = result.get("student_name", "")

            item_text = f"P{display_num}: {score_text}"
            if student:
                item_text += f" ({student})"

            item = QListWidgetItem(item_text)
            if score is not None:
                if score >= 10:
                    item.setForeground(Qt.GlobalColor.darkGreen)
                elif score >= 6:
                    item.setForeground(Qt.GlobalColor.darkYellow)
                else:
                    item.setForeground(Qt.GlobalColor.red)

            self._page_list.addItem(item)

    def _update_list_item(self, index: int):
        if index < 0 or index >= len(self._results):
            return
        result = self._results[index]
        display_num = index + 1
        score = result.get("total_score")
        score_text = f"{score}点" if score is not None else "未採点"
        student = result.get("student_name", "")

        item_text = f"P{display_num}: {score_text}"
        if student:
            item_text += f" ({student})"

        item = self._page_list.item(index)
        if item:
            item.setText(item_text)
            if score is not None:
                if score >= 10:
                    item.setForeground(Qt.GlobalColor.darkGreen)
                elif score >= 6:
                    item.setForeground(Qt.GlobalColor.darkYellow)
                else:
                    item.setForeground(Qt.GlobalColor.red)

    # ---- 採点 ----

    def _toggle_grading(self):
        if self._is_grading:
            self._stop_grading()
        else:
            self._start_grading()

    def _start_grading(self):
        if not self._additional_dir:
            return

        image_files = sorted(self._additional_dir.glob("*.png"))
        if not image_files:
            QMessageBox.warning(self, "採点", "追加答案の画像が見つかりません")
            return

        self._is_grading = True
        self._grade_btn.setText("停止")
        self._grade_btn.setStyleSheet("""
            QPushButton {
                background-color: #eb5757; color: white;
                border: none; border-radius: 6px; padding: 8px 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #d64545; }
        """)
        self._status_label.setText("採点中...")
        self._status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #37352f;")

        # Gemini OCR可能かチェック
        use_gemini_ocr = (
            Config.USE_GEMINI_OCR
            and _find_gemini_command() is not None
        )

        if use_gemini_ocr:
            self._pending_image_files = image_files
            self._ocr_worker = OcrWorker(image_files)
            self._ocr_worker.progress.connect(self._on_grading_progress)
            self._ocr_worker.finished.connect(self._on_ocr_finished)
            self._ocr_worker.error.connect(self._on_ocr_error)
            self._ocr_worker.start()
        else:
            self._start_grading_worker(image_files, ocr_results=None)

    def _start_grading_worker(self, image_files, ocr_results=None):
        self._grading_worker = GradingWorker(
            pdf_path="",
            image_files=image_files,
            ocr_results=ocr_results,
            prompt_file=self._prompt_file,
        )
        self._grading_worker.progress.connect(self._on_grading_progress)
        self._grading_worker.result_ready.connect(self._on_result_ready)
        self._grading_worker.finished.connect(self._on_grading_finished)
        self._grading_worker.error.connect(self._on_grading_error)
        self._grading_worker.start()

    def _on_ocr_finished(self, ocr_results: list):
        image_files = self._pending_image_files
        self._pending_image_files = None
        if image_files is None:
            return
        self._start_grading_worker(image_files, ocr_results=ocr_results)

    def _on_ocr_error(self, error_msg: str):
        self.status_message.emit(f"OCRフォールバック: {error_msg}")
        image_files = self._pending_image_files
        self._pending_image_files = None
        self._start_grading_worker(image_files, ocr_results=None)

    def _stop_grading(self):
        self._stop_grading_workers()
        self._is_grading = False
        self._grade_btn.setText("採点開始")
        self._grade_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0ad4e; color: white;
                border: none; border-radius: 6px; padding: 8px 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #ec971f; }
            QPushButton:disabled { background-color: #ccc; }
        """)
        self._status_label.setText("停止")
        self.status_message.emit("追加答案の採点を停止しました")

    def _stop_grading_workers(self):
        if self._ocr_worker and self._ocr_worker.isRunning():
            self._ocr_worker.cancel()
        if self._grading_worker and self._grading_worker.isRunning():
            self._grading_worker.cancel()
        self._pending_image_files = None

    def _on_grading_progress(self, current: int, total: int, message: str):
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        self._detail_label.setText(message)
        self.status_message.emit(message)

    def _on_result_ready(self, page_num: int, result: dict):
        self.status_message.emit(f"追加答案 {page_num} の採点完了")

    def _on_grading_finished(self, results: list):
        self._is_grading = False
        self._grade_btn.setText("採点開始")
        self._grade_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0ad4e; color: white;
                border: none; border-radius: 6px; padding: 8px 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #ec971f; }
            QPushButton:disabled { background-color: #ccc; }
        """)

        # エラーチェック
        error_results = [r for r in results if r.get("error")]
        if len(error_results) == len(results) and results:
            self._status_label.setText("エラー")
            self._status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #eb5757;")
            self._detail_label.setText(error_results[0].get("error", "不明なエラー"))
            return

        # 結果をマージ（画像パスや生徒情報を保持）
        for i, new_result in enumerate(results):
            if i < len(self._results):
                # 既存のメタデータは保持しつつ、採点結果を更新
                for key, val in new_result.items():
                    if key not in ("image_path", "student_name", "attendance_no", "original_page"):
                        self._results[i][key] = val

        self._update_page_list()
        if self._results:
            self._select_page(0)

        self._save_btn.setEnabled(True)
        self._export_btn.setEnabled(True)
        self._status_label.setText("完了")
        self._status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #0f7b0f;")
        self._detail_label.setText(f"採点完了: {len(results)}件")
        self.status_message.emit(f"追加答案の採点完了: {len(results)}件")

        if error_results:
            QMessageBox.warning(
                self, "一部エラー",
                f"{len(results)}件中{len(error_results)}件でエラーが発生しました。"
            )

    def _on_grading_error(self, error: str):
        self._is_grading = False
        self._grade_btn.setText("再試行")
        self._grade_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0ad4e; color: white;
                border: none; border-radius: 6px; padding: 8px 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #ec971f; }
            QPushButton:disabled { background-color: #ccc; }
        """)
        self._status_label.setText("エラー")
        self._status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #eb5757;")
        self._detail_label.setText(error)
        self.status_message.emit(f"採点エラー: {error}")
        QMessageBox.critical(self, "採点エラー", error)

    # ---- 保存 ----

    def _save_results(self):
        if not self._results or not self._additional_dir:
            self.status_message.emit("保存する採点結果がありません")
            return

        try:
            saved_path = self._additional_dir / "additional_results.json"
            with open(saved_path, "w", encoding="utf-8") as f:
                json.dump(self._results, f, ensure_ascii=False, indent=2)

            self._status_label.setText("保存済み")
            self._status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #0f7b0f;")
            self._detail_label.setText(f"保存先: {saved_path}")
            self.status_message.emit(f"追加答案の採点結果を保存: {saved_path}")

            # 保存ボタンの一時的なフィードバック
            self._save_btn.setText("保存済")
            QTimer.singleShot(2000, lambda: self._save_btn.setText("保存"))

        except Exception as e:
            self.status_message.emit(f"保存エラー: {e}")
            QMessageBox.critical(self, "保存エラー", str(e))

    # ---- PDF出力 ----

    def _export_pdf(self):
        if not self._source_pdf or not self._results:
            QMessageBox.warning(self, "PDF出力", "ソースPDFまたは採点結果がありません")
            return

        if not HAS_PYMUPDF:
            QMessageBox.warning(self, "PDF出力", "PyMuPDFがインストールされていません")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "追加答案PDFを保存",
            str(Config.get_output_dir() / "graded_additional.pdf"),
            "PDF Files (*.pdf)"
        )
        if not file_path:
            return

        self._export_progress.setVisible(True)
        self._export_progress.setMaximum(len(self._results))
        self._export_btn.setEnabled(False)

        try:
            doc = fitz.open(self._source_pdf)
            font_path = self._find_font()

            def mm_to_pt(mm):
                return mm * 72 / 25.4

            box_x = mm_to_pt(186.7)
            box_y = mm_to_pt(91.8)
            box_w = mm_to_pt(162.3)
            box_h = mm_to_pt(115)

            for i, result in enumerate(self._results):
                page_num = result.get("original_page", result.get("page", i + 1)) - 1
                if page_num < 0 or page_num >= len(doc):
                    continue

                page = doc[page_num]
                annot_text = self._format_annotation(result)
                if not annot_text.strip():
                    continue

                rect = fitz.Rect(box_x, box_y, box_x + box_w, box_y + box_h)
                font_size = 8
                color = (0, 0, 0.5)  # 濃い青

                if font_path:
                    font_obj = fitz.Font(fontfile=font_path)
                    min_size = 4
                    current_size = font_size
                    while current_size >= min_size:
                        tw = fitz.TextWriter(page.rect)
                        excess = tw.fill_textbox(rect, annot_text, font=font_obj, fontsize=current_size)
                        if not excess:
                            tw.write_text(page, color=color)
                            break
                        current_size -= 1
                    else:
                        tw = fitz.TextWriter(page.rect)
                        tw.fill_textbox(rect, annot_text, font=font_obj, fontsize=min_size)
                        tw.write_text(page, color=color)
                else:
                    page.add_freetext_annot(rect, annot_text, fontsize=font_size, text_color=color)

                # スタンプ
                if self._cb_stamp.isChecked():
                    total_score = result.get("total_score", 0)
                    if isinstance(total_score, (int, float)):
                        self._insert_stamp(page, int(total_score))

                self._export_progress.setValue(i + 1)

            doc.save(file_path)
            doc.close()

            self.status_message.emit(f"追加答案PDF出力完了: {file_path}")
            QMessageBox.information(self, "出力完了", f"PDFを出力しました:\n{file_path}")

            try:
                subprocess.run(["open", "-R", file_path], check=False)
            except Exception:
                pass

        except Exception as e:
            QMessageBox.critical(self, "出力エラー", str(e))
            self.status_message.emit(f"PDF出力エラー: {e}")
        finally:
            self._export_progress.setVisible(False)
            self._export_btn.setEnabled(True)

    def _format_annotation(self, result: dict) -> str:
        """注釈テキストをフォーマット"""
        lines = []

        if self._cb_scores.isChecked():
            total = result.get("total_score", "?")
            content = result.get("content_score", "?")
            deduction = result.get("expression_deduction", "?")

            lines.append(f"【得点】{total}点")

            detail_parts = []
            for i, criterion in enumerate(self._criteria.criteria):
                key_prefix = f"criterion{i+1}_"
                judgment = result.get(f"{key_prefix}judgment", "")
                score = result.get(f"{key_prefix}score", "")
                if not judgment:
                    if i == 0:
                        judgment = result.get("logic_judgment", "")
                        score = result.get("logic_score", "")
                    elif i == 1:
                        judgment = result.get("support_judgment", "")
                        score = result.get("support_score", "")
                if judgment:
                    detail_parts.append(f"{criterion.number}{judgment}{score}点")

            if detail_parts:
                lines.append(f"内容{content}点（{' '.join(detail_parts)}）")
            else:
                lines.append(f"（内容{content}点 - 表現{deduction}点）")
            lines.append(f"表現 -{deduction}点")
            lines.append("")

        if self._cb_comments.isChecked():
            if result.get("content_comment"):
                lines.append("【内容】")
                lines.append(self._add_list_breaks(result["content_comment"]))
                lines.append("")
            if result.get("expression_comment"):
                lines.append("【表現】")
                lines.append(self._add_list_breaks(result["expression_comment"]))
                lines.append("")

        if self._cb_corrected.isChecked() and result.get("corrected_text"):
            lines.append("【添削】")
            lines.append(result["corrected_text"])
            lines.append("")

        if self._cb_comments.isChecked() and result.get("revision_points"):
            lines.append("【書き直し】")
            lines.append(self._add_list_breaks(result["revision_points"]))

        return "\n".join(lines)

    @staticmethod
    def _add_list_breaks(text: str) -> str:
        result = re.sub(r'(\d+\.)\s*\n+\s*', r'\1 ', text)
        result = re.sub(r'([①②③④⑤⑥⑦⑧⑨⑩])\s*\n+\s*', r'\1', result)
        result = re.sub(r'(・)\s*\n+\s*', r'\1', result)
        result = re.sub(r'(?<!^)(\d+\.\s)', r'\n\1', result)
        result = re.sub(r'(?<!^)([①②③④⑤⑥⑦⑧⑨⑩])', r'\n\1', result)
        result = re.sub(r'(?<!^)(・)', r'\n\1', result)
        return result

    @staticmethod
    def _find_font() -> str | None:
        """日本語フォントを探す"""
        candidates = [
            "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
            "/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ]
        for path in candidates:
            if Path(path).exists():
                return path
        return None

    def _insert_stamp(self, page, score: int):
        stamp_settings = Config.load_stamp_settings()
        if not stamp_settings.get("enabled", True):
            return
        stamp_path = Config.get_stamp_for_score(score)
        if not stamp_path or not stamp_path.exists():
            return

        def mm_to_pt(mm):
            return mm * 72 / 25.4

        page_rect = page.rect
        stamp_size = mm_to_pt(stamp_settings.get("size", 50))
        margin_x = mm_to_pt(stamp_settings.get("margin_x", 10))
        margin_y = mm_to_pt(stamp_settings.get("margin_y", 10))
        position = stamp_settings.get("position", "top_right")

        if position == "top_right":
            x = page_rect.width - stamp_size - margin_x
            y = margin_y
        elif position == "top_left":
            x = margin_x
            y = margin_y
        elif position == "bottom_right":
            x = page_rect.width - stamp_size - margin_x
            y = page_rect.height - stamp_size - margin_y
        else:
            x = margin_x
            y = page_rect.height - stamp_size - margin_y

        rect = fitz.Rect(x, y, x + stamp_size, y + stamp_size)
        page.insert_image(rect, filename=str(stamp_path))

    def stop_workers(self):
        """アプリ終了時にワーカーを停止"""
        if self._ocr_worker:
            if self._ocr_worker.isRunning():
                self._ocr_worker.cancel()
                self._ocr_worker.wait(3000)
        if self._grading_worker:
            if self._grading_worker.isRunning():
                self._grading_worker.cancel()
                self._grading_worker.wait(3000)
        self._pending_image_files = None
