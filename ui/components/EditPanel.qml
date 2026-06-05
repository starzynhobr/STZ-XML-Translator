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

        // ---- Title ----
        Label {
            text: vm.strings["tools_panel_title"] ?? "Tools"
            font.pixelSize: 18
            font.weight: Font.DemiBold
            Layout.alignment: Qt.AlignHCenter
            Layout.bottomMargin: 4
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
            text: vm.strings["api_key_config"] ?? "API Key"
            Layout.fillWidth: true
            onClicked: vm.configureApiKey()
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

        // ---- Approve / Confirm ----
        AppButton {
            id: approveBtn
            text: vm.strings["approve_button"] ?? "Confirm Translation"
            Layout.fillWidth: true
            Layout.preferredHeight: 42
            enabled: root.xpath !== ""
            HoverHandler { cursorShape: approveBtn.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor }
            background: Rectangle {
                color: approveBtn.enabled
                    ? (approveBtn.hovered ? Theme.successHover : Theme.success)
                    : Theme.bgBase
                radius: 4
                border.color: approveBtn.enabled ? "transparent" : Theme.borderSubtle
                border.width: 1
                Behavior on color { ColorAnimation { duration: 100 } }
            }
            contentItem: Label {
                text: approveBtn.text
                color: approveBtn.enabled ? Theme.onSuccess : Theme.textDisabled
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                font.weight: Font.Medium
                font.pixelSize: 13
            }
            onClicked: vm.approveTranslation(root.xpath, translationArea.text)
        }
    }
}
