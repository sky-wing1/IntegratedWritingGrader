"""スタンプ管理パネル"""

from __future__ import annotations
from pathlib import Path
import shutil
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QPushButton, QFileDialog, QComboBox,
    QSpinBox, QListWidget, QListWidgetItem, QSplitter,
    QMessageBox, QScrollArea, QGridLayout, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QIcon

from app.utils.config import Config


class StampPanel(QWidget):
    """スタンプ管理パネル"""

    settings_changed = pyqtSignal()  # 設定変更シグナル

    def __init__(self):
        super().__init__()
        self._settings = Config.load_stamp_settings()
        Config.ensure_stamp_dirs()
        self._setup_ui()
        self._load_stamps()

    def _setup_ui(self):
        """UI構築"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # タイトル
        title = QLabel("スタンプ管理")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #37352f;")
        layout.addWidget(title)

        # 有効/無効
        self.enable_check = QCheckBox("スタンプ機能を有効にする")
        self.enable_check.setChecked(self._settings.get("enabled", True))
        self.enable_check.stateChanged.connect(self._on_enable_changed)
        layout.addWidget(self.enable_check)

        # メインスプリッター
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左側：カテゴリ一覧
        left_widget = self._create_category_list()
        splitter.addWidget(left_widget)

        # 右側：スタンプ管理
        right_widget = self._create_stamp_manager()
        splitter.addWidget(right_widget)

        splitter.setSizes([250, 500])
        layout.addWidget(splitter, 1)

        # 配置設定
        position_group = self._create_position_settings()
        layout.addWidget(position_group)

    def _create_category_list(self) -> QWidget:
        """カテゴリ一覧を作成"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel("カテゴリ（得点範囲）"))

        self.category_list = QListWidget()
        self.category_list.currentItemChanged.connect(self._on_category_selected)
        layout.addWidget(self.category_list)

        # カテゴリ編集
        edit_layout = QHBoxLayout()

        edit_layout.addWidget(QLabel("最小:"))
        self.min_score_spin = QSpinBox()
        self.min_score_spin.setRange(0, 12)
        self.min_score_spin.valueChanged.connect(self._on_score_range_changed)
        edit_layout.addWidget(self.min_score_spin)

        edit_layout.addWidget(QLabel("〜"))

        edit_layout.addWidget(QLabel("最大:"))
        self.max_score_spin = QSpinBox()
        self.max_score_spin.setRange(0, 12)
        self.max_score_spin.valueChanged.connect(self._on_score_range_changed)
        edit_layout.addWidget(self.max_score_spin)

        edit_layout.addStretch()
        layout.addLayout(edit_layout)

        return widget

    def _create_stamp_manager(self) -> QWidget:
        """スタンプ管理部分を作成"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # カテゴリ名
        self.category_name_label = QLabel("カテゴリを選択してください")
        self.category_name_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.category_name_label)

        # スタンプグリッド（スクロール可能）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                background-color: #fafafa;
            }
        """)

        self.stamps_container = QWidget()
        self.stamps_layout = QGridLayout(self.stamps_container)
        self.stamps_layout.setSpacing(16)
        self.stamps_layout.setContentsMargins(16, 16, 16, 16)
        scroll.setWidget(self.stamps_container)

        layout.addWidget(scroll, 1)

        # ボタン
        btn_layout = QHBoxLayout()

        self.add_stamp_btn = QPushButton("スタンプを追加")
        self.add_stamp_btn.setEnabled(False)
        self.add_stamp_btn.clicked.connect(self._add_stamp)
        self.add_stamp_btn.setStyleSheet("""
            QPushButton {
                background-color: #2eaadc;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #2496c4; }
            QPushButton:disabled { background-color: #ccc; }
        """)
        btn_layout.addWidget(self.add_stamp_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return widget

    def _create_position_settings(self) -> QGroupBox:
        """配置設定を作成"""
        group = QGroupBox("スタンプの配置設定")
        layout = QVBoxLayout(group)

        # 配置位置
        pos_layout = QHBoxLayout()
        pos_layout.addWidget(QLabel("配置位置:"))

        self.position_combo = QComboBox()
        self.position_combo.addItems([
            "右上",
            "左上",
            "右下",
            "左下"
        ])
        position_map = {
            "top_right": 0, "top_left": 1,
            "bottom_right": 2, "bottom_left": 3
        }
        current_pos = self._settings.get("position", "top_right")
        self.position_combo.setCurrentIndex(position_map.get(current_pos, 0))
        self.position_combo.currentIndexChanged.connect(self._on_position_changed)
        pos_layout.addWidget(self.position_combo)

        pos_layout.addStretch()
        layout.addLayout(pos_layout)

        # サイズ
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("サイズ:"))

        self.size_spin = QSpinBox()
        self.size_spin.setRange(10, 100)
        self.size_spin.setValue(self._settings.get("size", 50))
        self.size_spin.setSuffix(" mm")
        self.size_spin.valueChanged.connect(self._on_size_changed)
        size_layout.addWidget(self.size_spin)

        size_layout.addStretch()
        layout.addLayout(size_layout)

        # マージン
        margin_layout = QHBoxLayout()
        margin_layout.addWidget(QLabel("余白:"))

        margin_layout.addWidget(QLabel("X:"))
        self.margin_x_spin = QSpinBox()
        self.margin_x_spin.setRange(0, 200)
        self.margin_x_spin.setValue(self._settings.get("margin_x", 10))
        self.margin_x_spin.setSuffix(" mm")
        self.margin_x_spin.valueChanged.connect(self._on_margin_changed)
        margin_layout.addWidget(self.margin_x_spin)

        margin_layout.addWidget(QLabel("Y:"))
        self.margin_y_spin = QSpinBox()
        self.margin_y_spin.setRange(0, 200)
        self.margin_y_spin.setValue(self._settings.get("margin_y", 10))
        self.margin_y_spin.setSuffix(" mm")
        self.margin_y_spin.valueChanged.connect(self._on_margin_changed)
        margin_layout.addWidget(self.margin_y_spin)

        margin_layout.addStretch()
        layout.addLayout(margin_layout)

        return group

    def _load_stamps(self):
        """スタンプを読み込み"""
        self.category_list.clear()
        categories = self._settings.get("categories", Config.DEFAULT_STAMP_CATEGORIES)

        for category in categories:
            stamps = Config.get_stamps_for_category(category["id"])
            count = len(stamps)
            item = QListWidgetItem(
                f"{category['name']} ({category['min_score']}-{category['max_score']}点) [{count}枚]"
            )
            item.setData(Qt.ItemDataRole.UserRole, category)
            self.category_list.addItem(item)

    def _on_category_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        """カテゴリ選択"""
        if not current:
            self.category_name_label.setText("カテゴリを選択してください")
            self.add_stamp_btn.setEnabled(False)
            self._clear_stamps_display()
            return

        category = current.data(Qt.ItemDataRole.UserRole)
        self.category_name_label.setText(f"{category['name']}")
        self.add_stamp_btn.setEnabled(True)

        # 得点範囲を更新
        self.min_score_spin.blockSignals(True)
        self.max_score_spin.blockSignals(True)
        self.min_score_spin.setValue(category["min_score"])
        self.max_score_spin.setValue(category["max_score"])
        self.min_score_spin.blockSignals(False)
        self.max_score_spin.blockSignals(False)

        # スタンプを表示
        self._display_stamps(category["id"])

    def _clear_stamps_display(self):
        """スタンプ表示をクリア"""
        while self.stamps_layout.count():
            item = self.stamps_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _display_stamps(self, category_id: str):
        """スタンプを表示"""
        self._clear_stamps_display()

        stamps = Config.get_stamps_for_category(category_id)

        for i, stamp_path in enumerate(stamps):
            stamp_widget = self._create_stamp_widget(stamp_path)
            row = i // 3
            col = i % 3
            self.stamps_layout.addWidget(stamp_widget, row, col)

        # 空きスペースを埋める
        self.stamps_layout.setRowStretch(len(stamps) // 3 + 1, 1)

    def _create_stamp_widget(self, stamp_path: Path) -> QWidget:
        """スタンプウィジェットを作成"""
        widget = QWidget()
        widget.setFixedSize(120, 140)
        widget.setStyleSheet("""
            QWidget {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
            }
            QWidget:hover {
                border-color: #2eaadc;
            }
        """)

        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # 画像
        image_label = QLabel()
        image_label.setFixedSize(100, 100)
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        pixmap = QPixmap(str(stamp_path))
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                96, 96,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            image_label.setPixmap(scaled)

        layout.addWidget(image_label)

        # 削除ボタン
        delete_btn = QPushButton("削除")
        delete_btn.setFixedHeight(24)
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff6b6b;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #ee5a5a; }
        """)
        delete_btn.clicked.connect(lambda: self._delete_stamp(stamp_path))
        layout.addWidget(delete_btn)

        return widget

    def _add_stamp(self):
        """スタンプを追加"""
        current = self.category_list.currentItem()
        if not current:
            return

        category = current.data(Qt.ItemDataRole.UserRole)

        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "スタンプ画像を選択",
            str(Path.home() / "Desktop"),
            "Images (*.png *.jpg *.jpeg *.gif)"
        )

        if not file_paths:
            return

        category_path = Config.STAMPS_PATH / category["id"]
        category_path.mkdir(exist_ok=True)

        for file_path in file_paths:
            src = Path(file_path)
            dst = category_path / src.name

            # 同名ファイルがあれば連番を付ける
            counter = 1
            while dst.exists():
                dst = category_path / f"{src.stem}_{counter}{src.suffix}"
                counter += 1

            shutil.copy(src, dst)

        # 表示更新
        self._display_stamps(category["id"])
        self._load_stamps()  # カウント更新

        QMessageBox.information(
            self, "追加完了",
            f"{len(file_paths)}枚のスタンプを追加しました"
        )

    def _delete_stamp(self, stamp_path: Path):
        """スタンプを削除"""
        reply = QMessageBox.question(
            self, "削除確認",
            f"このスタンプを削除しますか？\n{stamp_path.name}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            stamp_path.unlink()

            # 表示更新
            current = self.category_list.currentItem()
            if current:
                category = current.data(Qt.ItemDataRole.UserRole)
                self._display_stamps(category["id"])
                self._load_stamps()

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"削除に失敗しました:\n{e}")

    def _on_enable_changed(self, state: int):
        """有効/無効切り替え"""
        self._settings["enabled"] = state == Qt.CheckState.Checked.value
        self._save_settings()

    def _on_score_range_changed(self):
        """得点範囲変更"""
        current = self.category_list.currentItem()
        if not current:
            return

        category = current.data(Qt.ItemDataRole.UserRole)
        category["min_score"] = self.min_score_spin.value()
        category["max_score"] = self.max_score_spin.value()

        # 設定を更新
        categories = self._settings.get("categories", Config.DEFAULT_STAMP_CATEGORIES)
        for cat in categories:
            if cat["id"] == category["id"]:
                cat["min_score"] = category["min_score"]
                cat["max_score"] = category["max_score"]
                break

        self._settings["categories"] = categories
        self._save_settings()
        self._load_stamps()

    def _on_position_changed(self, index: int):
        """配置位置変更"""
        positions = ["top_right", "top_left", "bottom_right", "bottom_left"]
        self._settings["position"] = positions[index]
        self._save_settings()

    def _on_size_changed(self, value: int):
        """サイズ変更"""
        self._settings["size"] = value
        self._save_settings()

    def _on_margin_changed(self):
        """マージン変更"""
        self._settings["margin_x"] = self.margin_x_spin.value()
        self._settings["margin_y"] = self.margin_y_spin.value()
        self._save_settings()

    def _save_settings(self):
        """設定を保存"""
        Config.save_stamp_settings(self._settings)
        self.settings_changed.emit()
