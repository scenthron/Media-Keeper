
import os
from PyQt6.QtWidgets import (
    QScrollArea, QFrame, QLabel, QSizePolicy, QLayout, QWidgetItem, QStyle,
    QPushButton, QVBoxLayout, QHBoxLayout
)
from PyQt6.QtCore import Qt, QPointF, QUrl, QSize, QRect, pyqtSignal
from PyQt6.QtGui import QPainter, QDesktopServices, QIcon

from config import AppContext
from utils_common import format_size, truncate_text
from logic_cache import DirCache

class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self.itemList = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self.itemList.append(item)

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self._do_layout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())
        size += QSize(2 * self.contentsMargins().top(), 2 * self.contentsMargins().top())
        return size

    def _do_layout(self, rect, test_only):
        x = rect.x()
        y = rect.y()
        line_height = 0
        spacing = self.spacing()

        for item in self.itemList:
            wid = item.widget()
            space_x = spacing + wid.style().layoutSpacing(QSizePolicy.ControlType.PushButton, QSizePolicy.ControlType.PushButton, Qt.Orientation.Horizontal)
            space_y = spacing + wid.style().layoutSpacing(QSizePolicy.ControlType.PushButton, QSizePolicy.ControlType.PushButton, Qt.Orientation.Vertical)
            
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPointF(x, y).toPoint(), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y()

class DraggableScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._is_dragging = False
        self._start_pos = QPointF()
        self._start_scroll_x = 0

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._start_pos = event.position()
            self._start_scroll_x = self.horizontalScrollBar().value()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_dragging:
            delta = event.position().x() - self._start_pos.x()
            self.horizontalScrollBar().setValue(int(self._start_scroll_x - delta))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        if event.angleDelta().y() != 0:
            scroll_val = self.horizontalScrollBar().value()
            self.horizontalScrollBar().setValue(scroll_val - event.angleDelta().y())
            event.accept()
        else:
            super().wheelEvent(event)

class ElidedLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._full_text = text
        self._elide_mode = Qt.TextElideMode.ElideMiddle
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0) 
    
    def setElideMode(self, mode):
        self._elide_mode = mode
        self.update()

    def setText(self, text):
        self._full_text = text
        self.setToolTip(text)
        self.update() 
        
    def paintEvent(self, event):
        painter = QPainter(self)
        metrics = self.fontMetrics()
        elided = metrics.elidedText(self._full_text, self._elide_mode, self.width())
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

class ElidedButton(QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._full_text = text
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(1) 
        self._update_elided_text()

    def setText(self, text):
        self._full_text = text
        self.setToolTip(text)
        self._update_elided_text()

    def resizeEvent(self, event):
        self._update_elided_text()
        super().resizeEvent(event)

    def _update_elided_text(self):
        width = self.width() - 10
        if width <= 0: return
        metrics = self.fontMetrics()
        elided = metrics.elidedText(self._full_text, Qt.TextElideMode.ElideRight, width)
        super().setText(elided)

class FolderLabel(QLabel):
    clicked = pyqtSignal()

    def __init__(self, text_prefix_key, path_getter, parent=None):
        super().__init__(parent)
        self.text_prefix_key = text_prefix_key
        self.path_getter = path_getter 
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        
        # Connect to Cache updates
        DirCache.inst().updated.connect(self._on_cache_updated)
        self.update_info()

    def _on_cache_updated(self, updated_path):
        current_path = self.path_getter()
        if current_path and os.path.normpath(current_path) == os.path.normpath(updated_path):
            self.update_info()

    def update_info(self):
        path = self.path_getter()
        prefix = AppContext.tr(self.text_prefix_key) 
        
        if path and os.path.exists(path):
            folder_name = os.path.basename(path)
            
            # Use Non-Blocking Cache
            count, size = DirCache.inst().get_data(path)
            
            size_str = format_size(size)
            display_text = f"{truncate_text(folder_name)}: {count} ({size_str})"
            self.setText(display_text)
            
            # Restore normal style (handled by parent logic usually, but ensure no 'empty' color)
            # We assume parent sets color.
            
            hint_open = AppContext.tr('tooltip_scroll_open_hint')
            hint_settings = AppContext.tr('tooltip_right_click_menu_hint')
            
            tooltip_text = (
                f"{prefix} ({folder_name}):\n"
                f"{path}\n\n"
                f"Files: {count} | Size: {size_str}\n\n"
                f"{hint_open}\n"
                f"{hint_settings}"
            )
            self.setToolTip(tooltip_text)
        else:
            # EMPTY STATE
            not_set_mark = AppContext.tr("lbl_not_set") # [?]
            self.setText(f"{prefix}: {not_set_mark}")
            
            # Detailed Tooltip
            detailed_tip = AppContext.tr("tip_folder_not_set_detailed")
            self.setToolTip(f"{prefix}\n{detailed_tip}")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        elif event.button() == Qt.MouseButton.MiddleButton:
            path = self.path_getter() 
            if path and os.path.exists(path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        super().mousePressEvent(event)

    def reset_style(self):
        """Reset any custom stylesheet applied to the label.
        Used when the folder is no longer the trash folder.
        """
        self.setStyleSheet("")

class DroppableButton(QPushButton):
    folder_dropped = pyqtSignal(str, bool)

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setAcceptDrops(True)

    def reset_style(self):
        self.setStyleSheet("")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        md = event.mimeData()
        if md.hasUrls():
            urls = md.urls()
            if urls:
                path = urls[0].toLocalFile()
                if os.path.isdir(path):
                    self.folder_dropped.emit(path, True)
                    event.accept()
                    return
        event.ignore()

class DropZoneWidget(QFrame):
    clicked = pyqtSignal()
    clear_default_requested = pyqtSignal()
    folder_dropped = pyqtSignal(str) 
    files_dropped = pyqtSignal(list) # New signal for multiple files 

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True) 
        self.setFixedHeight(100)
        self.setStyleSheet("""
            DropZoneWidget {
                background-color: rgba(255, 255, 255, 0.03);
                border: 2px dashed #555;
                border-radius: 8px;
                margin: 5px;
            }
            DropZoneWidget:hover {
                background-color: rgba(255, 255, 255, 0.05);
                border-color: #777;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(5)
        
        self.lbl_folder_name = QLabel("")
        self.lbl_folder_name.setStyleSheet("color: #aaa; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        self.lbl_folder_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_folder_name.hide()
        layout.addWidget(self.lbl_folder_name)

        self.lbl_text = QLabel(AppContext.tr("dz_text"))
        self.lbl_text.setStyleSheet("color: #777; font-size: 12px; border: none; background: transparent;")
        self.lbl_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_text)
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")

        self.btn_add = QPushButton(" +")
        self.btn_add.setIcon(QIcon(os.path.join(icons_dir, "folder-color.svg")))
        self.btn_add.setIconSize(QSize(16, 16))
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setFixedSize(80, 30)
        self.btn_add.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #888;
                border: 1px solid #555;
                border-radius: 15px;
                font-size: 14px;
                font-weight: bold;
                text-align: center;
            }
            QPushButton:hover {
                background-color: rgba(234, 179, 8, 0.1);
                color: white;
                border-color: #eab308;
            }
        """)
        self.btn_add.clicked.connect(self.clicked.emit)
        btn_layout.addWidget(self.btn_add)

        self.btn_clear = QPushButton("")
        self.btn_clear.setIcon(QIcon(os.path.join(icons_dir, "trash-color.svg")))
        self.btn_clear.setIconSize(QSize(16, 16))
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.setFixedSize(30, 30)
        self.btn_clear.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid #555;
                border-radius: 15px;
            }
            QPushButton:hover {
                background-color: #444;
                border-color: #ef4444;
            }
        """)
        self.btn_clear.setToolTip(AppContext.tr("dz_clear_tooltip"))
        self.btn_clear.clicked.connect(self.clear_default_requested.emit)
        self.btn_clear.hide() 
        btn_layout.addWidget(self.btn_clear)

        layout.addLayout(btn_layout)

    def update_ui_text(self):
        self.lbl_text.setText(AppContext.tr("dz_text"))
        self.btn_clear.setToolTip(AppContext.tr("dz_clear_tooltip"))

    def set_folder_info(self, path):
        if path and os.path.exists(path):
            name = os.path.basename(path) or path
            self.lbl_folder_name.setText(name)
            self.lbl_folder_name.show()
        else:
            self.lbl_folder_name.hide()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet("""
                DropZoneWidget {
                    background-color: rgba(59, 130, 246, 0.15);
                    border: 2px dashed #3b82f6;
                    border-radius: 8px;
                    margin: 5px;
                }
            """)
            super().dragEnterEvent(event) # Propagate correctly
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet("""
            DropZoneWidget {
                background-color: rgba(255, 255, 255, 0.03);
                border: 2px dashed #555;
                border-radius: 8px;
                margin: 5px;
            }
            DropZoneWidget:hover {
                background-color: rgba(255, 255, 255, 0.05);
                border-color: #777;
            }
        """)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        # Reset style manually instead of calling dragLeaveEvent with wrong event type
        self.setStyleSheet("""
            DropZoneWidget {
                background-color: rgba(255, 255, 255, 0.03);
                border: 2px dashed #555;
                border-radius: 8px;
                margin: 5px;
            }
            DropZoneWidget:hover {
                background-color: rgba(255, 255, 255, 0.05);
                border-color: #777;
            }
        """)

        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                # Handle both folders and files
                paths = [u.toLocalFile() for u in urls]
                # If single folder, use old logic for backward compatibility or check receiver
                # For now, we prefer a new signal for generic usage
                self.files_dropped.emit(paths)
                
                # Legacy support: if one folder, emit folder_dropped
                if len(paths) == 1 and os.path.isdir(paths[0]):
                    self.folder_dropped.emit(paths[0])
                    
                event.acceptProposedAction()
