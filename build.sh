#!/bin/bash
# IntegratedWritingGrader ビルドスクリプト (py2app版)

set -e

echo "=========================================="
echo "  IntegratedWritingGrader Build Script"
echo "=========================================="

# 仮想環境をアクティベート
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "Error: .venv not found. Run 'python3 -m venv .venv' first."
    exit 1
fi

# 依存関係確認
echo ""
echo "Checking dependencies..."
pip install -q py2app PyQt6 PyMuPDF

# アイコンがなければ生成
if [ ! -f "resources/AppIcon.icns" ]; then
    echo ""
    echo "Generating app icon..."
    pip install -q Pillow
    python scripts/generate_icon.py
fi

# ビルドディレクトリをクリーン
echo ""
echo "Cleaning previous build..."
rm -rf build dist

# py2appでビルド
echo ""
echo "Building application with py2app..."
python setup.py py2app

# quarantine属性を削除
echo ""
echo "Removing quarantine attributes..."
xattr -cr dist/IntegratedWritingGrader.app

# 実行権限を明示的に設定（念のため）
echo ""
echo "Setting executable permissions..."
chmod +x dist/IntegratedWritingGrader.app/Contents/MacOS/IntegratedWritingGrader
chmod +x dist/IntegratedWritingGrader.app/Contents/MacOS/python

# 完了
echo ""
echo "=========================================="
echo "  Build Complete!"
echo "=========================================="
echo ""
echo "App location: dist/IntegratedWritingGrader.app"
echo "App size: $(du -sh dist/IntegratedWritingGrader.app | cut -f1)"
echo ""
echo "To install (use -pR to preserve permissions):"
echo "  cp -pR dist/IntegratedWritingGrader.app /Applications/"
echo ""
echo "To run:"
echo "  open dist/IntegratedWritingGrader.app"
echo ""
