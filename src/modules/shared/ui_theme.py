"""
Centralized UI theme design tokens, color palettes, and reusable QSS styles
for Media Keeper Qt widgets.
"""

# Base Theme Colors (Dark Theme)
BG_MAIN = "#1e1e1e"
BG_PANEL = "#252526"
BG_CONTAINER = "#1a1a1a"
BG_DARK = "#111111"
BG_SECONDARY = "#2a2a2a"
BG_INPUT = "#333333"
BG_HOVER = "#3a3a3a"
BG_SELECTED = "#2d3748"

# Borders
BORDER_DARK = "#2d2d2d"
BORDER_DEFAULT = "#333333"
BORDER_MEDIUM = "#444444"
BORDER_LIGHT = "#555555"
BORDER_FOCUS = "#3b82f6"

# Text Colors
TEXT_PRIMARY = "#ffffff"
TEXT_SECONDARY = "#eeeeee"
TEXT_BODY = "#cccccc"
TEXT_MUTED = "#888888"
TEXT_MUTED_LIGHT = "#aaaaaa"

# Accent & Status Colors
COLOR_PRIMARY = "#3b82f6"
COLOR_PRIMARY_HOVER = "#2563eb"
COLOR_PRIMARY_LIGHT = "#60a5fa"
COLOR_PRIMARY_TEXT = "#93c5fd"

COLOR_SUCCESS = "#15803d"
COLOR_SUCCESS_HOVER = "#16a34a"
COLOR_SUCCESS_TEXT = "#4ade80"

COLOR_DANGER = "#ef4444"
COLOR_DANGER_HOVER = "#dc2626"
COLOR_DANGER_DARK = "#b91c1c"

COLOR_WARNING = "#eab308"
COLOR_WARNING_HOVER = "#ca8a04"

# Reusable QSS Styles
STYLE_SPLITTER = "QSplitter::handle { background-color: #2d2d2d; }"

STYLE_SLIDER_BLUE = """
    QSlider::groove:horizontal {
        height: 4px;
        background: #333;
        border-radius: 2px;
    }
    QSlider::sub-page:horizontal {
        background: #3b82f6;
        border-radius: 2px;
    }
    QSlider::handle:horizontal {
        background: #60a5fa;
        width: 14px;
        margin: -5px 0;
        border-radius: 7px;
    }
    QSlider::handle:horizontal:hover {
        background: #93c5fd;
    }
"""

STYLE_CHECKBOX = """
    QCheckBox {
        color: #ccc;
        font-weight: bold;
        font-size: 11px;
    }
    QCheckBox::indicator {
        width: 14px;
        height: 14px;
        border-radius: 3px;
        border: 1px solid #555;
        background: #111;
    }
    QCheckBox::indicator:hover {
        border-color: #3b82f6;
    }
    QCheckBox::indicator:checked {
        background-color: #3b82f6;
        border-color: #3b82f6;
    }
"""

STYLE_BTN_START = """
    QPushButton {
        background-color: #15803d;
        color: white;
        font-weight: 900;
        font-size: 13px;
        border: 1px solid #16a34a;
        border-radius: 6px;
        padding: 6px 14px;
    }
    QPushButton:hover {
        background-color: #16a34a;
    }
    QPushButton:disabled {
        background-color: #27272a;
        color: #71717a;
        border-color: #3f3f46;
    }
"""

STYLE_BTN_DANGER = """
    QPushButton {
        background-color: #b91c1c;
        color: white;
        font-weight: bold;
        border: 1px solid #dc2626;
        border-radius: 4px;
        padding: 4px 10px;
    }
    QPushButton:hover {
        background-color: #dc2626;
    }
    QPushButton:disabled {
        background-color: #27272a;
        color: #71717a;
        border-color: #3f3f46;
    }
"""

STYLE_BTN_SECONDARY = """
    QPushButton {
        background-color: #444;
        color: #fff;
        border: 1px solid #666;
        padding: 4px 10px;
        border-radius: 4px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #555;
        color: white;
        border-color: #888;
    }
    QPushButton:disabled {
        background-color: #2a2a2a;
        color: #666;
        border-color: #444;
    }
"""

STYLE_BTN_ACCENT = """
    QPushButton {
        background-color: #3b82f6;
        color: white;
        font-weight: bold;
        border: 1px solid #2563eb;
        border-radius: 4px;
        padding: 4px 12px;
    }
    QPushButton:hover {
        background-color: #2563eb;
    }
    QPushButton:disabled {
        background-color: #2a2a2a;
        color: #666;
        border-color: #444;
    }
"""

STYLE_PROGRESS_BAR = """
    QProgressBar {
        border: 1px solid #444;
        border-radius: 4px;
        text-align: center;
        background-color: #111;
        color: white;
        font-weight: bold;
        font-size: 11px;
    }
    QProgressBar::chunk {
        background-color: #3b82f6;
        border-radius: 3px;
    }
"""

STYLE_CONTEXT_MENU = """
    QMenu {
        background-color: #2b2b2b;
        color: #eee;
        border: 1px solid #444;
    }
    QMenu::item {
        padding: 6px 20px;
    }
    QMenu::item:selected {
        background-color: #3b82f6;
        color: white;
    }
"""

STYLE_SETTINGS_TABS = """
    QTabWidget::pane {
        border: 1px solid #2d2d2d;
        background-color: #161616;
        border-radius: 4px;
    }
    QTabBar::tab {
        background: #1e1e1e;
        color: #888;
        padding: 4px 12px;
        border: 1px solid #2d2d2d;
        border-bottom: none;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        font-size: 11px;
        font-weight: bold;
    }
    QTabBar::tab:selected {
        background: #161616;
        color: #3b82f6;
        border-bottom: 2px solid #3b82f6;
    }
    QTabBar::tab:hover:!selected {
        background: #252525;
        color: #ccc;
    }
"""

STYLE_TREE_RESULTS = """
    QTreeWidget {
        background-color: #1e1e1e;
        color: #eee;
        border: 1px solid #2d2d2d;
        border-radius: 4px;
        outline: none;
    }
    QTreeWidget::item {
        height: 24px;
        border-bottom: 1px solid #252525;
    }
    QTreeWidget::item:hover {
        background-color: #282828;
    }
    QTreeWidget::item:selected {
        background-color: #2563eb;
        color: white;
    }
    QHeaderView::section {
        background-color: #252526;
        color: #aaa;
        font-weight: bold;
        padding: 4px 8px;
        border: none;
        border-right: 1px solid #333;
        border-bottom: 1px solid #333;
    }
"""
