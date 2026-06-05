import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Controls.FluentWinUI3

Pane {
    id: root

    required property string logText
    required property int    progressDone
    required property int    progressTotal

    property var localeNames:  Object.keys(vm.availableLocales)
    property var localeCodes:  Object.values(vm.availableLocales)
    property int currentLocaleIdx: {
        var codes = Object.values(vm.availableLocales)
        var idx = codes.indexOf(vm.currentLocaleCode)
        return idx >= 0 ? idx : 0
    }

    background: Rectangle { color: Theme.bgSurface1; radius: 6 }

    ScrollView {
        anchors.fill: parent
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

            // ---- Language selector ----
            ComboBox {
                id: langCombo
                model: root.localeNames
                currentIndex: root.currentLocaleIdx
                Layout.fillWidth: true
                Layout.leftMargin: 16; Layout.rightMargin: 16
                Layout.bottomMargin: 12
                onActivated: vm.changeLanguage(root.localeCodes[currentIndex])

                contentItem: Text {
                    leftPadding: 8
                    text: langCombo.displayText
                    color: Theme.textInput
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                    font: langCombo.font
                }
                background: Rectangle {
                    color: langCombo.hovered ? Theme.bgSurface3 : Theme.bgInput
                    radius: 4
                    border.color: langCombo.activeFocus ? Theme.borderFocus : Theme.borderInput
                    border.width: langCombo.activeFocus ? 2 : 1
                }
                popup: Popup {
                    y: langCombo.height
                    width: langCombo.width
                    height: Math.min(langListView.contentHeight + 8, 200)
                    padding: 4
                    background: Rectangle { color: Theme.bgSurface2; radius: 4; border.color: Theme.borderInput; border.width: 1 }
                    contentItem: ListView {
                        id: langListView
                        model: langCombo.delegateModel
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

                // Current tag pair info
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

                // Description field (required)
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

                // File field (optional)
                Label {
                    text: vm.strings["preset_file_field"] ?? "Arquivo (opcional)"
                    font.pixelSize: 11; color: Theme.textSecondary
                }
                TextField {
                    id: savePresetFileField
                    Layout.fillWidth: true
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
                            savePresetFileField.text.trim()
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

            // ── Body — preset list
            Item {
                Layout.fillWidth: true
                implicitHeight: Math.min(Math.max(vm.tagPresets.length, 1) * 68 + 16, 340)

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
                                    spacing: 6
                                    Label {
                                        text: (modelData.parent_tag ?? "") + " → " + (modelData.target_tag ?? "")
                                        font.pixelSize: 11; color: Theme.primary
                                    }
                                    Label {
                                        visible: (modelData.file ?? "") !== ""
                                        text: "• " + (modelData.file ?? "")
                                        font.pixelSize: 10; color: Theme.textSecondary
                                        elide: Text.ElideRight
                                    }
                                }
                            }

                            // Apply button
                            AppButton {
                                text: vm.strings["preset_apply_button"] ?? "Aplicar"
                                font.pixelSize: 11
                                implicitWidth: 60; implicitHeight: 28
                                onClicked: {
                                    vm.applyTagPreset(
                                        modelData.label ?? "",
                                        modelData.parent_tag ?? "",
                                        modelData.target_tag ?? ""
                                    )
                                    loadPresetDialog.close()
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
                                onClicked: vm.deleteTagPreset(modelData.id ?? 0)
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

            // ── Footer
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
}
