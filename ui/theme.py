"""
ui/theme.py
──────────────────────────────────────────────────────────────────────────────
Hệ thống Design Token & Stylesheet tập trung cho Audio Factory.
Hỗ trợ Dark Mode và Light Mode, mặc định là Light Mode.
"""

from pathlib import Path as _Path

_ASSETS_DIR = _Path(__file__).parent.parent / "assets"
_SVG_ARROW_DOWN_URL    = (_ASSETS_DIR / "arrow_down.svg").as_posix()
_SVG_ARROW_DOWN_ON_URL = (_ASSETS_DIR / "arrow_down_on.svg").as_posix()
_SVG_TOGGLE_OFF_URL    = (_ASSETS_DIR / "toggle_off.svg").as_posix()
_SVG_TOGGLE_ON_URL     = (_ASSETS_DIR / "toggle_on.svg").as_posix()

# ═══════════════════════════════════════════════════════════════════════════════
#  BACKWARD COMPATIBILITY (Dành cho License Dialog và Custom Widgets)
# ═══════════════════════════════════════════════════════════════════════════════
BG_APP        = "#f1f5f9"
BG_PANEL      = "#ffffff"
BG_FIELD      = "#f8fafc"
BORDER_PANEL  = "#e2e8f0"
BORDER_FIELD  = "#cbd5e1"
BORDER_FOCUS  = "#3b82f6"
TEXT_PRIMARY  = "#0f172a"
TEXT_MUTED    = "#475569"
TEXT_DIM      = "#64748b"
ACCENT_SWITCH = "#10b981"
ACCENT_RED    = "#dc2626"

# ═══════════════════════════════════════════════════════════════════════════════
#  COLOUR TOKEN SETS
# ═══════════════════════════════════════════════════════════════════════════════

_DARK_TOKENS = {
    "BG_APP":        "#0b1324",     
    "BG_PANEL":      "#0d1728",     
    "BG_CARD":       "#111d31",     
    "BG_FIELD":      "#101e33",     
    "BG_CONSOLE":    "#07111e",     
    "BG_TABLE_ALT":  "#0e1a2d",     
    "BORDER_PANEL":  "#223a57",     
    "BORDER_FIELD":  "#2d4666",     
    "BORDER_FOCUS":  "#3b82f6",     
    "TEXT_PRIMARY":  "#ffffff",     
    "TEXT_MUTED":    "#f5f5f5",     
    "TEXT_DIM":      "#d0dce8",     
    "TEXT_BLUE":     "#4a9eff",     
    "TEXT_GREEN":    "#10d98c",     
    "ACCENT_BLUE":   "#2563eb",
    "ACCENT_GREEN":  "#059669",
    "ACCENT_RED":    "#dc2626",
    "ACCENT_SWITCH": "#10b981",
    "BTN_DEFAULT":   "#203956",
    "BTN_HOVER":     "#294766",
    "HEADER_TITLE":  "#F8FAFC",
    "HEADER_SUBTITLE": "#94A3B8",
}

_LIGHT_TOKENS = {
    "BG_APP":        "#f1f5f9",     
    "BG_PANEL":      "#ffffff",     
    "BG_CARD":       "#ffffff",     
    "BG_FIELD":      "#f8fafc",     
    "BG_CONSOLE":    "#ffffff",     
    "BG_TABLE_ALT":  "#f8fafc",     
    "BORDER_PANEL":  "#e2e8f0",     
    "BORDER_FIELD":  "#cbd5e1",     
    "BORDER_FOCUS":  "#3b82f6",     
    "TEXT_PRIMARY":  "#0f172a",     
    "TEXT_MUTED":    "#475569",     
    "TEXT_DIM":      "#64748b",     
    "TEXT_BLUE":     "#2563eb",     
    "TEXT_GREEN":    "#059669",     
    "ACCENT_BLUE":   "#2563eb",
    "ACCENT_GREEN":  "#059669",
    "ACCENT_RED":    "#dc2626",
    "ACCENT_SWITCH": "#10b981",
    "BTN_DEFAULT":   "#e2e8f0",
    "BTN_HOVER":     "#cbd5e1",
    "HEADER_TITLE":  "#1E293B",
    "HEADER_SUBTITLE": "#64748B",
}

# ═══════════════════════════════════════════════════════════════════════════════
#  STYLESHEET BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def build_stylesheet(mode: str = "light") -> str:
    T = _DARK_TOKENS if mode == "dark" else _LIGHT_TOKENS
    
    return f"""
/* BASE */
QMainWindow, QDialog, QScrollArea {{ background-color: {T["BG_APP"]}; border: none; }}
QScrollArea > QWidget > QWidget {{ background-color: {T["BG_APP"]}; }}
QWidget {{ color: {T["TEXT_PRIMARY"]}; font-family: 'Segoe UI', 'Inter', 'Roboto', sans-serif; font-size: 13px; background-color: transparent; }}

/* PANELS & CARDS */
QFrame#SectionPanel {{ background-color: {T["BG_PANEL"]}; border: 1px solid {T["BORDER_PANEL"]}; border-radius: 10px; }}
QFrame#FeatureCard {{ background-color: {T["BG_CARD"]}; border: 1px solid {T["BORDER_PANEL"]}; border-radius: 8px; }}
QFrame#FeatureCard:hover {{ border-color: {T["BORDER_FOCUS"]}; background-color: {T["BTN_HOVER"]}; }}

/* SUBTITLE & TRANSLATION CARDS */
QFrame#SubContentPanel, QFrame#TranslationDetailPanel {{ background-color: transparent; border: none; }}
QFrame#subtitle_settings_card, QFrame#translation_settings_card {{ background-color: {T["BG_CARD"]}; border: 1px solid {T["BORDER_PANEL"]}; border-radius: 6px; }}
QWidget#LabeledComboContainer {{ background: transparent; border: none; }}

/* COMBOBOX & INPUTS INSIDE CARDS */
QFrame#subtitle_settings_card QComboBox, QFrame#translation_settings_card QComboBox, QFrame#TranslationDetailPanel QComboBox {{
    border: 1px solid {T["BORDER_FIELD"]}; border-radius: 5px; background-color: {T["BG_FIELD"]}; padding: 6px 28px 6px 12px; color: {T["TEXT_PRIMARY"]}; min-height: 24px;
}}
QFrame#subtitle_settings_card QComboBox:focus, QFrame#translation_settings_card QComboBox:focus, QFrame#TranslationDetailPanel QComboBox:focus {{ border: 1px solid {T["BORDER_FOCUS"]}; }}
QFrame#subtitle_settings_card QComboBox::drop-down, QFrame#translation_settings_card QComboBox::drop-down, QFrame#TranslationDetailPanel QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right; width: 25px; border-left-width: 0px; background: transparent; }}
QFrame#subtitle_settings_card QComboBox::down-arrow, QFrame#translation_settings_card QComboBox::down-arrow, QFrame#TranslationDetailPanel QComboBox::down-arrow {{ image: url({_SVG_ARROW_DOWN_URL}); width: 10px; height: 6px; }}
QFrame#subtitle_settings_card QComboBox::down-arrow:on, QFrame#translation_settings_card QComboBox::down-arrow:on, QFrame#TranslationDetailPanel QComboBox::down-arrow:on {{ image: url({_SVG_ARROW_DOWN_ON_URL}); width: 10px; height: 6px; }}

QFrame#subtitle_settings_card QComboBox QAbstractItemView, QFrame#translation_settings_card QComboBox QAbstractItemView, QFrame#TranslationDetailPanel QComboBox QAbstractItemView {{
    border: 1px solid {T["BORDER_FIELD"]}; background-color: {T["BG_FIELD"]}; color: {T["TEXT_PRIMARY"]}; border-radius: 4px; padding: 4px; outline: none; selection-background-color: {T["BTN_HOVER"]}; selection-color: {T["TEXT_PRIMARY"]};
}}
QFrame#subtitle_settings_card QComboBox QAbstractItemView::item, QFrame#translation_settings_card QComboBox QAbstractItemView::item, QFrame#TranslationDetailPanel QComboBox QAbstractItemView::item {{ padding: 6px 10px; min-height: 26px; border-radius: 3px; color: {T["TEXT_PRIMARY"]}; background-color: transparent; }}
QFrame#subtitle_settings_card QComboBox QAbstractItemView::item:hover, QFrame#translation_settings_card QComboBox QAbstractItemView::item:hover, QFrame#TranslationDetailPanel QComboBox QAbstractItemView::item:hover {{ background-color: {T["BTN_HOVER"]}; }}

/* Styling for API Key Input Boxes (32px Height - Clean Borders) */
QPlainTextEdit#gemini_key_input, 
QPlainTextEdit#deepseek_key_input {{
    background-color: {T["BG_FIELD"]};
    border: 1.5px solid {T["BORDER_FIELD"]};
    border-radius: 6px;
    padding-top: 4px;            /* ✅ Reduced top padding prevents pushing bottom border out of view */
    padding-bottom: 2px;
    padding-left: 8px;
    padding-right: 8px;
    font-size: 12px;
    color: {T["TEXT_PRIMARY"]};
}}

QPlainTextEdit#gemini_key_input:hover, QPlainTextEdit#deepseek_key_input:hover {{
    border: 1.5px solid {T["TEXT_DIM"]};
}}

QPlainTextEdit#gemini_key_input:focus, 
QPlainTextEdit#deepseek_key_input:focus {{
    border: 2px solid {T["BORDER_FOCUS"]};
}}

/* Ensure inner scrollarea viewport remains transparent */
QPlainTextEdit#gemini_key_input QWidget#qt_scrollarea_viewport,
QPlainTextEdit#deepseek_key_input QWidget#qt_scrollarea_viewport {{
    background-color: transparent;
    border: none;
}}

/* TYPOGRAPHY */
QToolTip {{ background-color: {T["BG_PANEL"]}; color: {T["TEXT_PRIMARY"]}; border: 1px solid {T["BORDER_PANEL"]}; padding: 4px; }}
QLabel#HeaderTitle {{ font-family: "Arial"; font-size: 26px; font-weight: bold; color: {T["HEADER_TITLE"]}; padding: 0px; margin: 0px; }}
QLabel#HeaderSubtitle {{ font-family: "Arial"; font-size: 13px; font-weight: normal; color: {T["HEADER_SUBTITLE"]}; padding: 0px; margin: 0px 0px 2px 0px; }}
QLabel#AppTitle {{ font-size: 15px; font-weight: 700; color: {T["TEXT_PRIMARY"]}; }}
QLabel#SectionTitle, QLabel#CardTitle, QLabel#SubtitleToggleLabel {{ font-weight: 700; font-size: 13px; color: {T["TEXT_PRIMARY"]}; }}
QLabel#SectionSubtitle, QLabel#CardDesc, QLabel#CardSubLabel, QLabel#FieldLabel {{ color: {T["TEXT_MUTED"]}; font-size: 11px; }}
QLabel#TranslationFieldLabel {{ color: {T["TEXT_PRIMARY"]}; font-size: 11px; font-weight: 600; }}
QLabel#TranslationToggleLabel {{ font-size: 13px; font-weight: 700; color: {T["TEXT_PRIMARY"]}; }}
QLabel#HintLabel, QLabel#TranslationStatusLabel, QLabel#FooterLabel {{ color: {T["TEXT_DIM"]}; font-size: 11px; }}
QLabel#SummaryChip {{ background-color: {T["BG_FIELD"]}; color: {T["TEXT_MUTED"]}; padding: 5px 14px; border-radius: 6px; font-size: 11px; font-weight: 600; border: 1px solid {T["BORDER_FIELD"]}; }}
QLabel#ProgressLabel {{ color: {T["TEXT_MUTED"]}; font-size: 12px; }}
QLabel#ProgressValue {{ color: {T["TEXT_PRIMARY"]}; font-size: 12px; font-weight: 600; }}
QLabel#ProgressValueGreen {{ color: {T["TEXT_GREEN"]}; font-size: 12px; font-weight: 700; }}

/* INPUTS */
QLineEdit, QComboBox, QPlainTextEdit {{ background-color: {T["BG_FIELD"]}; border: 1px solid {T["BORDER_FIELD"]}; border-radius: 6px; padding: 6px 10px; color: {T["TEXT_PRIMARY"]}; min-height: 24px; }}
QLineEdit, QPushButton#btn_browse {{ height: 32px; min-height: 32px; max-height: 32px; }}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {T["BORDER_FOCUS"]}; }}
QComboBox {{ padding-right: 28px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 24px; border-left: none; background: transparent; }}
QComboBox::down-arrow {{ image: url({_SVG_ARROW_DOWN_URL}); width: 10px; height: 6px; }}
QComboBox::down-arrow:on {{ image: url({_SVG_ARROW_DOWN_ON_URL}); width: 10px; height: 6px; }}
QComboBox QAbstractItemView {{ background-color: {T["BG_PANEL"]}; border: 1px solid {T["BORDER_FIELD"]}; outline: none; border-radius: 4px; selection-background-color: {T["BTN_HOVER"]}; selection-color: {T["TEXT_PRIMARY"]}; color: {T["TEXT_PRIMARY"]}; }}
QComboBox QAbstractItemView::item {{ padding: 6px 10px; min-height: 26px; border-radius: 4px; color: {T["TEXT_PRIMARY"]}; }}
QComboBox QAbstractItemView::item:hover {{ background-color: {T["BTN_HOVER"]}; color: {T["TEXT_PRIMARY"]}; }}

/* THEME BUTTON — overridden by Video Cutter header block below */

/* BUTTONS */
QPushButton {{ background-color: {T["BTN_DEFAULT"]}; color: {T["TEXT_PRIMARY"]}; border: 1px solid {T["BORDER_PANEL"]}; border-radius: 6px; padding: 7px 14px; font-weight: 600; font-size: 13px; }}
QPushButton:hover {{ background-color: {T["BTN_HOVER"]}; }}
QPushButton#btn_add {{ background-color: #45b6d4; color: #ffffff; border: none; }}
QPushButton#btn_add:hover {{ background-color: #5ec2dc; }}
QPushButton#btn_remove {{ background-color: #bc212a; color: #ffffff; border: none; }}
QPushButton#btn_remove:hover {{ background-color: #d8343e; }}
QPushButton#delete_row_btn, QPushButton#btn_delete_row {{ background-color: #d32f2f; color: #ffffff; font-weight: bold; border-radius: 4px; border: none; }}
QPushButton#delete_row_btn:hover, QPushButton#btn_delete_row:hover {{ background-color: #b71c1c; }}
QPushButton#delete_row_btn:pressed, QPushButton#btn_delete_row:pressed {{ background-color: #c62828; }}
QPushButton#btn_start {{ background-color: #2da44e; color: #ffffff; border: none; font-size: 14px; padding: 10px; }}
QPushButton#btn_start:hover {{ background-color: #34c05a; }}
QPushButton#btn_cancel {{ background-color: #cf222e; color: #ffffff; border: none; font-size: 14px; padding: 10px; }}
QPushButton#btn_cancel:hover {{ background-color: #e0333e; }}
QPushButton#btn_neutral, QPushButton#btn_open_folder, QPushButton#btn_clear_log, QPushButton#btn_browse {{ background-color: {T["BTN_DEFAULT"]}; color: {T["TEXT_MUTED"]}; border: 1px solid {T["BORDER_FIELD"]}; }}
QPushButton#btn_neutral:hover, QPushButton#btn_open_folder:hover, QPushButton#btn_clear_log:hover, QPushButton#btn_browse:hover {{ background-color: {T["BTN_HOVER"]}; color: {T["TEXT_PRIMARY"]}; }}

/* TABLE */
QTableWidget {{ background-color: {T["BG_PANEL"]}; alternate-background-color: {T["BG_TABLE_ALT"]}; border: none; color: {T["TEXT_PRIMARY"]}; selection-background-color: {T["BTN_HOVER"]}; selection-color: {T["TEXT_PRIMARY"]}; }}
QTableWidget::item {{ padding: 6px 8px; border: none; }}
QTableWidget::item:selected {{ background-color: {T["BTN_HOVER"]}; color: {T["TEXT_PRIMARY"]}; }}
QHeaderView::section {{ background-color: {T["BG_FIELD"]}; color: {T["TEXT_MUTED"]}; border: none; border-bottom: 1px solid {T["BORDER_PANEL"]}; padding: 6px 8px; font-weight: 600; }}
QHeaderView::section:horizontal {{ border-right: 1px solid {T["BORDER_PANEL"]}; }}

/* PROGRESS & CONSOLE */
QProgressBar {{ border: 1px solid {T["BORDER_PANEL"]}; border-radius: 5px; text-align: center; background-color: {T["BG_FIELD"]}; color: {T["TEXT_PRIMARY"]}; font-weight: 700; }}
QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #10d98c); border-radius: 4px; }}
QTextEdit#LogConsole {{ background-color: {T["BG_CONSOLE"]}; border: 1px solid {T["BORDER_PANEL"]}; border-radius: 8px; padding: 10px; font-family: 'Consolas', monospace; color: {T["TEXT_GREEN"]}; }}

/* SCROLLBARS */
QScrollBar:vertical {{ border: none; background: {T["BG_APP"]}; width: 8px; }}
QScrollBar::handle:vertical {{ background: {T["BORDER_PANEL"]}; border-radius: 4px; min-height: 20px; }}
QScrollBar::handle:vertical:hover {{ background: {T["BORDER_FIELD"]}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

/* MISC */
QFrame#DropZoneFrame {{ border: 1px solid {T["BORDER_PANEL"]}; border-radius: 8px; }}
QCheckBox#ToggleSwitch::indicator {{ width: 44px; height: 22px; border-radius: 11px; image: url({_SVG_TOGGLE_OFF_URL}); }}
QCheckBox#ToggleSwitch::indicator:checked {{ image: url({_SVG_TOGGLE_ON_URL}); }}

/* ── ĐỒNG BỘ HEADER GIỐNG VIDEO CUTTER ── */
QWidget#HeaderPanel {{ background-color: transparent; border-bottom: none; padding: 0px 4px; }}
QLabel#HeaderTitle {{ font-family: "Arial"; font-size: 26px; font-weight: bold; color: {T["HEADER_TITLE"]}; padding: 0px; margin: 0px; }}
QLabel#HeaderSubtitle {{ font-family: "Arial"; font-size: 13px; font-weight: normal; color: {T["HEADER_SUBTITLE"]}; padding: 0px; margin: 0px 0px 2px 0px; }}
QFrame#HeaderDivider {{ border: none; min-height: 2px; max-height: 2px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FFD5A1, stop:0.6 rgba(255,213,161,0.3), stop:1 transparent); margin-top: 2px; margin-bottom: 0px; }}
QComboBox#HeaderLangMenu {{ border: 1px solid {T["BORDER_FIELD"]}; border-radius: 6px; padding: 2px 6px; height: 26px; min-height: 26px; min-width: 55px; background-color: {T["BG_FIELD"]}; color: {T["TEXT_PRIMARY"]}; }}
QPushButton#ThemeToggleButton {{ background-color: {T["BG_FIELD"]}; border: 1px solid {T["BORDER_FIELD"]}; border-radius: 6px; height: 26px; min-height: 26px; min-width: 36px; max-width: 36px; padding: 0px; color: {T["TEXT_PRIMARY"]}; }}
QPushButton#ThemeToggleButton:hover {{ background-color: {T["BORDER_PANEL"]}; }}

/* ═══════════════════════════════════════════════════════
   MESSAGE BOX (POP-UPS)
═══════════════════════════════════════════════════════ */
QMessageBox {{
    background-color: {T["BG_PANEL"]};
}}
QMessageBox QLabel {{
    color: {T["TEXT_PRIMARY"]};
    background: transparent;
    min-width: 240px;
    padding-top: 10px;
    padding-bottom: 10px;
    padding-left: 5px;
}}
QMessageBox QPushButton {{
    background-color: {T["BTN_DEFAULT"]};
    border: 1px solid {T["BORDER_FIELD"]};
    color: {T["TEXT_PRIMARY"]};
    font-weight: 600;
    padding: 5px 20px;
    border-radius: 6px;
    min-width: 65px;
    margin-bottom: 4px;
}}
QMessageBox QPushButton:hover {{
    background-color: {T["BTN_HOVER"]};
}}
"""

APP_STYLESHEET = build_stylesheet("light")
