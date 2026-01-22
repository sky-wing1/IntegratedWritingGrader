#!/bin/bash
# IntegratedWritingGrader ビルドスクリプト

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
pip install -q pyinstaller PyQt6 PyMuPDF

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

# PyInstallerでビルド
echo ""
echo "Building application..."
pyinstaller IntegratedWritingGrader.spec --noconfirm

# 完了
echo ""
echo "=========================================="
echo "  Build Complete!"
echo "=========================================="
echo ""
echo "App location: dist/IntegratedWritingGrader.app"
echo ""
echo "To install:"
echo "  cp -r dist/IntegratedWritingGrader.app /Applications/"
echo ""
echo "To run:"
echo "  open dist/IntegratedWritingGrader.app"
echo ""
