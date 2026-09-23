import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Controls.FluentWinUI3

Pane {
    id: root

    property string loadedFileName: ""
    property int progressDone: 0
    property int progressTotal: 0
    property bool translating: false
    property bool xmlBusy: false
    property int entryCount: 0
    property var targetLocaleNames: []
    property var targetLocaleCodes: []
    property string targetLocaleCode: ""

    signal loadRequested()
    signal targetLocaleRequested(string localeCode)
    signal translateRequested()
    signal glossaryRequested()
    signal settingsRequested()
    signal exportRequested()

    readonly property bool compact: width < 880
    readonly property int targetLocaleIndex: {
        var idx = targetLocaleCodes.indexOf(targetLocaleCode)
        return idx >= 0 ? idx : 0
    }

    implicitHeight: compact ? 94 : 54
    implicitWidth: 0
    padding: 0

    background: Rectangle {
        color: Theme.bgBase
        Rectangle {
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
            height: 1
            color: Theme.borderSubtle
        }
    }

    GridLayout {
        anchors.fill: parent
        anchors { leftMargin: 8; rightMargin: 8; topMargin: 4; bottomMargin: 6 }
        columns: root.compact ? 2 : 4
        columnSpacing: 12
        rowSpacing: 6

        ModernToolbarButton {
            objectName: "topBarLoadButton"
            Layout.row: 0
            Layout.column: 0
            Layout.preferredWidth: root.loadedFileName === "" ? 140 : 200
            text: root.loadedFileName !== ""
                ? "✓  " + root.loadedFileName
                : "📂  " + (vm.strings["topbar_load_xml"] ?? "Load XML")
            accented: root.loadedFileName === ""
            enabled: !root.translating && !root.xmlBusy
            ToolTip.visible: hovered && root.loadedFileName !== ""
            ToolTip.delay: 500
            ToolTip.text: root.loadedFileName
            onClicked: root.loadRequested()
        }

        RowLayout {
            Layout.row: 0
            Layout.column: 1
            spacing: 8

            Label {
                text: vm.strings["translate_to_label"] ?? "Translate to"
                color: Theme.textSecondary
                font.pixelSize: 11
            }
            StyledComboBox {
                id: targetLocaleCombo
                objectName: "topBarTargetLocale"
                model: root.targetLocaleNames
                currentIndex: root.targetLocaleIndex
                Layout.preferredWidth: 176
                implicitHeight: 32
                enabled: !root.xmlBusy
                onActivated: {
                    if (currentIndex >= 0 && currentIndex < root.targetLocaleCodes.length)
                        root.targetLocaleRequested(root.targetLocaleCodes[currentIndex])
                }
            }
        }

        Item {
            visible: !root.compact
            Layout.row: 0
            Layout.column: 2
            Layout.fillWidth: true
        }

        RowLayout {
            id: actionGroup
            Layout.row: root.compact ? 1 : 0
            Layout.column: root.compact ? 0 : 3
            Layout.columnSpan: root.compact ? 2 : 1
            Layout.fillWidth: root.compact
            Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
            spacing: 8

            Item { visible: root.compact; Layout.fillWidth: true }

            ModernToolbarButton {
                objectName: "topBarTranslateButton"
                text: (root.translating
                    ? (vm.strings["cancel_button"] ?? "Cancel")
                    : (vm.strings["topbar_translate_pending"] ?? "Translate pending"))
                    + ": " + root.progressDone + "/" + root.progressTotal
                accented: !root.translating
                enabled: (root.entryCount > 0 || root.translating) && !root.xmlBusy
                Layout.preferredWidth: 192
                onClicked: root.translateRequested()
            }
            ModernToolbarButton {
                objectName: "topBarGlossaryButton"
                text: vm.strings["topbar_glossary"] ?? "Glossary"
                Layout.preferredWidth: 90
                ToolTip.visible: hovered
                ToolTip.delay: 500
                ToolTip.text: vm.strings["topbar_glossary_tooltip"]
                    ?? "Set fixed translations for terms that should stay consistent."
                background: Rectangle {
                    color: parent.hovered ? Theme.bgSurface2 : Theme.bgBase
                    radius: 5
                    border.color: Theme.borderSubtle
                }
                onClicked: root.glossaryRequested()
            }
            ModernToolbarButton {
                objectName: "topBarExportButton"
                text: vm.strings["topbar_export"] ?? "Export XML"
                enabled: root.progressDone > 0 && !root.translating && !root.xmlBusy
                Layout.preferredWidth: 100
                background: Rectangle {
                    color: parent.hovered ? Theme.bgSurface2 : Theme.bgBase
                    radius: 5
                    border.color: Theme.borderSubtle
                }
                onClicked: root.exportRequested()
            }
            ModernToolbarButton {
                objectName: "topBarSettingsButton"
                text: "⚙"
                Layout.preferredWidth: 36
                Accessible.name: vm.strings["topbar_settings"] ?? "Settings"
                ToolTip.visible: hovered
                ToolTip.delay: 500
                ToolTip.text: Accessible.name
                onClicked: root.settingsRequested()
            }
        }
    }
}
