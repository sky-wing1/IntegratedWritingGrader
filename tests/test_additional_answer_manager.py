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
