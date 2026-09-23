from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Sequence
from threading import RLock

from core.extrator import ExtractedEntry, XmlDocumentIndex, indexar_xml
from core.project import TranslationProject
from core.translation_worker import TranslationWorker

TRANSLATION_TARGETS: dict[str, dict[str, str]] = {
    "pt": {"code": "pt", "deepl": "PT-BR", "label": "Portuguese (Brazil)", "display": "Português (Brasil)", "locale": "pt_BR"},
    "en": {"code": "en", "deepl": "EN-US", "label": "English", "display": "English (US)", "locale": "en_US"},
    "es": {"code": "es", "deepl": "ES", "label": "Spanish", "display": "Español (España)", "locale": "es_ES"},
    "fr": {"code": "fr", "deepl": "FR", "label": "French", "display": "Français (France)", "locale": "fr_FR"},
    "ja": {"code": "ja", "deepl": "JA", "label": "Japanese", "display": "日本語 (日本)", "locale": "ja_JP"},
    "it": {"code": "it", "deepl": "IT", "label": "Italian", "display": "Italiano", "locale": "it_IT"},
    "ru": {"code": "ru", "deepl": "RU", "label": "Russian", "display": "Русский", "locale": "ru_RU"},
    "da": {"code": "da", "deepl": "DA", "label": "Danish", "display": "Dansk", "locale": "da_DK"},
    "tr": {"code": "tr", "deepl": "TR", "label": "Turkish", "display": "Türkçe", "locale": "tr_TR"},
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


def _normalize_tag_list(value) -> list[str]:
    """Return a stable, deduplicated list from legacy or current tag values."""
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Sequence):
        values = value
    else:
        values = []

    normalized: list[str] = []
    for item in values:
        if not isinstance(item, str):
            continue
        tag = item.strip()
        if tag and tag not in normalized:
            normalized.append(tag)
    return normalized


def _normalize_preset(preset: dict) -> dict:
    """Normalize a preset in memory while retaining the legacy UI field."""
    normalized = dict(preset)
    target_tags = _normalize_tag_list(preset.get("target_tags"))
    if not target_tags:
        target_tags = _normalize_tag_list(preset.get("target_tag"))
    context_tags = _normalize_tag_list(preset.get("context_tags"))
    normalized["target_tags"] = target_tags
    normalized["context_tags"] = context_tags
    normalized["target_tag"] = target_tags[0] if target_tags else ""
    return normalized


def _preset_for_storage(preset: dict) -> dict:
    """Serialize presets using only the current list-based tag schema."""
    stored = _normalize_preset(preset)
    stored.pop("target_tag", None)
    return stored


def _preset_key(preset: dict) -> tuple[str, str, tuple[str, ...], tuple[str, ...]]:
    normalized = _normalize_preset(preset)
    return (
        str(normalized.get("label", "")),
        str(normalized.get("parent_tag", "")),
        tuple(normalized["target_tags"]),
        tuple(normalized["context_tags"]),
    )


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
        self._xml_index: XmlDocumentIndex | None = None
        self._xml_index_lock = RLock()
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
        self.preferred_ui_mode: str = "modern"
        self.last_update_check: float = 0.0
        self.skipped_update_version: str = ""

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
            ui_mode = data.get("ui_mode", "modern")
            self.preferred_ui_mode = ui_mode if ui_mode in {"classic", "modern"} else "modern"
            try:
                self.last_update_check = float(data.get("last_update_check", 0.0))
            except (TypeError, ValueError):
                self.last_update_check = 0.0
            self.skipped_update_version = str(data.get("skipped_update_version", ""))
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
            "ui_mode": self.preferred_ui_mode,
            "last_update_check": self.last_update_check,
            "skipped_update_version": self.skipped_update_version,
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

    def save_preferred_ui_mode(self, ui_mode: str) -> None:
        """Persist which QML shell should be loaded on the next launch."""
        if ui_mode not in {"classic", "modern"}:
            return
        self.preferred_ui_mode = ui_mode
        self.save_config(
            api_key=self.api_key,
            model_label=self.preferred_model_label,
            model_id=self.preferred_model_id,
        )

    def save_update_preferences(
        self,
        *,
        last_check: float | None = None,
        skipped_version: str | None = None,
    ) -> None:
        """Persist updater scheduling without overwriting the rest of the config."""
        if last_check is not None:
            self.last_update_check = last_check
        if skipped_version is not None:
            self.skipped_update_version = skipped_version
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

    def _get_xml_index(self, xml_path: str) -> tuple[bool, XmlDocumentIndex | str]:
        """Return the current document index, rebuilding it only when the file changed."""
        with self._xml_index_lock:
            if self._xml_index and self._xml_index.matches_file(xml_path):
                return True, self._xml_index
            success, result = indexar_xml(xml_path)
            if success and isinstance(result, XmlDocumentIndex):
                self._xml_index = result
            return success, result

    def analyze_xml(self, xml_path: str) -> tuple[bool, list[str] | str]:
        """Prepare a reusable index and return the available parent tags."""
        success, result = self._get_xml_index(xml_path)
        if not success or isinstance(result, str):
            return False, result
        return True, list(result.parent_tags)

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
        success, result = self.analyze_xml(xml_path)
        return result if success and isinstance(result, list) else []

    def get_child_tags(self, xml_path: str, parent_tag: str) -> list[str]:
        """
        Return unique child tag names that have non-empty text content inside
        any occurrence of parent_tag in the document.

        Prefers text-bearing children; falls back to all children if none have text.
        """
        success, result = self._get_xml_index(xml_path)
        if not success or isinstance(result, str):
            return []
        return result.child_tags(parent_tag)

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

    def available_translation_targets(self) -> dict[str, str]:
        """Return native display names and locale codes for supported targets."""
        return {
            meta["display"]: meta["locale"]
            for meta in TRANSLATION_TARGETS.values()
        }

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

    def load_xml(
        self,
        xml_path: str,
        parent_tag: str,
        target_tag: str | Sequence[str],
        context_tags: Sequence[str] = (),
    ) -> tuple[bool, str]:
        """Load XML into the project. Returns (success, error_message)."""
        target_tags = [target_tag] if isinstance(target_tag, str) else list(target_tag)
        success, result = self.extract_xml_entries(
            xml_path, parent_tag, target_tags, context_tags
        )
        if not success or isinstance(result, str):
            return False, result
        self.apply_xml_entries(xml_path, parent_tag, target_tags, context_tags, result)
        return True, ""

    def extract_xml_entries(
        self,
        xml_path: str,
        parent_tag: str,
        target_tags: Sequence[str],
        context_tags: Sequence[str] = (),
    ) -> tuple[bool, list[ExtractedEntry] | str]:
        """Prepare entries without mutating project state; safe to run in a worker."""
        success, result = self._get_xml_index(xml_path)
        if not success or isinstance(result, str):
            return False, result
        return result.extract_entries(parent_tag, target_tags, context_tags)

    def apply_xml_entries(
        self,
        xml_path: str,
        parent_tag: str,
        target_tags: Sequence[str],
        context_tags: Sequence[str],
        entries: Sequence[ExtractedEntry],
    ) -> None:
        """Apply worker-prepared entries on the owning/UI thread."""
        self.project.load_extracted(
            xml_path, parent_tag, target_tags, context_tags, entries
        )

    def preview_tag_selection(
        self,
        xml_path: str,
        parent_tag: str,
        target_tags: Sequence[str],
        context_tags: Sequence[str] = (),
    ) -> dict[str, int]:
        """Count the rows a tag selection would create without mutating the project."""
        success, result = self._get_xml_index(xml_path)
        if not success or isinstance(result, str):
            return {"records": 0, "lines": 0}
        return result.preview(parent_tag, target_tags, context_tags)

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
            "checkpoint_fallbacks": (
                self.checkpoint_fallbacks_for(self.project.xml_path)
                if self.project.xml_path
                else []
            ),
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
                "context_unsupported": i18n.get("log_context_unsupported"),
            }
        return cfg

    def current_checkpoint_path(self) -> str:
        """Checkpoint path for the currently loaded XML and translation target."""
        return self.checkpoint_path_for(self.project.xml_path)

    def checkpoint_path_for(self, xml_path: str) -> str:
        """Checkpoint path isolated by XML, target language, and selected tags."""
        return self.project.checkpoint_path(
            xml_path,
            self.translation_target.get("code", ""),
            user_data_path("checkpoints"),
            parent_tag=self.project.parent_tag,
            target_tags=self.project.target_tags,
            context_tags=self.project.context_tags,
        )

    def legacy_checkpoint_path_for(self, xml_path: str) -> str:
        """Return the filename used before tag selections became part of the identity."""
        return self.project.checkpoint_path(
            xml_path,
            self.translation_target.get("code", ""),
            user_data_path("checkpoints"),
        )

    def checkpoint_fallbacks_for(self, xml_path: str) -> list[str]:
        """Return legacy checkpoints in precedence order for controlled migration."""
        fallbacks = [self.legacy_checkpoint_path_for(xml_path)]
        if self.translation_target.get("code", "") == "pt":
            fallbacks.append(_legacy_cwd_path("textos_traduzidos_checkpoint.json"))
        return fallbacks

    def restore_checkpoint_for(self, xml_path: str) -> int:
        """Restore current progress, falling back to legacy data only when absent."""
        return self.project.load_checkpoint_with_fallback(
            self.checkpoint_path_for(xml_path),
            self.checkpoint_fallbacks_for(xml_path),
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
            checkpoint_paths = [
                self.current_checkpoint_path(),
                *self.checkpoint_fallbacks_for(self.project.xml_path),
            ]
            for checkpoint in dict.fromkeys(checkpoint_paths):
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
            if not isinstance(data, dict) or not isinstance(data.get("presets"), list):
                return []
            return [_normalize_preset(preset) for preset in data["presets"] if isinstance(preset, dict)]
        except (OSError, json.JSONDecodeError, ValueError):
            return []

    def save_tag_preset(
        self,
        label: str,
        parent_tag: str,
        target_tag: str | Sequence[str],
        file: str = "",
        folder: str = "",
        context_tags: Sequence[str] = (),
    ) -> bool:
        """Append a new preset and persist to disk. Returns True on success."""
        import time
        target_tags = _normalize_tag_list(target_tag)
        normalized_context = _normalize_tag_list(context_tags)
        if not target_tags or set(target_tags) & set(normalized_context):
            return False
        presets = self.get_tag_presets()
        presets.append({
            "id": int(time.time() * 1000),
            "label": label,
            "parent_tag": parent_tag,
            "target_tags": target_tags,
            "context_tags": normalized_context,
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
                {k: v for k, v in _preset_for_storage(p).items() if k != "folder"}
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
        Deduplicates by label, parent tag, target tags, and context tags.
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
        existing_keys = {_preset_key(p) for p in existing}
        imported = 0
        skipped = 0
        for preset in incoming:
            if not isinstance(preset, dict):
                skipped += 1
                continue
            normalized = _normalize_preset(preset)
            if not normalized["target_tags"] or set(normalized["target_tags"]) & set(
                normalized["context_tags"]
            ):
                skipped += 1
                continue
            key = _preset_key(normalized)
            if key in existing_keys:
                skipped += 1
                continue
            existing.append({
                "id": int(_time.time() * 1000) + imported,
                "label": normalized.get("label", ""),
                "parent_tag": normalized.get("parent_tag", ""),
                "target_tags": normalized["target_tags"],
                "context_tags": normalized["context_tags"],
                "file": normalized.get("file", ""),
                "folder": "",
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
                json.dump(
                    {"presets": [_preset_for_storage(preset) for preset in presets]},
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
            return True
        except OSError:
            return False
