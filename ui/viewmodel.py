"""
PySide6 ViewModel bridge — connects AppController to QML.

TranslationTableModel  — QAbstractTableModel fed to QML TableView
AppViewModel           — QObject with Signals/Slots/Properties for the UI
"""
from __future__ import annotations

import os
import threading
import time

from PySide6.QtCore import Property as QProperty
from PySide6.QtCore import (
    QAbstractTableModel,
    QCoreApplication,
    QModelIndex,
    QObject,
    Qt,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog

from core.app_controller import PROVIDER_URLS, AppController
from core.i18n import I18nManager
from core.project import EntryStatus, TranslationEntry
from core.tradutor_api import list_gemini_models
from core.updater import (
    ReleaseInfo,
    UpdateError,
    download_release,
    fetch_latest_release,
    launch_installer,
)
from core.version import app_version

# ---------------------------------------------------------------------------
# Table model
# ---------------------------------------------------------------------------

class TranslationTableModel(QAbstractTableModel):
    """Exposes TranslationProject entries to QML as a three-column table."""

    XpathRole = Qt.UserRole
    StatusRole = Qt.UserRole + 1
    SourceTagRole = Qt.UserRole + 2
    ContextRole = Qt.UserRole + 3
    ErrorCodeRole = Qt.UserRole + 4
    ErrorMessageRole = Qt.UserRole + 5
    countsChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._all_rows: list[TranslationEntry] = []
        self._all_index: dict[str, TranslationEntry] = {}
        self._ordinals: dict[str, int] = {}
        self._rows: list[TranslationEntry] = []
        self._index: dict[str, int] = {}
        self._filter_query = ""
        self.status_filter = "all"
        self.state_counts = {state.value: 0 for state in EntryStatus}
        self._known_states: dict[str, str] = {}
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
                return self._ordinals.get(entry.xpath, index.row() + 1)
            return entry.original if col == 1 else entry.translation
        if role == self.XpathRole:
            return entry.xpath
        if role == self.StatusRole:
            return entry.status
        if role == self.SourceTagRole:
            return entry.source_tag
        if role == self.ContextRole:
            return dict(entry.context)
        if role == self.ErrorCodeRole:
            return entry.error_code
        if role == self.ErrorMessageRole:
            return entry.error_message
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
            self.SourceTagRole: b"sourceTag",
            self.ContextRole: b"entryContext",
            self.ErrorCodeRole: b"errorCode",
            self.ErrorMessageRole: b"errorMessage",
        }

    def update_headers(self, original_label: str, translation_label: str) -> None:
        self._headers = ["#", original_label, translation_label]
        self.headerDataChanged.emit(Qt.Horizontal, 0, 2)

    def refresh_all(self, entries: dict[str, TranslationEntry]) -> None:
        self.beginResetModel()
        self._all_rows = list(entries.values())
        self._all_index = {entry.xpath: entry for entry in self._all_rows}
        self.state_counts = {state.value: 0 for state in EntryStatus}
        self._known_states = {}
        for entry in self._all_rows:
            self._known_states[entry.xpath] = str(entry.status)
            self.state_counts[str(entry.status)] += 1
        self._ordinals = {
            entry.xpath: ordinal for ordinal, entry in enumerate(self._all_rows, start=1)
        }
        self._apply_filter()
        self.endResetModel()
        self.countsChanged.emit()

    def _matches_filter(self, entry: TranslationEntry) -> bool:
        if self.status_filter != "all" and entry.status != self.status_filter:
            return False
        if not self._filter_query:
            return True
        searchable = [
            entry.original,
            entry.translation,
            entry.source_tag,
            *(str(key) for key in entry.context),
            *(str(value) for value in entry.context.values()),
        ]
        return any(self._filter_query in value.casefold() for value in searchable)

    def _apply_filter(self) -> None:
        self._rows = [entry for entry in self._all_rows if self._matches_filter(entry)]
        self._index = {entry.xpath: row for row, entry in enumerate(self._rows)}

    def set_filter(self, query: str) -> bool:
        normalized = query.strip().casefold()
        if normalized == self._filter_query:
            return False
        self.beginResetModel()
        self._filter_query = normalized
        self._apply_filter()
        self.endResetModel()
        return True

    def set_status_filter(self, status: str) -> bool:
        if status not in {"all", *(state.value for state in EntryStatus)} or status == self.status_filter:
            return False
        self.beginResetModel()
        self.status_filter = status
        self._apply_filter()
        self.endResetModel()
        return True

    def update_entry(self, xpath: str, translation: str, status: str) -> None:
        entry = self._all_index.get(xpath)
        if entry is None:
            return
        was_visible = xpath in self._index
        # Activity must never replace a valid translation with an ellipsis.
        if status != "translating":
            entry.set_translation(translation, status)
        old_status = self._known_states.get(xpath)
        new_status = str(entry.status)
        if old_status != new_status:
            if old_status is not None:
                self.state_counts[old_status] -= 1
            self.state_counts[new_status] += 1
            self._known_states[xpath] = new_status
            self.countsChanged.emit()
        is_visible = self._matches_filter(entry)
        if was_visible != is_visible:
            self.beginResetModel()
            self._apply_filter()
            self.endResetModel()
            return
        row = self._index.get(xpath)
        if row is None:
            return
        left = self.index(row, 0)
        right = self.index(row, 2)
        self.dataChanged.emit(left, right, [Qt.DisplayRole, self.StatusRole, self.ErrorCodeRole, self.ErrorMessageRole])

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
    UPDATE_CHECK_INTERVAL_SECONDS = 24 * 60 * 60

    statusFilterChanged = Signal()
    stateCountsChanged = Signal()
    selectionInvalidated = Signal()

    @QProperty(str, notify=statusFilterChanged)
    def statusFilter(self) -> str:
        return self._table.status_filter

    @QProperty("QVariantMap", notify=stateCountsChanged)
    def stateCounts(self) -> dict:
        return {"all": len(self._table._all_rows), **self._table.state_counts}

    @Slot(str)
    def setStatusFilter(self, status: str) -> None:
        if self._table.set_status_filter(status):
            self.statusFilterChanged.emit()

    def _invalidate_selection(self) -> None:
        self._selected_xpath = ""
        self._selected_xpaths = []
        self.selectedRowsChanged.emit()
        self.entrySelected.emit("", "", "")
        self.entryMetadataSelected.emit("", {})
        self.selectionInvalidated.emit()

    reviewChanged = Signal()

    @QProperty(int, notify=reviewChanged)
    def reviewRevision(self) -> int:
        return self._review_revision

    def _review_changed(self, *args) -> None:
        self._review_revision += 1
        self.reviewChanged.emit()

    @Slot(str, result="QVariantMap")
    def entryReview(self, xpath: str) -> dict:
        entry = self._ctrl.project.get_entry(xpath)
        return {"status": str(entry.status), "error_code": entry.error_code} if entry else {}

    """Bridge between AppController (Python) and QML UI."""

    # Signals emitted to QML
    logAppended = Signal(str)
    progressChanged = Signal(int, int)
    modelsChanged = Signal(list)
    translatingChanged = Signal(bool)
    singleTranslatingChanged = Signal(bool)
    entrySelected = Signal(str, str, str)
    entryMetadataSelected = Signal(str, "QVariantMap")
    languageChanged = Signal()
    xmlLoaded = Signal(int)
    errorOccurred = Signal(str)
    entryCountChanged = Signal(int)
    loadedFileNameChanged = Signal()
    providerChanged = Signal()
    parentTagsChanged = Signal()
    childTagsChanged = Signal()
    selectedTagChanged = Signal(str, str)   # (parent_tag, target_tag)
    selectedTagsChanged = Signal()          # target/context tag collections changed
    tagPreviewChanged = Signal()
    xmlPathSelectedChanged = Signal()        # fired when a file is chosen (before entries load)
    tagPresetsChanged = Signal()             # fired when the preset list changes
    gameFolderChanged = Signal()             # fired when the global game folder changes
    translationContextChanged = Signal()     # fired when the translation context/theme changes
    xmlPathsFound    = Signal(list)          # multiple XML files found during folder scan
    translationTargetChanged = Signal()      # fired when translation target locale changes
    themeChanged = Signal()                  # fired when the active theme changes
    uiModeChanged = Signal()                 # fired when the preferred UI shell changes
    selectedRowsChanged = Signal()
    searchChanged = Signal()
    apiKeyDialogRequested = Signal(str, str, str)  # (dialog_title, prompt_label, current_key)
    xmlBusyChanged = Signal()
    _xmlAnalysisFinished = Signal(int, str, object, str)
    _xmlExtractionFinished = Signal(int, str, str, object, object, object, str)
    updateChanged = Signal()
    _updateCheckFinished = Signal(object, str, bool)
    _updateDownloadProgress = Signal(int)
    _updateDownloadFinished = Signal(str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._ctrl = AppController()
        # Load the locale the user last selected (falls back to pt_BR if no config)
        saved_locale = self._ctrl.preferred_locale
        self._i18n = I18nManager(language=saved_locale)
        self._table = TranslationTableModel(self)
        self._review_revision = 0
        self._table.dataChanged.connect(self._review_changed)
        self._table.modelReset.connect(self._review_changed)
        self._table.modelReset.connect(self.searchChanged.emit)
        self._table.modelReset.connect(self._invalidate_selection)
        self._table.countsChanged.connect(self.stateCountsChanged.emit)
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
        self._selected_xpaths: list[str] = []
        self._search_query: str = ""
        self._skip_rows: int = 0
        self._parent_tags: list[str] = []
        self._child_tags: list[str] = []
        self._child_tags_cache: dict[tuple[str, str], list[str]] = {}
        self._pending_parent_tag: str = ""
        self._pending_target_tags: list[str] = []
        self._pending_context_tags: list[str] = []
        self._tag_preview_records: int = 0
        self._tag_preview_lines: int = 0
        self._xml_path_selected: str = ""   # path chosen via file dialog, before entries are loaded
        self._xml_busy: bool = False
        self._xml_busy_message: str = ""
        self._xml_operation_id: int = 0
        self._xmlAnalysisFinished.connect(self._finish_xml_analysis)
        self._xmlExtractionFinished.connect(self._finish_xml_extraction)
        self._update_status: str = "idle"
        self._update_error_code: str = ""
        self._update_progress: int = 0
        self._update_release: ReleaseInfo | None = None
        self._update_installer_path: str = ""
        self._updateCheckFinished.connect(self._finish_update_check)
        self._updateDownloadProgress.connect(self._set_update_progress)
        self._updateDownloadFinished.connect(self._finish_update_download)

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

    @QProperty(bool, notify=xmlBusyChanged)
    def isXmlBusy(self) -> bool:
        return self._xml_busy

    @QProperty(str, notify=xmlBusyChanged)
    def xmlBusyMessage(self) -> str:
        return self._xml_busy_message

    @QProperty(int, notify=entryCountChanged)
    def entryCount(self) -> int:
        return len(self._ctrl.project.entries)

    @QProperty(int, notify=selectedRowsChanged)
    def selectedCount(self) -> int:
        return len(self._selected_xpaths)

    @QProperty(str, notify=searchChanged)
    def searchQuery(self) -> str:
        return self._search_query

    @QProperty(int, notify=searchChanged)
    def filteredEntryCount(self) -> int:
        return self._table.rowCount()

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

    @QProperty("QVariantList", notify=selectedTagsChanged)
    def selectedTargetTags(self) -> list[str]:
        return list(self._pending_target_tags)

    @QProperty("QVariantList", notify=selectedTagsChanged)
    def selectedContextTags(self) -> list[str]:
        return list(self._pending_context_tags)

    @QProperty(int, notify=tagPreviewChanged)
    def tagPreviewRecords(self) -> int:
        return self._tag_preview_records

    @QProperty(int, notify=tagPreviewChanged)
    def tagPreviewLines(self) -> int:
        return self._tag_preview_lines

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

    @QProperty(str, constant=True)
    def appVersion(self) -> str:
        return app_version()

    @QProperty(str, notify=updateChanged)
    def updateStatus(self) -> str:
        return self._update_status

    @QProperty(str, notify=updateChanged)
    def updateStatusText(self) -> str:
        if self._update_status == "error":
            key = f"update_error_{self._update_error_code}"
            return self._i18n.get(key)
        key = f"update_status_{self._update_status}"
        return self._i18n.get(key)

    @QProperty(bool, notify=updateChanged)
    def updateAvailable(self) -> bool:
        return self._update_release is not None and self._update_status in {
            "available",
            "downloading",
            "ready",
        }

    @QProperty(str, notify=updateChanged)
    def updateVersion(self) -> str:
        return self._update_release.version if self._update_release else ""

    @QProperty(int, notify=updateChanged)
    def updateProgress(self) -> int:
        return self._update_progress

    @QProperty(bool, notify=updateChanged)
    def updateActionsEnabled(self) -> bool:
        return not (self._is_translating or self._is_single_translating or self._xml_busy)

    def _set_update_state(self, status: str, error_code: str = "") -> None:
        self._update_status = status
        self._update_error_code = error_code
        self.updateChanged.emit()

    def _begin_update_check(self, manual: bool) -> None:
        if self._update_status in {"checking", "downloading"}:
            return
        self._update_progress = 0
        self._set_update_state("checking")

        def worker() -> None:
            try:
                release = fetch_latest_release(app_version())
            except UpdateError as exc:
                self._updateCheckFinished.emit(None, exc.code, manual)
                return
            self._updateCheckFinished.emit(release, "", manual)

        threading.Thread(target=worker, daemon=True).start()

    @Slot()
    def checkForUpdatesAutomatically(self) -> None:
        if time.time() - self._ctrl.last_update_check < self.UPDATE_CHECK_INTERVAL_SECONDS:
            return
        self._begin_update_check(False)

    @Slot()
    def checkForUpdates(self) -> None:
        self._begin_update_check(True)

    @Slot(object, str, bool)
    def _finish_update_check(
        self,
        release: ReleaseInfo | None,
        error_code: str,
        manual: bool,
    ) -> None:
        if error_code:
            self._set_update_state("error" if manual else "idle", error_code if manual else "")
            return
        self._ctrl.save_update_preferences(last_check=time.time())
        if release is None:
            self._update_release = None
            self._set_update_state("up_to_date" if manual else "idle")
            return
        if release.version == self._ctrl.skipped_update_version and not manual:
            self._update_release = None
            self._set_update_state("idle")
            return
        self._update_release = release
        self._update_installer_path = ""
        self._set_update_state("available")

    @Slot()
    def downloadUpdate(self) -> None:
        release = self._update_release
        if release is None or self._update_status != "available" or not self.updateActionsEnabled:
            return
        self._update_progress = 0
        self._set_update_state("downloading")

        def worker() -> None:
            try:
                path = download_release(
                    release,
                    progress=lambda value: self._updateDownloadProgress.emit(value),
                )
            except UpdateError as exc:
                self._updateDownloadFinished.emit("", exc.code)
                return
            self._updateDownloadFinished.emit(path, "")

        threading.Thread(target=worker, daemon=True).start()

    @Slot(int)
    def _set_update_progress(self, value: int) -> None:
        self._update_progress = max(0, min(100, value))
        self.updateChanged.emit()

    @Slot(str, str)
    def _finish_update_download(self, path: str, error_code: str) -> None:
        if error_code:
            self._update_installer_path = ""
            self._set_update_state("error", error_code)
            return
        self._update_installer_path = path
        self._update_progress = 100
        self._set_update_state("ready")

    @Slot()
    def installUpdate(self) -> None:
        if self._update_status != "ready" or not self.updateActionsEnabled:
            return
        if not launch_installer(self._update_installer_path):
            self._set_update_state("error", "launch")
            return
        QCoreApplication.quit()

    @Slot()
    def remindUpdateLater(self) -> None:
        if self._update_status == "downloading":
            return
        self._set_update_state("idle")

    @Slot()
    def skipUpdate(self) -> None:
        if self._update_release is None or self._update_status == "downloading":
            return
        self._ctrl.save_update_preferences(skipped_version=self._update_release.version)
        self._update_release = None
        self._set_update_state("idle")

    @Slot()
    def openUpdateRelease(self) -> None:
        if self._update_release and self._update_release.page_url.startswith("https://github.com/"):
            QDesktopServices.openUrl(QUrl(self._update_release.page_url))

    @QProperty("QVariantMap", notify=languageChanged)
    def availableLocales(self) -> dict:
        return self._ctrl.available_locales()

    @QProperty("QVariantMap", constant=True)
    def availableTranslationTargets(self) -> dict:
        return self._ctrl.available_translation_targets()

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

    @QProperty(str, notify=uiModeChanged)
    def currentUiMode(self) -> str:
        return self._ctrl.preferred_ui_mode

    @Slot(str)
    def setUiMode(self, ui_mode: str) -> None:
        if ui_mode not in {"classic", "modern"} or ui_mode == self._ctrl.preferred_ui_mode:
            return
        self._ctrl.save_preferred_ui_mode(ui_mode)
        self.uiModeChanged.emit()

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
        self.updateChanged.emit()

    @Slot(str)
    def setTranslationTarget(self, locale_code: str) -> None:
        """Change the AI translation target language only. Does NOT affect UI strings."""
        previous_target = self._ctrl.translation_target.get("code", "")
        self._ctrl.save_preferred_translation_target(locale_code)
        next_target = self._ctrl.translation_target.get("code", "")
        if previous_target != next_target and self._ctrl.project.entries:
            self._ctrl.project.reset_translations()
            restored = 0
            if self._ctrl.project.xml_path:
                restored = self._ctrl.project.load_checkpoint(self._ctrl.current_checkpoint_path())
            self._table.refresh_all(self._ctrl.project.entries)
            done, total = self._ctrl.project.stats()
            self.progressChanged.emit(done, total)
            if restored:
                self.logAppended.emit(
                    self._i18n.get("log_checkpoint_loaded", n=restored)
                )
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
                self.entryMetadataSelected.emit(entry.source_tag, dict(entry.context))

    @Slot("QVariantList")
    def setSelectedRows(self, rows: list) -> None:
        selected: list[str] = []
        for value in rows:
            try:
                xpath = self._table.xpath_at_row(int(value))
            except (TypeError, ValueError):
                xpath = None
            if xpath and xpath not in selected:
                selected.append(xpath)
        if selected != self._selected_xpaths:
            self._selected_xpaths = selected
            self.selectedRowsChanged.emit()

    @Slot(str)
    def setSearchQuery(self, query: str) -> None:
        if query == self._search_query:
            return
        self._search_query = query
        filter_changed = self._table.set_filter(query)
        self._selected_xpath = ""
        if self._selected_xpaths:
            self._selected_xpaths = []
            self.selectedRowsChanged.emit()
        if not filter_changed:
            self.searchChanged.emit()

    @Slot()
    def approveSelectedTranslations(self) -> None:
        changed = 0
        for xpath in list(self._selected_xpaths):
            entry = self._ctrl.project.get_entry(xpath)
            if not entry or not entry.translation.strip():
                continue
            if not self._ctrl.project.confirm_translation(xpath):
                continue
            self._table.update_entry(xpath, entry.translation, "confirmed")
            changed += 1
        if changed:
            self._persist_review_state()
            done, total = self._ctrl.project.stats()
            self.progressChanged.emit(done, total)

    @Slot(str, str)
    def approveTranslation(self, xpath: str, text: str) -> None:
        if not self._ctrl.project.confirm_translation(xpath, text):
            return
        self._table.update_entry(xpath, text, "confirmed")
        self._persist_review_state()
        done, total = self._ctrl.project.stats()
        self.progressChanged.emit(done, total)

    @Slot(str, result=int)
    def countDuplicates(self, xpath: str) -> int:
        return self._ctrl.project.duplicate_count(xpath, pending_only=True)

    @Slot(str, str, result=int)
    def countDuplicateUpdates(self, xpath: str, text: str) -> int:
        return self._ctrl.project.duplicate_update_count(xpath, text)

    @Slot(str, str)
    def applyTranslationToDuplicates(self, xpath: str, text: str) -> None:
        changed = self._ctrl.project.apply_translation_to_duplicates(
            xpath, text, pending_only=False
        )
        for changed_xpath in changed:
            self._table.update_entry(changed_xpath, text, "done")
        if changed:
            done, total = self._ctrl.project.stats()
            self.progressChanged.emit(done, total)
            self.logAppended.emit(
                self._i18n.get("log_duplicates_applied", count=len(changed))
            )

    @Slot()
    def approveAllTranslations(self) -> None:
        for entry in self._ctrl.project.entries.values():
            if entry.translation and entry.translation.strip():
                self._ctrl.project.confirm_translation(entry.xpath)
        self._persist_review_state()
        self._table.refresh_all(self._ctrl.project.entries)
        done, total = self._ctrl.project.stats()
        self.progressChanged.emit(done, total)

    def _persist_review_state(self) -> None:
        if self._ctrl.project.xml_path:
            if not self._ctrl.project.save_checkpoint(self._ctrl.current_checkpoint_path()):
                self.errorOccurred.emit(self._i18n.get("export_fail"))

    @Slot()
    def translateSelected(self) -> None:
        if self._xml_busy:
            return
        if not self._selected_xpath:
            return
        if self.providerNeedsApiKey and not self._ctrl.api_key:
            self.errorOccurred.emit(self._i18n.get("log_api_key_needed"))
            return
        if self._is_single_translating:
            return  # already running, ignore extra clicks
        if len(self._selected_xpaths) > 1:
            self._translate_selected_batch()
            return
        xpath = self._selected_xpath
        config = self._ctrl.build_translation_config(self._selected_model_label, self._models, self._i18n)

        self._is_single_translating = True
        self.singleTranslatingChanged.emit(True)
        self.updateChanged.emit()

        def worker() -> None:
            self._ctrl.project.mark_translating(xpath)
            self._table.update_entry(xpath, "…", "translating")
            result = self._ctrl.translate_single(xpath, config)
            entry = self._ctrl.project.get_entry(xpath)
            if entry and entry.status == "error":
                self.errorOccurred.emit(result)
                result = entry.translation
                self._table.update_entry(xpath, result, "error")
            else:
                self._ctrl.project.set_translation(xpath, result)
                self._table.update_entry(xpath, result, "translated")
            done, total = self._ctrl.project.stats()
            self.progressChanged.emit(done, total)
            self._persist_review_state()
            entry = self._ctrl.project.get_entry(xpath)
            if entry and self._selected_xpath == xpath:
                self.entrySelected.emit(xpath, entry.original, result)
            self._is_single_translating = False
            self.singleTranslatingChanged.emit(False)
            self.updateChanged.emit()

        threading.Thread(target=worker, daemon=True).start()

    def _translate_selected_batch(self) -> None:
        if self._is_translating or self._xml_busy:
            return
        self._set_translating(True)
        config = self._ctrl.build_translation_config(
            self._selected_model_label, self._models, self._i18n
        )
        config["selected_xpaths"] = list(self._selected_xpaths)
        config["include_done"] = True

        def on_batch_start(xpaths: list[str]) -> None:
            for xpath in xpaths:
                self._table.update_entry(xpath, "…", "translating")

        def on_entry(xpath: str, text: str) -> None:
            self._table.update_entry(xpath, text, "done")
            done, total = self._ctrl.project.stats()
            self.progressChanged.emit(done, total)
            if self._selected_xpath == xpath:
                entry = self._ctrl.project.get_entry(xpath)
                if entry:
                    self.entrySelected.emit(xpath, entry.original, text)

        self._ctrl.start_batch_translation(
            config=config,
            on_entry_translated=on_entry,
            on_log=lambda msg: self.logAppended.emit(msg),
            on_done=self._batch_finished,
            on_batch_start=on_batch_start,
        )

    @Slot()
    @Slot(int)
    def setSkipRows(self, n: int) -> None:
        self._skip_rows = max(0, n)

    @Slot()
    def startBatchTranslation(self) -> None:
        if self._xml_busy:
            return
        if self.providerNeedsApiKey and not self._ctrl.api_key:
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
            self._batch_finished()

        self._ctrl.start_batch_translation(config, on_entry, on_log, on_done, on_batch_start)

    @Slot()
    def cancelTranslation(self) -> None:
        self._ctrl.cancel_translation()
        self.logAppended.emit(self._i18n.get("log_mass_translation_cancelled"))

    def _batch_finished(self) -> None:
        self._table.refresh_all(self._ctrl.project.entries)
        self.progressChanged.emit(*self._ctrl.project.stats())
        self._set_translating(False)

    # ------------------------------------------------------------------
    # Slots — file operations
    # ------------------------------------------------------------------

    def _begin_xml_operation(self, message_key: str) -> int:
        self._xml_operation_id += 1
        self._xml_busy = True
        self._xml_busy_message = self._i18n.get(message_key)
        self.xmlBusyChanged.emit()
        self.updateChanged.emit()
        return self._xml_operation_id

    def _end_xml_operation(self) -> None:
        if self._xml_busy or self._xml_busy_message:
            self._xml_busy = False
            self._xml_busy_message = ""
            self.xmlBusyChanged.emit()
            self.updateChanged.emit()

    def _start_xml_analysis(self, path: str) -> None:
        operation_id = self._begin_xml_operation("analyzing_xml_structure")

        def work() -> None:
            try:
                success, result = self._ctrl.analyze_xml(path)
                parents = result if success and isinstance(result, list) else []
                error = "" if success else str(result)
            except Exception as exc:
                parents = []
                error = str(exc)
            self._xmlAnalysisFinished.emit(operation_id, path, parents, error)

        threading.Thread(target=work, daemon=True).start()

    @Slot(int, str, object, str)
    def _finish_xml_analysis(
        self, operation_id: int, path: str, parent_tags: object, error: str
    ) -> None:
        if operation_id != self._xml_operation_id or path != self._xml_path_selected:
            return
        self._end_xml_operation()
        if error:
            self.errorOccurred.emit(error)
            self.logAppended.emit(error)
            return
        self._parent_tags = list(parent_tags)
        self.parentTagsChanged.emit()
        self.logAppended.emit(
            self._i18n.get("log_xml_structure_ready", filename=os.path.basename(path))
        )

    @Slot(str, str)
    def loadXml(self, parent_tag: str, target_tag: str) -> None:
        """
        Open a file-picker, then inspect the XML structure to populate the
        tag dropdowns. Deliberately does NOT load entries into the table —
        the user must choose parent + child tags and apply the structure.
        This avoids auto-loading huge files with irrelevant content.
        """
        if self._xml_busy or self._is_translating:
            return
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
        self._set_tag_selection([], [])
        self._child_tags_cache.clear()

        # Structure discovery runs outside the GUI thread. The resulting index is
        # reused by parent/child selection, preview and final extraction.
        self._parent_tags = []
        self.parentTagsChanged.emit()

        # Clear child tags until user picks a parent.
        self._child_tags = []
        self.childTagsChanged.emit()

        # Clear combo field values so user actively chooses.
        self.selectedTagChanged.emit("", "")
        self._start_xml_analysis(path)

    @Slot()
    def reloadXml(self) -> None:
        """Load entries using the currently selected path + tag settings."""
        if self._xml_busy or self._is_translating:
            return
        path = self._xml_path_selected or self._ctrl.project.xml_path
        if not path:
            return
        parent = self._pending_parent_tag
        targets = self._pending_target_tags
        contexts = self._pending_context_tags
        if not parent or not targets:
            self.logAppended.emit(self._i18n.get("log_select_tags_first"))
            return
        self._load_xml(path, parent, targets, contexts)

    def _load_xml(
        self,
        path: str,
        parent_tag: str,
        target_tags: list[str],
        context_tags: list[str] | None = None,
    ) -> None:
        selected_contexts = context_tags or []
        selected_targets = list(target_tags)
        operation_id = self._begin_xml_operation("loading_xml_entries")

        def work() -> None:
            try:
                success, result = self._ctrl.extract_xml_entries(
                    path, parent_tag, selected_targets, selected_contexts
                )
                entries = result if success and isinstance(result, list) else []
                error = "" if success else str(result)
            except Exception as exc:
                entries = []
                error = str(exc)
            self._xmlExtractionFinished.emit(
                operation_id,
                path,
                parent_tag,
                selected_targets,
                selected_contexts,
                entries,
                error,
            )

        threading.Thread(target=work, daemon=True).start()

    @Slot(int, str, str, object, object, object, str)
    def _finish_xml_extraction(
        self,
        operation_id: int,
        path: str,
        parent_tag: str,
        target_tags: object,
        context_tags: object,
        entries: object,
        error: str,
    ) -> None:
        if operation_id != self._xml_operation_id:
            return
        self._end_xml_operation()
        if error:
            self.errorOccurred.emit(error)
            self.logAppended.emit(error)
            return

        selected_targets = list(target_tags)
        selected_contexts = list(context_tags)
        self._ctrl.apply_xml_entries(
            path,
            parent_tag,
            selected_targets,
            selected_contexts,
            list(entries),
        )
        self._xml_path_selected = path

        restored = self._ctrl.restore_checkpoint_for(path)
        if restored:
            self.logAppended.emit(self._i18n.get("log_checkpoint_loaded", n=restored))

        if self._search_query:
            self._search_query = ""
            self._table.set_filter("")
        if self._table.set_status_filter("all"):
            self.statusFilterChanged.emit()
        self._table.refresh_all(self._ctrl.project.entries)
        self._selected_xpath = ""
        self._selected_xpaths = []
        self.selectedRowsChanged.emit()
        count = len(self._ctrl.project.entries)
        done, total = self._ctrl.project.stats()
        self.progressChanged.emit(done, total)
        self.xmlLoaded.emit(count)
        self.entryCountChanged.emit(count)
        self.loadedFileNameChanged.emit()
        self.xmlPathSelectedChanged.emit()

        # All these reads now come from the already prepared in-memory index.
        self._parent_tags = self._ctrl.get_parent_tags(path)
        self.parentTagsChanged.emit()
        self._pending_parent_tag = parent_tag
        self._child_tags = self._ctrl.get_child_tags(path, parent_tag)
        self._set_tag_selection(selected_targets, selected_contexts)
        self._refresh_tag_preview()
        self.childTagsChanged.emit()
        self.selectedTagChanged.emit(
            parent_tag, selected_targets[0] if selected_targets else ""
        )
        filename = os.path.basename(path)
        self.logAppended.emit(
            self._i18n.get("log_load_success", filename=filename, count=count)
        )

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
        target_tags = self._ctrl.project.target_tags
        context_tags = self._ctrl.project.context_tags
        if not path:
            return
        if self._ctrl.export_xml(path):
            filename = os.path.basename(path)
            self.logAppended.emit(self._i18n.get("log_saved_inplace", filename=filename))
            # Clear the checkpoint — no longer needed after saving.
            self._ctrl.clear_checkpoint()
            # Reload from the freshly-written file so the UI shows the new
            # content as the original text (translations column starts empty).
            self._load_xml(path, parent_tag, target_tags, context_tags)
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

        from core.app_controller import user_data_path
        path = user_data_path("glossario.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {e["original"]: e["translation"] for e in entries if e.get("original")}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        self.logAppended.emit(self._i18n.get("log_glossary_saved"))

    # ------------------------------------------------------------------
    # Slots — tag state
    # ------------------------------------------------------------------

    @Slot(str)
    def selectParentTag(self, tag: str) -> None:
        """Set parent tag and reload available child tags from the loaded XML."""
        changed = tag != self._pending_parent_tag
        self._pending_parent_tag = tag
        if changed:
            self._set_tag_selection([], [])
            self.selectedTagChanged.emit(tag, "")
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
        """Compatibility bridge for the former singular target selector."""
        self._set_tag_selection([tag], [])

    @Slot(str)
    def addTargetTag(self, tag: str) -> None:
        tag = tag.strip()
        if not tag or tag in self._pending_context_tags:
            return
        self._set_tag_selection([*self._pending_target_tags, tag], self._pending_context_tags)

    @Slot(str)
    def removeTargetTag(self, tag: str) -> None:
        self._set_tag_selection(
            [value for value in self._pending_target_tags if value != tag],
            self._pending_context_tags,
        )

    @Slot(str)
    def addContextTag(self, tag: str) -> None:
        tag = tag.strip()
        if not tag or tag in self._pending_target_tags:
            return
        self._set_tag_selection(self._pending_target_tags, [*self._pending_context_tags, tag])

    @Slot(str)
    def removeContextTag(self, tag: str) -> None:
        self._set_tag_selection(
            self._pending_target_tags,
            [value for value in self._pending_context_tags if value != tag],
        )

    def _set_tag_selection(self, target_tags: list[str], context_tags: list[str]) -> None:
        targets = list(dict.fromkeys(tag.strip() for tag in target_tags if tag.strip()))
        contexts = list(
            dict.fromkeys(
                tag.strip()
                for tag in context_tags
                if tag.strip() and tag.strip() not in targets
            )
        )
        if targets == self._pending_target_tags and contexts == self._pending_context_tags:
            return
        self._pending_target_tags = targets
        self._pending_context_tags = contexts
        self.selectedTagsChanged.emit()
        self._refresh_tag_preview()

    def _refresh_tag_preview(self) -> None:
        path = self._xml_path_selected or self._ctrl.project.xml_path
        if path and self._pending_parent_tag and self._pending_target_tags:
            preview = self._ctrl.preview_tag_selection(
                path,
                self._pending_parent_tag,
                self._pending_target_tags,
                self._pending_context_tags,
            )
            records = preview["records"]
            lines = preview["lines"]
        else:
            records = 0
            lines = 0
        if records != self._tag_preview_records or lines != self._tag_preview_lines:
            self._tag_preview_records = records
            self._tag_preview_lines = lines
            self.tagPreviewChanged.emit()

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

    @Slot(str, str, "QVariantList", "QVariantList", str, str)
    def saveTagPresetMulti(
        self,
        label: str,
        parent_tag: str,
        target_tags: list[str],
        context_tags: list[str],
        file: str,
        _folder: str,
    ) -> None:
        """Persist a multi-tag preset while keeping the singular slot available."""
        ok = self._ctrl.save_tag_preset(
            label.strip(), parent_tag, target_tags, file.strip(), "", context_tags
        )
        if ok:
            self.tagPresetsChanged.emit()
            self.logAppended.emit(self._i18n.get("log_preset_saved", label=label.strip()))

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
        self._apply_tag_preset(label, parent_tag, [target_tag], [], file_hint)

    @Slot(str, str, "QVariantList", "QVariantList", str)
    def applyTagPresetMulti(
        self,
        label: str,
        parent_tag: str,
        target_tags: list[str],
        context_tags: list[str],
        file_hint: str,
    ) -> None:
        self._apply_tag_preset(label, parent_tag, target_tags, context_tags, file_hint)

    def _apply_tag_preset(
        self,
        label: str,
        parent_tag: str,
        target_tags: list[str],
        context_tags: list[str],
        file_hint: str,
    ) -> None:
        self._pending_parent_tag = parent_tag
        self._set_tag_selection(target_tags, context_tags)
        xml_path = self._xml_path_selected or self._ctrl.project.xml_path
        if xml_path and parent_tag:
            self._child_tags = self._ctrl.get_child_tags(xml_path, parent_tag)
            self.childTagsChanged.emit()
        self.selectedTagChanged.emit(parent_tag, target_tags[0] if target_tags else "")
        self.logAppended.emit(self._i18n.get("log_preset_applied", label=label))

        if file_hint and self._ctrl.game_folder:
            resolved = self._ctrl.resolve_preset_file(file_hint)
            if resolved:
                self._apply_preset_with_file(resolved, parent_tag, target_tags, context_tags)
            else:
                self.logAppended.emit(
                    self._i18n.get("log_xml_not_found_in_folder",
                                   file=file_hint, folder=self._ctrl.game_folder)
                )

    def _apply_preset_with_file(
        self,
        path: str,
        parent_tag: str,
        target_tags: list[str],
        context_tags: list[str],
    ) -> None:
        """Load an XML file and entries directly (no dialog), filling all combos."""
        self._xml_path_selected = path
        self.xmlPathSelectedChanged.emit()
        self.loadedFileNameChanged.emit()
        # A preset may point to a file that has not been analyzed yet. Avoid
        # rebuilding its index synchronously from the UI thread; the extraction
        # worker below prepares it and completion repopulates these lists.
        self._parent_tags = []
        self.parentTagsChanged.emit()
        self._pending_parent_tag = parent_tag
        self._pending_target_tags = list(
            dict.fromkeys(tag.strip() for tag in target_tags if tag.strip())
        )
        self._pending_context_tags = list(
            dict.fromkeys(
                tag.strip()
                for tag in context_tags
                if tag.strip() and tag.strip() not in self._pending_target_tags
            )
        )
        self.selectedTagsChanged.emit()
        self._tag_preview_records = 0
        self._tag_preview_lines = 0
        self.tagPreviewChanged.emit()
        self._child_tags = []
        self.childTagsChanged.emit()
        self.selectedTagChanged.emit(parent_tag, target_tags[0] if target_tags else "")
        self._load_xml(path, parent_tag, target_tags, context_tags)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _set_translating(self, value: bool) -> None:
        if self._is_translating != value:
            self._is_translating = value
            self.translatingChanged.emit(value)
            self.updateChanged.emit()

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
