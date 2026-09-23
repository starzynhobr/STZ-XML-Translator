import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Controls.FluentWinUI3

ComboBox {
    id: control

    implicitHeight: 36

    // Suppress the FluentWinUI3 built-in indicator so only our chevron shows.
    // Without this, the framework renders its own arrow alongside our custom one.
    indicator: Item {}

    // ── Trigger button ────────────────────────────────────────────────
    contentItem: Item {
        Text {
            anchors {
                left: parent.left; right: chevron.left; verticalCenter: parent.verticalCenter
                leftMargin: 12; rightMargin: 4
            }
            text: control.displayText
            color: control.enabled ? Theme.textInput : Theme.textDisabled
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
            font: control.font
        }

        Canvas {
            id: chevron
            objectName: "comboChevron"
            width: 16
            height: 16
            anchors { right: parent.right; verticalCenter: parent.verticalCenter; rightMargin: 10 }
            property color strokeColor: control.enabled ? Theme.textSecondary : Theme.textDisabled
            onStrokeColorChanged: requestPaint()
            onPaint: {
                var ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                ctx.beginPath()
                ctx.moveTo(3, 6)
                ctx.lineTo(8, 11)
                ctx.lineTo(13, 6)
                ctx.lineWidth = 1.8
                ctx.lineCap = "round"
                ctx.lineJoin = "round"
                ctx.strokeStyle = strokeColor
                ctx.stroke()
            }
        }
    }

    background: Rectangle {
        color: control.hovered ? Theme.bgSurface3 : Theme.bgInput
        radius: 5
        border.color: control.activeFocus ? Theme.borderFocus : Theme.borderInput
        border.width: control.activeFocus ? 2 : 1
        Behavior on color       { ColorAnimation { duration: 100 } }
        Behavior on border.color { ColorAnimation { duration: 100 } }
    }

    // ── Popup ─────────────────────────────────────────────────────────
    popup: Popup {
        id: cbPopup
        objectName: "comboPopup"
        y: control.height + 3
        width: Math.max(control.width, 220)
        height: Math.min(control.count * 36 + 8, 260)
        padding: 4
        topPadding: 4
        bottomPadding: 4
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        onOpened: Qt.callLater(function() {
            if (control.currentIndex >= 0)
                cbList.positionViewAtIndex(control.currentIndex, ListView.Contain)
        })

        background: Rectangle {
            color: Theme.bgInput
            radius: 6
            border.color: Theme.borderInput
            border.width: 1
        }

        contentItem: ListView {
            id: cbList
            objectName: "comboPopupList"
            model: control.delegateModel
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {
                policy: control.count * 36 > cbList.height + 1
                    ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
                implicitWidth: 5
                minimumSize: 0.15
                background: Item {}
                contentItem: Rectangle {
                    implicitWidth: 3
                    radius: 2
                    color: Theme.textSecondary
                    opacity: parent.pressed ? 0.8 : parent.hovered ? 0.65 : 0.4
                }
            }

        }
    }

    // ── Item delegate ─────────────────────────────────────────────────
    delegate: ItemDelegate {
        id: del
        width: ListView.view
            ? ListView.view.width - (control.count * 36 > cbList.height + 1 ? 8 : 0)
            : control.width
        height: 36
        padding: 0

        // When the popup first opens there is no hover yet (highlightedIndex === -1).
        // In that state, visually highlight the currently selected item so the user
        // always has a clear focus indicator on open.
        readonly property bool isCurrent: control.currentIndex === index
        highlighted: control.highlightedIndex >= 0
                     ? control.highlightedIndex === index
                     : isCurrent

        background: Rectangle {
            color: del.highlighted ? Theme.bgSurface1 : "transparent"
            radius: 4
            Behavior on color { ColorAnimation { duration: 80 } }
        }

        contentItem: RowLayout {
            anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
            spacing: 6

            Text {
                text: "✓"
                font.pixelSize: 11
                font.weight: Font.Medium
                color: Theme.primary
                visible: del.isCurrent
                Layout.preferredWidth: 14
                Layout.alignment: Qt.AlignVCenter
            }
            Item {
                visible: !del.isCurrent
                Layout.preferredWidth: 14
                Layout.preferredHeight: 1
            }

            Text {
                Layout.fillWidth: true
                text: modelData ?? ""
                font.pixelSize: 13
                color: Theme.textPrimary
                font.weight: del.isCurrent ? Font.Medium : Font.Normal
                elide: Text.ElideRight
                verticalAlignment: Text.AlignVCenter
                Behavior on color { ColorAnimation { duration: 80 } }
            }
        }

        HoverHandler { cursorShape: Qt.PointingHandCursor }
    }

    HoverHandler { cursorShape: Qt.PointingHandCursor }
}
