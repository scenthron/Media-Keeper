import os
import shutil
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QSlider,
    QTreeWidget, QTreeWidgetItem, QProgressBar, QDialog, QLineEdit,
    QRadioButton, QButtonGroup, QAbstractItemView, QMenu, QSplitter,
    QScrollArea, QSizePolicy, QComboBox
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
# Всплывающее окно быстрого просмотра картинок при наведении мыши (в 2.5 раза больше)
# -----------------------------------------------------------------------------
class ImageHoverToolTip(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet("background-color: #2b2b2b; border: 2px solid #3b82f6; padding: 2px; border-radius: 6px;")
        self.setScaledContents(True)
        self.setFixedSize(650, 650) # В 2.5 раза больше (было 260x260)
        self.hide()
        
    def show_image(self, path: str, pos: QPoint):
        if not path or not os.path.exists(path):
            self.hide()
            return
            
        try:
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                # Масштабируем до 640x640 с сохранением пропорций
                scaled = pixmap.scaled(640, 640, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.setPixmap(scaled)
                self.setFixedSize(scaled.width() + 10, scaled.height() + 10)
                
                # Смещаем правее и ниже курсора
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
        self.setFixedSize(500, 520)
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
        self.rad_face = QRadioButton("Поиск конкретных лиц людей" if self.is_ru else "Face Recognition (People)")
        
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
        
        self.btn_train = QPushButton("Обучить" if self.is_ru else "Train")
        self.btn_train.setStyleSheet("background-color: #16a34a; border: none; padding: 6px 12px; border-radius: 4px; font-weight: bold;")
        self.btn_train.clicked.connect(self.train_group_ui)
        
        btn_list_layout.addWidget(self.btn_add_file)
        btn_list_layout.addWidget(self.btn_del_file)
        btn_list_layout.addWidget(self.btn_train)
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

    def reload_thumbnails(self):
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
        files, _ = QFileDialog.getOpenFileNames(
            self, 
            "Выберите картинки-эталоны" if self.is_ru else "Select Reference Images",
            "", 
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if files:
            self.add_dropped_files(files)

    def delete_selected_files(self):
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

    def train_group_ui(self):
        main_tab = self.parent()
        if main_tab and hasattr(main_tab, 'check_and_download_models_ui'):
            if not main_tab.check_and_download_models_ui():
                return
                
        status, count = self.classifier.get_group_status(self.group_name)
        if count == 0:
            QMessageBox.warning(self, "Внимание" if self.is_ru else "Warning", 
                                "Добавьте картинки-примеры перед расчетом!" if self.is_ru else "Add reference images first!")
            return
            
        self.btn_train.setEnabled(False)
        self.btn_train.setText("Расчет..." if self.is_ru else "Processing...")
        
        def on_prog(curr, tot):
            self.btn_train.setText(f"Расчет ({curr}/{tot})..." if self.is_ru else f"Proc ({curr}/{tot})...")
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            
        success = self.classifier.train_group(self.group_name, progress_callback=on_prog)
        
        self.btn_train.setEnabled(True)
        self.btn_train.setText("Обучить" if self.is_ru else "Train")
        
        if success:
            QMessageBox.information(self, "Успех" if self.is_ru else "Success", 
                                    "Обучение эталона завершено!" if self.is_ru else "Reference training completed!")

    def save_settings(self):
        new_name = self.txt_name.text().strip()
        new_name = "".join(c for c in new_name if c.isalnum() or c in " _-").strip()
        if not new_name:
            QMessageBox.warning(self, "Ошибка" if self.is_ru else "Error", 
                                "Некорректное имя группы!" if self.is_ru else "Invalid group name!")
            return
            
        settings = load_ai_settings()
        groups = settings.get("groups", {})
        
        if new_name != self.group_name:
            if new_name in groups:
                QMessageBox.warning(self, "Ошибка" if self.is_ru else "Error", 
                                    "Группа с таким именем уже существует!" if self.is_ru else "Group already exists!")
                return
                
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
            
            info = groups.pop(self.group_name)
            groups[new_name] = info
            self.group_name = new_name
            self.has_changes = True
            
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
        self.txt_name.setMinimumHeight(32)
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
        
        self.chk = QCheckBoxCustom()
        self.chk.setChecked(is_enabled)
        self.chk.toggled.connect(lambda checked: self.state_changed.emit(self.group_name, checked))
        layout.addWidget(self.chk)
        
        self.lbl_icon = QLabel()
        self.lbl_icon.setFixedSize(14, 14)
        self.lbl_icon.setText("👤" if is_face else "🖼️")
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
                    border: 1.5px solid #ef4444;
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


# -----------------------------------------------------------------------------
# Основная вкладка ИИ-классификации
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
        self.chips_map = {}
        
        self._init_ui()
        self.reload_groups()
        self.check_models_status()

    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # =====================================================================
        # ЭКРАН-ЗАГЛУШКА ДЛЯ СКАЧИВАНИЯ МОДЕЛЕЙ (ПО УМОЛЧАНИЮ СКРЫТ)
        # =====================================================================
        self.download_placeholder = QFrame()
        self.download_placeholder.setStyleSheet("QFrame { background-color: #1e1e1e; border: none; }")
        
        ph_layout = QVBoxLayout(self.download_placeholder)
        ph_layout.setContentsMargins(40, 40, 40, 40)
        ph_layout.setSpacing(18)
        
        ph_layout.addStretch(1)
        
        lbl_brain = QLabel("🧠")
        lbl_brain.setStyleSheet("font-size: 48px; background: transparent; border: none;")
        lbl_brain.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_layout.addWidget(lbl_brain)
        
        lbl_title = QLabel("Требуется инициализация ИИ-моделей" if AppContext.is_ru() else "AI Models Initialization Required")
        lbl_title.setStyleSheet("font-weight: bold; color: white; font-size: 16px; background: transparent; border: none;")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_layout.addWidget(lbl_title)
        
        lbl_desc = QLabel(
            "Для работы локального классификатора и поиска по лицам необходимо загрузить модели нейросети (~57 МБ).\n"
            "Загрузка выполняется один раз, после чего ИИ работает полностью автономно без подключения к интернету."
            if AppContext.is_ru() else
            "To use local AI classification and face recognition, neural network models (~57 MB) need to be downloaded.\n"
            "This download is done once, and then the AI runs completely offline."
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setFixedWidth(400)
        lbl_desc.setStyleSheet("color: #aaa; font-size: 12px; background: transparent; border: none; line-height: 1.5;")
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        desc_layout = QHBoxLayout()
        desc_layout.addStretch(1)
        desc_layout.addWidget(lbl_desc)
        desc_layout.addStretch(1)
        ph_layout.addLayout(desc_layout)
        
        self.btn_download_models = QPushButton("Загрузить модели ИИ" if AppContext.is_ru() else "Download AI Models")
        self.btn_download_models.setFixedSize(200, 36)
        self.btn_download_models.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_download_models.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6; 
                color: white; 
                border: none; 
                border-radius: 4px; 
                font-weight: bold; 
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
            QPushButton:disabled {
                background-color: #333;
                color: #666;
            }
        """)
        self.btn_download_models.clicked.connect(self.start_placeholder_download)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        btn_layout.addWidget(self.btn_download_models)
        btn_layout.addStretch(1)
        ph_layout.addLayout(btn_layout)
        
        self.placeholder_progress = QProgressBar()
        self.placeholder_progress.setFixedSize(300, 16)
        self.placeholder_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #444;
                border-radius: 4px;
                background-color: #111;
                text-align: center;
                color: white;
                font-size: 10px;
            }
            QProgressBar::chunk {
                background-color: #3b82f6;
            }
        """)
        self.placeholder_progress.hide()
        
        progress_layout = QHBoxLayout()
        progress_layout.addStretch(1)
        progress_layout.addWidget(self.placeholder_progress)
        progress_layout.addStretch(1)
        ph_layout.addLayout(progress_layout)
        
        self.placeholder_status = QLabel("")
        self.placeholder_status.setStyleSheet("color: #ef4444; font-size: 11px; background: transparent; border: none;")
        self.placeholder_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_layout.addWidget(self.placeholder_status)
        
        ph_layout.addStretch(1)
        self.main_layout.addWidget(self.download_placeholder)
        
        # =====================================================================
        # ГЛАВНЫЙ КОНТЕНТ ВКЛАДКИ (НАСТРОЙКИ СВЕРХУ, ТАБЛИЦА СНИЗУ В SPLITTER)
        # =====================================================================
        self.main_content_widget = QWidget(self)
        content_layout = QVBoxLayout(self.main_content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # Создаем вертикальный сплиттер, чтобы область настроек можно было расширять/сжимать
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.setHandleWidth(2)
        self.main_splitter.setStyleSheet("QSplitter::handle { background-color: #2d2d2d; }")
        
        # Верхняя панель настроек (со свободным изменением высоты от 130 до 280)
        self.top_settings = QFrame()
        self.top_settings.setMinimumHeight(130)
        self.top_settings.setMaximumHeight(280)
        self.top_settings.setStyleSheet("background-color: #1e1e1e; border-bottom: 1px solid #2d2d2d;")
        top_layout = QHBoxLayout(self.top_settings)
        top_layout.setContentsMargins(15, 6, 15, 6)
        top_layout.setSpacing(12)
        
        # КОЛОНКА 1: Группы эталонов
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
        
        scroll_ref = QScrollArea()
        scroll_ref.setWidgetResizable(True)
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
        
        # КОЛОНКА 2: Каталоги для поиска (ДРОП-ЗОНА НА ВСЮ ШИРИНУ В СТИЛЕ CLEANER)
        col_dirs = QVBoxLayout()
        col_dirs.setContentsMargins(0, 0, 0, 0)
        col_dirs.setSpacing(4)
        
        dirs_header = QHBoxLayout()
        dirs_title = QLabel("Каталоги для поиска" if AppContext.is_ru() else "Folders to Search")
        dirs_title.setStyleSheet("font-weight: bold; color: #888; font-size: 11px; font-family: 'Segoe UI';")
        dirs_header.addWidget(dirs_title)
        dirs_header.addStretch()
        col_dirs.addLayout(dirs_header)
        
        # Scroll area для тождественного отображения каталогов Cleaner
        scroll_dirs = QScrollArea()
        scroll_dirs.setWidgetResizable(True)
        scroll_dirs.setStyleSheet("QScrollArea { border: 1px solid #333; background-color: #111; border-radius: 4px; }")
        
        self.sources_list_widget_ai = QWidget()
        self.sources_list_widget_ai.setStyleSheet("background-color: #111111;")
        
        dirs_container_layout = QVBoxLayout(self.sources_list_widget_ai)
        dirs_container_layout.setContentsMargins(5, 5, 5, 5)
        dirs_container_layout.setSpacing(4)
        dirs_container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.folder_list_layout_ai = QVBoxLayout()
        self.folder_list_layout_ai.setContentsMargins(0, 0, 0, 0)
        self.folder_list_layout_ai.setSpacing(4)
        self.folder_list_layout_ai.setAlignment(Qt.AlignmentFlag.AlignTop)
        dirs_container_layout.addLayout(self.folder_list_layout_ai)
        
        # ТОЖДЕСТВЕННЫЙ DROP ZONE WIDGET НА ВСЮ ОБЛАСТЬ
        self.drop_zone_ai = DropZoneWidget()
        self.drop_zone_ai.clicked.connect(self.cleaner.add_folder)
        self.drop_zone_ai.folder_dropped.connect(self.cleaner.add_folder_path)
        self.drop_zone_ai.clear_default_requested.connect(self.cleaner.clear_folders)
        self.drop_zone_ai.btn_clear.show()
        self.drop_zone_ai.setStyleSheet(self.drop_zone_ai.styleSheet() + "margin: 0px; padding: 2px;")
        dirs_container_layout.addWidget(self.drop_zone_ai)
        
        scroll_dirs.setWidget(self.sources_list_widget_ai)
        col_dirs.addWidget(scroll_dirs)
        top_layout.addLayout(col_dirs, 1)
        
        # КОЛОНКА 3: Параметры поиска (С КНОПКОЙ-ИНФОРМАЦИЕЙ ℹ️)
        col_params = QVBoxLayout()
        col_params.setContentsMargins(0, 0, 0, 0)
        col_params.setSpacing(4)
        
        params_header = QHBoxLayout()
        params_title = QLabel("Параметры ИИ поиска" if AppContext.is_ru() else "AI Search Parameters")
        params_title.setStyleSheet("font-weight: bold; color: #888; font-size: 11px; font-family: 'Segoe UI';")
        params_header.addWidget(params_title)
        
        self.lbl_info_icon = QLabel("ℹ️")
        self.lbl_info_icon.setCursor(Qt.CursorShape.WhatsThisCursor)
        self.lbl_info_icon.setStyleSheet("color: #3b82f6; font-size: 12px; margin-left: 4px; background: transparent; border: none;")
        
        info_text = (
            "🧠 КАК РАБОТАЕТ ИИ-ПОИСК:\n\n"
            "1. Типы анализа:\n"
            "   • Общее сходство: ИИ сравнивает цветовую гамму, композицию и объекты.\n"
            "   • Поиск лиц: ИИ находит на фото человеческие лица и сравнивает их черты.\n\n"
            "2. Сколько картинок-примеров добавлять:\n"
            "   • Для лиц: достаточно 1-3 четких фото лица под разными углами.\n"
            "   • Для общего поиска: достаточно 2-5 характерных скриншотов/картинок.\n\n"
            "3. Порог схожести (Confidence):\n"
            "   • 85% - 100%: Строгий поиск (тот же человек, почти идентичные скриншоты).\n"
            "   • 70% - 85%: Умеренное сходство (тот же человек в другой одежде, похожие сцены).\n"
            "   • 50% - 70%: Широкий поиск (похожие по цветам и структуре изображения).\n\n"
            "💡 Совет: Для лучшего результата используйте четкие примеры и отключайте ненужные группы эталонов."
            if AppContext.is_ru() else
            "🧠 HOW AI SEARCH WORKS:\n\n"
            "1. Analysis Types:\n"
            "   • General Similarity: Compares colors, composition, and objects.\n"
            "   • Face Recognition: Detects human faces and matches facial features.\n\n"
            "2. Number of Reference Images:\n"
            "   • For Faces: 1-3 clear photos from different angles are enough.\n"
            "   • For General: 2-5 typical screenshots or images.\n\n"
            "3. Similarity Threshold (Confidence):\n"
            "   • 85% - 100%: Strict match (same person, nearly identical screenshots).\n"
            "   • 70% - 85%: Medium match (same person in other clothes, similar scenes).\n"
            "   • 50% - 70%: Broad match (similar colors and structure).\n\n"
            "💡 Tip: Disable unused reference groups to speed up scanning."
        )
        self.lbl_info_icon.setToolTip(info_text)
        params_header.addWidget(self.lbl_info_icon)
        params_header.addStretch()
        col_params.addLayout(params_header)
        
        params_container = QFrame()
        params_container.setStyleSheet("QFrame { background-color: #111; border: 1px solid #333; border-radius: 4px; }")
        params_sub_layout = QVBoxLayout(params_container)
        params_sub_layout.setContentsMargins(8, 8, 8, 8)
        params_sub_layout.setSpacing(8)
        
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
        
        # Выбор режима сопоставления
        self.lbl_match_mode = QLabel("Режим сопоставления:" if AppContext.is_ru() else "Matching Mode:")
        self.lbl_match_mode.setStyleSheet("color: #ccc; font-weight: bold; font-size: 11px; border: none; background: transparent; margin-top: 4px;")
        params_sub_layout.addWidget(self.lbl_match_mode)
        
        self.combo_match_mode = QComboBox()
        self.combo_match_mode.setMinimumHeight(24)
        self.combo_match_mode.setStyleSheet("""
            QComboBox {
                background-color: #2b2b2b;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 2px 8px;
                color: white;
                font-size: 11px;
            }
            QComboBox:hover {
                border-color: #555;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #2b2b2b;
                color: white;
                selection-background-color: #3b82f6;
            }
        """)
        
        is_ru = AppContext.is_ru()
        self.combo_match_mode.addItem("Средний образ" if is_ru else "Average Centroid", "centroid")
        self.combo_match_mode.setItemData(0, 
            "Сравнивает изображение со средним арифметическим всех эталонов.\nПодходит для поиска однотипных скриншотов или портретов одного человека."
            if is_ru else
            "Compares with the average vector of all references.\nBest for uniform images (e.g. same face, same UI).",
            Qt.ItemDataRole.ToolTipRole
        )
        
        self.combo_match_mode.addItem("Любое совпадение" if is_ru else "Best Match (Any)", "best_match")
        self.combo_match_mode.setItemData(1, 
            "Сравнивает с каждым эталоном отдельно и берет максимальное сходство.\nПозволяет искать разнородные объекты в одной группе (разные ракурсы, цвета, машины)."
            if is_ru else
            "Compares with each reference individually and takes the maximum similarity.\nBest for diverse images in one group.",
            Qt.ItemDataRole.ToolTipRole
        )
        
        self.combo_match_mode.addItem("Большинство совпадений" if is_ru else "Majority Match", "majority")
        self.combo_match_mode.setItemData(2, 
            "Файл должен быть похож минимум на половину (50%) всех эталонов в группе.\nИсключает случайные ложные совпадения."
            if is_ru else
            "Requires the file to match at least 50% of the reference images.\nPrevents accidental false positives.",
            Qt.ItemDataRole.ToolTipRole
        )
        
        # Загружаем сохраненный режим из настроек
        settings = load_ai_settings()
        saved_mode = settings.get("match_mode", "centroid")
        idx = self.combo_match_mode.findData(saved_mode)
        if idx >= 0:
            self.combo_match_mode.setCurrentIndex(idx)
            
        self.combo_match_mode.currentIndexChanged.connect(self.on_match_mode_changed)
        params_sub_layout.addWidget(self.combo_match_mode)
        
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
        
        self.main_splitter.addWidget(self.top_settings)
        
        # Нижняя часть (таблица, превью, воркеры и кнопки действий)
        self.bottom_container = QWidget()
        bot_layout = QVBoxLayout(self.bottom_container)
        bot_layout.setContentsMargins(0, 0, 0, 0)
        bot_layout.setSpacing(0)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: none; background-color: #151515; text-align: center; color: white; font-size: 11px; }
            QProgressBar::chunk { background-color: #3b82f6; }
        """)
        self.progress_bar.hide()
        bot_layout.addWidget(self.progress_bar)
        
        self.lbl_stats = QLabel("")
        self.lbl_stats.setStyleSheet("color: #4ade80; font-weight: bold; font-size: 12px; border: none; padding: 4px 15px; background-color: #1e1e1e;")
        bot_layout.addWidget(self.lbl_stats)
        
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
        bot_layout.addWidget(self.action_bar)
        
        self.right_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.right_splitter.setHandleWidth(2)
        self.right_splitter.setStyleSheet("QSplitter::handle { background-color: #2d2d2d; }")
        
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
        
        # ЗАМЕТНЫЕ ЧЕКБОКСЫ QTreeWidget (дизайн тождественный)
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
            QTreeWidget::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #666;
                border-radius: 3px;
                background-color: #2b2b2b;
            }
            QTreeWidget::indicator:hover {
                border-color: #3b82f6;
            }
            QTreeWidget::indicator:checked {
                background-color: #3b82f6;
                border: 1px solid #2563eb;
            }
            QTreeWidget::indicator:unchecked {
                background-color: #2b2b2b;
            }
        """)
        self.tree_results.itemSelectionChanged.connect(self.on_tree_selection_changed)
        self.tree_results.itemChanged.connect(self.on_tree_item_changed)
        
        # Поддержка контекстного меню по заголовку группы
        self.tree_results.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_results.customContextMenuRequested.connect(self.show_results_context_menu)
        
        self.right_splitter.addWidget(self.tree_results)
        
        from .ui_preview import CleanerPreviewWidget
        self.preview_widget = CleanerPreviewWidget()
        self.preview_widget.show_empty("Выберите файл для предпросмотра" if AppContext.is_ru() else "Select a file to preview")
        self.right_splitter.addWidget(self.preview_widget)
        
        self.right_splitter.setSizes([650, 350])
        bot_layout.addWidget(self.right_splitter, 1)
        
        self.main_splitter.addWidget(self.bottom_container)
        
        # Начальные размеры вертикального сплиттера: 155px под настройки, остальное под таблицу
        self.main_splitter.setSizes([155, 450])
        
        content_layout.addWidget(self.main_splitter, 1)
        self.main_layout.addWidget(self.main_content_widget, 1)

    def check_models_status(self):
        if self.ai.are_models_present():
            if not self.ai._is_initialized:
                self.ai.initialize_sessions()
            self.download_placeholder.hide()
            self.main_content_widget.show()
        else:
            self.download_placeholder.show()
            self.main_content_widget.hide()

    def start_placeholder_download(self):
        self.btn_download_models.setEnabled(False)
        self.placeholder_progress.show()
        self.placeholder_progress.setValue(0)
        self.placeholder_status.setStyleSheet("color: #93c5fd;")
        self.placeholder_status.setText("Подключение..." if AppContext.is_ru() else "Connecting...")
        
        is_ru = AppContext.is_ru()
        
        def on_progress(filename, downloaded, total_size):
            if total_size > 0:
                pct = int((downloaded / total_size) * 100.0)
                self.placeholder_progress.setValue(pct)
                self.placeholder_status.setText(f"Загрузка {filename}: {downloaded // 1024} KB / {total_size // 1024} KB")
            else:
                self.placeholder_status.setText(f"Загрузка {filename}: {downloaded // 1024} KB")
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            
        success = self.ai.download_models(progress_callback=on_progress)
        
        if success:
            self.placeholder_status.setStyleSheet("color: #4ade80;")
            self.placeholder_status.setText("Инициализация..." if is_ru else "Initializing...")
            
            if self.ai.initialize_sessions():
                self.placeholder_status.setText("Успешно!" if is_ru else "Success!")
                self.download_placeholder.hide()
                self.main_content_widget.show()
            else:
                self.btn_download_models.setEnabled(True)
                self.placeholder_status.setStyleSheet("color: #ef4444;")
                self.placeholder_status.setText("Ошибка инициализации!" if is_ru else "Initialization failed!")
        else:
            self.btn_download_models.setEnabled(True)
            self.placeholder_status.setStyleSheet("color: #ef4444;")
            self.placeholder_status.setText("Ошибка при скачивании моделей!" if is_ru else "Failed to download models!")

    def reload_groups(self):
        self.chips_map.clear()
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
            self.chips_map[name] = widget

    def on_group_state_changed(self, group_name: str, is_enabled: bool):
        settings = load_ai_settings()
        if group_name in settings.get("groups", {}):
            settings["groups"][group_name]["enabled"] = is_enabled
            save_ai_settings(settings)
            
        if group_name in self.chips_map:
            self.chips_map[group_name].set_error_highlight(False)

    def open_edit_group_dialog(self, group_name: str):
        dlg = EditAiGroupDialog(group_name, self.classifier, self)
        if dlg.exec():
            self.reload_groups()

    def create_group(self):
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

    def on_match_mode_changed(self, index):
        mode = self.combo_match_mode.itemData(index)
        settings = load_ai_settings()
        settings["match_mode"] = mode
        save_ai_settings(settings)

    def set_scan_enabled(self, enabled: bool):
        self.btn_start_scan.setEnabled(enabled)

    def check_and_download_models_ui(self) -> bool:
        if self.ai.are_models_present():
            return True
        self.check_models_status()
        return False

    def update_folders_label(self, folders: list):
        pass

    def toggle_scan(self):
        if self.active_worker and self.active_worker.isRunning():
            self.active_worker.stop()
            return
            
        folders = self.cleaner.get_active_source_folders()
        if not folders:
            return
            
        for widget in self.chips_map.values():
            widget.set_error_highlight(False)
            
        settings = load_ai_settings()
        enabled_groups = [name for name, info in settings.get("groups", {}).items() if info.get("enabled", True)]
        
        if not enabled_groups:
            QMessageBox.warning(self, "Ошибка" if AppContext.is_ru() else "Error", 
                                "Выберите хотя бы одну группу эталонов для поиска!" if AppContext.is_ru() else "Select at least one reference group to search!")
            return
            
        for name in enabled_groups:
            status, count = self.classifier.get_group_status(name)
            if status == "gray":
                if name in self.chips_map:
                    self.chips_map[name].set_error_highlight(True)
                QMessageBox.critical(
                    self, 
                    "Ошибка" if AppContext.is_ru() else "Error", 
                    f"Группа '{name}' включена в поиск, но не содержит картинок-примеров! Загрузите картинки или выключите группу." if AppContext.is_ru()
                    else f"Group '{name}' is enabled but contains no reference images! Load images or disable the group."
                )
                return
                
        needs_training = []
        for name in enabled_groups:
            status, count = self.classifier.get_group_status(name)
            if status == "orange":
                needs_training.append(name)
                
        if needs_training:
            if not self.check_and_download_models_ui():
                return
                
            dlg = QDialog(self)
            dlg.setWindowTitle("Автоматическое обучение ИИ" if AppContext.is_ru() else "AI Auto-training")
            dlg.setFixedSize(300, 100)
            dlg_layout = QVBoxLayout(dlg)
            
            lbl_title = QLabel("Идет подготовка эталонов..." if AppContext.is_ru() else "Preparing reference groups...")
            bar = QProgressBar()
            bar.setRange(0, len(needs_training))
            
            dlg_layout.addWidget(lbl_title)
            dlg_layout.addWidget(bar)
            dlg.show()
            
            for idx, name in enumerate(needs_training):
                lbl_title.setText(f"Обучение эталона ({idx + 1}/{len(needs_training)}): {name}")
                from PyQt6.QtWidgets import QApplication
                QApplication.processEvents()
                
                success = self.classifier.train_group(name)
                if not success:
                    dlg.close()
                    QMessageBox.critical(self, "Ошибка" if AppContext.is_ru() else "Error", 
                                         f"Не удалось обучить группу '{name}'!" if AppContext.is_ru() else f"Failed to train group '{name}'!")
                    return
                bar.setValue(idx + 1)
                
            dlg.close()
            self.reload_groups()
            
        self.scan_started.emit()
        self.btn_start_scan.setText("Остановить" if AppContext.is_ru() else "Stop")
        self.btn_start_scan.setStyleSheet("background-color: #ef4444; color: white; border: none; padding: 6px; border-radius: 4px; font-weight: bold;")
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.tree_results.clear()
        self.lbl_stats.setText("")
        
        filter_cfg = getattr(self.cleaner, 'filter_config', None)
        threshold = float(self.slider_threshold.value())
        
        match_mode = self.combo_match_mode.currentData() or "centroid"
        self.active_worker = AiScanWorker(folders, self.classifier, threshold=threshold, filter_config=filter_cfg, match_mode=match_mode)
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

    def show_results_context_menu(self, pos: QPoint):
        """Контекстное меню по заголовку группы результатов."""
        item = self.tree_results.itemAt(pos)
        if not item:
            return
            
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get("is_group", False):
            menu = QMenu(self)
            menu.setStyleSheet("QMenu { background-color: #2b2b2b; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #3b82f6; }")
            
            act_select = QAction("Выделить все файлы в этой группе" if AppContext.is_ru() else "Select all files in this group", self)
            act_deselect = QAction("Снять выделение со всех файлов в группе" if AppContext.is_ru() else "Deselect all files in this group", self)
            
            act_select.triggered.connect(lambda: self.set_group_selection_state(item, Qt.CheckState.Checked))
            act_deselect.triggered.connect(lambda: self.set_group_selection_state(item, Qt.CheckState.Unchecked))
            
            menu.addAction(act_select)
            menu.addAction(act_deselect)
            menu.exec(self.tree_results.mapToGlobal(pos))

    def set_group_selection_state(self, group_item, state):
        self.tree_results.blockSignals(True)
        try:
            group_item.setCheckState(0, state)
            for i in range(group_item.childCount()):
                group_item.child(i).setCheckState(0, state)
        finally:
            self.tree_results.blockSignals(False)
        self.update_cleaner_action_bar_info()


# -----------------------------------------------------------------------------
# Кнопка чекбокса, использующаяся в чипах эталонов
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
