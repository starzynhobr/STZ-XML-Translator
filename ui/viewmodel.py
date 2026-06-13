"""
PySide6 ViewModel bridge — connects AppController to QML.

TranslationTableModel  — QAbstractTableModel fed to QML TableView
AppViewModel           — QObject with Signals/Slots/Properties for the UI
"""
from __future__ import annotations

import os
import threading

from PySide6.QtCore import Property as QProperty
from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtWidgets import QFileDialog

from core.app_controller import PROVIDER_URLS, AppController
from core.i18n import I18nManager
from core.project import TranslationEntry
from core.tradutor_api import list_gemini_models

# ---------------------------------------------------------------------------
# Table model
# ---------------------------------------------------------------------------

class TranslationTableModel(QAbstractTableModel):
    """Exposes TranslationProject entries to QML as a 2-column table."""

    XpathRole = Qt.UserRole
    StatusRole = Qt.UserRole + 1

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[TranslationEntry] = []
        self._index: dict[str, int] = {}
        self._headers = ["#", "Original", "Translation"]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else 3

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._rows):
            return None
        entry = self._rows[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            if col == 0:
                return index.row() + 1
            return entry.original if col == 1 else entry.translation
        if role == self.XpathRole:
            return entry.xpath
        if role == self.StatusRole:
            return entry.status
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole and 0 <= section < 3:
            return self._headers[section]
        return None

    def roleNames(self) -> dict:
        return {
            Qt.DisplayRole: b"display",
            self.XpathRole: b"xpath",
            self.StatusRole: b"entryStatus",
        }

    def update_headers(self, original_label: str, translation_label: str) -> None:
        self._headers = ["#", original_label, translation_label]
        self.headerDataChanged.emit(Qt.Horizontal, 0, 2)

    def refresh_all(self, entries: dict[str, TranslationEntry]) -> None:
        self.beginResetModel()
        self._rows = list(entries.values())
        self._index = {e.xpath: i for i, e in enumerate(self._rows)}
        self.endResetModel()

    def update_entry(self, xpath: str, translation: str, status: str) -> None:
        row = self._index.get(xpath)
        if row is None:
            return
        self._rows[row].translation = translation
        self._rows[row].status = status
        left = self.index(row, 0)
        right = self.index(row, 2)
        self.dataChanged.emit(left, right, [Qt.DisplayRole, self.StatusRole])

    def xpath_at_row(self, row: int) -> str | None:
        if 0 <= row < len(self._rows):
            return self._rows[row].xpath
        return None

    def row_of(self, xpath: str) -> int:
        return self._index.get(xpath, -1)


# ---------------------------------------------------------------------------
# Main ViewModel
# ---------------------------------------------------------------------------

class AppViewModel(QObject):
    """Bridge between AppController (Python) and QML UI."""

    # Signals emitted to QML
    logAppended = Signal(str)
    progressChanged = Signal(int, int)
    modelsChanged = Signal(list)
    translatingChanged = Signal(bool)
    singleTranslatingChanged = Signal(bool)
    entrySelected = Signal(str, str, str)
    languageChanged = Signal()
    xmlLoaded = Signal(int)
    errorOccurred = Signal(str)
    entryCountChanged = Signal(int)
    loadedFileNameChanged = Signal()
    providerChanged = Signal()
    parentTagsChanged = Signal()
    childTagsChanged = Signal()
    selectedTagChanged = Signal(str, str)   # (parent_tag, target_tag)
    xmlPathSelectedChanged = Signal()        # fired when a file is chosen (before entries load)
    tagPresetsChanged = Signal()             # fired when the preset list changes
    gameFolderChanged = Signal()             # fired when the global game folder changes
    translationContextChanged = Signal()     # fired when the translation context/theme changes
    xmlPathsFound    = Signal(list)          # multiple XML files found during folder scan
    translationTargetChanged = Signal()      # fired when translation target locale changes
    themeChanged = Signal()                  # fired when the active theme changes
    apiKeyDialogRequested = Signal(str, str, str)  # (dialog_title, prompt_label, current_key)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._ctrl = AppController()
        # Load the locale the user last selected (falls back to pt_BR if no config)
        saved_locale = self._ctrl.preferred_locale
        self._i18n = I18nManager(language=saved_locale)
        self._table = TranslationTableModel(self)
        self._table.update_headers(
            self._i18n.get("original_text_label"),
            self._i18n.get("translation_label"),
        )

        # _models: {bare_label: (model_id, timeout_s, is_paid)}
        self._models: dict[str, tuple[str, int, bool]] = {
            "Gemini Flash Lite Latest": ("models/gemini-flash-lite-latest", 60, False),
            "Gemini Flash Latest": ("models/gemini-flash-latest", 60, False),
        }
        self._selected_model_label: str = list(self._models.keys())[0]
        self._is_translating: bool = False
        self._is_single_translating: bool = False
        self._selected_xpath: str = ""
        self._skip_rows: int = 0
        self._parent_tags: list[str] = []
        self._child_tags: list[str] = []
        self._child_tags_cache: dict[tuple[str, str], list[str]] = {}
        self._xml_path_selected: str = ""   # path chosen via file dialog, before entries are loaded

        # Restore preferred model from config
        saved_label = self._ctrl.preferred_model_label
        if saved_label and saved_label in self._models:
            self._selected_model_label = saved_label

        # Use saved translation target if available; fall back to UI locale.
        target_locale = self._ctrl.preferred_translation_target or saved_locale
        self._ctrl.set_translation_target(target_locale)

        # Kick off model sync if Gemini key exists
        if self._ctrl.preferred_provider == "Gemini" and self._ctrl.api_key:
            threading.Thread(target=self._fetch_models, daemon=True).start()

    # ------------------------------------------------------------------
    # Properties — table / state
    # ------------------------------------------------------------------

    @QProperty(QObject, constant=True)
    def tableModel(self) -> TranslationTableModel:
        return self._table

    @QProperty(bool, notify=translatingChanged)
    def isTranslating(self) -> bool:
        return self._is_translating

    @QProperty(bool, notify=singleTranslatingChanged)
    def isSingleTranslating(self) -> bool:
        return self._is_single_translating

    @QProperty(int, notify=entryCountChanged)
    def entryCount(self) -> int:
        return len(self._ctrl.project.entries)

    @QProperty(str, notify=loadedFileNameChanged)
    def loadedFileName(self) -> str:
        # Show filename as soon as a file is chosen, even before entries are loaded.
        path = self._xml_path_selected or self._ctrl.project.xml_path
        return os.path.basename(path) if path else ""

    @QProperty(str, notify=loadedFileNameChanged)
    def loadedFileDir(self) -> str:
        """Directory of the currently loaded (or selected) XML file."""
        path = self._xml_path_selected or self._ctrl.project.xml_path
        return os.path.dirname(path) if path else ""

    @QProperty(str, notify=loadedFileNameChanged)
    def loadedFileRelPath(self) -> str:
        """
        Path to save in a preset's file field.
        - With game_folder: relative path (portable across machines in the same game install).
        - Without game_folder: full absolute path (works on this machine without extra setup).
        """
        path = self._xml_path_selected or self._ctrl.project.xml_path
        if not path:
            return ""
        game_folder = self._ctrl.game_folder
        if game_folder:
            try:
                return os.path.relpath(path, game_folder)
            except ValueError:
                pass  # different drives on Windows — fall through to absolute
        return path  # absolute path when no game_folder defined

    @QProperty(str, notify=gameFolderChanged)
    def gameFolder(self) -> str:
        """Global game root folder used to resolve preset file hints."""
        return self._ctrl.game_folder

    @Slot(str)
    def setGameFolder(self, path: str) -> None:
        """Persist the global game folder and refresh preset validity."""
        self._ctrl.save_game_folder(path)
        self.gameFolderChanged.emit()
        self.tagPresetsChanged.emit()

    @QProperty(bool, notify=xmlPathSelectedChanged)
    def hasXmlPath(self) -> bool:
        """True once the user has picked an XML file (even before entries load)."""
        return bool(self._xml_path_selected or self._ctrl.project.xml_path)

    @QProperty(list, notify=parentTagsChanged)
    def parentTags(self) -> list:
        return self._parent_tags

    @QProperty(list, notify=childTagsChanged)
    def childTags(self) -> list:
        return self._child_tags

    @QProperty(list, notify=tagPresetsChanged)
    def tagPresets(self) -> list:
        """Preset list enriched with file_exists: True/False/None per item."""
        game_folder = self._ctrl.game_folder
        # Cache resolve results within this call (multiple presets may share a file)
        _resolve_cache: dict[str, str] = {}

        def _resolve(file_hint: str) -> str:
            if file_hint not in _resolve_cache:
                _resolve_cache[file_hint] = self._ctrl.resolve_preset_file(file_hint)
            return _resolve_cache[file_hint]

        result = []
        for p in self._ctrl.get_tag_presets():
            enriched = dict(p)
            # preset_id: alias for id (QML treats "id" as a reserved keyword)
            enriched["preset_id"] = p.get("id", 0)
            file_hint = p.get("file", "")
            # file_name: just the basename, for compact display in the dialog
            enriched["file_name"] = os.path.basename(file_hint) if file_hint else ""
            if file_hint:
                is_abs = os.path.isabs(file_hint)
                if is_abs or game_folder:
                    # Can attempt resolution → show ✓ or ✗
                    enriched["file_exists"] = bool(_resolve(file_hint))
                # else: relative path and no game_folder → omit (undefined in QML)
            result.append(enriched)
        return result

    # ------------------------------------------------------------------
    # Properties — models (Gemini)
    # ------------------------------------------------------------------

    @QProperty(list, notify=modelsChanged)
    def modelLabels(self) -> list:
        """Displayed labels with localised tier badge."""
        free = self._i18n.translations.get("tier_free", "Free")
        paid = self._i18n.translations.get("tier_paid", "Paid")
        return [
            f"{lbl} ({paid if is_p else free})"
            for lbl, (_, _, is_p) in self._models.items()
        ]

    @QProperty(int, notify=modelsChanged)
    def selectedModelIndex(self) -> int:
        labels = list(self._models.keys())
        try:
            return labels.index(self._selected_model_label)
        except ValueError:
            return 0

    # ------------------------------------------------------------------
    # Properties — provider
    # ------------------------------------------------------------------

    @QProperty(list, constant=True)
    def providers(self) -> list:
        return self._ctrl.available_providers()

    @QProperty(str, notify=providerChanged)
    def selectedProvider(self) -> str:
        return self._ctrl.preferred_provider

    @QProperty(bool, notify=providerChanged)
    def providerNeedsApiKey(self) -> bool:
        return self._ctrl.preferred_provider not in ("Ollama (Local)", "Google Translate (Free)")

    _AI_PROVIDERS = frozenset({"Gemini", "Ollama (Local)"})

    @QProperty(bool, notify=providerChanged)
    def providerUsesAi(self) -> bool:
        """True for generative AI providers (Gemini, Ollama) that use context/theme prompts."""
        return self._ctrl.preferred_provider in self._AI_PROVIDERS

    @QProperty(str, notify=providerChanged)
    def providerApiKeyLinkText(self) -> str:
        mapping = {
            "Gemini": "api_key_link_gemini",
            "Google Translate (Free)": "google_translate_free_note",
            "DeepL": "api_key_link_deepl",
            "Microsoft Azure": "api_key_link_azure",
            "Ollama (Local)": "ollama_no_key",
        }
        key = mapping.get(self._ctrl.preferred_provider, "api_key_link_gemini")
        return self._i18n.get(key)

    @QProperty(str, notify=providerChanged)
    def providerApiKeyUrl(self) -> str:
        return PROVIDER_URLS.get(self._ctrl.preferred_provider, "")

    @QProperty(str, notify=providerChanged)
    def currentApiKey(self) -> str:
        """Pre-fills the API key dialog with the currently stored key."""
        return self._ctrl.get_api_key(self._ctrl.preferred_provider)

    @QProperty(str, notify=providerChanged)
    def ollamaModel(self) -> str:
        return self._ctrl.ollama_model

    @QProperty(str, notify=translationContextChanged)
    def translationContext(self) -> str:
        return self._ctrl.translation_context

    # ------------------------------------------------------------------
    # Properties — i18n
    # ------------------------------------------------------------------

    @QProperty("QVariantMap", notify=languageChanged)
    def strings(self) -> dict:
        return dict(self._i18n.translations)

    @QProperty("QVariantMap", notify=languageChanged)
    def availableLocales(self) -> dict:
        return self._ctrl.available_locales()

    @QProperty(str, notify=languageChanged)
    def currentLocaleCode(self) -> str:
        return self._i18n.language

    @QProperty(str, notify=translationTargetChanged)
    def translationTargetCode(self) -> str:
        """The locale code used as the AI translation target (independent of UI language)."""
        return self._ctrl.preferred_translation_target or self._ctrl.preferred_locale

    # ------------------------------------------------------------------
    # Properties — theme
    # ------------------------------------------------------------------

    @QProperty("QVariantList", constant=True)
    def themeNames(self) -> list:
        from ui.theme import THEMES
        return list(THEMES.keys())

    @QProperty(str, notify=themeChanged)
    def currentThemeName(self) -> str:
        return self._ctrl.preferred_theme

    # ------------------------------------------------------------------
    # Slots — provider / model
    # ------------------------------------------------------------------

    @Slot(str)
    def selectProvider(self, name: str) -> None:
        self._ctrl.preferred_provider = name
        self._ctrl.api_key = self._ctrl.get_api_key(name)
        self._ctrl.save_config(
            api_key=self._ctrl.api_key,
            model_label=self._selected_model_label,
            model_id=self._ctrl.preferred_model_id,
            provider=name,
        )
        self.providerChanged.emit()
        if name == "Gemini" and self._ctrl.api_key:
            threading.Thread(target=self._fetch_models, daemon=True).start()

    @Slot(int)
    def selectModelByIndex(self, index: int) -> None:
        labels = list(self._models.keys())
        if 0 <= index < len(labels):
            self._selected_model_label = labels[index]
            mid, _, _ = self._models[self._selected_model_label]
            self._ctrl.save_config(
                api_key=self._ctrl.api_key,
                model_label=self._selected_model_label,
                model_id=mid,
            )

    @Slot(str)
    def setOllamaModel(self, model: str) -> None:
        self._ctrl.ollama_model = model
        self._ctrl.save_config(
            api_key=self._ctrl.api_key,
            model_label=self._selected_model_label,
            model_id=self._ctrl.preferred_model_id,
            ollama_model=model,
        )
        self.providerChanged.emit()

    @Slot(str)
    def setTranslationContext(self, context: str) -> None:
        self._ctrl.translation_context = context
        self._ctrl.save_config(
            api_key=self._ctrl.api_key,
            model_label=self._selected_model_label,
            model_id=self._ctrl.preferred_model_id,
        )
        self.translationContextChanged.emit()

    # ------------------------------------------------------------------
    # Slots — language
    # ------------------------------------------------------------------

    @Slot(str)
    def changeUiLanguage(self, locale_code: str) -> None:
        """Change the app UI language only. Does NOT affect the translation target."""
        self._i18n.load_language(locale_code)
        self._ctrl.save_preferred_locale(locale_code)
        self._table.update_headers(
            self._i18n.get("original_text_label"),
            self._i18n.get("translation_label"),
        )
        self.languageChanged.emit()
        # Properties whose text comes from i18n but are notified via providerChanged
        # (e.g. providerApiKeyLinkText) need an extra nudge when the language changes.
        self.providerChanged.emit()

    @Slot(str)
    def setTranslationTarget(self, locale_code: str) -> None:
        """Change the AI translation target language only. Does NOT affect UI strings."""
        self._ctrl.save_preferred_translation_target(locale_code)
        self.translationTargetChanged.emit()
        # Rebuild model labels with new locale tier strings
        self.modelsChanged.emit(self.modelLabels)
        # providerApiKeyLinkText depends on _i18n — refresh it too
        self.providerChanged.emit()

    # ------------------------------------------------------------------
    # Slots — table selection / translation
    # ------------------------------------------------------------------

    @Slot(int)
    def selectRow(self, row: int) -> None:
        xpath = self._table.xpath_at_row(row)
        if xpath:
            self._selected_xpath = xpath
            entry = self._ctrl.project.get_entry(xpath)
            if entry:
                self.entrySelected.emit(xpath, entry.original, entry.translation)

    @Slot(str, str)
    def approveTranslation(self, xpath: str, text: str) -> None:
        self._ctrl.project.set_translation(xpath, text, status="done")
        self._table.update_entry(xpath, text, "done")
        done, total = self._ctrl.project.stats()
        self.progressChanged.emit(done, total)

    @Slot()
    def approveAllTranslations(self) -> None:
        for entry in self._ctrl.project.entries.values():
            if entry.translation and entry.translation.strip():
                self._ctrl.project.set_translation(entry.xpath, entry.translation, status="done")
        self._table.refresh_all(self._ctrl.project.entries)
        done, total = self._ctrl.project.stats()
        self.progressChanged.emit(done, total)

    @Slot()
    def translateSelected(self) -> None:
        if not self._selected_xpath:
            return
        if self._ctrl.preferred_provider != "Ollama (Local)" and not self._ctrl.api_key:
            self.errorOccurred.emit(self._i18n.get("log_api_key_needed"))
            return
        if self._is_single_translating:
            return  # already running, ignore extra clicks
        xpath = self._selected_xpath
        config = self._ctrl.build_translation_config(self._selected_model_label, self._models, self._i18n)

        self._is_single_translating = True
        self.singleTranslatingChanged.emit(True)

        def worker() -> None:
            self._table.update_entry(xpath, "…", "translating")
            result = self._ctrl.translate_single(xpath, config)
            self._ctrl.project.set_translation(xpath, result, status="done")
            self._table.update_entry(xpath, result, "done")
            done, total = self._ctrl.project.stats()
            self.progressChanged.emit(done, total)
            entry = self._ctrl.project.get_entry(xpath)
            if entry and self._selected_xpath == xpath:
                self.entrySelected.emit(xpath, entry.original, result)
            self._is_single_translating = False
            self.singleTranslatingChanged.emit(False)

        threading.Thread(target=worker, daemon=True).start()

    @Slot()
    @Slot(int)
    def setSkipRows(self, n: int) -> None:
        self._skip_rows = max(0, n)

    def startBatchTranslation(self) -> None:
        if self._ctrl.preferred_provider != "Ollama (Local)" and not self._ctrl.api_key:
            self.errorOccurred.emit(self._i18n.get("log_api_key_needed"))
            return
        self._set_translating(True)
        config = self._ctrl.build_translation_config(self._selected_model_label, self._models, self._i18n)
        config["skip_rows"] = self._skip_rows

        def on_batch_start(xpaths: list[str]) -> None:
            # Mark rows yellow ("translating") so the user sees activity
            # while waiting for the API response — especially important for
            # Gemini where the whole batch is sent in one call.
            for xpath in xpaths:
                self._table.update_entry(xpath, "…", "translating")

        def on_entry(xpath: str, text: str) -> None:
            self._table.update_entry(xpath, text, "done")
            done, total = self._ctrl.project.stats()
            self.progressChanged.emit(done, total)

        def on_log(msg: str) -> None:
            self.logAppended.emit(msg)

        def on_done() -> None:
            self._set_translating(False)

        self._ctrl.start_batch_translation(config, on_entry, on_log, on_done, on_batch_start)

    @Slot()
    def cancelTranslation(self) -> None:
        self._ctrl.cancel_translation()
        self.logAppended.emit(self._i18n.get("log_mass_translation_cancelled"))

    # ------------------------------------------------------------------
    # Slots — file operations
    # ------------------------------------------------------------------

    @Slot(str, str)
    def loadXml(self, parent_tag: str, target_tag: str) -> None:
        """
        Open a file-picker, then inspect the XML structure to populate the
        tag dropdowns.  Deliberately does NOT load entries into the table —
        the user must choose parent + child tags and click Recarregar.
        This avoids auto-loading huge files with irrelevant content.
        """
        path, _ = QFileDialog.getOpenFileName(
            caption=self._i18n.get("select_xml_file"),
            filter="XML Files (*.xml);;All Files (*.*)",
        )
        if not path:
            return

        # Store chosen path and update filename label immediately.
        self._xml_path_selected = path
        self.xmlPathSelectedChanged.emit()
        self.loadedFileNameChanged.emit()

        # Reset pending tags so stale selections from a previous file don't carry over.
        self._pending_parent_tag = ""
        self._pending_target_tag = ""
        self._child_tags_cache.clear()

        # Detect repeating elements with text children → populate parent dropdown.
        self._parent_tags = self._ctrl.get_parent_tags(path)
        self.parentTagsChanged.emit()

        # Clear child tags until user picks a parent.
        self._child_tags = []
        self.childTagsChanged.emit()

        # Clear combo field values so user actively chooses.
        self.selectedTagChanged.emit("", "")

    @Slot()
    def reloadXml(self) -> None:
        """Load entries using the currently selected path + tag settings."""
        path = self._xml_path_selected or self._ctrl.project.xml_path
        if not path:
            return
        parent = self._pending_parent_tag or self._ctrl.project.parent_tag
        target = self._pending_target_tag or self._ctrl.project.target_tag
        if not parent or not target:
            self.logAppended.emit(self._i18n.get("log_select_tags_first"))
            return
        self._load_xml(path, parent, target)

    def _load_xml(self, path: str, parent_tag: str, target_tag: str) -> None:
        sucesso, err = self._ctrl.load_xml(path, parent_tag, target_tag)
        if sucesso:
            # Keep _xml_path_selected in sync with the successfully loaded path.
            self._xml_path_selected = path

            # Auto-restore checkpoint for this specific file.
            from core.project import TranslationProject
            cp_path = TranslationProject.checkpoint_path(path)
            _legacy = "textos_traduzidos_checkpoint.json"
            if not os.path.exists(cp_path) and os.path.exists(_legacy):
                import shutil
                shutil.copy2(_legacy, cp_path)
            restored = self._ctrl.project.load_checkpoint(cp_path)
            if restored:
                self.logAppended.emit(
                    self._i18n.get("log_checkpoint_loaded", n=restored)
                )

            self._table.refresh_all(self._ctrl.project.entries)
            count = len(self._ctrl.project.entries)
            done, total = self._ctrl.project.stats()
            self.progressChanged.emit(done, total)
            self.xmlLoaded.emit(count)
            self.entryCountChanged.emit(count)
            self.loadedFileNameChanged.emit()
            self.xmlPathSelectedChanged.emit()
            # Keep tag pickers in sync with what was actually loaded.
            self._parent_tags = self._ctrl.get_parent_tags(path)
            self.parentTagsChanged.emit()
            self._pending_parent_tag = parent_tag
            self._child_tags = self._ctrl.get_child_tags(path, parent_tag)
            self._pending_target_tag = target_tag
            self.childTagsChanged.emit()
            self.selectedTagChanged.emit(parent_tag, target_tag)
            filename = os.path.basename(path)
            self.logAppended.emit(
                self._i18n.get("log_load_success", filename=filename, count=count)
            )
        else:
            self.errorOccurred.emit(err)
            self.logAppended.emit(err)

    @Slot()
    def saveInPlace(self) -> None:
        """
        Overwrite the currently loaded XML file with the translated content,
        then immediately reload it so the table reflects the new state:
        the formerly-translated text becomes the new 'original', ready for
        a follow-up translation pass if needed.
        """
        path = self._ctrl.project.xml_path
        parent_tag = self._ctrl.project.parent_tag
        target_tag = self._ctrl.project.target_tag
        if not path:
            return
        if self._ctrl.export_xml(path):
            filename = os.path.basename(path)
            self.logAppended.emit(self._i18n.get("log_saved_inplace", filename=filename))
            # Clear the checkpoint — no longer needed after saving.
            self._ctrl.clear_checkpoint()
            # Reload from the freshly-written file so the UI shows the new
            # content as the original text (translations column starts empty).
            self._load_xml(path, parent_tag, target_tag)
        else:
            self.errorOccurred.emit(self._i18n.get("export_fail"))

    @Slot()
    def clearCheckpoint(self) -> None:
        """Manually reset all translations to pending and delete the checkpoint file."""
        count = self._ctrl.clear_checkpoint()
        self._table.refresh_all(self._ctrl.project.entries)
        done, total = self._ctrl.project.stats()
        self.progressChanged.emit(done, total)
        self.logAppended.emit(
            self._i18n.get("log_checkpoint_cleared", count=count)
        )

    @Slot(str)
    def exportXml(self, path: str) -> None:
        if not path:
            # Pre-fill the dialog with the currently loaded filename so the user
            # doesn't have to retype it (they can still rename before saving).
            default = self._ctrl.project.xml_path or ""
            path, _ = QFileDialog.getSaveFileName(
                caption=self._i18n.get("save_as"),
                dir=default,
                filter="XML Files (*.xml);;All Files (*.*)",
            )
        if path and self._ctrl.export_xml(path):
            self.logAppended.emit(self._i18n.get("log_xml_exported", path=path))
        elif path:
            self.errorOccurred.emit(self._i18n.get("export_fail"))

    @Slot(str)
    def exportJson(self, path: str) -> None:
        if not path:
            path, _ = QFileDialog.getSaveFileName(
                caption=self._i18n.get("caption_save_json"),
                filter="JSON Files (*.json);;All Files (*.*)",
            )
        if path and self._ctrl.export_json(path):
            self.logAppended.emit(self._i18n.get("log_json_exported", path=path))

    @Slot(str)
    def exportCsv(self, path: str) -> None:
        if not path:
            path, _ = QFileDialog.getSaveFileName(
                caption=self._i18n.get("caption_save_csv"),
                filter="CSV Files (*.csv);;All Files (*.*)",
            )
        if path and self._ctrl.export_csv(path):
            self.logAppended.emit(self._i18n.get("log_csv_exported", path=path))

    @Slot(str)
    def importJson(self, path: str) -> None:
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                caption=self._i18n.get("import_json_button"),
                filter="JSON Files (*.json);;All Files (*.*)",
            )
        if not path:
            return
        count = self._ctrl.import_json(path)
        self._table.refresh_all(self._ctrl.project.entries)
        done, total = self._ctrl.project.stats()
        self.progressChanged.emit(done, total)
        self.logAppended.emit(self._i18n.get("log_items_updated", count=count))

    @Slot(str)
    def importCsv(self, path: str) -> None:
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                caption=self._i18n.get("caption_import_csv"),
                filter="CSV Files (*.csv);;All Files (*.*)",
            )
        if not path:
            return
        count = self._ctrl.import_csv(path)
        self._table.refresh_all(self._ctrl.project.entries)
        done, total = self._ctrl.project.stats()
        self.progressChanged.emit(done, total)
        self.logAppended.emit(self._i18n.get("log_items_updated", count=count))

    # ------------------------------------------------------------------
    # Slots — API key
    # ------------------------------------------------------------------

    @Slot()
    def configureApiKey(self) -> None:
        provider = self._ctrl.preferred_provider
        title = self._i18n.get("api_key_config_title").format(provider=provider)
        prompt = self._i18n.get("api_key_prompt").format(provider=provider)
        current = self._ctrl.get_api_key(provider) or ""
        self.apiKeyDialogRequested.emit(title, prompt, current)

    @Slot(str)
    def submitApiKey(self, key: str) -> None:
        key = key.strip()
        if not key:
            return
        provider = self._ctrl.preferred_provider
        self._ctrl.set_api_key(provider, key)
        mid = self._ctrl.preferred_model_id
        self._ctrl.save_config(
            api_key=key,
            model_label=self._selected_model_label,
            model_id=mid,
            provider=provider,
        )
        self.logAppended.emit(self._i18n.get("log_api_key_saved"))
        if provider == "Gemini":
            threading.Thread(target=self._fetch_models, daemon=True).start()

    # ------------------------------------------------------------------
    # Slots — Glossary
    # ------------------------------------------------------------------

    @Slot(result="QVariantList")
    def loadGlossary(self) -> list:
        from core.tradutor_api import carregar_glossario
        data = carregar_glossario()
        return [{"original": k, "translation": v} for k, v in data.items()]

    @Slot("QVariantList")
    def saveGlossary(self, entries: list) -> None:
        import json

        from core.app_controller import resource_path
        path = os.path.join(resource_path("scripts"), "glossario.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {e["original"]: e["translation"] for e in entries if e.get("original")}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        self.logAppended.emit(self._i18n.get("log_glossary_saved"))

    # ------------------------------------------------------------------
    # Slots — tag state
    # ------------------------------------------------------------------

    _pending_parent_tag: str = ""
    _pending_target_tag: str = ""

    @Slot(str)
    def selectParentTag(self, tag: str) -> None:
        """Set parent tag and reload available child tags from the loaded XML."""
        self._pending_parent_tag = tag
        # Use _xml_path_selected so this works even before entries are loaded.
        xml_path = self._xml_path_selected or self._ctrl.project.xml_path
        if xml_path and tag:
            cache_key = (xml_path, tag)
            if cache_key not in self._child_tags_cache:
                self._child_tags_cache[cache_key] = self._ctrl.get_child_tags(xml_path, tag)
            self._child_tags = self._child_tags_cache[cache_key]
            self.childTagsChanged.emit()

    @Slot(str)
    def setParentTag(self, tag: str) -> None:
        self._pending_parent_tag = tag

    @Slot(str)
    def setTargetTag(self, tag: str) -> None:
        self._pending_target_tag = tag

    # ------------------------------------------------------------------
    # Slots — tag presets
    # ------------------------------------------------------------------

    @Slot(str, str, str, str, str)
    def saveTagPreset(self, label: str, parent_tag: str, target_tag: str, file: str, _folder: str) -> None:
        """Persist a new preset. file is stored as-is (relative path from game_folder)."""
        ok = self._ctrl.save_tag_preset(label.strip(), parent_tag, target_tag, file.strip(), "")
        if ok:
            self.tagPresetsChanged.emit()
            self.logAppended.emit(
                self._i18n.get("log_preset_saved", label=label.strip())
            )

    @Slot("qlonglong", str)
    def setPresetFolder(self, preset_id: int, folder: str) -> None:
        """Assign (or clear) the local root folder for an existing preset."""
        self._ctrl.update_preset_folder(preset_id, folder)
        self.tagPresetsChanged.emit()

    @Slot("qlonglong")
    def deleteTagPreset(self, preset_id: int) -> None:
        """Remove a preset by id."""
        ok = self._ctrl.delete_tag_preset(preset_id)
        if ok:
            self.tagPresetsChanged.emit()
            self.logAppended.emit(self._i18n.get("log_preset_deleted"))

    @Slot("qlonglong", str)
    def renameTagPreset(self, preset_id: int, new_label: str) -> None:
        """Change only the label of a preset."""
        if not new_label.strip():
            return
        ok = self._ctrl.rename_tag_preset(preset_id, new_label.strip())
        if ok:
            self.tagPresetsChanged.emit()

    @Slot()
    def exportPresets(self) -> None:
        """Export all presets to a JSON file chosen by the user."""
        path, _ = QFileDialog.getSaveFileName(
            caption=self._i18n.get("export_preset_caption"),
            filter="STZ Presets (*.json);;All Files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        ok = self._ctrl.export_presets(path)
        if ok:
            import os as _os
            self.logAppended.emit(
                self._i18n.get("log_presets_exported", path=_os.path.basename(path))
            )
        else:
            self.logAppended.emit(self._i18n.get("log_presets_export_fail"))

    @Slot()
    def importPresets(self) -> None:
        """Import presets from a JSON file, merging with existing (deduplicates by label+tags)."""
        path, _ = QFileDialog.getOpenFileName(
            caption=self._i18n.get("import_preset_caption"),
            filter="STZ Presets (*.json);;All Files (*)",
        )
        if not path:
            return
        imported, skipped = self._ctrl.import_presets(path)
        if imported == -1:
            self.logAppended.emit(self._i18n.get("log_presets_import_fail"))
            return
        self.tagPresetsChanged.emit()
        self.logAppended.emit(
            self._i18n.get("log_presets_imported", count=imported, skipped=skipped)
        )

    @Slot(str, str, str, str)
    def applyTagPreset(self, label: str, parent_tag: str, target_tag: str, file_hint: str) -> None:
        """Apply a preset: fill combos and, if game_folder is set, load the file + entries."""
        self._pending_parent_tag = parent_tag
        self._pending_target_tag = target_tag
        xml_path = self._xml_path_selected or self._ctrl.project.xml_path
        if xml_path and parent_tag:
            self._child_tags = self._ctrl.get_child_tags(xml_path, parent_tag)
            self.childTagsChanged.emit()
        self.selectedTagChanged.emit(parent_tag, target_tag)
        self.logAppended.emit(self._i18n.get("log_preset_applied", label=label))

        if file_hint and self._ctrl.game_folder:
            resolved = self._ctrl.resolve_preset_file(file_hint)
            if resolved:
                self._apply_preset_with_file(resolved, parent_tag, target_tag)
            else:
                self.logAppended.emit(
                    self._i18n.get("log_xml_not_found_in_folder",
                                   file=file_hint, folder=self._ctrl.game_folder)
                )

    def _apply_preset_with_file(self, path: str, parent_tag: str, target_tag: str) -> None:
        """Load an XML file and entries directly (no dialog), filling all combos."""
        self._xml_path_selected = path
        self.xmlPathSelectedChanged.emit()
        self.loadedFileNameChanged.emit()
        self._parent_tags = self._ctrl.get_parent_tags(path)
        self.parentTagsChanged.emit()
        self._pending_parent_tag = parent_tag
        self._pending_target_tag = target_tag
        self._child_tags = self._ctrl.get_child_tags(path, parent_tag)
        self.childTagsChanged.emit()
        self.selectedTagChanged.emit(parent_tag, target_tag)
        self._load_xml(path, parent_tag, target_tag)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _set_translating(self, value: bool) -> None:
        if self._is_translating != value:
            self._is_translating = value
            self.translatingChanged.emit(value)

    def _fetch_models(self) -> None:
        try:
            models = list_gemini_models(self._ctrl.api_key)
            if models:
                self._models = models
                labels = list(models.keys())
                # Restore selection: prefer saved label, fall back to saved model id
                saved_label = self._ctrl.preferred_model_label
                if saved_label in models:
                    self._selected_model_label = saved_label
                elif self._ctrl.preferred_model_id:
                    for lbl, (mid, _, _) in models.items():
                        if mid == self._ctrl.preferred_model_id:
                            self._selected_model_label = lbl
                            break
                    else:
                        self._selected_model_label = labels[0]
                else:
                    self._selected_model_label = labels[0]
                self.modelsChanged.emit(self.modelLabels)
                provider = self._ctrl.preferred_provider
                self.logAppended.emit(
                    self._i18n.get("log_models_loaded", provider=provider, count=len(models))
                )
        except Exception as exc:
            provider = self._ctrl.preferred_provider
            self.logAppended.emit(
                self._i18n.get("log_models_load_fail", provider=provider, error=str(exc))
            )
