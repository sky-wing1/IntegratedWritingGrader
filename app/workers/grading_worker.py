"""採点ワーカー - Claude Code CLI"""

from __future__ import annotations
import json
import subprocess
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal

from app.utils.config import Config
from app.utils.criteria_parser import (
    parse_criteria_from_prompt,
    GradingCriteria,
    _default_criteria,
)


class GradingWorker(QThread):
    """Claude Code CLIで採点を行うワーカー"""

    progress = pyqtSignal(int, int, str)  # current, total, message
    result_ready = pyqtSignal(int, dict)  # page_number, result
    finished = pyqtSignal(list)  # all results
    error = pyqtSignal(str)

    def __init__(self, pdf_path: str, parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self._is_cancelled = False
        self._results: list[dict] = []
        self._criteria: GradingCriteria = _default_criteria()

    def run(self):
        """採点実行"""
        try:
            # プロンプト読み込み
            current = Config.get_current_week()
            if not current:
                raise RuntimeError("週が選択されていません")

            week_path = Config.get_week_path(current["term"], current["week"])
            prompt_file = week_path / "prompt.txt"

            if not prompt_file.exists():
                raise RuntimeError(f"プロンプトファイルが見つかりません: {prompt_file}")

            with open(prompt_file, "r", encoding="utf-8") as f:
                base_prompt = f.read()

            # 採点基準をパース
            self._criteria = parse_criteria_from_prompt(prompt_file)

            # クロップ済み画像を取得
            cropped_dir = Config.get_work_dir()
            if cropped_dir.exists():
                image_files = sorted(cropped_dir.glob("*.png"))
            else:
                image_files = []

            if not image_files:
                raise RuntimeError("クロップ済み画像が見つかりません。先にPDF処理を実行してください。")

            total = len(image_files)

            for i, image_file in enumerate(image_files):
                if self._is_cancelled:
                    return

                self.progress.emit(i, total, f"ページ {i + 1}/{total} を採点中...")

                result = self._grade_with_cli(base_prompt, image_file, i + 1)
                self._results.append(result)
                self.result_ready.emit(i + 1, result)

            self.progress.emit(total, total, "完了")

            if not self._is_cancelled:
                self.finished.emit(self._results)

        except Exception as e:
            self.error.emit(str(e))

    def _grade_with_cli(self, prompt: str, image_file: Path, page_num: int) -> dict:
        """Claude Code CLIで1ページ採点"""
        # 動的なJSON形式を生成
        json_schema = self._build_json_schema()

        # プロンプトに画像パスを追加
        full_prompt = f"""{prompt}

以下の画像ファイルの答案を採点してください。
画像: {image_file}

必ず以下のJSON形式で結果を出力してください:
```json
{json_schema}
```"""

        try:
            # Claude Code CLI呼び出し
            cmd = [
                "claude",
                "-p", full_prompt,
                "--allowedTools", "Read",  # 画像読み込み許可
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180  # 3分タイムアウト
            )

            if result.returncode == 0:
                return self._parse_result(result.stdout, page_num)
            else:
                return {
                    "page": page_num,
                    "error": f"CLI エラー: {result.stderr}",
                    "total_score": None
                }

        except subprocess.TimeoutExpired:
            return {
                "page": page_num,
                "error": "タイムアウト（3分）",
                "total_score": None
            }
        except FileNotFoundError:
            return {
                "page": page_num,
                "error": "claude コマンドが見つかりません。Claude Code CLIをインストールしてください。",
                "total_score": None
            }

    def _parse_result(self, text: str, page_num: int) -> dict:
        """採点結果をパース"""
        result = {
            "page": page_num,
            "raw_response": text,
            "content_score": None,
            "expression_deduction": None,
            "total_score": None,
            "corrected_text": "",
            "content_comment": "",
            "expression_comment": "",
            "revision_points": "",
        }

        # 動的な基準項目を初期化
        for i, criterion in enumerate(self._criteria.criteria):
            result[f"criterion{i+1}_judgment"] = ""
            result[f"criterion{i+1}_score"] = None
            result[f"criterion{i+1}_name"] = criterion.name

        # レガシーキーも初期化
        result["logic_judgment"] = ""
        result["logic_score"] = None
        result["support_judgment"] = ""
        result["support_score"] = None

        try:
            # ```json ... ``` を探す
            if "```json" in text:
                json_start = text.find("```json") + 7
                json_end = text.find("```", json_start)
                json_text = text[json_start:json_end].strip()
            elif "{" in text:
                # 最初の{から最後の}まで
                json_start = text.find("{")
                json_end = text.rfind("}") + 1
                json_text = text[json_start:json_end]
            else:
                json_text = None

            if json_text:
                data = json.loads(json_text)

                # 動的な基準項目を取得
                for i, criterion in enumerate(self._criteria.criteria):
                    key_prefix = f"criterion{i+1}_"
                    result[f"{key_prefix}judgment"] = data.get(f"{key_prefix}judgment", "")
                    result[f"{key_prefix}score"] = data.get(f"{key_prefix}score")

                # レガシーキーも試す（旧形式との互換性）
                result["logic_judgment"] = data.get("logic_judgment", "")
                result["logic_score"] = data.get("logic_score")
                result["support_judgment"] = data.get("support_judgment", "")
                result["support_score"] = data.get("support_score")

                # 共通フィールド
                result.update({
                    "content_score": data.get("content_score") or data.get("内容点"),
                    "expression_deduction": data.get("expression_deduction") or data.get("表現減点"),
                    "total_score": data.get("total_score") or data.get("合計点"),
                    "corrected_text": data.get("corrected_text") or data.get("添削答案", ""),
                    "content_comment": data.get("content_comment") or data.get("内容コメント", ""),
                    "expression_comment": data.get("expression_comment") or data.get("表現コメント", ""),
                    "revision_points": data.get("revision_points") or data.get("書き直しポイント", ""),
                })

        except (json.JSONDecodeError, ValueError):
            # JSONパース失敗時は生テキストのまま
            result["error"] = "JSON パースエラー"

        return result

    def cancel(self):
        """キャンセル"""
        self._is_cancelled = True

    def _build_json_schema(self) -> str:
        """動的なJSON形式を構築"""
        lines = ["{"]

        # 各基準項目
        for i, criterion in enumerate(self._criteria.criteria):
            options_judgment = "/".join([o.judgment for o in criterion.options])
            options_score = "/".join([str(o.score) for o in criterion.options])
            lines.append(f'  "criterion{i+1}_judgment": "<{criterion.number}{criterion.name}の判定: {options_judgment}>",')
            lines.append(f'  "criterion{i+1}_score": <{criterion.number}{criterion.name}の点数: {options_score}>,')

        # 共通フィールド
        lines.append(f'  "content_score": <内容点合計 0-{self._criteria.content_total}>,')
        lines.append('  "expression_deduction": <表現減点 0以上>,')
        lines.append('  "total_score": <合計点（内容点-表現減点、0以上）>,')
        lines.append('  "corrected_text": "<添削後の文章（修正箇所は【】で囲む）>",')
        lines.append('  "content_comment": "<内容についてのコメント>",')
        lines.append('  "expression_comment": "<表現についてのコメント>",')
        lines.append('  "revision_points": "<書き直しで意識すべきポイント>"')
        lines.append("}")

        return "\n".join(lines)


def load_results_from_json(json_path: str) -> list[dict]:
    """JSONファイルから採点結果を読み込む"""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 配列形式
    if isinstance(data, list):
        return load_results_from_json_data(data)

    # オブジェクト形式（results キーがある場合）
    if isinstance(data, dict) and "results" in data:
        return load_results_from_json_data(data["results"])

    raise ValueError("不正なJSONフォーマットです。配列形式か {results: [...]} 形式にしてください。")


def load_results_from_json_data(data: list) -> list[dict]:
    """JSON配列から採点結果を読み込む"""
    results = []
    for i, item in enumerate(data):
        result = {
            "page": item.get("page", i + 1),
            "content_score": item.get("content_score") or item.get("内容点"),
            "expression_deduction": item.get("expression_deduction") or item.get("表現減点"),
            "total_score": item.get("total_score") or item.get("合計点"),
            "corrected_text": item.get("corrected_text") or item.get("添削答案", ""),
            "content_comment": item.get("content_comment") or item.get("内容コメント", ""),
            "expression_comment": item.get("expression_comment") or item.get("表現コメント", ""),
            "revision_points": item.get("revision_points") or item.get("書き直しポイント", ""),
            "student_name": item.get("student_name") or item.get("生徒名", ""),
        }

        # 動的なcriterion*キーをすべてコピー
        for key in item.keys():
            if key.startswith("criterion"):
                result[key] = item[key]

        # レガシーキー（互換性のため）
        result["logic_judgment"] = item.get("logic_judgment", "")
        result["logic_score"] = item.get("logic_score")
        result["support_judgment"] = item.get("support_judgment", "")
        result["support_score"] = item.get("support_score")

        results.append(result)
    return results
