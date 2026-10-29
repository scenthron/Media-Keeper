"""
Модуль виртуальной сетки миниатюр (Grid View) для результатов визуального ИИ-поиска.
Обеспечивает легкий, быстрый и отзывчивый рендеринг 5 000+ элементов с асинхронной загрузкой превью,
синхронизацией отметок чекбоксов, зумом и быстрым предпросмотром при наведении.
"""

import os
import time
import logging
from collections import OrderedDict
from PyQt6.QtWidgets import (
    QWidget, QListView, QStyledItemDelegate, QStyle, QDialog,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDoubleSpinBox,
    QSpinBox, QGraphicsOpacityEffect, QAbstractItemView
)
from PyQt6.QtCore import (
    Qt, QSize, QRect, QPoint, pyqtSignal, QTimer, QObject,
    QAbstractListModel, QModelIndex, QSortFilterProxyModel, QEvent
)
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QPixmap, QCursor,
    QFontMetrics, QKeySequence
)

from config import AppContext
from modules.shared import ui_theme
from utils_io import ensure_long_path, strip_long_path_prefix
from modules.sorter.thumbnail_loader import ThumbnailLoader
from modules.sorter.ui_preview_popup import LargePreviewPopup
from modules.sorter.logic_config import ConfigManager
from utils_extensions import VIDEO_EXTS, AUDIO_EXTS, IMAGE_EXTS


class AiGridItem:
    """Хранит данные одного элемента результата ИИ-поиска для отображения в сетке."""
    __slots__ = (
        "path", "name", "size", "confidence", "tree_item",
        "bbox", "item_type", "tag_scores", "color_hex"
    )

    def __init__(self, path: str, name: str, size: int, confidence: float,
                 tree_item, bbox=None, item_type="face",
                 tag_scores=None, color_hex="#555"):
        self.path = path
        self.name = name
        self.size = size
        self.confidence = confidence  # 0.0 - 100.0
        self.tree_item = tree_item
        self.bbox = bbox
        self.item_type = item_type
        self.tag_scores = tag_scores or {}
        self.color_hex = color_hex or "#555"


class AiResultsListModel(QAbstractListModel):
    """
    Легковесная модель списка файлов для сетки результатов ИИ-поиска.
    Делегирует состояние чекбокса в соответствующий QTreeWidgetItem.
    """
    check_state_changed = pyqtSignal(object, Qt.CheckState)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: list[AiGridItem] = []

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.items)):
            return None

        item = self.items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return item.name
        elif role == Qt.ItemDataRole.CheckStateRole:
            if item.tree_item:
                return item.tree_item.checkState(0)
            return Qt.CheckState.Unchecked
        elif role == Qt.ItemDataRole.UserRole:
            return item
        return None

    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or not (0 <= index.row() < len(self.items)):
            return False

        if role == Qt.ItemDataRole.CheckStateRole:
            item = self.items[index.row()]
            if item.tree_item:
                item.tree_item.setCheckState(0, value)
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
            self.check_state_changed.emit(item.tree_item, value)
            return True
        return False

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsUserCheckable
        )

    def set_items(self, items: list[AiGridItem]):
        self.beginResetModel()
        self.items = list(items)
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self.items.clear()
        self.endResetModel()

    def get_item(self, row: int) -> AiGridItem | None:
        if 0 <= row < len(self.items):
            return self.items[row]
        return None

    def remove_paths(self, paths_set: set[str]):
        normalized_targets = {os.path.normpath(p) for p in paths_set}
        new_items = [it for it in self.items if os.path.normpath(it.path) not in normalized_targets]
        if len(new_items) != len(self.items):
            self.beginResetModel()
            self.items = new_items
            self.endResetModel()

    def notify_all_changed(self):
        if self.items:
            first = self.index(0, 0)
            last = self.index(len(self.items) - 1, 0)
            self.dataChanged.emit(first, last, [Qt.ItemDataRole.CheckStateRole])

    def notify_item_changed(self, tree_item):
        for idx, it in enumerate(self.items):
            if it.tree_item == tree_item:
                idx_model = self.index(idx, 0)
                self.dataChanged.emit(idx_model, idx_model, [Qt.ItemDataRole.CheckStateRole])
                break


class AiResultsFilterProxyModel(QSortFilterProxyModel):
    """
    Прокси-модель фильтрации для сетки:
    Отображает только те элементы, которые видимы в дереве результатов (не скрыты пост-фильтром).
    """
    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        src_model = self.sourceModel()
        if not src_model:
            return True
        item = src_model.get_item(source_row)
        if not item or not item.tree_item:
            return True

        if item.tree_item.isHidden():
            return False

        parent = item.tree_item.parent()
        if parent and parent.isHidden():
            return False

        return True


class AiCardDelegate(QStyledItemDelegate):
    """
    Кастомный делегат карточки файла в сетке результатов.
    Отрисовывает:
      - Фон карточки с рамкой выделения/наведения
      - Кликабельный чекбокс (верхний левый угол)
      - Бейдж процента схожести (верхний правый угол)
      - Превью миниатюры (по центру, с сохранением пропорций)
      - Цветовую метку папки-источника
      - Название файла с эллипсисом (внизу)
    """
    MAX_CACHE_SIZE = 1500

    def __init__(self, parent=None, thumbnail_size: int = 130):
        super().__init__(parent)
        self.thumbnail_size = thumbnail_size
        self._pixmap_cache: OrderedDict[str, QPixmap] = OrderedDict()

    def set_thumbnail_size(self, size: int):
        self.thumbnail_size = max(70, min(320, size))

    def set_cached_pixmap(self, norm_path: str, pixmap: QPixmap):
        if norm_path in self._pixmap_cache:
            self._pixmap_cache.move_to_end(norm_path)
            self._pixmap_cache[norm_path] = pixmap
        else:
            self._pixmap_cache[norm_path] = pixmap
            if len(self._pixmap_cache) > self.MAX_CACHE_SIZE:
                self._pixmap_cache.popitem(last=False)

    def sizeHint(self, option, index: QModelIndex) -> QSize:
        w = self.thumbnail_size + 16
        h = self.thumbnail_size + 50
        return QSize(w, h)

    def paint(self, painter: QPainter, option, index: QModelIndex):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        item: AiGridItem = index.data(Qt.ItemDataRole.UserRole)
        if not item:
            painter.restore()
            return

        rect = option.rect.adjusted(3, 3, -3, -3)
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        # 1. Фон карточки
        if is_selected:
            bg_color = QColor(30, 58, 95)
            border_color = QColor(59, 130, 246)
            border_width = 2
        elif is_hovered:
            bg_color = QColor(42, 46, 55)
            border_color = QColor(96, 165, 250)
            border_width = 1
        else:
            bg_color = QColor(32, 34, 38)
            border_color = QColor(51, 56, 66)
            border_width = 1

        painter.setPen(QPen(border_color, border_width))
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(rect, 6, 6)

        # 2. Чекбокс (верхний левый угол)
        chk_rect = QRect(rect.left() + 6, rect.top() + 6, 16, 16)
        check_state = index.data(Qt.ItemDataRole.CheckStateRole)
        if check_state == Qt.CheckState.Checked:
            painter.setPen(QPen(QColor(37, 99, 235), 1))
            painter.setBrush(QBrush(QColor(59, 130, 246)))
            painter.drawRoundedRect(chk_rect, 3, 3)

            # Белая галочка
            painter.setPen(QPen(Qt.GlobalColor.white, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p1 = QPoint(chk_rect.left() + 4, chk_rect.top() + 8)
            p2 = QPoint(chk_rect.left() + 7, chk_rect.top() + 11)
            p3 = QPoint(chk_rect.left() + 12, chk_rect.top() + 5)
            painter.drawLine(p1, p2)
            painter.drawLine(p2, p3)
        else:
            painter.setPen(QPen(QColor(100, 100, 100), 1))
            painter.setBrush(QBrush(QColor(43, 43, 43)))
            painter.drawRoundedRect(chk_rect, 3, 3)

        # 3. Бейдж сходства (верхний правый угол)
        if item.confidence > 0:
            sim_text = f"{item.confidence:.0f}%" if item.confidence.is_integer() else f"{item.confidence:.1f}%"
            font_badge = QFont(option.font)
            font_badge.setPointSize(9)
            font_badge.setBold(True)
            painter.setFont(font_badge)

            fm = QFontMetrics(font_badge)
            text_w = fm.horizontalAdvance(sim_text)
            badge_w = text_w + 8
            badge_h = 16
            badge_rect = QRect(rect.right() - badge_w - 6, rect.top() + 6, badge_w, badge_h)

            # Цвет бейджа: зеленый при высоком сходстве, синий при среднем
            if item.confidence >= 80.0:
                badge_bg = QColor(6, 95, 70, 220)
                badge_border = QColor(16, 185, 129)
                badge_text_color = QColor(209, 250, 229)
            else:
                badge_bg = QColor(29, 78, 216, 220)
                badge_border = QColor(96, 165, 250)
                badge_text_color = QColor(224, 242, 254)

            painter.setPen(QPen(badge_border, 1))
            painter.setBrush(QBrush(badge_bg))
            painter.drawRoundedRect(badge_rect, 3, 3)

            painter.setPen(badge_text_color)
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, sim_text)

        # 4. Область миниатюры
        thumb_top = rect.top() + 26
        thumb_bottom = rect.bottom() - 22
        thumb_rect = QRect(rect.left() + 6, thumb_top, rect.width() - 12, max(10, thumb_bottom - thumb_top))

        norm_path = os.path.normpath(strip_long_path_prefix(item.path))
        cached_pix = self._pixmap_cache.get(norm_path)

        if cached_pix and not cached_pix.isNull():
            scaled_pix = cached_pix.scaled(
                thumb_rect.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            # Центрируем картинку внутри области превью
            target_x = thumb_rect.left() + (thumb_rect.width() - scaled_pix.width()) // 2
            target_y = thumb_rect.top() + (thumb_rect.height() - scaled_pix.height()) // 2
            painter.drawPixmap(target_x, target_y, scaled_pix)
        else:
            # Плейсхолдер при фоновой загрузке
            painter.setPen(QPen(QColor(40, 40, 40), 1))
            painter.setBrush(QBrush(QColor(22, 22, 24)))
            painter.drawRoundedRect(thumb_rect, 4, 4)

            # Запрос асинхронной загрузки через ThumbnailLoader
            target_load_size = QSize(self.thumbnail_size * 2, self.thumbnail_size * 2)
            ThumbnailLoader.inst().get_thumbnail(item.path, target_load_size)

        # 5. Цветовой маркер источника (если задан цвет папки)
        if item.color_hex and item.color_hex != "#555":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(item.color_hex)))
            dot_rect = QRect(rect.left() + 26, rect.top() + 11, 6, 6)
            painter.drawEllipse(dot_rect)

        # 6. Имя файла внизу
        caption_rect = QRect(rect.left() + 4, rect.bottom() - 20, rect.width() - 8, 16)
        font_caption = QFont(option.font)
        font_caption.setPointSize(9)
        painter.setFont(font_caption)
        painter.setPen(QColor(226, 232, 240))

        fm_caption = QFontMetrics(font_caption)
        elided_name = fm_caption.elidedText(item.name, Qt.TextElideMode.ElideMiddle, caption_rect.width())
        painter.drawText(caption_rect, Qt.AlignmentFlag.AlignCenter, elided_name)

        painter.restore()

    def editorEvent(self, event, model, option, index: QModelIndex) -> bool:
        rect = option.rect.adjusted(3, 3, -3, -3)
        chk_rect = QRect(rect.left() + 4, rect.top() + 4, 22, 22)

        if event.type() == QEvent.Type.MouseButtonRelease:
            pos = event.position().toPoint()
            if chk_rect.contains(pos):
                cur_state = index.data(Qt.ItemDataRole.CheckStateRole)
                new_state = Qt.CheckState.Unchecked if cur_state == Qt.CheckState.Checked else Qt.CheckState.Checked
                model.setData(index, new_state, Qt.ItemDataRole.CheckStateRole)
                return True

        return super().editorEvent(event, model, option, index)


class HoverSettingsDialog(QDialog):
    """
    Диалог настройки быстрого просмотра по наведению:
    позволяет настроить задержку появления и размеры окна предпросмотра,
    сохраняя параметры в settings.ini.
    """
    settings_saved = pyqtSignal(float, QSize)

    def __init__(self, parent=None, initial_delay: float = 0.4, initial_size: QSize = None):
        super().__init__(parent)
        self.setWindowTitle(AppContext.tr("cln_ai_hover_settings"))
        self.setFixedWidth(320)
        self.setStyleSheet("""
            QDialog {
                background-color: #202020;
                border: 1px solid #444;
                border-radius: 6px;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 11px;
                font-weight: bold;
            }
            QDoubleSpinBox, QSpinBox {
                background-color: #2b2b2b;
                color: white;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px;
                font-size: 11px;
                font-weight: bold;
            }
            QDoubleSpinBox:focus, QSpinBox:focus {
                border: 1px solid #3b82f6;
            }
            QPushButton {
                background-color: #333;
                color: white;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3b82f6;
                border-color: #2563eb;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 1. Задержка
        row_delay = QHBoxLayout()
        row_delay.addWidget(QLabel(AppContext.tr("cln_ai_hover_delay")))
        self.spin_delay = QDoubleSpinBox()
        self.spin_delay.setRange(0.0, 5.0)
        self.spin_delay.setSingleStep(0.1)
        self.spin_delay.setDecimals(1)
        self.spin_delay.setSuffix(f" {AppContext.tr('cln_ai_hover_sec')}")
        self.spin_delay.setValue(initial_delay)
        row_delay.addWidget(self.spin_delay)
        layout.addLayout(row_delay)

        # 2. Размеры окна
        lbl_size = QLabel(AppContext.tr("cln_ai_hover_size"))
        layout.addWidget(lbl_size)

        row_dims = QHBoxLayout()
        self.spin_w = QSpinBox()
        self.spin_w.setRange(360, 1600)
        self.spin_w.setSingleStep(40)
        curr_w = initial_size.width() if initial_size else 640
        self.spin_w.setValue(curr_w)

        self.spin_h = QSpinBox()
        self.spin_h.setRange(260, 1200)
        self.spin_h.setSingleStep(30)
        curr_h = initial_size.height() if initial_size else 520
        self.spin_h.setValue(curr_h)

        row_dims.addWidget(QLabel("W:"))
        row_dims.addWidget(self.spin_w)
        row_dims.addWidget(QLabel("H:"))
        row_dims.addWidget(self.spin_h)
        layout.addLayout(row_dims)

        # 3. Кнопки
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_reset = QPushButton(AppContext.tr("cln_ai_btn_reset"))
        self.btn_reset.clicked.connect(self._reset_defaults)
        btn_layout.addWidget(self.btn_reset)

        btn_layout.addStretch(1)

        self.btn_cancel = QPushButton(AppContext.tr("cln_btn_cancel") if hasattr(AppContext, "tr") else "Отмена")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("OK")
        self.btn_save.clicked.connect(self._save_settings)
        btn_layout.addWidget(self.btn_save)

        layout.addLayout(btn_layout)

    def _reset_defaults(self):
        self.spin_delay.setValue(0.4)
        self.spin_w.setValue(640)
        self.spin_h.setValue(520)

    def _save_settings(self):
        delay = float(self.spin_delay.value())
        size = QSize(self.spin_w.value(), self.spin_h.value())

        # Сохранение в settings.ini
        try:
            cfg = ConfigManager.load()
            cfg["hover_delay"] = delay
            cfg["hover_preview_w"] = size.width()
            cfg["hover_preview_h"] = size.height()
            ConfigManager.save(cfg)
        except Exception as e:
            logging.error(f"Не удалось сохранить настройки ховера в settings.ini: {e}", exc_info=True)

        self.settings_saved.emit(delay, size)
        self.accept()


class AiResultsGridView(QListView):
    """
    Виртуальная сетка миниатюр для результатов ИИ-поиска.
    Поддерживает:
      - Асинхронную догрузку миниатюр
      - Синхронизацию чекбоксов и выделения с деревом
      - Быстрый просмотр по наведению курсора (Hover Preview)
      - Масштабирование размера плиток
    """
    file_selected = pyqtSignal(str)
    item_double_clicked = pyqtSignal(str)
    zoom_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setUniformItemSizes(True)
        self.setMovement(QListView.Movement.Static)
        self.setSpacing(8)
        self.setMouseTracking(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        self.setStyleSheet("""
            QListView {
                background-color: #1a1a1a;
                border: none;
                outline: none;
                color: #eee;
            }
            QScrollBar:vertical {
                background: #1e1e1e;
                width: 10px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background: #3a3a3a;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #4a4a4a;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        self.delegate = AiCardDelegate(self, thumbnail_size=130)
        self.setItemDelegate(self.delegate)

        # Асинхронный загрузчик миниатюр
        ThumbnailLoader.inst().thumbnail_ready.connect(self._on_thumbnail_ready)

        # Конфигурация быстрого просмотра по наведению
        self.hover_enabled = True
        self.hover_delay = 0.4
        self.popup_size = QSize(640, 520)
        self._load_hover_config()

        self.hover_timer = QTimer(self)
        self.hover_timer.setSingleShot(True)
        self.hover_timer.timeout.connect(self._show_hover_popup)

        self.current_hover_index: QModelIndex = QModelIndex()
        self.current_hover_path: str = ""
        self.large_preview_popup: LargePreviewPopup | None = None
        self.popup_track_timer = QTimer(self)
        self.popup_track_timer.timeout.connect(self._track_popup_cursor)

        self.doubleClicked.connect(self._on_double_click)

    def _load_hover_config(self):
        try:
            cfg = ConfigManager.load()
            self.hover_delay = float(cfg.get("hover_delay", 0.4))
            w = int(cfg.get("hover_preview_w", 640))
            h = int(cfg.get("hover_preview_h", 520))
            self.popup_size = QSize(w, h)
        except Exception as e:
            logging.debug(f"Используются дефолтные параметры ховера: {e}")

    def set_thumbnail_size(self, size: int):
        self.delegate.set_thumbnail_size(size)
        self.setGridSize(QSize(size + 20, size + 56))
        self.doItemsLayout()
        self.viewport().update()

    def set_hover_enabled(self, enabled: bool):
        self.hover_enabled = enabled
        if not enabled:
            self._stop_hover()

    def set_hover_params(self, delay: float, size: QSize):
        self.hover_delay = delay
        self.popup_size = size

    def _on_thumbnail_ready(self, filepath: str, qimage):
        norm_path = os.path.normpath(strip_long_path_prefix(filepath))
        pixmap = QPixmap.fromImage(qimage)
        self.delegate.set_cached_pixmap(norm_path, pixmap)
        self.viewport().update()

    def _on_double_click(self, index: QModelIndex):
        if not index.isValid():
            return
        item: AiGridItem = index.data(Qt.ItemDataRole.UserRole)
        if item and item.path:
            self._stop_hover()
            self.item_double_clicked.emit(item.path)

    # -------------------------------------------------------------------------
    # Логика Hover Preview (Большой просмотр при наведении)
    # -------------------------------------------------------------------------
    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if not self.hover_enabled:
            return

        pos = event.position().toPoint()
        index = self.indexAt(pos)

        # Если курсор находится над открытым попапом (в глобальных координатах), не закрываем его
        if self.large_preview_popup and not self.large_preview_popup.isHidden():
            global_cursor = QCursor.pos()
            popup_geom = self.large_preview_popup.geometry()
            if popup_geom.adjusted(-8, -8, 8, 8).contains(global_cursor):
                return

        # Если курсор остался на той же самой плитке — не перезапускаем
        if index.isValid() and index == self.current_hover_index:
            return

        # Курсор ушел с плитки или перешел на другую! Немедленно закрываем старый попап
        self._stop_hover()

        # Если новая плитка валидна — запоминаем её и запускаем таймер
        if index.isValid():
            item: AiGridItem = index.data(Qt.ItemDataRole.UserRole)
            if item and item.path and os.path.exists(item.path):
                self.current_hover_index = index
                self.current_hover_path = ensure_long_path(item.path)
                self.hover_timer.start(int(self.hover_delay * 1000))

    def leaveEvent(self, event):
        super().leaveEvent(event)
        # Если курсор перешел внутрь попапа — не закрываем
        if self.large_preview_popup and not self.large_preview_popup.isHidden():
            global_cursor = QCursor.pos()
            popup_geom = self.large_preview_popup.geometry()
            if popup_geom.adjusted(-8, -8, 8, 8).contains(global_cursor):
                return
        self._stop_hover()

    def mousePressEvent(self, event):
        self._stop_hover()
        super().mousePressEvent(event)

    def hideEvent(self, event):
        self._stop_hover()
        super().hideEvent(event)

    def _stop_hover(self):
        self.hover_timer.stop()
        self.popup_track_timer.stop()

        if self.large_preview_popup is not None:
            popup = self.large_preview_popup
            self.large_preview_popup = None
            try:
                if hasattr(popup, 'cleanup'):
                    popup.cleanup()
                popup.hide()
                popup.close()
                popup.deleteLater()
            except Exception as e:
                logging.debug(f"Error closing large preview popup: {e}")

        self.current_hover_index = QModelIndex()
        self.current_hover_path = ""

    def _show_hover_popup(self):
        if not self.current_hover_path or not os.path.exists(self.current_hover_path):
            return

        ext = os.path.splitext(self.current_hover_path)[1].lower()
        if ext not in VIDEO_EXTS and ext not in AUDIO_EXTS and ext not in IMAGE_EXTS:
            return

        # Гарантируем, что любой старый попап полностью уничтожен перед созданием нового!
        if self.large_preview_popup is not None:
            old_popup = self.large_preview_popup
            self.large_preview_popup = None
            try:
                if hasattr(old_popup, 'cleanup'):
                    old_popup.cleanup()
                old_popup.hide()
                old_popup.close()
                old_popup.deleteLater()
            except Exception:
                pass

        win = self.window()
        self.large_preview_popup = LargePreviewPopup(self.current_hover_path, None, win)
        self.large_preview_popup.destroyed.connect(self._on_popup_destroyed)

        popup_w = self.popup_size.width()
        popup_h = self.popup_size.height()

        app_geom = win.geometry()
        pos = QCursor.pos()

        # Позиционирование рядом с курсором/плиткой
        if self.current_hover_index.isValid():
            rect = self.visualRect(self.current_hover_index)
            tile_pos = self.viewport().mapToGlobal(rect.topLeft())
            x = tile_pos.x() + rect.width() + 10
            y = tile_pos.y()
        else:
            x = pos.x() + 15
            y = pos.y() + 15

        # Коррекция выхода за границы окна
        if x + popup_w > app_geom.right():
            x = pos.x() - popup_w - 15
        if x < app_geom.left():
            x = app_geom.left() + 10

        if y + popup_h > app_geom.bottom():
            y = app_geom.bottom() - popup_h - 10
        if y < app_geom.top():
            y = app_geom.top() + 10

        self.large_preview_popup.setFixedSize(popup_w, popup_h)
        self.large_preview_popup.move(x, y)
        self.large_preview_popup.show()

        self.popup_track_timer.start(80)

    def _on_popup_destroyed(self):
        self.large_preview_popup = None
        self.popup_track_timer.stop()

    def _track_popup_cursor(self):
        if not self.large_preview_popup or self.large_preview_popup.isHidden():
            self.popup_track_timer.stop()
            return

        cursor_pos = QCursor.pos()
        popup_rect = self.large_preview_popup.geometry()

        # Если курсор внутри попапа — оставляем открытым
        if popup_rect.adjusted(-8, -8, 8, 8).contains(cursor_pos):
            return

        # Если курсор над текущей плиткой — оставляем открытым
        if self.current_hover_index.isValid():
            try:
                rect = self.visualRect(self.current_hover_index)
                global_rect = QRect(self.viewport().mapToGlobal(rect.topLeft()), rect.size())
                if global_rect.adjusted(-6, -6, 6, 6).contains(cursor_pos):
                    return
            except Exception:
                pass

        # Иначе закрываем
        self._stop_hover()

    def wheelEvent(self, event):
        self._stop_hover()
        # Масштабирование колесом мыши с зажатым Ctrl
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            step = 15 if delta > 0 else -15
            new_size = max(80, min(280, self.delegate.thumbnail_size + step))
            self.set_thumbnail_size(new_size)
            self.zoom_changed.emit(new_size)
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event):
        # Пробел переключает чекбокс текущего элемента
        if event.key() == Qt.Key.Key_Space:
            idx = self.currentIndex()
            if idx.isValid():
                cur_state = idx.data(Qt.ItemDataRole.CheckStateRole)
                new_state = Qt.CheckState.Unchecked if cur_state == Qt.CheckState.Checked else Qt.CheckState.Checked
                self.model().setData(idx, new_state, Qt.ItemDataRole.CheckStateRole)
                event.accept()
                return
        super().keyPressEvent(event)
