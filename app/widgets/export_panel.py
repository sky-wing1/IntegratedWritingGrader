"""PDF出力パネル"""

from __future__ import annotations
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QPushButton, QFileDialog, QTextEdit,
    QCheckBox, QProgressBar, QSpinBox, QComboBox
)
from PyQt6.QtCore import pyqtSignal

from app.utils.config import Config
from app.utils.criteria_parser import GradingCriteria, _default_criteria
from app.workers.review_worker import ReviewWorker

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False


class ExportPanel(QWidget):
    """PDF出力パネル"""

    export_complete = pyqtSignal(str)  # 出力ファイルパス
    review_complete = pyqtSignal(str)  # 講評テキスト

    def __init__(self):
        super().__init__()
        self._results: list[dict] = []
        self._source_pdf: str | None = None
        self._criteria: GradingCriteria = _default_criteria()
        self._review_worker: ReviewWorker | None = None
        self._is_additional_mode = False
        self._setup_ui()

    def set_criteria(self, criteria: GradingCriteria):
        """採点基準を設定"""
        self._criteria = criteria

    def set_additional_mode(self, is_additional: bool, week: int = 0, count: int = 0):
        """追加答案モードを設定"""
        self._is_additional_mode = is_additional

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

        self.include_stamp = QCheckBox("評価スタンプを追加")
        self.include_stamp.setChecked(True)
        options_layout.addWidget(self.include_stamp)

        layout.addWidget(options_group)

        # スタイル設定
        style_group = QGroupBox("注釈スタイル")
        style_layout = QVBoxLayout(style_group)

        # フォント選択
        font_layout = QHBoxLayout()
        font_layout.addWidget(QLabel("フォント:"))
        self.font_combo = QComboBox()
        self._populate_fonts()
        font_layout.addWidget(self.font_combo)
        font_layout.addStretch()
        style_layout.addLayout(font_layout)

        # フォントサイズ
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("フォントサイズ:"))
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(6, 16)
        self.font_size_spin.setValue(8)
        self.font_size_spin.setSuffix("pt")
        size_layout.addWidget(self.font_size_spin)
        size_layout.addStretch()
        style_layout.addLayout(size_layout)

        # 文字色
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("文字色:"))
        self.color_combo = QComboBox()
        self.color_combo.addItems([
            "濃い青（デフォルト）",
            "赤",
            "黒",
            "緑",
            "紫",
            "オレンジ"
        ])
        color_layout.addWidget(self.color_combo)
        color_layout.addStretch()
        style_layout.addLayout(color_layout)

        layout.addWidget(style_group)

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

        # 講評生成ボタン
        self.review_btn = QPushButton("講評を生成")
        self.review_btn.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 12px 32px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        self.review_btn.clicked.connect(self._generate_review)
        button_layout.addWidget(self.review_btn)

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

        # デフォルトファイル名
        default_name = "graded.pdf"
        if self._is_additional_mode:
            default_name = "graded_additional.pdf"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "採点済みPDFを保存",
            str(Config.get_output_dir() / default_name),
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

            # 選択されたフォントを使用
            font_path = self._get_selected_font()

            # mm → pt 変換関数（ループ外で定義）
            def mm_to_pt(mm):
                return mm * 72 / 25.4

            # 【採点欄】エリアの座標（ループ外で計算）
            box_x = mm_to_pt(186.7)
            box_y = mm_to_pt(91.8)  # 86.8→91.8に変更（5mm下にずらす）
            box_w = mm_to_pt(162.3)
            box_h = mm_to_pt(115)

            # 失敗したページを追跡
            failed_pages = []
            skipped_pages = []

            for i, result in enumerate(self._results):
                page_num = result.get("page", i + 1) - 1
                if page_num < 0 or page_num >= len(doc):
                    skipped_pages.append(page_num + 1)
                    continue

                page = doc[page_num]

                # 注釈テキスト作成
                annot_text = self._format_annotation(result)

                # 注釈テキストが空の場合はスキップ
                if not annot_text.strip():
                    skipped_pages.append(page_num + 1)
                    continue

                rect = fitz.Rect(
                    box_x,
                    box_y,
                    box_x + box_w,
                    box_y + box_h
                )

                # スタイル設定を取得
                font_size = self.font_size_spin.value()
                color = self._get_selected_color()

                # 日本語フォントでテキスト挿入（自動フォントサイズ縮小対応）
                try:
                    if font_path:
                        # 最小フォントサイズ
                        min_font_size = 4
                        current_font_size = font_size
                        font_adjusted = False

                        # TextWriterを使って収まるフォントサイズを探す
                        font_obj = fitz.Font(fontfile=font_path)

                        while current_font_size >= min_font_size:
                            tw = fitz.TextWriter(page.rect)
                            # fill_textboxは収まらない場合に残りテキストを返す
                            excess = tw.fill_textbox(
                                rect,
                                annot_text,
                                font=font_obj,
                                fontsize=current_font_size,
                            )
                            if not excess:
                                # 収まった場合、実際に描画
                                tw.write_text(page, color=color)
                                if current_font_size < font_size:
                                    font_adjusted = True
                                break
                            current_font_size -= 1
                        else:
                            # 最小サイズでも収まらなかった場合、最小サイズで描画
                            tw = fitz.TextWriter(page.rect)
                            tw.fill_textbox(
                                rect,
                                annot_text,
                                font=font_obj,
                                fontsize=min_font_size,
                            )
                            tw.write_text(page, color=color)
                            failed_pages.append((page_num + 1, f"テキストが長すぎます（{min_font_size}ptでも一部切れています）"))

                        # フォントサイズ縮小の通知
                        if font_adjusted:
                            failed_pages.append((page_num + 1, f"フォントサイズを{font_size}pt→{current_font_size}ptに縮小"))
                    else:
                        # フォールバック：注釈として追加
                        page.add_freetext_annot(
                            rect,
                            annot_text,
                            fontsize=font_size,
                            text_color=color,
                        )
                except Exception as page_error:
                    failed_pages.append((page_num + 1, str(page_error)))

                # スタンプを追加
                if self.include_stamp.isChecked():
                    total_score = result.get("total_score", 0)
                    if isinstance(total_score, (int, float)):
                        self._insert_stamp(page, int(total_score))

                self.progress_bar.setValue(i + 1)

            doc.save(file_path)
            doc.close()

            # 結果メッセージを構築
            result_msg = f"出力完了: {file_path}"
            if failed_pages:
                result_msg += f"\n\n⚠️ 以下のページで注釈の挿入に問題がありました:\n"
                for page, reason in failed_pages:
                    result_msg += f"  - ページ {page}: {reason}\n"
            if skipped_pages:
                result_msg += f"\n⚠️ スキップされたページ: {skipped_pages}"

            self.preview_text.setText(result_msg)
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

    def _get_selected_color(self) -> tuple:
        """選択された色をRGBタプルで返す"""
        color_map = {
            0: (0, 0, 0.5),      # 濃い青（デフォルト）
            1: (0.8, 0, 0),      # 赤
            2: (0, 0, 0),        # 黒
            3: (0, 0.5, 0),      # 緑
            4: (0.5, 0, 0.5),    # 紫
            5: (0.9, 0.5, 0),    # オレンジ
        }
        return color_map.get(self.color_combo.currentIndex(), (0, 0, 0.5))

    def _populate_fonts(self):
        """利用可能なフォントを一覧に追加"""
        # macOSの日本語フォント候補
        self._font_list = [
            ("ヒラギノ角ゴシック W3", "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"),
            ("ヒラギノ角ゴシック W6", "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"),
            ("ヒラギノ明朝 ProN W3", "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc"),
            ("ヒラギノ丸ゴ ProN W4", "/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc"),
            ("游ゴシック Medium", "/System/Library/Fonts/YuGothic-Medium.otf"),
            ("游明朝 Medium", "/System/Library/Fonts/YuMincho-Medium.otf"),
            ("Osaka", "/System/Library/Fonts/Osaka.ttf"),
            ("Arial Unicode", "/Library/Fonts/Arial Unicode.ttf"),
        ]

        for name, path in self._font_list:
            if Path(path).exists():
                self.font_combo.addItem(name, path)

        # 何も見つからなかったらデフォルトを追加
        if self.font_combo.count() == 0:
            self.font_combo.addItem("（システムフォント）", None)

    def _get_selected_font(self) -> str | None:
        """選択されたフォントのパスを返す"""
        return self.font_combo.currentData()

    def _insert_stamp(self, page, score: int):
        """スタンプを挿入"""
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

        # 配置位置を計算
        if position == "top_right":
            x = page_rect.width - stamp_size - margin_x
            y = margin_y
        elif position == "top_left":
            x = margin_x
            y = margin_y
        elif position == "bottom_right":
            x = page_rect.width - stamp_size - margin_x
            y = page_rect.height - stamp_size - margin_y
        else:  # bottom_left
            x = margin_x
            y = page_rect.height - stamp_size - margin_y

        rect = fitz.Rect(x, y, x + stamp_size, y + stamp_size)

        # 画像を挿入
        page.insert_image(rect, filename=str(stamp_path))

    def _generate_review(self):
        """講評を生成"""
        if not self._results:
            self.preview_text.setText("採点結果がありません")
            return

        # 元答案テキストがあるかチェック
        has_original = any(r.get("original_text") for r in self._results)
        if not has_original:
            self.preview_text.setText(
                "元答案テキストがありません。\n"
                "講評を生成するには、採点を再実行して元答案を取得してください。"
            )
            return

        # プロンプトファイルを取得
        prompt_file = None
        current = Config.get_current_week()
        if current:
            week_path = Config.get_week_path(current["term"], current["week"])
            prompt_file = week_path / "prompt.txt"
            if not prompt_file.exists():
                prompt_file = None

        # UIを更新
        self.review_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(0)  # インデターミネート
        self.preview_text.setText("講評を生成中...（数分かかる場合があります）")

        # ワーカー開始（画像不要）
        self._review_worker = ReviewWorker(
            results=self._results,
            prompt_file=prompt_file
        )
        self._review_worker.progress.connect(self._on_review_progress)
        self._review_worker.finished.connect(self._on_review_finished)
        self._review_worker.error.connect(self._on_review_error)
        self._review_worker.start()

    def _on_review_progress(self, message: str):
        """講評生成進捗"""
        self.preview_text.setText(message)

    def _on_review_finished(self, plain_text: str, latex_text: str):
        """講評生成完了"""
        self.progress_bar.setVisible(False)
        self.review_btn.setEnabled(True)

        # 両方を表示
        display_text = f"=== プレーンテキスト版 ===\n\n{plain_text}"
        if latex_text:
            display_text += f"\n\n=== LaTeX版 ===\n\n{latex_text}"

        self.preview_text.setText(display_text)
        self.review_complete.emit(plain_text)

        # 保存ダイアログ
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "講評生成完了",
            "講評を保存しますか？\n（プレーンテキストとLaTeX版の両方を保存します）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._save_review_both(plain_text, latex_text)

    def _on_review_error(self, error: str):
        """講評生成エラー"""
        self.progress_bar.setVisible(False)
        self.review_btn.setEnabled(True)
        self.preview_text.setText(f"エラー: {error}")

    def _save_review(self, review_text: str):
        """講評を保存（レガシー）"""
        self._save_review_both(review_text, "")

    def _save_review_both(self, plain_text: str, latex_text: str):
        """講評を両形式で保存"""
        # 保存先ディレクトリを選択
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "講評の保存先フォルダを選択",
            str(Config.get_output_dir())
        )

        if not dir_path:
            return

        try:
            saved_files = []

            # プレーンテキスト版を保存
            plain_path = Path(dir_path) / "講評.txt"
            with open(plain_path, "w", encoding="utf-8") as f:
                f.write(plain_text)
            saved_files.append(str(plain_path))

            # LaTeX版を保存
            if latex_text:
                latex_path = Path(dir_path) / "講評.tex"
                with open(latex_path, "w", encoding="utf-8") as f:
                    f.write(latex_text)
                saved_files.append(str(latex_path))

            self.preview_text.setText(
                f"講評を保存しました:\n" +
                "\n".join(f"  - {f}" for f in saved_files) +
                f"\n\n=== プレーンテキスト版 ===\n\n{plain_text}"
            )

            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self,
                "保存完了",
                f"講評を保存しました:\n" + "\n".join(saved_files)
            )

        except Exception as e:
            self.preview_text.setText(f"保存エラー: {e}")
