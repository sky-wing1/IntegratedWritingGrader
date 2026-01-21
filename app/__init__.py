"""IntegratedWritingGrader - 英作文採点アプリ"""

import sys
from pathlib import Path

# 既存スクリプトへのパスを追加
EXISTING_SCRIPTS_PATH = Path("/Users/Tsubasa/Desktop/2025/02-高2英語A/英作文B新添削用紙/scripts")
if EXISTING_SCRIPTS_PATH.exists():
    sys.path.insert(0, str(EXISTING_SCRIPTS_PATH))

# 週別問題のベースパス
WEEKS_BASE_PATH = Path("/Users/Tsubasa/Desktop/2025/02-高2英語A/英作文B新添削用紙/週別問題")
