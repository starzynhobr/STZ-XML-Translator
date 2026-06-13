"""
Entry point for STZ XML Translator (PySide6 + QML).
Run: python main_qt.py
"""

# nuitka-project: --standalone
# nuitka-project: --enable-plugin=pyside6
# nuitka-project: --include-qt-plugins=qml
# nuitka-project: --msvc=latest
# nuitka-project: --windows-console-mode=disable
# nuitka-project: --lto=no
# nuitka-project: --python-flag=no_docstrings
# nuitka-project: --noinclude-pytest-mode=nofollow
# nuitka-project: --noinclude-unittest-mode=nofollow
# nuitka-project: --include-data-dir=ui=ui
# nuitka-project: --include-data-dir=locales=locales
# nuitka-project: --include-data-dir=assets=assets
# nuitka-project: --include-data-files=scripts/glossario.json=scripts/glossario.json
# nuitka-project: --nofollow-import-to=tests
# nuitka-project: --nofollow-import-to=*.tests
# nuitka-project: --nofollow-import-to=ruff
# nuitka-project: --nofollow-import-to=pygments
# nuitka-project: --assume-yes-for-downloads
# nuitka-project: --output-filename=STZXMLTranslator.exe
# nuitka-project: --output-dir=dist
# nuitka-project: --windows-icon-from-ico=assets/icon.ico
# nuitka-project: --company-name=STZ XML Translator
# nuitka-project: --product-name=STZ XML Translator
# nuitka-project: --file-description=STZ XML Translator -- XML localization tool for game modders
import os
import sys

# Force FluentWinUI3 dark theme before importing Qt
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "FluentWinUI3")
os.environ.setdefault("QT_QUICK_CONTROLS_FLUENTWINUI3_THEME", "Dark")

# On Windows, request dark-mode native decorations and menus (requires Win10 1809+).
# darkmode=2 = force dark, regardless of the OS-wide light/dark setting.
if sys.platform == "win32":
    _plat = os.environ.get("QT_QPA_PLATFORM", "")
    if "darkmode" not in _plat:
        os.environ["QT_QPA_PLATFORM"] = (
            (_plat + ":darkmode=2") if ("windows" in _plat) else "windows:darkmode=2"
        )

# High-DPI scaling (Qt 6 handles this automatically, but ensure it's on)
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")


def _log_qml_warnings(warnings) -> None:
    """Module-level handler — avoids closure reference to engine during teardown."""
    for w in warnings:
        print(
            f"QML [{w.messageType()}] {w.url().toString()}:{w.line()} — {w.description()}",
            file=sys.stderr,
        )


def _resolve(relative: str) -> str:
    """Resolve a path relative to this file, bundled or not."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, relative)
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative)


def _apply_dark_palette(app) -> None:
    """
    Set a dark QPalette on the QApplication so that native/system widgets
    (context menus, tooltips, scroll bars) respect the dark theme instead
    of inheriting the OS light palette and rendering white-on-white.
    """
    from PySide6.QtGui import QColor, QPalette

    p = QPalette()

    def c(hex_: str) -> QColor:
        return QColor(hex_)

    # Active / Normal group
    p.setColor(QPalette.ColorRole.Window,          c("#181818"))
    p.setColor(QPalette.ColorRole.WindowText,      c("#f0f0f0"))
    p.setColor(QPalette.ColorRole.Base,            c("#2b2b2b"))
    p.setColor(QPalette.ColorRole.AlternateBase,   c("#232323"))
    p.setColor(QPalette.ColorRole.Text,            c("#f0f0f0"))
    p.setColor(QPalette.ColorRole.BrightText,      c("#ffffff"))
    p.setColor(QPalette.ColorRole.Button,          c("#3a3a3a"))
    p.setColor(QPalette.ColorRole.ButtonText,      c("#f0f0f0"))
    p.setColor(QPalette.ColorRole.Highlight,       c("#0078d4"))
    p.setColor(QPalette.ColorRole.HighlightedText, c("#ffffff"))
    p.setColor(QPalette.ColorRole.ToolTipBase,     c("#2b2b2b"))
    p.setColor(QPalette.ColorRole.ToolTipText,     c("#f0f0f0"))
    p.setColor(QPalette.ColorRole.PlaceholderText, c("#666666"))
    p.setColor(QPalette.ColorRole.Link,            c("#0078d4"))
    p.setColor(QPalette.ColorRole.LinkVisited,     c("#5c9fd4"))
    # Borders / shadows
    p.setColor(QPalette.ColorRole.Light,           c("#3a3a3a"))
    p.setColor(QPalette.ColorRole.Midlight,        c("#2f2f2f"))
    p.setColor(QPalette.ColorRole.Mid,             c("#252525"))
    p.setColor(QPalette.ColorRole.Dark,            c("#181818"))
    p.setColor(QPalette.ColorRole.Shadow,          c("#000000"))

    # Disabled group — dimmed versions of the above
    for role, hex_ in [
        (QPalette.ColorRole.WindowText, "#666666"),
        (QPalette.ColorRole.Text,       "#666666"),
        (QPalette.ColorRole.ButtonText, "#666666"),
        (QPalette.ColorRole.Base,       "#1e1e1e"),
    ]:
        p.setColor(QPalette.ColorGroup.Disabled, role, c(hex_))

    app.setPalette(p)


def main() -> int:
    from PySide6.QtGui import QIcon
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("STZ XML Translator")
    app.setApplicationVersion("1.2.0")
    app.setOrganizationName("GameXMLTranslator")

    # Dark palette is applied after loading the initial theme below.

    # QSS fallback: style QWidget-based menus/tooltips that may bypass QPalette.
    app.setStyleSheet("""
        QMenu {
            background-color: #2b2b2b;
            color: #f0f0f0;
            border: 1px solid #444444;
            padding: 2px;
        }
        QMenu::item {
            padding: 6px 28px 6px 12px;
            border-radius: 3px;
        }
        QMenu::item:selected {
            background-color: #0078d4;
            color: #ffffff;
        }
        QMenu::item:disabled {
            color: #666666;
        }
        QMenu::separator {
            height: 1px;
            background-color: #444444;
            margin: 3px 8px;
        }
        QToolTip {
            background-color: #2b2b2b;
            color: #f0f0f0;
            border: 1px solid #555555;
            padding: 4px;
        }
    """)

    icon_path = _resolve(os.path.join("assets", "icon.ico"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Instantiate ViewModel before the engine so it's available to QML
    from ui.theme import DEFAULT_THEME, THEMES, build_palette
    from ui.theme_controller import ThemeController
    from ui.viewmodel import AppViewModel
    vm = AppViewModel()

    # Pick the saved theme (falls back to default if unknown)
    initial_theme_name = vm._ctrl.preferred_theme
    initial_theme = THEMES.get(initial_theme_name, THEMES[DEFAULT_THEME])
    app.setPalette(build_palette(initial_theme))

    engine = QQmlApplicationEngine()
    engine.warnings.connect(_log_qml_warnings)
    engine.rootContext().setContextProperty("vm", vm)
    engine.rootContext().setContextProperty("Theme", initial_theme)

    theme_ctrl = ThemeController(engine.rootContext(), app, vm._ctrl, vm.themeChanged.emit)
    engine.rootContext().setContextProperty("themeCtrl", theme_ctrl)

    # Add ui/ to QML import path so "components/Foo.qml" is found
    ui_dir = _resolve("ui")
    engine.addImportPath(ui_dir)

    qml_file = _resolve(os.path.join("ui", "main.qml"))
    print(f"Loading QML: {qml_file}", file=sys.stderr)
    engine.load(qml_file)

    if not engine.rootObjects():
        print("ERROR: Failed to load main.qml — check QML warnings above", file=sys.stderr)
        return 1

    result = app.exec()

    # Explicit teardown order: destroy the QML engine FIRST (while vm is still alive),
    # then let vm be garbage-collected. This prevents "Cannot read property of null"
    # errors that occur when QML bindings are evaluated during engine destruction
    # after the Python ViewModel has already been collected.
    del engine

    return result


if __name__ == "__main__":
    sys.exit(main())
