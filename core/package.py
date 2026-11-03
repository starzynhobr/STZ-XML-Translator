"""Share a translation: one file another translator can import into their project.

A package (``.stzpack``, a zip) holds one language of one game: every
translated text with its original and the glossary. Importing never overwrites
work already in the project: a text that is already translated differently is
counted as a conflict and left alone; everything comes in as "to review".
"""
from __future__ import annotations

import json
import os
import time
import zipfile

from core.store import EntryState, TranslationStore
from core.workspace import Project, xml_files

FORMAT = "stz-translation-package"
VERSION = 1


class PackageError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def export_package(store: TranslationStore, project: Project, lang: str, glossary: list[dict], path: str) -> dict:
    files: dict[str, list[list[str]]] = {}
    for rel in xml_files(project.folder):
        rows = [
            [xpath, row.original, row.translation, row.status]
            for xpath, row in store.load(f"{project.id}:{rel}", lang).items()
            if row.translation.strip() and row.status in ("translated", "confirmed")
        ]
        if rows:
            files[rel] = rows
    manifest = {
        "format": FORMAT,
        "version": VERSION,
        "game": project.name,
        "language": lang,
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "files": len(files),
        "texts": sum(len(rows) for rows in files.values()),
    }
    temporary = path + ".tmp"
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("translations.json", json.dumps(files, ensure_ascii=False))
        archive.writestr("glossary.json", json.dumps(glossary, ensure_ascii=False, indent=2))
    os.replace(temporary, path)
    return {"files": manifest["files"], "texts": manifest["texts"]}


def read_package(path: str) -> tuple[dict, dict, list[dict]]:
    try:
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            files = json.loads(archive.read("translations.json"))
            glossary = json.loads(archive.read("glossary.json")) if "glossary.json" in archive.namelist() else []
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        raise PackageError("package_invalid") from None
    if manifest.get("format") != FORMAT or not isinstance(files, dict):
        raise PackageError("package_invalid")
    return manifest, files, glossary if isinstance(glossary, list) else []


def import_package(store: TranslationStore, project: Project, lang: str, path: str) -> dict:
    manifest, files, glossary = read_package(path)
    if manifest.get("language") != lang:
        raise PackageError("package_language")
    imported = conflicts = unchanged = 0
    for rel, rows in files.items():
        key = f"{project.id}:{rel}"
        existing = store.load(key, lang)
        fresh = []
        for xpath, original, translation, _status in rows:
            current = existing.get(xpath)
            if current and current.original == original and current.translation.strip():
                if current.translation == translation:
                    unchanged += 1
                else:
                    conflicts += 1  # the project's own translation wins
                continue
            fresh.append(EntryState(xpath, original, translation, "translated", source="import"))
        if fresh:
            store.save(key, lang, fresh, "import")
            imported += len(fresh)
    return {"imported": imported, "conflicts": conflicts, "unchanged": unchanged,
            "game": manifest.get("game", ""), "glossary": glossary}
