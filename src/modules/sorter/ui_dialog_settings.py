import os
from PyQt6.QtWidgets import (
    QDialog, QGridLayout, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QCheckBox, QComboBox, QLineEdit, QFrame, QSpacerItem, QSizePolicy, QFileDialog,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence
from config import AppContext
from .logic_config import ConfigManager

class SorterSettingsDialog(QDialog):
    def __init__(self, current_config, parent=None):
        super().__init__(parent)
        self.config = current_config
        is_ru = (AppContext.LANG == "RU")
        
        self.setWindowTitle("Настройки сортировщика" if is_ru else "Sorter Settings")
        self.setFixedSize(450, 320)
        self.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: white; }
            QLabel { color: #cccccc; font-size: 13px; font-weight: bold; }
            QLineEdit { color: white; background-color: #444; border: 1px solid #555; padding: 5px; border-radius: 4px;}
            QComboBox { background-color: #444; color: white; padding: 5px; border: 1px solid #555; border-radius: 4px; min-width: 180px; combobox-popup: 0; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { color: white; background-color: #444; selection-background-color: #3b82f6; padding: 0px; margin: 0px; outline: 0px; }
            QPushButton { color: white; background-color: #555; border: 1px solid #444; padding: 6px; border-radius: 3px; font-weight: bold;}
            QPushButton:hover { background-color: #666; }
            QCheckBox { color: white; font-weight: bold; spacing: 8px; }
            QFrame[frameShape="4"] { color: #444; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        # --- Сортировка ---
        row_sort = QHBoxLayout()
        lbl_sort = QLabel("Сортировка файлов:" if is_ru else "File Sorting:")
        row_sort.addWidget(lbl_sort)
        
        self.cb_sort = QComboBox()
        self.sort_options = [
            ("name_asc", "Имя (А-Я)" if is_ru else "Name (A-Z)"),
            ("name_desc", "Имя (Я-А)" if is_ru else "Name (Z-A)"),
            ("type_asc", "Тип файла" if is_ru else "File Type"),
            ("size_desc", "Размер (По убыванию)" if is_ru else "Size (Large to Small)"),
            ("size_asc", "Размер (По возрастанию)" if is_ru else "Size (Small to Large)"),
            ("mtime_desc", "Дата изменения (Новые)" if is_ru else "Date Modified (Newest)"),
            ("mtime_asc", "Дата изменения (Старые)" if is_ru else "Date Modified (Oldest)"),
            ("ctime_desc", "Дата создания (Новые)" if is_ru else "Date Created (Newest)"),
            ("ctime_asc", "Дата создания (Старые)" if is_ru else "Date Created (Oldest)"),
        ]
        for key, name in self.sort_options:
            self.cb_sort.addItem(name, key)
            
        # Устанавливаем текущую сортировку
        current_sort = self.config.get("sort_type", "name_asc")
        for idx in range(self.cb_sort.count()):
            if self.cb_sort.itemData(idx) == current_sort:
                self.cb_sort.setCurrentIndex(idx)
                break
        row_sort.addWidget(self.cb_sort)
        layout.addLayout(row_sort)
        
        self.add_line(layout)
        
        # --- Сканирование ---
        self.cb_recursive = QCheckBox("Сканировать вложенные папки" if is_ru else "Scan subfolders")
        self.cb_recursive.setChecked(self.config.get("scan_subfolders", False))
        layout.addWidget(self.cb_recursive)
        
        # --- Фильтр расширений ---
        lbl_filter = QLabel("Фильтр расширений (через запятую):" if is_ru else "Extension Filter (comma separated):")
        layout.addWidget(lbl_filter)
        
        row_filter = QHBoxLayout()
        self.e_filter = QLineEdit(self.config.get("filter_extensions", ""))
        self.e_filter.setPlaceholderText("например: png, jpg, mp4" if is_ru else "e.g. png, jpg, mp4")
        row_filter.addWidget(self.e_filter, stretch=1)
        
        self.cb_filter_mode = QComboBox()
        self.cb_filter_mode.addItem("Включать" if is_ru else "Include", "include")
        self.cb_filter_mode.addItem("Исключать" if is_ru else "Exclude", "exclude")
        
        current_mode = self.config.get("filter_mode", "include")
        if current_mode == "exclude":
            self.cb_filter_mode.setCurrentIndex(1)
        else:
            self.cb_filter_mode.setCurrentIndex(0)
            
        row_filter.addWidget(self.cb_filter_mode)
        layout.addLayout(row_filter)
        
        layout.addSpacing(10)
        self.add_line(layout)
        layout.addSpacing(5)
        
        # --- Кнопки сохранения ---
        btn_box = QHBoxLayout()
        self.btn_save = QPushButton("Сохранить" if is_ru else "Save")
        self.btn_save.clicked.connect(self.save)
        self.btn_save.setStyleSheet("background-color: #2563eb; color: white; font-weight: bold; min-width: 90px;")
        
        self.btn_cancel = QPushButton("Отмена" if is_ru else "Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_cancel.setMinimumWidth(80)
        
        btn_box.addStretch()
        btn_box.addWidget(self.btn_save)
        btn_box.addWidget(self.btn_cancel)
        layout.addLayout(btn_box)

    def add_line(self, layout):
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #444; border: none;")
        layout.addWidget(sep)

    def save(self):
        # Обновляем конфиг новыми значениями
        self.config["sort_type"] = self.cb_sort.currentData()
        self.config["scan_subfolders"] = self.cb_recursive.isChecked()
        self.config["filter_extensions"] = self.e_filter.text().strip()
        self.config["filter_mode"] = self.cb_filter_mode.currentData()
        self.accept()


class HotkeyCaptureButton(QPushButton):
    hotkey_captured = pyqtSignal(str)

    def __init__(self, current_key="", parent=None):
        super().__init__(parent)
        self.current_key = current_key
        self.capturing = False
        self.update_button_text()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
    def update_button_text(self):
        if self.capturing:
            is_ru = (AppContext.LANG == "RU")
            self.setText("Нажмите клавишу..." if is_ru else "Press key...")
            self.setStyleSheet("background-color: #2563eb; color: white; border: 1px solid #60a5fa; font-weight: bold; min-height: 26px; padding: 2px 10px;")
        else:
            self.setText(self.current_key if self.current_key else ("[Нет]" if AppContext.LANG == "RU" else "[None]"))
            self.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; font-family: monospace; font-size: 13px; font-weight: bold; min-width: 120px; min-height: 26px; padding: 2px 10px;")

    def mousePressEvent(self, event):
        if not self.capturing:
            self.start_capture()
        super().mousePressEvent(event)

    def start_capture(self):
        self.capturing = True
        self.update_button_text()
        self.grabKeyboard()

    def cancel_capture(self):
        self.capturing = False
        self.releaseKeyboard()
        self.update_button_text()

    def keyPressEvent(self, event):
        if not self.capturing:
            super().keyPressEvent(event)
            return

        key = event.key()
        if key in (
            Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
            Qt.Key.Key_Menu, Qt.Key.Key_Super_L, Qt.Key.Key_Super_R
        ):
            return

        if key == Qt.Key.Key_Escape:
            self.cancel_capture()
            return

        modifiers = event.modifiers()
        key_val = key.value if hasattr(key, 'value') else int(key)
        
        mod_val = 0
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            mod_val |= Qt.KeyboardModifier.ControlModifier.value
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            mod_val |= Qt.KeyboardModifier.ShiftModifier.value
        if modifiers & Qt.KeyboardModifier.AltModifier:
            mod_val |= Qt.KeyboardModifier.AltModifier.value
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            mod_val |= Qt.KeyboardModifier.MetaModifier.value

        key_seq = QKeySequence(key_val | mod_val)
        key_str = key_seq.toString()

        self.current_key = key_str
        self.capturing = False
        self.releaseKeyboard()
        self.update_button_text()
        self.hotkey_captured.emit(key_str)

    def focusOutEvent(self, event):
        if self.capturing:
            self.cancel_capture()
        super().focusOutEvent(event)


class PathSettingsDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        is_ru = (AppContext.LANG == "RU")
        self.setWindowTitle(AppContext.tr("dlg_settings_title"))
        self.resize(750, 600)
        self.config = cfg.copy()
        
        self.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: white; }
            QLabel { color: white; font-size: 13px; font-weight: bold; background-color: transparent; }
            QLineEdit { color: white; background-color: #444; border: 1px solid #555; padding: 5px; border-radius: 4px; }
            QLineEdit:disabled { background-color: #333; color: #777; border: 1px solid #444; }
            QLineEdit#InvalidInput { border: 1px solid #ef4444; background-color: #451a1a; }
            QPushButton { color: white; background-color: #555; border: 1px solid #444; padding: 6px; border-radius: 3px; font-weight: bold; }
            QPushButton:hover { background-color: #666; }
            QComboBox { background-color: #444; color: white; padding: 5px; border: 1px solid #555; border-radius: 4px; combobox-popup: 0; }
            QComboBox:disabled { background-color: #333; color: #777; }
            QComboBox::item { color: white; background-color: #444; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { color: white; background-color: #444; selection-background-color: #3b82f6; padding: 0px; margin: 0px; outline: 0px; }
            QSpinBox { background-color: #444; color: white; padding: 5px; border: 1px solid #555; border-radius: 4px; }
            QCheckBox { color: white; font-weight: bold; spacing: 8px; }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        
        # QTabWidget
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::panel {
                border: 1px solid #444;
                background-color: #2b2b2b;
            }
            QTabBar::tab {
                background-color: #333;
                color: #aaa;
                border: 1px solid #444;
                border-bottom: none;
                padding: 8px 16px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-weight: bold;
                font-size: 13px;
            }
            QTabBar::tab:selected {
                background-color: #2b2b2b;
                color: white;
                border-bottom: 1px solid #2b2b2b;
            }
            QTabBar::tab:hover {
                background-color: #3d3d3d;
                color: white;
            }
        """)
        
        # Вкладка 1: Основные
        self.tab_general = QWidget()
        self.setup_general_tab()
        self.tab_widget.addTab(self.tab_general, "Основные" if is_ru else "General")
        
        # Вкладка 2: Горячие клавиши
        self.tab_hotkeys = QWidget()
        self.setup_hotkeys_tab()
        self.tab_widget.addTab(self.tab_hotkeys, "Горячие клавиши" if is_ru else "Hotkeys")
        
        main_layout.addWidget(self.tab_widget)

        # Нижняя панель кнопок
        box = QHBoxLayout()
        b_save = QPushButton(AppContext.tr("btn_save"))
        b_save.clicked.connect(self.on_save)
        b_save.setStyleSheet("background-color: #2563eb; color: white; font-weight: bold; min-width: 90px;")
        
        b_can = QPushButton(AppContext.tr("btn_cancel"))
        b_can.clicked.connect(self.reject)
        b_can.setMinimumWidth(80)
        
        box.addStretch()
        box.addWidget(b_save)
        box.addWidget(b_can)
        main_layout.addLayout(box)

    def setup_general_tab(self):
        is_ru = (AppContext.LANG == "RU")
        self.icons_dir = AppContext.find_resource_dir("icons")
        
        l = QGridLayout(self.tab_general)
        l.setContentsMargins(20, 20, 20, 20)
        l.setVerticalSpacing(12)
        l.setHorizontalSpacing(10)
        l.setColumnStretch(1, 1)
        
        # Заголовок секции
        lbl_section = QLabel("СОРТИРОВКА: НАСТРОЙКА ДИРЕКТОРИЙ" if is_ru else "SORTER: DIRECTORY SETTINGS")
        lbl_section.setStyleSheet("color: #888; font-size: 11px; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 5px;")
        l.addWidget(lbl_section, 0, 0, 1, 3)
        
        self.e_sort = self.add_path_new(l, 1, "lbl_sort", "path_sort")
        self.e_todel = self.add_path_new(l, 2, "lbl_todel", "path_todel")

        l.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding), 3, 0, 1, 3)

        # Подсказка о смене языка
        lbl_lang_hint = QLabel(
            "ℹ Для смены языка перезапустите программу и выберите язык на стартовом окне."
            if is_ru else
            "ℹ To change the language, restart the app and select your language in the launcher window."
        )
        lbl_lang_hint.setStyleSheet("color: #89b4fa; font-size: 11px; font-weight: normal; margin-top: 10px;")
        lbl_lang_hint.setWordWrap(True)
        l.addWidget(lbl_lang_hint, 5, 0, 1, 3)

    def setup_hotkeys_tab(self):
        is_ru = (AppContext.LANG == "RU")
        layout = QVBoxLayout(self.tab_hotkeys)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        lbl_info = QLabel(
            "Нажмите на кнопку с клавишей для переназначения хоткея. Нажатие Escape отменит захват." if is_ru
            else "Click a key button to reassign. Press Escape to cancel capture."
        )
        lbl_info.setStyleSheet("color: #888; font-size: 12px; font-style: italic;")
        layout.addWidget(lbl_info)
        
        self.table_hotkeys = QTableWidget()
        self.table_hotkeys.setColumnCount(2)
        self.table_hotkeys.setHorizontalHeaderLabels(
            ["Действие", "Клавиша"] if is_ru else ["Action", "Key"]
        )
        self.table_hotkeys.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_hotkeys.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table_hotkeys.setColumnWidth(1, 180)
        self.table_hotkeys.verticalHeader().setVisible(False)
        self.table_hotkeys.verticalHeader().setDefaultSectionSize(36)
        self.table_hotkeys.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        
        self.table_hotkeys.setStyleSheet("""
            QTableWidget {
                background-color: #222;
                gridline-color: #333;
                border: 1px solid #444;
                color: white;
            }
            QHeaderView::section {
                background-color: #333;
                color: #ccc;
                padding: 6px;
                border: 1px solid #444;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.table_hotkeys)
        
        self.btn_reset_all = QPushButton("Сбросить все" if is_ru else "Reset All")
        self.btn_reset_all.setStyleSheet("background-color: #991b1b; color: white; font-weight: bold; min-width: 100px;")
        self.btn_reset_all.clicked.connect(self.reset_all_hotkeys)
        
        bottom_row = QHBoxLayout()
        bottom_row.addWidget(self.btn_reset_all)
        bottom_row.addStretch()
        layout.addLayout(bottom_row)
        
        self.populate_hotkeys_table()

    def populate_hotkeys_table(self):
        self.table_hotkeys.setRowCount(0)
        self.registry = getattr(self.parent(), '_hotkey_registry', None)
        if not self.registry:
            return
            
        actions = self.registry.get_all_actions()
        is_ru = (AppContext.LANG == "RU")
        
        group_names = {
            "navigation": "Навигация" if is_ru else "Navigation",
            "file": "Операции с файлами" if is_ru else "File Operations",
            "playback": "Плеер" if is_ru else "Playback",
            "view": "Режимы просмотра" if is_ru else "View Modes"
        }
        
        sorted_actions = sorted(actions, key=lambda a: a.group)
        self.table_hotkeys.setRowCount(len(sorted_actions))
        
        for idx, action in enumerate(sorted_actions):
            lbl_desc = QLabel(action.label_ru if is_ru else action.label_en)
            lbl_desc.setStyleSheet("padding: 4px; font-weight: bold;")
            group_lbl = group_names.get(action.group, action.group)
            lbl_desc.setText(f"[{group_lbl}] {lbl_desc.text()}")
            self.table_hotkeys.setCellWidget(idx, 0, lbl_desc)
            
            current_key = self.registry.get_effective_key(action.action_id)
            btn_capture = HotkeyCaptureButton(current_key)
            btn_capture.hotkey_captured.connect(lambda key_str, act_id=action.action_id, btn=btn_capture: self.on_hotkey_changed(act_id, key_str, btn))
            self.table_hotkeys.setCellWidget(idx, 1, btn_capture)
            


    def on_hotkey_changed(self, action_id, key_str, btn_widget):
        if not self.registry:
            return
            
        conflict_action = None
        for act in self.registry.get_all_actions():
            if act.action_id != action_id:
                effective_key = self.registry.get_effective_key(act.action_id)
                if effective_key == key_str and key_str != "":
                    conflict_action = act
                    break
                    
        if conflict_action:
            is_ru = (AppContext.LANG == "RU")
            conflict_name = conflict_action.label_ru if is_ru else conflict_action.label_en
            current_name = self.registry._actions[action_id].label_ru if is_ru else self.registry._actions[action_id].label_en
            
            reply = QMessageBox.question(
                self,
                "Конфликт горячих клавиш" if is_ru else "Hotkey Conflict",
                f"Сочетание '{key_str}' уже используется для действия:\n「{conflict_name}」.\n\nНазначить его для «{current_name}» и очистить старое действие?" if is_ru
                else f"Shortcut '{key_str}' is already assigned to:\n\"{conflict_name}\".\n\nAssign it to \"{current_name}\" and clear the conflicting action?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.registry.set_key(conflict_action.action_id, "")
                self.registry.set_key(action_id, key_str)
                self.populate_hotkeys_table()
            else:
                btn_widget.current_key = self.registry.get_effective_key(action_id)
                btn_widget.update_button_text()
        else:
            self.registry.set_key(action_id, key_str)
            btn_widget.current_key = key_str
            btn_widget.update_button_text()



    def reset_all_hotkeys(self):
        is_ru = (AppContext.LANG == "RU")
        reply = QMessageBox.question(
            self,
            "Сброс горячих клавиш" if is_ru else "Reset Hotkeys",
            "Вы уверены, что хотите сбросить все горячие клавиши к значениям по умолчанию?" if is_ru
            else "Are you sure you want to reset all hotkeys to their default values?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self.registry:
                self.registry.reset_to_defaults()
                self.populate_hotkeys_table()

    def add_line(self, layout, row):
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #555; border: none;")
        layout.addWidget(sep, row, 0, 1, 4)

    def add_path_new(self, grid_layout, row_idx, key_tr, config_val):
        is_ru = (AppContext.LANG == "RU")
        from PyQt6.QtGui import QIcon
        from PyQt6.QtCore import QSize
        
        # 1. Лейбл слева
        lbl = QLabel(AppContext.tr(key_tr))
        grid_layout.addWidget(lbl, row_idx, 0, Qt.AlignmentFlag.AlignVCenter)
        
        # 2. Слитный виджет: Поле ввода + Кнопка обзора (папка)
        joint_widget = QWidget()
        joint_layout = QHBoxLayout(joint_widget)
        joint_layout.setContentsMargins(0, 0, 0, 0)
        joint_layout.setSpacing(0)
        
        e = QLineEdit(self.config.get(config_val, ""))
        e.setFixedHeight(28)
        e.setStyleSheet("""
            QLineEdit {
                color: white;
                background-color: #444;
                border: 1px solid #555;
                border-right: none;
                padding: 4px 8px;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
                border-top-left-radius: 4px;
                border-bottom-left-radius: 4px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #3b82f6;
            }
        """)
        joint_layout.addWidget(e, 1)
        
        btn_browse = QPushButton()
        btn_browse.setFixedSize(28, 28)
        btn_browse.setIcon(QIcon(os.path.join(self.icons_dir, "folder-color.svg")))
        btn_browse.setIconSize(QSize(16, 16))
        btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browse.setToolTip(AppContext.tr("dlg_browse"))
        btn_browse.setStyleSheet("""
            QPushButton {
                background-color: #444;
                border: 1px solid #555;
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #555;
                border-color: #666;
            }
        """)
        btn_browse.clicked.connect(lambda: self.browse(e))
        joint_layout.addWidget(btn_browse)
        
        grid_layout.addWidget(joint_widget, row_idx, 1)
        
        # 3. Кнопка очистки (корзина)
        btn_clear = QPushButton()
        btn_clear.setFixedSize(28, 28)
        btn_clear.setIcon(QIcon(os.path.join(self.icons_dir, "trash-color.svg")))
        btn_clear.setIconSize(QSize(16, 16))
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear.setToolTip("Очистить путь" if is_ru else "Clear path")
        btn_clear.setStyleSheet("""
            QPushButton {
                background-color: #444;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #991b1b;
                border-color: #b91c1c;
            }
        """)
        btn_clear.clicked.connect(lambda: e.setText(""))
        
        grid_layout.addWidget(btn_clear, row_idx, 2, Qt.AlignmentFlag.AlignVCenter)
        
        return e

    def browse(self, e):
        start_dir = e.text() if e.text() and os.path.exists(e.text()) else os.path.expanduser("~")
        p = QFileDialog.getExistingDirectory(self, AppContext.tr("dlg_browse"), start_dir)
        if p: e.setText(p)

    def on_save(self):
        self.accept()

    def get_new_config_data(self):
        return {
            "max_nesting": self.config.get("max_nesting", 10),
            "scan_subfolders": self.config.get("scan_subfolders", False),
            "filter_mode": self.config.get("filter_mode", "include"),
            "filter_extensions": self.config.get("filter_extensions", ""),
            "affix_mode": self.config.get("affix_mode", "prefix"),
            "affix_text": self.config.get("affix_text", ""),
            "path_unsort": self.config.get("path_unsort", ""),
            "path_sort": self.e_sort.text(),
            "path_todel": self.e_todel.text()
        }
