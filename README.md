# IntegratedWritingGrader

英作文の採点を効率化するPyQt6デスクトップアプリケーション。Claude Code CLIを使ったAI採点機能を搭載。

## 機能

- **PDF読み込み**: スキャンした答案PDFを読み込み、プレビュー表示
- **AI採点**: Claude Code CLIを使って自動採点
- **手動編集**: AI採点結果の確認・修正（自動保存対応）
- **保存済み結果の読み込み**: 中断した採点を再開可能
- **動的採点基準**: 週ごとに異なる採点基準を自動で読み込み
- **週管理**: problem.tex・prompt.txtの編集
- **PDF出力**: 採点結果を元のPDFに注釈として追加
- **添削用紙生成**: LaTeXテンプレートから個別化された添削用紙を生成
- **バッチ処理**: 複数クラスの一括処理
- **名簿管理**: 生徒名簿の管理・紐付け
- **スタンプ機能**: PDF注釈の一括追加
- **データ保存**: 学期・週ごとに採点結果をJSON形式で保存

## 必要環境

- Python 3.9+
- macOS
- Claude Code CLI (`claude` コマンド)

### オプション

- TeX環境 (uplatex, dvipdfmx) - 添削用紙生成用
- DyNAMiKS.app - 連携機能用
- scancrop - PDF自動クロップ用

## インストール

### 開発環境

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

### ビルド済みアプリ

```bash
./build.sh
cp -r dist/IntegratedWritingGrader.app /Applications/
```

## 使い方

### 起動方法

**開発モード:**
```bash
# ダブルクリックで起動
英作文採点.command

# または
source .venv/bin/activate
python -m app.main
```

**ビルド済みアプリ:**
```bash
open /Applications/IntegratedWritingGrader.app
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
├── weeks/                    # 週別問題データ
│   ├── 前期/
│   │   └── 第01週/
│   │       ├── problem.tex   # 問題文
│   │       └── prompt.txt    # 採点基準
│   └── 後期/
│       └── ...
├── 2024前期/                 # 採点結果
│   ├── Week01/
│   │   ├── cropped/          # クロップ画像
│   │   └── results.json      # 採点結果
│   └── Week13/
│       └── ...
└── 2024後期/
    └── ...
```

## ドキュメント

- [Contributing Guide](docs/CONTRIB.md) - 開発環境セットアップ、コード規約
- [Runbook](docs/RUNBOOK.md) - デプロイ、トラブルシューティング

## 依存関係

| Package | Version | Purpose |
|---------|---------|---------|
| PyQt6 | >=6.10.0 | GUI |
| PyMuPDF | >=1.26.0 | PDF処理 |
| py2app | >=0.28.0 | macOSアプリ化 |
| Pillow | >=10.0.0 | アイコン生成 |

## ライセンス

MIT License
