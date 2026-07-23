from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QLineEdit, QWidget, QFrame, QScrollArea)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent
from PyQt6.QtGui import QIcon

from ui_widgets_base import FlowLayout
from config import AppContext
from .logic_ai_tags import AiTextTagsManager

class AiTagChipWidget(QFrame):
    edit_clicked = pyqtSignal(str, str)
    delete_clicked = pyqtSignal(str)

    def __init__(self, name: str, body: str, is_multi: bool, in_delete_mode: bool = False, parent=None):
        super().__init__(parent)
        self.tag_name = name
        self.tag_body = body
        self.is_multi = is_multi
        self.in_delete_mode = in_delete_mode

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedHeight(30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(8, 0, 8, 0)
        self.layout.setSpacing(4)

        self.lbl_name = QLabel(self.tag_name)
        self.lbl_name.setStyleSheet("font-weight: bold; font-size: 12px; background: transparent; border: none;")
        self.layout.addWidget(self.lbl_name)

        # Edit button (pencil)
        self.btn_edit = QPushButton("✏️")
        self.btn_edit.setFixedSize(18, 18)
        self.btn_edit.setStyleSheet("""
            QPushButton { background: transparent; border: none; font-size: 12px; }
            QPushButton:hover { background-color: rgba(255, 255, 255, 0.2); border-radius: 9px; }
        """)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_edit.hide()
        self.layout.addWidget(self.btn_edit)

        self.installEventFilter(self)
        self.update_style()

    def update_style(self):
        if self.in_delete_mode:
            self.setStyleSheet("""
                QFrame {
                    background-color: #7f1d1d;
                    border: 1px solid #b91c1c;
                    border-radius: 4px;
                    color: white;
                }
                QFrame:hover { background-color: #991b1b; }
            """)
            self.lbl_name.setStyleSheet("font-weight: bold; font-size: 12px; background: transparent; border: none; color: white;")
        else:
            if self.is_multi:
                self.setStyleSheet("""
                    QFrame {
                        background-color: #d97706;
                        border: 1px solid #f59e0b;
                        border-radius: 4px;
                        color: white;
                    }
                    QFrame:hover { background-color: #f59e0b; }
                """)
            else:
                self.setStyleSheet("""
                    QFrame {
                        background-color: #166534;
                        border: 1px solid #15803d;
                        border-radius: 4px;
                        color: white;
                    }
                    QFrame:hover { background-color: #15803d; }
                """)
            self.lbl_name.setStyleSheet("font-weight: bold; font-size: 12px; background: transparent; border: none; color: white;")

    def set_delete_mode(self, enabled: bool):
        self.in_delete_mode = enabled
        self.update_style()
        if enabled:
            self.btn_edit.hide()

    def eventFilter(self, obj, event):
        if obj == self:
            if event.type() == QEvent.Type.Enter:
                if not self.in_delete_mode:
                    self.btn_edit.show()
            elif event.type() == QEvent.Type.Leave:
                self.btn_edit.hide()
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.in_delete_mode:
                self.delete_clicked.emit(self.tag_name)
        super().mousePressEvent(event)

    def _on_edit(self):
        self.edit_clicked.emit(self.tag_name, self.tag_body)


class AiTagManagerDialog(QDialog):
    tags_changed = pyqtSignal()

    def __init__(self, manager: AiTextTagsManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.delete_mode = False
        
        self.setWindowTitle("Менеджер тегов" if AppContext.is_ru() else "Tag Manager")
        self.setMinimumSize(500, 400)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; }
            QLabel { color: #eee; }
            QLineEdit {
                background-color: #2b2b2b; color: #eee;
                border: 1px solid #444; border-radius: 4px; padding: 4px;
            }
            QLineEdit:focus { border: 1px solid #3b82f6; }
        """)

        layout = QVBoxLayout(self)

        # Creation Panel
        create_panel = QHBoxLayout()
        
        self.line_name = QLineEdit()
        self.line_name.setPlaceholderText("Название тега" if AppContext.is_ru() else "Tag Name")
        self.line_name.textChanged.connect(self.validate_input)
        create_panel.addWidget(self.line_name, 1)

        self.line_body = QLineEdit()
        self.line_body.setPlaceholderText("Пример: собака, кошка" if AppContext.is_ru() else "Example: dog, cat")
        self.line_body.textChanged.connect(self.validate_input)
        create_panel.addWidget(self.line_body, 2)

        self.btn_create = QPushButton("Создать" if AppContext.is_ru() else "Create")
        self.btn_create.setFixedSize(80, 26)
        self.btn_create.clicked.connect(self.on_create_clicked)
        create_panel.addWidget(self.btn_create)

        self.btn_toggle_delete = QPushButton("❌")
        self.btn_toggle_delete.setFixedSize(26, 26)
        self.btn_toggle_delete.setCheckable(True)
        self.btn_toggle_delete.toggled.connect(self.on_delete_toggled)
        self.btn_toggle_delete.setStyleSheet("""
            QPushButton { background-color: #2b2b2b; border: 1px solid #444; border-radius: 4px; color: #eee; }
            QPushButton:checked { background-color: #7f1d1d; border: 1px solid #b91c1c; }
            QPushButton:hover { background-color: #444; }
        """)
        create_panel.addWidget(self.btn_toggle_delete)

        layout.addLayout(create_panel)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("border: 1px solid #333;")
        layout.addWidget(sep)

        # Flow Layout for tags
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        self.flow_container = QWidget()
        self.flow_container.setStyleSheet("background-color: transparent;")
        self.flow_layout = FlowLayout(self.flow_container, margin=0, spacing=8)
        self.scroll_area.setWidget(self.flow_container)
        layout.addWidget(self.scroll_area)

        self.refresh_tags()
        self.validate_input()

    def validate_input(self):
        name = self.line_name.text().strip()
        body = self.line_body.text().strip()

        if not name or not body:
            self.btn_create.setStyleSheet("""
                QPushButton { background-color: #444; color: #888; border: 1px solid #555; border-radius: 4px; font-weight: bold; }
            """)
            self.btn_create.setEnabled(False)
            return

        self.btn_create.setEnabled(True)

        if self.manager.tag_exists(name):
            # Update mode
            self.btn_create.setText("Обновить" if AppContext.is_ru() else "Update")
            self.btn_create.setStyleSheet("""
                QPushButton { background-color: #b91c1c; color: white; border: 1px solid #dc2626; border-radius: 4px; font-weight: bold; }
                QPushButton:hover { background-color: #dc2626; }
            """)
        else:
            self.btn_create.setText("Создать" if AppContext.is_ru() else "Create")
            # Check if multi-tag
            if "," in body:
                self.btn_create.setStyleSheet("""
                    QPushButton { background-color: #f59e0b; color: white; border: 1px solid #f59e0b; border-radius: 4px; font-weight: bold; }
                    QPushButton:hover { background-color: #f59e0b; }
                """)
            else:
                self.btn_create.setStyleSheet("""
                    QPushButton { background-color: #15803d; color: white; border: 1px solid #16a34a; border-radius: 4px; font-weight: bold; }
                    QPushButton:hover { background-color: #16a34a; }
                """)

    def on_create_clicked(self):
        name = self.line_name.text().strip()
        body = self.line_body.text().strip()
        if not name or not body:
            return

        self.manager.add_or_update_tag(name, body)
        self.line_name.clear()
        self.line_body.clear()
        self.refresh_tags()
        self.tags_changed.emit()

    def on_delete_toggled(self, checked):
        self.delete_mode = checked
        # Update all chips
        for i in range(self.flow_layout.count()):
            item = self.flow_layout.itemAt(i)
            if item and item.widget():
                item.widget().set_delete_mode(self.delete_mode)

    def refresh_tags(self):
        # Clear existing
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        tags = self.manager.get_tags()
        for name, body in tags.items():
            is_multi = "," in body
            chip = AiTagChipWidget(name, body, is_multi, self.delete_mode)
            chip.edit_clicked.connect(self.on_tag_edit)
            chip.delete_clicked.connect(self.on_tag_delete)
            self.flow_layout.addWidget(chip)

    def on_tag_edit(self, name, body):
        self.line_name.setText(name)
        self.line_body.setText(body)

    def on_tag_delete(self, name):
        self.manager.delete_tag(name)
        self.refresh_tags()
        self.tags_changed.emit()
