# IntegratedWritingGrader

英作文の採点を効率化するPyQt6デスクトップアプリケーション。Claude Code CLIを使ったAI採点機能を搭載。

## 機能

- **PDF読み込み**: スキャンした答案PDFを読み込み、プレビュー表示
- **AI採点**: Claude Code CLIを使って自動採点
- **手動編集**: AI採点結果の確認・修正
- **動的採点基準**: 週ごとに異なる採点基準を自動で読み込み
- **PDF出力**: 採点結果を元のPDFに注釈として追加
- **データ保存**: 学期・週ごとに採点結果をJSON形式で保存

## 必要環境

- Python 3.9+
- macOS (DyNAMiKS連携はmacOSのみ)
- Claude Code CLI (`claude` コマンド)

## インストール

```bash
# リポジトリをクローン
git clone https://github.com/YOUR_USERNAME/IntegratedWritingGrader.git
cd IntegratedWritingGrader

# 仮想環境を作成
python3 -m venv .venv
source .venv/bin/activate

# 依存関係をインストール
pip install -r requirements.txt
```

## 使い方

```bash
# アプリを起動
source .venv/bin/activate
python -m app.main
```

### 基本的な流れ

1. **週選択**: 学期と週を選択してPDFを読み込む
2. **採点**: 「Claude Code CLI」または「結果JSONインポート」で採点
3. **編集**: 採点結果を確認・修正
4. **保存**: 「結果を保存」でJSONに保存
5. **出力**: 「PDF出力」で採点済みPDFを生成

## データ保存場所

```
~/Documents/IntegratedWritingGrader/
├── 2024前期/
│   ├── Week01/
│   │   ├── cropped/        # クロップ画像
│   │   └── results.json    # 採点結果
│   └── Week13/
│       └── ...
└── 2024後期/
    └── ...
```

## 依存関係

- PyQt6 - GUI
- PyMuPDF (fitz) - PDF処理

## ライセンス

MIT License
