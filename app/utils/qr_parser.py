"""QRコード値とscancrop出力のパーサー"""

from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import csv


@dataclass
class StudentInfo:
    """生徒情報"""
    year: int           # 年度（2025など）
    term: str           # 学期（前期/後期）
    week: int           # 週番号
    class_name: str     # クラス名（A, B, C等）
    attendance_no: int  # 出席番号
    name: str           # 氏名
    page: int = 0       # ページ番号（PDF内）

    @property
    def full_class_name(self) -> str:
        """フルクラス名を取得（例: 高2英語A）"""
        return f"高2英語{self.class_name}"

    @property
    def year_str(self) -> str:
        """年度文字列を取得（例: 2025年度）"""
        return f"{self.year}年度"

    def to_dict(self) -> dict:
        """辞書形式に変換"""
        return {
            "year": self.year,
            "year_str": self.year_str,
            "term": self.term,
            "week": self.week,
            "class_name": self.class_name,
            "full_class_name": self.full_class_name,
            "attendance_no": self.attendance_no,
            "name": self.name,
            "page": self.page,
        }


def parse_qr_value(qr_value: str) -> Optional[StudentInfo]:
    """QRコード値をパース

    QRコードフォーマット（新）: 年度_学期_週番号_クラス_出席番号_姓名
    例: 2025_後期_13_A_01_山田太郎

    QRコードフォーマット（旧）: 学期_週番号_クラス_出席番号_姓名
    例: 後期_13_A_01_山田太郎（年度は現在の年度として扱う）

    Args:
        qr_value: QRコードの値

    Returns:
        StudentInfo または None（パース失敗時）
    """
    if not qr_value or not isinstance(qr_value, str):
        return None

    # アンダースコアで分割
    parts = qr_value.strip().split('_')

    if len(parts) < 4:
        return None

    try:
        # 最初の要素が数字（年度）かどうかで新旧フォーマットを判定
        if parts[0].isdigit() and len(parts[0]) == 4:
            # 新フォーマット: 年度_学期_週番号_クラス_出席番号_姓名
            year = int(parts[0])
            term = parts[1]  # 前期 or 後期
            week = int(parts[2])  # 週番号
            class_name = parts[3]  # クラス (A, B, C...)
            attendance_no = int(parts[4])  # 出席番号
            # 氏名は6番目以降をすべて結合
            name = '_'.join(parts[5:]) if len(parts) > 5 else ""
        else:
            # 旧フォーマット: 学期_週番号_クラス_出席番号_姓名
            from datetime import datetime
            # 現在の年度を推定（4月始まり）
            now = datetime.now()
            year = now.year if now.month >= 4 else now.year - 1

            term = parts[0]  # 前期 or 後期
            week = int(parts[1])  # 週番号
            class_name = parts[2]  # クラス (A, B, C...)
            attendance_no = int(parts[3])  # 出席番号
            # 氏名は5番目以降をすべて結合
            name = '_'.join(parts[4:]) if len(parts) > 4 else ""

        return StudentInfo(
            year=year,
            term=term,
            week=week,
            class_name=class_name,
            attendance_no=attendance_no,
            name=name,
        )
    except (ValueError, IndexError):
        return None


def parse_dynamiks_csv(csv_path: Path) -> list[StudentInfo]:
    """DyNAMiKS scancropのCSV出力をパース

    CSVフォーマット（想定）:
    - 1列目: ページ番号またはファイル名
    - 返却SID列: QRコード値

    Args:
        csv_path: CSVファイルのパス

    Returns:
        StudentInfoのリスト
    """
    students = []

    if not csv_path.exists():
        return students

    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row_num, row in enumerate(reader, start=1):
                # QRコード列を探す（「返却SID」または「code」列）
                qr_value = None
                for key in ['返却SID', 'code', 'SID', 'qr', 'QR']:
                    if key in row:
                        qr_value = row[key]
                        break

                if not qr_value:
                    # 最初の列がQRコードの可能性
                    first_col = list(row.values())[0] if row else None
                    if first_col and '_' in first_col:
                        qr_value = first_col

                if qr_value:
                    student = parse_qr_value(qr_value)
                    if student:
                        # ページ番号を設定
                        page = row.get('page', row.get('ページ', row_num))
                        try:
                            student.page = int(page) if page else row_num
                        except ValueError:
                            student.page = row_num
                        students.append(student)

    except Exception:
        pass

    return students


def parse_scancrop_qrcode_txt(txt_path: Path) -> list[StudentInfo]:
    """tetex scancropのQRcode.txt出力をパース

    フォーマット1: ページ番号,QRコード値
        例: 1,2025_後期_13_A_01_山田太郎

    フォーマット2: QRコード値のみ（各行）
        例: 後期_13_A_01_山田太郎

    Args:
        txt_path: QRcode.txtファイルのパス

    Returns:
        StudentInfoのリスト
    """
    students = []

    if not txt_path.exists():
        return students

    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            for page_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue

                # カンマで分割: ページ番号,QRコード値
                if ',' in line:
                    parts = line.split(',', 1)
                    if len(parts) == 2:
                        page_str, qr_value = parts
                        try:
                            page_num = int(page_str.strip())
                        except ValueError:
                            pass
                        student = parse_qr_value(qr_value.strip())
                        if student:
                            student.page = page_num
                            students.append(student)
                else:
                    # カンマなし: 各行がQRコード値（行番号=ページ番号）
                    student = parse_qr_value(line)
                    if student:
                        student.page = page_num
                        students.append(student)
    except Exception:
        pass

    return students


def parse_dynamiks_output_txt(txt_path: Path) -> list[StudentInfo]:
    """DyNAMiKS scancropのテキスト出力をパース（レガシー）

    各行がQRコード値の場合

    Args:
        txt_path: テキストファイルのパス

    Returns:
        StudentInfoのリスト
    """
    students = []

    if not txt_path.exists():
        return students

    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            for page_num, line in enumerate(f, start=1):
                line = line.strip()
                if line:
                    student = parse_qr_value(line)
                    if student:
                        student.page = page_num
                        students.append(student)
    except Exception:
        pass

    return students


def find_scancrop_output(work_dir: Path) -> list[StudentInfo]:
    """作業ディレクトリ内のscancrop出力ファイルを検索してパース

    優先順位:
    1. *-QRcode.txt (tetex scancrop出力)
    2. *.csv (DyNAMiKS出力)
    3. *.txt (その他テキスト)

    Args:
        work_dir: 作業ディレクトリ

    Returns:
        StudentInfoのリスト
    """
    students = []

    # tetex scancropのQRcode.txtを優先検索
    for txt_file in work_dir.glob("*-QRcode.txt"):
        parsed = parse_scancrop_qrcode_txt(txt_file)
        if parsed:
            students.extend(parsed)
            return students

    # CSVファイルを検索（DyNAMiKS用）
    for csv_file in work_dir.glob("*.csv"):
        parsed = parse_dynamiks_csv(csv_file)
        if parsed:
            students.extend(parsed)
            return students

    # その他のテキストファイルを検索
    for txt_file in work_dir.glob("*.txt"):
        if not txt_file.name.endswith("-QRcode.txt"):
            parsed = parse_dynamiks_output_txt(txt_file)
            if parsed:
                students.extend(parsed)
                return students

    return students


# 後方互換性のためのエイリアス
def find_dynamiks_output(work_dir: Path) -> list[StudentInfo]:
    """作業ディレクトリ内の出力ファイルを検索してパース（後方互換性用）"""
    return find_scancrop_output(work_dir)


def extract_week_info(qr_value: str) -> dict | None:
    """QRコード値から週情報を抽出

    Args:
        qr_value: QRコードの値

    Returns:
        {"year": int, "term": str, "week": int, "class_name": str} or None
    """
    student = parse_qr_value(qr_value)
    if not student:
        return None

    return {
        "year": student.year,
        "term": student.term,
        "week": student.week,
        "class_name": student.class_name,
    }


def is_different_week(
    qr_value: str,
    current_week: int,
    current_term: str
) -> bool:
    """QRコードの週が現在の週と異なるかチェック

    Args:
        qr_value: QRコードの値
        current_week: 現在処理中の週番号
        current_term: 現在処理中の学期

    Returns:
        True: 異なる週の答案（追加答案）
        False: 同じ週の答案、またはQRコードが無効
    """
    info = extract_week_info(qr_value)
    if not info:
        # QRコードが読めない場合は通常処理に含める
        return False

    return info["week"] != current_week or info["term"] != current_term
