"""
Tests for the theme system (ui/theme.py and ui/theme_controller.py).

These tests exist to catch:
  - Missing or extra tokens in one theme vs the others
  - Invalid color format (non-hex values break QML Color bindings silently)
  - DEFAULT_THEME not matching a key in THEMES
  - ThemeController no-op on unknown theme name
  - build_palette not raising (QPalette construction path)
  - AppController preferred_theme persistence
"""

import re
from unittest.mock import MagicMock, call, patch

import pytest

from ui.theme import DEFAULT_THEME, THEME, THEMES, _dark_base

# ── helpers ────────────────────────────────────────────────────────────────

HEX_RE = re.compile(r"^#[0-9a-fA-F]{3}$|^#[0-9a-fA-F]{6}$|^#[0-9a-fA-F]{8}$")


def _is_hex_color(value: str) -> bool:
    return bool(HEX_RE.match(value))


# ── token structure ────────────────────────────────────────────────────────

class TestThemeStructure:
    def test_default_theme_exists_in_themes(self):
        assert DEFAULT_THEME in THEMES

    def test_theme_alias_matches_default(self):
        assert THEME is THEMES[DEFAULT_THEME]

    def test_all_themes_have_identical_key_sets(self):
        reference_keys = set(THEMES[DEFAULT_THEME].keys())
        for name, theme in THEMES.items():
            assert set(theme.keys()) == reference_keys, (
                f"Theme '{name}' has different keys.\n"
                f"  Missing: {reference_keys - set(theme.keys())}\n"
                f"  Extra:   {set(theme.keys()) - reference_keys}"
            )

    def test_minimum_token_count(self):
        # Guard against accidentally stripping tokens in _dark_base refactors
        assert len(THEMES[DEFAULT_THEME]) >= 30

    def test_expected_tokens_present(self):
        required = [
            "bgBase", "bgSurface1", "bgSurface2", "bgSurface3",
            "bgInput", "borderInput", "borderFocus",
            "textInput", "textPlaceholder", "textPrimary", "textSecondary", "textDisabled",
            "primary", "primaryHover", "onPrimary",
            "success", "onSuccess", "danger", "onDanger",
            "rowDone", "rowDoneHover", "rowSelected", "rowDefaultHover",
            "rowTranslating", "rowTranslatingHover",
            "borderSubtle", "borderModerate",
            "bgHeader", "borderHeader", "textHeader",
            "textCell", "textCellSelected",
            "warning", "dangerSubtle",
        ]
        theme = THEMES[DEFAULT_THEME]
        for token in required:
            assert token in theme, f"Required token '{token}' missing from {DEFAULT_THEME}"

    @pytest.mark.parametrize("name", list(THEMES.keys()))
    def test_all_values_are_hex_colors(self, name):
        for token, value in THEMES[name].items():
            assert _is_hex_color(value), (
                f"Theme '{name}', token '{token}': '{value}' is not a valid hex color"
            )

    def test_five_themes_defined(self):
        assert len(THEMES) == 5

    def test_expected_theme_names(self):
        assert "Windows Fluent" in THEMES
        assert "Neutral Deep" in THEMES
        assert "Cool Tint" in THEMES
        assert "Light Azure" in THEMES
        assert "Beige Café" in THEMES


# ── surface progression ────────────────────────────────────────────────────

_DARK_THEMES = {"Windows Fluent", "Neutral Deep", "Cool Tint"}
_LIGHT_THEMES = {"Light Azure", "Beige Café"}


class TestSurfaceLevels:
    """
    Dark themes: surfaces ascend in luminance (bgBase darkest, bgSurface3 lightest).
    Light themes: surfaces descend in luminance (bgBase lightest, bgSurface3 most tinted).
    Either way the four values must be strictly monotonic.
    """

    @staticmethod
    def _luminance(hex_color: str) -> int:
        """Rough luminance proxy: sum of RGB channels."""
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return r + g + b

    @pytest.mark.parametrize("name", list(THEMES.keys()))
    def test_surface_levels_are_monotonic(self, name):
        t = THEMES[name]
        lum = self._luminance
        lums = [lum(t["bgBase"]), lum(t["bgSurface1"]),
                lum(t["bgSurface2"]), lum(t["bgSurface3"])]
        ascending  = all(lums[i] <= lums[i + 1] for i in range(3))
        descending = all(lums[i] >= lums[i + 1] for i in range(3))
        assert ascending or descending, (
            f"Theme '{name}': surface luminance values are not monotonically ordered: {lums}"
        )

    @pytest.mark.parametrize("name", list(_DARK_THEMES))
    def test_dark_surfaces_ascend(self, name):
        t = THEMES[name]
        lum = self._luminance
        assert lum(t["bgBase"]) <= lum(t["bgSurface1"]), \
            f"{name}: bgBase should be darker than bgSurface1"

    @pytest.mark.parametrize("name", list(_LIGHT_THEMES))
    def test_light_base_is_lightest(self, name):
        t = THEMES[name]
        lum = self._luminance
        assert lum(t["bgBase"]) >= lum(t["bgSurface3"]), \
            f"{name}: bgBase (lightest) should have higher luminance than bgSurface3"


# ── build_palette ──────────────────────────────────────────────────────────

class TestBuildPalette:
    def test_returns_qpalette_without_raising(self):
        from ui.theme import build_palette
        palette = build_palette(THEMES[DEFAULT_THEME])
        from PySide6.QtGui import QPalette
        assert isinstance(palette, QPalette)

    @pytest.mark.parametrize("name", list(THEMES.keys()))
    def test_all_themes_build_palette(self, name):
        from ui.theme import build_palette
        palette = build_palette(THEMES[name])
        assert palette is not None

    def test_window_color_matches_bg_base(self):
        from PySide6.QtGui import QColor, QPalette

        from ui.theme import build_palette
        palette = build_palette(THEMES[DEFAULT_THEME])
        bg_base = THEMES[DEFAULT_THEME]["bgBase"]
        window_color = palette.color(QPalette.ColorRole.Window)
        assert window_color == QColor(bg_base)

    def test_highlight_color_matches_primary(self):
        from PySide6.QtGui import QColor, QPalette

        from ui.theme import build_palette
        palette = build_palette(THEMES[DEFAULT_THEME])
        primary = THEMES[DEFAULT_THEME]["primary"]
        highlight = palette.color(QPalette.ColorRole.Highlight)
        assert highlight == QColor(primary)


# ── ThemeController ────────────────────────────────────────────────────────

class TestThemeController:
    def _make_controller(self, on_changed=None):
        from ui.theme_controller import ThemeController
        ctx = MagicMock()
        app = MagicMock()
        ctrl = MagicMock()
        return ThemeController(ctx, app, ctrl, on_theme_changed=on_changed), ctx, app, ctrl

    def test_set_valid_theme_updates_context_property(self):
        tc, ctx, app, ctrl = self._make_controller()
        tc.setTheme("Neutral Deep")
        ctx.setContextProperty.assert_called_once_with("Theme", THEMES["Neutral Deep"])

    def test_set_valid_theme_updates_palette(self):
        from ui.theme import build_palette
        tc, ctx, app, ctrl = self._make_controller()
        tc.setTheme("Cool Tint")
        app.setPalette.assert_called_once()

    def test_set_valid_theme_saves_preference(self):
        tc, ctx, app, ctrl = self._make_controller()
        tc.setTheme("Neutral Deep")
        ctrl.save_preferred_theme.assert_called_once_with("Neutral Deep")

    def test_set_unknown_theme_is_noop(self):
        tc, ctx, app, ctrl = self._make_controller()
        tc.setTheme("NonExistentTheme")
        ctx.setContextProperty.assert_not_called()
        app.setPalette.assert_not_called()
        ctrl.save_preferred_theme.assert_not_called()

    def test_on_theme_changed_callback_fires(self):
        fired = []
        tc, ctx, app, ctrl = self._make_controller(on_changed=lambda: fired.append(1))
        tc.setTheme("Cool Tint")
        assert len(fired) == 1

    def test_no_callback_does_not_raise(self):
        tc, ctx, app, ctrl = self._make_controller(on_changed=None)
        tc.setTheme("Windows Fluent")  # should not raise


# ── _dark_base contract ────────────────────────────────────────────────────

class TestDarkBase:
    def test_returns_dict(self):
        result = _dark_base(
            bg_base="#111111", bg1="#222222", bg2="#333333", bg3="#444444",
            bg_input="#333333", border_input="#555555", border_focus="#0078d4",
            primary="#0078d4", primary_hover="#1a8be0",
            row_done="#1a3d2a", row_done_hover="#235c3e", row_default_hover="#2e2e2e",
            row_translating="#383838", row_translating_hover="#4a4a4a",
            border_subtle="#2a2a2a", border_moderate="#383838",
            bg_header="#333333", border_header="#3a3a3a",
        )
        assert isinstance(result, dict)

    def test_primary_propagates_to_row_selected(self):
        result = _dark_base(
            bg_base="#111111", bg1="#222222", bg2="#333333", bg3="#444444",
            bg_input="#333333", border_input="#555555", border_focus="#0078d4",
            primary="#ff0000", primary_hover="#ff3333",
            row_done="#1a3d2a", row_done_hover="#235c3e", row_default_hover="#2e2e2e",
            row_translating="#383838", row_translating_hover="#4a4a4a",
            border_subtle="#2a2a2a", border_moderate="#383838",
            bg_header="#333333", border_header="#3a3a3a",
        )
        assert result["rowSelected"] == "#ff0000"

    def test_on_color_tokens_are_universal(self):
        """onPrimary / onSuccess / onDanger must be #ffffff in every theme
        (these are always text-on-colored-background regardless of light/dark)."""
        universal = ["onPrimary", "onSuccess", "onDanger"]
        for token in universal:
            values = {name: theme[token] for name, theme in THEMES.items()}
            unique = set(values.values())
            assert unique == {"#ffffff"}, (
                f"Token '{token}' should be '#ffffff' in every theme but got: {values}"
            )

    def test_semantic_action_colors_shared_across_families(self):
        """success / danger are the same value in both dark and light themes."""
        for token in ["success", "danger"]:
            values = {name: theme[token] for name, theme in THEMES.items()}
            unique = set(values.values())
            assert len(unique) == 1, (
                f"Token '{token}' should be the same across all themes but differs: {values}"
            )

    def test_dark_themes_share_text_tokens(self):
        """All dark themes use the same text/input color tokens."""
        shared = ["textInput", "textPrimary", "textSecondary", "textDisabled"]
        for token in shared:
            values = {name: THEMES[name][token] for name in _DARK_THEMES}
            unique = set(values.values())
            assert len(unique) == 1, (
                f"[dark] Token '{token}' should be shared but differs: {values}"
            )

    def test_light_themes_have_dark_text(self):
        """Light themes must have textPrimary with low luminance (dark on light)."""
        for name in _LIGHT_THEMES:
            hex_c = THEMES[name]["textPrimary"].lstrip("#")
            r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
            luminance_sum = r + g + b
            assert luminance_sum < 300, (
                f"Theme '{name}': textPrimary '{THEMES[name]['textPrimary']}' seems too light "
                f"for a light theme (RGB sum = {luminance_sum})"
            )

    def test_dark_themes_have_light_text(self):
        """Dark themes must have textPrimary with high luminance (light on dark)."""
        for name in _DARK_THEMES:
            hex_c = THEMES[name]["textPrimary"].lstrip("#")
            r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
            luminance_sum = r + g + b
            assert luminance_sum > 400, (
                f"Theme '{name}': textPrimary '{THEMES[name]['textPrimary']}' seems too dark "
                f"for a dark theme (RGB sum = {luminance_sum})"
            )
