"""Whole-project operations: apply to the game, translate everything, new builds, packages."""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from engine.server import create_app
from engine.session import Session
from tests.test_engine import TOKEN, XML


def descriptions(path):
    return [d.text for d in ET.parse(path).getroot().iter("description")]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("STZ_XML_TRANSLATOR_DATA_DIR", str(tmp_path / "data"))
    game = tmp_path / "Game"
    xmls = game / "Game_Data" / "XMLs"
    xmls.mkdir(parents=True)
    (game / "Game.exe").write_bytes(b"MZ")
    (xmls / "items.xml").write_text(XML, encoding="utf-8")
    (xmls / "other.xml").write_text(XML, encoding="utf-8")
    session = Session()
    client = TestClient(create_app(session, TOKEN), headers={"Authorization": f"Bearer {TOKEN}"})
    project = client.post("/api/projects", json={"folder": str(game), "name": "Game"}).json()
    client.post(f"/api/projects/{project['id']}/open")
    return client, session, project, xmls, tmp_path


def wait_job(client):
    deadline = time.time() + 15
    while time.time() < deadline:
        job = client.get("/api/state").json()["job"]
        if job["status"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("job never finished")


def translate_items(client, xmls, text="Uma espada curta."):
    client.post("/api/xml/open", json={"path": str(xmls / "items.xml")})
    client.post("/api/xml/load", json={"parent": "item", "targets": ["description"], "contexts": ["name"]})
    entry = next(e for e in client.get("/api/entries").json()["entries"] if e["original"] == "A short sword.")
    client.post("/api/entries/edit", json={"id": entry["id"], "text": text})
    client.post("/api/xml/close")


def test_apply_writes_the_game_keeps_a_backup_and_restores(env):
    client, _session, project, xmls, _tmp = env
    translate_items(client, xmls)
    assert client.post("/api/game/apply", json={}).status_code == 200
    job = wait_job(client)
    assert job["status"] == "done" and job["result"] == {"files": 1, "texts": 1}
    assert descriptions(xmls / "items.xml")[0] == "Uma espada curta."
    assert descriptions(xmls / "other.xml")[0] == "A short sword."  # untranslated files untouched

    detail = client.get(f"/api/projects/{project['id']}").json()
    assert detail["applied"] is True and detail["hasOriginals"] is True
    assert detail["gameExe"] == "Game.exe"
    # Files still open from the English originals, not the translated game file.
    items = next(f for f in detail["files"] if f["name"] == "items.xml")
    assert "originals" in items["path"]

    client.post("/api/job/dismiss")
    client.post("/api/game/restore")
    assert wait_job(client)["result"] == {"files": 1}
    assert descriptions(xmls / "items.xml")[0] == "A short sword."
    assert client.get(f"/api/projects/{project['id']}").json()["applied"] is False


def test_launch_starts_the_game_executable(env):
    client, *_ = env
    with patch("core.game_ops.subprocess.Popen") as popen:
        assert client.post("/api/game/launch").json() == {"launched": "Game.exe"}
    assert popen.call_args.args[0][0].endswith("Game.exe")


def test_export_writes_translated_xmls_to_any_folder(env):
    client, _session, _project, xmls, tmp = env
    translate_items(client, xmls)
    out = tmp / "share"
    client.post("/api/project/export-xmls", json={"path": str(out)})
    assert wait_job(client)["status"] == "done"
    assert descriptions(out / "items.xml")[0] == "Uma espada curta."
    assert descriptions(xmls / "items.xml")[0] == "A short sword."  # the game itself is untouched


def test_translate_the_whole_project(env):
    client, session, project, xmls, _tmp = env
    session.ctrl.preferred_provider = "Google Translate (Free)"

    def fake(entries, _config):
        return {e.xpath: f"PT {e.original}" for e in entries}

    with patch("core.translation_worker.translate_batch_google_free", side_effect=fake):
        assert client.post("/api/project/translate").status_code == 200
        job = wait_job(client)
    assert job["status"] == "done"
    assert job["result"]["files"] == 2
    detail = client.get(f"/api/projects/{project['id']}").json()
    assert all(f["progress"]["translated"] == f["progress"]["total"] > 0 for f in detail["files"])
    assert all(f["groups"] for f in detail["files"])  # fields chosen for each file


def test_a_new_build_keeps_moves_and_flags_changes(env):
    client, _session, project, xmls, tmp = env
    translate_items(client, xmls)
    client.post("/api/xml/open", json={"path": str(xmls / "items.xml")})
    client.post("/api/xml/load", json={"parent": "item", "targets": ["description"], "contexts": ["name"]})
    for entry in client.get("/api/entries").json()["entries"]:
        if entry["original"] == "A reliable tool.":
            client.post("/api/entries/edit", json={"id": entry["id"], "text": "Uma ferramenta confiável."})
    client.post("/api/xml/close")

    new_build = tmp / "Game v2"
    new_xmls = new_build / "Game_Data" / "XMLs"
    new_xmls.mkdir(parents=True)
    (new_build / "Game.exe").write_bytes(b"MZ")
    # Item 1's text changed; a new item is inserted first, so every record moves down one.
    changed = XML.replace("A short sword.", "A short, sharp sword.")
    new_item = '<item id="0" rarity="common">\n    <name>Torch</name>\n    <description>It lights the way.</description>\n  </item>\n  '
    (new_xmls / "items.xml").write_text(changed.replace('<item id="1"', new_item + '<item id="1"', 1), encoding="utf-8")
    (new_xmls / "other.xml").write_text(XML, encoding="utf-8")

    client.post("/api/project/update", json={"path": str(new_build)})
    job = wait_job(client)
    assert job["status"] == "done", job
    result = job["result"]
    assert result["moved"] == 1  # "A reliable tool." moved to a new place
    assert result["new"] >= 2  # the torch, plus the changed sword at a position never translated
    assert client.post("/api/project/update/apply").json()["reused"] >= 1

    detail = client.get(f"/api/projects/{project['id']}").json()
    assert detail["folder"] == str(new_xmls)
    items = next(f for f in detail["files"] if f["name"] == "items.xml")
    client.post("/api/xml/open", json={"path": items["path"]})
    client.post("/api/xml/load", json={"groups": items["groups"]})
    by_original = {e["original"]: e for e in client.get("/api/entries").json()["entries"]}
    assert by_original["A reliable tool."]["translation"] == "Uma ferramenta confiável."
    assert by_original["A reliable tool."]["status"] == "translated"  # reused, to review
    assert by_original["It lights the way."]["status"] == "pending"


def test_update_refuses_a_game_folder_that_holds_the_translation(env):
    client, _session, _project, xmls, _tmp = env
    translate_items(client, xmls)
    client.post("/api/game/apply", json={})
    wait_job(client)
    client.post("/api/job/dismiss")
    assert client.post("/api/project/update", json={"path": str(xmls)}).json() == {"error": "restore_first"}


def test_packages_share_a_translation_without_overwriting(env, tmp_path):
    client, _session, project, xmls, _tmp = env
    translate_items(client, xmls)
    package = tmp_path / "game-pt.stzpack"
    assert client.post("/api/project/package/export", json={"path": str(package)}).json() == {"files": 1, "texts": 1}

    # Another translator: same game, a different translation for one text, nothing for the other file.
    other = client.post("/api/projects", json={"folder": str(xmls), "name": "Copy"}).json()
    client.post(f"/api/projects/{other['id']}/open")
    result = client.post("/api/project/package/import", json={"path": str(package)}).json()
    assert result["imported"] == 1 and result["conflicts"] == 0
    again = client.post("/api/project/package/import", json={"path": str(package)}).json()
    assert again["imported"] == 0 and again["unchanged"] == 1

    bad = tmp_path / "bad.stzpack"
    bad.write_text("not a zip", encoding="utf-8")
    assert client.post("/api/project/package/import", json={"path": str(bad)}).json() == {"error": "package_invalid"}


def test_a_reworded_text_keeps_its_translation_for_review(tmp_path):
    from core.build_update import similar

    assert similar("A short sword.", "A short, sharp sword.")
    assert not similar("A short sword.", "It lights the way.")


def test_cancel_says_so_at_once(env):
    client, session, _project, _xmls, _tmp = env
    release = __import__("threading").Event()
    session._start_job("translate", lambda _progress: release.wait(5) and {})
    client.post("/api/job/cancel")
    job = client.get("/api/state").json()["job"]
    assert job["status"] == "running" and job["cancelling"] is True
    release.set()
    assert wait_job(client)["status"] == "cancelled"
