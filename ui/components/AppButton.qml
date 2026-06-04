import QtQuick
import QtQuick.Controls
import QtQuick.Controls.FluentWinUI3

Button {
    HoverHandler { cursorShape: parent.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor }
}
