import pytest

from core.i18n import I18nManager

SUPPORTED_LANGUAGES = ["pt_BR", "en_US", "es_ES", "fr_FR", "ja_JP"]
COMMON_KEYS = ["window_title", "load_xml_button", "translate_all_button", "export_button"]


class TestI18nManager:
    def test_default_language_is_pt_br(self):
        mgr = I18nManager()
        assert mgr.language == "pt_BR"

    def test_loads_all_supported_languages(self):
        for lang in SUPPORTED_LANGUAGES:
            mgr = I18nManager(language=lang)
            assert mgr.language == lang
            assert len(mgr.translations) > 0

    def test_returns_key_when_missing(self):
        mgr = I18nManager()
        result = mgr.get("this_key_does_not_exist_xyz")
        assert result == "this_key_does_not_exist_xyz"

    def test_common_keys_exist_in_all_languages(self):
        for lang in SUPPORTED_LANGUAGES:
            mgr = I18nManager(language=lang)
            for key in COMMON_KEYS:
                value = mgr.get(key)
                assert value != key, f"Key '{key}' not translated in {lang}"
                assert value.strip() != ""

    def test_string_formatting_works(self):
        mgr = I18nManager(language="pt_BR")
        result = mgr.get("stats_template", done=5, total=10)
        assert "5" in result
        assert "10" in result

    def test_fallback_to_english_on_unknown_language(self):
        mgr = I18nManager(language="zz_ZZ")
        assert mgr.language == "en_US"
        assert len(mgr.translations) > 0

    def test_load_language_switches_locale(self):
        mgr = I18nManager(language="pt_BR")
        pt_button = mgr.get("load_xml_button")
        mgr.load_language("en_US")
        en_button = mgr.get("load_xml_button")
        assert pt_button != en_button

    @pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
    def test_language_name_key_exists(self, lang):
        mgr = I18nManager(language=lang)
        name = mgr.get("_language_name")
        assert name != "_language_name"
