import json
import os
import shutil
from unittest.mock import MagicMock, patch

import pytest

from core.app_controller import TRANSLATION_TARGETS, AppController
from core.extrator import indexar_xml
from core.project import TranslationProject

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

    @pytest.mark.parametrize(
        ("locale", "code", "deepl", "label"),
        [
            ("it_IT", "it", "IT", "Italian"),
            ("ru_RU", "ru", "RU", "Russian"),
            ("da_DK", "da", "DA", "Danish"),
            ("tr_TR", "tr", "TR", "Turkish"),
        ],
    )
    def test_requested_translation_targets(self, ctrl, locale, code, deepl, label):
        assert ctrl.resolve_translation_target(locale) == {
            "code": code,
            "deepl": deepl,
            "label": label,
            "display": TRANSLATION_TARGETS[code]["display"],
            "locale": locale,
        }

    def test_available_targets_are_independent_from_ui_locales(self, ctrl):
        targets = ctrl.available_translation_targets()

        assert targets["Italiano"] == "it_IT"
        assert targets["Русский"] == "ru_RU"
        assert targets["Dansk"] == "da_DK"
        assert targets["Türkçe"] == "tr_TR"
        assert set(targets.values()) > set(ctrl.available_locales().values())


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

    def test_preview_tag_selection_does_not_mutate_project(self, ctrl):
        preview = ctrl.preview_tag_selection(
            FIXTURE_XML,
            "item",
            ["dispName", "description"],
            ["id"],
        )

        assert preview == {"records": 3, "lines": 6}
        assert ctrl.project.xml_path == ""
        assert ctrl.project.entries == {}

    def test_preview_without_parent_preserves_legacy_scope(self, ctrl):
        preview = ctrl.preview_tag_selection(FIXTURE_XML, "", ["dispName"])

        assert preview == {"records": 3, "lines": 3}

    def test_structure_preview_and_extraction_reuse_one_document_index(self, ctrl):
        with patch("core.app_controller.indexar_xml", wraps=indexar_xml) as build_index:
            assert "item" in ctrl.get_parent_tags(FIXTURE_XML)
            assert "dispName" in ctrl.get_child_tags(FIXTURE_XML, "item")
            assert ctrl.preview_tag_selection(FIXTURE_XML, "item", ["dispName"])["lines"] == 3
            success, entries = ctrl.extract_xml_entries(FIXTURE_XML, "item", ["dispName"])

        assert success is True
        assert len(entries) == 3
        assert build_index.call_count == 1

    def test_document_index_is_invalidated_when_file_changes(self, ctrl, tmp_path):
        xml_path = tmp_path / "sample.xml"
        shutil.copy2(FIXTURE_XML, xml_path)

        with patch("core.app_controller.indexar_xml", wraps=indexar_xml) as build_index:
            ctrl.get_parent_tags(str(xml_path))
            xml_path.write_text(
                xml_path.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            ctrl.get_parent_tags(str(xml_path))

        assert build_index.call_count == 2


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

    def test_includes_legacy_checkpoint_fallbacks_for_loaded_project(self, ctrl):
        ctrl.load_xml(FIXTURE_XML, "item", ["dispName"], ["id"])

        config = ctrl.build_translation_config("", {})

        legacy = TranslationProject.checkpoint_path(
            FIXTURE_XML,
            ctrl.translation_target["code"],
            config["checkpoint_dir"],
        )
        assert legacy in config["checkpoint_fallbacks"]


class TestCheckpointMigration:
    def test_restores_legacy_checkpoint_when_current_is_missing(self, ctrl):
        ctrl.load_xml(FIXTURE_XML, "item", ["dispName"], ["id"])
        xpath = next(iter(ctrl.project.entries))
        legacy = ctrl.legacy_checkpoint_path_for(FIXTURE_XML)
        os.makedirs(os.path.dirname(legacy), exist_ok=True)
        with open(legacy, "w", encoding="utf-8") as file:
            json.dump({xpath: "Do legado"}, file)

        restored = ctrl.restore_checkpoint_for(FIXTURE_XML)

        assert restored == 1
        assert ctrl.project.entries[xpath].translation == "Do legado"

    def test_current_checkpoint_takes_precedence_over_legacy(self, ctrl):
        ctrl.load_xml(FIXTURE_XML, "item", ["dispName"], ["id"])
        xpath = next(iter(ctrl.project.entries))
        current = ctrl.checkpoint_path_for(FIXTURE_XML)
        legacy = ctrl.legacy_checkpoint_path_for(FIXTURE_XML)
        os.makedirs(os.path.dirname(current), exist_ok=True)
        with open(current, "w", encoding="utf-8") as file:
            json.dump({xpath: "Atual"}, file)
        with open(legacy, "w", encoding="utf-8") as file:
            json.dump({xpath: "Legado"}, file)

        restored = ctrl.restore_checkpoint_for(FIXTURE_XML)

        assert restored == 1
        assert ctrl.project.entries[xpath].translation == "Atual"

    def test_clear_checkpoint_removes_current_and_legacy_files(self, ctrl):
        ctrl.load_xml(FIXTURE_XML, "item", ["dispName"], ["id"])
        current = ctrl.checkpoint_path_for(FIXTURE_XML)
        legacy = ctrl.legacy_checkpoint_path_for(FIXTURE_XML)
        os.makedirs(os.path.dirname(current), exist_ok=True)
        for path in (current, legacy):
            with open(path, "w", encoding="utf-8") as file:
                json.dump({}, file)

        ctrl.clear_checkpoint()

        assert not os.path.exists(current)
        assert not os.path.exists(legacy)


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

    def test_update_preferences_roundtrip_without_losing_other_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ctrl = AppController()
        ctrl.save_config(api_key="key", model_label="Model", model_id="models/test")
        ctrl.save_update_preferences(last_check=1234.5, skipped_version="1.5.0")

        restored = AppController()

        assert restored.last_update_check == 1234.5
        assert restored.skipped_update_version == "1.5.0"
        assert restored.api_key == "key"
        assert restored.preferred_model_id == "models/test"


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


class TestPreferredUiMode:
    def test_default_ui_mode_is_modern(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ctrl = AppController()
        assert ctrl.preferred_ui_mode == "modern"

    def test_save_preferred_ui_mode_persists(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ctrl1 = AppController()
        ctrl1.save_preferred_ui_mode("modern")

        ctrl2 = AppController()
        assert ctrl2.preferred_ui_mode == "modern"

    def test_saved_classic_ui_is_preserved(self, tmp_path, monkeypatch):
        import json

        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.json").write_text(
            json.dumps({"ui_mode": "classic"}), encoding="utf-8"
        )
        assert AppController().preferred_ui_mode == "classic"

    def test_invalid_saved_ui_mode_falls_back_to_modern(self, tmp_path, monkeypatch):
        import json

        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.json").write_text(
            json.dumps({"ui_mode": "unknown"}), encoding="utf-8"
        )
        ctrl = AppController()
        assert ctrl.preferred_ui_mode == "modern"

    def test_invalid_ui_mode_is_not_persisted(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ctrl = AppController()
        ctrl.save_preferred_ui_mode("unknown")
        assert ctrl.preferred_ui_mode == "modern"


class TestTagPresetPersistence:
    def test_get_presets_normalizes_legacy_format_without_rewriting_file(
        self, tmp_path, monkeypatch
    ):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        path = data_dir / "tag_presets.json"
        legacy_content = (
            '{"presets":[{"id":1,"label":"Items","parent_tag":"item",'
            '"target_tag":"dispName","file":"items.xml"}]}'
        )
        path.write_text(legacy_content, encoding="utf-8")
        monkeypatch.setenv("STZ_XML_TRANSLATOR_DATA_DIR", str(data_dir))

        presets = AppController().get_tag_presets()

        assert presets[0]["target_tags"] == ["dispName"]
        assert presets[0]["context_tags"] == []
        assert presets[0]["target_tag"] == "dispName"
        assert path.read_text(encoding="utf-8") == legacy_content

    def test_save_legacy_single_target_writes_new_format(self, tmp_path, monkeypatch):
        data_dir = tmp_path / "data"
        monkeypatch.setenv("STZ_XML_TRANSLATOR_DATA_DIR", str(data_dir))
        ctrl = AppController()

        assert ctrl.save_tag_preset("Items", "item", "dispName", "items.xml")

        saved = json.loads((data_dir / "tag_presets.json").read_text(encoding="utf-8"))
        assert saved["presets"][0]["target_tags"] == ["dispName"]
        assert saved["presets"][0]["context_tags"] == []
        assert "target_tag" not in saved["presets"][0]

    def test_save_preset_accepts_multiple_targets_and_context(self, tmp_path, monkeypatch):
        data_dir = tmp_path / "data"
        monkeypatch.setenv("STZ_XML_TRANSLATOR_DATA_DIR", str(data_dir))
        ctrl = AppController()

        result = ctrl.save_tag_preset(
            "Villains",
            "baseVillain",
            ["bio", "description", "bio"],
            "villains.xml",
            "",
            ["dispName", "archetype", "dispName"],
        )

        assert result is True
        preset = ctrl.get_tag_presets()[0]
        assert preset["target_tags"] == ["bio", "description"]
        assert preset["context_tags"] == ["dispName", "archetype"]
        assert preset["target_tag"] == "bio"

    def test_save_preset_rejects_target_context_overlap(self, tmp_path, monkeypatch):
        data_dir = tmp_path / "data"
        monkeypatch.setenv("STZ_XML_TRANSLATOR_DATA_DIR", str(data_dir))

        result = AppController().save_tag_preset(
            "Invalid",
            "item",
            ["description"],
            context_tags=["description"],
        )

        assert result is False
        assert not (data_dir / "tag_presets.json").exists()

    def test_import_deduplicates_equivalent_legacy_and_new_presets(
        self, tmp_path, monkeypatch
    ):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "tag_presets.json").write_text(
            '{"presets":[{"id":1,"label":"Items","parent_tag":"item",'
            '"target_tag":"dispName"}]}',
            encoding="utf-8",
        )
        source = tmp_path / "presets.json"
        source.write_text(
            '{"presets":[{"label":"Items","parent_tag":"item",'
            '"target_tags":["dispName"],"context_tags":[]}]}',
            encoding="utf-8",
        )
        monkeypatch.setenv("STZ_XML_TRANSLATOR_DATA_DIR", str(data_dir))

        imported, skipped = AppController().import_presets(str(source))

        assert (imported, skipped) == (0, 1)
        assert json.loads((data_dir / "tag_presets.json").read_text(encoding="utf-8"))[
            "presets"
        ][0]["target_tag"] == "dispName"

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
