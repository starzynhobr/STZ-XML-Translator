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
import threading
import time
from collections.abc import Sequence

import requests

from core import updater
from core.app_controller import PROVIDER_URLS, AppController, user_data_dir, user_data_path
from core.atomic import write_json_atomic
from core.extrator import XmlDocumentIndex, _local_name
from core.i18n import I18nManager
from core.project import EntryStatus
from core.tradutor_api import carregar_glossario, glossary_filename, list_gemini_models
from core.version import app_version

PREFS_FILE = "ui_prefs.json"
FEEDBACK_URL = "https://stzlabs.com/api/feedback"
FEEDBACK_PRODUCT = "xml-translator"
FEEDBACK_MIN, FEEDBACK_MAX = 10, 2000
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
                    }
                    if project.xml_path
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

    def load(self, parent: str, targets: Sequence[str], contexts: Sequence[str]) -> dict:
        self._require_idle()
        self._index()
        targets = [t for t in dict.fromkeys(targets) if t]
        contexts = [c for c in dict.fromkeys(contexts) if c and c not in targets]
        if not parent or not targets:
            raise SessionError("tags_required")
        self._xml_busy = True
        self._bump()
        try:
            success, error = self.ctrl.load_xml(self._xml_path, parent, targets, contexts)
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
        if restored:
            self.log(self.i18n.get("log_checkpoint_loaded", n=restored))
        self.log(
            self.i18n.get("log_load_success", filename=os.path.basename(self._xml_path), count=count)
        )
        return {"count": count, "restored": restored}

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
                    self.ctrl.project.set_translation(xpath, result)
                self._persist()
            except Exception as exc:  # the UI must never be left with a stuck row
                self.ctrl.project.mark_error(xpath)
                self.log(str(exc), "error")
            finally:
                self.ctrl.project.recover_interrupted()
                self._single.discard(xpath)
                self._bump(xpath)

        self._spawn(work)

    def edit(self, xpath: str, text: str) -> None:
        self._require_project()
        entry = self.ctrl.project.get_entry(xpath)
        if entry is None:
            raise SessionError("entry_not_found", 404)
        if entry.status == EntryStatus.TRANSLATING:
            raise SessionError("busy", 409)
        if text == entry.translation:
            return
        # An edited text is no longer the reviewed one: it goes back to "to review".
        self.ctrl.project.set_translation(xpath, text, "translated")
        self._persist()
        self._bump(xpath)

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
        return {
            "product": FEEDBACK_PRODUCT,
            "text": text.strip(),
            "version": app_version(),
            "locale": self.i18n.language,
            "os": f"{platform.system()} {platform.release()}",
        }

    def send_feedback(self, text: str, *, http=requests) -> None:
        payload = self.feedback_payload(text)
        if not FEEDBACK_MIN <= len(payload["text"]) <= FEEDBACK_MAX:
            raise SessionError("feedback_length")
        try:
            response = http.post(FEEDBACK_URL, json=payload, timeout=12)
        except requests.RequestException as exc:
            raise SessionError("feedback_offline", 502) from exc
        if response.status_code == 429:
            raise SessionError("feedback_rate_limited", 429)
        if response.status_code >= 400:
            raise SessionError("feedback_unavailable", 502)
