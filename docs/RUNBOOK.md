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
| Grading results | `~/Documents/IntegratedWritingGrader/{year}{term}/Week{nn}/results.json` |
| Cropped images | `~/Documents/IntegratedWritingGrader/{year}{term}/Week{nn}/cropped/` |
| Worksheets | `~/Library/Application Support/IntegratedWritingGrader/worksheets/` |

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
```

**Fix:** Install and authenticate Claude Code CLI.

### LaTeX Compilation Fails

**Symptom:** Worksheet generation fails.

**Checks:**
```bash
# Is TeX installed?
which uplatex
which dvipdfmx

# Check TeX bin path
ls /usr/local/teTeX/bin/
```

**Fix:** Install MacTeX or update path in `app/utils/config.py`.

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
