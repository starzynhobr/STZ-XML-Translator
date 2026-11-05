import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from core.updater import (
    INSTALLER_TEMPLATE,
    ReleaseInfo,
    UpdateError,
    download_release,
    fetch_latest_release,
    is_newer_version,
    launch_installer,
    parse_version,
)


class FakeResponse:
    def __init__(self, *, payload=None, content: bytes = b"") -> None:
        self._payload = payload
        self._content = content
        self.headers = {"Content-Length": str(len(content))}

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload

    def iter_content(self, chunk_size: int):
        del chunk_size
        yield self._content[:3]
        yield self._content[3:]


class FakeHttp:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def release_payload(version: str = "1.5.0", content: bytes = b"setup") -> dict:
    name = INSTALLER_TEMPLATE.format(version=version)
    return {
        "tag_name": f"v{version}",
        "name": f"Version {version}",
        "body": "Release notes",
        "html_url": f"https://github.com/StarzynhoBR/STZ-XML-Translator/releases/tag/v{version}",
        "draft": False,
        "prerelease": False,
        "assets": [
            {
                "name": name,
                "browser_download_url": (
                    "https://github.com/StarzynhoBR/STZ-XML-Translator/"
                    f"releases/download/v{version}/{name}"
                ),
                "digest": f"sha256:{hashlib.sha256(content).hexdigest()}",
                "size": len(content),
            }
        ],
    }


@pytest.mark.parametrize(
    "candidate,current,expected",
    [("1.4.1", "1.4.0", True), ("2.0.0", "1.9.9", True), ("1.4.0", "1.4.0", False)],
)
def test_semantic_version_comparison(candidate, current, expected):
    assert is_newer_version(candidate, current) is expected


def test_parse_version_rejects_non_semantic_versions():
    with pytest.raises(UpdateError, match="invalid_release"):
        parse_version("1.4")


def test_latest_release_selects_exact_installer_and_digest():
    payload = release_payload()
    payload["assets"][0]["browser_download_url"] = payload["assets"][0][
        "browser_download_url"
    ].replace("StarzynhoBR", "starzynhobr")
    http = FakeHttp(FakeResponse(payload=payload))

    release = fetch_latest_release("1.4.0", http=http)

    assert release is not None
    assert release.version == "1.5.0"
    assert release.installer_name == "STZXMLTranslator-Setup-1.5.0.exe"
    assert len(release.sha256) == 64
    assert http.calls[0][1]["timeout"] == 12


def test_latest_release_rejects_asset_from_another_repository():
    payload = release_payload()
    payload["assets"][0]["browser_download_url"] = payload["assets"][0][
        "browser_download_url"
    ].replace("STZ-XML-Translator", "another-repository")

    with pytest.raises(UpdateError, match="invalid_release"):
        fetch_latest_release("1.4.0", http=FakeHttp(FakeResponse(payload=payload)))


def test_latest_release_returns_none_when_current_is_newer():
    http = FakeHttp(FakeResponse(payload=release_payload("1.3.0")))
    assert fetch_latest_release("1.4.0", http=http) is None


@pytest.mark.parametrize("field", ["digest", "browser_download_url"])
def test_latest_release_rejects_unverifiable_installer(field):
    payload = release_payload()
    payload["assets"][0][field] = ""
    with pytest.raises(UpdateError):
        fetch_latest_release("1.4.0", http=FakeHttp(FakeResponse(payload=payload)))


def test_download_is_atomic_and_hash_verified(tmp_path):
    content = b"valid installer bytes"
    payload = release_payload(content=content)
    info = fetch_latest_release("1.4.0", http=FakeHttp(FakeResponse(payload=payload)))
    progress = []

    path = download_release(
        info,
        destination_dir=tmp_path,
        progress=progress.append,
        http=FakeHttp(FakeResponse(content=content)),
    )

    assert Path(path).read_bytes() == content
    assert progress[-1] == 100
    assert not list(tmp_path.glob("*.part"))


def test_download_removes_partial_file_after_integrity_failure(tmp_path):
    payload = release_payload(content=b"expected")
    info = fetch_latest_release("1.4.0", http=FakeHttp(FakeResponse(payload=payload)))

    with pytest.raises(UpdateError, match="integrity"):
        download_release(
            info,
            destination_dir=tmp_path,
            http=FakeHttp(FakeResponse(content=b"tampered")),
        )

    assert not list(tmp_path.iterdir())


def test_launch_installer_detaches_from_the_engine_tree(tmp_path):
    installer = tmp_path / "setup.exe"
    installer.write_bytes(b"placeholder")
    with patch("core.updater.subprocess.run") as run:
        assert launch_installer(str(installer)) is True
    args = run.call_args.args[0]
    assert args[:4] == ["cmd.exe", "/c", "start", ""]
    assert args[4] == str(installer)


def test_launch_installer_rejects_missing_or_non_executable_files(tmp_path):
    assert launch_installer(str(tmp_path / "missing.exe")) is False
    text_file = tmp_path / "setup.txt"
    text_file.write_text("no")
    assert launch_installer(str(text_file)) is False
