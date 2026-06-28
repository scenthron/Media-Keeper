
import os
from PyQt6.QtWidgets import (
    QScrollArea, QFrame, QLabel, QSizePolicy, QLayout, QWidgetItem, QStyle,
    QPushButton, QVBoxLayout, QHBoxLayout, QDoubleSpinBox, QComboBox, QWidget
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

class CleanSpinBox(QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lineEdit().setPlaceholderText("0")
        
    def textFromValue(self, val):
        if val == 0: return ""
        if val.is_integer(): return str(int(val))
        return f"{val:.1f}".rstrip('0').rstrip('.')
        
    def valueFromText(self, text):
        if not text.strip(): return 0.0
        return super().valueFromText(text)

class SizeFilterWidget(QWidget):
    valueChanged = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        is_ru = (AppContext.LANG == "RU")
        
        # Шаблоны иконок chevron в base64
        UP_BASE64 = b'PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiNmZmZmZmYiIHN0cm9rZS13aWR0aD0iMyIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cGF0aCBkPSJtMTggMTUtNi02LTYgNiIvPjwvc3ZnPg=='
        DOWN_BASE64 = b'PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiNmZmZmZmYiIHN0cm9rZS13aWR0aD0iMyIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cGF0aCBkPSJtNiA5IDYgNiA2LTYiLz48L3N2Zz4='
        
        import base64
        from PyQt6.QtGui import QPixmap, QIcon
        
        def get_svg_icon(svg_b64):
            pix = QPixmap()
            pix.loadFromData(base64.b64decode(svg_b64))
            return QIcon(pix)
            
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)
        
        # --- БЛОК МИНИМУМА ---
        self.frame_min = QFrame()
        self.frame_min.setFixedHeight(26)
        self.frame_min.setFixedWidth(128)
        
        layout_min = QHBoxLayout(self.frame_min)
        layout_min.setContentsMargins(0, 0, 0, 0)
        layout_min.setSpacing(0)
        
        # 1. Кнопки стрелок (слева)
        arrows_min = QWidget()
        arrows_min.setFixedWidth(18)
        arrows_min.setFixedHeight(24)
        layout_arrows_min = QVBoxLayout(arrows_min)
        layout_arrows_min.setContentsMargins(0, 0, 0, 0)
        layout_arrows_min.setSpacing(0)
        
        self.btn_up_min = QPushButton()
        self.btn_up_min.setFixedHeight(12)
        self.btn_up_min.setIcon(get_svg_icon(UP_BASE64))
        self.btn_up_min.setIconSize(QSize(8, 8))
        self.btn_up_min.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_up_min.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_up_min.setStyleSheet("""
            QPushButton { border: none; background: rgba(0, 0, 0, 0.2); border-top-left-radius: 5px; }
            QPushButton:hover { background: rgba(255, 255, 255, 0.1); }
        """)
        
        self.btn_down_min = QPushButton()
        self.btn_down_min.setFixedHeight(12)
        self.btn_down_min.setIcon(get_svg_icon(DOWN_BASE64))
        self.btn_down_min.setIconSize(QSize(8, 8))
        self.btn_down_min.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_down_min.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_down_min.setStyleSheet("""
            QPushButton { border: none; background: rgba(0, 0, 0, 0.2); border-bottom-left-radius: 5px; }
            QPushButton:hover { background: rgba(255, 255, 255, 0.1); }
        """)
        
        layout_arrows_min.addWidget(self.btn_up_min)
        layout_arrows_min.addWidget(self.btn_down_min)
        layout_min.addWidget(arrows_min)
        
        # 2. Спинбокс (поле ввода)
        self.spin_min = CleanSpinBox()
        self.spin_min.setRange(0.0, 999999.0)
        self.spin_min.setDecimals(1)
        self.spin_min.setSingleStep(0.1)
        self.spin_min.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.spin_min.setFixedWidth(64)
        self.spin_min.setFixedHeight(24)
        self.spin_min.setStyleSheet("border: none; background: transparent; color: white; font-weight: bold; font-size: 12px; padding: 0 4px;")
        self.spin_min.valueChanged.connect(self.validate_inputs)
        
        self.btn_up_min.clicked.connect(self.spin_min.stepUp)
        self.btn_down_min.clicked.connect(self.spin_min.stepDown)
        layout_min.addWidget(self.spin_min)
        
        # 3. Комбобокс выбора единиц
        self.combo_unit_min = QComboBox()
        self.combo_unit_min.addItems(["KB", "MB", "GB"] if not is_ru else ["КБ", "МБ", "ГБ"])
        self.combo_unit_min.setCurrentIndex(1)
        self.combo_unit_min.setFixedWidth(42)
        self.combo_unit_min.setFixedHeight(24)
        self.combo_unit_min.setStyleSheet("""
            QComboBox { border: none; background: transparent; color: white; padding-left: 2px; }
            QComboBox::drop-down { border: none; width: 0px; }
            QComboBox QAbstractItemView { background-color: #2b2b2b; color: white; selection-background-color: #3b82f6; outline: none; }
        """)
        self.combo_unit_min.currentIndexChanged.connect(self.validate_inputs)
        layout_min.addWidget(self.combo_unit_min)
        
        main_layout.addWidget(self.frame_min)
        
        # --- РАЗДЕЛИТЕЛЬ ---
        self.lbl_separator = QLabel("-")
        self.lbl_separator.setStyleSheet("color: #888; font-weight: bold; background: transparent;")
        main_layout.addWidget(self.lbl_separator)
        
        # --- БЛОК МАКСИМУМА ---
        self.frame_max = QFrame()
        self.frame_max.setFixedHeight(26)
        self.frame_max.setFixedWidth(128)
        
        layout_max = QHBoxLayout(self.frame_max)
        layout_max.setContentsMargins(0, 0, 0, 0)
        layout_max.setSpacing(0)
        
        # 1. Кнопки стрелок (слева)
        arrows_max = QWidget()
        arrows_max.setFixedWidth(18)
        arrows_max.setFixedHeight(24)
        layout_arrows_max = QVBoxLayout(arrows_max)
        layout_arrows_max.setContentsMargins(0, 0, 0, 0)
        layout_arrows_max.setSpacing(0)
        
        self.btn_up_max = QPushButton()
        self.btn_up_max.setFixedHeight(12)
        self.btn_up_max.setIcon(get_svg_icon(UP_BASE64))
        self.btn_up_max.setIconSize(QSize(8, 8))
        self.btn_up_max.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_up_max.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_up_max.setStyleSheet("""
            QPushButton { border: none; background: rgba(0, 0, 0, 0.2); border-top-left-radius: 5px; }
            QPushButton:hover { background: rgba(255, 255, 255, 0.1); }
        """)
        
        self.btn_down_max = QPushButton()
        self.btn_down_max.setFixedHeight(12)
        self.btn_down_max.setIcon(get_svg_icon(DOWN_BASE64))
        self.btn_down_max.setIconSize(QSize(8, 8))
        self.btn_down_max.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_down_max.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_down_max.setStyleSheet("""
            QPushButton { border: none; background: rgba(0, 0, 0, 0.2); border-bottom-left-radius: 5px; }
            QPushButton:hover { background: rgba(255, 255, 255, 0.1); }
        """)
        
        layout_arrows_max.addWidget(self.btn_up_max)
        layout_arrows_max.addWidget(self.btn_down_max)
        layout_max.addWidget(arrows_max)
        
        # 2. Спинбокс (поле ввода)
        self.spin_max = CleanSpinBox()
        self.spin_max.setRange(0.0, 999999.0)
        self.spin_max.setDecimals(1)
        self.spin_max.setSingleStep(0.1)
        self.spin_max.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.spin_max.setFixedWidth(64)
        self.spin_max.setFixedHeight(24)
        self.spin_max.setStyleSheet("border: none; background: transparent; color: white; font-weight: bold; font-size: 12px; padding: 0 4px;")
        self.spin_max.valueChanged.connect(self.validate_inputs)
        
        self.btn_up_max.clicked.connect(self.spin_max.stepUp)
        self.btn_down_max.clicked.connect(self.spin_max.stepDown)
        layout_max.addWidget(self.spin_max)
        
        # 3. Комбобокс выбора единиц
        self.combo_unit_max = QComboBox()
        self.combo_unit_max.addItems(["KB", "MB", "GB"] if not is_ru else ["КБ", "МБ", "ГБ"])
        self.combo_unit_max.setCurrentIndex(1)
        self.combo_unit_max.setFixedWidth(42)
        self.combo_unit_max.setFixedHeight(24)
        self.combo_unit_max.setStyleSheet("""
            QComboBox { border: none; background: transparent; color: white; padding-left: 2px; }
            QComboBox::drop-down { border: none; width: 0px; }
            QComboBox QAbstractItemView { background-color: #2b2b2b; color: white; selection-background-color: #3b82f6; outline: none; }
        """)
        self.combo_unit_max.currentIndexChanged.connect(self.validate_inputs)
        layout_max.addWidget(self.combo_unit_max)
        
        main_layout.addWidget(self.frame_max)
        
        # --- КНОПКА СБРОСА ---
        self.btn_reset = QPushButton()
        self.btn_reset.setFixedSize(26, 26)
        self.btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset.setToolTip("Сбросить размер" if is_ru else "Reset size filter")
        self.btn_reset.clicked.connect(self.reset_values)
        
        icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
        self.btn_reset.setIcon(QIcon(os.path.join(icons_dir, "cross.svg")))
        self.btn_reset.setIconSize(QSize(10, 10))
        self.btn_reset.setStyleSheet("""
            QPushButton { 
                background-color: #333333; 
                border: 1px solid #555555; 
                border-radius: 4px;
            }
            QPushButton:hover { 
                background-color: #991b1b; 
                border-color: #b91c1c; 
            }
        """)
        main_layout.addWidget(self.btn_reset)
        
        self.validate_inputs()

    def get_min_bytes(self) -> int:
        val = self.spin_min.value()
        if val <= 0: return 0
        unit = self.combo_unit_min.currentIndex()
        return int(val * (1024 ** (unit + 1)))
        
    def get_max_bytes(self) -> int:
        val = self.spin_max.value()
        if val <= 0: return 0
        unit = self.combo_unit_max.currentIndex()
        return int(val * (1024 ** (unit + 1)))

    def get_min_mb(self) -> float:
        return self.get_min_bytes() / (1024 * 1024)
        
    def get_max_mb(self) -> float:
        return self.get_max_bytes() / (1024 * 1024)

    def set_values_mb(self, min_mb: float, max_mb: float):
        def auto_unit(val_bytes):
            if val_bytes <= 0:
                return 0.0, 1
            if val_bytes < 1024 * 1024:
                return val_bytes / 1024, 0
            if val_bytes < 1024 * 1024 * 1024:
                return val_bytes / (1024 * 1024), 1
            return val_bytes / (1024 * 1024 * 1024), 2
            
        min_val, min_unit = auto_unit(min_mb * 1024 * 1024)
        max_val, max_unit = auto_unit(max_mb * 1024 * 1024)
        
        self.spin_min.blockSignals(True)
        self.combo_unit_min.blockSignals(True)
        self.spin_max.blockSignals(True)
        self.combo_unit_max.blockSignals(True)
        
        self.spin_min.setValue(min_val)
        self.combo_unit_min.setCurrentIndex(min_unit)
        self.spin_max.setValue(max_val)
        self.combo_unit_max.setCurrentIndex(max_unit)
        
        self.spin_min.blockSignals(False)
        self.combo_unit_min.blockSignals(False)
        self.spin_max.blockSignals(False)
        self.combo_unit_max.blockSignals(False)
        
        self.validate_inputs()

    def set_values_bytes(self, min_bytes: int, max_bytes: int):
        self.set_values_mb(min_bytes / (1024 * 1024), max_bytes / (1024 * 1024))

    def reset_values(self):
        self.spin_min.setValue(0.0)
        self.spin_max.setValue(0.0)
        self.combo_unit_min.setCurrentIndex(1)
        self.combo_unit_max.setCurrentIndex(1)
        self.validate_inputs()

    def has_error(self) -> bool:
        min_b = self.get_min_bytes()
        max_b = self.get_max_bytes()
        return max_b > 0 and min_b > 0 and min_b >= max_b

    def validate_inputs(self):
        min_b = self.get_min_bytes()
        max_b = self.get_max_bytes()
        is_error = self.has_error()
        
        style_def = "QFrame { background: #1a1a1a; border: 1px solid #444; border-radius: 6px; }"
        style_ok = "QFrame { background: #14532d; border: 1px solid #16a34a; border-radius: 6px; }"
        style_err = "QFrame { background: #451a1a; border: 1px solid #ef4444; border-radius: 6px; }"
        
        if is_error:
            self.frame_min.setStyleSheet(style_err)
            self.frame_max.setStyleSheet(style_err)
        else:
            self.frame_min.setStyleSheet(style_ok if min_b > 0 else style_def)
            self.frame_max.setStyleSheet(style_ok if max_b > 0 else style_def)
            
        self.valueChanged.emit()

