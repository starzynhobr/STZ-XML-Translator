from pathlib import Path

from main_qt import _load_ui_with_fallback, _ui_candidates

UI_DIR = Path(__file__).resolve().parents[1] / "ui"


class FakeEngine:
    def __init__(self, successful_file: str) -> None:
        self.successful_file = successful_file
        self.loaded: list[str] = []
        self.cache_clear_count = 0

    def load(self, qml_file: str) -> None:
        self.loaded.append(qml_file)

    def rootObjects(self) -> list[object]:
        return [object()] if self.loaded[-1] == self.successful_file else []

    def clearComponentCache(self) -> None:
        self.cache_clear_count += 1


def test_classic_mode_loads_only_classic_shell(tmp_path):
    candidates = _ui_candidates("classic", str(tmp_path))
    assert candidates == [("classic", str(tmp_path / "main.qml"))]


def test_modern_mode_falls_back_to_classic_shell(tmp_path):
    classic_file = str(tmp_path / "main.qml")
    engine = FakeEngine(successful_file=classic_file)

    loaded_mode = _load_ui_with_fallback(engine, "modern", str(tmp_path))

    assert loaded_mode == "classic"
    assert engine.loaded == [str(tmp_path / "ModernMain.qml"), classic_file]
    assert engine.cache_clear_count == 1


def test_modern_mode_does_not_load_classic_when_modern_succeeds(tmp_path):
    modern_file = str(tmp_path / "ModernMain.qml")
    engine = FakeEngine(successful_file=modern_file)

    loaded_mode = _load_ui_with_fallback(engine, "modern", str(tmp_path))

    assert loaded_mode == "modern"
    assert engine.loaded == [modern_file]
    assert engine.cache_clear_count == 0


def test_modern_shell_is_independent_from_classic_shell():
    modern_qml = (UI_DIR / "ModernMain.qml").read_text(encoding="utf-8")

    assert "ApplicationWindow {" in modern_qml
    assert "ClassicMain" not in modern_qml


def test_modern_shell_declares_migration_regions():
    modern_qml = (UI_DIR / "ModernMain.qml").read_text(encoding="utf-8")

    for object_name in (
        "globalActionRegion",
        "workbenchRegion",
        "structureDock",
        "structureRegion",
        "contentRegion",
        "tableCommandRegion",
        "tableRegion",
        "activityRegion",
        "editorRegion",
    ):
        assert f'objectName: "{object_name}"' in modern_qml


def test_modern_shell_reuses_shared_workflow_components():
    modern_qml = (UI_DIR / "ModernMain.qml").read_text(encoding="utf-8")

    for component in (
        "ModernTopBar",
        "LeftSidebar",
        "TranslationTable",
        "ActivityDock",
        "EditPanel",
        "UpdateBanner",
    ):
        assert f"{component} {{" in modern_qml


def test_both_shells_expose_the_shared_update_banner_and_settings_action():
    for shell in ("main.qml", "ModernMain.qml"):
        qml = (UI_DIR / shell).read_text(encoding="utf-8")
        assert "UpdateBanner {" in qml

    sidebar = (UI_DIR / "components" / "LeftSidebar.qml").read_text(encoding="utf-8")
    banner = (UI_DIR / "components" / "UpdateBanner.qml").read_text(encoding="utf-8")
    assert 'objectName: "checkForUpdatesButton"' in sidebar
    for object_name in (
        "updateBanner",
        "updateNotesButton",
        "updateSkipButton",
        "updateLaterButton",
        "updatePrimaryButton",
    ):
        assert f'objectName: "{object_name}"' in banner


def test_modern_top_bar_exposes_global_actions():
    top_bar_qml = (UI_DIR / "components" / "ModernTopBar.qml").read_text(encoding="utf-8")

    for object_name in (
        "topBarLoadButton",
        "topBarTargetLocale",
        "topBarTranslateButton",
        "topBarGlossaryButton",
        "topBarSettingsButton",
        "topBarExportButton",
    ):
        assert f'objectName: "{object_name}"' in top_bar_qml


def test_modern_top_bar_keeps_primary_action_compact():
    top_bar_qml = (UI_DIR / "components" / "ModernTopBar.qml").read_text(
        encoding="utf-8"
    )

    assert "Layout.preferredWidth: root.loadedFileName === \"\" ? 140 : 200" in top_bar_qml
    assert "Layout.preferredWidth: 192" in top_bar_qml
    assert "root.progressDone + \"/\" + root.progressTotal" in top_bar_qml


def test_modern_shell_uses_streamlined_collapsible_structure_panel():
    modern_qml = (UI_DIR / "ModernMain.qml").read_text(encoding="utf-8")

    assert "streamlined: true" in modern_qml
    assert 'objectName: "structureToggle"' in modern_qml
    assert "property bool structureCollapsed: width < 1120" in modern_qml


def test_xml_workflow_exposes_loading_and_preview_states():
    table_qml = (UI_DIR / "components" / "TranslationTable.qml").read_text(
        encoding="utf-8"
    )
    sidebar_qml = (UI_DIR / "components" / "LeftSidebar.qml").read_text(
        encoding="utf-8"
    )
    top_bar_qml = (UI_DIR / "components" / "ModernTopBar.qml").read_text(
        encoding="utf-8"
    )

    assert 'objectName: "xmlWorkState"' in table_qml
    assert "vm.isXmlBusy" in table_qml
    assert 'vm.strings["structure_preview_ready"]' in table_qml
    assert 'vm.strings["filter_empty"]' in table_qml
    assert 'vm.strings["apply_structure_count_button"]' in sidebar_qml
    assert "property bool xmlBusy" in top_bar_qml


def test_translation_table_exposes_resizable_content_columns():
    table_qml = (UI_DIR / "components" / "TranslationTable.qml").read_text(
        encoding="utf-8"
    )

    assert 'objectName: "columnResizeHandle"' in table_qml
    assert "property real originalColumnRatio: 0.45" in table_qml
    assert "minimumContentColumnWidth" in table_qml
    assert "onDoubleClicked: root.resetColumnWidths()" in table_qml


def test_modern_shell_exposes_search_and_contextual_selection_actions():
    modern_qml = (UI_DIR / "ModernMain.qml").read_text(encoding="utf-8")
    command_qml = (UI_DIR / "components" / "TableCommandBar.qml").read_text(
        encoding="utf-8"
    )

    assert "TableCommandBar {" in modern_qml
    assert "vm.setSearchQuery(query)" in modern_qml
    assert "vm.approveSelectedTranslations()" in modern_qml
    for object_name in (
        "tableSearchField",
        "translateSelectionButton",
        "approveSelectionButton",
        "clearTableSelectionButton",
    ):
        assert f'objectName: "{object_name}"' in command_qml
    assert "sequences: [StandardKey.Find]" in command_qml
    assert 'sequence: "Escape"' in command_qml


def test_search_bar_has_fixed_height_and_translation_targets_are_separate():
    modern_qml = (UI_DIR / "ModernMain.qml").read_text(encoding="utf-8")
    sidebar_qml = (UI_DIR / "components" / "LeftSidebar.qml").read_text(
        encoding="utf-8"
    )
    command_qml = (UI_DIR / "components" / "TableCommandBar.qml").read_text(
        encoding="utf-8"
    )

    assert "Layout.maximumHeight: implicitHeight" in command_qml
    assert "Layout.preferredHeight: 30" in command_qml
    assert "Object.keys(vm.availableTranslationTargets)" in modern_qml
    assert "Object.keys(vm.availableTranslationTargets)" in sidebar_qml


def test_uir006_exposes_navigation_shortcuts_and_collapsible_activity():
    modern_qml = (UI_DIR / "ModernMain.qml").read_text(encoding="utf-8")
    table_qml = (UI_DIR / "components" / "TranslationTable.qml").read_text(
        encoding="utf-8"
    )
    editor_qml = (UI_DIR / "components" / "EditPanel.qml").read_text(
        encoding="utf-8"
    )
    activity_qml = (UI_DIR / "components" / "ActivityDock.qml").read_text(
        encoding="utf-8"
    )

    assert "ActivityDock {" in modern_qml
    assert 'sequences: ["Ctrl+Return", "Ctrl+Enter"]' in modern_qml
    assert 'sequence: "Ctrl+S"' in modern_qml
    assert "function selectRelative(offset)" in table_qml
    assert "Keys.onPressed" in table_qml
    assert 'objectName: "previousEntryButton"' in editor_qml
    assert 'objectName: "nextEntryButton"' in editor_qml
    assert "property bool expanded: false" in activity_qml
