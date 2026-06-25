import os
import logging
import subprocess
from typing import Any
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QSplitter, QProgressBar, QMenu, QComboBox, QListView, QTextEdit
)
from PyQt6.QtCore import Qt, QTimer, QElapsedTimer, QUrl, pyqtSignal, QModelIndex, QRect, QSize
from PyQt6.QtGui import QDesktopServices, QIcon, QPainter, QTransform, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from config import AppContext, APP_DESIGN
from utils_common import format_size
from .ui_panels import CleanerSettingsPanel, CleanerActionBar
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

        self.source_folders: dict[str, dict[str, Any]] = {}
        self.filter_config: dict[str, Any] | None = None
        self.last_scanned_count: int = 0
        self.current_view_mode: int = VIEW_MODE_DUPLES
        self.was_stopped_manually: bool = False
        self.view_limit: int = 100
        self.view_filter_exts: list[str] | None = None
        self.view_filter_mode: str = 'include'

        self.finder: Any = None
        self.scanner: Any = None
        self.mover: Any = None
        self.deleter: Any = None

        self.db_helper: CleanerDB = CleanerDB()
        self.session_db: SessionDB = SessionDB()
        self.session_db.clear_db()

        self.virtual_model: DuplicateVirtualModel = DuplicateVirtualModel(self)
        self.virtual_delegate: DuplicateDelegate = DuplicateDelegate(self)

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

        self.lbl_title = QLabel(AppContext.tr("cln_title"))
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: 900; color: #eee; letter-spacing: 1px;")
        tt_layout.addWidget(self.lbl_title, 0, Qt.AlignmentFlag.AlignVCenter)
        tt_layout.addStretch()

        self.btn_toggle_settings = QPushButton(AppContext.tr("cln_toggle_settings_hide"))
        self.btn_toggle_settings.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.btn_toggle_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_settings.setStyleSheet("background: transparent; color: #888; border: none; font-weight: bold;")
        self.btn_toggle_settings.clicked.connect(self.toggle_settings)
        tt_layout.addWidget(self.btn_toggle_settings)
        self.main_layout.addWidget(self.top_toolbar)

        # 2. SETTINGS PANEL
        self.settings_panel = CleanerSettingsPanel()
        self.settings_panel.add_folder_clicked.connect(self.add_folder)
        self.settings_panel.folder_dropped.connect(self.add_folder_path)
        self.settings_panel.clear_folders_clicked.connect(self.clear_folders)
        self.settings_panel.open_filter_clicked.connect(self.open_filter_dialog)
        self.settings_panel.start_scan_clicked.connect(self.toggle_scan)
        self.settings_panel.chk_safe_scan.toggled.connect(self.on_safe_scan_toggled)
        self.settings_panel.clear_cache_clicked.connect(self.clear_cache)
        self.settings_panel.mode_duples_clicked.connect(lambda: self.switch_view_mode(VIEW_MODE_DUPLES))
        self.settings_panel.mode_zero_clicked.connect(lambda: self.switch_view_mode(VIEW_MODE_ZERO))
        self.settings_panel.mode_empty_clicked.connect(lambda: self.switch_view_mode(VIEW_MODE_EMPTY))
        self.settings_panel.set_scan_enabled(False)
        self.main_layout.addWidget(self.settings_panel)

        self.settings_separator = QFrame()
        self.settings_separator.setFixedHeight(2)
        self.settings_separator.setStyleSheet("background-color: #1a1a1a; border-top: 1px solid #333; border-bottom: 1px solid #333;")
        self.main_layout.addWidget(self.settings_separator)

        # 3. RESULTS AREA
        self.results_widget = QWidget()
        results_layout = QVBoxLayout(self.results_widget)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(0)

        self.action_bar = CleanerActionBar()
        self.action_bar.autoselect_changed.connect(self.on_autoselect_changed)
        self.action_bar.deselect_clicked.connect(self.deselect_all)
        self.action_bar.select_all_clicked.connect(self.select_all_items)
        self.action_bar.move_clicked.connect(self.move_selected)
        self.action_bar.delete_clicked.connect(self.delete_selected)
        self.action_bar.browse_clicked.connect(self.browse_dest)
        self.action_bar.drop_zone.path_changed.connect(self.validate_move_state)
        results_layout.addWidget(self.action_bar)

        res_splitter = QSplitter(Qt.Orientation.Horizontal)
        res_splitter.setHandleWidth(1)
        res_splitter.setStyleSheet("QSplitter::handle { background-color: #444; }")

        tree_container = QWidget()
        tree_l = QVBoxLayout(tree_container)
        tree_l.setContentsMargins(0, 0, 0, 0)
        tree_l.setSpacing(0)
        self.init_tree_toolbar(tree_l)

        # Список — основной список дубликатов
        self.tree = CleanerListView()
        self.tree.setModel(self.virtual_model)
        self.tree.setItemDelegate(self.virtual_delegate)
        self.tree.setUniformItemSizes(True)
        self.tree.setMouseTracking(True)
        self.tree.viewport().setMouseTracking(True)
        self.tree.setStyleSheet("""
            QListView { background-color: #222222; border: none; color: #ccc; font-size: 13px; }
            QListView::item { border: none; padding: 0px; margin: 0px; }
            QListView::item:hover { background-color: #262626; }
            QListView::item:selected { background-color: #333; }
        """)
        self.tree.setSelectionMode(self.tree.SelectionMode.SingleSelection)
        self.tree.clicked.connect(self.on_item_clicked)
        self.tree.selectionModel().currentChanged.connect(self.on_current_changed)
        self.tree.doubleClicked.connect(self.on_item_double_clicked)
        self.tree.itemMiddleClicked.connect(self.on_item_middle_clicked)
        self.tree.customContextMenuRequested.connect(self.on_tree_context_menu)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        # =========================================================
        # IRON RULE: подключаем сигнал чекбокса к единственному
        # обработчику, который enforces правило N-1.
        # =========================================================
        self.tree.checkbox_clicked.connect(self._on_tree_checkbox_clicked)

        tree_l.addWidget(self.tree)
        res_splitter.addWidget(tree_container)

        # Preview
        self.preview_container = QWidget()
        self.preview_container.setStyleSheet("background-color: #000;")
        prev_l = QVBoxLayout(self.preview_container)
        prev_l.setContentsMargins(0, 0, 0, 0)
        prev_l.setSpacing(0)

        prev_header = QWidget()
        prev_header.setStyleSheet("background-color: #2b2b2b; border-bottom: 1px solid #444;")
        phl = QHBoxLayout(prev_header)
        phl.setContentsMargins(10, 5, 10, 5)

        self.btn_info_toggle = QPushButton(AppContext.tr("cln_btn_info"))
        self.btn_info_toggle.setCheckable(True)
        self.btn_info_toggle.setFixedHeight(24)
        self.btn_info_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_info_toggle.setStyleSheet("""
            QPushButton { background-color: #333; color: #aaa; border: 1px solid #444; border-radius: 4px; padding: 0 8px; font-weight: bold; }
            QPushButton:checked { background-color: #3b82f6; color: white; border-color: #3b82f6; }
            QPushButton:hover { background-color: #444; color: white; }
        """)
        self.btn_info_toggle.clicked.connect(self.toggle_info_panel)

        self.lbl_prev = QLabel(AppContext.tr("cln_preview_title"))
        self.lbl_prev.setStyleSheet("color: #888; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        phl.addWidget(self.lbl_prev)
        
        phl.addStretch()
        phl.addWidget(self.btn_info_toggle)
        prev_l.addWidget(prev_header)

        self.preview_widget = CleanerPreviewWidget()
        if hasattr(self.preview_widget, 'splitter'):
            self.preview_widget.splitter.setSizes([200, 150])
        prev_l.addWidget(self.preview_widget)

        self.info_panel = QTextEdit()
        self.info_panel.setReadOnly(True)
        self.info_panel.setVisible(False)
        self.info_panel.setMaximumHeight(150)
        self.info_panel.setStyleSheet("QTextEdit { background-color: #222; color: #ccc; border-top: 1px solid #444; font-size: 12px; padding: 5px; border-bottom: none; border-left: none; border-right: none; }")
        prev_l.addWidget(self.info_panel)

        res_splitter.addWidget(self.preview_container)
        res_splitter.setSizes([850, 350])

        results_layout.addWidget(res_splitter)
        self.main_layout.addWidget(self.results_widget, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setStyleSheet("QProgressBar { border: none; background: #222; } QProgressBar::chunk { background: #3b82f6; }")
        self.progress_bar.hide()
        self.main_layout.addWidget(self.progress_bar)

        self.overlay = CleanerOverlay(self)
        self.overlay.hide()
        self.overlay.cancel_requested.connect(self.on_overlay_cancel)

        self.update_ui_text()
        self.on_safe_scan_toggled()
        self.update_cache_info()
        self.switch_view_mode(VIEW_MODE_DUPLES)

    def init_tree_toolbar(self, layout: QVBoxLayout) -> None:
        tt_bar = QFrame()
        tt_bar.setFixedHeight(40)
        tt_bar.setStyleSheet("background: #2a2a2a; border-bottom: 1px solid #333;")
        tt_layout = QHBoxLayout(tt_bar)
        tt_layout.setContentsMargins(10, 0, 10, 0)
        tt_layout.setSpacing(10)

        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")

        self.btn_exp = QPushButton()
        self.btn_exp.setIcon(QIcon(os.path.join(icons_dir, "square-chevron-down.svg")))
        self.btn_exp.setIconSize(QSize(18, 18))
        self.btn_exp.setToolTip(AppContext.tr("cln_btn_expand"))

        self.btn_col = QPushButton()
        self.btn_col.setIcon(QIcon(os.path.join(icons_dir, "square-chevron-up.svg")))
        self.btn_col.setIconSize(QSize(18, 18))
        self.btn_col.setToolTip(AppContext.tr("cln_btn_collapse"))

        for b in [self.btn_exp, self.btn_col]:
            b.setFixedWidth(30)
            b.setStyleSheet("QPushButton { background: #333; border: 1px solid #444; border-radius: 3px; } QPushButton:hover { background: #444; }")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _, x=b: self.toggle_tree(x == self.btn_exp))
            tt_layout.addWidget(b)

        self.btn_sort_v = QPushButton()
        self.btn_sort_v.setIcon(QIcon(os.path.join(icons_dir, "arrow-up-down.svg")))
        self.btn_sort_v.setIconSize(QSize(18, 18))
        self.btn_sort_v.setFixedWidth(30)
        self.btn_sort_v.setToolTip(AppContext.tr("cln_tooltip_sort_v"))
        self.btn_sort_v.setStyleSheet("""
            QPushButton { background: #333; border: 1px solid #444; border-radius: 3px; }
            QPushButton:hover { background: #444; }
            QPushButton:pressed { background: #3b82f6; border-color: #3b82f6; }
        """)
        self.btn_sort_v.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sort_v.clicked.connect(self.sort_tree_by_selection)
        tt_layout.addWidget(self.btn_sort_v)

        tt_layout.addSpacing(10)

        self.lbl_show = QLabel("")
        self.lbl_show.hide()
        self.combo_limit = QComboBox()
        self.combo_limit.hide()
        self.btn_load_more = QPushButton("")
        self.btn_load_more.hide()
        self.btn_stop_load = QPushButton("")
        self.btn_stop_load.hide()

        self.btn_types = QPushButton(AppContext.tr("cln_btn_types"))
        self.btn_types.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_types_button_style()
        self.btn_types.clicked.connect(self.on_type_filter_click)
        self.btn_types.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.btn_types.customContextMenuRequested.connect(self.on_types_context_menu)
        tt_layout.addWidget(self.btn_types)

        tt_layout.addStretch()

        self.lbl_groups_found = QLabel(AppContext.tr("cln_lbl_groups").format("0 (0)"))
        self.lbl_groups_found.setStyleSheet("color: #aaa; font-size: 11px; margin-right: 15px;")
        self.lbl_groups_found.setFixedWidth(160)
        self.lbl_groups_found.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        tt_layout.addWidget(self.lbl_groups_found)

        self.lbl_selection_info = QLabel(AppContext.tr("cln_lbl_selected").format(0, "0 B"))
        self.lbl_selection_info.setStyleSheet("color: #93c5fd; font-size: 11px; font-weight: bold;")
        tt_layout.addWidget(self.lbl_selection_info)

        layout.addWidget(tt_bar)

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
        self.lbl_title.setText(AppContext.tr("cln_title"))
        self.update_toggle_settings_button()
        self.lbl_prev.setText(AppContext.tr("cln_preview_title"))
        if hasattr(self, 'btn_info_toggle'):
            self.btn_info_toggle.setText(AppContext.tr("cln_btn_info"))
        self.settings_panel.update_ui_text()
        self.action_bar.update_ui_text()
        self.preview_widget.update_ui_text()
        self.btn_types.setText(AppContext.tr("cln_btn_types"))
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
