"""
viewer_views.py: Реализация сеточного (SorterGridView) и табличного (SorterListView) режимов
на базе SorterBaseListView.
"""
import os
import logging
import subprocess
from PyQt6.QtWidgets import (
    QWidget, QListWidget, QListWidgetItem, QAbstractItemView, QMenu,
    QApplication, QStyle
)
from PyQt6.QtCore import Qt, QTimer, QSize, QPoint, QUrl, pyqtSignal, QItemSelectionModel
from PyQt6.QtGui import (
    QMouseEvent, QWheelEvent, QKeyEvent, QAction, QDesktopServices,
    QCursor, QKeySequence, QPixmap, QMovie
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

from config import AppContext, VIEWER_DESIGN, APP_DESIGN
from utils_extensions import VIDEO_EXTS, AUDIO_EXTS, IMAGE_EXTS
from utils_io import ensure_long_path, strip_long_path_prefix
from .ui_preview_popup import LargePreviewPopup
from .viewer_items import (
    find_main_app, FileIconManager, SorterGridItemWidget, SorterListItemWidget,
    SorterGridGroupSeparatorWidget, SorterListGroupSeparatorWidget,
    format_short_size, safe_relpath
)

class SorterBaseListView(QListWidget):
    """Base class for Grid and List views with shared keyboard and drag & drop logic."""
    items_dropped = pyqtSignal(list, bool)
    item_double_clicked = pyqtSignal(str) # Emits absolute path to switch to Single view
    send_to_editor_requested = pyqtSignal(str, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        
        # Design TITAN Style
        self.setStyleSheet("""
            QListWidget {
                background-color: #1e1e1e;
                border: none;
                outline: none;
            }
            QListWidget::item {
                background-color: #2b2b2b;
                color: #ddd;
                border: 1px solid #444;
                border-radius: 6px;
                margin: 4px;
                padding: 0px;
            }
            QListWidget::item:hover {
                background-color: #353535;
                border-color: #555;
            }
            QListWidget::item:selected {
                background-color: #1e3a8a;
                border-color: #3b82f6;
                color: white;
            }
        """)
            
        # Hover Player
        self.hover_player = QMediaPlayer()
        self.hover_audio = QAudioOutput()
        self.hover_player.setAudioOutput(self.hover_audio)
        self.hover_audio.setVolume(0.0) # Zero volume for hover
        
        self.hover_video_widget = None
        self.hover_movie = None
        self.current_hover_item = None
        self.current_hover_path = ""
        
        self.entered.connect(self._on_item_hover_entered)
        self.itemDoubleClicked.connect(self._on_double_clicked)
        
        # Контекстное меню ПКМ
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        
        # Синхронизация текущего индекса при клике мышью (смена активной строки)
        self.currentRowChanged.connect(self._notify_viewer_area)
        
        # Debounce timer to prevent rapid hover player rebuilding
        self.hover_timer = QTimer(self)
        self.hover_timer.setSingleShot(True)
        self.hover_timer.setInterval(250)
        self.hover_timer.timeout.connect(self._start_hover_playback)

        # Timer for large preview on hover
        self.large_preview_timer = QTimer(self)
        self.large_preview_timer.setSingleShot(True)
        self.large_preview_timer.setInterval(100) # 0.1 seconds (default)
        self.large_preview_timer.timeout.connect(self._show_large_preview)
        
        # Предохранитель дребезга на 100 мс перед началом отсчета
        self.debounce_timer = QTimer(self)
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(100)
        self.debounce_timer.timeout.connect(self._on_debounce_timeout)

        # Таймер периодического отслеживания положения курсора
        self.popup_track_timer = QTimer(self)
        self.popup_track_timer.setInterval(100)
        self.popup_track_timer.timeout.connect(self._track_popup_mouse)
        
        self.large_preview_popup = None

        # Anchor для Shift-выделения (как в Проводнике Windows)
        self._selection_anchor: int = -1
        self.currentItemChanged.connect(self._on_current_item_changed)

    def check_hover_under_mouse(self):
        """Проверяет элемент под курсором мыши и при необходимости вызывает появление ховера."""
        if not self.isVisible():
            return
        from PyQt6.QtGui import QCursor
        pos = self.viewport().mapFromGlobal(QCursor.pos())
        if self.viewport().rect().contains(pos):
            index = self.indexAt(pos)
            if index.isValid():
                self._on_item_hover_entered(index)
            else:
                if self.current_hover_item is not None:
                    if not self.large_preview_popup:
                        self._stop_hover_playback(force=True)
                        self.debounce_timer.stop()
                        self.large_preview_timer.stop()

    def _on_current_item_changed(self, current, previous):
        if current:
            modifiers = QApplication.keyboardModifiers()
            if not (modifiers & Qt.KeyboardModifier.ShiftModifier):
                row = self.row(current)
                if row >= 0:
                    self._selection_anchor = row

    def _get_action_key(self, action_id: str):
        viewer_area = self.get_viewer_area()
        if not viewer_area:
            return None
        main_app = viewer_area.get_main_app()
        if not main_app or not hasattr(main_app, '_hotkey_registry'):
            return None
        registry = main_app._hotkey_registry
        key_str = registry.get_effective_key(action_id)
        if not key_str:
            return None
        seq = QKeySequence(key_str)
        if seq.isEmpty():
            return None
        return seq[0].key()

    def _get_file_row(self, row: int) -> bool:
        """Возвращает True если элемент row является файлом (не группировщиком/сепаратором)."""
        item = self.item(row)
        return item is not None and item.data(Qt.ItemDataRole.UserRole) is not None

    def _next_file_row(self, start: int, direction: int) -> int:
        """Ищет ближайший файловый row в заданном направлении, пропуская сепараторы."""
        count = self.count()
        row = start
        for _ in range(count):
            row = (row + direction) % count
            if self._get_file_row(row):
                return row
        return start  # фолбек если файлов нет вообще

    def _apply_key_navigation(self, new_row: int, modifiers) -> None:
        """Применяет навигационный переход к new_row с учётом модификаторов Shift/Ctrl."""
        shift = modifiers & Qt.KeyboardModifier.ShiftModifier
        ctrl = modifiers & Qt.KeyboardModifier.ControlModifier

        if not self._get_file_row(new_row):
            return

        if shift:
            # Диапазонное выделение от anchor до new_row (как Shift+Click в Проводнике)
            anchor = self._selection_anchor if self._selection_anchor >= 0 else new_row
            lo, hi = min(anchor, new_row), max(anchor, new_row)
            
            # Если Ctrl не зажат, очищаем предыдущие выделения
            if not ctrl:
                self.clearSelection()
                
            for r in range(lo, hi + 1):
                item = self.item(r)
                if item and item.data(Qt.ItemDataRole.UserRole):
                    item.setSelected(True)
            # Устанавливаем текущий без изменения якоря
            self.setCurrentRow(new_row, QItemSelectionModel.SelectionFlag.Current)
        elif ctrl:
            # Ctrl: добавляем элемент к выделению без сброса остальных
            item = self.item(new_row)
            if item:
                item.setSelected(True)
            self.setCurrentRow(new_row, QItemSelectionModel.SelectionFlag.Current)
        else:
            # Без модификаторов: сбросить выделение, выбрать только новый элемент
            self._selection_anchor = new_row
            self.clearSelection()
            item = self.item(new_row)
            if item:
                item.setSelected(True)
            self.setCurrentRow(new_row, QItemSelectionModel.SelectionFlag.Current)

        self.scrollToItem(self.item(new_row))
        # Синхронизируем тулбар главного приложения
        self._notify_viewer_area(new_row)

    def _notify_viewer_area(self, row: int) -> None:
        """Уведомляет SorterViewerArea о смене активного элемента для синхронизации тулбара."""
        viewer_area = self.get_viewer_area()
        if viewer_area and hasattr(viewer_area, '_sync_main_app_index'):
            viewer_area._sync_main_app_index(row)

    def keyPressEvent(self, event) -> None:
        """Обработка стрелок с поддержкой multi-select (Shift/Ctrl) как в Проводнике Windows."""
        key = event.key()
        modifiers = event.modifiers()
        count = self.count()

        if count == 0:
            super().keyPressEvent(event)
            return

        # Получаем коды клавиш из реестра горячих клавиш
        key_up = self._get_action_key("move_up")
        key_down = self._get_action_key("move_down")
        key_left = self._get_action_key("prev_file")
        key_right = self._get_action_key("next_file")

        # Если клавиши не настроены в реестре, используем дефолтные стрелки
        if not key_up: key_up = Qt.Key.Key_Up
        if not key_down: key_down = Qt.Key.Key_Down
        if not key_left: key_left = Qt.Key.Key_Left
        if not key_right: key_right = Qt.Key.Key_Right

        nav_keys = (key_up, key_down, key_left, key_right)

        if key not in nav_keys:
            super().keyPressEvent(event)
            return

        current_row = self.currentRow()
        if current_row < 0:
            current_row = 0

        # Определяем режим (Grid=IconMode, List=ListMode) по родительскому ViewerArea
        viewer_area = self.get_viewer_area()
        is_grid = (viewer_area is not None and
                   viewer_area.stack.currentIndex() == 1)

        if is_grid:
            cols = viewer_area.get_grid_columns_count() if hasattr(viewer_area, 'get_grid_columns_count') else 1
            cols = max(1, cols)

            if key == key_right:
                new_row = self._next_file_row(current_row, 1)
            elif key == key_left:
                new_row = self._next_file_row(current_row, -1)
            elif key == key_down:
                candidate = current_row + cols
                # Ищем ближайший файловый элемент вниз по строке
                while candidate < count and not self._get_file_row(candidate):
                    candidate += 1
                new_row = candidate if candidate < count else current_row
            elif key == key_up:
                candidate = current_row - cols
                # Ищем ближайший файловый элемент вверх по строке
                while candidate >= 0 and not self._get_file_row(candidate):
                    candidate -= 1
                new_row = candidate if candidate >= 0 else current_row
            else:
                new_row = current_row
        else:
            # List-режим: Left/Right = Up/Down (одномерный список)
            if key in (key_right, key_down):
                new_row = self._next_file_row(current_row, 1)
            elif key in (key_left, key_up):
                new_row = self._next_file_row(current_row, -1)
            else:
                new_row = current_row

        if new_row != current_row:
            self._apply_key_navigation(new_row, modifiers)

        event.accept()

    def _on_large_preview_closed(self):
        self.large_preview_popup = None
        self.current_hover_item = None
        self.current_hover_path = ""

    def mouseMoveEvent(self, event):
        if not self.isVisible():
            return
        super().mouseMoveEvent(event)
        index = self.indexAt(event.pos())
        if index.isValid():
            item = self.itemFromIndex(index)
            if item != self.current_hover_item:
                self._on_item_hover_entered(index)
        else:
            # Мышь ушла на пустое место списка
            if self.current_hover_item is not None:
                if not self.large_preview_popup:
                    self._stop_hover_playback(force=True)
                    self.debounce_timer.stop()
                    self.large_preview_timer.stop()

    def get_video_widget(self):
        try:
            if not hasattr(self, 'hover_video_widget') or self.hover_video_widget is None:
                raise RuntimeError("no widget")
            self.hover_video_widget.parent()
        except (RuntimeError, AttributeError):
            logging.info("Recreating deleted/missing hover_video_widget")
            self.hover_video_widget = QVideoWidget()
            self.hover_video_widget.hide()
            self.hover_player.setVideoOutput(self.hover_video_widget)
        return self.hover_video_widget

    def leaveEvent(self, event):
        # Если зажата левая кнопка (выделение или перетаскивание) — не закрывать
        from PyQt6.QtWidgets import QApplication
        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            super().leaveEvent(event)
            return
            
        # Если попап открыт, то пусть закрытием управляет таймер отслеживания (popup_track_timer)
        if hasattr(self, 'large_preview_popup') and self.large_preview_popup:
            super().leaveEvent(event)
            return
            
        # Иначе останавливаем обычный ховер и таймеры
        self._stop_hover_playback(force=True)
        self.debounce_timer.stop()
        self.large_preview_timer.stop()
        super().leaveEvent(event)

    def hideEvent(self, event):
        self._stop_hover_playback(force=True)
        self.debounce_timer.stop()
        self.large_preview_timer.stop()
        super().hideEvent(event)

    def _on_item_hover_entered(self, index):
        if not self.isVisible():
            return
        viewer_area = self.get_viewer_area()
        if viewer_area and getattr(viewer_area, 'disable_hover_preview', False):
            if self.current_hover_item is not None or self.large_preview_popup is not None:
                self._stop_hover_playback(force=True)
            return
            
        item = self.itemFromIndex(index)
        if item == self.current_hover_item:
            return
        
        # Сразу останавливаем таймеры и закрываем старый попап
        self._stop_hover_playback(force=True)
        self.debounce_timer.stop()
        self.large_preview_timer.stop()
        
        if item:
            p = item.data(Qt.ItemDataRole.UserRole)
            if not p:
                self.current_hover_item = None
                self.current_hover_path = None
                return
                
            self.current_hover_item = item
            self.current_hover_path = ensure_long_path(p)
            
            # Запускаем предохранитель дребезга на 100 мс
            self.debounce_timer.start(100)

    def _on_debounce_timeout(self):
        # 100 мс прошло. Запускаем мини-плеер и таймер задержки большого просмотра
        if self.current_hover_item:
            self.hover_timer.start()
            
            viewer_area = self.get_viewer_area()
            main_app = viewer_area.get_main_app() if viewer_area and hasattr(viewer_area, 'get_main_app') else None
            delay_sec = 0.4
            if main_app and hasattr(main_app, 'config'):
                try:
                    delay_sec = float(main_app.config.get("hover_delay", 0.4))
                except (ValueError, TypeError):
                    delay_sec = 0.4
            
            self.large_preview_timer.setInterval(int(delay_sec * 1000))
            self.large_preview_timer.start()

    def _start_hover_playback(self):
        if not self.current_hover_path or not os.path.exists(self.current_hover_path): return
        
        from utils_extensions import VIDEO_EXTS, AUDIO_EXTS, IMAGE_EXTS
        from utils_io import strip_long_path_prefix
        norm_path = os.path.normpath(strip_long_path_prefix(self.current_hover_path))
        main_app = self.get_main_app()
        if main_app and hasattr(main_app, 'locked_files') and norm_path in main_app.locked_files:
            return
            
        ext = os.path.splitext(self.current_hover_path)[1].lower()
        
        # Check if multiple items are selected. If so, don't play anything.
        if len(self.selectedItems()) > 1:
            return
            
        widget = self.itemWidget(self.current_hover_item)
        if not widget:
            return
            
        # Мини-ховер для видео и gif отключён: используется только окно предпросмотра (LargePreviewPopup)
        pass

    def _update_hover_movie_frame(self):
        if self.hover_movie and self.current_hover_item:
            try:
                widget = self.itemWidget(self.current_hover_item)
            except RuntimeError:
                self.current_hover_item = None
                self._stop_hover_playback(force=True)
                return
            if widget and hasattr(widget, 'preview_frame'):
                pixmap = self.hover_movie.currentPixmap()
                target_size = widget.preview_frame.size() - QSize(4, 4)
                scaled = pixmap.scaled(
                    target_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                widget.lbl_preview.setPixmap(scaled)

    def _stop_hover_playback(self, force=False):
        if not force:
            import time
            if hasattr(self, '_popup_open_time') and (time.time() - self._popup_open_time) < 0.15:
                return

        self.hover_timer.stop()
        self.large_preview_timer.stop()
        self.popup_track_timer.stop()
        
        if hasattr(self, 'large_preview_popup') and self.large_preview_popup:
            popup = self.large_preview_popup
            self.large_preview_popup = None
            try:
                popup.cleanup()
                popup.close()
            except Exception:
                pass

        if self.hover_movie:
            try:
                self.hover_movie.stop()
                self.hover_movie.deleteLater()
            except Exception:
                pass
            self.hover_movie = None
            
        try:
            self.hover_player.stop()
            self.hover_player.setSource(QUrl())
        except Exception:
            pass
        
        self.current_hover_item = None
        self.current_hover_path = ""

    def _track_popup_mouse(self):
        try:
            if hasattr(self, 'large_preview_popup') and self.large_preview_popup and not self.large_preview_popup.isHidden():
                from PyQt6.QtCore import QRect
                pos = QCursor.pos()
                popup_geom = self.large_preview_popup.geometry()
                
                # Получаем геометрию текущей плитки в глобальных координатах
                tile_geom = QRect()
                if getattr(self, 'current_hover_item', None):
                    try:
                        rect = self.visualItemRect(self.current_hover_item)
                        tile_global_pos = self.viewport().mapToGlobal(rect.topLeft())
                        tile_geom = QRect(tile_global_pos, rect.size())
                    except RuntimeError:
                        # C++ object has been deleted
                        self.current_hover_item = None
                
                in_popup = popup_geom.adjusted(-8, -8, 8, 8).contains(pos)
                in_tile = tile_geom.adjusted(-8, -8, 8, 8).contains(pos)
                
                # Если курсор вне попапа и вне плитки (с буфером безопасности 8px), закрываем попап
                if not in_popup and not in_tile:
                    self._stop_hover_playback(force=True)
            else:
                if hasattr(self, 'popup_track_timer'):
                    self.popup_track_timer.stop()
        except Exception as e:
            import logging
            logging.error(f"[TrackPopup] Exception in tracking mouse: {e}")
            self._stop_hover_playback(force=True)

    def get_main_app(self):
        """Поднимается по дереву родителей до первого объекта с global_volume.
        Это надёжнее чем фиксированное количество уровней (parent -> grandparent),
        так как глубина вложенности может меняться.
        """
        widget = self.parent()
        while widget is not None:
            if hasattr(widget, 'global_volume'):
                return widget
            widget = widget.parent()
        return None

    def get_viewer_area(self):
        """Поднимается по дереву родителей до первого объекта с методом sync_files_queue."""
        widget = self.parent()
        while widget is not None:
            if hasattr(widget, 'sync_files_queue'):
                return widget
            widget = widget.parent()
        return None

    def _on_popup_destroyed(self):
        self.large_preview_popup = None

    def _show_large_preview(self):
        # Если идет загрузка файлов — не открываем окно быстрого просмотра
        viewer_area = self.get_viewer_area()
        if viewer_area and hasattr(viewer_area, 'loading_overlay') and not viewer_area.loading_overlay.isHidden():
            return
            
        if not self.current_hover_path or not os.path.exists(self.current_hover_path):
            return
            
        from utils_extensions import VIDEO_EXTS, AUDIO_EXTS, IMAGE_EXTS
        from utils_io import strip_long_path_prefix
        norm_path = os.path.normpath(strip_long_path_prefix(self.current_hover_path))
        main_app = self.get_main_app()
        if main_app and hasattr(main_app, 'locked_files') and norm_path in main_app.locked_files:
            return
            
        ext = os.path.splitext(self.current_hover_path)[1].lower()
        is_media = ext in VIDEO_EXTS or ext in AUDIO_EXTS or ext in IMAGE_EXTS
        if not is_media:
            return
            
        # Stop mini hover playback
        self.hover_timer.stop()
        self.hover_player.stop()
        if self.hover_movie:
            self.hover_movie.stop()
            
        # Автовыделение элемента, если выделено 0 или 1 файл (при множественном выделении выделение не сбрасывается)
        selected_items = self.selectedItems()
        if len(selected_items) <= 1:
            if self.current_hover_item and (not selected_items or selected_items[0] != self.current_hover_item):
                self.clearSelection()
                self.current_hover_item.setSelected(True)
                self.setCurrentItem(self.current_hover_item)
            
        main_app = self.get_main_app()
        self.large_preview_popup = LargePreviewPopup(self.current_hover_path, main_app, self.window())
        self.large_preview_popup.destroyed.connect(self._on_popup_destroyed)
        
        # Размеры попапа, установленные пользователем
        viewer_area = self.get_viewer_area()
        popup_size = viewer_area.popup_size if (viewer_area and hasattr(viewer_area, 'popup_size')) else QSize(640, 520)
        popup_w = popup_size.width()
        popup_h = popup_size.height()
        
        # Позиционирование
        pos = QCursor.pos()
        app_geom = self.window().geometry()
        
        if self.current_hover_item:
            try:
                rect = self.visualItemRect(self.current_hover_item)
                tile_global_pos = self.viewport().mapToGlobal(rect.topLeft())
                tile_w = rect.width()
                tile_h = rect.height()
            except RuntimeError:
                # Item was deleted
                self.current_hover_item = None
                self._stop_hover_playback(force=True)
                return
            
            # Область превью: ширина равна ширине плитки, высота исключает текстовый блок 42px
            preview_w = tile_w
            preview_h = tile_h - 42
            
            # Внутренний прямоугольник превью с отступами: 15% справа/слева и 20% сверху/снизу
            dx = int(0.15 * preview_w)
            dy = int(0.20 * preview_h)
            X_inner_left = tile_global_pos.x() + dx
            X_inner_right = tile_global_pos.x() + preview_w - dx
            Y_inner_top = tile_global_pos.y() + dy
            Y_inner_bottom = tile_global_pos.y() + preview_h - dy
            
            # Считаем свободное место справа и слева до краев окна приложения
            space_right = app_geom.right() - X_inner_right
            space_left = X_inner_left - app_geom.left()
            
            # Выбираем направление по горизонтали
            if space_right >= space_left:
                x_start = X_inner_left
                dir_x = 'right'
            else:
                x_start = X_inner_right
                dir_x = 'left'
                
            # Считаем свободное место снизу и сверху до краев окна приложения
            space_bottom = app_geom.bottom() - Y_inner_bottom
            space_top = Y_inner_top - app_geom.top()
            
            # Выбираем направление по вертикали
            if space_bottom >= space_top:
                y_start = Y_inner_bottom
                dir_y = 'bottom'
            else:
                y_start = Y_inner_top
                dir_y = 'top'
                
            # Рассчитываем максимально доступное пространство для попапа в выбранном направлении
            max_w = (app_geom.right() - x_start) if dir_x == 'right' else (x_start - app_geom.left())
            max_h = (app_geom.bottom() - y_start) if dir_y == 'bottom' else (y_start - app_geom.top())
            
            # Пропорциональное масштабирование, чтобы попап поместился до краев экрана
            scale = min(1.0, max_w / popup_w, max_h / popup_h)
            
            # Задаем фактический размер (не меньше минимального)
            actual_w = max(320, int(popup_w * scale))
            actual_h = max(260, int(popup_h * scale))
            
            # Финальные координаты верхнего левого угла
            x = x_start if dir_x == 'right' else (x_start - actual_w)
            y = y_start if dir_y == 'bottom' else (y_start - actual_h)
            
            # Корректируем координаты, чтобы попап гарантированно не вылетал за границы окна приложения (экрана)
            if x + actual_w > app_geom.right():
                x = app_geom.right() - actual_w
            if x < app_geom.left():
                x = app_geom.left()
                
            if y + actual_h > app_geom.bottom():
                y = app_geom.bottom() - actual_h
            if y < app_geom.top():
                y = app_geom.top()
            
            popup_w = actual_w
            popup_h = actual_h
        else:
            # Фолбэк на курсор, если плитки вдруг нет
            x = pos.x() - 50
            y = pos.y() - 20
            
            # Гарантируем, что попап не выходит за горизонтальные границы приложения
            if x + popup_w > app_geom.right():
                x = app_geom.right() - popup_w
            if x < app_geom.left():
                x = app_geom.left()
                
            # Гарантируем, что попап не выходит за вертикальные границы приложения
            if y + popup_h > app_geom.bottom():
                y = app_geom.bottom() - popup_h
            if y < app_geom.top():
                y = app_geom.top()
            
        self.large_preview_popup.setFixedSize(popup_w, popup_h)
        self.large_preview_popup.move(x, y)
        import time
        self._popup_open_time = time.time()
        self.large_preview_popup.show()
        
        # Запускаем отслеживание координат мыши
        self.popup_track_timer.start(100)

    def _on_double_clicked(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self._stop_hover_playback(force=True)
            self.item_double_clicked.emit(path)

    def mousePressEvent(self, event):
        """Обработка клика средней кнопкой мыши — открыть папку с файлом."""
        if event.button() == Qt.MouseButton.MiddleButton:
            index = self.indexAt(event.position().toPoint())
            if index.isValid() and len(self.selectedItems()) <= 1:
                item = self.itemFromIndex(index)
                if item:
                    path = item.data(Qt.ItemDataRole.UserRole)
                    if path:
                        self._open_folder_with_focus(path)
        super().mousePressEvent(event)

    def _on_context_menu(self, pos):
        """Контекстное меню ПКМ — поддерживает одиночное и множественное выделение."""
        selected_items = self.selectedItems()
        item = self.itemAt(pos)
        if item and item not in selected_items:
            self.clearSelection()
            item.setSelected(True)
            self.setCurrentItem(item)
            selected_items = [item]
            
        if not selected_items:
            return
            
        paths = [i.data(Qt.ItemDataRole.UserRole) for i in selected_items if i.data(Qt.ItemDataRole.UserRole)]
        paths = [p for p in paths if os.path.exists(p)]
        if not paths:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #252525;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                color: #dddddd;
                padding: 6px 20px 6px 12px;
                border-radius: 4px;
                font-size: 12px;
            }
            QMenu::item:selected {
                background-color: #3b82f6;
                color: white;
            }
            QMenu::separator {
                height: 1px;
                background: #444;
                margin: 3px 8px;
            }
        """)

        video_exts = VIDEO_EXTS
        audio_exts = AUDIO_EXTS
        image_exts = IMAGE_EXTS

        if len(paths) == 1:
            path = paths[0]
            ext = os.path.splitext(path)[1].lower()
            
            act_open = QAction(AppContext.tr("srt_ctx_open_file"), self)
            act_open.triggered.connect(lambda Checked, p=path: self._open_file(p))
            menu.addAction(act_open)

            act_folder = QAction(AppContext.tr("srt_ctx_open_folder"), self)
            act_folder.triggered.connect(lambda Checked, p=path: self._open_folder_with_focus(p))
            menu.addAction(act_folder)
            
            if ext in video_exts:
                menu.addSeparator()
                act_vconv = QAction(AppContext.tr("srt_ctx_convert_video"), self)
                act_vconv.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("video_conv", p))
                menu.addAction(act_vconv)
                
                act_aconv = QAction(AppContext.tr("srt_ctx_convert_audio_to"), self)
                act_aconv.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("audio_conv", p))
                menu.addAction(act_aconv)
                
                act_vedit = QAction(AppContext.tr("srt_ctx_edit_video"), self)
                act_vedit.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("video_edit", p))
                menu.addAction(act_vedit)
                
            elif ext in audio_exts:
                menu.addSeparator()
                act_aconv = QAction(AppContext.tr("srt_ctx_convert_audio"), self)
                act_aconv.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("audio_conv", p))
                menu.addAction(act_aconv)
                
                act_aedit = QAction(AppContext.tr("srt_ctx_edit_audio"), self)
                act_aedit.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("audio_edit", p))
                menu.addAction(act_aedit)
                
            elif ext in image_exts:
                menu.addSeparator()
                act_iconv = QAction(AppContext.tr("srt_ctx_convert_image"), self)
                act_iconv.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("image_conv", p))
                menu.addAction(act_iconv)
                
                act_ai = QAction("Сделать эталоном ИИ поиска" if AppContext.LANG == "RU" else "Use as AI Search Reference", self)
                act_ai.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("ai_search", p))
                menu.addAction(act_ai)
                
                if ext == '.gif':
                    from PyQt6.QtGui import QImageReader
                    reader = QImageReader(path)
                    if reader.supportsAnimation() and reader.imageCount() > 1:
                        act_vconv = QAction(AppContext.tr("srt_ctx_convert_video"), self)
                        act_vconv.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("video_conv", p))
                        menu.addAction(act_vconv)
        else:
            is_all_video = all(os.path.splitext(p)[1].lower() in video_exts for p in paths)
            is_all_audio = all(os.path.splitext(p)[1].lower() in audio_exts for p in paths)
            is_all_image = all(os.path.splitext(p)[1].lower() in image_exts for p in paths)
            
            if is_all_video:
                act_vconv = QAction(AppContext.tr("srt_ctx_convert_video_count").format(len(paths)), self)
                act_vconv.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("video_conv", p))
                menu.addAction(act_vconv)
                
                act_aconv = QAction(AppContext.tr("srt_ctx_convert_audio_to_count").format(len(paths)), self)
                act_aconv.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("audio_conv", p))
                menu.addAction(act_aconv)
                
            elif is_all_audio:
                act_aconv = QAction(AppContext.tr("srt_ctx_convert_audio_count").format(len(paths)), self)
                act_aconv.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("audio_conv", p))
                menu.addAction(act_aconv)
                
            elif is_all_image:
                act_iconv = QAction(AppContext.tr("srt_ctx_convert_image_count").format(len(paths)), self)
                act_iconv.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("image_conv", p))
                menu.addAction(act_iconv)
                
                act_ai = QAction("Сделать эталоном ИИ поиска" if AppContext.LANG == "RU" else "Use as AI Search Reference", self)
                act_ai.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("ai_search", p))
                menu.addAction(act_ai)

        menu.addSeparator()
        if len(paths) <= 1:
            del_label = AppContext.tr("srt_ctx_delete_files")
        else:
            del_label = AppContext.tr("srt_ctx_delete_files_count").format(len(paths))
        act_delete = QAction(del_label, self)
        act_delete.triggered.connect(lambda checked, p=paths: self.delete_files_requested(p))
        menu.addAction(act_delete)

        if menu.actions():
            menu.exec(self.mapToGlobal(pos))

    def delete_files_requested(self, file_paths):
        main_app = self.get_main_app()
        if main_app and hasattr(main_app, 'delete_files_permanently'):
            main_app.delete_files_permanently(file_paths)

    def _open_file(self, path):
        """Открыть файл в программе по умолчанию ОС."""
        try:
            os.startfile(os.path.normpath(path))
        except Exception as e:
            logging.error(f"Cannot open file '{path}': {e}")

    def _open_folder_with_focus(self, path):
        """Открыть папку в Проводнике с выделением файла."""
        try:
            from utils_common import reveal_in_explorer
            reveal_in_explorer(path)
        except Exception as e:
            logging.error(f"Cannot open folder for '{path}': {e}")
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        md = event.mimeData()
        paths = []
        is_external = False
        if md.hasUrls():
            urls = md.urls()
            if urls:
                paths = [u.toLocalFile() for u in urls]
                is_external = True
        if paths:
            self.items_dropped.emit(paths, is_external)
            event.acceptProposedAction()
        else:
            event.ignore()


class SorterGridView(SorterBaseListView):
    """Grid View (IconMode) showing thumbnails with Ctrl+Wheel scaling."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setWordWrap(True)
        self.setSpacing(4)
        
        self.tile_size = 128
        self._update_grid_sizes()
        
        self.zoom_commit_timer = QTimer(self)
        self.zoom_commit_timer.setSingleShot(True)
        self.zoom_commit_timer.timeout.connect(self._commit_zoom)
        self._commit_index = 0
        self._zoom_session_id = 0
        
        # Make items background and border transparent in Grid mode to avoid selection overlays
        self.setStyleSheet("""
            QListWidget {
                background-color: #1e1e1e;
                border: none;
                outline: none;
                padding-bottom: 20px;
            }
            QListWidget::item {
                background-color: transparent;
                border: none;
                border-radius: 0px;
                margin: 4px;
                padding: 0px;
            }
            QListWidget::item:hover {
                background-color: transparent;
                border: none;
            }
            QListWidget::item:selected {
                background-color: transparent;
                border: none;
                color: white;
            }
        """)

    def selectionChanged(self, selected, deselected):
        super().selectionChanged(selected, deselected)
        for index in selected.indexes():
            item = self.item(index.row())
            if item:
                widget = self.itemWidget(item)
                if widget and hasattr(widget, 'set_selected'):
                    widget.set_selected(True)
        for index in deselected.indexes():
            item = self.item(index.row())
            if item:
                widget = self.itemWidget(item)
                if widget and hasattr(widget, 'set_selected'):
                    widget.set_selected(False)

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            viewer_area = self.get_viewer_area()
            old_cols = viewer_area.get_grid_columns_count() if viewer_area and hasattr(viewer_area, 'get_grid_columns_count') else 1
            
            delta = event.angleDelta().y()
            if delta > 0:
                self.tile_size = min(256, self.tile_size + 16)
            else:
                self.tile_size = max(64, self.tile_size - 16)
            self._update_grid_sizes()
            self._zoom_session_id += 1
            
            # Scale only visible item custom widgets for ultra-smooth zoom
            viewport_rect = self.viewport().rect()
            start_index = self.indexAt(viewport_rect.topLeft())
            end_index = self.indexAt(viewport_rect.bottomRight())
            
            start_row = start_index.row() if start_index.isValid() else 0
            end_row = end_index.row() if end_index.isValid() else self.count() - 1
            if end_row < 0:
                end_row = self.count() - 1
            
            _thumb_exts = set(VIDEO_EXTS) | set(IMAGE_EXTS)
            target_thumb_size = QSize(max(256, self.tile_size), max(256, self.tile_size))
            
            for i in range(max(0, start_row), min(self.count(), end_row + 1)):
                item = self.item(i)
                widget = self.itemWidget(item)
                if widget and hasattr(widget, 'set_tile_size'):
                    widget.set_tile_size(self.tile_size)
                    item.setSizeHint(widget.sizeHint())
                    
                    filepath = widget.filepath
                    norm_path = os.path.normpath(strip_long_path_prefix(filepath))
                    ext = os.path.splitext(filepath)[1].lower()
                    
                    if norm_path in ThumbnailLoader.inst().cache:
                        widget.set_preview_image(ThumbnailLoader.inst().cache[norm_path])
                    elif ext in _thumb_exts:
                        ThumbnailLoader.inst().get_thumbnail(filepath, target_thumb_size)
                        if widget.placeholder_pixmap:
                            widget.set_placeholder(widget.placeholder_pixmap)
                    elif widget.placeholder_pixmap:
                        widget.set_placeholder(widget.placeholder_pixmap)
            
            self.doItemsLayout()
            self.viewport().update()
            
            self.zoom_commit_timer.start(250)
            
            if viewer_area and hasattr(viewer_area, 'sync_files_queue'):
                main_app = viewer_area.get_main_app()
                group_enabled = main_app.config.get("group_by_sort", False) if main_app and hasattr(main_app, 'config') else False
                if group_enabled and hasattr(viewer_area, 'current_inbox_dir') and viewer_area.current_inbox_dir is not None and viewer_area.loading_files:
                    new_cols = viewer_area.get_grid_columns_count()
                    if old_cols != new_cols:
                        viewer_area._last_cols_count = new_cols
                        viewer_area.loading_target_select_idx = viewer_area.get_current_selected_index()
                        viewer_area.sync_files_queue(viewer_area.current_inbox_dir, viewer_area.loading_files, viewer_area.loading_target_select_idx, silent=True)
            
            event.accept()
        else:
            super().wheelEvent(event)

    def _update_grid_sizes(self):
        self.setGridSize(QSize(self.tile_size + 4, self.tile_size + 42))

    def _commit_zoom(self):
        self._commit_index = 0
        self._commit_batch(self._zoom_session_id)

    def _commit_batch(self, session_id):
        if session_id != self._zoom_session_id:
            return
            
        if self._commit_index >= self.count():
            self.doItemsLayout()
            self.viewport().update()
            return
            
        end = min(self.count(), self._commit_index + 500)
        _thumb_exts = set(VIDEO_EXTS) | set(IMAGE_EXTS)
        target_thumb_size = QSize(max(256, self.tile_size), max(256, self.tile_size))
        
        for i in range(self._commit_index, end):
            item = self.item(i)
            widget = self.itemWidget(item)
            if widget and hasattr(widget, 'set_tile_size'):
                if widget.tile_size != self.tile_size:
                    widget.set_tile_size(self.tile_size)
                    item.setSizeHint(widget.sizeHint())
                    
                    filepath = widget.filepath
                    norm_path = os.path.normpath(strip_long_path_prefix(filepath))
                    ext = os.path.splitext(filepath)[1].lower()
                    
                    if norm_path in ThumbnailLoader.inst().cache:
                        widget.set_preview_image(ThumbnailLoader.inst().cache[norm_path])
                    elif ext in _thumb_exts:
                        ThumbnailLoader.inst().get_thumbnail(filepath, target_thumb_size)
                        if widget.placeholder_pixmap:
                            widget.set_placeholder(widget.placeholder_pixmap)
                    elif widget.placeholder_pixmap:
                        widget.set_placeholder(widget.placeholder_pixmap)
                        
        self._commit_index = end
        QTimer.singleShot(0, lambda: self._commit_batch(session_id))


class SorterListView(SorterBaseListView):
    """List View (ListMode) showing thumbnails and details (filename, size)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.ListMode)
        self.setSpacing(1)
        self.icon_size = 44
        
        # Переопределяем stylesheet: компактные строки без лишних отступов
        self.setStyleSheet("""
            QListWidget {
                background-color: #1e1e1e;
                border: none;
                outline: none;
            }
            QListWidget::item {
                background-color: #2b2b2b;
                color: #ddd;
                border: none;
                border-bottom: 1px solid #333;
                border-radius: 0px;
                margin: 0px;
                padding: 0px;
            }
            QListWidget::item:first {
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QListWidget::item:last {
                border-bottom: none;
                border-bottom-left-radius: 4px;
                border-bottom-right-radius: 4px;
            }
            QListWidget::item:hover {
                background-color: #333333;
            }
            QListWidget::item:selected {
                background-color: #1e3a8a;
                border-color: #3b82f6;
                color: white;
            }
        """)

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.icon_size = min(128, self.icon_size + 8)
            else:
                self.icon_size = max(32, self.icon_size - 8)
            
            # Scale all items
            for i in range(self.count()):
                item = self.item(i)
                widget = self.itemWidget(item)
                if widget and hasattr(widget, 'set_icon_size'):
                    widget.set_icon_size(self.icon_size)
                    item.setSizeHint(widget.sizeHint())
                    
                    # Reload cached thumbnail if exists
                    filepath = widget.filepath
                    norm_path = os.path.normpath(strip_long_path_prefix(filepath))
                    if norm_path in ThumbnailLoader.inst().cache:
                        widget.set_preview_image(ThumbnailLoader.inst().cache[norm_path])
                    elif widget.placeholder_pixmap:
                        widget.set_placeholder(widget.placeholder_pixmap)
                        
            self.doItemsLayout()
            self.viewport().update()
            event.accept()
        else:
            super().wheelEvent(event)


