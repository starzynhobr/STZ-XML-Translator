from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import requests

REPOSITORY = "StarzynhoBR/STZ-XML-Translator"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
RELEASE_DOWNLOAD_PREFIX = f"https://github.com/{REPOSITORY}/releases/download/"
INSTALLER_TEMPLATE = "STZXMLTranslator-Setup-{version}.exe"
_SHA256_RE = re.compile(r"^sha256:([0-9a-fA-F]{64})$")


class UpdateError(RuntimeError):
    """Safe updater error identified by a localization key suffix."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    tag_name: str
    notes: str
    page_url: str
    installer_name: str
    download_url: str
    sha256: str
    size: int


def parse_version(value: str) -> tuple[int, int, int]:
    normalized = value.strip().removeprefix("v")
    parts = normalized.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise UpdateError("invalid_release")
    return int(parts[0]), int(parts[1]), int(parts[2])


def is_newer_version(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


def _request_headers() -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "STZ-XML-Translator-Updater",
    }


def fetch_latest_release(
    current_version: str,
    *,
    http=requests,
    timeout: int = 12,
) -> ReleaseInfo | None:
    """Return the latest compatible release, or None when already current."""
    try:
        response = http.get(LATEST_RELEASE_URL, headers=_request_headers(), timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError, TypeError) as exc:
        raise UpdateError("network") from exc

    if not isinstance(payload, dict) or payload.get("draft") or payload.get("prerelease"):
        raise UpdateError("invalid_release")

    tag_name = str(payload.get("tag_name", ""))
    try:
        candidate_parts = parse_version(tag_name)
    except UpdateError as exc:
        raise UpdateError("invalid_release") from exc
    version = ".".join(str(part) for part in candidate_parts)
    if not is_newer_version(version, current_version):
        return None

    installer_name = INSTALLER_TEMPLATE.format(version=version)
    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise UpdateError("installer_missing")
    asset = next(
        (item for item in assets if isinstance(item, dict) and item.get("name") == installer_name),
        None,
    )
    if asset is None:
        raise UpdateError("installer_missing")

    download_url = str(asset.get("browser_download_url", ""))
    # GitHub canonicalizes repository owners in asset URLs and may change only
    # their letter casing. URL paths are otherwise kept exact.
    if not download_url.casefold().startswith(RELEASE_DOWNLOAD_PREFIX.casefold()):
        raise UpdateError("invalid_release")
    digest_match = _SHA256_RE.fullmatch(str(asset.get("digest", "")))
    if not digest_match:
        raise UpdateError("checksum_missing")

    try:
        size = max(0, int(asset.get("size", 0)))
    except (TypeError, ValueError) as exc:
        raise UpdateError("invalid_release") from exc

    return ReleaseInfo(
        version=version,
        tag_name=tag_name,
        notes=str(payload.get("body", "")),
        page_url=str(payload.get("html_url", "")),
        installer_name=installer_name,
        download_url=download_url,
        sha256=digest_match.group(1).lower(),
        size=size,
    )


def download_release(
    release: ReleaseInfo,
    *,
    destination_dir: str | Path | None = None,
    progress: Callable[[int], None] | None = None,
    http=requests,
    timeout: tuple[int, int] = (12, 120),
) -> str:
    """Download an installer atomically and verify its GitHub SHA-256 digest."""
    target_dir = Path(destination_dir or Path(tempfile.gettempdir()) / "STZXMLTranslatorUpdates")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / release.installer_name
    partial = target.with_suffix(target.suffix + ".part")
    digest = hashlib.sha256()
    downloaded = 0

    try:
        response = http.get(
            release.download_url,
            headers={"User-Agent": "STZ-XML-Translator-Updater"},
            stream=True,
            timeout=timeout,
        )
        response.raise_for_status()
        total = release.size or int(response.headers.get("Content-Length", 0) or 0)
        with partial.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                output.write(chunk)
                digest.update(chunk)
                downloaded += len(chunk)
                if progress and total > 0:
                    progress(min(99, int(downloaded * 100 / total)))
        if release.size and downloaded != release.size:
            raise UpdateError("download_incomplete")
        if digest.hexdigest().lower() != release.sha256:
            raise UpdateError("integrity")
        os.replace(partial, target)
        if progress:
            progress(100)
        return str(target)
    except UpdateError:
        partial.unlink(missing_ok=True)
        raise
    except (OSError, requests.RequestException, ValueError) as exc:
        partial.unlink(missing_ok=True)
        raise UpdateError("download") from exc


def launch_installer(path: str) -> bool:
    installer = Path(path)
    if not installer.is_file() or installer.suffix.lower() != ".exe":
        return False
    try:
        # The app kills the engine's whole process tree on exit, which took the
        # installer with it. Going through `start` leaves the installer with no
        # living parent, so it survives that kill.
        subprocess.run(
            ["cmd.exe", "/c", "start", "", str(installer)],
            check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return True
