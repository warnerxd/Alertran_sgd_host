# utils/theme.py
"""
macOS Sonoma-inspired theme — auto-detects Windows dark/light mode.
Premium palette following Apple Human Interface Guidelines.
"""
import sys
from PySide6.QtCore import QObject, Signal


class _ThemeSignals(QObject):
    """Singleton que emite 'changed' cuando el tema cambia."""
    changed = Signal()


signals = _ThemeSignals()

_DARK: bool | None = None


def is_dark() -> bool:
    """Devuelve True si el sistema usa tema oscuro."""
    global _DARK
    if _DARK is not None:
        return _DARK
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            )
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            _DARK = (val == 0)
            return _DARK
        except Exception:
            pass
    _DARK = False
    return _DARK


# ── Paletas macOS Sonoma ────────────────────────────────────────────────────

DARK = {
    # Backgrounds
    "bg":            "#1c1c1e",
    "surface":       "#2c2c2e",
    "surface2":      "#3a3a3c",
    "surface3":      "#48484a",
    # Borders
    "border":        "#3a3a3c",
    "border_strong": "#48484a",
    "sep":           "#38383a",
    # Accent — macOS Blue Dark
    "accent":        "#0a84ff",
    "accent_hover":  "#409cff",
    "accent_light":  "#0a2040",
    "accent_press":  "#0060cc",
    # Text hierarchy
    "text":          "#f2f2f7",
    "text2":         "#aeaeb2",
    "text3":         "#636366",
    "text4":         "#3a3a3c",
    # Status
    "success":       "#30d158",
    "success_bg":    "#0d2e18",
    "warning":       "#ff9f0a",
    "warning_bg":    "#2d1e00",
    "error":         "#ff453a",
    "error_bg":      "#2d0e0e",
    "purple":        "#bf5af2",
    # UI chrome
    "header_bg":     "#111113",
    "header_border": "#2c2c2e",
    "action_bg":     "#111113",
    "log_bg":        "#0d0d0f",
    "log_fg":        "#d1d1d6",
    "input_bg":      "#2c2c2e",
    "input_border":  "#48484a",
    "group_bg":      "#2c2c2e",
    "group_border":  "#3a3a3c",
    "group_title":   "#98989d",
    "table_hdr_bg":  "#1e1e20",
    "table_hdr_fg":  "#98989d",
    "table_alt":     "#242426",
    "table_grid":    "#3a3a3c",
    "table_sel":     "#0a84ff",
    "sb_bg":         "transparent",
    "sb_handle":     "#48484a",
    "btn_tool_bg":   "#2c2c2e",
    "btn_tool_brd":  "#48484a",
    "dis_bg":        "#2c2c2e",
    "dis_fg":        "#3a3a3c",
    "stat_zero":     "#3a3a3c",
    "stat_text":     "#98989d",
    "cb_all_bg":     "#242426",
    "status_bg":     "#242426",
}

LIGHT = {
    # Backgrounds — macOS Sonoma system colors
    "bg":            "#f2f2f7",
    "surface":       "#ffffff",
    "surface2":      "#f9f9fb",
    "surface3":      "#f2f2f7",
    # Borders
    "border":        "#e5e5ea",
    "border_strong": "#c7c7cc",
    "sep":           "#d1d1d6",
    # Accent — macOS Blue
    "accent":        "#007aff",
    "accent_hover":  "#0066d6",
    "accent_light":  "#e8f2ff",
    "accent_press":  "#004db3",
    # Text hierarchy
    "text":          "#1c1c1e",
    "text2":         "#3c3c43",
    "text3":         "#8e8e93",
    "text4":         "#c7c7cc",
    # Status
    "success":       "#34c759",
    "success_bg":    "#f0fdf4",
    "warning":       "#ff9500",
    "warning_bg":    "#fffbeb",
    "error":         "#ff3b30",
    "error_bg":      "#fff5f5",
    "purple":        "#af52de",
    
    # UI chrome
    "header_bg":     "#f9f9fb",
    "header_border": "#e5e5ea",
    "action_bg":     "#f2f2f7",
    "log_bg":        "#ffffff",
    "log_fg":        "#1c1c1e",
    "input_bg":      "#ffffff",
    "input_border":  "#d1d1d6",
    "group_bg":      "#ffffff",
    "group_border":  "#e5e5ea",
    "group_title":   "#8e8e93",
    "table_hdr_bg":  "#f9f9fb",
    "table_hdr_fg":  "#8e8e93",
    "table_alt":     "#fafafa",
    "table_grid":    "#f2f2f7",
    "table_sel":     "#007aff",
    "sb_bg":         "transparent",
    "sb_handle":     "#c7c7cc",
    "btn_tool_bg":   "#ffffff",
    "btn_tool_brd":  "#e5e5ea",
    "dis_bg":        "#f5f5f7",
    "dis_fg":        "#c7c7cc",
    "stat_zero":     "#e5e5ea",
    "stat_text":     "#8e8e93",
    "cb_all_bg":     "#f2f2f7",
    "status_bg":     "#f9f9fb",
}


def set_dark(value: bool) -> None:
    """Fuerza el tema oscuro o claro, ignorando la configuración del sistema."""
    global _DARK
    _DARK = value


def toggle() -> bool:
    """Alterna entre tema oscuro y claro. Devuelve el nuevo valor is_dark."""
    set_dark(not is_dark())
    return is_dark()


def colors() -> dict:
    return DARK if is_dark() else LIGHT


def base_stylesheet() -> str:
    """Stylesheet premium macOS Sonoma compartido por todas las ventanas."""
    c = colors()
    return f"""
        /* ═══════════════════════════════════════════════════
           BASE — macOS Sonoma Premium Style
           Apple Human Interface Guidelines compliant
        ═══════════════════════════════════════════════════ */

        QDialog, QMainWindow, QWidget {{
            background-color: {c['bg']};
            color: {c['text']};
            font-family: 'SF Pro Display', 'Segoe UI Variable Display',
                         'Segoe UI', 'Inter', Arial, sans-serif;
            font-size: 10pt;
        }}

        QLabel {{
            color: {c['text']};
            background: transparent;
            border: none;
        }}

        /* ── Inputs ─────────────────────────────────────── */

        QLineEdit, QSpinBox, QComboBox {{
            background-color: {c['input_bg']};
            color: {c['text']};
            border: 1.5px solid {c['input_border']};
            border-radius: 10px;
            padding: 6px 12px;
            min-height: 32px;
            selection-background-color: {c['accent']};
            selection-color: white;
        }}

        QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
            border: 2px solid {c['accent']};
            background-color: {c['surface']};
        }}

        QLineEdit:hover:!focus, QSpinBox:hover:!focus, QComboBox:hover:!focus {{
            border-color: {c['border_strong']};
        }}

        QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
            background-color: {c['dis_bg']};
            color: {c['dis_fg']};
            border-color: {c['border']};
        }}

        QLineEdit[readOnly="true"] {{
            background-color: {c['surface2']};
            color: {c['text3']};
        }}

        /* ── ComboBox — macOS style selector ────────────── */

        QComboBox {{
            padding-right: 36px;
        }}

        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: right center;
            width: 32px;
            background-color: {c['accent']};
            border-top-right-radius: 8px;
            border-bottom-right-radius: 8px;
            border: none;
            margin: 2px 2px 2px 0px;
        }}

        QComboBox::drop-down:hover {{
            background-color: {c['accent_hover']};
        }}

        QComboBox::down-arrow {{
            image: url(assets/arrow_updown.svg);
            width: 12px;
            height: 14px;
        }}

        /* QAbstractItemView del popup se estiliza en RoundedComboBox.showPopup()
           para poder aplicar WA_TranslucentBackground + border-radius real. */
        QComboBox QAbstractItemView {{
            outline: none;
        }}

        /* ── SpinBox ────────────────────────────────────── */

        /* ── SpinBox — stacked blue buttons like macOS stepper ── */

        QSpinBox {{
            padding-right: 36px;
            min-height: 36px;
        }}

        QSpinBox::up-button {{
            subcontrol-origin: border;
            subcontrol-position: top right;
            width: 30px;
            background-color: {c['accent']};
            border-top-right-radius: 9px;
            border-bottom-right-radius: 0px;
            border: none;
            margin: 2px 2px 0px 0px;
        }}

        QSpinBox::down-button {{
            subcontrol-origin: border;
            subcontrol-position: bottom right;
            width: 30px;
            background-color: {c['accent']};
            border-top-right-radius: 0px;
            border-bottom-right-radius: 9px;
            border: none;
            margin: 0px 2px 2px 0px;
        }}

        QSpinBox::up-button:hover {{
            background-color: {c['accent_hover']};
        }}

        QSpinBox::down-button:hover {{
            background-color: {c['accent_hover']};
        }}

        QSpinBox::up-button:pressed {{
            background-color: {c['accent_press']};
        }}

        QSpinBox::down-button:pressed {{
            background-color: {c['accent_press']};
        }}

        QSpinBox::up-arrow {{
            image: url(assets/arrow_up.svg);
            width: 10px;
            height: 7px;
        }}

        QSpinBox::down-arrow {{
            image: url(assets/arrow_down.svg);
            width: 10px;
            height: 7px;
        }}

        /* ── TextEdit ───────────────────────────────────── */

        QTextEdit {{
            background-color: {c['log_bg']};
            color: {c['log_fg']};
            border: 1.5px solid {c['border']};
            border-radius: 12px;
            padding: 10px 12px;
            selection-background-color: {c['accent']};
        }}

        QTextEdit:focus {{
            border: 2px solid {c['accent']};
        }}

        /* ── GroupBox — Card style ──────────────────────── */

        QGroupBox {{
            background-color: {c['group_bg']};
            border: 1.5px solid {c['group_border']};
            border-radius: 14px;
            margin-top: 22px;
            padding-top: 18px;
            font-weight: 600;
            color: {c['group_title']};
        }}

        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 16px;
            padding: 3px 10px;
            color: {c['group_title']};
            background-color: {c['group_bg']};
            border-radius: 6px;
            font-size: 9pt;
            font-weight: 700;
            letter-spacing: 0.3px;
        }}

        /* ── Scrollbars — thin macOS style ─────────────── */

        QScrollBar:vertical {{
            background: {c['sb_bg']};
            width: 6px;
            border-radius: 3px;
            margin: 4px 2px;
        }}

        QScrollBar::handle:vertical {{
            background: {c['sb_handle']};
            border-radius: 3px;
            min-height: 28px;
        }}

        QScrollBar::handle:vertical:hover {{ background: {c['text3']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

        QScrollBar:horizontal {{
            background: {c['sb_bg']};
            height: 6px;
            border-radius: 3px;
            margin: 2px 4px;
        }}

        QScrollBar::handle:horizontal {{
            background: {c['sb_handle']};
            border-radius: 3px;
            min-width: 28px;
        }}

        QScrollBar::handle:horizontal:hover {{ background: {c['text3']}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}

        /* ── CheckBox ───────────────────────────────────── */

        QCheckBox {{
            color: {c['text']};
            spacing: 8px;
            font-size: 10pt;
        }}

        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border: 1.5px solid {c['border_strong']};
            border-radius: 5px;
            background-color: {c['input_bg']};
        }}

        QCheckBox::indicator:hover {{
            border-color: {c['accent']};
            background-color: {c['accent_light']};
        }}

        QCheckBox::indicator:checked {{
            background-color: {c['accent']};
            border-color: {c['accent']};
            image: url(assets/checkmark_white.svg);
        }}

        QCheckBox::indicator:checked:hover {{
            background-color: {c['accent_hover']};
        }}

        /* ── QPushButton — macOS secondary style ────────── */

        QPushButton {{
            padding: 7px 18px;
            border-radius: 10px;
            font-weight: 600;
            min-height: 34px;
            background-color: {c['btn_tool_bg']};
            border: 1.5px solid {c['btn_tool_brd']};
            color: {c['text']};
            font-size: 10pt;
        }}

        QPushButton:hover {{
            background-color: {c['surface2']};
            border-color: {c['accent']};
            color: {c['accent']};
        }}

        QPushButton:pressed {{
            background-color: {c['accent_light']};
            border-color: {c['accent']};
            color: {c['accent']};
        }}

        QPushButton:disabled {{
            background-color: {c['dis_bg']};
            color: {c['dis_fg']};
            border: 1.5px solid {c['border']};
        }}

        QPushButton:focus {{
            border: 2px solid {c['accent']};
            outline: none;
        }}

        /* ── QTabWidget ─────────────────────────────────── */

        QTabWidget::pane {{
            background-color: {c['surface']};
            border: 1.5px solid {c['border']};
            border-radius: 12px;
            top: -2px;
        }}

        QTabBar {{
            background: transparent;
        }}

        QTabBar::tab {{
            background-color: transparent;
            color: {c['text3']};
            padding: 8px 20px;
            border: none;
            border-bottom: 2px solid transparent;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            font-weight: 600;
            font-size: 10pt;
            margin-right: 2px;
            min-width: 80px;
        }}

        QTabBar::tab:selected {{
            color: {c['accent']};
            border-bottom: 2.5px solid {c['accent']};
            background-color: {c['surface']};
        }}

        QTabBar::tab:hover:!selected {{
            color: {c['text']};
            background-color: {c['surface2']};
            border-radius: 8px;
        }}

        /* ── QTableWidget ───────────────────────────────── */

        QTableWidget {{
            background-color: {c['surface']};
            color: {c['text']};
            border: 1.5px solid {c['border']};
            border-radius: 12px;
            gridline-color: {c['table_grid']};
            selection-background-color: {c['accent']};
            selection-color: white;
            alternate-background-color: {c['table_alt']};
            outline: none;
        }}

        QHeaderView::section {{
            background-color: {c['table_hdr_bg']};
            color: {c['table_hdr_fg']};
            border: none;
            border-bottom: 1.5px solid {c['border']};
            border-right: 1px solid {c['border']};
            padding: 8px 12px;
            font-weight: 700;
            font-size: 9pt;
            letter-spacing: 0.3px;
        }}

        QHeaderView::section:first {{
            border-top-left-radius: 10px;
        }}

        QHeaderView::section:last {{
            border-top-right-radius: 10px;
            border-right: none;
        }}

        QTableWidget::item {{
            padding: 8px 12px;
            border-bottom: 1px solid {c['table_grid']};
        }}

        QTableWidget::item:selected {{
            background-color: {c['accent']};
            color: white;
            border-radius: 0;
        }}

        /* ── QSplitter ──────────────────────────────────── */

        QSplitter::handle {{
            background-color: {c['sep']};
        }}

        QSplitter::handle:horizontal {{
            width: 1px;
            margin: 8px 4px;
        }}

        QSplitter::handle:vertical {{
            height: 1px;
            margin: 4px 8px;
        }}

        /* ── Tooltip ────────────────────────────────────── */

        QToolTip {{
            background-color: {c['surface']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 8px;
            padding: 6px 10px;
            font-size: 9.5pt;
        }}

        /* ── QFrame separators ──────────────────────────── */

        QFrame[frameShape="4"],
        QFrame[frameShape="5"] {{
            background-color: {c['sep']};
            border: none;
            max-height: 1px;
        }}

        /* ── QProgressBar ───────────────────────────────── */

        QProgressBar {{
            background-color: {c['surface2']};
            border: none;
            border-radius: 4px;
            height: 6px;
            text-align: center;
            color: transparent;
        }}

        QProgressBar::chunk {{
            background-color: {c['accent']};
            border-radius: 4px;
        }}
    """
