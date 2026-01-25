# 自動アップデート機能 実装計画

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** GitHub Actionsによるリリース自動化と、アプリ起動時の自動更新チェック＆インストール機能を実装する

**Architecture:** GitHub APIで最新リリースをチェックし、新バージョンがあればZIPをダウンロード→解凍→/Applications/に置換→再起動。GitHub Actionsでタグpush時に自動ビルド＆Release作成。

**Tech Stack:** Python 3.11, PyQt6, GitHub Actions, GitHub Releases API, urllib, zipfile

---

## Task 1: バージョン一元化

**Files:**
- Modify: `setup.py:1-53`

**Step 1: setup.pyでバージョンを動的に読み込むように変更**

```python
"""
py2app build script for IntegratedWritingGrader
Usage: python setup.py py2app
"""

import re
from setuptools import setup

# app/__init__.py から __version__ を読み込む
with open("app/__init__.py") as f:
    version_match = re.search(r'__version__ = "(.+)"', f.read())
    if version_match:
        VERSION = version_match.group(1)
    else:
        VERSION = "0.0.0"

APP = ['app/main.py']
DATA_FILES = [
    ('app/resources/templates', [
        'app/resources/templates/名簿.tex',
        'app/resources/templates/復テ個別化スタイル.sty',
        'app/resources/templates/添削用紙個別化.tex',
        'app/resources/templates/高２Integrated Writing 添削用紙.tex',
    ]),
]
OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'resources/AppIcon.icns',
    'plist': {
        'CFBundleName': 'IntegratedWritingGrader',
        'CFBundleDisplayName': '英作文採点',
        'CFBundleIdentifier': 'com.integratedwritinggrader.app',
        'CFBundleVersion': VERSION,
        'CFBundleShortVersionString': VERSION,
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,
        'LSMinimumSystemVersion': '10.15',
    },
    'packages': ['PyQt6', 'fitz', 'app'],
    'includes': [
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
    ],
    'excludes': [
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
    ],
}

setup(
    name='IntegratedWritingGrader',
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
```

**Step 2: 動作確認**

Run: `python -c "exec(open('setup.py').read().split('setup(')[0]); print(VERSION)"`
Expected: `1.0.0`

**Step 3: Commit**

```bash
git add setup.py
git commit -m "refactor: read version from app/__init__.py in setup.py"
```

---

## Task 2: GitHub Actions ワークフロー作成

**Files:**
- Create: `.github/workflows/release.yml`

**Step 1: ディレクトリ作成**

Run: `mkdir -p .github/workflows`

**Step 2: ワークフローファイル作成**

```yaml
name: Build and Release

on:
  push:
    tags:
      - 'v*.*.*'

jobs:
  build:
    runs-on: macos-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install -r requirements.txt
          pip install py2app

      - name: Verify version matches tag
        run: |
          TAG_VERSION="${GITHUB_REF#refs/tags/v}"
          APP_VERSION=$(python -c "import re; print(re.search(r'__version__ = \"(.+)\"', open('app/__init__.py').read()).group(1))")
          if [ "$TAG_VERSION" != "$APP_VERSION" ]; then
            echo "Error: Tag version ($TAG_VERSION) does not match app version ($APP_VERSION)"
            exit 1
          fi
          echo "Version verified: $APP_VERSION"

      - name: Build app
        run: python setup.py py2app

      - name: Create ZIP
        run: |
          cd dist
          zip -r ../IntegratedWritingGrader-${{ github.ref_name }}.zip IntegratedWritingGrader.app

      - name: Create Release
        uses: softprops/action-gh-release@v2
        with:
          files: IntegratedWritingGrader-${{ github.ref_name }}.zip
          generate_release_notes: true
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci: add GitHub Actions workflow for automated releases"
```

---

## Task 3: UpdateChecker クラス作成

**Files:**
- Create: `app/utils/updater.py`

**Step 1: updater.py を作成**

```python
"""アプリ自動更新機能"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from app import __version__

logger = logging.getLogger(__name__)

GITHUB_REPO = "sky-wing1/IntegratedWritingGrader"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
APP_INSTALL_PATH = Path("/Applications/IntegratedWritingGrader.app")


@dataclass
class ReleaseInfo:
    """リリース情報"""
    version: str
    download_url: str
    release_notes: str
    published_at: str


class UpdateChecker:
    """アップデートチェッカー"""

    def __init__(self):
        self.current_version = __version__

    def check_for_updates(self) -> ReleaseInfo | None:
        """
        GitHub APIで最新リリースをチェック

        Returns:
            新バージョンがあればReleaseInfo、なければNone
        """
        try:
            request = Request(
                GITHUB_API_URL,
                headers={"Accept": "application/vnd.github.v3+json"}
            )
            with urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))

            tag_name = data.get("tag_name", "")
            latest_version = tag_name.lstrip("v")

            if not self._is_newer_version(latest_version):
                logger.info(f"No update available. Current: {self.current_version}, Latest: {latest_version}")
                return None

            # ZIPアセットを探す
            download_url = None
            for asset in data.get("assets", []):
                if asset["name"].endswith(".zip"):
                    download_url = asset["browser_download_url"]
                    break

            if not download_url:
                logger.warning("No ZIP asset found in release")
                return None

            return ReleaseInfo(
                version=latest_version,
                download_url=download_url,
                release_notes=data.get("body", ""),
                published_at=data.get("published_at", "")
            )

        except URLError as e:
            logger.warning(f"Failed to check for updates: {e}")
            return None
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse release info: {e}")
            return None

    def _is_newer_version(self, latest: str) -> bool:
        """バージョン比較（セマンティックバージョニング）"""
        try:
            current_parts = [int(x) for x in self.current_version.split(".")]
            latest_parts = [int(x) for x in latest.split(".")]
            return latest_parts > current_parts
        except ValueError:
            return False

    def download_update(
        self,
        release: ReleaseInfo,
        progress_callback: Callable[[int, int], None] | None = None
    ) -> Path:
        """
        アップデートをダウンロード

        Args:
            release: リリース情報
            progress_callback: 進捗コールバック (downloaded_bytes, total_bytes)

        Returns:
            ダウンロードしたZIPファイルのパス
        """
        temp_dir = Path(tempfile.mkdtemp())
        zip_path = temp_dir / f"IntegratedWritingGrader-v{release.version}.zip"

        request = Request(release.download_url)
        with urlopen(request, timeout=60) as response:
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 8192

            with open(zip_path, "wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total_size)

        logger.info(f"Downloaded update to {zip_path}")
        return zip_path

    def install_update(self, zip_path: Path) -> bool:
        """
        アップデートをインストール

        Args:
            zip_path: ダウンロードしたZIPファイルのパス

        Returns:
            成功したらTrue
        """
        temp_dir = zip_path.parent
        extract_dir = temp_dir / "extracted"

        try:
            # ZIP解凍
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            # 解凍された.appを探す
            app_path = None
            for item in extract_dir.iterdir():
                if item.suffix == ".app":
                    app_path = item
                    break

            if not app_path:
                logger.error("No .app found in ZIP")
                return False

            # /Applications/に置換
            if APP_INSTALL_PATH.exists():
                # 管理者権限が必要な場合はosascriptを使用
                try:
                    shutil.rmtree(APP_INSTALL_PATH)
                except PermissionError:
                    logger.info("Requesting admin privileges for installation")
                    script = f'''
                    do shell script "rm -rf '{APP_INSTALL_PATH}' && cp -R '{app_path}' '{APP_INSTALL_PATH}'" with administrator privileges
                    '''
                    result = subprocess.run(
                        ["osascript", "-e", script],
                        capture_output=True,
                        text=True
                    )
                    if result.returncode != 0:
                        logger.error(f"Installation failed: {result.stderr}")
                        return False
                    return True

            shutil.copytree(app_path, APP_INSTALL_PATH)
            logger.info(f"Installed update to {APP_INSTALL_PATH}")
            return True

        except Exception as e:
            logger.error(f"Installation failed: {e}")
            return False
        finally:
            # クリーンアップ
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass

    def restart_app(self) -> None:
        """アプリを再起動"""
        logger.info("Restarting application...")
        subprocess.Popen(["open", str(APP_INSTALL_PATH)])
        sys.exit(0)
```

**Step 2: 動作確認（インポートテスト）**

Run: `cd /Users/Tsubasa/Developer/IntegratedWritingGrader && python -c "from app.utils.updater import UpdateChecker, ReleaseInfo; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add app/utils/updater.py
git commit -m "feat: add UpdateChecker class for auto-update functionality"
```

---

## Task 4: 更新ダイアログUI作成

**Files:**
- Create: `app/widgets/update_dialog.py`

**Step 1: update_dialog.py を作成**

```python
"""アップデートダイアログ"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QMessageBox,
)

if TYPE_CHECKING:
    from app.utils.updater import ReleaseInfo, UpdateChecker

logger = logging.getLogger(__name__)


class DownloadWorker(QThread):
    """ダウンロードワーカー"""

    progress = pyqtSignal(int, int)  # downloaded, total
    finished = pyqtSignal(object)  # zip_path or None
    error = pyqtSignal(str)

    def __init__(self, checker: "UpdateChecker", release: "ReleaseInfo"):
        super().__init__()
        self.checker = checker
        self.release = release

    def run(self):
        try:
            zip_path = self.checker.download_update(
                self.release,
                progress_callback=lambda d, t: self.progress.emit(d, t)
            )
            self.finished.emit(zip_path)
        except Exception as e:
            logger.error(f"Download failed: {e}")
            self.error.emit(str(e))


class UpdateDialog(QDialog):
    """アップデート確認ダイアログ"""

    def __init__(self, checker: "UpdateChecker", release: "ReleaseInfo", parent=None):
        super().__init__(parent)
        self.checker = checker
        self.release = release
        self._download_worker: DownloadWorker | None = None

        self.setWindowTitle("アップデート")
        self.setMinimumWidth(450)
        self.setModal(True)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # タイトル
        title = QLabel(f"新バージョン v{self.release.version} が利用可能です")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # 現在のバージョン
        current_label = QLabel(f"現在のバージョン: v{self.checker.current_version}")
        current_label.setStyleSheet("color: #666;")
        layout.addWidget(current_label)

        # リリースノート
        if self.release.release_notes:
            notes_label = QLabel("更新内容:")
            notes_label.setStyleSheet("font-weight: bold; margin-top: 8px;")
            layout.addWidget(notes_label)

            notes_text = QTextEdit()
            notes_text.setReadOnly(True)
            notes_text.setPlainText(self.release.release_notes)
            notes_text.setMaximumHeight(150)
            notes_text.setStyleSheet("""
                QTextEdit {
                    background-color: #f5f5f5;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    padding: 8px;
                }
            """)
            layout.addWidget(notes_text)

        # プログレスバー（初期は非表示）
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("ダウンロード中... %p%")
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # ステータスラベル
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666;")
        self.status_label.hide()
        layout.addWidget(self.status_label)

        # ボタン
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.later_btn = QPushButton("後で")
        self.later_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.later_btn)

        self.update_btn = QPushButton("今すぐ更新")
        self.update_btn.setDefault(True)
        self.update_btn.setStyleSheet("""
            QPushButton {
                background-color: #0066cc;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0052a3;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        self.update_btn.clicked.connect(self._start_update)
        button_layout.addWidget(self.update_btn)

        layout.addLayout(button_layout)

    def _start_update(self):
        """アップデート開始"""
        self.update_btn.setEnabled(False)
        self.later_btn.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        self.status_label.show()
        self.status_label.setText("ダウンロード中...")

        self._download_worker = DownloadWorker(self.checker, self.release)
        self._download_worker.progress.connect(self._on_progress)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.error.connect(self._on_error)
        self._download_worker.start()

    def _on_progress(self, downloaded: int, total: int):
        """ダウンロード進捗"""
        if total > 0:
            percent = int(downloaded / total * 100)
            self.progress_bar.setValue(percent)
            mb_downloaded = downloaded / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            self.status_label.setText(f"ダウンロード中... {mb_downloaded:.1f} / {mb_total:.1f} MB")

    def _on_download_finished(self, zip_path):
        """ダウンロード完了"""
        if not zip_path:
            self._on_error("ダウンロードに失敗しました")
            return

        self.status_label.setText("インストール中...")
        self.progress_bar.setFormat("インストール中...")
        self.progress_bar.setValue(100)

        # インストール実行
        if self.checker.install_update(zip_path):
            self.status_label.setText("インストール完了！再起動します...")
            QMessageBox.information(
                self,
                "アップデート完了",
                "アップデートが完了しました。アプリを再起動します。"
            )
            self.checker.restart_app()
        else:
            self._on_error("インストールに失敗しました")

    def _on_error(self, error: str):
        """エラー発生"""
        self.progress_bar.hide()
        self.status_label.setText(f"エラー: {error}")
        self.status_label.setStyleSheet("color: red;")
        self.update_btn.setEnabled(True)
        self.later_btn.setEnabled(True)
        QMessageBox.critical(self, "アップデートエラー", error)
```

**Step 2: 動作確認（インポートテスト）**

Run: `cd /Users/Tsubasa/Developer/IntegratedWritingGrader && python -c "from app.widgets.update_dialog import UpdateDialog; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add app/widgets/update_dialog.py
git commit -m "feat: add UpdateDialog for auto-update UI"
```

---

## Task 5: main.py への統合

**Files:**
- Modify: `app/main.py:1-34`

**Step 1: main.py に更新チェック機能を追加**

```python
"""IntegratedWritingGrader - メインエントリーポイント"""

import logging
import sys
from pathlib import Path

# アプリケーションパスを追加
app_path = Path(__file__).parent
sys.path.insert(0, str(app_path.parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer
from app.main_window import MainWindow
from app.utils.updater import UpdateChecker
from app.widgets.update_dialog import UpdateDialog

logger = logging.getLogger(__name__)


def check_for_updates(app: QApplication, window: MainWindow) -> None:
    """起動時にアップデートをチェック"""
    try:
        checker = UpdateChecker()
        release = checker.check_for_updates()

        if release:
            logger.info(f"New version available: {release.version}")
            dialog = UpdateDialog(checker, release, window)
            dialog.exec()
    except Exception as e:
        logger.warning(f"Update check failed: {e}")


def main():
    """アプリケーション起動"""
    # ロギング設定
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    app = QApplication(sys.argv)
    app.setApplicationName("IntegratedWritingGrader")
    app.setOrganizationName("Tsubasa")

    # ハイDPI対応
    app.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    window = MainWindow()
    window.show()

    # 起動後にアップデートチェック（UIが表示されてから）
    QTimer.singleShot(1000, lambda: check_for_updates(app, window))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

**Step 2: 動作確認**

Run: `cd /Users/Tsubasa/Developer/IntegratedWritingGrader && python -c "from app.main import check_for_updates; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add app/main.py
git commit -m "feat: add auto-update check on app startup"
```

---

## Task 6: main_window.py のバージョン表示を動的に

**Files:**
- Modify: `app/main_window.py:138-142`

**Step 1: バージョン表示を動的に変更**

`app/main_window.py` の139行目付近を変更:

```python
# Before:
version = QLabel("v1.0.0")

# After:
from app import __version__
version = QLabel(f"v{__version__}")
```

具体的には、ファイル先頭のimport部分に追加:
```python
from app import __version__
```

そして139行目を:
```python
version = QLabel(f"v{__version__}")
```

**Step 2: 動作確認**

Run: `cd /Users/Tsubasa/Developer/IntegratedWritingGrader && python -c "from app.main_window import MainWindow; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add app/main_window.py
git commit -m "refactor: show dynamic version in sidebar"
```

---

## Task 7: 統合テスト（手動）

**Step 1: アプリを起動して動作確認**

Run: `cd /Users/Tsubasa/Developer/IntegratedWritingGrader && python -m app.main`

確認事項:
- [ ] アプリが正常に起動する
- [ ] サイドバーにバージョンが表示される
- [ ] 1秒後にアップデートチェックが実行される（ログで確認）
- [ ] 現在リリースがないのでダイアログは表示されない

**Step 2: 全ての変更をコミット確認**

Run: `git log --oneline -10`

Expected commits:
- refactor: show dynamic version in sidebar
- feat: add auto-update check on app startup
- feat: add UpdateDialog for auto-update UI
- feat: add UpdateChecker class for auto-update functionality
- ci: add GitHub Actions workflow for automated releases
- refactor: read version from app/__init__.py in setup.py

---

## リリース手順（将来）

新しいバージョンをリリースするとき:

```bash
# 1. バージョンを更新
# app/__init__.py の __version__ を "1.1.0" に変更

# 2. コミット
git add app/__init__.py
git commit -m "chore: bump version to 1.1.0"

# 3. タグを作成してpush
git tag v1.1.0
git push origin main --tags

# 4. GitHub Actionsが自動でビルド＆Release作成
```
