"""Run the engine: ``python -m engine``.

Reserves a loopback port, publishes it with a session token in a per-user
``runtime.json`` the desktop shell reads, and serves until the shell exits.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import sys
import threading
from pathlib import Path

import uvicorn

from core.app_controller import APP_DATA_DIR_NAME

HOST = "127.0.0.1"


def runtime_path() -> Path:
    """Always under LocalAppData, even in development: the shell looks here."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / APP_DATA_DIR_NAME / "runtime.json"


def publish_runtime(port: int, token: str) -> Path:
    target = runtime_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(f".{os.getpid()}.tmp")
    temp.write_text(
        json.dumps({"pid": os.getpid(), "host": HOST, "port": port, "token": token}),
        encoding="utf-8",
    )
    os.replace(temp, target)
    return target


def remove_runtime(token: str) -> None:
    """Remove the record only while it is still ours."""
    target = runtime_path()
    try:
        if json.loads(target.read_text(encoding="utf-8")).get("token") == token:
            target.unlink()
    except (OSError, ValueError):
        pass


def _exit_with_parent(pid: int) -> None:
    """Stop when the shell that started us dies, so no engine is left behind."""
    if sys.platform != "win32" or pid <= 0:
        return
    import ctypes

    synchronize = 0x00100000
    handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        return

    def wait() -> None:
        ctypes.windll.kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)
        os._exit(0)

    threading.Thread(target=wait, daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="engine")
    parser.add_argument("--port", type=int, default=int(os.environ.get("STZ_XML_BRIDGE_PORT", "0")))
    parser.add_argument("--parent-pid", type=int, default=0)
    args = parser.parse_args(argv)

    # Imported late so `--help` stays instant and import errors are reported here.
    from engine.server import create_app
    from engine.session import Session

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((HOST, args.port))
    port = int(sock.getsockname()[1])
    # A fixed token is only for running the UI in a plain browser during development.
    token = os.environ.get("STZ_XML_BRIDGE_TOKEN") or secrets.token_urlsafe(32)

    session = Session()
    app = create_app(session, token)
    publish_runtime(port, token)
    _exit_with_parent(args.parent_pid)
    session.check_updates(automatic=True)

    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
    try:
        server.run(sockets=[sock])
    finally:
        remove_runtime(token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
