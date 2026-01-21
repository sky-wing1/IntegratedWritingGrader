#!/bin/bash
# IntegratedWritingGrader 起動スクリプト

cd "$(dirname "$0")"

# 仮想環境があれば有効化
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

python -m app.main
