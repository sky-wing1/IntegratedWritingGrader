"""採点基準パーサー"""

from __future__ import annotations
import re
from pathlib import Path
from dataclasses import dataclass


@dataclass
class CriterionOption:
    """判定オプション（○、△、×など）"""
    judgment: str  # ○, △, ×, ◎ など
    score: int     # 点数


@dataclass
class Criterion:
    """採点基準の1項目"""
    number: str      # ①, ②, etc.
    name: str        # 項目名（根拠の論理性など）
    options: list[CriterionOption]  # 判定オプションのリスト


@dataclass
class GradingCriteria:
    """採点基準全体"""
    content_total: int  # 内容点満点（通常12点）
    criteria: list[Criterion]  # 各基準項目
    expression_note: str  # 表現点についての注記


def parse_criteria_from_prompt(prompt_path: str | Path) -> GradingCriteria:
    """プロンプトファイルから採点基準をパース"""
    with open(prompt_path, "r", encoding="utf-8") as f:
        text = f.read()

    return parse_criteria_from_text(text)


def parse_criteria_from_text(text: str) -> GradingCriteria:
    """テキストから採点基準をパース"""
    # 採点基準セクションを抽出
    criteria_match = re.search(
        r'###参考情報\d*（採点基準）###(.+?)(?=###|$)',
        text,
        re.DOTALL
    )

    if not criteria_match:
        # デフォルト基準を返す
        return _default_criteria()

    criteria_text = criteria_match.group(1)

    # 内容点満点を取得
    content_total_match = re.search(r'●内容点[：:]\s*(\d+)点', criteria_text)
    content_total = int(content_total_match.group(1)) if content_total_match else 12

    # 各基準項目をパース
    # パターン: ①項目名（○：X点，△：Y点，×：Z点）
    # 項目名に（）が含まれる場合もあるので、判定記号（○△×◎）から始まる部分を探す
    criterion_pattern = re.compile(
        r'([①②③④⑤])(.+?)[（(]([○△×◎][：:][^）)]+)[）)]',
        re.MULTILINE
    )

    criteria = []
    for match in criterion_pattern.finditer(criteria_text):
        number = match.group(1)
        name = match.group(2).strip()
        options_text = match.group(3)

        # オプションをパース（○：4点 形式）
        option_pattern = re.compile(r'([○△×◎])[\s：:]+(\d+)点')
        options = []
        for opt_match in option_pattern.finditer(options_text):
            options.append(CriterionOption(
                judgment=opt_match.group(1),
                score=int(opt_match.group(2))
            ))

        if options:  # オプションがある場合のみ追加
            criteria.append(Criterion(
                number=number,
                name=name,
                options=options
            ))

    # 表現点の注記
    expression_match = re.search(r'●文法・表現点[：:](.+?)(?=\n\n|###|$)', criteria_text, re.DOTALL)
    expression_note = expression_match.group(1).strip() if expression_match else "原則1点ずつ減点"

    if not criteria:
        return _default_criteria()

    return GradingCriteria(
        content_total=content_total,
        criteria=criteria,
        expression_note=expression_note
    )


def _default_criteria() -> GradingCriteria:
    """デフォルトの採点基準"""
    return GradingCriteria(
        content_total=12,
        criteria=[
            Criterion(
                number="①",
                name="根拠の論理性",
                options=[
                    CriterionOption("○", 4),
                    CriterionOption("△", 2),
                    CriterionOption("×", 0),
                ]
            ),
            Criterion(
                number="②",
                name="根拠のサポート",
                options=[
                    CriterionOption("○", 8),
                    CriterionOption("△", 4),
                    CriterionOption("×", 0),
                ]
            ),
        ],
        expression_note="原則1点ずつ減点"
    )


def criteria_to_json_schema(criteria: GradingCriteria) -> str:
    """採点基準からJSON形式の説明を生成"""
    lines = []

    for c in criteria.criteria:
        options_str = "/".join([f"{o.judgment}({o.score}点)" for o in c.options])
        lines.append(f'  "{c.number.replace("①", "criterion1_").replace("②", "criterion2_").replace("③", "criterion3_")}judgment": "<{c.name}の判定: {"/".join([o.judgment for o in c.options])}>"')
        lines.append(f'  "{c.number.replace("①", "criterion1_").replace("②", "criterion2_").replace("③", "criterion3_")}score": <{c.name}の点数: {"/".join([str(o.score) for o in c.options])}>')

    return ",\n".join(lines)


def criteria_to_prompt_instruction(criteria: GradingCriteria) -> str:
    """採点基準からプロンプト用の説明を生成"""
    lines = ["採点基準（内容点）:"]

    for c in criteria.criteria:
        options_str = "、".join([f"{o.judgment}：{o.score}点" for o in c.options])
        lines.append(f"  {c.number}{c.name}（{options_str}）")

    return "\n".join(lines)
