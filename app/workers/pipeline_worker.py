"""パイプラインワーカー - scancrop処理とPDFクロップ"""
from __future__ import annotations

import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Tuple, List
from PyQt6.QtCore import QThread, pyqtSignal

from app.utils.config import Config
from app.utils.qr_parser import StudentInfo, parse_qr_value, find_scancrop_output, parse_scancrop_qrcode_txt


class PipelineWorker(QThread):
    """DyNAMiKS処理 + PDFクロップを行うワーカー"""

    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(str)  # 処理済みPDFパス
    students_found = pyqtSignal(list)  # 生徒情報リスト
    error = pyqtSignal(str)

    def __init__(self, input_pdf: str, parent=None):
        super().__init__(parent)
        self.input_pdf = input_pdf
        self._is_cancelled = False
        self._students: List[StudentInfo] = []

    def run(self):
        """処理実行"""
        try:
            # 一時ディレクトリを作成（QRスキャン前に使用）
            self._temp_dir = Path(tempfile.mkdtemp(prefix="iwg_"))

            self.progress.emit(0, 4, "scancrop処理を開始...")

            # Step 1: tetex scancrop（QRコード読み取り）
            corrected_pdf, qrcode_txt = self._run_scancrop()
            if self._is_cancelled:
                return

            self.progress.emit(1, 4, "QRコードを解析中...")

            # Step 2: QRコードを解析 → 年度・学期・週・クラスを設定
            self._parse_qr_codes(qrcode_txt)
            if self._students:
                self.students_found.emit([s.to_dict() for s in self._students])
            if self._is_cancelled:
                return

            self.progress.emit(2, 4, "PDFをクロップ中...")

            # Step 3: 答案部分をクロップ（正式なディレクトリに出力）
            cropped_dir = self._crop_answers(corrected_pdf)
            if self._is_cancelled:
                return

            self.progress.emit(3, 4, "完了処理中...")

            # Step 4: 一時ファイルを正式な場所に移動
            final_pdf = self._move_to_final_location(corrected_pdf)

            # 一時ディレクトリを削除
            shutil.rmtree(self._temp_dir, ignore_errors=True)

            self.progress.emit(4, 4, "完了")
            self.finished.emit(final_pdf)

        except Exception as e:
            # エラー時も一時ディレクトリを削除
            if hasattr(self, '_temp_dir') and self._temp_dir.exists():
                shutil.rmtree(self._temp_dir, ignore_errors=True)
            self.error.emit(str(e))

    def _run_scancrop(self) -> Tuple[str, Optional[Path]]:
        """tetex scancropを実行してQRコード読み取り

        Returns:
            (処理済みPDFパス, QRcode.txtパス)
        """
        input_path = Path(self.input_pdf)
        scancrop_path = Config.SCANCROP_PATH

        # scancropがない場合はスキップ
        if not scancrop_path:
            return self.input_pdf, None

        # 一時ディレクトリにコピーして処理（scancropは入力ファイルと同じ場所に出力するため）
        temp_pdf = self._temp_dir / input_path.name
        shutil.copy2(input_path, temp_pdf)

        # scancropコマンド（QRコード読み取り＆ページソート）
        # 注: --crop オプションはDyNAMiKS三点マークでの傾き補正用だが、
        #     現在のPDFではクラッシュするため使用しない
        cmd = [
            str(scancrop_path),
            "--read-qr",
            "--sort-pages",
            "--detect-rotation",
            "--barcode-position", "16",  # 右下端
            str(temp_pdf)
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5分タイムアウト
                cwd=str(self._temp_dir)
            )

            # 出力ファイルパス
            converted_pdf = self._temp_dir / f"{input_path.stem}-converted.pdf"
            qrcode_txt = self._temp_dir / f"{input_path.stem}-converted-QRcode.txt"

            if converted_pdf.exists():
                return str(converted_pdf), qrcode_txt if qrcode_txt.exists() else None
            else:
                # 変換PDFがなければ元のPDFを使う
                return self.input_pdf, qrcode_txt if qrcode_txt.exists() else None

        except FileNotFoundError:
            return self.input_pdf, None
        except subprocess.TimeoutExpired:
            raise RuntimeError("scancrop処理がタイムアウトしました")

    def _crop_answers(self, pdf_path: str) -> Path:
        """答案部分をクロップ（PyMuPDFで直接処理）"""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise RuntimeError("PyMuPDFがインストールされていません")

        # 出力先ディレクトリ（QRスキャン成功時は正式ディレクトリ、失敗時は一時ディレクトリ）
        try:
            cropped_dir = Config.get_cropped_dir()
        except RuntimeError:
            # 年度・学期・週が未設定の場合は一時ディレクトリを使用
            cropped_dir = self._temp_dir / "cropped"
        cropped_dir.mkdir(parents=True, exist_ok=True)

        # PDFを開く
        doc = fitz.open(pdf_path)

        # クロップ領域（答案部分）- mm単位をポイントに変換
        def mm_to_pt(mm):
            return mm * 72 / 25.4

        # 答案エリア: 左上原点で X=5mm, Y=112mm, W=175mm, H=140mm
        # 【解答欄】ヘッダーから「○○ words)」まで含む
        crop_x = mm_to_pt(5)
        crop_y = mm_to_pt(112)
        crop_w = mm_to_pt(175)
        crop_h = mm_to_pt(140)

        for page_num in range(len(doc)):
            page = doc[page_num]

            # クロップ領域
            crop_rect = fitz.Rect(crop_x, crop_y, crop_x + crop_w, crop_y + crop_h)

            # 画像として出力
            mat = fitz.Matrix(2, 2)  # 2倍のスケール
            pix = page.get_pixmap(matrix=mat, clip=crop_rect)

            output_path = cropped_dir / f"page_{page_num + 1:03d}.png"
            pix.save(str(output_path))

        doc.close()
        return cropped_dir

    def _parse_qr_codes(self, qrcode_txt: Optional[Path]):
        """QRコードを解析して生徒情報を取得"""
        self._students = []

        if qrcode_txt and qrcode_txt.exists():
            # tetex scancropのQRcode.txt出力をパース
            self._students = parse_scancrop_qrcode_txt(qrcode_txt)
        else:
            # QRcode.txtがない場合は一時ディレクトリを検索
            if hasattr(self, '_temp_dir') and self._temp_dir.exists():
                self._students = find_scancrop_output(self._temp_dir)

        # 生徒情報があれば年度・クラス・学期・週を設定
        if self._students:
            first_student = self._students[0]
            # 最初の生徒の情報から設定
            Config.set_current_week(
                first_student.year,
                first_student.term,
                first_student.week,
                first_student.class_name
            )

    def _move_to_final_location(self, temp_pdf_path: str) -> str:
        """一時ファイルを正式な場所に移動"""
        temp_path = Path(temp_pdf_path)

        # 元のPDFがそのまま使われた場合は移動不要
        if temp_path == Path(self.input_pdf):
            return self.input_pdf

        # 正式なディレクトリに移動
        try:
            final_dir = Config.get_data_dir()
            final_path = final_dir / temp_path.name

            # ファイルをコピー
            shutil.copy2(temp_path, final_path)
            return str(final_path)
        except RuntimeError:
            # 年度・学期・週が未設定の場合は元のパスを返す
            return temp_pdf_path

    @property
    def students(self) -> List[StudentInfo]:
        """解析された生徒情報を取得"""
        return self._students

    def cancel(self):
        """キャンセル"""
        self._is_cancelled = True
