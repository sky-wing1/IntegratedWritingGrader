"""PDFプレビューウィジェット"""

from __future__ import annotations
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QPushButton, QSpinBox
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False


class PDFPreviewWidget(QWidget):
    """PDFプレビューウィジェット"""

    page_changed = pyqtSignal(int)  # ページ番号（1始まり）

    def __init__(self):
        super().__init__()
        self._pdf_doc = None
        self._current_page = 0
        self._zoom = 1.0
        self._setup_ui()

    def _setup_ui(self):
        """UI構築"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ツールバー
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 8, 8, 8)

        # ページナビゲーション
        self.prev_btn = QPushButton("◀")
        self.prev_btn.setFixedWidth(40)
        self.prev_btn.clicked.connect(self._prev_page)
        toolbar.addWidget(self.prev_btn)

        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.valueChanged.connect(self._goto_page)
        toolbar.addWidget(self.page_spin)

        self.page_label = QLabel("/ 0")
        toolbar.addWidget(self.page_label)

        self.next_btn = QPushButton("▶")
        self.next_btn.setFixedWidth(40)
        self.next_btn.clicked.connect(self._next_page)
        toolbar.addWidget(self.next_btn)

        toolbar.addStretch()

        # ズーム
        zoom_out_btn = QPushButton("−")
        zoom_out_btn.setFixedWidth(40)
        zoom_out_btn.clicked.connect(self._zoom_out)
        toolbar.addWidget(zoom_out_btn)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setFixedWidth(50)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toolbar.addWidget(self.zoom_label)

        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedWidth(40)
        zoom_in_btn.clicked.connect(self._zoom_in)
        toolbar.addWidget(zoom_in_btn)

        layout.addLayout(toolbar)

        # スクロールエリア
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll.setStyleSheet("background-color: #525252;")

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll.setWidget(self.image_label)

        layout.addWidget(scroll, 1)

        self._update_buttons()

    def load_pdf(self, pdf_path: str):
        """PDF読み込み"""
        if not HAS_PYMUPDF:
            self.image_label.setText("PyMuPDFがインストールされていません\npip install PyMuPDF")
            return

        try:
            self._pdf_doc = fitz.open(pdf_path)
            self._current_page = 0
            self.page_spin.setMaximum(len(self._pdf_doc))
            self.page_spin.setValue(1)
            self.page_label.setText(f"/ {len(self._pdf_doc)}")
            self._render_page()
        except Exception as e:
            self.image_label.setText(f"PDF読み込みエラー:\n{e}")

    def _render_page(self):
        """現在ページをレンダリング"""
        if not self._pdf_doc:
            return

        page = self._pdf_doc[self._current_page]
        mat = fitz.Matrix(self._zoom * 2, self._zoom * 2)  # 2x for retina
        pix = page.get_pixmap(matrix=mat)

        # QImageに変換
        img = QImage(
            pix.samples,
            pix.width,
            pix.height,
            pix.stride,
            QImage.Format.Format_RGB888 if pix.n == 3 else QImage.Format.Format_RGBA8888
        )

        pixmap = QPixmap.fromImage(img)
        self.image_label.setPixmap(pixmap)
        self._update_buttons()

    def _update_buttons(self):
        """ボタン状態更新"""
        has_pdf = self._pdf_doc is not None
        page_count = len(self._pdf_doc) if has_pdf else 0

        self.prev_btn.setEnabled(has_pdf and self._current_page > 0)
        self.next_btn.setEnabled(has_pdf and self._current_page < page_count - 1)
        self.zoom_label.setText(f"{int(self._zoom * 100)}%")

    def _prev_page(self):
        """前ページ"""
        if self._current_page > 0:
            self._current_page -= 1
            self.page_spin.setValue(self._current_page + 1)
            self._render_page()

    def _next_page(self):
        """次ページ"""
        if self._pdf_doc and self._current_page < len(self._pdf_doc) - 1:
            self._current_page += 1
            self.page_spin.setValue(self._current_page + 1)
            self._render_page()

    def _goto_page(self, page_num: int):
        """指定ページへ（スピンボックスから）"""
        if self._pdf_doc and 1 <= page_num <= len(self._pdf_doc):
            self._current_page = page_num - 1
            self._render_page()
            self.page_changed.emit(page_num)

    def set_page(self, page_num: int):
        """外部からページを設定（シグナル発火なし、無限ループ防止）"""
        if self._pdf_doc and 1 <= page_num <= len(self._pdf_doc):
            self._current_page = page_num - 1
            self.page_spin.blockSignals(True)
            self.page_spin.setValue(page_num)
            self.page_spin.blockSignals(False)
            self._render_page()

    def _zoom_in(self):
        """ズームイン"""
        if self._zoom < 3.0:
            self._zoom += 0.25
            self._render_page()

    def _zoom_out(self):
        """ズームアウト"""
        if self._zoom > 0.25:
            self._zoom -= 0.25
            self._render_page()

    @property
    def current_page(self) -> int:
        """現在のページ番号（1始まり）"""
        return self._current_page + 1

    @property
    def page_count(self) -> int:
        """総ページ数"""
        return len(self._pdf_doc) if self._pdf_doc else 0
