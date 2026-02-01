"""講評生成ワーカー"""

from __future__ import annotations
import subprocess
from pathlib import Path
from typing import List, Optional
from PyQt6.QtCore import QThread, pyqtSignal

from app.workers.grading_worker import _find_claude_command, _get_claude_env


# 講評生成プロンプト
REVIEW_PROMPT = r"""ここまで評価してきた答案についての講評を作ってください。

講評は、以下の構成にしてください：

①全体の所感（どれを選んだ人が何人いたか、といったデータも含める）

②この問題の考え方・解き方振り返り

③実際の答案を3つ用いて、答案の内容面での問題点を考えさせ、その後に答え（改善例）を示すコーナー

④優秀答案を5つ紹介（実際の答案の文法ミスを修正したものに、ひとことコメントを付け加える。）

生徒が読んでためになる、具体的で参考になる内容になるように心がけてください。
改善例を示す際には、制限語数を超えないように注意してください。

---

出力は以下の2つの形式で返してください：

【プレーンテキスト版】
通常のテキスト形式で講評を書いてください。

---SEPARATOR---

【LaTeX版】
以下のTeXフォーマットで講評を書いてください：

```latex
\begin{長いカラーボックス}{\▲ 講評}

\br{.5}

\Subsection*{① 全体の所感}

[内容]

\begin{enumerate}[\textbullet]
\item \太強調{選択肢1:} X名（約Y%）
\item \太強調{選択肢2:} X名（約Y%）
\end{enumerate}

[全体の傾向についてのコメント]

\Subsection*{② この問題の考え方・解き方振り返り}

[内容]

\begin{enumerate}
\item \太強調{戦略1のタイトル}

[説明]

\item \太強調{戦略2のタイトル}

[説明]

\end{enumerate}

\Subsection*{③答案クリニック}

内容面で「あと一歩」だった答案を3つ取り上げます。

\太強調{【ケース1】タイトル}

\begin{枠囲み}{答案例}
[元答案の問題部分を\太強調{}で強調]
\end{枠囲み}

\begin{ascolorbox5}{解説}
[問題点の解説]

\begin{枠囲み}{改善例}
[改善した答案]
\end{枠囲み}

\end{ascolorbox5}

[ケース2, ケース3も同様に]

\Subsection*{④ 優秀答案の紹介}

論理構成が明確で，具体例の選び方が秀逸だった答案を紹介します。（文法ミスは修正済みです）

\begin{枠囲み}{優秀答案1：タイトル}
[答案内容。キーポイントは\太強調{}で強調]
\end{枠囲み}

\太強調{【講評】}：[コメント]

[優秀答案2〜5も同様に]

\end{長いカラーボックス}
```

重要：
- \太強調{} で重要な単語やフレーズを強調
- \begin{枠囲み}{タイトル}...\end{枠囲み} で答案例を囲む
- \begin{ascolorbox5}{タイトル}...\end{ascolorbox5} で解説を囲む
- \begin{enumerate}[\textbullet] で箇条書き
- \Subsection*{} でセクション見出し
- \br{.5} や \br{1} で適宜改行

出力形式の注意：
- 余計な前置き（「了解です」「完成しました」など）は絶対に追加しないでください
- 必ず【プレーンテキスト版】から直接始めてください
- ---SEPARATOR--- の後に必ず【LaTeX版】を出力してください
- 出力の最後に要約やコメントを追加しないでください
"""


class ReviewWorker(QThread):
    """講評生成ワーカー"""

    progress = pyqtSignal(str)  # ステータスメッセージ
    finished = pyqtSignal(str, str)  # (プレーンテキスト, LaTeX)
    error = pyqtSignal(str)

    def __init__(
        self,
        results: List[dict],
        prompt_file: Optional[Path] = None,
        parent=None
    ):
        super().__init__(parent)
        self.results = results
        self.prompt_file = prompt_file
        self._is_cancelled = False

    def run(self):
        """講評生成実行"""
        try:
            self.progress.emit("講評を生成中...")

            # 採点基準（プロンプト）を読み込み
            base_prompt = ""
            if self.prompt_file and self.prompt_file.exists():
                with open(self.prompt_file, "r", encoding="utf-8") as f:
                    base_prompt = f.read()

            # 採点結果のサマリーを作成（元答案テキスト含む）
            results_summary = self._build_results_summary()

            # フルプロンプトを構築（画像なし、テキストのみ）
            full_prompt = f"""以下は英作文問題の採点基準です：

{base_prompt}

---

以下は各答案の採点結果と元答案です：

{results_summary}

---

{REVIEW_PROMPT}"""

            # Claude Code CLI呼び出し（画像読み込み不要）
            claude_cmd = _find_claude_command()

            # 余計な前置きや会話的応答を防ぐためのシステムプロンプト
            system_prompt = (
                "You are a professional essay reviewer. "
                "Output EXACTLY what is requested in the prompt. "
                "Do not add explanations, questions, commentary, or summaries "
                "before or after the requested output. "
                "Do not use casual language or emojis. "
                "Follow the output format precisely. "
                "Start directly with 【プレーンテキスト版】."
            )

            cmd = [
                claude_cmd,
                "-p", full_prompt,
                "--system-prompt", system_prompt,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5分タイムアウト（画像なしなので短縮）
                env=_get_claude_env()
            )

            if self._is_cancelled:
                return

            if result.returncode == 0:
                review_text = result.stdout.strip()
                plain_text, latex_text = self._split_output(review_text)
                self.finished.emit(plain_text, latex_text)
            else:
                self.error.emit(f"CLI エラー: {result.stderr}")

        except subprocess.TimeoutExpired:
            self.error.emit("タイムアウト（5分）")
        except FileNotFoundError:
            self.error.emit("claude コマンドが見つかりません")
        except Exception as e:
            self.error.emit(str(e))

    def _build_results_summary(self) -> str:
        """採点結果のサマリーを構築（元答案テキスト含む）"""
        lines = []

        for i, result in enumerate(self.results):
            page = result.get("page", i + 1)
            total_score = result.get("total_score", "?")
            content_score = result.get("content_score", "?")
            expression_deduction = result.get("expression_deduction", "?")
            original_text = result.get("original_text", "")
            corrected_text = result.get("corrected_text", "")
            content_comment = result.get("content_comment", "")

            lines.append(f"【答案{page}】")
            lines.append(f"  合計点: {total_score}点 (内容点: {content_score}, 表現減点: {expression_deduction})")

            # 基準項目の判定を追加
            for key, value in result.items():
                if key.endswith("_judgment") and value:
                    criterion_name = result.get(key.replace("_judgment", "_name"), "")
                    if criterion_name:
                        lines.append(f"  {criterion_name}: {value}")

            if original_text:
                lines.append(f"  元答案: {original_text}")
            if corrected_text:
                lines.append(f"  添削答案: {corrected_text}")
            if content_comment:
                lines.append(f"  コメント: {content_comment}")
            lines.append("")

        return "\n".join(lines)

    def _split_output(self, text: str) -> tuple:
        """出力をプレーンテキストとLaTeXに分割"""
        separator = "---SEPARATOR---"
        plain_marker = "【プレーンテキスト版】"
        latex_marker = "【LaTeX版】"

        # 前置き（「了解です」など）を除去
        # 【プレーンテキスト版】より前の部分を削除
        if plain_marker in text:
            text = text[text.index(plain_marker):]

        if separator in text:
            parts = text.split(separator, 1)
            plain_text = parts[0].strip()
            latex_text = parts[1].strip() if len(parts) > 1 else ""

            # 【プレーンテキスト版】と【LaTeX版】のヘッダーを除去
            if plain_marker in plain_text:
                plain_text = plain_text.replace(plain_marker, "").strip()
            if latex_marker in latex_text:
                latex_text = latex_text.replace(latex_marker, "").strip()

            # ```latex ... ``` を除去
            if "```latex" in latex_text:
                latex_text = latex_text.replace("```latex", "").replace("```", "").strip()

            return plain_text, latex_text
        else:
            # セパレーターがない場合
            # 【プレーンテキスト版】マーカーを除去
            if plain_marker in text:
                text = text.replace(plain_marker, "").strip()
            return text, ""

    def cancel(self):
        """キャンセル"""
        self._is_cancelled = True


def generate_review_sync(
    results: List[dict],
    prompt_file: Optional[Path] = None
) -> str:
    """同期的に講評を生成（テスト用）"""
    worker = ReviewWorker(results, prompt_file)

    review_text = ""
    error_msg = ""

    def on_finished(text):
        nonlocal review_text
        review_text = text

    def on_error(msg):
        nonlocal error_msg
        error_msg = msg

    worker.finished.connect(on_finished)
    worker.error.connect(on_error)

    worker.start()
    worker.wait()

    if error_msg:
        raise RuntimeError(error_msg)

    return review_text
