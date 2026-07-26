import os
import tempfile
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, 
    QMenu, QRadioButton, QButtonGroup, QAbstractItemView, QStyledItemDelegate, QStyle
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QSize, QRect
from PyQt6.QtGui import QIcon, QPixmap, QColor, QPen, QPainter, QImage

from config import AppContext
from .logic_ai_dump import save_dump

class RemovableImageDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hovered_index = None

    def paint(self, painter: QPainter, option, index):
        super().paint(painter, option, index)
        
        # If hovered, draw a close button overlay
        if self.hovered_index is not None and self.hovered_index == index:
            rect = option.rect
            btn_rect = QRect(rect.right() - 20, rect.top() + 4, 16, 16)
            
            painter.save()
            painter.setBrush(QColor(255, 0, 0, 200))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(btn_rect)
            
            painter.setPen(QPen(Qt.GlobalColor.white, 2))
            painter.drawLine(btn_rect.left() + 4, btn_rect.top() + 4, btn_rect.right() - 4, btn_rect.bottom() - 4)
            painter.drawLine(btn_rect.right() - 4, btn_rect.top() + 4, btn_rect.left() + 4, btn_rect.bottom() - 4)
            painter.restore()

class FastSearchDropArea(QListWidget):
    cleared = pyqtSignal()
    cleared_all = pyqtSignal()
    
    def __init__(self, title_text, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(96, 96))
        self.setSpacing(8)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMouseTracking(True)
        
        self.delegate = RemovableImageDelegate(self)
        self.setItemDelegate(self.delegate)
        
        self.paths = []
        
        self.setStyleSheet("""
            QListWidget {
                background-color: #2b2b2b;
                border: 2px dashed #444;
                border-radius: 8px;
                padding: 10px;
            }
            QListWidget:hover {
                border-color: #3b82f6;
            }
            QListWidget::item {
                border-radius: 6px;
                background-color: #333;
            }
            QListWidget::item:selected {
                background-color: #3b82f6;
            }
        """)

    def _create_thumbnail(self, path: str) -> QPixmap:
        pixmap = QPixmap(path)
        if pixmap.isNull() and path.lower().endswith('.avif'):
            try:
                from PIL import Image
                with Image.open(path) as pil_img:
                    if pil_img.mode != 'RGB': pil_img = pil_img.convert('RGB')
                    data = pil_img.tobytes("raw", "RGB")
                    img = QImage(data, pil_img.width, pil_img.height, pil_img.width * 3, QImage.Format.Format_RGB888).copy()
                    pixmap = QPixmap.fromImage(img)
            except:
                pass
                
        if not pixmap.isNull():
            scaled = pixmap.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            square = QPixmap(96, 96)
            square.fill(Qt.GlobalColor.transparent)
            painter = QPainter(square)
            painter.drawPixmap((96 - scaled.width()) // 2, (96 - scaled.height()) // 2, scaled)
            painter.end()
            return square
        return QPixmap()

    def add_files(self, files: list[str]):
        valid_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.avif'}
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in valid_exts and f not in self.paths:
                self.paths.append(f)
                item = QListWidgetItem()
                item.setIcon(QIcon(self._create_thumbnail(f)))
                item.setData(Qt.ItemDataRole.UserRole, f)
                self.addItem(item)
                
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            
    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            
    def dropEvent(self, e):
        files = []
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if os.path.isfile(p):
                files.append(p)
            elif os.path.isdir(p):
                for root, _, fnames in os.walk(p):
                    for fname in fnames:
                        files.append(os.path.join(root, fname))
        self.add_files(files)
        e.acceptProposedAction()

    def mouseMoveEvent(self, e):
        item = self.itemAt(e.pos())
        if item:
            index = self.indexFromItem(item)
            if self.delegate.hovered_index != index:
                self.delegate.hovered_index = index
                self.viewport().update()
        else:
            if self.delegate.hovered_index is not None:
                self.delegate.hovered_index = None
                self.viewport().update()
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        if self.delegate.hovered_index is not None:
            self.delegate.hovered_index = None
            self.viewport().update()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(e.pos())
            if item:
                rect = self.visualItemRect(item)
                # Close button rect
                if e.pos().x() >= rect.right() - 20 and e.pos().y() <= rect.top() + 20:
                    self.paths.remove(item.data(Qt.ItemDataRole.UserRole))
                    self.takeItem(self.row(item))
                    self.delegate.hovered_index = None
                    return
        super().mousePressEvent(e)

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        a_clear = menu.addAction("Очистить" if AppContext.is_ru() else "Clear")
        a_clear_all = menu.addAction("Очистить всё" if AppContext.is_ru() else "Clear All")
        
        action = menu.exec(e.globalPos())
        if action == a_clear:
            self.clear_items()
            self.cleared.emit()
        elif action == a_clear_all:
            self.cleared_all.emit()
            
    def clear_items(self):
        self.clear()
        self.paths = []


class AiFastSearchWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_ru = AppContext.is_ru()
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Mode selector
        mode_layout = QHBoxLayout()
        self.btn_mode_faces = QRadioButton("Искать Лица" if self.is_ru else "Search Faces")
        self.btn_mode_general = QRadioButton("Общий контекст" if self.is_ru else "General Context")
        self.btn_mode_general.setChecked(True)
        
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.btn_mode_faces)
        self.mode_group.addButton(self.btn_mode_general)
        
        mode_layout.addWidget(self.btn_mode_faces)
        mode_layout.addWidget(self.btn_mode_general)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)
        
        # Drop areas
        self.pos_area = FastSearchDropArea("Позитивные образцы" if self.is_ru else "Positive Samples")
        self.neg_area = FastSearchDropArea("Антипаттерны" if self.is_ru else "Negative Samples")
        
        self.pos_area.cleared_all.connect(self.clear_all)
        self.neg_area.cleared_all.connect(self.clear_all)
        
        lbl_pos = QLabel("Позитивные образцы (что искать):" if self.is_ru else "Positive Samples:")
        lbl_pos.setStyleSheet("color: #aaa; font-weight: bold;")
        
        lbl_neg = QLabel("Негативные образцы (антипаттерны):" if self.is_ru else "Negative Samples:")
        lbl_neg.setStyleSheet("color: #aaa; font-weight: bold;")
        
        layout.addWidget(lbl_pos)
        layout.addWidget(self.pos_area)
        layout.addWidget(lbl_neg)
        layout.addWidget(self.neg_area)

    def clear_all(self):
        self.pos_area.clear_items()
        self.neg_area.clear_items()

    def get_search_type(self):
        return "face" if self.btn_mode_faces.isChecked() else "general"

    def get_pos_paths(self):
        return self.pos_area.paths
        
    def get_neg_paths(self):
        return self.neg_area.paths

    def generate_temp_dump(self) -> str:
        temp_file = os.path.join(tempfile.gettempdir(), "_fast_search.mkaidump")
        if os.path.exists(temp_file):
            try: os.remove(temp_file)
            except: pass
            
        save_dump(
            path=temp_file,
            search_type=self.get_search_type(),
            pos_image_paths=self.get_pos_paths(),
            neg_image_paths=self.get_neg_paths(),
            pos_features=[],
            neg_features=[],
            pos_faces=[],
            neg_faces=[],
            is_hash_only=False
        )
        return temp_file
