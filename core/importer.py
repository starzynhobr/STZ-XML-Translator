"""Bring in translations made outside the app (by hand, in a text editor).

Someone who edited the game's XMLs directly has the translation in the game
folder but no record of what the original text was. Given a clean copy of the
same XMLs, every text that differs at the same place in the file is taken as a
translation of the clean one. The clean copy is then kept with the project, so
from that point the app always opens the untranslated original even though the
game folder holds the edited files.

Imported texts are marked "to review": if the clean copy comes from another
build, a text the developers changed would also look translated.
"""
from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field

from core.extrator import Group, extract_groups, indexar_xml
from core.game_profiles import GameProfile, plan, suggested_groups
from core.store import EntryState, TranslationStore
from core.workspace import Project, xml_files

# Imported translations need a human look before they count as reviewed.
IMPORTED_STATUS = "translated"


@dataclass
class FileComparison:
    rel: str
    groups: list[Group] = field(default_factory=list)
    texts: int = 0  # translatable texts in the clean file
    found: list[EntryState] = field(default_factory=list)
    clean: dict[str, str] = field(default_factory=dict)  # xpath -> original
    problem: str = ""  # "missing" (no clean copy) or "invalid" (unreadable XML)

    def to_json(self) -> dict:
        return {"file": self.rel, "texts": self.texts, "found": len(self.found), "problem": self.problem}


def _entries(path: str, groups: list[Group]) -> dict[str, str] | None:
    ok, index = indexar_xml(path)
    if not ok or isinstance(index, str):
        return None
    ok, entries = extract_groups(index, groups)
    if not ok or isinstance(entries, str):
        return {}
    return {entry.xpath: entry.original for entry in entries}


def compare(
    project: Project,
    clean_folder: str,
    profile: GameProfile,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[FileComparison]:
    """Per file of the project, the texts that differ from the clean copy."""
    results = []
    files = xml_files(project.folder)
    for done, rel in enumerate(files):
        if on_progress:
            on_progress(done, len(files))
        item = FileComparison(rel)
        results.append(item)
        clean_path = os.path.join(clean_folder, rel)
        if not os.path.isfile(clean_path):
            item.problem = "missing"
            continue
        groups = project.selections.get(rel)
        if not groups:
            ok, index = indexar_xml(clean_path)
            if not ok or isinstance(index, str):
                item.problem = "invalid"
                continue
            groups = suggested_groups(plan(index, profile))
        item.groups = list(groups)
        if not groups:
            continue
        clean = _entries(clean_path, item.groups)
        edited = _entries(os.path.join(project.folder, rel), item.groups)
        if clean is None or edited is None:
            item.problem = "invalid"
            continue
        item.texts = len(clean)
        item.clean = clean
        for xpath, original in clean.items():
            text = edited.get(xpath)
            if text and text != original:
                item.found.append(EntryState(xpath, original, text, IMPORTED_STATUS, source="import"))
    return results


def keep_originals(clean_folder: str, target: str, files: list[str]) -> None:
    """Copy the clean XMLs into the project, replacing any earlier copy."""
    staging = target + ".new"
    shutil.rmtree(staging, ignore_errors=True)
    for rel in files:
        source = os.path.join(clean_folder, rel)
        if os.path.isfile(source):
            destination = os.path.join(staging, rel)
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            shutil.copy2(source, destination)
    shutil.rmtree(target, ignore_errors=True)
    os.replace(staging, target)


def store_found(store: TranslationStore, project: Project, lang: str, results: list[FileComparison]) -> int:
    """Save imported texts; translations already made in the app are left alone."""
    saved = 0
    for item in results:
        if not item.found:
            continue
        key = f"{project.id}:{item.rel}"
        existing = store.load(key, lang)
        found = {entry.xpath: entry for entry in item.found}
        rows = []
        for xpath, original in item.clean.items():
            row = existing.get(xpath)
            if row and row.original == original and row.translation:
                continue  # translated in the app already
            if xpath in found:
                rows.append(found[xpath])
                saved += 1
            elif row is None:
                # Untranslated texts are recorded too, so the file's progress has its real total.
                rows.append(EntryState(xpath, original, "", "pending"))
        store.save(key, lang, rows, "import")
    return saved
