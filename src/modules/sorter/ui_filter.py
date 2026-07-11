
import os
import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, 
    QScrollArea, QWidget, QCheckBox, QLineEdit, QFileDialog, QDoubleSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QPalette, QIcon

from config import AppContext, APP_DESIGN
from ui_widgets_base import FlowLayout, SizeFilterWidget
from .utils_extensions import EXT_CATEGORIES

class SorterFilterDialog(QDialog):
    def __init__(self, unsort_dir, found_extensions, current_selection, current_mode, recursive_state, min_size=0.0, max_size=0.0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройка директории и типов файлов" if AppContext.LANG == "RU" else "Directory & File Types Setup")
        self.resize(800, 600)
        self.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: white; }
            QLabel { color: #cccccc; }
            QPushButton { background-color: #444; border: 1px solid #555; color: white; border-radius: 4px; padding: 6px; }
            QPushButton:hover { background-color: #555; }
            QScrollArea { border: none; background: transparent; }
            QCheckBox { color: #ccc; spacing: 8px; font-size: 13px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; border: 2px solid #555; background: #333; }
            QCheckBox::indicator:checked { background-color: #3b82f6; border-color: #3b82f6; }
            QCheckBox::indicator:hover { border-color: #666; }
        """)
        
        self.unsort_dir = unsort_dir
        self.extension_counts = found_extensions if isinstance(found_extensions, dict) else {k: 0 for k in found_extensions}
        self.found_extensions = set(self.extension_counts.keys())
        self.selected_exts = set(current_selection)
        self.mode = current_mode
        self.min_size = min_size
        self.max_size = max_size
        self.icons_dir = AppContext.find_resource_dir("icons")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Compact Header with Title
        header = QFrame()
        header.setStyleSheet("background-color: #1e1e1e;")
        header.setFixedHeight(40)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(15, 0, 15, 0)
        
        lbl_title = QLabel("НАСТРОЙКА ДИРЕКТОРИИ И ТИПОВ ФАЙЛОВ" if AppContext.LANG == "RU" else "DIRECTORY & FILE TYPES SETUP")
        lbl_title.setStyleSheet("color: white; font-size: 13px; font-weight: bold; background: transparent;")
        header_layout.addWidget(lbl_title, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(header)
        
        # Directory Selection Row
        dir_frame = QFrame()
        dir_frame.setStyleSheet("background-color: #202020; border-bottom: 1px solid #333333;")
        dir_layout = QHBoxLayout(dir_frame)
        dir_layout.setContentsMargins(15, 8, 15, 8)
        dir_layout.setSpacing(10)
        
        lbl_dir = QLabel((AppContext.tr("lbl_unsort") or "Входящие") + ":" if AppContext.LANG == "RU" else "Inbox:")
        lbl_dir.setStyleSheet("color: #aaaaaa; font-size: 13px; font-weight: bold; background: transparent;")
        dir_layout.addWidget(lbl_dir)
        
        self.txt_dir = QLineEdit()
        self.txt_dir.setReadOnly(True)
        self.txt_dir.setText(self.unsort_dir or "")
        self.txt_dir.setPlaceholderText("Выберите папку входящих..." if AppContext.LANG == "RU" else "Select incoming folder...")
        self.txt_dir.setStyleSheet("""
            QLineEdit {
                background-color: #1a1a1a;
                border: 1px solid #444444;
                color: #ffffff;
                border-radius: 4px;
                padding: 6px;
                font-size: 12px;
            }
        """)
        dir_layout.addWidget(self.txt_dir)
        
        btn_browse = QPushButton("Обзор..." if AppContext.LANG == "RU" else "Browse...")
        btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browse.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                border: 1px solid #2563eb;
                color: white;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
        """)
        btn_browse.clicked.connect(self.browse_unsort_dir)
        dir_layout.addWidget(btn_browse)
        
        self.chk_recursive = QCheckBox(AppContext.tr("filter_subfolders"))
        self.chk_recursive.setChecked(recursive_state)
        self.chk_recursive.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_recursive.stateChanged.connect(self.update_extensions_matrix)
        dir_layout.addWidget(self.chk_recursive)
        
        layout.addWidget(dir_frame)
        
        # Mode Selection (Include/Exclude)
        mode_container = QFrame()
        mode_container.setStyleSheet("background-color: #2b2b2b;")
        ml = QHBoxLayout(mode_container)
        ml.setContentsMargins(15, 15, 15, 15)
        ml.setSpacing(10)
        
        self.btn_include = QPushButton(AppContext.tr("filter_mode_include"))
        self.btn_include.setCheckable(True)
        self.btn_include.clicked.connect(lambda: self.set_mode('include'))
        self.btn_include.setMinimumHeight(44)
        
        self.btn_exclude = QPushButton(AppContext.tr("filter_mode_exclude"))
        self.btn_exclude.setCheckable(True)
        self.btn_exclude.clicked.connect(lambda: self.set_mode('exclude'))
        self.btn_exclude.setMinimumHeight(44)
        
        ml.addWidget(self.btn_include)
        ml.addWidget(self.btn_exclude)
        layout.addWidget(mode_container)
        
        # Фильтр размеров файлов
        size_frame = QFrame()
        size_frame.setStyleSheet("background-color: #262626; border-bottom: 1px solid #333333; border-top: 1px solid #333333;")
        size_layout = QHBoxLayout(size_frame)
        size_layout.setContentsMargins(15, 8, 15, 8)
        size_layout.setSpacing(10)
        
        lbl_size_title = QLabel("Размер файлов:" if AppContext.LANG == "RU" else "File size:")
        lbl_size_title.setStyleSheet("color: white; font-size: 13px; font-weight: bold; background: transparent;")
        size_layout.addWidget(lbl_size_title)
        
        self.size_widget = SizeFilterWidget()
        self.size_widget.set_values_mb(self.min_size, self.max_size)
        self.size_widget.valueChanged.connect(self.validate_dialog_inputs)
        size_layout.addWidget(self.size_widget)
        size_layout.addStretch()
        
        layout.addWidget(size_frame)
        
        # Extensions Matrix
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.matrix_widget = QWidget()
        self.matrix_layout = QVBoxLayout(self.matrix_widget)
        self.matrix_layout.setContentsMargins(15, 5, 15, 15)
        
        self.chip_buttons = {}
        self.render_matrix()
        
        scroll.setWidget(self.matrix_widget)
        layout.addWidget(scroll)
        
        # Compact Footer (48px high, no borders, 28px high buttons)
        footer = QFrame()
        footer.setStyleSheet("background-color: #1e1e1e;")
        footer.setFixedHeight(48)
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(15, 0, 15, 0)
        
        self.lbl_stats = QLabel(AppContext.tr("filter_stats_selected").format(len(self.selected_exts)))
        self.lbl_stats.setStyleSheet("font-size: 12px; color: #aaa;")
        fl.addWidget(self.lbl_stats)
        fl.addStretch()
        
        btn_cancel = QPushButton(AppContext.tr("btn_cancel"))
        btn_cancel.setFixedSize(100, 28)
        btn_cancel.setStyleSheet("""
            QPushButton { background-color: #333333; border: 1px solid #555555; color: white; border-radius: 4px; padding: 2px 10px; font-size: 12px; }
            QPushButton:hover { background-color: #444; }
        """)
        btn_cancel.clicked.connect(self.reject)
        fl.addWidget(btn_cancel)
        
        btn_clear = QPushButton(AppContext.tr("filter_btn_clear"))
        btn_clear.setFixedSize(120, 28)
        btn_clear.setStyleSheet("""
            QPushButton { background-color: #4b5563; border: 1px solid #6b7280; color: white; border-radius: 4px; padding: 2px 10px; font-size: 12px; }
            QPushButton:hover { background-color: #5a6575; }
        """)
        btn_clear.clicked.connect(self.clear_filter)
        fl.addWidget(btn_clear)
        
        self.btn_apply = QPushButton(AppContext.tr("filter_btn_apply"))
        self.btn_apply.setFixedHeight(28)
        self.btn_apply.setMinimumWidth(160)
        self.btn_apply.clicked.connect(self.accept)
        fl.addWidget(self.btn_apply)
        
        layout.addWidget(footer)
        
        self.set_mode(self.mode)
        self.validate_dialog_inputs()

    def validate_dialog_inputs(self):
        is_error = self.size_widget.has_error()
        self.btn_apply.setEnabled(not is_error)
        if is_error:
            self.btn_apply.setStyleSheet("""
                QPushButton { background-color: #222; border: 1px solid #333; color: #555; font-weight: bold; padding: 2px 16px; font-size: 12px; }
            """)
        else:
            self.btn_apply.setStyleSheet("""
                QPushButton { background-color: #15803d; border: 1px solid #16a34a; color: white; border-radius: 4px; font-weight: bold; padding: 2px 16px; font-size: 12px; }
                QPushButton:hover { background-color: #166534; }
            """)

    def set_mode(self, mode):
        self.mode = mode
        if mode == 'include':
            self.btn_include.setChecked(True)
            self.btn_exclude.setChecked(False)
            self.btn_include.setStyleSheet("background-color: #064e3b; color: #34d399; border: 1px solid #059669; font-weight: bold;")
            self.btn_exclude.setStyleSheet("background-color: #333; color: #888; border: 1px solid #444;")
        else:
            self.btn_include.setChecked(False)
            self.btn_exclude.setChecked(True)
            self.btn_include.setStyleSheet("background-color: #333; color: #888; border: 1px solid #444;")
            self.btn_exclude.setStyleSheet("background-color: #450a0a; color: #fca5a5; border: 1px solid #b91c1c; font-weight: bold;")

    def render_matrix(self):
        """Render extensions grouped by category like in cleaner module."""
        tr_key_map = {
            "Images": "cln_grp_images", 
            "Video": "cln_grp_video", 
            "Audio": "cln_grp_audio", 
            "Documents": "cln_grp_docs", 
            "Archives": "cln_grp_archives", 
            "Code": "cln_grp_code",
            "Other": "cln_grp_other"
        }
        
        # Group found extensions by category
        grouped = {}
        uncategorized = set()
        
        for ext in self.found_extensions:
            found_category = None
            for cat_name, cat_exts in EXT_CATEGORIES.items():
                if ext.lower() in cat_exts:
                    found_category = cat_name
                    break
            
            if found_category:
                if found_category not in grouped:
                    grouped[found_category] = []
                grouped[found_category].append(ext)
            else:
                uncategorized.add(ext)
        
        # Render each category
        for group_name in ["Images", "Video", "Audio", "Documents", "Archives", "Code"]:
            if group_name not in grouped:
                continue
            items = sorted(grouped[group_name])
            
            header_frame = QFrame()
            header_layout = QHBoxLayout(header_frame)
            header_layout.setContentsMargins(0, 8, 0, 4)
            
            display_name = AppContext.tr(tr_key_map.get(group_name, group_name.upper()))
            lbl_g = QLabel(display_name.upper())
            lbl_g.setStyleSheet("color: #888; font-weight: bold; font-size: 11px;")
            header_layout.addWidget(lbl_g)
            
            btn_toggle_group = QPushButton()
            icon_gray = os.path.join(self.icons_dir, "square-chevron-down-gray.svg").replace("\\", "/")
            icon_white = os.path.join(self.icons_dir, "square-chevron-down.svg").replace("\\", "/")
            btn_toggle_group.setFixedSize(24, 24)
            btn_toggle_group.setIconSize(QSize(16, 16))
            btn_toggle_group.setToolTip(AppContext.tr("cln_btn_select_group"))
            btn_toggle_group.setStyleSheet(f"""
                QPushButton {{ 
                    background-color: transparent; 
                    border: 1px solid #555; 
                    border-radius: 4px; 
                    qproperty-icon: url("{icon_gray}");
                }}
                QPushButton:hover {{ 
                    background-color: rgba(59, 130, 246, 0.1); 
                    border-color: #3b82f6; 
                    qproperty-icon: url("{icon_white}");
                }}
            """)
            btn_toggle_group.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_toggle_group.clicked.connect(lambda _, i=items: self.toggle_group(i))
            header_layout.addWidget(btn_toggle_group)
            header_layout.addStretch()
            
            self.matrix_layout.addWidget(header_frame)
            
            flow_container = QWidget()
            flow = FlowLayout(flow_container, margin=0, spacing=8)
            
            for ext in items:
                count = self.extension_counts.get(ext, 0)
                btn_text = f"{ext} ({count})" if count > 0 else ext
                btn = QPushButton(btn_text)
                btn.setCheckable(True)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda _, e=ext: self.toggle_ext(e))
                
                is_selected = ext in self.selected_exts
                btn.setChecked(is_selected)
                self.update_chip_style(btn, is_selected)
                
                self.chip_buttons[ext] = btn
                flow.addWidget(btn)
            
            self.matrix_layout.addWidget(flow_container)
        
        # Other category for uncategorized extensions
        if uncategorized:
            header_frame = QFrame()
            header_layout = QHBoxLayout(header_frame)
            header_layout.setContentsMargins(0, 8, 0, 4)
            
            display_name = AppContext.tr(tr_key_map.get("Other", "OTHER"))
            lbl_g = QLabel(display_name.upper())
            lbl_g.setStyleSheet("color: #888; font-weight: bold; font-size: 11px;")
            header_layout.addWidget(lbl_g)
            
            btn_toggle_group = QPushButton()
            icon_gray = os.path.join(self.icons_dir, "square-chevron-down-gray.svg").replace("\\", "/")
            icon_white = os.path.join(self.icons_dir, "square-chevron-down.svg").replace("\\", "/")
            btn_toggle_group.setFixedSize(24, 24)
            btn_toggle_group.setIconSize(QSize(16, 16))
            btn_toggle_group.setToolTip(AppContext.tr("cln_btn_select_group"))
            btn_toggle_group.setStyleSheet(f"""
                QPushButton {{ 
                    background-color: transparent; 
                    border: 1px solid #555; 
                    border-radius: 4px; 
                    qproperty-icon: url("{icon_gray}");
                }}
                QPushButton:hover {{ 
                    background-color: rgba(59, 130, 246, 0.1); 
                    border-color: #3b82f6; 
                    qproperty-icon: url("{icon_white}");
                }}
            """)
            btn_toggle_group.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_toggle_group.clicked.connect(lambda _, i=list(uncategorized): self.toggle_group(i))
            header_layout.addWidget(btn_toggle_group)
            header_layout.addStretch()
            
            self.matrix_layout.addWidget(header_frame)
            
            flow_container = QWidget()
            flow = FlowLayout(flow_container, margin=0, spacing=8)
            
            for ext in sorted(uncategorized):
                count = self.extension_counts.get(ext, 0)
                btn_text = f"{ext} ({count})" if count > 0 else ext
                btn = QPushButton(btn_text)
                btn.setCheckable(True)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda _, e=ext: self.toggle_ext(e))
                
                is_selected = ext in self.selected_exts
                btn.setChecked(is_selected)
                self.update_chip_style(btn, is_selected)
                
                self.chip_buttons[ext] = btn
                flow.addWidget(btn)
            
            self.matrix_layout.addWidget(flow_container)
        
        self.matrix_layout.addStretch()

    def update_chip_style(self, btn, checked):
        if checked:
            btn.setStyleSheet("QPushButton { background-color: rgba(59, 130, 246, 0.2); border: 1px solid #3b82f6; color: white; border-radius: 12px; padding: 4px 12px; font-size: 13px; font-weight: bold; }")
        else:
            btn.setStyleSheet("QPushButton { background-color: #333; border: 1px solid #444; color: #ccc; border-radius: 12px; padding: 4px 12px; font-size: 13px; } QPushButton:hover { background-color: #444; color: white; }")

    def toggle_ext(self, ext):
        if ext in self.selected_exts:
            self.selected_exts.remove(ext)
            self.update_chip_style(self.chip_buttons[ext], False)
        else:
            self.selected_exts.add(ext)
            self.update_chip_style(self.chip_buttons[ext], True)
        self.update_stats()

    def toggle_group(self, items):
        """Toggle all extensions in a group."""
        all_selected = all(ext in self.selected_exts for ext in items)
        should_select = not all_selected
        
        for ext in items:
            if ext not in self.chip_buttons:
                continue
            if should_select:
                if ext not in self.selected_exts:
                    self.selected_exts.add(ext)
                    self.update_chip_style(self.chip_buttons[ext], True)
                    self.chip_buttons[ext].setChecked(True)
            else:
                if ext in self.selected_exts:
                    self.selected_exts.remove(ext)
                    self.update_chip_style(self.chip_buttons[ext], False)
                    self.chip_buttons[ext].setChecked(False)
        self.update_stats()

    def update_stats(self):
        self.lbl_stats.setText(AppContext.tr("filter_stats_selected").format(len(self.selected_exts)))

    def clear_filter(self):
        """Clear all selected extensions."""
        for ext in list(self.selected_exts):
            if ext in self.chip_buttons:
                self.update_chip_style(self.chip_buttons[ext], False)
                self.chip_buttons[ext].setChecked(False)
        self.selected_exts.clear()
        self.update_stats()

    def browse_unsort_dir(self):
        start_dir = self.unsort_dir if self.unsort_dir and os.path.exists(self.unsort_dir) else os.path.expanduser("~")
        p = QFileDialog.getExistingDirectory(None, AppContext.tr("dlg_select_inbox") or "Выбор папки входящих", start_dir)
        if p:
            self.unsort_dir = os.path.normpath(p)
            self.txt_dir.setText(self.unsort_dir)
            self.update_extensions_matrix()

    def scan_directory_extensions(self, directory, recursive):
        found_exts = set()
        if directory:
            from utils_io import ensure_long_path
            long_dir = ensure_long_path(directory)
            if os.path.exists(long_dir):
                try:
                    if recursive:
                        for root, _, files in os.walk(long_dir):
                            for f in files:
                                ext = os.path.splitext(f)[1].lower()
                                if ext:
                                    found_exts.add(ext)
                    else:
                        for f in os.listdir(long_dir):
                            if os.path.isfile(os.path.join(long_dir, f)):
                                ext = os.path.splitext(f)[1].lower()
                                if ext:
                                    found_exts.add(ext)
                except Exception as e:
                    logging.error(f"Error scanning directory extensions: {e}", exc_info=True)
        return found_exts

    def update_extensions_matrix(self):
        # 1. Сканируем новые расширения
        new_exts = self.scan_directory_extensions(self.unsort_dir, self.chk_recursive.isChecked())
        self.found_extensions = new_exts
        
        # 2. Очищаем выбранные расширения, которых нет в новой папке
        self.selected_exts = self.selected_exts.intersection(self.found_extensions)
        
        # 3. Очищаем старую матрицу
        self.clear_matrix()
        
        # 4. Рендерим новую матрицу
        self.render_matrix()
        
        # 5. Обновляем статистику
        self.update_stats()

    def clear_matrix(self):
        self.chip_buttons.clear()
        if self.matrix_layout is not None:
            while self.matrix_layout.count() > 0:
                item = self.matrix_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                else:
                    layout = item.layout()
                    if layout is not None:
                        self.clear_layout(layout)

    def clear_layout(self, layout):
        if layout is not None:
            while layout.count() > 0:
                item = layout.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.deleteLater()
                else:
                    sub_layout = item.layout()
                    if sub_layout is not None:
                        self.clear_layout(sub_layout)

    def get_result(self):
        return {
            'unsort_dir': self.unsort_dir,
            'mode': self.mode, 
            'exts': list(self.selected_exts),
            'recursive': self.chk_recursive.isChecked(),
            'min_size': self.size_widget.get_min_mb(),
            'max_size': self.size_widget.get_max_mb()
        }
