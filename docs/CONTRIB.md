# Contributing Guide

## Development Environment Setup

### Prerequisites

- Python 3.9+
- macOS (required for DyNAMiKS integration and app bundling)
- Claude Code CLI (`claude` command)

### Initial Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/IntegratedWritingGrader.git
cd IntegratedWritingGrader

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Development Workflow

### Running the App (Development Mode)

**Option 1: Double-click launcher**
```
英作文採点.command
```

**Option 2: Terminal**
```bash
source .venv/bin/activate
python -m app.main
```

### Building for Distribution

```bash
./build.sh
```

This creates `dist/IntegratedWritingGrader.app` using py2app.

## Project Structure

```
IntegratedWritingGrader/
├── app/
│   ├── main.py                    # Entry point
│   ├── main_window.py             # Main window UI
│   ├── widgets/                   # UI components
│   │   ├── week_selector.py       # 学期・週選択
│   │   ├── pdf_preview.py         # PDFプレビュー
│   │   ├── pdf_loader_panel.py    # PDF読み込みパネル
│   │   ├── feedback_editor.py     # 採点結果編集（自動保存）
│   │   ├── export_panel.py        # PDF出力パネル
│   │   ├── progress_panel.py      # 進捗表示・保存済み読み込み
│   │   ├── integrated_grading_panel.py  # 採点統合パネル
│   │   ├── worksheet_panel.py     # 添削用紙生成
│   │   ├── week_manager_panel.py  # 週管理（problem.tex編集）
│   │   ├── batch_panel.py         # バッチ処理パネル
│   │   ├── roster_panel.py        # 名簿管理パネル
│   │   └── stamp_panel.py         # スタンプ機能パネル
│   ├── workers/                   # Background workers
│   │   ├── grading_worker.py      # AI採点ワーカー
│   │   ├── pipeline_worker.py     # パイプラインワーカー
│   │   ├── batch_worker.py        # バッチ処理ワーカー
│   │   └── review_worker.py       # レビューワーカー
│   ├── utils/                     # Utilities
│   │   ├── config.py              # アプリ設定・パス管理
│   │   ├── criteria_parser.py     # 採点基準パーサー
│   │   ├── roster_manager.py      # 名簿管理
│   │   └── qr_parser.py           # QRコードパーサー
│   └── resources/
│       └── templates/             # LaTeXテンプレート
├── scripts/
│   └── generate_icon.py           # App icon generator
├── resources/
│   └── AppIcon.icns               # App icon
├── docs/                          # Documentation
├── .reports/                      # Analysis reports
├── build.sh                       # Build script (py2app)
├── run_app.sh                     # Development run script
├── 英作文採点.command              # Double-click launcher
├── setup.py                       # py2app configuration
├── requirements.txt               # Python dependencies
└── README.md
```

## Available Scripts

| Script | Description |
|--------|-------------|
| `英作文採点.command` | Launch app in development mode (double-click) |
| `run_app.sh` | Launch app in development mode (terminal) |
| `build.sh` | Build standalone macOS app with py2app |
| `scripts/generate_icon.py` | Generate AppIcon.icns from source |

### Build Commands

```bash
# Development run
./run_app.sh

# Production build
./build.sh

# Manual build
source .venv/bin/activate
python setup.py py2app

# Code sign (optional, for distribution)
codesign --force --deep --sign - dist/IntegratedWritingGrader.app
```

## Dependencies

### Core
| Package | Version | Purpose |
|---------|---------|---------|
| PyQt6 | >=6.10.0 | GUI framework |
| PyMuPDF | >=1.26.0 | PDF processing (fitz) |

### Build
| Package | Version | Purpose |
|---------|---------|---------|
| py2app | >=0.28.0 | macOS app bundling |
| Pillow | >=10.0.0 | Icon generation |

### External Tools (optional)
| Tool | Path | Purpose |
|------|------|---------|
| Claude Code CLI | `claude` | AI grading |
| uplatex/dvipdfmx | `/usr/local/teTeX/bin/` | LaTeX compilation |
| DyNAMiKS.app | `/Applications/` | Mark sheet integration |
| scancrop | `/usr/local/tetex/bin/` | PDF auto-crop |

## Testing

Currently no automated tests. Manual testing workflow:

1. Load a PDF
2. Run AI grading
3. Edit feedback
4. Export annotated PDF
5. Verify output

## Code Style

- Follow existing patterns
- Use type hints
- No print statements (use logging)
- Keep files under 800 lines
- Prefer immutable patterns

## Pull Request Process

1. Create feature branch from `main`
2. Make changes following code style
3. Test manually
4. Run `/code-review` before submitting
5. Submit PR with clear description
