import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Controls.FluentWinUI3

Pane {
    id: root

    required property string xpath
    required property string originalText
    required property string translationText

    signal translationEdited(string text)

    onTranslationTextChanged: {
        if (translationArea.text !== translationText)
            translationArea.text = translationText
    }
    onOriginalTextChanged: {
        originalArea.text = originalText
    }

    background: Rectangle { color: Theme.bgSurface1; radius: 6 }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8

        // ---- Title row with info button ----
        Item {
            Layout.fillWidth: true
            implicitHeight: 32
            Layout.bottomMargin: 4

            Label {
                anchors.centerIn: parent
                text: vm.strings["tools_panel_title"] ?? "Ferramentas"
                font.pixelSize: 18
                font.weight: Font.DemiBold
                color: Theme.textPrimary
            }

            Rectangle {
                id: infoBtn
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                width: 24; height: 24; radius: 12
                color: infoBtnMouse.containsMouse ? Theme.bgSurface3 : "transparent"
                border.color: Theme.borderModerate
                border.width: 1

                Text {
                    anchors.centerIn: parent
                    text: "i"
                    color: infoBtnMouse.containsMouse ? Theme.primary : Theme.textSecondary
                    font.pixelSize: 13
                    font.italic: true
                    font.weight: Font.Bold
                }

                MouseArea {
                    id: infoBtnMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: infoDialog.open()
                }
            }
        }

        // ── Info / Help Dialog ──────────────────────────────────────────────
        Dialog {
            id: infoDialog
            modal: true
            anchors.centerIn: Overlay.overlay
            width: 500
            padding: 0
            closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

            background: Rectangle {
                color: Theme.bgSurface2; radius: 8
                border.color: Theme.borderModerate; border.width: 1
            }

            contentItem: ColumnLayout {
                spacing: 0

                // Header
                Item {
                    Layout.fillWidth: true; implicitHeight: 52
                    Label {
                        anchors { left: parent.left; right: parent.right
                                  verticalCenter: parent.verticalCenter
                                  leftMargin: 20; rightMargin: 20 }
                        text: vm.strings["info_dialog_title"] ?? "Como usar"
                        font.pixelSize: 15; font.weight: Font.DemiBold
                        color: Theme.textPrimary
                    }
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.borderSubtle }
                }

                // Scrollable tips
                ScrollView {
                    Layout.fillWidth: true
                    implicitHeight: Math.min(
                        Overlay.overlay ? Overlay.overlay.height * 0.72 : 520,
                        520
                    )
                    clip: true
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                    ColumnLayout {
                        width: 500 - 24   // dialog width minus scrollbar gutter
                        spacing: 0

                        Repeater {
                            id: tipsRepeater
                            model: [
                                { icon: "📂", key: "info_tip_load_xml_title",  bodyKey: "info_tip_load_xml"  },
                                { icon: "🏷️", key: "info_tip_tags_title",       bodyKey: "info_tip_tags"      },
                                { icon: "💾", key: "info_tip_presets_title",    bodyKey: "info_tip_presets"   },
                                { icon: "⚡", key: "info_tip_batch_title",      bodyKey: "info_tip_batch"     },
                                { icon: "✏️", key: "info_tip_single_title",     bodyKey: "info_tip_single"    },
                                { icon: "📤", key: "info_tip_save_title",       bodyKey: "info_tip_save"      },
                                { icon: "🎯", key: "info_tip_context_title",    bodyKey: "info_tip_context"   },
                                { icon: "📖", key: "info_tip_glossary_title",   bodyKey: "info_tip_glossary"  },
                            ]

                            delegate: ColumnLayout {
                                Layout.fillWidth: true
                                Layout.leftMargin: 16; Layout.rightMargin: 16
                                Layout.topMargin: 10
                                Layout.bottomMargin: 0
                                spacing: 3

                                // Section title
                                RowLayout {
                                    spacing: 6
                                    Text { text: modelData.icon; font.pixelSize: 14 }
                                    Label {
                                        text: vm.strings[modelData.key] ?? modelData.key
                                        font.pixelSize: 13; font.weight: Font.DemiBold
                                        color: Theme.textPrimary
                                    }
                                }

                                // Section body
                                Label {
                                    Layout.fillWidth: true
                                    text: vm.strings[modelData.bodyKey] ?? ""
                                    font.pixelSize: 12
                                    color: Theme.textSecondary
                                    wrapMode: Text.WordWrap
                                    lineHeight: 1.35
                                }

                                // Thin separator (except last item)
                                Rectangle {
                                    visible: index < tipsRepeater.count - 1
                                    Layout.fillWidth: true; height: 1
                                    color: Theme.borderSubtle
                                    Layout.topMargin: 8
                                }
                            }
                        }

                        Item { implicitHeight: 12 }
                    }
                }

                // Footer
                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.borderSubtle }
                Row {
                    Layout.alignment: Qt.AlignRight
                    Layout.rightMargin: 16; Layout.topMargin: 10; Layout.bottomMargin: 10

                    AppButton {
                        text: vm.strings["close_button"] ?? "Fechar"
                        onClicked: infoDialog.close()
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

        // ---- Provider selector ----
        Label {
            text: vm.strings["provider_label"] ?? "AI Provider:"
            font.pixelSize: 12
            color: Theme.textSecondary
        }
        ComboBox {
            id: providerCombo
            model: vm.providers
            currentIndex: vm.providers.indexOf(vm.selectedProvider)
            Layout.fillWidth: true
            enabled: !vm.isTranslating
            onActivated: vm.selectProvider(currentText)

            contentItem: Text {
                leftPadding: 8
                text: providerCombo.displayText
                color: Theme.textInput
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                font: providerCombo.font
            }
            background: Rectangle {
                color: providerCombo.hovered ? Theme.bgSurface3 : Theme.bgInput
                radius: 4
                border.color: providerCombo.activeFocus ? Theme.borderFocus : Theme.borderInput
                border.width: providerCombo.activeFocus ? 2 : 1
            }
            popup: Popup {
                y: providerCombo.height
                width: providerCombo.width
                height: Math.min(providerListView.contentHeight + 8, 200)
                padding: 4
                background: Rectangle { color: Theme.bgSurface2; radius: 4; border.color: Theme.borderInput; border.width: 1 }
                contentItem: ListView {
                    id: providerListView
                    model: providerCombo.delegateModel
                    clip: true
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                }
            }

            HoverHandler { cursorShape: Qt.PointingHandCursor }
        }

        // ---- Model selector (Gemini only) ----
        Label {
            visible: vm.selectedProvider === "Gemini"
            text: vm.strings["ai_model_label"] ?? "AI Model:"
            font.pixelSize: 12
            color: Theme.textSecondary
        }
        ComboBox {
            id: modelCombo
            visible: vm.selectedProvider === "Gemini"
            enabled: !vm.isTranslating
            model: vm.modelLabels
            currentIndex: vm.selectedModelIndex
            Layout.fillWidth: true
            onActivated: vm.selectModelByIndex(currentIndex)

            contentItem: Text {
                leftPadding: 8
                text: modelCombo.displayText
                color: Theme.textInput
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                font: modelCombo.font
            }
            background: Rectangle {
                color: modelCombo.hovered ? Theme.bgSurface3 : Theme.bgInput
                radius: 4
                border.color: modelCombo.activeFocus ? Theme.borderFocus : Theme.borderInput
                border.width: modelCombo.activeFocus ? 2 : 1
            }
            popup: Popup {
                y: modelCombo.height
                width: modelCombo.width
                height: Math.min(modelListView.contentHeight + 8, 280)
                padding: 4
                background: Rectangle { color: Theme.bgSurface2; radius: 4; border.color: Theme.borderInput; border.width: 1 }
                contentItem: ListView {
                    id: modelListView
                    model: modelCombo.delegateModel
                    clip: true
                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                        minimumSize: 0.1
                    }
                }
            }

            HoverHandler { cursorShape: Qt.PointingHandCursor }

            Connections {
                target: vm
                function onModelsChanged(labels) {
                    modelCombo.model = labels
                    modelCombo.currentIndex = vm.selectedModelIndex
                }
            }
        }

        // ---- Ollama model name (Ollama only) ----
        Label {
            visible: vm.selectedProvider === "Ollama (Local)"
            text: vm.strings["ollama_model_label"] ?? "Ollama Model:"
            font.pixelSize: 12
            color: Theme.textSecondary
        }
        TextField {
            id: ollamaModelField
            visible: vm.selectedProvider === "Ollama (Local)"
            enabled: !vm.isTranslating
            text: vm.ollamaModel
            placeholderText: "llama3"
            Layout.fillWidth: true
            onEditingFinished: vm.setOllamaModel(text)

            color: Theme.textInput
            placeholderTextColor: Theme.textPlaceholder
            background: Rectangle {
                color: Theme.bgInput
                radius: 4
                border.color: parent.activeFocus ? Theme.borderFocus : Theme.borderInput
                border.width: parent.activeFocus ? 2 : 1
            }
        }

        // ---- API Key (hidden for Ollama) ----
        AppButton {
            visible: vm.providerNeedsApiKey
            enabled: !vm.isTranslating
            text: vm.strings["api_key_config"] ?? "API Key"
            Layout.fillWidth: true
            onClicked: vm.configureApiKey()
        }

        Connections {
            target: vm
            function onApiKeyDialogRequested(title, prompt, currentKey) {
                apiKeyDialog.dialogTitle = title
                apiKeyDialog.promptLabel = prompt
                apiKeyField.text = currentKey
                apiKeyDialog.open()
            }
        }

        Popup {
            id: apiKeyDialog
            parent: Overlay.overlay
            anchors.centerIn: Overlay.overlay
            width: 420
            height: apiKeyContent.implicitHeight + 40
            padding: 0
            modal: true
            closePolicy: Popup.CloseOnEscape

            property string dialogTitle: ""
            property string promptLabel: ""

            background: Rectangle {
                color: Theme.bgSurface1
                radius: 8
                border.color: Theme.borderModerate
                border.width: 1
            }

            ColumnLayout {
                id: apiKeyContent
                anchors { left: parent.left; right: parent.right; top: parent.top }
                anchors.margins: 20
                spacing: 14

                Label {
                    text: apiKeyDialog.dialogTitle
                    font.pixelSize: 14
                    font.weight: Font.Medium
                    color: Theme.textPrimary
                }

                Label {
                    text: apiKeyDialog.promptLabel
                    color: Theme.textSecondary
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }

                TextField {
                    id: apiKeyField
                    Layout.fillWidth: true
                    echoMode: TextInput.Password
                    placeholderText: "••••••••••••••••••••"
                    color: Theme.textInput
                    placeholderTextColor: Theme.textPlaceholder
                    background: Rectangle {
                        color: Theme.bgInput
                        radius: 4
                        border.color: apiKeyField.activeFocus ? Theme.borderFocus : Theme.borderInput
                        border.width: apiKeyField.activeFocus ? 2 : 1
                    }
                    Keys.onReturnPressed: {
                        vm.submitApiKey(apiKeyField.text)
                        apiKeyDialog.close()
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Item { Layout.fillWidth: true }

                    AppButton {
                        text: vm.strings["dialog_cancel_button"] ?? "Cancelar"
                        onClicked: apiKeyDialog.close()
                    }

                    AppButton {
                        text: "OK"
                        enabled: apiKeyField.text.trim().length > 0
                        onClicked: {
                            vm.submitApiKey(apiKeyField.text)
                            apiKeyDialog.close()
                        }
                        background: Rectangle {
                            color: parent.hovered ? Theme.primaryHover : Theme.primary
                            radius: 4
                            Behavior on color { ColorAnimation { duration: 100 } }
                        }
                        contentItem: Label {
                            text: parent.text
                            color: Theme.onPrimary
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            font: parent.font
                        }
                    }
                }
            }
        }

        // Dynamic link: get API key / install Ollama / etc.
        Label {
            text: vm.providerApiKeyLinkText
            font.pixelSize: 11
            color: Theme.primary
            Layout.alignment: Qt.AlignHCenter
            Layout.bottomMargin: 2
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: Qt.openUrlExternally(vm.providerApiKeyUrl)
            }
        }

        // ---- Batch translate ----
        AppButton {
            id: translateBtn
            text: vm.isTranslating
                  ? (vm.strings["cancel_button"] ?? "Cancel")
                  : (vm.strings["translate_all_button"] ?? "Translate All (AI)")
            Layout.fillWidth: true
            highlighted: !vm.isTranslating
            background: Rectangle {
                color: vm.isTranslating
                    ? (translateBtn.hovered ? Theme.dangerHover : Theme.danger)
                    : (translateBtn.hovered ? Theme.primaryHover : Theme.primary)
                radius: 4
                Behavior on color { ColorAnimation { duration: 100 } }
            }
            contentItem: Label {
                text: translateBtn.text
                color: Theme.onPrimary
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                font: translateBtn.font
            }
            onClicked: vm.isTranslating ? vm.cancelTranslation() : vm.startBatchTranslation()
        }

        // ---- Reset translations (small secondary action) ----
        // Visible only when there are loaded entries and not currently translating.
        Label {
            visible: vm.entryCount > 0 && !vm.isTranslating
            text: vm.strings["clear_checkpoint_button"] ?? "🔄 Reset Translation"
            font.pixelSize: 11
            color: Theme.textSecondary
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: -4   // pull closer to the button above

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                hoverEnabled: true
                onEntered: parent.color = Theme.textPrimary
                onExited:  parent.color = Theme.textSecondary
                onClicked: vm.clearCheckpoint()
            }
        }

        // ---- Separator ----
        Rectangle { height: 1; color: Theme.borderModerate; Layout.fillWidth: true }

        // ---- Glossary button ----
        AppButton {
            text: vm.strings["manage_glossary_button"] ?? "📖 Gerenciar Glossário"
            Layout.fillWidth: true
            onClicked: glossaryDialog.open()
            background: Rectangle {
                color: parent.hovered ? Theme.bgSurface3 : Theme.bgSurface2
                radius: 4
                border.color: Theme.borderModerate; border.width: 1
                Behavior on color { ColorAnimation { duration: 100 } }
            }
            contentItem: Label {
                text: parent.text; color: Theme.textPrimary
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                font: parent.font
            }
        }

        // ---- Translation context / theme ----
        Label {
            text: vm.strings["translation_context_label"] ?? "Contexto / Tema"
            font.pixelSize: 12
            color: Theme.textSecondary

            HoverHandler { id: contextLabelHover }
            ToolTip.visible: contextLabelHover.hovered
            ToolTip.delay: 500
            ToolTip.text: vm.strings["translation_context_tooltip"] ?? "Ex: \"Marvel Comics, superhero game\"\n\"Skyrim, medieval fantasy RPG\"\n\nEscreva em inglês para melhor resultado.\nUse o Glossário para fixar termos específicos."
        }
        TextField {
            id: contextField
            text: vm.translationContext
            placeholderText: vm.strings["translation_context_placeholder"] ?? "Ex: Marvel, Skyrim, The Sims 4..."
            Layout.fillWidth: true
            enabled: !vm.isTranslating
            onEditingFinished: vm.setTranslationContext(text)
            color: Theme.textInput
            placeholderTextColor: Theme.textPlaceholder
            background: Rectangle {
                color: Theme.bgInput
                radius: 4
                border.color: parent.activeFocus ? Theme.borderFocus : Theme.borderInput
                border.width: parent.activeFocus ? 2 : 1
            }
        }

        // ---- Original text (read-only) ----
        Label {
            text: vm.strings["original_text_label"] ?? "Original"
            font.pixelSize: 12
            color: Theme.textSecondary
        }
        ScrollView {
            Layout.fillWidth: true
            Layout.preferredHeight: 90
            clip: true
            background: Rectangle {
                color: Theme.bgInput
                radius: 4
                border.color: Theme.borderInput
                border.width: 1
            }

            TextArea {
                id: originalArea
                text: root.originalText
                readOnly: true
                wrapMode: TextArea.Wrap
                color: Theme.textSecondary
                font.pixelSize: 13
                background: null
                padding: 8
            }
        }

        // ---- Translation (editable) ----
        Label {
            text: vm.strings["translation_label"] ?? "Translation"
            font.pixelSize: 12
            color: Theme.textSecondary
        }
        ScrollView {
            Layout.fillWidth: true
            Layout.preferredHeight: 90
            clip: true
            background: Rectangle {
                color: Theme.bgInput
                radius: 4
                border.color: Theme.borderInput
                border.width: 1
            }

            TextArea {
                id: translationArea
                text: root.translationText
                wrapMode: TextArea.Wrap
                color: Theme.textInput
                font.pixelSize: 13
                background: null
                padding: 8
                onTextChanged: root.translationEdited(text)
            }
        }

        // ---- Suggest (selected item only) ----
        AppButton {
            id: suggestBtn
            text: vm.isSingleTranslating
                  ? (vm.strings["translating_button"] ?? "Translating…")
                  : (vm.strings["generate_suggestion_button"] ?? "Translate Selected (AI)")
            Layout.fillWidth: true
            enabled: root.xpath !== "" && !vm.isSingleTranslating
            onClicked: vm.translateSelected()

            background: Rectangle {
                color: vm.isSingleTranslating
                    ? Theme.bgSurface2
                    : (suggestBtn.enabled
                        ? (suggestBtn.hovered ? Theme.bgSurface3 : Theme.secondary)
                        : Theme.bgBase)
                radius: 4
                border.color: vm.isSingleTranslating
                    ? Theme.primary
                    : (suggestBtn.enabled ? Theme.borderModerate : Theme.borderSubtle)
                border.width: vm.isSingleTranslating ? 2 : 1
                Behavior on color { ColorAnimation { duration: 100 } }
            }
            contentItem: Row {
                spacing: 6
                anchors.centerIn: parent

                // Pulsing dot — only visible while translating
                Rectangle {
                    visible: vm.isSingleTranslating
                    width: 8; height: 8; radius: 4
                    color: Theme.primary
                    anchors.verticalCenter: parent.verticalCenter

                    SequentialAnimation on opacity {
                        running: vm.isSingleTranslating
                        loops: Animation.Infinite
                        NumberAnimation { to: 0.2; duration: 500; easing.type: Easing.InOutSine }
                        NumberAnimation { to: 1.0; duration: 500; easing.type: Easing.InOutSine }
                    }
                }

                Label {
                    text: suggestBtn.text
                    color: vm.isSingleTranslating
                        ? Theme.primary
                        : (suggestBtn.enabled ? Theme.onSecondary : Theme.textDisabled)
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    anchors.verticalCenter: parent.verticalCenter
                    font: suggestBtn.font
                }
            }
        }

        Item { Layout.fillHeight: true }

        // ---- Approve selected ----
        AppButton {
            id: approveBtn
            text: vm.strings["approve_button"] ?? "✅ Confirmar Tradução Selecionada"
            Layout.fillWidth: true
            Layout.preferredHeight: 34
            enabled: root.xpath !== "" && !vm.isTranslating
            HoverHandler { cursorShape: approveBtn.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor }
            background: Rectangle {
                color: approveBtn.enabled
                    ? (approveBtn.hovered ? Theme.bgSurface3 : Theme.bgSurface2)
                    : Theme.bgBase
                radius: 4
                border.color: approveBtn.enabled ? Theme.borderModerate : Theme.borderSubtle
                border.width: 1
                Behavior on color { ColorAnimation { duration: 100 } }
            }
            contentItem: Label {
                text: approveBtn.text
                color: approveBtn.enabled ? Theme.textPrimary : Theme.textDisabled
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                font.weight: Font.Normal
                font.pixelSize: 12
            }
            onClicked: vm.approveTranslation(root.xpath, translationArea.text)
        }

        // ---- Approve all ----
        AppButton {
            id: approveAllBtn
            text: vm.strings["approve_all_button"] ?? "✅ Confirmar Todas as Traduções"
            Layout.fillWidth: true
            Layout.preferredHeight: 34
            enabled: vm.hasXmlPath && !vm.isTranslating
            HoverHandler { cursorShape: approveAllBtn.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor }
            background: Rectangle {
                color: approveAllBtn.enabled
                    ? (approveAllBtn.hovered ? Theme.bgSurface3 : Theme.bgSurface2)
                    : Theme.bgBase
                radius: 4
                border.color: approveAllBtn.enabled ? Theme.borderModerate : Theme.borderSubtle
                border.width: 1
                Behavior on color { ColorAnimation { duration: 100 } }
            }
            contentItem: Label {
                text: approveAllBtn.text
                color: approveAllBtn.enabled ? Theme.textPrimary : Theme.textDisabled
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                font.weight: Font.Normal
                font.pixelSize: 12
            }
            onClicked: vm.approveAllTranslations()
        }
    }

    GlossaryDialog { id: glossaryDialog }
}
