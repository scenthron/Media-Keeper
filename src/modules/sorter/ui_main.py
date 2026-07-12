
import sys
import os
import ctypes
import subprocess
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QFrame, QSplitter, QScrollArea, QStyle, QLabel, QFileDialog, QMessageBox, QComboBox
)
from PyQt6.QtCore import Qt, QUrl, QTimer, QFileSystemWatcher, QRectF, QPointF, QEvent, QTimeLine, QSize
from PyQt6.QtGui import QPixmap, QDesktopServices, QKeySequence, QShortcut, QIcon
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from config import APP_DESIGN, AppContext
from .ui_viewer import SorterViewerArea
from .ui_player import VideoPlayerControls, TimeOverlayWidget
from .ui_sidebar_base import DragContainer, DropZoneWidget, SIDEBAR_DESIGN
from .ui_sidebar_leaf import LeafNodeWidget
from .ui_sidebar_category import CategoryWidget
from .ui_affix import AffixToolWindow

from .logic_config import ConfigManager
from utils_common import format_size
from utils_io import ensure_long_path, strip_long_path_prefix
from .logic_ui import UiSetupMixin
from .logic_files import FileOpsMixin
from .logic_player import PlayerMixin
from .logic_hotkeys import SorterHotkeysMixin
from .logic_automation import AutomationConfig

class SorterModule(QWidget, UiSetupMixin, FileOpsMixin, PlayerMixin, SorterHotkeysMixin):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = ConfigManager.load()
        self.icons_dir = AppContext.find_resource_dir("icons")
        
        self.category_colors_cache = {}
        self.custom_orders = {} 
        self.session_bg_color = None
        self.session_viewer_color = None
        
        self.is_focus_mode = False
        self.original_sort_dir = None
        self.current_file_path = None
        
        self.temp_roots = []
        self.ui_root_order = [] 
        
        self.session_inbox_path = None
        self.session_trash_path = None
        
        self.session_video_speed = AppContext.session_video_speed
        self.session_all_videos_active = AppContext.session_all_videos_active 
        self.session_loop = AppContext.session_loop 
        self.current_media_is_video = False
        
        self.session_counters = {} 
        
        import time
        import logging
        t0 = time.perf_counter()
        logging.info("[PROFILER] SorterModule.__init__ started")
        
        self.update_paths_from_config()
        t1 = time.perf_counter()
        logging.info(f"[PROFILER] update_paths_from_config took {t1 - t0:.4f}s")
        
        self.files_queue = []
        self.current_index = 0
        self.history = [] 
        self.global_volume = AppContext.global_volume
        self._pending_refresh_file = None

        self.fs_watcher = QFileSystemWatcher(self)
        self.fs_watcher.directoryChanged.connect(self.on_fs_directory_changed)
        
        self.fs_debounce_timer = QTimer()
        self.fs_debounce_timer.setSingleShot(True)
        self.fs_debounce_timer.setInterval(1000) 
        self.fs_debounce_timer.timeout.connect(self.on_fs_debounce_timeout)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0,0,0,0)
        self.main_layout.setSpacing(0)
        
        self.affix_window = None # Will be created on demand
        
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_layout.addWidget(self.splitter)
        
        left_column = QWidget()
        self.left_layout = QVBoxLayout(left_column)
        self.left_layout.setContentsMargins(0,0,0,0)
        self.left_layout.setSpacing(0)
        
        self.create_toolbar()
        self.update_filter_ui()
        
        self.viewer = SorterViewerArea(self)
        self.viewer.single_view.double_click_callback = self.open_current_file_system
        self.viewer.single_view.middle_click_callback = self.reveal_current_file_in_explorer
        self.viewer.canvas_clicked.connect(self._on_click_canvas)
        self.viewer.fullscreen_toggled.connect(self.toggle_app_fullscreen)
        self.viewer.folder_dropped.connect(self.on_viewer_drop) 
        self.viewer.browse_requested.connect(self.browse_for_inbox)
        self.viewer.btn_fullscreen.setToolTip(AppContext.tr("tooltip_fullscreen"))
        
        self.viewer.mode_changed.connect(self.on_view_mode_changed)
        self.viewer.selection_changed.connect(self.on_selection_changed)
        self.viewer.grid_view.item_double_clicked.connect(self.on_item_double_clicked)
        self.viewer.list_view.item_double_clicked.connect(self.on_item_double_clicked)
        self.viewer.send_to_editor_requested.connect(self.on_send_to_editor_requested)
        
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.viewer.video_item)
        self.audio_output.setVolume(self.global_volume)
        self.media_player.mediaStatusChanged.connect(self._fit_video)
        
        self.viewer.video_item.nativeSizeChanged.connect(self._fit_video_size_changed)
        
        self.left_layout.addWidget(self.viewer, stretch=1)

        self.video_controls = VideoPlayerControls()
        self.video_controls.set_app_reference(self)
        self.video_controls.play_pause_clicked.connect(self.toggle_playback)
        
        self.video_controls.seek_requested.connect(self.media_player.setPosition)
        self.video_controls.seek_moved.connect(self.media_player.setPosition)
        self.video_controls.seek_drag_start.connect(self._on_scrub_start)
        self.video_controls.seek_drag_stop.connect(self._on_scrub_stop)
        
        self.video_controls.speed_changed.connect(self._on_speed_changed)
        self.video_controls.loop_toggled.connect(self._set_loop_state)
        self.video_controls.apply_all_toggled.connect(self._on_apply_all_toggled)
        self.video_controls.volume_changed.connect(self.change_volume)
        
        # Sync initial volume
        self.video_controls.vol_slider.setValue(int(self.global_volume * 100))

        self.media_player.positionChanged.connect(self.video_controls.update_position)
        self.media_player.durationChanged.connect(self.video_controls.update_duration)
        self.media_player.playbackStateChanged.connect(self._on_playback_state_changed)
        
        # Setup time overlay for main viewer
        self.time_overlay = TimeOverlayWidget(self.viewer.single_view)
        self.viewer.single_view.time_overlay = self.time_overlay
        self.time_overlay.hide()
        
        self.media_player.positionChanged.connect(self._update_overlay_time)
        self.media_player.durationChanged.connect(self._update_overlay_duration)
        
        self.video_controls.hide()
        self.left_layout.addWidget(self.video_controls)
        
        t2 = time.perf_counter()
        logging.info(f"[PROFILER] Viewer and video controls created in {t2 - t1:.4f}s")
        
        self.bottom_controls_container = None 
        self.create_bottom_controls()
        
        t3 = time.perf_counter()
        logging.info(f"[PROFILER] Bottom controls created in {t3 - t2:.4f}s")
        
        self.splitter.addWidget(left_column)

        self.sidebar = QWidget()
        self.sidebar.setMinimumWidth(350) 
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(10, 10, 10, 10)
        self.sidebar_layout.setSpacing(SIDEBAR_DESIGN["section_spacing"])
        
        header_sidebar = QWidget()
        hs_layout = QHBoxLayout(header_sidebar)
        hs_layout.setContentsMargins(0,0,0,0)
        hs_layout.setSpacing(5)
        
        self.btn_back = QPushButton("←")
        self.btn_back.setFixedSize(40, 40)
        self.btn_back.setStyleSheet(f"background-color: {APP_DESIGN['btn_back_bg']}; color: white; font-weight: bold; font-size: 20px; border-radius: 5px;")
        self.btn_back.setToolTip(AppContext.tr("btn_back_root"))
        self.btn_back.clicked.connect(self.exit_focus_mode)
        self.btn_back.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_back.hide()
        hs_layout.addWidget(self.btn_back)

        self.btn_new_cat = QPushButton() 
        self.btn_new_cat.setFixedHeight(40)
        self.btn_new_cat.clicked.connect(self.handle_create_or_reset)
        self.btn_new_cat.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        hs_layout.addWidget(self.btn_new_cat, stretch=1)
        
        # Nesting level selector
        self.combo_nesting = QComboBox()
        self.combo_nesting.setFixedSize(40, 40)
        self.combo_nesting.setToolTip(AppContext.tr("tooltip_nesting_level"))
        self.combo_nesting.setEditable(True)
        self.combo_nesting.lineEdit().setReadOnly(True)
        self.combo_nesting.lineEdit().setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.combo_nesting.lineEdit().installEventFilter(self)
        
        self.combo_nesting.setStyleSheet("""
            QComboBox { 
                background-color: #333; 
                color: white; 
                border: 1px solid #555; 
                border-radius: 5px; 
                font-weight: bold;
                font-size: 14px;
                font-family: 'Consolas', 'Courier New', monospace;
                combobox-popup: 0;
            }
            QComboBox:hover { border-color: #666; }
            QComboBox::drop-down { border: none; width: 0px; }
            QComboBox QAbstractItemView { 
                background-color: #333; 
                color: white; 
                selection-background-color: #3b82f6; 
                padding: 0px;
                margin: 0px;
                outline: 0px;
            }
            QLineEdit {
                background: transparent;
                border: none;
                color: white;
                font-weight: bold;
            }
        """)
        for i in range(1, 11):
            self.combo_nesting.addItem(str(i), i)
        current_level = self.config.get("max_nesting_depth", 5)
        self.combo_nesting.setCurrentIndex(current_level - 1)
        self.combo_nesting.setCurrentIndex(current_level - 1)
        self.combo_nesting.currentIndexChanged.connect(self.on_nesting_changed)
        self.combo_nesting.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        hs_layout.addWidget(self.combo_nesting)
        
        
        self.btn_refresh = QPushButton()
        self.btn_refresh.setFixedSize(40, 40)
        self.btn_refresh.setIcon(QIcon(os.path.join(self.icons_dir, "reset_view.svg")))
        self.btn_refresh.setIconSize(QSize(20, 20))
        self.btn_refresh.setStyleSheet("QPushButton { background-color: #15803d; border-radius: 5px; padding: 0px; } QPushButton:hover { background-color: #166534; }")
        self.btn_refresh.setToolTip(AppContext.tr("tooltip_refresh"))
        self.btn_refresh.clicked.connect(lambda: self.manual_full_refresh(reset_position=False, silent=False))
        self.btn_refresh.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        hs_layout.addWidget(self.btn_refresh)
        
        self.sidebar_layout.addWidget(header_sidebar)

        self.cats_scroll = QScrollArea()
        self.cats_scroll.setWidgetResizable(True)
        self.cats_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cats_scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
        self.cats_container = DragContainer(self.SORT_DIR, self)
        self.cats_container.setObjectName("CatsContainer")
        self.cats_container.external_folders_dropped.connect(self.add_temporary_roots)
        self.cats_container.internal_reorder.connect(self.on_internal_reorder)
        
        self.cats_layout = self.cats_container.v_layout
        self.cats_scroll.setWidget(self.cats_container)
        
        self.sidebar_layout.addWidget(self.cats_scroll)
        
        self.splitter.addWidget(self.sidebar)
        
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setCollapsible(1, False)
        
        self.splitter.setSizes([1200, 350])
        
        self.ui_root_order = []
        raw_temp = self.config.get("temp_roots", "")
        self.temp_roots = [p for p in raw_temp.split("|") if p and os.path.exists(p)]
        
        self.apply_theme()
        self.update_ui_text() 
        self.update_watcher_paths()
        has_virtual = False
        try:
            from logic_paths import get_app_data_dir
            import json
            session_path = os.path.join(get_app_data_dir(), "virtual_session.json")
            if os.path.exists(session_path):
                with open(session_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if data.get('source_name') and data.get('files'):
                    self.load_virtual_files(data['files'], data['source_name'])
                    has_virtual = True
        except Exception as e:
            import logging
            logging.error(f"Failed to load virtual session: {e}")
            
        if not has_virtual:
            self.refresh_files_list()
            
        self.reload_categories_ui()
        self.init_hotkeys()
        
        # Инициализация Быстрой цели (Fast Move)
        self.quick_target_path = None
        self.quick_target_timeline = QTimeLine(1500, self)
        self.quick_target_timeline.setFrameRange(0, 100)
        self.quick_target_timeline.setLoopCount(0)  # бесконечно
        self.quick_target_timeline.valueChanged.connect(self._on_quick_target_pulse)
        
        self.viewer.set_mode(1) # По умолчанию открываем в режиме плиток (Grid)
        
        QTimer.singleShot(300, self.show_current_file)
        self.setFocus()

    def request_analysis(self, path):
        win = self.window()
        if hasattr(win, 'request_analysis'):
            win.request_analysis(path)
            if hasattr(win, 'analyzer_tab'):
                win.analyzer_tab.start_analysis(path, from_sorter=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'sidebar'):
            half_width = event.size().width() // 2
            self.sidebar.setMaximumWidth(half_width)


    def on_internal_reorder(self, target_parent_path, source_path, new_index):
        source_norm = os.path.normpath(source_path)
        main_context = os.path.normpath(self.SORT_DIR) if self.SORT_DIR else ""
        
        if not target_parent_path:
            target_norm = main_context
        else:
            target_norm = os.path.normpath(target_parent_path)
        
        need_reload = False

        if target_norm == main_context and self.temp_roots:
            current_roots_norm = [os.path.normpath(p) for p in self.ui_root_order]
            if source_norm in current_roots_norm:
                try:
                    old_index = current_roots_norm.index(source_norm)
                    item_to_move = self.ui_root_order.pop(old_index)
                    if new_index > len(self.ui_root_order): new_index = len(self.ui_root_order)
                    if new_index < 0: new_index = 0
                    self.ui_root_order.insert(new_index, item_to_move)
                    need_reload = True
                except ValueError: pass
        else:
             parent_of_source = os.path.normpath(os.path.dirname(source_path))
             if parent_of_source == target_norm:
                 filename = os.path.basename(source_path)
                 
                 if target_norm in self.custom_orders: 
                     items = self.custom_orders[target_norm]
                 else:
                     try: items = sorted(os.listdir(target_norm))
                     except: items = []
                
                 if filename in items: 
                     items.remove(filename)
                     if new_index < 0: new_index = 0
                     if new_index > len(items): new_index = len(items)
                     items.insert(new_index, filename)
                     
                     self.custom_orders[target_norm] = items
                     need_reload = True

        if need_reload:
            QTimer.singleShot(0, self.reload_categories_ui)
    
    def set_session_inbox(self, path):
        self.session_inbox_path = path

        # Reset filter on new inbox
        self.config["filter_extensions"] = ""
        ConfigManager.save(self.config)
        self.update_filter_ui()

        self.update_paths_from_config()
        self.manual_full_refresh(reset_position=True)
        self.refresh_sidebar_styling()

    def set_permanent_inbox(self, path):
        self.session_inbox_path = None  # Reset temporary override
        
        # Reset filter on new inbox
        self.config["filter_extensions"] = ""
        self.config["path_unsort"] = path if path else ""
        ConfigManager.save(self.config)
        self.update_filter_ui()

        self.update_paths_from_config()
        self.manual_full_refresh(reset_position=True)
        self.refresh_sidebar_styling()

    def set_session_trash(self, path):
        self.session_trash_path = path
        self.config["path_todel"] = path if path else ""
        ConfigManager.save(self.config)
        self.lbl_todel_count.update_info()
        self.validate_controls_state()
        self.refresh_sidebar_styling()

    def refresh_sidebar_styling(self):
        def recursive_update(layout):
            if not layout: return
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if not item: continue
                w = item.widget()
                if w and hasattr(w, 'update_visual_state'):
                    w.update_visual_state()
                    if isinstance(w, CategoryWidget) and w.sections_container:
                         if w.sections_container.v_layout:
                             recursive_update(w.sections_container.v_layout)
                        
        if self.cats_container and self.cats_container.v_layout:
            recursive_update(self.cats_container.v_layout)

    def browse_for_inbox(self):
        start_dir = self.UNSORT_DIR if self.UNSORT_DIR and os.path.exists(self.UNSORT_DIR) else os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(self, AppContext.tr("dlg_select_inbox"), start_dir)
        if path:
             self.set_session_inbox(path)

    def on_viewer_drop(self, path, is_external):
        if not os.path.isdir(path): return
        
        norm_path = os.path.normpath(path)
        
        current_trash = getattr(self, 'session_trash_path', None) or self.config.get("path_todel")
        if current_trash and os.path.normpath(current_trash) == norm_path:
            self.set_session_trash(None)

        if is_external:
            old_unsort = self.config.get("path_unsort", "")
            if os.path.normpath(old_unsort) != path:
                self.config["filter_min_size"] = 0.0
                self.config["filter_max_size"] = 0.0
                
            self.config["path_unsort"] = path
            
            # Reset filter on new inbox (external drop)
            self.config["filter_extensions"] = ""
            
            ConfigManager.save(self.config)
            self.session_inbox_path = None 
            self.update_filter_ui()
        else:
            self.session_inbox_path = path

        self.update_paths_from_config()
        self.manual_full_refresh(reset_position=True)
        self.refresh_sidebar_styling()

    def update_paths_from_config(self):
        if self.session_inbox_path and os.path.exists(self.session_inbox_path):
            self.UNSORT_DIR = self.session_inbox_path
        else:
            self.UNSORT_DIR = self.config.get("path_unsort", "")
            
        if not self.is_focus_mode:
            self.SORT_DIR = self.config.get("path_sort", "")
        
        self.TO_DEL_DIR = self.config.get("path_todel", "")
        if hasattr(self, 'cats_container'):
            self.cats_container.parent_path = self.SORT_DIR

    def add_temporary_roots(self, urls):
        has_default = bool(self.config.get("path_sort", ""))
        
        paths = []
        for url in urls:
            p = url.toLocalFile()
            if os.path.isdir(p): paths.append(p)
            
        if not paths: return

        if not has_default:
            new_default = paths.pop(0)
            self.config["path_sort"] = new_default
            ConfigManager.save(self.config)
            self.SORT_DIR = new_default
            self.cats_container.parent_path = self.SORT_DIR
            has_default = True
            
        if paths:
            for i in range(self.cats_layout.count()):
                item = self.cats_layout.itemAt(i)
                if item and item.widget():
                    w = item.widget()
                    if isinstance(w, CategoryWidget) and not w.is_collapsed:
                        w.toggle_collapse()

        if paths:
            for p in paths:
                if p not in self.temp_roots:
                    self.temp_roots.append(p)
            self.config["temp_roots"] = "|".join(self.temp_roots)
            ConfigManager.save(self.config)
        
        self.reload_categories_ui()
        self.validate_controls_state()

    def clear_default_sort(self):
        self.config["path_sort"] = ""
        self.config["temp_roots"] = ""
        ConfigManager.save(self.config)
        self.SORT_DIR = ""
        self.temp_roots = []
        self.reload_categories_ui()
        self.validate_controls_state()

    def browse_and_add_temp_root(self):
        start_dir = self.SORT_DIR if self.SORT_DIR and os.path.exists(self.SORT_DIR) else os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(self, AppContext.tr("dlg_select_folder"), start_dir)
        if path:
            if not self.config.get("path_sort", ""):
                 self.config["path_sort"] = path
                 ConfigManager.save(self.config)
                 self.SORT_DIR = path
                 self.reload_categories_ui()
                 return

            for i in range(self.cats_layout.count()):
                item = self.cats_layout.itemAt(i)
                if item and item.widget():
                    w = item.widget()
                    if isinstance(w, CategoryWidget) and not w.is_collapsed:
                        w.toggle_collapse()

            if path not in self.temp_roots:
                self.temp_roots.append(path)
                self.reload_categories_ui()

    def handle_create_or_reset(self):
        if self.temp_roots:
            self.temp_roots = []
            self.config["temp_roots"] = ""
            ConfigManager.save(self.config)
            self.reload_categories_ui()
        else:
            self.create_category()

    def _collect_collapsed_states(self) -> dict[str, bool]:
        states = {}
        layout = self.cats_container.v_layout
        
        def traverse(w):
            if isinstance(w, CategoryWidget):
                states[w.path] = w.is_collapsed
                if hasattr(w, 'sections_container') and w.sections_container:
                    sec_layout = w.sections_container.layout
                    if sec_layout:
                        for i in range(sec_layout.count()):
                            child_w = sec_layout.itemAt(i).widget()
                            if child_w:
                                traverse(child_w)
                                
        for i in range(layout.count()):
            widget = layout.itemAt(i).widget()
            if widget:
                traverse(widget)
        return states

    def reload_categories_ui(self):
        import time
        import logging
        t3 = time.perf_counter()
        # Очищаем кэш автоматизации перед перерисовкой дерева
        AutomationConfig.clear_cache()
        # Сохраняем состояние свернутости для всех уровней
        self.collapsed_states_cache = self._collect_collapsed_states()
        
        # Update btn_new_cat style based on state (Sync with Analyzer)
        has_any_root = bool(self.SORT_DIR and os.path.exists(self.SORT_DIR)) or bool(self.temp_roots)
        
        if not has_any_root:
             self.btn_new_cat.setText(AppContext.tr("btn_create_cat"))
             self.btn_new_cat.setStyleSheet("background-color: #333; color: #555; font-weight: bold; border-radius: 5px; border: 1px solid #444;")
             self.btn_new_cat.setEnabled(False)
             self.btn_refresh.setStyleSheet("QPushButton { background-color: #333; border-radius: 5px; border: 1px solid #444; padding: 0px; }")
             self.btn_refresh.setEnabled(False)
        elif self.temp_roots:
             self.btn_new_cat.setText(AppContext.tr("btn_reset_view"))
             self.btn_new_cat.setStyleSheet("background-color: #555; color: #ddd; font-weight: bold; border-radius: 5px; border: 1px solid #777;")
             self.btn_new_cat.setToolTip(AppContext.tr("tooltip_reset_view"))
             self.btn_new_cat.setEnabled(True)
             self.btn_refresh.setStyleSheet("QPushButton { background-color: #15803d; border-radius: 5px; padding: 0px; } QPushButton:hover { background-color: #166534; }")
             self.btn_refresh.setEnabled(True)
        else:
             self.btn_new_cat.setText(AppContext.tr("btn_create_cat"))
             self.btn_new_cat.setStyleSheet(f"background-color: {APP_DESIGN['btn_create_bg']}; color: white; font-weight: bold; border-radius: 5px;")
             self.btn_new_cat.setToolTip("")
             self.btn_new_cat.setEnabled(True)
             self.btn_refresh.setStyleSheet("QPushButton { background-color: #15803d; border-radius: 5px; padding: 0px; } QPushButton:hover { background-color: #166534; }")
             self.btn_refresh.setEnabled(True)
         
        self.btn_new_cat.show()

        # 1. Собираем целевой список элементов
        target_items = []

        fresh_roots = []
        if self.SORT_DIR and os.path.exists(self.SORT_DIR):
             fresh_roots.append(self.SORT_DIR)
        for t in self.temp_roots:
             if os.path.exists(t) and t not in fresh_roots:
                 fresh_roots.append(t)
                 
        new_order = []
        for p in self.ui_root_order:
             if p in fresh_roots:
                 new_order.append(p)
                 fresh_roots.remove(p) 
         
        new_order.extend(fresh_roots)
        self.ui_root_order = new_order
         
        for path in self.ui_root_order:
             is_main_sort = (path == self.SORT_DIR)
             
             if self.temp_roots and is_main_sort:
                 name = f"📍 {os.path.basename(path)}"
             elif not is_main_sort: 
                 name = f"⚡ {os.path.basename(path)}"
             else:
                 name = ""
             
             if self.temp_roots or (is_main_sort and self.temp_roots):
                 target_items.append((name, path, "category"))
                 
             elif is_main_sort and not self.temp_roots:
                 try:
                     items = []
                     with os.scandir(path) as it:
                         for entry in it:
                             if entry.is_dir() and entry.name != ".mediakeeper":
                                 items.append(entry.name)
                 except:
                     items = []
                 
                 key_path = os.path.normpath(path)
                 
                 if key_path in self.custom_orders:
                     order = self.custom_orders[key_path]
                     ordered_items = [i for i in order if i in items]
                     new_items = sorted([i for i in items if i not in order])
                     final_items = ordered_items + new_items
                     self.custom_orders[key_path] = final_items
                     items = final_items
                 else: items = sorted(items)

                 for cat_name in items:
                     cat_path = os.path.join(path, cat_name)
                     target_items.append((cat_name, cat_path, "category"))

        target_items.append(("", self.SORT_DIR, "drop_zone"))

        t4 = time.perf_counter()
        logging.info(f"[PROFILER] target_items ({len(target_items)} items) assembled in {t4 - t3:.4f}s")

        # 2. Находим текущие виджеты в cats_container
        layout = self.cats_container.v_layout
        current_widgets = {}
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if w:
                if hasattr(w, 'path'):
                    current_widgets[w.path] = w
                elif w.__class__.__name__ == "DropZoneWidget":
                    current_widgets["__drop_zone__"] = w

        # 3. Удаляем те виджеты, которых больше нет в целевом списке
        target_keys = {item[1] if item[2] != "drop_zone" else "__drop_zone__" for item in target_items}
        for key, w in list(current_widgets.items()):
            if key not in target_keys:
                layout.removeWidget(w)
                w.deleteLater()
                del current_widgets[key]

        # 4. Инкрементально вставляем и синхронизируем
        for idx, (name, path, item_type) in enumerate(target_items):
            key = path if item_type != "drop_zone" else "__drop_zone__"
            
            if key in current_widgets:
                widget = current_widgets[key]
                if layout.indexOf(widget) != idx:
                    layout.removeWidget(widget)
                    layout.insertWidget(idx, widget)
                if item_type == "category" and isinstance(widget, CategoryWidget):
                    if getattr(widget, '_sections_loaded', False):
                        widget.refresh_sections()
            else:
                if item_type == "category":
                    widget = CategoryWidget(name, path, self, level=0)
                    if path not in getattr(self, 'collapsed_states_cache', {}) and self.temp_roots:
                        if not widget.is_collapsed:
                            widget.toggle_collapse()
                    layout.insertWidget(idx, widget)
                else:
                    drop_zone = DropZoneWidget()
                    drop_zone.set_folder_info(self.SORT_DIR)
                    drop_zone.clicked.connect(self.browse_and_add_temp_root)
                    drop_zone.clear_default_requested.connect(self.clear_default_sort)
                    drop_zone.files_dropped.connect(self.on_drop_zone_files_dropped)
                    
                    if self.config.get("path_sort", ""):
                        drop_zone.btn_clear.show()
                    else:
                        drop_zone.btn_clear.hide()
                    layout.insertWidget(idx, drop_zone)

        t5 = time.perf_counter()
        logging.info(f"[PROFILER] UI widgets inserted/updated in {t5 - t4:.4f}s. Total reload_categories_ui time: {t5 - t3:.4f}s")



    def closeEvent(self, event):
        if hasattr(self, 'affix_window') and self.affix_window:
            self.affix_window.close()
        super().closeEvent(event)

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
    
    def on_drop_zone_files_dropped(self, paths):
        """Adapter to convert string paths from DropZone to QUrls for add_temporary_roots."""
        if not paths: return
        urls = [QUrl.fromLocalFile(p) for p in paths]
        self.add_temporary_roots(urls)

    def stop_playback(self):
        if hasattr(self, 'media_player'):
            self.media_player.stop()
            self.media_player.setSource(QUrl())
        if hasattr(self, 'viewer'):
            self.viewer.clear_scene_content()
        if hasattr(self, 'video_controls'):
            self.video_controls.hide()

    def on_tab_enter(self):
        if getattr(self, '_categories_dirty', False):
            self.reload_categories_ui()
            self._categories_dirty = False
            
        if getattr(self, '_incoming_dirty', False):
            self.refresh_files_list(show_progress=False)
            self._incoming_dirty = False

        if self.current_file_path and os.path.exists(self.current_file_path):
            if self.viewer.stack.currentIndex() == 0:
                if self.media_player.source().isEmpty():
                    self.show_current_file()
            else:
                self.stop_playback()
                if hasattr(self, 'video_controls'):
                    self.video_controls.hide()

    def open_settings_dialog(self):
        super().open_settings_dialog()

    def enter_focus_mode(self, new_root_path):
        if not os.path.exists(new_root_path): return
        
        if not self.is_focus_mode:
            self.original_sort_dir = self.SORT_DIR
            
        self.is_focus_mode = True
        self.SORT_DIR = new_root_path
        self.cats_container.parent_path = self.SORT_DIR
        
        self.reload_categories_ui()
        self.update_watcher_paths()
        
        self.btn_back.show()
        self.btn_new_cat.show() 

    def exit_focus_mode(self):
        if not self.is_focus_mode: return
        
        self.is_focus_mode = False
        self.SORT_DIR = self.original_sort_dir
        self.cats_container.parent_path = self.SORT_DIR
        
        self.reload_categories_ui()
        self.update_watcher_paths()
        
        self.btn_back.hide()

    def _fit_video_size_changed(self, size):
        if hasattr(self, 'viewer') and hasattr(self.viewer, 'single_view'):
            # Force resize event to recalculate overlay position when video size changes
            self.viewer.single_view.resizeEvent(None)
            
    def _update_overlay_time(self, pos):
        if hasattr(self, 'media_player') and hasattr(self, 'time_overlay'):
            dur = self.media_player.duration()
            self.time_overlay.set_time(pos, dur)

    def _update_overlay_duration(self, dur):
        if hasattr(self, 'media_player') and hasattr(self, 'time_overlay'):
            pos = self.media_player.position()
            self.time_overlay.set_time(pos, dur)
            if hasattr(self, 'viewer') and hasattr(self.viewer, 'single_view'):
                self.viewer.single_view.resizeEvent(None)

    def on_nesting_changed(self, index):
        """Handle nesting level change from combobox."""
        level = index + 1  # Index 0 = level 1, etc.
        self.config["max_nesting_depth"] = level
        ConfigManager.save(self.config)
        self.reload_categories_ui()
        self.setFocus()

    def eventFilter(self, obj, event):
        """Filter events to make read-only editable combobox open on click."""
        if obj == self.combo_nesting.lineEdit():
            if event.type() == QEvent.Type.MouseButtonPress:
                self.combo_nesting.showPopup()
                return True
        return super().eventFilter(obj, event)

    def on_view_mode_changed(self, mode_idx):
        if hasattr(self, 'update_hotkeys_context'):
            self.update_hotkeys_context(mode_idx)
            
        if mode_idx == 0:
            # Switched to Single view mode. Show current file.
            if hasattr(self, 'btn_rot_l') and self.btn_rot_l:
                self.btn_rot_l.show()
            if hasattr(self, 'btn_rot_r') and self.btn_rot_r:
                self.btn_rot_r.show()
            self.show_current_file()
        else:
            # Switched to Grid/List mode. Stop player.
            if hasattr(self, 'btn_rot_l') and self.btn_rot_l:
                self.btn_rot_l.hide()
            if hasattr(self, 'btn_rot_r') and self.btn_rot_r:
                self.btn_rot_r.hide()
            self.stop_playback()
            if hasattr(self, 'video_controls'):
                self.video_controls.hide()
            if self.current_index < len(self.files_queue):
                # Ensure current file is selected
                grid_item = self.viewer.get_grid_item(self.current_index)
                list_item = self.viewer.get_list_item(self.current_index)
                if grid_item:
                    grid_item.setSelected(True)
                    self.viewer.grid_view.scrollToItem(grid_item)
                if list_item:
                    list_item.setSelected(True)
                    self.viewer.list_view.scrollToItem(list_item)

    def on_selection_changed(self) -> None:
        selected = self.viewer.get_selected_files()
        count = len(selected)
        
        if count > 1:
            # Ручное переименование (карандаш) всегда заблокировано для множественного выделения
            self.btn_rename_cur.setEnabled(False)
            
            if count <= 40:
                # Панель аффиксов разрешена
                self.btn_tag_toggle.setEnabled(True)
                if self.affix_window:
                    self.affix_window.setEnabled(True)
                
                if AppContext.LANG == "RU":
                    self.lbl_filename.setText(f"Выбрано файлов: {count}")
                else:
                    self.lbl_filename.setText(f"Selected files: {count}")
            else:
                # Больше 40 файлов - панель аффиксов отключается
                self.btn_tag_toggle.setEnabled(False)
                if self.affix_window:
                    self.affix_window.setEnabled(False)
                
                if AppContext.LANG == "RU":
                    self.lbl_filename.setText(f"Выбрано файлов: {count} (макс. 40 для аффиксов)")
                else:
                    self.lbl_filename.setText(f"Selected files: {count} (max 40 for affixes)")
        else:
            # Одиночный выбор (1 или 0 файлов)
            self.btn_rename_cur.setEnabled(True)
            self.btn_tag_toggle.setEnabled(True)
            if self.affix_window:
                self.affix_window.setEnabled(True)
                
            if count == 1:
                path = selected[0]
                self.current_file_path = ensure_long_path(path)
                
                # Sync index
                long_path = ensure_long_path(path)
                long_unsort = ensure_long_path(self.UNSORT_DIR)
                rel_path = os.path.relpath(long_path, long_unsort)
                rel_path_norm = os.path.normpath(rel_path)
                for idx, f in enumerate(self.files_queue):
                    if os.path.normpath(f) == rel_path_norm:
                        self.current_index = idx
                        break
                
                self.update_file_info_label()
            else:
                # 0 files selected
                if self.files_queue:
                    if self.current_index < len(self.files_queue):
                        self.current_file_path = ensure_long_path(os.path.join(self.UNSORT_DIR, self.files_queue[self.current_index]))
                    self.update_file_info_label()
                else:
                    self.current_file_path = None
                    self.lbl_filename.setText(AppContext.tr("msg_empty"))

    def on_send_to_editor_requested(self, mode, filepaths):
        win = self.window()
        if not win: return
        
        if mode == "video_conv":
            if hasattr(win, "send_to_video_converter"):
                win.send_to_video_converter(filepaths)
        elif mode == "video_edit":
            if hasattr(win, "send_to_video_editor"):
                win.send_to_video_editor(filepaths[0])
        elif mode == "audio_conv":
            if hasattr(win, "send_to_audio_converter"):
                win.send_to_audio_converter(filepaths)
        elif mode == "audio_edit":
            if hasattr(win, "send_to_video_editor"):
                win.send_to_video_editor(filepaths[0])
        elif mode == "image_conv":
            if hasattr(win, "send_to_image_converter"):
                win.send_to_image_converter(filepaths)

    def on_item_double_clicked(self, filepath):
        if filepath:
            long_fp = ensure_long_path(filepath)
            if os.path.exists(long_fp):
                clean_path = strip_long_path_prefix(long_fp)
                QDesktopServices.openUrl(QUrl.fromLocalFile(clean_path))

    def update_file_info_label(self):
        if not self.current_file_path:
            self.lbl_filename.setText(AppContext.tr("msg_empty"))
            return
            
        long_curr = ensure_long_path(self.current_file_path)
        if not os.path.exists(long_curr):
            self.lbl_filename.setText(AppContext.tr("msg_empty"))
            return
            
        filename = os.path.basename(self.current_file_path)
        size = 0
        try: 
            size = os.path.getsize(self.current_file_path)
        except: 
            pass
        size_str = format_size(size)
        
        # Find index in queue
        long_unsort = ensure_long_path(self.UNSORT_DIR)
        rel_path = os.path.relpath(long_curr, long_unsort)
        rel_path_norm = os.path.normpath(rel_path)
        idx_str = ""
        for idx, f in enumerate(self.files_queue):
            if os.path.normpath(f) == rel_path_norm:
                idx_str = f"[{idx + 1}/{len(self.files_queue)}]"
                break
                
        display_text = f"[{size_str}]  {filename}  {idx_str}"
        self.lbl_filename.setText(display_text)

    def set_quick_target_path(self, path):
        """Устанавливает или сбрасывает целевой каталог для Быстрого перемещения."""
        # Сбрасываем эффект пульсации у предыдущей папки
        if self.quick_target_path:
            old_widget = self.find_category_widget_by_path(self.quick_target_path)
            if old_widget:
                pulse_sub_widget = getattr(old_widget, 'btn_name', getattr(old_widget, 'btn_action', None))
                if pulse_sub_widget and pulse_sub_widget.graphicsEffect():
                    pulse_sub_widget.setGraphicsEffect(None)

        if path:
            self.quick_target_path = os.path.normpath(path)
            if self.quick_target_timeline.state() == QTimeLine.State.NotRunning:
                self.quick_target_timeline.start()
        else:
            self.quick_target_path = None
            self.quick_target_timeline.stop()
            if hasattr(self, 'viewer') and hasattr(self.viewer, 'btn_quick_target_icon'):
                if self.viewer.btn_quick_target_icon.graphicsEffect():
                    self.viewer.btn_quick_target_icon.setGraphicsEffect(None)

        # Обновляем звездочки в сайдбаре
        self.refresh_sidebar_styling()
        
        # Обновляем видимость и подсказку кнопки на холсте
        if hasattr(self, 'viewer') and self.viewer:
            self.viewer.update_quick_target_visibility()
            self.viewer.update_quick_target_tooltip()

    def find_category_widget_by_path(self, path):
        """Рекурсивно ищет виджет папки по ее абсолютному пути в сайдбаре."""
        if not path:
            return None
        norm_path = os.path.normpath(path)

        def search_layout(layout):
            if not layout:
                return None
            for i in range(layout.count()):
                item = layout.itemAt(i)
                w = item.widget()
                if w:
                    if hasattr(w, 'path') and os.path.normpath(w.path) == norm_path:
                        return w
                    # Если у виджета есть sections_container (это CategoryWidget), ищем в нем
                    if hasattr(w, 'sections_container') and w.sections_container and w.sections_container.layout:
                        sub_w = search_layout(w.sections_container.layout)
                        if sub_w:
                            return sub_w
            return None

        if hasattr(self, 'cats_container') and self.cats_container.v_layout:
            return search_layout(self.cats_container.v_layout)
        return None

    def _on_quick_target_pulse(self, value):
        """Вызывается по таймлайну для обеспечения синхронной пульсации."""
        import math
        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        # value меняется от 0.0 до 1.0. Превращаем в синус:
        opacity = 0.6 + 0.4 * math.sin(value * 2 * math.pi)

        # 1. Пульсирует кнопка быстрого перемещения на холсте через QGraphicsOpacityEffect
        if hasattr(self, 'viewer') and hasattr(self.viewer, 'btn_quick_target_icon') and self.viewer.btn_quick_target.isVisible():
            effect = self.viewer.btn_quick_target_icon.graphicsEffect()
            if not effect or not isinstance(effect, QGraphicsOpacityEffect):
                effect = QGraphicsOpacityEffect(self.viewer.btn_quick_target_icon)
                self.viewer.btn_quick_target_icon.setGraphicsEffect(effect)
            effect.setOpacity(opacity)

        # 2. Пульсирует активная папка в сайдбаре
        if self.quick_target_path:
            target_widget = self.find_category_widget_by_path(self.quick_target_path)
            if target_widget:
                pulse_sub_widget = getattr(target_widget, 'btn_name', getattr(target_widget, 'btn_action', None))
                if pulse_sub_widget:
                    effect = pulse_sub_widget.graphicsEffect()
                    if not effect:
                        effect = QGraphicsOpacityEffect(pulse_sub_widget)
                        pulse_sub_widget.setGraphicsEffect(effect)
                    effect.setOpacity(opacity)

    def refresh_video_thumbnails(self) -> None:
        """Передает запрос на обновление видео-превью во viewer."""
        if hasattr(self, 'viewer') and self.viewer:
            self.viewer.refresh_video_thumbnails()

