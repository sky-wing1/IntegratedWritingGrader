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
│   ├── main.py              # Entry point
│   ├── main_window.py       # Main window UI
│   ├── widgets/             # UI components
│   │   ├── week_selector.py
│   │   ├── pdf_preview.py
│   │   ├── feedback_editor.py
│   │   ├── export_panel.py
│   │   ├── progress_panel.py
│   │   ├── integrated_grading_panel.py
│   │   └── worksheet_panel.py
│   ├── workers/             # Background workers
│   │   ├── grading_worker.py
│   │   └── pipeline_worker.py
│   ├── utils/               # Utilities
│   │   ├── config.py
│   │   ├── criteria_parser.py
│   │   └── roster_manager.py
│   └── resources/
│       └── templates/       # LaTeX templates
├── scripts/
│   └── generate_icon.py     # App icon generator
├── resources/
│   └── AppIcon.icns         # App icon
├── docs/                    # Documentation
├── .reports/                # Analysis reports
├── build.sh                 # Build script (py2app)
├── setup.py                 # py2app configuration
├── requirements.txt         # Python dependencies
└── README.md
```

## Available Scripts

| Script | Description |
|--------|-------------|
| `英作文採点.command` | Launch app in development mode |
| `build.sh` | Build standalone macOS app with py2app |
| `scripts/generate_icon.py` | Generate AppIcon.icns from source |

## Dependencies

### Core
| Package | Version | Purpose |
|---------|---------|---------|
| PyQt6 | >=6.10.0 | GUI framework |
| PyMuPDF | >=1.26.0 | PDF processing |

### Build
| Package | Version | Purpose |
|---------|---------|---------|
| py2app | latest | macOS app bundling |
| Pillow | >=10.0.0 | Icon generation |

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
