import json

from engine.__main__ import publish_runtime, remove_runtime, runtime_path


def test_shell_runtime_records_are_isolated(tmp_path, monkeypatch):
    first = tmp_path / "first" / "runtime.json"
    second = tmp_path / "second" / "runtime.json"
    monkeypatch.setenv("STZ_XML_RUNTIME_FILE", str(first))
    assert runtime_path() == first
    publish_runtime(1234, "first-session")
    monkeypatch.setenv("STZ_XML_RUNTIME_FILE", str(second))
    publish_runtime(5678, "second-session")
    remove_runtime("first-session")
    assert first.exists()
    assert json.loads(second.read_text())["port"] == 5678
    remove_runtime("second-session")
    assert not second.exists()
    assert first.exists()
