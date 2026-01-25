"""アプリ自動更新機能"""

from __future__ import annotations

import json
import logging
import shlex
import shutil
import ssl
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import certifi

from app import __version__

# SSL context with certifi certificates
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

logger = logging.getLogger(__name__)

GITHUB_REPO = "sky-wing1/IntegratedWritingGrader"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
APP_INSTALL_PATH = Path("/Applications/IntegratedWritingGrader.app")

# Security: Allowed download hosts for update files
ALLOWED_DOWNLOAD_HOSTS = {"github.com", "objects.githubusercontent.com"}


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
            with urlopen(request, timeout=10, context=SSL_CONTEXT) as response:
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

    def _validate_download_url(self, url: str) -> bool:
        """Validate that download URL is from trusted GitHub domain"""
        parsed = urlparse(url)
        return parsed.scheme == "https" and parsed.netloc in ALLOWED_DOWNLOAD_HOSTS

    def _safe_extract(self, zip_path: Path, extract_dir: Path) -> None:
        """Safely extract ZIP file, preventing path traversal (Zip Slip)"""
        extract_dir_resolved = extract_dir.resolve()
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                target_path = (extract_dir / member).resolve()
                if not str(target_path).startswith(str(extract_dir_resolved)):
                    raise ValueError(f"Attempted path traversal in ZIP: {member}")
            zf.extractall(extract_dir)

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

        Raises:
            ValueError: If download URL is from untrusted domain
        """
        # Security: Validate download URL is from trusted domain
        if not self._validate_download_url(release.download_url):
            raise ValueError(f"Untrusted download URL: {release.download_url}")

        temp_dir = Path(tempfile.mkdtemp())
        zip_path = temp_dir / f"IntegratedWritingGrader-v{release.version}.zip"

        request = Request(release.download_url)
        with urlopen(request, timeout=60, context=SSL_CONTEXT) as response:
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
            # ZIP解凍（安全な解凍でパストラバーサル攻撃を防止）
            self._safe_extract(zip_path, extract_dir)

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
                    # Security: Use shlex.quote() to prevent shell injection
                    script = f'''
                    do shell script "rm -rf {shlex.quote(str(APP_INSTALL_PATH))} && cp -R {shlex.quote(str(app_path))} {shlex.quote(str(APP_INSTALL_PATH))}" with administrator privileges
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
