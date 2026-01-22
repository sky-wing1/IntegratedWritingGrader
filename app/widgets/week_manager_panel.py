"""週管理パネル"""

from __future__ import annotations
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QPushButton, QFileDialog, QComboBox,
    QSpinBox, QTextEdit, QMessageBox, QListWidget,
    QListWidgetItem, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal

from app.utils.config import Config


class WeekManagerPanel(QWidget):
    """週管理パネル"""

    week_updated = pyqtSignal()  # 週が更新された

    def __init__(self):
        super().__init__()
        self._current_term: str | None = None
        self._current_week: int | None = None
        self._setup_ui()
        self._refresh_weeks()

    def _setup_ui(self):
        """UI構築"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # タイトル
        title = QLabel("週管理")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #37352f;")
        layout.addWidget(title)

        # メインスプリッター
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左側：週一覧
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # 学期選択
        term_layout = QHBoxLayout()
        term_layout.addWidget(QLabel("学期:"))
        self.term_combo = QComboBox()
        self.term_combo.addItems(["前期", "後期"])
        self.term_combo.currentTextChanged.connect(self._on_term_changed)
        term_layout.addWidget(self.term_combo)
        term_layout.addStretch()
        left_layout.addLayout(term_layout)

        # 週リスト
        self.week_list = QListWidget()
        self.week_list.currentItemChanged.connect(self._on_week_selected)
        left_layout.addWidget(self.week_list)

        # 新規週追加
        add_layout = QHBoxLayout()
        add_layout.addWidget(QLabel("新規:"))
        self.new_week_spin = QSpinBox()
        self.new_week_spin.setRange(1, 22)
        self.new_week_spin.setPrefix("第")
        self.new_week_spin.setSuffix("週")
        add_layout.addWidget(self.new_week_spin)

        self.add_week_btn = QPushButton("追加")
        self.add_week_btn.clicked.connect(self._add_week)
        add_layout.addWidget(self.add_week_btn)
        add_layout.addStretch()
        left_layout.addLayout(add_layout)

        splitter.addWidget(left_widget)

        # 右側：詳細編集
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # 週情報
        self.week_info = QLabel("週を選択してください")
        self.week_info.setStyleSheet("font-size: 16px; font-weight: bold;")
        right_layout.addWidget(self.week_info)

        # プロンプト編集
        prompt_group = QGroupBox("採点基準（prompt.txt）")
        prompt_layout = QVBoxLayout(prompt_group)

        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("採点基準を入力...")
        self.prompt_edit.setMinimumHeight(200)
        prompt_layout.addWidget(self.prompt_edit)

        prompt_btn_layout = QHBoxLayout()
        self.save_prompt_btn = QPushButton("プロンプトを保存")
        self.save_prompt_btn.setEnabled(False)
        self.save_prompt_btn.clicked.connect(self._save_prompt)
        self.save_prompt_btn.setStyleSheet("""
            QPushButton {
                background-color: #0f7b0f;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #0d6b0d; }
            QPushButton:disabled { background-color: #ccc; }
        """)
        prompt_btn_layout.addWidget(self.save_prompt_btn)
        prompt_btn_layout.addStretch()
        prompt_layout.addLayout(prompt_btn_layout)

        right_layout.addWidget(prompt_group)

        # 問題PDF
        pdf_group = QGroupBox("問題PDF")
        pdf_layout = QVBoxLayout(pdf_group)

        self.pdf_status = QLabel("PDFが登録されていません")
        self.pdf_status.setStyleSheet("color: #9b9a97;")
        pdf_layout.addWidget(self.pdf_status)

        pdf_btn_layout = QHBoxLayout()
        self.register_pdf_btn = QPushButton("PDFを登録")
        self.register_pdf_btn.setEnabled(False)
        self.register_pdf_btn.clicked.connect(self._register_pdf)
        pdf_btn_layout.addWidget(self.register_pdf_btn)

        self.open_pdf_btn = QPushButton("PDFを開く")
        self.open_pdf_btn.setEnabled(False)
        self.open_pdf_btn.clicked.connect(self._open_pdf)
        pdf_btn_layout.addWidget(self.open_pdf_btn)

        pdf_btn_layout.addStretch()
        pdf_layout.addLayout(pdf_btn_layout)

        right_layout.addWidget(pdf_group)
        right_layout.addStretch()

        splitter.addWidget(right_widget)
        splitter.setSizes([250, 500])

        layout.addWidget(splitter, 1)

    def _refresh_weeks(self):
        """週リストを更新"""
        self.week_list.clear()
        term = self.term_combo.currentText()

        term_path = Config.WEEKS_PATH / term
        if not term_path.exists():
            return

        # 週フォルダを取得
        weeks = []
        for week_dir in term_path.iterdir():
            if week_dir.is_dir() and week_dir.name.startswith("第"):
                try:
                    # "第XX週" から番号を抽出
                    week_num = int(week_dir.name[1:3])
                    weeks.append((week_num, week_dir))
                except ValueError:
                    continue

        # ソートして追加
        for week_num, week_dir in sorted(weeks):
            # プロンプトとPDFの有無をチェック
            has_prompt = (week_dir / "prompt.txt").exists()
            has_pdf = any(week_dir.glob("*.pdf"))

            status = ""
            if has_prompt and has_pdf:
                status = " ✓"
            elif has_prompt or has_pdf:
                status = " △"

            item = QListWidgetItem(f"第{week_num:02d}週{status}")
            item.setData(Qt.ItemDataRole.UserRole, week_num)
            self.week_list.addItem(item)

        # 次の週番号を設定
        if weeks:
            max_week = max(w[0] for w in weeks)
            self.new_week_spin.setValue(min(max_week + 1, 22))
        else:
            self.new_week_spin.setValue(1)

    def _on_term_changed(self, term: str):
        """学期変更"""
        self._refresh_weeks()
        self._clear_detail()

    def _on_week_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        """週選択"""
        if not current:
            self._clear_detail()
            return

        week_num = current.data(Qt.ItemDataRole.UserRole)
        term = self.term_combo.currentText()

        self._current_term = term
        self._current_week = week_num

        self.week_info.setText(f"{term} 第{week_num:02d}週")
        self.save_prompt_btn.setEnabled(True)
        self.register_pdf_btn.setEnabled(True)

        # プロンプト読み込み
        week_path = Config.get_week_path(term, week_num)
        prompt_file = week_path / "prompt.txt"

        if prompt_file.exists():
            with open(prompt_file, "r", encoding="utf-8") as f:
                self.prompt_edit.setText(f.read())
        else:
            self.prompt_edit.clear()

        # PDF確認
        pdfs = list(week_path.glob("*.pdf"))
        if pdfs:
            self.pdf_status.setText(f"登録済み: {pdfs[0].name}")
            self.pdf_status.setStyleSheet("color: #0f7b0f; font-weight: bold;")
            self.open_pdf_btn.setEnabled(True)
        else:
            self.pdf_status.setText("PDFが登録されていません")
            self.pdf_status.setStyleSheet("color: #9b9a97;")
            self.open_pdf_btn.setEnabled(False)

    def _clear_detail(self):
        """詳細をクリア"""
        self._current_term = None
        self._current_week = None
        self.week_info.setText("週を選択してください")
        self.prompt_edit.clear()
        self.pdf_status.setText("PDFが登録されていません")
        self.pdf_status.setStyleSheet("color: #9b9a97;")
        self.save_prompt_btn.setEnabled(False)
        self.register_pdf_btn.setEnabled(False)
        self.open_pdf_btn.setEnabled(False)

    def _add_week(self):
        """新しい週を追加"""
        term = self.term_combo.currentText()
        week_num = self.new_week_spin.value()

        week_path = Config.get_week_path(term, week_num)

        if week_path.exists():
            QMessageBox.warning(
                self, "追加エラー",
                f"{term} 第{week_num:02d}週 は既に存在します"
            )
            return

        try:
            week_path.mkdir(parents=True, exist_ok=True)

            # デフォルトのプロンプトを作成
            prompt_file = week_path / "prompt.txt"
            default_prompt = f"""# {term} 第{week_num:02d}週 採点基準

## 採点項目
- ①内容: 4点
- ②構成: 4点
- ③表現: 4点

## 減点基準
- 文法ミス: -1点/箇所
- スペルミス: -0.5点/箇所
"""
            with open(prompt_file, "w", encoding="utf-8") as f:
                f.write(default_prompt)

            self._refresh_weeks()
            self.week_updated.emit()

            QMessageBox.information(
                self, "追加完了",
                f"{term} 第{week_num:02d}週 を追加しました"
            )

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"追加に失敗しました:\n{e}")

    def _save_prompt(self):
        """プロンプトを保存"""
        if not self._current_term or not self._current_week:
            return

        week_path = Config.get_week_path(self._current_term, self._current_week)
        prompt_file = week_path / "prompt.txt"

        try:
            with open(prompt_file, "w", encoding="utf-8") as f:
                f.write(self.prompt_edit.toPlainText())

            self._refresh_weeks()
            self.week_updated.emit()

            QMessageBox.information(self, "保存完了", "プロンプトを保存しました")

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"保存に失敗しました:\n{e}")

    def _register_pdf(self):
        """PDFを登録"""
        if not self._current_term or not self._current_week:
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "問題PDFを選択",
            str(Path.home() / "Desktop"),
            "PDF Files (*.pdf)"
        )

        if not file_path:
            return

        week_path = Config.get_week_path(self._current_term, self._current_week)

        try:
            import shutil
            # 既存のPDFを削除
            for old_pdf in week_path.glob("*.pdf"):
                old_pdf.unlink()

            # 新しいPDFをコピー
            src = Path(file_path)
            dst = week_path / src.name
            shutil.copy(src, dst)

            self.pdf_status.setText(f"登録済み: {src.name}")
            self.pdf_status.setStyleSheet("color: #0f7b0f; font-weight: bold;")
            self.open_pdf_btn.setEnabled(True)

            self._refresh_weeks()
            self.week_updated.emit()

            QMessageBox.information(self, "登録完了", "PDFを登録しました")

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"登録に失敗しました:\n{e}")

    def _open_pdf(self):
        """PDFを開く"""
        if not self._current_term or not self._current_week:
            return

        week_path = Config.get_week_path(self._current_term, self._current_week)
        pdfs = list(week_path.glob("*.pdf"))

        if pdfs:
            import subprocess
            subprocess.run(["open", str(pdfs[0])], check=False)
