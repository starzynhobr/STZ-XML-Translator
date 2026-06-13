import os
from unittest.mock import MagicMock, patch

import pytest

from core.app_controller import TRANSLATION_TARGETS, AppController

FIXTURE_XML = os.path.join(os.path.dirname(__file__), "fixtures", "sample.xml")


@pytest.fixture
def ctrl(tmp_path, monkeypatch) -> AppController:
    monkeypatch.chdir(tmp_path)
    return AppController()


class TestResolveTranslationTarget:
    def test_known_locale(self, ctrl):
        target = ctrl.resolve_translation_target("pt_BR")
        assert target["code"] == "pt"
        assert target["label"] == "Portuguese (Brazil)"

    def test_english_locale(self, ctrl):
        target = ctrl.resolve_translation_target("en_US")
        assert target["code"] == "en"

    def test_unknown_locale_fallback(self, ctrl):
        target = ctrl.resolve_translation_target("zz_ZZ")
        assert target["code"] == "zz"

    def test_all_known_locales_resolve(self, ctrl):
        for code in TRANSLATION_TARGETS:
            target = ctrl.resolve_translation_target(code)
            assert "code" in target
            assert "label" in target
            assert "deepl" in target


class TestAvailableLocales:
    def test_returns_dict(self, ctrl):
        locales = ctrl.available_locales()
        assert isinstance(locales, dict)

    def test_pt_br_present(self, ctrl):
        locales = ctrl.available_locales()
        assert "pt_BR" in locales.values()

    def test_friendly_names_are_strings(self, ctrl):
        for name, code in ctrl.available_locales().items():
            assert isinstance(name, str)
            assert isinstance(code, str)


class TestLoadXml:
    def test_load_valid_xml(self, ctrl):
        sucesso, err = ctrl.load_xml(FIXTURE_XML, "item", "dispName")
        assert sucesso is True
        assert err == ""
        assert len(ctrl.project.entries) == 3

    def test_load_invalid_path(self, ctrl):
        sucesso, err = ctrl.load_xml("/nonexistent/file.xml", "item", "dispName")
        assert sucesso is False
        assert isinstance(err, str)


class TestBuildTranslationConfig:
    def test_includes_all_required_keys(self, ctrl):
        ctrl.api_key = "test-key"
        models = {"Gemini 1.5 Flash": ("gemini-1.5-flash", 5)}
        config = ctrl.build_translation_config("Gemini 1.5 Flash", models)
        assert "api_key" in config
        assert "model" in config
        assert "target_lang" in config
        assert "target_label" in config
        assert "source_label" in config

    def test_uses_api_key(self, ctrl):
        ctrl.api_key = "my-key"
        config = ctrl.build_translation_config("", {})
        assert config["api_key"] == "my-key"

    def test_falls_back_to_preferred_model_id(self, ctrl):
        ctrl.preferred_model_id = "gemini-1.5-flash"
        config = ctrl.build_translation_config("unknown-label", {})
        assert config["model"] == "gemini-1.5-flash"


class TestTranslationLifecycle:
    def test_is_translating_false_initially(self, ctrl):
        assert ctrl.is_translating() is False

    def test_cancel_does_not_raise_when_no_worker(self, ctrl):
        ctrl.cancel_translation()  # should not raise

    def test_start_batch_creates_worker_and_runs(self, ctrl):
        ctrl.load_xml(FIXTURE_XML, "item", "dispName")
        log_msgs: list[str] = []
        done_called: list[bool] = []

        # We mock get_gemini_model to avoid real API call
        mock_model = MagicMock()
        mock_model.generate_content.return_value = MagicMock(text="[ID: /x]\nTranslated\n---")

        import threading

        done_event = threading.Event()

        def on_done():
            done_called.append(True)
            done_event.set()

        with patch("core.translation_worker.get_gemini_model", return_value=mock_model):
            ctrl.start_batch_translation(
                config={"api_key": "fake", "model": "gemini-1.5-flash", "target_label": "PT"},
                on_entry_translated=lambda *_: None,
                on_log=lambda m: log_msgs.append(m),
                on_done=on_done,
            )
            assert ctrl.is_translating() is True
            done_event.wait(timeout=10)

        assert done_called


class TestConfigPersistence:
    def test_save_and_reload_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ctrl1 = AppController()
        ctrl1.save_config(api_key="abc123", model_label="Gemini Flash", model_id="gemini-1.5-flash")

        ctrl2 = AppController()
        assert ctrl2.api_key == "abc123"
        assert ctrl2.preferred_model_id == "gemini-1.5-flash"
        assert ctrl2.preferred_model_label == "Gemini Flash"

    def test_save_config_creates_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ctrl = AppController()
        ctrl.save_config(api_key="key", model_label="lbl", model_id="mid")
        assert (tmp_path / "config.json").exists()


class TestPreferredTheme:
    def test_default_theme_is_windows_fluent(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ctrl = AppController()
        assert ctrl.preferred_theme == "Windows Fluent"

    def test_save_preferred_theme_persists(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ctrl1 = AppController()
        ctrl1.save_preferred_theme("Cool Tint")

        ctrl2 = AppController()
        assert ctrl2.preferred_theme == "Cool Tint"

    def test_save_preferred_theme_updates_in_memory(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ctrl = AppController()
        ctrl.save_preferred_theme("Neutral Deep")
        assert ctrl.preferred_theme == "Neutral Deep"

    def test_save_preferred_theme_preserves_api_key(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ctrl = AppController()
        ctrl.save_config(api_key="my-key", model_label="lbl", model_id="mid")
        ctrl.save_preferred_theme("Cool Tint")

        ctrl2 = AppController()
        assert ctrl2.api_key == "my-key"
        assert ctrl2.preferred_theme == "Cool Tint"

    def test_missing_theme_key_in_config_falls_back_to_default(self, tmp_path, monkeypatch):
        import json
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.json").write_text(
            json.dumps({"api_key": "k", "model_label": "l", "model_id": "m"})
        )
        ctrl = AppController()
        assert ctrl.preferred_theme == "Windows Fluent"


class TestTagPresetPersistence:
    def test_import_presets_uses_configured_user_data_dir(self, tmp_path, monkeypatch):
        data_dir = tmp_path / "data"
        source = tmp_path / "presets.json"
        source.write_text(
            """
            {
              "presets": [
                {
                  "label": "Items",
                  "parent_tag": "item",
                  "target_tag": "dispName",
                  "file": "items.xml"
                }
              ]
            }
            """,
            encoding="utf-8",
        )
        monkeypatch.setenv("STZ_XML_TRANSLATOR_DATA_DIR", str(data_dir))

        ctrl = AppController()
        imported, skipped = ctrl.import_presets(str(source))

        assert (imported, skipped) == (1, 0)
        assert (data_dir / "tag_presets.json").exists()
        assert ctrl.get_tag_presets()[0]["label"] == "Items"

    def test_import_presets_reports_write_failure(self, tmp_path, monkeypatch):
        source = tmp_path / "presets.json"
        source.write_text(
            '{"presets":[{"label":"Items","parent_tag":"item","target_tag":"dispName"}]}',
            encoding="utf-8",
        )
        ctrl = AppController()
        monkeypatch.setattr(ctrl, "_write_presets", lambda _presets: False)

        assert ctrl.import_presets(str(source)) == (-1, 0)
