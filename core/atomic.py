from __future__ import annotations

import json
import os


def write_text_atomic(path: str, text: str, *, encoding: str = "utf-8") -> None:
    """Write a file so a crash mid-write never leaves it truncated.

    The content goes to a sibling temp file first and replaces the target in
    one step; readers see either the old file or the complete new one.
    """
    temp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(temp, "w", encoding=encoding, newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    except BaseException:
        try:
            os.remove(temp)
        except OSError:
            pass
        raise


def write_json_atomic(path: str, data, *, indent: int = 2, ensure_ascii: bool = False) -> None:
    write_text_atomic(path, json.dumps(data, indent=indent, ensure_ascii=ensure_ascii))


def write_bytes_atomic(path: str, payload: bytes) -> None:
    temp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(temp, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    except BaseException:
        try:
            os.remove(temp)
        except OSError:
            pass
        raise
