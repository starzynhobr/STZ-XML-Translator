"""Standalone GUI QA: uv run python -m tests.qml_parity_check.

Uses synthetic data, no network/config writes; captures go to the OS temp folder.
Run separately from pytest so QApplication owns the process.
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "FluentWinUI3")

from PySide6.QtCore import (  # noqa: E402
    Q_ARG,
    QMetaObject,  # noqa: E402
    QObject,
    QPointF,
    Qt,
    QUrl,
)
from PySide6.QtGui import QFont, QFontDatabase  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickItem, QQuickWindow  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.project import TranslationEntry  # noqa: E402
from core.updater import ReleaseInfo  # noqa: E402
from ui.theme import THEMES, build_palette  # noqa: E402
from ui.theme_controller import ThemeController  # noqa: E402
from ui.viewmodel import AppViewModel  # noqa: E402


def settle(app):
    for _ in range(8):
        app.processEvents()
    QTest.qWait(100)


def invoke(obj, name, value=None):
    args = () if value is None else (Q_ARG("QVariant", value),)
    assert QMetaObject.invokeMethod(obj, name, Qt.DirectConnection, *args), name


def main():
    app = QApplication([])
    for font in ("segoeui.ttf", "seguisym.ttf", "meiryo.ttc"):
        path = Path("C:/Windows/Fonts") / font
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont("Segoe UI", 10))
    output = Path(tempfile.mkdtemp(prefix="stz-uir006-"))
    scenarios = 0
    for shell in ("main.qml", "ModernMain.qml"):
        with patch("core.app_controller.AppController._load_config"):
            vm = AppViewModel()
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda values: warnings.extend(str(v.toString()) for v in values))
        ctx = engine.rootContext()
        ctx.setContextProperty("vm", vm)
        ctx.setContextProperty("Theme", THEMES["Windows Fluent"])
        controller = ThemeController(ctx, app, vm._ctrl, vm.themeChanged.emit)
        ctx.setContextProperty("themeCtrl", controller)
        engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1] / "ui" / shell)))
        assert engine.rootObjects(), warnings
        root = engine.rootObjects()[0]
        settle(app)
        for loaded in (False, True):
            entries = {
                f"/hero[{i}]/bio": TranslationEntry(
                    f"/hero[{i}]/bio", f"Hero {i} protects the city and supports the Avengers.",
                    translation="Protege a cidade." if i % 3 == 0 else "",
                    status="error" if i == 4 else "confirmed" if i == 3 else "translated" if i % 3 == 0 else "pending",
                    error_code="rate_limit" if i == 4 else "",
                    source_tag="bio", context={"dispName": f"Hero {i}"},
                ) for i in range(1, 121)
            } if loaded else {}
            if loaded and len(sys.argv) > 1:
                ok, error = vm._ctrl.project.load(sys.argv[1], "action", ["dispName"])
                assert ok, error
                entries = vm._ctrl.project.entries
            vm._ctrl.project.entries = entries
            vm._table.refresh_all(entries)
            vm.entryCountChanged.emit(len(entries))
            vm.progressChanged.emit(*vm._ctrl.project.stats())
            for theme in ("Windows Fluent", "Light Azure"):
                ctx.setContextProperty("Theme", THEMES[theme])
                app.setPalette(build_palette(THEMES[theme]))
                sizes = ((900, 620), (1024, 620), (1280, 760), (1600, 900)) \
                    if shell == "ModernMain.qml" else ((1024, 620), (1280, 760), (1600, 900))
                for width, height in sizes:
                    root.resize(width, height)
                    settle(app)
                    if shell == "ModernMain.qml":
                        for name in ("globalActionRegion", "contentRegion", "editorRegion", "activityRegion",
                                     "topBarLoadButton", "topBarTranslateButton", "topBarExportButton",
                                     "previousEntryButton", "nextEntryButton"):
                            item = root.findChild(QQuickItem, name)
                            assert item is not None, name
                            point = item.mapToScene(QPointF(0, 0))
                            assert point.x() >= -1 and point.x() + item.width() <= width + 1, (
                                shell, theme, width, name, point.x(), item.width())
                        command_bar = root.findChild(QQuickItem, "tableCommandRegion")
                        search_field = root.findChild(QQuickItem, "tableSearchField")
                        bar_center = command_bar.mapToScene(
                            QPointF(0, command_bar.height() / 2)
                        ).y()
                        search_center = search_field.mapToScene(
                            QPointF(0, search_field.height() / 2)
                        ).y()
                        assert abs(bar_center - search_center) <= 1, (
                            shell, theme, width, bar_center, search_center
                        )
                        table = root.findChild(QObject, "tableRegion")
                        if loaded:
                            invoke(table, "selectSingleRow", 3)
                    settle(app)
                    capture = output / f"{shell}-{theme}-{width}-{'loaded' if loaded else 'empty'}.png"
                    assert QQuickWindow.grabWindow(root).save(str(capture))
                    scenarios += 1
                    if width == 1280:
                        selector = root.findChild(QQuickItem, "statusFilterSelector")
                        point = selector.mapToScene(QPointF(selector.width() / 2, selector.height() / 2))
                        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, point.toPoint())
                        settle(app)
                        assert QQuickWindow.grabWindow(root).save(str(output / f"{shell}-{theme}-popup.png"))
                        QTest.keyClick(root, Qt.Key_Escape)
                        settle(app)
                        if shell == "ModernMain.qml" and not loaded:
                            target = root.findChild(QQuickItem, "topBarTargetLocale")
                            chevron = target.findChild(QQuickItem, "comboChevron")
                            assert chevron is not None
                            closed_position = chevron.mapToScene(QPointF(0, 0))
                            center = target.mapToScene(QPointF(target.width() / 2, target.height() / 2))
                            QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, center.toPoint())
                            settle(app)
                            popup_list = root.findChild(QQuickItem, "comboPopupList")
                            popup = root.findChild(QObject, "comboPopup")
                            assert popup_list.height() == popup.property("height") - 8
                            assert popup_list.property("contentY") % 36 == 0
                            open_position = chevron.mapToScene(QPointF(0, 0))
                            assert open_position == closed_position
                            assert QQuickWindow.grabWindow(root).save(
                                str(output / f"ModernMain.qml-{theme}-language-open.png")
                            )
                            QTest.keyClick(root, Qt.Key_Escape)
                            settle(app)
                            assert chevron.mapToScene(QPointF(0, 0)) == closed_position
                        if shell == "ModernMain.qml" and theme == "Light Azure" and loaded:
                            terms = {f"Term {i}": f"Tradução {i}" for i in range(20)}
                            with patch("core.tradutor_api.carregar_glossario", return_value=terms):
                                invoke(root.findChild(QObject, "editorRegion"), "openGlossary")
                                QTest.qWait(250)
                                settle(app)
                                glossary_list = root.findChild(QQuickItem, "glossaryTermList")
                                assert glossary_list is not None
                                assert 250 <= glossary_list.height() <= 312, (
                                    glossary_list.height(), glossary_list.property("count"),
                                    root.findChild(QObject, "glossaryDialog").property("visible"),
                                )
                                assert QQuickWindow.grabWindow(root).save(
                                    str(output / "ModernMain.qml-Light Azure-glossary.png")
                                )
                                QTest.keyClick(root, Qt.Key_Escape)
                                settle(app)
                            with patch("core.tradutor_api.carregar_glossario", return_value={
                                "Hammerhead": "Cabeça de Martelo", "Roxxon": "Roxxon",
                            }):
                                invoke(root.findChild(QObject, "editorRegion"), "openGlossary")
                                QTest.qWait(250)
                                settle(app)
                                assert glossary_list.property("count") == 2
                                assert 80 <= glossary_list.height() <= 100
                                assert QQuickWindow.grabWindow(root).save(
                                    str(output / "ModernMain.qml-Light Azure-glossary-short.png")
                                )
                                QTest.keyClick(root, Qt.Key_Escape)
                                settle(app)
                    if loaded:
                        selector = root.findChild(QObject, "statusFilterSelector")
                        assert selector is not None
                        assert QMetaObject.invokeMethod(selector, "activated", Qt.DirectConnection, Q_ARG("int", 5))
                        settle(app)
                        assert vm.filteredEntryCount == sum(e.status == "error" for e in entries.values())
                        assert root.property("selectedXpath") == ""
                        filtered = output / f"{shell}-{theme}-{width}-filtered.png"
                        assert QQuickWindow.grabWindow(root).save(str(filtered))
                        scenarios += 1
                        vm.setStatusFilter("all")
                        settle(app)

        vm._update_release = ReleaseInfo(
            version="1.5.0",
            tag_name="v1.5.0",
            notes="Update QA",
            page_url="https://github.com/StarzynhoBR/STZ-XML-Translator/releases/tag/v1.5.0",
            installer_name="STZXMLTranslator-Setup-1.5.0.exe",
            download_url=(
                "https://github.com/StarzynhoBR/STZ-XML-Translator/"
                "releases/download/v1.5.0/STZXMLTranslator-Setup-1.5.0.exe"
            ),
            sha256="a" * 64,
            size=100,
        )
        vm._update_status = "available"
        vm.updateChanged.emit()
        for theme in ("Windows Fluent", "Light Azure"):
            ctx.setContextProperty("Theme", THEMES[theme])
            for width in (1024, 1600):
                root.resize(width, 760)
                settle(app)
                banner = root.findChild(QQuickItem, "updateBanner")
                primary = root.findChild(QQuickItem, "updatePrimaryButton")
                assert banner is not None and banner.isVisible()
                assert primary is not None and primary.isVisible()
                for item in (banner, primary):
                    point = item.mapToScene(QPointF(0, 0))
                    assert point.x() >= -1 and point.x() + item.width() <= width + 1
                update_capture = output / f"{shell}-{theme}-{width}-update.png"
                assert QQuickWindow.grabWindow(root).save(str(update_capture))
                scenarios += 1
        vm._update_status = "idle"
        vm._update_release = None
        vm.updateChanged.emit()
        settle(app)
        if shell == "ModernMain.qml":
            target_selector = root.findChild(QObject, "topBarTargetLocale")
            assert target_selector.property("count") == 9
            paths = list(vm._ctrl.project.entries)
            table = root.findChild(QObject, "tableRegion")
            view = root.findChild(QQuickItem, "translationTableView")
            view.setProperty("contentY", 0)
            settle(app)

            def click_table_row(row, modifiers=Qt.NoModifier, window=root):
                point = view.mapToScene(QPointF(100, row * 28 + 14))
                QTest.mouseClick(window, Qt.LeftButton, modifiers, point.toPoint())
                settle(app)

            click_table_row(1)
            assert vm.selectedCount == 1
            click_table_row(3, Qt.ControlModifier)
            assert vm.selectedCount == 2
            click_table_row(5, Qt.ShiftModifier)
            assert vm.selectedCount == 3
            invoke(table, "clearSelection")

            invoke(table, "selectSingleRow", 1)
            invoke(root.findChild(QObject, "nextEntryButton"), "click")
            assert root.property("selectedXpath") == paths[2]
            invoke(root.findChild(QObject, "previousEntryButton"), "click")
            assert root.property("selectedXpath") == paths[1]
            view.forceActiveFocus()
            QTest.keyClick(root, Qt.Key_Down)
            settle(app)
            assert root.property("selectedXpath") == paths[2]
            QTest.keyClick(root, Qt.Key_Return)
            settle(app)
            editor = root.findChild(QQuickItem, "translationEditor")
            assert editor.hasActiveFocus()
            flick = root.findChild(QQuickItem, "editorFlick")
            editor_y = editor.mapToItem(flick, QPointF(0, 0)).y()
            assert 0 <= editor_y < flick.height(), editor_y
            activity = root.findChild(QObject, "activityRegion")
            activity.setProperty("expanded", True)
            settle(app)
            assert activity.property("height") == 136
            activity.setProperty("expanded", False)
            settle(app)
            assert activity.property("height") == 34
            toggle = root.findChild(QObject, "providerOptionsToggle")
            invoke(toggle, "click")
            settle(app)
            assert root.findChild(QQuickItem, "providerOptions").isVisible()
            invoke(toggle, "click")
            settle(app)
            assert not root.findChild(QQuickItem, "providerOptions").isVisible()
            for locale in ("pt_BR", "en_US", "es_ES", "fr_FR", "ja_JP"):
                vm._i18n.load_language(locale)
                vm.languageChanged.emit()
                root.resize(900, 620)
                settle(app)
                for name in ("topBarExportButton", "nextEntryButton", "tableCommandRegion"):
                    item = root.findChild(QQuickItem, name)
                    assert item.mapToScene(QPointF(0, 0)).x() + item.width() <= 901
        else:
            target_selector = root.findChild(QObject, "sidebarTargetLocale")
            assert target_selector.property("count") == 9
        assert not warnings, warnings[:10]
        root.close()
        del root, engine
        settle(app)
    print(f"PASS: {scenarios} captures; two shells, two themes, responsive sizes, empty/loaded/filtered/update; navigation/focus/log/filter.")
    print(output)


if __name__ == "__main__":
    main()
