"""
Tests for locale file completeness.

Every locale file must have the exact same set of keys as every other locale file.
A missing key causes QML to fall back to the raw key string, which shows up as
untranslated text in the UI (e.g. "appearance_section_title" rendered literally).
"""

import json
import os
from pathlib import Path

import pytest

LOCALES_DIR = Path(__file__).parent.parent / "locales"
SUPPORTED = ["en_US", "pt_BR", "es_ES", "fr_FR", "ja_JP"]
REFERENCE_LOCALE = "en_US"


def _load(locale: str) -> dict:
    path = LOCALES_DIR / f"{locale}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def all_locales() -> dict[str, dict]:
    return {locale: _load(locale) for locale in SUPPORTED}


@pytest.fixture(scope="module")
def reference_keys(all_locales) -> set[str]:
    return set(all_locales[REFERENCE_LOCALE].keys())


class TestLocaleFiles:
    def test_all_locale_files_exist(self):
        for locale in SUPPORTED:
            path = LOCALES_DIR / f"{locale}.json"
            assert path.exists(), f"Locale file missing: {path}"

    def test_locale_files_are_valid_json(self):
        for locale in SUPPORTED:
            path = LOCALES_DIR / f"{locale}.json"
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            assert isinstance(data, dict), f"{locale}.json should be a JSON object"

    @pytest.mark.parametrize("locale", SUPPORTED)
    def test_no_missing_keys(self, locale, all_locales, reference_keys):
        locale_keys = set(all_locales[locale].keys())
        missing = reference_keys - locale_keys
        assert not missing, (
            f"Locale '{locale}' is missing {len(missing)} key(s): {sorted(missing)}"
        )

    @pytest.mark.parametrize("locale", SUPPORTED)
    def test_no_extra_keys(self, locale, all_locales, reference_keys):
        locale_keys = set(all_locales[locale].keys())
        extra = locale_keys - reference_keys
        assert not extra, (
            f"Locale '{locale}' has {len(extra)} extra key(s) not in {REFERENCE_LOCALE}: "
            f"{sorted(extra)}"
        )

    @pytest.mark.parametrize("locale", SUPPORTED)
    def test_no_empty_values(self, locale, all_locales):
        for key, value in all_locales[locale].items():
            assert isinstance(value, str), f"[{locale}] '{key}' is not a string"
            assert value.strip() != "", f"[{locale}] '{key}' is empty"

    def test_appearance_keys_present_in_all_locales(self, all_locales):
        appearance_keys = ["appearance_section_title", "appearance_section_subtitle"]
        for locale, data in all_locales.items():
            for key in appearance_keys:
                assert key in data, f"[{locale}] Missing key: '{key}'"

    def test_language_name_key_present(self, all_locales):
        for locale, data in all_locales.items():
            assert "_language_name" in data, f"[{locale}] Missing '_language_name' key"
