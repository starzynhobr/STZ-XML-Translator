"""End to end: the real engine process, over real HTTP, against a fake Ollama.

Nothing is mocked inside the engine. It is started the way the desktop shell
starts it, found through its runtime.json, and translates by calling a local
server that stands in for Ollama. This is the path a release has to survive.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import requests

REPO = Path(__file__).resolve().parents[1]
XML = """<?xml version="1.0" encoding="UTF-8"?>
<!-- game data -->
<items>
\t<item id="1" rarity="rare">
\t\t<name>Ember Blade</name>
\t\t<description>A short sword.</description>
\t\t<icon>a/blade.png</icon>
\t</item>
\t<item id="2" rarity="epic">
\t\t<name>Frost Shield</name>
\t\t<description><![CDATA[Blocks <b>fire</b>.]]></description>
\t\t<icon>a/shield.png</icon>
\t</item>
\t<item id="3" rarity="common">
\t\t<name>Iron Hatchet</name>
\t\t<description>A Blade for wood.</description>
\t\t<icon>a/hatchet.png</icon>
\t</item>
</items>
"""


class FakeOllama(BaseHTTPRequestHandler):
    """Answers /api/generate by prefixing every text with [PT]."""

    requests_seen: list[dict] = []

    def do_POST(self):  # noqa: N802 (http.server naming)
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.requests_seen.append(body)
        prompt = body["prompt"]
        if '"inputs"' in prompt:
            payload = json.loads(prompt[prompt.index("Input: ") + 7 : prompt.rindex("[/INST]")])
            answer = {"translations": [f"[PT] {item['text']}" for item in payload["inputs"]]}
        else:
            payload = json.loads(prompt[prompt.index("Input:\n") + 7 : prompt.index("\n\nOutput:")])
            answer = {"text": f"[PT] {payload['text']}"}
        data = json.dumps({"response": json.dumps(answer)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args):
        pass


@pytest.fixture
def fake_ollama():
    FakeOllama.requests_seen = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def pid_alive(pid: int) -> bool:
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    import ctypes

    handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not handle:
        return False
    try:
        return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == 0x102  # WAIT_TIMEOUT
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


class Engine:
    def __init__(self, home: Path, ollama: str, extra_args: tuple[str, ...] = ()):
        self.home = home
        env = {
            **os.environ,
            "STZ_XML_TRANSLATOR_DATA_DIR": str(home / "data"),
            # runtime.json goes under LocalAppData: keep it out of the real one.
            "LOCALAPPDATA": str(home / "local"),
            "OLLAMA_HOST": ollama,
            "PYTHONIOENCODING": "utf-8",
        }
        env.pop("STZ_XML_BRIDGE_TOKEN", None)
        env.pop("STZ_XML_BRIDGE_PORT", None)
        runtime = home / "local" / "STZ XML Translator" / "runtime.json"
        # The shell removes a previous run's record before starting the engine.
        runtime.unlink(missing_ok=True)
        self.process = subprocess.Popen(
            [sys.executable, "-m", "engine", *extra_args],
            cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        deadline = time.time() + 30
        while not runtime.exists():
            if self.process.poll() is not None or time.time() > deadline:
                raise AssertionError("engine did not start: " + self.process.stderr.read().decode(errors="replace"))
            time.sleep(0.05)
        info = json.loads(runtime.read_text(encoding="utf-8"))
        # A venv's python.exe is a launcher: the engine is its child, with its own pid.
        self.pid = info["pid"]
        self.base = f"http://{info['host']}:{info['port']}"
        self.headers = {"Authorization": f"Bearer {info['token']}"}

    def call(self, method: str, path: str, body=None, expect: int = 200):
        response = requests.request(method, self.base + path, json=body, headers=self.headers, timeout=20)
        assert response.status_code == expect, response.text
        return response.json()

    def wait_idle(self) -> dict:
        deadline = time.time() + 30
        while time.time() < deadline:
            state = self.call("GET", "/api/state")
            if not state["translating"] and not state["translatingEntries"] and not state["xmlBusy"]:
                return state
            time.sleep(0.05)
        raise AssertionError("engine never became idle")

    def alive(self) -> bool:
        return pid_alive(self.pid)

    def stop(self) -> None:
        for pid in {self.pid, self.process.pid}:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)
        self.process.wait(timeout=10)


@pytest.fixture
def home(tmp_path):
    xml = tmp_path / "items.xml"
    xml.write_text(XML, encoding="utf-8", newline="\n")
    return tmp_path


STRUCTURE = {"parent": "item", "targets": ["description"], "contexts": ["name"]}


def test_full_flow_from_open_to_export_and_restart(home, fake_ollama):
    xml = home / "items.xml"
    engine = Engine(home, fake_ollama)
    try:
        # The bridge is closed to anyone without the session token.
        assert requests.get(engine.base + "/api/state", timeout=10).status_code == 401

        opened = engine.call("POST", "/api/xml/open", {"path": str(xml)})
        assert opened["parents"] == [{"tag": "item", "count": 3}]
        assert engine.call("GET", "/api/xml/children?parent=item")["tags"] == ["name", "description", "icon"]
        assert engine.call("POST", "/api/xml/preview", STRUCTURE)["lines"] == 3
        assert engine.call("POST", "/api/xml/load", STRUCTURE) == {"count": 3, "restored": 0}

        engine.call("PUT", "/api/settings", {"provider": "Ollama (Local)"})
        engine.call("PUT", "/api/glossary", {"terms": [{"original": "Blade", "translation": "Lâmina"}]})

        entries = engine.call("GET", "/api/entries")["entries"]
        first, second, third = (entry["id"] for entry in entries)

        # One entry on its own, then the rest as a batch.
        engine.call("POST", "/api/entries/translate", {"id": first})
        engine.wait_idle()
        engine.call("POST", "/api/translate", {})
        state = engine.wait_idle()
        assert state["counts"]["translated"] == 3
        assert state["counts"]["error"] == 0

        by_id = {entry["id"]: entry for entry in engine.call("GET", "/api/entries")["entries"]}
        assert by_id[first]["translation"] == "[PT] A short sword."
        assert by_id[second]["translation"] == "[PT] Blocks <b>fire</b>."
        # The glossary term went out as a token and came back as the fixed translation.
        assert by_id[third]["translation"] == "[PT] A Lâmina for wood."
        assert all("Blade" not in json.dumps(seen) or "A Blade" not in seen["prompt"] for seen in FakeOllama.requests_seen)

        # Review: confirm one, rewrite another.
        engine.call("POST", "/api/entries/confirm", {"id": first})
        engine.call("POST", "/api/entries/edit", {"id": third, "text": "Um machado para madeira."})
        assert engine.call("POST", "/api/entries/confirm", {"id": third, "text": ""}, expect=400) == {"error": "empty_translation"}

        out = home / "out.xml"
        engine.call("POST", "/api/xml/export", {"path": str(out)})
    finally:
        engine.stop()

    # Only the three descriptions changed; layout, comment and CDATA are intact.
    expected = (
        XML.replace("A short sword.", "[PT] A short sword.")
        .replace("Blocks <b>fire</b>.", "[PT] Blocks <b>fire</b>.")
        .replace("A Blade for wood.", "Um machado para madeira.")
    )
    assert out.read_bytes() == expected.encode("utf-8")
    assert ET.parse(out).getroot().find("item/name").text == "Ember Blade"

    # A new process picks the work up from the checkpoint.
    restarted = Engine(home, fake_ollama)
    try:
        restarted.call("POST", "/api/xml/open", {"path": str(xml)})
        assert restarted.call("POST", "/api/xml/load", STRUCTURE) == {"count": 3, "restored": 3}
        statuses = [entry["status"] for entry in restarted.call("GET", "/api/entries")["entries"]]
        assert statuses == ["confirmed", "translated", "translated"]
        assert restarted.call("GET", "/api/state")["settings"]["provider"] == "Ollama (Local)"
    finally:
        restarted.stop()


def test_provider_failure_is_reported_and_never_exported(home):
    xml = home / "items.xml"
    # Nothing listens here: every request to "Ollama" fails.
    engine = Engine(home, "http://127.0.0.1:9")
    try:
        engine.call("POST", "/api/xml/open", {"path": str(xml)})
        engine.call("POST", "/api/xml/load", STRUCTURE)
        engine.call("PUT", "/api/settings", {"provider": "Ollama (Local)"})
        engine.call("POST", "/api/translate", {})
        state = engine.wait_idle()
        assert state["counts"]["translated"] == 0
        assert state["counts"]["error"] >= 1
        entries = engine.call("GET", "/api/entries")["entries"]
        assert all(entry["translation"] == "" for entry in entries)
        failed = next(entry for entry in entries if entry["status"] == "error")
        assert failed["error"]
        # With nothing translated there is nothing to export.
        engine.call("POST", "/api/xml/export", {"path": str(home / "out.xml")}, expect=500)
        assert not (home / "out.xml").exists()
    finally:
        engine.stop()


def test_engine_exits_when_the_shell_that_started_it_dies(home, fake_ollama):
    if sys.platform != "win32":
        pytest.skip("the parent watchdog is Windows-only")
    shell = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    engine = Engine(home, fake_ollama, ("--parent-pid", str(shell.pid)))
    try:
        assert engine.alive()
        shell.kill()
        shell.wait(timeout=10)
        deadline = time.time() + 10
        while engine.alive() and time.time() < deadline:
            time.sleep(0.1)
        assert not engine.alive(), "the engine outlived its shell"
    finally:
        if shell.poll() is None:
            shell.kill()
        engine.stop()
