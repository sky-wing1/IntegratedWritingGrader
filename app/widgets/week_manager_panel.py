"""週管理パネル"""

from __future__ import annotations
import re
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QPushButton, QComboBox,
    QSpinBox, QTextEdit, QMessageBox, QListWidget,
    QListWidgetItem, QSplitter, QLineEdit
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

        # 問題文（problem.tex）
        problem_group = QGroupBox("問題文（problem.tex）")
        problem_layout = QVBoxLayout(problem_group)

        # 週タイトル
        title_layout = QHBoxLayout()
        title_layout.addWidget(QLabel("週タイトル:"))
        self.week_title_edit = QLineEdit()
        self.week_title_edit.setPlaceholderText("後期第14週")
        title_layout.addWidget(self.week_title_edit, 1)
        problem_layout.addLayout(title_layout)

        # テーマ
        theme_layout = QHBoxLayout()
        theme_layout.addWidget(QLabel("テーマ:"))
        self.theme_edit = QLineEdit()
        self.theme_edit.setPlaceholderText("Violent Video Games")
        theme_layout.addWidget(self.theme_edit, 1)
        problem_layout.addLayout(theme_layout)

        # 問題文
        problem_layout.addWidget(QLabel("問題文:"))
        self.problem_text_edit = QTextEdit()
        self.problem_text_edit.setPlaceholderText("Do you agree or disagree with the following statement?...")
        self.problem_text_edit.setMinimumHeight(80)
        self.problem_text_edit.setMaximumHeight(120)
        problem_layout.addWidget(self.problem_text_edit)

        # 保存ボタン
        problem_btn_layout = QHBoxLayout()
        self.save_problem_btn = QPushButton("問題文を保存")
        self.save_problem_btn.setEnabled(False)
        self.save_problem_btn.clicked.connect(self._save_problem)
        self.save_problem_btn.setStyleSheet("""
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
        problem_btn_layout.addWidget(self.save_problem_btn)
        problem_btn_layout.addStretch()
        problem_layout.addLayout(problem_btn_layout)

        right_layout.addWidget(problem_group)

        # 採点基準（prompt.txt）
        prompt_group = QGroupBox("採点基準（prompt.txt）")
        prompt_layout = QVBoxLayout(prompt_group)

        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("採点基準を入力...")
        self.prompt_edit.setMinimumHeight(150)
        prompt_layout.addWidget(self.prompt_edit)

        prompt_btn_layout = QHBoxLayout()
        self.save_prompt_btn = QPushButton("採点基準を保存")
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
            # プロンプトと問題文の有無をチェック
            has_prompt = (week_dir / "prompt.txt").exists()
            has_problem = (week_dir / "problem.tex").exists()

            status = ""
            if has_prompt and has_problem:
                status = " ✓"
            elif has_prompt or has_problem:
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
        self.save_problem_btn.setEnabled(True)

        week_path = Config.get_week_path(term, week_num)

        # problem.tex読み込み
        problem_data = self._load_problem_tex(week_path)
        self.week_title_edit.setText(problem_data["週タイトル"])
        self.theme_edit.setText(problem_data["テーマ"])
        self.problem_text_edit.setText(problem_data["問題文"])

        # プロンプト読み込み
        prompt_file = week_path / "prompt.txt"
        if prompt_file.exists():
            with open(prompt_file, "r", encoding="utf-8") as f:
                self.prompt_edit.setText(f.read())
        else:
            self.prompt_edit.clear()

    def _load_problem_tex(self, week_path: Path) -> dict:
        """problem.texを読み込んで変数を抽出"""
        problem_file = week_path / "problem.tex"

        defaults = {
            "週タイトル": f"{self._current_term}第{self._current_week:02d}週" if self._current_term and self._current_week else "",
            "テーマ": "",
            "問題文": ""
        }

        if not problem_file.exists():
            return defaults

        with open(problem_file, "r", encoding="utf-8") as f:
            content = f.read()

        for key in defaults.keys():
            # \def\キー{値} パターンを抽出（複数行対応）
            pattern = rf'\\def\\{key}\{{((?:[^{{}}]|\{{[^{{}}]*\}})*)\}}'
            match = re.search(pattern, content, re.DOTALL)
            if match:
                defaults[key] = match.group(1)

        return defaults

    def _clear_detail(self):
        """詳細をクリア"""
        self._current_term = None
        self._current_week = None
        self.week_info.setText("週を選択してください")
        self.week_title_edit.clear()
        self.theme_edit.clear()
        self.problem_text_edit.clear()
        self.prompt_edit.clear()
        self.save_prompt_btn.setEnabled(False)
        self.save_problem_btn.setEnabled(False)

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

            # デフォルトのproblem.texを作成
            problem_file = week_path / "problem.tex"
            default_problem = f"""% {term}第{week_num:02d}週
\\def\\週タイトル{{{term}第{week_num:02d}週}}
\\def\\テーマ{{Writing Practice}}
\\def\\問題文{{問題文を入力してください。}}
"""
            with open(problem_file, "w", encoding="utf-8") as f:
                f.write(default_problem)

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

    def _save_problem(self):
        """problem.texを保存"""
        if not self._current_term or not self._current_week:
            return

        week_path = Config.get_week_path(self._current_term, self._current_week)
        problem_file = week_path / "problem.tex"

        # 入力値を取得
        week_title = self.week_title_edit.text() or f"{self._current_term}第{self._current_week:02d}週"
        theme = self.theme_edit.text() or "Writing Practice"
        problem_text = self.problem_text_edit.toPlainText()

        content = f"""% {week_title} - {theme}
\\def\\週タイトル{{{week_title}}}
\\def\\テーマ{{{theme}}}
\\def\\問題文{{{problem_text}}}
"""

        try:
            with open(problem_file, "w", encoding="utf-8") as f:
                f.write(content)

            self._refresh_weeks()
            self.week_updated.emit()

            QMessageBox.information(self, "保存完了", "問題文を保存しました")

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"保存に失敗しました:\n{e}")

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

            QMessageBox.information(self, "保存完了", "採点基準を保存しました")

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"保存に失敗しました:\n{e}")
