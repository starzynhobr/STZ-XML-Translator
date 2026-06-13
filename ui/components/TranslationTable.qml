import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Qt.labs.qmlmodels
import QtQuick.Controls.FluentWinUI3

Pane {
    id: root

    signal rowClicked(int row)

    background: Rectangle { color: Theme.bgBase; radius: 6 }

    function statusColor(status, hovered, selected) {
        if (selected)                  return Theme.rowSelected
        if (status === "done")         return hovered ? Theme.rowDoneHover     : Theme.rowDone
        if (status === "translating")  return hovered ? Theme.rowTranslatingHover : Theme.rowTranslating
        return hovered ? Theme.rowDefaultHover : "transparent"
    }

    // ---------------------------------------------------------------
    // Header
    // ---------------------------------------------------------------
    HorizontalHeaderView {
        id: header
        syncView: tableView
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: 32

        delegate: Rectangle {
            required property int column
            implicitHeight: 32
            color: Theme.bgHeader
            border.color: Theme.borderHeader
            border.width: 1

            Label {
                anchors.centerIn: parent
                text: column === 0 ? "#"
                    : column === 1 ? (vm.strings["original_text_label"] ?? "Original")
                    :                (vm.strings["translation_label"]   ?? "Translation")
                font.pixelSize: 12
                font.weight: Font.Medium
                color: Theme.textHeader
            }
        }
    }

    // ---------------------------------------------------------------
    // Table
    // ---------------------------------------------------------------
    property int _selectedRow: -1

    TableView {
        id: tableView
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: scrollBar.left
        anchors.bottom: parent.bottom

        model: vm.tableModel
        clip: true
        reuseItems: true
        columnWidthProvider: function(col) {
            if (col === 0) return 44
            var rest = width - 44
            return col === 1 ? rest * 0.45 : rest * 0.55
        }

        ScrollBar.vertical: scrollBar

        selectionModel: ItemSelectionModel {
            model: vm.tableModel
        }

        delegate: Rectangle {
            id: cell
            required property int    row
            required property int    column
            required property bool   selected
            required property string display
            required property string entryStatus

            implicitHeight: 28
            clip: true
            color: root.statusColor(entryStatus, cellMouse.containsMouse, selected)

            Behavior on color { ColorAnimation { duration: 80 } }

            Label {
                anchors {
                    left: parent.left; right: parent.right
                    verticalCenter: parent.verticalCenter
                    leftMargin: cell.column === 0 ? 0 : 8
                    rightMargin: cell.column === 0 ? 0 : 8
                }
                text: cell.display
                elide: Text.ElideRight
                font.pixelSize: cell.column === 0 ? 11 : 13
                horizontalAlignment: cell.column === 0 ? Text.AlignHCenter : Text.AlignLeft
                color: cell.column === 0
                    ? (cell.selected ? Theme.textCellSelected : Theme.textSecondary)
                    : (cell.selected ? Theme.textCellSelected : Theme.textCell)
                wrapMode: Text.NoWrap
            }

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width; height: 1
                color: Theme.borderSubtle
            }

            MouseArea {
                id: cellMouse
                anchors.fill: parent
                hoverEnabled: true
                onClicked: {
                    root._selectedRow = cell.row
                    tableView.selectionModel.setCurrentIndex(
                        tableView.model.index(cell.row, cell.column),
                        ItemSelectionModel.ClearAndSelect | ItemSelectionModel.Rows
                    )
                    root.rowClicked(cell.row)
                }
            }
        }
    }

    ScrollBar {
        id: scrollBar
        anchors.top: header.bottom
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        policy: ScrollBar.AsNeeded
    }
}
