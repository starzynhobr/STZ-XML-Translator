import json
import re
import tomllib
from pathlib import Path

import core.version as version_module
from core.version import _build_script_version, app_version

ROOT = Path(__file__).resolve().parents[1]


def test_canonical_build_version_is_1_5_0():
    assert _build_script_version(ROOT / "build_nuitka.bat") == (1, 5, 0, 0)
    assert app_version() == "1.5.0"


def test_nuitka_output_reads_version_from_windows_executable(monkeypatch):
    monkeypatch.setattr(
        version_module.sys,
        "executable",
        r"C:\Program Files\STZ XML Translator\STZXMLTranslator.exe",
    )
    monkeypatch.setattr(
        version_module,
        "_EMBEDDED_BUILD_VERSION",
        "1.4.0.0",
    )
    monkeypatch.setattr(
        version_module,
        "_windows_executable_version",
        lambda path: (_ for _ in ()).throw(AssertionError("fallback should not run")),
    )

    assert version_module.app_version() == "1.4.0"


def test_packaged_version_falls_back_to_windows_resource(monkeypatch):
    monkeypatch.setattr(
        version_module.sys,
        "executable",
        r"C:\Program Files\STZ XML Translator\STZXMLTranslator.exe",
    )
    monkeypatch.setattr(version_module, "_EMBEDDED_BUILD_VERSION", None)
    monkeypatch.setattr(
        version_module,
        "_windows_executable_version",
        lambda path: (1, 4, 0, 0),
    )

    assert version_module.app_version() == "1.4.0"


def test_project_metadata_matches_canonical_version():
    with open(ROOT / "pyproject.toml", "rb") as file:
        project_version = tomllib.load(file)["project"]["version"]

    assert project_version == app_version()


def test_ui_titles_get_version_from_viewmodel():
    for qml_name in ("main.qml", "ModernMain.qml"):
        qml = (ROOT / "ui" / qml_name).read_text(encoding="utf-8")
        assert "vm.appVersion" in qml

    for locale_file in (ROOT / "locales").glob("*.json"):
        title = json.loads(locale_file.read_text(encoding="utf-8"))["window_title"]
        assert not re.search(r"\bv?\d+\.\d+", title)


def test_release_workflow_enforces_tag_and_package_version():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "build_nuitka.bat" in workflow
    assert "does not match canonical version" in workflow
    assert "pyproject.toml version" in workflow
    assert "STZXMLTranslator-Setup-$env:VERSION.exe" in workflow
    assert "STZXMLTranslator-Portable-$env:VERSION.zip" in workflow
    assert "build-msix.ps1" not in workflow
