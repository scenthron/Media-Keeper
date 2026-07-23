import os
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QScrollArea, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from config import AppContext

class RefDropContainer(QWidget):
    dump_dropped = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".mkaidump"):
                    event.acceptProposedAction()
                    return
                    
    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".mkaidump"):
                self.dump_dropped.emit(path)

class QCheckBoxCustom(QFrame):
    toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_checked = True
        self.setFixedSize(14, 14)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_style()

    def isChecked(self) -> bool:
        return self.is_checked

    def setChecked(self, checked: bool):
        self.is_checked = checked
        self.update_style()

    def update_style(self):
        if self.is_checked:
            self.setStyleSheet("background-color: #3b82f6; border-radius: 3px; border: none;")
        else:
            self.setStyleSheet("background-color: #111; border-radius: 3px; border: 1px solid #555;")

    def mousePressEvent(self, event):
        self.is_checked = not self.is_checked
        self.update_style()
        self.toggled.emit(self.is_checked)

class AiGroupChipWidget(QFrame):
    state_changed = pyqtSignal(str, bool)
    settings_clicked = pyqtSignal(str)
    remove_clicked = pyqtSignal(str)
    
    def __init__(self, name: str, is_enabled: bool, is_face: bool, status_color: str, count: int, is_external: bool = False, parent=None):
        super().__init__(parent)
        self.group_name = name
        
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #2b2b2b;
                border: 1px solid #444;
                border-radius: 4px;
            }
        """)
        self.setFixedHeight(30)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(6)
        
        self.chk = QCheckBoxCustom()
        self.chk.setChecked(is_enabled)
        self.chk.toggled.connect(lambda checked: self.state_changed.emit(self.group_name, checked))
        layout.addWidget(self.chk)
        
        self.lbl_icon = QLabel()
        self.lbl_icon.setFixedSize(22, 22)
        self.lbl_icon.setText("🙂" if is_face else "🖼️")
        self.lbl_icon.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(self.lbl_icon)
        
        self.lbl_name = QLabel(f"{name} [{count}]")
        self.lbl_name.setStyleSheet("font-weight: bold; color: #eee; font-size: 12px; border: none; background: transparent;")
        layout.addWidget(self.lbl_name)
        
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(8, 8)
        self.update_status_dot(status_color)
        layout.addWidget(self.status_dot)
        
        self.btn_gear = QPushButton("⚙️")
        self.btn_gear.setFixedSize(18, 18)
        self.btn_gear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_gear.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #aaa;
                font-size: 12px;
            }
            QPushButton:hover {
                color: #3b82f6;
            }
        """)
        self.btn_gear.clicked.connect(lambda: self.settings_clicked.emit(self.group_name))
        layout.addWidget(self.btn_gear)
        
        self.btn_remove = QPushButton("✕")
        self.btn_remove.setToolTip("Убрать Образец из списка (файл не удалится)")
        self.btn_remove.setFixedSize(18, 18)
        self.btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #ef4444;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                color: #fca5a5;
            }
        """)
        self.btn_remove.clicked.connect(lambda: self.remove_clicked.emit(self.group_name))
        layout.addWidget(self.btn_remove)
        if not is_external:
            self.btn_remove.hide()

    def update_status_dot(self, color: str):
        hex_color = "#888888" # gray
        if color == "orange":
            hex_color = "#f97316" # orange
        elif color == "green":
            hex_color = "#22c55e" # green
            
        self.status_dot.setStyleSheet(f"""
            background-color: {hex_color};
            border-radius: 4px;
            border: 1px solid rgba(0,0,0,0.5);
        """)

    def set_error_highlight(self, enabled: bool):
        if enabled:
            self.setStyleSheet("""
                QFrame {
                    background-color: #2d1e1e;
                    border: 1px solid #ef4444;
                    border-radius: 4px;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame {
                    background-color: #2b2b2b;
                    border: 1px solid #444;
                    border-radius: 4px;
                }
            """)
