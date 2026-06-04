"""
Entry point for the PySide6 + QML version of Game XML Translator.
Run: python main_qt.py

The CustomTkinter version (main.py) remains available as fallback.
"""
import os
import sys

# Force FluentWinUI3 dark theme before importing Qt
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "FluentWinUI3")
os.environ.setdefault("QT_QUICK_CONTROLS_FLUENTWINUI3_THEME", "Dark")

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


def main() -> int:
    from PySide6.QtGui import QIcon
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("Game XML Translator")
    app.setApplicationVersion("1.2.0")
    app.setOrganizationName("GameXMLTranslator")

    icon_path = _resolve(os.path.join("assets", "icon.ico"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Instantiate ViewModel before the engine so it's available to QML
    from ui.viewmodel import AppViewModel
    from ui.theme import THEME
    vm = AppViewModel()

    engine = QQmlApplicationEngine()
    engine.warnings.connect(_log_qml_warnings)
    engine.rootContext().setContextProperty("vm", vm)
    engine.rootContext().setContextProperty("Theme", THEME)

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
