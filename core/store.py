"""SQLite storage for translations and their history.

One database holds every file the user translates. A file is identified by a
stable key (the project and the file's path inside it, or just the file name
outside a project), so moving or reinstalling a game keeps its progress. Each
entry is stored with its original text: a translation is only applied while the
original still matches, which keeps a newer game build from inheriting
translations of texts that changed.

Every change of text or status is appended to ``history`` with where it came
from (AI, manual edit, confirmation, import), so nothing is lost when a
translation is overwritten and any version can be restored.

The JSON checkpoints are still written next to it as a portable backup; the
first time a file is opened its JSON progress is imported here.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY,
    key TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS translations (
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    lang TEXT NOT NULL,
    xpath TEXT NOT NULL,
    original TEXT NOT NULL,
    translation TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    error_code TEXT NOT NULL DEFAULT '',
    updated_at REAL NOT NULL,
    PRIMARY KEY (file_id, lang, xpath)
);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    lang TEXT NOT NULL,
    xpath TEXT NOT NULL,
    original TEXT NOT NULL,
    old_text TEXT NOT NULL,
    new_text TEXT NOT NULL,
    old_status TEXT NOT NULL,
    new_status TEXT NOT NULL,
    source TEXT NOT NULL,
    at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS history_entry ON history (file_id, lang, xpath, at);
CREATE INDEX IF NOT EXISTS translation_memory ON translations (lang, original);
"""

# Where a change came from; shown next to each version in the history.
SOURCES = frozenset({"ai", "manual", "confirm", "import", "reset", "edit", "memory", "agent"})


def _like(text: str) -> str:
    """A LIKE pattern that matches ``text`` literally anywhere."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _like_prefix(prefix: str) -> str:
    escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"{escaped}%"


@dataclass(frozen=True)
class StoredRow:
    original: str
    translation: str
    status: str
    error_code: str


@dataclass(frozen=True)
class EntryState:
    xpath: str
    original: str
    translation: str
    status: str
    error_code: str = ""
    source: str = ""


class TranslationStore:
    def __init__(self, path: str) -> None:
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        # The engine serves requests from several threads; one connection, one lock.
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._lock = threading.RLock()
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA foreign_keys=ON")
            self._db.executescript(SCHEMA)
            self._db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ------------------------------------------------------------------

    def _file_id(self, key: str, create: bool) -> int | None:
        row = self._db.execute("SELECT id FROM files WHERE key = ?", (key,)).fetchone()
        if row:
            return int(row[0])
        if not create:
            return None
        return int(self._db.execute("INSERT INTO files (key) VALUES (?)", (key,)).lastrowid)

    def has(self, key: str, lang: str) -> bool:
        with self._lock:
            file_id = self._file_id(key, create=False)
            if file_id is None:
                return False
            row = self._db.execute(
                "SELECT 1 FROM translations WHERE file_id = ? AND lang = ? LIMIT 1", (file_id, lang)
            ).fetchone()
            return row is not None

    def load(self, key: str, lang: str) -> dict[str, StoredRow]:
        with self._lock:
            file_id = self._file_id(key, create=False)
            if file_id is None:
                return {}
            rows = self._db.execute(
                "SELECT xpath, original, translation, status, error_code FROM translations"
                " WHERE file_id = ? AND lang = ?",
                (file_id, lang),
            ).fetchall()
        return {xpath: StoredRow(original, text, status, error) for xpath, original, text, status, error in rows}

    def save(self, key: str, lang: str, entries: Iterable[EntryState], default_source: str = "edit") -> int:
        """Write entries that changed and log each change. Returns how many changed."""
        now = time.time()
        with self._lock:
            file_id = self._file_id(key, create=True)
            current = {
                xpath: (original, text, status)
                for xpath, original, text, status in self._db.execute(
                    "SELECT xpath, original, translation, status FROM translations WHERE file_id = ? AND lang = ?",
                    (file_id, lang),
                )
            }
            upserts = []
            changes = []
            for entry in entries:
                before = current.get(entry.xpath)
                if before == (entry.original, entry.translation, entry.status):
                    continue
                upserts.append(
                    (file_id, lang, entry.xpath, entry.original, entry.translation, entry.status, entry.error_code, now)
                )
                old_text, old_status = (before[1], before[2]) if before and before[0] == entry.original else ("", "pending")
                if (old_text, old_status) != (entry.translation, entry.status) and (old_text or entry.translation):
                    changes.append(
                        (file_id, lang, entry.xpath, entry.original, old_text, entry.translation, old_status,
                         entry.status, entry.source or default_source, now)
                    )
            if not upserts:
                return 0
            self._db.execute("BEGIN")
            try:
                self._db.executemany(
                    "INSERT INTO translations (file_id, lang, xpath, original, translation, status, error_code, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT (file_id, lang, xpath) DO UPDATE SET original = excluded.original,"
                    " translation = excluded.translation, status = excluded.status,"
                    " error_code = excluded.error_code, updated_at = excluded.updated_at",
                    upserts,
                )
                self._db.executemany(
                    "INSERT INTO history (file_id, lang, xpath, original, old_text, new_text, old_status, new_status, source, at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    changes,
                )
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
            return len(upserts)

    def history(self, key: str, lang: str, xpath: str, limit: int = 50) -> list[dict]:
        with self._lock:
            file_id = self._file_id(key, create=False)
            if file_id is None:
                return []
            rows = self._db.execute(
                "SELECT old_text, new_text, old_status, new_status, source, at FROM history"
                " WHERE file_id = ? AND lang = ? AND xpath = ? ORDER BY at DESC, id DESC LIMIT ?",
                (file_id, lang, xpath, limit),
            ).fetchall()
        return [
            {"oldText": o, "newText": n, "oldStatus": os_, "newStatus": ns, "source": s, "at": at}
            for o, n, os_, ns, s, at in rows
        ]

    def search(self, key_prefix: str, lang: str, query: str, limit: int = 200) -> list[dict]:
        """Entries of every file whose key starts with ``key_prefix`` matching ``query``.

        Matches the original or the translation, case-insensitively for ASCII.
        """
        needle = query.strip()
        if not needle:
            return []
        pattern = _like(needle)
        with self._lock:
            rows = self._db.execute(
                "SELECT f.key, t.xpath, t.original, t.translation, t.status FROM translations t"
                " JOIN files f ON f.id = t.file_id"
                " WHERE f.key LIKE ? ESCAPE '\\' AND t.lang = ?"
                " AND (t.original LIKE ? ESCAPE '\\' OR t.translation LIKE ? ESCAPE '\\')"
                " ORDER BY f.key, t.rowid LIMIT ?",
                (_like_prefix(key_prefix), lang, pattern, pattern, limit),
            ).fetchall()
        return [
            {"key": key, "xpath": xpath, "original": original, "translation": text, "status": status}
            for key, xpath, original, text, status in rows
        ]

    def memory(self, lang: str, original: str, limit: int = 5) -> list[dict]:
        """Translations already given to this exact original anywhere, confirmed first."""
        with self._lock:
            rows = self._db.execute(
                "SELECT translation, MAX(status = 'confirmed') AS confirmed, COUNT(*) AS uses"
                " FROM translations WHERE lang = ? AND original = ? AND translation != ''"
                " AND status IN ('translated', 'confirmed')"
                " GROUP BY translation ORDER BY confirmed DESC, uses DESC LIMIT ?",
                (lang, original, limit),
            ).fetchall()
        return [{"translation": text, "confirmed": bool(confirmed), "uses": int(uses)} for text, confirmed, uses in rows]

    def progress(self, key: str, lang: str) -> dict | None:
        with self._lock:
            file_id = self._file_id(key, create=False)
            if file_id is None:
                return None
            total, translated, confirmed = self._db.execute(
                "SELECT COUNT(*), SUM(translation != ''), SUM(status = 'confirmed' AND translation != '')"
                " FROM translations WHERE file_id = ? AND lang = ?",
                (file_id, lang),
            ).fetchone()
        if not total:
            return None
        return {"total": int(total), "translated": int(translated or 0), "confirmed": int(confirmed or 0)}
