"""パイプラインワーカー - DyNAMiKS処理とPDFクロップ"""

import subprocess
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal

from app.utils.config import Config


class PipelineWorker(QThread):
    """DyNAMiKS処理 + PDFクロップを行うワーカー"""

    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(str)  # 処理済みPDFパス
    error = pyqtSignal(str)

    def __init__(self, input_pdf: str, parent=None):
        super().__init__(parent)
        self.input_pdf = input_pdf
        self._is_cancelled = False

    def run(self):
        """処理実行"""
        try:
            self.progress.emit(0, 3, "DyNAMiKS処理を開始...")

            # Step 1: DyNAMiKS scancrop
            corrected_pdf = self._run_dynamiks()
            if self._is_cancelled:
                return

            self.progress.emit(1, 3, "PDFをクロップ中...")

            # Step 2: 答案部分をクロップ
            cropped_dir = self._crop_answers(corrected_pdf)
            if self._is_cancelled:
                return

            self.progress.emit(2, 3, "完了処理中...")

            # Step 3: 完了
            self.progress.emit(3, 3, "完了")
            self.finished.emit(corrected_pdf)

        except Exception as e:
            self.error.emit(str(e))

    def _run_dynamiks(self) -> str:
        """DyNAMiKS scancropを実行"""
        input_path = Path(self.input_pdf)
        output_path = Config.get_session_dir() / f"{input_path.stem}_corrected.pdf"

        # DyNAMiKS CLIコマンド
        cmd = [
            str(Config.DYNAMIKS_APP_PATH / "Contents/MacOS/dyna"),
            "scancrop",
            str(input_path),
            "-o", str(output_path)
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5分タイムアウト
            )

            if result.returncode != 0:
                # DyNAMiKSがない場合、元のPDFをそのまま使う
                if "No such file" in result.stderr or not Config.DYNAMIKS_APP_PATH.exists():
                    # DyNAMiKSがない場合はスキップして元PDFを使用
                    return self.input_pdf
                raise RuntimeError(f"DyNAMiKS error: {result.stderr}")

            return str(output_path)

        except FileNotFoundError:
            # DyNAMiKSがない場合、元のPDFをそのまま使う
            return self.input_pdf
        except subprocess.TimeoutExpired:
            raise RuntimeError("DyNAMiKS処理がタイムアウトしました")

    def _crop_answers(self, pdf_path: str) -> Path:
        """答案部分をクロップ"""
        # 出力先ディレクトリ
        cropped_dir = Config.get_work_dir()
        cropped_dir.mkdir(parents=True, exist_ok=True)

        # 既存のcrop_answer_area.pyを使用
        scripts_path = Config.SCRIPTS_PATH / "crop_answer_area.py"

        if scripts_path.exists():
            cmd = [
                "python3",
                str(scripts_path),
                pdf_path,
                str(cropped_dir)  # 出力ディレクトリを指定
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode != 0:
                raise RuntimeError(f"クロップエラー: {result.stderr}")

        return cropped_dir

    def cancel(self):
        """キャンセル"""
        self._is_cancelled = True
