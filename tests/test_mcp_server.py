"""The MCP tools an agent uses, end to end over the real Session."""
from __future__ import annotations

import asyncio
import json
import xml.etree.ElementTree as ET

import pytest

pytest.importorskip("mcp")

from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from engine.mcp_server import build_server  # noqa: E402
from engine.session import Session  # noqa: E402
from tests.test_engine import XML  # noqa: E402


@pytest.fixture
def call(tmp_path, monkeypatch):
    monkeypatch.setenv("STZ_XML_TRANSLATOR_DATA_DIR", str(tmp_path / "data"))
    server = build_server(Session())

    def invoke(tool: str, /, **arguments):
        result = asyncio.run(server.call_tool(tool, arguments))
        structured = result.structured_content or {}
        if "result" in structured:  # lists come wrapped
            return structured["result"]
        return json.loads(result.content[0].text) if result.content else None

    invoke.server = server
    return invoke


@pytest.fixture
def game(tmp_path):
    folder = tmp_path / "game"
    folder.mkdir()
    (folder / "items.xml").write_text(XML, encoding="utf-8")
    return folder


def test_tools_are_listed():
    server = build_server(Session())
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert {"list_projects", "load_file", "list_entries", "set_translations", "export_xml", "search_project"} <= names


def test_an_agent_translates_a_file(call, game, tmp_path):
    project = call("create_project", game_folder=str(game), name="Game", target_language="pt_BR")
    detail = call("open_project", project_id=project["id"])
    assert [f["name"] for f in detail["files"]] == ["items.xml"]

    loaded = call("load_file", path=str(game / "items.xml"))
    assert loaded["count"] == 6  # name + description of 3 items, both suggested
    pending = call("list_entries", status="pending", field="item > description")
    assert pending["total"] == 3
    first = pending["entries"][0]
    assert first["context"] == {}

    saved = call("set_translations", translations=[{"id": first["id"], "text": "Uma espada curta."}])
    assert saved == {"saved": 1, "failed": []}
    assert call("list_entries", status="translated")["entries"][0]["translation"] == "Uma espada curta."
    assert call("entry_history", id=first["id"])[0]["source"] == "agent"
    assert call("search_project", query="espada")[0]["file"] == "items.xml"

    call("confirm_entries", ids=[first["id"]])
    assert call("status")["counts"]["confirmed"] == 1

    out = tmp_path / "items_pt.xml"
    call("export_xml", output_path=str(out))
    texts = [d.text for d in ET.parse(out).getroot().iter("description")]
    assert texts[0] == "Uma espada curta."


def test_an_agent_imports_a_hand_made_translation(call, tmp_path):
    game, clean = tmp_path / "edited", tmp_path / "clean"
    game.mkdir()
    clean.mkdir()
    (clean / "items.xml").write_text(XML, encoding="utf-8")
    (game / "items.xml").write_text(XML.replace("A short sword.", "Uma espada curta."), encoding="utf-8")
    project = call("create_project", game_folder=str(game), name="Game")
    call("open_project", project_id=project["id"])

    preview = call("import_translation", clean_folder=str(clean))
    assert preview["found"] == 1
    assert call("import_translation", clean_folder=str(clean), apply=True) == {"saved": 1}
    files = call("open_project", project_id=project["id"])["files"]
    assert files[0]["progress"]["translated"] == 1


def test_errors_carry_a_code(call):
    with pytest.raises(ToolError, match="error: no_file"):
        call("list_entries")
