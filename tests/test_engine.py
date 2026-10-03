"""The HTTP bridge used by the React UI, driven end to end without a network."""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from engine import session as session_module
from engine.server import create_app
from engine.session import Session

TOKEN = "test-token"
XML = """<?xml version="1.0" encoding="UTF-8"?>
<items>
  <item id="1" rarity="rare">
    <name>Ember Blade</name>
    <description>A short sword.</description>
  </item>
  <item id="2" rarity="epic">
    <name>Frostbound Shield</name>
    <description>Reduces fire damage.</description>
  </item>
  <item id="3" rarity="common">
    <name>Iron Hatchet</name>
    <description>A reliable tool.</description>
  </item>
</items>
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("STZ_XML_TRANSLATOR_DATA_DIR", str(tmp_path / "data"))
    xml_path = tmp_path / "items.xml"
    xml_path.write_text(XML, encoding="utf-8")
    session = Session()
    client = TestClient(create_app(session, TOKEN), headers={"Authorization": f"Bearer {TOKEN}"})
    return session, client, xml_path, tmp_path


def load(client, xml_path):
    assert client.post("/api/xml/open", json={"path": str(xml_path)}).status_code == 200
    body = {"parent": "item", "targets": ["description"], "contexts": ["name"]}
    assert client.post("/api/xml/load", json=body).json() == {"count": 3, "restored": 0}
    return client.get("/api/entries").json()["entries"]


def wait_idle(client):
    deadline = time.time() + 5
    while time.time() < deadline:
        state = client.get("/api/state").json()
        if not state["translating"] and not state["translatingEntries"]:
            return state
        time.sleep(0.02)
    raise AssertionError("engine never became idle")


def test_requires_the_session_token(env):
    session, _client, _xml, _tmp = env
    anonymous = TestClient(create_app(session, TOKEN))
    assert anonymous.get("/api/state").status_code == 401
    assert anonymous.get("/api/health").status_code == 200


def test_open_reports_repeating_tags_and_preview(env):
    _session, client, xml_path, _tmp = env
    opened = client.post("/api/xml/open", json={"path": str(xml_path)}).json()
    assert opened["parents"] == [{"tag": "item", "count": 3}]
    assert client.get("/api/xml/children", params={"parent": "item"}).json()["tags"] == [
        "name",
        "description",
    ]
    body = {"parent": "item", "targets": ["description"], "contexts": ["name"]}
    preview = client.post("/api/xml/preview", json=body).json()
    assert (preview["records"], preview["lines"]) == (3, 3)
    assert preview["sample"][0]["attributes"] == {"id": "1", "rarity": "rare"}
    assert preview["sample"][0]["fields"][0] == {"tag": "name", "text": "Ember Blade"}


def test_missing_file_is_refused(env):
    _session, client, _xml, tmp = env
    response = client.post("/api/xml/open", json={"path": str(tmp / "nope.xml")})
    assert (response.status_code, response.json()) == (404, {"error": "file_not_found"})


def test_edit_confirm_and_incremental_entries(env):
    _session, client, xml_path, _tmp = env
    entries = load(client, xml_path)
    assert [e["status"] for e in entries] == ["pending"] * 3
    assert entries[0]["context"] == {"name": "Ember Blade"}
    first, second = entries[0]["id"], entries[1]["id"]
    rev = client.get("/api/entries").json()["rev"]

    assert client.post("/api/entries/edit", json={"id": first, "text": "Uma espada curta."}).status_code == 200
    changed = client.get("/api/entries", params={"since": rev}).json()
    assert changed["full"] is False
    assert [(e["id"], e["status"]) for e in changed["entries"]] == [(first, "translated")]

    assert client.post("/api/entries/confirm", json={"id": first}).status_code == 200
    empty = client.post("/api/entries/confirm", json={"id": second})
    assert (empty.status_code, empty.json()) == (400, {"error": "empty_translation"})
    counts = client.get("/api/state").json()["counts"]
    assert (counts["confirmed"], counts["pending"]) == (1, 2)


def test_progress_survives_a_restart_through_the_checkpoint(env):
    _session, client, xml_path, _tmp = env
    entries = load(client, xml_path)
    client.post("/api/entries/confirm", json={"id": entries[0]["id"], "text": "Uma espada curta."})

    reopened = TestClient(create_app(Session(), TOKEN), headers={"Authorization": f"Bearer {TOKEN}"})
    reopened.post("/api/xml/open", json={"path": str(xml_path)})
    body = {"parent": "item", "targets": ["description"], "contexts": ["name"]}
    assert reopened.post("/api/xml/load", json=body).json()["restored"] == 1
    restored = reopened.get("/api/entries").json()["entries"][0]
    assert (restored["translation"], restored["status"]) == ("Uma espada curta.", "confirmed")


def test_batch_translation_and_export_keep_the_structure(env, monkeypatch):
    session, client, xml_path, tmp = env
    client.put("/api/settings", json={"provider": "Google Translate (Free)"})
    monkeypatch.setattr(
        "core.translation_worker.translate_batch_google_free",
        lambda batch, _config: {entry.xpath: f"PT {entry.original}" for entry in batch},
    )
    load(client, xml_path)
    assert client.post("/api/translate", json={}).status_code == 200
    state = wait_idle(client)
    assert state["counts"]["translated"] == 3

    out = tmp / "out.xml"
    assert client.post("/api/xml/export", json={"path": str(out)}).status_code == 200
    before = list(ET.parse(xml_path).getroot().iter())
    after = list(ET.parse(out).getroot().iter())
    assert [(e.tag, e.attrib) for e in before] == [(e.tag, e.attrib) for e in after]
    assert [e.text for e in after if e.tag == "description"] == [
        "PT A short sword.",
        "PT Reduces fire damage.",
        "PT A reliable tool.",
    ]
    assert [e.text for e in after if e.tag == "name"] == [e.text for e in before if e.tag == "name"]
    assert session.ctrl.project.stats() == (3, 3)


def test_translating_without_a_key_is_refused(env):
    _session, client, xml_path, _tmp = env
    client.put("/api/settings", json={"provider": "DeepL"})
    load(client, xml_path)
    response = client.post("/api/translate", json={})
    assert (response.status_code, response.json()) == (409, {"error": "api_key_required"})


def test_api_keys_are_stored_but_never_returned(env):
    _session, client, _xml, _tmp = env
    settings = client.put("/api/settings/api-key", json={"provider": "DeepL", "key": "secret-123"}).json()
    deepl = next(p for p in settings["providers"] if p["id"] == "DeepL")
    assert deepl["hasKey"] is True
    assert "secret-123" not in client.get("/api/state").text
    providers = [p["id"] for p in settings["providers"]]
    assert "Llama 3 (Local)" not in providers and "Ollama (Local)" in providers


def test_glossary_and_presets_round_trip(env):
    _session, client, xml_path, _tmp = env
    terms = [{"original": "Blade", "translation": "Lâmina"}, {"original": " ", "translation": "x"}]
    assert client.put("/api/glossary", json={"terms": terms}).json()["terms"] == [terms[0]]
    assert client.get("/api/state").json()["settings"]["glossaryCount"] == 1

    client.post("/api/xml/open", json={"path": str(xml_path)})
    body = {"label": "Itens", "parent": "item", "targets": ["description"], "contexts": ["name"]}
    presets = client.post("/api/presets", json=body).json()["presets"]
    assert [(p["label"], p["targets"], p["contexts"], p["file"]) for p in presets] == [
        ("Itens", ["description"], ["name"], "items.xml")
    ]
    assert client.delete(f"/api/presets/{presets[0]['id']}").json()["presets"] == []


def test_preferences_persist_and_reject_unknown_values(env):
    _session, client, _xml, _tmp = env
    saved = client.put("/api/settings", json={"theme": "light", "accent": "amber", "autoUpdate": False}).json()
    assert (saved["theme"], saved["accent"], saved["autoUpdate"]) == ("light", "amber", False)
    assert client.put("/api/settings", json={"theme": "neon"}).json()["theme"] == "light"
    assert Session().prefs == {"theme": "light", "accent": "amber", "auto_update": False}
    assert client.put("/api/settings", json={"locale": "xx_XX"}).status_code == 400


def test_update_check_exposes_release_notes(env, monkeypatch):
    _session, client, _xml, _tmp = env
    release = session_module.updater.ReleaseInfo(
        version="9.9.9", tag_name="v9.9.9", notes="## Novo\n- Algo", page_url="https://example.test",
        installer_name="x.exe", download_url="https://example.test/x.exe", sha256="0" * 64, size=1,
    )
    monkeypatch.setattr(session_module.updater, "fetch_latest_release", lambda _current: release)
    client.post("/api/update/check")
    deadline = time.time() + 5
    while time.time() < deadline:
        update = client.get("/api/state").json()["update"]
        if update["status"] == "idle" and update["available"]:
            break
        time.sleep(0.02)
    assert (update["version"], update["notes"]) == ("9.9.9", "## Novo\n- Algo")
    client.post("/api/update/skip")
    assert client.get("/api/state").json()["update"]["available"] is False


def test_feedback_sends_only_the_declared_fields(env):
    session, client, _xml, _tmp = env
    sent = {}

    class Http:
        @staticmethod
        def post(url, json, timeout):
            sent.update(url=url, json=json)
            return type("Response", (), {"status_code": 200})()

    session.send_feedback("O botão de exportar poderia lembrar a última pasta.", http=Http)
    assert sent["url"] == "https://stzlabs.com/api/feedback"
    assert set(sent["json"]) == {"product", "text", "version", "locale", "os"}
    assert sent["json"]["product"] == "xml-translator"
    short = client.post("/api/feedback", json={"text": "curto"})
    assert (short.status_code, short.json()) == (400, {"error": "feedback_length"})


def test_each_target_language_keeps_its_own_glossary(env):
    _session, client, _xml, _tmp = env
    client.put("/api/glossary", json={"terms": [{"original": "Blade", "translation": "Lâmina"}]})
    assert client.put("/api/settings", json={"target": "es_ES"}).status_code == 200
    assert client.get("/api/glossary").json()["terms"] == []
    client.put("/api/glossary", json={"terms": [{"original": "Blade", "translation": "Hoja"}]})
    assert client.get("/api/state").json()["settings"]["glossaryCount"] == 1

    client.put("/api/settings", json={"target": "pt_BR"})
    assert client.get("/api/glossary").json()["terms"] == [{"original": "Blade", "translation": "Lâmina"}]


def test_importing_a_file_that_is_not_a_backup_reports_zero(env):
    _session, client, xml_path, tmp = env
    load(client, xml_path)
    bad = tmp / "bad.json"
    bad.write_text('["not", "a", "backup"]', encoding="utf-8")
    response = client.post("/api/backup/import", json={"path": str(bad)})
    assert (response.status_code, response.json()) == (200, {"count": 0})
