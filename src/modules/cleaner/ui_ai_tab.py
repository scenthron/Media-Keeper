import os
import shutil
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QSlider,
    QTreeWidget, QTreeWidgetItem, QProgressBar, QDialog, QLineEdit,
    QRadioButton, QButtonGroup, QAbstractItemView, QMenu, QSplitter,
    QScrollArea, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer, QPoint, QEvent
from PyQt6.QtGui import QIcon, QPixmap, QColor, QAction, QCursor

from config import AppContext, APP_DESIGN
from ui_widgets_base import DropZoneWidget
from .logic_ai import AiEngine
from .logic_ai_cache import AiCacheManager
from .logic_ai_classifier import AiClassifier, load_ai_settings, save_ai_settings, get_ai_assets_dir
from .workers import AiScanWorker, STAGE_SCANNING, STAGE_ANALYSIS

# -----------------------------------------------------------------------------
# Всплывающее окно быстрого просмотра картинок при наведении мыши
# -----------------------------------------------------------------------------
class ImageHoverToolTip(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet("background-color: #2b2b2b; border: 2px solid #3b82f6; padding: 2px; border-radius: 6px;")
        self.setScaledContents(True)
        self.setFixedSize(260, 260)
        self.hide()
        
    def show_image(self, path: str, pos: QPoint):
        if not path or not os.path.exists(path):
            self.hide()
            return
            
        try:
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(250, 250, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.setPixmap(scaled)
                self.setFixedSize(scaled.width() + 8, scaled.height() + 8)
                
                # Позиционируем правее и ниже курсора, чтобы не перекрывать его
                self.move(pos.x() + 15, pos.y() + 15)
                self.show()
            else:
                self.hide()
        except Exception:
            self.hide()


# -----------------------------------------------------------------------------
# Кастомный список для картинок-примеров с поддержкой Drag & Drop и Hover-превью
# -----------------------------------------------------------------------------
class RefImagesListWidget(QListWidget):
    files_dropped = pyqtSignal(list)
    item_hovered = pyqtSignal(str, QPoint)
    hover_left = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(76, 76))
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setGridSize(QSize(86, 86))
        self.setMouseTracking(True)
        self.setStyleSheet("""
            QListWidget {
                background-color: #151515;
                border: 1px solid #444;
                border-radius: 6px;
                outline: none;
            }
            QListWidget::item {
                border: 1px solid transparent;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background-color: #2a2a2a;
                border: 1px solid #555;
            }
            QListWidget::item:selected {
                background-color: #3b82f6;
                border: 1px solid #2563eb;
            }
        """)
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dropEvent(self, event):
        files = []
        for url in event.mimeData().urls():
            fp = url.toLocalFile()
            if os.path.isfile(fp):
                ext = os.path.splitext(fp)[1].lower()
                if ext in {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}:
                    files.append(fp)
        if files:
            self.files_dropped.emit(files)
            event.acceptProposedAction()

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        item = self.itemAt(event.pos())
        if item:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path:
                # Переводим координаты в глобальные
                glob_pos = self.mapToGlobal(event.pos())
                self.item_hovered.emit(path, glob_pos)
        else:
            self.hover_left.emit()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.hover_left.emit()


# -----------------------------------------------------------------------------
# Диалог настроек группы эталонов (вызывается при клике по шестеренке)
# -----------------------------------------------------------------------------
class EditAiGroupDialog(QDialog):
    def __init__(self, group_name: str, classifier, parent=None):
        super().__init__(parent)
        self.group_name = group_name
        self.classifier = classifier
        self.is_ru = AppContext.is_ru()
        self.has_changes = False
        
        self.setWindowTitle(f"Настройка эталона: {group_name}" if self.is_ru else f"Edit Reference: {group_name}")
        self.setFixedSize(500, 480)
        self.setStyleSheet("background-color: #202020; color: white;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        
        # 1. Изменение имени
        layout.addWidget(QLabel("Имя группы:" if self.is_ru else "Group Name:"))
        self.txt_name = QLineEdit(group_name)
        self.txt_name.setMinimumHeight(32)
        self.txt_name.setStyleSheet("""
            QLineEdit {
                background-color: #2b2b2b; 
                border: 1px solid #444; 
                padding: 4px 8px; 
                border-radius: 4px; 
                color: white;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #3b82f6;
            }
        """)
        layout.addWidget(self.txt_name)
        
        # 2. Тип анализа
        layout.addWidget(QLabel("Тип анализа:" if self.is_ru else "Analysis Type:"))
        
        settings = load_ai_settings()
        group_info = settings.get("groups", {}).get(group_name, {})
        is_face_type = group_info.get("type") == "face"
        
        self.btn_group = QButtonGroup(self)
        self.rad_general = QRadioButton("Общее сходство изображений" if self.is_ru else "General Image Similarity")
        self.rad_face = QRadioButton("Поиск конкретных лиц людей" if self.is_ru_face() else "Face Recognition (People)")
        
        self.btn_group.addButton(self.rad_general, 0)
        self.btn_group.addButton(self.rad_face, 1)
        
        if is_face_type:
            self.rad_face.setChecked(True)
        else:
            self.rad_general.setChecked(True)
            
        type_layout = QHBoxLayout()
        type_layout.addWidget(self.rad_general)
        type_layout.addWidget(self.rad_face)
        layout.addLayout(type_layout)
        
        # 3. Перетаскивание картинок-примеров
        lbl_drop = QLabel("Перетащите файлы картинок (.png, .jpg) прямо в поле ниже:" if self.is_ru else "Drag and drop image files (.png, .jpg) directly to the area below:")
        lbl_drop.setStyleSheet("color: #aaa; font-size: 11px; font-style: italic;")
        layout.addWidget(lbl_drop)
        
        self.list_ref_images = RefImagesListWidget(self)
        self.list_ref_images.files_dropped.connect(self.add_dropped_files)
        
        # Подключаем всплывающее превью
        self.hover_tooltip = ImageHoverToolTip(self)
        self.list_ref_images.item_hovered.connect(self.hover_tooltip.show_image)
        self.list_ref_images.hover_left.connect(self.hover_tooltip.hide)
        
        layout.addWidget(self.list_ref_images, 1)
        
        # Кнопки под списком
        btn_list_layout = QHBoxLayout()
        self.btn_add_file = QPushButton("Добавить файл" if self.is_ru else "Add File")
        self.btn_add_file.setStyleSheet("background-color: #444; border: 1px solid #555; padding: 6px 12px; border-radius: 4px;")
        self.btn_add_file.clicked.connect(self.choose_files)
        
        self.btn_del_file = QPushButton("Удалить выбранные" if self.is_ru else "Delete Selected")
        self.btn_del_file.setStyleSheet("background-color: #ef4444; border: none; padding: 6px 12px; border-radius: 4px;")
        self.btn_del_file.clicked.connect(self.delete_selected_files)
        
        btn_list_layout.addWidget(self.btn_add_file)
        btn_list_layout.addWidget(self.btn_del_file)
        btn_list_layout.addStretch()
        layout.addLayout(btn_list_layout)
        
        # Кнопки сохранения
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        self.btn_cancel = QPushButton("Отмена" if self.is_ru else "Cancel")
        self.btn_cancel.setStyleSheet("background-color: #333; border: 1px solid #555; padding: 6px 16px; border-radius: 4px;")
        self.btn_cancel.clicked.connect(self.reject)
        
        self.btn_save = QPushButton("Сохранить" if self.is_ru else "Save")
        self.btn_save.setStyleSheet("background-color: #3b82f6; border: none; padding: 6px 16px; border-radius: 4px; font-weight: bold;")
        self.btn_save.clicked.connect(self.save_settings)
        
        buttons_layout.addWidget(self.btn_cancel)
        buttons_layout.addWidget(self.btn_save)
        layout.addLayout(buttons_layout)
        
        self.reload_thumbnails()

    def is_ru_face(self) -> bool:
        return AppContext.is_ru()

    def reload_thumbnails(self):
        """Загружает миниатюры картинок эталона."""
        self.list_ref_images.clear()
        group_dir = os.path.join(get_ai_assets_dir(), self.group_name)
        if not os.path.exists(group_dir):
            return
            
        valid_exts = {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}
        try:
            files = [
                f for f in os.listdir(group_dir)
                if os.path.isfile(os.path.join(group_dir, f)) and os.path.splitext(f)[1].lower() in valid_exts
            ]
            for f in files:
                fp = os.path.join(group_dir, f)
                item = QListWidgetItem()
                item.setIcon(QIcon(fp))
                item.setData(Qt.ItemDataRole.UserRole, fp)
                item.setToolTip(f)
                self.list_ref_images.addItem(item)
        except Exception as e:
            logging.error(f"Ошибка загрузки миниатюр эталона: {e}")

    def add_dropped_files(self, paths: list):
        """Копирует файлы, перетащенные в DropZone списка."""
        group_dir = os.path.join(get_ai_assets_dir(), self.group_name)
        os.makedirs(group_dir, exist_ok=True)
        
        for fp in paths:
            dest = os.path.join(group_dir, os.path.basename(fp))
            try:
                shutil.copy2(fp, dest)
            except Exception as e:
                logging.error(f"Ошибка копирования эталона {fp}: {e}")
                
        self.reload_thumbnails()
        self.has_changes = True

    def choose_files(self):
        """Открывает диалог для ручного выбора файлов-примеров."""
        files, _ = QFileDialog.getOpenFileNames(
            self, 
            "Выберите картинки-эталоны" if self.is_ru else "Select Reference Images",
            "", 
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if files:
            self.add_dropped_files(files)

    def delete_selected_files(self):
        """Удаляет выбранные картинки-примеры с диска."""
        selected = self.list_ref_images.selectedItems()
        if not selected:
            return
            
        for item in selected:
            fp = item.data(Qt.ItemDataRole.UserRole)
            if fp and os.path.exists(fp):
                try:
                    os.remove(fp)
                except Exception as e:
                    logging.error(f"Не удалось удалить файл примера {fp}: {e}")
                    
        self.reload_thumbnails()
        self.has_changes = True

    def save_settings(self):
        """Сохраняет новое имя группы и её тип."""
        new_name = self.txt_name.text().strip()
        new_name = "".join(c for c in new_name if c.isalnum() or c in " _-").strip()
        if not new_name:
            QMessageBox.warning(self, "Ошибка" if self.is_ru else "Error", 
                                "Некорректное имя группы!" if self.is_ru else "Invalid group name!")
            return
            
        # Обновляем имя и тип в json
        settings = load_ai_settings()
        groups = settings.get("groups", {})
        
        # Если имя изменилось
        if new_name != self.group_name:
            if new_name in groups:
                QMessageBox.warning(self, "Ошибка" if self.is_ru else "Error", 
                                    "Группа с таким именем уже существует!" if self.is_ru else "Group already exists!")
                return
                
            # Переименовываем папку
            old_dir = os.path.join(get_ai_assets_dir(), self.group_name)
            new_dir = os.path.join(get_ai_assets_dir(), new_name)
            if os.path.exists(old_dir):
                try:
                    os.rename(old_dir, new_dir)
                except Exception as e:
                    logging.error(f"Ошибка переименования папки эталона: {e}")
                    QMessageBox.critical(self, "Ошибка" if self.is_ru else "Error", 
                                         "Не удалось переименовать каталог эталона!" if self.is_ru else "Failed to rename reference directory!")
                    return
            
            # Переносим запись в json
            info = groups.pop(self.group_name)
            groups[new_name] = info
            self.group_name = new_name
            self.has_changes = True
            
        # Обновляем тип
        selected_type = "face" if self.rad_face.isChecked() else "general"
        if groups[self.group_name].get("type") != selected_type:
            groups[self.group_name]["type"] = selected_type
            self.has_changes = True
            
        if self.has_changes:
            save_ai_settings(settings)
            
        self.accept()


# -----------------------------------------------------------------------------
# Диалог создания нового эталона
# -----------------------------------------------------------------------------
class CreateAiGroupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        is_ru = AppContext.is_ru()
        self.setWindowTitle("Создать группу эталонов" if is_ru else "Create Reference Group")
        self.setFixedSize(350, 210)
        self.setStyleSheet("background-color: #2b2b2b; color: white;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        layout.addWidget(QLabel("Имя группы:" if is_ru else "Group Name:"))
        self.txt_name = QLineEdit()
        self.txt_name.setMinimumHeight(32) # Защита от обрезания на Windows
        self.txt_name.setStyleSheet("""
            QLineEdit {
                background-color: #333; 
                border: 1px solid #555; 
                padding: 4px 8px; 
                border-radius: 4px; 
                color: white;
                font-size: 13px;
            }
        """)
        layout.addWidget(self.txt_name)
        
        layout.addWidget(QLabel("Тип анализа:" if is_ru else "Analysis Type:"))
        
        self.btn_group = QButtonGroup(self)
        self.rad_general = QRadioButton("Общее сходство изображений" if is_ru else "General Image Similarity")
        self.rad_general.setChecked(True)
        self.rad_face = QRadioButton("Поиск конкретных лиц людей" if is_ru else "Face Recognition (People)")
        
        self.btn_group.addButton(self.rad_general, 0)
        self.btn_group.addButton(self.rad_face, 1)
        
        layout.addWidget(self.rad_general)
        layout.addWidget(self.rad_face)
        
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        self.btn_cancel = QPushButton("Отмена" if is_ru else "Cancel")
        self.btn_cancel.setStyleSheet("background-color: #444; border: none; padding: 6px 12px; border-radius: 4px;")
        self.btn_cancel.clicked.connect(self.reject)
        
        self.btn_ok = QPushButton("Создать" if is_ru else "Create")
        self.btn_ok.setStyleSheet("background-color: #3b82f6; border: none; padding: 6px 12px; border-radius: 4px; font-weight: bold;")
        self.btn_ok.clicked.connect(self.accept)
        
        buttons_layout.addWidget(self.btn_cancel)
        buttons_layout.addWidget(self.btn_ok)
        layout.addLayout(buttons_layout)


# -----------------------------------------------------------------------------
# Чекбокс с кастомным дизайном в стиле Cleaner
# -----------------------------------------------------------------------------
class QCheckBoxCustom(QPushButton):
    toggled = pyqtSignal(bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(16, 16)
        self.clicked.connect(self._on_clicked)
        self.update_style()
        
    def _on_clicked(self):
        self.toggled.emit(self.isChecked())
        self.update_style()
        
    def setChecked(self, checked):
        super().setChecked(checked)
        self.update_style()
        
    def update_style(self):
        if self.isChecked():
            self.setStyleSheet("background-color: #3b82f6; border: 1px solid #2563eb; border-radius: 3px; color: white; font-size: 10px; font-weight: bold;")
            self.setText("✓")
        else:
            self.setStyleSheet("background-color: #333; border: 1px solid #555; border-radius: 3px;")
            self.setText("")


# -----------------------------------------------------------------------------
# Горизонтальный чип (плашка) эталона в верхней панели настроек
# -----------------------------------------------------------------------------
class AiGroupChipWidget(QFrame):
    state_changed = pyqtSignal(str, bool)
    settings_clicked = pyqtSignal(str)
    
    def __init__(self, name: str, is_enabled: bool, is_face: bool, status_color: str, count: int, parent=None):
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
        
        # 1. Чекбокс активности
        self.chk = QCheckBoxCustom()
        self.chk.setChecked(is_enabled)
        self.chk.toggled.connect(lambda checked: self.state_changed.emit(self.group_name, checked))
        layout.addWidget(self.chk)
        
        # 2. Иконка типа
        self.lbl_icon = QLabel()
        self.lbl_icon.setFixedSize(14, 14)
        self.lbl_icon.setText("👤" if is_face else "🖼️")
        self.lbl_icon.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(self.lbl_icon)
        
        # 3. Название + счетчик
        self.lbl_name = QLabel(f"{name} [{count}]")
        self.lbl_name.setStyleSheet("font-weight: bold; color: #eee; font-size: 12px; border: none; background: transparent;")
        layout.addWidget(self.lbl_name)
        
        # 4. Круглый статус-индикатор
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(8, 8)
        self.update_status_dot(status_color)
        layout.addWidget(self.status_dot)
        
        # 5. Шестеренка настроек ⚙️
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


# -----------------------------------------------------------------------------
# Основная вкладка ИИ-классификации с новым дизайном (по аналогии с Cleaner)
# -----------------------------------------------------------------------------
class AiClassificationTab(QWidget):
    scan_started = pyqtSignal()
    scan_finished = pyqtSignal()
    file_selected = pyqtSignal(str)
    
    def __init__(self, cleaner_module, parent=None):
        super().__init__(parent)
        self.cleaner = cleaner_module
        
        # Бэкенд
        self.ai = AiEngine()
        self.cache = AiCacheManager()
        self.classifier = AiClassifier(self.cache, self.ai)
        
        self.active_worker = None
        
        self._init_ui()
        self.reload_groups()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # =====================================================================
        # ВЕРХНЯЯ ЧАСТЬ: Настройки (3 колонки настроек бок о бок)
        # =====================================================================
        self.top_settings = QFrame()
        self.top_settings.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.top_settings.setStyleSheet("background-color: #1e1e1e; border-bottom: 1px solid #2d2d2d;")
        top_layout = QHBoxLayout(self.top_settings)
        top_layout.setContentsMargins(15, 6, 15, 6)
        top_layout.setSpacing(12)
        
        # ---------------------------------------------------------------------
        # КОЛОНКА 1: Группы эталонов
        # ---------------------------------------------------------------------
        col_ref = QVBoxLayout()
        col_ref.setContentsMargins(0, 0, 0, 0)
        col_ref.setSpacing(4)
        
        ref_header = QHBoxLayout()
        ref_title = QLabel("Группы эталонов" if AppContext.is_ru() else "Reference Groups")
        ref_title.setStyleSheet("font-weight: bold; color: #888; font-size: 11px; font-family: 'Segoe UI';")
        ref_header.addWidget(ref_title)
        
        self.btn_create_ref = QPushButton("[+] Создать" if AppContext.is_ru() else "[+] Create")
        self.btn_create_ref.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_create_ref.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6; 
                color: white; 
                border: none; 
                padding: 2px 8px; 
                border-radius: 3px; 
                font-weight: bold; 
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
        """)
        self.btn_create_ref.clicked.connect(self.create_group)
        ref_header.addWidget(self.btn_create_ref)
        ref_header.addStretch()
        col_ref.addLayout(ref_header)
        
        # Scroll area для чипов эталонов
        scroll_ref = QScrollArea()
        scroll_ref.setWidgetResizable(True)
        scroll_ref.setFixedHeight(120)
        scroll_ref.setStyleSheet("QScrollArea { border: 1px solid #333; background-color: #111; border-radius: 4px; }")
        
        self.ref_container = QWidget()
        self.ref_container.setStyleSheet("background-color: #111;")
        self.group_list_layout_ai = QVBoxLayout(self.ref_container)
        self.group_list_layout_ai.setContentsMargins(5, 5, 5, 5)
        self.group_list_layout_ai.setSpacing(4)
        self.group_list_layout_ai.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        scroll_ref.setWidget(self.ref_container)
        col_ref.addWidget(scroll_ref)
        top_layout.addLayout(col_ref, 1)
        
        # ---------------------------------------------------------------------
        # КОЛОНКА 2: Каталоги для поиска (ИИ-каталоги)
        # ---------------------------------------------------------------------
        col_dirs = QVBoxLayout()
        col_dirs.setContentsMargins(0, 0, 0, 0)
        col_dirs.setSpacing(4)
        
        dirs_header = QHBoxLayout()
        dirs_title = QLabel("Каталоги для поиска" if AppContext.is_ru() else "Folders to Search")
        dirs_title.setStyleSheet("font-weight: bold; color: #888; font-size: 11px; font-family: 'Segoe UI';")
        dirs_header.addWidget(dirs_title)
        dirs_header.addStretch()
        col_dirs.addLayout(dirs_header)
        
        # Интегрируем DropZone и ScrollArea для папок (аналогично дубликаторам)
        self.sources_list_widget_ai = QWidget()
        self.sources_list_widget_ai.setStyleSheet("QWidget { background-color: #111111; }")
        self.folder_list_layout_ai = QVBoxLayout(self.sources_list_widget_ai)
        self.folder_list_layout_ai.setContentsMargins(2, 2, 2, 2)
        self.folder_list_layout_ai.setSpacing(4)
        self.folder_list_layout_ai.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        scroll_dirs = QScrollArea()
        scroll_dirs.setWidgetResizable(True)
        scroll_dirs.setFixedHeight(75)
        scroll_dirs.setStyleSheet("QScrollArea { border: 1px solid #333; background-color: #111; border-radius: 4px; }")
        scroll_dirs.setWidget(self.sources_list_widget_ai)
        col_dirs.addWidget(scroll_dirs)
        
        # Дроп-зона папок
        self.drop_zone_ai = DropZoneWidget()
        self.drop_zone_ai.setFixedHeight(40)
        self.drop_zone_ai.clicked.connect(self.cleaner.add_folder)
        self.drop_zone_ai.folder_dropped.connect(self.cleaner.add_folder_path)
        self.drop_zone_ai.btn_clear.clicked.connect(self.cleaner.clear_folders)
        self.drop_zone_ai.setStyleSheet(self.drop_zone_ai.styleSheet() + "margin: 0px; padding: 0px;")
        col_dirs.addWidget(self.drop_zone_ai)
        
        top_layout.addLayout(col_dirs, 1)
        
        # ---------------------------------------------------------------------
        # КОЛОНКА 3: Параметры поиска
        # ---------------------------------------------------------------------
        col_params = QVBoxLayout()
        col_params.setContentsMargins(0, 0, 0, 0)
        col_params.setSpacing(4)
        
        params_title = QLabel("Параметры ИИ поиска" if AppContext.is_ru() else "AI Search Parameters")
        params_title.setStyleSheet("font-weight: bold; color: #888; font-size: 11px; font-family: 'Segoe UI'; padding: 2px 0px;")
        col_params.addWidget(params_title)
        
        params_container = QFrame()
        params_container.setFixedHeight(120)
        params_container.setStyleSheet("QFrame { background-color: #111; border: 1px solid #333; border-radius: 4px; }")
        params_sub_layout = QVBoxLayout(params_container)
        params_sub_layout.setContentsMargins(8, 8, 8, 8)
        params_sub_layout.setSpacing(8)
        
        # Ползунок минимальной схожести
        self.lbl_threshold = QLabel("Схожесть: 75%" if AppContext.is_ru() else "Similarity: 75%")
        self.lbl_threshold.setStyleSheet("color: #ccc; font-weight: bold; font-size: 11px; border: none; background: transparent;")
        params_sub_layout.addWidget(self.lbl_threshold)
        
        self.slider_threshold = QSlider(Qt.Orientation.Horizontal)
        self.slider_threshold.setRange(50, 100)
        self.slider_threshold.setValue(75)
        self.slider_threshold.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #333; border-radius: 2px; }
            QSlider::handle:horizontal { background: #3b82f6; width: 12px; height: 12px; margin-top: -4px; margin-bottom: -4px; border-radius: 6px; }
        """)
        self.slider_threshold.valueChanged.connect(self.on_threshold_changed)
        params_sub_layout.addWidget(self.slider_threshold)
        
        # Кнопка пуска
        self.btn_start_scan = QPushButton("Начать ИИ Поиск" if AppContext.is_ru() else "Start AI Search")
        self.btn_start_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start_scan.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6; 
                color: white; 
                border: none; 
                padding: 6px; 
                border-radius: 4px; 
                font-weight: bold; 
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
            QPushButton:disabled {
                background-color: #222;
                color: #555;
            }
        """)
        self.btn_start_scan.clicked.connect(self.toggle_scan)
        params_sub_layout.addWidget(self.btn_start_scan)
        
        col_params.addWidget(params_container)
        top_layout.addLayout(col_params, 1)
        
        main_layout.addWidget(self.top_settings)
        
        # Прогресс-бар сканирования
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #151515;
                text-align: center;
                color: white;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background-color: #3b82f6;
            }
        """)
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)
        
        # Статистика найденного
        self.lbl_stats = QLabel("")
        self.lbl_stats.setStyleSheet("color: #4ade80; font-weight: bold; font-size: 12px; border: none; padding: 4px 15px; background-color: #1e1e1e;")
        main_layout.addWidget(self.lbl_stats)
        
        # =====================================================================
        # СРЕДНЯЯ ЧАСТЬ: Панель действий CleanerActionBar
        # =====================================================================
        from .ui_panels import CleanerActionBar
        self.action_bar = CleanerActionBar()
        self.action_bar.is_similar_mode = False
        self.action_bar.combo_autoselect.hide()
        self.action_bar.deselect_clicked.connect(lambda: self.select_all_results(False))
        self.action_bar.select_all_clicked.connect(lambda: self.select_all_results(True))
        
        self.action_bar.move_clicked.connect(self.cleaner.move_selected)
        self.action_bar.move_to_clicked.connect(self.cleaner.prompt_move_selected)
        self.action_bar.delete_clicked.connect(self.cleaner.delete_selected)
        self.action_bar.browse_clicked.connect(self.cleaner.browse_dest)
        self.action_bar.drop_zone.path_changed.connect(self.cleaner.validate_move_state)
        
        main_layout.addWidget(self.action_bar)
        
        # =====================================================================
        # НИЖНЯЯ ЧАСТЬ: Результаты (Сплиттер)
        # =====================================================================
        self.right_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.right_splitter.setHandleWidth(2)
        self.right_splitter.setStyleSheet("QSplitter::handle { background-color: #2d2d2d; }")
        
        # Таблица результатов
        self.tree_results = QTreeWidget()
        self.tree_results.setColumnCount(4)
        self.tree_results.setHeaderLabels([
            "Имя файла" if AppContext.is_ru() else "File Name",
            "Сходство (%)" if AppContext.is_ru() else "Similarity (%)",
            "Размер" if AppContext.is_ru() else "Size",
            "Путь" if AppContext.is_ru() else "Path"
        ])
        self.tree_results.setColumnWidth(0, 240)
        self.tree_results.setColumnWidth(1, 100)
        self.tree_results.setColumnWidth(2, 90)
        self.tree_results.setStyleSheet("""
            QTreeWidget {
                background-color: #1a1a1a;
                border: none;
                outline: none;
                color: #eee;
            }
            QTreeWidget::item {
                padding: 6px;
                border-bottom: 1px solid #222;
            }
            QTreeWidget::item:selected {
                background-color: #2b2b2b;
            }
        """)
        self.tree_results.itemSelectionChanged.connect(self.on_tree_selection_changed)
        self.tree_results.itemChanged.connect(self.on_tree_item_changed)
        self.right_splitter.addWidget(self.tree_results)
        
        # Встроенный превью-виджет
        from .ui_preview import CleanerPreviewWidget
        self.preview_widget = CleanerPreviewWidget()
        self.preview_widget.show_empty("Выберите файл для предпросмотра" if AppContext.is_ru() else "Select a file to preview")
        self.right_splitter.addWidget(self.preview_widget)
        
        self.right_splitter.setSizes([650, 350])
        main_layout.addWidget(self.right_splitter, 1)

    def reload_groups(self):
        """Перезагружает список эталонов на панели настроек."""
        # Очищаем layout
        while self.group_list_layout_ai.count():
            item = self.group_list_layout_ai.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        settings = load_ai_settings()
        groups = settings.get("groups", {})
        
        for name, info in groups.items():
            status, count = self.classifier.get_group_status(name)
            is_face = info.get("type") == "face"
            is_enabled = info.get("enabled", True)
            
            widget = AiGroupChipWidget(name, is_enabled, is_face, status, count, self)
            widget.state_changed.connect(self.on_group_state_changed)
            widget.settings_clicked.connect(self.open_edit_group_dialog)
            self.group_list_layout_ai.addWidget(widget)

    def on_group_state_changed(self, group_name: str, is_enabled: bool):
        settings = load_ai_settings()
        if group_name in settings.get("groups", {}):
            settings["groups"][group_name]["enabled"] = is_enabled
            save_ai_settings(settings)

    def open_edit_group_dialog(self, group_name: str):
        """Открывает диалог редактирования группы."""
        dlg = EditAiGroupDialog(group_name, self.classifier, self)
        if dlg.exec():
            self.reload_groups()

    def create_group(self):
        """Создает новую группу эталонов."""
        dlg = CreateAiGroupDialog(self)
        if dlg.exec():
            name = dlg.txt_name.text().strip()
            if not name:
                return
                
            name = "".join(c for c in name if c.isalnum() or c in " _-").strip()
            if not name:
                return
                
            settings = load_ai_settings()
            if name in settings.get("groups", {}):
                QMessageBox.warning(self, "Ошибка" if AppContext.is_ru() else "Error", 
                                    "Группа с таким именем уже существует!" if AppContext.is_ru() else "Group already exists!")
                return
                
            group_type = "face" if dlg.rad_face.isChecked() else "general"
            
            group_dir = os.path.join(get_ai_assets_dir(), name)
            os.makedirs(group_dir, exist_ok=True)
            
            settings["groups"][name] = {
                "type": group_type,
                "enabled": True
            }
            save_ai_settings(settings)
            
            self.reload_groups()

    def on_threshold_changed(self, value):
        self.lbl_threshold.setText(f"Схожесть: {value}%" if AppContext.is_ru() else f"Similarity: {value}%")

    def set_scan_enabled(self, enabled: bool):
        """Включает/выключает кнопку запуска на основе наличия выбранных каталогов."""
        self.btn_start_scan.setEnabled(enabled)

    def check_and_download_models_ui(self) -> bool:
        if self.ai.are_models_present():
            return True
            
        is_ru = AppContext.is_ru()
        reply = QMessageBox.question(
            self,
            "Инициализация ИИ" if is_ru else "AI Initialization",
            "Для работы ИИ-классификатора необходимо загрузить модели нейросети (~22 МБ). Скачать их сейчас?" if is_ru else "AI classification requires downloading neural network models (~22 MB). Download now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return False
            
        dlg = QDialog(self)
        dlg.setWindowTitle("Загрузка моделей ИИ" if is_ru else "Downloading AI Models")
        dlg.setFixedSize(320, 100)
        dlg_layout = QVBoxLayout(dlg)
        
        lbl = QLabel("Загрузка..." if is_ru else "Downloading...")
        bar = QProgressBar()
        bar.setRange(0, 100)
        
        dlg_layout.addWidget(lbl)
        dlg_layout.addWidget(bar)
        
        dlg.show()
        
        def on_progress(filename, downloaded, total_size):
            if total_size > 0:
                pct = int((downloaded / total_size) * 100.0)
                bar.setValue(pct)
                lbl.setText(f"Загрузка {filename}: {downloaded // 1024} KB / {total_size // 1024} KB")
            else:
                lbl.setText(f"Загрузка {filename}: {downloaded // 1024} KB")
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            
        success = self.ai.download_models(progress_callback=on_progress)
        dlg.close()
        
        if success:
            return True
        else:
            QMessageBox.critical(self, "Ошибка" if is_ru else "Error", 
                                 "Не удалось загрузить модели нейросетей!" if is_ru else "Failed to download neural network models!")
            return False

    def update_folders_label(self, folders: list):
        """В новом дизайне мы отображаем выбранные папки списком во 2-й колонке."""
        # Этот метод больше не пишет текст в QLabel, так как папки отображаются карточками SourceListItem.
        pass

    def toggle_scan(self):
        if self.active_worker and self.active_worker.isRunning():
            self.active_worker.stop()
            return
            
        folders = self.cleaner.get_active_source_folders()
        if not folders:
            return
            
        # Проверяем, обучены ли эталоны
        settings = load_ai_settings()
        has_active_trained = False
        for name, info in settings.get("groups", {}).items():
            if info.get("enabled", True):
                status, count = self.classifier.get_group_status(name)
                if status == "green":
                    has_active_trained = True
                    break
                    
        if not has_active_trained:
            QMessageBox.warning(self, "Ошибка" if AppContext.is_ru() else "Error", 
                                "Нет активных обученных групп эталонов! Обучите хотя бы одну группу (зеленый статус)." if AppContext.is_ru() else "No active trained reference groups found! Please train at least one group (green status).")
            return
            
        if not self.check_and_download_models_ui():
            return
            
        self.scan_started.emit()
        self.btn_start_scan.setText("Остановить" if AppContext.is_ru() else "Stop")
        self.btn_start_scan.setStyleSheet("background-color: #ef4444; color: white; border: none; padding: 6px; border-radius: 4px; font-weight: bold;")
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.tree_results.clear()
        self.lbl_stats.setText("")
        
        filter_cfg = getattr(self.cleaner, 'filter_config', None)
        threshold = float(self.slider_threshold.value())
        
        self.active_worker = AiScanWorker(folders, self.classifier, threshold=threshold, filter_config=filter_cfg)
        self.active_worker.progress.connect(self.on_scan_progress)
        self.active_worker.finished.connect(self.on_scan_finished)
        self.active_worker.start()

    def on_scan_progress(self, stage, percent, text, scanned_files, groups_found, wasted_bytes, scanned_bytes, zero, empty):
        if stage == STAGE_SCANNING:
            self.progress_bar.setMaximum(0)
            self.progress_bar.setFormat(text)
        else:
            self.progress_bar.setMaximum(100)
            self.progress_bar.setValue(int(percent))
            self.progress_bar.setFormat(f"Анализ: {int(percent)}% - {text}")
            
        from utils_common import format_size
        self.lbl_stats.setText(
            f"Найдено совпадений: {groups_found} групп, {wasted_bytes // (1024*1024) if wasted_bytes else 0} MB" if AppContext.is_ru()
            else f"Matches found: {groups_found} groups, {format_size(wasted_bytes)}"
        )

    def on_scan_finished(self, results):
        self.progress_bar.hide()
        self.btn_start_scan.setText("Начать ИИ Поиск" if AppContext.is_ru() else "Start AI Search")
        self.btn_start_scan.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6; 
                color: white; 
                border: none; 
                padding: 6px; 
                border-radius: 4px; 
                font-weight: bold; 
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
        """)
        
        self.active_worker = None
        self.scan_finished.emit()
        
        self.populate_results(results)

    def populate_results(self, results):
        """Заполняет дерево результатов группированными ИИ-классами."""
        self.tree_results.clear()
        if not results:
            return
            
        from utils_common import format_size
        
        for group_name, files in results.items():
            if not files:
                continue
                
            group_size = sum(f["size"] for f in files)
            
            group_item = QTreeWidgetItem(self.tree_results)
            group_item.setText(0, f"Группа: {group_name} ({len(files)} файлов)" if AppContext.is_ru() else f"Group: {group_name} ({len(files)} files)")
            group_item.setText(2, format_size(group_size))
            group_item.setData(0, Qt.ItemDataRole.UserRole, {"is_group": True, "name": group_name})
            
            font = group_item.font(0)
            font.setBold(True)
            group_item.setFont(0, font)
            group_item.setFont(2, font)
            
            for f in files:
                file_item = QTreeWidgetItem(group_item)
                file_item.setCheckState(0, Qt.CheckState.Unchecked)
                file_item.setText(0, os.path.basename(f["path"]))
                file_item.setText(1, f"{f['confidence']:.1f}%")
                file_item.setText(2, format_size(f["size"]))
                file_item.setText(3, f["path"])
                file_item.setData(0, Qt.ItemDataRole.UserRole, {"is_group": False, "path": f["path"], "size": f["size"]})
                
            group_item.setExpanded(True)

    def on_tree_selection_changed(self):
        selected_items = self.tree_results.selectedItems()
        if not selected_items:
            return
            
        item = selected_items[0]
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and not data.get("is_group", False):
            path = data.get("path")
            if path and os.path.exists(path):
                self.preview_widget.load_file(path)
                self.file_selected.emit(path)

    def on_tree_item_changed(self, item, column):
        if column != 0:
            return
            
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
            
        self.tree_results.blockSignals(True)
        try:
            if data.get("is_group", False):
                state = item.checkState(0)
                for i in range(item.childCount()):
                    item.child(i).setCheckState(0, state)
            else:
                parent = item.parent()
                if parent:
                    all_checked = True
                    any_checked = False
                    for i in range(parent.childCount()):
                        c_state = parent.child(i).checkState(0)
                        if c_state == Qt.CheckState.Checked:
                            any_checked = True
                        else:
                            all_checked = False
                            
                    if all_checked:
                        parent.setCheckState(0, Qt.CheckState.Checked)
                    elif any_checked:
                        parent.setCheckState(0, Qt.CheckState.PartiallyChecked)
                    else:
                        parent.setCheckState(0, Qt.CheckState.Unchecked)
        finally:
            self.tree_results.blockSignals(False)
            
        self.update_cleaner_action_bar_info()

    def get_selected_files_paths(self) -> list:
        paths = []
        root = self.tree_results.invisibleRootItem()
        for i in range(root.childCount()):
            group_item = root.child(i)
            for j in range(group_item.childCount()):
                file_item = group_item.child(j)
                if file_item.checkState(0) == Qt.CheckState.Checked:
                    data = file_item.data(0, Qt.ItemDataRole.UserRole)
                    if data and data.get("path"):
                        paths.append(data["path"])
        return paths

    def select_all_results(self, checked: bool):
        self.tree_results.blockSignals(True)
        try:
            root = self.tree_results.invisibleRootItem()
            state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            for i in range(root.childCount()):
                group_item = root.child(i)
                group_item.setCheckState(0, state)
                for j in range(group_item.childCount()):
                    group_item.child(j).setCheckState(0, state)
        finally:
            self.tree_results.blockSignals(False)
        self.update_cleaner_action_bar_info()

    def update_cleaner_action_bar_info(self):
        selected_paths = self.get_selected_files_paths()
        count = len(selected_paths)
        size = sum(os.path.getsize(p) for p in selected_paths if os.path.exists(p))
        
        from utils_common import format_size
        size_str = format_size(size)
        
        self.action_bar.lbl_selection_info.setStyleSheet("color: #93c5fd; font-size: 11px; font-weight: bold;")
        self.action_bar.lbl_selection_info.setText(f"Выбрано: {count} файлов • {size_str}")
        self.action_bar.lbl_selection_info.setToolTip(f"Выбрано файлов: {count}\nРазмер: {size_str}")
        
        has_selection = (count > 0)
        self.action_bar.btn_delete.setEnabled(has_selection)
        self.action_bar.btn_move.setEnabled(has_selection and bool(self.action_bar.drop_zone.get_path()))
        self.action_bar.btn_move_to.setEnabled(has_selection)

    def remove_processed_files(self, paths: list[str]):
        paths_set = set(os.path.normpath(p) for p in paths)
        root = self.tree_results.invisibleRootItem()
        
        for i in range(root.childCount() - 1, -1, -1):
            group_item = root.child(i)
            for j in range(group_item.childCount() - 1, -1, -1):
                file_item = group_item.child(j)
                data = file_item.data(0, Qt.ItemDataRole.UserRole)
                if data and data.get("path") and os.path.normpath(data["path"]) in paths_set:
                    group_item.removeChild(file_item)
                    
            if group_item.childCount() == 0:
                root.removeChild(group_item)
                
        self.preview_widget.show_empty("Выберите файл для предпросмотра" if AppContext.is_ru() else "Select a file to preview")
        self.update_cleaner_action_bar_info()
