"""Translation projects through the HTTP bridge."""
from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from core.workspace import detect_game, xml_files
from engine.server import create_app
from engine.session import Session
from tests.test_engine import TOKEN, XML


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("STZ_XML_TRANSLATOR_DATA_DIR", str(tmp_path / "data"))
    game = tmp_path / "game" / "XMLs"
    (game / "missions").mkdir(parents=True)
    (game / "items.xml").write_text(XML, encoding="utf-8")
    (game / "missions" / "10.xml").write_text(XML, encoding="utf-8")
    (game / "missions" / "2.xml").write_text(XML, encoding="utf-8")
    session = Session()
    client = TestClient(create_app(session, TOKEN), headers={"Authorization": f"Bearer {TOKEN}"})
    return client, game, tmp_path


def create(client, game, name="MAA Redux"):
    response = client.post("/api/projects", json={"name": name, "folder": str(game)})
    assert response.status_code == 200
    return response.json()


def load_items(client, game):
    assert client.post("/api/xml/open", json={"path": str(game / "items.xml")}).status_code == 200
    body = {"parent": "item", "targets": ["description"], "contexts": ["name"]}
    assert client.post("/api/xml/load", json=body).status_code == 200


def test_xml_files_are_listed_shallow_first_in_natural_order(env):
    _client, game, _tmp = env
    assert xml_files(str(game)) == ["items.xml", "missions/2.xml", "missions/10.xml"]


@pytest.fixture
def unity_game(tmp_path):
    """A Unity install inside a Downloads folder that also holds installers."""
    downloads = tmp_path / "Downloads"
    root = downloads / "MAA Redux [Build v2]"
    xmls = root / "MAA Redux_Data" / "StreamingAssets" / "XMLs"
    xmls.mkdir(parents=True)
    (root / "MAA Redux.exe").write_bytes(b"MZ")
    (root / "UnityCrashHandler64.exe").write_bytes(b"MZ")
    (downloads / "setup.exe").write_bytes(b"MZ")
    (root / "MAA Redux_Data" / "config.xml").write_text(XML, encoding="utf-8")
    for name in ("characters", "items", "story", "client", "101", "102"):
        (xmls / f"{name}.xml").write_text(XML, encoding="utf-8")
    return downloads, root, xmls


@pytest.mark.parametrize("pick", ["root", "data", "streaming", "xmls"])
def test_detect_game_finds_root_and_xml_folder_from_any_level(unity_game, pick):
    _downloads, root, xmls = unity_game
    picked = {
        "root": root,
        "data": root / "MAA Redux_Data",
        "streaming": root / "MAA Redux_Data" / "StreamingAssets",
        "xmls": xmls,
    }[pick]
    game = detect_game(str(picked))
    assert game["root"] == str(root)
    assert game["name"] == "MAA Redux"
    # The data folder's one stray XML must not hide the XMLs folder.
    assert game["xmlFolder"] == str(xmls)
    assert game["count"] == 6


def test_detect_game_from_a_folder_without_xmls_inside_the_install(unity_game):
    _downloads, root, xmls = unity_game
    (root / "D3D12").mkdir()
    game = detect_game(str(root / "D3D12"))
    assert game["root"] == str(root)
    assert game["xmlFolder"] == str(xmls)


def test_detect_game_never_climbs_into_a_downloads_folder(unity_game):
    downloads, _root, _xmls = unity_game
    loose = downloads / "loose-xmls"
    loose.mkdir()
    (loose / "a.xml").write_text(XML, encoding="utf-8")
    game = detect_game(str(loose))
    assert game["root"] == str(loose)
    assert game["xmlFolder"] == str(loose)
    assert game["count"] == 1


def test_creating_from_the_game_root_uses_its_xml_folder(env, unity_game):
    client, _game, _tmp = env
    _downloads, root, xmls = unity_game
    detected = client.post("/api/projects/detect", json={"path": str(root)}).json()
    assert detected["count"] == 6
    project = client.post("/api/projects", json={"folder": str(root)}).json()
    assert project["name"] == "MAA Redux"
    assert project["folder"] == str(xmls)
    assert project["gameRoot"] == str(root)


def test_create_list_and_open_a_project(env):
    client, game, _tmp = env
    project = create(client, game)
    assert project["name"] == "MAA Redux"
    assert project["summary"]["files"] == 3

    listed = client.get("/api/projects").json()["projects"]
    assert [p["id"] for p in listed] == [project["id"]]

    detail = client.post(f"/api/projects/{project['id']}/open").json()
    assert [f["name"] for f in detail["files"]] == ["items.xml", "missions/2.xml", "missions/10.xml"]
    assert client.get("/api/state").json()["project"]["id"] == project["id"]


def test_missing_folder_is_refused(env):
    client, _game, tmp = env
    response = client.post("/api/projects", json={"folder": str(tmp / "nope")})
    assert response.status_code == 404
    assert response.json() == {"error": "folder_not_found"}


def test_loading_a_file_remembers_selection_and_reports_progress(env):
    client, game, _tmp = env
    project = create(client, game)
    client.post(f"/api/projects/{project['id']}/open")
    load_items(client, game)
    entry = client.get("/api/entries").json()["entries"][0]
    assert client.post("/api/entries/edit", json={"id": entry["id"], "text": "Uma espada curta."}).status_code == 200

    assert client.post("/api/xml/close").status_code == 200
    state = client.get("/api/state").json()
    assert state["loaded"] is False
    assert state["project"]["id"] == project["id"]

    detail = client.get(f"/api/projects/{project['id']}").json()
    items = next(f for f in detail["files"] if f["name"] == "items.xml")
    assert items["groups"] == [{"parent": "item", "targets": ["description"], "contexts": ["name"]}]
    assert items["progress"] == {"total": 3, "translated": 1, "confirmed": 0}
    assert detail["lastFile"] == "items.xml"
    assert detail["summary"]["translated"] == 1


def test_progress_survives_moving_the_game_folder(env):
    client, game, tmp = env
    project = create(client, game)
    client.post(f"/api/projects/{project['id']}/open")
    load_items(client, game)
    entry = client.get("/api/entries").json()["entries"][0]
    client.post("/api/entries/edit", json={"id": entry["id"], "text": "Uma espada curta."})
    client.post("/api/projects/close")

    moved = tmp / "reinstalled" / "XMLs"
    shutil.copytree(game, moved)
    shutil.rmtree(game)
    assert client.put(f"/api/projects/{project['id']}", json={"folder": str(moved)}).status_code == 200
    client.post(f"/api/projects/{project['id']}/open")

    assert client.post("/api/xml/open", json={"path": str(moved / "items.xml")}).status_code == 200
    body = {"parent": "item", "targets": ["description"], "contexts": ["name"]}
    assert client.post("/api/xml/load", json=body).json()["restored"] == 1


def test_delete_project_closes_it(env):
    client, game, _tmp = env
    project = create(client, game)
    client.post(f"/api/projects/{project['id']}/open")
    assert client.delete(f"/api/projects/{project['id']}").status_code == 200
    assert client.get("/api/state").json()["project"] is None
    assert client.get(f"/api/projects/{project['id']}").status_code == 404
