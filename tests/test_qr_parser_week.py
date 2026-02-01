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
