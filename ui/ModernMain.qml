import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Controls.FluentWinUI3

import "components"

ApplicationWindow {
    id: root
    objectName: "modernShell"
    title: (vm.strings["window_title"] ?? "STZ XML Translator") + " v" + vm.appVersion
        + " — " + (vm.strings["ui_mode_modern"] ?? "New")
    width: 1280
    height: 760
    minimumWidth: 1024
    minimumHeight: 620
    visible: true

    palette.window:          Theme.bgBase
    palette.windowText:      Theme.textPrimary
    palette.base:            Theme.bgSurface2
    palette.alternateBase:   Theme.bgSurface1
    palette.text:            Theme.textPrimary
    palette.button:          Theme.secondary
    palette.buttonText:      Theme.onSecondary
    palette.highlight:       Theme.primary
    palette.highlightedText: Theme.onPrimary
    palette.toolTipBase:     Theme.bgSurface2
    palette.toolTipText:     Theme.textPrimary

    property string logText: ""
    property int progressDone: 0
    property int progressTotal: 0
    property string selectedXpath: ""
    property string selectedOriginal: ""
    property string selectedTranslation: ""
    property string selectedSourceTag: ""
    property var selectedEntryContext: ({})
    property bool structureCollapsed: width < 1120

    function clearWorkspaceState() {
        activityRegion.clear()
        root.logText = ""
        root.selectedXpath = ""
        root.selectedOriginal = ""
        root.selectedTranslation = ""
        root.selectedSourceTag = ""
        root.selectedEntryContext = ({})
    }

    Connections {
        target: vm

        function onLogAppended(msg) {
            var ts = new Date().toLocaleTimeString(
                "pt-BR", {hour: "2-digit", minute: "2-digit", second: "2-digit"}
            )
            root.logText += "[" + ts + "] " + msg + "\n"
        }
        function onProgressChanged(done, total) {
            root.progressDone = done
            root.progressTotal = total
        }
        function onEntrySelected(xpath, original, translation) {
            root.selectedXpath = xpath
            root.selectedOriginal = original
            root.selectedTranslation = translation
        }
        function onEntryMetadataSelected(sourceTag, context) {
            root.selectedSourceTag = sourceTag
            root.selectedEntryContext = context
        }
        function onXmlLoaded(count) {
            root.clearWorkspaceState()
        }
        function onErrorOccurred(msg) {
            root.logText += "[ERRO] " + msg + "\n"
            activityRegion.expand()
        }
    }

    ColumnLayout {
        id: shellLayout
        objectName: "shellLayout"
        anchors.fill: parent
        anchors.margins: 6
        spacing: 6

        ModernTopBar {
            id: globalActionRegion
            objectName: "globalActionRegion"
            Layout.fillWidth: true
            Layout.minimumWidth: 0

            loadedFileName: vm.loadedFileName
            progressDone: root.progressDone
            progressTotal: root.progressTotal
            translating: vm.isTranslating
            xmlBusy: vm.isXmlBusy
            entryCount: vm.entryCount
            targetLocaleNames: Object.keys(vm.availableTranslationTargets)
            targetLocaleCodes: Object.values(vm.availableTranslationTargets)
            targetLocaleCode: vm.translationTargetCode

            onLoadRequested: structureRegion.openXmlPicker()
            onTargetLocaleRequested: (localeCode) => vm.setTranslationTarget(localeCode)
            onTranslateRequested: vm.isTranslating
                ? vm.cancelTranslation() : vm.startBatchTranslation()
            onGlossaryRequested: editorRegion.openGlossary()
            onSettingsRequested: structureRegion.openSettings()
            onExportRequested: vm.exportXml("")
        }

        UpdateBanner {
            Layout.fillWidth: true
            Layout.maximumHeight: implicitHeight
        }

        RowLayout {
            id: workbenchRegion
            objectName: "workbenchRegion"
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 6

            Item {
                id: structureDock
                objectName: "structureDock"
                Layout.preferredWidth: root.structureCollapsed ? 32 : 290
                Layout.minimumWidth: root.structureCollapsed ? 32 : 290
                Layout.maximumWidth: root.structureCollapsed ? 32 : 290
                Layout.fillHeight: true

                LeftSidebar {
                    id: structureRegion
                    objectName: "structureRegion"
                    anchors.fill: parent
                    visible: !root.structureCollapsed
                    streamlined: true

                    logText: root.logText
                    progressDone: root.progressDone
                    progressTotal: root.progressTotal
                }

                ModernToolbarButton {
                    id: structureToggle
                    objectName: "structureToggle"
                    anchors.top: parent.top
                    anchors.right: parent.right
                    anchors.topMargin: root.structureCollapsed ? 0 : 8
                    anchors.rightMargin: root.structureCollapsed ? 0 : 8
                    width: 28
                    height: 28
                    z: 10
                    text: root.structureCollapsed ? "›" : "‹"
                    font.pixelSize: 18
                    Accessible.name: root.structureCollapsed
                        ? (vm.strings["expand_structure"] ?? "Expand XML structure")
                        : (vm.strings["collapse_structure"] ?? "Collapse XML structure")
                    ToolTip.visible: hovered
                    ToolTip.delay: 400
                    ToolTip.text: Accessible.name
                    onClicked: root.structureCollapsed = !root.structureCollapsed
                }
            }

            ColumnLayout {
                id: contentRegion
                objectName: "contentRegion"
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 6

                TableCommandBar {
                    id: tableCommandRegion
                    objectName: "tableCommandRegion"
                    Layout.fillWidth: true

                    query: vm.searchQuery
                    resultCount: vm.filteredEntryCount
                    totalCount: vm.entryCount
                    selectedCount: vm.selectedCount
                    busy: vm.isTranslating || vm.isSingleTranslating || vm.isXmlBusy

                    onSearchRequested: function(query) {
                        tableRegion.clearSelection()
                        root.selectedXpath = ""
                        root.selectedOriginal = ""
                        root.selectedTranslation = ""
                        root.selectedSourceTag = ""
                        root.selectedEntryContext = ({})
                        vm.setSearchQuery(query)
                    }
                    onTranslateSelectionRequested: vm.translateSelected()
                    onApproveSelectionRequested: vm.approveSelectedTranslations()
                    onClearSelectionRequested: {
                        tableRegion.clearSelection()
                        root.selectedXpath = ""
                        root.selectedOriginal = ""
                        root.selectedTranslation = ""
                        root.selectedSourceTag = ""
                        root.selectedEntryContext = ({})
                    }
                }

                TranslationTable {
                    id: tableRegion
                    objectName: "tableRegion"
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    onRowClicked: (row) => vm.selectRow(row)
                    onSelectedRowsChanged: (rows) => vm.setSelectedRows(rows)
                    onEditRequested: editorRegion.focusTranslation()
                }

                ActivityDock {
                    id: activityRegion
                    objectName: "activityRegion"
                    Layout.fillWidth: true
                    Layout.fillHeight: false
                    Layout.minimumHeight: activityRegion.expanded ? 136 : 34
                    Layout.preferredHeight: activityRegion.expanded ? 136 : 34
                    Layout.maximumHeight: activityRegion.expanded ? 136 : 34
                    logText: root.logText
                }
            }

            EditPanel {
                id: editorRegion
                objectName: "editorRegion"
                streamlined: true
                Layout.preferredWidth: 330
                Layout.fillHeight: true

                xpath: root.selectedXpath
                originalText: root.selectedOriginal
                translationText: root.selectedTranslation
                sourceTag: root.selectedSourceTag
                entryContext: root.selectedEntryContext

                onTranslationEdited: (text) => {
                    root.selectedTranslation = text
                }
                onPreviousRequested: tableRegion.selectRelative(-1)
                onNextRequested: tableRegion.selectRelative(1)
            }
        }
    }

    Shortcut {
        objectName: "confirmTranslationShortcut"
        sequences: ["Ctrl+Return", "Ctrl+Enter"]
        context: Qt.WindowShortcut
        enabled: root.selectedXpath !== "" && root.selectedTranslation.trim() !== ""
            && !vm.isTranslating && !vm.isSingleTranslating && !vm.isXmlBusy
        onActivated: vm.approveTranslation(root.selectedXpath, root.selectedTranslation)
    }

    Shortcut {
        objectName: "saveInPlaceShortcut"
        sequence: "Ctrl+S"
        context: Qt.WindowShortcut
        enabled: vm.entryCount > 0 && !vm.isTranslating
            && !vm.isSingleTranslating && !vm.isXmlBusy
        onActivated: structureRegion.confirmSaveInPlace()
    }
}
