"""
Color design tokens for the QML UI.
Exposed to QML as the global `Theme` context property.
Access any token in QML with: Theme.tokenName

Dark themes (surfaces: low → high luminance):
  - Windows Fluent  (default, Windows 11 style)
  - Neutral Deep    (deeper neutral blacks, less elevated)
  - Cool Tint       (GitHub dark, blue-tinted surfaces)

Light themes (surfaces: high → low luminance):
  - Light Azure     (white base, Windows blue accent)
  - Beige Café      (warm paper tones, coffee accent)
"""

DEFAULT_THEME = "Windows Fluent"


def _dark_base(
    bg_base: str, bg1: str, bg2: str, bg3: str,
    bg_input: str, border_input: str, border_focus: str,
    primary: str, primary_hover: str,
    row_done: str, row_done_hover: str, row_default_hover: str,
    row_translating: str, row_translating_hover: str,
    border_subtle: str, border_moderate: str,
    bg_header: str, border_header: str,
) -> dict[str, str]:
    """Build a complete theme dict from variable surface tokens; semantic tokens are shared."""
    return {
        # ── Surfaces (increasing elevation) ──────────────────────────────
        "bgBase":     bg_base,
        "bgSurface1": bg1,
        "bgSurface2": bg2,
        "bgSurface3": bg3,

        # ── Inputs — explicit override required for FluentWinUI3 ─────────
        "bgInput":         bg_input,
        "borderInput":     border_input,
        "borderFocus":     border_focus,
        "textInput":       "#f0f0f0",
        "textPlaceholder": "#666666",

        # ── Text ──────────────────────────────────────────────────────────
        "textPrimary":   "#f0f0f0",
        "textSecondary": "#b0b0b0",
        "textDisabled":  "#666666",
        "textLog":       "#8fbc8f",

        # ── Semantic colors ───────────────────────────────────────────────
        "primary":      primary,
        "primaryHover": primary_hover,
        "onPrimary":    "#ffffff",

        "secondary":    "#3a3a3a",
        "onSecondary":  "#f0f0f0",

        "success":      "#107c10",
        "successHover": "#1a9a1a",
        "onSuccess":    "#ffffff",

        "danger":       "#c42b1c",
        "dangerHover":  "#a32518",
        "onDanger":     "#ffffff",

        "warning":      "#e0a030",
        "dangerSubtle": "#3d1a1a",

        # ── Table row status colors ───────────────────────────────────────
        "rowDone":             row_done,
        "rowDoneHover":        row_done_hover,
        "rowSelected":         primary,
        "rowTranslating":      row_translating,
        "rowTranslatingHover": row_translating_hover,
        "rowDefaultHover":     row_default_hover,

        # ── Borders and dividers ──────────────────────────────────────────
        "borderSubtle":   border_subtle,
        "borderModerate": border_moderate,

        # ── Table header ──────────────────────────────────────────────────
        "bgHeader":     bg_header,
        "borderHeader": border_header,
        "textHeader":   "#cccccc",

        # ── Table cells ───────────────────────────────────────────────────
        "textCell":         "#e0e0e0",
        "textCellSelected": "#ffffff",
    }


def _light_base(
    bg_base: str, bg1: str, bg2: str, bg3: str,
    bg_input: str, border_input: str, border_focus: str,
    primary: str, primary_hover: str,
    row_done: str, row_done_hover: str, row_default_hover: str,
    row_translating: str, row_translating_hover: str,
    border_subtle: str, border_moderate: str,
    bg_header: str, border_header: str,
    text_primary: str, text_secondary: str, text_disabled: str,
    text_header: str, text_log: str, danger_subtle: str,
) -> dict[str, str]:
    """Build a complete light-theme dict from variable surface tokens."""
    return {
        # ── Surfaces (decreasing luminance with each elevation step) ──────
        "bgBase":     bg_base,
        "bgSurface1": bg1,
        "bgSurface2": bg2,
        "bgSurface3": bg3,

        # ── Inputs ────────────────────────────────────────────────────────
        "bgInput":         bg_input,
        "borderInput":     border_input,
        "borderFocus":     border_focus,
        "textInput":       text_primary,
        "textPlaceholder": text_secondary,

        # ── Text ──────────────────────────────────────────────────────────
        "textPrimary":   text_primary,
        "textSecondary": text_secondary,
        "textDisabled":  text_disabled,
        "textLog":       text_log,

        # ── Semantic colors ───────────────────────────────────────────────
        "primary":      primary,
        "primaryHover": primary_hover,
        "onPrimary":    "#ffffff",

        "secondary":    bg2,
        "onSecondary":  text_primary,

        "success":      "#107c10",
        "successHover": "#1a9a1a",
        "onSuccess":    "#ffffff",

        "danger":       "#c42b1c",
        "dangerHover":  "#a32518",
        "onDanger":     "#ffffff",

        # Darker warning token for sufficient contrast on light backgrounds
        "warning":      "#c07010",
        "dangerSubtle": danger_subtle,

        # ── Table row status colors ───────────────────────────────────────
        "rowDone":             row_done,
        "rowDoneHover":        row_done_hover,
        "rowSelected":         primary,
        "rowTranslating":      row_translating,
        "rowTranslatingHover": row_translating_hover,
        "rowDefaultHover":     row_default_hover,

        # ── Borders and dividers ──────────────────────────────────────────
        "borderSubtle":   border_subtle,
        "borderModerate": border_moderate,

        # ── Table header ──────────────────────────────────────────────────
        "bgHeader":     bg_header,
        "borderHeader": border_header,
        "textHeader":   text_header,

        # ── Table cells ───────────────────────────────────────────────────
        "textCell":         text_primary,
        "textCellSelected": "#ffffff",
    }


THEMES: dict[str, dict[str, str]] = {
    "Windows Fluent": _dark_base(
        bg_base="#181818", bg1="#232323", bg2="#2b2b2b", bg3="#333333",
        bg_input="#2b2b2b",   border_input="#555555", border_focus="#0078d4",
        primary="#0078d4",    primary_hover="#1a8be0",
        row_done="#1a3d2a",   row_done_hover="#235c3e",
        row_default_hover="#2e2e2e",
        row_translating="#383838", row_translating_hover="#4a4a4a",
        border_subtle="#2a2a2a",   border_moderate="#383838",
        bg_header="#2b2b2b",       border_header="#3a3a3a",
    ),
    "Neutral Deep": _dark_base(
        bg_base="#111111", bg1="#1c1c1c", bg2="#252525", bg3="#303030",
        bg_input="#252525",   border_input="#4a4a4a", border_focus="#0078d4",
        primary="#0078d4",    primary_hover="#1a8be0",
        row_done="#162d1e",   row_done_hover="#1e4229",
        row_default_hover="#272727",
        row_translating="#2e2e2e", row_translating_hover="#3d3d3d",
        border_subtle="#1e1e1e",   border_moderate="#2e2e2e",
        bg_header="#252525",       border_header="#323232",
    ),
    "Cool Tint": _dark_base(
        bg_base="#0d1117", bg1="#161b22", bg2="#21262d", bg3="#2d333b",
        bg_input="#21262d",   border_input="#30363d", border_focus="#388bfd",
        primary="#388bfd",    primary_hover="#58a6ff",
        row_done="#0d2318",   row_done_hover="#163320",
        row_default_hover="#1c2128",
        row_translating="#2d333b", row_translating_hover="#373e47",
        border_subtle="#21262d",   border_moderate="#30363d",
        bg_header="#21262d",       border_header="#30363d",
    ),

    # ── Light themes ──────────────────────────────────────────────────────
    "Light Azure": _light_base(
        bg_base="#ffffff",  bg1="#f0f4fa",  bg2="#e2ecf7",  bg3="#d0e1f4",
        bg_input="#ffffff", border_input="#a8c0e0", border_focus="#0078d4",
        primary="#0078d4",  primary_hover="#006cbf",
        row_done="#d4edda",       row_done_hover="#bde0c8",
        row_default_hover="#eaf1fb",
        row_translating="#e2ecf7",  row_translating_hover="#ccddf0",
        border_subtle="#dde8f5",    border_moderate="#c0d4ec",
        bg_header="#e2ecf7",        border_header="#c0d4ec",
        text_primary="#1a1a1a",     text_secondary="#4a4a4a",
        text_disabled="#9a9a9a",    text_header="#2a2a2a",
        text_log="#1a6e1a",         danger_subtle="#fde8e6",
    ),
    "Beige Café": _light_base(
        bg_base="#faf7f2",  bg1="#f0ebe2",  bg2="#e6ddd0",  bg3="#dacfbf",
        bg_input="#faf7f2", border_input="#c4b09a", border_focus="#8b5e3c",
        primary="#8b5e3c",  primary_hover="#7a5233",
        row_done="#d8eac8",        row_done_hover="#c5ddb0",
        row_default_hover="#ede7de",
        row_translating="#e6ddd0",   row_translating_hover="#d8d0c4",
        border_subtle="#e6ddd0",     border_moderate="#cfc0ad",
        bg_header="#e6ddd0",         border_header="#cfc0ad",
        text_primary="#2a1a0e",      text_secondary="#6a5040",
        text_disabled="#b0a090",     text_header="#4a3828",
        text_log="#4a6a2a",          danger_subtle="#f5e0da",
    ),
}

THEME: dict[str, str] = THEMES[DEFAULT_THEME]


def build_palette(theme: dict[str, str]):
    """Build a QPalette from a theme dict. PySide6 imported lazily to avoid startup overhead."""
    from PySide6.QtGui import QColor, QPalette

    p = QPalette()

    def c(key: str) -> QColor:
        return QColor(theme.get(key, "#000000"))

    p.setColor(QPalette.ColorRole.Window,          c("bgBase"))
    p.setColor(QPalette.ColorRole.WindowText,      c("textPrimary"))
    p.setColor(QPalette.ColorRole.Base,            c("bgSurface2"))
    p.setColor(QPalette.ColorRole.AlternateBase,   c("bgSurface1"))
    p.setColor(QPalette.ColorRole.Text,            c("textPrimary"))
    p.setColor(QPalette.ColorRole.BrightText,      QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.Button,          c("secondary"))
    p.setColor(QPalette.ColorRole.ButtonText,      c("onSecondary"))
    p.setColor(QPalette.ColorRole.Highlight,       c("primary"))
    p.setColor(QPalette.ColorRole.HighlightedText, c("onPrimary"))
    p.setColor(QPalette.ColorRole.ToolTipBase,     c("bgSurface2"))
    p.setColor(QPalette.ColorRole.ToolTipText,     c("textPrimary"))
    p.setColor(QPalette.ColorRole.PlaceholderText, c("textPlaceholder"))
    p.setColor(QPalette.ColorRole.Link,            c("primary"))
    p.setColor(QPalette.ColorRole.LinkVisited,     QColor("#5c9fd4"))
    p.setColor(QPalette.ColorRole.Light,           c("bgSurface3"))
    p.setColor(QPalette.ColorRole.Midlight,        c("bgSurface2"))
    p.setColor(QPalette.ColorRole.Mid,             c("bgSurface1"))
    p.setColor(QPalette.ColorRole.Dark,            c("bgBase"))
    p.setColor(QPalette.ColorRole.Shadow,          QColor("#000000"))

    for role, key in [
        (QPalette.ColorRole.WindowText, "textDisabled"),
        (QPalette.ColorRole.Text,       "textDisabled"),
        (QPalette.ColorRole.ButtonText, "textDisabled"),
        (QPalette.ColorRole.Base,       "bgBase"),
    ]:
        p.setColor(QPalette.ColorGroup.Disabled, role, c(key))

    return p
