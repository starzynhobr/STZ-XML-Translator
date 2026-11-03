"""Telling text apart from technical values, game profiles and multi-tag loading."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from core.extrator import Group, indexar_xml
from core.field_analysis import CODE, FLAG, ID, NAME, NUMBER, PATH, TEXT, classify_field, classify_value
from core.game_profiles import CONTEXT, GENERIC, IGNORE, MAA_REDUX, TRANSLATE, plan, profile_for
from core.project import TranslationProject
from engine.server import create_app
from engine.session import Session
from tests.test_engine import TOKEN

CHARACTERS = """<?xml version="1.0" encoding="UTF-8"?>
<data>
  <baseVillains>
    <baseVillain>
      <bio>Raven Darkholme, a mutant shapeshifter able to assume any humanoid appearance.</bio>
      <dispName>MYSTIQUE</dispName>
      <iconAssetId>a/fs/ax0011.png</iconAssetId>
      <id>00c2ca90ff9ae0fec2146e23938c06f4</id>
      <name>MYSTIQUE</name>
    </baseVillain>
    <baseVillain>
      <bio>It took millions of dollars in weapons development to create Militant.</bio>
      <dispName>MILITANT</dispName>
      <iconAssetId>a/fs/1580011.png</iconAssetId>
      <id>01e8c144fe156b1234cdff698119aec6</id>
      <name>MILITANT</name>
    </baseVillain>
  </baseVillains>
  <actions>
    <action><id>SO6_GB_Cosmic_Conduit_Counter</id><sequenceNumber>0</sequenceNumber></action>
    <action><dispName>A Pound of Cure</dispName><id>069ab1c0-8eab-11e3-b1c0-0025906a2be6</id><sequenceNumber>0</sequenceNumber></action>
    <action><dispName>Mindbender</dispName><id>169ab1c0-8eab-11e3-b1c0-0025906a2be6</id><sequenceNumber>1</sequenceNumber></action>
  </actions>
  <villainActions>
    <villainAction><actionId>34687950-bf02-11e5-8070-065676001937</actionId><level>0</level></villainAction>
    <villainAction><actionId>e22764f0-efb0-11e0-8204-000c295d00fe</actionId><level>0</level></villainAction>
  </villainActions>
</data>
"""


@pytest.mark.parametrize(
    ("value", "kind"),
    [
        ("Defend the world.", TEXT),
        ("MYSTIQUE", NAME),
        ("069ab1c0-8eab-11e3-b1c0-0025906a2be6", ID),
        ("00c2ca90ff9ae0fec2146e23938c06f4", ID),
        ("a/fs/ax0011.png", PATH),
        ("10000.0", NUMBER),
        ("false", FLAG),
        ("SO6_GB_Cosmic_Conduit_Counter", CODE),
        ("heroLevel", CODE),
        ("melee", CODE),
    ],
)
def test_values_are_classified(value, kind):
    assert classify_value(value) == kind


def test_text_with_a_slash_is_not_a_path():
    assert classify_value("HP/Energy restored by 10") == TEXT


def test_field_names_break_ties():
    assert classify_field("dispName", ["MYSTIQUE", "HOGUN"]) == NAME
    assert classify_field("className", ["SpawnStatus", "Gear"]) == CODE
    assert classify_field("iconAssetId", ["a/fs/Amulet of Ashake Action I", "a/fs/x.png"]) in (PATH, CODE)


@pytest.fixture
def characters(tmp_path):
    path = tmp_path / "characters.xml"
    path.write_text(CHARACTERS, encoding="utf-8")
    ok, index = indexar_xml(str(path))
    assert ok
    return path, index


def test_generic_plan_selects_text_tags_and_hides_technical_ones(characters):
    _path, index = characters
    plans = {p.tag: p for p in plan(index, GENERIC)}

    villain = plans["baseVillain"]
    roles = {f.tag: f.role for f in villain.fields}
    assert villain.selected
    assert roles["bio"] == TRANSLATE and roles["dispName"] == TRANSLATE
    assert roles["id"] == IGNORE and roles["iconAssetId"] == IGNORE

    action = plans["action"]
    assert action.selected and {f.tag: f.role for f in action.fields}["id"] == IGNORE
    assert not plans["villainAction"].selected
    assert not plans["villainAction"].useful


def test_maa_profile_turns_internal_names_into_context(characters, tmp_path):
    _path, index = characters
    (tmp_path / "MAA Redux_Data").mkdir()
    assert profile_for(str(tmp_path)) is MAA_REDUX
    villain = next(p for p in plan(index, MAA_REDUX) if p.tag == "baseVillain")
    assert {f.tag: f.role for f in villain.fields}["name"] == CONTEXT
    assert villain.group() == Group.of("baseVillain", ["bio", "dispName"], ["name"])


def test_single_group_checkpoint_keeps_the_old_name(characters):
    path, _index = characters
    old = TranslationProject.checkpoint_path(
        str(path), "pt", "ck", parent_tag="action", target_tags=["dispName"], portable=True
    )
    new = TranslationProject.checkpoint_path(
        str(path), "pt", "ck", portable=True, groups=[Group.of("action", ["dispName"])]
    )
    assert old == new


@pytest.fixture
def client(tmp_path, monkeypatch, characters):
    monkeypatch.setenv("STZ_XML_TRANSLATOR_DATA_DIR", str(tmp_path / "data"))
    session = Session()
    return TestClient(create_app(session, TOKEN), headers={"Authorization": f"Bearer {TOKEN}"})


def test_analyze_and_load_several_tags_at_once(client, characters):
    path, _index = characters
    assert client.post("/api/xml/open", json={"path": str(path)}).status_code == 200
    analysis = client.get("/api/xml/analyze").json()
    selected = [t for t in analysis["tags"] if t["selected"]]
    assert [t["tag"] for t in selected] == ["baseVillain", "action"]

    groups = [
        {
            "parent": t["tag"],
            "targets": [f["tag"] for f in t["fields"] if f["role"] == "translate"],
            "contexts": [f["tag"] for f in t["fields"] if f["role"] == "context"],
        }
        for t in selected
    ]
    preview = client.post("/api/xml/preview-groups", json={"groups": groups}).json()
    assert preview["lines"] == 8  # bio, dispName, name of 2 villains + 2 action names
    assert [record["tag"] for record in preview["sample"]] == ["baseVillain", "action"]
    # The action sample is one that has text, not the first record.
    assert any(f["tag"] == "dispName" for f in preview["sample"][1]["fields"])

    assert client.post("/api/xml/load", json={"groups": groups}).json()["count"] == 8
    state = client.get("/api/state").json()
    assert [g["parent"] for g in state["structure"]["groups"]] == ["baseVillain", "action"]

    # The multi-tag selection has its own checkpoint, which survives a reload.
    entry = next(e for e in client.get("/api/entries").json()["entries"] if e["original"] == "Mindbender")
    client.post("/api/entries/edit", json={"id": entry["id"], "text": "Dobra-mentes"})
    client.post("/api/xml/close")
    client.post("/api/xml/open", json={"path": str(path)})
    assert client.post("/api/xml/load", json={"groups": groups}).json()["restored"] == 1


def test_old_single_tag_projects_still_load(tmp_path):
    from core.workspace import Project

    project = Project.from_json(
        {
            "id": "abc",
            "name": "Old",
            "folder": str(tmp_path),
            "target": "pt_BR",
            "selections": {"items.xml": {"parent": "item", "targets": ["description"], "contexts": ["name"]}},
        }
    )
    assert project.selections["items.xml"] == [Group.of("item", ["description"], ["name"])]
    assert json.loads(json.dumps(project.to_json()))["selections"]["items.xml"][0]["parent"] == "item"
