"""クラス名簿管理パネル"""

from __future__ import annotations
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QGroupBox, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QComboBox, QDialog, QFormLayout,
    QDialogButtonBox, QSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal

from app.utils.roster_manager import (
    ClassRoster, Student, parse_roster_file,
    save_roster_json, load_roster_json
)
from app.utils.config import Config


class RosterPanel(QWidget):
    """クラス名簿管理パネル"""

    roster_loaded = pyqtSignal(object)  # ClassRoster

    def __init__(self):
        super().__init__()
        self._roster: ClassRoster | None = None
        self._setup_ui()

    def _setup_ui(self):
        """UI構築"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # タイトル
        title = QLabel("クラス名簿管理")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #37352f;")
        layout.addWidget(title)

        # クラス情報入力
        info_group = QGroupBox("クラス情報")
        info_layout = QHBoxLayout(info_group)

        info_layout.addWidget(QLabel("年度:"))
        self.year_input = QLineEdit()
        self.year_input.setPlaceholderText("2025")
        self.year_input.setFixedWidth(80)
        info_layout.addWidget(self.year_input)

        info_layout.addSpacing(16)

        info_layout.addWidget(QLabel("クラス名:"))
        self.class_input = QLineEdit()
        self.class_input.setPlaceholderText("高2英語A")
        self.class_input.setFixedWidth(150)
        info_layout.addWidget(self.class_input)

        info_layout.addStretch()
        layout.addWidget(info_group)

        # 保存済み名簿選択
        saved_group = QGroupBox("保存済み名簿")
        saved_layout = QHBoxLayout(saved_group)

        self.roster_combo = QComboBox()
        self.roster_combo.setMinimumWidth(200)
        self.roster_combo.currentIndexChanged.connect(self._on_roster_selected)
        saved_layout.addWidget(self.roster_combo)

        refresh_btn = QPushButton("更新")
        refresh_btn.clicked.connect(self._refresh_roster_list)
        saved_layout.addWidget(refresh_btn)

        saved_layout.addStretch()
        layout.addWidget(saved_group)

        # 名簿読み込み
        self._refresh_roster_list()

        # 名簿操作
        action_group = QGroupBox("新規名簿を追加")
        action_layout = QHBoxLayout(action_group)

        self.import_btn = QPushButton("名簿ファイルを読み込み")
        self.import_btn.setStyleSheet("""
            QPushButton {
                background-color: #2eaadc;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #2496c4; }
        """)
        self.import_btn.clicked.connect(self._import_roster)
        action_layout.addWidget(self.import_btn)

        self.save_btn = QPushButton("名簿を保存")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #0f7b0f;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #0d6b0d; }
            QPushButton:disabled { background-color: #ccc; }
        """)
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._save_roster)
        action_layout.addWidget(self.save_btn)

        action_layout.addStretch()
        layout.addWidget(action_group)

        # 名簿テーブル
        table_group = QGroupBox("生徒一覧")
        table_layout = QVBoxLayout(table_group)

        self.status_label = QLabel("名簿が読み込まれていません")
        self.status_label.setStyleSheet("color: #9b9a97;")
        table_layout.addWidget(self.status_label)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "出席番号", "姓", "名", "せい", "めい"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
            QTableWidget::item {
                padding: 4px;
            }
        """)
        table_layout.addWidget(self.table)

        # テーブル操作ボタン
        table_btn_layout = QHBoxLayout()

        self.add_student_btn = QPushButton("生徒を追加")
        self.add_student_btn.setEnabled(False)
        self.add_student_btn.clicked.connect(self._add_student)
        table_btn_layout.addWidget(self.add_student_btn)

        self.reload_roster_btn = QPushButton("名簿を再読み込み（上書き）")
        self.reload_roster_btn.setEnabled(False)
        self.reload_roster_btn.clicked.connect(self._reload_roster)
        table_btn_layout.addWidget(self.reload_roster_btn)

        table_btn_layout.addStretch()
        table_layout.addLayout(table_btn_layout)

        layout.addWidget(table_group, 1)

    def _import_roster(self):
        """名簿ファイルを読み込み"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "クラス名簿を選択",
            str(Path.home() / "Desktop"),
            "Text Files (*.txt);;All Files (*)"
        )

        if not file_path:
            return

        try:
            students = parse_roster_file(file_path)

            if not students:
                QMessageBox.warning(self, "読み込みエラー", "生徒が見つかりませんでした")
                return

            # 年度・クラス名を取得（入力されていなければデフォルト）
            year = self.year_input.text() or "2025"
            class_name = self.class_input.text() or "クラス"

            self._roster = ClassRoster(
                year=year,
                class_name=class_name,
                students=students
            )

            self._update_table()
            self.save_btn.setEnabled(True)
            self.add_student_btn.setEnabled(True)
            self.reload_roster_btn.setEnabled(True)
            self.roster_loaded.emit(self._roster)

            QMessageBox.information(
                self,
                "読み込み完了",
                f"{len(students)} 名の生徒を読み込みました"
            )

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"読み込みに失敗しました:\n{e}")

    def _save_roster(self):
        """名簿を保存"""
        if not self._roster:
            return

        # 年度・クラス名を更新
        self._roster.year = self.year_input.text() or self._roster.year
        self._roster.class_name = self.class_input.text() or self._roster.class_name

        try:
            # アプリデータフォルダに保存
            roster_dir = Config.APP_DATA_DIR / "rosters"
            roster_dir.mkdir(parents=True, exist_ok=True)

            filename = f"{self._roster.year}_{self._roster.class_name}.json"
            save_path = roster_dir / filename

            save_roster_json(self._roster, save_path)

            # ドロップダウンを更新
            self._refresh_roster_list()

            QMessageBox.information(
                self,
                "保存完了",
                f"名簿を保存しました:\n{save_path}"
            )

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"保存に失敗しました:\n{e}")

    def _refresh_roster_list(self):
        """保存済み名簿リストを更新"""
        self.roster_combo.clear()
        self.roster_combo.addItem("-- 選択してください --", None)

        roster_dir = Config.APP_DATA_DIR / "rosters"
        if not roster_dir.exists():
            return

        for json_file in sorted(roster_dir.glob("*.json")):
            # ファイル名から表示名を生成（拡張子を除く）
            display_name = json_file.stem.replace("_", " ")
            self.roster_combo.addItem(display_name, str(json_file))

    def _on_roster_selected(self, index: int):
        """ドロップダウンで名簿が選択された"""
        file_path = self.roster_combo.currentData()
        if not file_path:
            return

        try:
            self._roster = load_roster_json(file_path)
            self.year_input.setText(self._roster.year)
            self.class_input.setText(self._roster.class_name)
            self._update_table()
            self.save_btn.setEnabled(True)
            self.add_student_btn.setEnabled(True)
            self.reload_roster_btn.setEnabled(True)
            self.roster_loaded.emit(self._roster)

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"読み込みに失敗しました:\n{e}")

    def _update_table(self):
        """テーブルを更新"""
        if not self._roster:
            return

        active_students = self._roster.get_active_students()
        self.table.setRowCount(len(active_students))

        for row, student in enumerate(active_students):
            self.table.setItem(row, 0, QTableWidgetItem(f"{student.attendance_no:02d}"))
            self.table.setItem(row, 1, QTableWidgetItem(student.last_name))
            self.table.setItem(row, 2, QTableWidgetItem(student.first_name))
            self.table.setItem(row, 3, QTableWidgetItem(student.last_name_kana))
            self.table.setItem(row, 4, QTableWidgetItem(student.first_name_kana))

        self.status_label.setText(
            f"{self._roster.year} {self._roster.class_name}: "
            f"{len(active_students)} 名（在籍）"
        )

    def get_roster(self) -> ClassRoster | None:
        """現在の名簿を取得"""
        return self._roster

    def _add_student(self):
        """生徒を追加"""
        if not self._roster:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("生徒を追加")
        dialog.setMinimumWidth(300)

        layout = QFormLayout(dialog)

        # 入力フィールド
        attendance_spin = QSpinBox()
        attendance_spin.setRange(1, 99)
        # 次の出席番号を自動設定
        max_no = max((s.attendance_no for s in self._roster.students), default=0)
        attendance_spin.setValue(max_no + 1)
        layout.addRow("出席番号:", attendance_spin)

        last_name_input = QLineEdit()
        layout.addRow("姓:", last_name_input)

        first_name_input = QLineEdit()
        layout.addRow("名:", first_name_input)

        last_name_kana_input = QLineEdit()
        layout.addRow("せい:", last_name_kana_input)

        first_name_kana_input = QLineEdit()
        layout.addRow("めい:", first_name_kana_input)

        # ボタン
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 入力チェック
            if not last_name_input.text() or not first_name_input.text():
                QMessageBox.warning(self, "入力エラー", "姓と名は必須です")
                return

            # 生徒を追加
            new_student = Student(
                student_id=f"manual_{attendance_spin.value()}",
                attendance_no=attendance_spin.value(),
                last_name=last_name_input.text(),
                first_name=first_name_input.text(),
                last_name_kana=last_name_kana_input.text(),
                first_name_kana=first_name_kana_input.text(),
                status="在籍"
            )
            self._roster.students.append(new_student)
            self._roster.students.sort(key=lambda s: s.attendance_no)
            self._update_table()
            self.roster_loaded.emit(self._roster)

    def _reload_roster(self):
        """名簿を再読み込み（現在のクラス情報を維持して上書き）"""
        if not self._roster:
            return

        reply = QMessageBox.question(
            self,
            "名簿の再読み込み",
            f"現在の名簿「{self._roster.year} {self._roster.class_name}」を\n"
            "新しい名簿ファイルで上書きします。\n\n"
            "よろしいですか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "新しい名簿ファイルを選択",
            str(Path.home() / "Desktop"),
            "Text Files (*.txt);;All Files (*)"
        )

        if not file_path:
            return

        try:
            students = parse_roster_file(file_path)

            if not students:
                QMessageBox.warning(self, "読み込みエラー", "生徒が見つかりませんでした")
                return

            # 年度・クラス名は維持して生徒リストのみ更新
            self._roster.students = students
            self._update_table()
            self.roster_loaded.emit(self._roster)

            QMessageBox.information(
                self,
                "再読み込み完了",
                f"{len(students)} 名の生徒で名簿を更新しました\n"
                "（保存ボタンを押すと保存されます）"
            )

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"読み込みに失敗しました:\n{e}")
