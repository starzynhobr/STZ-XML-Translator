import json
from unittest.mock import Mock, patch

import pytest

from core.project import EntryStatus, TranslationEntry, TranslationProject
from core.translation_worker import TranslationWorker


@pytest.fixture
def project():
    project = TranslationProject()
    project.entries = {"/a": TranslationEntry("/a", "Hello")}
    return project


def test_legacy_done_does_not_imply_review():
    assert TranslationEntry("/a", "Hello", "Olá", "done").status == "translated"


def test_edit_invalidates_confirmation_and_empty_text_resets(project):
    project.set_translation("/a", "Olá")
    assert project.confirm_translation("/a")
    assert project.entries["/a"].status == "confirmed"
    project.set_translation("/a", "Oi")
    assert project.entries["/a"].status == "translated"
    project.set_translation("/a", "  ")
    assert project.entries["/a"].status == "pending"
    assert not project.confirm_translation("/a")


def test_cannot_confirm_in_flight(project):
    project.mark_translating("/a")
    assert not project.confirm_translation("/a", "Olá")


@pytest.mark.parametrize("state", list(EntryStatus))
def test_pending_selection_and_counts(project, state):
    project.entries["/a"] = TranslationEntry("/a", "Hello", "Olá", state)
    assert bool(project.get_pending_entries()) == (state in (EntryStatus.PENDING, EntryStatus.ERROR))
    assert project.state_counts()[state] == 1
    assert sum(project.state_counts().values()) == 1
    assert project.stats()[0] == (state in (EntryStatus.TRANSLATED, EntryStatus.CONFIRMED))


def test_invalid_state_is_atomic(project):
    with pytest.raises(ValueError):
        project.set_translation("/a", "lost", "unknown")
    assert project.entries["/a"].translation == ""


def test_checkpoint_preserves_review_and_recovers_inflight(project, tmp_path):
    project.confirm_translation("/a", "Olá")
    project.entries["/b"] = TranslationEntry("/b", "B", status="translating")
    project.entries["/c"] = TranslationEntry("/c", "C", "Anterior", "translating")
    project.entries["/d"] = TranslationEntry("/d", "D", status="error")
    path = str(tmp_path / "checkpoint.json")
    assert project.save_checkpoint(path)
    restored = TranslationProject()
    restored.entries = {key: TranslationEntry(key, entry.original) for key, entry in project.entries.items()}
    assert restored.load_checkpoint(path) == 2
    assert [e.status for e in restored.entries.values()] == ["confirmed", "pending", "translated", "error"]


def test_legacy_checkpoint_is_translated_not_confirmed(project, tmp_path):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"/a": "Olá"}), encoding="utf-8")
    assert project.load_checkpoint(str(path)) == 1
    assert project.entries["/a"].status == "translated"


@pytest.mark.parametrize("data", [[], {"version": 999}, {"version": 2, "entries": []}, {"/a": 42}])
def test_invalid_checkpoint_is_ignored(project, tmp_path, data):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert project.load_checkpoint(str(path)) == 0
    assert project.entries["/a"].status == "pending"


def make_worker(project, tmp_path, service="Gemini"):
    return TranslationWorker(project, {"service": service, "checkpoint_dir": str(tmp_path)},
                             lambda *_: None, lambda _: None, Mock())


def test_single_api_error_keeps_previous_translation(project, tmp_path):
    project.confirm_translation("/a", "Anterior")
    worker = make_worker(project, tmp_path)
    with patch("core.translation_worker.translate_text", side_effect=RuntimeError("test error")):
        result = worker.translate_single("/a")
        assert result == project.entries["/a"].error_message
        assert "test error" not in result
    assert project.entries["/a"].status == "error"
    assert project.get_translations_map() == {"/a": "Anterior"}


@pytest.mark.parametrize("result", [None, {}])
def test_batch_failed_or_missing_result_marks_error(project, tmp_path, result):
    worker = make_worker(project, tmp_path)
    with patch.object(worker, "_translate_batch_gemini", return_value=result):
        worker._run()
    assert project.entries["/a"].status == "error"
    assert project.get_translations_map() == {}
    worker._on_done.assert_called_once()


def test_cancelled_response_is_kept_and_does_not_leave_translating(project, tmp_path):
    # The answer of a request already in flight was paid for: cancelling stops
    # the next batch but keeps what arrived.
    worker = make_worker(project, tmp_path)
    def response(_):
        worker.cancel()
        return {"/a": "Late response"}
    with patch.object(worker, "_translate_batch_gemini", side_effect=response):
        worker._run()
    assert project.entries["/a"].status == "translated"
    assert project.entries["/a"].translation == "Late response"


def test_confirmed_entries_not_retranslated_by_pending_batch(project, tmp_path):
    project.confirm_translation("/a", "Olá")
    worker = make_worker(project, tmp_path)
    with patch.object(worker, "_translate_batch_gemini") as api:
        worker._run()
    api.assert_not_called()
    assert project.entries["/a"].status == "confirmed"
