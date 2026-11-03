"""SQLite storage: progress, history, migration from JSON and project scoping."""
from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from core.store import EntryState, TranslationStore
from engine.server import create_app
from engine.session import Session
from tests.test_engine import TOKEN, XML


def test_save_load_and_history(tmp_path):
    store = TranslationStore(str(tmp_path / "t.db"))
    store.save("file:a.xml", "pt", [EntryState("/a[1]", "Sword", "Espada", "translated", source="ai")])
    store.save("file:a.xml", "pt", [EntryState("/a[1]", "Sword", "Espadinha", "translated", source="manual")])
    store.save("file:a.xml", "pt", [EntryState("/a[1]", "Sword", "Espadinha", "confirmed", source="confirm")])

    assert store.load("file:a.xml", "pt")["/a[1]"].translation == "Espadinha"
    versions = store.history("file:a.xml", "pt", "/a[1]")
    assert [(v["newText"], v["source"]) for v in versions] == [
        ("Espadinha", "confirm"),
        ("Espadinha", "manual"),
        ("Espada", "ai"),
    ]
    assert versions[1]["oldText"] == "Espada"
    assert store.progress("file:a.xml", "pt") == {"total": 1, "translated": 1, "confirmed": 1}
    assert store.load("file:a.xml", "en") == {}


def test_unchanged_saves_write_nothing(tmp_path):
    store = TranslationStore(str(tmp_path / "t.db"))
    rows = [EntryState("/a[1]", "Sword", "", "pending"), EntryState("/a[2]", "Shield", "Escudo", "translated")]
    assert store.save("k", "pt", rows) == 2
    assert store.save("k", "pt", rows) == 0
    # A pending entry with no text never enters the history.
    assert store.history("k", "pt", "/a[1]") == []


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("STZ_XML_TRANSLATOR_DATA_DIR", str(tmp_path / "data"))
    game = tmp_path / "game"
    game.mkdir()
    (game / "items.xml").write_text(XML, encoding="utf-8")
    client = TestClient(create_app(Session(), TOKEN), headers={"Authorization": f"Bearer {TOKEN}"})
    return client, game, tmp_path


def load(client, path):
    client.post("/api/xml/open", json={"path": str(path)})
    body = {"parent": "item", "targets": ["description"], "contexts": ["name"]}
    return client.post("/api/xml/load", json=body).json()


def test_edits_are_versioned_and_listed(env):
    client, game, _tmp = env
    load(client, game / "items.xml")
    entry = client.get("/api/entries").json()["entries"][0]
    client.post("/api/entries/edit", json={"id": entry["id"], "text": "Uma espada"})
    client.post("/api/entries/edit", json={"id": entry["id"], "text": "Uma espada curta"})
    client.post("/api/entries/confirm", json={"id": entry["id"]})

    versions = client.get("/api/entries/history", params={"id": entry["id"]}).json()["versions"]
    assert [v["source"] for v in versions] == ["confirm", "manual", "manual"]
    assert versions[1]["oldText"] == "Uma espada"


def test_json_checkpoints_are_imported_once(env, tmp_path, monkeypatch):
    client, game, _tmp = env
    load(client, game / "items.xml")
    entry = client.get("/api/entries").json()["entries"][0]
    client.post("/api/entries/edit", json={"id": entry["id"], "text": "Uma espada"})
    client.post("/api/xml/close")

    # An install from before SQLite: only the JSON checkpoints exist.
    older = tmp_path / "older"
    shutil.copytree(tmp_path / "data" / "checkpoints", older / "checkpoints")
    monkeypatch.setenv("STZ_XML_TRANSLATOR_DATA_DIR", str(older))
    fresh = TestClient(create_app(Session(), TOKEN), headers={"Authorization": f"Bearer {TOKEN}"})
    assert load(fresh, game / "items.xml")["restored"] == 1
    versions = fresh.get("/api/entries/history", params={"id": entry["id"]}).json()["versions"]
    assert [v["source"] for v in versions] == ["import"]


def test_search_and_memory(tmp_path):
    store = TranslationStore(str(tmp_path / "t.db"))
    store.save("p1:a.xml", "pt", [EntryState("/x[1]", "Iron Hatchet", "Machado de Ferro", "confirmed")])
    store.save("p1:b.xml", "pt", [EntryState("/y[1]", "Iron Hatchet", "Machadinha", "translated"),
                                  EntryState("/y[2]", "50% off_sale", "", "pending")])
    store.save("p2:a.xml", "pt", [EntryState("/x[1]", "Iron Hatchet", "Outro", "translated")])

    found = store.search("p1:", "pt", "hatchet")
    assert [(r["key"], r["translation"]) for r in found] == [("p1:a.xml", "Machado de Ferro"), ("p1:b.xml", "Machadinha")]
    assert [r["xpath"] for r in store.search("p1:", "pt", "%")] == ["/y[2]"]  # wildcards are literal
    assert store.search("p1:", "pt", "machado")[0]["xpath"] == "/x[1]"  # translations too

    memory = store.memory("pt", "Iron Hatchet")
    assert memory[0] == {"translation": "Machado de Ferro", "confirmed": True, "uses": 1}
    assert {m["translation"] for m in memory} == {"Machado de Ferro", "Machadinha", "Outro"}


def test_suggestions_and_project_search_endpoints(env):
    client, game, _tmp = env
    project = client.post("/api/projects", json={"folder": str(game), "name": "Game"}).json()
    client.post(f"/api/projects/{project['id']}/open")
    load(client, game / "items.xml")
    entries = client.get("/api/entries").json()["entries"]
    client.post("/api/entries/edit", json={"id": entries[0]["id"], "text": "Uma espada"})

    results = client.get("/api/search", params={"q": "espada"}).json()["results"]
    assert [(r["file"], r["original"]) for r in results] == [("items.xml", entries[0]["original"])]
    assert results[0]["path"].endswith("items.xml")
    # Its own text is not suggested back to it.
    assert client.get("/api/entries/suggestions", params={"id": entries[0]["id"]}).json()["suggestions"] == []

    client.post("/api/entries/edit", json={"id": entries[1]["id"], "text": "Escudo", "source": "memory"})
    versions = client.get("/api/entries/history", params={"id": entries[1]["id"]}).json()["versions"]
    assert versions[0]["source"] == "memory"
    assert client.post("/api/entries/edit", json={"id": entries[1]["id"], "text": "x", "source": "ai"}).status_code == 422


def test_project_progress_comes_from_the_database_and_survives_a_move(env, tmp_path):
    client, game, _tmp = env
    project = client.post("/api/projects", json={"folder": str(game), "name": "Game"}).json()
    client.post(f"/api/projects/{project['id']}/open")
    load(client, game / "items.xml")
    entry = client.get("/api/entries").json()["entries"][0]
    client.post("/api/entries/edit", json={"id": entry["id"], "text": "Uma espada"})
    client.post("/api/xml/close")

    moved = tmp_path / "moved"
    shutil.copytree(game, moved)
    client.put(f"/api/projects/{project['id']}", json={"folder": str(moved)})
    detail = client.get(f"/api/projects/{project['id']}").json()
    assert detail["files"][0]["progress"] == {"total": 3, "translated": 1, "confirmed": 0}
    assert load(client, moved / "items.xml")["restored"] == 1
