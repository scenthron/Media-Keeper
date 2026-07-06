import os
import shutil
import logging
import tempfile
import numpy as np
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QButtonGroup, QRadioButton, QMessageBox, QFileDialog, QTabWidget, QWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap, QImage
from config import AppContext
from .logic_ai_classifier import get_ai_assets_dir, load_ai_settings, save_ai_settings
from .logic_ai_dump import load_dump_info, extract_images_to_temp, save_dump, extract_images_to_dir, load_features
from .ui_widgets import RefImagesListWidget
import cv2

class AiGroupSettingsDialog(QDialog):
    def __init__(self, classifier, group_name: str = None, parent=None):
        super().__init__(parent)
        self.classifier = classifier
        self.group_name = group_name
        self.is_ru = AppContext.is_ru()
        self.has_changes = False
        
        self.pending_pos = []
        self.pending_neg = []
        self.dump_path = None
        self.temp_dir = None
        self.is_hash_only = False
        
        # Load dump info if group exists
        if self.group_name:
            settings = load_ai_settings()
            group_info = settings.get("groups", {}).get(self.group_name, {})
            self.dump_path = group_info.get("path")
            
            if self.dump_path and os.path.exists(self.dump_path):
                info = load_dump_info(self.dump_path)
                self.is_hash_only = info.get("is_hash_only", False)
                self.temp_dir, pos_paths, neg_paths = extract_images_to_temp(self.dump_path)
                self.pending_pos.extend(pos_paths)
                self.pending_neg.extend(neg_paths)
            
        title = f"Настройка эталона: {group_name}" if self.group_name else "Создание группы эталонов"
        if not self.is_ru:
            title = f"Edit Reference: {group_name}" if self.group_name else "Create Reference Group"
            
        self.setWindowTitle(title)
        self.setFixedSize(600, 650)
        self.setStyleSheet("background-color: #202020; color: white;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        
        # 1. Изменение имени
        layout.addWidget(QLabel("Имя группы:" if self.is_ru else "Group Name:"))
        self.txt_name = QLineEdit(self.group_name if self.group_name else "")
        self.txt_name.setMinimumHeight(32)
        self.txt_name.setStyleSheet("QLineEdit { background-color: #2b2b2b; border: 1px solid #444; padding: 4px 8px; border-radius: 4px; color: white; font-size: 13px; } QLineEdit:focus { border: 1px solid #3b82f6; }")
        self.txt_name.textChanged.connect(self._on_name_changed)
        layout.addWidget(self.txt_name)
        
        # 2. Тип анализа
        layout.addWidget(QLabel("Тип анализа:" if self.is_ru else "Analysis Type:"))
        
        is_face_type = True
        if self.dump_path and os.path.exists(self.dump_path):
            info = load_dump_info(self.dump_path)
            is_face_type = info.get("type", "face") == "face"
            
        self.btn_group = QButtonGroup(self)
        self.rad_general = QRadioButton(" Общее сходство" if self.is_ru else " General Similarity")
        self.rad_face = QRadioButton(" Поиск лиц" if self.is_ru else " Face Search")
        
        rad_style = "QRadioButton { background-color: #3b3b3b; color: #e0e0e0; border-radius: 14px; padding: 7px 12px; margin: 2px 0px; font-weight: bold; font-size: 13px; border: 1px solid #555; } QRadioButton:hover { background-color: #4a4a4a; border: 1px solid #666; } QRadioButton::indicator { width: 0px; height: 0px; } QRadioButton:checked { background-color: #3b82f6; color: white; border: 1px solid #2563eb; }"
        self.rad_general.setStyleSheet(rad_style)
        self.rad_face.setStyleSheet(rad_style)
        self.rad_general.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rad_face.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.btn_group.addButton(self.rad_general, 0)
        self.btn_group.addButton(self.rad_face, 1)
        
        if is_face_type:
            self.rad_face.setChecked(True)
        else:
            self.rad_general.setChecked(True)
            
        if self.is_hash_only:
            self.rad_face.setEnabled(False)
            self.rad_general.setEnabled(False)
            
        type_layout = QHBoxLayout()
        type_layout.addWidget(self.rad_general)
        type_layout.addWidget(self.rad_face)
        type_layout.addStretch()
        layout.addLayout(type_layout)
        
        # 3. Вкладки (Позитивы / Негативы)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabWidget::pane { border: 1px solid #444; border-radius: 4px; } QTabBar::tab { background: #2b2b2b; border: 1px solid #444; padding: 8px 16px; margin-right: 2px; } QTabBar::tab:selected { background: #3b82f6; border: 1px solid #2563eb; font-weight: bold; }")
        layout.addWidget(self.tabs, 1)
        
        self.tab_pos = QWidget()
        self.tab_neg = QWidget()
        
        self._setup_tab(self.tab_pos, is_positive=True)
        self._setup_tab(self.tab_neg, is_positive=False)
        
        self.tabs.addTab(self.tab_pos, "Позитивы (Эталоны)" if self.is_ru else "Positives")
        self.tabs.addTab(self.tab_neg, "Негативы (Анти-эталоны)" if self.is_ru else "Negatives")
        
        # 4. Нижние кнопки
        btn_list_layout = QHBoxLayout()
        self.btn_train = QPushButton("Обучить" if self.is_ru else "Train")
        self.btn_train.setStyleSheet("background-color: #16a34a; border: none; padding: 6px 12px; border-radius: 4px; font-weight: bold;")
        self.btn_train.clicked.connect(self.train_group_ui)
        btn_list_layout.addWidget(self.btn_train)
        
        self.btn_save_hash = QPushButton("Экспорт в хэш-дамп" if self.is_ru else "Export as Hash Dump")
        self.btn_save_hash.setStyleSheet("background-color: #8b5cf6; border: none; padding: 6px 12px; border-radius: 4px; font-weight: bold;")
        self.btn_save_hash.clicked.connect(self.save_hash_dump)
        if not self.group_name:
            self.btn_save_hash.setEnabled(False)
        btn_list_layout.addWidget(self.btn_save_hash)
        
        btn_list_layout.addStretch()
        layout.addLayout(btn_list_layout)
        
        buttons_layout = QHBoxLayout()
        if self.group_name:
            self.btn_delete_group = QPushButton("Удалить эталон" if self.is_ru else "Delete Reference")
            self.btn_delete_group.setStyleSheet("background-color: #ef4444; border: none; padding: 6px 16px; border-radius: 4px; font-weight: bold; color: white;")
            self.btn_delete_group.clicked.connect(self.delete_group_ui)
            buttons_layout.addWidget(self.btn_delete_group)
            
        buttons_layout.addStretch()
        
        self.btn_cancel = QPushButton("Отмена" if self.is_ru else "Cancel")
        self.btn_cancel.setStyleSheet("background-color: #333; border: 1px solid #555; padding: 6px 16px; border-radius: 4px;")
        self.btn_cancel.clicked.connect(self.reject)
        
        self.btn_save_copy = QPushButton("Сохранить и копировать" if self.is_ru else "Save and Copy")
        self.btn_save_copy.setStyleSheet("background-color: #0ea5e9; border: none; padding: 6px 16px; border-radius: 4px; font-weight: bold;")
        self.btn_save_copy.setToolTip("Настройка будет сохранена в директорию программы" if self.is_ru else "Configuration will be saved to program directory")
        self.btn_save_copy.clicked.connect(lambda: self.save_settings(copy_to_system=True))
        
        self.btn_save = QPushButton("Сохранить" if self.is_ru else "Save")
        self.btn_save.setStyleSheet("background-color: #3b82f6; border: none; padding: 6px 16px; border-radius: 4px; font-weight: bold;")
        self.btn_save.clicked.connect(lambda: self.save_settings(copy_to_system=False))
        
        buttons_layout.addWidget(self.btn_cancel)
        buttons_layout.addWidget(self.btn_save_copy)
        buttons_layout.addWidget(self.btn_save)
        layout.addLayout(buttons_layout)
        
        # Tooltip
        from .ui_ai_tab import ImageHoverToolTip
        self.hover_tooltip = ImageHoverToolTip(self)
        self.list_pos.item_hovered.connect(self._on_item_hover)
        self.list_pos.hover_left.connect(self.hover_tooltip.hide)
        self.list_neg.item_hovered.connect(self._on_item_hover)
        self.list_neg.hover_left.connect(self.hover_tooltip.hide)
        
        self.reload_thumbnails()
        self._on_name_changed(self.txt_name.text())

    def _setup_tab(self, tab: QWidget, is_positive: bool):
        t_layout = QVBoxLayout(tab)
        t_layout.setContentsMargins(10, 10, 10, 10)
        
        lbl_drop = QLabel("⬇ Перетащите картинки (.png, .jpg) прямо в поле ниже ⬇" if self.is_ru else "⬇ Drag and drop image files (.png, .jpg) directly below ⬇")
        lbl_drop.setStyleSheet("color: #3b82f6; font-size: 12px; font-weight: bold; margin-bottom: 2px;")
        lbl_drop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t_layout.addWidget(lbl_drop)
        
        list_widget = RefImagesListWidget(self)
        list_widget.files_dropped.connect(lambda files: self.add_dropped_files(files, is_positive))
        t_layout.addWidget(list_widget, 1)
        
        if is_positive:
            self.list_pos = list_widget
        else:
            self.list_neg = list_widget
            
        btn_layout = QHBoxLayout()
        
        btn_extract = QPushButton("Извлечь файлы" if self.is_ru else "Extract Files")
        btn_extract.setStyleSheet("background-color: #475569; border: none; padding: 6px 12px; border-radius: 4px;")
        btn_extract.clicked.connect(self.extract_files_ui)
        if self.is_hash_only:
            btn_extract.setEnabled(False)
        btn_layout.addWidget(btn_extract)
        
        btn_layout.addStretch()
        
        btn_add = QPushButton("Добавить файлы" if self.is_ru else "Add Files")
        btn_add.setStyleSheet("background-color: #444; border: 1px solid #555; padding: 6px 12px; border-radius: 4px;")
        btn_add.clicked.connect(lambda: self.choose_files(is_positive))
        
        btn_del = QPushButton("Удалить выбранные" if self.is_ru else "Delete Selected")
        btn_del.setStyleSheet("background-color: #ef4444; border: none; padding: 6px 12px; border-radius: 4px;")
        btn_del.clicked.connect(lambda: self.delete_selected_files(is_positive))
        
        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_del)
        t_layout.addLayout(btn_layout)

    def extract_files_ui(self):
        if not self.dump_path or not os.path.exists(self.dump_path):
            QMessageBox.warning(self, "Ошибка" if self.is_ru else "Error", "Нет сохраненного дампа для извлечения!" if self.is_ru else "No saved dump to extract!")
            return
            
        dest_dir = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения картинок" if self.is_ru else "Select directory to save images")
        if dest_dir:
            try:
                extract_images_to_dir(self.dump_path, dest_dir)
                QMessageBox.information(self, "Успех" if self.is_ru else "Success", "Файлы успешно извлечены!" if self.is_ru else "Files extracted successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка" if self.is_ru else "Error", f"Ошибка извлечения: {e}")

    def _on_name_changed(self, text):
        is_valid = bool(text.strip())
        self.btn_save.setEnabled(is_valid)
        
        from .logic_ai_classifier import get_ai_assets_dir
        import os
        assets_dir = get_ai_assets_dir()
        if not self.dump_path or os.path.abspath(self.dump_path).startswith(os.path.abspath(assets_dir)):
            self.btn_save_copy.setEnabled(False)
            self.btn_save_copy.setToolTip("Эталон уже находится в системной директории" if self.is_ru else "Reference is already in system directory")
        else:
            self.btn_save_copy.setEnabled(is_valid)
            self.btn_save_copy.setToolTip("Настройка будет сохранена в директорию программы" if self.is_ru else "Configuration will be saved to program directory")

        if self.group_name:
            self.btn_train.setEnabled(is_valid)
        else:
            self.btn_train.setEnabled(False)
            
        active_style = "background-color: #3b82f6; color: white; border: none; padding: 6px 16px; border-radius: 4px; font-weight: bold;"
        disabled_style = "background-color: #222; color: #555; border: 1px solid #333; padding: 6px 16px; border-radius: 4px; font-weight: bold;"
        
        self.btn_save.setStyleSheet(active_style if is_valid else disabled_style)
        self.btn_save_copy.setStyleSheet(active_style if self.btn_save_copy.isEnabled() else disabled_style)
        
        if not is_valid:
            self.txt_name.setStyleSheet("QLineEdit { background-color: #451a1a; border: 1px solid #ef4444; padding: 4px 8px; border-radius: 4px; color: white; }")
        else:
            self.txt_name.setStyleSheet("QLineEdit { background-color: #2b2b2b; border: 1px solid #444; padding: 4px 8px; border-radius: 4px; color: white; }")

    def choose_files(self, is_positive):
        files, _ = QFileDialog.getOpenFileNames(
            self, 
            "Выберите картинки" if self.is_ru else "Select Images",
            "", 
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if files:
            self.add_dropped_files(files, is_positive)

    def add_dropped_files(self, file_paths, is_positive):
        target_list = self.pending_pos if is_positive else self.pending_neg
        target_widget = self.list_pos if is_positive else self.list_neg
        
        for path in file_paths:
            if path not in target_list:
                if is_positive:
                    self.pending_pos.append(path)
                else:
                    self.pending_neg.append(path)
                item = QListWidgetItem()
                item.setIcon(QIcon(path))
                item.setData(Qt.ItemDataRole.UserRole, path)
                is_face = self.rad_face.isChecked()
                item.setData(Qt.ItemDataRole.UserRole + 1, is_face)
                try:
                    stat = os.stat(path)
                    if is_face:
                        faces = self.classifier.cache.get_file_faces(path, stat.st_mtime, stat.st_size)
                        item.setData(Qt.ItemDataRole.UserRole + 2, len(faces) > 0 if faces is not None else None)
                    else:
                        emb = self.classifier.cache.get_image_embedding(path, stat.st_mtime, stat.st_size)
                        item.setData(Qt.ItemDataRole.UserRole + 2, True if emb is not None else None)
                except:
                    item.setData(Qt.ItemDataRole.UserRole + 2, None)
                    
                status = item.data(Qt.ItemDataRole.UserRole + 2)
                tt = os.path.basename(path)
                if is_face:
                    if status == True: tt += "\n[🙂 Лицо найдено и сохранено]"
                    elif status == False: tt += "\n[🙁 Ошибка: Лицо не найдено на фото]"
                    else: tt += "\n[⚪ Файл не проанализирован]"
                else:
                    if status == True: tt += "\n[✓ Успешно проанализировано]"
                    elif status == False: tt += "\n[✕ Ошибка при анализе файла]"
                    else: tt += "\n[⚪ Файл не проанализирован]"
                item.setToolTip(tt)
                target_widget.addItem(item)
                self.has_changes = True

    def delete_selected_files(self, is_positive):
        target_widget = self.list_pos if is_positive else self.list_neg
        target_list = self.pending_pos if is_positive else self.pending_neg
        
        selected_items = target_widget.selectedItems()
        if not selected_items:
            return
            
        for item in selected_items:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path == "HASH":
                # User cannot delete HASH proxy yet, they must delete the whole group
                QMessageBox.warning(self, "Внимание", "Нельзя удалить хэш-данные. Если нужно, удалите весь эталон.")
                continue
            if path in target_list:
                target_list.remove(path)
            target_widget.takeItem(target_widget.row(item))
            self.has_changes = True

    def reload_thumbnails(self):
        self.list_pos.clear()
        self.list_neg.clear()
        
        if self.is_hash_only:
            # Add HASH proxies
            if self.dump_path:
                info = load_dump_info(self.dump_path)
                if info.get("pos_features_count", 0) > 0:
                    item = QListWidgetItem()
                    # You could use a special icon here
                    item.setText(" [ HASH ВЕКТОРЫ ] ")
                    item.setData(Qt.ItemDataRole.UserRole, "HASH")
                    item.setToolTip("Предобученные векторы из дампа")
                    self.list_pos.addItem(item)
                if info.get("neg_features_count", 0) > 0:
                    item = QListWidgetItem()
                    item.setText(" [ HASH ВЕКТОРЫ ] ")
                    item.setData(Qt.ItemDataRole.UserRole, "HASH")
                    item.setToolTip("Предобученные векторы из дампа")
                    self.list_neg.addItem(item)
        
        for path in self.pending_pos:
            item = QListWidgetItem()
            item.setIcon(QIcon(path))
            item.setData(Qt.ItemDataRole.UserRole, path)
            is_face = self.rad_face.isChecked()
            item.setData(Qt.ItemDataRole.UserRole + 1, is_face)
            try:
                stat = os.stat(path)
                if is_face:
                    faces = self.classifier.cache.get_file_faces(path, stat.st_mtime, stat.st_size)
                    item.setData(Qt.ItemDataRole.UserRole + 2, len(faces) > 0 if faces is not None else None)
                else:
                    emb = self.classifier.cache.get_image_embedding(path, stat.st_mtime, stat.st_size)
                    item.setData(Qt.ItemDataRole.UserRole + 2, True if emb is not None else None)
            except:
                item.setData(Qt.ItemDataRole.UserRole + 2, None)
                
            status = item.data(Qt.ItemDataRole.UserRole + 2)
            tt = os.path.basename(path)
            if is_face:
                if status == True: tt += "\n[🙂 Лицо найдено и сохранено]"
                elif status == False: tt += "\n[🙁 Ошибка: Лицо не найдено на фото]"
                else: tt += "\n[⚪ Файл не проанализирован]"
            else:
                if status == True: tt += "\n[✓ Успешно проанализировано]"
                elif status == False: tt += "\n[✕ Ошибка при анализе файла]"
                else: tt += "\n[⚪ Файл не проанализирован]"
            item.setToolTip(tt)
            self.list_pos.addItem(item)
            
        for path in self.pending_neg:
            item = QListWidgetItem()
            item.setIcon(QIcon(path))
            item.setData(Qt.ItemDataRole.UserRole, path)
            is_face = self.rad_face.isChecked()
            item.setData(Qt.ItemDataRole.UserRole + 1, is_face)
            try:
                stat = os.stat(path)
                if is_face:
                    faces = self.classifier.cache.get_file_faces(path, stat.st_mtime, stat.st_size)
                    item.setData(Qt.ItemDataRole.UserRole + 2, len(faces) > 0 if faces is not None else None)
                else:
                    emb = self.classifier.cache.get_image_embedding(path, stat.st_mtime, stat.st_size)
                    item.setData(Qt.ItemDataRole.UserRole + 2, True if emb is not None else None)
            except:
                item.setData(Qt.ItemDataRole.UserRole + 2, None)
                
            status = item.data(Qt.ItemDataRole.UserRole + 2)
            tt = os.path.basename(path)
            if is_face:
                if status == True: tt += "\n[🙂 Лицо найдено и сохранено]"
                elif status == False: tt += "\n[🙁 Ошибка: Лицо не найдено на фото]"
                else: tt += "\n[⚪ Файл не проанализирован]"
            else:
                if status == True: tt += "\n[✓ Успешно проанализировано]"
                elif status == False: tt += "\n[✕ Ошибка при анализе файла]"
                else: tt += "\n[⚪ Файл не проанализирован]"
            item.setToolTip(tt)
            self.list_neg.addItem(item)

    def _on_item_hover(self, path, global_pos):
        if not path or path == "HASH" or not os.path.exists(path):
            return
            
        if self.rad_face.isChecked() and self.classifier.ai.initialize_sessions():
            try:
                import cv2
                import numpy as np
                from PIL import Image
                from PyQt6.QtGui import QImage, QPixmap
                from PyQt6.QtCore import Qt
                
                faces = self.classifier.ai.detect_and_extract_faces(path)
                if faces:
                    with Image.open(path) as img:
                        img = img.convert('RGB')
                        img_data = np.array(img, dtype=np.uint8)
                    
                    bgr_img = cv2.cvtColor(img_data, cv2.COLOR_RGB2BGR)
                    for face in faces:
                        x, y, w, h = face["bbox"]
                        cv2.rectangle(bgr_img, (x, y), (x+w, y+h), (0, 255, 0), 2)
                    
                    rgb_img = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2RGB)
                    height, width, ch = rgb_img.shape
                    bytes_per_line = ch * width
                    qt_img = QImage(rgb_img.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
                    pixmap = QPixmap.fromImage(qt_img)
                    
                    if pixmap.width() > 300 or pixmap.height() > 300:
                        pixmap = pixmap.scaled(300, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                        
                    self.hover_tooltip.setPixmap(pixmap)
                    # Adjust position slightly down/right
                    self.hover_tooltip.move(global_pos.x() + 15, global_pos.y() + 15)
                    self.hover_tooltip.show()
                    return
            except Exception:
                pass
                
        self.hover_tooltip.show_image(path, global_pos)

    def save_settings(self, copy_to_system=False):
        new_name = self.txt_name.text().strip()
        new_name = "".join(c for c in new_name if c.isalnum() or c in " _-").strip()
        if not new_name:
            QMessageBox.warning(self, "Ошибка" if self.is_ru else "Error", 
                                "Некорректное имя группы!" if self.is_ru else "Invalid group name!")
            return
            
        settings = load_ai_settings()
        groups = settings.get("groups", {})
        
        if self.group_name and new_name != self.group_name:
            if new_name in groups:
                QMessageBox.warning(self, "Ошибка" if self.is_ru else "Error", 
                                    "Группа с таким именем уже существует!" if self.is_ru else "Group already exists!")
                return
            
        # Determine paths
        # If it's a new group, default path is in ai_assets
        system_path = os.path.join(get_ai_assets_dir(), new_name + ".mkaidump")
        target_path = self.dump_path if self.dump_path else system_path
        
        if copy_to_system:
            target_path = system_path
            
        if not self.has_changes and target_path == self.dump_path:
            # Rename group only in settings if no other changes
            if self.group_name and new_name != self.group_name:
                info = groups.pop(self.group_name)
                groups[new_name] = info
                self.group_name = new_name
                save_ai_settings(settings)
            self.accept()
            return
            
        # Now we need features. If they didn't train, they cannot save!
        QMessageBox.information(self, "Внимание", "Не забудьте нажать 'Обучить' перед сохранением, если вы добавляли новые фото." if self.is_ru else "Don't forget to press 'Train' before saving if you added new photos.")
        # But we force train logic to happen inside train_group_ui which saves a temporary memory state?
        # Actually, let's just train right here if needed!
        if self.has_changes:
            success = self.train_and_save(target_path, is_hash_only=False)
            if not success:
                return
                
        # Update settings
        if self.group_name and new_name != self.group_name:
            if self.group_name in groups:
                groups.pop(self.group_name)
                
        groups[new_name] = {"enabled": True, "path": target_path}
        self.group_name = new_name
        settings["groups"] = groups
        save_ai_settings(settings)
        
        self.dump_path = target_path
        self.accept()

    def train_and_save(self, target_path, is_hash_only=False):
        # We compute features for all pending images
        self.btn_save.setText("Расчет..." if self.is_ru else "Proc...")
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        
        if not self.classifier.ai.initialize_sessions():
            QMessageBox.critical(self, "Ошибка", "Не удалось запустить ИИ модели!")
            self.btn_save.setText("Сохранить")
            return False
            
        search_type = "face" if self.rad_face.isChecked() else "general"
        pos_features = []
        neg_features = []
        
        # Load existing features if any
        if self.dump_path and os.path.exists(self.dump_path):
            exist_pos, exist_neg = load_features(self.dump_path)
            # If we are keeping HASH, we keep them. If we are replacing, we still keep them because we just appended images.
            # But wait, pending_pos contains ALL extracted images too!
            # So if we process pending_pos, we will re-compute existing images!
            # To avoid recomputing, we could check cache. But dumps don't rely on cache.
            # If they are Hash features, they are NOT in pending_pos.
            if self.is_hash_only:
                pos_features.extend(exist_pos)
                neg_features.extend(exist_neg)
        
        for path in self.pending_pos:
            if not os.path.exists(path): continue
            if search_type == "face":
                faces = self.classifier.ai.detect_and_extract_faces(path)
                if faces:
                    for f in faces: pos_features.append(f["descriptor"])
            else:
                emb = self.classifier.ai.extract_image_embedding(path)
                if emb is not None: pos_features.append(emb)
                
        for path in self.pending_neg:
            if not os.path.exists(path): continue
            if search_type == "face":
                faces = self.classifier.ai.detect_and_extract_faces(path)
                if faces:
                    for f in faces: neg_features.append(f["descriptor"])
            else:
                emb = self.classifier.ai.extract_image_embedding(path)
                if emb is not None: neg_features.append(emb)
                
        if not pos_features and not is_hash_only:
            QMessageBox.warning(self, "Ошибка", "Не найдено ни одного лица/вектора в эталонах!")
            self.btn_save.setText("Сохранить")
            return False
            
        save_dump(
            target_path, 
            search_type, 
            self.pending_pos, 
            self.pending_neg, 
            pos_features, 
            neg_features, 
            is_hash_only=is_hash_only
        )
        self.btn_save.setText("Сохранить")
        return True

    def train_group_ui(self):
        self.btn_train.setEnabled(False)
        self.btn_train.setText("Расчет..." if self.is_ru else "Processing...")
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        
        if not self.classifier.ai.initialize_sessions():
            QMessageBox.critical(self, "Ошибка", "Не удалось запустить ИИ модели!")
            self.btn_train.setEnabled(True)
            self.btn_train.setText("Обучить" if self.is_ru else "Train")
            return
            
        search_type = "face" if self.rad_face.isChecked() else "general"
        if search_type == "face":
            for path in self.pending_pos + self.pending_neg:
                if not os.path.exists(path): continue
                try:
                    stat = os.stat(path)
                    faces = self.classifier.cache.get_file_faces(path, stat.st_mtime, stat.st_size)
                    if faces is None:
                        faces = self.classifier.ai.detect_and_extract_faces(path)
                        self.classifier.cache.save_file_faces(path, stat.st_mtime, stat.st_size, faces)
                except Exception:
                    pass
        else:
            for path in self.pending_pos + self.pending_neg:
                if not os.path.exists(path): continue
                try:
                    stat = os.stat(path)
                    emb = self.classifier.cache.get_image_embedding(path, stat.st_mtime, stat.st_size)
                    if emb is None:
                        emb = self.classifier.ai.extract_image_embedding(path)
                        if emb is not None:
                            self.classifier.cache.save_image_embedding(path, stat.st_mtime, stat.st_size, emb)
                except Exception:
                    pass
                    
        self.reload_thumbnails()
        self.btn_train.setEnabled(True)
        self.btn_train.setText("Обучить" if self.is_ru else "Train")
        QMessageBox.information(self, "Успех", "Расчет завершен! Лица распознаны." if search_type == "face" else "Расчет завершен!")
        
    def save_hash_dump(self):
        new_name = self.txt_name.text().strip()
        if not new_name: return
        
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт хэш-дампа", f"{new_name}.hash.mkaidump", "Hash Dumps (*.hash.mkaidump)")
        if path:
            success = self.train_and_save(path, is_hash_only=True)
            if success:
                QMessageBox.information(self, "Успех", "Хэш-дамп успешно экспортирован!")

    def delete_group_ui(self):
        reply = QMessageBox.question(
            self,
            "Удалить группу эталонов" if self.is_ru else "Delete Reference Group",
            f"Удалить эталон '{self.group_name}' из программы?\\nСам файл дампа может остаться на диске.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            settings = load_ai_settings()
            if "groups" in settings and self.group_name in settings["groups"]:
                del settings["groups"][self.group_name]
                save_ai_settings(settings)
                
            if self.group_name in self.classifier.face_reference_descriptors:
                del self.classifier.face_reference_descriptors[self.group_name]
            if self.group_name in self.classifier.general_embeddings:
                del self.classifier.general_embeddings[self.group_name]
            if self.group_name in self.classifier.general_centroids:
                del self.classifier.general_centroids[self.group_name]
            
            self.has_changes = True
            self.reject()

    def closeEvent(self, event):
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().closeEvent(event)
