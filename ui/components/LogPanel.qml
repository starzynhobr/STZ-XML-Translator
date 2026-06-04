import QtQuick
import QtQuick.Controls
import QtQuick.Controls.FluentWinUI3

Pane {
    id: root

    required property string logText

    function clear() {}

    background: Rectangle { color: Theme.bgBase; radius: 6 }

    ScrollView {
        anchors.fill: parent
        clip: true

        TextArea {
            id: logArea
            text: root.logText
            readOnly: true
            wrapMode: TextArea.NoWrap
            color: Theme.textLog
            font.family: "Consolas, monospace"
            font.pixelSize: 12
            background: null
            padding: 6
            onTextChanged: cursorPosition = text.length
        }
    }
}
