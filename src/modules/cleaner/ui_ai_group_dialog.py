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
                
                if not hasattr(self, "trained_status"):
                    self.trained_status = {}
                for p in pos_paths + neg_paths:
                    self.trained_status[p] = True
            
        title = f"Настройка эталона: {group_name}" if self.group_name else "Создание группы эталонов"
        if not self.is_ru:
            title = f"Edit Reference: {group_name}" if self.group_name else "Create Reference Group"
            
        self.setWindowTitle(title)
        self.setFixedSize(600, 650)
        self.setStyleSheet("background-color: #202020; color: white;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        
        # 1. Путь к эталону
        layout.addWidget(QLabel("Файл эталона:" if self.is_ru else "Reference File:"))
        
        path_layout = QHBoxLayout()
        
        def format_path(path):
            if not path:
                return "Новый эталон (не сохранен)" if self.is_ru else "New Reference (Unsaved)"
            parts = path.replace("\\", "/").split("/")
            if len(parts) > 3:
                return f"{parts[0]}/.../{parts[-2]}/{parts[-1]}"
            return path
            
        self.lbl_path = QLabel(format_path(self.dump_path))
        self.lbl_path.setStyleSheet("background-color: #2b2b2b; border: 1px solid #444; padding: 6px 8px; border-radius: 4px; color: #a3a3a3; font-size: 13px;")
        self.lbl_path.setMinimumHeight(32)
        path_layout.addWidget(self.lbl_path, 1)
        
        self.btn_open_folder = QPushButton("📁")
        self.btn_open_folder.setToolTip("Открыть директорию" if self.is_ru else "Open Directory")
        self.btn_open_folder.setStyleSheet("background-color: #3b3b3b; border: 1px solid #444; border-radius: 4px; font-size: 16px;")
        self.btn_open_folder.setFixedSize(32, 32)
        self.btn_open_folder.clicked.connect(self.open_dump_folder)
        if not self.dump_path or not os.path.exists(self.dump_path):
            self.btn_open_folder.setEnabled(False)
        path_layout.addWidget(self.btn_open_folder)
        
        layout.addLayout(path_layout)
        
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
        
        self.rad_general.toggled.connect(self._on_type_changed)
        self.rad_face.toggled.connect(self._on_type_changed)
        
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
        
        self.btn_save_as = QPushButton("Сохранить как..." if self.is_ru else "Save As...")
        self.btn_save_as.setStyleSheet("background-color: #0ea5e9; border: none; padding: 6px 16px; border-radius: 4px; font-weight: bold; color: white;")
        self.btn_save_as.clicked.connect(lambda: self.save_settings(is_save_as=True))
        
        self.btn_save = QPushButton("Сохранить" if self.is_ru else "Save")
        if self.dump_path:
            self.btn_save.setStyleSheet("background-color: #3b82f6; border: none; padding: 6px 16px; border-radius: 4px; font-weight: bold; color: white;")
        else:
            self.btn_save.setEnabled(False)
            self.btn_save.setStyleSheet("background-color: #222; color: #555; border: 1px solid #333; padding: 6px 16px; border-radius: 4px; font-weight: bold;")
        self.btn_save.clicked.connect(lambda: self.save_settings(is_save_as=False))
        
        buttons_layout.addWidget(self.btn_cancel)
        buttons_layout.addWidget(self.btn_save_as)
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
        self._update_save_state()

    
    def _show_silent_msg(self, title, text):
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setIcon(QMessageBox.Icon.NoIcon)
        msg.exec()

    def _show_silent_question(self, title, text):
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setIcon(QMessageBox.Icon.NoIcon)
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        return msg.exec()

    def open_dump_folder(self):
        if self.dump_path and os.path.exists(self.dump_path):
            from utils_common import reveal_in_explorer
            reveal_in_explorer(self.dump_path)

    def _update_save_state(self):
        if not hasattr(self, 'btn_save'):
            return
            
        has_data = len(self.pending_pos) > 0 or len(self.pending_neg) > 0 or self.is_hash_only
        
        if not has_data:
            self.btn_save.setEnabled(False)
            self.btn_save_as.setEnabled(False)
            self.btn_save_hash.setEnabled(False)
            self.btn_train.setEnabled(False)
            
            tooltip = "Добавьте изображения для анализа" if self.is_ru else "Add images for analysis"
            self.btn_save.setToolTip(tooltip)
            self.btn_save_as.setToolTip(tooltip)
            self.btn_save_hash.setToolTip(tooltip)
            
            disabled_style = "background-color: #222; color: #555; border: 1px solid #333; padding: 6px 16px; border-radius: 4px; font-weight: bold;"
            self.btn_save.setStyleSheet(disabled_style)
            self.btn_save_as.setStyleSheet(disabled_style)
        else:
            self.btn_save.setToolTip("")
            self.btn_save_as.setToolTip("")
            self.btn_save_hash.setToolTip("")
            
            self.btn_save_as.setEnabled(True)
            self.btn_save_as.setStyleSheet("background-color: #0ea5e9; border: none; padding: 6px 16px; border-radius: 4px; font-weight: bold; color: white;")
            
            self.btn_save_hash.setEnabled(bool(self.group_name))
            self.btn_train.setEnabled(True)
            
            if self.has_changes or not self.dump_path:
                self.btn_save.setEnabled(True)
                self.btn_save.setStyleSheet("background-color: #3b82f6; border: none; padding: 6px 16px; border-radius: 4px; font-weight: bold; color: white;")
            else:
                self.btn_save.setEnabled(False)
                self.btn_save.setStyleSheet("background-color: #222; color: #555; border: 1px solid #333; padding: 6px 16px; border-radius: 4px; font-weight: bold;")

    def _on_type_changed(self):
        self.has_changes = True
        self._update_save_state()

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
            self._show_silent_msg("Ошибка" if self.is_ru else "Error", "Нет сохраненного дампа для извлечения!" if self.is_ru else "No saved dump to extract!")
            return
            
        dest_dir = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения картинок" if self.is_ru else "Select directory to save images")
        if dest_dir:
            try:
                extract_images_to_dir(self.dump_path, dest_dir)
                self._show_silent_msg("Успех" if self.is_ru else "Success", "Файлы успешно извлечены!" if self.is_ru else "Files extracted successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка" if self.is_ru else "Error", f"Ошибка извлечения: {e}")

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
                pixmap = QPixmap(path)
                if not pixmap.isNull():
                    scaled = pixmap.scaled(128, 128, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    square = QPixmap(128, 128)
                    square.fill(Qt.GlobalColor.transparent)
                    from PyQt6.QtGui import QPainter
                    painter = QPainter(square)
                    painter.drawPixmap((128 - scaled.width()) // 2, (128 - scaled.height()) // 2, scaled)
                    painter.end()
                    item.setIcon(QIcon(square))
                else:
                    item.setIcon(QIcon(path))
                item.setData(Qt.ItemDataRole.UserRole, path)
                item.setToolTip(os.path.basename(path))
                target_widget.addItem(item)
                self.has_changes = True
        self._update_save_state()

    def delete_selected_files(self, is_positive):
        target_widget = self.list_pos if is_positive else self.list_neg
        target_list = self.pending_pos if is_positive else self.pending_neg
        
        selected_items = target_widget.selectedItems()
        if not selected_items:
            return
            
        for item in selected_items:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path == "HASH":
                self._show_silent_msg("Внимание", "Нельзя удалить хэш-данные. Если нужно, удалите весь эталон.")
                continue
            if path in target_list:
                target_list.remove(path)
            target_widget.takeItem(target_widget.row(item))
            self.has_changes = True
        self._update_save_state()

    def reload_thumbnails(self):
        self.list_pos.clear()
        self.list_neg.clear()
        
        if self.is_hash_only:
            if self.dump_path:
                info = load_dump_info(self.dump_path)
                from PyQt6.QtGui import QPixmap, QColor, QPainter, QIcon
                from PyQt6.QtCore import Qt
                
                def create_hash_item(count, is_positive):
                    item = QListWidgetItem()
                    pixmap = QPixmap(128, 128)
                    pixmap.fill(QColor("#22c55e") if is_positive else QColor("#ef4444"))
                    painter = QPainter(pixmap)
                    painter.setPen(QColor("white"))
                    font = painter.font()
                    font.setPointSize(18)
                    font.setBold(True)
                    painter.setFont(font)
                    text = f"HASH\n{count} шт." if self.is_ru else f"HASH\n{count} items"
                    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, text)
                    painter.end()
                    
                    item.setIcon(QIcon(pixmap))
                    item.setData(Qt.ItemDataRole.UserRole, "HASH")
                    item.setData(Qt.ItemDataRole.UserRole + 1, self.rad_face.isChecked())
                    item.setData(Qt.ItemDataRole.UserRole + 2, True) # Show success emoji
                    item.setToolTip("Предобученные векторы из дампа (без исходных фото)" if self.is_ru else "Pre-trained vectors from dump (no original photos)")
                    return item

                if info.get("pos_features_count", 0) > 0:
                    self.list_pos.addItem(create_hash_item(info["pos_features_count"], True))
                if info.get("neg_features_count", 0) > 0:
                    self.list_neg.addItem(create_hash_item(info["neg_features_count"], False))
        
        from PyQt6.QtGui import QPainter, QColor, QPen, QPixmap
        if not hasattr(self, "trained_status"):
            self.trained_status = {}
            
        def _create_item(path, list_widget):
            item = QListWidgetItem()
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(128, 128, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                # Чтобы превью были квадратными и не искажались, создадим квадратную основу
                square = QPixmap(128, 128)
                square.fill(Qt.GlobalColor.transparent)
                from PyQt6.QtGui import QPainter
                painter = QPainter(square)
                painter.drawPixmap((128 - scaled.width()) // 2, (128 - scaled.height()) // 2, scaled)
                painter.end()
                item.setIcon(QIcon(square))
            else:
                item.setIcon(QIcon(path))
            
            item.setData(Qt.ItemDataRole.UserRole, path)
            
            is_face = self.rad_face.isChecked()
            item.setData(Qt.ItemDataRole.UserRole + 1, is_face)
            
            if hasattr(self, "trained_status") and path in self.trained_status:
                item.setData(Qt.ItemDataRole.UserRole + 2, self.trained_status[path])
            else:
                item.setData(Qt.ItemDataRole.UserRole + 2, None)
                
            item.setToolTip(os.path.basename(path))
            list_widget.addItem(item)

        from PyQt6.QtWidgets import QApplication
        for path in self.pending_pos:
            _create_item(path, self.list_pos)
            QApplication.processEvents()
            
        for path in self.pending_neg:
            _create_item(path, self.list_neg)
            QApplication.processEvents()

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
                    self.hover_tooltip.adjustSize()
                    self.hover_tooltip.move(global_pos.x() + 15, global_pos.y() + 15)
                    self.hover_tooltip.show()
                    return
            except Exception:
                pass
                
        self.hover_tooltip.show_image(path, global_pos)

    def save_settings(self, is_save_as=False):
        settings = load_ai_settings()
        groups = settings.get("groups", {})
        from .logic_ai_classifier import get_ai_assets_dir
        
        target_path = self.dump_path
        
        if is_save_as or not target_path:
            default_name = self.group_name if self.group_name else "Новый_эталон"
            default_path = os.path.join(get_ai_assets_dir(), f"{default_name}.mkaidump")
            path, _ = QFileDialog.getSaveFileName(self, "Сохранить эталон", default_path, "AI Dumps (*.mkaidump)")
            if not path:
                return
            target_path = path
            
        new_name = os.path.basename(target_path).replace(".hash.mkaidump", "").replace(".mkaidump", "")
        
        if self.group_name and new_name != self.group_name:
            if new_name in groups:
                self._show_silent_msg("Ошибка" if self.is_ru else "Error", "Эталон с таким именем уже добавлен!" if self.is_ru else "Group already exists!")
                return
                
        success = self.train_and_save(target_path, is_hash_only=False)
        if not success:
            return
            
        if self.group_name and new_name != self.group_name:
            if self.group_name in groups:
                groups.pop(self.group_name)
                
        groups[new_name] = {"enabled": True, "path": target_path}
        self.group_name = new_name
        settings["groups"] = groups
        save_ai_settings(settings)
        
        self.dump_path = target_path
        def format_path(path):
            if not path: return ""
            parts = path.replace("\\", "/").split("/")
            if len(parts) > 3: return f"{parts[0]}/.../{parts[-2]}/{parts[-1]}"
            return path
        self.lbl_path.setText(format_path(self.dump_path))
        self.btn_open_folder.setEnabled(True)
        
        self.btn_save.setEnabled(True)
        self.btn_save.setStyleSheet("background-color: #3b82f6; border: none; padding: 6px 16px; border-radius: 4px; font-weight: bold; color: white;")
        
        self.has_changes = False
        self.btn_save_hash.setEnabled(True)
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
        if not hasattr(self, "trained_status"): self.trained_status = {}
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
            success = False
            try:
                stat = os.stat(path)
                if search_type == "face":
                    faces = self.classifier.cache.get_file_faces(path, stat.st_mtime, stat.st_size)
                    if faces is None:
                        faces = self.classifier.ai.detect_and_extract_faces(path)
                        if faces is not None:
                            self.classifier.cache.save_file_faces(path, stat.st_mtime, stat.st_size, faces)
                    if faces:
                        success = True
                        for f in faces: pos_features.append(f["descriptor"])
                else:
                    emb = self.classifier.cache.get_image_embedding(path, stat.st_mtime, stat.st_size)
                    if emb is None:
                        emb = self.classifier.ai.extract_image_embedding(path)
                        if emb is not None:
                            self.classifier.cache.save_image_embedding(path, stat.st_mtime, stat.st_size, emb)
                    if emb is not None:
                        success = True
                        pos_features.append(emb)
            except Exception:
                pass
            self.trained_status[path] = success
                
        for path in self.pending_neg:
            if not os.path.exists(path): continue
            success = False
            try:
                stat = os.stat(path)
                if search_type == "face":
                    faces = self.classifier.cache.get_file_faces(path, stat.st_mtime, stat.st_size)
                    if faces is None:
                        faces = self.classifier.ai.detect_and_extract_faces(path)
                        if faces is not None:
                            self.classifier.cache.save_file_faces(path, stat.st_mtime, stat.st_size, faces)
                    if faces:
                        success = True
                        for f in faces: neg_features.append(f["descriptor"])
                else:
                    emb = self.classifier.cache.get_image_embedding(path, stat.st_mtime, stat.st_size)
                    if emb is None:
                        emb = self.classifier.ai.extract_image_embedding(path)
                        if emb is not None:
                            self.classifier.cache.save_image_embedding(path, stat.st_mtime, stat.st_size, emb)
                    if emb is not None:
                        success = True
                        neg_features.append(emb)
            except Exception:
                pass
            self.trained_status[path] = success
                
        if not pos_features and not is_hash_only:
            self._show_silent_msg("Ошибка", "Не найдено ни одного лица/вектора в эталонах!")
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
        self.reload_thumbnails()
        return True

    def train_group_ui(self):
        self.btn_train.setEnabled(False)
        self.btn_train.setText("Расчет..." if self.is_ru else "Processing...")
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        
        if not self.classifier.ai.initialize_sessions():
            self.btn_train.setEnabled(True)
            self.btn_train.setText("Обучить" if self.is_ru else "Train")
            return
            
        search_type = "face" if self.rad_face.isChecked() else "general"
        if not hasattr(self, "trained_status"):
            self.trained_status = {}
            
        for path in self.pending_pos + self.pending_neg:
            if not os.path.exists(path): continue
            success = False
            try:
                stat = os.stat(path)
                if search_type == "face":
                    faces = self.classifier.cache.get_file_faces(path, stat.st_mtime, stat.st_size)
                    if faces is None:
                        faces = self.classifier.ai.detect_and_extract_faces(path)
                        if faces is not None:
                            self.classifier.cache.save_file_faces(path, stat.st_mtime, stat.st_size, faces)
                    if faces:
                        success = True
                else:
                    emb = self.classifier.cache.get_image_embedding(path, stat.st_mtime, stat.st_size)
                    if emb is None:
                        emb = self.classifier.ai.extract_image_embedding(path)
                        if emb is not None:
                            self.classifier.cache.save_image_embedding(path, stat.st_mtime, stat.st_size, emb)
                    if emb is not None:
                        success = True
            except Exception:
                pass
            self.trained_status[path] = success
                    
        self.reload_thumbnails()
        self.btn_train.setEnabled(True)
        self.btn_train.setText("Обучить" if self.is_ru else "Train")
        self._show_silent_msg("Успех", "Обучение завершено успешно!" if self.is_ru else "Training completed successfully!")
        
    def save_hash_dump(self):
        default_name = self.group_name if self.group_name else "Новый_хэш_эталон"
        default_name = default_name.replace(".hash.mkaidump", "").replace(".mkaidump", "")
        from .logic_ai_classifier import get_ai_assets_dir
        default_path = os.path.join(get_ai_assets_dir(), default_name + ".hash.mkaidump")
        
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт хэш-дампа", default_path, "Hash Dumps (*.hash.mkaidump)")
        if path:
            if not path.endswith(".hash.mkaidump"):
                if path.endswith(".mkaidump"):
                    path = path.replace(".mkaidump", ".hash.mkaidump")
                else:
                    path += ".hash.mkaidump"
                    
            if self.has_changes:
                self.train_group_ui()
                
            success = self.train_and_save(path, is_hash_only=True)
            pass

    def delete_group_ui(self):
        reply = self._show_silent_question(
            "Удалить эталон" if self.is_ru else "Delete Reference Group",
            f"Вы действительно хотите физически удалить файл эталона '{self.group_name}' с диска?"
        )
        if reply == QMessageBox.StandardButton.Yes:
            settings = load_ai_settings()
            if "groups" in settings and self.group_name in settings["groups"]:
                del settings["groups"][self.group_name]
                save_ai_settings(settings)
            
            if self.dump_path and os.path.exists(self.dump_path):
                try:
                    os.remove(self.dump_path)
                except Exception as e:
                    self._show_silent_msg("Ошибка", f"Не удалось удалить файл: {e}")
            self.accept()

    def closeEvent(self, event):
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().closeEvent(event)
