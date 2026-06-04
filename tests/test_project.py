import csv
import json
import os

import pytest

from core.project import TranslationEntry, TranslationProject

FIXTURE_XML = os.path.join(os.path.dirname(__file__), "fixtures", "sample.xml")


@pytest.fixture
def loaded_project() -> TranslationProject:
    p = TranslationProject()
    sucesso, _ = p.load(FIXTURE_XML, "item", "dispName")
    assert sucesso
    return p


class TestTranslationEntry:
    def test_default_status_is_pending(self):
        e = TranslationEntry(xpath="/root/item[1]/dispName[1]", original="Hello")
        assert e.status == "pending"
        assert e.translation == ""

    def test_dataclass_fields(self):
        e = TranslationEntry(xpath="/x", original="orig", translation="trans", status="done")
        assert e.xpath == "/x"
        assert e.original == "orig"
        assert e.translation == "trans"
        assert e.status == "done"


class TestTranslationProjectLoad:
    def test_load_populates_entries(self, loaded_project):
        assert len(loaded_project.entries) == 3  # 4th item has empty dispName

    def test_entries_are_TranslationEntry(self, loaded_project):
        for entry in loaded_project.entries.values():
            assert isinstance(entry, TranslationEntry)

    def test_xml_path_stored(self, loaded_project):
        assert loaded_project.xml_path == FIXTURE_XML

    def test_load_nonexistent_returns_false(self):
        p = TranslationProject()
        sucesso, err = p.load("/nonexistent/file.xml", "item", "dispName")
        assert sucesso is False
        assert isinstance(err, str)

    def test_reload_preserves_existing_translations(self, loaded_project):
        first_xpath = next(iter(loaded_project.entries))
        loaded_project.set_translation(first_xpath, "Herói da Luz")
        # Reload same file
        loaded_project.load(FIXTURE_XML, "item", "dispName")
        assert loaded_project.entries[first_xpath].translation == "Herói da Luz"
        assert loaded_project.entries[first_xpath].status == "done"


class TestTranslationProjectEntryAccess:
    def test_get_entry_exists(self, loaded_project):
        xpath = next(iter(loaded_project.entries))
        entry = loaded_project.get_entry(xpath)
        assert entry is not None
        assert isinstance(entry, TranslationEntry)

    def test_get_entry_missing_returns_none(self, loaded_project):
        assert loaded_project.get_entry("/nonexistent/xpath") is None

    def test_set_translation_updates_entry(self, loaded_project):
        xpath = next(iter(loaded_project.entries))
        loaded_project.set_translation(xpath, "Traduzido")
        entry = loaded_project.get_entry(xpath)
        assert entry.translation == "Traduzido"
        assert entry.status == "done"

    def test_set_translation_with_custom_status(self, loaded_project):
        xpath = next(iter(loaded_project.entries))
        loaded_project.set_translation(xpath, "...", status="translating")
        assert loaded_project.get_entry(xpath).status == "translating"

    def test_get_pending_entries_all_pending_initially(self, loaded_project):
        pending = loaded_project.get_pending_entries()
        assert len(pending) == len(loaded_project.entries)

    def test_get_pending_excludes_done(self, loaded_project):
        xpath = next(iter(loaded_project.entries))
        loaded_project.set_translation(xpath, "Done")
        pending = loaded_project.get_pending_entries()
        assert len(pending) == len(loaded_project.entries) - 1

    def test_get_translations_map_empty_initially(self, loaded_project):
        assert loaded_project.get_translations_map() == {}

    def test_get_translations_map_after_setting(self, loaded_project):
        xpaths = list(loaded_project.entries.keys())
        loaded_project.set_translation(xpaths[0], "Tradução A")
        loaded_project.set_translation(xpaths[1], "Tradução B")
        mapping = loaded_project.get_translations_map()
        assert len(mapping) == 2
        assert mapping[xpaths[0]] == "Tradução A"


class TestTranslationProjectStats:
    def test_stats_initial(self, loaded_project):
        done, total = loaded_project.stats()
        assert done == 0
        assert total == len(loaded_project.entries)

    def test_stats_after_translation(self, loaded_project):
        xpath = next(iter(loaded_project.entries))
        loaded_project.set_translation(xpath, "text")
        done, total = loaded_project.stats()
        assert done == 1
        assert total == len(loaded_project.entries)

    def test_empty_project_stats(self):
        p = TranslationProject()
        done, total = p.stats()
        assert done == 0
        assert total == 0


class TestCheckpoint:
    def test_save_and_load_checkpoint(self, tmp_path, loaded_project):
        xpaths = list(loaded_project.entries.keys())
        loaded_project.set_translation(xpaths[0], "Herói da Luz")
        loaded_project.set_translation(xpaths[1], "Ladrão das Sombras")

        ckpt = str(tmp_path / "ckpt.json")
        assert loaded_project.save_checkpoint(ckpt)

        # Create fresh project and load checkpoint
        p2 = TranslationProject()
        p2.load(FIXTURE_XML, "item", "dispName")
        count = p2.load_checkpoint(ckpt)

        assert count == 2
        assert p2.entries[xpaths[0]].translation == "Herói da Luz"
        assert p2.entries[xpaths[1]].status == "done"

    def test_load_nonexistent_checkpoint_returns_zero(self, loaded_project):
        count = loaded_project.load_checkpoint("/nonexistent/ckpt.json")
        assert count == 0

    def test_corrupted_checkpoint_returns_zero(self, tmp_path, loaded_project):
        bad = tmp_path / "bad.json"
        bad.write_text("not json {{{{", encoding="utf-8")
        assert loaded_project.load_checkpoint(str(bad)) == 0


class TestExport:
    def test_export_xml(self, tmp_path, loaded_project):
        xpath = next(iter(loaded_project.entries))
        loaded_project.set_translation(xpath, "Herói da Luz")
        out = str(tmp_path / "out.xml")
        assert loaded_project.export_xml(out)
        assert os.path.exists(out)

    def test_export_xml_no_translations_returns_false(self, loaded_project):
        assert loaded_project.export_xml("/tmp/whatever.xml") is False

    def test_export_xml_no_path_returns_false(self):
        p = TranslationProject()
        assert p.export_xml("/tmp/out.xml") is False

    def test_export_json(self, tmp_path, loaded_project):
        out = str(tmp_path / "originals.json")
        assert loaded_project.export_json(out)
        data = json.loads(open(out, encoding="utf-8").read())
        assert len(data) == len(loaded_project.entries)
        for v in data.values():
            assert isinstance(v, str) and v.strip()

    def test_export_csv(self, tmp_path, loaded_project):
        out = str(tmp_path / "export.csv")
        assert loaded_project.export_csv(out)
        rows = list(csv.DictReader(open(out, encoding="utf-8")))
        assert len(rows) == len(loaded_project.entries)
        assert "xpath" in rows[0]
        assert "original_text" in rows[0]
        assert "translated_text" in rows[0]


class TestImport:
    def test_import_json(self, tmp_path, loaded_project):
        xpaths = list(loaded_project.entries.keys())
        data = {xpaths[0]: "Herói", xpaths[1]: "Ladrão"}
        src = tmp_path / "tr.json"
        src.write_text(json.dumps(data), encoding="utf-8")
        count = loaded_project.import_json(str(src))
        assert count == 2
        assert loaded_project.entries[xpaths[0]].translation == "Herói"
        assert loaded_project.entries[xpaths[0]].status == "done"

    def test_import_json_unknown_xpaths_ignored(self, tmp_path, loaded_project):
        data = {"/nonexistent/xpath": "ghost"}
        src = tmp_path / "tr.json"
        src.write_text(json.dumps(data), encoding="utf-8")
        count = loaded_project.import_json(str(src))
        assert count == 0

    def test_import_json_invalid_file_returns_zero(self, loaded_project):
        assert loaded_project.import_json("/nonexistent.json") == 0

    def test_import_csv(self, tmp_path, loaded_project):
        xpaths = list(loaded_project.entries.keys())
        csv_path = tmp_path / "tr.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["xpath", "original_text", "translated_text"])
            w.writerow([xpaths[0], "original", "Herói"])
        count = loaded_project.import_csv(str(csv_path))
        assert count == 1
        assert loaded_project.entries[xpaths[0]].translation == "Herói"

    def test_import_csv_missing_file_returns_zero(self, loaded_project):
        assert loaded_project.import_csv("/nonexistent.csv") == 0

    def test_round_trip_json_export_import(self, tmp_path, loaded_project):
        """Export originals as JSON, simulate external translation, import back."""
        xpaths = list(loaded_project.entries.keys())
        export_path = str(tmp_path / "originals.json")
        loaded_project.export_json(export_path)

        # Simulate manual translation
        with open(export_path, encoding="utf-8") as f:
            originals = json.load(f)
        translated = {k: f"[PT] {v}" for k, v in originals.items()}
        translated_path = str(tmp_path / "translated.json")
        with open(translated_path, "w", encoding="utf-8") as f:
            json.dump(translated, f)

        count = loaded_project.import_json(translated_path)
        assert count == len(xpaths)
        done, total = loaded_project.stats()
        assert done == total
