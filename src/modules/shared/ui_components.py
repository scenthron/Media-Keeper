"""
Reusable UI component library and design system primitives for Media Keeper.
Provides standardized, battle-tested widgets for consistent styling across all modules:
- StyledCheckBox: Contrasting checkbox with custom SVG checkmark and hover effects.
- StyledSpinBox: Numeric integer spinbox with stable, aligned SVG chevron arrows.
- StyledDoubleSpinBox: Floating-point spinbox with custom decimal precision and stable arrows.
- PathPickerWidget: Unified file/directory selection widget (LineEdit + Browse SVG + Clear SVG).
"""

import os
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLineEdit, QPushButton, QLabel,
    QCheckBox, QSpinBox, QDoubleSpinBox, QFileDialog, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QIcon

from config import AppContext
from modules.shared.ui_theme import (
    BG_INPUT, BG_HOVER, BG_CONTAINER, BORDER_MEDIUM, BORDER_FOCUS,
    COLOR_PRIMARY, COLOR_PRIMARY_HOVER, COLOR_DANGER, COLOR_DANGER_HOVER,
    TEXT_PRIMARY, TEXT_MUTED
)


def get_icon_path(icon_name: str) -> str:
    """Resolve absolute path to an icon in resource or source directories."""
    icons_dir = AppContext.find_resource_dir("icons")
    if not icons_dir or not os.path.exists(icons_dir):
        icons_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "icons"))
    path = os.path.join(icons_dir, icon_name)
    return path.replace('\\', '/')


# ---------------------------------------------------------------------------
# 1. StyledCheckBox
# ---------------------------------------------------------------------------
class StyledCheckBox(QCheckBox):
    """
    Standardized dark-theme checkbox with high-contrast indicator box,
    smooth hover highlights, and crisp SVG checkmark.
    """

    STYLE = f"""
        QCheckBox {{
            color: {TEXT_PRIMARY};
            font-size: 13px;
            font-weight: bold;
            spacing: 8px;
            background: transparent;
        }}
        QCheckBox:disabled {{
            color: #6b7280;
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border: 1px solid #6b7280;
            border-radius: 3px;
            background-color: #374151;
        }}
        QCheckBox::indicator:hover {{
            border-color: {COLOR_PRIMARY};
            background-color: #4b5563;
        }}
        QCheckBox::indicator:disabled {{
            border-color: #4b5563;
            background-color: #1f2937;
        }}
        QCheckBox::indicator:checked {{
            background-color: {COLOR_PRIMARY};
            border-color: {COLOR_PRIMARY};
            image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxNiAxNiIgZmlsbD0id2hpdGUiPjxwYXRoIGQ9Ik0xMy44NiAzLjY2YS41LjUgMCAwIDEgLjA4LjdsLTcgOGEuNS41IDAgMCAxLS43MiAwbC0zLjUtNGEuNS41IDAgMSAxIC43Ni0uNjRMNi41IDExLjIybDYuNjYtNy42YS41LjUgMCAwIDEgLjctLjA2eiIvPjwvc3ZnPg==);
        }}
        QCheckBox::indicator:checked:hover {{
            background-color: {COLOR_PRIMARY_HOVER};
            border-color: {COLOR_PRIMARY_HOVER};
        }}
    """

    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(self.STYLE)


# ---------------------------------------------------------------------------
# 2. StyledSpinBox & StyledDoubleSpinBox
# ---------------------------------------------------------------------------
def _get_spinbox_qss() -> str:
    up_arrow = get_icon_path("chevron-up.svg")
    down_arrow = get_icon_path("chevron-down.svg")
    return f"""
        QSpinBox, QDoubleSpinBox {{
            background-color: {BG_INPUT};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_MEDIUM};
            border-radius: 4px;
            font-size: 13px;
            font-weight: bold;
            padding-left: 8px;
            padding-right: 26px;
            min-height: 26px;
        }}
        QSpinBox:focus, QDoubleSpinBox:focus {{
            border-color: {BORDER_FOCUS};
        }}
        QSpinBox::up-button, QDoubleSpinBox::up-button {{
            subcontrol-origin: border;
            subcontrol-position: top right;
            width: 22px;
            height: 14px;
            background: #2a2a2a;
            border-left: 1px solid #444;
            border-bottom: 1px solid #444;
            border-top-right-radius: 4px;
        }}
        QSpinBox::down-button, QDoubleSpinBox::down-button {{
            subcontrol-origin: border;
            subcontrol-position: bottom right;
            width: 22px;
            height: 14px;
            background: #2a2a2a;
            border-left: 1px solid #444;
            border-bottom-right-radius: 4px;
        }}
        QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
        QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
            background: #444444;
        }}
        QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
        QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {{
            background: {COLOR_PRIMARY};
        }}
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
            image: url('{up_arrow}');
            width: 10px;
            height: 10px;
        }}
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
            image: url('{down_arrow}');
            width: 10px;
            height: 10px;
        }}
    """


class StyledSpinBox(QSpinBox):
    """
    Standardized dark-theme integer spinbox with properly positioned,
    high-DPI SVG chevron arrows that never overlap the numbers.
    """

    def __init__(
        self,
        min_val: int = 0,
        max_val: int = 100,
        step: int = 1,
        value: int = 0,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.setRange(min_val, max_val)
        self.setSingleStep(step)
        self.setValue(value)
        self.setFixedHeight(28)
        self.setStyleSheet(_get_spinbox_qss())


class StyledDoubleSpinBox(QDoubleSpinBox):
    """
    Standardized dark-theme floating-point spinbox with custom decimal precision,
    step size, and high-DPI SVG chevron arrows.
    """

    def __init__(
        self,
        min_val: float = 0.0,
        max_val: float = 100.0,
        step: float = 0.1,
        decimals: int = 2,
        value: float = 0.0,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.setRange(min_val, max_val)
        self.setSingleStep(step)
        self.setDecimals(decimals)
        self.setValue(value)
        self.setFixedHeight(28)
        self.setStyleSheet(_get_spinbox_qss())


# ---------------------------------------------------------------------------
# 3. PathPickerWidget
# ---------------------------------------------------------------------------
class PathPickerWidget(QWidget):
    """
    Unified path picker widget:
    - Text field with dark styling and focus border.
    - Attached browse button with folder-color.svg icon.
    - Quick clear button with trash-color.svg icon (red hover highlight).
    """

    path_changed = pyqtSignal(str)

    def __init__(
        self,
        initial_path: str = "",
        placeholder: str = "",
        dialog_title: str = "",
        is_folder: bool = True,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.is_folder = is_folder
        self.dialog_title = dialog_title or (AppContext.tr("dlg_browse") if AppContext else "Выбор папки")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Joint container for QLineEdit + Browse Button
        joint_widget = QWidget()
        joint_layout = QHBoxLayout(joint_widget)
        joint_layout.setContentsMargins(0, 0, 0, 0)
        joint_layout.setSpacing(0)

        # LineEdit
        self.line_edit = QLineEdit(initial_path)
        self.line_edit.setFixedHeight(28)
        self.line_edit.setPlaceholderText(placeholder)
        self.line_edit.textChanged.connect(self.path_changed.emit)
        self.line_edit.setStyleSheet(f"""
            QLineEdit {{
                color: {TEXT_PRIMARY};
                background-color: {BG_INPUT};
                border: 1px solid {BORDER_MEDIUM};
                border-right: none;
                padding: 4px 8px;
                border-top-left-radius: 4px;
                border-bottom-left-radius: 4px;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {BORDER_FOCUS};
            }}
        """)
        joint_layout.addWidget(self.line_edit, stretch=1)

        # Browse button with folder icon
        self.btn_browse = QPushButton()
        self.btn_browse.setFixedSize(28, 28)
        self.btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse.setToolTip(AppContext.tr("dlg_browse") if AppContext else "Обзор...")
        folder_icon = QIcon(get_icon_path("folder-color.svg"))
        self.btn_browse.setIcon(folder_icon)
        self.btn_browse.setIconSize(QSize(16, 16))
        self.btn_browse.setStyleSheet(f"""
            QPushButton {{
                background-color: {BG_INPUT};
                border: 1px solid {BORDER_MEDIUM};
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
                padding: 4px;
            }}
            QPushButton:hover {{
                background-color: {BG_HOVER};
                border-color: {BORDER_FOCUS};
            }}
        """)
        self.btn_browse.clicked.connect(self._on_browse_clicked)
        joint_layout.addWidget(self.btn_browse)

        layout.addWidget(joint_widget, stretch=1)

        # Clear button with trash icon
        self.btn_clear = QPushButton()
        self.btn_clear.setFixedSize(28, 28)
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.setToolTip("Очистить путь" if AppContext.is_ru() else "Clear path")
        trash_icon = QIcon(get_icon_path("trash-color.svg"))
        self.btn_clear.setIcon(trash_icon)
        self.btn_clear.setIconSize(QSize(16, 16))
        self.btn_clear.setStyleSheet(f"""
            QPushButton {{
                background-color: {BG_INPUT};
                border: 1px solid {BORDER_MEDIUM};
                border-radius: 4px;
                padding: 4px;
            }}
            QPushButton:hover {{
                background-color: #991b1b;
                border-color: {COLOR_DANGER};
            }}
        """)
        self.btn_clear.clicked.connect(self.clear)
        layout.addWidget(self.btn_clear)

    def _on_browse_clicked(self):
        current_dir = self.text()
        if not current_dir or not os.path.exists(current_dir):
            current_dir = os.path.expanduser("~")

        if self.is_folder:
            folder = QFileDialog.getExistingDirectory(self, self.dialog_title, current_dir)
            if folder:
                self.setText(folder)
        else:
            file_path, _ = QFileDialog.getOpenFileName(self, self.dialog_title, current_dir)
            if file_path:
                self.setText(file_path)

    def text(self) -> str:
        return self.line_edit.text().strip()

    def setText(self, text: str):
        self.line_edit.setText(text)

    def clear(self):
        self.line_edit.setText("")

    def setPlaceholderText(self, text: str):
        self.line_edit.setPlaceholderText(text)

    def setReadOnly(self, read_only: bool):
        self.line_edit.setReadOnly(read_only)

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self.line_edit.setEnabled(enabled)
        self.btn_browse.setEnabled(enabled)
        self.btn_clear.setEnabled(enabled)
