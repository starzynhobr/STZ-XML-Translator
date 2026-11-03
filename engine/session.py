"""Qt-free application session used by the HTTP bridge.

It plays the role ``ui/viewmodel.py`` plays for QML: it owns one
``AppController``, runs slow work on daemon threads, and exposes plain
JSON-able snapshots. The web UI polls ``state()`` and asks ``entries()`` only
for what changed since the revision it already has.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import threading
import time
from collections.abc import Callable, Sequence

import requests

from core import gemini_batch, updater
from core.app_controller import PROVIDER_URLS, AppController, user_data_dir, user_data_path
from core.atomic import write_json_atomic
from core.build_update import compare_build, store_update
from core.extrator import Group, XmlDocumentIndex, _local_name, extract_groups, indexar_xml
from core.game_ops import (
    GameOpError,
    apply_to_game,
    game_executable,
    has_backup,
    launch_game,
    restore_game,
    write_translated,
)
from core.game_profiles import GENERIC, GameProfile, TagPlan, plan, profile_for, suggested_groups
from core.i18n import I18nManager
from core.importer import compare, keep_originals, store_found
from core.package import PackageError, export_package, import_package
from core.project import EntryStatus, TranslationProject
from core.tradutor_api import carregar_glossario, glossary_filename, list_gemini_models
from core.translation_worker import GEMINI_RPM, TranslationWorker
from core.version import app_version
from core.workspace import Project, ProjectStore, detect_game, file_rows, summarize, xml_files

PREFS_FILE = "ui_prefs.json"
FEEDBACK_URL = "https://stzlabs.com/api/feedback/stz-xml-translator"
FEEDBACK_MIN, FEEDBACK_MAX = 10, 400
FEEDBACK_API_MAX = 500
UPDATE_INTERVAL_SECONDS = 24 * 60 * 60
LOG_KEPT = 200

KEYLESS_PROVIDERS = frozenset({"Google Translate (Free)", "Ollama (Local)", "Llama 3 (Local)"})
AI_PROVIDERS = frozenset({"Gemini", "Ollama (Local)", "Llama 3 (Local)"})
# "Llama 3 (Local)" is a legacy alias of the Ollama service: keep it working
# for configs that still name it, but don't offer it as a separate choice.
LEGACY_PROVIDERS = frozenset({"Llama 3 (Local)"})
THEMES = ("dark", "light", "system")
ACCENTS = ("teal", "blue", "amber")
DEFAULT_PREFS = {"theme": "dark", "accent": "teal", "auto_update": True}
DEFAULT_MODELS: dict[str, tuple[str, int, bool]] = {
    "Gemini Flash Lite Latest": ("models/gemini-flash-lite-latest", 60, False),
    "Gemini Flash Latest": ("models/gemini-flash-latest", 60, False),
}


_LAST_SEGMENT = re.compile(r"(?:\*\[local-name\(\)='([^']+)'\]|([^/\[]+))(?:\[\d+\])?$")


def _record_tag(container_xpath: str) -> str:
    """The record tag an entry belongs to: the last step of its container's XPath."""
    match = _LAST_SEGMENT.search(container_xpath or "")
    return (match.group(1) or match.group(2)) if match else ""


class SessionError(Exception):
    """A request the session refused; ``code`` is a stable machine name."""

    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


class Session:
    def __init__(self) -> None:
        self.ctrl = AppController()
        self.i18n = I18nManager(language=self.ctrl.preferred_locale)
        self.ctrl.set_translation_target(
            self.ctrl.preferred_translation_target or self.ctrl.preferred_locale
        )
        self._lock = threading.RLock()

        # Revisions let the UI fetch only the entries that changed.
        self._rev = 1
        self._full_rev = 1
        self._entry_rev: dict[str, int] = {}

        self._xml_path = ""
        self._parents: list[str] = []
        self._xml_busy = False
        self._translating = False
        self._single: set[str] = set()
        self._log: list[dict] = []

        self.projects = ProjectStore(user_data_path("projects"))
        self._project = None
        self._import: dict = {"status": "idle"}
        self._job: dict = {"status": "idle"}
        self._job_cancel = threading.Event()
        self._job_worker = None
        self._build_update: dict | None = None
        self._import_results: list = []
        self._plans: list[TagPlan] = []
        self._plans_key: tuple | None = None

        self._models = dict(DEFAULT_MODELS)
        self._model_label = next(iter(self._models))
        if self.ctrl.preferred_model_label in self._models:
            self._model_label = self.ctrl.preferred_model_label

        self.prefs = self._load_prefs()
        self._release: updater.ReleaseInfo | None = None
        self._update = {"status": "idle", "error": "", "progress": 0, "installer": ""}

        if self.ctrl.preferred_provider == "Gemini" and self.ctrl.api_key:
            self._spawn(self._fetch_models)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _spawn(target, *args) -> None:
        threading.Thread(target=target, args=args, daemon=True).start()

    def _bump(self, xpath: str | None = None) -> None:
        with self._lock:
            self._rev += 1
            if xpath is None:
                self._full_rev = self._rev
            else:
                self._entry_rev[xpath] = self._rev

    def log(self, message: str, level: str = "info") -> None:
        with self._lock:
            self._log.append({"at": time.time(), "text": message, "level": level})
            del self._log[:-LOG_KEPT]
            self._rev += 1

    def _require_idle(self) -> None:
        if self._xml_busy or self._translating or self._single:
            raise SessionError("busy", 409)

    def _require_project(self) -> None:
        if not self.ctrl.project.xml_path:
            raise SessionError("no_file", 409)

    def _save_config(self, *, api_key: str = "", provider: str = "", ollama_model: str = "") -> None:
        self.ctrl.save_config(
            api_key=api_key,
            model_label=self._model_label,
            model_id=self._models.get(self._model_label, (self.ctrl.preferred_model_id,))[0],
            provider=provider,
            ollama_model=ollama_model,
        )

    def _persist(self) -> None:
        if self.ctrl.project.xml_path:
            self.ctrl.project.save_checkpoint(self.ctrl.current_checkpoint_path())

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def state(self) -> dict:
        project = self.ctrl.project
        with self._lock:
            last = self._log[-1] if self._log else None
            return {
                "version": app_version(),
                "rev": self._rev,
                "file": (
                    {"path": self._xml_path, "name": os.path.basename(self._xml_path)}
                    if self._xml_path
                    else None
                ),
                "parents": list(self._parents),
                "structure": (
                    {
                        "parent": project.parent_tag,
                        "targets": list(project.target_tags),
                        "contexts": list(project.context_tags),
                        "groups": [g.to_json() for g in project.groups],
                    }
                    if project.xml_path
                    else None
                ),
                "project": (
                    {"id": self._project.id, "name": self._project.name, "folder": self._project.folder}
                    if self._project
                    else None
                ),
                "loaded": bool(project.xml_path),
                "total": len(project.entries),
                "counts": project.state_counts(),
                "xmlBusy": self._xml_busy,
                "translating": self._translating,
                "translatingEntries": sorted(self._single),
                "activity": last,
                "log": self._log[-50:],
                "settings": self.settings(),
                "update": self.update_state(),
                "import": dict(self._import),
                "job": dict(self._job),
            }

    def entries(self, since: int = 0) -> dict:
        project = self.ctrl.project
        with self._lock:
            full = since < self._full_rev
            rev = self._rev
            changed = None if full else {x for x, r in self._entry_rev.items() if r > since}
        items = []
        for number, entry in enumerate(list(project.entries.values()), start=1):
            if changed is not None and entry.xpath not in changed:
                continue
            items.append(
                {
                    "id": entry.xpath,
                    "n": number,
                    "original": entry.original,
                    "translation": entry.translation,
                    "status": str(entry.status),
                    "sourceTag": entry.source_tag,
                    "group": _record_tag(entry.container_xpath),
                    "context": dict(entry.context),
                    "error": entry.error_message,
                }
            )
        return {"rev": rev, "full": full, "entries": items}

    # ------------------------------------------------------------------
    # XML: open, inspect, load
    # ------------------------------------------------------------------

    def open_xml(self, path: str) -> dict:
        self._require_idle()
        if not path or not os.path.isfile(path):
            raise SessionError("file_not_found", 404)
        self._xml_busy = True
        self._bump()
        try:
            success, result = self.ctrl.analyze_xml(path)
        finally:
            self._xml_busy = False
            self._bump()
        if not success or not isinstance(result, list):
            self.log(str(result), "error")
            raise SessionError("xml_invalid", 422)
        self._xml_path = path
        self._parents = result
        self.log(self.i18n.get("log_xml_structure_ready", filename=os.path.basename(path)))
        index = self._index()
        return {
            "path": path,
            "name": os.path.basename(path),
            "size": os.path.getsize(path),
            "parents": [
                {"tag": tag, "count": len(index.elements_by_tag.get(tag, []))} for tag in result
            ],
        }

    def _index(self) -> XmlDocumentIndex:
        if not self._xml_path:
            raise SessionError("no_file", 409)
        success, index = self.ctrl._get_xml_index(self._xml_path)
        if not success or isinstance(index, str):
            raise SessionError("xml_invalid", 422)
        return index

    def child_tags(self, parent: str) -> list[str]:
        self._index()
        return self.ctrl.get_child_tags(self._xml_path, parent)

    def preview(self, parent: str, targets: Sequence[str], contexts: Sequence[str]) -> dict:
        index = self._index()
        counts = (
            self.ctrl.preview_tag_selection(self._xml_path, parent, targets, contexts)
            if targets
            else {"records": len(index.elements_by_tag.get(parent, [])), "lines": 0}
        )
        sample = []
        for element in index.elements_by_tag.get(parent, [])[:2]:
            sample.append(
                {
                    "tag": _local_name(element.tag),
                    "attributes": {_local_name(k): v for k, v in element.attrib.items()},
                    "fields": [
                        {"tag": _local_name(child.tag), "text": (child.text or "").strip()}
                        for child in list(element)[:8]
                        if isinstance(child.tag, str)
                    ],
                }
            )
        return {**counts, "sample": sample}

    def _profile(self) -> GameProfile:
        return profile_for(self._project.game_root) if self._project else GENERIC

    def analyze(self) -> dict:
        """Record tags of the open XML with a suggested role for each field."""
        index = self._index()
        profile = self._profile()
        key = (index.path, index.mtime_ns, profile.id)
        if self._plans_key != key:
            self._plans = plan(index, profile)
            self._plans_key = key
        return {
            "profile": {"id": profile.id, "name": profile.name},
            "tags": [p.to_json() for p in self._plans],
        }

    def preview_groups(self, groups: Sequence[Group]) -> dict:
        """Counts for a multi-tag selection and a sample record per tag that has text."""
        index = self._index()
        records = lines = 0
        sample = []
        for group in groups:
            if not group.targets:
                continue
            counts = index.preview(group.parent, group.targets, group.contexts)
            records += counts["records"]
            lines += counts["lines"]
            wanted = set(group.targets)
            for element in index.elements_by_tag.get(group.parent, []):
                if any(_local_name(c.tag) in wanted and (c.text or "").strip() for c in element):
                    sample.append(self._sample_record(element))
                    break
        return {"records": records, "lines": lines, "sample": sample[:6]}

    @staticmethod
    def _sample_record(element) -> dict:
        return {
            "tag": _local_name(element.tag),
            "attributes": {_local_name(k): v for k, v in element.attrib.items()},
            "fields": [
                {"tag": _local_name(child.tag), "text": (child.text or "").strip()[:240]}
                for child in list(element)[:14]
                if isinstance(child.tag, str) and len(child) == 0
            ],
        }

    def load(self, parent: str, targets: Sequence[str], contexts: Sequence[str]) -> dict:
        return self.load_groups([Group.of(parent, targets, contexts)])

    def load_groups(self, groups: Sequence[Group]) -> dict:
        self._require_idle()
        self._index()
        groups = [g for g in groups if g.parent and g.targets]
        if not groups:
            raise SessionError("tags_required")
        self._xml_busy = True
        self._bump()
        try:
            success, error = self.ctrl.load_xml_groups(self._xml_path, groups)
            if not success:
                self.log(error, "error")
                raise SessionError("xml_invalid", 422)
            restored = self.ctrl.restore_checkpoint_for(self._xml_path)
        finally:
            self._xml_busy = False
            with self._lock:
                self._entry_rev.clear()
            self._bump()
        count = len(self.ctrl.project.entries)
        if self._project:
            remembered = self.projects.remember(self._project.id, self._xml_path, groups)
            self._project = remembered or self._project
        if restored:
            self.log(self.i18n.get("log_checkpoint_loaded", n=restored))
        self.log(
            self.i18n.get("log_load_success", filename=os.path.basename(self._xml_path), count=count)
        )
        return {"count": count, "restored": restored}

    def close_file(self) -> None:
        """Save progress and unload the XML, back to the project or the start."""
        self._require_idle()
        self._persist()
        self.ctrl.project = TranslationProject()
        self._xml_path = ""
        self._parents = []
        with self._lock:
            self._entry_rev.clear()
        self._bump()

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    @property
    def _project(self) -> Project | None:
        return self.__project

    @_project.setter
    def _project(self, project: Project | None) -> None:
        # Files of an open project are stored under the project, not their name alone.
        self.__project = project
        self.ctrl.store_scope = (project.id, project.folder, project.source_folder) if project else None

    def _file_rows(self, project: Project) -> list[dict]:
        code = self._project_code(project)
        return file_rows(
            project,
            code,
            user_data_path("checkpoints"),
            progress_of=lambda rel: self.ctrl.store.progress(f"{project.id}:{rel}", code),
        )

    def _project_json(self, project: Project, rows: list[dict] | None = None) -> dict:
        if rows is None:
            rows = self._file_rows(project)
        return {
            "id": project.id,
            "name": project.name,
            "folder": project.folder,
            "gameRoot": project.game_root,
            "hasOriginals": bool(project.source_folder) and os.path.isdir(project.source_folder),
            "applied": has_backup(self.projects, project),
            "gameExe": os.path.basename(game_executable(project) or ""),
            "profile": profile_for(project.game_root).name,
            "folderExists": os.path.isdir(project.folder),
            "target": project.target,
            "lastFile": project.last_file,
            "updatedAt": project.updated_at,
            "summary": summarize(rows),
        }

    def _project_code(self, project: Project) -> str:
        if not project.target:
            return self._target_code()
        return self.ctrl.resolve_translation_target(project.target).get("code", "pt")

    def _get_project(self, project_id: str) -> Project:
        try:
            return self.projects.get(project_id)
        except KeyError:
            raise SessionError("project_not_found", 404) from None

    def list_projects(self) -> list[dict]:
        return [self._project_json(project) for project in self.projects.list()]

    @staticmethod
    def detect_game(folder: str) -> dict:
        game = detect_game(folder) if folder else None
        if game is None:
            raise SessionError("folder_not_found", 404)
        return game

    def create_project(self, name: str, folder: str, target: str = "") -> dict:
        game = self.detect_game(folder)
        if target and target not in self.ctrl.available_translation_targets().values():
            raise SessionError("locale_invalid")
        project = self.projects.create(
            name or game["name"],
            game["xmlFolder"],
            target or self.ctrl.translation_target.get("locale", ""),
            game_root=game["root"],
        )
        return self._project_json(project)

    def project_detail(self, project_id: str) -> dict:
        project = self._get_project(project_id)
        rows = self._file_rows(project)
        return {**self._project_json(project, rows), "files": rows}

    def rename_project(self, project_id: str, name: str, folder: str | None = None) -> dict:
        self._get_project(project_id)
        game = self.detect_game(folder) if folder is not None else None
        project = self.projects.update(
            project_id,
            name=name,
            folder=game["xmlFolder"] if game else None,
            game_root=game["root"] if game else None,
        )
        if self._project and self._project.id == project_id:
            self._project = project
            self._bump()
        return self._project_json(project)

    def delete_project(self, project_id: str) -> None:
        if self._project and self._project.id == project_id:
            self.close_project()
        self.projects.delete(project_id)

    def open_project(self, project_id: str) -> dict:
        project = self._get_project(project_id)
        if self.ctrl.project.xml_path:
            self.close_file()
        if project.target and project.target in self.ctrl.available_translation_targets().values():
            self._set_target(project.target)
        self._project = self.projects.update(project_id)
        self._bump()
        return self.project_detail(project_id)

    def close_project(self) -> None:
        if self.ctrl.project.xml_path:
            self.close_file()
        self._project = None
        self._import = {"status": "idle"}
        self._bump()

    # ------------------------------------------------------------------
    # Importing translations made outside the app
    # ------------------------------------------------------------------

    def import_state(self) -> dict:
        with self._lock:
            return dict(self._import)

    def start_import(self, folder: str) -> None:
        """Compare a clean copy of the game's XMLs with the edited ones, in the background."""
        if not self._project:
            raise SessionError("no_project", 409)
        self._require_idle()
        if self._import.get("status") == "running":
            raise SessionError("busy", 409)
        clean = self.detect_game(folder)["xmlFolder"]
        project = self._project
        if os.path.normcase(os.path.abspath(clean)) == os.path.normcase(os.path.abspath(project.folder)):
            raise SessionError("same_folder")
        if project.source_folder and os.path.normcase(os.path.abspath(clean)) == os.path.normcase(project.source_folder):
            raise SessionError("same_folder")
        with self._lock:
            self._import = {"status": "running", "folder": clean, "done": 0, "total": 0}
        self._bump()

        def progress(done: int, total: int) -> None:
            with self._lock:
                self._import.update(done=done, total=total)
            self._bump()

        def work() -> None:
            try:
                results = compare(project, clean, profile_for(project.game_root), progress)
            except Exception as exc:  # report it instead of leaving the import spinning
                self.log(str(exc), "error")
                with self._lock:
                    self._import = {"status": "error", "folder": clean}
                self._bump()
                return
            self._import_results = results
            summary = [r.to_json() for r in results if r.found or r.problem]
            summary.sort(key=lambda r: (-r["found"], r["file"]))
            with self._lock:
                self._import = {
                    "status": "ready",
                    "folder": clean,
                    "files": summary,
                    "found": sum(len(r.found) for r in results),
                    "texts": sum(r.texts for r in results),
                    "missing": sum(r.problem == "missing" for r in results),
                }
            self._bump()

        self._spawn(work)

    def apply_import(self) -> dict:
        """Keep the clean originals in the project and save the texts found as "to review"."""
        if not self._project or self._import.get("status") != "ready":
            raise SessionError("no_import", 409)
        self._require_idle()
        if self.ctrl.project.xml_path:
            self.close_file()
        project = self._project
        results = self._import_results
        target = os.path.join(self.projects.data_dir(project.id), "originals")
        keep_originals(self._import["folder"], target, [r.rel for r in results if r.problem != "missing"])
        self._project = self.projects.keep_originals(project.id, target, {r.rel: r.groups for r in results})
        saved = store_found(self.ctrl.store, self._project, self._project_code(self._project), results)
        with self._lock:
            self._import = {"status": "idle"}
        self._import_results = []
        self.log(self.i18n.get("log_import_applied", n=saved))
        self._bump()
        return {"saved": saved}

    def cancel_import(self) -> None:
        if self._import.get("status") == "running":
            raise SessionError("busy", 409)
        with self._lock:
            self._import = {"status": "idle"}
        self._import_results = []
        self._bump()

    # ------------------------------------------------------------------
    # Project jobs: long work over the whole game, one at a time
    # ------------------------------------------------------------------

    def job_state(self) -> dict:
        with self._lock:
            return dict(self._job)

    def _start_job(self, kind: str, work: Callable[[Callable[[int, int], None]], dict]) -> None:
        if not self._project:
            raise SessionError("no_project", 409)
        self._require_idle()
        if self._job.get("status") == "running" or self._import.get("status") == "running":
            raise SessionError("busy", 409)
        self._job_cancel.clear()
        with self._lock:
            self._job = {"kind": kind, "status": "running", "done": 0, "total": 0}
        self._bump()

        def progress(done: int, total: int) -> None:
            with self._lock:
                self._job.update(done=done, total=total)
            self._bump()

        def run() -> None:
            try:
                result = work(progress)
                status, error = ("cancelled" if self._job_cancel.is_set() else "done"), ""
            except (GameOpError, SessionError) as exc:
                result, status, error = {}, "error", exc.code
            except Exception as exc:  # reported, never left spinning
                self.log(str(exc), "error")
                result, status, error = {}, "error", "unknown"
            with self._lock:
                self._job = {"kind": kind, "status": status, "error": error, "result": result,
                             "done": self._job.get("total", 0), "total": self._job.get("total", 0)}
            self._bump()

        self._spawn(run)

    def cancel_job(self) -> None:
        """Stop after the requests already in flight: their answers are paid for and saved."""
        self._job_cancel.set()
        with self._lock:
            if self._job.get("status") == "running":
                self._job["cancelling"] = True
        self._bump()
        worker = self._job_worker
        if worker is not None:
            worker.cancel()

    def dismiss_job(self) -> None:
        if self._job.get("status") == "running":
            raise SessionError("busy", 409)
        with self._lock:
            self._job = {"status": "idle"}
        self._bump()

    def _game_ready(self) -> Project:
        if self.ctrl.project.xml_path:
            self.close_file()
        return self._project

    def apply_to_game(self, confirmed_only: bool = False, launch: bool = False) -> None:
        """Write the translated files into the game folder (backing up what was there)."""
        project = self._game_ready()
        lang = self._project_code(project)

        def work(progress) -> dict:
            result = apply_to_game(self.ctrl.store, self.projects, project, lang, confirmed_only, progress)
            self._project = self.projects.get(project.id)
            if launch:
                result["launched"] = launch_game(self._project)
            return result

        self._start_job("play" if launch else "apply", work)

    def restore_game(self) -> None:
        project = self._game_ready()
        self._start_job("restore", lambda _progress: {"files": restore_game(self.projects, project)})

    def launch_game(self) -> dict:
        if not self._project:
            raise SessionError("no_project", 409)
        try:
            return {"launched": launch_game(self._project)}
        except GameOpError as exc:
            raise SessionError(exc.code) from None

    def export_translated(self, folder: str) -> None:
        """The translated XMLs, ready to share, written to a folder of the user's choice."""
        project = self._game_ready()
        if not folder:
            raise SessionError("folder_not_found", 404)
        lang = self._project_code(project)
        self._start_job(
            "export",
            lambda progress: write_translated(self.ctrl.store, project, lang, folder, on_progress=progress),
        )

    def translate_project(self) -> None:
        """Translate every pending text of every file of the project, file after file."""
        if self._needs_key():
            raise SessionError("api_key_required", 409)
        project = self._game_ready()
        profile = profile_for(project.game_root)

        def work(progress) -> dict:
            files = xml_files(project.folder)
            # One pace for the whole run: small files in a row must not burst past the limit.
            gate = gemini_batch.RateGate(float(GEMINI_RPM))
            # The same model and settings for every file of the run.
            config = self.ctrl.build_translation_config(self._model_label, self._models, self.i18n)
            config["_rate_gate"] = gate
            translated = 0
            touched: set[str] = set()
            retry: list[str] = []
            stopped = ""
            # A second pass picks up files a per-minute limit left with errors.
            for pass_files in (files, None):
                queue = pass_files if pass_files is not None else retry
                if not queue or stopped or self._job_cancel.is_set():
                    break
                retry = []
                for done, rel in enumerate(queue):
                    progress(done, len(queue))
                    if self._job_cancel.is_set():
                        break
                    path = project.open_path(rel)
                    ok, index = indexar_xml(path)
                    if not ok or isinstance(index, str):
                        continue
                    groups = self._project.selections.get(rel) or suggested_groups(plan(index, profile))
                    ok, entries = extract_groups(index, groups) if groups else (False, [])
                    if not ok or isinstance(entries, str):
                        continue
                    part = TranslationProject()
                    part.load_extracted(path, groups[0].parent, groups[0].targets, groups[0].contexts, entries, groups=groups)
                    part.on_save = self.ctrl._mirror_to_store
                    self.ctrl.restore_checkpoint_for(path, project=part)
                    self._project = self.projects.keep_originals(project.id, self._project.source_folder, {rel: groups})
                    before = sum(1 for e in part.entries.values() if e.needs_translation)
                    if not before:
                        continue
                    touched.add(rel)
                    with self._lock:
                        self._job["file"] = rel
                    self._bump()
                    worker = TranslationWorker(part, dict(config), lambda *_: None, self.log, lambda: None)
                    self._job_worker = worker
                    worker._run()
                    self._job_worker = None
                    translated += before - sum(1 for e in part.entries.values() if e.needs_translation)
                    codes = {e.error_code for e in part.entries.values() if e.status == EntryStatus.ERROR}
                    # A spent daily quota or a bad key fails every next file too: stop, resume later.
                    stopped = next((c for c in ("daily_quota", "authentication") if c in codes), "")
                    if stopped:
                        break
                    if "rate_limit" in codes:
                        retry.append(rel)
            if stopped:
                raise SessionError(stopped)
            return {"files": len(touched), "texts": translated}

        self._start_job("translate", work)

    def start_update(self, folder: str) -> None:
        """Compare a new build of the game with the project (preview; apply_update saves it)."""
        game = self.detect_game(folder)
        project = self._game_ready()
        same = os.path.normcase(os.path.abspath(game["xmlFolder"])) == os.path.normcase(os.path.abspath(project.folder))
        if same and has_backup(self.projects, project):
            # The game folder holds the app's translation, not the new build's texts.
            raise SessionError("restore_first")
        lang = self._project_code(project)
        profile = profile_for(game["root"])

        def work(progress) -> dict:
            results = compare_build(project, game["xmlFolder"], profile, self.ctrl.store, lang, progress)
            self._build_update = {"game": game, "results": results}
            files = [r.to_json() for r in results if r.changed or r.moved or r.removed]
            return {
                "folder": game["xmlFolder"],
                "kept": sum(r.kept for r in results),
                "changed": sum(r.changed for r in results),
                "moved": sum(r.moved for r in results),
                "new": sum(r.new for r in results),
                "removed": sum(r.removed for r in results),
                "files": sorted(files, key=lambda f: -(f["changed"] + f["moved"]))[:50],
            }

        self._start_job("update", work)

    def apply_update(self) -> dict:
        if not self._project or not self._build_update or self._job.get("kind") != "update" or self._job.get("status") != "done":
            raise SessionError("no_update_ready", 409)
        project = self._game_ready()
        game, results = self._build_update["game"], self._build_update["results"]
        target = os.path.join(self.projects.data_dir(project.id), "originals")
        keep_originals(game["xmlFolder"], target, [r.rel for r in results])
        if os.path.normcase(game["xmlFolder"]) != os.path.normcase(project.folder):
            # A backup of the old install means nothing for the new one.
            shutil.rmtree(os.path.join(self.projects.data_dir(project.id), "game-backup"), ignore_errors=True)
        self.projects.update(project.id, folder=game["xmlFolder"], game_root=game["root"])
        self._project = self.projects.keep_originals(project.id, target, {r.rel: r.groups for r in results})
        saved = store_update(self.ctrl.store, self._project, self._project_code(self._project), results)
        self._build_update = None
        with self._lock:
            self._job = {"status": "idle"}
        self._bump()
        return {"reused": saved}

    def export_package(self, path: str) -> dict:
        if not self._project:
            raise SessionError("no_project", 409)
        if not path:
            raise SessionError("export_failed")
        self._persist()
        return export_package(self.ctrl.store, self._project, self._project_code(self._project), self.glossary(), path)

    def import_package(self, path: str) -> dict:
        if not self._project:
            raise SessionError("no_project", 409)
        project = self._game_ready()
        try:
            result = import_package(self.ctrl.store, project, self._project_code(project), path)
        except PackageError as exc:
            raise SessionError(exc.code) from None
        # Their glossary fills in terms this project does not have yet; ours wins on conflicts.
        terms = {t["original"]: t for t in result.pop("glossary") if isinstance(t, dict) and t.get("original")}
        terms.update({t["original"]: t for t in self.glossary()})
        added = len(terms) - len(self.glossary())
        if added:
            self.save_glossary(list(terms.values()))
        self._bump()
        return {**result, "glossaryAdded": added}

    # ------------------------------------------------------------------
    # Translation
    # ------------------------------------------------------------------

    def _needs_key(self) -> bool:
        return self.ctrl.preferred_provider not in KEYLESS_PROVIDERS and not self.ctrl.api_key

    def translate(self, xpaths: Sequence[str] | None = None) -> None:
        self._require_project()
        self._require_idle()
        if self._needs_key():
            raise SessionError("api_key_required", 409)
        config = self.ctrl.build_translation_config(self._model_label, self._models, self.i18n)
        if xpaths is not None:
            config["selected_xpaths"] = list(xpaths)
            config["include_done"] = True
        self._translating = True
        self._bump()

        def on_batch_start(batch: list[str]) -> None:
            for xpath in batch:
                self._bump(xpath)

        def on_entry(xpath: str, _text: str) -> None:
            self._bump(xpath)

        def on_done() -> None:
            self._translating = False
            self._bump()

        self.ctrl.start_batch_translation(config, on_entry, self.log, on_done, on_batch_start)

    def cancel(self) -> None:
        self.ctrl.cancel_translation()

    def translate_entry(self, xpath: str) -> None:
        self._require_project()
        if self._xml_busy or self._translating or xpath in self._single:
            raise SessionError("busy", 409)
        entry = self.ctrl.project.get_entry(xpath)
        if entry is None:
            raise SessionError("entry_not_found", 404)
        if self._needs_key():
            raise SessionError("api_key_required", 409)
        config = self.ctrl.build_translation_config(self._model_label, self._models, self.i18n)
        self._single.add(xpath)
        self.ctrl.project.mark_translating(xpath)
        self._bump(xpath)

        def work() -> None:
            try:
                result = self.ctrl.translate_single(xpath, config)
                current = self.ctrl.project.get_entry(xpath)
                if current is not None and current.status == EntryStatus.ERROR:
                    self.log(str(result), "error")
                else:
                    self.ctrl.project.set_translation(xpath, result, source="ai")
                self._persist()
            except Exception as exc:  # the UI must never be left with a stuck row
                self.ctrl.project.mark_error(xpath)
                self.log(str(exc), "error")
            finally:
                self.ctrl.project.recover_interrupted()
                self._single.discard(xpath)
                self._bump(xpath)

        self._spawn(work)

    def edit(self, xpath: str, text: str, source: str = "manual") -> None:
        self._require_project()
        entry = self.ctrl.project.get_entry(xpath)
        if entry is None:
            raise SessionError("entry_not_found", 404)
        if entry.status == EntryStatus.TRANSLATING:
            raise SessionError("busy", 409)
        if text == entry.translation:
            return
        # An edited text is no longer the reviewed one: it goes back to "to review".
        self.ctrl.project.set_translation(xpath, text, "translated", source=source)
        self._persist()
        self._bump(xpath)

    def suggestions(self, xpath: str) -> list[dict]:
        """How this exact original was already translated elsewhere (translation memory)."""
        self._require_project()
        entry = self.ctrl.project.get_entry(xpath)
        if entry is None:
            raise SessionError("entry_not_found", 404)
        found = self.ctrl.store.memory(self._target_code(), entry.original)
        return [s for s in found if s["translation"] != entry.translation]

    def search_project(self, query: str, limit: int = 200) -> list[dict]:
        """Matches across every opened file of the active project (or the loose files)."""
        prefix = f"{self._project.id}:" if self._project else "file:"
        results = []
        for row in self.ctrl.store.search(prefix, self._target_code(), query, limit):
            rel = row["key"][len(prefix):]
            path = os.path.join(self._project.folder, rel) if self._project else ""
            results.append({**row, "file": rel, "path": path})
        return results

    def history(self, xpath: str) -> list[dict]:
        """Earlier versions of an entry, newest first."""
        self._require_project()
        if self.ctrl.project.get_entry(xpath) is None:
            raise SessionError("entry_not_found", 404)
        return self.ctrl.entry_history(xpath)

    def confirm(self, xpath: str, text: str | None = None) -> None:
        self._require_project()
        if self.ctrl.project.get_entry(xpath) is None:
            raise SessionError("entry_not_found", 404)
        if not self.ctrl.project.confirm_translation(xpath, text):
            raise SessionError("empty_translation")
        self._persist()
        self._bump(xpath)

    # ------------------------------------------------------------------
    # Export / backup
    # ------------------------------------------------------------------

    def export_xml(self, path: str) -> None:
        self._require_project()
        self._require_idle()
        if not path or not self.ctrl.export_xml(path):
            self.log(self.i18n.get("export_fail"), "error")
            raise SessionError("export_failed", 500)
        self.log(self.i18n.get("log_xml_exported", path=path))

    def export_backup(self, path: str, fmt: str) -> None:
        self._require_project()
        writer = {"json": self.ctrl.export_json, "csv": self.ctrl.export_csv}.get(fmt)
        if writer is None or not path or not writer(path):
            raise SessionError("export_failed", 500)

    def import_backup(self, path: str) -> int:
        self._require_project()
        self._require_idle()
        reader = self.ctrl.import_csv if path.lower().endswith(".csv") else self.ctrl.import_json
        try:
            count = int(reader(path))
        except (OSError, ValueError) as exc:
            raise SessionError("import_failed", 422) from exc
        self._persist()
        self._bump()
        return count

    # ------------------------------------------------------------------
    # Glossary
    # ------------------------------------------------------------------

    def _target_code(self) -> str:
        return self.ctrl.translation_target.get("code", "pt")

    def glossary(self) -> list[dict]:
        """The glossary of the current target language: each language has its own."""
        terms = carregar_glossario(self._target_code())
        return [{"original": k, "translation": v} for k, v in terms.items()]

    def save_glossary(self, terms: Sequence[dict]) -> list[dict]:
        data: dict[str, str] = {}
        for term in terms:
            original = str(term.get("original", "")).strip()
            translation = str(term.get("translation", "")).strip()
            if original and translation:
                data[original] = translation
        os.makedirs(user_data_dir(), exist_ok=True)
        write_json_atomic(user_data_path(glossary_filename(self._target_code())), data, indent=4)
        self._bump()
        return self.glossary()

    def export_glossary(self, path: str) -> None:
        try:
            write_json_atomic(path, carregar_glossario(self._target_code()), indent=4)
        except OSError as exc:
            raise SessionError("export_failed", 500) from exc

    def import_glossary(self, path: str) -> list[dict]:
        """Merge a {"original": "translation"} file; imported terms win on conflict."""
        try:
            with open(path, encoding="utf-8") as f:
                incoming = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise SessionError("import_failed", 422) from exc
        if not isinstance(incoming, dict):
            raise SessionError("import_failed", 422)
        current = carregar_glossario(self._target_code())
        merged = {**current, **{str(k): str(v) for k, v in incoming.items()}}
        return self.save_glossary(
            [{"original": k, "translation": v} for k, v in merged.items()]
        )

    # ------------------------------------------------------------------
    # Tag presets
    # ------------------------------------------------------------------

    def presets(self) -> list[dict]:
        return [
            {
                "id": preset.get("id"),
                "label": preset.get("label", ""),
                "parent": preset.get("parent_tag", ""),
                "targets": preset["target_tags"],
                "contexts": preset["context_tags"],
                "file": preset.get("file", ""),
            }
            for preset in self.ctrl.get_tag_presets()
        ]

    def save_preset(self, label: str, parent: str, targets: Sequence[str], contexts: Sequence[str]) -> list[dict]:
        label = label.strip()
        if not label or not parent:
            raise SessionError("preset_invalid")
        file_hint = os.path.basename(self._xml_path) if self._xml_path else ""
        if not self.ctrl.save_tag_preset(label, parent, list(targets), file_hint, "", list(contexts)):
            raise SessionError("preset_invalid")
        return self.presets()

    def delete_preset(self, preset_id: int) -> list[dict]:
        self.ctrl.delete_tag_preset(preset_id)
        return self.presets()

    def export_presets(self, path: str) -> None:
        if not path or not self.ctrl.export_presets(path):
            raise SessionError("export_failed", 500)

    def import_presets(self, path: str) -> dict:
        imported, skipped = self.ctrl.import_presets(path)
        if imported < 0:
            raise SessionError("import_failed", 422)
        return {"imported": imported, "skipped": skipped, "presets": self.presets()}

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _load_prefs(self) -> dict:
        prefs = dict(DEFAULT_PREFS)
        try:
            with open(user_data_path(PREFS_FILE), encoding="utf-8") as f:
                stored = json.load(f)
        except (OSError, json.JSONDecodeError):
            return prefs
        if isinstance(stored, dict):
            if stored.get("theme") in THEMES:
                prefs["theme"] = stored["theme"]
            if stored.get("accent") in ACCENTS:
                prefs["accent"] = stored["accent"]
            if isinstance(stored.get("auto_update"), bool):
                prefs["auto_update"] = stored["auto_update"]
        return prefs

    def _save_prefs(self) -> None:
        os.makedirs(user_data_dir(), exist_ok=True)
        write_json_atomic(user_data_path(PREFS_FILE), self.prefs)

    def settings(self) -> dict:
        current = self.ctrl.preferred_provider
        providers = [
            {
                "id": name,
                "needsKey": name not in KEYLESS_PROVIDERS,
                "hasKey": bool(self.ctrl.get_api_key(name)),
                "ai": name in AI_PROVIDERS,
                "keyUrl": PROVIDER_URLS.get(name, ""),
            }
            for name in self.ctrl.available_providers()
            if name not in LEGACY_PROVIDERS or name == current
        ]
        return {
            "provider": current,
            "providers": providers,
            "locale": self.i18n.language,
            "locales": self.ctrl.available_locales(),
            "target": self.ctrl.translation_target.get("locale", ""),
            "targets": self.ctrl.available_translation_targets(),
            "ollamaModel": self.ctrl.ollama_model,
            "ollamaThinking": bool(self.ctrl.ollama_thinking),
            "azureRegion": self.ctrl.azure_region,
            "context": self.ctrl.translation_context,
            "models": [
                {"label": label, "paid": paid} for label, (_id, _timeout, paid) in self._models.items()
            ],
            "model": self._model_label,
            "theme": self.prefs["theme"],
            "accent": self.prefs["accent"],
            "autoUpdate": self.prefs["auto_update"],
            "glossaryCount": len(carregar_glossario(self._target_code())),
        }

    def update_settings(self, changes: dict) -> dict:
        if "provider" in changes:
            provider = changes["provider"]
            if provider not in self.ctrl.available_providers():
                raise SessionError("provider_invalid")
            self._save_config(provider=provider)
            if provider == "Gemini" and self.ctrl.api_key:
                self._spawn(self._fetch_models)
        if "model" in changes and changes["model"] in self._models:
            self._model_label = changes["model"]
            self._save_config()
        if "ollamaModel" in changes:
            model = str(changes["ollamaModel"]).strip()
            if model:
                self._save_config(ollama_model=model)
        if isinstance(changes.get("ollamaThinking"), bool):
            self.ctrl.ollama_thinking = changes["ollamaThinking"]
            self._save_config()
        if "azureRegion" in changes:
            self.ctrl.azure_region = str(changes["azureRegion"]).strip()[:64]
            self._save_config()
        if "context" in changes:
            self.ctrl.translation_context = str(changes["context"])[:2000]
            self._save_config()
        if "locale" in changes:
            locale = changes["locale"]
            if locale not in self.ctrl.available_locales().values():
                raise SessionError("locale_invalid")
            self.i18n.load_language(locale)
            self.ctrl.save_preferred_locale(locale)
        if "target" in changes:
            self._set_target(changes["target"])
            if self._project:
                self._project = self.projects.update(self._project.id, target=changes["target"])
        prefs_changed = False
        if changes.get("theme") in THEMES:
            self.prefs["theme"] = changes["theme"]
            prefs_changed = True
        if changes.get("accent") in ACCENTS:
            self.prefs["accent"] = changes["accent"]
            prefs_changed = True
        if isinstance(changes.get("autoUpdate"), bool):
            self.prefs["auto_update"] = changes["autoUpdate"]
            prefs_changed = True
        if prefs_changed:
            self._save_prefs()
        self._bump()
        return self.settings()

    def _set_target(self, locale: str) -> None:
        if locale not in self.ctrl.available_translation_targets().values():
            raise SessionError("locale_invalid")
        if locale == self.ctrl.translation_target.get("locale"):
            return
        self._require_idle()
        # Each target language keeps its own checkpoint: save this one, then
        # swap in whatever was already translated for the new target.
        self._persist()
        self.ctrl.save_preferred_translation_target(locale)
        if self.ctrl.project.xml_path:
            self.ctrl.project.reset_translations()
            restored = self.ctrl.restore_checkpoint_for(self.ctrl.project.xml_path)
            if restored:
                self.log(self.i18n.get("log_checkpoint_loaded", n=restored))

    def set_api_key(self, provider: str, key: str) -> dict:
        if provider not in self.ctrl.available_providers() or provider in KEYLESS_PROVIDERS:
            raise SessionError("provider_invalid")
        self.ctrl.set_api_key(provider, key.strip())
        self._save_config()
        if provider == "Gemini" and key.strip() and provider == self.ctrl.preferred_provider:
            self._spawn(self._fetch_models)
        self._bump()
        return self.settings()

    def _fetch_models(self) -> None:
        try:
            models = list_gemini_models(self.ctrl.api_key)
        except Exception as exc:
            self.log(self.i18n.get("log_models_load_fail", provider="Gemini", error=str(exc)), "error")
            return
        if not models:
            return
        self._models = models
        saved = self.ctrl.preferred_model_label
        by_id = next(
            (label for label, info in models.items() if info[0] == self.ctrl.preferred_model_id), None
        )
        self._model_label = saved if saved in models else by_id or next(iter(models))
        self._bump()

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------

    def update_state(self) -> dict:
        release = self._release
        return {
            "current": app_version(),
            "status": self._update["status"],
            "error": self._update["error"],
            "progress": self._update["progress"],
            "available": release is not None,
            "version": release.version if release else "",
            "notes": release.notes if release else "",
            "pageUrl": release.page_url if release else "",
            "checkedAt": self.ctrl.last_update_check,
        }

    def _set_update(self, **changes) -> None:
        self._update.update(changes)
        self._bump()

    def check_updates(self, *, automatic: bool = False) -> None:
        if self._update["status"] in ("checking", "downloading"):
            return
        if automatic:
            recent = time.time() - self.ctrl.last_update_check < UPDATE_INTERVAL_SECONDS
            if not self.prefs["auto_update"] or recent:
                return
        self._set_update(status="checking", error="")

        def work() -> None:
            try:
                release = updater.fetch_latest_release(app_version())
            except updater.UpdateError as exc:
                self._set_update(status="error", error=exc.code)
                return
            self.ctrl.save_update_preferences(last_check=time.time())
            if release and automatic and release.version == self.ctrl.skipped_update_version:
                release = None
            self._release = release
            self._set_update(status="idle", error="", progress=0, installer="")

        self._spawn(work)

    def download_update(self) -> None:
        release = self._release
        if release is None:
            raise SessionError("no_update", 409)
        if self._update["status"] == "downloading":
            return
        self._set_update(status="downloading", error="", progress=0)

        def work() -> None:
            try:
                path = updater.download_release(
                    release, progress=lambda percent: self._set_update(progress=percent)
                )
            except updater.UpdateError as exc:
                self._set_update(status="error", error=exc.code)
                return
            self._set_update(status="ready", installer=path, progress=100)

        self._spawn(work)

    def install_update(self) -> None:
        if self._update["status"] != "ready" or self._translating or self._single:
            raise SessionError("busy", 409)
        self._persist()
        if not updater.launch_installer(self._update["installer"]):
            self._set_update(status="error", error="launch")
            raise SessionError("update_launch_failed", 500)

    def skip_update(self) -> None:
        if self._release is not None:
            self.ctrl.save_update_preferences(skipped_version=self._release.version)
            self._release = None
            self._set_update(status="idle", error="")

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------

    def feedback_payload(self, text: str) -> dict:
        """Everything a feedback message carries. Never file contents or keys."""
        message = text.strip()
        # Match the browser counter and the server JavaScript string length.
        message_length = len(message.encode("utf-16-le")) // 2
        if not FEEDBACK_MIN <= message_length <= FEEDBACK_MAX:
            raise SessionError("feedback_length")
        language = self.i18n.language
        locale = language.split("_")[0].split("-")[0]
        # The site currently supports no Japanese locale; retain it in diagnostics.
        if locale not in {"pt", "en", "es", "fr", "de", "it"}:
            locale = "en"
        diagnostics = (
            f"[STZ XML Translator {app_version()} | {language} | "
            f"{platform.system()} {platform.release()}]"
        )
        final_text = f"{diagnostics}\n{message}"
        if len(final_text.encode("utf-16-le")) // 2 > FEEDBACK_API_MAX:
            raise SessionError("feedback_length")
        return {"type": "suggestion", "text": final_text, "locale": locale}

    def send_feedback(self, text: str, *, http=requests) -> None:
        payload = self.feedback_payload(text)
        try:
            response = http.post(FEEDBACK_URL, json=payload, timeout=12)
        except requests.RequestException as exc:
            raise SessionError("feedback_offline", 502) from exc
        if response.status_code == 429:
            raise SessionError("feedback_rate_limited", 429)
        if not 200 <= response.status_code < 300:
            raise SessionError("feedback_unavailable", 502)
