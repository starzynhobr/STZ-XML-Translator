"""
Color design tokens for the QML UI.
Exposed to QML as the global `Theme` context property.
Access any token in QML with: Theme.tokenName
"""

THEME: dict[str, str] = {
    # ── Superfícies (elevação crescente) ─────────────────────────────
    "bgBase":     "#181818",   # window background (mais fundo)
    "bgSurface1": "#232323",   # painéis laterais
    "bgSurface2": "#2b2b2b",   # inputs, cards, headers de tabela
    "bgSurface3": "#333333",   # hover de linhas e controles

    # ── Inputs — override crítico do FluentWinUI3 ────────────────────
    # O FluentWinUI3 não herda palette.base para TextField/ComboBox;
    # é necessário sobrescrever background explicitamente.
    "bgInput":         "#2b2b2b",
    "borderInput":     "#555555",
    "borderFocus":     "#0078d4",
    "textInput":       "#f0f0f0",
    "textPlaceholder": "#666666",

    # ── Texto ─────────────────────────────────────────────────────────
    "textPrimary":   "#f0f0f0",
    "textSecondary": "#b0b0b0",   # era #aaaaaa — elevado para margem WCAG AA+
    "textDisabled":  "#666666",
    "textLog":       "#8fbc8f",   # terminal de log (verde suave)

    # ── Cores semânticas ──────────────────────────────────────────────
    "primary":      "#0078d4",   # Windows 11 blue
    "primaryHover": "#1a8be0",
    "onPrimary":    "#ffffff",

    "secondary":    "#3a3a3a",
    "onSecondary":  "#f0f0f0",

    "success":      "#107c10",   # botão Aprovar
    "successHover": "#1a9a1a",
    "onSuccess":    "#ffffff",

    "danger":       "#c42b1c",   # botão Cancelar
    "dangerHover":  "#a32518",
    "onDanger":     "#ffffff",

    # ── Status das linhas da tabela ───────────────────────────────────
    "rowDone":            "#1a3d2a",
    "rowDoneHover":       "#235c3e",
    "rowSelected":        "#0078d4",
    "rowTranslating":     "#383838",
    "rowTranslatingHover":"#4a4a4a",
    "rowDefaultHover":    "#2e2e2e",

    # ── Bordas e divisores ────────────────────────────────────────────
    "borderSubtle":   "#2a2a2a",   # divisor de linhas da tabela
    "borderModerate": "#383838",   # separadores de painel

    # ── Header da tabela ──────────────────────────────────────────────
    "bgHeader":     "#2b2b2b",
    "borderHeader": "#3a3a3a",
    "textHeader":   "#cccccc",

    # ── Células da tabela ─────────────────────────────────────────────
    "textCell":         "#e0e0e0",
    "textCellSelected": "#ffffff",
}
