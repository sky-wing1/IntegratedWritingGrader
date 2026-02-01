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
