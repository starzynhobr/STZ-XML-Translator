import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Controls.FluentWinUI3

Dialog {
    id: root
    title: vm.strings["glossary_window_title"] ?? "Manage Glossary"
    width: 580
    modal: true
    anchors.centerIn: Overlay.overlay
    padding: 0
    closePolicy: Popup.CloseOnEscape

    background: Rectangle {
        color: Theme.bgSurface1
        radius: 8
        border.color: Theme.borderModerate
        border.width: 1
    }

    // ---------------------------------------------------------------
    // Header
    // ---------------------------------------------------------------
    header: Item {
        implicitHeight: 56

        Label {
            anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter
                      leftMargin: 20; rightMargin: 20 }
            text: root.title
            font.pixelSize: 16
            font.weight: Font.DemiBold
            color: Theme.textPrimary
        }

        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width; height: 1
            color: Theme.borderSubtle
        }
    }

    // ---------------------------------------------------------------
    // Content
    // ---------------------------------------------------------------
    contentItem: ColumnLayout {
        spacing: 0

        // Column labels
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 14
            Layout.bottomMargin: 6
            Layout.leftMargin: 20
            Layout.rightMargin: 20
            spacing: 8

            Label {
                text: vm.strings["original_text_label"] ?? "Original"
                Layout.fillWidth: true
                font.pixelSize: 11
                font.weight: Font.Medium
                color: Theme.textSecondary
            }
            Label {
                text: vm.strings["translation_label"] ?? "Translation"
                Layout.fillWidth: true
                font.pixelSize: 11
                font.weight: Font.Medium
                color: Theme.textSecondary
            }
            Item { width: 32 }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.borderSubtle }

        // Term list
        ScrollView {
            Layout.fillWidth: true
            implicitHeight: Math.min(termList.contentHeight + 16, 280)
            Layout.topMargin: 8
            clip: true
            ScrollBar.vertical: StyledScrollBar {}

            ListView {
                id: termList
                model: glossaryModel
                spacing: 4
                clip: true
                leftMargin: 20
                rightMargin: 20
                topMargin: 4
                bottomMargin: 4

                delegate: RowLayout {
                    width: termList.width - termList.leftMargin - termList.rightMargin
                    spacing: 8

                    TextField {
                        id: origField
                        text: model.original
                        placeholderText: vm.strings["glossary_original_placeholder"] ?? "Original term…"
                        Layout.fillWidth: true
                        implicitHeight: 34
                        onEditingFinished: glossaryModel.setProperty(index, "original", text)
                        onTextEdited:      glossaryModel.setProperty(index, "original", text)
                        color: Theme.textInput
                        placeholderTextColor: Theme.textPlaceholder
                        background: Rectangle {
                            color: Theme.bgInput; radius: 4
                            border.color: origField.activeFocus ? Theme.borderFocus : Theme.borderInput
                            border.width: origField.activeFocus ? 2 : 1
                        }
                    }
                    TextField {
                        id: transField
                        text: model.translation
                        placeholderText: vm.strings["glossary_translation_placeholder"] ?? "Translation…"
                        Layout.fillWidth: true
                        implicitHeight: 34
                        onEditingFinished: glossaryModel.setProperty(index, "translation", text)
                        onTextEdited:      glossaryModel.setProperty(index, "translation", text)
                        color: Theme.textInput
                        placeholderTextColor: Theme.textPlaceholder
                        background: Rectangle {
                            color: Theme.bgInput; radius: 4
                            border.color: transField.activeFocus ? Theme.borderFocus : Theme.borderInput
                            border.width: transField.activeFocus ? 2 : 1
                        }
                    }

                    // Delete button
                    Rectangle {
                        width: 32; height: 32; radius: 4
                        color: delHover.containsMouse ? Theme.dangerSubtle : "transparent"
                        border.color: delHover.containsMouse ? Theme.danger : Theme.borderInput
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            text: "✕"; font.pixelSize: 12
                            color: delHover.containsMouse ? Theme.danger : Theme.textSecondary
                        }
                        MouseArea {
                            id: delHover
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: glossaryModel.remove(index)
                        }
                    }
                }
            }
        }

        // Add Term button row
        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.borderSubtle; Layout.topMargin: 8 }

        Item {
            Layout.fillWidth: true
            implicitHeight: 52

            AppButton {
                anchors { left: parent.left; verticalCenter: parent.verticalCenter; leftMargin: 20 }
                text: vm.strings["glossary_add_button"] ?? "+ Add Term"
                onClicked: {
                    glossaryModel.append({"original": "", "translation": ""})
                    Qt.callLater(function() { termList.positionViewAtEnd() })
                }
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
        }
    }

    ListModel { id: glossaryModel }

    onOpened: {
        var loaded = vm.loadGlossary()
        glossaryModel.clear()
        for (var i = 0; i < loaded.length; i++)
            glossaryModel.append(loaded[i])
    }

    // ---------------------------------------------------------------
    // Footer
    // ---------------------------------------------------------------
    footer: Item {
        implicitHeight: 60

        Rectangle {
            anchors.top: parent.top
            width: parent.width; height: 1
            color: Theme.borderSubtle
        }

        RowLayout {
            anchors { right: parent.right; verticalCenter: parent.verticalCenter
                      rightMargin: 16 }
            spacing: 8

            AppButton {
                text: vm.strings["close_button"] ?? "Close"
                onClicked: root.reject()
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

            AppButton {
                text: vm.strings["glossary_save_button"] ?? "Save"
                onClicked: {
                    // Force active focus away to flush any pending onEditingFinished
                    root.forceActiveFocus()
                    Qt.callLater(root.accept)
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
                    font: parent.font
                }
            }
        }
    }

    onAccepted: {
        var result = []
        for (var i = 0; i < glossaryModel.count; i++) {
            var item = glossaryModel.get(i)
            if (item.original && item.original.trim() !== "")
                result.push({"original": item.original.trim(), "translation": item.translation})
        }
        vm.saveGlossary(result)
    }
}
