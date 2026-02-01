# 追加答案検出機能 実装計画

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** PDF読み込み時に異なる週の答案を自動検出し、別フォルダに退避、後からアプリ内で採点・出力できるようにする

**Architecture:** QRコードパース時に週番号を比較し、不一致の答案を`additional/`フォルダに分離保存。PDF読込パネルに追加答案セクションを追加し、選択した追加答案を独立して採点・出力可能にする。

**Tech Stack:** Python 3.11+, PyQt6, PyMuPDF, 既存のqr_parser/config/pipeline_worker

---

## Task 1: AdditionalAnswerManager クラス作成

追加答案のメタデータ管理、保存、読み込みを担当するユーティリティクラス。

**Files:**
- Create: `app/utils/additional_answer_manager.py`
- Test: `tests/test_additional_answer_manager.py`

### Step 1: テストファイル作成

```python
# tests/test_additional_answer_manager.py
"""追加答案マネージャーのテスト"""

import pytest
import json
import shutil
from pathlib import Path
from datetime import datetime

from app.utils.additional_answer_manager import (
    AdditionalAnswerItem,
    AdditionalAnswerManager,
)


@pytest.fixture
def temp_data_dir(tmp_path):
    """一時データディレクトリ"""
    data_dir = tmp_path / "2025年度" / "高2英語A" / "前期" / "Week05"
    data_dir.mkdir(parents=True)
    return data_dir


@pytest.fixture
def manager(temp_data_dir):
    """マネージャーインスタンス"""
    return AdditionalAnswerManager(temp_data_dir)


class TestAdditionalAnswerItem:
    """AdditionalAnswerItem のテスト"""

    def test_to_dict(self):
        item = AdditionalAnswerItem(
            filename="page_001.png",
            student_name="山田太郎",
            attendance_no=15,
            class_name="A",
            target_week=5,
            target_term="前期",
            qr_data="2025_前期_05_A_15_山田太郎",
        )
        d = item.to_dict()
        assert d["filename"] == "page_001.png"
        assert d["student_name"] == "山田太郎"
        assert d["attendance_no"] == 15
        assert d["target_week"] == 5

    def test_from_dict(self):
        d = {
            "filename": "page_002.png",
            "student_name": "佐藤花子",
            "attendance_no": 8,
            "class_name": "B",
            "target_week": 3,
            "target_term": "前期",
            "qr_data": "2025_前期_03_B_08_佐藤花子",
        }
        item = AdditionalAnswerItem.from_dict(d)
        assert item.filename == "page_002.png"
        assert item.student_name == "佐藤花子"
        assert item.target_week == 3


class TestAdditionalAnswerManager:
    """AdditionalAnswerManager のテスト"""

    def test_get_additional_dir(self, manager, temp_data_dir):
        """additional ディレクトリのパス取得"""
        assert manager.get_additional_dir() == temp_data_dir / "additional"

    def test_add_item(self, manager):
        """アイテム追加"""
        item = AdditionalAnswerItem(
            filename="page_001.png",
            student_name="山田太郎",
            attendance_no=15,
            class_name="A",
            target_week=5,
            target_term="前期",
            qr_data="2025_前期_05_A_15_山田太郎",
        )
        manager.add_item(item)
        assert len(manager.items) == 1
        assert manager.items[0].student_name == "山田太郎"

    def test_save_and_load_metadata(self, manager, temp_data_dir):
        """メタデータの保存と読み込み"""
        item = AdditionalAnswerItem(
            filename="page_001.png",
            student_name="山田太郎",
            attendance_no=15,
            class_name="A",
            target_week=5,
            target_term="前期",
            qr_data="2025_前期_05_A_15_山田太郎",
        )
        manager.add_item(item)
        manager.detected_from_week = 6
        manager.save_metadata()

        # 新しいマネージャーで読み込み
        new_manager = AdditionalAnswerManager(temp_data_dir)
        new_manager.load_metadata()

        assert len(new_manager.items) == 1
        assert new_manager.items[0].student_name == "山田太郎"
        assert new_manager.detected_from_week == 6

    def test_save_image(self, manager, tmp_path):
        """画像保存"""
        # ダミー画像を作成
        src_image = tmp_path / "source.png"
        src_image.write_bytes(b"dummy png data")

        saved_path = manager.save_image(src_image, "page_001.png")

        assert saved_path.exists()
        assert saved_path.name == "page_001.png"
        assert saved_path.parent.name == "additional"

    def test_list_all_additional_answers(self, temp_data_dir):
        """全追加答案の一覧取得"""
        # Week05 に追加答案を作成
        week05_dir = temp_data_dir
        additional_dir = week05_dir / "additional"
        additional_dir.mkdir()

        metadata = {
            "detected_from_week": 6,
            "detected_at": datetime.now().isoformat(),
            "items": [
                {
                    "filename": "page_001.png",
                    "student_name": "山田太郎",
                    "attendance_no": 15,
                    "class_name": "A",
                    "target_week": 5,
                    "target_term": "前期",
                    "qr_data": "2025_前期_05_A_15_山田太郎",
                }
            ],
        }
        with open(additional_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False)

        # 一覧取得
        all_items = AdditionalAnswerManager.list_all_additional_answers(
            temp_data_dir.parent.parent.parent  # 2025年度ディレクトリ
        )
        assert len(all_items) == 1
        assert all_items[0]["student_name"] == "山田太郎"
```

### Step 2: テスト実行（失敗確認）

Run: `cd /Users/Tsubasa/Developer/IntegratedWritingGrader && python -m pytest tests/test_additional_answer_manager.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.utils.additional_answer_manager'"

### Step 3: AdditionalAnswerManager 実装

```python
# app/utils/additional_answer_manager.py
"""追加答案マネージャー"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import json
import shutil


@dataclass
class AdditionalAnswerItem:
    """追加答案アイテム"""

    filename: str           # 画像ファイル名
    student_name: str       # 生徒名
    attendance_no: int      # 出席番号
    class_name: str         # クラス名
    target_week: int        # 本来の週番号
    target_term: str        # 本来の学期
    qr_data: str            # QRコード生データ
    graded: bool = False    # 採点済みフラグ

    def to_dict(self) -> dict:
        """辞書形式に変換"""
        return {
            "filename": self.filename,
            "student_name": self.student_name,
            "attendance_no": self.attendance_no,
            "class_name": self.class_name,
            "target_week": self.target_week,
            "target_term": self.target_term,
            "qr_data": self.qr_data,
            "graded": self.graded,
        }

    @classmethod
    def from_dict(cls, d: dict) -> AdditionalAnswerItem:
        """辞書から生成"""
        return cls(
            filename=d["filename"],
            student_name=d["student_name"],
            attendance_no=d["attendance_no"],
            class_name=d["class_name"],
            target_week=d["target_week"],
            target_term=d["target_term"],
            qr_data=d.get("qr_data", ""),
            graded=d.get("graded", False),
        )


@dataclass
class AdditionalAnswerManager:
    """追加答案マネージャー

    特定の週フォルダ内の追加答案を管理する。
    """

    base_dir: Path  # 週フォルダ（例: Week05/）
    items: list[AdditionalAnswerItem] = field(default_factory=list)
    detected_from_week: int = 0  # 検出元の週番号
    detected_at: Optional[datetime] = None

    def __post_init__(self):
        self.base_dir = Path(self.base_dir)

    def get_additional_dir(self) -> Path:
        """追加答案ディレクトリのパスを取得"""
        return self.base_dir / "additional"

    def add_item(self, item: AdditionalAnswerItem) -> None:
        """アイテムを追加"""
        self.items.append(item)

    def save_image(self, src_path: Path, filename: str) -> Path:
        """画像を追加答案ディレクトリに保存"""
        additional_dir = self.get_additional_dir()
        additional_dir.mkdir(parents=True, exist_ok=True)

        dest_path = additional_dir / filename
        shutil.copy2(src_path, dest_path)
        return dest_path

    def save_metadata(self) -> Path:
        """メタデータを保存"""
        additional_dir = self.get_additional_dir()
        additional_dir.mkdir(parents=True, exist_ok=True)

        metadata = {
            "detected_from_week": self.detected_from_week,
            "detected_at": (self.detected_at or datetime.now()).isoformat(),
            "items": [item.to_dict() for item in self.items],
        }

        metadata_path = additional_dir / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        return metadata_path

    def load_metadata(self) -> bool:
        """メタデータを読み込み"""
        metadata_path = self.get_additional_dir() / "metadata.json"

        if not metadata_path.exists():
            return False

        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        self.detected_from_week = metadata.get("detected_from_week", 0)
        detected_at_str = metadata.get("detected_at")
        if detected_at_str:
            self.detected_at = datetime.fromisoformat(detected_at_str)

        self.items = [
            AdditionalAnswerItem.from_dict(d)
            for d in metadata.get("items", [])
        ]

        return True

    def has_items(self) -> bool:
        """追加答案があるか"""
        return len(self.items) > 0

    def get_ungraded_items(self) -> list[AdditionalAnswerItem]:
        """未採点のアイテムを取得"""
        return [item for item in self.items if not item.graded]

    @staticmethod
    def list_all_additional_answers(year_dir: Path) -> list[dict]:
        """年度ディレクトリ内の全追加答案を一覧取得

        Args:
            year_dir: 年度ディレクトリ（例: ~/Documents/.../2025年度/）

        Returns:
            追加答案情報のリスト（週情報付き）
        """
        all_items = []

        if not year_dir.exists():
            return all_items

        # クラス/学期/週 の階層を探索
        for class_dir in year_dir.iterdir():
            if not class_dir.is_dir():
                continue

            for term_dir in class_dir.iterdir():
                if not term_dir.is_dir():
                    continue
                if term_dir.name not in ("前期", "後期"):
                    continue

                for week_dir in term_dir.iterdir():
                    if not week_dir.is_dir():
                        continue
                    if not week_dir.name.startswith("Week"):
                        continue

                    additional_dir = week_dir / "additional"
                    metadata_path = additional_dir / "metadata.json"

                    if not metadata_path.exists():
                        continue

                    try:
                        with open(metadata_path, "r", encoding="utf-8") as f:
                            metadata = json.load(f)

                        week_num = int(week_dir.name.replace("Week", ""))

                        for item_data in metadata.get("items", []):
                            item_data["week_dir"] = str(week_dir)
                            item_data["current_week"] = week_num
                            item_data["term"] = term_dir.name
                            item_data["class_name_dir"] = class_dir.name
                            all_items.append(item_data)
                    except (json.JSONDecodeError, ValueError):
                        continue

        return all_items
```

### Step 4: テスト実行（成功確認）

Run: `cd /Users/Tsubasa/Developer/IntegratedWritingGrader && python -m pytest tests/test_additional_answer_manager.py -v`
Expected: PASS

### Step 5: コミット

```bash
git add app/utils/additional_answer_manager.py tests/test_additional_answer_manager.py
git commit -m "feat: add AdditionalAnswerManager for tracking late submissions"
```

---

## Task 2: qr_parser に週番号抽出ヘルパー追加

QRコードから週番号を抽出し、現在の週と比較するヘルパー関数を追加。

**Files:**
- Modify: `app/utils/qr_parser.py:45-106`
- Test: `tests/test_qr_parser_week.py`

### Step 1: テストファイル作成

```python
# tests/test_qr_parser_week.py
"""QRパーサー週番号抽出のテスト"""

import pytest
from app.utils.qr_parser import (
    parse_qr_value,
    extract_week_info,
    is_different_week,
)


class TestExtractWeekInfo:
    """extract_week_info のテスト"""

    def test_new_format(self):
        """新フォーマット: 年度_学期_週番号_クラス_出席番号_姓名"""
        info = extract_week_info("2025_後期_13_A_01_山田太郎")
        assert info["year"] == 2025
        assert info["term"] == "後期"
        assert info["week"] == 13
        assert info["class_name"] == "A"

    def test_old_format(self):
        """旧フォーマット: 学期_週番号_クラス_出席番号_姓名"""
        info = extract_week_info("後期_13_A_01_山田太郎")
        assert info["term"] == "後期"
        assert info["week"] == 13
        assert info["class_name"] == "A"
        assert "year" in info  # 年度は推定される

    def test_invalid_qr(self):
        """無効なQRコード"""
        info = extract_week_info("invalid")
        assert info is None

    def test_empty_qr(self):
        """空のQRコード"""
        info = extract_week_info("")
        assert info is None


class TestIsDifferentWeek:
    """is_different_week のテスト"""

    def test_same_week(self):
        """同じ週"""
        assert is_different_week(
            "2025_後期_13_A_01_山田太郎",
            current_week=13,
            current_term="後期"
        ) is False

    def test_different_week(self):
        """異なる週"""
        assert is_different_week(
            "2025_後期_12_A_01_山田太郎",
            current_week=13,
            current_term="後期"
        ) is True

    def test_different_term(self):
        """異なる学期"""
        assert is_different_week(
            "2025_前期_13_A_01_山田太郎",
            current_week=13,
            current_term="後期"
        ) is True

    def test_invalid_qr_returns_false(self):
        """無効なQRコードはFalse（通常処理に含める）"""
        assert is_different_week(
            "invalid",
            current_week=13,
            current_term="後期"
        ) is False
```

### Step 2: テスト実行（失敗確認）

Run: `cd /Users/Tsubasa/Developer/IntegratedWritingGrader && python -m pytest tests/test_qr_parser_week.py -v`
Expected: FAIL with "cannot import name 'extract_week_info'"

### Step 3: qr_parser.py に関数追加

`app/utils/qr_parser.py` の末尾（289行目以降）に追加:

```python
def extract_week_info(qr_value: str) -> dict | None:
    """QRコード値から週情報を抽出

    Args:
        qr_value: QRコードの値

    Returns:
        {"year": int, "term": str, "week": int, "class_name": str} or None
    """
    student = parse_qr_value(qr_value)
    if not student:
        return None

    return {
        "year": student.year,
        "term": student.term,
        "week": student.week,
        "class_name": student.class_name,
    }


def is_different_week(
    qr_value: str,
    current_week: int,
    current_term: str
) -> bool:
    """QRコードの週が現在の週と異なるかチェック

    Args:
        qr_value: QRコードの値
        current_week: 現在処理中の週番号
        current_term: 現在処理中の学期

    Returns:
        True: 異なる週の答案（追加答案）
        False: 同じ週の答案、またはQRコードが無効
    """
    info = extract_week_info(qr_value)
    if not info:
        # QRコードが読めない場合は通常処理に含める
        return False

    return info["week"] != current_week or info["term"] != current_term
```

### Step 4: テスト実行（成功確認）

Run: `cd /Users/Tsubasa/Developer/IntegratedWritingGrader && python -m pytest tests/test_qr_parser_week.py -v`
Expected: PASS

### Step 5: コミット

```bash
git add app/utils/qr_parser.py tests/test_qr_parser_week.py
git commit -m "feat: add week extraction helpers to qr_parser"
```

---

## Task 3: PipelineWorker に追加答案検出ロジック追加

PDF処理時に追加答案を検出し、別フォルダに保存するロジックを追加。

**Files:**
- Modify: `app/workers/pipeline_worker.py:15-224`

### Step 1: PipelineWorker にシグナルとメンバー追加

`app/workers/pipeline_worker.py` の `PipelineWorker` クラスを修正:

```python
# 既存のimportに追加
from app.utils.qr_parser import StudentInfo, parse_qr_value, find_scancrop_output, parse_scancrop_qrcode_txt, is_different_week
from app.utils.additional_answer_manager import AdditionalAnswerManager, AdditionalAnswerItem


class PipelineWorker(QThread):
    """DyNAMiKS処理 + PDFクロップを行うワーカー"""

    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(str)  # 処理済みPDFパス
    students_found = pyqtSignal(list)  # 生徒情報リスト
    additional_answers_found = pyqtSignal(int)  # 追加答案件数 ★新規
    error = pyqtSignal(str)

    def __init__(self, input_pdf: str, parent=None):
        super().__init__(parent)
        self.input_pdf = input_pdf
        self._is_cancelled = False
        self._students: List[StudentInfo] = []
        self._additional_items: List[AdditionalAnswerItem] = []  # ★新規
```

### Step 2: _crop_answers メソッドを修正して追加答案を分離

`_crop_answers` メソッド（128行目付近）を修正:

```python
def _crop_answers(self, pdf_path: str) -> Path:
    """答案部分をクロップ（PyMuPDFで直接処理）

    追加答案（異なる週の答案）は別フォルダに分離する。
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError("PyMuPDFがインストールされていません")

    # 出力先ディレクトリ
    try:
        cropped_dir = Config.get_cropped_dir()
    except RuntimeError:
        cropped_dir = self._temp_dir / "cropped"
    cropped_dir.mkdir(parents=True, exist_ok=True)

    # 現在の週情報を取得
    current = Config.get_current_week()
    current_week = current.get("week") if current else None
    current_term = current.get("term") if current else None

    # PDFを開く
    doc = fitz.open(pdf_path)

    # クロップ領域（答案部分）- mm単位をポイントに変換
    def mm_to_pt(mm):
        return mm * 72 / 25.4

    crop_x = mm_to_pt(5)
    crop_y = mm_to_pt(112)
    crop_w = mm_to_pt(175)
    crop_h = mm_to_pt(140)

    # 追加答案マネージャーのキャッシュ（週ごとに管理）
    additional_managers: dict[tuple, AdditionalAnswerManager] = {}

    for page_num in range(len(doc)):
        page = doc[page_num]

        # このページの生徒情報を取得
        student_info = None
        if page_num < len(self._students):
            student_info = self._students[page_num]

        # 追加答案かどうかチェック
        is_additional = False
        if student_info and current_week and current_term:
            if student_info.week != current_week or student_info.term != current_term:
                is_additional = True

        # クロップ領域
        crop_rect = fitz.Rect(crop_x, crop_y, crop_x + crop_w, crop_y + crop_h)

        # 画像として出力
        mat = fitz.Matrix(2, 2)  # 2倍のスケール
        pix = page.get_pixmap(matrix=mat, clip=crop_rect)

        filename = f"page_{page_num + 1:03d}.png"

        if is_additional and student_info:
            # 追加答案として保存
            target_key = (student_info.term, student_info.week)

            if target_key not in additional_managers:
                # 該当週のディレクトリを取得/作成
                target_dir = Config.get_data_dir(
                    year=student_info.year,
                    term=student_info.term,
                    week=student_info.week,
                    class_name=student_info.class_name
                )
                manager = AdditionalAnswerManager(target_dir)
                manager.detected_from_week = current_week
                additional_managers[target_key] = manager

            manager = additional_managers[target_key]

            # 一時ファイルに保存してからコピー
            temp_path = self._temp_dir / filename
            pix.save(str(temp_path))
            manager.save_image(temp_path, filename)

            # アイテムを追加
            item = AdditionalAnswerItem(
                filename=filename,
                student_name=student_info.name,
                attendance_no=student_info.attendance_no,
                class_name=student_info.class_name,
                target_week=student_info.week,
                target_term=student_info.term,
                qr_data=f"{student_info.year}_{student_info.term}_{student_info.week}_{student_info.class_name}_{student_info.attendance_no}_{student_info.name}",
            )
            manager.add_item(item)
            self._additional_items.append(item)
        else:
            # 通常の答案として保存
            output_path = cropped_dir / filename
            pix.save(str(output_path))

    doc.close()

    # 追加答案のメタデータを保存
    for manager in additional_managers.values():
        manager.save_metadata()

    # 追加答案が見つかった場合はシグナル発火
    if self._additional_items:
        self.additional_answers_found.emit(len(self._additional_items))

    return cropped_dir
```

### Step 3: additional_items プロパティ追加

クラスの末尾に追加:

```python
@property
def additional_items(self) -> List[AdditionalAnswerItem]:
    """検出された追加答案を取得"""
    return self._additional_items
```

### Step 4: 動作確認

手動テスト: アプリを起動し、異なる週番号のQRコードを含むPDFを読み込んで、追加答案が分離されることを確認。

### Step 5: コミット

```bash
git add app/workers/pipeline_worker.py
git commit -m "feat: detect and separate additional answers in pipeline"
```

---

## Task 4: PDF読込パネルに追加答案セクション追加

追加答案の一覧表示と採点ボタンを追加。

**Files:**
- Modify: `app/widgets/pdf_loader_panel.py:100-377`

### Step 1: インポートとシグナル追加

`app/widgets/pdf_loader_panel.py` の先頭部分を修正:

```python
"""PDF読み込みパネル（QRコードから自動判定）"""

from __future__ import annotations
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QPushButton, QFileDialog, QTextEdit,
    QProgressBar, QMessageBox, QFrame, QGridLayout,
    QListWidget, QListWidgetItem, QCheckBox  # ★追加
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

from app.utils.config import Config
from app.workers.pipeline_worker import PipelineWorker
from app.utils.additional_answer_manager import AdditionalAnswerManager, AdditionalAnswerItem  # ★追加
```

### Step 2: PdfLoaderPanel クラスにメンバーとシグナル追加

```python
class PdfLoaderPanel(QWidget):
    """PDF読み込みパネル"""

    pdf_loaded = pyqtSignal(str, dict)  # (PDFパス, 検出された情報)
    additional_grading_requested = pyqtSignal(list)  # 追加答案採点リクエスト ★新規

    def __init__(self):
        super().__init__()
        self._current_pdf_path: str | None = None
        self._pipeline_worker: PipelineWorker | None = None
        self._detected_info: dict = {}
        self._additional_items: list[AdditionalAnswerItem] = []  # ★新規
        self._setup_ui()
```

### Step 3: _setup_ui に追加答案セクション追加

`_setup_ui` メソッドの `self.start_btn` の後（226行目付近）に追加:

```python
        # 採点開始ボタン（既存）
        self.start_btn = QPushButton("採点画面へ進む →")
        # ... 既存のコード ...
        layout.addWidget(self.start_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # ★ 追加答案セクション（新規）
        self.additional_group = QGroupBox("追加答案")
        self.additional_group.setVisible(False)
        additional_layout = QVBoxLayout(self.additional_group)

        self.additional_header = QLabel("検出された追加答案はありません")
        self.additional_header.setStyleSheet("color: #6b6b6b; font-size: 13px;")
        additional_layout.addWidget(self.additional_header)

        self.additional_list = QListWidget()
        self.additional_list.setMaximumHeight(150)
        self.additional_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.additional_list.setStyleSheet("""
            QListWidget {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:selected {
                background-color: #fff3cd;
                color: #37352f;
            }
        """)
        additional_layout.addWidget(self.additional_list)

        # 追加答案のボタン
        additional_btn_layout = QHBoxLayout()

        self.select_all_btn = QPushButton("すべて選択")
        self.select_all_btn.clicked.connect(self._select_all_additional)
        additional_btn_layout.addWidget(self.select_all_btn)

        self.grade_additional_btn = QPushButton("選択した答案を採点")
        self.grade_additional_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0ad4e;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #ec971f; }
            QPushButton:disabled { background-color: #ccc; }
        """)
        self.grade_additional_btn.clicked.connect(self._on_grade_additional)
        additional_btn_layout.addWidget(self.grade_additional_btn)

        additional_btn_layout.addStretch()
        additional_layout.addLayout(additional_btn_layout)

        layout.addWidget(self.additional_group)

        layout.addStretch()
```

### Step 4: 追加答案関連のメソッド追加

クラスの末尾に追加:

```python
    def _on_additional_found(self, count: int):
        """追加答案検出時"""
        if self._pipeline_worker:
            self._additional_items = self._pipeline_worker.additional_items
        self._update_additional_list()

    def _update_additional_list(self):
        """追加答案リストを更新"""
        self.additional_list.clear()

        if not self._additional_items:
            self.additional_group.setVisible(False)
            return

        self.additional_group.setVisible(True)
        self.additional_header.setText(
            f"異なる週の答案が {len(self._additional_items)} 件検出されました"
        )

        for item in self._additional_items:
            text = f"第{item.target_week:02d}週 - {item.student_name} (出席番号{item.attendance_no})"
            list_item = QListWidgetItem(text)
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self.additional_list.addItem(list_item)

    def _select_all_additional(self):
        """すべての追加答案を選択"""
        for i in range(self.additional_list.count()):
            self.additional_list.item(i).setSelected(True)

    def _on_grade_additional(self):
        """選択した追加答案を採点"""
        selected_items = []
        for i in range(self.additional_list.count()):
            item = self.additional_list.item(i)
            if item.isSelected():
                additional_item = item.data(Qt.ItemDataRole.UserRole)
                selected_items.append(additional_item)

        if not selected_items:
            QMessageBox.information(self, "追加答案", "採点する答案を選択してください")
            return

        self.additional_grading_requested.emit(selected_items)

    def load_additional_answers(self):
        """保存済みの追加答案を読み込み"""
        current = Config.get_current_week()
        if not current:
            return

        try:
            year_dir = Config.APP_DATA_DIR / f"{current.get('year')}年度"
            all_items = AdditionalAnswerManager.list_all_additional_answers(year_dir)

            # AdditionalAnswerItem に変換
            self._additional_items = []
            for item_data in all_items:
                if not item_data.get("graded", False):
                    item = AdditionalAnswerItem(
                        filename=item_data["filename"],
                        student_name=item_data["student_name"],
                        attendance_no=item_data["attendance_no"],
                        class_name=item_data.get("class_name", ""),
                        target_week=item_data["target_week"],
                        target_term=item_data["target_term"],
                        qr_data=item_data.get("qr_data", ""),
                        graded=item_data.get("graded", False),
                    )
                    self._additional_items.append(item)

            self._update_additional_list()
        except Exception:
            pass
```

### Step 5: _start_processing でシグナル接続

`_start_processing` メソッド（235行目付近）を修正:

```python
    def _start_processing(self):
        """PDF処理開始"""
        if not self._current_pdf_path:
            return

        # UI更新
        self.drop_area.setVisible(False)
        self.info_group.setVisible(False)
        self.prompt_group.setVisible(False)
        self.start_btn.setVisible(False)
        self.additional_group.setVisible(False)  # ★追加
        self.progress_group.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("処理開始...")

        # 追加答案リストをクリア
        self._additional_items = []  # ★追加

        # ワーカー開始
        self._pipeline_worker = PipelineWorker(self._current_pdf_path)
        self._pipeline_worker.progress.connect(self._on_progress)
        self._pipeline_worker.students_found.connect(self._on_students_found)
        self._pipeline_worker.additional_answers_found.connect(self._on_additional_found)  # ★追加
        self._pipeline_worker.finished.connect(self._on_finished)
        self._pipeline_worker.error.connect(self._on_error)
        self._pipeline_worker.start()
```

### Step 6: reset メソッドを修正

```python
    def reset(self):
        """リセット"""
        self._current_pdf_path = None
        self._detected_info = {}
        self._additional_items = []  # ★追加

        self.drop_area.setVisible(True)
        self.info_group.setVisible(False)
        self.prompt_group.setVisible(False)
        self.progress_group.setVisible(False)
        self.start_btn.setVisible(False)
        self.additional_group.setVisible(False)  # ★追加

        for label in self.info_labels.values():
            label.setText("-")

        self.additional_list.clear()  # ★追加
```

### Step 7: 動作確認

手動テスト: アプリを起動し、追加答案セクションが表示されることを確認。

### Step 8: コミット

```bash
git add app/widgets/pdf_loader_panel.py
git commit -m "feat: add additional answers section to PDF loader panel"
```

---

## Task 5: MainWindow に追加答案モードの配線

追加答案採点リクエストを受け取り、採点・編集パネルに渡す配線を追加。

**Files:**
- Modify: `app/main_window.py:145-175, 240-275`

### Step 1: インポート追加

```python
from app.utils.additional_answer_manager import AdditionalAnswerItem
```

### Step 2: _add_pages でシグナル接続追加

`_add_pages` メソッド（146行目付近）を修正:

```python
    def _add_pages(self):
        """ページ追加"""
        # PDF読み込みページ（QRコードから自動判定）
        self.pdf_loader = PdfLoaderPanel()
        self.pdf_loader.pdf_loaded.connect(self._on_pdf_loaded_with_info)
        self.pdf_loader.additional_grading_requested.connect(self._on_additional_grading_requested)  # ★追加
        self.content_stack.addWidget(self.pdf_loader)
        # ... 残りは既存のまま
```

### Step 3: 追加答案採点ハンドラ追加

クラスの末尾（561行目付近）に追加:

```python
    def _on_additional_grading_requested(self, items: list):
        """追加答案の採点リクエスト"""
        if not items:
            return

        # 最初のアイテムの週情報を使用
        first_item = items[0]

        # 該当週のディレクトリを取得
        current = Config.get_current_week()
        if not current:
            QMessageBox.warning(self, "追加答案", "週が選択されていません")
            return

        year = current.get("year")
        target_dir = Config.get_data_dir(
            year=year,
            term=first_item.target_term,
            week=first_item.target_week,
            class_name=first_item.class_name
        )

        additional_dir = target_dir / "additional"

        if not additional_dir.exists():
            QMessageBox.warning(
                self, "追加答案",
                f"追加答案フォルダが見つかりません:\n{additional_dir}"
            )
            return

        # 週を一時的に切り替え
        Config.set_current_week(
            year=year,
            term=first_item.target_term,
            week=first_item.target_week,
            class_name=first_item.class_name
        )

        # 採点基準を読み込み
        self._load_criteria()

        # 追加答案モードで採点・編集パネルに遷移
        self.integrated_panel.set_criteria(self._current_criteria)
        self.integrated_panel.load_additional_answers(additional_dir, items)

        # ステータスバー更新
        self.statusbar.showMessage(
            f"追加答案モード: 第{first_item.target_week}週 ({len(items)}件)"
        )

        # 採点・編集ページに移動
        self.nav_list.setCurrentRow(1)
```

### Step 4: コミット

```bash
git add app/main_window.py
git commit -m "feat: wire additional answer grading to main window"
```

---

## Task 6: IntegratedGradingPanel に追加答案モード追加

追加答案を読み込んで採点できるようにする。

**Files:**
- Modify: `app/widgets/integrated_grading_panel.py:16-237`

### Step 1: インポート追加

```python
from app.utils.additional_answer_manager import AdditionalAnswerItem
```

### Step 2: メンバー変数追加

`__init__` を修正:

```python
    def __init__(self):
        super().__init__()
        self._results: list[dict] = []
        self._current_index = -1
        self._is_additional_mode = False  # ★追加
        self._additional_items: list[AdditionalAnswerItem] = []  # ★追加
        self._additional_dir: Path | None = None  # ★追加
        self._setup_ui()
```

### Step 3: 追加答案モード用のヘッダー追加

`_setup_ui` の先頭部分（layout定義後）を修正:

```python
    def _setup_ui(self):
        """UI構築"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ★追加: 追加答案モードヘッダー
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

        # 上部: 進捗パネル（既存）
        self.progress_panel = ProgressPanel()
        layout.addWidget(self.progress_panel)
        # ... 残りは既存のまま
```

### Step 4: 追加答案読み込みメソッド追加

クラスの末尾に追加:

```python
    def load_additional_answers(self, additional_dir: Path, items: list):
        """追加答案を読み込み"""
        from pathlib import Path

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

        # PDFプレビューを画像モードに切り替え
        if self._results and self._results[0].get("image_path"):
            self.pdf_preview.load_image(self._results[0]["image_path"])

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
```

### Step 5: _select_page を修正して画像表示に対応

`_select_page` メソッドを修正:

```python
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
```

### Step 6: コミット

```bash
git add app/widgets/integrated_grading_panel.py
git commit -m "feat: add additional answer mode to grading panel"
```

---

## Task 7: PDFPreviewWidget に画像表示機能追加

追加答案の画像を表示できるようにする。

**Files:**
- Modify: `app/widgets/pdf_preview.py`

### Step 1: load_image メソッド追加

`app/widgets/pdf_preview.py` のクラスに追加:

```python
    def load_image(self, image_path: str):
        """画像を読み込んで表示"""
        from pathlib import Path
        from PyQt6.QtGui import QPixmap

        path = Path(image_path)
        if not path.exists():
            return

        # PDFモードを解除
        self._doc = None
        self._current_page = 1
        self._total_pages = 1

        # 画像を読み込み
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            # スケーリングして表示
            scaled = pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(scaled)

        # ページ情報更新
        self.page_label.setText("画像モード")
```

### Step 2: コミット

```bash
git add app/widgets/pdf_preview.py
git commit -m "feat: add image display support to PDF preview"
```

---

## Task 8: Config に追加答案パス設定追加

追加答案ディレクトリのパスを取得するヘルパーを追加。

**Files:**
- Modify: `app/utils/config.py:117-127`

### Step 1: get_additional_dir メソッド追加

`get_cropped_dir` の後（120行目付近）に追加:

```python
    @classmethod
    def get_additional_dir(
        cls,
        year: int | None = None,
        term: str | None = None,
        week: int | None = None,
        class_name: str | None = None
    ) -> Path:
        """追加答案ディレクトリを取得"""
        additional_dir = cls.get_data_dir(year, term, week, class_name) / "additional"
        additional_dir.mkdir(parents=True, exist_ok=True)
        return additional_dir

    @classmethod
    def get_additional_results_path(
        cls,
        year: int | None = None,
        term: str | None = None,
        week: int | None = None,
        class_name: str | None = None
    ) -> Path:
        """追加答案の採点結果JSONのパスを取得"""
        return cls.get_additional_dir(year, term, week, class_name) / "additional_results.json"

    @classmethod
    def save_additional_results(
        cls,
        results: list[dict],
        year: int | None = None,
        term: str | None = None,
        week: int | None = None,
        class_name: str | None = None
    ):
        """追加答案の採点結果を保存"""
        results_path = cls.get_additional_results_path(year, term, week, class_name)

        data = {
            "year": year or cls._current_year,
            "term": term or cls._current_term,
            "week": week or cls._current_week,
            "class_name": class_name or cls._current_class,
            "saved_at": datetime.now().isoformat(),
            "is_additional": True,
            "results": results
        }

        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return results_path

    @classmethod
    def load_additional_results(
        cls,
        year: int | None = None,
        term: str | None = None,
        week: int | None = None,
        class_name: str | None = None
    ) -> list[dict] | None:
        """追加答案の採点結果を読み込み"""
        results_path = cls.get_additional_results_path(year, term, week, class_name)

        if not results_path.exists():
            return None

        with open(results_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "results" in data:
            return data["results"]

        return None
```

### Step 2: コミット

```bash
git add app/utils/config.py
git commit -m "feat: add additional answer path helpers to config"
```

---

## Task 9: ExportPanel に追加答案モード対応追加

追加答案の出力に対応する。

**Files:**
- Modify: `app/widgets/export_panel.py:189-220`

### Step 1: set_additional_mode メソッド追加

クラスに追加:

```python
    def set_additional_mode(self, is_additional: bool, week: int = 0, count: int = 0):
        """追加答案モードを設定"""
        self._is_additional_mode = is_additional

        if is_additional:
            # タイトルを変更
            self.findChild(QLabel).setText(f"PDF出力 - 追加答案モード (第{week:02d}週 {count}件)")
        else:
            self.findChild(QLabel).setText("PDF出力")
```

### Step 2: _export_pdf の出力ファイル名を修正

`_export_pdf` メソッドのファイル名生成部分を修正:

```python
    def _export_pdf(self):
        """PDF出力"""
        if not self._source_pdf or not self._results:
            return

        # デフォルトファイル名
        default_name = "graded.pdf"
        if hasattr(self, '_is_additional_mode') and self._is_additional_mode:
            default_name = "graded_additional.pdf"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "採点済みPDFを保存",
            str(Config.get_output_dir() / default_name),
            "PDF Files (*.pdf)"
        )
        # ... 残りは既存のまま
```

### Step 3: コミット

```bash
git add app/widgets/export_panel.py
git commit -m "feat: add additional answer mode support to export panel"
```

---

## Task 10: 完了通知のUI追加

処理完了時に追加答案の件数を通知するダイアログを追加。

**Files:**
- Modify: `app/widgets/pdf_loader_panel.py:276-320`

### Step 1: _on_finished を修正

`_on_finished` メソッドの末尾に追加:

```python
    def _on_finished(self, pdf_path: str):
        """処理完了"""
        # ... 既存のコード ...

        # ★追加: 追加答案の通知
        if self._additional_items:
            count = len(self._additional_items)
            QMessageBox.information(
                self,
                "追加答案を検出",
                f"{count} 件の追加答案（異なる週の答案）を検出しました。\n\n"
                "「追加答案」セクションから採点できます。"
            )
```

### Step 2: コミット

```bash
git add app/widgets/pdf_loader_panel.py
git commit -m "feat: add notification for detected additional answers"
```

---

## Task 11: 全体テストと動作確認

### Step 1: アプリ起動テスト

```bash
cd /Users/Tsubasa/Developer/IntegratedWritingGrader
python -m app.main
```

### Step 2: 手動テスト項目

1. [ ] PDF読み込み時に異なる週の答案を検出できる
2. [ ] 検出した追加答案が該当週の `additional/` フォルダに保存される
3. [ ] 処理完了後に追加答案の件数が通知される
4. [ ] PDF読込パネルで追加答案一覧が表示される
5. [ ] 追加答案を選択して採点・出力ができる
6. [ ] 採点結果が `additional_results.json` に保存される
7. [ ] 既存の週データに影響しない

### Step 3: 最終コミット

```bash
git add -A
git commit -m "feat: complete additional answer detection feature"
```

---

**Plan complete and saved to `docs/plans/2026-02-01-additional-answer-detection-plan.md`. Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
