"""Put a project's translation into the game, take it back out, start the game.

Applying writes every translated file of the project into the game folder,
built from the kept originals plus the translations in the database. The first
time a game file is overwritten, the file that was there is kept aside so
"restore" can put the game back exactly as it was. Projects that never kept
originals get them now, from the game folder, before anything is written:
otherwise the next time a file opens its "original" would be the translation.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable

from core.injetor import injetar_traducoes
from core.store import TranslationStore
from core.workspace import Project, ProjectStore, _game_exes, xml_files

Progress = Callable[[int, int], None] | None
# Executables next to a game that are not the game.
_HELPERS = ("unitycrashhandler", "unins", "setup", "launcher", "crashpad", "vc_redist", "vcredist", "dxsetup")


class GameOpError(Exception):
    """A stable code the UI turns into a message."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def ensure_originals(projects: ProjectStore, project: Project) -> Project:
    """Keep a copy of the game's XMLs before the app ever writes into the game folder."""
    if project.source_folder and os.path.isdir(project.source_folder):
        return project
    target = os.path.join(projects.data_dir(project.id), "originals")
    for rel in xml_files(project.folder):
        destination = os.path.join(target, rel)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copy2(os.path.join(project.folder, rel), destination)
    return projects.keep_originals(project.id, target, {})


def translations_for(store: TranslationStore, project: Project, rel: str, lang: str, confirmed_only: bool = False) -> dict[str, str]:
    wanted = ("confirmed",) if confirmed_only else ("translated", "confirmed")
    return {
        xpath: row.translation
        for xpath, row in store.load(f"{project.id}:{rel}", lang).items()
        if row.translation.strip() and row.status in wanted
    }


def write_translated(
    store: TranslationStore,
    project: Project,
    lang: str,
    out_folder: str,
    backup_folder: str | None = None,
    confirmed_only: bool = False,
    on_progress: Progress = None,
) -> dict:
    """Write each translated file into ``out_folder``; untranslated files are left alone."""
    files = xml_files(project.folder)
    written = texts = 0
    for done, rel in enumerate(files):
        if on_progress:
            on_progress(done, len(files))
        translations = translations_for(store, project, rel, lang, confirmed_only)
        if not translations:
            continue
        source = project.open_path(rel)
        target = os.path.join(out_folder, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if backup_folder:
            kept = os.path.join(backup_folder, rel)
            # Only the first time: the backup is the game as it was before the app.
            if not os.path.exists(kept) and os.path.isfile(target):
                os.makedirs(os.path.dirname(kept), exist_ok=True)
                shutil.copy2(target, kept)
        temporary = target + ".stz-tmp"
        if not injetar_traducoes(source, translations, temporary):
            raise GameOpError("export_failed")
        os.replace(temporary, target)
        written += 1
        texts += len(translations)
    return {"files": written, "texts": texts}


def backup_folder(projects: ProjectStore, project: Project) -> str:
    return os.path.join(projects.data_dir(project.id), "game-backup")


def apply_to_game(store: TranslationStore, projects: ProjectStore, project: Project, lang: str,
                  confirmed_only: bool = False, on_progress: Progress = None) -> dict:
    if not os.path.isdir(project.folder):
        raise GameOpError("folder_not_found")
    project = ensure_originals(projects, project)
    return write_translated(store, project, lang, project.folder, backup_folder(projects, project),
                            confirmed_only, on_progress)


def restore_game(projects: ProjectStore, project: Project) -> int:
    """Put back every game file the app replaced; returns how many."""
    kept = backup_folder(projects, project)
    if not os.path.isdir(kept):
        return 0
    restored = 0
    for current, _dirs, names in os.walk(kept):
        for name in names:
            source = os.path.join(current, name)
            rel = os.path.relpath(source, kept)
            target = os.path.join(project.folder, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(source, target)
            restored += 1
    shutil.rmtree(kept, ignore_errors=True)
    return restored


def has_backup(projects: ProjectStore, project: Project) -> bool:
    return os.path.isdir(backup_folder(projects, project))


def game_executable(project: Project) -> str | None:
    root = project.game_root
    if not root or not os.path.isdir(root):
        return None
    candidates = [name for name in _game_exes(root) if not name.lower().startswith(_HELPERS)]
    if not candidates:
        return None
    # Prefer the one named like the Unity data folder ("MAA Redux_Data" -> "MAA Redux.exe").
    data = {name[: -len("_Data")].lower() for name in os.listdir(root) if name.endswith("_Data")}
    candidates.sort(key=lambda name: (os.path.splitext(name)[0].lower() not in data, name.lower()))
    return os.path.join(root, candidates[0])


def launch_game(project: Project) -> str:
    executable = game_executable(project)
    if executable is None:
        raise GameOpError("no_game_exe")
    subprocess.Popen([executable], cwd=os.path.dirname(executable), close_fds=True)  # noqa: S603
    return os.path.basename(executable)
