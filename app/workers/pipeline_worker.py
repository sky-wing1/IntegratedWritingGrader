"""パイプラインワーカー - scancrop処理とPDFクロップ"""
from __future__ import annotations

import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Tuple, List
from PyQt6.QtCore import QThread, pyqtSignal

from app.utils.config import Config
from app.utils.qr_parser import StudentInfo, find_scancrop_output, parse_scancrop_qrcode_txt
from app.utils.additional_answer_manager import AdditionalAnswerManager, AdditionalAnswerItem


class PipelineWorker(QThread):
    """DyNAMiKS処理 + PDFクロップを行うワーカー"""

    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(str)  # 処理済みPDFパス
    students_found = pyqtSignal(list)  # 生徒情報リスト
    additional_answers_found = pyqtSignal(int)  # 追加答案件数
    error = pyqtSignal(str)

    def __init__(self, input_pdf: str, parent=None):
        super().__init__(parent)
        self.input_pdf = input_pdf
        self._is_cancelled = False
        self._students: List[StudentInfo] = []
        self._additional_items: List[AdditionalAnswerItem] = []

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
        """答案部分をクロップ（PyMuPDFで直接処理）

        追加答案（異なる週の答案）は別フォルダに分離する。
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise RuntimeError("PyMuPDFがインストールされていません")

        # 出力先ディレクトリ
        try:
            cropped_dir = Config.get_cropped_dir()
        except RuntimeError:
            cropped_dir = self._temp_dir / "cropped"
        cropped_dir.mkdir(parents=True, exist_ok=True)

        # 現在の週情報を取得
        current = Config.get_current_week()
        current_week = current.get("week") if current else None
        current_term = current.get("term") if current else None

        # PDFを開く
        doc = fitz.open(pdf_path)

        # クロップ領域（答案部分）- mm単位をポイントに変換
        def mm_to_pt(mm):
            return mm * 72 / 25.4

        crop_x = mm_to_pt(5)
        crop_y = mm_to_pt(112)
        crop_w = mm_to_pt(175)
        crop_h = mm_to_pt(140)

        # 追加答案マネージャーのキャッシュ（週ごとに管理）
        additional_managers: dict[tuple, AdditionalAnswerManager] = {}

        for page_num in range(len(doc)):
            page = doc[page_num]

            # このページの生徒情報を取得
            student_info = None
            if page_num < len(self._students):
                student_info = self._students[page_num]

            # 追加答案かどうかチェック
            is_additional = False
            if student_info and current_week and current_term:
                if student_info.week != current_week or student_info.term != current_term:
                    is_additional = True

            # クロップ領域
            crop_rect = fitz.Rect(crop_x, crop_y, crop_x + crop_w, crop_y + crop_h)

            # 画像として出力
            mat = fitz.Matrix(2, 2)  # 2倍のスケール
            pix = page.get_pixmap(matrix=mat, clip=crop_rect)

            filename = f"page_{page_num + 1:03d}.png"

            if is_additional and student_info:
                # 追加答案として保存
                target_key = (student_info.term, student_info.week)

                if target_key not in additional_managers:
                    # 該当週のディレクトリを取得/作成
                    target_dir = Config.get_data_dir(
                        year=student_info.year,
                        term=student_info.term,
                        week=student_info.week,
                        class_name=student_info.class_name
                    )
                    manager = AdditionalAnswerManager(target_dir)
                    manager.detected_from_week = current_week
                    additional_managers[target_key] = manager

                manager = additional_managers[target_key]

                # 一時ファイルに保存してからコピー
                temp_path = self._temp_dir / filename
                pix.save(str(temp_path))
                manager.save_image(temp_path, filename)

                # アイテムを追加
                item = AdditionalAnswerItem(
                    filename=filename,
                    student_name=student_info.name,
                    attendance_no=student_info.attendance_no,
                    class_name=student_info.class_name,
                    target_week=student_info.week,
                    target_term=student_info.term,
                    qr_data=f"{student_info.year}_{student_info.term}_{student_info.week}_{student_info.class_name}_{student_info.attendance_no}_{student_info.name}",
                )
                manager.add_item(item)
                self._additional_items.append(item)
            else:
                # 通常の答案として保存
                output_path = cropped_dir / filename
                pix.save(str(output_path))

        doc.close()

        # 追加答案のメタデータを保存
        for manager in additional_managers.values():
            manager.save_metadata()

        # 追加答案が見つかった場合はシグナル発火
        if self._additional_items:
            self.additional_answers_found.emit(len(self._additional_items))

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
        # 枚数が最も多い週をメインとして設定
        if self._students:
            from collections import Counter
            # (year, term, week, class_name) の組み合わせでカウント
            week_counts = Counter(
                (s.year, s.term, s.week, s.class_name)
                for s in self._students
            )
            # 最も枚数が多い週を取得
            most_common = week_counts.most_common(1)[0][0]
            year, term, week, class_name = most_common

            Config.set_current_week(year, term, week, class_name)

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

    @property
    def additional_items(self) -> List[AdditionalAnswerItem]:
        """検出された追加答案を取得"""
        return self._additional_items

    def cancel(self):
        """キャンセル"""
        self._is_cancelled = True
