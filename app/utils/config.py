"""設定管理"""

from __future__ import annotations
from pathlib import Path
from datetime import datetime
import json


class Config:
    """アプリケーション設定"""

    # アプリデータフォルダ
    APP_DATA_DIR = Path.home() / "Documents" / "IntegratedWritingGrader"

    # アプリ内リソース（バンドル用）
    _APP_ROOT = Path(__file__).parent.parent  # app/ ディレクトリ
    TEMPLATES_PATH = _APP_ROOT / "resources" / "templates"

    # 週別問題（アプリデータフォルダに一元化）
    WEEKS_PATH = APP_DATA_DIR / "weeks"

    # スタンプフォルダ
    STAMPS_PATH = APP_DATA_DIR / "stamps"

    # デフォルトのスタンプカテゴリ（12点満点ベース）
    DEFAULT_STAMP_CATEGORIES = [
        {"id": "excellent", "name": "最高！", "min_score": 11, "max_score": 12},
        {"id": "good", "name": "いいね！", "min_score": 9, "max_score": 10},
        {"id": "average", "name": "まあまあ", "min_score": 6, "max_score": 8},
        {"id": "needs_work", "name": "がんばろう", "min_score": 0, "max_score": 5},
    ]

    # DyNAMiKS設定（存在しない場合はNone）
    _DYNAMIKS_APP_PATH = Path("/Applications/DyNAMiKS.app")
    DYNAMIKS_APP_PATH = _DYNAMIKS_APP_PATH if _DYNAMIKS_APP_PATH.exists() else None

    # scancrop設定（存在しない場合はNone）
    _SCANCROP_PATH = Path("/usr/local/tetex/bin/scancrop")
    SCANCROP_PATH = _SCANCROP_PATH if _SCANCROP_PATH.exists() else None

    # TeX設定（存在しない場合はNone）
    _TEX_BIN_PATH = Path("/usr/local/teTeX/bin")
    TEX_BIN_PATH = _TEX_BIN_PATH if _TEX_BIN_PATH.exists() else None

    # Claude設定
    CLAUDE_MODEL = "claude-sonnet-4-20250514"

    # 現在の年度・学期・週・クラス（メモリ内）
    _current_year: int | None = None   # 年度（2025など）
    _current_term: str | None = None   # 学期（前期/後期）
    _current_week: int | None = None   # 週番号
    _current_class: str | None = None  # クラス名（A, B, C等）

    @classmethod
    def ensure_dirs(cls):
        """必要なディレクトリを作成"""
        cls.APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_data_dir(
        cls,
        year: int | None = None,
        term: str | None = None,
        week: int | None = None,
        class_name: str | None = None
    ) -> Path:
        """データディレクトリを取得

        Args:
            year: 年度（例: 2025）。Noneの場合は現在の年度
            term: 学期（例: "前期"）。Noneの場合は現在の学期
            week: 週番号。Noneの場合は現在の週
            class_name: クラス名（例: "A"）。Noneの場合は現在のクラス

        Returns:
            ~/Documents/IntegratedWritingGrader/{年度}/高2英語{class}/{学期}/Week{week:02d}/
            または（クラスなし）
            ~/Documents/IntegratedWritingGrader/{年度}/{学期}/Week{week:02d}/
        """
        year = year or cls._current_year
        term = term or cls._current_term
        week = week or cls._current_week
        class_name = class_name or cls._current_class

        if not year or not term or not week:
            raise RuntimeError("年度・学期・週が設定されていません")

        # 年度/クラス/学期/週 の階層構造
        if class_name:
            data_dir = (
                cls.APP_DATA_DIR
                / f"{year}年度"
                / f"高2英語{class_name}"
                / term
                / f"Week{week:02d}"
            )
        else:
            # 後方互換性：クラスなしの場合
            data_dir = (
                cls.APP_DATA_DIR
                / f"{year}年度"
                / term
                / f"Week{week:02d}"
            )

        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    @classmethod
    def get_cropped_dir(
        cls,
        year: int | None = None,
        term: str | None = None,
        week: int | None = None,
        class_name: str | None = None
    ) -> Path:
        """クロップ画像ディレクトリを取得"""
        cropped_dir = cls.get_data_dir(year, term, week, class_name) / "cropped"
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
    def get_results_path(
        cls,
        year: int | None = None,
        term: str | None = None,
        week: int | None = None,
        class_name: str | None = None
    ) -> Path:
        """採点結果JSONのパスを取得"""
        return cls.get_data_dir(year, term, week, class_name) / "results.json"

    @classmethod
    def save_results(
        cls,
        results: list[dict],
        year: int | None = None,
        term: str | None = None,
        week: int | None = None,
        class_name: str | None = None
    ):
        """採点結果を保存"""
        results_path = cls.get_results_path(year, term, week, class_name)

        # メタデータを追加
        data = {
            "year": year or cls._current_year,
            "term": term or cls._current_term,
            "week": week or cls._current_week,
            "class_name": class_name or cls._current_class,
            "saved_at": datetime.now().isoformat(),
            "results": results
        }

        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return results_path

    @classmethod
    def load_results(
        cls,
        year: int | None = None,
        term: str | None = None,
        week: int | None = None,
        class_name: str | None = None
    ) -> list[dict] | None:
        """採点結果を読み込み"""
        results_path = cls.get_results_path(year, term, week, class_name)

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
    def has_saved_results(
        cls,
        year: int | None = None,
        term: str | None = None,
        week: int | None = None,
        class_name: str | None = None
    ) -> bool:
        """保存済みの採点結果があるかチェック"""
        try:
            results_path = cls.get_results_path(year, term, week, class_name)
            return results_path.exists()
        except RuntimeError:
            return False

    @classmethod
    def get_current_week(cls) -> dict | None:
        """現在の週を取得"""
        if cls._current_year and cls._current_term and cls._current_week:
            result = {
                "year": cls._current_year,
                "term": cls._current_term,
                "week": cls._current_week
            }
            if cls._current_class:
                result["class_name"] = cls._current_class
            return result

        # current.json から読み込み試行
        current_json = cls.WEEKS_PATH / "current.json"
        if current_json.exists():
            with open(current_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                cls._current_year = data.get("year")
                cls._current_term = data.get("term")
                cls._current_week = data.get("week")
                cls._current_class = data.get("class_name")
                return data
        return None

    @classmethod
    def set_current_week(
        cls,
        year: int,
        term: str,
        week: int,
        class_name: str | None = None
    ):
        """現在の週を設定"""
        cls._current_year = year
        cls._current_term = term
        cls._current_week = week
        cls._current_class = class_name

        # current.json に保存
        current_json = cls.WEEKS_PATH / "current.json"
        data = {"year": year, "term": term, "week": week}
        if class_name:
            data["class_name"] = class_name
        with open(current_json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def get_current_year(cls) -> int | None:
        """現在の年度を取得"""
        if not cls._current_year:
            cls.get_current_week()  # current.jsonから読み込み
        return cls._current_year

    @classmethod
    def set_current_year(cls, year: int | None):
        """現在の年度を設定"""
        cls._current_year = year

    @classmethod
    def get_current_class(cls) -> str | None:
        """現在のクラス名を取得"""
        if not cls._current_class:
            cls.get_current_week()  # current.jsonから読み込み
        return cls._current_class

    @classmethod
    def set_current_class(cls, class_name: str | None):
        """現在のクラス名を設定"""
        cls._current_class = class_name

    @classmethod
    def get_week_path(cls, term: str, week: int) -> Path:
        """週のパス（プロンプト等）を取得"""
        return cls.WEEKS_PATH / term / f"第{week:02d}週"

    @classmethod
    def list_saved_weeks(cls) -> list[dict]:
        """保存済みの週一覧を取得

        新フォルダ構造: {年度}/高2英語{クラス}/{学期}/Week{週}/
        旧フォルダ構造: {学期}/高2英語{クラス}/Week{週}/ または {学期}/Week{週}/
        """
        saved = []
        if not cls.APP_DATA_DIR.exists():
            return saved

        for year_or_term_dir in cls.APP_DATA_DIR.iterdir():
            if not year_or_term_dir.is_dir():
                continue

            dir_name = year_or_term_dir.name

            # 新フォルダ構造: 年度ディレクトリ（例: 2025年度）
            if dir_name.endswith("年度"):
                year = int(dir_name.replace("年度", ""))
                saved.extend(cls._scan_year_dir(year_or_term_dir, year))

            # 旧フォルダ構造: 学期ディレクトリ（例: 前期, 後期）
            elif dir_name in ("前期", "後期"):
                saved.extend(cls._scan_term_dir_legacy(year_or_term_dir, dir_name))

        return sorted(
            saved,
            key=lambda x: (
                x.get("year") or 0,
                x.get("class_name") or "",
                x.get("term") or "",
                x.get("week") or 0
            )
        )

    @classmethod
    def _scan_year_dir(cls, year_dir: Path, year: int) -> list[dict]:
        """年度ディレクトリをスキャン"""
        saved = []
        for class_or_term_dir in year_dir.iterdir():
            if not class_or_term_dir.is_dir():
                continue

            dir_name = class_or_term_dir.name

            # クラスディレクトリ（例: 高2英語A）
            if dir_name.startswith("高2英語"):
                class_name = dir_name.replace("高2英語", "")
                for term_dir in class_or_term_dir.iterdir():
                    if not term_dir.is_dir():
                        continue
                    term = term_dir.name
                    if term not in ("前期", "後期"):
                        continue
                    for week_dir in term_dir.iterdir():
                        if not week_dir.is_dir() or not week_dir.name.startswith("Week"):
                            continue
                        try:
                            week_num = int(week_dir.name.replace("Week", ""))
                            results_path = week_dir / "results.json"
                            if results_path.exists():
                                saved.append({
                                    "year": year,
                                    "term": term,
                                    "class_name": class_name,
                                    "week": week_num,
                                    "path": str(week_dir),
                                    "has_results": True
                                })
                        except ValueError:
                            continue

            # 学期ディレクトリ（クラスなしの場合）
            elif dir_name in ("前期", "後期"):
                term = dir_name
                for week_dir in class_or_term_dir.iterdir():
                    if not week_dir.is_dir() or not week_dir.name.startswith("Week"):
                        continue
                    try:
                        week_num = int(week_dir.name.replace("Week", ""))
                        results_path = week_dir / "results.json"
                        if results_path.exists():
                            saved.append({
                                "year": year,
                                "term": term,
                                "class_name": None,
                                "week": week_num,
                                "path": str(week_dir),
                                "has_results": True
                            })
                    except ValueError:
                        continue

        return saved

    @classmethod
    def _scan_term_dir_legacy(cls, term_dir: Path, term: str) -> list[dict]:
        """旧形式の学期ディレクトリをスキャン（後方互換性）"""
        saved = []
        for sub_dir in term_dir.iterdir():
            if not sub_dir.is_dir():
                continue

            # クラス別フォルダ構造の場合（高2英語A/Week01）
            if sub_dir.name.startswith("高2英語"):
                class_name = sub_dir.name.replace("高2英語", "")
                for week_dir in sub_dir.iterdir():
                    if not week_dir.is_dir() or not week_dir.name.startswith("Week"):
                        continue
                    try:
                        week_num = int(week_dir.name.replace("Week", ""))
                        results_path = week_dir / "results.json"
                        if results_path.exists():
                            saved.append({
                                "year": None,
                                "term": term,
                                "class_name": class_name,
                                "week": week_num,
                                "path": str(week_dir),
                                "has_results": True
                            })
                    except ValueError:
                        continue

            # 従来フォルダ構造の場合（Week01）
            elif sub_dir.name.startswith("Week"):
                try:
                    week_num = int(sub_dir.name.replace("Week", ""))
                    results_path = sub_dir / "results.json"
                    if results_path.exists():
                        saved.append({
                            "year": None,
                            "term": term,
                            "class_name": None,
                            "week": week_num,
                            "path": str(sub_dir),
                            "has_results": True
                        })
                except ValueError:
                    continue

        return saved

    # ===== スタンプ関連 =====

    @classmethod
    def ensure_stamp_dirs(cls):
        """スタンプディレクトリを作成"""
        cls.STAMPS_PATH.mkdir(parents=True, exist_ok=True)
        for category in cls.DEFAULT_STAMP_CATEGORIES:
            (cls.STAMPS_PATH / category["id"]).mkdir(exist_ok=True)

    @classmethod
    def get_stamp_settings_path(cls) -> Path:
        """スタンプ設定ファイルのパス"""
        return cls.STAMPS_PATH / "settings.json"

    @classmethod
    def load_stamp_settings(cls) -> dict:
        """スタンプ設定を読み込み"""
        settings_path = cls.get_stamp_settings_path()

        if settings_path.exists():
            with open(settings_path, "r", encoding="utf-8") as f:
                return json.load(f)

        # デフォルト設定
        return {
            "enabled": True,
            "categories": cls.DEFAULT_STAMP_CATEGORIES,
            "position": "bottom_right",  # top_right, top_left, bottom_right, bottom_left
            "size": 50,  # mm
            "margin_x": 120,  # mm
            "margin_y": 10,  # mm
        }

    @classmethod
    def save_stamp_settings(cls, settings: dict):
        """スタンプ設定を保存"""
        cls.ensure_stamp_dirs()
        settings_path = cls.get_stamp_settings_path()
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

    @classmethod
    def get_stamps_for_category(cls, category_id: str) -> list[Path]:
        """カテゴリ内のスタンプ画像を取得"""
        category_path = cls.STAMPS_PATH / category_id
        if not category_path.exists():
            return []

        stamps = []
        for ext in ["*.png", "*.jpg", "*.jpeg", "*.gif"]:
            stamps.extend(category_path.glob(ext))
        return sorted(stamps)

    @classmethod
    def get_stamp_for_score(cls, score: int) -> Path | None:
        """得点に応じたスタンプを取得（ランダム）"""
        import random

        settings = cls.load_stamp_settings()
        categories = settings.get("categories", cls.DEFAULT_STAMP_CATEGORIES)

        for category in categories:
            if category["min_score"] <= score <= category["max_score"]:
                stamps = cls.get_stamps_for_category(category["id"])
                if stamps:
                    return random.choice(stamps)
                break

        return None
