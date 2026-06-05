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

PROVIDER_URLS: dict[str, str] = {
    "Gemini": "https://aistudio.google.com/app/apikey",
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
        self.ollama_model: str = "llama3"
        self._api_keys: dict[str, str] = {}
        self.translation_target: dict[str, str] = TRANSLATION_TARGETS["pt"].copy()

        self._load_config()

    # ------------------------------------------------------------------
    # Config persistence
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                data = json.load(f)
            self.preferred_provider = data.get("provider", "Gemini")
            self.preferred_locale = data.get("locale", "pt_BR")
            self.preferred_model_id = data.get("preferred_model_id", self.preferred_model_id)
            self.preferred_model_label = data.get("preferred_model", "")
            self.ollama_model = data.get("ollama_model", "llama3")
            # Per-provider keys (new format)
            self._api_keys = data.get("api_keys", {})
            # Backward compat: old config stored a single api_key for Gemini
            if not self._api_keys.get("Gemini") and data.get("api_key"):
                self._api_keys["Gemini"] = data["api_key"]
            self.api_key = self._api_keys.get(self.preferred_provider, "")
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
            "preferred_model": model_label,
            "preferred_model_id": model_id,
            "ollama_model": self.ollama_model,
            "api_keys": {k: v for k, v in self._api_keys.items() if v},
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass

    def save_preferred_locale(self, locale_code: str) -> None:
        """Persist the selected UI locale independently of a full save_config call."""
        self.preferred_locale = locale_code
        self.save_config(
            api_key=self.api_key,
            model_label=self.preferred_model_label,
            model_id=self.preferred_model_id,
        )

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

    def build_translation_config(self, model_label: str, models_available: dict) -> dict:
        """Builds the config dict expected by TranslationWorker / translate_text."""
        model_info = models_available.get(model_label, (self.preferred_model_id, 60, False))
        model_id = model_info[0]
        meta = self.translation_target
        return {
            "service": self.preferred_provider,
            "api_key": self.api_key,
            "model": model_id if self.preferred_provider == "Gemini" else self.ollama_model,
            "target_lang": meta.get("code", "pt"),
            "target_label": meta.get("label", "Portuguese (Brazil)"),
            "deepl_lang": meta.get("deepl", "PT-BR"),
            "source_label": self.source_language_label,
        }

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
        checkpoint = "textos_traduzidos_checkpoint.json"
        try:
            os.remove(checkpoint)
        except FileNotFoundError:
            pass
        except OSError:
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
