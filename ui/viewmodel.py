"""
PySide6 ViewModel bridge — connects AppController to QML.

TranslationTableModel  — QAbstractTableModel fed to QML TableView
AppViewModel           — QObject with Signals/Slots/Properties for the UI
"""
from __future__ import annotations

import os
import threading
from collections.abc import Callable

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtCore import Property as QProperty
from PySide6.QtWidgets import QFileDialog, QInputDialog, QLineEdit

from core.app_controller import AppController, PROVIDER_URLS
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
        self._headers = ["Original", "Translation"]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else 2

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._rows):
            return None
        entry = self._rows[index.row()]
        if role == Qt.DisplayRole:
            return entry.original if index.column() == 0 else entry.translation
        if role == self.XpathRole:
            return entry.xpath
        if role == self.StatusRole:
            return entry.status
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole and 0 <= section < 2:
            return self._headers[section]
        return None

    def roleNames(self) -> dict:
        return {
            Qt.DisplayRole: b"display",
            self.XpathRole: b"xpath",
            self.StatusRole: b"entryStatus",
        }

    def update_headers(self, original_label: str, translation_label: str) -> None:
        self._headers = [original_label, translation_label]
        self.headerDataChanged.emit(Qt.Horizontal, 0, 1)

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
        left = self.index(row, 1)
        self.dataChanged.emit(left, left, [Qt.DisplayRole, self.StatusRole])

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
        self._parent_tags: list[str] = []
        self._child_tags: list[str] = []
        self._xml_path_selected: str = ""   # path chosen via file dialog, before entries are loaded

        # Restore preferred model from config
        saved_label = self._ctrl.preferred_model_label
        if saved_label and saved_label in self._models:
            self._selected_model_label = saved_label

        self._ctrl.set_translation_target(saved_locale)

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
        return self._ctrl.preferred_provider != "Ollama (Local)"

    @QProperty(str, notify=providerChanged)
    def providerApiKeyLinkText(self) -> str:
        mapping = {
            "Gemini": "api_key_link_gemini",
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

    # ------------------------------------------------------------------
    # Slots — language
    # ------------------------------------------------------------------

    @Slot(str)
    def changeLanguage(self, locale_code: str) -> None:
        self._i18n.load_language(locale_code)
        self._ctrl.set_translation_target(locale_code)
        self._ctrl.save_preferred_locale(locale_code)
        self._table.update_headers(
            self._i18n.get("original_text_label"),
            self._i18n.get("translation_label"),
        )
        self.languageChanged.emit()
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
    def translateSelected(self) -> None:
        if not self._selected_xpath:
            return
        if self._ctrl.preferred_provider != "Ollama (Local)" and not self._ctrl.api_key:
            self.errorOccurred.emit(self._i18n.get("log_api_key_needed"))
            return
        if self._is_single_translating:
            return  # already running, ignore extra clicks
        xpath = self._selected_xpath
        config = self._ctrl.build_translation_config(self._selected_model_label, self._models)

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
    def startBatchTranslation(self) -> None:
        if self._ctrl.preferred_provider != "Ollama (Local)" and not self._ctrl.api_key:
            self.errorOccurred.emit(self._i18n.get("log_api_key_needed"))
            return
        self._set_translating(True)
        config = self._ctrl.build_translation_config(self._selected_model_label, self._models)

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
            # Nothing selected yet — don't attempt to load
            self.logAppended.emit(self._i18n.get("log_select_tags_first",
                                                  "Select parent and target tags before loading."))
            return
        self._load_xml(path, parent, target)

    def _load_xml(self, path: str, parent_tag: str, target_tag: str) -> None:
        sucesso, err = self._ctrl.load_xml(path, parent_tag, target_tag)
        if sucesso:
            # Keep _xml_path_selected in sync with the successfully loaded path.
            self._xml_path_selected = path
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
        """Overwrite the currently loaded XML file with the translated content."""
        path = self._ctrl.project.xml_path
        if not path:
            return
        if self._ctrl.export_xml(path):
            filename = os.path.basename(path)
            self.logAppended.emit(self._i18n.get("log_saved_inplace", filename=filename))
            # Clear the checkpoint after saving — it is no longer needed for
            # resuming, and keeping it would block future retranslation passes.
            self._ctrl.clear_checkpoint()
            self._table.refresh_all(self._ctrl.project.entries)
            self.progressChanged.emit(0, len(self._ctrl.project.entries))
            self.entryCountChanged.emit(len(self._ctrl.project.entries))
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
        text, ok = QInputDialog.getText(
            None,
            self._i18n.get("api_key_config"),
            self._i18n.get("api_gemini_key"),
            QLineEdit.Password,
            self._ctrl.get_api_key(provider),
        )
        if ok and text:
            self._ctrl.set_api_key(provider, text.strip())
            mid = self._ctrl.preferred_model_id
            self._ctrl.save_config(
                api_key=text.strip(),
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
            self._child_tags = self._ctrl.get_child_tags(xml_path, tag)
            self.childTagsChanged.emit()

    @Slot(str)
    def setParentTag(self, tag: str) -> None:
        self._pending_parent_tag = tag

    @Slot(str)
    def setTargetTag(self, tag: str) -> None:
        self._pending_target_tag = tag

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
