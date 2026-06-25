
import os
import re
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QCheckBox, QComboBox, QLineEdit, QMenu, QMessageBox, QFrame,
    QGridLayout, QScrollArea, QWidget
)
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QAction

from config import AppContext
from .logic_automation import AutomationConfig, TemplateEngine

class IconPickerPopup(QDialog):
    def __init__(self, current_icon, parent=None):
        super().__init__(parent)
        self.selected_icon = current_icon
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.setFixedSize(300, 360)
        
        self.frame = QFrame(self)
        self.frame.setObjectName("MainFrame")
        self.frame.setStyleSheet("""
            QFrame#MainFrame {
                background-color: #1f2937;
                border: 2px solid #3b82f6;
                border-radius: 8px;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QWidget#ScrollContent {
                background-color: transparent;
            }
            QScrollBar:vertical {
                width: 6px;
                background: transparent;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:vertical {
                background: #4b5563;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #3b82f6;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
                height: 0px;
            }
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {
                border: none;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QPushButton {
                background-color: #374151;
                color: white;
                border: 1px solid #4b5563;
                border-radius: 4px;
                font-size: 16px;
                padding: 3px;
            }
            QPushButton:hover {
                background-color: #4b5563;
                border-color: #3b82f6;
            }
            QPushButton#btn_reset {
                background-color: #7f1d1d;
                color: #fca5a5;
                border: 1px solid #991b1b;
                font-size: 12px;
                font-weight: bold;
                padding: 6px;
            }
            QPushButton#btn_reset:hover {
                background-color: #991b1b;
                color: white;
            }
        """)
        
        layout = QVBoxLayout(self.frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        scroll_content = QWidget()
        scroll_content.setObjectName("ScrollContent")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 5, 0)
        scroll_layout.setSpacing(10)
        
        self.categories = {
            "auto_cat_media": [
                "📷", "🎬", "🍿", "🎥", "📺", "🎭", "🎞️", "🛸", 
                "🎵", "🎙️", "🎧", "📻", "🎹", "📣"
            ],
            "auto_cat_art": [
                "🖼️", "🎨", "🖌️", "📐", "🌈", "🔮", "🎮", "🎲", 
                "👾", "🃏", "🎳"
            ],
            "auto_cat_family": [
                "👨‍👩‍👧‍👦", "👶", "🐾", "🐱", "🐶", "🦁", "🌍", "✈️", 
                "⛺", "🏖️", "🌲", "🚗", "🎁", "🎄", "🎈", "⚽", 
                "☀️", "❄️", "🍂"
            ],
            "auto_cat_work": [
                "📄", "💼", "📚", "📊", "📝", "🗂️", "📧", "💡", 
                "🔐", "⭐", "⚡", "🗑️", "🔞", "🆗", "🔄", "🆕", 
                "📌", "🚫"
            ],
            "auto_cat_food": [
                "🍳", "🍕", "🍰", "🍔", "🍣", "☕", "🍷", "🍎"
            ],
            "auto_cat_travel": [
                "🗺️", "🧭", "🚢", "🚇", "🗼", "🏔️", "🗽", "🏰"
            ],
            "auto_cat_study": [
                "🎓", "🔬", "🔭", "🧬", "🧪", "🧠", "🏫", "📜"
            ],
            "auto_cat_health": [
                "🏃", "🚴", "🧘", "🏋️", "🥗", "💊", "🏥", "🏆"
            ],
            "auto_cat_holidays": [
                "🎉", "🎂", "🎆", "🍾", "🤵", "👰", "🥳", "🎁"
            ],
            "auto_cat_hobby": [
                "🧵", "🧶", "🔨", "🔧", "✂️", "🪴", "🎣"
            ],
            "auto_cat_music": [
                "🎸", "🎻", "🎺", "🥁", "🎷", "🎤", "🎼"
            ],
            "auto_cat_finance": [
                "💰", "💳", "💵", "📈", "🛒", "🏦", "💎"
            ],
            "auto_cat_home": [
                "🏠", "🛋️", "🪟", "🔑", "🕯️", "🧹", "🛠️"
            ],
            "auto_cat_it": [
                "💻", "🖥️", "💾", "⚙️", "🔗", "🛡️", "🛸"
            ],
            "auto_cat_space": [
                "🪐", "☄️", "🌙", "☀️", "☁️", "⚡", "🌊"
            ],
            "auto_cat_entertainment": [
                "🎪", "🎟️", "🎫", "🤹", "🎰", "🎭", "🎈"
            ]
        }
        
        for cat_name, icon_list in self.categories.items():
            header_widget = QWidget()
            header_layout = QHBoxLayout(header_widget)
            header_layout.setContentsMargins(0, 5, 0, 2)
            header_layout.setSpacing(10)
            
            lbl_title = QLabel(AppContext.tr(cat_name))
            lbl_title.setStyleSheet("color: #3b82f6; font-weight: bold; font-size: 11px; text-transform: uppercase;")
            
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setStyleSheet("color: #374151; background-color: #374151; max-height: 1px;")
            
            header_layout.addWidget(lbl_title)
            header_layout.addWidget(line, 1)
            
            scroll_layout.addWidget(header_widget)
            
            grid_widget = QWidget()
            grid_layout = QGridLayout(grid_widget)
            grid_layout.setContentsMargins(0, 0, 0, 0)
            grid_layout.setSpacing(6)
            
            for idx, icon in enumerate(icon_list):
                btn = QPushButton(icon)
                btn.setFixedSize(36, 36)
                if icon == current_icon:
                    btn.setStyleSheet("background-color: #2563eb; border-color: #60a5fa;")
                btn.clicked.connect(lambda checked, symbol=icon: self.select_and_close(symbol))
                
                cols_count = 6
                row = idx // cols_count
                col = idx % cols_count
                grid_layout.addWidget(btn, row, col)
                
            scroll_layout.addWidget(grid_widget)
            
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
        
        btn_reset = QPushButton(AppContext.tr("auto_no_icon"))
        btn_reset.setObjectName("btn_reset")
        btn_reset.clicked.connect(lambda: self.select_and_close(""))
        layout.addWidget(btn_reset)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.frame)

    def select_and_close(self, symbol):
        self.selected_icon = symbol
        self.accept()

from PyQt6.QtCore import Qt

class AutomationDialog(QDialog):
    def __init__(self, folder_path, parent=None):
        super().__init__(parent)
        self.folder_path = folder_path
        self.folder_name = os.path.basename(folder_path)
        self.setWindowTitle(AppContext.tr("dlg_folder_settings_title"))
        self.resize(550, 280)
        self.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: white; }
            QLabel { color: #cccccc; font-size: 13px; font-weight: bold; }
            QLineEdit { color: white; background-color: #444; border: 1px solid #555; padding: 5px; border-radius: 4px;}
            QComboBox { background-color: #444; color: white; padding: 5px; border: 1px solid #555; border-radius: 4px; min-width: 150px; combobox-popup: 0; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { color: white; background-color: #444; selection-background-color: #3b82f6; padding: 0px; margin: 0px; outline: 0px; }
            QPushButton { color: white; background-color: #555; border: 1px solid #444; padding: 6px; border-radius: 3px;}
            QPushButton:hover { background-color: #666; }
            QCheckBox { color: white; font-weight: bold; spacing: 8px; }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #6b7280;
                border-radius: 3px;
                background-color: #1f2937;
            }
            QCheckBox::indicator:hover {
                border-color: #3b82f6;
            }
            QCheckBox::indicator:checked {
                background-color: #3b82f6;
                border-color: #3b82f6;
                image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxNiAxNiIgZmlsbD0id2hpdGUiPjxwYXRoIGQ9Ik0xMy44NiAzLjY2YS41LjUgMCAwIDEgLjA4LjdsLTcgOGEuNS41IDAgMCAxLS43MiAwbC0zLjUtNGEuNS41IDAgMSAxIC43Ni0uNjRMNi41IDExLjIybDYuNjYtNy42YS41LjUgMCAwIDEgLjctLjA2eiIvPjwvc3ZnPg==);
            }
            QFrame[frameShape="4"] { color: #444; }
            QPushButton:disabled { color: #777; border-color: #555; background-color: #333; }
        """)
        
        cfg = AutomationConfig.load_config(self.folder_path)
        # FIX: Check the actual boolean value inside the config, not just if config exists
        is_enabled = cfg.get("enabled", False) if cfg else False
        current_template = cfg["template"] if cfg else ""
        current_collision = cfg["collision"] if cfg else "Increment"
        
        self.saved_template = current_template
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        lbl_path = QLabel(f"{AppContext.tr('lbl_auto_folder')} {self.folder_path}")
        lbl_path.setStyleSheet("color: #888; font-weight: normal; font-size: 11px;")
        layout.addWidget(lbl_path)
        
        self.add_line(layout)
        
        row_config = QHBoxLayout()
        
        self.btn_help = QPushButton("!")
        self.btn_help.setFixedSize(24, 24)
        self.btn_help.setStyleSheet("QPushButton { background-color: #eab308; color: black; font-weight: 900; border-radius: 12px; }")
        self.btn_help.clicked.connect(self.show_help)
        row_config.addWidget(self.btn_help)
        
        self.cb_enable = QCheckBox(AppContext.tr("lbl_auto_renamer"))
        self.cb_enable.setChecked(is_enabled)
        self.cb_enable.toggled.connect(self.toggle_ui)
        row_config.addWidget(self.cb_enable)
        
        row_config.addStretch()
        
        self.lbl_col = QLabel(AppContext.tr("lbl_auto_collision"))
        row_config.addWidget(self.lbl_col)
        
        self.cb_collision = QComboBox()
        self.cb_collision.addItems([AppContext.tr("col_inc"), AppContext.tr("col_rnd")])
        self.cb_collision.setCurrentIndex(0 if current_collision == "Increment" else 1)
        row_config.addWidget(self.cb_collision)
        
        layout.addLayout(row_config)
        
        self.lbl_tmpl = QLabel(AppContext.tr("lbl_template"))
        layout.addWidget(self.lbl_tmpl)
        
        row_template = QHBoxLayout()
        self.e_template = QLineEdit(current_template)
        self.e_template.setPlaceholderText(AppContext.tr("hint_template"))
        self.e_template.textChanged.connect(self.on_template_changed)
        row_template.addWidget(self.e_template)
        
        self.btn_tags = QPushButton("[?]")
        self.btn_tags.setFixedWidth(40)
        self.btn_tags.clicked.connect(self.show_tags_menu)
        self.btn_tags.setToolTip(AppContext.tr("btn_insert_tag"))
        row_template.addWidget(self.btn_tags)
        
        layout.addLayout(row_template)

        row_batch = QHBoxLayout()
        row_batch.addStretch()
        self.btn_run_now = QPushButton(AppContext.tr("btn_batch_rename")) 
        self.btn_run_now.setStyleSheet("""
            QPushButton { background-color: #7c2d12; color: #fdba74; border: 1px solid #9a3412; padding: 6px 12px; font-weight: bold; } 
            QPushButton:hover { background-color: #9a3412; color: white; }
            QPushButton:disabled { background-color: #333; color: #666; border: 1px solid #444; }
        """)
        self.btn_run_now.clicked.connect(self.run_automation_now)
        row_batch.addWidget(self.btn_run_now)
        layout.addLayout(row_batch)
        
        # Строка выбора кастомной иконки папки
        self.current_icon = AutomationConfig.load_icon(self.folder_path)
        
        row_icon = QHBoxLayout()
        lbl_icon_title = QLabel(AppContext.tr("auto_folder_icon"))
        self.btn_pick_icon = QPushButton()
        self.btn_pick_icon.setMinimumWidth(120)
        self.update_icon_button_text()
        self.btn_pick_icon.clicked.connect(self.choose_icon)
        
        row_icon.addWidget(lbl_icon_title)
        row_icon.addWidget(self.btn_pick_icon)
        row_icon.addStretch()
        layout.addLayout(row_icon)
        
        layout.addSpacing(5)
        self.add_line(layout)
        layout.addSpacing(5)
        
        btn_box = QHBoxLayout()
        self.btn_save = QPushButton(AppContext.tr("btn_save"))
        self.btn_save.clicked.connect(self.save)
        self.btn_save.setStyleSheet("background-color: #2563eb; font-weight: bold; min-width: 80px;")
        self.btn_cancel = QPushButton(AppContext.tr("btn_cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_box.addStretch()
        btn_box.addWidget(self.btn_save)
        btn_box.addWidget(self.btn_cancel)
        layout.addLayout(btn_box)
        
        self.toggle_ui(self.cb_enable.isChecked())
        self.check_btn_state()

    def show_help(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(AppContext.tr("help_auto_renamer_title"))
        dlg.setFixedWidth(400)
        dlg.setStyleSheet("background-color: #2b2b2b; color: white;")
        
        layout = QVBoxLayout(dlg)
        
        label = QLabel(AppContext.tr("help_auto_renamer_text"))
        label.setWordWrap(True)
        label.setStyleSheet("font-size: 13px; color: #dddddd; padding: 10px;")
        layout.addWidget(label)
        
        btn = QPushButton("OK")
        btn.clicked.connect(dlg.accept)
        btn.setStyleSheet("background-color: #555; color: white; border: 1px solid #444; padding: 5px; border-radius: 3px;")
        
        h_layout = QHBoxLayout()
        h_layout.addStretch()
        h_layout.addWidget(btn)
        layout.addLayout(h_layout)
        
        dlg.exec()

    def add_line(self, layout):
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setFixedHeight(2)
        layout.addWidget(sep)

    def toggle_ui(self, checked):
        self.cb_collision.setEnabled(checked)
        self.e_template.setEnabled(checked)
        self.btn_tags.setEnabled(checked)
        self.check_btn_state()
        self.lbl_col.setStyleSheet("color: #cccccc;" if checked else "color: #555;")
        self.lbl_tmpl.setStyleSheet("color: #cccccc;" if checked else "color: #555;")

    def on_template_changed(self):
        self.check_btn_state()

    def check_btn_state(self):
        is_enabled = self.cb_enable.isChecked()
        current = self.e_template.text()
        matches_saved = (current == self.saved_template)
        
        if is_enabled and current and matches_saved:
            self.btn_run_now.setEnabled(True)
            self.btn_run_now.setToolTip("")
        else:
            self.btn_run_now.setEnabled(False)
            if not matches_saved:
                 self.btn_run_now.setToolTip(AppContext.tr("auto_tip_save_template"))
            elif not is_enabled:
                 self.btn_run_now.setToolTip(AppContext.tr("auto_tip_enable"))
            else:
                 self.btn_run_now.setToolTip(AppContext.tr("auto_tip_enter_template"))

    def show_tags_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #2b2b2b; color: white; } QMenu::item:selected { background-color: #3b82f6; }")
        
        tags = [
            ("%date", AppContext.tr("tag_date")),
            ("%time", AppContext.tr("tag_time")),
            ("%rand[4]", AppContext.tr("tag_rand4")),
            ("%randNum[3]", AppContext.tr("tag_randnum3")),
            ("%seq", AppContext.tr("tag_seq")),
            ("%parent", AppContext.tr("tag_parent")),
            ("%name", AppContext.tr("tag_name")),
            ("%dell[%date_%time]", AppContext.tr("tag_dell"))
        ]
        
        for tag, desc in tags:
            action = QAction(f"{tag} - {desc}", self)
            action.triggered.connect(lambda _, t=tag: self.insert_tag(t))
            menu.addAction(action)
        
        menu.exec(self.btn_tags.mapToGlobal(QPointF(0, self.btn_tags.height()).toPoint()))

    def insert_tag(self, tag):
        self.e_template.insert(tag)
        self.e_template.setFocus()

    def update_icon_button_text(self):
        if self.current_icon:
            self.btn_pick_icon.setText(f"{self.current_icon} {AppContext.tr('auto_btn_change_icon')}")
        else:
            self.btn_pick_icon.setText(AppContext.tr("auto_no_icon"))

    def choose_icon(self):
        popup = IconPickerPopup(self.current_icon, self)
        btn_pos = self.btn_pick_icon.mapToGlobal(QPointF(0, self.btn_pick_icon.height()).toPoint())
        popup.move(btn_pos)
        if popup.exec() == QDialog.DialogCode.Accepted:
            self.current_icon = popup.selected_icon
            self.update_icon_button_text()

    def save(self):
        template = self.e_template.text().strip()
        if self.cb_enable.isChecked() and not template:
            self.e_template.setPlaceholderText("TEMPLATE REQUIRED!")
            return
            
        policy = "Increment" if self.cb_collision.currentIndex() == 0 else "Random"
        AutomationConfig.save_config(self.folder_path, self.cb_enable.isChecked(), template, policy)
        AutomationConfig.save_icon(self.folder_path, self.current_icon)
        self.accept()

    def run_automation_now(self):
        template = self.e_template.text().strip()
        if not template: return

        try:
            # Только файлы непосредственно в этой папке (не рекурсивно)
            # Исключаем содержимое .mediakeeper и скрытые системные файлы
            meta_dir = os.path.join(self.folder_path, ".mediakeeper")
            all_entries = os.listdir(self.folder_path)
            all_files = [
                f for f in all_entries
                if os.path.isfile(os.path.join(self.folder_path, f))
                and not f.startswith('.')
                and os.path.join(self.folder_path, f) != meta_dir
            ]
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return

        if any(f.lower().endswith('.exe') for f in all_files):
            QMessageBox.critical(self, AppContext.tr("batch_warn_title"), AppContext.tr("batch_warn_exe"))
            return

        # Исключаем .cfg и файлы из .mediakeeper
        files = [
            f for f in all_files
            if not f.endswith('.cfg')
            and not f.endswith('.ini')
        ]
        count_total = len(files)

        if count_total == 0:
            QMessageBox.information(self, "Info", AppContext.tr("msg_batch_no_files"))
            return

        confirm_dlg = QDialog(self)
        confirm_dlg.setWindowTitle(AppContext.tr("batch_warn_title"))
        confirm_dlg.setStyleSheet("background-color: #2b2b2b; color: white;")
        confirm_dlg.setFixedSize(450, 200)
        c_layout = QVBoxLayout(confirm_dlg)

        warn_lbl = QLabel(AppContext.tr("batch_warn_text").format(count_total))
        warn_lbl.setStyleSheet("font-size: 13px; color: #fca5a5; font-weight: bold;")
        warn_lbl.setWordWrap(True)
        c_layout.addWidget(warn_lbl)

        c_btns = QHBoxLayout()
        b_yes = QPushButton(AppContext.tr("btn_yes_rename"))
        b_yes.setStyleSheet("background-color: #dc2626; color: white; font-weight: bold; padding: 6px;")
        b_yes.clicked.connect(confirm_dlg.accept)
        b_no = QPushButton(AppContext.tr("btn_cancel"))
        b_no.setStyleSheet("background-color: #555; color: white; padding: 6px;")
        b_no.clicked.connect(confirm_dlg.reject)
        c_btns.addWidget(b_yes)
        c_btns.addWidget(b_no)
        c_layout.addLayout(c_btns)

        if confirm_dlg.exec() != QDialog.DialogCode.Accepted:
            return

        collision_policy = "Increment" if self.cb_collision.currentIndex() == 0 else "Random"
        count = 0
        errors = 0

        files.sort(key=lambda x: [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', x)])

        # Находим главное окно (SorterModule) для управления watcher-ом
        app = None
        if self.parent() and hasattr(self.parent(), "app"):
            app = self.parent().app

        if app:
            app._ignore_watcher = True

        try:
            for i, f in enumerate(files):
                full_path = os.path.join(self.folder_path, f)
                if not os.path.isfile(full_path):
                    continue
                name, ext = os.path.splitext(f)

                new_path = TemplateEngine.get_unique_target(
                    self.folder_path, template, f, ext, collision_policy, iterator=(i + 1)
                )

                if os.path.normpath(new_path) == os.path.normpath(full_path):
                    continue

                try:
                    os.rename(full_path, new_path)
                    count += 1
                except Exception as rename_err:
                    import logging
                    logging.error(f"Batch rename error for '{f}': {rename_err}")
                    errors += 1

        except Exception as e:
            errors += 1
            import logging
            logging.error(f"Batch rename outer error: {e}", exc_info=True)
        finally:
            if app:
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(1000, lambda: setattr(app, '_ignore_watcher', False))
                if app.UNSORT_DIR and os.path.normpath(app.UNSORT_DIR) == os.path.normpath(self.folder_path):
                    app.refresh_files_list(show_progress=False)

        # Показываем результат на самом диалоге, который гарантированно жив
        QMessageBox.information(
            self,
            AppContext.tr("dlg_folder_settings_title"),
            AppContext.tr("msg_batch_result").format(count_total, count, errors)
        )
        self.accept()

