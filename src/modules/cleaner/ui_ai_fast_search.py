import os
import tempfile
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, 
    QMenu, QPushButton, QButtonGroup, QAbstractItemView, QStyledItemDelegate
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QSize, QRect
from PyQt6.QtGui import QIcon, QPixmap, QColor, QPen, QPainter, QImage

from config import AppContext
from .logic_ai_dump import save_dump
from logic_paths import get_app_data_dir
import shutil
import uuid

class RemovableImageDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hovered_index = None

    def paint(self, painter: QPainter, option, index):
        super().paint(painter, option, index)
        
        path = index.data(Qt.ItemDataRole.UserRole)
        is_defective = hasattr(self, 'defective_paths') and path in self.defective_paths
        
        if is_defective:
            rect = option.rect
            painter.save()
            painter.setBrush(QColor(255, 0, 0, 100))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(rect)
            
            painter.setPen(QPen(QColor(255, 0, 0, 200), 4))
            center_x = rect.center().x()
            center_y = rect.center().y()
            sz = min(rect.width(), rect.height()) // 3
            painter.drawLine(center_x - sz, center_y - sz, center_x + sz, center_y + sz)
            painter.drawLine(center_x + sz, center_y - sz, center_x - sz, center_y + sz)
            painter.restore()

        # If hovered, draw a close button overlay on top
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
    paths_changed = pyqtSignal()
    
    def __init__(self, title_text, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(48, 48))
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
                padding: 5px;
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

    def set_defective_paths(self, paths: list[str]):
        self.delegate.defective_paths = paths
        self.viewport().update()

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
            scaled = pixmap.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            square = QPixmap(48, 48)
            square.fill(Qt.GlobalColor.transparent)
            painter = QPainter(square)
            painter.drawPixmap((48 - scaled.width()) // 2, (48 - scaled.height()) // 2, scaled)
            painter.end()
            return square
        return QPixmap()

    def add_files(self, files: list[str]):
        valid_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.avif'}
        temp_dir = os.path.join(get_app_data_dir(), "Ai_assets", "Temp", "FastSearch")
        os.makedirs(temp_dir, exist_ok=True)
        
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in valid_exts:
                # To prevent duplicates in UI, we check if the ORIGINAL file was already added.
                # But since we store temp paths in self.paths, we'll just check if a file with this original name was added?
                # Actually, self.paths will contain temp paths, so `f not in self.paths` will always be true if they drop it again.
                # To keep it simple, we'll just copy it.
                
                new_filename = f"{uuid.uuid4().hex}{ext}"
                temp_path = os.path.join(temp_dir, new_filename)
                
                try:
                    shutil.copy2(f, temp_path)
                    self.paths.append(temp_path)
                    item = QListWidgetItem()
                    item.setIcon(QIcon(self._create_thumbnail(temp_path)))
                    item.setData(Qt.ItemDataRole.UserRole, temp_path)
                    self.addItem(item)
                except Exception as e:
                    import logging
                    logging.error(f"Failed to copy {f} to temp for Fast Search: {e}")
        self.paths_changed.emit()
                
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
                    path_to_remove = item.data(Qt.ItemDataRole.UserRole)
                    self.paths.remove(path_to_remove)
                    try: os.remove(path_to_remove)
                    except: pass
                    self.takeItem(self.row(item))
                    self.delegate.hovered_index = None
                    self.paths_changed.emit()
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
        for p in self.paths:
            try: os.remove(p)
            except: pass
        self.clear()
        self.paths = []


class AiFastSearchWidget(QWidget):
    paths_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_ru = AppContext.is_ru()
        self._init_temp_dir()
        self._init_ui()
        
    def _init_temp_dir(self):
        temp_dir = os.path.join(get_app_data_dir(), "Ai_assets", "Temp", "FastSearch")
        if os.path.exists(temp_dir):
            try: shutil.rmtree(temp_dir)
            except: pass
        os.makedirs(temp_dir, exist_ok=True)
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Drop areas (Horizontal layout: Pos on left, Neg on right)
        areas_layout = QHBoxLayout()
        
        # Positive column
        pos_col = QVBoxLayout()
        lbl_pos = QLabel("Позитивные образцы:" if self.is_ru else "Positive Samples:")
        lbl_pos.setStyleSheet("color: #aaa; font-weight: bold;")
        self.pos_area = FastSearchDropArea("Позитивные образцы" if self.is_ru else "Positive Samples")
        pos_col.addWidget(lbl_pos)
        pos_col.addWidget(self.pos_area)
        
        # Negative column
        neg_col = QVBoxLayout()
        lbl_neg = QLabel("Антипаттерны:" if self.is_ru else "Negative Samples:")
        lbl_neg.setStyleSheet("color: #aaa; font-weight: bold;")
        self.neg_area = FastSearchDropArea("Антипаттерны" if self.is_ru else "Negative Samples")
        neg_col.addWidget(lbl_neg)
        neg_col.addWidget(self.neg_area)
        
        areas_layout.addLayout(pos_col)
        areas_layout.addLayout(neg_col)
        
        self.pos_area.cleared_all.connect(self.clear_all)
        self.neg_area.cleared_all.connect(self.clear_all)
        self.pos_area.paths_changed.connect(self.paths_changed.emit)
        self.neg_area.paths_changed.connect(self.paths_changed.emit)
        
        layout.addLayout(areas_layout)

        # Mode selector
        mode_layout = QHBoxLayout()
        self.btn_mode_faces = QPushButton("Искать Лица" if self.is_ru else "Search Faces")
        self.btn_mode_general = QPushButton("Общий контекст" if self.is_ru else "General Context")
        
        mode_style = """
            QPushButton { background-color: #2b2b2b; color: #888; border: 1px solid #444; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
            QPushButton:checked { background-color: #16a34a; color: white; border-color: #15803d; }
            QPushButton:hover:!checked { background-color: #333; }
        """
        self.btn_mode_faces.setStyleSheet(mode_style)
        self.btn_mode_general.setStyleSheet(mode_style)
        self.btn_mode_faces.setCheckable(True)
        self.btn_mode_general.setCheckable(True)
        self.btn_mode_faces.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mode_general.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.btn_mode_faces.setChecked(True)
        
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.btn_mode_faces)
        self.mode_group.addButton(self.btn_mode_general)
        
        mode_layout.addStretch()
        mode_layout.addWidget(self.btn_mode_faces)
        mode_layout.addWidget(self.btn_mode_general)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)

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
