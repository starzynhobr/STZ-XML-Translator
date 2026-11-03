"""Bulk Gemini translation: deduplication, sizing, pacing and the parallel run."""
from __future__ import annotations

import json
import threading
import time
from unittest.mock import patch

from core import gemini_batch
from core.project import TranslationEntry, TranslationProject
from core.translation_worker import TranslationWorker


def entries(*originals):
    return [TranslationEntry(f"/e[{i}]", text) for i, text in enumerate(originals, start=1)]


def test_dedupe_sends_each_text_once():
    units = gemini_batch.dedupe(entries("A.I.M. PISTOL", "Bio", "A.I.M. PISTOL", "Bio", "Other"))
    assert [(u.original, u.xpaths) for u in units] == [
        ("A.I.M. PISTOL", ["/e[1]", "/e[3]"]),
        ("Bio", ["/e[2]", "/e[4]"]),
        ("Other", ["/e[5]"]),
    ]


def test_pack_fills_requests_by_size():
    units = gemini_batch.dedupe(entries("x" * 50, "y" * 50, "z" * 50, "short"))
    chunks = gemini_batch.pack(units, max_chars=100, max_items=10)
    assert [[u.original[0] for u in chunk] for chunk in chunks] == [["x", "y"], ["z", "s"]]
    many = gemini_batch.dedupe(entries(*[f"n{i}" for i in range(7)]))
    assert [len(c) for c in gemini_batch.pack(many, max_chars=10_000, max_items=3)] == [3, 3, 1]


def test_rate_gate_spaces_requests_and_slows_down():
    now = [0.0]
    gate = gemini_batch.RateGate(60, clock=lambda: now[0], sleep=lambda s: now.__setitem__(0, now[0] + s))
    starts = []
    for _ in range(3):
        gate.wait()
        starts.append(round(now[0], 2))
    assert starts == [0.0, 1.0, 2.0]
    gate.slow_down(10)
    gate.wait()
    assert now[0] >= 12.0 and gate.interval == 2.0


def test_retry_after_reads_the_api_hint():
    assert gemini_batch.retry_after(RuntimeError("HTTP 429: quota. Please retry in 7.5s.")) == 10.0  # never under MIN_RATE_WAIT
    assert gemini_batch.retry_after(RuntimeError("HTTP 429: quota. Please retry in 31s.")) == 31.0
    assert gemini_batch.retry_after(RuntimeError("HTTP 429: You exceeded your current quota")) == 20.0
    assert gemini_batch.retry_after(RuntimeError("HTTP 503: overloaded")) is None
    daily = "HTTP 429: You exceeded your current quota [quota: GenerateRequestsPerDayPerProjectPerModel-FreeTier]"
    minute = "HTTP 429: You exceeded your current quota [quota: GenerateRequestsPerMinutePerProjectPerModel-FreeTier]"
    both = "HTTP 429: quota [quota: GenerateRequestsPerMinutePerProjectPerModel-FreeTier, GenerateRequestsPerDayPerProjectPerModel-FreeTier]"
    assert gemini_batch.daily_quota_exhausted(RuntimeError(daily))
    assert not gemini_batch.daily_quota_exhausted(RuntimeError(minute))
    assert not gemini_batch.daily_quota_exhausted(RuntimeError(both))  # the minute one may pass after a wait
    assert not gemini_batch.daily_quota_exhausted(RuntimeError("HTTP 429: You exceeded your current quota"))


def test_parse_accepts_wrapped_arrays():
    assert gemini_batch.parse('[{"id": "t1", "text": "Oi"}]') == {"t1": "Oi"}
    assert gemini_batch.parse('{"items": [{"id": "t2", "text": "Tchau"}]}') == {"t2": "Tchau"}


def make_worker(project, parallel=3):
    translated = []
    worker = TranslationWorker(
        project=project,
        config={"service": "Gemini", "api_key": "k", "gemini_parallel": parallel, "gemini_rpm": 6000},
        on_entry_translated=lambda xpath, _text: translated.append(xpath),
        on_log=lambda _m: None,
        on_done=lambda: None,
    )
    return worker, translated


def test_run_translates_duplicates_once_and_requests_in_parallel(monkeypatch):
    monkeypatch.setattr(gemini_batch, "MAX_ITEMS", 1)  # one text per request to observe the overlap
    project = TranslationProject()
    for entry in entries("One", "Two", "One", "Three", "Four"):
        project.entries[entry.xpath] = entry
    worker, translated = make_worker(project)
    in_flight, peak, sent = [0], [0], []
    lock = threading.Lock()

    def fake(batch):
        with lock:
            in_flight[0] += 1
            peak[0] = max(peak[0], in_flight[0])
            sent.extend(e.original for e in batch)
        time.sleep(0.05)
        with lock:
            in_flight[0] -= 1
        return {e.xpath: e.original.upper() for e in batch}

    with (
        patch.object(worker, "_translate_batch_gemini", side_effect=fake),
        patch.object(project, "save_checkpoint", return_value=True),
    ):
        worker._run()

    assert sorted(sent) == ["Four", "One", "Three", "Two"]  # "One" went once
    assert peak[0] > 1
    assert project.entries["/e[3]"].translation == "ONE"  # the copy got it too
    assert sorted(translated) == sorted(project.entries)
    assert all(e.status == "translated" for e in project.entries.values())


def test_a_failed_request_stops_the_rest_without_losing_finished_ones(monkeypatch):
    monkeypatch.setattr(gemini_batch, "MAX_ITEMS", 1)
    project = TranslationProject()
    for entry in entries("A", "B", "C", "D"):
        project.entries[entry.xpath] = entry
    worker, _ = make_worker(project, parallel=1)

    def fake(batch):
        if batch[0].original == "B":
            worker._local.error = "authentication"
            return None
        return {e.xpath: e.original.lower() for e in batch}

    with (
        patch.object(worker, "_translate_batch_gemini", side_effect=fake),
        patch.object(project, "save_checkpoint", return_value=True),
    ):
        worker._run()

    states = {e.original: (e.status, e.error_code) for e in project.entries.values()}
    assert states["A"][0] == "translated"
    assert states["B"] == ("error", "authentication")
    assert states["C"][0] == "pending" and states["D"][0] == "pending"  # never sent


def test_short_texts_are_only_shared_within_a_field():
    items = [
        TranslationEntry("/a", "Charge", source_tag="label"),
        TranslationEntry("/b", "Charge", source_tag="dispName"),
        TranslationEntry("/c", "Charge", source_tag="label"),
        TranslationEntry("/d", "A long sentence about the hero", source_tag="bio"),
        TranslationEntry("/e", "A long sentence about the hero", source_tag="cogBio"),
    ]
    units = gemini_batch.dedupe(items)
    assert [u.xpaths for u in units] == [["/a", "/c"], ["/b"], ["/d", "/e"]]


def test_names_are_found_in_texts():
    memory = {"Moondragon": "Dragão da Lua", "Hulk": "Hulk", "Al": "Al"}
    found = gemini_batch.names_in(["Heather became MOONDRAGON.", "Hulkbuster armor"], memory)
    assert found == [("Moondragon", "Dragão da Lua")]  # whole words only, never 2-letter names
    assert gemini_batch.is_name_field("dispName") and gemini_batch.is_name_field("cogName")
    assert not gemini_batch.is_name_field("className") and not gemini_batch.is_name_field("bio")


def test_names_go_first_and_guide_the_texts_that_mention_them():
    project = TranslationProject()
    for entry in (
        TranslationEntry("/v/bio", "Heather Douglas became Moondragon.", source_tag="bio"),
        TranslationEntry("/v/name", "Moondragon", source_tag="dispName"),
    ):
        project.entries[entry.xpath] = entry
    worker, _ = make_worker(project)
    prompts, order = [], []

    class Model:
        def generate_content(self, prompt, response_schema=None):
            prompts.append(prompt)
            items = json.loads(prompt.split("Items: ", 1)[1])
            order.extend(item["field"] for item in items)
            text = {"Moondragon": "Dragão da Lua", "Heather Douglas became Moondragon.": "Heather virou Dragão da Lua."}
            return type("R", (), {"text": json.dumps([{"id": i["id"], "text": text[i["text"]]} for i in items])})()

    with (
        patch("core.translation_worker.get_gemini_model", return_value=Model()),
        patch.object(project, "save_checkpoint", return_value=True),
    ):
        worker._run()

    assert order == ["dispName", "bio"]
    assert '"Moondragon" = "Dragão da Lua"' in prompts[1]
    assert project.entries["/v/bio"].translation == "Heather virou Dragão da Lua."


def test_quota_in_the_middle_then_resume(monkeypatch, tmp_path):
    """Finished requests are kept and saved; the next run sends only what is left."""
    monkeypatch.setattr(gemini_batch, "MAX_ITEMS", 1)
    project = TranslationProject()
    for entry in entries("A text", "B text", "C text", "D text"):
        project.entries[entry.xpath] = entry
    worker, _ = make_worker(project, parallel=1)
    saves = []

    def first_run(batch):
        if batch[0].original == "C text":
            worker._local.error = "rate_limit"
            return None
        return {e.xpath: e.original.upper() for e in batch}

    with (
        patch.object(worker, "_translate_batch_gemini", side_effect=first_run),
        patch.object(project, "save_checkpoint", side_effect=lambda _p: saves.append(1) or True),
    ):
        worker._run()
    assert [e.status for e in project.entries.values()] == ["translated", "translated", "error", "pending"]
    assert len(saves) == 4  # A, B and the failed C as each finished, then once more on the way out

    resumed, sent = make_worker(project, parallel=1)[0], []
    with (
        patch.object(resumed, "_translate_batch_gemini",
                     side_effect=lambda b: sent.extend(e.original for e in b) or {e.xpath: "ok" for e in b}),
        patch.object(project, "save_checkpoint", return_value=True),
    ):
        resumed._run()
    assert sorted(sent) == ["C text", "D text"]
    assert all(e.status == "translated" for e in project.entries.values())


def test_closing_the_app_mid_request_leaves_it_pending(tmp_path):
    """A request in flight when the app dies comes back as pending, never stuck "translating"."""
    project = TranslationProject()
    for entry in entries("Done", "In flight"):
        project.entries[entry.xpath] = entry
    project.set_translation("/e[1]", "Feito")
    project.mark_translating("/e[2]")
    checkpoint = tmp_path / "ck.json"
    project.save_checkpoint(str(checkpoint))  # what was on disk when the process died

    reopened = TranslationProject()
    for entry in entries("Done", "In flight"):
        reopened.entries[entry.xpath] = entry
    reopened.load_checkpoint(str(checkpoint))
    assert reopened.entries["/e[1]"].translation == "Feito"
    assert reopened.entries["/e[2]"].status == "pending"


def test_a_per_minute_limit_waits_and_carries_on(monkeypatch):
    monkeypatch.setattr(gemini_batch, "MIN_RATE_WAIT", 0.0)
    project = TranslationProject()
    for entry in entries("Sword", "Shield"):
        project.entries[entry.xpath] = entry
    worker, _ = make_worker(project, parallel=1)
    calls = []

    class Model:
        def generate_content(self, prompt, response_schema=None):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("Gemini API HTTP 429: quota exceeded. Please retry in 0.01s.")
            items = json.loads(prompt.split("Items: ", 1)[1])
            return type("R", (), {"text": json.dumps([{"id": i["id"], "text": "ok"} for i in items])})()

    with (
        patch("core.translation_worker.get_gemini_model", return_value=Model()),
        patch.object(project, "save_checkpoint", return_value=True),
    ):
        worker._run()
    assert len(calls) == 2
    assert all(e.status == "translated" for e in project.entries.values())


def test_a_spent_daily_quota_stops_with_its_own_error():
    project = TranslationProject()
    for entry in entries("Sword"):
        project.entries[entry.xpath] = entry
    worker, _ = make_worker(project, parallel=1)

    class Model:
        def generate_content(self, prompt, response_schema=None):
            raise RuntimeError("HTTP 429: quota [quota: GenerateRequestsPerDayPerProjectPerModel-FreeTier]")

    with (
        patch("core.translation_worker.get_gemini_model", return_value=Model()),
        patch.object(project, "save_checkpoint", return_value=True),
    ):
        worker._run()
    assert project.entries["/e[1]"].error_code == "daily_quota"


def test_a_model_without_quota_fails_fast_instead_of_waiting_hours():
    project = TranslationProject()
    for entry in entries("Sword"):
        project.entries[entry.xpath] = entry
    worker, _ = make_worker(project, parallel=1)

    class Model:
        def generate_content(self, prompt, response_schema=None):
            raise RuntimeError("Gemini API HTTP 429: You exceeded your current quota. Please retry in 66305s.")

    started = time.monotonic()
    with (
        patch("core.translation_worker.get_gemini_model", return_value=Model()),
        patch.object(project, "save_checkpoint", return_value=True),
    ):
        worker._run()
    assert time.monotonic() - started < 5
    assert project.entries["/e[1]"].error_code == "daily_quota"
