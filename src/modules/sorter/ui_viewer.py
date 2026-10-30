"""
ui_viewer.py: Главный координатор и фасад отображения медиафайлов (SorterViewerArea / MediaViewer).
Координирует режимы Сетка, Список, Одиночный просмотр и Таблица.
"""
import os
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QListWidget, QListWidgetItem,
    QStyle, QPushButton, QFrame, QAbstractItemView, QLabel,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QApplication, QDialog, QMenu, QDoubleSpinBox
)
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, pyqtSignal, QSize, QUrl, QFileInfo, QPoint, QSizeF, QItemSelectionModel
from PyQt6.QtGui import (
    QColor, QPixmap, QMovie, QWheelEvent, QMouseEvent, QFont, QPainter, QKeyEvent,
    QIcon, QFontMetrics, QCursor, QAction, QDesktopServices, QTransform, QKeySequence
)

from config import AppContext, VIEWER_DESIGN, APP_DESIGN
from utils_extensions import VIDEO_EXTS, AUDIO_EXTS, IMAGE_EXTS
from utils_io import ensure_long_path, strip_long_path_prefix

from .thumbnail_loader import ThumbnailLoader
from .ui_table import TableModeContainer

from .viewer_items import (
    safe_relpath, format_short_size, elide_text_to_two_lines, _scale_pixmap_to_canvas,
    FileIconManager, SorterGridItemWidget, ThumbnailCard, SorterListItemWidget,
    SorterGridGroupSeparatorWidget, SorterListGroupSeparatorWidget,
    SorterPlaceholderWidget, find_main_app
)
from .viewer_media_player import ZoomableGraphicsView, SingleCanvasView
from .viewer_views import SorterBaseListView, SorterGridView, SorterListView

class SorterViewerArea(QWidget):
    """Stacked Widget Area controlling Single, Grid and List modes."""
    canvas_clicked = pyqtSignal()
    fullscreen_toggled = pyqtSignal()
    items_dropped = pyqtSignal(list, bool)
    browse_requested = pyqtSignal()
    mode_changed = pyqtSignal(int)      # Emits index: 0=Single, 1=Grid, 2=List
    selection_changed = pyqtSignal()    # Emits when selected items in Grid/List change
    send_to_editor_requested = pyqtSignal(str, list)

    def get_main_app(self):
        return find_main_app(self)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.stack = QStackedWidget(self)
        layout.addWidget(self.stack)
        
        # 0. Single Viewer
        self.single_view = ZoomableGraphicsView(self)
        self.single_view.canvas_clicked.connect(self.canvas_clicked.emit)
        self.single_view.fullscreen_toggled.connect(self.fullscreen_toggled.emit)
        self.single_view.items_dropped.connect(self.items_dropped.emit)
        self.single_view.browse_requested.connect(self.browse_requested.emit)
        self.single_view.controls_visibility_changed.connect(self._on_controls_visibility_changed)
        self.stack.addWidget(self.single_view)
        
        # Expose video_item and pixmap_item for play/fit compatibility
        self.video_item = self.single_view.video_item
        self.pixmap_item = self.single_view.pixmap_item
        
        # 1. Grid Viewer
        self.grid_view = SorterGridView(self)
        self.grid_view.items_dropped.connect(self.items_dropped.emit)
        self.grid_view.itemSelectionChanged.connect(self.selection_changed.emit)
        self.grid_view.send_to_editor_requested.connect(self.send_to_editor_requested.emit)
        self.stack.addWidget(self.grid_view)
        
        # 2. List Viewer
        self.list_view = TableModeContainer(self)
        self.list_view.items_dropped.connect(self.items_dropped.emit)
        self.list_view.itemSelectionChanged.connect(self.selection_changed.emit)
        self.list_view.send_to_editor_requested.connect(self.send_to_editor_requested.emit)
        self.stack.addWidget(self.list_view)
        
        # 3. Empty Placeholder View
        self.empty_placeholder_widget = SorterPlaceholderWidget(self)
        self.empty_placeholder_widget.items_dropped.connect(self.items_dropped.emit)
        self.empty_placeholder_widget.browse_requested.connect(self.browse_requested.emit)
        self.empty_placeholder_widget.double_clicked.connect(self._on_placeholder_double_clicked)
        self.empty_placeholder_widget.middle_clicked.connect(self._on_placeholder_middle_clicked)
        self.stack.addWidget(self.empty_placeholder_widget)
        
        self.current_view_mode = 0
        self.loading_files = []
        
        # Floating Overlay Containers
        self.overlay_container_right = QWidget(self)
        self.overlay_container_right.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.overlay_container_right.setStyleSheet("background: transparent;")
        
        self.overlay_container_left = QWidget(self)
        self.overlay_container_left.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.overlay_container_left.setStyleSheet("background: transparent;")
        
        btn_style = """
            QPushButton { 
                background-color: rgba(0,0,0,0.5); 
                color: white; 
                font-size: 20px; 
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 4px;
                outline: none;
                padding: 0px;
            }
            QPushButton:hover { 
                background-color: rgba(0,0,0,0.8); 
                border: 1px solid rgba(255, 255, 255, 0.8);
            }
        """
        self.overlay_btn_style = btn_style
        self.user_hover_preview_state = False
        self.disable_hover_preview = True # По умолчанию в режиме одиночного просмотра быстрый просмотр отключен
        
        # Загрузка иконок режимов просмотра
        icons_dir_global = AppContext.find_resource_dir("icons")
        self.icons_dir = icons_dir_global
        self.icon_grid = QIcon(os.path.join(icons_dir_global, "view_grid.svg"))
        self.icon_list = QIcon(os.path.join(icons_dir_global, "view_list.svg"))
        self.icon_single = QIcon(os.path.join(icons_dir_global, "view_single.svg"))

        self.btn_view_mode = QPushButton(self.overlay_container_right)
        self.btn_view_mode.setFixedSize(40, 40)
        self.btn_view_mode.setIconSize(QSize(22, 22))
        self.btn_view_mode.setIcon(self.icon_grid)
        self.btn_view_mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_mode.setStyleSheet(btn_style)
        self.btn_view_mode.clicked.connect(self.toggle_mode)
        self.btn_view_mode.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_view_mode.setToolTip("Режим сетки" if AppContext.LANG == "RU" else "Grid Mode")
        self.btn_view_mode.move(0, 0)
        
        self.btn_fullscreen = QPushButton(self.overlay_container_left)
        self.btn_fullscreen.setFixedSize(40, 40)
        self.btn_fullscreen.setIconSize(QSize(22, 22))
        self.btn_fullscreen.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fullscreen.setStyleSheet(btn_style)
        self.btn_fullscreen.clicked.connect(self.fullscreen_toggled.emit)
        self.btn_fullscreen.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_fullscreen.setToolTip("Во весь экран" if AppContext.LANG == "RU" else "Fullscreen")
        self.btn_fullscreen.move(0, 0)
        
        self.btn_toggle_preview = QPushButton("👁", self.overlay_container_right)
        self.btn_toggle_preview.setFixedSize(40, 40)
        self.btn_toggle_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_preview.setCheckable(True)
        self.btn_toggle_preview.setStyleSheet(btn_style)
        self.btn_toggle_preview.clicked.connect(self.on_toggle_preview_clicked)
        self.btn_toggle_preview.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_toggle_preview.setToolTip("Отключить быстрый просмотр по наведению" if AppContext.LANG == "RU" else "Disable hover preview")
        self.btn_toggle_preview.move(0, 50)
        
        self.btn_quick_target = QPushButton(self.overlay_container_right)
        self.btn_quick_target.setFixedSize(40, 40)
        self.btn_quick_target.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_quick_target.setStyleSheet(btn_style)
        self.btn_quick_target.clicked.connect(self.on_quick_target_clicked)
        self.btn_quick_target.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_quick_target.move(0, 100)
        self.btn_quick_target.hide()
        
        # --- Pagination Buttons ---
        self.btn_page_prev = QPushButton("◀", self.overlay_container_right)
        self.btn_page_prev.setFixedSize(40, 40)
        self.btn_page_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_page_prev.setStyleSheet(btn_style)
        self.btn_page_prev.clicked.connect(lambda: self.change_page(-1))
        self.btn_page_prev.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_page_prev.setToolTip("Предыдущая страница" if AppContext.LANG == "RU" else "Previous Page")
        self.btn_page_prev.move(0, 200)
        
        self.lbl_page_text = QLabel("1/1", self.overlay_container_right)
        self.lbl_page_text.setFixedSize(40, 40)
        self.lbl_page_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_page_text.setStyleSheet("""
            background-color: rgba(30, 30, 30, 0.7);
            color: white;
            font-size: 11px;
            font-weight: bold;
            border-radius: 4px;
        """)
        self.lbl_page_text.setToolTip("Текущая страница" if AppContext.LANG == "RU" else "Current Page")
        self.lbl_page_text.move(0, 250)
        
        self.btn_page_next = QPushButton("▶", self.overlay_container_right)
        self.btn_page_next.setFixedSize(40, 40)
        self.btn_page_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_page_next.setStyleSheet(btn_style)
        self.btn_page_next.clicked.connect(lambda: self.change_page(1))
        self.btn_page_next.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_page_next.setToolTip("Следующая страница" if AppContext.LANG == "RU" else "Next Page")
        self.btn_page_next.move(0, 300)
        
        self.btn_page_refresh = QPushButton("↻", self.overlay_container_right)
        self.btn_page_refresh.setFixedSize(40, 40)
        self.btn_page_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_page_refresh.setStyleSheet(btn_style)
        self.btn_page_refresh.clicked.connect(lambda: self.refresh_pagination())
        self.btn_page_refresh.setToolTip("Обновить списки и переформировать группы" if AppContext.LANG == "RU" else "Refresh lists and regroup")
        self.btn_page_refresh.move(0, 350)
        
        self.current_page_idx = 0
        self.total_pages = 1
        
        self.btn_quick_target_icon = QLabel(self.btn_quick_target)
        self.btn_quick_target_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.btn_quick_target_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_quick_target_icon.setStyleSheet("background: transparent; border: none; padding: 0px;")
        self.btn_quick_target_icon.setPixmap(QIcon(os.path.join(self.icons_dir, "star-color.svg")).pixmap(26, 26))
        self.btn_quick_target_icon.setGeometry(7, 7, 26, 26)
        
        # Connect Thumbnail Loader singleton
        ThumbnailLoader.inst().thumbnail_ready.connect(self._on_thumbnail_ready)
        
        self.current_inbox_dir = ""
        self.placeholders = {}
        self.grid_items_map = {}
        self.list_items_map = {}
        self.file_rotations = {}
        self.popup_size = QSize(640, 520)

        # Batch loading setup
        self.loading_timer = QTimer(self)
        self.loading_timer.timeout.connect(self._load_next_batch)
        self.loading_files = []
        self.loading_dir = ""
        self.loading_current_idx = 0
        self.loading_target_select_idx = 0
        self.batch_size = 30
        self.is_loading_interrupted = False
        
        # Loading Overlay Widget
        self.loading_overlay = QFrame(self)
        self.loading_overlay.setObjectName("LoadingOverlay")
        self.loading_overlay.setStyleSheet("""
            #LoadingOverlay {
                background-color: rgba(15, 15, 15, 0.7);
                border: none;
            }
        """)
        
        # Контейнер для статуса по центру
        self.loading_content = QFrame(self.loading_overlay)
        self.loading_content.setObjectName("LoadingContent")
        self.loading_content.setFixedSize(400, 115)
        self.loading_content.setStyleSheet("""
            #LoadingContent {
                background-color: #2b2b2b;
                border: 2px solid #3b82f6;
                border-radius: 8px;
            }
            QLabel {
                color: #ffffff;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton#BtnStopLoading {
                background-color: #ef4444;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 13px;
            }
            QPushButton#BtnStopLoading:hover {
                background-color: #dc2626;
            }
            QPushButton#BtnStopLoading:pressed {
                background-color: #b91c1c;
            }
        """)
        
        overlay_layout = QVBoxLayout(self.loading_overlay)
        overlay_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        content_layout = QVBoxLayout(self.loading_content)
        content_layout.setContentsMargins(15, 12, 15, 12)
        content_layout.setSpacing(10)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_loading_status = QLabel("Загрузка файлов...", self.loading_content)
        self.lbl_loading_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_loading_status.setFixedWidth(370)
        content_layout.addWidget(self.lbl_loading_status)

        self.btn_stop_loading = QPushButton(AppContext.tr("btn_stop"), self.loading_content)
        self.btn_stop_loading.setObjectName("BtnStopLoading")
        self.btn_stop_loading.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stop_loading.clicked.connect(self.stop_loading_batch)
        content_layout.addWidget(self.btn_stop_loading, 0, Qt.AlignmentFlag.AlignCenter)
        
        overlay_layout.addWidget(self.loading_content)
        self.loading_overlay.hide()
        self.update_fullscreen_tooltip(False)

    def change_page(self, delta: int):
        main_app = self.get_main_app()
        if main_app and hasattr(main_app, 'change_page'):
            main_app.change_page(delta)

    def refresh_pagination(self):
        main_app = self.get_main_app()
        if main_app and hasattr(main_app, 'refresh_pagination'):
            main_app.refresh_pagination()

    def update_pagination_ui(self, current: int, total: int):
        self.current_page_idx = current
        self.total_pages = total
        self.lbl_page_text.setText(f"{current + 1}/{total}")
        
        # Только для режима сетки (1) и списка (2)
        is_single_view = getattr(self, 'current_view_mode', 0) == 0
        show_pagination = not is_single_view
        
        self.btn_page_prev.setVisible(show_pagination)
        self.btn_page_prev.setEnabled(total > 1)
        self.lbl_page_text.setVisible(show_pagination)
        self.btn_page_next.setVisible(show_pagination)
        self.btn_page_next.setEnabled(total > 1)
        
        # Кнопка обновления видна всегда в режимах сетки/списка
        self.btn_page_refresh.setVisible(show_pagination)
        
        self.resizeEvent(None)

    def get_grid_columns_count(self):
        grid_w = self.grid_view.gridSize().width()
        if grid_w <= 0:
            grid_w = 120
        viewport_w = self.grid_view.viewport().width()
        if viewport_w <= 0:
            viewport_w = self.grid_view.width()
        if viewport_w <= 0:
            viewport_w = 800
        return max(1, viewport_w // grid_w)

    def get_current_selected_index(self):
        """Returns the index of the currently selected file in loading_files list."""
        main_app = self.get_main_app()
        if main_app and hasattr(main_app, 'current_index'):
            return main_app.current_index
            
        curr_mode = self.stack.currentIndex()
        view = self.grid_view if curr_mode == 1 else self.list_view
        selected = view.selectedItems()
        if selected:
            p = selected[0].data(Qt.ItemDataRole.UserRole)
            if p and hasattr(self, 'loading_files') and self.loading_files and hasattr(self, 'current_inbox_dir') and self.current_inbox_dir is not None:
                rel = safe_relpath(p, self.current_inbox_dir)
                norm_rel = os.path.normpath(rel)
                for idx, f in enumerate(self.loading_files):
                    if os.path.normpath(f) == norm_rel:
                        return idx
        return self.loading_target_select_idx

    def get_grid_item(self, idx):
        if not self.loading_files or idx >= len(self.loading_files):
            return None
        rel_path = self.loading_files[idx]
        full_path = os.path.join(self.current_inbox_dir, rel_path)
        return self.grid_items_map.get(os.path.normpath(strip_long_path_prefix(full_path)))

    def get_list_item(self, idx):
        if not self.loading_files or idx >= len(self.loading_files):
            return None
        rel_path = self.loading_files[idx]
        full_path = os.path.join(self.current_inbox_dir, rel_path)
        return self.list_items_map.get(os.path.normpath(strip_long_path_prefix(full_path)))

    def _center_loading_overlay(self):
        self.loading_overlay.setGeometry(self.rect())
        self.loading_overlay.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        if not self.loading_overlay.isHidden():
            self._center_loading_overlay()

    def resizeEvent(self, event):
        if event:
            super().resizeEvent(event)
        
        # Position floating controls
        m = 10
        m_right = 20  # Отступ справа скорректирован до 20px, чтобы кнопки были вплотную к скроллбару, но не перекрывали его
        w = 40
        spacing = 10
        
        # Right container (view mode, hover preview, quick target toggles, and 4 pagination buttons)
        # We need to calculate height based on visible buttons. 
        # For now, there are 8 buttons (indices 0 to 350 + 40 height) -> 400px
        container_right_w = w
        container_right_h = 400
        self.overlay_container_right.setGeometry(self.width() - container_right_w - m_right, m, container_right_w, container_right_h)
        self.overlay_container_right.raise_()
        
        # Left container (fullscreen toggle)
        # Width: 40px, Height: 40px
        container_left_w = w
        container_left_h = w
        self.overlay_container_left.setGeometry(m, m, container_left_w, container_left_h)
        
        is_fs = getattr(self.single_view, 'is_fullscreen_mode', False)
        if not is_fs:
            self.overlay_container_right.show()
            if self.current_view_mode == 0:
                self.overlay_container_left.show()
                self.overlay_container_left.raise_()
            else:
                self.overlay_container_left.hide()
        
        if not self.loading_overlay.isHidden():
            self._center_loading_overlay()

        # Если включена группировка и изменилось количество колонок в Grid View, перестраиваем список тихо
        main_app = self.get_main_app()
        group_enabled = main_app.config.get("group_by_sort", False) if main_app and hasattr(main_app, 'config') else False
        if group_enabled and hasattr(self, 'current_inbox_dir') and self.current_inbox_dir is not None and self.loading_files:
            cols = self.get_grid_columns_count()
            if not hasattr(self, '_last_cols_count') or self._last_cols_count != cols:
                self._last_cols_count = cols
                self.loading_target_select_idx = self.get_current_selected_index()
                # Запускаем тихое обновление, чтобы пересчитать пустые заполнители
                self.sync_files_queue(self.current_inbox_dir, self.loading_files, self.loading_target_select_idx, silent=True)



    def toggle_mode(self):
        curr = self.current_view_mode
        if curr == 1:       # Grid (плитка) -> List (список)
            next_mode = 2
        elif curr == 2:     # List (список) -> Single (одиночный)
            next_mode = 0
        else:               # Single (одиночный) -> Grid (плитка)
            next_mode = 1
        self.set_mode(next_mode)

    def apply_hover_preview_state(self):
        """Применяет визуальные стили кнопки быстрого просмотра в зависимости от disable_hover_preview."""
        state = self.disable_hover_preview
        if state:
            self.btn_toggle_preview.setChecked(True)
            self.btn_toggle_preview.setStyleSheet("""
                QPushButton { 
                    background-color: rgba(239, 68, 68, 0.6); 
                    color: white; 
                    font-size: 20px; 
                    border: 1px solid #ef4444;
                    border-radius: 4px;
                    outline: none;
                    padding: 0px;
                }
                QPushButton:hover { 
                    background-color: rgba(220, 38, 38, 0.8); 
                    border: 1px solid white;
                }
            """)
            self.btn_toggle_preview.setToolTip(
                "Включить быстрый просмотр по наведению (F1)"
                if AppContext.LANG == "RU" else
                "Enable hover preview (F1)"
            )
            # Принудительно закрываем попапы у списков
            for view in [self.grid_view, self.list_view]:
                if hasattr(view, 'large_preview_popup') and view.large_preview_popup:
                    popup = view.large_preview_popup
                    view.large_preview_popup = None
                    try:
                        popup.cleanup()
                        popup.close()
                    except Exception:
                        pass
                view._stop_hover_playback(force=True)
        else:
            self.btn_toggle_preview.setChecked(False)
            self.btn_toggle_preview.setStyleSheet(self.overlay_btn_style)
            self.btn_toggle_preview.setToolTip(
                "Отключить быстрый просмотр по наведению (F1)"
                if AppContext.LANG == "RU" else
                "Disable hover preview (F1)"
            )

    def toggle_hover_preview(self) -> None:
        """
        Публичный метод переключения быстрого просмотра по наведению.
        Вызывается как кнопкой 👁, так и горячей клавишей F1.
        """
        # Переключаем предпочтение пользователя
        self.user_hover_preview_state = not self.user_hover_preview_state
        
        # В режиме одиночного просмотра (currentIndex == 0 или 3) быстрый просмотр принудительно выключен
        if self.current_view_mode != 0:
            self.disable_hover_preview = self.user_hover_preview_state
        else:
            self.disable_hover_preview = True
            
        self.apply_hover_preview_state()

    def _on_controls_visibility_changed(self, visible: bool):
        is_fs = getattr(self.single_view, 'is_fullscreen_mode', False)
        if not is_fs: return
        if visible:
            self.overlay_container_right.show()
            if self.current_view_mode == 0:
                self.overlay_container_left.show()
        else:
            self.overlay_container_right.hide()
            self.overlay_container_left.hide()

    def on_toggle_preview_clicked(self, checked: bool) -> None:
        """Обработчик клика кнопки 👁 — делегирует в toggle_hover_preview()."""
        # Синхронизируем состояние флага, toggle_hover_preview сам сделает flip предпочтения
        self.toggle_hover_preview()

    def update_ui_text(self):
        if hasattr(self, 'list_view') and hasattr(self.list_view, 'update_ui_text'):
            self.list_view.update_ui_text()
        self.set_mode(self.current_view_mode)
        if hasattr(self, 'btn_fullscreen'):
            self.btn_fullscreen.setToolTip("Во весь экран" if AppContext.is_ru() else "Fullscreen")
        if hasattr(self, 'btn_page_prev'):
            self.btn_page_prev.setToolTip("Предыдущая страница" if AppContext.is_ru() else "Previous Page")
        if hasattr(self, 'lbl_page_text'):
            self.lbl_page_text.setToolTip("Текущая страница" if AppContext.is_ru() else "Current Page")
        if hasattr(self, 'btn_page_next'):
            self.btn_page_next.setToolTip("Следующая страница" if AppContext.is_ru() else "Next Page")
        if hasattr(self, 'btn_page_refresh'):
            self.btn_page_refresh.setToolTip("Обновить списки и переформировать группы" if AppContext.is_ru() else "Refresh lists and regroup")

    def set_mode(self, mode_idx):
        self.grid_view._stop_hover_playback(force=True)
        self.list_view._stop_hover_playback(force=True)
        
        # Сохраняем/восстанавливаем состояние быстрого просмотра при смене режимов
        if mode_idx == 0:
            self.disable_hover_preview = True
        else:
            self.disable_hover_preview = getattr(self, 'user_hover_preview_state', False)
        self.apply_hover_preview_state()
        
        self.current_view_mode = mode_idx
        
        # If files queue is empty, keep showing empty placeholder widget across all modes
        if not getattr(self, 'loading_files', None):
            self.stack.setCurrentIndex(3)
        else:
            self.stack.setCurrentIndex(mode_idx)
            
        self.mode_changed.emit(mode_idx)
        
        # Update mode button icon and tooltips
        if mode_idx == 0:
            self.btn_view_mode.setText("")
            self.btn_view_mode.setIcon(self.icon_grid)
            self.btn_view_mode.setToolTip("Режим сетки" if AppContext.LANG == "RU" else "Grid Mode")
            self.btn_toggle_preview.hide()
            self.btn_page_prev.hide()
            self.lbl_page_text.hide()
            self.btn_page_next.hide()
            self.btn_page_refresh.hide()
        elif mode_idx == 1:
            self.btn_view_mode.setText("")
            self.btn_view_mode.setIcon(self.icon_list)
            self.btn_view_mode.setToolTip("Режим списка" if AppContext.LANG == "RU" else "List Mode")
            self.btn_toggle_preview.show()
            self.btn_page_prev.show()
            self.lbl_page_text.show()
            self.btn_page_next.show()
            self.btn_page_refresh.show()
        else:
            self.btn_view_mode.setText("")
            self.btn_view_mode.setIcon(self.icon_single)
            self.btn_view_mode.setToolTip("Одиночный просмотр" if AppContext.LANG == "RU" else "Single View")
            self.btn_toggle_preview.hide()
            self.btn_page_prev.show()
            self.lbl_page_text.show()
            self.btn_page_next.show()
            self.btn_page_refresh.show()
            
        self.resizeEvent(None)
        self.update_quick_target_visibility()
        self.update_quick_target_tooltip()
        # Гарантируем что overlays всегда поверх текущего виджета стека
        self.overlay_container_right.raise_()
        if mode_idx == 0:
            self.overlay_container_left.raise_()
        
        # Synchronize active item selection when returning to modes
        if mode_idx in [1, 2]:
            self.grid_view.setFocus()
            self.list_view.setFocus()
            
    # Proxy methods for Single mode compatibility
    def set_image(self, pixmap):
        if self.stack.currentIndex() == 3:
            self.stack.setCurrentIndex(0)
        self.single_view.set_image(pixmap)
        main_app = self.get_main_app()
        if main_app and getattr(main_app, 'current_file_path', None):
            norm_path = os.path.normpath(main_app.current_file_path)
            angle = self.file_rotations.get(norm_path, 0)
            if angle != 0:
                if hasattr(self.single_view, 'set_absolute_rotation'):
                    self.single_view.set_absolute_rotation(angle)
                else:
                    self.single_view.rotate(angle)

    def set_animated(self, filepath):
        if self.stack.currentIndex() == 3:
            self.stack.setCurrentIndex(0)
        self.single_view.set_animated(filepath)
        norm_path = os.path.normpath(strip_long_path_prefix(filepath))
        angle = self.file_rotations.get(norm_path, 0)
        if angle != 0:
            if hasattr(self.single_view, 'set_absolute_rotation'):
                self.single_view.set_absolute_rotation(angle)
            else:
                self.single_view.rotate(angle)

    def update_item_preview(self, filepath):
        norm_path = os.path.normpath(strip_long_path_prefix(filepath))
        item_grid = self.grid_items_map.get(norm_path)
        if item_grid:
            widget = self.grid_view.itemWidget(item_grid)
            if widget and hasattr(widget, 'update_rotation'):
                widget.update_rotation()
        item_list = self.list_items_map.get(norm_path)
        if item_list:
            widget = self.list_view.itemWidget(item_list)
            if widget and hasattr(widget, 'update_rotation'):
                widget.update_rotation()

    def set_video_mode(self): 
        if self.stack.currentIndex() == 3:
            self.stack.setCurrentIndex(0)
        self.single_view.set_video_mode()
        
    def set_audio_mode(self, text): 
        if self.stack.currentIndex() == 3:
            self.stack.setCurrentIndex(0)
        self.single_view.set_audio_mode(text)
    
    def show_empty_state(self, message):
        main_app = self.get_main_app()
        show_btn = True
        if main_app and getattr(main_app, 'UNSORT_DIR', None) and getattr(main_app, 'files_queue', None):
            show_btn = False
            
        self.empty_placeholder_widget.set_message(message, show_btn)
        self.stack.setCurrentIndex(3)
        
    def change_rotation(self, angle): self.single_view.change_rotation(angle)
    def set_background_color(self, color): self.single_view.set_background_color(color)
    def set_fullscreen_mode(self, enabled, controls_widget=None):
        self.single_view.set_fullscreen_mode(enabled, controls_widget)
        if not enabled:
            self.overlay_container_right.show()
            if self.current_view_mode == 0:
                self.overlay_container_left.show()
            else:
                self.overlay_container_left.hide()
        self.update_fullscreen_tooltip(enabled)

    def update_fullscreen_tooltip(self, is_fullscreen: bool):
        main_app = self.get_main_app()
        if is_fullscreen:
            self.btn_fullscreen.setIcon(QIcon(os.path.join(self.icons_dir, "square-arrow-out-down-left.svg")))
            key_str = "Escape"
            if main_app and hasattr(main_app, '_hotkey_registry'):
                key = main_app._hotkey_registry.get_effective_key("exit_fullscreen")
                if key:
                    key_str = key.replace("Return", "Enter")
            
            tooltip_text = (
                f"Выйти из полноэкранного режима ({key_str})"
                if AppContext.LANG == "RU" else
                f"Exit fullscreen ({key_str})"
            )
        else:
            self.btn_fullscreen.setIcon(QIcon(os.path.join(self.icons_dir, "scan.svg")))
            key_str = "Alt+Enter"
            if main_app and hasattr(main_app, '_hotkey_registry'):
                key = main_app._hotkey_registry.get_effective_key("toggle_fullscreen_solo")
                if key:
                    key_str = key.replace("Return", "Enter")
            
            tooltip_text = (
                f"Во весь экран ({key_str})"
                if AppContext.LANG == "RU" else
                f"Fullscreen ({key_str})"
            )
        self.btn_fullscreen.setToolTip(tooltip_text)

    def update_quick_target_visibility(self):
        """Управляет видимостью кнопки Быстрой цели на холсте."""
        main_app = self.get_main_app()
        has_target = main_app and getattr(main_app, 'quick_target_path', None) is not None
        in_valid_mode = self.current_view_mode in [0, 1, 2, 3]
        if has_target and in_valid_mode:
            self.btn_quick_target.show()
        else:
            self.btn_quick_target.hide()

    def update_quick_target_tooltip(self):
        """Обновляет текст подсказки кнопки Быстрой цели с учетом пути и хоткея."""
        main_app = self.get_main_app()
        target_path = getattr(main_app, 'quick_target_path', None)
        if target_path:
            folder_name = os.path.basename(target_path)
            key_str = self.get_fast_move_key_string()
            
            tooltip_text = (
                f"Быстрое перемещение в «{folder_name}» ({key_str})"
                if AppContext.LANG == "RU" else
                f"Fast move to '{folder_name}' ({key_str})"
            )
            self.btn_quick_target.setToolTip(tooltip_text)

    def get_fast_move_key_string(self):
        """Считывает назначенную горячую клавишу для быстрого перемещения."""
        main_app = self.get_main_app()
        if main_app and hasattr(main_app, '_hotkey_registry'):
            key = main_app._hotkey_registry.get_effective_key("fast_move_to_target")
            if key:
                return key
        return "Space"

    def on_quick_target_clicked(self):
        """Обработчик нажатия на кнопку Быстрой цели на холсте."""
        main_app = self.get_main_app()
        if main_app and hasattr(main_app, 'fast_move_to_target'):
            main_app.fast_move_to_target()
            
    def reset_view(self):
        self.single_view.reset_view()

    def clear_scene_content(self):
        self.single_view.clear_scene_content()
        self.grid_view._stop_hover_playback(force=True)
        self.list_view._stop_hover_playback(force=True)

    # SYNC FILES QUEUE WITH GRID/LIST
    def sync_files_queue(self, unsort_dir, files, current_index, silent=False):
        """Build grid and list widget items from incoming files queue."""
        # Stop loading timer if already running
        self.loading_timer.stop()
        
        # Stop hover playback FIRST to prevent crashes
        self.grid_view._stop_hover_playback(force=True)
        self.list_view._stop_hover_playback(force=True)
        
        self.current_inbox_dir = unsort_dir
        
        # Explicitly delete old item widgets to avoid memory leaks in Qt
        for i in range(self.grid_view.count()):
            item = self.grid_view.item(i)
            if item:
                w = self.grid_view.itemWidget(item)
                if w:
                    self.grid_view.removeItemWidget(item)
                    w.deleteLater()
        pass # Table mode clears itself

        self.grid_view.clear()
        self.list_view.clear()
        
        # Clear thumbnail and icon caches when loading a new folder to free RAM
        if getattr(self, 'current_inbox_dir', None) != unsort_dir:
            ThumbnailLoader.inst().clear_cache()
            FileIconManager.inst().clear_cache()
        
        self.grid_items_map = {}
        self.list_items_map = {}
        self.loading_render_items = []
        self.is_loading_interrupted = False
        
        if not files:
            self.loading_overlay.hide()
            self.loading_files = []
            if not unsort_dir:
                self.show_empty_state("Входящие не выбраны\n\nПеретащите папку или группу файлов для анализа на этот холст\nили выберите их через кнопку ниже" if AppContext.LANG == "RU" else "Inbox folder not selected\n\nDrag a folder or a group of files here for analysis\nor choose them using the button below")
            else:
                self.show_empty_state("Папка пуста\n\nВ выбранной папке нет поддерживаемых медиафайлов" if AppContext.LANG == "RU" else "Folder is empty\n\nNo supported media files found in selected folder")
            return
            
        self.loading_files = files
        if hasattr(self.list_view, 'populate'):
            file_stats = []
            for rel_path in files:
                fp = os.path.join(unsort_dir, rel_path)
                try:
                    st = os.stat(fp)
                    file_stats.append((fp, st.st_mtime, st.st_size))
                except:
                    file_stats.append((fp, 0, 0))
            self.list_view.populate(file_stats)
        if self.stack.currentIndex() == 3:
            self.stack.setCurrentIndex(self.current_view_mode)
            
        self.loading_dir = unsort_dir
        self.loading_current_idx = 0
        self.loading_target_select_idx = current_index
        
        # Если мы в одиночном режиме, нам не нужно генерировать плитки и списки для тысяч файлов
        if getattr(self, 'current_view_mode', 0) in (0, 2):
            self.loading_overlay.hide()
            self.selection_changed.emit()
            main_window = self.window()
            if main_window and hasattr(main_window, 'show_current_file'):
                main_window.show_current_file()
            return
            
        # Сбор элементов для рендеринга с учетом группировки
        main_app = self.get_main_app()
        group_enabled = main_app.config.get("group_by_sort", False) if main_app and hasattr(main_app, 'config') else False
        
        if group_enabled:
            sort_type = main_app.config.get("sort_type", "name_asc") if main_app and hasattr(main_app, 'config') else "name_asc"
            
            def get_group_title(rel_path):
                full_path = os.path.join(unsort_dir, rel_path)
                size, mtime, ctime = 0, 0.0, 0.0
                try:
                    stat = os.stat(full_path)
                    size = stat.st_size
                    mtime = stat.st_mtime
                    ctime = stat.st_ctime
                except Exception:
                    pass
                    
                is_ru = (AppContext.LANG == "RU")
                ext = os.path.splitext(rel_path)[1].lower()
                
                if sort_type in ["name_asc", "name_desc"]:
                    name = os.path.basename(rel_path)
                    if name:
                        first_char = name[0].upper()
                        if first_char.isdigit():
                            return "0-9"
                        elif not first_char.isalnum():
                            return "#"
                        return first_char
                    return "#"
                    
                elif sort_type == "type_asc":
                    video_exts = VIDEO_EXTS
                    audio_exts = AUDIO_EXTS
                    image_exts = IMAGE_EXTS
                    
                    clean_ext = ext.lstrip('.')
                    if not clean_ext:
                        clean_ext = "no ext"
                        
                    if ext in video_exts:
                        cat_name = "Видео" if is_ru else "Video"
                    elif ext in image_exts:
                        cat_name = "Изображения" if is_ru else "Images"
                    elif ext in audio_exts:
                        cat_name = "Аудио" if is_ru else "Audio"
                    else:
                        cat_name = "Другие файлы" if is_ru else "Other files"
                        
                    return f"{cat_name} ({clean_ext})"
                        
                elif sort_type in ["size_desc", "size_asc"]:
                    if size >= 1024*1024*1024:
                        return "Гиганты (> 1 GB)" if is_ru else "Giants (> 1 GB)"
                    elif size >= 1024*1024*100:
                        return "Крупные (100 MB - 1 GB)" if is_ru else "Large (100 MB - 1 GB)"
                    elif size >= 1024*1024*10:
                        return "Средние (10 MB - 100 MB)" if is_ru else "Medium (10 MB - 100 MB)"
                    else:
                        return "Мелкие (< 10 MB)" if is_ru else "Small (< 10 MB)"
                        
                elif sort_type in ["mtime_desc", "mtime_asc", "ctime_desc", "ctime_asc"]:
                    t = mtime if "mtime" in sort_type else ctime
                    from datetime import datetime
                    try:
                        return datetime.fromtimestamp(t).strftime("%d.%m.%Y")
                    except Exception:
                        return "Неизвестная дата" if is_ru else "Unknown date"
                return "Группа" if is_ru else "Group"

            cols = self.get_grid_columns_count()
            last_group = None
            rendered_count = 0
            
            for idx, rel_path in enumerate(files):
                g_title = get_group_title(rel_path)
                if g_title != last_group:
                    # Заполняем пустые плитки в Grid для переноса строки (нового абзаца)
                    if rendered_count > 0:
                        pos = rendered_count % cols
                        if pos != 0:
                            num_placeholders = cols - pos
                            for _ in range(num_placeholders):
                                self.loading_render_items.append(("grid_placeholder",))
                                rendered_count += 1
                                
                    self.loading_render_items.append(("separator", g_title))
                    # Обратите внимание: separator в grid_view не добавляется,
                    # поэтому rendered_count НЕ увеличиваем, чтобы файлы новой группы
                    # начались точно с первой колонки новой строки.
                    last_group = g_title
                    
                self.loading_render_items.append(("file", rel_path, idx))
                rendered_count += 1
        else:
            for idx, rel_path in enumerate(files):
                self.loading_render_items.append(("file", rel_path, idx))
        
        # Show loading overlay (only if not silent)
        if not silent:
            is_ru = (AppContext.LANG == "RU")
            total = len(files)
            w_val = len(str(total))
            self.lbl_loading_status.setText(f"Загрузка файлов... {0:>{w_val}} / {total}" if is_ru else f"Loading files... {0:>{w_val}} / {total}")
            self._center_loading_overlay()
            self.loading_overlay.show()
            self.loading_overlay.raise_()
            QApplication.processEvents()
        else:
            self.loading_overlay.hide()
        
        # Start batch loading
        self.loading_timer.start(0)

    def stop_loading_batch(self):
        logging.info("Загрузка файлов в интерфейс остановлена пользователем.")
        self.is_loading_interrupted = True
        self.loading_timer.stop()
        self.loading_render_items = []
        self.loading_overlay.hide()
        self.grid_view.doItemsLayout()
        self.list_view.doItemsLayout()

    def _load_next_batch(self):
        if not self.loading_render_items:
            self.loading_timer.stop()
            self.loading_overlay.hide()
            return
            
        total = len(self.loading_render_items)
        start = self.loading_current_idx
        end = min(start + self.batch_size, total)
        
        is_ru = (AppContext.LANG == "RU")
        
        # Disable updates during batch insertion to prevent flickering
        self.grid_view.setUpdatesEnabled(False)
        self.list_view.setUpdatesEnabled(False)
        
        try:
            for idx in range(start, end):
                item_data = self.loading_render_items[idx]
                if item_data[0] == "grid_placeholder":
                    # Пустая невыделяемая плитка для переноса строк в Grid
                    item_grid = QListWidgetItem()
                    item_grid.setFlags(item_grid.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                    widget_grid = QWidget()
                    item_grid.setSizeHint(QSize(self.grid_view.gridSize().width(), self.grid_view.gridSize().height()))
                    self.grid_view.addItem(item_grid)
                    self.grid_view.setItemWidget(item_grid, widget_grid)
                elif item_data[0] == "separator":
                    title = item_data[1]
                    
                    # List Separator
                    if hasattr(self.list_view, 'addItem'):
                        item_list = QListWidgetItem()
                        item_list.setFlags(item_list.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                        widget_list = SorterListGroupSeparatorWidget(title)
                        item_list.setSizeHint(QSize(self.list_view.width() - 30, 30))
                        self.list_view.addItem(item_list)
                        self.list_view.setItemWidget(item_list, widget_list)
                elif item_data[0] == "file":
                    rel_path = item_data[1]
                    orig_idx = item_data[2]
                    full_path = os.path.join(self.loading_dir, rel_path)
                    
                    # --- 1. Grid Item ---
                    item_grid = QListWidgetItem()
                    item_grid.setData(Qt.ItemDataRole.UserRole, full_path)
                    
                    widget_grid = SorterGridItemWidget(full_path, self.grid_view.tile_size)
                    ph = self._get_placeholder_pixmap(full_path)
                    widget_grid.set_placeholder(ph)
                    
                    item_grid.setSizeHint(widget_grid.sizeHint())
                    self.grid_view.addItem(item_grid)
                    self.grid_view.setItemWidget(item_grid, widget_grid)
                    
                    self.grid_items_map[os.path.normpath(strip_long_path_prefix(full_path))] = item_grid
                    
                    # --- 2. List Item ---
                    if not hasattr(self.list_view, 'table'):
                        item_list = QListWidgetItem()
                        item_list.setData(Qt.ItemDataRole.UserRole, full_path)

                        widget_list = SorterListItemWidget(full_path, self.list_view.icon_size)
                        widget_list.set_placeholder(ph)

                        item_list.setSizeHint(widget_list.sizeHint())
                        self.list_view.addItem(item_list)
                        self.list_view.setItemWidget(item_list, widget_list)

                        self.list_items_map[os.path.normpath(strip_long_path_prefix(full_path))] = item_list
                    
                    # Request async thumbnail generation
                    ext = os.path.splitext(rel_path)[1].lower()
                    if ext in set(VIDEO_EXTS) | set(IMAGE_EXTS):
                        ThumbnailLoader.inst().get_thumbnail(full_path, QSize(256, 256))
        finally:
            self.grid_view.setUpdatesEnabled(True)
            self.list_view.setUpdatesEnabled(True)
            
        self.loading_current_idx = end
        
        # Update progress overlay (show loaded files count based on files list)
        loaded_files_count = sum(1 for item in self.loading_render_items[:end] if item[0] == "file")
        total_files_count = len(self.loading_files)
        w_val = len(str(total_files_count))
        self.lbl_loading_status.setText(
            f"Загрузка файлов... {loaded_files_count:>{w_val}} / {total_files_count}" if is_ru else f"Loading files... {loaded_files_count:>{w_val}} / {total_files_count}"
        )
        self.loading_overlay.raise_()
        
        if end >= total:
            self.loading_timer.stop()
            self.loading_overlay.hide()
            self.is_loading_interrupted = False
            
            # Set selection on current index
            if self.loading_target_select_idx < len(self.loading_files):
                grid_item = self.get_grid_item(self.loading_target_select_idx)
                list_item = self.get_list_item(self.loading_target_select_idx)
                if grid_item: grid_item.setSelected(True)
                if list_item: list_item.setSelected(True)
                
            # Ensure all widgets have correct set_selected state initially
            for i in range(self.grid_view.count()):
                item = self.grid_view.item(i)
                if not item: continue
                p = item.data(Qt.ItemDataRole.UserRole)
                if not p: continue
                widget = self.grid_view.itemWidget(item)
                if widget and hasattr(widget, 'set_selected'):
                    widget.set_selected(item.isSelected())
                    
            self.selection_changed.emit()
            
            if getattr(self, 'current_view_mode', -1) == 0:
                main_window = self.window()
                if main_window and hasattr(main_window, 'show_current_file'):
                    main_window.show_current_file()
            
            # Schedule hover check after load finishes
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(150, self.grid_view.check_hover_under_mouse)
            QTimer.singleShot(150, self.list_view.check_hover_under_mouse)

    def get_selected_files(self):
        """Returns list of absolute filepaths of selected items."""
        curr_mode = self.current_view_mode
        selected_paths = []
        if curr_mode == 0:
            pass
        elif curr_mode == 1:
            for item in self.grid_view.selectedItems():
                p = item.data(Qt.ItemDataRole.UserRole)
                if p: selected_paths.append(p)
        elif curr_mode == 2:
            if hasattr(self.list_view, 'table'):
                checked = self.list_view.table.get_checked_files()
                if checked:
                    selected_paths.extend(checked)
                else:
                    row = self.list_view.table.currentRow()
                    if row >= 0:
                        item = self.list_view.table.item(row, 0)
                        if item:
                            p = item.data(Qt.ItemDataRole.UserRole)
                            if p: selected_paths.append(p)
            else:
                for item in self.list_view.selectedItems():
                    p = item.data(Qt.ItemDataRole.UserRole)
                    if p: selected_paths.append(p)
        return selected_paths

    def _get_placeholder_pixmap(self, filepath):
        return FileIconManager.inst().get_icon_pixmap(filepath, QSize(128, 128))

    def _on_thumbnail_ready(self, filepath, image):
        # Update corresponding item icon in Grid and List views using O(1) map lookups
        norm_path = os.path.normpath(strip_long_path_prefix(filepath))
        
        # Sync Grid
        item_grid = getattr(self, 'grid_items_map', {}).get(norm_path)
        if item_grid:
            widget = self.grid_view.itemWidget(item_grid)
            if widget and hasattr(widget, 'set_preview_image'):
                widget.set_preview_image(image)
                
        # Sync List
        item_list = getattr(self, 'list_items_map', {}).get(norm_path)
        if item_list:
            widget = self.list_view.itemWidget(item_list)
            if widget and hasattr(widget, 'set_preview_image'):
                widget.set_preview_image(image)

    def refresh_video_thumbnails(self) -> None:
        """Перегенерирует превью для всех видеофайлов в текущем каталоге."""
        logging.info("Начато обновление видео-превью после скачивания FFmpeg.")
        video_extensions = VIDEO_EXTS
        
        # Собираем все видеофайлы из текущего кэша отображения
        paths_to_refresh = []
        for path in self.grid_items_map.keys():
            ext = os.path.splitext(path)[1].lower()
            if ext in video_extensions:
                paths_to_refresh.append(path)
                
        if not paths_to_refresh:
            logging.debug("Видеофайлы для обновления превью не найдены.")
            return
            
        logging.info(f"Найдено {len(paths_to_refresh)} видеофайлов для обновления превью.")
        loader = ThumbnailLoader.inst()
        for path in paths_to_refresh:
            # Сбрасываем кэш и текущие активные запросы, чтобы разрешить генерацию заново
            loader.cache.pop(path, None)
            loader.active_requests.discard(path)
            # Запрашиваем генерацию
            loader.get_thumbnail(path, QSize(256, 256))

    def remove_files_from_view(self, paths):
        """Мгновенно скрывает указанные файлы из сетки и списка без перерисовки всей очереди."""
        self.grid_view._stop_hover_playback(force=True)
        self.list_view._stop_hover_playback(force=True)
        
        # Запоминаем текущую позицию прокрутки
        grid_scroll = self.grid_view.verticalScrollBar().value()
        list_scroll = self.list_view.verticalScrollBar().value()
        
        self.grid_view.setUpdatesEnabled(False)
        self.list_view.setUpdatesEnabled(False)
        
        # Блокируем сигналы, чтобы не сбить main_app.current_index при удалении элементов
        grid_blocked = self.grid_view.blockSignals(True)
        list_blocked = self.list_view.blockSignals(True)
        try:
            for path in paths:
                from utils_io import strip_long_path_prefix
                norm_path = os.path.normpath(strip_long_path_prefix(path))
                
                item_grid = self.grid_items_map.get(norm_path)
                if item_grid:
                    item_grid.setHidden(True)
                    
                item_list = self.list_items_map.get(norm_path)
                if item_list:
                    item_list.setHidden(True)
                    
            if hasattr(self.list_view, 'table'):
                self.list_view.table.remove_files(paths)
        finally:
            self.grid_view.blockSignals(grid_blocked)
            self.list_view.blockSignals(list_blocked)
            self.grid_view.setUpdatesEnabled(True)
            self.list_view.setUpdatesEnabled(True)
            
        self.grid_view.doItemsLayout()
        self.list_view.doItemsLayout()
        
        # Восстанавливаем позицию прокрутки
        self.grid_view.verticalScrollBar().setValue(grid_scroll)
        self.list_view.verticalScrollBar().setValue(list_scroll)
        
        # Schedule hover check after files are removed
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(150, self.grid_view.check_hover_under_mouse)
        QTimer.singleShot(150, self.list_view.check_hover_under_mouse)

    def insert_files_into_view(self, files_to_insert):
        """
        Точечно вставляет новые файлы в сетку и список.
        files_to_insert: список кортежей (full_path, index_in_queue)
        """
        self.grid_view._stop_hover_playback(force=True)
        self.list_view._stop_hover_playback(force=True)
        
        self.grid_view.setUpdatesEnabled(False)
        self.list_view.setUpdatesEnabled(False)
        try:
            for full_path, idx in files_to_insert:
                from utils_io import strip_long_path_prefix
                norm_path = os.path.normpath(strip_long_path_prefix(full_path))
                
                # Проверяем, есть ли элемент уже в памяти (скрытый после переноса)
                item_grid = self.grid_items_map.get(norm_path)
                if item_grid:
                    item_grid.setHidden(False)
                else:
                    ph = self._get_placeholder_pixmap(full_path)
                    
                    # --- 1. Вставка в Grid View ---
                    item_grid = QListWidgetItem()
                    item_grid.setData(Qt.ItemDataRole.UserRole, full_path)
                    widget_grid = SorterGridItemWidget(full_path, self.grid_view.tile_size)
                    widget_grid.set_placeholder(ph)
                    item_grid.setSizeHint(widget_grid.sizeHint())
                    
                    self.grid_view.insertItem(idx, item_grid)
                    self.grid_view.setItemWidget(item_grid, widget_grid)
                    self.grid_items_map[norm_path] = item_grid
                    
                item_list = self.list_items_map.get(norm_path)
                if item_list:
                    item_list.setHidden(False)
                else:
                    if 'ph' not in locals(): ph = self._get_placeholder_pixmap(full_path)
                    # --- 2. Вставка в List/Table View ---
                    if hasattr(self.list_view, 'table'):
                        self.list_view.insert_file(idx, full_path)
                    else:
                        item_list = QListWidgetItem()
                        item_list.setData(Qt.ItemDataRole.UserRole, full_path)
                        widget_list = SorterListItemWidget(full_path, self.list_view.icon_size)
                        widget_list.set_placeholder(ph)
                        item_list.setSizeHint(widget_list.sizeHint())

                        self.list_view.insertItem(idx, item_list)
                        self.list_view.setItemWidget(item_list, widget_list)
                        self.list_items_map[norm_path] = item_list
                    
                    # Запуск асинхронной загрузки превью только для новых элементов
                    from utils_extensions import VIDEO_EXTS, AUDIO_EXTS, IMAGE_EXTS
                    ext = os.path.splitext(full_path)[1].lower()
                    if ext in VIDEO_EXTS or ext in AUDIO_EXTS or ext in IMAGE_EXTS:
                        from modules.sorter.thumbnail_loader import ThumbnailLoader
                        from PyQt6.QtCore import QSize
                        ThumbnailLoader.inst().get_thumbnail(full_path, QSize(256, 256))
                        
            # Также обновим self.loading_files в памяти
            for full_path, idx in files_to_insert:
                rel = safe_relpath(full_path, self.current_inbox_dir)
                if rel not in self.loading_files:
                    self.loading_files.insert(idx, rel)
        finally:
            self.grid_view.setUpdatesEnabled(True)
            self.list_view.setUpdatesEnabled(True)
            
        self.grid_view.doItemsLayout()
        self.list_view.doItemsLayout()
        
        # Schedule hover check after files are inserted
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(150, self.grid_view.check_hover_under_mouse)
        QTimer.singleShot(150, self.list_view.check_hover_under_mouse)

    def update_file_path_in_view(self, old_path: str, new_path: str) -> None:
        """
        Точечно обновляет путь к файлу в сетке, списке и кэшах без перерисовки всей очереди.
        
        На будущее для множественного тегирования: если потребуется обновлять множество путей,
        этот метод можно легко переписать или вызвать в цикле по списку пар (old_path, new_path).
        """
        norm_old = os.path.normpath(old_path)
        if norm_old.startswith("\\\\?\\"):
            norm_old = norm_old[4:]
        norm_new = os.path.normpath(new_path)
        if norm_new.startswith("\\\\?\\"):
            norm_new = norm_new[4:]
        
        self.grid_view.setUpdatesEnabled(False)
        self.list_view.setUpdatesEnabled(False)
        try:
            # 1. Обновляем Grid View
            item_grid = self.grid_items_map.pop(norm_old, None)
            if item_grid:
                item_grid.setData(Qt.ItemDataRole.UserRole, new_path)
                self.grid_items_map[norm_new] = item_grid
                widget_grid = self.grid_view.itemWidget(item_grid)
                if isinstance(widget_grid, SorterGridItemWidget):
                    widget_grid.filepath = new_path
                    # Обновляем бэдж расширения
                    ext = os.path.splitext(new_path)[1].upper()
                    if ext.startswith('.'): ext = ext[1:]
                    widget_grid.lbl_badge.setText(ext if ext else "FILE")
                    # Обновляем размер
                    file_size = 0
                    try: file_size = os.path.getsize(ensure_long_path(new_path))
                    except Exception: pass
                    widget_grid.lbl_size_badge.setText(format_short_size(file_size))
                    # Обновляем имя и размеры
                    widget_grid.update_sizes()
                    
            # 2. Обновляем List View
            item_list = self.list_items_map.pop(norm_old, None)
            if item_list:
                item_list.setData(Qt.ItemDataRole.UserRole, new_path)
                self.list_items_map[norm_new] = item_list
                widget_list = self.list_view.itemWidget(item_list)
                if isinstance(widget_list, SorterListItemWidget):
                    widget_list.filepath = new_path
                    # Обновляем имя
                    widget_list.lbl_name.setText(os.path.basename(new_path))
                    # Обновляем бэдж расширения
                    ext = os.path.splitext(new_path)[1].upper()
                    if ext.startswith('.'): ext = ext[1:]
                    widget_list.lbl_badge.setText(ext if ext else "FILE")
                    # Обновляем размер
                    file_size = 0
                    try: file_size = os.path.getsize(ensure_long_path(new_path))
                    except Exception: pass
                    from utils_common import format_size
                    widget_list.lbl_size.setText(format_size(file_size))
                    widget_list.update_sizes()
                    
            # 3. Обновляем список загруженных файлов в памяти
            if hasattr(self, 'loading_files') and self.loading_files and hasattr(self, 'current_inbox_dir') and self.current_inbox_dir is not None:
                # Находим относительные пути
                rel_old = safe_relpath(old_path, self.current_inbox_dir)
                rel_new = safe_relpath(new_path, self.current_inbox_dir)
                for idx, f in enumerate(self.loading_files):
                    if os.path.normpath(f) == os.path.normpath(rel_old):
                        self.loading_files[idx] = rel_new
                        break
                        
            # 4. Обновляем кэш миниатюр
            ThumbnailLoader.inst().rename_cache_key(old_path, new_path)
            
        finally:
            self.grid_view.setUpdatesEnabled(True)
            self.list_view.setUpdatesEnabled(True)
            
        self.grid_view.doItemsLayout()
        self.list_view.doItemsLayout()

    def sync_active_index(self, idx, scroll=True):
        """Синхронизирует выделенный элемент в сетке и списке с указанным индексом."""
        self.grid_view.clearSelection()
        
        grid_item = self.get_grid_item(idx)
        if grid_item:
            grid_item.setSelected(True)
            self.grid_view.setCurrentItem(grid_item)
            if scroll:
                self.grid_view.scrollToItem(grid_item)
            
        if hasattr(self.list_view, 'table'):
            self.list_view.table.clearSelection()
            if 0 <= idx < self.list_view.table.rowCount():
                self.list_view.table.selectRow(idx)
                self.list_view.table.setCurrentCell(idx, 0)
                item = self.list_view.table.item(idx, 0)
                if item and scroll:
                    self.list_view.table.scrollToItem(item)
        else:
            self.list_view.clearSelection()
            list_item = self.get_list_item(idx)
            if list_item and hasattr(self.list_view, 'setCurrentItem'):
                list_item.setSelected(True)
                self.list_view.setCurrentItem(list_item)
                if scroll:
                    self.list_view.scrollToItem(list_item)
            
        # Обновим визуальное состояние кастомных виджетов
        for view in [self.grid_view, self.list_view]:
            if not hasattr(view, 'count'): continue
            for i in range(view.count()):
                item = view.item(i)
                if not item: continue
                widget = view.itemWidget(item)
                if widget and hasattr(widget, 'set_selected'):
                    widget.set_selected(item.isSelected())
        self.selection_changed.emit()

    def _sync_main_app_index(self, row: int) -> None:
        """Синхронизирует текущий индекс главного приложения с выбранной строкой в списке/плитке."""
        curr_mode = self.stack.currentIndex()
        view = None
        if curr_mode == 1:
            view = self.grid_view
        elif curr_mode == 2:
            view = self.list_view
            
        if not view:
            return
            
        item = view.item(row)
        if not item:
            return
            
        filepath = item.data(Qt.ItemDataRole.UserRole)
        if not filepath:
            return
            
        main_app = self.get_main_app()
        if not main_app:
            return
            
        rel_path = safe_relpath(filepath, main_app.UNSORT_DIR)
        rel_path_norm = os.path.normpath(rel_path)
        
        target_idx = -1
        if hasattr(main_app, 'find_queue_index'):
            target_idx = main_app.find_queue_index(rel_path)
        elif 0 <= row < len(main_app.files_queue):
            target_idx = row
            
        if target_idx != -1 and main_app.current_index != target_idx:
            main_app.current_index = target_idx
            main_app.current_file_path = filepath
            logging.info(f"[SorterViewerArea] Synced main app current_index to {target_idx} ({os.path.basename(filepath)}) from row {row}")
            # Обновляем тулбар только если выделен 1 файл
            selected_count = len(self.get_selected_files())
            if selected_count <= 1:
                main_app.update_file_info_label()

    def navigate_vertical(self, direction: int) -> None:
        """Перемещает фокус вверх (-1) или вниз (1) по списку/плиткам в зависимости от режима."""
        curr_mode = self.stack.currentIndex()
        if curr_mode == 0:
            main_app = self.get_main_app()
            if main_app:
                if direction == -1:
                    main_app.prev_file()
                else:
                    main_app.next_file()
            return
            
        view = None
        if curr_mode == 1:
            view = self.grid_view
        elif curr_mode == 2:
            view = self.list_view
            
        if not view or view.count() == 0:
            return
            
        current_row = view.currentRow()
        if current_row < 0:
            current_row = 0
            
        if curr_mode == 1:
            cols = self.get_grid_columns_count()
            cols = max(1, cols)
            if direction == -1:
                candidate = current_row - cols
                while candidate >= 0 and not view._get_file_row(candidate):
                    candidate -= 1
                new_row = candidate if candidate >= 0 else current_row
            else:
                candidate = current_row + cols
                while candidate < view.count() and not view._get_file_row(candidate):
                    candidate += 1
                new_row = candidate if candidate < view.count() else current_row
        else:
            new_row = view._next_file_row(current_row, direction)
            
        if new_row != current_row:
            view._apply_key_navigation(new_row, Qt.KeyboardModifier.NoModifier)

    def select_file_from_preview(self, filepath: str) -> None:
        """
        Выделяет файл из окна быстрого просмотра в соответствии с логикой:
        - Если выделено 0 или 1 файл: сбросить всё и выделить только этот файл.
        - Если выделено >= 2 файлов:
          - Если этот файл НЕ выделен: добавить его к текущей выборке.
          - Если этот файл УЖЕ выделен: снять выделение со всех остальных и оставить только его.
        """
        target_path = os.path.normpath(filepath)
        selected_paths = self.get_selected_files()
        count = len(selected_paths)
        
        item_grid = getattr(self, 'grid_items_map', {}).get(target_path)
        item_list = getattr(self, 'list_items_map', {}).get(target_path)
        
        if count <= 1:
            # Сценарий 1: сбрасываем всё и выделяем только этот
            self.grid_view.clearSelection()
            self.list_view.clearSelection()
            if item_grid:
                item_grid.setSelected(True)
                self.grid_view.setCurrentItem(item_grid)
                self.grid_view.scrollToItem(item_grid)
            if item_list:
                item_list.setSelected(True)
                self.list_view.setCurrentItem(item_list)
                self.list_view.scrollToItem(item_list)
        else:
            # Сценарий 2: выделено >= 2 файлов
            if target_path not in selected_paths:
                # 2a: добавить к текущему выделению
                if item_grid:
                    item_grid.setSelected(True)
                if item_list:
                    item_list.setSelected(True)
            else:
                # 2b: снять с других, оставить только этот
                self.grid_view.clearSelection()
                self.list_view.clearSelection()
                if item_grid:
                    item_grid.setSelected(True)
                    self.grid_view.setCurrentItem(item_grid)
                    self.grid_view.scrollToItem(item_grid)
                if item_list:
                    item_list.setSelected(True)
                    self.list_view.setCurrentItem(item_list)
                    self.list_view.scrollToItem(item_list)
                    
        # Обновим визуальное состояние кастомных виджетов
        for view in [self.grid_view, self.list_view]:
            for i in range(view.count()):
                item = view.item(i)
                if not item: continue
                widget = view.itemWidget(item)
                if widget and hasattr(widget, 'set_selected'):
                    widget.set_selected(item.isSelected())
        self.selection_changed.emit()

    def _on_placeholder_double_clicked(self):
        if self.single_view.double_click_callback:
            self.single_view.double_click_callback()

    def _on_placeholder_middle_clicked(self):
        if self.single_view.middle_click_callback:
            self.single_view.middle_click_callback()


# Псевдоним фасада для соответствия паттерну MediaViewer
MediaViewer = SorterViewerArea

__all__ = [
    "SorterViewerArea",
    "MediaViewer",
    "ZoomableGraphicsView",
    "SingleCanvasView",
    "SorterBaseListView",
    "SorterGridView",
    "SorterListView",
    "SorterGridItemWidget",
    "ThumbnailCard",
    "SorterListItemWidget",
    "SorterGridGroupSeparatorWidget",
    "SorterListGroupSeparatorWidget",
    "SorterPlaceholderWidget",
    "FileIconManager",
    "find_main_app",
    "safe_relpath",
    "format_short_size",
    "elide_text_to_two_lines",
]
