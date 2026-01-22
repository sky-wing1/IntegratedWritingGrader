#!/bin/bash
# IntegratedWritingGrader 起動スクリプト

cd "$(dirname "$0")"
source .venv/bin/activate
python -m app.main
