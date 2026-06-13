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

        Text {
            id: chevron
            anchors { right: parent.right; verticalCenter: parent.verticalCenter; rightMargin: 10 }
            text: "▾"
            color: Theme.textSecondary
            font.pixelSize: 9
            rotation: control.popup.visible ? 180 : 0
            Behavior on rotation { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
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
        y: control.height + 3
        width: control.width
        // +20px vertical padding (10 top + 10 bottom) so rounding errors at any DPI
        // never push contentHeight over viewHeight and trigger an unwanted scrollbar.
        height: Math.min(control.count * 36 + 20, 256)
        padding: 4
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        // Only animate opacity — animating `y` while the `y` property has a
        // static binding breaks that binding under Qt 6 and shifts the popup.
        enter: Transition {
            NumberAnimation {
                property: "opacity"; from: 0.0; to: 1.0
                duration: 120; easing.type: Easing.OutQuad
            }
        }
        exit: Transition {
            NumberAnimation {
                property: "opacity"; from: 1.0; to: 0.0
                duration: 80; easing.type: Easing.InQuad
            }
        }

        background: Rectangle {
            color: Theme.bgSurface2
            radius: 7
            border.color: Theme.borderModerate
            border.width: 1
        }

        contentItem: ListView {
            id: cbList
            model: control.delegateModel
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: StyledScrollBar {}

            // When the list is populated, scroll so the selected item is visible.
            // We do NOT set currentIndex here — that conflicts with delegateModel's
            // own state tracking and caused item 0 to disappear on open.
            onCountChanged: {
                if (count > 0 && control.currentIndex >= 0)
                    positionViewAtIndex(control.currentIndex, ListView.Beginning)
            }
        }
    }

    // ── Item delegate ─────────────────────────────────────────────────
    delegate: ItemDelegate {
        id: del
        width: ListView.view ? ListView.view.width : control.width
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
            color: del.highlighted ? Theme.bgSurface3 : "transparent"
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
                color: del.highlighted ? Theme.textPrimary : Theme.textSecondary
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
