
import os
import logging
import random
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, 
    QSizePolicy, QMenu, QMessageBox, QDialog, QApplication
)
from PyQt6.QtCore import Qt, QMimeData, QUrl, QFile, QEvent, QTimer, QSize
from PyQt6.QtGui import QDrag, QDesktopServices, QAction, QIcon

from config import AppContext, APP_DESIGN
from ui_dialogs_generic import SmartNameDialog, FolderStatsDialog
from .ui_dialog_automation import AutomationDialog
from utils_common import truncate_text
from .logic_automation import AutomationConfig
from .ui_sidebar_base import SIDEBAR_DESIGN, DragContainer, SidebarNodeMixin
from .ui_sidebar_leaf import LeafNodeWidget
from ui_widgets_base import ElidedButton
from logic_cache import DirCache

class CategoryWidget(QFrame, SidebarNodeMixin):
    def __init__(self, name, path, parent_app, level=0, parent_cat=None):
        super().__init__()
        self.name = name
        self.path = path
        self.app = parent_app
        self.level = level 
        self.parent_cat = parent_cat
        self.is_collapsed = False
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAcceptDrops(True)
        self._drag_start_pos = None
        
        self.is_inbox = False
        self.is_trash = False
        
        if self.path in self.app.category_colors_cache:
            self.current_color = self.app.category_colors_cache[self.path]
        else:
            self.current_color = self.generate_random_color()
            self.app.category_colors_cache[self.path] = self.current_color
            
        self.init_ui()
        
        # Connect to Cache Update
        DirCache.inst().updated.connect(self._on_cache_updated)
        
        self.update_visual_state()

    def generate_random_color(self):
        r = random.randint(40, 120)
        g = random.randint(40, 120)
        b = random.randint(40, 120)
        return f"#{r:02x}{g:02x}{b:02x}"

    def init_ui(self):
        self.update_style()
        self.main_layout_v = QVBoxLayout(self)
        pad = 2 if self.level > 0 else 5
        self.main_layout_v.setContentsMargins(pad, pad, pad, pad)
        self.main_layout_v.setSpacing(0)

        h = QWidget()
        h.setStyleSheet("background: transparent;") 
        h.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        h.customContextMenuRequested.connect(lambda pos: self.open_context_menu(pos))
        h.installEventFilter(self)

        hl = QHBoxLayout(h)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)

        cat_btn_style = """
            QPushButton { 
                background-color: rgba(0,0,0,0.1); 
                border: 1px solid rgba(0,0,0,0.8); 
                color: white; 
                border-radius: 4px;
                padding: 0px;
                text-align: center;
            }
            QPushButton:hover {
                background-color: rgba(255,255,255,0.2); 
                border: 1px solid white;
            }
        """
        self.btn_collapse = QPushButton("▼")
        sz = 24 if self.level == 0 else 20
        self.btn_collapse.setFixedSize(sz, sz)
        self.btn_collapse.clicked.connect(self.toggle_collapse)
        btn_fs = "13px" if self.level == 0 else "11px"
        self.btn_collapse.setStyleSheet(cat_btn_style + f"font-size: {btn_fs};")
        self.btn_collapse.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        fs = SIDEBAR_DESIGN['font_size_main'] if self.level == 0 else SIDEBAR_DESIGN['font_size_sub']
        
        self.btn_name = ElidedButton(self.name)
        self.btn_name.setStyleSheet(f"QPushButton {{ font-size: {fs}px; text-align: left; padding-left: 4px; font-weight: bold; border: none; background: transparent; color: white; }}")
        self.btn_name.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_name.clicked.connect(self.handle_click) 
        self.btn_name.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_name.installEventFilter(self)
        
        self.lbl_count = QLabel("(0)")
        self.lbl_count.setStyleSheet("color: #ddd; font-size: 12px; margin-right: 5px; background: transparent; padding-right: 6px;")

        icons_dir = AppContext.find_resource_dir("icons")
        
        self.btn_color = QPushButton()
        self.btn_color.setFixedSize(sz, sz)
        self.btn_color.setIcon(QIcon(os.path.join(icons_dir, "rotate_right.svg")))
        self.btn_color.setIconSize(QSize(sz - 6, sz - 6))
        self.btn_color.clicked.connect(self.randomize_color)
        self.btn_color.setStyleSheet(cat_btn_style + "padding: 0px;") 
        self.btn_color.setToolTip(AppContext.tr("tooltip_change_color"))
        self.btn_color.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.btn_settings = QPushButton()
        self.btn_settings.setFixedSize(sz, sz)
        self.btn_settings.setIcon(QIcon(os.path.join(icons_dir, "settings.svg")))
        self.btn_settings.setIconSize(QSize(sz - 6, sz - 6))
        self.btn_settings.clicked.connect(self.open_automation_settings)
        self.btn_settings.setToolTip(AppContext.tr("tooltip_folder_settings"))
        self.btn_settings.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.update_automation_status()

        btn_add_sec = QPushButton()
        btn_add_sec.setFixedSize(sz, sz)
        btn_add_sec.setIcon(QIcon(os.path.join(icons_dir, "plus.svg")))
        btn_add_sec.setIconSize(QSize(sz - 6, sz - 6))
        max_nesting = self.app.config.get("max_nesting", 10)
        if self.level >= max_nesting:
            btn_add_sec.setEnabled(False)
            btn_add_sec.setStyleSheet("QPushButton { background-color: rgba(0,0,0,0.3); border: 1px solid rgba(0,0,0,0.5); border-radius: 4px; padding: 0px; }")
            btn_add_sec.setToolTip(AppContext.tr("tooltip_nesting_limit"))
        else:
            btn_add_sec.clicked.connect(self.create_section)
            btn_add_sec.setStyleSheet(cat_btn_style + "padding: 0px;")
            btn_add_sec.setToolTip(AppContext.tr("tooltip_add_sub"))
        btn_add_sec.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        hl.addWidget(self.btn_collapse)
        hl.addWidget(self.btn_name, 1)
        hl.addWidget(self.lbl_count)
        hl.addWidget(self.btn_color)
        hl.addWidget(self.btn_settings) 
        hl.addWidget(btn_add_sec)

        self.main_layout_v.addWidget(h)

        self.sections_container = DragContainer(self.path, self.app, self)
        self.sections_container.setStyleSheet("background: transparent;")
        self.sections_container.internal_reorder.connect(self.app.on_internal_reorder)
        
        indent = 10 if self.level == 0 else 8
        self.sections_container.layout.setContentsMargins(indent, 2, 0, 0)
        
        self.refresh_sections()
        self.main_layout_v.addWidget(self.sections_container)

    def _on_cache_updated(self, updated_path):
        if os.path.normpath(self.path) == os.path.normpath(updated_path):
            self.update_count_visual()

    def handle_click(self):
        is_inbox, _ = self.check_if_blocked()
        if is_inbox: return

        # Multi-module support: Sorter vs Analyzer
        if hasattr(self.app, 'move_current_file'):
            # Sorter mode: Move active single file
            self.app.move_current_file(self.path)
        elif hasattr(self.app, 'move_selected_files'):
            # Analyzer mode: Move all checked files
            self.app.move_selected_files(self.path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            is_inbox, _ = self.check_if_blocked()
            if is_inbox:
                event.ignore()
                return
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            self.app.add_temporary_roots(event.mimeData().urls())
            event.accept()
        else:
            super().dropEvent(event)

    def update_visual_state(self):
        self.is_inbox, self.is_trash = self.check_if_blocked()
        self.update_style()
        self.update_count_visual() # Refresh count logic
        
        icon_prefix = ""
        is_clean_root = (self.level == 0 and not self.app.temp_roots)
        
        custom_icon = AutomationConfig.load_icon(self.path)
        
        if self.is_trash: icon_prefix = "🗑️ "
        elif self.is_inbox: icon_prefix = "📥 "
        elif custom_icon: icon_prefix = f"{custom_icon} "
        elif "⚡" in self.name: icon_prefix = "" 
        elif "📍" in self.name: icon_prefix = "📁 "
        elif self.level == 0 and not is_clean_root: icon_prefix = "📁 "
            
        is_quick_target = hasattr(self.app, 'quick_target_path') and self.app.quick_target_path and os.path.normpath(self.app.quick_target_path) == os.path.normpath(self.path)
        star_prefix = "★ " if is_quick_target else ""

        display_name = self.name.replace("📍", "").strip()
        self.btn_name.setText(star_prefix + icon_prefix + display_name)
        
        if self.check_if_last_target():
            self.lbl_count.setStyleSheet("color: #4ade80; font-size: 12px; margin-right: 5px; background: transparent; padding-right: 6px; font-weight: bold;")
        else:
            self.lbl_count.setStyleSheet("color: #ddd; font-size: 12px; margin-right: 5px; background: transparent; padding-right: 6px;")
        
        self.apply_rich_tooltip(self.is_inbox, self.is_trash)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.MiddleButton:
                if self.path and os.path.exists(self.path):
                    QDesktopServices.openUrl(QUrl.fromLocalFile(self.path))
                return True
            elif event.button() == Qt.MouseButton.LeftButton:
                self._drag_start_pos = event.position().toPoint()
        elif event.type() == QEvent.Type.MouseMove:
            if (event.buttons() & Qt.MouseButton.LeftButton) and self._drag_start_pos:
                distance = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
                if distance >= QApplication.startDragDistance():
                    self.start_drag(event)
                    return True # Stop further processing of this move
        return super().eventFilter(watched, event)

    def start_drag(self, event):
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(self.path)
        drag.setMimeData(mime)
        pixmap = self.grab()
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.position().toPoint())
        # Important: reset start pos so we don't start multiple drags
        self._drag_start_pos = None
        drag.exec(Qt.DropAction.MoveAction)

    def update_count_visual(self):
        if not os.path.exists(self.path): return
        # Non-blocking Cache call
        count, _ = DirCache.inst().get_data(self.path)
        self.lbl_count.setText(f"({count})")

    def update_automation_status(self):
        cfg = AutomationConfig.load_config(self.path)
        base_style = """
            QPushButton { 
                background-color: rgba(0,0,0,0.1); 
                border: 1px solid rgba(0,0,0,0.8); 
                border-radius: 4px;
                padding: 0px;
            }
            QPushButton:hover { background-color: rgba(255,255,255,0.2); border: 1px solid white; }
        """
        has_automation = cfg and (cfg.get("enabled", False) or cfg.get("template", "").strip())
        if has_automation:
            is_enabled = cfg.get("enabled", False)
            template = cfg.get("template", "").strip()
            if is_enabled:
                if template:
                    self.btn_settings.setStyleSheet("QPushButton { background-color: #16a34a; border: 1px solid rgba(0,0,0,0.8); border-radius: 4px; padding: 0px; } QPushButton:hover { background-color: #15803d; border: 1px solid white; }")
                    self.btn_settings.setToolTip("Автоматизация: Включена")
                else:
                    self.btn_settings.setStyleSheet("QPushButton { background-color: #dc2626; border: 1px solid rgba(0,0,0,0.8); border-radius: 4px; padding: 0px; } QPushButton:hover { background-color: #b91c1c; border: 1px solid white; }")
                    self.btn_settings.setToolTip("Ошибка: Шаблон пуст!")
            else:
                self.btn_settings.setStyleSheet("QPushButton { background-color: #d97706; border: 1px solid rgba(0,0,0,0.8); border-radius: 4px; padding: 0px; } QPushButton:hover { background-color: #b45309; border: 1px solid white; }")
                self.btn_settings.setToolTip("Автоматизация: На паузе")
        else:
            self.btn_settings.setStyleSheet(base_style)
            self.btn_settings.setToolTip(AppContext.tr("tooltip_folder_settings"))

    def open_automation_settings(self):
        dlg = AutomationDialog(self.path, self)
        if dlg.exec():
            self.update_automation_status()
            self.update_visual_state()

    def rename_category(self):
        parent_dir = os.path.dirname(self.path)
        dlg = SmartNameDialog("dlg_rename_title", "dlg_enter_name", parent_dir, self.name, self)
        if dlg.exec():
            new_name = dlg.final_name
            new_path = os.path.join(parent_dir, new_name)
            try:
                os.rename(self.path, new_path)
                if self.path in self.app.category_colors_cache:
                    self.app.category_colors_cache[new_path] = self.app.category_colors_cache.pop(self.path)
                if parent_dir in self.app.custom_orders:
                    norm_parent = os.path.normpath(parent_dir)
                    if norm_parent in self.app.custom_orders:
                        order = self.app.custom_orders[norm_parent]
                        if self.name in order:
                            idx = order.index(self.name)
                            order[idx] = new_name
                self.app.reload_categories_ui()
            except Exception as e:
                QMessageBox.critical(self, AppContext.tr("err_title"), str(e))
    
    def delete_category(self):
        total_files = 0
        total_subfolders = 0
        try:
            for root, dirs, files in os.walk(self.path):
                total_files += len(files)
                total_subfolders += len(dirs)
        except: pass

        confirm_dlg = QDialog(self)
        confirm_dlg.setWindowTitle(AppContext.tr("msg_del_confirm_title"))
        confirm_dlg.setStyleSheet("QDialog { background-color: #2b2b2b; color: white; }")
        confirm_dlg.setFixedSize(450, 260)
        
        main_layout = QVBoxLayout(confirm_dlg)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(15)

        icon_lbl = QLabel("🗑️")
        icon_lbl.setStyleSheet("font-size: 42px; background: transparent; border: none; color: #ef4444;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        
        title_lbl = QLabel(f"{AppContext.tr('menu_delete')}: {truncate_text(self.name, 25)}")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: white; background: transparent;")
        
        path_lbl = QLabel(self.path)
        path_lbl.setStyleSheet("font-size: 11px; color: #888; font-family: 'Segoe UI', sans-serif; background: transparent;")
        path_lbl.setWordWrap(True)
        
        text_layout.addWidget(title_lbl)
        text_layout.addWidget(path_lbl)
        
        header_layout.addWidget(icon_lbl)
        header_layout.addLayout(text_layout)
        main_layout.addLayout(header_layout)

        stats_frame = QFrame()
        stats_frame.setStyleSheet("background-color: #333; border-radius: 8px; border: 1px solid #444;")
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setContentsMargins(15, 10, 15, 10)
        
        def make_stat(val, label):
            c = QWidget()
            cl = QVBoxLayout(c)
            cl.setContentsMargins(0,0,0,0)
            cl.setSpacing(0)
            v = QLabel(str(val))
            v.setStyleSheet("font-size: 16px; font-weight: bold; color: white; background: transparent;")
            v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l = QLabel(label)
            l.setStyleSheet("font-size: 10px; color: #aaa; text-transform: uppercase; background: transparent;")
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cl.addWidget(v)
            cl.addWidget(l)
            return c
            
        stats_layout.addWidget(make_stat(total_files, AppContext.tr("stat_files")))
        
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("background-color: #555;")
        stats_layout.addWidget(sep)
        
        stats_layout.addWidget(make_stat(total_subfolders, AppContext.tr("stat_folders")))
        
        main_layout.addWidget(stats_frame)

        warn_lbl = QLabel(AppContext.tr('msg_cannot_undo'))
        warn_lbl.setStyleSheet("color: #fca5a5; font-size: 12px; font-style: italic; background: transparent;")
        warn_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(warn_lbl)

        btns_layout = QHBoxLayout()
        btns_layout.setSpacing(10)
        
        b_del = QPushButton(AppContext.tr("menu_delete"))
        b_del.setCursor(Qt.CursorShape.PointingHandCursor)
        b_del.setStyleSheet("""
            QPushButton { 
                background-color: #dc2626; color: white; font-weight: bold; 
                padding: 8px 20px; border-radius: 4px; border: none; font-size: 13px;
            } 
            QPushButton:hover { background-color: #ef4444; }
        """)
        b_del.clicked.connect(confirm_dlg.accept)
        
        b_cancel = QPushButton(AppContext.tr("btn_cancel"))
        b_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        b_cancel.setStyleSheet("""
            QPushButton { 
                background-color: #555; color: white; 
                padding: 8px 15px; border-radius: 4px; border: 1px solid #666; font-size: 13px;
            } 
            QPushButton:hover { background-color: #666; border-color: #777; }
        """)
        b_cancel.clicked.connect(confirm_dlg.reject)
        
        btns_layout.addStretch()
        btns_layout.addWidget(b_del)
        btns_layout.addWidget(b_cancel)
        main_layout.addLayout(btns_layout)
        
        if confirm_dlg.exec() == QDialog.DialogCode.Accepted:
            success = QFile.moveToTrash(self.path)
            # QFile.moveToTrash returns (bool, str) on Windows in PyQt6, or bool on other platforms
            trash_ok = success[0] if isinstance(success, tuple) else bool(success)
            if trash_ok:
                if self.parent_cat:
                    self.parent_cat.refresh_sections()
                else:
                    self.app.reload_categories_ui()
            else:
                QMessageBox.warning(self, AppContext.tr("err_title"), AppContext.tr("msg_del_fail"))

    def update_style(self):
        bg = self.current_color
        if self.is_trash:
            bg = "#ef4444" 
        elif self.is_inbox:
            bg = "#3b82f6" 
        
        # Restore visual nesting: darken children but keep them visible
        if self.level > 0:
            self.setStyleSheet(f"CategoryWidget {{ background-color: {bg}; border-radius: 6px; margin: 0px; color: {APP_DESIGN['text_color']}; }} QWidget#HeaderPart {{ background-color: rgba(0,0,0,0.2); border-top-left-radius: 6px; border-bottom-left-radius: 6px; }}")
        else:
            self.setStyleSheet(f"CategoryWidget {{ background-color: {bg}; border-radius: 6px; margin: 0px; color: {APP_DESIGN['text_color']}; }}")

    def randomize_color(self):
        self.current_color = self.generate_random_color()
        self.app.category_colors_cache[self.path] = self.current_color
        self.update_style()

    def refresh_sections(self):
        layout = self.sections_container.layout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        
        if not os.path.exists(self.path): return
        max_level = self.app.config.get("max_nesting", 10)
        try: items = os.listdir(self.path)
        except: items = []
        
        key_path = os.path.normpath(self.path)
        
        if key_path in self.app.custom_orders:
            order = self.app.custom_orders[key_path]
            ordered_items = [i for i in order if i in items]
            new_items = sorted([i for i in items if i not in order])
            final_items = ordered_items + new_items
            self.app.custom_orders[key_path] = final_items
            items = final_items
        else:
            items = sorted(items)

        folders = [d for d in items if os.path.isdir(os.path.join(self.path, d)) and d != ".mediakeeper"]
        
        has_any_folders = bool(folders)
        for f in folders:
            fp = os.path.join(self.path, f)
            has_sub = False
            if self.level + 1 < max_level:
                try:
                    sub = os.listdir(fp)
                    has_sub = any(
                        os.path.isdir(os.path.join(fp, i)) for i in sub
                        if i != ".mediakeeper"
                    )
                except:
                    pass
            
            if has_sub:
                layout.addWidget(CategoryWidget(f, fp, self.app, self.level + 1, parent_cat=self))
            else:
                layout.addWidget(LeafNodeWidget(f, fp, self.app, self, self.level + 1))
        
        self.btn_collapse.setVisible(has_any_folders)

    def toggle_collapse(self):
        self.is_collapsed = not self.is_collapsed
        self.sections_container.setVisible(not self.is_collapsed)
        self.btn_collapse.setText("▶" if self.is_collapsed else "▼")

    def create_section(self):
        dlg = SmartNameDialog("dlg_new_sub_title", "dlg_enter_name", self.path, "", self)
        if dlg.exec() and dlg.final_name:
            os.makedirs(os.path.join(self.path, dlg.final_name), exist_ok=True)
            self.refresh_sections()

    def open_stats(self):
        dlg = FolderStatsDialog(self.path, self)
        dlg.exec()

    def request_analysis(self):
        win = self.window()
        if hasattr(win, 'request_analysis'):
            win.request_analysis(self.path)

    def set_as_temp_inbox(self):
        if hasattr(self.app, 'set_session_inbox'):
            curr_inbox = self.app.session_inbox_path
            if curr_inbox and os.path.normpath(curr_inbox) == os.path.normpath(self.path):
                self.app.set_session_inbox(None)
            else:
                self.app.set_session_inbox(self.path)
        self.update_visual_state()

    def set_as_perm_inbox(self):
        if hasattr(self.app, 'set_permanent_inbox'):
            curr_inbox = self.app.config.get("path_unsort", "")
            if curr_inbox and os.path.normpath(curr_inbox) == os.path.normpath(self.path):
                self.app.set_permanent_inbox(None)
            else:
                self.app.set_permanent_inbox(self.path)
        self.update_visual_state()

    def set_as_trash(self):
        if hasattr(self.app, 'set_session_trash'):
            curr_trash = self.app.session_trash_path
            config_trash = self.app.config.get("path_todel", "")
            is_already_trash = (
                (curr_trash and os.path.normpath(curr_trash) == os.path.normpath(self.path)) or
                (config_trash and os.path.normpath(config_trash) == os.path.normpath(self.path))
            )
            if is_already_trash:
                self.app.set_session_trash(None)
                logging.info("[Sidebar] Корзина сброшена.")
            else:
                self.app.set_session_trash(self.path)
                logging.info(f"[Sidebar] Корзина назначена: {self.path}")
        self.update_visual_state()

    def open_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #2b2b2b; color: white; } QMenu::item:selected { background-color: #3b82f6; }")
        
        open_action = QAction(AppContext.tr("menu_open_explorer"), self)
        open_action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.path)))
        menu.addAction(open_action)

        menu.addSeparator()

        focus_action = QAction(AppContext.tr("menu_focus"), self)
        focus_action.setToolTip(AppContext.tr("tooltip_focus"))
        focus_action.triggered.connect(lambda: self.app.enter_focus_mode(self.path))
        menu.addAction(focus_action)
        
        # Получаем состояния Входящих и Корзины
        inbox_conf = self.app.config.get("path_unsort", "")
        sess_inbox = getattr(self.app, 'session_inbox_path', None)
        my_norm = os.path.normpath(self.path)
        is_temp_inbox = sess_inbox and os.path.normpath(sess_inbox) == my_norm
        is_perm_inbox = inbox_conf and os.path.normpath(inbox_conf) == my_norm
        
        is_inbox, is_trash = self.check_if_blocked()
                   
        # Временный источник
        temp_inbox_text = AppContext.tr("menu_unset_temp_inbox") if is_temp_inbox else AppContext.tr("menu_set_temp_inbox")
        temp_inbox_action = QAction(temp_inbox_text, self)
        temp_inbox_action.triggered.connect(self.set_as_temp_inbox)
        menu.addAction(temp_inbox_action)
        
        # Постоянный источник
        perm_inbox_text = AppContext.tr("menu_unset_perm_inbox") if is_perm_inbox else AppContext.tr("menu_set_perm_inbox")
        perm_inbox_action = QAction(perm_inbox_text, self)
        perm_inbox_action.triggered.connect(self.set_as_perm_inbox)
        menu.addAction(perm_inbox_action)
        
        trash_text = AppContext.tr("menu_unset_trash") if is_trash else AppContext.tr("menu_set_trash")
        trash_action = QAction(trash_text, self)
        trash_action.triggered.connect(self.set_as_trash)
        menu.addAction(trash_action)

        is_quick_target = hasattr(self.app, 'quick_target_path') and self.app.quick_target_path and os.path.normpath(self.app.quick_target_path) == os.path.normpath(self.path)
        quick_target_text = AppContext.tr("menu_unset_quick_target") if is_quick_target else AppContext.tr("menu_set_quick_target")
        quick_target_action = QAction(quick_target_text, self)
        if is_inbox or is_trash:
            quick_target_action.setEnabled(False)
        quick_target_action.triggered.connect(lambda: self.app.set_quick_target_path(None if is_quick_target else self.path))
        menu.addAction(quick_target_action)

        menu.addSeparator()

        analyze_action = QAction(AppContext.tr("menu_analyze"), self)
        analyze_action.triggered.connect(self.request_analysis)
        menu.addAction(analyze_action)

        duplicates_action = QAction(AppContext.tr("menu_duplicates"), self)
        duplicates_action.triggered.connect(self.request_duplicates)
        menu.addAction(duplicates_action)

        stats_action = QAction(AppContext.tr("menu_stats"), self)
        stats_action.triggered.connect(self.open_stats)
        menu.addAction(stats_action)

        rename_action = QAction(AppContext.tr("menu_rename"), self)
        rename_action.triggered.connect(self.rename_category)
        menu.addAction(rename_action)

        menu.addSeparator()

        del_action = QAction(AppContext.tr("menu_delete"), self)
        del_action.triggered.connect(self.delete_category)
        menu.addAction(del_action)

        menu.exec(self.mapToGlobal(pos))

    def request_duplicates(self):
        win = self.window()
        if hasattr(win, 'cleaner_tab'):
            win.cleaner_tab.add_folder_path(self.path)
            win.switch_tab(2)
