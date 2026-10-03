import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Controls.FluentWinUI3
import QtQuick.Dialogs
import Qt5Compat.GraphicalEffects

Pane {
    id: root

    required property string logText
    required property int    progressDone
    required property int    progressTotal
    property bool streamlined: false

    // UI language locales and translation targets intentionally remain separate.
    property var localeNames: Object.keys(vm.availableLocales)
    property var localeCodes: Object.values(vm.availableLocales)
    property var targetLocaleNames: Object.keys(vm.availableTranslationTargets)
    property var targetLocaleCodes: Object.values(vm.availableTranslationTargets)

    // Paths found during folder scan (populated by xmlPathsFound signal)
    property var xmlPickerPaths: []
    // Preset pending apply while folder dialog is open
    property var pendingApplyPreset: null

    function formatTags(tags) {
        if (!tags)
            return ""
        var values = []
        for (var i = 0; i < tags.length; i++)
            values.push(tags[i])
        return values.join(", ")
    }

    function openXmlPicker() {
        vm.loadXml(parentTagCombo.value, "")
    }

    function openSettings() {
        settingsDrawer.open()
    }

    // Overwriting the original file always goes through the confirmation dialog.
    function confirmSaveInPlace() {
        overwriteDialog.open()
    }

    // Index of the currently selected TRANSLATION TARGET locale
    property int currentTargetIdx: {
        var idx = targetLocaleCodes.indexOf(vm.translationTargetCode)
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
        radius: 6
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

        Popup {
            id: uiLangPopup
            y: -Math.min(root.localeNames.length * 34 + 8, 200) - 4
            width: parent.width
            height: Math.min(root.localeNames.length * 34 + 8, 200)
            padding: 4
            closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

            enter: Transition {
                NumberAnimation { property: "opacity"; from: 0.0; to: 1.0; duration: 120; easing.type: Easing.OutQuad }
            }
            exit: Transition {
                NumberAnimation { property: "opacity"; from: 1.0; to: 0.0; duration: 80 }
            }

            background: Rectangle {
                color: Theme.bgSurface2; radius: 7
                border.color: Theme.borderModerate; border.width: 1
            }

            contentItem: ListView {
                model: root.localeNames
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: StyledScrollBar {}

                delegate: Rectangle {
                    width: ListView.view.width
                    height: 34
                    color: uiLangItemMouse.containsMouse ? Theme.bgSurface3 : "transparent"
                    radius: 4
                    Behavior on color { ColorAnimation { duration: 80 } }

                    RowLayout {
                        anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                        spacing: 6

                        Text {
                            text: "✓"
                            font.pixelSize: 11; font.weight: Font.Medium
                            color: Theme.primary
                            visible: root.localeCodes[index] === vm.currentLocaleCode
                            Layout.preferredWidth: 14
                            Layout.alignment: Qt.AlignVCenter
                        }
                        Item {
                            visible: root.localeCodes[index] !== vm.currentLocaleCode
                            Layout.preferredWidth: 14; Layout.preferredHeight: 1
                        }

                        Text {
                            Layout.fillWidth: true
                            text: modelData
                            color: root.localeCodes[index] === vm.currentLocaleCode
                                   ? Theme.textPrimary : Theme.textSecondary
                            font.pixelSize: 12
                            font.weight: root.localeCodes[index] === vm.currentLocaleCode
                                         ? Font.Medium : Font.Normal
                            elide: Text.ElideRight
                            verticalAlignment: Text.AlignVCenter
                        }
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

    // ── Gear icon — top-right of sidebar ─────────────────────────────────
    Item {
        id: gearRow
        anchors { top: parent.top; left: parent.left; right: parent.right }
        height: root.streamlined ? 0 : 30
        visible: !root.streamlined

        Rectangle {
            id: gearBtn
            objectName: "sidebarSettingsButton"
            anchors { right: parent.right; rightMargin: 8; verticalCenter: parent.verticalCenter }
            width: 26; height: 26; radius: 5
            color: gearMouse.containsMouse ? Theme.bgSurface2 : "transparent"

            Behavior on color { ColorAnimation { duration: 100 } }

            Image {
                id: settingsIcon
                anchors.centerIn: parent
                width: 16; height: 16
                source: "../../assets/settings.svg"
                sourceSize: Qt.size(32, 32)
                smooth: true
                antialiasing: true
                layer.enabled: true
                layer.effect: ColorOverlay {
                    color: gearMouse.containsMouse ? Theme.textPrimary : Theme.textSecondary
                    Behavior on color { ColorAnimation { duration: 100 } }
                }
            }

            ToolTip.visible: gearMouse.containsMouse
            ToolTip.text: vm.strings["settings_tooltip"] ?? "Configurações"
            ToolTip.delay: 500

            MouseArea {
                id: gearMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: settingsDrawer.open()
            }
        }
    }

    // ── Main scrollable content (clean — only essential elements) ─────────
    ScrollView {
        anchors {
            top: gearRow.bottom
            left: parent.left; right: parent.right
            bottom: uiLangFooter.top
        }
        contentWidth: availableWidth
        clip: true

        ColumnLayout {
            StatusFilterPanel {
                Layout.fillWidth: true
                Layout.leftMargin: 14
                Layout.rightMargin: 14
                Layout.topMargin: 8
            }
            width: parent.width
            spacing: 0

            Label {
                objectName: "structureSectionTitle"
                visible: root.streamlined
                text: vm.strings["structure_section_title"] ?? "XML structure"
                color: Theme.textPrimary
                font.pixelSize: 13
                font.weight: Font.DemiBold
                Layout.fillWidth: true
                Layout.leftMargin: 14; Layout.rightMargin: 44
                Layout.topMargin: 14
                Layout.bottomMargin: 2
                elide: Text.ElideRight
            }

            Label {
                visible: root.streamlined
                text: vm.strings["structure_section_subtitle"]
                    ?? "Choose the text and context fields"
                color: Theme.textSecondary
                font.pixelSize: 10
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
                Layout.leftMargin: 14; Layout.rightMargin: 14
                Layout.bottomMargin: 10
            }

            Rectangle {
                visible: root.streamlined
                height: 1; color: Theme.borderSubtle
                Layout.fillWidth: true
                Layout.leftMargin: 12; Layout.rightMargin: 12
                Layout.bottomMargin: 12
            }

            // ── Carregar XML ──────────────────────────────────────────────
            AppButton {
                objectName: "sidebarLoadButton"
                visible: !root.streamlined
                text: vm.strings["load_xml_button"] ?? "Load XML"
                highlighted: true
                enabled: !vm.isTranslating && !vm.isXmlBusy
                Layout.fillWidth: true
                Layout.leftMargin: 12; Layout.rightMargin: 12
                Layout.topMargin: 10
                Layout.bottomMargin: vm.loadedFileName ? 3 : 10
                onClicked: vm.loadXml(parentTagCombo.value, "")
            }

            Label {
                visible: !root.streamlined && vm.loadedFileName !== ""
                text: vm.loadedFileName
                font.pixelSize: 11
                color: Theme.textSecondary
                elide: Text.ElideMiddle
                horizontalAlignment: Text.AlignHCenter
                Layout.fillWidth: true
                Layout.leftMargin: 12; Layout.rightMargin: 12
                Layout.bottomMargin: 10
            }

            // ── Separator ─────────────────────────────────────────────────
            Rectangle {
                visible: !root.streamlined
                height: 1; color: Theme.borderSubtle
                Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12
                Layout.bottomMargin: 10
            }

            // ── Translation target language ───────────────────────────────
            Label {
                visible: !root.streamlined
                text: vm.strings["translate_to_label"] ?? "Traduzir para:"
                font.pixelSize: 11
                color: Theme.textSecondary
                Layout.leftMargin: 12
                Layout.bottomMargin: 3
            }
            StyledComboBox {
                id: targetLangCombo
                objectName: "sidebarTargetLocale"
                visible: !root.streamlined
                model: root.targetLocaleNames
                currentIndex: root.currentTargetIdx
                Layout.fillWidth: true
                Layout.leftMargin: 12; Layout.rightMargin: 12
                Layout.bottomMargin: 10
                onActivated: vm.setTranslationTarget(root.targetLocaleCodes[currentIndex])
            }

            // ── Tag Pai ───────────────────────────────────────────────────
            Label {
                text: root.streamlined
                    ? (vm.strings["structure_parent_tag"] ?? "Parent tag")
                    : (vm.strings["parent_tag_label"] ?? "Parent Tag")
                font.pixelSize: 11
                color: Theme.textSecondary
                Layout.leftMargin: 12
                Layout.bottomMargin: 3
            }
            TagComboBox {
                id: parentTagCombo
                suggestions: vm.parentTags
                enabled: vm.hasXmlPath && !vm.isXmlBusy
                placeholderText: "ex: baseVillain"
                Layout.fillWidth: true
                Layout.leftMargin: 12; Layout.rightMargin: 12
                Layout.bottomMargin: 8
                onCommitted: function(tag) { vm.selectParentTag(tag) }

                Connections {
                    target: vm
                    function onSelectedTagChanged(parentTag, targetTag) {
                        parentTagCombo.value = parentTag
                    }
                }
            }

            // ── Tags Alvo ─────────────────────────────────────────────────
            Label {
                text: vm.strings["target_tags_label"] ?? "Target tags"
                font.pixelSize: 11
                color: Theme.textSecondary
                Layout.leftMargin: 12
                Layout.bottomMargin: 3
            }
            TagMultiSelect {
                id: targetTagsSelect
                suggestions: vm.childTags
                selectedValues: vm.selectedTargetTags
                excludedValues: vm.selectedContextTags
                enabled: vm.hasXmlPath && !vm.isXmlBusy
                placeholderText: vm.strings["target_tag_placeholder"] ?? "Add a tag to translate"
                roleMarker: "T"
                roleDescription: vm.strings["target_tags_label"] ?? "Target tags"
                removeText: vm.strings["remove_target_tag"] ?? "Remove target tag"
                accentColor: Theme.primary
                Layout.fillWidth: true
                Layout.leftMargin: 12; Layout.rightMargin: 12
                Layout.bottomMargin: 8
                onAddRequested: function(tag) { vm.addTargetTag(tag) }
                onRemoveRequested: function(tag) { vm.removeTargetTag(tag) }
            }

            // ── Tags de Contexto ─────────────────────────────────────────
            Label {
                text: vm.strings["context_tags_label"] ?? "Context tags"
                font.pixelSize: 11
                color: Theme.textSecondary
                Layout.leftMargin: 12
                Layout.bottomMargin: 3
            }
            TagMultiSelect {
                id: contextTagsSelect
                suggestions: vm.childTags
                selectedValues: vm.selectedContextTags
                excludedValues: vm.selectedTargetTags
                enabled: vm.hasXmlPath && !vm.isXmlBusy
                placeholderText: vm.strings["context_tag_placeholder"] ?? "Add context (optional)"
                roleMarker: "C"
                roleDescription: vm.strings["context_tags_label"] ?? "Context tags"
                removeText: vm.strings["remove_context_tag"] ?? "Remove context tag"
                accentColor: Theme.warning
                Layout.fillWidth: true
                Layout.leftMargin: 12; Layout.rightMargin: 12
                Layout.bottomMargin: 4
                onAddRequested: function(tag) { vm.addContextTag(tag) }
                onRemoveRequested: function(tag) { vm.removeContextTag(tag) }
            }

            Label {
                text: vm.isXmlBusy
                    ? vm.xmlBusyMessage
                    : (vm.strings["tag_selection_summary"] ?? "%1 tag(s) → %2 lines · %3 context")
                        .replace("%1", vm.selectedTargetTags.length)
                        .replace("%2", vm.tagPreviewLines)
                        .replace("%3", vm.selectedContextTags.length)
                font.pixelSize: 10
                color: Theme.textSecondary
                Layout.alignment: Qt.AlignRight
                Layout.rightMargin: 12
                Layout.bottomMargin: 8
            }

            // ── Reload ────────────────────────────────────────────────────
            AppButton {
                id: reloadBtn
                objectName: "applyStructureButton"
                text: vm.isXmlBusy
                    ? vm.xmlBusyMessage
                    : (root.streamlined && vm.tagPreviewLines > 0
                        ? (vm.strings["apply_structure_count_button"] ?? "Load %1 lines")
                            .replace("%1", vm.tagPreviewLines)
                        : (root.streamlined
                            ? (vm.strings["apply_structure_button"] ?? "Apply structure")
                            : (vm.strings["reload_button"] ?? "Recarregar")))
                Layout.fillWidth: true
                Layout.leftMargin: 12; Layout.rightMargin: 12
                Layout.bottomMargin: 10
                enabled: vm.hasXmlPath && parentTagCombo.value !== ""
                    && vm.selectedTargetTags.length > 0 && !vm.isTranslating && !vm.isXmlBusy
                onClicked: vm.reloadXml()
                ToolTip.visible: hovered; ToolTip.delay: 400
                ToolTip.text: root.streamlined
                    ? (vm.strings["apply_structure_button"] ?? "Apply structure")
                    : (vm.strings["reload_button"] ?? "Recarregar")
                background: Rectangle {
                    color: reloadBtn.enabled
                        ? (reloadBtn.hovered ? Theme.bgSurface3 : Theme.bgSurface2)
                        : Theme.bgBase
                    radius: 4
                    border.color: reloadBtn.enabled ? Theme.borderModerate : Theme.borderSubtle
                    border.width: 1
                    Behavior on color { ColorAnimation { duration: 100 } }
                }
                contentItem: Label {
                    text: reloadBtn.text
                    color: reloadBtn.enabled ? Theme.textPrimary : Theme.textDisabled
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    font: reloadBtn.font
                }
            }

            // ── Separator ─────────────────────────────────────────────────
            Rectangle {
                height: 1; color: Theme.borderModerate
                Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12
                Layout.bottomMargin: 10
            }

            // ── Progress ──────────────────────────────────────────────────
            Label {
                visible: !root.streamlined
                text: vm.strings["progress_label"] ?? "Progress"
                font.pixelSize: 11
                color: Theme.textSecondary
                Layout.alignment: Qt.AlignHCenter
                Layout.bottomMargin: 4
            }

            ProgressBar {
                id: progressBar
                objectName: "sidebarProgress"
                visible: !root.streamlined
                value: root.progressTotal > 0 ? root.progressDone / root.progressTotal : 0
                Layout.fillWidth: true
                Layout.leftMargin: 12; Layout.rightMargin: 12
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
                visible: !root.streamlined
                text: {
                    var tpl = vm.strings["stats_template"] ?? "Done: {done} / {total}"
                    return tpl.replace("{done}", root.progressDone).replace("{total}", root.progressTotal)
                }
                font.pixelSize: 11
                color: Theme.textSecondary
                Layout.alignment: Qt.AlignHCenter
                Layout.bottomMargin: 10
            }

            // ── Export XML ────────────────────────────────────────────────
            AppButton {
                id: exportXmlBtn
                objectName: "sidebarExportButton"
                visible: !root.streamlined
                text: vm.strings["export_button"] ?? "Export XML"
                Layout.fillWidth: true
                Layout.leftMargin: 12; Layout.rightMargin: 12
                Layout.bottomMargin: 6
                enabled: root.progressDone > 0 && !vm.isTranslating && !vm.isXmlBusy
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

            Rectangle {
                visible: !root.streamlined
                height: 1; color: Theme.borderSubtle
                Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12
                Layout.bottomMargin: 6
            }

            // ── Save In Place ─────────────────────────────────────────────
            AppButton {
                id: saveInPlaceBtn
                objectName: "sidebarSaveInPlaceButton"
                text: vm.strings["save_inplace_button"] ?? "💾 Save to Current File"
                Layout.fillWidth: true
                Layout.leftMargin: 12; Layout.rightMargin: 12
                Layout.bottomMargin: 12
                enabled: vm.entryCount > 0 && !vm.isTranslating && !vm.isXmlBusy
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

    // ── Settings Drawer ───────────────────────────────────────────────────
    // Slides in from the left edge of the window overlay.
    Popup {
        id: settingsDrawer
        objectName: "settingsDrawer"
        parent: Overlay.overlay
        x: 0; y: 0
        width: 270
        height: parent ? parent.height : 700
        modal: true
        padding: 0
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        enter: Transition {
            NumberAnimation { property: "x"; from: -270; to: 0; duration: 220; easing.type: Easing.OutCubic }
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 180 }
        }
        exit: Transition {
            NumberAnimation { property: "x"; from: 0; to: -270; duration: 180; easing.type: Easing.InCubic }
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 150 }
        }

        background: Rectangle {
            color: Theme.bgSurface1
            // Right border shadow line
            Rectangle {
                anchors { right: parent.right; top: parent.top; bottom: parent.bottom }
                width: 1; color: Theme.borderModerate
            }
        }

        contentItem: ColumnLayout {
            spacing: 0

            // ── Drawer header ─────────────────────────────────────────────
            Item {
                Layout.fillWidth: true
                implicitHeight: 52

                Label {
                    anchors { left: parent.left; verticalCenter: parent.verticalCenter; leftMargin: 18 }
                    text: vm.strings["settings_title"] ?? "Configurações"
                    font.pixelSize: 15; font.weight: Font.DemiBold
                    color: Theme.textPrimary
                }

                Rectangle {
                    id: drawerCloseBtn
                    anchors { right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
                    width: 26; height: 26; radius: 5
                    color: drawerCloseMouse.containsMouse ? Theme.bgSurface3 : "transparent"
                    Behavior on color { ColorAnimation { duration: 80 } }

                    Text {
                        anchors.centerIn: parent
                        text: "✕"; font.pixelSize: 12
                        color: drawerCloseMouse.containsMouse ? Theme.textPrimary : Theme.textSecondary
                    }
                    MouseArea {
                        id: drawerCloseMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: settingsDrawer.close()
                    }
                }

                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.borderSubtle }
            }

            // ── Scrollable drawer content ─────────────────────────────────
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentWidth: availableWidth
                clip: true

                ColumnLayout {
                    width: parent.width
                    spacing: 0

                    // ── Export / Import section ───────────────────────────
                    Label {
                        text: vm.strings["export_import_section_title"] ?? "Exportar / Importar"
                        font.pixelSize: 12; font.weight: Font.Medium
                        color: Theme.textSecondary
                        Layout.leftMargin: 18
                        Layout.topMargin: 16
                        Layout.bottomMargin: 2
                    }
                    Label {
                        text: vm.strings["export_import_section_subtitle"] ?? "Backup de traduções (.json, .csv)"
                        font.pixelSize: 10; color: Theme.textDisabled
                        Layout.leftMargin: 18
                        Layout.bottomMargin: 8
                    }

                    GridLayout {
                        columns: 2
                        Layout.fillWidth: true
                        Layout.leftMargin: 18; Layout.rightMargin: 18
                        Layout.bottomMargin: 16
                        columnSpacing: 6; rowSpacing: 6

                        AppButton {
                            text: vm.strings["export_json_button"] ?? "Exportar JSON"
                            Layout.fillWidth: true; font.pixelSize: 12
                            onClicked: vm.exportJson("")
                            ToolTip.visible: hovered; ToolTip.delay: 400
                            ToolTip.text: vm.strings["export_json_button"] ?? "Exportar JSON"
                        }
                        AppButton {
                            text: vm.strings["export_csv_button"] ?? "Exportar CSV"
                            Layout.fillWidth: true; font.pixelSize: 12
                            onClicked: vm.exportCsv("")
                            ToolTip.visible: hovered; ToolTip.delay: 400
                            ToolTip.text: vm.strings["export_csv_button"] ?? "Exportar CSV"
                        }
                        AppButton {
                            text: vm.strings["import_json_button"] ?? "Importar JSON"
                            Layout.fillWidth: true; font.pixelSize: 12
                            enabled: !vm.isTranslating && !vm.isXmlBusy; onClicked: vm.importJson("")
                            ToolTip.visible: hovered; ToolTip.delay: 400
                            ToolTip.text: vm.strings["import_json_button"] ?? "Importar JSON"
                        }
                        AppButton {
                            text: vm.strings["import_csv_button"] ?? "Importar CSV"
                            Layout.fillWidth: true; font.pixelSize: 12
                            enabled: !vm.isTranslating && !vm.isXmlBusy; onClicked: vm.importCsv("")
                            ToolTip.visible: hovered; ToolTip.delay: 400
                            ToolTip.text: vm.strings["import_csv_button"] ?? "Importar CSV"
                        }
                    }

                    // ── Separator ─────────────────────────────────────────
                    Rectangle {
                        height: 1; color: Theme.borderSubtle
                        Layout.fillWidth: true; Layout.leftMargin: 18; Layout.rightMargin: 18
                        Layout.bottomMargin: 14
                    }

                    // ── Presets section ───────────────────────────────────
                    Label {
                        text: vm.strings["presets_section_title"] ?? "Presets de Tags"
                        font.pixelSize: 12; font.weight: Font.Medium
                        color: Theme.textSecondary
                        Layout.leftMargin: 18
                        Layout.bottomMargin: 8
                    }

                    GridLayout {
                        columns: 2
                        Layout.fillWidth: true
                        Layout.leftMargin: 18; Layout.rightMargin: 18
                        Layout.bottomMargin: 16
                        columnSpacing: 6; rowSpacing: 6

                        AppButton {
                            id: drawerSavePresetBtn
                            text: vm.strings["save_preset_button"] ?? "💾 Salvar Preset"
                            Layout.fillWidth: true; font.pixelSize: 12
                            enabled: vm.hasXmlPath && parentTagCombo.value !== ""
                                && vm.selectedTargetTags.length > 0 && !vm.isXmlBusy
                            onClicked: {
                                savePresetLabelField.text = ""
                                savePresetFileField.text = vm.loadedFileName
                                savePresetDialog.open()
                            }
                            ToolTip.visible: hovered; ToolTip.delay: 400
                            ToolTip.text: vm.strings["save_preset_button"] ?? "Salvar Preset"
                            background: Rectangle {
                                color: drawerSavePresetBtn.enabled
                                    ? (drawerSavePresetBtn.hovered ? Theme.bgSurface3 : Theme.bgSurface2)
                                    : Theme.bgBase
                                radius: 4
                                border.color: drawerSavePresetBtn.enabled ? Theme.borderModerate : Theme.borderSubtle
                                border.width: 1
                                Behavior on color { ColorAnimation { duration: 100 } }
                            }
                            contentItem: Label {
                                text: drawerSavePresetBtn.text
                                color: drawerSavePresetBtn.enabled ? Theme.textPrimary : Theme.textDisabled
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                font: drawerSavePresetBtn.font
                                elide: Text.ElideRight
                            }
                        }
                        AppButton {
                            text: vm.strings["load_preset_button"] ?? "📂 Carregar Preset"
                            Layout.fillWidth: true; font.pixelSize: 12
                            onClicked: loadPresetDialog.open()
                            ToolTip.visible: hovered; ToolTip.delay: 400
                            ToolTip.text: vm.strings["load_preset_button"] ?? "Carregar Preset"
                        }
                        AppButton {
                            id: drawerExportPresetBtn
                            text: vm.strings["export_preset_button"] ?? "📤 Exportar Presets"
                            Layout.fillWidth: true; font.pixelSize: 12
                            enabled: vm.tagPresets.length > 0
                            onClicked: vm.exportPresets()
                            ToolTip.visible: hovered; ToolTip.delay: 400
                            ToolTip.text: vm.strings["export_preset_button"] ?? "Exportar Presets"
                            background: Rectangle {
                                color: drawerExportPresetBtn.enabled
                                    ? (drawerExportPresetBtn.hovered ? Theme.bgSurface3 : Theme.bgSurface2)
                                    : Theme.bgBase
                                radius: 4
                                border.color: drawerExportPresetBtn.enabled ? Theme.borderModerate : Theme.borderSubtle
                                border.width: 1
                                Behavior on color { ColorAnimation { duration: 100 } }
                            }
                            contentItem: Label {
                                text: drawerExportPresetBtn.text
                                color: drawerExportPresetBtn.enabled ? Theme.textPrimary : Theme.textDisabled
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                font: drawerExportPresetBtn.font
                                elide: Text.ElideRight
                            }
                        }
                        AppButton {
                            text: vm.strings["import_preset_button"] ?? "📥 Importar Presets"
                            Layout.fillWidth: true; font.pixelSize: 12
                            onClicked: vm.importPresets()
                            ToolTip.visible: hovered; ToolTip.delay: 400
                            ToolTip.text: vm.strings["import_preset_button"] ?? "Importar Presets"
                        }
                    }

                    // ── Separator ─────────────────────────────────────────
                    Rectangle {
                        height: 1; color: Theme.borderSubtle
                        Layout.fillWidth: true; Layout.leftMargin: 18; Layout.rightMargin: 18
                        Layout.bottomMargin: 14
                    }

                    // ── Appearance section ────────────────────────────────
                    Label {
                        text: vm.strings["appearance_section_title"] ?? "Appearance"
                        font.pixelSize: 12; font.weight: Font.Medium
                        color: Theme.textSecondary
                        Layout.leftMargin: 18
                        Layout.bottomMargin: 2
                    }
                    Label {
                        text: vm.strings["appearance_section_subtitle"] ?? "Interface theme"
                        font.pixelSize: 10; color: Theme.textDisabled
                        Layout.leftMargin: 18
                        Layout.bottomMargin: 8
                    }

                    StyledComboBox {
                        id: themeCombo
                        model: vm.themeNames
                        Layout.fillWidth: true
                        Layout.leftMargin: 18; Layout.rightMargin: 18
                        Layout.bottomMargin: 16

                        Component.onCompleted: {
                            var idx = vm.themeNames.indexOf(vm.currentThemeName)
                            currentIndex = idx >= 0 ? idx : 0
                        }

                        onActivated: themeCtrl.setTheme(model[currentIndex])
                    }

                    Label {
                        text: vm.strings["ui_mode_label"] ?? "Interface"
                        font.pixelSize: 11
                        color: Theme.textSecondary
                        Layout.leftMargin: 18
                        Layout.bottomMargin: 2
                    }

                    StyledComboBox {
                        id: uiModeCombo
                        model: [
                            vm.strings["ui_mode_classic"] ?? "Classic",
                            vm.strings["ui_mode_modern"] ?? "New"
                        ]
                        Layout.fillWidth: true
                        Layout.leftMargin: 18; Layout.rightMargin: 18
                        currentIndex: vm.currentUiMode === "modern" ? 1 : 0
                        onActivated: vm.setUiMode(currentIndex === 1 ? "modern" : "classic")
                    }

                    Label {
                        text: vm.strings["ui_mode_restart_hint"]
                            ?? "The change is applied after restarting the app."
                        font.pixelSize: 10
                        color: Theme.textDisabled
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                        Layout.leftMargin: 18; Layout.rightMargin: 18
                        Layout.bottomMargin: 16
                    }

                    Rectangle {
                        height: 1; color: Theme.borderSubtle
                        Layout.fillWidth: true; Layout.leftMargin: 18; Layout.rightMargin: 18
                        Layout.bottomMargin: 14
                    }

                    Label {
                        text: vm.strings["updates_section_title"] ?? "Updates"
                        font.pixelSize: 12; font.weight: Font.Medium
                        color: Theme.textSecondary
                        Layout.leftMargin: 18
                        Layout.bottomMargin: 2
                    }
                    Label {
                        text: (vm.strings["update_current_version"] ?? "Installed version: %1")
                            .arg(vm.appVersion)
                        font.pixelSize: 10
                        color: Theme.textDisabled
                        Layout.leftMargin: 18; Layout.rightMargin: 18
                        Layout.bottomMargin: 8
                    }
                    AppButton {
                        objectName: "checkForUpdatesButton"
                        text: vm.updateStatus === "checking"
                            ? (vm.strings["update_status_checking"] ?? "Checking…")
                            : (vm.strings["update_check_now"] ?? "Check for updates")
                        Layout.fillWidth: true
                        Layout.leftMargin: 18; Layout.rightMargin: 18
                        font.pixelSize: 12
                        enabled: vm.updateStatus !== "checking" && vm.updateStatus !== "downloading"
                        onClicked: vm.checkForUpdates()
                    }
                    Label {
                        objectName: "updateStatusLabel"
                        text: vm.updateStatusText
                        visible: vm.updateStatus !== "idle"
                        font.pixelSize: 10
                        color: vm.updateStatus === "error"
                            ? Theme.danger
                            : vm.updateStatus === "up_to_date" ? Theme.success : Theme.textSecondary
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                        Layout.leftMargin: 18; Layout.rightMargin: 18
                        Layout.topMargin: 6
                        Layout.bottomMargin: 16
                    }

                    Item { implicitHeight: 8; Layout.fillWidth: true }

                }
            }
        }
    }

    // ── Overwrite confirmation dialog ─────────────────────────────────────
    Dialog {
        id: overwriteDialog
        modal: true
        anchors.centerIn: Overlay.overlay
        width: 360
        padding: 0
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            color: Theme.bgSurface2
            radius: 8
            border.color: Theme.borderModerate
            border.width: 1
        }

        contentItem: ColumnLayout {
            spacing: 0

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

            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.borderSubtle }

            Row {
                Layout.alignment: Qt.AlignRight
                Layout.rightMargin: 16
                Layout.topMargin: 12
                Layout.bottomMargin: 12
                spacing: 8

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
                        text: parent.text; color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        font: parent.font
                    }
                }

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
                        text: parent.text; color: "#ffffff"
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        font.weight: Font.Medium; font.pixelSize: 13
                    }
                }
            }
        }
    }

    // ── Save Preset Dialog ────────────────────────────────────────────────
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

            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 20
                spacing: 10

                Rectangle {
                    Layout.fillWidth: true
                    height: 50; radius: 4
                    color: Theme.bgSurface1
                    border.color: Theme.borderSubtle; border.width: 1
                    Column {
                        anchors { left: parent.left; right: parent.right
                                  verticalCenter: parent.verticalCenter
                                  leftMargin: 10; rightMargin: 10 }
                        spacing: 2
                        Label {
                            width: parent.width
                            text: parentTagCombo.value + "  →  " + root.formatTags(vm.selectedTargetTags)
                            font.pixelSize: 12; font.weight: Font.Medium
                            color: Theme.primary; elide: Text.ElideRight
                        }
                        Label {
                            width: parent.width
                            text: (vm.strings["context_tags_short"] ?? "Context") + ": "
                                + (root.formatTags(vm.selectedContextTags) || "—")
                            font.pixelSize: 10
                            color: Theme.textSecondary; elide: Text.ElideRight
                        }
                    }
                }

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
                        vm.saveTagPresetMulti(
                            savePresetLabelField.text.trim(),
                            parentTagCombo.value,
                            vm.selectedTargetTags,
                            vm.selectedContextTags,
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

    // ── Load Preset Dialog ────────────────────────────────────────────────
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

            // Game folder row
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

            // Preset list
            Item {
                Layout.fillWidth: true
                implicitHeight: Math.min(Math.max(vm.tagPresets.length, 1) * 68 + 16, 300)

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
                    ScrollBar.vertical: StyledScrollBar {}

                    delegate: Rectangle {
                        id: presetDelegate
                        width: ListView.view.width
                        height: 60
                        radius: 6
                        color: Theme.bgSurface1
                        border.color: Theme.borderSubtle; border.width: 1

                        TapHandler {
                            acceptedButtons: Qt.RightButton
                            onTapped: presetContextMenu.popup()
                        }

                        Menu {
                            id: presetContextMenu
                            MenuItem {
                                text: "✏️  Renomear"
                                onTriggered: {
                                    renameField.text = modelData.label ?? ""
                                    renameField.selectAll()
                                    renamePopup.presetId = modelData.preset_id ?? 0
                                    renamePopup.open()
                                }
                            }
                        }

                        RowLayout {
                            anchors { fill: parent; leftMargin: 12; rightMargin: 8; topMargin: 6; bottomMargin: 6 }
                            spacing: 8

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
                                        text: (modelData.parent_tag ?? "") + " → "
                                            + root.formatTags(modelData.target_tags ?? [])
                                            + ((modelData.context_tags ?? []).length > 0
                                                ? "  ·  C: " + root.formatTags(modelData.context_tags)
                                                : "")
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
                                    Label {
                                        visible: (modelData.file ?? "") !== "" && modelData.file_exists !== undefined
                                        text: modelData.file_exists ? "✓" : "✗"
                                        font.pixelSize: 10; font.weight: Font.Medium
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

                            AppButton {
                                text: vm.strings["preset_apply_button"] ?? "Aplicar"
                                font.pixelSize: 11
                                implicitWidth: 60; implicitHeight: 28
                                onClicked: {
                                    var fileHint = modelData.file ?? ""
                                    var isAbsolute = fileHint.length > 1 &&
                                        (fileHint[1] === ':' || fileHint[0] === '/')
                                    if (fileHint !== "" && !isAbsolute && vm.gameFolder === "") {
                                        root.pendingApplyPreset = modelData
                                        gameFolderDialog.open()
                                    } else {
                                        vm.applyTagPresetMulti(
                                            modelData.label ?? "",
                                            modelData.parent_tag ?? "",
                                            modelData.target_tags ?? [],
                                            modelData.context_tags ?? [],
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

    // ── Rename Preset Popup ───────────────────────────────────────────────
    Popup {
        id: renamePopup
        parent: Overlay.overlay
        anchors.centerIn: Overlay.overlay
        width: 320
        height: renameContent.implicitHeight + 40
        padding: 0; modal: true
        closePolicy: Popup.CloseOnEscape

        property var presetId: 0

        background: Rectangle {
            color: Theme.bgSurface2; radius: 8
            border.color: Theme.borderModerate; border.width: 1
        }

        ColumnLayout {
            id: renameContent
            anchors { left: parent.left; right: parent.right; top: parent.top }
            anchors.margins: 20
            spacing: 12

            Label {
                text: "✏️  Renomear Preset"
                font.pixelSize: 14; font.weight: Font.Medium
                color: Theme.textPrimary
            }

            TextField {
                id: renameField
                Layout.fillWidth: true
                color: Theme.textInput
                placeholderTextColor: Theme.textPlaceholder
                background: Rectangle {
                    color: Theme.bgInput; radius: 4
                    border.color: renameField.activeFocus ? Theme.borderFocus : Theme.borderInput
                    border.width: renameField.activeFocus ? 2 : 1
                }
                Keys.onReturnPressed: {
                    vm.renameTagPreset(renamePopup.presetId, renameField.text)
                    renamePopup.close()
                }
                Keys.onEscapePressed: renamePopup.close()
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Item { Layout.fillWidth: true }

                AppButton {
                    text: vm.strings["dialog_cancel_button"] ?? "Cancelar"
                    onClicked: renamePopup.close()
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
                    text: "OK"
                    onClicked: {
                        vm.renameTagPreset(renamePopup.presetId, renameField.text)
                        renamePopup.close()
                    }
                    background: Rectangle {
                        color: parent.hovered ? Theme.primaryHover : Theme.primary
                        radius: 4
                        Behavior on color { ColorAnimation { duration: 100 } }
                    }
                    contentItem: Label {
                        text: parent.text; color: Theme.onPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter; font: parent.font
                    }
                }
            }

            Item { height: 2 }
        }

        onOpened: renameField.forceActiveFocus()
    }

    // ── FolderDialog for global game folder ──────────────────────────────
    FolderDialog {
        id: gameFolderDialog
        title: vm.strings["preset_game_folder_tooltip"] ?? "Selecionar Pasta do Jogo"
        onAccepted: {
            var s = selectedFolder.toString()
            var path = s.startsWith("file:///") ? s.slice(8) : s
            vm.setGameFolder(path)
            if (root.pendingApplyPreset !== null) {
                var p = root.pendingApplyPreset
                vm.applyTagPresetMulti(
                    p.label ?? "",
                    p.parent_tag ?? "",
                    p.target_tags ?? [],
                    p.context_tags ?? [],
                    p.file ?? ""
                )
                loadPresetDialog.close()
                root.pendingApplyPreset = null
            }
        }
        onRejected: root.pendingApplyPreset = null
    }

    // ── Listen for multiple XML scan results ─────────────────────────────
    Connections {
        target: vm
        function onXmlPathsFound(paths) {
            root.xmlPickerPaths = paths
            xmlPickerDialog.open()
        }
    }

    // ── XML Picker Dialog ─────────────────────────────────────────────────
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

            Label {
                Layout.fillWidth: true
                Layout.leftMargin: 20; Layout.rightMargin: 20; Layout.topMargin: 12
                text: (vm.strings["xml_picker_subtitle"] ?? "{count} arquivo(s) encontrado(s). Selecione qual carregar:").replace("{count}", root.xmlPickerPaths.length)
                font.pixelSize: 12; color: Theme.textSecondary
                wrapMode: Text.Wrap
            }

            Item {
                Layout.fillWidth: true
                Layout.topMargin: 8; Layout.bottomMargin: 8
                implicitHeight: Math.min(root.xmlPickerPaths.length * 56 + 16, 280)

                ListView {
                    anchors { fill: parent; margins: 8 }
                    model: root.xmlPickerPaths
                    clip: true
                    spacing: 4
                    ScrollBar.vertical: StyledScrollBar {}

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
