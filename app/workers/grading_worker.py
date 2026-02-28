"""採点ワーカー - Claude Code CLI"""

from __future__ import annotations
import json
import os
import shutil
import subprocess
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal

from app.utils.config import Config
import re

from app.utils.criteria_parser import (
    parse_criteria_from_prompt,
    GradingCriteria,
    _default_criteria,
)


def _extract_page_number(filename: str) -> int:
    """ファイル名からページ番号を抽出

    例: "page_021.png" → 21
    """
    match = re.search(r'page_(\d+)', filename)
    if match:
        return int(match.group(1))
    return 0


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

    # ネストセッション検出を回避（アプリからのCLI呼び出しは独立セッション）
    env.pop("CLAUDECODE", None)

    return env


def _find_gemini_command() -> str | None:
    """geminiコマンドのパスを検索

    バンドルされたアプリ内ではPATHが制限されているため、
    一般的なインストール先を順番に探す。
    見つからない場合はNoneを返す。
    """
    # 1. PATHにあればそれを使う
    gemini_path = shutil.which("gemini")
    if gemini_path:
        return gemini_path

    # 2. 一般的なインストール先を探す
    home = Path.home()
    common_paths = [
        home / ".local/bin",
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
        home / ".npm-global/bin",
        home / ".yarn/bin",
    ]

    # nvmの場合は最新バージョンを探す
    nvm_path = home / ".nvm/versions/node"
    if nvm_path.exists():
        versions = sorted(nvm_path.iterdir(), reverse=True)
        for ver in versions:
            gemini_bin = ver / "bin/gemini"
            if gemini_bin.exists():
                return str(gemini_bin)

    # その他のパスを探す
    for p in common_paths:
        if p.is_file() and p.name == "gemini":
            return str(p)
        gemini_bin = p / "gemini"
        if gemini_bin.exists():
            return str(gemini_bin)

    return None


class GradingWorker(QThread):
    """Claude Code CLIで採点を行うワーカー"""

    progress = pyqtSignal(int, int, str)  # current, total, message
    result_ready = pyqtSignal(int, dict)  # page_number, result
    finished = pyqtSignal(list)  # all results
    error = pyqtSignal(str)

    def __init__(
        self,
        pdf_path: str,
        image_files: list[Path] | None = None,
        ocr_results: list[dict] | None = None,
        prompt_file: Path | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self._image_files = image_files  # 外部から指定された画像リスト
        self._ocr_results = ocr_results  # Gemini OCR結果 [{page, original_text}, ...]
        self._prompt_file = prompt_file  # 外部から指定されたプロンプトファイル
        self._is_cancelled = False
        self._results: list[dict] = []
        self._criteria: GradingCriteria = _default_criteria()

    def run(self):
        """採点実行（一括処理）"""
        try:
            # プロンプト読み込み
            if self._prompt_file:
                prompt_file = self._prompt_file
            else:
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
            self.progress.emit(0, total, f"{total}件の答案を採点中...")

            # デバッグログ初期化
            try:
                debug_dir = Path.home() / ".IntegratedWritingGrader" / "debug"
                debug_dir.mkdir(parents=True, exist_ok=True)
                with open(debug_dir / "last_cli_output.txt", "w", encoding="utf-8") as f:
                    f.write(f"=== {total} pages, ocr={self._ocr_results is not None} ===\n")
            except Exception:
                pass

            if self._is_cancelled:
                return

            # 一括採点
            self._results = self._grade_batch_with_cli(base_prompt, image_files)

            # 結果を通知（結果内のページ番号を使用）
            for result in self._results:
                page_num = result.get("page", 0)
                self.result_ready.emit(page_num, result)

            self.progress.emit(total, total, "完了")

            if not self._is_cancelled:
                self.finished.emit(self._results)

        except Exception as e:
            self.error.emit(str(e))

    # 採点の1バッチあたりの最大ページ数
    BATCH_SIZE = 5

    def _grade_batch_with_cli(self, prompt: str, image_files: list[Path]) -> list[dict]:
        """Claude Code CLIで一括採点（小バッチに分割）"""
        json_schema = self._build_json_schema_for_batch()
        page_numbers = [_extract_page_number(img.name) or (i + 1) for i, img in enumerate(image_files)]

        has_ocr = self._ocr_results is not None and len(self._ocr_results) > 0

        if has_ocr:
            return self._grade_ocr_batch(prompt, image_files, page_numbers, json_schema)

        # 画像ベース: 小バッチに分割して採点
        all_results = [self._create_empty_result(pn) for pn in page_numbers]
        total = len(image_files)
        claude_cmd = _find_claude_command()

        for batch_start in range(0, total, self.BATCH_SIZE):
            if self._is_cancelled:
                break

            batch_end = min(batch_start + self.BATCH_SIZE, total)
            batch_files = image_files[batch_start:batch_end]
            batch_pages = page_numbers[batch_start:batch_end]

            self.progress.emit(
                batch_start, total,
                f"採点中... ({batch_start + 1}-{batch_end}/{total})"
            )

            batch_results = self._grade_image_batch(
                claude_cmd, prompt, batch_files, batch_pages, json_schema
            )

            for i, result in enumerate(batch_results):
                all_results[batch_start + i] = result

        return all_results

    def _grade_ocr_batch(
        self, prompt: str, image_files: list[Path],
        page_numbers: list[int], json_schema: str,
    ) -> list[dict]:
        """OCRテキストベースの一括採点"""
        ocr_by_page = {r["page"]: r.get("original_text", "") for r in self._ocr_results}

        def _sanitize_ocr_text(text: str) -> str:
            return text.replace("```", "'''")

        valid_pages = []
        for i in range(len(image_files)):
            pn = page_numbers[i]
            ocr_text = ocr_by_page.get(pn, "")
            if ocr_text and not ocr_text.startswith("[OCR"):
                valid_pages.append((i, pn, ocr_text))

        if not valid_pages:
            # 全ページOCRエラー → 画像ベースにフォールバック
            claude_cmd = _find_claude_command()
            all_results = [self._create_empty_result(pn) for pn in page_numbers]
            total = len(image_files)
            for batch_start in range(0, total, self.BATCH_SIZE):
                if self._is_cancelled:
                    break
                batch_end = min(batch_start + self.BATCH_SIZE, total)
                batch_results = self._grade_image_batch(
                    claude_cmd, prompt,
                    image_files[batch_start:batch_end],
                    page_numbers[batch_start:batch_end],
                    json_schema,
                )
                for i, result in enumerate(batch_results):
                    all_results[batch_start + i] = result
            return all_results

        # OCRテキストベースもバッチ分割して採点
        claude_cmd = _find_claude_command()
        all_results = [self._create_empty_result(pn) for pn in page_numbers]
        page_index = {pn: idx for idx, pn in enumerate(page_numbers)}

        for batch_start in range(0, len(valid_pages), self.BATCH_SIZE):
            if self._is_cancelled:
                break

            batch = valid_pages[batch_start:batch_start + self.BATCH_SIZE]

            self.progress.emit(
                batch_start, len(valid_pages),
                f"採点中... ({batch_start + 1}-{min(batch_start + len(batch), len(valid_pages))}/{len(valid_pages)})"
            )

            text_list = "\n".join([
                f"--- ページ{pn} ---\n{_sanitize_ocr_text(ocr_text)}"
                for _, pn, ocr_text in batch
            ])

            full_prompt = f"""{prompt}

以下は生徒の答案を文字起こししたテキストです。これらをすべて採点してください。

{text_list}

上記の全{len(batch)}件を採点し、結果をJSON配列で出力してください。
各要素は以下の形式です:
{json_schema}

出力はJSON配列のみにしてください。説明文やmarkdownコードブロックは不要です。
結果は必ず1つのJSON配列にまとめてください。分割出力は禁止です。
"original_text" には上記の文字起こしテキストをそのまま使用してください。"""

            batch_pages = [pn for _, pn, _ in batch]
            batch_results = self._run_cli_and_parse(
                claude_cmd, full_prompt, False,
                len(batch), batch_pages, json_schema,
            )

            for result in batch_results:
                pn = result.get("page", 0)
                if pn in page_index:
                    all_results[page_index[pn]] = result

        return all_results

    def _grade_image_batch(
        self, claude_cmd: str, prompt: str,
        batch_files: list[Path], batch_pages: list[int],
        json_schema: str,
    ) -> list[dict]:
        """画像ベースの小バッチ採点（5件程度）"""
        image_list = "\n".join([
            f"- ページ{batch_pages[i]}: {img}"
            for i, img in enumerate(batch_files)
        ])

        full_prompt = f"""あなたは英作文の採点者です。出力はJSON配列のみにしてください。
説明文、サマリー、表、markdownコードブロックは一切不要です。

{prompt}

以下の{len(batch_files)}件の画像ファイルの答案を採点してください。

{image_list}

全{len(batch_files)}件分の結果を以下のJSON配列形式で出力してください:
[
{json_schema}
]

出力はJSON配列のみです。"""

        return self._run_cli_and_parse(
            claude_cmd, full_prompt, True,
            len(batch_files), batch_pages, json_schema,
        )

    def _run_cli_and_parse(
        self, claude_cmd: str, full_prompt: str, use_read_tool: bool,
        total_pages: int, page_numbers: list[int], json_schema: str,
    ) -> list[dict]:
        """CLI実行→パース（リトライ付き）"""
        try:
            cmd = [claude_cmd, "-p", full_prompt]
            if use_read_tool:
                cmd.extend(["--allowedTools", "Read"])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1200,
                env=_get_claude_env(),
            )

            raw_output = result.stdout or ""
            raw_stderr = result.stderr or ""

            # デバッグログ
            try:
                debug_dir = Path.home() / ".IntegratedWritingGrader" / "debug"
                debug_dir.mkdir(parents=True, exist_ok=True)
                with open(debug_dir / "last_cli_output.txt", "a", encoding="utf-8") as f:
                    f.write(f"\n=== batch pages={page_numbers} rc={result.returncode} ===\n")
                    f.write(raw_output[:3000])
                    if raw_stderr:
                        f.write(f"\n--- stderr ---\n{raw_stderr[:1000]}")
            except Exception:
                pass

            if result.returncode == 0:
                parsed = self._parse_batch_result(raw_output, total_pages, page_numbers)
                # 全失敗ならリトライ
                if all(r.get("error") for r in parsed) and raw_output.strip():
                    retry_out = self._retry_json_conversion(
                        claude_cmd, raw_output, json_schema, total_pages,
                    )
                    if retry_out:
                        parsed = self._parse_batch_result(retry_out, total_pages, page_numbers)
                for r in parsed:
                    if not r.get("raw_response"):
                        r["raw_response"] = raw_output
                return parsed

            error_msg = f"CLI エラー (code={result.returncode}): {raw_stderr[:500]}"
            return [
                {"page": page_numbers[i], "error": error_msg,
                 "raw_response": raw_output, "total_score": None}
                for i in range(total_pages)
            ]

        except subprocess.TimeoutExpired:
            return [
                {"page": page_numbers[i] if i < len(page_numbers) else i + 1,
                 "error": "タイムアウト（20分）", "total_score": None}
                for i in range(total_pages)
            ]
        except FileNotFoundError:
            return [
                {"page": page_numbers[i] if i < len(page_numbers) else i + 1,
                 "error": "claude コマンドが見つかりません。Claude Code CLIをインストールしてください。",
                 "total_score": None}
                for i in range(total_pages)
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

    def _retry_json_conversion(
        self, claude_cmd: str, raw_output: str, json_schema: str, total_pages: int
    ) -> str | None:
        """採点結果がJSON形式でなかった場合、JSON変換をリトライ"""
        retry_prompt = f"""以下は英作文の採点結果ですが、JSON形式ではありません。
この内容を以下のJSON配列形式に変換してください。

採点結果テキスト:
{raw_output[:3000]}

JSON配列形式（全{total_pages}件分）:
[
{json_schema}
]

出力はJSON配列のみにしてください。説明文は不要です。
情報が不足している項目はnullにしてください。"""

        try:
            result = subprocess.run(
                [claude_cmd, "-p", retry_prompt],
                capture_output=True,
                text=True,
                timeout=120,
                env=_get_claude_env()
            )
            if result.returncode == 0 and result.stdout:
                # デバッグログ
                try:
                    debug_dir = Path.home() / ".IntegratedWritingGrader" / "debug"
                    with open(debug_dir / "last_cli_retry.txt", "w", encoding="utf-8") as f:
                        f.write(result.stdout[:5000])
                except Exception:
                    pass
                return result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

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

    @staticmethod
    def _extract_all_json_arrays(text: str) -> list[dict]:
        """出力テキストから全てのJSON配列を抽出してマージする。

        Claudeが出力を分割した場合（複数のJSON配列がmarkdown等で
        区切られている場合）にも全結果を回収する。
        """
        merged: list[dict] = []

        # ```json ... ``` ブロックを全て抽出
        pos = 0
        while True:
            code_start = text.find("```", pos)
            if code_start == -1:
                break
            # ```json or ``` の後
            content_start = text.find("\n", code_start)
            if content_start == -1:
                break
            content_start += 1
            code_end = text.find("```", content_start)
            if code_end == -1:
                break
            block = text[content_start:code_end].strip()
            try:
                parsed = json.loads(block)
                if isinstance(parsed, list):
                    merged.extend(parsed)
                elif isinstance(parsed, dict):
                    merged.append(parsed)
            except (json.JSONDecodeError, ValueError):
                pass
            pos = code_end + 3

        if merged:
            return merged

        # コードブロックがない場合: [ ... ] パターンを全て探す
        # ブラケットの対応を追跡して正しくJSON配列を抽出
        i = 0
        while i < len(text):
            if text[i] == '[':
                depth = 0
                start = i
                for j in range(i, len(text)):
                    if text[j] == '[':
                        depth += 1
                    elif text[j] == ']':
                        depth -= 1
                        if depth == 0:
                            candidate = text[start:j + 1]
                            try:
                                parsed = json.loads(candidate)
                                if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                                    merged.extend(parsed)
                            except (json.JSONDecodeError, ValueError):
                                pass
                            i = j + 1
                            break
                else:
                    break
            else:
                i += 1

        return merged

    def _parse_batch_result(self, text: str, total_pages: int, page_numbers: list[int] | None = None) -> list[dict]:
        """一括採点結果をパース

        Args:
            text: CLIからの出力テキスト
            total_pages: 総ページ数
            page_numbers: 各結果の実際のページ番号リスト（ファイル名から抽出）
        """
        # page_numbersが指定されていない場合は連番を使用
        if page_numbers is None:
            page_numbers = list(range(1, total_pages + 1))

        results = []

        # デフォルト結果を準備（実際のページ番号を使用）
        for i in range(total_pages):
            actual_page = page_numbers[i] if i < len(page_numbers) else i + 1
            results.append(self._create_empty_result(actual_page))

        # 出力が空の場合
        if not text or not text.strip():
            for result in results:
                result["error"] = "CLIからの出力が空です"
                result["raw_response"] = text
            return results

        try:
            # 出力中の全JSON配列を抽出してマージ
            # （Claudeが出力を分割した場合に対応）
            data = self._extract_all_json_arrays(text)

            if not data:
                for result in results:
                    result["error"] = "JSON形式の結果が見つかりません"
                    result["raw_response"] = text[:2000]
                return results

            if isinstance(data, list):
                # CLIからの結果をページ番号でマッピング
                # page_numbersの値とCLIが返すpageの値を照合
                page_to_index = {pn: i for i, pn in enumerate(page_numbers)}

                for item in data:
                    cli_page_num = item.get("page", 0)
                    # CLIが返したページ番号がpage_numbersに含まれているか確認
                    if cli_page_num in page_to_index:
                        idx = page_to_index[cli_page_num]
                        results[idx] = self._parse_single_item(item, cli_page_num)
                    elif 1 <= cli_page_num <= total_pages:
                        # フォールバック: 連番として扱う（互換性のため）
                        idx = cli_page_num - 1
                        actual_page = page_numbers[idx] if idx < len(page_numbers) else cli_page_num
                        results[idx] = self._parse_single_item(item, actual_page)

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
