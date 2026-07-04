import os
import shutil
import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QButtonGroup, QRadioButton, QMessageBox, QFileDialog, QTabWidget, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from config import AppContext
from .logic_ai_classifier import get_ai_assets_dir, load_ai_settings, save_ai_settings
from .ui_widgets import RefImagesListWidget
import cv2
from PyQt6.QtGui import QPixmap, QImage

class AiGroupSettingsDialog(QDialog):
    def __init__(self, classifier, group_name: str = None, parent=None):
        super().__init__(parent)
        self.classifier = classifier
        self.group_name = group_name
        self.is_ru = AppContext.is_ru()
        self.has_changes = False
        
        self.pending_positive = []
        self.pending_negative = []
        
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
        self.txt_name.textChanged.connect(self._on_name_changed)
        layout.addWidget(self.txt_name)
        
        # 2. Тип анализа
        layout.addWidget(QLabel("Тип анализа:" if self.is_ru else "Analysis Type:"))
        
        is_face_type = True
        if self.group_name:
            settings = load_ai_settings()
            group_info = settings.get("groups", {}).get(self.group_name, {})
            is_face_type = group_info.get("type", "face") == "face"
            
        self.btn_group = QButtonGroup(self)
        self.rad_general = QRadioButton(" Общее сходство" if self.is_ru else " General Similarity")
        self.rad_face = QRadioButton(" Поиск лиц" if self.is_ru else " Face Search")
        
        rad_style = """
            QRadioButton {
                background-color: #3b3b3b;
                color: #e0e0e0;
                border-radius: 14px;
                padding: 7px 12px;
                margin: 2px 0px;
                font-weight: bold;
                font-size: 13px;
                border: 1px solid #555;
            }
            QRadioButton:hover {
                background-color: #4a4a4a;
                border: 1px solid #666;
            }
            QRadioButton::indicator {
                width: 0px;
                height: 0px;
            }
            QRadioButton:checked {
                background-color: #3b82f6;
                color: white;
                border: 1px solid #2563eb;
            }
        """
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
            
        type_layout = QHBoxLayout()
        type_layout.addWidget(self.rad_general)
        type_layout.addWidget(self.rad_face)
        type_layout.addStretch()
        layout.addLayout(type_layout)
        
        # 3. Вкладки (Позитивы / Негативы)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #444; border-radius: 4px; }
            QTabBar::tab { background: #2b2b2b; border: 1px solid #444; padding: 8px 16px; margin-right: 2px; }
            QTabBar::tab:selected { background: #3b82f6; border: 1px solid #2563eb; font-weight: bold; }
        """)
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
        
        self.btn_save = QPushButton("Сохранить" if self.is_ru else "Save")
        self.btn_save.setStyleSheet("background-color: #3b82f6; border: none; padding: 6px 16px; border-radius: 4px; font-weight: bold;")
        self.btn_save.clicked.connect(self.save_settings)
        
        buttons_layout.addWidget(self.btn_cancel)
        buttons_layout.addWidget(self.btn_save)
        layout.addLayout(buttons_layout)
        
        # Tooltip для Bounding Boxes
        from .ui_ai_tab import ImageHoverToolTip
        self.hover_tooltip = ImageHoverToolTip(self)
        self.list_pos.item_hovered.connect(self._on_item_hover)
        self.list_pos.hover_left.connect(self.hover_tooltip.hide)
        self.list_neg.item_hovered.connect(self._on_item_hover)
        self.list_neg.hover_left.connect(self.hover_tooltip.hide)
        
        if self.group_name:
            self.reload_thumbnails()
        self._on_name_changed(self.txt_name.text())

    def _setup_tab(self, tab: QWidget, is_positive: bool):
        t_layout = QVBoxLayout(tab)
        t_layout.setContentsMargins(10, 10, 10, 10)
        
        lbl_drop = QLabel("Перетащите файлы картинок (.png, .jpg) прямо в поле ниже:" if self.is_ru else "Drag and drop image files (.png, .jpg) directly to the area below:")
        lbl_drop.setStyleSheet("color: #aaa; font-size: 11px; font-style: italic;")
        t_layout.addWidget(lbl_drop)
        
        list_widget = RefImagesListWidget(self)
        list_widget.files_dropped.connect(lambda files: self.add_dropped_files(files, is_positive))
        t_layout.addWidget(list_widget, 1)
        
        if is_positive:
            self.list_pos = list_widget
        else:
            self.list_neg = list_widget
            
        btn_layout = QHBoxLayout()
        btn_add = QPushButton("Добавить файлы" if self.is_ru else "Add Files")
        btn_add.setStyleSheet("background-color: #444; border: 1px solid #555; padding: 6px 12px; border-radius: 4px;")
        btn_add.clicked.connect(lambda: self.choose_files(is_positive))
        
        btn_del = QPushButton("Удалить выбранные" if self.is_ru else "Delete Selected")
        btn_del.setStyleSheet("background-color: #ef4444; border: none; padding: 6px 12px; border-radius: 4px;")
        btn_del.clicked.connect(lambda: self.delete_selected_files(is_positive))
        
        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_del)
        btn_layout.addStretch()
        t_layout.addLayout(btn_layout)

    def _on_name_changed(self, text):
        is_valid = bool(text.strip())
        self.btn_save.setEnabled(is_valid)
        if self.group_name:
            self.btn_train.setEnabled(is_valid)
        else:
            self.btn_train.setEnabled(False) # Нельзя обучать пока не сохранено
            
        active_style = "background-color: #3b82f6; color: white; border: none; padding: 6px 16px; border-radius: 4px; font-weight: bold;"
        disabled_style = "background-color: #222; color: #555; border: 1px solid #333; padding: 6px 16px; border-radius: 4px; font-weight: bold;"
        
        self.btn_save.setStyleSheet(active_style if is_valid else disabled_style)
        
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
        from PyQt6.QtWidgets import QListWidgetItem
        target_list = self.pending_pos if is_positive else self.pending_neg
        target_widget = self.list_pos if is_positive else self.list_neg
        
        if not hasattr(self, "pending_pos"):
            self.pending_pos = []
            self.pending_neg = []
            
        for path in file_paths:
            if path not in target_list:
                if is_positive:
                    self.pending_pos.append(path)
                else:
                    self.pending_neg.append(path)
                item = QListWidgetItem()
                item.setIcon(QIcon(path))
                item.setData(Qt.ItemDataRole.UserRole, path)
                item.setToolTip(os.path.basename(path))
                target_widget.addItem(item)
                
    def delete_selected_files(self, is_positive):
        target_widget = self.list_pos if is_positive else self.list_neg
        selected = target_widget.selectedItems()
        if not selected: return
        
        for item in selected:
            fp = item.data(Qt.ItemDataRole.UserRole)
            if hasattr(self, "pending_pos") and fp in self.pending_pos:
                self.pending_pos.remove(fp)
            elif hasattr(self, "pending_neg") and fp in self.pending_neg:
                self.pending_neg.remove(fp)
            elif self.group_name and os.path.exists(fp):
                try:
                    os.remove(fp)
                    self.has_changes = True
                except:
                    pass
            target_widget.takeItem(target_widget.row(item))

    def reload_thumbnails(self):
        self.list_pos.clear()
        self.list_neg.clear()
        
        if not self.group_name: return
        
        group_dir = os.path.join(get_ai_assets_dir(), self.group_name)
        neg_dir = os.path.join(group_dir, "negative")
        
        from PyQt6.QtWidgets import QListWidgetItem
        
        if os.path.exists(group_dir):
            for f in os.listdir(group_dir):
                fp = os.path.join(group_dir, f)
                if os.path.isfile(fp):
                    item = QListWidgetItem()
                    item.setIcon(QIcon(fp))
                    item.setData(Qt.ItemDataRole.UserRole, fp)
                    item.setToolTip(f)
                    self.list_pos.addItem(item)
                    
        if os.path.exists(neg_dir):
            for f in os.listdir(neg_dir):
                fp = os.path.join(neg_dir, f)
                if os.path.isfile(fp):
                    item = QListWidgetItem()
                    item.setIcon(QIcon(fp))
                    item.setData(Qt.ItemDataRole.UserRole, fp)
                    item.setToolTip(f)
                    self.list_neg.addItem(item)
                    
    def _on_item_hover(self, path, global_pos):
        if not path or not os.path.exists(path):
            return
            
        # Draw bounding boxes if it's a face search group
        if self.rad_face.isChecked() and self.classifier.ai.initialize_sessions():
            try:
                faces = self.classifier.ai.detect_and_extract_faces(path)
                if faces:
                    import numpy as np
                    from PIL import Image
                    with Image.open(path) as img:
                        img = img.convert('RGB')
                        img_data = np.array(img, dtype=np.uint8)
                    
                    bgr_img = cv2.cvtColor(img_data, cv2.COLOR_RGB2BGR)
                    for face in faces:
                        x, y, w, h = face["bbox"]
                        cv2.rectangle(bgr_img, (x, y), (x+w, y+h), (0, 255, 0), 2)
                        
                    rgb_img = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2RGB)
                    h, w, ch = rgb_img.shape
                    bytes_per_line = ch * w
                    qt_img = QImage(rgb_img.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                    pixmap = QPixmap.fromImage(qt_img)
                    
                    # scale down if too big
                    if pixmap.width() > 300 or pixmap.height() > 300:
                        pixmap = pixmap.scaled(300, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                        
                    self.hover_tooltip.setPixmap(pixmap)
                    self.hover_tooltip.move(global_pos)
                    self.hover_tooltip.show()
                    return
            except Exception as e:
                logging.error(f"Error drawing bbox: {e}")
                
        self.hover_tooltip.show_image(path, global_pos)

    def save_settings(self):
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
                
            old_dir = os.path.join(get_ai_assets_dir(), self.group_name)
            new_dir = os.path.join(get_ai_assets_dir(), new_name)
            if os.path.exists(old_dir):
                os.rename(old_dir, new_dir)
            
            info = groups.pop(self.group_name)
            groups[new_name] = info
            self.group_name = new_name
            self.has_changes = True
            
        if not self.group_name:
            if new_name in groups:
                QMessageBox.warning(self, "Ошибка" if self.is_ru else "Error", 
                                    "Группа с таким именем уже существует!" if self.is_ru else "Group already exists!")
                return
            groups[new_name] = {"enabled": True, "type": "face" if self.rad_face.isChecked() else "general"}
            self.group_name = new_name
            self.has_changes = True
            
        group_dir = os.path.join(get_ai_assets_dir(), self.group_name)
        neg_dir = os.path.join(group_dir, "negative")
        os.makedirs(group_dir, exist_ok=True)
        os.makedirs(neg_dir, exist_ok=True)
        
        if hasattr(self, "pending_pos"):
            for fp in self.pending_pos:
                if os.path.exists(fp):
                    shutil.copy2(fp, os.path.join(group_dir, os.path.basename(fp)))
                    self.has_changes = True
        
        if hasattr(self, "pending_neg"):
            for fp in self.pending_neg:
                if os.path.exists(fp):
                    shutil.copy2(fp, os.path.join(neg_dir, os.path.basename(fp)))
                    self.has_changes = True
                    
        selected_type = "face" if self.rad_face.isChecked() else "general"
        if groups[self.group_name].get("type") != selected_type:
            groups[self.group_name]["type"] = selected_type
            self.has_changes = True
            
        if self.has_changes:
            save_ai_settings(settings)
            
        self.accept()

    def train_group_ui(self):
        if not self.group_name: return
        
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
            
        success = self.classifier.train_group(self.group_name, progress_callback=on_prog, force_recalculate=True)
        
        self.btn_train.setEnabled(True)
        self.btn_train.setText("Обучить" if self.is_ru else "Train")
        
        if success:
            QMessageBox.information(self, "Успех" if self.is_ru else "Success", 
                                    "Обучение эталона завершено!" if self.is_ru else "Reference training completed!")
            self.reload_thumbnails()
            
            main_tab = self.parent()
            if main_tab and hasattr(main_tab, 'update_cache_info_ai'):
                main_tab.update_cache_info_ai()

    def delete_group_ui(self):
        reply = QMessageBox.question(
            self,
            "Удалить группу эталонов" if self.is_ru else "Delete Reference Group",
            f"Вы уверены, что хотите полностью удалить группу эталонов '{self.group_name}'?\nЭто приведет к безвозвратному удалению всех файлов-примеров и настроек этой группы."
            if self.is_ru else
            f"Are you sure you want to delete the reference group '{self.group_name}'?\nAll reference image files and configurations for this group will be permanently deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            group_dir = os.path.join(get_ai_assets_dir(), self.group_name)
            if os.path.exists(group_dir):
                shutil.rmtree(group_dir, ignore_errors=True)
            
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
            self.reject() # close without saving other changes
