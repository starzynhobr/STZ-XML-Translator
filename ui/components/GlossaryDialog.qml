import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Controls.FluentWinUI3

Dialog {
    id: root
    title: vm.strings["glossary_window_title"] ?? "Manage Glossary"
    width: 580
    height: 440
    modal: true

    anchors.centerIn: Overlay.overlay

    // Override Dialog background — FluentWinUI3 não herda dark palette
    background: Rectangle {
        color: Theme.bgSurface1
        radius: 8
        border.color: Theme.borderModerate
        border.width: 1
    }

    // Override title bar
    header: Pane {
        background: Rectangle { color: Theme.bgSurface1 }
        padding: 16
        Label {
            text: root.title
            font.pixelSize: 16
            font.weight: Font.DemiBold
            color: Theme.textPrimary
        }
    }

    property var entries: []

    onOpened: {
        entries = vm.loadGlossary()
        glossaryModel.clear()
        for (var i = 0; i < entries.length; i++)
            glossaryModel.append(entries[i])
    }

    ListModel { id: glossaryModel }

    // ---------------------------------------------------------------
    // Content
    // ---------------------------------------------------------------
    ColumnLayout {
        anchors.fill: parent
        spacing: 8

        Label {
            text: vm.strings["glossary_terms_label"] ?? "Terms"
            font.pixelSize: 12
            color: Theme.textSecondary
        }

        // Column headers
        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            Label { text: vm.strings["original_text_label"] ?? "Original";    Layout.fillWidth: true; color: Theme.textSecondary; font.pixelSize: 11 }
            Label { text: vm.strings["translation_label"]   ?? "Translation"; Layout.fillWidth: true; color: Theme.textSecondary; font.pixelSize: 11 }
            Item { width: 36 }
        }

        // Term list
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            ListView {
                id: termList
                model: glossaryModel
                spacing: 6
                clip: true

                delegate: RowLayout {
                    width: termList.width
                    spacing: 6

                    TextField {
                        text: model.original
                        Layout.fillWidth: true
                        onEditingFinished: glossaryModel.setProperty(index, "original", text)
                        color: Theme.textInput
                        placeholderTextColor: Theme.textPlaceholder
                        background: Rectangle {
                            color: Theme.bgInput
                            radius: 4
                            border.color: parent.activeFocus ? Theme.borderFocus : Theme.borderInput
                            border.width: parent.activeFocus ? 2 : 1
                        }
                    }
                    TextField {
                        text: model.translation
                        Layout.fillWidth: true
                        onEditingFinished: glossaryModel.setProperty(index, "translation", text)
                        color: Theme.textInput
                        placeholderTextColor: Theme.textPlaceholder
                        background: Rectangle {
                            color: Theme.bgInput
                            radius: 4
                            border.color: parent.activeFocus ? Theme.borderFocus : Theme.borderInput
                            border.width: parent.activeFocus ? 2 : 1
                        }
                    }
                    AppButton {
                        text: "✕"
                        width: 32
                        flat: true
                        onClicked: glossaryModel.remove(index)
                    }
                }
            }
        }

        AppButton {
            text: vm.strings["glossary_add_button"] ?? "+ Add Term"
            onClicked: glossaryModel.append({"original": "", "translation": ""})
        }
    }

    // ---------------------------------------------------------------
    // Footer — apenas 2 botões, sem standardButtons
    // ---------------------------------------------------------------
    footer: Pane {
        background: Rectangle {
            color: Theme.bgSurface1
            radius: 8   // só canto inferior
        }
        padding: 12

        RowLayout {
            anchors.fill: parent
            spacing: 8

            Item { Layout.fillWidth: true }   // empurra botões para a direita

            AppButton {
                text: vm.strings["glossary_save_button"] ?? "Save"
                highlighted: true
                onClicked: root.accept()
            }
            AppButton {
                text: vm.strings["close_button"] ?? "Close"
                onClicked: root.reject()
            }
        }
    }

    onAccepted: {
        var result = []
        for (var i = 0; i < glossaryModel.count; i++) {
            var item = glossaryModel.get(i)
            if (item.original && item.original.trim())
                result.push({"original": item.original, "translation": item.translation})
        }
        vm.saveGlossary(result)
    }
}
