"""Translation projects: a named game folder translated into one language.

A project only records where the XMLs live, the target language and the tag
selection last used for each file. The translations themselves stay in the
portable checkpoints (see ``TranslationProject.checkpoint_path``), keyed by file
name, language and selection, so a reinstalled or moved game finds its progress
and several projects over the same folder can target different languages.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field

from core.atomic import write_json_atomic
from core.extrator import Group
from core.project import TranslationProject

PROJECT_SUFFIX = ".stzproj.json"
# Deep enough for Unity's StreamingAssets/XMLs; asset trees stay out.
MAX_DEPTH = 3
MAX_FILES = 2000


def _group(data: dict) -> Group:
    return Group.of(
        str(data.get("parent", "")),
        [str(t) for t in data.get("targets", [])],
        [str(c) for c in data.get("contexts", [])],
    )


@dataclass
class Project:
    id: str
    name: str
    folder: str
    target: str
    created_at: float
    updated_at: float
    game_root: str = ""
    last_file: str = ""
    # Clean copy of the game's XMLs kept with the project (see core.importer).
    # When present, files open from here so the original is always the
    # untranslated text, even if the game folder was edited by hand.
    source_folder: str = ""
    # Record tags chosen for each file (relative path), in load order.
    selections: dict[str, list[Group]] = field(default_factory=dict)

    def to_json(self) -> dict:
        data = asdict(self)
        data["selections"] = {name: [g.to_json() for g in groups] for name, groups in self.selections.items()}
        return data

    @classmethod
    def from_json(cls, data: dict) -> Project:
        selections: dict[str, list[Group]] = {}
        for name, sel in (data.get("selections") or {}).items():
            # Version 1 stored a single tag per file as one object.
            items = [sel] if isinstance(sel, dict) else sel if isinstance(sel, list) else []
            groups = [_group(item) for item in items if isinstance(item, dict)]
            if groups:
                selections[name] = groups
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            folder=str(data["folder"]),
            target=str(data.get("target", "")),
            created_at=float(data.get("created_at", 0)),
            updated_at=float(data.get("updated_at", 0)),
            game_root=str(data.get("game_root", "")),
            source_folder=str(data.get("source_folder", "")),
            last_file=str(data.get("last_file", "")),
            selections=selections,
        )

    def relative(self, xml_path: str) -> str | None:
        """Path of ``xml_path`` inside the game or originals folder, or None when outside both."""
        for base in (self.folder, self.source_folder):
            if base and (rel := relative_to(xml_path, base)) is not None:
                return rel
        return None

    def open_path(self, rel: str) -> str:
        """The file to translate: the kept original when there is one, else the game's."""
        if self.source_folder:
            kept = os.path.join(self.source_folder, rel)
            if os.path.isfile(kept):
                return kept
        return os.path.join(self.folder, rel)


def relative_to(path: str, base: str) -> str | None:
    """``path`` relative to ``base`` with forward slashes, or None when outside it."""
    try:
        rel = os.path.relpath(os.path.abspath(path), os.path.abspath(base))
    except ValueError:  # another drive on Windows
        return None
    if rel.startswith(".."):
        return None
    return rel.replace("\\", "/")


class ProjectStore:
    def __init__(self, root: str) -> None:
        self.root = root

    def _path(self, project_id: str) -> str:
        if not project_id or any(ch in project_id for ch in "/\\.:"):
            raise KeyError(project_id)
        return os.path.join(self.root, project_id + PROJECT_SUFFIX)

    def list(self) -> list[Project]:
        if not os.path.isdir(self.root):
            return []
        projects = []
        for name in os.listdir(self.root):
            if not name.endswith(PROJECT_SUFFIX):
                continue
            try:
                with open(os.path.join(self.root, name), encoding="utf-8") as f:
                    projects.append(Project.from_json(json.load(f)))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return sorted(projects, key=lambda p: p.updated_at, reverse=True)

    def get(self, project_id: str) -> Project:
        try:
            with open(self._path(project_id), encoding="utf-8") as f:
                return Project.from_json(json.load(f))
        except (OSError, ValueError, TypeError) as exc:
            raise KeyError(project_id) from exc

    def save(self, project: Project) -> Project:
        os.makedirs(self.root, exist_ok=True)
        write_json_atomic(self._path(project.id), project.to_json(), indent=2)
        return project

    def create(self, name: str, folder: str, target: str, game_root: str = "") -> Project:
        now = time.time()
        project = Project(
            id=uuid.uuid4().hex[:12],
            name=name.strip() or os.path.basename(os.path.normpath(folder)) or "Projeto",
            folder=os.path.abspath(folder),
            target=target,
            created_at=now,
            updated_at=now,
            game_root=os.path.abspath(game_root) if game_root else "",
        )
        return self.save(project)

    def update(
        self,
        project_id: str,
        *,
        name: str | None = None,
        folder: str | None = None,
        game_root: str | None = None,
        target: str | None = None,
    ) -> Project:
        project = self.get(project_id)
        if name is not None and name.strip():
            project.name = name.strip()
        if folder is not None:
            project.folder = os.path.abspath(folder)
        if game_root is not None:
            project.game_root = os.path.abspath(game_root) if game_root else ""
        if target:
            project.target = target
        project.updated_at = time.time()
        return self.save(project)

    def delete(self, project_id: str) -> None:
        try:
            os.remove(self._path(project_id))
        except FileNotFoundError:
            pass
        shutil.rmtree(self.data_dir(project_id), ignore_errors=True)

    def data_dir(self, project_id: str) -> str:
        """Folder for a project's own files, such as its kept originals."""
        self._path(project_id)  # validates the id
        return os.path.join(self.root, project_id)

    def keep_originals(self, project_id: str, source_folder: str, groups: dict[str, list[Group]]) -> Project:
        """Record the kept originals and the tags used for files not opened yet."""
        project = self.get(project_id)
        project.source_folder = source_folder
        for rel, file_groups in groups.items():
            if file_groups and rel not in project.selections:
                project.selections[rel] = list(file_groups)
        project.updated_at = time.time()
        return self.save(project)

    def remember(
        self,
        project_id: str,
        xml_path: str,
        groups: Sequence[Group],
    ) -> Project | None:
        """Store the record tags used for a file of the project."""
        project = self.get(project_id)
        rel = project.relative(xml_path)
        if rel is None:
            return None
        project.selections[rel] = list(groups)
        project.last_file = rel
        project.updated_at = time.time()
        return self.save(project)


# Executables that ship next to a game but do not name it.
_HELPER_EXE = re.compile(r"^(unitycrashhandler|unins|setup|launcher|crashpad|vc_?redist|dxsetup|ue4prereq)", re.I)
ROOT_SEARCH_LEVELS = 6
XML_SEARCH_DEPTH = 6
XML_SEARCH_DIRS = 5000
# A picked folder whose own XMLs are fewer than 1/4 of the busiest folder's only holds strays.
STRAY_RATIO = 4
# How far up a pick without XMLs may look for the install.
MISS_CLIMB_LEVELS = 2


def _game_exes(folder: str) -> list[str]:
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    return [n for n in names if n.lower().endswith(".exe") and os.path.isfile(os.path.join(folder, n))]


def _looks_like_root(folder: str, via: str | None) -> bool:
    """Whether ``folder`` is the install. ``via`` is the child we climbed from.

    The picked folder counts when it holds an executable or a Unity data folder.
    A folder above it only counts through its Unity "<Game>_Data" folder, so a
    pick inside Downloads never makes Downloads (full of installers) the game.
    """
    if via is not None:
        return via.endswith("_Data") and any(n.lower().endswith(".exe") for n in _game_exes(folder))
    if _game_exes(folder):
        return True
    try:
        return any(n.endswith("_Data") and os.path.isdir(os.path.join(folder, n)) for n in os.listdir(folder))
    except OSError:
        return False


def _xml_folders(root: str) -> dict[str, int]:
    """XML count per folder below ``root``, bounded so a huge install stays quick."""
    counts: dict[str, int] = {}
    visited = 0
    for current, dirs, names in os.walk(root):
        visited += 1
        depth = 0 if current == root else os.path.relpath(current, root).count(os.sep) + 1
        dirs[:] = [] if depth >= XML_SEARCH_DEPTH or visited >= XML_SEARCH_DIRS else [
            d for d in dirs if not d.startswith(".")
        ]
        found = sum(1 for n in names if n.lower().endswith(".xml"))
        if found:
            counts[current] = found
    return counts


def detect_game(selected: str) -> dict | None:
    """Find the game install and its XML folder from any folder the user picked.

    The pick may be the install itself, a folder inside it (``<Game>_Data``,
    ``StreamingAssets/XMLs``) or a plain folder of XMLs. The root is the nearest
    folder at or above the pick that holds an executable or a Unity data folder;
    the XML folder is the busiest one at or below the pick, else under the root.
    """
    picked = os.path.abspath(selected)
    if not os.path.isdir(picked):
        return None
    root = picked
    current, via = picked, None
    for _ in range(ROOT_SEARCH_LEVELS):
        if _looks_like_root(current, via):
            root = current
            break
        parent = os.path.dirname(current)
        if parent == current:
            break
        current, via = parent, os.path.basename(current)

    counts = _xml_folders(root)
    if not counts and root == picked:
        # A folder without XMLs inside the install (e.g. "D3D12"): the game is
        # the nearest folder above it that looks like one and holds XMLs.
        current = picked
        for _ in range(MISS_CLIMB_LEVELS):
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
            if _looks_like_root(current, None) and (found := _xml_folders(current)):
                root, counts = current, found
                break
    below ={path: n for path, n in counts.items() if path == picked or path.startswith(picked + os.sep)}
    # Most XMLs wins (shallower on a tie), looking first under the pick: a
    # stray XML in the data folder must not hide StreamingAssets/XMLs.
    pool = below or counts
    xml_folder = max(pool, key=lambda path: (pool[path], -path.count(os.sep))) if pool else picked
    # A pick with a fair share of the XMLs stays: its subfolders are listed too.
    if counts.get(picked, 0) * STRAY_RATIO >= pool.get(xml_folder, 0):
        xml_folder = picked

    exes = [n for n in _game_exes(root) if not _HELPER_EXE.match(n)]
    name = os.path.splitext(exes[0])[0] if len(exes) == 1 else os.path.basename(os.path.normpath(root))
    return {
        "root": root,
        "xmlFolder": xml_folder,
        "name": name,
        "count": len(xml_files(xml_folder)),
    }


def xml_files(folder: str) -> list[str]:
    """XML files under ``folder`` (relative, forward slashes), shallow first."""
    found: list[str] = []
    root = os.path.abspath(folder)
    if not os.path.isdir(root):
        return found
    for current, dirs, names in os.walk(root):
        depth = 0 if current == root else os.path.relpath(current, root).count(os.sep) + 1
        dirs[:] = [] if depth >= MAX_DEPTH else sorted(d for d in dirs if not d.startswith("."))
        for name in names:
            if name.lower().endswith(".xml"):
                found.append(os.path.relpath(os.path.join(current, name), root).replace("\\", "/"))
                if len(found) >= MAX_FILES:
                    return found
    return sorted(found, key=lambda rel: (rel.count("/"), _natural(rel)))


def _natural(text: str) -> list:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def checkpoint_progress(path: str) -> dict | None:
    """Counts stored in a checkpoint without parsing the XML it belongs to."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    records = data.get("entries") if isinstance(data, dict) and "version" in data else data
    if not isinstance(records, dict):
        return None
    total = translated = confirmed = 0
    for record in records.values():
        total += 1
        text = record.get("translation") if isinstance(record, dict) else record
        status = record.get("status", "translated") if isinstance(record, dict) else "translated"
        if isinstance(text, str) and text.strip():
            translated += 1
            confirmed += status == "confirmed"
    return {"total": total, "translated": translated, "confirmed": confirmed}


def summarize(rows: Sequence[dict]) -> dict:
    """Totals over the files whose progress is known."""
    known = [row["progress"] for row in rows if row["progress"]]
    return {
        "files": len(rows),
        "started": len(known),
        "total": sum(p["total"] for p in known),
        "translated": sum(p["translated"] for p in known),
        "confirmed": sum(p["confirmed"] for p in known),
    }


def file_rows(
    project: Project,
    target_code: str,
    checkpoint_dir: str,
    progress_of: Callable[[str], dict | None] | None = None,
) -> list[dict]:
    """One row per XML in the project folder, with progress when it was opened.

    ``progress_of`` reads the database (keyed by the file's path in the
    project); the JSON checkpoint is the fallback for files not migrated yet.
    """
    rows = []
    for rel in xml_files(project.folder):
        path = project.open_path(rel)
        groups = project.selections.get(rel) or []
        progress = progress_of(rel) if progress_of else None
        if progress is None and groups:
            checkpoint = TranslationProject.checkpoint_path(
                path, target_code, checkpoint_dir, portable=True, groups=groups
            )
            progress = checkpoint_progress(checkpoint)
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        rows.append(
            {
                "path": path,
                "name": rel,
                "size": size,
                "groups": [g.to_json() for g in groups],
                "progress": progress,
            }
        )
    return rows
