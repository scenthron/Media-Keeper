import os
import shutil
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QSlider,
    QTreeWidget, QTreeWidgetItem, QProgressBar, QDialog, QLineEdit,
    QRadioButton, QButtonGroup, QAbstractItemView, QMenu, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QColor, QAction

from config import AppContext, APP_DESIGN
from .logic_ai import AiEngine
from .logic_ai_cache import AiCacheManager
from .logic_ai_classifier import AiClassifier, load_ai_settings, save_ai_settings, get_ai_assets_dir
from .workers import AiScanWorker, STAGE_SCANNING, STAGE_ANALYSIS

class CreateAiGroupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Создать группу эталонов" if AppContext.is_ru() else "Create Reference Group")
        self.setFixedSize(350, 200)
        self.setStyleSheet("background-color: #2b2b2b; color: white;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        layout.addWidget(QLabel("Имя группы:" if AppContext.is_ru() else "Group Name:"))
        self.txt_name = QLineEdit()
        self.txt_name.setStyleSheet("background-color: #333; border: 1px solid #555; padding: 6px; border-radius: 4px; color: white;")
        layout.addWidget(self.txt_name)
        
        layout.addWidget(QLabel("Тип анализа:" if AppContext.is_ru() else "Analysis Type:"))
        
        self.btn_group = QButtonGroup(self)
        self.rad_general = QRadioButton("Общее сходство изображений" if AppContext.is_ru() else "General Image Similarity")
        self.rad_general.setChecked(True)
        self.rad_face = QRadioButton("Поиск конкретных лиц людей" if AppContext.is_ru() else "Face Recognition (People)")
        
        self.btn_group.addButton(self.rad_general, 0)
        self.btn_group.addButton(self.rad_face, 1)
        
        layout.addWidget(self.rad_general)
        layout.addWidget(self.rad_face)
        
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        self.btn_cancel = QPushButton("Отмена" if AppContext.is_ru() else "Cancel")
        self.btn_cancel.setStyleSheet("background-color: #444; border: none; padding: 6px 12px; border-radius: 4px;")
        self.btn_cancel.clicked.connect(self.reject)
        
        self.btn_ok = QPushButton("Создать" if AppContext.is_ru() else "Create")
        self.btn_ok.setStyleSheet("background-color: #3b82f6; border: none; padding: 6px 12px; border-radius: 4px; font-weight: bold;")
        self.btn_ok.clicked.connect(self.accept)
        
        buttons_layout.addWidget(self.btn_cancel)
        buttons_layout.addWidget(self.btn_ok)
        layout.addLayout(buttons_layout)


class GroupListWidgetItem(QWidget):
    """Кастомный элемент списка эталонов с чекбоксом, иконкой, счетчиком и статусом."""
    state_changed = pyqtSignal(str, bool) # (group_name, is_enabled)
    
    def __init__(self, name: str, is_enabled: bool, is_face: bool, status_color: str, count: int, parent=None):
        super().__init__(parent)
        self.group_name = name
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(8)
        
        # 1. Чекбокс включения/выключения
        self.chk = QCheckBoxCustom()
        self.chk.setChecked(is_enabled)
        self.chk.toggled.connect(lambda checked: self.state_changed.emit(self.group_name, checked))
        layout.addWidget(self.chk)
        
        # 2. Иконка типа
        self.lbl_icon = QLabel()
        self.lbl_icon.setFixedSize(16, 16)
        if is_face:
            self.lbl_icon.setText("👤") # Специальная иконка для лиц
        else:
            self.lbl_icon.setText("🖼️") # Иконка для общих
        layout.addWidget(self.lbl_icon)
        
        # 3. Название группы
        self.lbl_name = QLabel(name)
        self.lbl_name.setStyleSheet("font-weight: bold; color: #eee;")
        layout.addWidget(self.lbl_name, 1)
        
        # 4. Количество файлов
        self.lbl_count = QLabel(f"[{count}]")
        self.lbl_count.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.lbl_count)
        
        # 5. Круглый индикатор статуса
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(10, 10)
        self.update_status_dot(status_color)
        layout.addWidget(self.status_dot)

    def update_status_dot(self, color: str):
        hex_color = "#888888" # gray
        if color == "orange":
            hex_color = "#f97316" # orange
        elif color == "green":
            hex_color = "#22c55e" # green
            
        self.status_dot.setStyleSheet(f"""
            background-color: {hex_color};
            border-radius: 5px;
            border: 1px solid rgba(0,0,0,0.5);
        """)


class QCheckBoxCustom(QPushButton):
    """Кастомный легковесный чекбокс в стиле чекбоксов дубликатора."""
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


class AiClassificationTab(QWidget):
    scan_started = pyqtSignal()
    scan_finished = pyqtSignal()
    file_selected = pyqtSignal(str) # Передается путь для превью
    
    def __init__(self, cleaner_module, parent=None):
        super().__init__(parent)
        self.cleaner = cleaner_module
        
        # Бэкенд
        self.ai = AiEngine()
        self.cache = AiCacheManager()
        self.classifier = AiClassifier(self.cache, self.ai)
        
        self.active_worker = None
        self.selected_group_name = None
        
        self._init_ui()
        self.reload_groups()

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # =====================================================================
        # 1. ЛЕВАЯ ПАНЕЛЬ: Управление эталонами (Сайдбар)
        # =====================================================================
        self.left_sidebar = QFrame()
        self.left_sidebar.setFixedWidth(280)
        self.left_sidebar.setStyleSheet("background-color: #202020; border-right: 1px solid #2d2d2d;")
        left_layout = QVBoxLayout(self.left_sidebar)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(10)
        
        # Заголовок сайдбара
        title_lbl = QLabel("Группы эталонов" if AppContext.is_ru() else "Reference Groups")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: white; border: none;")
        left_layout.addWidget(title_lbl)
        
        # Список эталонов
        self.list_groups = QListWidget()
        self.list_groups.setStyleSheet("""
            QListWidget {
                background-color: #1a1a1a;
                border: 1px solid #2d2d2d;
                border-radius: 6px;
                outline: none;
            }
            QListWidget::item {
                border-bottom: 1px solid #252525;
                padding: 4px;
            }
            QListWidget::item:selected {
                background-color: #2b2b2b;
            }
        """)
        self.list_groups.currentItemChanged.connect(self.on_group_selection_changed)
        left_layout.addWidget(self.list_groups, 2)
        
        # Кнопки под списком
        btn_layout = QHBoxLayout()
        self.btn_add_group = QPushButton("[+] Создать" if AppContext.is_ru() else "[+] Create")
        self.btn_add_group.setStyleSheet("background-color: #3b82f6; color: white; border: none; padding: 6px; border-radius: 4px; font-weight: bold;")
        self.btn_add_group.clicked.connect(self.create_group)
        
        self.btn_del_group = QPushButton("🗑️ Удалить" if AppContext.is_ru() else "🗑️ Delete")
        self.btn_del_group.setStyleSheet("background-color: #ef4444; color: white; border: none; padding: 6px; border-radius: 4px;")
        self.btn_del_group.clicked.connect(self.delete_selected_group)
        
        btn_layout.addWidget(self.btn_add_group)
        btn_layout.addWidget(self.btn_del_group)
        left_layout.addLayout(btn_layout)
        
        # Сетка миниатюр картинок-примеров текущей группы
        left_layout.addWidget(QLabel("Картинки-примеры эталона:" if AppContext.is_ru() else "Reference Images:"))
        
        self.list_thumbnails = QListWidget()
        self.list_thumbnails.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_thumbnails.setIconSize(QSize(60, 60))
        self.list_thumbnails.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_thumbnails.setGridSize(QSize(70, 70))
        self.list_thumbnails.setStyleSheet("""
            QListWidget {
                background-color: #151515;
                border: 1px solid #2d2d2d;
                border-radius: 6px;
                outline: none;
            }
        """)
        self.list_thumbnails.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_thumbnails.customContextMenuRequested.connect(self.show_thumbnail_context_menu)
        left_layout.addWidget(self.list_thumbnails, 3)
        
        # Кнопки для миниатюр
        thumb_btn_layout = QHBoxLayout()
        self.btn_add_ref_file = QPushButton("Добавить пример" if AppContext.is_ru() else "Add Example")
        self.btn_add_ref_file.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 6px; border-radius: 4px;")
        self.btn_add_ref_file.clicked.connect(self.add_reference_files)
        
        self.btn_train_group = QPushButton("Обучить группу" if AppContext.is_ru() else "Train Group")
        self.btn_train_group.setStyleSheet("background-color: #16a34a; color: white; border: none; padding: 6px; border-radius: 4px; font-weight: bold;")
        self.btn_train_group.clicked.connect(self.train_selected_group)
        
        thumb_btn_layout.addWidget(self.btn_add_ref_file)
        thumb_btn_layout.addWidget(self.btn_train_group)
        left_layout.addLayout(thumb_btn_layout)
        
        main_layout.addWidget(self.left_sidebar)
        
        # =====================================================================
        # 2. ПРАВАЯ ОБЛАСТЬ: Результаты и запуск
        # =====================================================================
        self.right_content = QFrame()
        self.right_content.setStyleSheet("background-color: #1e1e1e;")
        right_layout = QVBoxLayout(self.right_content)
        right_layout.setContentsMargins(15, 10, 15, 15)
        right_layout.setSpacing(10)
        
        # Верхняя панель настроек сканирования
        self.top_settings = QFrame()
        self.top_settings.setStyleSheet("background-color: #252525; border-radius: 6px; border: 1px solid #2d2d2d;")
        top_settings_layout = QVBoxLayout(self.top_settings)
        top_settings_layout.setContentsMargins(10, 10, 10, 10)
        top_settings_layout.setSpacing(8)
        
        # 1. Строка с кнопками сканирования
        row1_layout = QHBoxLayout()
        
        self.lbl_folders = QLabel("Целевые папки не выбраны" if AppContext.is_ru() else "No folders selected")
        self.lbl_folders.setStyleSheet("color: #aaa; border: none;")
        row1_layout.addWidget(self.lbl_folders, 1)
        
        self.btn_start_scan = QPushButton("Начать ИИ Поиск" if AppContext.is_ru() else "Start AI Search")
        self.btn_start_scan.setStyleSheet("background-color: #3b82f6; color: white; border: none; padding: 8px 16px; border-radius: 4px; font-weight: bold; font-size: 13px;")
        self.btn_start_scan.clicked.connect(self.toggle_scan)
        row1_layout.addWidget(self.btn_start_scan)
        
        top_settings_layout.addLayout(row1_layout)
        
        # 2. Строка с ползунком порога уверенности
        row2_layout = QHBoxLayout()
        row2_layout.setSpacing(10)
        
        self.lbl_threshold = QLabel("Минимальная схожесть: 75%" if AppContext.is_ru() else "Min Similarity: 75%")
        self.lbl_threshold.setStyleSheet("color: white; font-weight: bold; width: 180px; border: none;")
        row2_layout.addWidget(self.lbl_threshold)
        
        self.slider_threshold = QSlider(Qt.Orientation.Horizontal)
        self.slider_threshold.setRange(50, 100)
        self.slider_threshold.setValue(75)
        self.slider_threshold.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: #444;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #3b82f6;
                width: 14px;
                height: 14px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 7px;
            }
        """)
        self.slider_threshold.valueChanged.connect(self.on_threshold_changed)
        row2_layout.addWidget(self.slider_threshold, 1)
        
        top_settings_layout.addLayout(row2_layout)
        right_layout.addWidget(self.top_settings)
        
        # Прогресс-бар сканирования
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #333;
                background-color: #1a1a1a;
                border-radius: 4px;
                text-align: center;
                color: white;
            }
            QProgressBar::chunk {
                background-color: #3b82f6;
                border-radius: 3px;
            }
        """)
        self.progress_bar.hide()
        right_layout.addWidget(self.progress_bar)
        
        # Статистика найденного
        self.lbl_stats = QLabel("")
        self.lbl_stats.setStyleSheet("color: #4ade80; font-weight: bold; font-size: 12px; border: none;")
        right_layout.addWidget(self.lbl_stats)
        
        # Панель действий (CleanerActionBar)
        from .ui_panels import CleanerActionBar
        self.action_bar = CleanerActionBar()
        self.action_bar.is_similar_mode = False
        self.action_bar.combo_autoselect.hide()  # В ИИ автовыделение не требуется
        self.action_bar.deselect_clicked.connect(lambda: self.select_all_results(False))
        self.action_bar.select_all_clicked.connect(lambda: self.select_all_results(True))
        
        # Проксируем сигналы к CleanerModule
        self.action_bar.move_clicked.connect(self.cleaner.move_selected)
        self.action_bar.move_to_clicked.connect(self.cleaner.prompt_move_selected)
        self.action_bar.delete_clicked.connect(self.cleaner.delete_selected)
        self.action_bar.browse_clicked.connect(self.cleaner.browse_dest)
        self.action_bar.drop_zone.path_changed.connect(self.cleaner.validate_move_state)
        
        right_layout.addWidget(self.action_bar)
        
        # Сплиттер для дерева результатов и превью
        self.right_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.right_splitter.setHandleWidth(1)
        self.right_splitter.setStyleSheet("QSplitter::handle { background-color: #2d2d2d; }")
        
        # Таблица результатов (Дерево групп)
        self.tree_results = QTreeWidget()
        self.tree_results.setColumnCount(4)
        self.tree_results.setHeaderLabels([
            "Имя файла" if AppContext.is_ru() else "File Name",
            "Сходство (%)" if AppContext.is_ru() else "Similarity (%)",
            "Размер" if AppContext.is_ru() else "Size",
            "Путь" if AppContext.is_ru() else "Path"
        ])
        self.tree_results.setColumnWidth(0, 220)
        self.tree_results.setColumnWidth(1, 100)
        self.tree_results.setColumnWidth(2, 90)
        self.tree_results.setStyleSheet("""
            QTreeWidget {
                background-color: #1a1a1a;
                border: 1px solid #2d2d2d;
                border-radius: 6px;
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
        
        # Превью-виджет (CleanerPreviewWidget)
        from .ui_preview import CleanerPreviewWidget
        self.preview_widget = CleanerPreviewWidget()
        self.preview_widget.show_empty("Выберите файл для предпросмотра" if AppContext.is_ru() else "Select a file to preview")
        self.right_splitter.addWidget(self.preview_widget)
        
        # Размеры сплиттера: 65% список результатов, 35% превью
        self.right_splitter.setSizes([650, 350])
        right_layout.addWidget(self.right_splitter, 1)
        
        main_layout.addWidget(self.right_content)

    def reload_groups(self):
        """Перезагружает список эталонов из ai_settings.json."""
        self.list_groups.clear()
        self.list_thumbnails.clear()
        self.selected_group_name = None
        
        settings = load_ai_settings()
        groups = settings.get("groups", {})
        
        for name, info in groups.items():
            status, count = self.classifier.get_group_status(name)
            is_face = info.get("type") == "face"
            is_enabled = info.get("enabled", True)
            
            # Создаем элемент списка
            item = QListWidgetItem(self.list_groups)
            item.setSizeHint(QSize(250, 28))
            
            widget = GroupListWidgetItem(name, is_enabled, is_face, status, count, self)
            widget.state_changed.connect(self.on_group_state_changed)
            
            self.list_groups.addItem(item)
            self.list_groups.setItemWidget(item, widget)

    def on_group_state_changed(self, group_name: str, is_enabled: bool):
        """Вызывается при включении/выключении чекбокса эталона."""
        settings = load_ai_settings()
        if group_name in settings.get("groups", {}):
            settings["groups"][group_name]["enabled"] = is_enabled
            save_ai_settings(settings)
            logging.info(f"Статус группы {group_name} изменен: enabled={is_enabled}")

    def on_group_selection_changed(self, current, previous):
        """Вызывается при клике по строке списка эталонов."""
        self.list_thumbnails.clear()
        self.selected_group_name = None
        
        if not current:
            return
            
        widget = self.list_groups.itemWidget(current)
        if not widget:
            return
            
        self.selected_group_name = widget.group_name
        self.reload_thumbnails()

    def reload_thumbnails(self):
        """Загружает миниатюры картинок эталона в нижний список."""
        self.list_thumbnails.clear()
        if not self.selected_group_name:
            return
            
        group_dir = os.path.join(get_ai_assets_dir(), self.selected_group_name)
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
                self.list_thumbnails.addItem(item)
        except Exception as e:
            logging.error(f"Ошибка загрузки миниатюр: {e}")

    def create_group(self):
        """Создает новый эталон."""
        dlg = CreateAiGroupDialog(self)
        if dlg.exec():
            name = dlg.txt_name.text().strip()
            if not name:
                return
                
            # Исключаем опасные символы для имени папки
            name = "".join(c for c in name if c.isalnum() or c in " _-").strip()
            if not name:
                return
                
            settings = load_ai_settings()
            if name in settings.get("groups", {}):
                QMessageBox.warning(self, "Ошибка" if AppContext.is_ru() else "Error", 
                                    "Группа с таким именем уже существует!" if AppContext.is_ru() else "Group already exists!")
                return
                
            group_type = "face" if dlg.rad_face.isChecked() else "general"
            
            # Создаем папку
            group_dir = os.path.join(get_ai_assets_dir(), name)
            os.makedirs(group_dir, exist_ok=True)
            
            # Сохраняем в настройки
            settings["groups"][name] = {
                "type": group_type,
                "enabled": True
            }
            save_ai_settings(settings)
            
            self.reload_groups()

    def delete_selected_group(self):
        """Удаляет выбранную группу."""
        if not self.selected_group_name:
            return
            
        is_ru = AppContext.is_ru()
        reply = QMessageBox.question(
            self, 
            "Удаление" if is_ru else "Delete",
            f"Вы уверены, что хотите удалить группу '{self.selected_group_name}' и все ее эталонные файлы?" if is_ru else f"Are you sure you want to delete '{self.selected_group_name}' and all its reference files?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            # Удаляем папку
            group_dir = os.path.join(get_ai_assets_dir(), self.selected_group_name)
            if os.path.exists(group_dir):
                try: shutil.rmtree(group_dir)
                except Exception as e: logging.error(f"Не удалось удалить папку {group_dir}: {e}")
                
            # Удаляем из настроек
            settings = load_ai_settings()
            settings.get("groups", {}).pop(self.selected_group_name, None)
            save_ai_settings(settings)
            
            self.reload_groups()

    def add_reference_files(self):
        """Добавляет файлы-примеры в выбранную группу."""
        if not self.selected_group_name:
            QMessageBox.warning(self, "Внимание" if AppContext.is_ru() else "Warning", 
                                "Выберите группу эталонов слева!" if AppContext.is_ru() else "Select reference group first!")
            return
            
        files, _ = QFileDialog.getOpenFileNames(
            self, 
            "Выберите картинки-эталоны" if AppContext.is_ru() else "Select Reference Images",
            "", 
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not files:
            return
            
        group_dir = os.path.join(get_ai_assets_dir(), self.selected_group_name)
        os.makedirs(group_dir, exist_ok=True)
        
        for fp in files:
            dest = os.path.join(group_dir, os.path.basename(fp))
            try:
                shutil.copy2(fp, dest)
            except Exception as e:
                logging.error(f"Ошибка копирования эталона {fp}: {e}")
                
        # Обновляем
        self.reload_thumbnails()
        self.update_current_group_item_visual()

    def show_thumbnail_context_menu(self, pos):
        """Контекстное меню для удаления картинок-примеров."""
        item = self.list_thumbnails.itemAt(pos)
        if not item:
            return
            
        menu = QMenu(self)
        del_action = QAction("Удалить файл примера" if AppContext.is_ru() else "Delete Example File", self)
        del_action.triggered.connect(lambda: self.delete_thumbnail_file(item))
        menu.addAction(del_action)
        menu.exec(self.list_thumbnails.mapToGlobal(pos))

    def delete_thumbnail_file(self, item):
        """Удаляет файл эталона с диска."""
        fp = item.data(Qt.ItemDataRole.UserRole)
        if fp and os.path.exists(fp):
            try:
                os.remove(fp)
                logging.info(f"Файл примера удален: {fp}")
            except Exception as e:
                logging.error(f"Не удалось удалить файл {fp}: {e}")
                
        self.reload_thumbnails()
        self.update_current_group_item_visual()

    def update_current_group_item_visual(self):
        """Обновляет статус и количество файлов текущей группы в списке QListWidget."""
        if not self.selected_group_name:
            return
            
        for i in range(self.list_groups.count()):
            item = self.list_groups.item(i)
            widget = self.list_groups.itemWidget(item)
            if widget and widget.group_name == self.selected_group_name:
                status, count = self.classifier.get_group_status(self.selected_group_name)
                widget.lbl_count.setText(f"[{count}]")
                widget.update_status_dot(status)
                break

    def train_selected_group(self):
        """Запускает процесс расчета кэша векторов для выбранной группы."""
        if not self.selected_group_name:
            return
            
        # Убедимся, что модели скачаны
        if not self.check_and_download_models_ui():
            return
            
        self.btn_train_group.setEnabled(False)
        self.btn_train_group.setText("Расчет..." if AppContext.is_ru() else "Processing...")
        
        # Расчет в фоновом потоке, но для простоты на этапе MVP сделаем это прямо с QApplication.processEvents()
        # так как это занимает всего 1-2 секунды.
        status, count = self.classifier.get_group_status(self.selected_group_name)
        if count == 0:
            self.btn_train_group.setEnabled(True)
            self.btn_train_group.setText("Обучить группу" if AppContext.is_ru() else "Train Group")
            return
            
        def on_prog(curr, tot):
            self.btn_train_group.setText(f"Расчет ({curr}/{tot})..." if AppContext.is_ru() else f"Proc ({curr}/{tot})...")
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            
        success = self.classifier.train_group(self.selected_group_name, progress_callback=on_prog)
        
        self.btn_train_group.setEnabled(True)
        self.btn_train_group.setText("Обучить группу" if AppContext.is_ru() else "Train Group")
        
        if success:
            self.update_current_group_item_visual()
            QMessageBox.information(self, "Успех" if AppContext.is_ru() else "Success", 
                                    "Обучение группы успешно завершено!" if AppContext.is_ru() else "Group training completed!")

    def check_and_download_models_ui(self) -> bool:
        """Проверяет наличие моделей, скачивает с UI если их нет."""
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
            
        # Показываем диалог загрузки
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
            
        # Скачиваем
        success = self.ai.download_models(progress_callback=on_progress)
        dlg.close()
        
        if success:
            return True
        else:
            QMessageBox.critical(self, "Ошибка" if is_ru else "Error", 
                                 "Не удалось загрузить модели нейросетей!" if is_ru else "Failed to download neural network models!")
            return False

    def update_folders_label(self, folders: list):
        """Обновляет текст выбранных папок."""
        if not folders:
            self.lbl_folders.setText("Целевые папки не выбраны" if AppContext.is_ru() else "No folders selected")
        else:
            paths_str = ", ".join(os.path.basename(p) for p in folders)
            self.lbl_folders.setText(f"Ищем в: {paths_str}" if AppContext.is_ru() else f"Search in: {paths_str}")

    def on_threshold_changed(self, value):
        self.lbl_threshold.setText(f"Минимальная схожесть: {value}%" if AppContext.is_ru() else f"Min Similarity: {value}%")

    def toggle_scan(self):
        """Запускает или останавливает ИИ сканирование."""
        if self.active_worker and self.active_worker.isRunning():
            self.active_worker.stop()
            return
            
        # Проверяем выбранные папки
        folders = self.cleaner.get_active_source_folders()
        if not folders:
            QMessageBox.warning(self, "Внимание" if AppContext.is_ru() else "Warning", 
                                "Добавьте папки для сканирования на панели настроек дубликатов!" if AppContext.is_ru() else "Add folders to scan on duplicate settings panel first!")
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
            
        # Начинаем сканирование
        self.scan_started.emit()
        self.btn_start_scan.setText("Остановить" if AppContext.is_ru() else "Stop")
        self.btn_start_scan.setStyleSheet("background-color: #ef4444; color: white; border: none; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.tree_results.clear()
        self.lbl_stats.setText("")
        
        # Получаем конфиг фильтров из CleanerModule
        filter_cfg = getattr(self.cleaner, 'filter_config', None)
        threshold = float(self.slider_threshold.value())
        
        self.active_worker = AiScanWorker(folders, self.classifier, threshold=threshold, filter_config=filter_cfg)
        self.active_worker.progress.connect(self.on_scan_progress)
        self.active_worker.finished.connect(self.on_scan_finished)
        self.active_worker.start()

    def on_scan_progress(self, stage, percent, text, scanned_files, groups_found, wasted_bytes, scanned_bytes, zero, empty):
        if stage == STAGE_SCANNING:
            self.progress_bar.setMaximum(0) # Анимация бесконечности при поиске файлов
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
        self.btn_start_scan.setStyleSheet("background-color: #3b82f6; color: white; border: none; padding: 8px 16px; border-radius: 4px; font-weight: bold; font-size: 13px;")
        
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
                
            # Считаем размер группы
            group_size = sum(f["size"] for f in files)
            
            # Создаем корневой элемент группы
            group_item = QTreeWidgetItem(self.tree_results)
            group_item.setText(0, f"Группа: {group_name} ({len(files)} файлов)" if AppContext.is_ru() else f"Group: {group_name} ({len(files)} files)")
            group_item.setText(2, format_size(group_size))
            group_item.setData(0, Qt.ItemDataRole.UserRole, {"is_group": True, "name": group_name})
            
            # Делаем шрифт группы жирным
            font = group_item.font(0)
            font.setBold(True)
            group_item.setFont(0, font)
            group_item.setFont(2, font)
            
            # Добавляем файлы
            for f in files:
                file_item = QTreeWidgetItem(group_item)
                file_item.setCheckState(0, Qt.CheckState.Unchecked)
                file_item.setText(0, os.path.basename(f["path"]))
                file_item.setText(1, f"{f['confidence']:.1f}%")
                file_item.setText(2, format_size(f["size"]))
                file_item.setText(3, f["path"])
                file_item.setData(0, Qt.ItemDataRole.UserRole, {"is_group": False, "path": f["path"], "size": f["size"]})
                
            # Раскрываем группу по умолчанию
            group_item.setExpanded(True)

    def on_tree_selection_changed(self):
        """Вызывается при выделении файлов в таблице результатов."""
        selected_items = self.tree_results.selectedItems()
        if not selected_items:
            return
            
        item = selected_items[0]
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and not data.get("is_group", False):
            path = data.get("path")
            if path and os.path.exists(path):
                self.file_selected.emit(path)

    def on_tree_item_changed(self, item, column):
        """Рекурсивно обновляет галочки при выборе группы или дочернего элемента."""
        if column != 0:
            return
            
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
            
        self.tree_results.blockSignals(True)
        try:
            if data.get("is_group", False):
                # Если кликнули по группе, ставим такую же галочку всем детям
                state = item.checkState(0)
                for i in range(item.childCount()):
                    item.child(i).setCheckState(0, state)
            else:
                # Если кликнули по файлу, проверяем состояние сородичей
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
            
        # Обновляем информацию о выбранных файлах на экшн-баре
        self.update_cleaner_action_bar_info()

    def get_selected_files_paths(self) -> list:
        """Возвращает список путей к файлам, отмеченным галочками."""
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
        """Ставит/снимает галочки со всех файлов результатов."""
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
        """Обновляет счетчик выбранных файлов на главной панели действий Cleaner."""
        selected_paths = self.get_selected_files_paths()
        count = len(selected_paths)
        size = sum(os.path.getsize(p) for p in selected_paths if os.path.exists(p))
        
        from utils_common import format_size
        size_str = format_size(size)
        
        self.action_bar.lbl_selection_info.setStyleSheet("color: #93c5fd; font-size: 11px; font-weight: bold;")
        self.action_bar.lbl_selection_info.setText(f"Выбрано: {count} файлов • {size_str}")
        self.action_bar.lbl_selection_info.setToolTip(f"Выбрано файлов: {count}\nРазмер: {size_str}")
        
        # Активируем или деактивируем кнопки действий
        has_selection = (count > 0)
        self.action_bar.btn_delete.setEnabled(has_selection)
        self.action_bar.btn_move.setEnabled(has_selection and bool(self.action_bar.drop_zone.get_path()))
        self.action_bar.btn_move_to.setEnabled(has_selection)

    def remove_processed_files(self, paths: list[str]):
        """Точечно удаляет перемещенные/удаленные файлы из таблицы результатов."""
        paths_set = set(os.path.normpath(p) for p in paths)
        root = self.tree_results.invisibleRootItem()
        
        # Обходим группы снизу вверх, чтобы безопасно удалять элементы
        for i in range(root.childCount() - 1, -1, -1):
            group_item = root.child(i)
            # Обходим файлы внутри группы снизу вверх
            for j in range(group_item.childCount() - 1, -1, -1):
                file_item = group_item.child(j)
                data = file_item.data(0, Qt.ItemDataRole.UserRole)
                if data and data.get("path") and os.path.normpath(data["path"]) in paths_set:
                    group_item.removeChild(file_item)
                    
            # Если в группе не осталось файлов, удаляем саму группу
            if group_item.childCount() == 0:
                root.removeChild(group_item)
                
        # Обновляем превью и экшн-бар
        self.preview_widget.show_empty("Выберите файл для предпросмотра" if AppContext.is_ru() else "Select a file to preview")
        self.update_cleaner_action_bar_info()
