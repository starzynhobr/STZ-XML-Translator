import QtQuick
import QtQuick.Controls
import QtQuick.Controls.FluentWinUI3

// Editable text field with an optional filtered suggestion dropdown.
// When `suggestions` is empty it behaves like a plain TextField.
// When `suggestions` is populated a chevron appears and typing filters results.
Item {
    id: root

    // ── Public API ────────────────────────────────────────────────────────
    property var    suggestions: []   // list<string> — populated from ViewModel
    property alias  value: field.text // current tag value (read/write)
    property string placeholderText: ""

    // Emitted when the value is committed (item selected or Enter pressed).
    signal committed(string tag)

    // Cached suggestion count — avoids scope issues accessing root.suggestions
    // from inside the Popup, and drives a stable height binding.
    property int _totalCount: 0
    onSuggestionsChanged: {
        _totalCount = suggestions ? suggestions.length : 0
        _refreshList(field.text)
    }

    // Clear value and close popup when the component is disabled
    // (e.g. no XML loaded yet).
    onEnabledChanged: {
        if (!enabled) {
            field.text = ""
            popup.close()
        }
    }

    implicitHeight: 36

    // ── Outer container (provides unified border + background) ────────────
    Rectangle {
        id: container
        anchors.fill: parent
        color: root.enabled ? Theme.bgInput : Theme.bgBase
        radius: 4
        border.color: !root.enabled        ? Theme.borderSubtle
                    : (field.activeFocus || popup.opened) ? Theme.borderFocus
                    : Theme.borderInput
        border.width: (field.activeFocus || popup.opened) ? 2 : 1

        Behavior on border.color { ColorAnimation { duration: 80 } }

        // ── Editable input ─────────────────────────────────────────────
        TextField {
            id: field
            anchors {
                left: parent.left
                right: hasSuggestions ? chevron.left : parent.right
                top: parent.top; bottom: parent.bottom
            }
            property bool hasSuggestions: root.suggestions.length > 0

            enabled: root.enabled
            placeholderText: root.placeholderText
            color: root.enabled ? Theme.textInput : Theme.textDisabled
            placeholderTextColor: Theme.textPlaceholder
            font.pixelSize: 13
            leftPadding: 8
            rightPadding: 4
            background: null   // container rectangle provides the background

            onTextEdited: {
                // Filter the list immediately (pure QML, no XML read)
                _refreshList(text)
                // Delay the "committed" signal so get_child_tags() isn't called
                // on every keystroke — fires 300 ms after the user stops typing.
                commitDebounce.restart()
                // Auto-open popup if there are filtered results
                if (filteredModel.count > 0 && text.length > 0)
                    popup.open()
                else if (text.length === 0 && root.suggestions.length > 0)
                    popup.open()   // show all on clear
                else
                    popup.close()
            }

            onActiveFocusChanged: {
                if (activeFocus && root.suggestions.length > 0) {
                    _refreshList(text)
                    popup.open()
                }
            }

            Keys.onEscapePressed: { popup.close(); focus = false }
            Keys.onReturnPressed: { popup.close(); root.committed(text) }
            Keys.onTabPressed:    { popup.close(); root.committed(text) }
        }

        // ── Chevron button (only when suggestions available) ───────────
        Rectangle {
            id: chevron
            visible: root.suggestions.length > 0
            anchors { right: parent.right; top: parent.top; bottom: parent.bottom }
            width: 26
            color: "transparent"
            radius: 4

            // Thin vertical separator
            Rectangle {
                anchors { left: parent.left; top: parent.top; bottom: parent.bottom
                          topMargin: 6; bottomMargin: 6 }
                width: 1
                color: Theme.borderSubtle
            }

            Text {
                anchors.centerIn: parent
                text: popup.opened ? "▲" : "▼"
                color: chevronMouse.containsMouse ? Theme.textPrimary : Theme.textSecondary
                font.pixelSize: 9
            }

            MouseArea {
                id: chevronMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    if (popup.opened) {
                        popup.close()
                    } else if (root._totalCount > 0) {
                        _refreshList("")   // show all suggestions
                        popup.open()
                        field.forceActiveFocus()
                    }
                }
            }
        }
    }

    // ── Suggestion popup ──────────────────────────────────────────────────
    Popup {
        id: popup
        y: root.height + 2
        width: root.width
        // Height is fixed to the TOTAL suggestion count so the popup never
        // shrinks while the user types. _totalCount is updated on the root
        // item (avoiding scope resolution issues from inside the Popup).
        height: Math.min(Math.max(root._totalCount, 3) * 34 + 8, 264)
        padding: 4
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        enter: Transition {
            ParallelAnimation {
                NumberAnimation { property: "opacity"; from: 0.0; to: 1.0; duration: 120; easing.type: Easing.OutQuad }
                NumberAnimation { property: "y"; from: root.height - 2; to: root.height + 2; duration: 120; easing.type: Easing.OutCubic }
            }
        }
        exit: Transition {
            NumberAnimation { property: "opacity"; from: 1.0; to: 0.0; duration: 80; easing.type: Easing.InQuad }
        }

        background: Rectangle {
            color: Theme.bgSurface2
            radius: 7
            border.color: Theme.borderModerate
            border.width: 1
        }

        contentItem: ListView {
            id: listView
            model: ListModel { id: filteredModel }
            clip: true
            ScrollBar.vertical: StyledScrollBar {}

            delegate: Rectangle {
                width: listView.width
                height: 34
                color: itemMouse.containsMouse ? Theme.bgSurface3 : "transparent"
                radius: 4
                Behavior on color { ColorAnimation { duration: 80 } }

                // Tag name
                Text {
                    anchors {
                        left: parent.left; verticalCenter: parent.verticalCenter
                        leftMargin: 12
                    }
                    text: model.name
                    color: model.name === field.text ? Theme.primary : Theme.textPrimary
                    font.pixelSize: 13
                    font.weight: model.name === field.text ? Font.Medium : Font.Normal
                }

                // Selection check mark
                Text {
                    anchors {
                        right: parent.right; verticalCenter: parent.verticalCenter
                        rightMargin: 12
                    }
                    text: "✓"
                    color: Theme.primary
                    font.pixelSize: 11
                    visible: model.name === field.text
                }

                MouseArea {
                    id: itemMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        field.text = model.name
                        root.committed(model.name)
                        popup.close()
                        field.forceActiveFocus()
                    }
                }
            }
        }
    }

    // ── Debounce timer — commits 300 ms after typing stops ────────────────
    // This prevents get_child_tags() (an XML file read) from firing on
    // every keystroke; only fires when the user pauses or finishes typing.
    Timer {
        id: commitDebounce
        interval: 300
        repeat: false
        onTriggered: root.committed(field.text)
    }

    // ── Helpers ───────────────────────────────────────────────────────────
    function _refreshList(filter) {
        filteredModel.clear()
        var f = filter.toLowerCase()
        for (var i = 0; i < root.suggestions.length; i++) {
            var s = root.suggestions[i]
            if (f === "" || s.toLowerCase().indexOf(f) >= 0)
                filteredModel.append({ name: s })
        }
    }

}
