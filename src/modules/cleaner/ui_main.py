import os
import logging
import subprocess
from typing import Any
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QSplitter, QProgressBar, QMenu, QComboBox, QListView, QTextEdit,
    QStackedWidget, QTabBar
)
from PyQt6.QtCore import Qt, QTimer, QElapsedTimer, QUrl, pyqtSignal, QModelIndex, QRect, QSize
from PyQt6.QtGui import QDesktopServices, QIcon, QPainter, QTransform, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from config import AppContext, APP_DESIGN
from utils_common import format_size
from .ui_panels import CleanerSettingsPanel, CleanerActionBar, SimilarSettingsPanel
from .ui_preview import CleanerPreviewWidget
from .ui_widgets import SourceListItem, GroupHeaderWidget
from .ui_dialogs import CleanerOverlay
from .db_cache import CleanerDB
from .db_session import SessionDB
from .ui_model import DuplicateVirtualModel, DuplicateDelegate

from .logic_tree import CleanerTreeMixin
from .logic_scan import ScanMixin
from .logic_view import ViewMixin
from .logic_actions import ActionMixin
from .logic_selection import CleanerSelectionMixin

VIEW_MODE_DUPLES: int = 0
VIEW_MODE_ZERO: int = 1
VIEW_MODE_EMPTY: int = 2


class CleanerListView(QListView):
    itemMiddleClicked = pyqtSignal(QModelIndex)
    checkbox_clicked = pyqtSignal(object, bool)

    def mousePressEvent(self, event: Any) -> None:
        # --- Middle click: reveal in explorer ---
        if event.button() == Qt.MouseButton.MiddleButton:
            index: QModelIndex = self.indexAt(event.pos())
            if index.isValid():
                self.itemMiddleClicked.emit(index)

        # --- Left click: check for checkbox hit ---
        if event.button() == Qt.MouseButton.LeftButton:
            vp_pos = self.viewport().mapFrom(self, event.pos())
            index = self.indexAt(vp_pos)

            if index.isValid():
                item = index.data(Qt.ItemDataRole.UserRole)
                if item:
                    item_type = item.get('type')

                    # Checkbox для файла дубликата (незащищённого)
                    if item_type == 'file' and not item.get('is_protected', False):
                        visual_rect = self.visualRect(index)
                        cb_x = visual_rect.left() + 30
                        cb_y = visual_rect.top() + (visual_rect.height() - 16) // 2
                        cb_rect = QRect(cb_x, cb_y, 16, 16)
                        if cb_rect.contains(vp_pos):
                            new_state = not bool(item.get('is_marked', 0))
                            self.checkbox_clicked.emit(item, new_state)
                            return  # поглощаем событие, строка не меняется

                    # Checkbox для пустой папки
                    elif item_type == 'empty_folder':
                        visual_rect = self.visualRect(index)
                        cb_x = visual_rect.left() + 10
                        cb_y = visual_rect.top() + (visual_rect.height() - 16) // 2
                        cb_rect = QRect(cb_x, cb_y, 16, 16)
                        if cb_rect.contains(vp_pos):
                            new_state = not bool(item.get('is_marked', 0))
                            self.checkbox_clicked.emit(item, new_state)
                            return

        super().mousePressEvent(event)


class CleanerModule(QWidget, CleanerTreeMixin, ScanMixin, ViewMixin, ActionMixin, CleanerSelectionMixin):
    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        logging.info("Initializing CleanerModule")

        self.source_folders_dupes: dict[str, dict[str, Any]] = {}
        self.source_folders_similar: dict[str, dict[str, Any]] = {}
        self.filter_config: dict[str, Any] | None = None
        self.last_scanned_count: int = 0
        self.current_view_mode: int = VIEW_MODE_DUPLES
        self.was_stopped_manually: bool = False
        self.view_limit: int = 100
        self.view_filter_exts: list[str] | None = None
        self.view_filter_mode: str = 'include'

        self.finder_dupes: Any = None
        self.finder_similar: Any = None
        self.scanner_dupes: Any = None
        self.scanner_similar: Any = None
        self.mover_dupes: Any = None
        self.mover_similar: Any = None
        self.deleter_dupes: Any = None
        self.deleter_similar: Any = None

        self.db_helper_dupes = CleanerDB()
        from .db_cache import SimilarDB
        self.db_helper_similar = SimilarDB()
        
        self.session_db_dupes = SessionDB()
        self.session_db_dupes.clear_db()
        from .db_session import SimilarSessionDB
        self.session_db_similar = SimilarSessionDB()
        self.session_db_similar.clear_db()

        self.virtual_model_dupes = DuplicateVirtualModel(self)
        self.virtual_model_dupes.is_similar_mode = False
        self.virtual_delegate_dupes = DuplicateDelegate(self)
        
        self.virtual_model_similar = DuplicateVirtualModel(self)
        self.virtual_model_similar.is_similar_mode = True
        self.virtual_delegate_similar = DuplicateDelegate(self)

        self.scan_timer: QElapsedTimer = QElapsedTimer()
        self.move_timer: QElapsedTimer = QElapsedTimer()
        self.ui_timer: QTimer = QTimer()
        self.ui_timer.setInterval(50)
        self.ui_timer.timeout.connect(self.update_timer_label)

        self.loading_timer: QTimer = QTimer()
        self.selection_timer: QTimer = QTimer()
        self.incremental_loader_timer: QTimer = QTimer(self)

        self.setAcceptDrops(True)
        self.init_ui()

    @property
    def current_tab(self) -> int:
        if hasattr(self, 'tab_bar'):
            return self.tab_bar.currentIndex()
        return 0

    @property
    def source_folders(self) -> dict:
        return self.source_folders_similar if self.current_tab == 1 else self.source_folders_dupes

    @source_folders.setter
    def source_folders(self, val: dict) -> None:
        if self.current_tab == 1:
            self.source_folders_similar = val
        else:
            self.source_folders_dupes = val

    @property
    def db_helper(self):
        return self.db_helper_similar if self.current_tab == 1 else self.db_helper_dupes

    @property
    def session_db(self):
        return self.session_db_similar if self.current_tab == 1 else self.session_db_dupes

    @property
    def virtual_model(self):
        return self.virtual_model_similar if self.current_tab == 1 else self.virtual_model_dupes

    @property
    def virtual_delegate(self):
        return self.virtual_delegate_similar if self.current_tab == 1 else self.virtual_delegate_dupes

    @property
    def tree(self):
        return self.tree_similar if self.current_tab == 1 else self.tree_dupes

    @property
    def settings_panel(self):
        return self.settings_panel_similar if self.current_tab == 1 else self.settings_panel_dupes

    @property
    def settings_separator(self):
        return self.settings_separator_similar if self.current_tab == 1 else self.settings_separator_dupes

    @property
    def action_bar(self):
        return self.action_bar_similar if self.current_tab == 1 else self.action_bar_dupes

    @property
    def preview_widget(self):
        return self.preview_widget_similar if self.current_tab == 1 else self.preview_widget_dupes

    @property
    def progress_bar(self):
        return self.progress_bar_similar if self.current_tab == 1 else self.progress_bar_dupes

    @property
    def btn_info_toggle(self):
        return self.btn_info_toggle_similar if self.current_tab == 1 else self.btn_info_toggle_dupes

    @property
    def info_panel(self):
        return self.info_panel_similar if self.current_tab == 1 else self.info_panel_dupes

    @property
    def preview_container(self):
        return self.preview_container_similar if self.current_tab == 1 else self.preview_container_dupes

    @property
    def results_widget(self):
        return self.results_widget_similar if self.current_tab == 1 else self.results_widget_dupes

    @property
    def finder(self):
        return self.finder_similar if self.current_tab == 1 else self.finder_dupes

    @finder.setter
    def finder(self, val):
        if self.current_tab == 1:
            self.finder_similar = val
        else:
            self.finder_dupes = val

    @property
    def scanner(self):
        return self.scanner_similar if self.current_tab == 1 else self.scanner_dupes

    @scanner.setter
    def scanner(self, val):
        if self.current_tab == 1:
            self.scanner_similar = val
        else:
            self.scanner_dupes = val

    @property
    def mover(self):
        return self.mover_similar if self.current_tab == 1 else self.mover_dupes

    @mover.setter
    def mover(self, val):
        if self.current_tab == 1:
            self.mover_similar = val
        else:
            self.mover_dupes = val

    @property
    def deleter(self):
        return self.deleter_similar if self.current_tab == 1 else self.deleter_dupes

    @deleter.setter
    def deleter(self, val):
        if self.current_tab == 1:
            self.deleter_similar = val
        else:
            self.deleter_dupes = val

    @property
    def btn_exp(self):
        return self.btn_exp_similar if self.current_tab == 1 else self.btn_exp_dupes

    @property
    def btn_col(self):
        return self.btn_col_similar if self.current_tab == 1 else self.btn_col_dupes

    @property
    def btn_sort_v(self):
        return self.btn_sort_v_similar if self.current_tab == 1 else self.btn_sort_v_dupes

    @property
    def lbl_show(self):
        return self.lbl_show_similar if self.current_tab == 1 else self.lbl_show_dupes

    @property
    def combo_limit(self):
        return self.combo_limit_similar if self.current_tab == 1 else self.combo_limit_dupes

    @property
    def btn_types(self):
        # Кнопка типов есть только на странице дублей
        return self.btn_types_dupes

    @property
    def lbl_groups_found(self):
        return self.lbl_groups_found_similar if self.current_tab == 1 else self.lbl_groups_found_dupes

    @property
    def lbl_selection_info(self):
        return self.lbl_selection_info_similar if self.current_tab == 1 else self.lbl_selection_info_dupes

    def init_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 1. HEADER
        self.top_toolbar = QFrame()
        self.top_toolbar.setFixedHeight(40)
        self.top_toolbar.setStyleSheet("background-color: #2b2b2b;")
        tt_layout = QHBoxLayout(self.top_toolbar)
        tt_layout.setContentsMargins(60, 0, 15, 0)

        is_ru = (AppContext.LANG == "RU")
        self.tab_bar = QTabBar()
        self.tab_bar.addTab("Поиск дубликатов" if is_ru else "Duplicates Search")
        self.tab_bar.addTab("Поиск похожих" if is_ru else "Similar Search")
        self.tab_bar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tab_bar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tab_bar.setStyleSheet("""
            QTabBar::tab {
                background-color: #222;
                color: #888;
                border: 1px solid #3e3e42;
                padding: 6px 16px;
                font-weight: bold;
                font-size: 13px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
                margin-top: 4px;
            }
            QTabBar::tab:hover {
                background-color: #333;
                color: #ccc;
            }
            QTabBar::tab:selected {
                background-color: #1e1e1e;
                color: white;
                border-bottom: 2px solid #3b82f6;
            }
        """)
        self.tab_bar.currentChanged.connect(self.on_tab_changed)
        tt_layout.addWidget(self.tab_bar, 0, Qt.AlignmentFlag.AlignVCenter)
        tt_layout.addStretch()

        self.btn_toggle_settings = QPushButton(AppContext.tr("cln_toggle_settings_hide"))
        self.btn_toggle_settings.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.btn_toggle_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_settings.setStyleSheet("background: transparent; color: #888; border: none; font-weight: bold;")
        self.btn_toggle_settings.clicked.connect(self.toggle_settings)
        tt_layout.addWidget(self.btn_toggle_settings)
        self.main_layout.addWidget(self.top_toolbar)

        # 2. STACKED WIDGET FOR PAGES
        self.stacked_widget = QStackedWidget()
        
        # Create Duplicates Page
        (self.page_dupes, self.settings_panel_dupes, self.settings_separator_dupes, 
         self.results_widget_dupes, self.action_bar_dupes, self.tree_dupes, 
         self.preview_container_dupes, self.preview_widget_dupes, self.info_panel_dupes, 
         self.progress_bar_dupes, self.btn_info_toggle_dupes, self.btn_exp_dupes, 
         self.btn_col_dupes, self.btn_sort_v_dupes, self.lbl_show_dupes, 
         self.combo_limit_dupes, self.btn_types_dupes, self.lbl_groups_found_dupes,
         self.lbl_selection_info_dupes) = self.create_page(is_similar=False)
        self.stacked_widget.addWidget(self.page_dupes)
        
        # Create Similar Page
        (self.page_similar, self.settings_panel_similar, self.settings_separator_similar, 
         self.results_widget_similar, self.action_bar_similar, self.tree_similar, 
         self.preview_container_similar, self.preview_widget_similar, self.info_panel_similar, 
         self.progress_bar_similar, self.btn_info_toggle_similar, self.btn_exp_similar, 
         self.btn_col_similar, self.btn_sort_v_similar, self.lbl_show_similar, 
         self.combo_limit_similar, self.btn_types_similar, self.lbl_groups_found_similar,
         self.lbl_selection_info_similar) = self.create_page(is_similar=True)
        self.stacked_widget.addWidget(self.page_similar)
        
        self.main_layout.addWidget(self.stacked_widget, 1)

        self.overlay = CleanerOverlay(self)
        self.overlay.hide()
        self.overlay.cancel_requested.connect(self.on_overlay_cancel)

        self.update_ui_text()
        self.on_safe_scan_toggled()
        self.update_cache_info()
        self.switch_view_mode(VIEW_MODE_DUPLES)

    def on_tab_changed(self, index: int) -> None:
        self.stacked_widget.setCurrentIndex(index)
        self.update_toggle_settings_button()
        self.update_cache_info()
        self.on_safe_scan_toggled()

    def on_media_type_changed(self, index: int) -> None:
        self.filter_config = None
        self.on_safe_scan_toggled()

    def create_page(self, is_similar: bool):
        page_widget = QWidget()
        page_layout = QVBoxLayout(page_widget)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        
        # 1. Settings Panel
        if is_similar:
            settings_panel = SimilarSettingsPanel()
            settings_panel.add_folder_clicked.connect(self.add_folder)
            settings_panel.folder_dropped.connect(self.add_folder_path)
            settings_panel.clear_folders_clicked.connect(self.clear_folders)
            settings_panel.open_filter_clicked.connect(self.open_filter_dialog)
            settings_panel.start_scan_clicked.connect(self.toggle_scan)
            settings_panel.clear_cache_clicked.connect(self.clear_cache)
            settings_panel.combo_media_type.currentIndexChanged.connect(self.on_media_type_changed)
        else:
            settings_panel = CleanerSettingsPanel()
            settings_panel.add_folder_clicked.connect(self.add_folder)
            settings_panel.folder_dropped.connect(self.add_folder_path)
            settings_panel.clear_folders_clicked.connect(self.clear_folders)
            settings_panel.open_filter_clicked.connect(self.open_filter_dialog)
            settings_panel.start_scan_clicked.connect(self.toggle_scan)
            settings_panel.chk_safe_scan.toggled.connect(self.on_safe_scan_toggled)
            settings_panel.clear_cache_clicked.connect(self.clear_cache)
            settings_panel.mode_duples_clicked.connect(lambda: self.switch_view_mode(VIEW_MODE_DUPLES))
            settings_panel.mode_zero_clicked.connect(lambda: self.switch_view_mode(VIEW_MODE_ZERO))
            settings_panel.mode_empty_clicked.connect(lambda: self.switch_view_mode(VIEW_MODE_EMPTY))
            
        settings_panel.set_scan_enabled(False)
        page_layout.addWidget(settings_panel)
        
        # Separator
        settings_separator = QFrame()
        settings_separator.setFixedHeight(2)
        settings_separator.setStyleSheet("background-color: #1a1a1a; border-top: 1px solid #333; border-bottom: 1px solid #333;")
        page_layout.addWidget(settings_separator)
        
        # Results area
        results_widget = QWidget()
        results_layout = QVBoxLayout(results_widget)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(0)
        
        action_bar = CleanerActionBar()
        action_bar.is_similar_mode = is_similar
        action_bar.update_autoselect_items()
        action_bar.autoselect_changed.connect(self.on_autoselect_changed)
        action_bar.deselect_clicked.connect(self.deselect_all)
        action_bar.select_all_clicked.connect(self.select_all_items)
        action_bar.move_clicked.connect(self.move_selected)
        action_bar.delete_clicked.connect(self.delete_selected)
        action_bar.browse_clicked.connect(self.browse_dest)
        action_bar.drop_zone.path_changed.connect(self.validate_move_state)
        results_layout.addWidget(action_bar)
        
        res_splitter = QSplitter(Qt.Orientation.Horizontal)
        res_splitter.setHandleWidth(1)
        res_splitter.setStyleSheet("QSplitter::handle { background-color: #444; }")
        
        tree_container = QWidget()
        tree_l = QVBoxLayout(tree_container)
        tree_l.setContentsMargins(0, 0, 0, 0)
        tree_l.setSpacing(0)
        
        # Инициализация тулбара с кнопками раскрытия/сортировки
        tt_bar = QFrame()
        tt_bar.setFixedHeight(40)
        tt_bar.setStyleSheet("background: #2a2a2a; border-bottom: 1px solid #333;")
        tt_layout = QHBoxLayout(tt_bar)
        tt_layout.setContentsMargins(10, 0, 10, 0)
        tt_layout.setSpacing(10)

        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")

        btn_exp = QPushButton()
        btn_exp.setIcon(QIcon(os.path.join(icons_dir, "square-chevron-down.svg")))
        btn_exp.setIconSize(QSize(18, 18))
        btn_exp.setToolTip(AppContext.tr("cln_btn_expand"))

        btn_col = QPushButton()
        btn_col.setIcon(QIcon(os.path.join(icons_dir, "square-chevron-up.svg")))
        btn_col.setIconSize(QSize(18, 18))
        btn_col.setToolTip(AppContext.tr("cln_btn_collapse"))

        for b in [btn_exp, btn_col]:
            b.setFixedWidth(30)
            b.setStyleSheet("QPushButton { background: #333; border: 1px solid #444; border-radius: 3px; } QPushButton:hover { background: #444; }")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _, x=b: self.toggle_tree(x == btn_exp))
            tt_layout.addWidget(b)

        btn_sort_v = QPushButton()
        btn_sort_v.setIcon(QIcon(os.path.join(icons_dir, "arrow-up-down.svg")))
        btn_sort_v.setIconSize(QSize(18, 18))
        btn_sort_v.setFixedWidth(30)
        btn_sort_v.setToolTip(AppContext.tr("cln_tooltip_sort_v"))
        btn_sort_v.setStyleSheet("""
            QPushButton { background: #333; border: 1px solid #444; border-radius: 3px; }
            QPushButton:hover { background: #444; }
            QPushButton:pressed { background: #3b82f6; border-color: #3b82f6; }
        """)
        btn_sort_v.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_sort_v.clicked.connect(self.sort_tree_by_selection)
        tt_layout.addWidget(btn_sort_v)

        tt_layout.addSpacing(10)

        # btn_types: кнопка фильтра по типам файлов (только для вкладки Дубликаты)
        btn_types = None
        if not is_similar:
            btn_types = QPushButton(AppContext.tr("cln_btn_types"))
            btn_types.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_types.setStyleSheet("QPushButton { background: #333; color: white; border: 1px solid #444; border-radius: 3px; padding: 2px 8px; } QPushButton:disabled { color: #555; background: #222; border-color: #333; }")
            btn_types.clicked.connect(self.on_type_filter_click)
            btn_types.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn_types.customContextMenuRequested.connect(self.on_types_context_menu)
            tt_layout.addWidget(btn_types)

        tt_layout.addStretch()

        lbl_groups_found = QLabel(AppContext.tr("cln_lbl_groups").format("0 (0)"))
        lbl_groups_found.setStyleSheet("color: #aaa; font-size: 11px; margin-right: 15px;")
        lbl_groups_found.setFixedWidth(160)
        lbl_groups_found.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        tt_layout.addWidget(lbl_groups_found)

        lbl_selection_info = QLabel(AppContext.tr("cln_lbl_selected").format(0, "0 B"))
        lbl_selection_info.setStyleSheet("color: #93c5fd; font-size: 11px; font-weight: bold;")
        tt_layout.addWidget(lbl_selection_info)

        lbl_show = QLabel("")
        lbl_show.hide()
        combo_limit = QComboBox()
        combo_limit.hide()
        
        tree_l.addWidget(tt_bar)
        
        tree = CleanerListView()
        if is_similar:
            tree.setModel(self.virtual_model_similar)
            tree.setItemDelegate(self.virtual_delegate_similar)
        else:
            tree.setModel(self.virtual_model_dupes)
            tree.setItemDelegate(self.virtual_delegate_dupes)
            
        tree.setUniformItemSizes(True)
        tree.setMouseTracking(True)
        tree.viewport().setMouseTracking(True)
        tree.setStyleSheet("""
            QListView { background-color: #222222; border: none; color: #ccc; font-size: 13px; }
            QListView::item { border: none; padding: 0px; margin: 0px; }
            QListView::item:hover { background-color: #262626; }
            QListView::item:selected { background-color: #333; }
        """)
        tree.setSelectionMode(tree.SelectionMode.SingleSelection)
        tree.clicked.connect(self.on_item_clicked)
        tree.selectionModel().currentChanged.connect(self.on_current_changed)
        tree.doubleClicked.connect(self.on_item_double_clicked)
        tree.itemMiddleClicked.connect(self.on_item_middle_clicked)
        tree.customContextMenuRequested.connect(self.on_tree_context_menu)
        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tree.checkbox_clicked.connect(self._on_tree_checkbox_clicked)
        
        tree_l.addWidget(tree)
        res_splitter.addWidget(tree_container)
        
        # Preview
        preview_container = QWidget()
        preview_container.setStyleSheet("background-color: #000;")
        prev_l = QVBoxLayout(preview_container)
        prev_l.setContentsMargins(0, 0, 0, 0)
        prev_l.setSpacing(0)
        
        prev_header = QWidget()
        prev_header.setStyleSheet("background-color: #2b2b2b; border-bottom: 1px solid #444;")
        phl = QHBoxLayout(prev_header)
        phl.setContentsMargins(10, 5, 10, 5)
        
        btn_info_toggle = QPushButton(AppContext.tr("cln_btn_info"))
        btn_info_toggle.setCheckable(True)
        btn_info_toggle.setFixedHeight(24)
        btn_info_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_info_toggle.setStyleSheet("""
            QPushButton { background-color: #333; color: #aaa; border: 1px solid #444; border-radius: 4px; padding: 0 8px; font-weight: bold; }
            QPushButton:checked { background-color: #3b82f6; color: white; border-color: #3b82f6; }
            QPushButton:hover { background-color: #444; color: white; }
        """)
        btn_info_toggle.clicked.connect(self.toggle_info_panel)
        
        lbl_prev = QLabel(AppContext.tr("cln_preview_title"))
        lbl_prev.setStyleSheet("color: #888; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        phl.addWidget(lbl_prev)
        phl.addStretch()
        phl.addWidget(btn_info_toggle)
        prev_l.addWidget(prev_header)
        
        preview_widget = CleanerPreviewWidget()
        if hasattr(preview_widget, 'splitter'):
            preview_widget.splitter.setSizes([200, 150])
        prev_l.addWidget(preview_widget)
        
        info_panel = QTextEdit()
        info_panel.setReadOnly(True)
        info_panel.setVisible(False)
        info_panel.setMaximumHeight(150)
        info_panel.setStyleSheet("QTextEdit { background-color: #222; color: #ccc; border-top: 1px solid #444; font-size: 12px; padding: 5px; border-bottom: none; border-left: none; border-right: none; }")
        prev_l.addWidget(info_panel)
        
        res_splitter.addWidget(preview_container)
        res_splitter.setSizes([850, 350])
        
        results_layout.addWidget(res_splitter)
        page_layout.addWidget(results_widget, 1)
        
        progress_bar = QProgressBar()
        progress_bar.setFixedHeight(4)
        progress_bar.setStyleSheet("QProgressBar { border: none; background: #222; } QProgressBar::chunk { background: #3b82f6; }")
        progress_bar.hide()
        page_layout.addWidget(progress_bar)
        
        return (page_widget, settings_panel, settings_separator, results_widget, action_bar, tree, 
                preview_container, preview_widget, info_panel, progress_bar, btn_info_toggle,
                btn_exp, btn_col, btn_sort_v, lbl_show, combo_limit,
                btn_types, lbl_groups_found, lbl_selection_info)

    def init_tree_toolbar(self, layout: QVBoxLayout) -> None:
        # Метод сохранён для обратной совместимости, но не используется.
        # Тулбар теперь создаётся внутри create_page() для каждой страницы отдельно.
        pass

    def get_rotated_icon(self, file_path: str, angle: int, size: QSize = QSize(16, 16)) -> QIcon:
        renderer = QSvgRenderer(file_path)
        if not renderer.isValid():
            return QIcon()
            
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        
        transform = QTransform().rotate(angle)
        rotated_pixmap = pixmap.transformed(transform, Qt.TransformationMode.SmoothTransformation)
        
        return QIcon(rotated_pixmap)

    def get_reflected_icon(self, file_path: str, size: QSize = QSize(20, 20)) -> QIcon:
        renderer = QSvgRenderer(file_path)
        if not renderer.isValid():
            return QIcon()
            
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        
        image = pixmap.toImage()
        mirrored_image = image.mirrored(True, False)
        
        return QIcon(QPixmap.fromImage(mirrored_image))

    def update_toggle_settings_button(self) -> None:
        visible = self.settings_panel.isVisible()
        text_key = "cln_toggle_settings_hide" if visible else "cln_toggle_settings_show"
        self.btn_toggle_settings.setText(AppContext.tr(text_key))
        
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
        icon_path = os.path.join(icons_dir, "media_play.svg")
        
        angle = -90 if visible else 90
        rotated_icon = self.get_rotated_icon(icon_path, angle)
        self.btn_toggle_settings.setIcon(rotated_icon)
        self.btn_toggle_settings.setIconSize(QSize(12, 12))

    def update_ui_text(self) -> None:
        self.update_toggle_settings_button()
        self.settings_panel.update_ui_text()
        self.action_bar.update_ui_text()
        self.preview_widget.update_ui_text()
        self.btn_sort_v.setToolTip(AppContext.tr("cln_tooltip_sort_v"))
        self.btn_exp.setToolTip(AppContext.tr("cln_btn_expand"))
        self.btn_col.setToolTip(AppContext.tr("cln_btn_collapse"))
        self.update_view_stats()
        
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
        loupe_path = os.path.join(icons_dir, "loupe-color.svg")
        
        if self.finder and self.finder.isRunning():
            self.settings_panel.btn_scan.setText(AppContext.tr("cln_btn_stop"))
            self.settings_panel.btn_scan.setIcon(QIcon())
        else:
            if getattr(self.settings_panel, 'scan_stale', False):
                rescan_text = "⚠️ Пересканировать" if AppContext.LANG.upper() == "RU" else "⚠️ Rescan Required"
                self.settings_panel.btn_scan.setText(rescan_text)
                self.settings_panel.btn_scan.setIcon(QIcon())
            else:
                self.settings_panel.btn_scan.setText(" " + AppContext.tr("cln_btn_start"))
                self.settings_panel.btn_scan.setIcon(self.get_reflected_icon(loupe_path, QSize(20, 20)))
                self.settings_panel.btn_scan.setIconSize(QSize(20, 20))
        self.on_safe_scan_toggled()

    def toggle_settings(self) -> None:
        if self.settings_panel.isVisible():
            self.settings_panel.hide()
            self.settings_separator.hide()
        else:
            self.settings_panel.show()
            self.settings_separator.show()
        self.update_toggle_settings_button()

    def on_safe_scan_toggled(self) -> None:
        if not hasattr(self.settings_panel, 'chk_safe_scan'):
            return
        is_safe = self.settings_panel.chk_safe_scan.isChecked()
        if is_safe:
            self.settings_panel.lbl_filter_status.setText(AppContext.tr("cln_status_safe_media"))
            self.settings_panel.lbl_filter_status.setStyleSheet("font-size: 12px; color: #93c5fd; margin-left: 2px; font-weight: bold; margin-top: 2px;")
        else:
            if self.filter_config:
                count = len(self.filter_config.get('exts', []))
                if count == 0:
                    self.settings_panel.lbl_filter_status.setText(AppContext.tr("cln_filter_all"))
                else:
                    key = "cln_filter_status_inc" if self.filter_config.get('mode') == 'include' else "cln_filter_status_exc"
                    self.settings_panel.lbl_filter_status.setText(AppContext.tr(key).format(count))
            else:
                self.settings_panel.lbl_filter_status.setText(AppContext.tr("cln_filter_all"))
            self.settings_panel.lbl_filter_status.setStyleSheet("font-size: 12px; color: #ccc; margin-left: 2px; font-weight: bold; margin-top: 2px;")

    def update_cache_info(self) -> None:
        try:
            db_path = self.db_helper.db_path
            if os.path.exists(db_path):
                size = os.path.getsize(db_path)
                from utils_common import format_size
                self.settings_panel.update_cache_info(format_size(size))
            else:
                self.settings_panel.update_cache_info("0 B")
        except Exception:
            pass

    def clear_cache(self) -> None:
        try:
            db_path = self.db_helper.db_path
            if os.path.exists(db_path):
                if self.finder and self.finder.isRunning():
                    return
                os.remove(db_path)
            self.update_cache_info()
        except Exception as e:
            logging.error(f"Failed to clear cache: {e}")

    def update_timer_label(self) -> None:
        ms = self.scan_timer.elapsed()
        seconds = (ms // 1000) % 60
        minutes = (ms // (1000 * 60)) % 60
        milliseconds = ms % 1000
        self.settings_panel.val_time.setText(f"{minutes:02}:{seconds:02}.{milliseconds:03}")

    def on_limit_changed(self) -> None:
        pass

    # --- Item interaction ---

    def on_item_clicked(self, index: QModelIndex) -> None:
        item = index.data(Qt.ItemDataRole.UserRole)
        if item and item['type'] == 'file':
            self.preview_widget.load_file(item['path'])
            self.update_file_info(item['path'])
        elif item and item['type'] == 'empty_folder':
            self.preview_widget.show_empty(item['path'])
            self.update_file_info(item['path'])
            
    def on_current_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
        if current.isValid():
            self.on_item_clicked(current)

    def toggle_info_panel(self, checked: bool) -> None:
        self.info_panel.setVisible(checked)

    def update_file_info(self, path: str) -> None:
        if not path or not os.path.exists(path):
            self.info_panel.clear()
            return

        try:
            stat = os.stat(path)
            size_str = format_size(stat.st_size)
            import datetime
            dt_cal = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            dt_cre = datetime.datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
            
            html = f"""<div style='line-height: 1.4; color: #ccc;'>
                <b style='color: #fff; font-size: 13px;'>{os.path.basename(path)}</b><br>
                <span style='color: #888;'>{AppContext.tr("cln_meta_path")}:</span> {os.path.dirname(path)}<br>
                <span style='color: #888;'>{AppContext.tr("cln_meta_size")}:</span> <span style='color: #4ade80;'>{size_str}</span><br>
                <span style='color: #888;'>{AppContext.tr("cln_meta_date")}:</span> {dt_cal}<br>
                <span style='color: #888;'>{AppContext.tr("cln_meta_created")}:</span> {dt_cre}
            </div>"""
            self.info_panel.setHtml(html)
        except Exception as e:
            self.info_panel.setText(f"{AppContext.tr('msg_error_file')}{e}")

    def on_item_double_clicked(self, index: QModelIndex) -> None:
        item = index.data(Qt.ItemDataRole.UserRole)
        if item and item['type'] in ('file', 'empty_folder') and os.path.exists(item['path']):
            QDesktopServices.openUrl(QUrl.fromLocalFile(item['path']))

    def on_item_middle_clicked(self, index: QModelIndex) -> None:
        item = index.data(Qt.ItemDataRole.UserRole)
        if item and item['type'] in ('file', 'empty_folder') and os.path.exists(item['path']):
            path = item['path']
            from utils_common import reveal_in_explorer
            reveal_in_explorer(path)
    def setup_scan_buttons(self) -> None:
        self.settings_panel.setup_scan_buttons(self.toggle_scan, self.reset_scan)
        self.btn_abort = self.settings_panel.btn_abort
        self.btn_stop_scan = self.settings_panel.btn_stop_scan

    def restore_scan_buttons(self) -> None:
        self.settings_panel.restore_scan_buttons()
        self.btn_abort = None
        self.btn_stop_scan = None

    # =========================================================================
    # IRON RULE — единственная авторизованная точка ручного выделения файлов.
    # Вызывается из CleanerListView.mousePressEvent через сигнал checkbox_clicked.
    # Нельзя удалять, обходить или дублировать эту логику в другом месте.
    # Все операции — только в оперативной памяти, БД не затрагивается.
    # =========================================================================
    def _on_tree_checkbox_clicked(self, item: Any, new_state: bool) -> None:
        logging.debug(f"[IRON] checkbox_clicked: type={item.get('type')} new={new_state} path={item.get('path','?')}")

        if item['type'] == 'file' and getattr(self, 'current_view_mode', 0) == 0:
            # Delegate to CleanerSelectionMixin which enforces Iron Rules in RAM
            self.toggle_single_file_mark(item, new_state)

        elif item['type'] == 'empty_folder' or (item['type'] == 'file' and getattr(self, 'current_view_mode', 0) == 1):
            # Empty folders and zero files are not part of duplicate groups — simple toggle via session_db
            state_int = 1 if new_state else 0
            self.session_db.mark_file_selected(item['path'], state_int)
            
            # Find and update the original dictionary in _all_items
            for orig_item in self.virtual_model._all_items:
                if orig_item['type'] == item['type'] and orig_item['id'] == item['id']:
                    orig_item['is_marked'] = state_int
                    break
                    
            # Targeted repaint
            for row, flat_item in enumerate(self.virtual_model._flat_items):
                if flat_item['type'] == item['type'] and flat_item['id'] == item['id']:
                    idx = self.virtual_model.index(row)
                    self.virtual_model.dataChanged.emit(idx, idx, [])
                    break
            self.update_selection_info()

    def pause_playback(self) -> None:
        if hasattr(self, 'preview_widget') and self.preview_widget:
            self.preview_widget.pause_playback()

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        if hasattr(self, 'overlay') and self.overlay:
            self.overlay.resize(self.size())
