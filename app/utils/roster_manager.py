"""クラス名簿管理"""

from __future__ import annotations
import csv
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Student:
    """生徒情報"""
    student_id: str          # 生徒ID
    attendance_no: int       # 出席番号
    last_name: str           # 姓
    first_name: str          # 名
    last_name_kana: str      # せい
    first_name_kana: str     # めい
    status: str = "在籍"     # Status

    @property
    def full_name(self) -> str:
        return f"{self.last_name} {self.first_name}"

    @property
    def full_name_kana(self) -> str:
        return f"{self.last_name_kana} {self.first_name_kana}"


@dataclass
class ClassRoster:
    """クラス名簿"""
    year: str                # 年度（例: "2025"）
    class_name: str          # クラス名（例: "高2英語A"）
    students: list[Student]  # 生徒リスト

    def get_student_by_no(self, attendance_no: int) -> Optional[Student]:
        """出席番号で生徒を検索"""
        for s in self.students:
            if s.attendance_no == attendance_no:
                return s
        return None

    def get_active_students(self) -> list[Student]:
        """在籍中の生徒のみ取得"""
        return [s for s in self.students if s.status == "在籍"]


def parse_roster_file(file_path: str | Path) -> list[Student]:
    """クラス名簿.txt をパース

    形式: タブ区切り、ヘッダー行あり
    必要な列: 生徒ID, Status, 出席番号, 生徒姓, 生徒名, せいとせい, せいとめい
    """
    students = []
    file_path = Path(file_path)

    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")

        for row in reader:
            try:
                # 必須フィールドを取得
                student_id = row.get("生徒ID", "")
                status = row.get("Status", "在籍")
                attendance_no_str = row.get("出席番号", "0")
                last_name = row.get("生徒姓", "")
                first_name = row.get("生徒名", "")
                last_name_kana = row.get("せいとせい", "")
                first_name_kana = row.get("せいとめい", "")

                # 出席番号を数値に変換
                try:
                    attendance_no = int(attendance_no_str)
                except ValueError:
                    attendance_no = 0

                # 空の行はスキップ
                if not last_name and not first_name:
                    continue

                students.append(Student(
                    student_id=student_id,
                    attendance_no=attendance_no,
                    last_name=last_name,
                    first_name=first_name,
                    last_name_kana=last_name_kana,
                    first_name_kana=first_name_kana,
                    status=status,
                ))
            except Exception:
                continue  # 不正な行はスキップ

    # 出席番号でソート
    students.sort(key=lambda s: s.attendance_no)
    return students


def generate_meibo_tex(roster: ClassRoster, output_path: str | Path) -> Path:
    """名簿.tex を生成

    形式:
    \\個人出力{出席番号=02,姓=池ノ上,名=絵怜菜,せい=いけのうえ,めい=えれな}
    """
    output_path = Path(output_path)
    lines = [
        f"%!TEX root = 添削用紙個別化.tex",
        f"% 出席番号順に記載（コメントアウトで出力をスキップ可能）",
        f"% {roster.year} {roster.class_name} クラス名簿",
        "",
    ]

    for student in roster.get_active_students():
        line = (
            f"\\個人出力{{"
            f"出席番号={student.attendance_no:02d},"
            f"姓={student.last_name},"
            f"名={student.first_name},"
            f"せい={student.last_name_kana},"
            f"めい={student.first_name_kana}"
            f"}}"
        )
        lines.append(line)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return output_path


def save_roster_json(roster: ClassRoster, output_path: str | Path) -> Path:
    """名簿をJSONで保存"""
    output_path = Path(output_path)
    data = {
        "year": roster.year,
        "class_name": roster.class_name,
        "students": [asdict(s) for s in roster.students],
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return output_path


def load_roster_json(file_path: str | Path) -> ClassRoster:
    """JSONから名簿を読み込み"""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    students = [Student(**s) for s in data["students"]]
    return ClassRoster(
        year=data["year"],
        class_name=data["class_name"],
        students=students,
    )
