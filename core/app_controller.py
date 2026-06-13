from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable

from core.project import TranslationProject
from core.translation_worker import TranslationWorker

TRANSLATION_TARGETS: dict[str, dict[str, str]] = {
    "pt": {"code": "pt", "deepl": "PT-BR", "label": "Portuguese (Brazil)"},
    "en": {"code": "en", "deepl": "EN-US", "label": "English"},
    "es": {"code": "es", "deepl": "ES", "label": "Spanish"},
    "fr": {"code": "fr", "deepl": "FR", "label": "French"},
    "ja": {"code": "ja", "deepl": "JA", "label": "Japanese"},
}

CONFIG_FILE = "config.json"
PRESETS_FILE = "tag_presets.json"
APP_DATA_DIR_NAME = "STZ XML Translator"

PROVIDER_URLS: dict[str, str] = {
    "Gemini": "https://aistudio.google.com/app/apikey",
    "Google Translate (Free)": "",
    "DeepL": "https://www.deepl.com/pro-api",
    "Microsoft Azure": "https://portal.azure.com/#create/Microsoft.CognitiveServicesTextTranslation",
    "Ollama (Local)": "https://ollama.ai/download",
}


def resource_path(relative_path: str) -> str:
    """Resolve resource paths for bundled (Nuitka/PyInstaller) and script modes."""
    base_path = getattr(sys, "_MEIPASS", None)
    if base_path:
        return os.path.join(base_path, relative_path)
    if getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
        base_path = os.path.join(base_path, "..")  # core/ → project root
    return os.path.normpath(os.path.join(base_path, relative_path))


def _is_packaged_app() -> bool:
    """Return True when running from a bundled executable instead of python.exe."""
    exe_name = os.path.basename(sys.executable).lower()
    return bool(
        getattr(sys, "frozen", False)
        or "__compiled__" in globals()
        or not exe_name.startswith("python")
    )


def user_data_dir() -> str:
    """
    Writable directory for user state in packaged builds.

    During local development/tests we keep the old cwd-relative behaviour so
    existing workflows remain predictable. Packaged apps may run from read-only
    install folders, so config and presets must live under LocalAppData.
    """
    override = os.environ.get("STZ_XML_TRANSLATOR_DATA_DIR")
    if override:
        return os.path.abspath(override)

    if not _is_packaged_app():
        return os.getcwd()

    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return os.path.join(base, APP_DATA_DIR_NAME)

    return os.path.join(os.path.expanduser("~"), f".{APP_DATA_DIR_NAME.replace(' ', '-').lower()}")


def user_data_path(filename: str) -> str:
    return os.path.join(user_data_dir(), filename)


def _legacy_cwd_path(filename: str) -> str:
    return os.path.abspath(filename)


def _readable_user_file(filename: str) -> str:
    """Prefer the writable user-data file, falling back to legacy cwd files."""
    primary = user_data_path(filename)
    if os.environ.get("STZ_XML_TRANSLATOR_DATA_DIR"):
        return primary

    if os.path.exists(primary):
        return primary

    legacy = _legacy_cwd_path(filename)
    if os.path.exists(legacy):
        return legacy

    return primary


class AppController:
    """
    Facade that coordinates TranslationProject and TranslationWorker.
    The GUI talks exclusively to this class — no direct imports of core modules.
    """

    def __init__(self) -> None:
        self.project = TranslationProject()
        self._worker: TranslationWorker | None = None
        self.source_language_label = "English"

        # Config state
        self.api_key: str = ""
        self.preferred_model_id: str = "models/gemini-flash-lite-latest"
        self.preferred_model_label: str = ""
        self.preferred_provider: str = "Gemini"
        self.preferred_locale: str = "pt_BR"
        # Translation target is now independent from the UI locale.
        # Falls back to preferred_locale for backward compat on first run.
        self.preferred_translation_target: str = ""
        self.ollama_model: str = "llama3"
        self.ollama_thinking: bool = False
        self.translation_context: str = ""
        self._api_keys: dict[str, str] = {}
        self.translation_target: dict[str, str] = TRANSLATION_TARGETS["pt"].copy()
        self.game_folder: str = ""
        self.preferred_theme: str = "Windows Fluent"

        self._load_config()

    # ------------------------------------------------------------------
    # Config persistence
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        config_path = _readable_user_file(CONFIG_FILE)
        if not os.path.exists(config_path):
            return
        try:
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)
            self.preferred_provider = data.get("provider", "Gemini")
            self.preferred_locale = data.get("locale", "pt_BR")
            # translation_target_locale is independent from UI locale.
            # If not present (old config), fall back to the UI locale.
            self.preferred_translation_target = data.get(
                "translation_target_locale", self.preferred_locale
            )
            self.preferred_model_id = data.get("preferred_model_id", self.preferred_model_id)
            self.preferred_model_label = data.get("preferred_model", "")
            self.ollama_model = data.get("ollama_model", "llama3")
            self.ollama_thinking = data.get("ollama_thinking", False)
            self.translation_context = data.get("translation_context", "")
            # Per-provider keys (new format)
            self._api_keys = data.get("api_keys", {})
            # Backward compat: old config stored a single api_key for Gemini
            if not self._api_keys.get("Gemini") and data.get("api_key"):
                self._api_keys["Gemini"] = data["api_key"]
            self.api_key = self._api_keys.get(self.preferred_provider, "")
            self.game_folder = data.get("game_folder", "")
            self.preferred_theme = data.get("theme", "Windows Fluent")
        except (OSError, json.JSONDecodeError):
            pass

    def save_config(
        self,
        *,
        api_key: str,
        model_label: str,
        model_id: str,
        provider: str = "",
        ollama_model: str = "",
    ) -> None:
        if provider:
            self.preferred_provider = provider
        if api_key:
            self._api_keys[self.preferred_provider] = api_key
        self.api_key = self._api_keys.get(self.preferred_provider, "")
        self.preferred_model_label = model_label
        self.preferred_model_id = model_id
        if ollama_model:
            self.ollama_model = ollama_model
        data: dict = {
            "provider": self.preferred_provider,
            "locale": self.preferred_locale,
            "translation_target_locale": self.preferred_translation_target or self.preferred_locale,
            "preferred_model": model_label,
            "preferred_model_id": model_id,
            "ollama_model": self.ollama_model,
            "ollama_thinking": self.ollama_thinking,
            "translation_context": self.translation_context,
            "api_keys": {k: v for k, v in self._api_keys.items() if v},
            "game_folder": self.game_folder,
            "theme": self.preferred_theme,
        }
        try:
            os.makedirs(user_data_dir(), exist_ok=True)
            with open(user_data_path(CONFIG_FILE), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass

    def save_preferred_locale(self, locale_code: str) -> None:
        """Persist the UI locale. Does NOT change the translation target."""
        self.preferred_locale = locale_code
        self.save_config(
            api_key=self.api_key,
            model_label=self.preferred_model_label,
            model_id=self.preferred_model_id,
        )

    def save_preferred_translation_target(self, locale_code: str) -> None:
        """Persist and apply the translation target locale. Does NOT change the UI language."""
        self.preferred_translation_target = locale_code
        self.set_translation_target(locale_code)
        self.save_config(
            api_key=self.api_key,
            model_label=self.preferred_model_label,
            model_id=self.preferred_model_id,
        )

    def save_preferred_theme(self, theme_name: str) -> None:
        """Persist the selected UI theme."""
        self.preferred_theme = theme_name
        self.save_config(
            api_key=self.api_key,
            model_label=self.preferred_model_label,
            model_id=self.preferred_model_id,
        )

    def save_game_folder(self, path: str) -> None:
        """Persist the game root folder without overwriting other config keys."""
        self.game_folder = path
        try:
            data: dict = {}
            config_path = _readable_user_file(CONFIG_FILE)
            if os.path.exists(config_path):
                with open(config_path, encoding="utf-8") as f:
                    data = json.load(f)
            data["game_folder"] = path
            os.makedirs(user_data_dir(), exist_ok=True)
            with open(user_data_path(CONFIG_FILE), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except (OSError, json.JSONDecodeError):
            pass

    def resolve_preset_file(self, file_hint: str) -> str:
        """
        Return the absolute path for a preset file hint, or '' if not resolvable.

        Resolution order:
        1. Absolute path that exists → use directly (no game_folder needed).
        2. Relative path + game_folder → join and check.
        3. Any hint + game_folder → recursive scan by basename as fallback
           (handles old presets that stored only the filename).
        """
        if not file_hint:
            return ""
        # Case 1: absolute path that still exists on this machine
        if os.path.isabs(file_hint) and os.path.exists(file_hint):
            return file_hint
        # Cases 2 & 3 require a game_folder
        if not self.game_folder:
            return ""
        resolved = os.path.join(self.game_folder, file_hint)
        if os.path.exists(resolved):
            return resolved
        # Fallback: scan by basename (handles bare filenames and moved files)
        basename = os.path.basename(file_hint)
        paths = self.scan_for_xml(self.game_folder, basename)
        return paths[0] if len(paths) == 1 else ""

    def get_api_key(self, provider: str) -> str:
        return self._api_keys.get(provider, "")

    def set_api_key(self, provider: str, key: str) -> None:
        self._api_keys[provider] = key
        if provider == self.preferred_provider:
            self.api_key = key

    def available_providers(self) -> list[str]:
        from core.tradutor_api import AVAILABLE_SERVICES
        return list(AVAILABLE_SERVICES.keys())

    # ------------------------------------------------------------------
    # XML tag introspection
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_ns(tag: str) -> str:
        """Remove XML namespace prefix: {http://...}name → name."""
        return tag.split("}")[1] if "}" in tag else tag

    def get_parent_tags(self, xml_path: str) -> list[str]:
        """
        Return tag names of REPEATING elements that have at least one child
        with direct text content anywhere in the document.

        A repeating element is one whose tag name appears more than once
        under the same parent.  We then filter further to only include tags
        where at least one occurrence contains a child element with non-empty
        text — this excludes pure containers (e.g. <actionLevelStatuses>)
        whose children are themselves containers, not leaf fields.

          <data>
            <baseVillains>           ← container (appears once → excluded)
              <baseVillain> × N      ← repeating AND has text children → included
                <bio>…</bio>
              </baseVillain>
            </baseVillains>
            <heroes>
              <hero> × M             ← also included
              </hero>
            </heroes>
            <actionLevelStatuses>×K  ← repeating but no text children → excluded
              <status>…</status>     ← (status itself is a sub-container)
            </actionLevelStatuses>
          </data>
        """
        import xml.etree.ElementTree as ET
        from collections import Counter
        try:
            root = ET.parse(xml_path).getroot()
            repeating: set[str] = set()

            def _walk(element) -> None:
                counts = Counter(self._strip_ns(c.tag) for c in element)
                for tag, count in counts.items():
                    if count > 1:
                        repeating.add(tag)
                for child in element:
                    _walk(child)

            _walk(root)

            # Filter: keep only repeating tags whose occurrences contain at least
            # one child element with non-empty text (i.e. actual leaf fields).
            def _has_text_children(tag: str) -> bool:
                for elem in root.iter(tag):
                    for child in elem:
                        if child.text and child.text.strip():
                            return True
                return False

            result = [t for t in sorted(repeating) if _has_text_children(t)]
            # Fallback: if the filter removes everything, return unfiltered list
            # (better to show something than nothing).
            return result if result else sorted(repeating)
        except Exception:
            return []

    def get_child_tags(self, xml_path: str, parent_tag: str) -> list[str]:
        """
        Return unique child tag names that have non-empty text content inside
        any occurrence of parent_tag in the document.

        Prefers text-bearing children; falls back to all children if none have text.
        """
        import xml.etree.ElementTree as ET
        try:
            root = ET.parse(xml_path).getroot()

            # Collect child tags with actual text content across ALL occurrences.
            text_tags: set[str] = set()
            all_tags: list[str] = []
            all_seen: set[str] = set()

            for parent in root.iter(parent_tag):
                for child in parent:
                    name = self._strip_ns(child.tag)
                    if name not in all_seen:
                        all_seen.add(name)
                        all_tags.append(name)
                    if child.text and child.text.strip():
                        text_tags.add(name)

            if text_tags:
                # Return text-bearing tags in document order.
                return [t for t in all_tags if t in text_tags]
            # Fallback: return all child tags (first occurrence order).
            return all_tags
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Locale / translation target
    # ------------------------------------------------------------------

    def resolve_translation_target(self, locale_code: str) -> dict[str, str]:
        base = (locale_code or "").split("_")[0].lower()
        meta = TRANSLATION_TARGETS.get(base)
        if meta:
            return dict(meta)
        return {"code": base or "en", "deepl": (base or "en").upper(), "label": (base or "en").title()}

    def set_translation_target(self, locale_code: str) -> None:
        self.translation_target = self.resolve_translation_target(locale_code)

    def available_locales(self) -> dict[str, str]:
        """
        Returns {friendly_name: locale_code} by reading the locales/ directory.
        E.g. {"Português (Brasil)": "pt_BR", "English": "en_US"}
        """
        locales_path = resource_path("locales")
        result: dict[str, str] = {}
        if not os.path.exists(locales_path):
            return result
        for filename in sorted(os.listdir(locales_path)):
            if not filename.endswith(".json"):
                continue
            lang_code = filename.replace(".json", "")
            try:
                with open(os.path.join(locales_path, filename), encoding="utf-8") as f:
                    data = json.load(f)
                lang_name = data.get("_language_name", lang_code)
                result[lang_name] = lang_code
            except (OSError, json.JSONDecodeError):
                result[lang_code] = lang_code
        return result

    # ------------------------------------------------------------------
    # XML loading
    # ------------------------------------------------------------------

    def load_xml(self, xml_path: str, parent_tag: str, target_tag: str) -> tuple[bool, str]:
        """Load XML into the project. Returns (success, error_message)."""
        return self.project.load(xml_path, parent_tag, target_tag)

    # ------------------------------------------------------------------
    # Translation config builder
    # ------------------------------------------------------------------

    def build_translation_config(self, model_label: str, models_available: dict, i18n=None) -> dict:
        """Builds the config dict expected by TranslationWorker / translate_text."""
        model_info = models_available.get(model_label, (self.preferred_model_id, 60, False))
        model_id = model_info[0]
        meta = self.translation_target
        cfg: dict = {
            "service": self.preferred_provider,
            "api_key": self.api_key,
            "model": model_id if self.preferred_provider == "Gemini" else self.ollama_model,
            "target_lang": meta.get("code", "pt"),
            "target_label": meta.get("label", "Portuguese (Brazil)"),
            "deepl_lang": meta.get("deepl", "PT-BR"),
            "source_label": self.source_language_label,
            "translation_context": self.translation_context,
            "ollama_thinking": self.ollama_thinking,
            "checkpoint_dir": user_data_path("checkpoints"),
        }
        if i18n:
            cfg["_strings"] = {
                "checkpoint_loaded":   i18n.get("log_checkpoint_loaded"),
                "all_done":            i18n.get("log_translation_already_complete"),
                "batch_start":         i18n.get("log_mass_translation_start"),
                "sending_gemini":      i18n.get("log_sending_gemini"),
                "cancelled":           i18n.get("log_mass_translation_cancelled"),
                "batch_failed":        i18n.get("log_batch_fail"),
                "items_skipped":       i18n.get("log_items_skipped"),
                "ollama_mini":         i18n.get("log_ollama_mini"),
                "ollama_mini_failed":  i18n.get("log_ollama_mini_failed"),
                "api_error":           i18n.get("log_api_error_prefix"),
                "batch_count":         i18n.get("log_batch_complete"),
                "final_done":          i18n.get("log_mass_translation_done"),
            }
        return cfg

    def current_checkpoint_path(self) -> str:
        """Checkpoint path for the currently loaded XML and translation target."""
        return self.checkpoint_path_for(self.project.xml_path)

    def checkpoint_path_for(self, xml_path: str) -> str:
        """Checkpoint path for an XML file using the app's writable data directory."""
        return self.project.checkpoint_path(
            xml_path,
            self.translation_target.get("code", ""),
            user_data_path("checkpoints"),
        )

    # ------------------------------------------------------------------
    # Batch translation
    # ------------------------------------------------------------------

    def start_batch_translation(
        self,
        config: dict,
        on_entry_translated: Callable[[str, str], None],
        on_log: Callable[[str], None],
        on_done: Callable[[], None],
        on_batch_start: Callable[[list[str]], None] | None = None,
    ) -> None:
        """Instantiate and start a new TranslationWorker."""
        self._worker = TranslationWorker(
            project=self.project,
            config=config,
            on_entry_translated=on_entry_translated,
            on_log=on_log,
            on_done=on_done,
            on_batch_start=on_batch_start,
        )
        self._worker.start()

    def clear_checkpoint(self) -> int:
        """
        Delete the on-disk checkpoint file and reset all in-memory entry
        translations to pending/empty. Returns the number of entries reset.
        """
        if self.project.xml_path:
            checkpoint = self.current_checkpoint_path()
            try:
                os.remove(checkpoint)
            except (FileNotFoundError, OSError):
                pass
        return self.project.reset_translations()

    def cancel_translation(self) -> None:
        if self._worker:
            self._worker.cancel()

    def is_translating(self) -> bool:
        return self._worker is not None and self._worker.is_running()

    # ------------------------------------------------------------------
    # Single-entry translation
    # ------------------------------------------------------------------

    def translate_single(self, xpath: str, config: dict) -> str:
        """Translate one entry synchronously. Run inside a daemon thread."""
        worker = TranslationWorker(
            project=self.project,
            config=config,
            on_entry_translated=lambda *_: None,
            on_log=lambda _: None,
            on_done=lambda: None,
        )
        return worker.translate_single(xpath)

    # ------------------------------------------------------------------
    # Export / Import (delegate to project)
    # ------------------------------------------------------------------

    def export_xml(self, output_path: str) -> bool:
        return self.project.export_xml(output_path)

    def export_json(self, output_path: str) -> bool:
        return self.project.export_json(output_path)

    def export_csv(self, output_path: str) -> bool:
        return self.project.export_csv(output_path)

    def import_json(self, path: str) -> int:
        return self.project.import_json(path)

    def import_csv(self, path: str) -> int:
        return self.project.import_csv(path)

    # ------------------------------------------------------------------
    # Tag presets
    # ------------------------------------------------------------------

    def get_tag_presets(self) -> list[dict]:
        """Load all saved tag presets from disk. Returns [] if none exist."""
        try:
            presets_path = _readable_user_file(PRESETS_FILE)
            if not os.path.exists(presets_path):
                return []
            with open(presets_path, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("presets", [])
        except (OSError, json.JSONDecodeError):
            return []

    def save_tag_preset(
        self,
        label: str,
        parent_tag: str,
        target_tag: str,
        file: str = "",
        folder: str = "",
    ) -> bool:
        """Append a new preset and persist to disk. Returns True on success."""
        import time
        presets = self.get_tag_presets()
        presets.append({
            "id": int(time.time() * 1000),
            "label": label,
            "parent_tag": parent_tag,
            "target_tag": target_tag,
            "file": file,
            "folder": folder,
        })
        return self._write_presets(presets)

    def delete_tag_preset(self, preset_id: int) -> bool:
        """Remove the preset with the given id. Returns True on success."""
        presets = [p for p in self.get_tag_presets() if p.get("id") != preset_id]
        return self._write_presets(presets)

    def rename_tag_preset(self, preset_id: int, new_label: str) -> bool:
        """Change only the label of an existing preset. Returns True on success."""
        presets = self.get_tag_presets()
        for p in presets:
            if p.get("id") == preset_id:
                p["label"] = new_label
                return self._write_presets(presets)
        return False

    def update_preset_folder(self, preset_id: int, folder: str) -> bool:
        """Set or clear the root folder for an existing preset. Returns True on success."""
        presets = self.get_tag_presets()
        for p in presets:
            if p.get("id") == preset_id:
                p["folder"] = folder
                return self._write_presets(presets)
        return False

    def scan_for_xml(self, root_folder: str, filename: str) -> list[str]:
        """Recursively search root_folder for files matching filename. Returns sorted absolute paths."""
        from pathlib import Path
        root = Path(root_folder)
        if not root.is_dir() or not filename:
            return []
        return sorted(str(p) for p in root.rglob(filename) if p.is_file())

    def export_presets(self, path: str) -> bool:
        """Write current presets to a user-specified file (folder field stripped — machine-specific)."""
        try:
            presets = [
                {k: v for k, v in p.items() if k != "folder"}
                for p in self.get_tag_presets()
            ]
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"presets": presets}, f, indent=2, ensure_ascii=False)
            return True
        except OSError:
            return False

    def import_presets(self, path: str) -> tuple[int, int]:
        """
        Merge presets from an external file into the local store.
        Deduplicates by (label, parent_tag, target_tag).
        Returns (imported_count, skipped_count), or (-1, 0) on parse error.
        """
        import time as _time
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            incoming = data.get("presets", [])
            if not isinstance(incoming, list):
                return (-1, 0)
        except (OSError, json.JSONDecodeError, ValueError):
            return (-1, 0)

        existing = self.get_tag_presets()
        existing_keys = {
            (p.get("label", ""), p.get("parent_tag", ""), p.get("target_tag", ""))
            for p in existing
        }
        imported = 0
        skipped = 0
        for preset in incoming:
            if not isinstance(preset, dict):
                skipped += 1
                continue
            key = (
                preset.get("label", ""),
                preset.get("parent_tag", ""),
                preset.get("target_tag", ""),
            )
            if key in existing_keys:
                skipped += 1
                continue
            existing.append({
                "id": int(_time.time() * 1000) + imported,
                "label": preset.get("label", ""),
                "parent_tag": preset.get("parent_tag", ""),
                "target_tag": preset.get("target_tag", ""),
                "file": preset.get("file", ""),
            })
            existing_keys.add(key)
            imported += 1

        if imported > 0 and not self._write_presets(existing):
            return (-1, 0)
        return (imported, skipped)

    def _write_presets(self, presets: list[dict]) -> bool:
        try:
            os.makedirs(user_data_dir(), exist_ok=True)
            with open(user_data_path(PRESETS_FILE), "w", encoding="utf-8") as f:
                json.dump({"presets": presets}, f, indent=2, ensure_ascii=False)
            return True
        except OSError:
            return False
