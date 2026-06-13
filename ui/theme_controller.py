"""
ThemeController — QObject exposed to QML as `themeCtrl`.

Call themeCtrl.setTheme("Cool Tint") from QML to switch themes at runtime.
The controller updates both the QML context property `Theme` and the app QPalette.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Slot

from ui.theme import THEMES, build_palette


class ThemeController(QObject):
    def __init__(self, engine_context, app, ctrl, on_theme_changed=None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._ctx = engine_context
        self._app = app
        self._ctrl = ctrl
        self._on_theme_changed = on_theme_changed  # optional callable to notify ViewModel

    @Slot(str)
    def setTheme(self, name: str) -> None:
        theme = THEMES.get(name)
        if not theme:
            return
        self._ctrl.save_preferred_theme(name)
        self._ctx.setContextProperty("Theme", theme)
        self._app.setPalette(build_palette(theme))
        if self._on_theme_changed:
            self._on_theme_changed()
