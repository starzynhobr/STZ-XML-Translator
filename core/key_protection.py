"""API keys at rest, protected with Windows DPAPI.

DPAPI ties the ciphertext to the Windows user account: another user, or a copy
of the config file on another machine, cannot read the keys. It needs no
password and no extra dependency. Where DPAPI is not available (non-Windows),
callers keep the keys in plain text as before.
"""
from __future__ import annotations

import base64
import sys

# Only this app's own entropy can decrypt its blobs, even for the same user.
_ENTROPY = b"STZ XML Translator api keys v1"


def available() -> bool:
    return sys.platform == "win32"


def _crypt(function_name: str, payload: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(data: bytes) -> Blob:
        buffer = ctypes.create_string_buffer(data, len(data))
        return Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))

    source, entropy, result = blob(payload), blob(_ENTROPY), Blob()
    function = getattr(ctypes.windll.crypt32, function_name)
    # CRYPTPROTECT_UI_FORBIDDEN: never show a prompt from a background thread.
    if not function(ctypes.byref(source), None, ctypes.byref(entropy), None, None, 0x1, ctypes.byref(result)):
        raise OSError(f"{function_name} failed")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(result.pbData)


def protect(secret: str) -> str:
    """Encrypt a secret for the current Windows user; returns base64 text."""
    return base64.b64encode(_crypt("CryptProtectData", secret.encode("utf-8"))).decode("ascii")


def unprotect(token: str) -> str:
    """Decrypt a value written by ``protect``. Raises OSError/ValueError when it cannot."""
    return _crypt("CryptUnprotectData", base64.b64decode(token, validate=True)).decode("utf-8")
