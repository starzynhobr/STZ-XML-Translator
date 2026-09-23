import os
import threading
import time

import pytest
from PySide6.QtCore import QCoreApplication

from core.project import TranslationEntry
from ui.viewmodel import AppViewModel

FIXTURE_XML = os.path.join(os.path.dirname(__file__), "fixtures", "sample.xml")


def test_approve_persists_confirmed_state_and_preserves_other_entries(vm, tmp_path):
    vm._ctrl.project.xml_path = str(tmp_path / "example.xml")
    vm._ctrl.project.entries = {
        "/a": TranslationEntry("/a", "A", "AA", "translated"),
        "/b": TranslationEntry("/b", "B"),
    }
    vm._table.refresh_all(vm._ctrl.project.entries)
    vm.approveTranslation("/a", "Reviewed")
    assert vm._ctrl.project.entries["/a"].status == "confirmed"
    vm._ctrl.project.reset_translations()
    vm._ctrl.project.load_checkpoint(vm._ctrl.current_checkpoint_path())
    assert vm._ctrl.project.entries["/a"].status == "confirmed"
    assert vm._ctrl.project.entries["/b"].status == "pending"


def test_activity_does_not_replace_translation_with_placeholder(vm):
    entry = TranslationEntry("/a", "A", "Reviewed", "confirmed")
    vm._ctrl.project.entries = {"/a": entry}
    vm._table.refresh_all(vm._ctrl.project.entries)
    vm._ctrl.project.mark_translating("/a")
    vm._table.update_entry("/a", "…", "translating")
    assert entry.translation == "Reviewed"
    assert entry.status == "translating"


def test_review_updates_after_confirmation_and_error(vm):
    entry = TranslationEntry("/a", "A", "AA", "translated")
    vm._ctrl.project.entries = {"/a": entry}
    vm._table.refresh_all(vm._ctrl.project.entries)
    revision = vm.reviewRevision
    vm.approveTranslation("/a", "Reviewed")
    assert vm.entryReview("/a")["status"] == "confirmed"
    assert vm.reviewRevision > revision
    vm._ctrl.project.mark_error("/a", "network")
    vm._table.update_entry("/a", entry.translation, "error")
    assert vm.entryReview("/a") == {"status": "error", "error_code": "network"}
    assert vm.entryReview("missing") == {}


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


@pytest.fixture
def vm(tmp_path, monkeypatch) -> AppViewModel:
    monkeypatch.chdir(tmp_path)
    return AppViewModel()


def wait_for_xml_idle(vm: AppViewModel, timeout: float = 2.0) -> None:
    deadline = time.perf_counter() + timeout
    app = QCoreApplication.instance()
    while vm.isXmlBusy and time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    assert vm.isXmlBusy is False


def test_target_tags_are_ordered_and_deduplicated(vm):
    vm.addTargetTag("dispName")
    vm.addTargetTag(" description ")
    vm.addTargetTag("dispName")

    assert vm.selectedTargetTags == ["dispName", "description"]


def test_same_tag_cannot_be_target_and_context(vm):
    vm.addTargetTag("bio")
    vm.addContextTag("bio")
    vm.addContextTag("dispName")
    vm.addTargetTag("dispName")

    assert vm.selectedTargetTags == ["bio"]
    assert vm.selectedContextTags == ["dispName"]


def test_changing_parent_clears_child_tag_selection(vm):
    vm.addTargetTag("bio")
    vm.addContextTag("dispName")
    vm._pending_parent_tag = "character"

    vm.selectParentTag("item")

    assert vm.selectedTargetTags == []
    assert vm.selectedContextTags == []


def test_reload_uses_all_selected_target_and_context_tags(vm):
    vm._xml_path_selected = FIXTURE_XML
    vm.selectParentTag("item")
    vm.addTargetTag("dispName")
    vm.addTargetTag("description")
    vm.addContextTag("id")

    assert vm.tagPreviewRecords == 3
    assert vm.tagPreviewLines == 6

    vm.reloadXml()
    wait_for_xml_idle(vm)

    assert vm._ctrl.project.target_tags == ["dispName", "description"]
    assert vm._ctrl.project.context_tags == ["id"]
    assert len(vm._ctrl.project.entries) == 6


def test_reload_does_not_fall_back_to_a_removed_project_selection(vm):
    vm._xml_path_selected = FIXTURE_XML
    vm._pending_parent_tag = "item"
    vm._ctrl.project.target_tags = ["dispName"]

    vm.reloadXml()
    wait_for_xml_idle(vm)

    assert vm._ctrl.project.xml_path == ""
    assert vm._ctrl.project.entries == {}


def test_multi_preset_restores_target_and_context_tags(vm):
    vm.applyTagPresetMulti(
        "Personagens",
        "item",
        ["dispName", "description"],
        ["id"],
        "",
    )

    assert vm._pending_parent_tag == "item"
    assert vm.selectedTargetTags == ["dispName", "description"]
    assert vm.selectedContextTags == ["id"]


def test_table_model_exposes_source_tag_and_context(vm):
    vm._xml_path_selected = FIXTURE_XML
    vm.selectParentTag("item")
    vm.addTargetTag("description")
    vm.addContextTag("dispName")
    vm.reloadXml()
    wait_for_xml_idle(vm)

    index = vm.tableModel.index(0, 1)

    assert vm.tableModel.data(index, vm.tableModel.SourceTagRole) == "description"
    assert vm.tableModel.data(index, vm.tableModel.ContextRole) == {
        "dispName": "Hero of Light"
    }


def test_selecting_row_emits_entry_metadata(vm):
    vm._xml_path_selected = FIXTURE_XML
    vm.selectParentTag("item")
    vm.addTargetTag("description")
    vm.addContextTag("dispName")
    vm.reloadXml()
    wait_for_xml_idle(vm)
    selected = []
    vm.entryMetadataSelected.connect(lambda source_tag, context: selected.append((source_tag, context)))

    vm.selectRow(0)

    assert selected == [("description", {"dispName": "Hero of Light"})]


def test_selected_batch_translates_only_the_selected_rows(vm, monkeypatch):
    vm._ctrl.preferred_provider = "Google Translate (Free)"
    vm._ctrl.project.entries = {
        "/a": TranslationEntry("/a", "First"),
        "/b": TranslationEntry("/b", "Second"),
        "/c": TranslationEntry("/c", "Third"),
    }
    vm._table.refresh_all(vm._ctrl.project.entries)
    vm.selectRow(0)
    vm.setSelectedRows([0, 1])

    def run_selected(config, on_entry_translated, on_log, on_done, on_batch_start):
        del on_log
        assert config["selected_xpaths"] == ["/a", "/b"]
        assert config["include_done"] is True
        on_batch_start(config["selected_xpaths"])
        for xpath, text in (("/a", "Primeiro"), ("/b", "Segundo")):
            vm._ctrl.project.set_translation(xpath, text)
            on_entry_translated(xpath, text)
        on_done()

    monkeypatch.setattr(vm._ctrl, "start_batch_translation", run_selected)

    vm.translateSelected()

    assert vm._ctrl.project.entries["/a"].translation == "Primeiro"
    assert vm._ctrl.project.entries["/b"].translation == "Segundo"
    assert vm._ctrl.project.entries["/c"].translation == ""
    assert vm.isTranslating is False


def test_duplicate_action_updates_matching_unconfirmed_entries(vm):
    vm._ctrl.project.entries = {
        "/a": TranslationEntry("/a", "Same line"),
        "/b": TranslationEntry("/b", "Same line"),
        "/c": TranslationEntry("/c", "Same line", "Reviewed", "confirmed"),
        "/d": TranslationEntry("/d", "Same line!"),
    }
    vm._table.refresh_all(vm._ctrl.project.entries)

    vm.applyTranslationToDuplicates("/a", "Mesma linha")

    assert vm._ctrl.project.entries["/a"].translation == "Mesma linha"
    assert vm._ctrl.project.entries["/b"].translation == "Mesma linha"
    assert vm._ctrl.project.entries["/c"].translation == "Reviewed"
    assert vm._ctrl.project.entries["/d"].translation == ""


def test_duplicate_action_count_uses_edited_translation(vm):
    vm._ctrl.project.entries = {
        "/a": TranslationEntry("/a", "Same line", "Colaboração opcional", "done"),
        "/b": TranslationEntry("/b", "Same line", "Colaboração opcional", "done"),
    }

    assert vm.countDuplicateUpdates("/a", "Colaboração opcional") == 0
    assert vm.countDuplicateUpdates("/a", "Aliado opcional") == 1


def test_reload_extracts_outside_the_ui_thread(vm, monkeypatch):
    vm._xml_path_selected = FIXTURE_XML
    vm.selectParentTag("item")
    vm.addTargetTag("dispName")
    release_worker = threading.Event()
    original = vm._ctrl.extract_xml_entries

    def delayed_extract(*args, **kwargs):
        release_worker.wait(timeout=1)
        return original(*args, **kwargs)

    monkeypatch.setattr(vm._ctrl, "extract_xml_entries", delayed_extract)
    started = time.perf_counter()
    vm.reloadXml()
    elapsed = time.perf_counter() - started

    try:
        assert elapsed < 0.1
        assert vm.isXmlBusy is True
        assert vm._ctrl.project.entries == {}
    finally:
        release_worker.set()

    wait_for_xml_idle(vm)
    assert len(vm._ctrl.project.entries) == 3


def test_file_structure_analysis_runs_outside_the_ui_thread(vm, monkeypatch):
    release_worker = threading.Event()
    original = vm._ctrl.analyze_xml

    def delayed_analysis(*args, **kwargs):
        release_worker.wait(timeout=1)
        return original(*args, **kwargs)

    monkeypatch.setattr(vm._ctrl, "analyze_xml", delayed_analysis)
    monkeypatch.setattr(
        "ui.viewmodel.QFileDialog.getOpenFileName",
        lambda **_kwargs: (FIXTURE_XML, "XML Files (*.xml)"),
    )

    started = time.perf_counter()
    vm.loadXml("", "")
    elapsed = time.perf_counter() - started

    try:
        assert elapsed < 0.1
        assert vm.isXmlBusy is True
        assert vm.parentTags == []
    finally:
        release_worker.set()

    wait_for_xml_idle(vm)
    assert "item" in vm.parentTags
