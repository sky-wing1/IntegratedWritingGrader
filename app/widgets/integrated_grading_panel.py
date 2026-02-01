"""統合採点・編集パネル"""

from __future__ import annotations
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QLabel, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal

from app.widgets.pdf_preview import PDFPreviewWidget
from app.widgets.feedback_editor import FeedbackEditorWidget
from app.widgets.progress_panel import ProgressPanel
from app.utils.criteria_parser import GradingCriteria
from app.utils.additional_answer_manager import AdditionalAnswerItem


class IntegratedGradingPanel(QWidget):
    """統合採点・編集パネル

    左側: PDFプレビュー + ページリスト
    右側: 進捗パネル + フィードバック編集
    """

    result_updated = pyqtSignal(int, dict)  # ページ番号, 更新データ

    def __init__(self):
        super().__init__()
        self._results: list[dict] = []
        self._current_index = -1
        self._is_additional_mode = False
        self._additional_items: list[AdditionalAnswerItem] = []
        self._additional_dir: Path | None = None
        self._setup_ui()

    def _setup_ui(self):
        """UI構築"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 追加答案モードヘッダー
        self.additional_header = QWidget()
        self.additional_header.setStyleSheet("""
            QWidget {
                background-color: #fff3cd;
                border-bottom: 1px solid #ffc107;
            }
        """)
        self.additional_header.setVisible(False)
        header_layout = QHBoxLayout(self.additional_header)
        header_layout.setContentsMargins(16, 8, 16, 8)

        self.additional_label = QLabel("追加答案モード")
        self.additional_label.setStyleSheet("font-weight: bold; color: #856404;")
        header_layout.addWidget(self.additional_label)

        header_layout.addStretch()

        self.exit_additional_btn = QPushButton("通常モードに戻る")
        self.exit_additional_btn.setStyleSheet("""
            QPushButton {
                background-color: #856404;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
            }
            QPushButton:hover { background-color: #6c5303; }
        """)
        self.exit_additional_btn.clicked.connect(self._exit_additional_mode)
        header_layout.addWidget(self.exit_additional_btn)

        layout.addWidget(self.additional_header)

        # 上部: 進捗パネル
        self.progress_panel = ProgressPanel()
        layout.addWidget(self.progress_panel)

        # メイン: 左右分割
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左側: PDFプレビュー + ページリスト
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.pdf_preview = PDFPreviewWidget()
        self.pdf_preview.page_changed.connect(self._on_pdf_page_changed)
        left_layout.addWidget(self.pdf_preview, 1)

        # ページリスト（採点済みページを表示）
        list_container = QWidget()
        list_container.setStyleSheet("background-color: #f7f6f3; border-top: 1px solid #e0e0e0;")
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(8, 8, 8, 8)
        list_layout.setSpacing(4)

        list_header = QLabel("採点結果一覧")
        list_header.setStyleSheet("font-size: 12px; font-weight: bold; color: #37352f;")
        list_layout.addWidget(list_header)

        self.page_list = QListWidget()
        self.page_list.setMaximumHeight(150)
        self.page_list.setStyleSheet("""
            QListWidget {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:selected {
                background-color: #e8f4fc;
                color: #37352f;
            }
            QListWidget::item:hover:!selected {
                background-color: #f5f5f5;
            }
        """)
        self.page_list.currentRowChanged.connect(self._on_list_selection_changed)
        list_layout.addWidget(self.page_list)

        left_layout.addWidget(list_container)

        splitter.addWidget(left_widget)

        # 右側: フィードバック編集
        right_widget = QWidget()
        right_widget.setStyleSheet("background-color: #fafafa;")
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.feedback_editor = FeedbackEditorWidget()
        self.feedback_editor.data_changed.connect(self._on_data_changed)
        right_layout.addWidget(self.feedback_editor)

        splitter.addWidget(right_widget)

        # 分割比率（左:右 = 3:2）
        splitter.setSizes([600, 400])

        layout.addWidget(splitter, 1)

    def load_pdf(self, pdf_path: str):
        """PDF読み込み（後方互換性用）"""
        self.pdf_preview.load_pdf(pdf_path)

    def load_cropped_images(self, cropped_dir: Path):
        """croppedフォルダの画像を読み込み"""
        image_files = sorted(cropped_dir.glob("*.png"))
        if image_files:
            self.pdf_preview.load_images([str(f) for f in image_files])

    def set_criteria(self, criteria: GradingCriteria):
        """採点基準を設定"""
        self.feedback_editor.set_criteria(criteria)

    def set_results(self, results: list[dict]):
        """採点結果をセット"""
        self._results = results
        self._update_page_list()
        if results:
            self._select_page(0)

    def get_results(self) -> list[dict]:
        """全結果を取得"""
        return self._results

    def _on_pdf_page_changed(self, page_num: int):
        """PDFページ変更時（PDFプレビューから）"""
        # 対応するresultのインデックスを検索
        for i, result in enumerate(self._results):
            if result.get("page", i + 1) == page_num:
                self._select_page(i, sync_pdf=False)
                return

        # 結果がない場合はフィードバックをクリア
        self.feedback_editor.clear()
        self._current_index = -1
        self.page_list.blockSignals(True)
        self.page_list.clearSelection()
        self.page_list.blockSignals(False)

    def _on_list_selection_changed(self, index: int):
        """リスト選択変更時"""
        if index >= 0:
            self._select_page(index)

    def _select_page(self, index: int, sync_pdf: bool = True):
        """ページを選択"""
        if index < 0 or index >= len(self._results):
            return

        self._current_index = index
        result = self._results[index]

        # フィードバック編集パネルを更新
        self.feedback_editor.set_data(result)

        # PDFプレビューを同期（必要な場合）
        if sync_pdf:
            if self._is_additional_mode and result.get("image_path"):
                # 追加答案モード: 画像を表示
                self.pdf_preview.load_image(result["image_path"])
            else:
                # 通常モード: PDFページを表示
                page_num = result.get("page", index + 1)
                self.pdf_preview.set_page(page_num)

        # リスト選択を同期
        self.page_list.blockSignals(True)
        self.page_list.setCurrentRow(index)
        self.page_list.blockSignals(False)

    def _on_data_changed(self, data: dict):
        """フィードバックデータ変更時"""
        if self._current_index < 0 or self._current_index >= len(self._results):
            return

        # 内部データ更新
        self._results[self._current_index].update(data)

        # リスト表示更新
        self._update_list_item(self._current_index)

        # シグナル発火
        page_num = self._results[self._current_index].get("page", self._current_index + 1)
        self.result_updated.emit(page_num, data)

    def _update_page_list(self):
        """ページリスト更新"""
        self.page_list.clear()
        for i, result in enumerate(self._results):
            page_num = result.get("page", i + 1)
            score = result.get("total_score")
            score_text = f"{score}点" if score is not None else "未採点"
            student = result.get("student_name", "")

            item_text = f"P{page_num}: {score_text}"
            if student:
                item_text += f" ({student})"

            item = QListWidgetItem(item_text)

            # 色分け
            if score is not None:
                if score >= 10:
                    item.setForeground(Qt.GlobalColor.darkGreen)
                elif score >= 6:
                    item.setForeground(Qt.GlobalColor.darkYellow)
                else:
                    item.setForeground(Qt.GlobalColor.red)

            self.page_list.addItem(item)

    def _update_list_item(self, index: int):
        """リストアイテム更新"""
        if index < 0 or index >= len(self._results):
            return

        result = self._results[index]
        page_num = result.get("page", index + 1)
        score = result.get("total_score")
        score_text = f"{score}点" if score is not None else "未採点"
        student = result.get("student_name", "")

        item_text = f"P{page_num}: {score_text}"
        if student:
            item_text += f" ({student})"

        item = self.page_list.item(index)
        if item:
            item.setText(item_text)

            # 色分け
            if score is not None:
                if score >= 10:
                    item.setForeground(Qt.GlobalColor.darkGreen)
                elif score >= 6:
                    item.setForeground(Qt.GlobalColor.darkYellow)
                else:
                    item.setForeground(Qt.GlobalColor.red)

    def load_additional_answers(self, additional_dir: Path, items: list):
        """追加答案を読み込み"""
        self._is_additional_mode = True
        self._additional_items = items
        self._additional_dir = Path(additional_dir)

        # ヘッダーを表示
        self.additional_header.setVisible(True)
        first_item = items[0] if items else None
        if first_item:
            self.additional_label.setText(
                f"追加答案モード - 第{first_item.target_week:02d}週 ({len(items)}件)"
            )

        # 結果リストを初期化（画像パスを設定）
        self._results = []
        for i, item in enumerate(items):
            image_path = self._additional_dir / item.filename
            self._results.append({
                "page": i + 1,
                "student_name": item.student_name,
                "attendance_no": item.attendance_no,
                "image_path": str(image_path),
                "total_score": None,
                "content_score": None,
                "expression_deduction": None,
                "content_comment": "",
                "expression_comment": "",
                "corrected_text": "",
                "revision_points": "",
            })

        self._update_page_list()
        if self._results:
            self._select_page(0)

    def _exit_additional_mode(self):
        """追加答案モードを終了"""
        self._is_additional_mode = False
        self._additional_items = []
        self._additional_dir = None
        self.additional_header.setVisible(False)
        self._results = []
        self._update_page_list()
        self.feedback_editor.clear()

    def is_additional_mode(self) -> bool:
        """追加答案モードかどうか"""
        return self._is_additional_mode

    def get_additional_dir(self) -> Path | None:
        """追加答案ディレクトリを取得"""
        return self._additional_dir
