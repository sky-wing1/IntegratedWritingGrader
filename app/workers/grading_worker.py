"""採点ワーカー - Claude Code CLI"""

from __future__ import annotations
import json
import os
import shutil
import subprocess
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal

from app.utils.config import Config
from app.utils.criteria_parser import (
    parse_criteria_from_prompt,
    GradingCriteria,
    _default_criteria,
)


def _find_claude_command() -> str:
    """claudeコマンドのパスを検索

    バンドルされたアプリ内ではPATHが制限されているため、
    一般的なインストール先を順番に探す。
    """
    # 1. PATHにあればそれを使う
    claude_path = shutil.which("claude")
    if claude_path:
        return claude_path

    # 2. 一般的なインストール先を探す
    home = Path.home()
    common_paths = [
        # Claude Code CLI (公式インストール先)
        home / ".local/bin",
        # nvm経由のNode.js
        home / ".nvm/versions/node",
        # Homebrew
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
        # npm global
        home / ".npm-global/bin",
        # yarn global
        home / ".yarn/bin",
    ]

    # nvmの場合は最新バージョンを探す
    nvm_path = home / ".nvm/versions/node"
    if nvm_path.exists():
        versions = sorted(nvm_path.iterdir(), reverse=True)
        for ver in versions:
            claude_bin = ver / "bin/claude"
            if claude_bin.exists():
                return str(claude_bin)

    # その他のパスを探す
    for p in common_paths:
        if p.is_file() and p.name == "claude":
            return str(p)
        claude_bin = p / "claude"
        if claude_bin.exists():
            return str(claude_bin)

    # 見つからない場合はそのまま "claude" を返す（エラーになる）
    return "claude"


def _get_claude_env() -> dict:
    """Claude CLI実行用の環境変数を取得

    バンドルされたアプリ内ではPATHが制限されているため、
    一般的なNode.jsインストール先をPATHに追加する。
    """
    env = os.environ.copy()
    home = Path.home()

    # nvmの最新バージョンを動的に取得
    nvm_bin_path = None
    nvm_path = home / ".nvm/versions/node"
    if nvm_path.exists():
        versions = sorted(nvm_path.iterdir(), reverse=True)
        for ver in versions:
            bin_path = ver / "bin"
            if bin_path.exists():
                nvm_bin_path = str(bin_path)
                break

    extra_paths = [
        p for p in [
            str(home / ".local/bin"),  # Claude Code CLI
            nvm_bin_path,
            "/opt/homebrew/bin",
            "/usr/local/bin",
            str(home / ".npm-global/bin"),
            str(home / ".yarn/bin"),
        ] if p
    ]

    env["PATH"] = ":".join(extra_paths) + ":" + env.get("PATH", "")
    return env


class GradingWorker(QThread):
    """Claude Code CLIで採点を行うワーカー"""

    progress = pyqtSignal(int, int, str)  # current, total, message
    result_ready = pyqtSignal(int, dict)  # page_number, result
    finished = pyqtSignal(list)  # all results
    error = pyqtSignal(str)

    def __init__(self, pdf_path: str, image_files: list[Path] | None = None, parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self._image_files = image_files  # 外部から指定された画像リスト
        self._is_cancelled = False
        self._results: list[dict] = []
        self._criteria: GradingCriteria = _default_criteria()

    def run(self):
        """採点実行（一括処理）"""
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

            # 画像ファイルを取得（外部指定があればそれを使用）
            if self._image_files is not None:
                image_files = self._image_files
            else:
                # 従来の動作: cropped ディレクトリから取得
                cropped_dir = Config.get_work_dir()
                if cropped_dir.exists():
                    image_files = sorted(cropped_dir.glob("*.png"))
                else:
                    image_files = []

            if not image_files:
                raise RuntimeError("採点対象の画像が見つかりません。")

            total = len(image_files)
            self.progress.emit(0, total, f"{total}件の答案を一括採点中...")

            if self._is_cancelled:
                return

            # 一括採点
            self._results = self._grade_batch_with_cli(base_prompt, image_files)

            # 結果を通知
            for i, result in enumerate(self._results):
                self.result_ready.emit(i + 1, result)

            self.progress.emit(total, total, "完了")

            if not self._is_cancelled:
                self.finished.emit(self._results)

        except Exception as e:
            self.error.emit(str(e))

    def _grade_batch_with_cli(self, prompt: str, image_files: list[Path]) -> list[dict]:
        """Claude Code CLIで一括採点"""
        # 動的なJSON形式を生成
        json_schema = self._build_json_schema_for_batch()

        # 画像リストを作成
        image_list = "\n".join([f"- ページ{i+1}: {img}" for i, img in enumerate(image_files)])

        # プロンプトに全画像パスを追加
        full_prompt = f"""{prompt}

以下の画像ファイル群の答案をすべて採点してください。

{image_list}

必ず以下のJSON配列形式で、全ページ分の結果を出力してください:
```json
[
{json_schema}
]
```

重要: 必ず全{len(image_files)}件分の結果を配列で返してください。"""

        try:
            # claudeコマンドのパスを取得
            claude_cmd = _find_claude_command()

            # Claude Code CLI呼び出し
            cmd = [
                claude_cmd,
                "-p", full_prompt,
                "--allowedTools", "Read",  # 画像読み込み許可
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10分タイムアウト
                env=_get_claude_env()
            )

            # デバッグ用: 結果をログに保存
            raw_output = result.stdout or ""
            raw_stderr = result.stderr or ""

            if result.returncode == 0:
                parsed_results = self._parse_batch_result(raw_output, len(image_files))
                # raw_responseを全結果に追加（デバッグ用）
                for r in parsed_results:
                    if not r.get("raw_response"):
                        r["raw_response"] = raw_output
                return parsed_results
            else:
                # エラー時は全ページ分のエラー結果を返す
                error_msg = f"CLI エラー (code={result.returncode}): {raw_stderr[:500]}"
                return [
                    {
                        "page": i + 1,
                        "error": error_msg,
                        "raw_response": raw_output,
                        "total_score": None
                    }
                    for i in range(len(image_files))
                ]

        except subprocess.TimeoutExpired:
            return [
                {
                    "page": i + 1,
                    "error": "タイムアウト（10分）",
                    "total_score": None
                }
                for i in range(len(image_files))
            ]
        except FileNotFoundError:
            return [
                {
                    "page": i + 1,
                    "error": "claude コマンドが見つかりません。Claude Code CLIをインストールしてください。",
                    "total_score": None
                }
                for i in range(len(image_files))
            ]

    def _grade_with_cli(self, prompt: str, image_file: Path, page_num: int) -> dict:
        """Claude Code CLIで1ページ採点（レガシー）"""
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
            # claudeコマンドのパスを取得
            claude_cmd = _find_claude_command()

            # Claude Code CLI呼び出し
            cmd = [
                claude_cmd,
                "-p", full_prompt,
                "--allowedTools", "Read",  # 画像読み込み許可
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,  # 3分タイムアウト
                env=_get_claude_env()
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
        """動的なJSON形式を構築（単一）"""
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
        lines.append('  "original_text": "<生徒が書いた元の答案をそのまま書き写す>",')
        lines.append('  "corrected_text": "<添削後の文章（修正箇所は【】で囲む）>",')
        lines.append('  "content_comment": "<内容についてのコメント>",')
        lines.append('  "expression_comment": "<表現についてのコメント>",')
        lines.append('  "revision_points": "<書き直しで意識すべきポイント>"')
        lines.append("}")

        return "\n".join(lines)

    def _build_json_schema_for_batch(self) -> str:
        """動的なJSON形式を構築（バッチ用、1件分の例）"""
        lines = ["  {"]
        lines.append('    "page": <ページ番号>,')

        # 各基準項目
        for i, criterion in enumerate(self._criteria.criteria):
            options_judgment = "/".join([o.judgment for o in criterion.options])
            options_score = "/".join([str(o.score) for o in criterion.options])
            lines.append(f'    "criterion{i+1}_judgment": "<{criterion.number}{criterion.name}の判定: {options_judgment}>",')
            lines.append(f'    "criterion{i+1}_score": <{criterion.number}{criterion.name}の点数: {options_score}>,')

        # 共通フィールド
        lines.append(f'    "content_score": <内容点合計 0-{self._criteria.content_total}>,')
        lines.append('    "expression_deduction": <表現減点 0以上>,')
        lines.append('    "total_score": <合計点（内容点-表現減点、0以上）>,')
        lines.append('    "original_text": "<生徒が書いた元の答案をそのまま書き写す>",')
        lines.append('    "corrected_text": "<添削後の文章（修正箇所は【】で囲む）>",')
        lines.append('    "content_comment": "<内容についてのコメント>",')
        lines.append('    "expression_comment": "<表現についてのコメント>",')
        lines.append('    "revision_points": "<書き直しで意識すべきポイント>"')
        lines.append("  },")
        lines.append("  // ... 全ページ分続く")

        return "\n".join(lines)

    def _parse_batch_result(self, text: str, total_pages: int) -> list[dict]:
        """一括採点結果をパース"""
        results = []

        # デフォルト結果を準備
        for i in range(total_pages):
            results.append(self._create_empty_result(i + 1))

        # 出力が空の場合
        if not text or not text.strip():
            for result in results:
                result["error"] = "CLIからの出力が空です"
                result["raw_response"] = text
            return results

        try:
            # ```json ... ``` を探す
            if "```json" in text:
                json_start = text.find("```json") + 7
                json_end = text.find("```", json_start)
                json_text = text[json_start:json_end].strip()
            elif "[" in text:
                # 最初の[から最後の]まで
                json_start = text.find("[")
                json_end = text.rfind("]") + 1
                json_text = text[json_start:json_end]
            else:
                # JSONが見つからない場合
                for result in results:
                    result["error"] = "JSON形式の結果が見つかりません"
                    result["raw_response"] = text[:2000]  # 最初の2000文字を保存
                return results

            data = json.loads(json_text)

            if isinstance(data, list):
                for item in data:
                    page_num = item.get("page", 0)
                    if 1 <= page_num <= total_pages:
                        results[page_num - 1] = self._parse_single_item(item, page_num)

        except (json.JSONDecodeError, ValueError) as e:
            # JSONパース失敗時はエラーを記録
            for result in results:
                result["error"] = f"JSON パースエラー: {e}"
                result["raw_response"] = text[:2000]

        return results

    def _create_empty_result(self, page_num: int) -> dict:
        """空の結果を作成"""
        result = {
            "page": page_num,
            "raw_response": "",
            "content_score": None,
            "expression_deduction": None,
            "total_score": None,
            "original_text": "",
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

        return result

    def _parse_single_item(self, data: dict, page_num: int) -> dict:
        """単一の採点結果をパース"""
        result = self._create_empty_result(page_num)

        # 動的な基準項目を取得
        for i, criterion in enumerate(self._criteria.criteria):
            key_prefix = f"criterion{i+1}_"
            result[f"{key_prefix}judgment"] = data.get(f"{key_prefix}judgment", "")
            result[f"{key_prefix}score"] = data.get(f"{key_prefix}score")

        # 共通フィールド
        result.update({
            "content_score": data.get("content_score") or data.get("内容点"),
            "expression_deduction": data.get("expression_deduction") or data.get("表現減点"),
            "total_score": data.get("total_score") or data.get("合計点"),
            "original_text": data.get("original_text") or data.get("元答案", ""),
            "corrected_text": data.get("corrected_text") or data.get("添削答案", ""),
            "content_comment": data.get("content_comment") or data.get("内容コメント", ""),
            "expression_comment": data.get("expression_comment") or data.get("表現コメント", ""),
            "revision_points": data.get("revision_points") or data.get("書き直しポイント", ""),
        })

        return result


def merge_student_info(results: list[dict], students: list[dict]) -> list[dict]:
    """採点結果に生徒情報をマージ

    Args:
        results: 採点結果のリスト
        students: 生徒情報のリスト（StudentInfo.to_dict()の結果）

    Returns:
        生徒情報がマージされた採点結果
    """
    # ページ番号でマッピング
    student_by_page = {s.get("page", 0): s for s in students}

    merged = []
    for result in results:
        page = result.get("page", 0)
        student = student_by_page.get(page, {})

        # 新しい辞書を作成（イミュータブル）
        merged_result = {
            **result,
            "student_name": student.get("name", result.get("student_name", "")),
            "class_name": student.get("class_name", ""),
            "full_class_name": student.get("full_class_name", ""),
            "attendance_no": student.get("attendance_no", 0),
            "year": student.get("year", 0),
            "term": student.get("term", ""),
            "week": student.get("week", 0),
        }
        merged.append(merged_result)

    return merged


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
            # 生徒情報
            "student_name": item.get("student_name") or item.get("生徒名", ""),
            "class_name": item.get("class_name", ""),
            "full_class_name": item.get("full_class_name", ""),
            "attendance_no": item.get("attendance_no", 0),
            "year": item.get("year", 0),
            "term": item.get("term", ""),
            "week": item.get("week", 0),
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
