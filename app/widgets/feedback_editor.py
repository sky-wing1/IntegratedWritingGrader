"""単一ページのフィードバック編集ウィジェット"""

from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QSpinBox, QGroupBox, QScrollArea,
    QComboBox, QGridLayout
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from app.utils.criteria_parser import GradingCriteria, _default_criteria


class FeedbackEditorWidget(QWidget):
    """単一ページの採点結果編集ウィジェット"""

    data_changed = pyqtSignal(dict)  # 編集データ変更時

    def __init__(self):
        super().__init__()
        self._current_data: dict = {}
        self._criteria: GradingCriteria = _default_criteria()
        self._criterion_combos: list[QComboBox] = []

        # デバウンス用タイマー（テキスト入力中の頻繁な更新を防ぐ）
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(500)  # 500ms
        self._debounce_timer.timeout.connect(self._emit_data_changed)

        self._setup_ui()

    def _setup_ui(self):
        """UI構築"""
        # スクロール可能にする
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(16, 16, 16, 16)
        self._content_layout.setSpacing(16)

        # ページ情報ヘッダー
        self.page_header = QLabel("ページ: -")
        self.page_header.setStyleSheet("font-size: 18px; font-weight: bold; color: #37352f;")
        self._content_layout.addWidget(self.page_header)

        # 得点セクション（動的に構築）
        self._score_group = QGroupBox("得点")
        self._score_group.setStyleSheet("""
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
        self._score_group_layout = QVBoxLayout(self._score_group)
        self._build_score_section()
        self._content_layout.addWidget(self._score_group)

        # 添削答案
        corrected_group = QGroupBox("添削答案")
        corrected_layout = QVBoxLayout(corrected_group)
        self.corrected_text = QTextEdit()
        self.corrected_text.setPlaceholderText("添削後の文章...")
        self.corrected_text.setMinimumHeight(100)
        corrected_layout.addWidget(self.corrected_text)
        self._content_layout.addWidget(corrected_group)

        # 内容コメント
        content_group = QGroupBox("コメント（内容）")
        content_layout = QVBoxLayout(content_group)
        self.content_comment = QTextEdit()
        self.content_comment.setPlaceholderText("内容についてのコメント...")
        self.content_comment.setMaximumHeight(80)
        content_layout.addWidget(self.content_comment)
        self._content_layout.addWidget(content_group)

        # 表現コメント
        expression_group = QGroupBox("コメント（表現）")
        expression_layout = QVBoxLayout(expression_group)
        self.expression_comment = QTextEdit()
        self.expression_comment.setPlaceholderText("表現についてのコメント...")
        self.expression_comment.setMaximumHeight(80)
        expression_layout.addWidget(self.expression_comment)
        self._content_layout.addWidget(expression_group)

        # 書き直しポイント
        revision_group = QGroupBox("書き直しで意識すべきポイント")
        revision_layout = QVBoxLayout(revision_group)
        self.revision_points = QTextEdit()
        self.revision_points.setPlaceholderText("書き直しのポイント...")
        self.revision_points.setMaximumHeight(80)
        revision_layout.addWidget(self.revision_points)
        self._content_layout.addWidget(revision_group)

        self._content_layout.addStretch()

        # テキストフィールドの変更を自動反映（デバウンス付き）
        self.corrected_text.textChanged.connect(self._on_text_changed)
        self.content_comment.textChanged.connect(self._on_text_changed)
        self.expression_comment.textChanged.connect(self._on_text_changed)
        self.revision_points.textChanged.connect(self._on_text_changed)

        scroll.setWidget(content)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def set_criteria(self, criteria: GradingCriteria):
        """採点基準を設定（UIを再構築）"""
        self._criteria = criteria
        self._rebuild_score_section()

    def _build_score_section(self):
        """得点セクションを構築"""
        # 内容点詳細（動的）
        self._detail_layout = QGridLayout()
        self._detail_layout.setSpacing(8)
        self._criterion_combos = []

        for i, criterion in enumerate(self._criteria.criteria):
            label = QLabel(f"{criterion.number}{criterion.name}:")
            self._detail_layout.addWidget(label, i, 0)

            combo = QComboBox()
            for opt in criterion.options:
                combo.addItem(f"{opt.judgment} ({opt.score}点)", opt)
            combo.currentIndexChanged.connect(self._on_detail_changed)
            self._detail_layout.addWidget(combo, i, 1)
            self._criterion_combos.append(combo)

        self._score_group_layout.addLayout(self._detail_layout)

        # 合計行
        self._totals_layout = QHBoxLayout()

        # 内容点（自動計算）
        self._totals_layout.addWidget(QLabel("内容点:"))
        self.content_score_spin = QSpinBox()
        self.content_score_spin.setRange(0, self._criteria.content_total)
        self.content_score_spin.valueChanged.connect(self._on_score_changed)
        self._totals_layout.addWidget(self.content_score_spin)

        self._totals_layout.addSpacing(20)

        # 表現減点
        self._totals_layout.addWidget(QLabel("表現減点:"))
        self.expression_deduction_spin = QSpinBox()
        self.expression_deduction_spin.setRange(0, 20)
        self.expression_deduction_spin.valueChanged.connect(self._on_score_changed)
        self._totals_layout.addWidget(self.expression_deduction_spin)

        self._totals_layout.addSpacing(20)

        # 合計
        self._totals_layout.addWidget(QLabel("合計:"))
        self.total_label = QLabel("0点")
        self.total_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #2eaadc;")
        self._totals_layout.addWidget(self.total_label)

        self._totals_layout.addStretch()
        self._score_group_layout.addLayout(self._totals_layout)

    def _rebuild_score_section(self):
        """得点セクションを再構築"""
        # 既存のウィジェットを削除
        while self._score_group_layout.count():
            item = self._score_group_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

        self._criterion_combos = []
        self._build_score_section()

    def _clear_layout(self, layout):
        """レイアウト内のウィジェットを再帰的に削除"""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def set_data(self, result: dict):
        """採点データをセット"""
        self._current_data = result.copy()

        # ページヘッダー更新
        page_num = result.get("page", "?")
        student = result.get("student_name", "")
        header_text = f"ページ {page_num}"
        if student:
            header_text += f" - {student}"
        self.page_header.setText(header_text)

        # 各基準の判定をセット
        for i, (criterion, combo) in enumerate(zip(self._criteria.criteria, self._criterion_combos)):
            combo.blockSignals(True)

            # データからキーを探す
            key_prefix = f"criterion{i+1}_"
            judgment = result.get(f"{key_prefix}judgment", "")
            score = result.get(f"{key_prefix}score")

            # レガシーキーも試す
            if not judgment:
                if i == 0:
                    judgment = result.get("logic_judgment", "")
                    score = result.get("logic_score")
                elif i == 1:
                    judgment = result.get("support_judgment", "")
                    score = result.get("support_score")

            # 判定から選択
            found = False
            for j, opt in enumerate(criterion.options):
                if opt.judgment == judgment or opt.score == score:
                    combo.setCurrentIndex(j)
                    found = True
                    break

            if not found:
                combo.setCurrentIndex(0)

            combo.blockSignals(False)

        # 得点
        self.content_score_spin.blockSignals(True)
        self.content_score_spin.setValue(result.get("content_score") or 0)
        self.content_score_spin.blockSignals(False)

        self.expression_deduction_spin.blockSignals(True)
        self.expression_deduction_spin.setValue(result.get("expression_deduction") or 0)
        self.expression_deduction_spin.blockSignals(False)

        self._update_total()

        # テキスト
        self.corrected_text.blockSignals(True)
        self.corrected_text.setText(result.get("corrected_text") or "")
        self.corrected_text.blockSignals(False)

        self.content_comment.blockSignals(True)
        self.content_comment.setText(result.get("content_comment") or "")
        self.content_comment.blockSignals(False)

        self.expression_comment.blockSignals(True)
        self.expression_comment.setText(result.get("expression_comment") or "")
        self.expression_comment.blockSignals(False)

        self.revision_points.blockSignals(True)
        self.revision_points.setText(result.get("revision_points") or "")
        self.revision_points.blockSignals(False)

    def get_data(self) -> dict:
        """現在の編集データを取得"""
        data = {}

        # 各基準の判定と点数
        for i, (criterion, combo) in enumerate(zip(self._criteria.criteria, self._criterion_combos)):
            opt = combo.currentData()
            if opt:
                data[f"criterion{i+1}_judgment"] = opt.judgment
                data[f"criterion{i+1}_score"] = opt.score
                data[f"criterion{i+1}_name"] = criterion.name

        content = self.content_score_spin.value()
        deduction = self.expression_deduction_spin.value()

        data.update({
            "content_score": content,
            "expression_deduction": deduction,
            "total_score": max(0, content - deduction),
            "corrected_text": self.corrected_text.toPlainText(),
            "content_comment": self.content_comment.toPlainText(),
            "expression_comment": self.expression_comment.toPlainText(),
            "revision_points": self.revision_points.toPlainText(),
        })

        return data

    def clear(self):
        """データをクリア"""
        self._current_data = {}
        self.page_header.setText("ページ: -")
        for combo in self._criterion_combos:
            combo.setCurrentIndex(0)
        self.content_score_spin.setValue(0)
        self.expression_deduction_spin.setValue(0)
        self.total_label.setText("0点")
        self.corrected_text.clear()
        self.content_comment.clear()
        self.expression_comment.clear()
        self.revision_points.clear()

    def _on_detail_changed(self):
        """基準の詳細変更時"""
        # 各基準の点数を合計して内容点を自動更新
        total_content = 0
        for combo in self._criterion_combos:
            opt = combo.currentData()
            if opt:
                total_content += opt.score

        self.content_score_spin.blockSignals(True)
        self.content_score_spin.setValue(total_content)
        self.content_score_spin.blockSignals(False)

        self._update_total()
        self._emit_data_changed()  # 自動反映

    def _on_score_changed(self):
        """スコア変更時"""
        self._update_total()
        self._emit_data_changed()  # 自動反映

    def _on_text_changed(self):
        """テキスト変更時（デバウンス付き）"""
        self._debounce_timer.start()  # タイマーをリスタート

    def _update_total(self):
        """合計点更新"""
        content = self.content_score_spin.value()
        deduction = self.expression_deduction_spin.value()
        total = max(0, content - deduction)
        self.total_label.setText(f"{total}点")

        # 色分け
        max_score = self._criteria.content_total
        if total >= max_score * 0.8:
            color = "#0f7b0f"
        elif total >= max_score * 0.5:
            color = "#f59e0b"
        else:
            color = "#dc2626"
        self.total_label.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {color};")

    def _emit_data_changed(self):
        """データ変更を通知（自動反映）"""
        data = self.get_data()
        self._current_data.update(data)
        self.data_changed.emit(data)
