"""Importing a translation made by hand in the game folder, against a clean copy."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from engine.server import create_app
from engine.session import Session
from tests.test_engine import TOKEN, XML

EDITED = (
    XML.replace("A short sword.", "Uma espada curta.")
    .replace("Reduces fire damage.", "Reduz o dano de fogo.")
)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("STZ_XML_TRANSLATOR_DATA_DIR", str(tmp_path / "data"))
    game = tmp_path / "game"
    clean = tmp_path / "clean"
    for folder in (game, clean):
        (folder / "extra").mkdir(parents=True)
    (game / "items.xml").write_text(EDITED, encoding="utf-8")
    (clean / "items.xml").write_text(XML, encoding="utf-8")
    (game / "extra" / "same.xml").write_text(XML, encoding="utf-8")
    (clean / "extra" / "same.xml").write_text(XML, encoding="utf-8")
    (game / "only-in-game.xml").write_text(XML, encoding="utf-8")
    client = TestClient(create_app(Session(), TOKEN), headers={"Authorization": f"Bearer {TOKEN}"})
    project = client.post("/api/projects", json={"folder": str(game), "name": "Game"}).json()
    client.post(f"/api/projects/{project['id']}/open")
    return client, project, game, clean


def wait_import(client):
    deadline = time.time() + 10
    while time.time() < deadline:
        state = client.get("/api/state").json()["import"]
        if state["status"] != "running":
            return state
        time.sleep(0.02)
    raise AssertionError("import never finished")


def test_preview_finds_the_hand_made_translations(env):
    client, _project, _game, clean = env
    assert client.post("/api/import/start", json={"path": str(clean)}).status_code == 200
    state = wait_import(client)
    assert state["status"] == "ready"
    assert state["found"] == 2
    assert state["missing"] == 1
    files = {f["file"]: f for f in state["files"]}
    assert files["items.xml"]["found"] == 2
    assert files["only-in-game.xml"]["problem"] == "missing"
    assert "extra/same.xml" not in files  # nothing changed there


def test_applying_keeps_originals_and_saves_for_review(env):
    client, project, game, clean = env
    client.post("/api/import/start", json={"path": str(clean)})
    wait_import(client)
    assert client.post("/api/import/apply").json() == {"saved": 2}

    detail = client.get(f"/api/projects/{project['id']}").json()
    assert detail["hasOriginals"] is True
    items = next(f for f in detail["files"] if f["name"] == "items.xml")
    # Opens from the kept clean copy, not the edited game file.
    assert "originals" in items["path"] and items["path"].endswith("items.xml")
    assert items["progress"]["translated"] == 2
    assert items["progress"]["total"] == 6  # every suggested text counts, not just the imported ones

    client.post("/api/xml/open", json={"path": items["path"]})
    loaded = client.post("/api/xml/load", json={"groups": items["groups"]}).json()
    assert loaded["restored"] == 2
    entries = client.get("/api/entries").json()["entries"]
    sword = next(e for e in entries if e["original"] == "A short sword.")
    assert sword["translation"] == "Uma espada curta."
    assert sword["status"] == "translated"
    history = client.get("/api/entries/history", params={"id": sword["id"]}).json()["versions"]
    assert history[0]["source"] == "import"
    # The game folder was not touched.
    assert (game / "items.xml").read_text(encoding="utf-8") == EDITED


def test_import_never_overwrites_translations_made_in_the_app(env):
    client, project, game, clean = env
    client.post("/api/xml/open", json={"path": str(game / "items.xml")})
    client.post("/api/xml/load", json={"parent": "item", "targets": ["description"], "contexts": ["name"]})
    # Pretend the file had been opened from a clean copy: translate the clean text in the app.
    client.post("/api/xml/close")
    client.post("/api/import/start", json={"path": str(clean)})
    wait_import(client)
    client.post("/api/import/apply")
    items = next(f for f in client.get(f"/api/projects/{project['id']}").json()["files"] if f["name"] == "items.xml")
    client.post("/api/xml/open", json={"path": items["path"]})
    client.post("/api/xml/load", json={"groups": items["groups"]})
    entry = next(e for e in client.get("/api/entries").json()["entries"] if e["original"] == "A short sword.")
    client.post("/api/entries/confirm", json={"id": entry["id"], "text": "Espada curta"})
    client.post("/api/xml/close")

    client.post("/api/import/start", json={"path": str(clean)})
    wait_import(client)
    assert client.post("/api/import/apply").json()["saved"] == 0
    client.post("/api/xml/open", json={"path": items["path"]})
    client.post("/api/xml/load", json={"groups": items["groups"]})
    entry = next(e for e in client.get("/api/entries").json()["entries"] if e["original"] == "A short sword.")
    assert (entry["translation"], entry["status"]) == ("Espada curta", "confirmed")


def test_the_game_folder_itself_is_refused(env):
    client, _project, game, _clean = env
    response = client.post("/api/import/start", json={"path": str(game)})
    assert response.json() == {"error": "same_folder"}
