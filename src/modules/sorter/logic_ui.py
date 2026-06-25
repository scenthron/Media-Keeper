
import re
import os
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, 
    QScrollArea, QSlider, QMessageBox, QToolTip, QFileDialog, QMenu, QComboBox,
    QCheckBox
)
from PyQt6.QtCore import Qt, QPointF, QTimer, QSize
from PyQt6.QtGui import QColor, QAction, QIcon

from config import APP_DESIGN, AppContext, DEBUG_MODE, VIEWER_DESIGN
from ui_widgets_base import FolderLabel, ElidedLabel, DroppableButton
from ui_dialogs_generic import InfoDialog, FolderStatsDialog
from .ui_dialog_settings import PathSettingsDialog
from .ui_affix import AffixToolWindow
from .logic_config import ConfigManager
from .ui_filter import SorterFilterDialog
from utils_common import generate_random_bg_color
from utils_io import ensure_long_path

class VolumeSlider(QSlider):
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setObjectName("VolumeSlider")
        logging.debug("INIT: VolumeSlider created with styles.")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            #VolumeSlider { 
                background: transparent; 
                border: none;
                min-height: 20px; 
                max-height: 20px;
            }
            #VolumeSlider::groove:horizontal { 
                background: #333; 
                height: 6px; 
                border-radius: 3px; 
                margin: 0px;
            }
            #VolumeSlider::handle:horizontal { 
                background: #888; 
                width: 14px; 
                height: 14px; 
                margin: -4px 0; 
                border-radius: 7px; 
            }
            #VolumeSlider::handle:horizontal:hover { background: #aaa; }
            #VolumeSlider::sub-page:horizontal { background: #444; border-radius: 3px; }
            #VolumeSlider::add-page:horizontal { background: #333; border-radius: 3px; }
            #VolumeSlider::handle:horizontal:disabled { background: #555; }
            #VolumeSlider::groove:horizontal:disabled { background: #222; }
            #VolumeSlider::groove:vertical { background: #333; width: 6px; }
            #VolumeSlider::handle:vertical { background: #888; height: 14px; margin: 0 -4px; }
        """)

    def showEvent(self, event):
        logging.debug("SHOW: VolumeSlider is being shown.")
        super().showEvent(event)

    def paintEvent(self, event):
        try:
            super().paintEvent(event)
        except Exception as e:
            logging.error(f"Error painting VolumeSlider: {e}")

class UiSetupMixin:
    def update_window_title(self):
        pass

    def log_debug(self, message):
        if DEBUG_MODE: print(f"[DEBUG] {message}")

    def apply_theme(self):
        c = APP_DESIGN
        v = VIEWER_DESIGN
        bg = c['bg_color_main']
        
        self.setStyleSheet(f"""
            QWidget {{ color: {c['text_color']}; font-size: {c['font_size_main']}px; }}
            QSlider {{ background: transparent; border: none; }}
            QMainWindow {{ background-color: {bg}; }}
            QDialog {{ background-color: {bg}; }}
            QLabel {{ color: {c['text_color']}; background: transparent; }}
            QFrame#ControlsBar {{ background-color: {bg}; border-top: 1px solid #444; }}
            QMessageBox {{ background-color: #2b2b2b; }}
            QMessageBox QLabel {{ color: white; }}
            QMessageBox QPushButton {{ background-color: #555; color: white; padding: 5px 15px; border: 1px solid #444; border-radius: 3px; }}
            QMessageBox QPushButton:hover {{ background-color: #666; }}
            QMessageBox QPushButton:hover {{ background-color: #666; }}
            QSplitter::handle {{ background-color: #444; }}
        """)
        if hasattr(self, 'sidebar'): self.sidebar.setStyleSheet(f"background-color: {c['bg_color_sidebar']};")
        if hasattr(self, 'cats_container'): self.cats_container.setStyleSheet("background: transparent;")
        if hasattr(self, 'cats_scroll'): self.cats_scroll.setStyleSheet("background: transparent; border: none;")
        if hasattr(self, 'toolbar'): self.toolbar.setStyleSheet(f"background-color: {bg}; border: none;")
        
        v_bg = self.session_viewer_color if self.session_viewer_color else c['bg_color_viewer']
        if hasattr(self, 'viewer'): self.viewer.set_background_color(v_bg)

    def create_toolbar(self):
        self.toolbar = QFrame()
        self.toolbar.setFixedHeight(40)
        self.toolbar.setStyleSheet("background: transparent; border: none;")
        
        tb_layout = QHBoxLayout(self.toolbar)
        tb_layout.setContentsMargins(10, 0, 6, 0)
        tb_layout.setSpacing(0)
        tb_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        tb_layout.addSpacing(50)
        
        # Filter Button (Funnel icon)
        self.btn_filter = QPushButton()
        self.btn_filter.setFixedSize(28, 26)
        self.btn_filter.clicked.connect(self.open_filter_dialog)
        self.btn_filter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_filter.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        tb_layout.addWidget(self.btn_filter, 0, Qt.AlignmentFlag.AlignVCenter)
        
        tb_layout.addSpacing(8)
                # Сортировка файлов на холсте
        sort_container = QHBoxLayout()
        sort_container.setSpacing(0)
        sort_container.setContentsMargins(0, 0, 0, 0)
        
        self.cb_sort = QComboBox()
        self.cb_sort.setFixedWidth(160)
        self.cb_sort.setFixedHeight(26)
        self.cb_sort.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.cb_sort.setStyleSheet("""
            QComboBox {
                background-color: #333333;
                color: #dddddd;
                padding: 2px 4px;
                border: 1px solid #555555;
                border-right: none;
                border-top-left-radius: 4px;
                border-bottom-left-radius: 4px;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
                font-size: 12px;
                combobox-popup: 0;
            }
            QComboBox::drop-down {
                border: none;
                width: 0px;
                height: 0px;
                background: transparent;
            }
            QComboBox QAbstractItemView {
                background-color: #2b2b2b;
                color: #dddddd;
                selection-background-color: #3b82f6;
                selection-color: white;
                border: 1px solid #555555;
                padding: 0px;
                margin: 0px;
                outline: 0px;
            }
        """)
        
        is_ru = (AppContext.LANG == "RU")
        sort_options = [
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
        for key, name in sort_options:
            self.cb_sort.addItem(name, key)
            
        current_sort = self.config.get("sort_type", "name_asc")
        for idx in range(self.cb_sort.count()):
            if self.cb_sort.itemData(idx) == current_sort:
                self.cb_sort.setCurrentIndex(idx)
                break
                
        self.cb_sort.activated.connect(self._on_sort_changed)
        sort_container.addWidget(self.cb_sort)
        
        # Кнопка группировки, плавно переходящая в комбобокс
        self.btn_group = QPushButton()
        self.btn_group.setFixedSize(28, 26)
        self.btn_group.setCheckable(True)
        self.btn_group.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_group.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_group.setToolTip("Сортировать по группам" if is_ru else "Sort by groups")
        self.btn_group.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                border: 1px solid #555555;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #404040;
            }
        """)
        
        initial_checked = self.config.get("group_by_sort", False)
        self.btn_group.setChecked(initial_checked)
        self.update_group_button_icon(initial_checked)
        self.btn_group.toggled.connect(self._on_group_by_sort_changed)
        sort_container.addWidget(self.btn_group)
        tb_layout.addLayout(sort_container)
        
        tb_layout.addSpacing(12)
        
        # Суб-лейаут имени файла и карандаша
        filename_layout = QHBoxLayout()
        filename_layout.setContentsMargins(0, 0, 0, 0)
        filename_layout.setSpacing(6) # 1 символ отступа
        
        self.lbl_filename = ElidedLabel("")
        self.lbl_filename.setStyleSheet(f"font-size: {APP_DESIGN['font_size_header']}px; font-weight: bold;")
        filename_layout.addWidget(self.lbl_filename, 1, Qt.AlignmentFlag.AlignVCenter)
        
        self.btn_rename_cur = QPushButton()
        self.btn_rename_cur.setIcon(QIcon(os.path.join(self.icons_dir, "pencil-color.svg")))
        self.btn_rename_cur.setIconSize(QSize(18, 18))
        self.btn_rename_cur.setFixedSize(30, 30)
        self.btn_rename_cur.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_rename_cur.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_rename_cur.clicked.connect(self.rename_current_file)
        self._update_rename_btn_style()
        filename_layout.addWidget(self.btn_rename_cur, 0, Qt.AlignmentFlag.AlignVCenter)
        
        tb_layout.addLayout(filename_layout, 1)

        tb_layout.addSpacing(8) # Отступ в 1 символ от карандаша до зеленого кружочка

        # Labels connect to browse dialogs
        self.lbl_unsort_dot = QLabel("●")
        self.lbl_unsort_dot.setStyleSheet("color: #22c55e; font-size: 14px; padding: 0px; margin: 0px;")
        self.lbl_unsort_dot.setToolTip(AppContext.tr("tooltip_recursive_active"))
        self.lbl_unsort_dot.hide()

        self.lbl_unsort_count = FolderLabel("lbl_unsort", lambda: getattr(self, 'UNSORT_DIR', ""))
        self.lbl_unsort_count.setStyleSheet("color: #3b82f6; font-weight: bold;")
        self.lbl_unsort_count.clicked.connect(self.browse_for_inbox)
        self.lbl_unsort_count.customContextMenuRequested.connect(self.show_inbox_context_menu)
        
        def get_trash_path():
            session_tp = getattr(self, 'session_trash_path', None)
            if session_tp: return session_tp
            return self.config.get("path_todel", "")

        self.lbl_todel_count = FolderLabel("lbl_todel", get_trash_path)
        path_todel = get_trash_path()
        if path_todel:
            self.lbl_todel_count.setStyleSheet("color: #ef4444; font-weight: bold;")
        else:
            self.lbl_todel_count.setStyleSheet("color: #aaa;")
        self.lbl_todel_count.clicked.connect(self.browse_for_trash_path)
        self.lbl_todel_count.customContextMenuRequested.connect(self.show_trash_context_menu)
        
        unsort_layout = QHBoxLayout()
        unsort_layout.setContentsMargins(0, 0, 0, 0)
        unsort_layout.setSpacing(4)
        unsort_layout.addWidget(self.lbl_unsort_dot, 0, Qt.AlignmentFlag.AlignVCenter)
        unsort_layout.addWidget(self.lbl_unsort_count, 0, Qt.AlignmentFlag.AlignVCenter)
        
        tb_layout.addLayout(unsort_layout)
        tb_layout.addSpacing(16) # Отступ в 2 символа между Входящими и Мусором
        tb_layout.addWidget(self.lbl_todel_count, 0, Qt.AlignmentFlag.AlignVCenter)
        tb_layout.addSpacing(8) # Отступ в 1 символ до кнопки Аффиксов
        
        self.btn_tag_toggle = QPushButton()
        self.btn_tag_toggle.setIcon(QIcon(os.path.join(self.icons_dir, "tag-color.svg")))
        self.btn_tag_toggle.setIconSize(QSize(18, 18))
        self.btn_tag_toggle.setFixedSize(30, 30) 
        self.btn_tag_toggle.setToolTip(AppContext.tr("btn_affix_panel"))
        self.btn_tag_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tag_toggle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_tag_toggle.setStyleSheet("""
            QPushButton { 
                background: transparent; 
                border: none;
                border-radius: 4px; 
            }
            QPushButton:hover { 
                background-color: #333333; 
            }
        """)
        self.btn_tag_toggle.clicked.connect(self.show_affix_panel)
        tb_layout.addWidget(self.btn_tag_toggle, 0, Qt.AlignmentFlag.AlignVCenter)

        self.left_layout.addWidget(self.toolbar)

    def create_bottom_controls(self):
        self.bottom_controls_container = QFrame()
        self.bottom_controls_container.setFixedHeight(80)
        self.bottom_controls_container.setObjectName("ControlsBar")
        controls_layout = QHBoxLayout(self.bottom_controls_container)
        
        self.btn_rot_l = QPushButton()
        self.btn_rot_r = QPushButton()
        self.btn_rot_l.setIcon(QIcon(os.path.join(self.icons_dir, "rotate_left.svg")))
        self.btn_rot_r.setIcon(QIcon(os.path.join(self.icons_dir, "rotate_right.svg")))
        self.btn_rot_l.setIconSize(QSize(24, 24))
        self.btn_rot_r.setIconSize(QSize(24, 24))
        rot_style = "background-color: #555; border-radius: 5px; padding: 0px;"
        for b in [self.btn_rot_l, self.btn_rot_r]:
            b.setFixedSize(50, 50)
            b.setStyleSheet(rot_style)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            
            # Retain size when hidden so other controls stay in place
            sp = b.sizePolicy()
            sp.setRetainSizeWhenHidden(True)
            b.setSizePolicy(sp)
        
        self.btn_rot_l.clicked.connect(lambda: self.rotate_view(-90))
        self.btn_rot_r.clicked.connect(lambda: self.rotate_view(90))
        
        controls_layout.addWidget(self.btn_rot_l)
        controls_layout.addWidget(self.btn_rot_r)
        controls_layout.addSpacing(20)

        self.btn_prev = QPushButton()
        self.btn_prev.setIcon(QIcon(os.path.join(self.icons_dir, "move-left.svg")))
        self.btn_prev.setIconSize(QSize(20, 20))
        self.btn_del = DroppableButton() 
        self.btn_undo = QPushButton()
        self.btn_next = QPushButton()
        self.btn_next.setIcon(QIcon(os.path.join(self.icons_dir, "move-right.svg")))
        self.btn_next.setIconSize(QSize(20, 20))
        self.btn_next.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        self.btn_prev.clicked.connect(self.prev_file)
        self.btn_del.clicked.connect(self.handle_trash_click)
        self.btn_del.folder_dropped.connect(self.handle_trash_drop)
        
        self.btn_undo.clicked.connect(self.undo_action)
        self.btn_next.clicked.connect(self.next_file)
        
        for btn in [self.btn_prev, self.btn_del, self.btn_undo, self.btn_next]:
            btn.setFixedHeight(50)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            controls_layout.addWidget(btn)
        
        self.btn_prev.setStyleSheet(f"QPushButton {{ background-color: {APP_DESIGN['btn_nav_bg']}; color: white; padding-left: 8px; padding-right: 8px; }}")
        self.btn_next.setStyleSheet(f"QPushButton {{ background-color: {APP_DESIGN['btn_nav_bg']}; color: white; padding-left: 8px; padding-right: 8px; }}")
        self.btn_undo.setStyleSheet(f"background-color: {APP_DESIGN['btn_undo_bg']}; color: black; font-weight: bold;")
        self.left_layout.addWidget(self.bottom_controls_container)

    def handle_trash_click(self):
        path_todel = getattr(self, 'session_trash_path', None)
        if not path_todel:
            path_todel = self.config.get("path_todel", "")

        if path_todel and os.path.exists(path_todel):
            self.delete_file()
        else:
            self.browse_for_trash_path()

    def browse_for_trash_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Trash Folder", "")
        if path:
            self.handle_trash_drop(path, True) 

    def handle_trash_drop(self, path, is_external):
        if not path or not os.path.isdir(path): return
        norm_path = os.path.normpath(path)
        current_inbox = getattr(self, 'session_inbox_path', None) or self.config.get("path_unsort")
        if current_inbox and os.path.normpath(current_inbox) == norm_path:
            if self.session_inbox_path: self.session_inbox_path = None
            if self.config.get("path_unsort") and os.path.normpath(self.config.get("path_unsort")) == norm_path:
                 self.config["path_unsort"] = ""
                 ConfigManager.save(self.config)
            self.files_queue = []
            self.current_file_path = None
            self.lbl_filename.setText("Входящие сброшены")
            self.viewer.show_empty_state("Входящие не выбраны")
            self.lbl_unsort_count.update_info()

        if is_external:
            self.config["path_todel"] = path
            ConfigManager.save(self.config)
            self.session_trash_path = None 
        else:
            if hasattr(self, 'set_session_trash'):
                self.set_session_trash(path)
        
        self.update_paths_from_config()
        self.validate_controls_state()
        # Reset previous trash folder style before updating
        self.lbl_todel_count.reset_style()
        self.lbl_todel_count.update_info()
        if hasattr(self, 'refresh_sidebar_styling'):
            self.refresh_sidebar_styling()

    def format_button_text_with_hotkey(self, base_text: str, hotkey_str: str) -> str:
        if not hotkey_str:
            return f"<b>{base_text}</b>"
        
        display_hotkey = hotkey_str.replace("Return", "Enter")
        # Главный текст будет отображаться размером 14px (задается через стили QLabel в кнопке),
        # а горячая клавиша в скобках — размером 10px (более мелкий шрифт).
        return f"<b>{base_text}</b><br><span style='font-size: 10px; font-weight: normal;'>({display_hotkey})</span>"



    def set_button_rich_text(self, btn, html_text):
        btn.setText("") # Очищаем стандартный текст кнопки, чтобы он не рисовался под QLabel
        
        # Проверяем, существует ли уже дочерний QLabel
        lbl = btn.findChild(QLabel, "btn_rich_label")
        if not lbl:
            layout = QVBoxLayout(btn)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            lbl = QLabel()
            lbl.setObjectName("btn_rich_label")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            lbl.setStyleSheet("background: transparent; border: none;")
            layout.addWidget(lbl)
            
        lbl.setText(html_text)

    def update_button_hotkey_labels(self):
        import re
        del_key = ""
        undo_key = ""
        if hasattr(self, '_hotkey_registry'):
            del_key = self._hotkey_registry.get_effective_key("delete_file")
            undo_key = self._hotkey_registry.get_effective_key("undo_action")
        else:
            del_key = "Delete"
            undo_key = "Ctrl+Z"
        
        # Очищаем скобки из переводов, например "(Del)" или "(Ctrl+Z)"
        base_del_text = AppContext.tr("btn_del")
        base_del_text = re.sub(r'\s*\([^)]*\)', '', base_del_text)
        
        base_undo_text = AppContext.tr("btn_undo")
        base_undo_text = re.sub(r'\s*\([^)]*\)', '', base_undo_text)
        
        path_todel = getattr(self, 'session_trash_path', None) or self.config.get("path_todel", "")
        
        del_key_display = del_key.replace("Return", "Enter") if del_key else ""
        undo_key_display = undo_key.replace("Return", "Enter") if undo_key else ""
        
        # Настройка кнопки удаления в корзину
        if not path_todel:
            txt = self.format_button_text_with_hotkey(f"{base_del_text} (+)", del_key)
            self.set_button_rich_text(self.btn_del, txt)
            self.btn_del.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.05); 
                    border: 2px dashed rgba(255, 255, 255, 0.4);
                    border-radius: 8px; 
                    padding: 2px;
                    margin: 4px;
                }
                QPushButton QLabel {
                    color: #aaa; 
                    font-size: 14px;
                    font-weight: bold;
                    text-align: center;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.1); 
                    border-color: #ef4444;
                }
                QPushButton:hover QLabel {
                    color: white;
                }
            """)
            
            # Тултип, когда корзина не настроена
            tip = AppContext.tr("tooltip_trash_setup")
            if del_key_display:
                tip += f" ({del_key_display})"
            self.btn_del.setToolTip(tip)
        else:
            txt = self.format_button_text_with_hotkey(base_del_text, del_key)
            self.set_button_rich_text(self.btn_del, txt)
            self.btn_del.setStyleSheet(f"""
                QPushButton {{
                    background-color: {APP_DESIGN['btn_delete_bg']};
                    border: none;
                    border-radius: 4px;
                }}
                QPushButton QLabel {{
                    color: white;
                    font-size: 14px;
                    font-weight: bold;
                    text-align: center;
                }}
                QToolTip {{ background-color: #1e1e1e; color: white; border: 1px solid #333; }}
            """)
            
            # HTML-тултип с путем и горячей клавишей
            desc_part = AppContext.tr("tooltip_del_action").split(".")[0]
            key_line = f"<br><span style='color: #aaa;'>{desc_part}. ({del_key_display})</span>" if del_key_display else ""
            tooltip_html = f"<span style='color: #ef4444; font-weight: bold;'>{path_todel}</span><br><span style='color: #888;'>{AppContext.tr('tip_drop_to_change')}</span>{key_line}"
            self.btn_del.setToolTip(tooltip_html)
            
        # Настройка кнопки отмены
        txt = self.format_button_text_with_hotkey(base_undo_text, undo_key)
        self.set_button_rich_text(self.btn_undo, txt)
        self.btn_undo.setStyleSheet(f"""
            QPushButton {{
                background-color: {APP_DESIGN['btn_undo_bg']};
                border: none;
                border-radius: 4px;
            }}
            QPushButton QLabel {{
                color: black;
                font-size: 14px;
                font-weight: bold;
                text-align: center;
            }}
        """)
        
        # Тултип для кнопки отката
        undo_base_tip = AppContext.tr("tooltip_undo_action")
        if undo_key_display:
            undo_base_tip += f" ({undo_key_display})"
        self.btn_undo.setToolTip(undo_base_tip)

    def update_ui_text(self):
        self.lbl_unsort_count.text_prefix_key = "lbl_unsort"
        self.lbl_unsort_count.update_info()
        self.lbl_todel_count.text_prefix_key = "lbl_todel"
        self.lbl_todel_count.update_info()
        # Adjust trash label style based on trash path
        path_todel = getattr(self, 'session_trash_path', None) or self.config.get("path_todel", "")
        if path_todel:
            self.lbl_todel_count.setStyleSheet("color: #ef4444; font-weight: bold;")
        else:
            # Reset any previous trash styling and apply neutral color
            self.lbl_todel_count.reset_style()
            self.lbl_todel_count.setStyleSheet("color: #aaa;")
        
        self.btn_new_cat.setText(AppContext.tr("btn_create_cat"))
        self.btn_new_cat.setStyleSheet(f"background-color: {APP_DESIGN['btn_create_bg']}; color: white; font-weight: bold; border-radius: 5px;")
        
        if hasattr(self, '_hotkey_registry'):
            prev_key = self._hotkey_registry.get_effective_key("prev_file")
            next_key = self._hotkey_registry.get_effective_key("next_file")
        else:
            prev_key = "Left"
            next_key = "Right"

        prev_text = AppContext.tr("btn_prev")
        self.btn_prev.setText(prev_text)
        prev_tip = prev_text + f" ({prev_key.replace('Return', 'Enter')})" if prev_key else prev_text
        self.btn_prev.setToolTip(prev_tip)

        next_text = AppContext.tr("btn_next")
        self.btn_next.setText(next_text)
        next_tip = next_text + f" ({next_key.replace('Return', 'Enter')})" if next_key else next_text
        self.btn_next.setToolTip(next_tip)
        
        if hasattr(self, 'btn_refresh'): 
            self.btn_refresh.setToolTip(AppContext.tr("tooltip_refresh"))
        if hasattr(self, 'btn_back'): 
            self.btn_back.setToolTip(AppContext.tr("btn_back_root"))
        if hasattr(self, 'btn_rot_l'):
            self.btn_rot_l.setToolTip(AppContext.tr("tooltip_rotate_ccw"))
        if hasattr(self, 'btn_rot_r'):
            self.btn_rot_r.setToolTip(AppContext.tr("tooltip_rotate_cw"))
        if hasattr(self, 'btn_tag_toggle'):
            self.btn_tag_toggle.setIcon(QIcon(os.path.join(self.icons_dir, "tag-color.svg")))
            self.btn_tag_toggle.setIconSize(QSize(18, 18))
        
        self._update_rename_btn_style()

        if hasattr(self, 'video_controls'):
            self.video_controls.update_ui_text()
            
        if hasattr(self, 'viewer') and self.viewer:
            self.viewer.update_fullscreen_tooltip(self.window().isFullScreen() if self.window() else False)
            
        self.validate_controls_state()
        
        is_recursive = self.config.get("scan_subfolders", False)
        if is_recursive:
            self.lbl_unsort_dot.show()
        else:
            self.lbl_unsort_dot.hide()
        self.lbl_unsort_dot.setToolTip(AppContext.tr("tooltip_recursive_active"))

    def validate_controls_state(self):
        path_todel = getattr(self, 'session_trash_path', None)
        if not path_todel:
            path_todel = self.config.get("path_todel", "")

        if not path_todel:
            self.btn_del.setToolTip(AppContext.tr("tooltip_trash_setup"))
        else:
            tooltip_html = f"<span style='color: #ef4444; font-weight: bold;'>{path_todel}</span><br><span style='color: #888;'>{AppContext.tr('tip_drop_to_change')}</span>"
            self.btn_del.setToolTip(tooltip_html)
            
        self.update_button_hotkey_labels()

    def show_affix_panel(self):
        if not self.affix_window:
            self.affix_window = AffixToolWindow(self.config, None)
            self.affix_window.apply_affix_requested.connect(self.on_affix_click)
            self.affix_window.settings_changed.connect(self.on_affix_settings_changed)
            self.affix_window.closed.connect(self.on_affix_window_closed)
        
        self.affix_window.show()
        self.affix_window.raise_()
        self.affix_window.activateWindow()
        self.center_affix_window()

    def on_affix_settings_changed(self, new_data):
        self.config.update(new_data)
        ConfigManager.save(self.config)

    def on_affix_window_closed(self):
        # Just handle closing logic if needed
        pass

    def center_affix_window(self):
        if not hasattr(self, 'affix_window') or not self.affix_window: return
        if not self.window(): return

        main_geo = self.window().geometry()
        center = main_geo.center()
        
        w = self.affix_window.width()
        h = self.affix_window.height()
        x = center.x() - w // 2
        y = center.y() - h // 2
        
        self.affix_window.move(x, y)

    def show_info_manual(self):
        pass

    def open_settings_dialog(self):
        # 1. Сохраняем состояние хоткеев до открытия диалога
        old_hotkey_overrides = {}
        if hasattr(self, '_hotkey_registry'):
            old_hotkey_overrides = self._hotkey_registry.save_overrides()

        dlg = PathSettingsDialog(self.config, self)
        if dlg.exec():
            new_data = dlg.get_new_config_data()
            self.config.update(new_data)
            
            # 2. Забираем переопределения хоткеев и сохраняем их в конфиг
            if hasattr(self, '_hotkey_registry'):
                self.config["hotkeys_sorter"] = self._hotkey_registry.save_overrides()

            ConfigManager.save(self.config)

            self.update_paths_from_config()
            self.manual_full_refresh(reset_position=True)
            self.update_watcher_paths()
            
            # 3. Обновляем тексты интерфейса
            if self.window() and hasattr(self.window(), 'update_ui_text'):
                 self.window().update_ui_text()
            else:
                 self.update_ui_text() 
                 
            # 4. Переприменяем новые горячие клавиши
            if hasattr(self, '_hotkey_registry'):
                self._hotkey_registry.apply_all(self)
                
            # 5. Обновляем тултипы
            if hasattr(self, 'viewer') and self.viewer:
                self.viewer.update_quick_target_tooltip()
                
            self.update_ui_text()
        else:
            # 6. Если отмена — откатываем хоткеи
            if hasattr(self, '_hotkey_registry'):
                self._hotkey_registry.load_overrides(old_hotkey_overrides)
                self._hotkey_registry.apply_all(self)

        self.setFocus()

    def change_volume(self, val):
        self.global_volume = val / 100.0
        AppContext.global_volume = self.global_volume
        self.audio_output.setVolume(self.global_volume)
        self.setFocus()

    def rotate_view(self, angle):
        if not getattr(self, 'current_file_path', None): return
        
        # Защита от вращения видео/аудио
        ext = os.path.splitext(self.current_file_path)[1].lower()
        if ext not in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp']:
            logging.warning(f"Rotation ignored for non-image file: {self.current_file_path}")
            return
            
        self.viewer.change_rotation(angle)
        
        # Save angle in session dictionary
        norm_path = os.path.normpath(self.current_file_path)
        current_angle = self.viewer.file_rotations.get(norm_path, 0)
        new_angle = (current_angle + angle) % 360
        self.viewer.file_rotations[norm_path] = new_angle
        
        # Update preview in grid/list views
        self.viewer.update_item_preview(norm_path)
        logging.info(f"ROTATE MAIN: File {norm_path} rotated by {angle} deg. New angle: {new_angle} deg.")
        self.setFocus()

    def randomize_viewer_bg(self):
        self.session_viewer_color = generate_random_bg_color()
        self.viewer.set_background_color(self.session_viewer_color)

    def open_filter_dialog(self):
        """Opens filter dialog to select file types for display."""
        logging.info("Opening filter dialog.")
        
        # Scan current UNSORT_DIR for available extensions
        found_exts = set()
        unsort_dir = getattr(self, 'UNSORT_DIR', None)
        if unsort_dir:
            long_unsort = ensure_long_path(unsort_dir)
            if os.path.exists(long_unsort):
                recursive = self.config.get("scan_subfolders", False)
                if recursive:
                    for root, _, files in os.walk(long_unsort):
                        for f in files:
                            ext = os.path.splitext(f)[1].lower()
                            if ext: found_exts.add(ext)
                else:
                    for f in os.listdir(long_unsort):
                        if os.path.isfile(os.path.join(long_unsort, f)):
                            ext = os.path.splitext(f)[1].lower()
                            if ext: found_exts.add(ext)
        
        # Get current selections from config
        raw_filter = self.config.get("filter_extensions", "")
        current_exts = set()
        for e in raw_filter.split(','):
            e = e.strip().lower()
            if e:
                if not e.startswith('.'): e = '.' + e
                current_exts.add(e)
        
        current_mode = self.config.get("filter_mode", "include")
        recursive_state = self.config.get("scan_subfolders", False)
        
        dlg = SorterFilterDialog(
            unsort_dir=unsort_dir,
            found_extensions=list(found_exts),
            current_selection=current_exts,
            current_mode=current_mode,
            recursive_state=recursive_state,
            parent=self
        )
        
        if dlg.exec():
            result = dlg.get_result()
            logging.info(f"Filter dialog accepted: {result}")
            
            # Save to config
            exts_str = ", ".join(sorted(result['exts']))
            self.config["filter_extensions"] = exts_str
            self.config["filter_mode"] = result['mode']
            self.config["scan_subfolders"] = result['recursive']
            
            new_unsort = result.get('unsort_dir', '')
            self.config["path_unsort"] = new_unsort
            self.session_inbox_path = None  # Reset temporary override
            
            ConfigManager.save(self.config)
            
            # Update paths and UI
            self.update_paths_from_config()
            self.update_filter_ui()
            self.refresh_sidebar_styling()
            
            # Refresh files list with new filter and new directory
            self.manual_full_refresh(reset_position=True)
        
        self.setFocus()

    def update_filter_ui(self):
        """Updates filter button color, icon and tooltip based on current filter state."""
        raw_filter = self.config.get("filter_extensions", "")
        filter_mode = self.config.get("filter_mode", "include")
        
        exts = [e.strip() for e in raw_filter.split(',') if e.strip()]
        
        # Постоянный темно-серый стиль кнопки
        self.btn_filter.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #404040;
                border-color: #666666;
            }
        """)
        
        self.update_filter_button_icon()
        
        is_ru = (AppContext.LANG == "RU")
        if not exts:
            self.btn_filter.setToolTip(AppContext.tr("filter_tooltip_off") if hasattr(AppContext, "tr") else ("Фильтр выключен" if is_ru else "Filter is off"))
        else:
            exts_display = ", ".join(exts[:5])
            if len(exts) > 5:
                exts_display += f" (+{len(exts)-5})"
            
            if filter_mode == "include":
                tooltip = (AppContext.tr("filter_tooltip_include") if hasattr(AppContext, "tr") else "Фильтр: показывать только {exts}").replace("{exts}", exts_display)
            else:
                tooltip = (AppContext.tr("filter_tooltip_exclude") if hasattr(AppContext, "tr") else "Фильтр: исключать {exts}").replace("{exts}", exts_display)
            self.btn_filter.setToolTip(tooltip)
            
        # Update recursive indicator
        recursive = self.config.get("scan_subfolders", False)
        if recursive:
            self.lbl_unsort_dot.show()
        else:
            self.lbl_unsort_dot.hide()

    def _update_rename_btn_style(self):
        if hasattr(self, '_hotkey_registry'):
            rename_key = self._hotkey_registry.get_effective_key("rename_file")
        else:
            rename_key = "F2"
        key_suffix = f" ({rename_key.replace('Return', 'Enter')})" if rename_key else ""
        
        self.btn_rename_cur.setStyleSheet("""
            QPushButton { 
                background: transparent; 
                border: none; 
                border-radius: 4px;
            }
            QPushButton:hover { 
                background-color: #333333; 
            }
        """)
        self.btn_rename_cur.setToolTip(AppContext.tr("tooltip_rename_file") + key_suffix)

    def _on_sort_changed(self):
        sort_type = self.cb_sort.currentData()
        self.config["sort_type"] = sort_type
        ConfigManager.save(self.config)
        
        # Применяем новую сортировку к очереди
        if hasattr(self, 'apply_sorting_to_queue'):
            self.apply_sorting_to_queue(sort_type, trigger_sync=True)
            
        # Обновляем представление
        self.manual_full_refresh(reset_position=False, silent=True)

    def _on_group_by_sort_changed(self, checked: bool) -> None:
        enabled = bool(checked)
        self.config["group_by_sort"] = enabled
        from .logic_config import ConfigManager
        ConfigManager.save(self.config)
        
        self.update_group_button_icon(enabled)
        
        if hasattr(self, 'viewer') and self.viewer:
            self.viewer.sync_files_queue(self.UNSORT_DIR, self.files_queue, self.current_index)

    def show_inbox_context_menu(self, pos) -> None:
        path = self.UNSORT_DIR
        if not path or not os.path.exists(path):
            return
        self._show_folder_context_menu(self.lbl_unsort_count, path, "inbox", pos)

    def show_trash_context_menu(self, pos) -> None:
        session_tp = getattr(self, 'session_trash_path', None)
        path = session_tp if session_tp else self.config.get("path_todel", "")
        if not path or not os.path.exists(path):
            return
        self._show_folder_context_menu(self.lbl_todel_count, path, "trash", pos)

    def _show_folder_context_menu(self, widget: FolderLabel, path: str, folder_type: str, pos) -> None:
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #2b2b2b; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #3b82f6; }")

        reset_action = QAction(AppContext.tr("menu_reset_path_context"), self)
        if folder_type == "inbox":
            reset_action.triggered.connect(self.reset_inbox_path)
        else:
            reset_action.triggered.connect(self.reset_trash_path)
        menu.addAction(reset_action)

        menu.addSeparator()

        analyze_action = QAction(AppContext.tr("menu_analyze"), self)
        analyze_action.triggered.connect(lambda: self.request_analysis(path))
        menu.addAction(analyze_action)

        duplicates_action = QAction(AppContext.tr("menu_duplicates"), self)
        duplicates_action.triggered.connect(lambda: self.request_duplicates(path))
        menu.addAction(duplicates_action)

        stats_action = QAction(AppContext.tr("menu_stats"), self)
        stats_action.triggered.connect(lambda: self.open_stats_for_path(path))
        menu.addAction(stats_action)

        menu.exec(widget.mapToGlobal(pos))

    def reset_inbox_path(self) -> None:
        self.session_inbox_path = None
        self.config["path_unsort"] = ""
        ConfigManager.save(self.config)
        self.update_paths_from_config()
        self.manual_full_refresh(reset_position=True)
        self.refresh_sidebar_styling()
        self.lbl_unsort_count.update_info()

    def reset_trash_path(self) -> None:
        self.session_trash_path = None
        self.config["path_todel"] = ""
        ConfigManager.save(self.config)
        self.update_paths_from_config()
        self.lbl_todel_count.update_info()
        self.validate_controls_state()
        self.refresh_sidebar_styling()

    def open_stats_for_path(self, path: str) -> None:
        dlg = FolderStatsDialog(path, self)
        dlg.exec()

    def request_duplicates(self, path: str) -> None:
        win = self.window()
        if hasattr(win, 'cleaner_tab'):
            win.cleaner_tab.add_folder_path(path)
            win.switch_tab(2)

    def get_colored_icon(self, icon_name: str, color: str) -> QIcon:
        icons_dir = getattr(self, "icons_dir", "")
        if not icons_dir:
            icons_dir = AppContext.find_resource_dir("icons")
        svg_path = os.path.normpath(os.path.join(icons_dir, icon_name))
        if os.path.exists(svg_path):
            try:
                from PyQt6.QtSvg import QSvgRenderer
                from PyQt6.QtGui import QPixmap, QPainter
                from PyQt6.QtCore import QSize
                with open(svg_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                content = content.replace('fill="#000000"', f'fill="{color}"')
                content = content.replace('fill="black"', f'fill="{color}"')
                content = content.replace('fill="currentColor"', f'fill="{color}"')
                content = content.replace('stroke="currentColor"', f'stroke="{color}"')
                content = content.replace('stroke="black"', f'stroke="{color}"')
                content = content.replace('stroke="#000000"', f'stroke="{color}"')
                
                renderer = QSvgRenderer(content.encode('utf-8'))
                if renderer.isValid():
                    pixmap = QPixmap(QSize(16, 16))
                    pixmap.fill(Qt.GlobalColor.transparent)
                    painter = QPainter(pixmap)
                    renderer.render(painter)
                    painter.end()
                    return QIcon(pixmap)
            except Exception as e:
                logging.error(f"Error rendering colored icon {icon_name}: {e}")
        return QIcon()

    def update_group_button_icon(self, checked: bool) -> None:
        color = "#ffffff" if checked else "#666666"
        icon = self.get_colored_icon("menu-sort.svg", color)
        if hasattr(self, 'btn_group') and self.btn_group:
            self.btn_group.setIcon(icon)

    def update_filter_button_icon(self) -> None:
        raw_filter = self.config.get("filter_extensions", "")
        exts = [e.strip() for e in raw_filter.split(',') if e.strip()]
        has_filter = len(exts) > 0
        
        recursive = self.config.get("scan_subfolders", False)
        icon_name = "funnel-plus.svg" if recursive else "funnel.svg"
        
        # Активный зеленый (#22c55e) если включен фильтр, белый (#ffffff) если включена рекурсия подпапок без фильтра, иначе приглушенный серый (#888888)
        if has_filter:
            color = "#22c55e"
        elif recursive:
            color = "#ffffff"
        else:
            color = "#888888"
        
        icon = self.get_colored_icon(icon_name, color)
        if hasattr(self, 'btn_filter') and self.btn_filter:
            self.btn_filter.setIcon(icon)
            self.btn_filter.setIconSize(QSize(18, 18))
