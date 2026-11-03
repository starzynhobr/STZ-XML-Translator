"""Move a project to a new build of the game without losing its translation.

Every text of the new build is matched against what the project already has:

* **kept**    same place, same original: the translation still applies.
* **moved**   the same original now lives somewhere else (records added or
  reordered): its translation is reused at the new place, "to review".
* **changed** same place, the developers reworded the original (still similar):
  the previous translation stays as "to review", so it is checked, not redone.
  A completely different text at that place is a record that moved in: new.
* **new**     nothing to reuse: pending.

After applying, the new build's XMLs become the project's originals and its
game folder, so files open from the new texts from then on.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from core.extrator import Group, extract_groups, indexar_xml
from core.game_profiles import GameProfile, plan, suggested_groups
from core.store import EntryState, TranslationStore
from core.workspace import Project, xml_files

REVIEW = "translated"
# How alike an old and a new original at the same place must be to count as "changed".
SIMILARITY = 0.6


def similar(old: str, new: str) -> bool:
    return SequenceMatcher(None, old.casefold(), new.casefold()).ratio() >= SIMILARITY


@dataclass
class FileUpdate:
    rel: str
    groups: list[Group] = field(default_factory=list)
    kept: int = 0
    changed: int = 0
    moved: int = 0
    new: int = 0
    removed: int = 0
    rows: list[EntryState] = field(default_factory=list)

    def to_json(self) -> dict:
        return {"file": self.rel, "kept": self.kept, "changed": self.changed, "moved": self.moved,
                "new": self.new, "removed": self.removed}


def compare_build(
    project: Project,
    new_folder: str,
    profile: GameProfile,
    store: TranslationStore,
    lang: str,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[FileUpdate]:
    results = []
    files = xml_files(new_folder)
    for done, rel in enumerate(files):
        if on_progress:
            on_progress(done, len(files))
        ok, index = indexar_xml(os.path.join(new_folder, rel))
        if not ok or isinstance(index, str):
            continue
        groups = project.selections.get(rel) or suggested_groups(plan(index, profile))
        item = FileUpdate(rel, list(groups))
        results.append(item)
        if not groups:
            continue
        ok, entries = extract_groups(index, groups)
        if not ok or isinstance(entries, str):
            continue
        old = store.load(f"{project.id}:{rel}", lang)
        by_original = {}
        for xpath, row in old.items():
            if row.translation.strip():
                by_original.setdefault(row.original, row)
        seen = set()
        for entry in entries:
            seen.add(entry.xpath)
            row = old.get(entry.xpath)
            if row and row.original == entry.original:
                item.kept += 1
            elif (match := by_original.get(entry.original)) is not None:
                item.moved += 1
                item.rows.append(EntryState(entry.xpath, entry.original, match.translation, REVIEW, source="update"))
            elif row and row.translation.strip() and similar(row.original, entry.original):
                # A reworded text at the same place; a different one is a record that moved in.
                item.changed += 1
                item.rows.append(EntryState(entry.xpath, entry.original, row.translation, REVIEW, source="update"))
            else:
                item.new += 1
                if row is None:
                    item.rows.append(EntryState(entry.xpath, entry.original, "", "pending"))
        item.removed = sum(1 for xpath, row in old.items() if xpath not in seen and row.translation.strip())
    return results


def store_update(store: TranslationStore, project: Project, lang: str, results: list[FileUpdate]) -> int:
    saved = 0
    for item in results:
        if item.rows:
            store.save(f"{project.id}:{item.rel}", lang, item.rows, "update")
            saved += sum(1 for row in item.rows if row.translation)
    return saved
