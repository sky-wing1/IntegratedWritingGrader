"""設定管理"""

from __future__ import annotations
from pathlib import Path
from datetime import datetime
import json


class Config:
    """アプリケーション設定"""

    # アプリデータフォルダ
    APP_DATA_DIR = Path.home() / "Documents" / "IntegratedWritingGrader"

    # 外部リソース設定（将来的にはアプリにバンドル or 設定可能にする）
    EXISTING_PROJECT_PATH = Path("/Users/Tsubasa/Desktop/2025/02-高2英語A/英作文B新添削用紙")
    SCRIPTS_PATH = EXISTING_PROJECT_PATH / "scripts"
    WEEKS_PATH = EXISTING_PROJECT_PATH / "週別問題"

    # DyNAMiKS設定
    DYNAMIKS_APP_PATH = Path("/Applications/DyNAMiKS.app")

    # Claude設定
    CLAUDE_MODEL = "claude-sonnet-4-20250514"

    # 現在の学期・週（メモリ内）
    _current_term: str | None = None
    _current_week: int | None = None

    @classmethod
    def ensure_dirs(cls):
        """必要なディレクトリを作成"""
        cls.APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_data_dir(cls, term: str | None = None, week: int | None = None) -> Path:
        """データディレクトリを取得

        Args:
            term: 学期（例: "2024前期"）。Noneの場合は現在の学期
            week: 週番号。Noneの場合は現在の週

        Returns:
            ~/Documents/IntegratedWritingGrader/{term}/Week{week:02d}/
        """
        term = term or cls._current_term
        week = week or cls._current_week

        if not term or not week:
            raise RuntimeError("学期・週が設定されていません")

        data_dir = cls.APP_DATA_DIR / term / f"Week{week:02d}"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    @classmethod
    def get_cropped_dir(cls, term: str | None = None, week: int | None = None) -> Path:
        """クロップ画像ディレクトリを取得"""
        cropped_dir = cls.get_data_dir(term, week) / "cropped"
        cropped_dir.mkdir(parents=True, exist_ok=True)
        return cropped_dir

    @classmethod
    def get_work_dir(cls) -> Path:
        """作業ディレクトリ（クロップ画像）- 後方互換性のため"""
        return cls.get_cropped_dir()

    @classmethod
    def get_output_dir(cls) -> Path:
        """出力ディレクトリ - 後方互換性のため"""
        return cls.get_data_dir()

    @classmethod
    def get_results_path(cls, term: str | None = None, week: int | None = None) -> Path:
        """採点結果JSONのパスを取得"""
        return cls.get_data_dir(term, week) / "results.json"

    @classmethod
    def save_results(cls, results: list[dict], term: str | None = None, week: int | None = None):
        """採点結果を保存"""
        results_path = cls.get_results_path(term, week)

        # メタデータを追加
        data = {
            "term": term or cls._current_term,
            "week": week or cls._current_week,
            "saved_at": datetime.now().isoformat(),
            "results": results
        }

        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return results_path

    @classmethod
    def load_results(cls, term: str | None = None, week: int | None = None) -> list[dict] | None:
        """採点結果を読み込み"""
        results_path = cls.get_results_path(term, week)

        if not results_path.exists():
            return None

        with open(results_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 配列形式とオブジェクト形式の両方に対応
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "results" in data:
            return data["results"]

        return None

    @classmethod
    def has_saved_results(cls, term: str | None = None, week: int | None = None) -> bool:
        """保存済みの採点結果があるかチェック"""
        try:
            results_path = cls.get_results_path(term, week)
            return results_path.exists()
        except RuntimeError:
            return False

    @classmethod
    def get_current_week(cls) -> dict | None:
        """現在の週を取得"""
        if cls._current_term and cls._current_week:
            return {"term": cls._current_term, "week": cls._current_week}

        # 旧形式（current.json）からも読み込み試行
        current_json = cls.EXISTING_PROJECT_PATH / "current.json"
        if current_json.exists():
            with open(current_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                cls._current_term = data.get("term")
                cls._current_week = data.get("week")
                return data
        return None

    @classmethod
    def set_current_week(cls, term: str, week: int):
        """現在の週を設定"""
        cls._current_term = term
        cls._current_week = week

        # 旧形式（current.json）にも保存（互換性のため）
        current_json = cls.EXISTING_PROJECT_PATH / "current.json"
        data = {"term": term, "week": week}
        with open(current_json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def get_week_path(cls, term: str, week: int) -> Path:
        """週のパス（プロンプト等）を取得"""
        return cls.WEEKS_PATH / term / f"第{week:02d}週"

    @classmethod
    def list_saved_weeks(cls) -> list[dict]:
        """保存済みの週一覧を取得"""
        saved = []
        if not cls.APP_DATA_DIR.exists():
            return saved

        for term_dir in cls.APP_DATA_DIR.iterdir():
            if not term_dir.is_dir():
                continue
            term = term_dir.name

            for week_dir in term_dir.iterdir():
                if not week_dir.is_dir() or not week_dir.name.startswith("Week"):
                    continue

                try:
                    week_num = int(week_dir.name.replace("Week", ""))
                    results_path = week_dir / "results.json"

                    if results_path.exists():
                        saved.append({
                            "term": term,
                            "week": week_num,
                            "path": str(week_dir),
                            "has_results": True
                        })
                except ValueError:
                    continue

        return sorted(saved, key=lambda x: (x["term"], x["week"]))
