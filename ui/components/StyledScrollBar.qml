import QtQuick
import QtQuick.Controls
import QtQuick.Controls.FluentWinUI3

ScrollBar {
    id: bar

    policy: ScrollBar.AsNeeded
    minimumSize: 0.15

    contentItem: Rectangle {
        implicitWidth: 6
        implicitHeight: 40
        radius: 3
        color: bar.pressed ? Theme.textPrimary
             : bar.hovered ? Theme.textSecondary
             :               Theme.textDisabled
        opacity: bar.active ? 1.0 : 0.45
        Behavior on color   { ColorAnimation  { duration: 120 } }
        Behavior on opacity { NumberAnimation { duration: 200 } }
    }

    background: Rectangle {
        implicitWidth: 6
        implicitHeight: 40
        radius: 3
        color: bar.active ? Qt.rgba(1, 1, 1, 0.05) : "transparent"
        Behavior on color { ColorAnimation { duration: 200 } }
    }
}
