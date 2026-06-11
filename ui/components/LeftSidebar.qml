import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Controls.FluentWinUI3
import QtQuick.Dialogs

Pane {
    id: root

    required property string logText
    required property int    progressDone
    required property int    progressTotal

    // Shared locale list used by both selectors
    property var localeNames: Object.keys(vm.availableLocales)
    property var localeCodes: Object.values(vm.availableLocales)

    // Paths found during folder scan (populated by xmlPathsFound signal)
    property var xmlPickerPaths: []
    // Preset pending apply while folder dialog is open
    property var pendingApplyPreset: null

    // Index of the currently selected TRANSLATION TARGET locale
    property int currentTargetIdx: {
        var idx = localeCodes.indexOf(vm.translationTargetCode)
        return idx >= 0 ? idx : 0
    }

    // Display name for the current UI language (used in the footer button)
    property string currentUiLocaleName: {
        var idx = localeCodes.indexOf(vm.currentLocaleCode)
        return idx >= 0 ? localeNames[idx] : vm.currentLocaleCode
    }

    background: Rectangle { color: Theme.bgSurface1; radius: 6 }

    // ── UI Language button — pinned to the bottom of the sidebar ──────────
    Rectangle {
        id: uiLangFooter
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        height: 34
        color: uiLangFooterMouse.containsMouse ? Theme.bgSurface2 : Theme.bgSurface1
        radius: 6   // match Pane radius at the bottom
        clip: true

        Rectangle {
            anchors.top: parent.top; width: parent.width; height: 1
            color: Theme.borderSubtle
        }

        Row {
            anchors.centerIn: parent
            spacing: 5

            Text {
                text: "🌐"
                font.pixelSize: 12
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                text: root.currentUiLocaleName
                color: Theme.textSecondary
                font.pixelSize: 11
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                text: "▾"
                color: Theme.textSecondary
                font.pixelSize: 8
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        MouseArea {
            id: uiLangFooterMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: uiLangPopup.open()
        }

        // Language picker popup — opens upward from the footer
        Popup {
            id: uiLangPopup
            y: -Math.min(root.localeNames.length * 34 + 8, 200) - 4
            width: parent.width
            height: Math.min(root.localeNames.length * 34 + 8, 200)
            padding: 4
            closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

            background: Rectangle {
                color: Theme.bgSurface2; radius: 4
                border.color: Theme.borderInput; border.width: 1
            }

            contentItem: ListView {
                model: root.localeNames
                clip: true
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                delegate: Rectangle {
                    width: ListView.view.width
                    height: 34
                    color: uiLangItemMouse.containsMouse ? Theme.bgSurface3 : "transparent"
                    radius: 3

                    Text {
                        anchors { left: parent.left; verticalCenter: parent.verticalCenter; leftMargin: 10 }
                        text: modelData
                        color: root.localeCodes[index] === vm.currentLocaleCode
                               ? Theme.primary : Theme.textPrimary
                        font.pixelSize: 12
                        font.weight: root.localeCodes[index] === vm.currentLocaleCode
                                     ? Font.Medium : Font.Normal
                    }

                    Text {
                        anchors { right: parent.right; verticalCenter: parent.verticalCenter; rightMargin: 10 }
                        text: "✓"
                        color: Theme.primary; font.pixelSize: 11
                        visible: root.localeCodes[index] === vm.currentLocaleCode
                    }

                    MouseArea {
                        id: uiLangItemMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            vm.changeUiLanguage(root.localeCodes[index])
                            uiLangPopup.close()
                        }
                    }
                }
            }
        }
    }

    ScrollView {
        anchors { left: parent.left; right: parent.right; top: parent.top; bottom: uiLangFooter.top }
        contentWidth: availableWidth
        clip: true

        ColumnLayout {
            width: parent.width
            spacing: 0

            // ---- Carregar XML (ação primária) ----
            AppButton {
                text: vm.strings["load_xml_button"] ?? "Load XML"
                highlighted: true
                enabled: !vm.isTranslating
                Layout.fillWidth: true
                Layout.leftMargin: 16; Layout.rightMargin: 16
                Layout.topMargin: 16
                Layout.bottomMargin: vm.loadedFileName ? 4 : 6
                onClicked: vm.loadXml(parentTagCombo.value, targetTagCombo.value)
            }

            // Nome do arquivo carregado — só aparece quando há arquivo
            Label {
                visible: vm.loadedFileName !== ""
                text: vm.loadedFileName
                font.pixelSize: 11
                color: Theme.textSecondary
                elide: Text.ElideMiddle
                horizontalAlignment: Text.AlignHCenter
                Layout.fillWidth: true
                Layout.leftMargin: 16; Layout.rightMargin: 16
                Layout.bottomMargin: 6
            }

            // Glossary
            AppButton {
                text: vm.strings["manage_glossary_button"] ?? "Glossary"
                Layout.fillWidth: true
                Layout.leftMargin: 16; Layout.rightMargin: 16
                Layout.bottomMargin: 16
                onClicked: glossaryDialog.open()
            }

            // ---- Separador ----
            Rectangle {
                height: 1; color: Theme.borderSubtle
                Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16
                Layout.bottomMargin: 12
            }

            // ---- Import / Export ----
            Label {
                text: vm.strings["export_import_section_title"] ?? "Export / Import"
                font.pixelSize: 12
                font.weight: Font.Medium
                color: Theme.textSecondary
                Layout.leftMargin: 16
                Layout.bottomMargin: 2
            }
            Label {
                text: vm.strings["export_import_section_subtitle"] ?? "Translation backup (.json, .csv)"
                font.pixelSize: 10
                color: Theme.textDisabled
                Layout.leftMargin: 16
                Layout.bottomMargin: 8
            }

            GridLayout {
                columns: 2
                Layout.fillWidth: true
                Layout.leftMargin: 16; Layout.rightMargin: 16
                Layout.bottomMargin: 16
                columnSpacing: 6
                rowSpacing: 6

                AppButton { text: vm.strings["export_json_button"] ?? "Export JSON"; Layout.fillWidth: true; font.pixelSize: 12; onClicked: vm.exportJson("") }
                AppButton { text: vm.strings["export_csv_button"]  ?? "Export CSV";  Layout.fillWidth: true; font.pixelSize: 12; onClicked: vm.exportCsv("")  }
                AppButton { text: vm.strings["import_json_button"] ?? "Import JSON"; Layout.fillWidth: true; font.pixelSize: 12; enabled: !vm.isTranslating; onClicked: vm.importJson("") }
                AppButton { text: vm.strings["import_csv_button"]  ?? "Import CSV";  Layout.fillWidth: true; font.pixelSize: 12; enabled: !vm.isTranslating; onClicked: vm.importCsv("")  }
            }

            // ---- Separador ----
            Rectangle {
                height: 1; color: Theme.borderSubtle
                Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16
                Layout.bottomMargin: 12
            }

            // ---- Translation target language ----
            Label {
                text: vm.strings["translate_to_label"] ?? "Traduzir para:"
                font.pixelSize: 11
                color: Theme.textSecondary
                Layout.leftMargin: 16
                Layout.bottomMargin: 2
            }
            ComboBox {
                id: targetLangCombo
                model: root.localeNames
                currentIndex: root.currentTargetIdx
                Layout.fillWidth: true
                Layout.leftMargin: 16; Layout.rightMargin: 16
                Layout.bottomMargin: 12
                onActivated: vm.setTranslationTarget(root.localeCodes[currentIndex])

                contentItem: Text {
                    leftPadding: 8
                    text: targetLangCombo.displayText
                    color: Theme.textInput
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                    font: targetLangCombo.font
                }
                background: Rectangle {
                    color: targetLangCombo.hovered ? Theme.bgSurface3 : Theme.bgInput
                    radius: 4
                    border.color: targetLangCombo.activeFocus ? Theme.borderFocus : Theme.borderInput
                    border.width: targetLangCombo.activeFocus ? 2 : 1
                }
                popup: Popup {
                    y: targetLangCombo.height
                    width: targetLangCombo.width
                    height: Math.min(targetLangListView.contentHeight + 8, 200)
                    padding: 4
                    background: Rectangle { color: Theme.bgSurface2; radius: 4; border.color: Theme.borderInput; border.width: 1 }
                    contentItem: ListView {
                        id: targetLangListView
                        model: targetLangCombo.delegateModel
                        clip: true
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    }
                }
            }

            // ---- Tag fields ----
            Label {
                text: vm.strings["parent_tag_label"] ?? "Parent Tag"
                font.pixelSize: 12
                color: Theme.textSecondary
                Layout.leftMargin: 16
                Layout.bottomMargin: 2
            }
            TagComboBox {
                id: parentTagCombo
                suggestions: vm.parentTags
                // Enable as soon as a file is chosen (even before entries load).
                enabled: vm.hasXmlPath
                placeholderText: "ex: baseVillain"
                Layout.fillWidth: true
                Layout.leftMargin: 16; Layout.rightMargin: 16
                Layout.bottomMargin: 8
                onCommitted: function(tag) { vm.selectParentTag(tag) }

                // Sync fields when tags are set (e.g. after Recarregar).
                Connections {
                    target: vm
                    function onSelectedTagChanged(parentTag, targetTag) {
                        parentTagCombo.value = parentTag
                        targetTagCombo.value = targetTag
                    }
                }
            }

            Label {
                text: vm.strings["target_tag_label"] ?? "Target Tag"
                font.pixelSize: 12
                color: Theme.textSecondary
                Layout.leftMargin: 16
                Layout.bottomMargin: 2
            }
            TagComboBox {
                id: targetTagCombo
                suggestions: vm.childTags
                enabled: vm.hasXmlPath
                placeholderText: "ex: bio"
                Layout.fillWidth: true
                Layout.leftMargin: 16; Layout.rightMargin: 16
                Layout.bottomMargin: 8
                onCommitted: function(tag) { vm.setTargetTag(tag) }
            }

            // ---- Preset action row ----
            Row {
                Layout.fillWidth: true
                Layout.leftMargin: 16; Layout.rightMargin: 16
                Layout.bottomMargin: 6
                spacing: 6

                // Save current tag pair as a named preset
                AppButton {
                    id: savePresetBtn
                    text: vm.strings["save_preset_button"] ?? "💾 Salvar Preset"
                    width: (parent.width - parent.spacing) / 2
                    enabled: vm.hasXmlPath && parentTagCombo.value !== "" && targetTagCombo.value !== ""
                    font.pixelSize: 11
                    onClicked: {
                        savePresetLabelField.text = ""
                        savePresetFileField.text = vm.loadedFileName
                        savePresetDialog.open()
                    }
                    background: Rectangle {
                        color: savePresetBtn.enabled
                            ? (savePresetBtn.hovered ? Theme.bgSurface3 : Theme.bgSurface2)
                            : Theme.bgBase
                        radius: 4
                        border.color: savePresetBtn.enabled ? Theme.borderModerate : Theme.borderSubtle
                        border.width: 1
                        Behavior on color { ColorAnimation { duration: 100 } }
                    }
                    contentItem: Label {
                        text: savePresetBtn.text
                        color: savePresetBtn.enabled ? Theme.textPrimary : Theme.textDisabled
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        font: savePresetBtn.font
                        elide: Text.ElideRight
                    }
                }

                // Browse and apply saved presets
                AppButton {
                    id: loadPresetBtn
                    text: vm.strings["load_preset_button"] ?? "📂 Carregar Preset"
                    width: (parent.width - parent.spacing) / 2
                    font.pixelSize: 11
                    onClicked: loadPresetDialog.open()
                    background: Rectangle {
                        color: loadPresetBtn.hovered ? Theme.bgSurface3 : Theme.bgSurface2
                        radius: 4
                        border.color: Theme.borderModerate
                        border.width: 1
                        Behavior on color { ColorAnimation { duration: 100 } }
                    }
                    contentItem: Label {
                        text: loadPresetBtn.text
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        font: loadPresetBtn.font
                        elide: Text.ElideRight
                    }
                }
            }

            // ---- Preset export / import row ----
            Row {
                Layout.fillWidth: true
                Layout.leftMargin: 16; Layout.rightMargin: 16
                Layout.bottomMargin: 6
                spacing: 6

                AppButton {
                    id: exportPresetBtn
                    text: vm.strings["export_preset_button"] ?? "📤 Exportar Presets"
                    width: (parent.width - parent.spacing) / 2
                    enabled: vm.tagPresets.length > 0
                    font.pixelSize: 11
                    onClicked: vm.exportPresets()
                    background: Rectangle {
                        color: exportPresetBtn.enabled
                            ? (exportPresetBtn.hovered ? Theme.bgSurface3 : Theme.bgSurface2)
                            : Theme.bgBase
                        radius: 4
                        border.color: exportPresetBtn.enabled ? Theme.borderModerate : Theme.borderSubtle
                        border.width: 1
                        Behavior on color { ColorAnimation { duration: 100 } }
                    }
                    contentItem: Label {
                        text: exportPresetBtn.text
                        color: exportPresetBtn.enabled ? Theme.textPrimary : Theme.textDisabled
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        font: exportPresetBtn.font
                        elide: Text.ElideRight
                    }
                }

                AppButton {
                    id: importPresetBtn
                    text: vm.strings["import_preset_button"] ?? "📥 Importar Presets"
                    width: (parent.width - parent.spacing) / 2
                    font.pixelSize: 11
                    onClicked: vm.importPresets()
                    background: Rectangle {
                        color: importPresetBtn.hovered ? Theme.bgSurface3 : Theme.bgSurface2
                        radius: 4
                        border.color: Theme.borderModerate
                        border.width: 1
                        Behavior on color { ColorAnimation { duration: 100 } }
                    }
                    contentItem: Label {
                        text: importPresetBtn.text
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        font: importPresetBtn.font
                        elide: Text.ElideRight
                    }
                }
            }

            AppButton {
                id: reloadBtn
                text: vm.strings["reload_button"] ?? "Reload"
                Layout.fillWidth: true
                Layout.leftMargin: 16; Layout.rightMargin: 16
                Layout.bottomMargin: 16
                enabled: vm.hasXmlPath && !vm.isTranslating
                onClicked: vm.reloadXml()

                background: Rectangle {
                    color: reloadBtn.enabled
                        ? (reloadBtn.hovered ? Theme.bgSurface3 : Theme.secondary)
                        : Theme.bgBase
                    radius: 4
                    border.color: reloadBtn.enabled ? Theme.borderModerate : Theme.borderSubtle
                    border.width: 1
                    Behavior on color { ColorAnimation { duration: 100 } }
                }
                contentItem: Label {
                    text: reloadBtn.text
                    color: reloadBtn.enabled ? Theme.onSecondary : Theme.textDisabled
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    font: reloadBtn.font
                }
            }

            // ---- Separador ----
            Rectangle {
                height: 1; color: Theme.borderModerate
                Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16
                Layout.bottomMargin: 12
            }

            // ---- Progress ----
            Label {
                text: vm.strings["progress_label"] ?? "Progress"
                font.pixelSize: 12
                color: Theme.textSecondary
                Layout.alignment: Qt.AlignHCenter
                Layout.bottomMargin: 4
            }

            ProgressBar {
                id: progressBar
                value: root.progressTotal > 0 ? root.progressDone / root.progressTotal : 0
                Layout.fillWidth: true
                Layout.leftMargin: 16; Layout.rightMargin: 16
                Layout.bottomMargin: 4

                background: Rectangle {
                    color: Theme.bgSurface2
                    radius: 2
                    border.color: Theme.borderModerate
                    border.width: 1
                }
                contentItem: Rectangle {
                    width: progressBar.visualPosition * parent.width
                    height: parent.height
                    radius: 2
                    color: Theme.primary
                }
            }

            Label {
                text: {
                    var tpl = vm.strings["stats_template"] ?? "Done: {done} / {total}"
                    return tpl.replace("{done}", root.progressDone).replace("{total}", root.progressTotal)
                }
                font.pixelSize: 12
                color: Theme.textSecondary
                Layout.alignment: Qt.AlignHCenter
                Layout.bottomMargin: 16
            }

            // ---- Export XML ----
            AppButton {
                id: exportXmlBtn
                text: vm.strings["export_button"] ?? "Export XML"
                Layout.fillWidth: true
                Layout.leftMargin: 16; Layout.rightMargin: 16
                Layout.bottomMargin: 8
                enabled: root.progressDone > 0 && !vm.isTranslating
                onClicked: vm.exportXml("")

                background: Rectangle {
                    color: exportXmlBtn.enabled
                        ? (exportXmlBtn.hovered ? Theme.primaryHover : Theme.primary)
                        : Theme.bgBase
                    radius: 4
                    border.color: exportXmlBtn.enabled ? "transparent" : Theme.borderSubtle
                    border.width: 1
                    Behavior on color { ColorAnimation { duration: 100 } }
                }
                contentItem: Label {
                    text: exportXmlBtn.text
                    color: exportXmlBtn.enabled ? Theme.onPrimary : Theme.textDisabled
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    font.weight: Font.Medium
                    font.pixelSize: 13
                }
            }

            // ---- separator to visually distance Save In Place ----
            Rectangle {
                height: 1; color: Theme.borderSubtle
                Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16
                Layout.bottomMargin: 8
            }

            // ---- Save In Place (neutral style — the modal is the warning) ----
            AppButton {
                id: saveInPlaceBtn
                text: vm.strings["save_inplace_button"] ?? "💾 Save to Current File"
                Layout.fillWidth: true
                Layout.leftMargin: 16; Layout.rightMargin: 16
                Layout.bottomMargin: 16
                enabled: vm.entryCount > 0 && !vm.isTranslating
                onClicked: overwriteDialog.open()

                background: Rectangle {
                    color: saveInPlaceBtn.enabled
                        ? (saveInPlaceBtn.hovered ? Theme.bgSurface3 : Theme.secondary)
                        : Theme.bgBase
                    radius: 4
                    border.color: saveInPlaceBtn.enabled ? Theme.borderModerate : Theme.borderSubtle
                    border.width: 1
                    Behavior on color { ColorAnimation { duration: 100 } }
                }
                contentItem: Label {
                    text: saveInPlaceBtn.text
                    color: saveInPlaceBtn.enabled ? Theme.onSecondary : Theme.textDisabled
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    font.pixelSize: 13
                }
            }
        }
    }

    // ---- Overwrite confirmation dialog ----
    // Everything lives in a single contentItem (ColumnLayout) to avoid the
    // header/footer height-calculation bugs in FluentWinUI3's Dialog style.
    Dialog {
        id: overwriteDialog
        modal: true
        anchors.centerIn: Overlay.overlay
        width: 360
        padding: 0
        // Close on Esc OR clicking outside the dialog
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            color: Theme.bgSurface2
            radius: 8
            border.color: Theme.borderModerate
            border.width: 1
        }

        contentItem: ColumnLayout {
            spacing: 0

            // ── Header ──────────────────────────────────────────────────
            Item {
                Layout.fillWidth: true
                implicitHeight: 56

                Label {
                    anchors {
                        left: parent.left; right: parent.right
                        verticalCenter: parent.verticalCenter
                        leftMargin: 20; rightMargin: 20
                    }
                    text: vm.strings["save_inplace_confirm_title"] ?? "Overwrite Original File"
                    font.pixelSize: 15
                    font.weight: Font.DemiBold
                    color: Theme.danger
                    elide: Text.ElideRight
                }

                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width; height: 1
                    color: Theme.borderSubtle
                }
            }

            // ── Body ─────────────────────────────────────────────────────
            Label {
                Layout.fillWidth: true
                Layout.topMargin: 20
                Layout.leftMargin: 20
                Layout.rightMargin: 20
                Layout.bottomMargin: 20
                text: {
                    var tpl = vm.strings["save_inplace_confirm_message"]
                              ?? "This will permanently replace:\n\n{filename}\n\nThis cannot be undone."
                    return tpl.replace("{filename}", vm.loadedFileName)
                }
                wrapMode: Text.WordWrap
                font.pixelSize: 13
                color: Theme.textPrimary
                lineHeight: 1.5
            }

            // ── Footer ───────────────────────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: Theme.borderSubtle
            }

            Row {
                Layout.alignment: Qt.AlignRight
                Layout.rightMargin: 16
                Layout.topMargin: 12
                Layout.bottomMargin: 12
                spacing: 8

                // Neutral "close" — no destructive connotation
                AppButton {
                    text: vm.strings["close_button"] ?? "Close"
                    onClicked: overwriteDialog.close()

                    background: Rectangle {
                        color: parent.hovered ? Theme.bgSurface3 : Theme.bgSurface2
                        radius: 4
                        border.color: Theme.borderModerate
                        border.width: 1
                        Behavior on color { ColorAnimation { duration: 100 } }
                    }
                    contentItem: Label {
                        text: parent.text
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        font: parent.font
                    }
                }

                // Destructive confirm — stays red as the clear danger signal
                AppButton {
                    text: vm.strings["save_inplace_confirm_action"] ?? "Overwrite"
                    onClicked: {
                        overwriteDialog.close()
                        vm.saveInPlace()
                    }

                    background: Rectangle {
                        color: parent.hovered ? Theme.dangerHover : Theme.danger
                        radius: 4
                        Behavior on color { ColorAnimation { duration: 100 } }
                    }
                    contentItem: Label {
                        text: parent.text
                        color: "#ffffff"
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        font.weight: Font.Medium
                        font.pixelSize: 13
                    }
                }
            }
        }
    }

    // ── Save Preset Dialog ────────────────────────────────────────────────────
    Dialog {
        id: savePresetDialog
        modal: true
        anchors.centerIn: Overlay.overlay
        width: 360
        padding: 0
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            color: Theme.bgSurface2; radius: 8
            border.color: Theme.borderModerate; border.width: 1
        }

        contentItem: ColumnLayout {
            spacing: 0

            // ── Header
            Item {
                Layout.fillWidth: true; implicitHeight: 52
                Label {
                    anchors { left: parent.left; right: parent.right
                              verticalCenter: parent.verticalCenter
                              leftMargin: 20; rightMargin: 20 }
                    text: vm.strings["save_preset_title"] ?? "Salvar Preset de Tags"
                    font.pixelSize: 14; font.weight: Font.DemiBold
                    color: Theme.textPrimary; elide: Text.ElideRight
                }
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.borderSubtle }
            }

            // ── Body
            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 20
                spacing: 10

                // Tag pair pill
                Rectangle {
                    Layout.fillWidth: true
                    height: 32; radius: 4
                    color: Theme.bgSurface1
                    border.color: Theme.borderSubtle; border.width: 1
                    Label {
                        anchors { left: parent.left; right: parent.right
                                  verticalCenter: parent.verticalCenter
                                  leftMargin: 10; rightMargin: 10 }
                        text: parentTagCombo.value + "  →  " + targetTagCombo.value
                        font.pixelSize: 12; font.weight: Font.Medium
                        color: Theme.primary; elide: Text.ElideRight
                    }
                }

                // Description (required)
                Label {
                    text: vm.strings["preset_label_field"] ?? "Descrição *"
                    font.pixelSize: 11; color: Theme.textSecondary
                }
                TextField {
                    id: savePresetLabelField
                    Layout.fillWidth: true
                    placeholderText: vm.strings["preset_label_placeholder"] ?? "ex: Biografia dos Heróis"
                    color: Theme.textInput
                    placeholderTextColor: Theme.textPlaceholder
                    font.pixelSize: 13
                    background: Rectangle {
                        color: Theme.bgInput; radius: 4
                        border.color: parent.activeFocus ? Theme.borderFocus : Theme.borderInput
                        border.width: parent.activeFocus ? 2 : 1
                    }
                }

                // File hint — auto-filled from the loaded XML
                Label {
                    text: vm.gameFolder
                        ? (vm.strings["preset_file_relative_label"] ?? "Arquivo (relativo à pasta do jogo)")
                        : (vm.strings["preset_file_field"] ?? "Arquivo")
                    font.pixelSize: 11; color: Theme.textSecondary
                }
                TextField {
                    id: savePresetFileField
                    Layout.fillWidth: true
                    text: vm.loadedFileRelPath
                    placeholderText: vm.strings["preset_file_placeholder"] ?? "ex: characters.xml"
                    color: Theme.textInput
                    placeholderTextColor: Theme.textPlaceholder
                    font.pixelSize: 13
                    background: Rectangle {
                        color: Theme.bgInput; radius: 4
                        border.color: parent.activeFocus ? Theme.borderFocus : Theme.borderInput
                        border.width: parent.activeFocus ? 2 : 1
                    }
                }
            }

            // ── Footer
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.borderSubtle }
            Row {
                Layout.alignment: Qt.AlignRight
                Layout.rightMargin: 16; Layout.topMargin: 12; Layout.bottomMargin: 12
                spacing: 8

                AppButton {
                    text: vm.strings["close_button"] ?? "Fechar"
                    onClicked: savePresetDialog.close()
                    background: Rectangle {
                        color: parent.hovered ? Theme.bgSurface3 : Theme.bgSurface2
                        radius: 4; border.color: Theme.borderModerate; border.width: 1
                        Behavior on color { ColorAnimation { duration: 100 } }
                    }
                    contentItem: Label {
                        text: parent.text; color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter; font: parent.font
                    }
                }

                AppButton {
                    text: vm.strings["save_preset_save_button"] ?? "Salvar"
                    enabled: savePresetLabelField.text.trim() !== ""
                    onClicked: {
                        vm.saveTagPreset(
                            savePresetLabelField.text.trim(),
                            parentTagCombo.value,
                            targetTagCombo.value,
                            savePresetFileField.text.trim(),
                            ""
                        )
                        savePresetDialog.close()
                    }
                    background: Rectangle {
                        color: parent.enabled
                            ? (parent.hovered ? Theme.primaryHover : Theme.primary)
                            : Theme.bgBase
                        radius: 4
                        border.color: parent.enabled ? "transparent" : Theme.borderSubtle
                        border.width: 1
                        Behavior on color { ColorAnimation { duration: 100 } }
                    }
                    contentItem: Label {
                        text: parent.text
                        color: parent.enabled ? Theme.onPrimary : Theme.textDisabled
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        font.weight: Font.Medium; font.pixelSize: 13
                    }
                }
            }
        }
    }

    // ── Load Preset Dialog ────────────────────────────────────────────────────
    Dialog {
        id: loadPresetDialog
        modal: true
        anchors.centerIn: Overlay.overlay
        width: 400
        padding: 0
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            color: Theme.bgSurface2; radius: 8
            border.color: Theme.borderModerate; border.width: 1
        }

        contentItem: ColumnLayout {
            spacing: 0

            // ── Header
            Item {
                Layout.fillWidth: true; implicitHeight: 52
                Label {
                    anchors { left: parent.left; right: parent.right
                              verticalCenter: parent.verticalCenter
                              leftMargin: 20; rightMargin: 20 }
                    text: vm.strings["load_preset_title"] ?? "Presets de Tags"
                    font.pixelSize: 14; font.weight: Font.DemiBold
                    color: Theme.textPrimary; elide: Text.ElideRight
                }
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.borderSubtle }
            }

            // ── Game folder row
            Rectangle {
                Layout.fillWidth: true
                height: 44
                color: gameFolderRowMouse.containsMouse ? Theme.bgSurface3 : Theme.bgSurface1

                RowLayout {
                    anchors { fill: parent; leftMargin: 14; rightMargin: 12 }
                    spacing: 8

                    Text {
                        text: "📁"; font.pixelSize: 13
                        Layout.alignment: Qt.AlignVCenter
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        spacing: 1

                        Label {
                            text: vm.strings["preset_game_folder_label"] ?? "Pasta do jogo"
                            font.pixelSize: 10; color: Theme.textSecondary
                        }
                        Label {
                            Layout.fillWidth: true
                            text: vm.gameFolder !== ""
                                ? vm.gameFolder
                                : (vm.strings["preset_game_folder_not_set"] ?? "Não definida — clique para selecionar")
                            font.pixelSize: 11
                            color: vm.gameFolder !== "" ? Theme.textPrimary : Theme.textSecondary
                            elide: Text.ElideMiddle
                        }
                    }

                    Label {
                        text: "▾"; font.pixelSize: 9
                        color: Theme.textSecondary
                        Layout.alignment: Qt.AlignVCenter
                    }
                }

                MouseArea {
                    id: gameFolderRowMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: gameFolderDialog.open()
                    ToolTip.visible: containsMouse
                    ToolTip.text: vm.strings["preset_game_folder_tooltip"] ?? "Pasta raiz do jogo — usada para localizar os XMLs dos presets"
                    ToolTip.delay: 600
                }

                Behavior on color { ColorAnimation { duration: 80 } }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.borderSubtle }

            // ── Body — preset list
            Item {
                Layout.fillWidth: true
                implicitHeight: Math.min(Math.max(vm.tagPresets.length, 1) * 68 + 16, 300)

                // Empty state
                Label {
                    visible: vm.tagPresets.length === 0
                    anchors.centerIn: parent
                    text: vm.strings["no_presets_label"] ?? "Nenhum preset salvo."
                    font.pixelSize: 13; color: Theme.textSecondary
                }

                ListView {
                    visible: vm.tagPresets.length > 0
                    anchors { fill: parent; margins: 8 }
                    model: vm.tagPresets
                    clip: true
                    spacing: 4
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                    delegate: Rectangle {
                        width: ListView.view.width
                        height: 60
                        radius: 6
                        color: Theme.bgSurface1
                        border.color: Theme.borderSubtle; border.width: 1

                        RowLayout {
                            anchors { fill: parent; leftMargin: 12; rightMargin: 8; topMargin: 6; bottomMargin: 6 }
                            spacing: 8

                            // Info column
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2

                                Label {
                                    Layout.fillWidth: true
                                    text: modelData.label ?? ""
                                    font.pixelSize: 12; font.weight: Font.Medium
                                    color: Theme.textPrimary; elide: Text.ElideRight
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 6
                                    Label {
                                        Layout.fillWidth: true
                                        text: (modelData.parent_tag ?? "") + " → " + (modelData.target_tag ?? "")
                                        font.pixelSize: 11; color: Theme.primary
                                        elide: Text.ElideRight
                                    }
                                    Label {
                                        visible: (modelData.file_name ?? "") !== ""
                                        text: "• " + (modelData.file_name ?? "")
                                        font.pixelSize: 10; color: Theme.textSecondary
                                        elide: Text.ElideRight
                                        Layout.maximumWidth: 100
                                    }
                                    // Validity indicator — only shown when game_folder is set and file hint exists
                                    Label {
                                        visible: (modelData.file ?? "") !== "" && modelData.file_exists !== undefined
                                        text: modelData.file_exists ? "✓" : "✗"
                                        font.pixelSize: 10
                                        font.weight: Font.Medium
                                        color: modelData.file_exists ? "#4ec94e" : Theme.danger
                                        ToolTip.visible: hoverStatus.containsMouse
                                        ToolTip.text: modelData.file_exists
                                            ? (vm.strings["preset_file_valid"] ?? "Arquivo encontrado")
                                            : (vm.strings["preset_file_invalid"] ?? "Arquivo não encontrado na pasta do jogo")
                                        ToolTip.delay: 400
                                        MouseArea { id: hoverStatus; anchors.fill: parent; hoverEnabled: true }
                                    }
                                }
                            }

                            // Apply button
                            AppButton {
                                text: vm.strings["preset_apply_button"] ?? "Aplicar"
                                font.pixelSize: 11
                                implicitWidth: 60; implicitHeight: 28
                                onClicked: {
                                    var fileHint = modelData.file ?? ""
                                    // Only ask for game folder when the hint is a relative
                                    // path (no drive letter / leading slash) AND no game
                                    // folder is set — absolute paths work without it.
                                    var isAbsolute = fileHint.length > 1 &&
                                        (fileHint[1] === ':' || fileHint[0] === '/')
                                    if (fileHint !== "" && !isAbsolute && vm.gameFolder === "") {
                                        root.pendingApplyPreset = modelData
                                        gameFolderDialog.open()
                                    } else {
                                        vm.applyTagPreset(
                                            modelData.label ?? "",
                                            modelData.parent_tag ?? "",
                                            modelData.target_tag ?? "",
                                            fileHint
                                        )
                                        loadPresetDialog.close()
                                    }
                                }
                                background: Rectangle {
                                    color: parent.hovered ? Theme.primaryHover : Theme.primary
                                    radius: 4
                                    Behavior on color { ColorAnimation { duration: 100 } }
                                }
                                contentItem: Label {
                                    text: parent.text; color: Theme.onPrimary
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                    font.pixelSize: 11
                                }
                            }

                            // Delete button
                            AppButton {
                                text: "🗑"
                                font.pixelSize: 13
                                implicitWidth: 30; implicitHeight: 28
                                onClicked: vm.deleteTagPreset(modelData.preset_id ?? 0)
                                background: Rectangle {
                                    color: parent.hovered ? Theme.dangerHover : "transparent"
                                    radius: 4
                                    border.color: parent.hovered ? "transparent" : Theme.borderSubtle
                                    border.width: 1
                                    Behavior on color { ColorAnimation { duration: 100 } }
                                }
                                contentItem: Label {
                                    text: parent.text
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                }
                            }
                        }
                    }
                }
            }

            // ── Footer (load preset)
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.borderSubtle }
            Row {
                Layout.alignment: Qt.AlignRight
                Layout.rightMargin: 16; Layout.topMargin: 12; Layout.bottomMargin: 12

                AppButton {
                    text: vm.strings["close_button"] ?? "Fechar"
                    onClicked: loadPresetDialog.close()
                    background: Rectangle {
                        color: parent.hovered ? Theme.bgSurface3 : Theme.bgSurface2
                        radius: 4; border.color: Theme.borderModerate; border.width: 1
                        Behavior on color { ColorAnimation { duration: 100 } }
                    }
                    contentItem: Label {
                        text: parent.text; color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter; font: parent.font
                    }
                }
            }
        }
    }

    GlossaryDialog { id: glossaryDialog }

    // ── FolderDialog for global game folder ──────────────────────────────────
    FolderDialog {
        id: gameFolderDialog
        title: vm.strings["preset_game_folder_tooltip"] ?? "Selecionar Pasta do Jogo"
        onAccepted: {
            var s = selectedFolder.toString()
            var path = s.startsWith("file:///") ? s.slice(8) : s
            vm.setGameFolder(path)
            // If Apply was pending while waiting for folder, execute it now
            if (root.pendingApplyPreset !== null) {
                var p = root.pendingApplyPreset
                vm.applyTagPreset(
                    p.label ?? "",
                    p.parent_tag ?? "",
                    p.target_tag ?? "",
                    p.file ?? ""
                )
                loadPresetDialog.close()
                root.pendingApplyPreset = null
            }
        }
        onRejected: root.pendingApplyPreset = null
    }

    // ── Listen for multiple XML scan results ─────────────────────────────────
    Connections {
        target: vm
        function onXmlPathsFound(paths) {
            root.xmlPickerPaths = paths
            xmlPickerDialog.open()
        }
    }

    // ── XML Picker Dialog (shown when folder scan finds multiple files) ───────
    Dialog {
        id: xmlPickerDialog
        modal: true
        anchors.centerIn: Overlay.overlay
        width: 460
        padding: 0
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            color: Theme.bgSurface2; radius: 8
            border.color: Theme.borderModerate; border.width: 1
        }

        contentItem: ColumnLayout {
            spacing: 0

            // ── Header
            Item {
                Layout.fillWidth: true; implicitHeight: 52
                Label {
                    anchors { left: parent.left; right: parent.right
                              verticalCenter: parent.verticalCenter
                              leftMargin: 20; rightMargin: 20 }
                    text: vm.strings["xml_picker_title"] ?? "Selecionar Arquivo XML"
                    font.pixelSize: 14; font.weight: Font.DemiBold
                    color: Theme.textPrimary; elide: Text.ElideRight
                }
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.borderSubtle }
            }

            // ── Subtitle
            Label {
                Layout.fillWidth: true
                Layout.leftMargin: 20; Layout.rightMargin: 20; Layout.topMargin: 12
                text: (vm.strings["xml_picker_subtitle"] ?? "{count} arquivo(s) encontrado(s). Selecione qual carregar:").replace("{count}", root.xmlPickerPaths.length)
                font.pixelSize: 12; color: Theme.textSecondary
                wrapMode: Text.Wrap
            }

            // ── File list
            Item {
                Layout.fillWidth: true
                Layout.topMargin: 8; Layout.bottomMargin: 8
                implicitHeight: Math.min(root.xmlPickerPaths.length * 56 + 16, 280)

                ListView {
                    anchors { fill: parent; margins: 8 }
                    model: root.xmlPickerPaths
                    clip: true
                    spacing: 4
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                    delegate: Rectangle {
                        width: ListView.view.width
                        height: 48
                        radius: 6
                        color: hoverArea.containsMouse ? Theme.bgSurface3 : Theme.bgSurface1
                        border.color: Theme.borderSubtle; border.width: 1

                        Behavior on color { ColorAnimation { duration: 80 } }

                        ColumnLayout {
                            anchors { fill: parent; leftMargin: 12; rightMargin: 12; topMargin: 6; bottomMargin: 6 }
                            spacing: 2
                            Label {
                                Layout.fillWidth: true
                                text: {
                                    var parts = modelData.replace(/\\/g, "/").split("/")
                                    return parts[parts.length - 1]
                                }
                                font.pixelSize: 12; font.weight: Font.Medium
                                color: Theme.textPrimary; elide: Text.ElideRight
                            }
                            Label {
                                Layout.fillWidth: true
                                text: {
                                    var parts = modelData.replace(/\\/g, "/").split("/")
                                    parts.pop()
                                    return parts.join("/")
                                }
                                font.pixelSize: 10; color: Theme.textSecondary
                                elide: Text.ElideLeft
                            }
                        }

                        MouseArea {
                            id: hoverArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                vm.loadXml(modelData)
                                xmlPickerDialog.close()
                            }
                        }
                    }
                }
            }

            // ── Footer
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.borderSubtle }
            Row {
                Layout.alignment: Qt.AlignRight
                Layout.rightMargin: 16; Layout.topMargin: 12; Layout.bottomMargin: 12

                AppButton {
                    text: vm.strings["close_button"] ?? "Fechar"
                    onClicked: xmlPickerDialog.close()
                    background: Rectangle {
                        color: parent.hovered ? Theme.bgSurface3 : Theme.bgSurface2
                        radius: 4; border.color: Theme.borderModerate; border.width: 1
                        Behavior on color { ColorAnimation { duration: 100 } }
                    }
                    contentItem: Label {
                        text: parent.text; color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter; font: parent.font
                    }
                }
            }
        }
    }
}
