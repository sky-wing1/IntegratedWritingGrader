# Runbook

Operational guide for IntegratedWritingGrader.

## Deployment

### Building the App

```bash
cd /path/to/IntegratedWritingGrader
./build.sh
```

Output: `dist/IntegratedWritingGrader.app`

### Installing

```bash
cp -r dist/IntegratedWritingGrader.app /Applications/
```

### First Launch

If macOS blocks the app:
1. Right-click the app
2. Select "Open"
3. Click "Open" in the dialog

Or remove quarantine:
```bash
xattr -cr /Applications/IntegratedWritingGrader.app
```

## Data Locations

| Type | Location |
|------|----------|
| App data | `~/Documents/IntegratedWritingGrader/` |
| Week problems | `~/Documents/IntegratedWritingGrader/weeks/{term}/第{nn}週/problem.tex` |
| Week prompts | `~/Documents/IntegratedWritingGrader/weeks/{term}/第{nn}週/prompt.txt` |
| Grading results | `~/Documents/IntegratedWritingGrader/{year}{term}/Week{nn}/results.json` |
| Cropped images | `~/Documents/IntegratedWritingGrader/{year}{term}/Week{nn}/cropped/` |
| Worksheets | Generated on demand (temp directory) |

## Common Issues and Fixes

### App Won't Start

**Symptom:** App crashes immediately on launch.

**Diagnosis:**
```bash
# Check console logs
log show --predicate 'process == "IntegratedWritingGrader"' --last 5m

# Or run from terminal
open -a IntegratedWritingGrader.app
```

**Common causes:**
1. Missing dependencies - Rebuild with `./build.sh`
2. Corrupted app bundle - Delete and reinstall
3. Permission issue - Run `xattr -cr` on the app

### PDF Loading Fails

**Symptom:** "Failed to load PDF" error.

**Checks:**
1. Is the PDF file corrupted?
2. Is the file path accessible?
3. Does the app have file access permissions?

**Fix:** Grant file access in System Settings > Privacy & Security > Files and Folders.

### AI Grading Not Working

**Symptom:** Claude Code CLI errors during grading.

**Checks:**
```bash
# Is Claude CLI installed?
which claude

# Is it authenticated?
claude --version

# Check common installation paths
ls ~/.nvm/versions/node/*/bin/claude
ls /opt/homebrew/bin/claude
ls /usr/local/bin/claude
```

**Fix:** Install and authenticate Claude Code CLI.

**Note:** The app automatically searches for `claude` in these locations:
- PATH environment variable
- nvm (Node Version Manager): `~/.nvm/versions/node/*/bin/`
- Homebrew: `/opt/homebrew/bin/`, `/usr/local/bin/`
- npm global: `~/.npm-global/bin/`
- yarn global: `~/.yarn/bin/`

### Claude CLI Not Found (Bundled App)

**Symptom:** "claude コマンドが見つかりません" error when running from /Applications/.

**Cause:** Bundled macOS apps have limited PATH environment.

**Checks:**
```bash
# Verify claude is installed somewhere
find ~ -name "claude" -type f 2>/dev/null | head -5
```

**Fix:** The app now automatically detects claude in common locations. If still failing:
1. Ensure claude is installed via `npm install -g @anthropic/claude-code`
2. Note the installation path
3. The app should find it automatically on next launch

### LaTeX Compilation Fails

**Symptom:** Worksheet generation fails.

**Checks:**
```bash
# Is TeX installed?
which uplatex
which dvipdfmx

# Check TeX bin path
ls /usr/local/teTeX/bin/

# Check TeXShop uplatex2pdf (preferred)
ls ~/Library/TeXShop/bin/uplatex2pdf
```

**Fix:** Install MacTeX or update path in `app/utils/config.py`.

### Week Problem File Missing

**Symptom:** "problem.tex not found" error.

**Checks:**
```bash
# Check weeks directory
ls ~/Documents/IntegratedWritingGrader/weeks/

# Check specific week
ls ~/Documents/IntegratedWritingGrader/weeks/後期/第14週/
```

**Fix:** Use the "週管理" tab to create problem.tex for the week.

### scancrop Not Found

**Symptom:** PDF cropping skipped.

**Checks:**
```bash
ls /usr/local/tetex/bin/scancrop
```

**Fix:** Install scancrop or the feature will be skipped automatically.

## Backup and Recovery

### Backing Up Data

```bash
# Backup all grading data
cp -r ~/Documents/IntegratedWritingGrader ~/Documents/IntegratedWritingGrader_backup_$(date +%Y%m%d)
```

### Restoring Data

```bash
# Restore from backup
cp -r ~/Documents/IntegratedWritingGrader_backup_YYYYMMDD/* ~/Documents/IntegratedWritingGrader/
```

## Optional Integrations

### DyNAMiKS

If `/Applications/DyNAMiKS.app` exists, the app can integrate with it for additional features.

### TeX Environment

If `/usr/local/teTeX/bin/` exists, worksheet PDF generation is available.

### scancrop

If `/usr/local/tetex/bin/scancrop` exists, automatic PDF cropping is available.

## Performance Notes

- Large PDFs (100+ pages) may take time to process
- AI grading runs sequentially to avoid rate limits
- Background workers prevent UI freezing
- Feedback editing auto-saves with 500ms debounce
- Claude CLI path is cached after first detection

## Resuming Work

To resume a previous grading session:
1. Select the term and week
2. Choose "保存済み結果を読み込み" from the dropdown
3. Select the saved result from the dialog
4. Continue editing

## Logs

The app uses Python logging. To see debug output, run from terminal:

```bash
cd /path/to/IntegratedWritingGrader
source .venv/bin/activate
python -m app.main
```

## Updates

1. Pull latest changes
2. Rebuild: `./build.sh`
3. Replace app in /Applications/
