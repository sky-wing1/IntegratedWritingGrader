"""PDF出力パネル"""

from __future__ import annotations
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QPushButton, QFileDialog, QTextEdit,
    QCheckBox, QProgressBar
)
from PyQt6.QtCore import Qt, pyqtSignal

from app.utils.config import Config
from app.utils.criteria_parser import GradingCriteria, _default_criteria

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False


class ExportPanel(QWidget):
    """PDF出力パネル"""

    export_complete = pyqtSignal(str)  # 出力ファイルパス

    def __init__(self):
        super().__init__()
        self._results: list[dict] = []
        self._source_pdf: str | None = None
        self._criteria: GradingCriteria = _default_criteria()
        self._setup_ui()

    def set_criteria(self, criteria: GradingCriteria):
        """採点基準を設定"""
        self._criteria = criteria

    def _setup_ui(self):
        """UI構築"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # タイトル
        title = QLabel("PDF出力")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #37352f;")
        layout.addWidget(title)

        # オプション
        options_group = QGroupBox("出力オプション")
        options_layout = QVBoxLayout(options_group)

        self.include_scores = QCheckBox("得点を含める")
        self.include_scores.setChecked(True)
        options_layout.addWidget(self.include_scores)

        self.include_comments = QCheckBox("コメントを含める")
        self.include_comments.setChecked(True)
        options_layout.addWidget(self.include_comments)

        self.include_corrected = QCheckBox("添削答案を含める")
        self.include_corrected.setChecked(True)
        options_layout.addWidget(self.include_corrected)

        layout.addWidget(options_group)

        # プレビュー
        preview_group = QGroupBox("出力プレビュー")
        preview_layout = QVBoxLayout(preview_group)

        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMinimumHeight(200)
        self.preview_text.setStyleSheet("""
            QTextEdit {
                background-color: #fafafa;
                font-family: monospace;
                font-size: 12px;
            }
        """)
        preview_layout.addWidget(self.preview_text)

        layout.addWidget(preview_group)

        # プログレス
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 出力ボタン
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.export_btn = QPushButton("PDFを出力")
        self.export_btn.setStyleSheet("""
            QPushButton {
                background-color: #2eaadc;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 12px 32px;
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
        self.export_btn.clicked.connect(self._export_pdf)
        button_layout.addWidget(self.export_btn)

        layout.addLayout(button_layout)
        layout.addStretch()

    def set_data(self, source_pdf: str, results: list[dict]):
        """データをセット"""
        self._source_pdf = source_pdf
        self._results = results
        self._update_preview()

    def _update_preview(self):
        """プレビュー更新"""
        if not self._results:
            self.preview_text.setText("採点結果がありません")
            return

        lines = []
        for result in self._results:
            page = result.get("page", "?")
            score = result.get("total_score", "?")
            lines.append(f"ページ {page}: {score}点")

            if self.include_comments.isChecked():
                if result.get("content_comment"):
                    lines.append(f"  内容: {result['content_comment'][:50]}...")
                if result.get("expression_comment"):
                    lines.append(f"  表現: {result['expression_comment'][:50]}...")

            lines.append("")

        self.preview_text.setText("\n".join(lines))

    def _export_pdf(self):
        """PDF出力"""
        if not self._source_pdf or not self._results:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "採点済みPDFを保存",
            str(Config.get_output_dir() / "graded.pdf"),
            "PDF Files (*.pdf)"
        )

        if not file_path:
            return

        if not HAS_PYMUPDF:
            self.preview_text.setText("PyMuPDFがインストールされていません")
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(self._results))
        self.export_btn.setEnabled(False)

        try:
            doc = fitz.open(self._source_pdf)

            # 日本語フォントを準備（ヒラギノ or システムフォント）
            font_path = None
            possible_fonts = [
                "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
                "/System/Library/Fonts/Hiragino Sans GB.ttc",
                "/Library/Fonts/Arial Unicode.ttf",
            ]
            for fp in possible_fonts:
                if Path(fp).exists():
                    font_path = fp
                    break

            for i, result in enumerate(self._results):
                page_num = result.get("page", i + 1) - 1
                if page_num < 0 or page_num >= len(doc):
                    continue

                page = doc[page_num]
                page_rect = page.rect

                # 注釈テキスト作成
                annot_text = self._format_annotation(result)

                # 【採点欄】エリアに配置
                # 座標: 左上原点で X=186.7mm, Y=86.8mm, W=162.3mm, H=115mm
                def mm_to_pt(mm):
                    return mm * 72 / 25.4

                box_x = mm_to_pt(186.7)
                box_y = mm_to_pt(86.8)
                box_w = mm_to_pt(162.3)
                box_h = mm_to_pt(115)

                rect = fitz.Rect(
                    box_x,
                    box_y,
                    box_x + box_w,
                    box_y + box_h
                )

                # 日本語フォントでテキスト挿入
                if font_path:
                    page.insert_textbox(
                        rect,
                        annot_text,
                        fontsize=8,
                        fontfile=font_path,
                        fontname="F0",
                        color=(0, 0, 0.5),  # 濃い青
                    )
                else:
                    # フォールバック：注釈として追加
                    annot = page.add_freetext_annot(
                        rect,
                        annot_text,
                        fontsize=8,
                        text_color=(0, 0, 0.5),
                    )

                self.progress_bar.setValue(i + 1)

            doc.save(file_path)
            doc.close()

            self.preview_text.setText(f"出力完了: {file_path}")
            self.export_complete.emit(file_path)

        except Exception as e:
            self.preview_text.setText(f"出力エラー: {e}")

        finally:
            self.progress_bar.setVisible(False)
            self.export_btn.setEnabled(True)

    def _format_annotation(self, result: dict) -> str:
        """注釈テキストをフォーマット"""
        lines = []

        if self.include_scores.isChecked():
            total = result.get("total_score", "?")
            content = result.get("content_score", "?")
            deduction = result.get("expression_deduction", "?")

            lines.append(f"【得点】{total}点")

            # 動的な採点基準から詳細を取得
            detail_parts = []
            for i, criterion in enumerate(self._criteria.criteria):
                key_prefix = f"criterion{i+1}_"
                judgment = result.get(f"{key_prefix}judgment", "")
                score = result.get(f"{key_prefix}score", "")

                # レガシーキーも試す
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

        if self.include_comments.isChecked():
            if result.get("content_comment"):
                lines.append("【内容】")
                lines.append(self._add_list_breaks(result["content_comment"]))
                lines.append("")

            if result.get("expression_comment"):
                lines.append("【表現】")
                lines.append(self._add_list_breaks(result["expression_comment"]))
                lines.append("")

        if self.include_corrected.isChecked() and result.get("corrected_text"):
            lines.append("【添削】")
            lines.append(result["corrected_text"])
            lines.append("")

        if self.include_comments.isChecked() and result.get("revision_points"):
            lines.append("【書き直し】")
            lines.append(self._add_list_breaks(result["revision_points"]))

        return "\n".join(lines)

    def _add_list_breaks(self, text: str) -> str:
        """箇条書き番号の前に改行を追加"""
        import re
        # 「1. 」「2. 」「①」「②」などの前に改行を追加
        # ただし文頭の場合は追加しない
        result = re.sub(r'(?<!^)(\d+\.\s)', r'\n\1', text)
        result = re.sub(r'(?<!^)([①②③④⑤⑥⑦⑧⑨⑩])', r'\n\1', result)
        result = re.sub(r'(?<!^)(・)', r'\n\1', result)
        return result
