"""アプリ自動更新機能"""

from __future__ import annotations

import json
import logging
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
