"""OCRワーカー - Gemini CLIで画像からテキスト一括抽出"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from app.utils.config import Config
from app.workers.grading_worker import _find_gemini_command, _get_claude_env

BATCH_SIZE = 5  # Gemini CLI 1回あたりの最大画像数


def _compute_image_hash(image_path: Path) -> str:
    """画像ファイルのSHA256ハッシュを計算"""
    sha256 = hashlib.sha256()
    with open(image_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _load_ocr_cache(cache_path: Path) -> dict | None:
    """OCRキャッシュを読み込み"""
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_ocr_cache(cache_path: Path, pages: list[dict], provider: str = "gemini"):
    """OCRキャッシュを保存"""
    data = {
        "version": 1,
        "provider": provider,
        "pages": pages,
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class OcrWorker(QThread):
    """Gemini CLIで画像からテキストを一括抽出するワーカー"""

    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(list)  # [{page: int, original_text: str}, ...]
    error = pyqtSignal(str)

    def __init__(
        self,
        image_files: list[Path],
        page_numbers: list[int] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._image_files = image_files
        self._page_numbers = page_numbers
        self._is_cancelled = False

    def run(self):
        """OCR実行（バッチ分割処理）"""
        try:
            gemini_cmd = _find_gemini_command()
            if not gemini_cmd:
                self.error.emit("gemini コマンドが見つかりません。Gemini CLIをインストールしてください。")
                return

            total = len(self._image_files)
            if total == 0:
                self.finished.emit([])
                return

            # ページ番号リストを準備
            if self._page_numbers is None:
                from app.workers.grading_worker import _extract_page_number
                self._page_numbers = [
                    _extract_page_number(img.name) or (i + 1)
                    for i, img in enumerate(self._image_files)
                ]

            # キャッシュを確認
            cache_path = self._get_cache_path()
            cached = _load_ocr_cache(cache_path) if cache_path else None
            cached_pages = {}
            if cached and cached.get("version") == 1:
                for p in cached.get("pages", []):
                    cached_pages[p.get("image_hash", "")] = p

            # キャッシュヒットと未処理を分離
            results = [None] * total
            pending_indices = []

            for i, image_file in enumerate(self._image_files):
                image_hash = _compute_image_hash(image_file)
                if image_hash in cached_pages:
                    cached_entry = cached_pages[image_hash]
                    results[i] = {
                        "page": self._page_numbers[i],
                        "original_text": cached_entry.get("original_text", ""),
                        "image_hash": image_hash,
                    }
                else:
                    pending_indices.append((i, image_file, image_hash))

            cached_count = total - len(pending_indices)

            # 全件キャッシュヒット
            if not pending_indices:
                self.progress.emit(total, total, f"文字起こし完了（キャッシュ{cached_count}件）")
                if not self._is_cancelled:
                    self.finished.emit([r for r in results if r])
                return

            if self._is_cancelled:
                return

            # バッチ分割でOCR実行
            pending_files = [(idx, img_file) for idx, img_file, _ in pending_indices]
            all_ocr_texts = {}
            batch_num = 0
            total_batches = (len(pending_files) + BATCH_SIZE - 1) // BATCH_SIZE

            for batch_start in range(0, len(pending_files), BATCH_SIZE):
                if self._is_cancelled:
                    return

                batch = pending_files[batch_start:batch_start + BATCH_SIZE]
                batch_num += 1
                done_count = cached_count + batch_start

                self.progress.emit(
                    done_count, total,
                    f"文字起こし中... [Gemini] バッチ {batch_num}/{total_batches}（{len(batch)}件）",
                )

                batch_texts = self._ocr_single_batch(gemini_cmd, batch)
                all_ocr_texts.update(batch_texts)

            # 結果をマージ
            for j, (idx, img_file, img_hash) in enumerate(pending_indices):
                text = all_ocr_texts.get(self._page_numbers[idx], "")
                results[idx] = {
                    "page": self._page_numbers[idx],
                    "original_text": text,
                    "image_hash": img_hash,
                }

            # キャッシュ保存（エラー結果はキャッシュしない）
            if cache_path:
                cacheable = [
                    r for r in results
                    if r and not r.get("original_text", "").startswith("[OCR")
                ]
                if cacheable:
                    _save_ocr_cache(cache_path, cacheable)

            self.progress.emit(total, total, "文字起こし完了")

            if not self._is_cancelled:
                self.finished.emit([r for r in results if r])

        except Exception as e:
            self.error.emit(f"OCRエラー: {e}")

    def _ocr_single_batch(
        self, gemini_cmd: str, batch_files: list[tuple[int, Path]]
    ) -> dict[int, str]:
        """1バッチ分（最大BATCH_SIZE枚）のGemini CLI呼び出し

        Returns:
            {page_number: transcribed_text, ...}
        """
        include_dirs = set()
        for _, img_file in batch_files:
            include_dirs.add(str(img_file.parent))

        file_list = "\n".join([
            f"- Page {self._page_numbers[idx]}: {img_file}"
            for idx, img_file in batch_files
        ])

        prompt = f"""Read ALL of the following image files. Each contains a handwritten English essay by a Japanese high school student.
Transcribe the English text from each image exactly as written.
- Preserve line breaks as closely as possible
- Use [?] for illegible characters
- Also transcribe any Japanese notes if present

Files:
{file_list}

Output ONLY a JSON array with this format (no other text):
[{{"page": <page_number>, "text": "<transcribed text>"}}, ...]"""

        try:
            cmd = [gemini_cmd, "-p", prompt, "--yolo"]
            for d in include_dirs:
                cmd.extend(["--include-directories", d])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                env=_get_claude_env(),
            )

            # デバッグログ（バッチごとに追記）
            try:
                debug_dir = Path.home() / ".IntegratedWritingGrader" / "debug"
                debug_dir.mkdir(parents=True, exist_ok=True)
                pages = [self._page_numbers[idx] for idx, _ in batch_files]
                with open(debug_dir / "ocr_output_all.txt", "a", encoding="utf-8") as f:
                    f.write(f"\n=== batch pages: {pages} ===\n")
                    f.write(f"=== returncode: {result.returncode} ===\n")
                    f.write(f"=== stdout ({len(result.stdout or '')}) ===\n")
                    f.write((result.stdout or "")[:8000])
                    f.write(f"\n=== stderr ({len(result.stderr or '')}) ===\n")
                    f.write((result.stderr or "")[:2000])
                    f.write("\n")
            except Exception:
                pass

            if result.returncode != 0:
                return self._fallback_empty(
                    batch_files,
                    f"[OCRエラー: CLI code={result.returncode}]",
                )

            return self._parse_batch_ocr_result(
                result.stdout or "", batch_files
            )

        except subprocess.TimeoutExpired:
            return self._fallback_empty(batch_files, "[OCRタイムアウト]")
        except Exception as e:
            return self._fallback_empty(batch_files, f"[OCRエラー: {e}]")

    def _parse_batch_ocr_result(
        self, text: str, pending_files: list[tuple[int, Path]]
    ) -> dict[int, str]:
        """一括OCR結果をパース"""
        try:
            # ```json ... ``` を探す
            if "```json" in text:
                json_start = text.find("```json") + 7
                json_end = text.find("```", json_start)
                json_text = text[json_start:json_end].strip()
            elif "```" in text and "[" in text:
                json_start = text.find("```") + 3
                json_end = text.find("```", json_start)
                json_text = text[json_start:json_end].strip()
            elif "[" in text:
                json_start = text.find("[")
                json_end = text.rfind("]") + 1
                json_text = text[json_start:json_end]
            else:
                return self._fallback_empty(
                    pending_files, "[OCRエラー: JSON未検出]"
                )

            try:
                data = json.loads(json_text)
            except json.JSONDecodeError:
                # フォールバック: テキスト全体から [ ... ] を再抽出
                if "[" in text and "]" in text:
                    fb_start = text.find("[")
                    fb_end = text.rfind("]") + 1
                    json_text = text[fb_start:fb_end]
                    data = json.loads(json_text)
                else:
                    raise

            if not isinstance(data, list):
                return self._fallback_empty(
                    pending_files, "[OCRエラー: JSON配列でない]"
                )

            return {
                item.get("page", 0): item.get("text", "")
                for item in data
            }

        except (json.JSONDecodeError, ValueError):
            return self._fallback_empty(
                pending_files, "[OCRエラー: JSONパース失敗]"
            )

    def _fallback_empty(
        self, pending_files: list[tuple[int, Path]], error_text: str
    ) -> dict[int, str]:
        """エラー時のフォールバック"""
        return {
            self._page_numbers[idx]: error_text
            for idx, _ in pending_files
        }

    def _get_cache_path(self) -> Path | None:
        """OCRキャッシュファイルのパスを取得"""
        try:
            data_dir = Config.get_data_dir()
            return data_dir / "ocr_cache.json"
        except RuntimeError:
            return None

    def cancel(self):
        """キャンセル"""
        self._is_cancelled = True
