import os
import logging
from typing import Any
from PyQt6.QtCore import Qt, QAbstractListModel, QModelIndex, QRect, QPoint, QSize, QEvent, QRectF
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QMouseEvent
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle
from PyQt6.QtSvg import QSvgRenderer

from config import AppContext, APP_DESIGN
from utils_common import format_size, get_folder_icon, is_subpath

class DuplicateVirtualModel(QAbstractListModel):
    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._all_items: list[dict[str, Any]] = []
        self._flat_items: list[dict[str, Any]] = []
        self._source_flat_items: list[dict[str, Any]] = []
        self._expanded_groups: set[Any] = set()
        self._group_files_cache: dict[Any, list[dict[str, Any]]] = {}
        self.source_folders: dict[str, Any] = {}
        self._parent_widget: Any = parent
        self.is_similar_mode: bool = False

    def set_items(self, items: list[dict[str, Any]], source_folders: dict[str, Any]) -> None:
        self.beginResetModel()
        self.source_folders = source_folders
        self._all_items = items
        self._group_files_cache = {}
        
        # Enrich files with source_folders metadata and build group cache
        for item in self._all_items:
            if item['type'] == 'file':
                path: str = item['path']
                is_protected = False
                is_reference = False
                color = "#555"
                for src_path, data in source_folders.items():
                    if is_subpath(path, src_path):
                        is_reference = data.get('reference', False)
                        is_protected = data.get('protected', False) or is_reference
                        color = data.get('color', '#555')
                        break
                item['is_protected'] = is_protected
                item['is_reference'] = is_reference
                item['color'] = color
                
                # Добавляем в кэш группы
                g_id = item['group_id']
                if g_id not in self._group_files_cache:
                    self._group_files_cache[g_id] = []
                self._group_files_cache[g_id].append(item)
                
        # By default, expand all groups
        self._expanded_groups = {item['id'] for item in self._all_items if item['type'] == 'group'}
        self.rebuild_flat_items()
        self._flat_items = list(self._source_flat_items)
        self.endResetModel()

    def rebuild_flat_items(self) -> None:
        new_flat: list[dict[str, Any]] = []
        current_group_visible = True
        for item in self._all_items:
            if item['type'] == 'group':
                new_flat.append(item)
                current_group_visible = item['id'] in self._expanded_groups
            elif item['type'] == 'file':
                if current_group_visible:
                    new_flat.append(item)
            elif item['type'] == 'empty_folder':
                new_flat.append(item)
        self._source_flat_items = new_flat

    def load_initial_chunk(self, chunk_size: int = 2000) -> None:
        """Мгновенно загружает и отображает первую порцию элементов"""
        self.beginResetModel()
        self._flat_items = self._source_flat_items[:chunk_size]
        self.endResetModel()

    def load_next_chunk(self, chunk_size: int = 2000) -> bool:
        """
        Фоново подгружает следующую порцию в конец списка.
        Возвращает True, если еще остались не подгруженные элементы.
        """
        current_len = len(self._flat_items)
        total_len = len(self._source_flat_items)
        if current_len >= total_len:
            return False
            
        next_chunk = self._source_flat_items[current_len:current_len + chunk_size]
        if not next_chunk:
            return False
            
        self.beginInsertRows(QModelIndex(), current_len, current_len + len(next_chunk) - 1)
        self._flat_items.extend(next_chunk)
        self.endInsertRows()
        return len(self._flat_items) < total_len

    def toggle_group_expand(self, group_id: Any) -> None:
        """
        Мгновенно раскрывает или сворачивает группу дубликатов точечной вставкой/удалением.
        Устраняет зависания endResetModel() при кликах.
        """
        # Ищем индекс группы в текущем _flat_items
        group_idx = -1
        for idx, item in enumerate(self._flat_items):
            if item['type'] == 'group' and item['id'] == group_id:
                group_idx = idx
                break
        
        if group_idx == -1:
            return
            
        is_expanded = group_id in self._expanded_groups
        
        if is_expanded:
            # Сворачиваем группу: удаляем дочерние файлы из _flat_items
            self._expanded_groups.remove(group_id)
            
            # Находим, сколько файлов этой группы идет следом за ней в _flat_items
            files_to_remove = 0
            for i in range(group_idx + 1, len(self._flat_items)):
                if self._flat_items[i]['type'] == 'file' and self._flat_items[i]['group_id'] == group_id:
                    files_to_remove += 1
                else:
                    break
                    
            if files_to_remove > 0:
                self.beginRemoveRows(QModelIndex(), group_idx + 1, group_idx + files_to_remove)
                del self._flat_items[group_idx + 1 : group_idx + 1 + files_to_remove]
                self.endRemoveRows()
        else:
            # Раскрываем группу: вставляем дочерние файлы из кэша
            self._expanded_groups.add(group_id)
            group_files = self._group_files_cache.get(group_id, [])
            
            if group_files:
                self.beginInsertRows(QModelIndex(), group_idx + 1, group_idx + len(group_files))
                # Вставляем файлы группы сразу за заголовком
                for f_idx, f in enumerate(group_files):
                    self._flat_items.insert(group_idx + 1 + f_idx, f)
                self.endInsertRows()

    def expand_all(self) -> None:
        self.beginResetModel()
        self._expanded_groups = {item['id'] for item in self._all_items if item['type'] == 'group'}
        self.rebuild_flat_items()
        self._flat_items = list(self._source_flat_items)
        self.endResetModel()

    def collapse_all(self) -> None:
        self.beginResetModel()
        self._expanded_groups.clear()
        self.rebuild_flat_items()
        self._flat_items = list(self._source_flat_items)
        self.endResetModel()

    def append_items_chunk(self, chunk: list[dict[str, Any]]) -> None:
        """Appends a chunk of pre-enriched items to the model and updates the group cache."""
        self._all_items.extend(chunk)
        for item in chunk:
            if item['type'] == 'file':
                g_id = item['group_id']
                if g_id not in self._group_files_cache:
                    self._group_files_cache[g_id] = []
                self._group_files_cache[g_id].append(item)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._flat_items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= len(self._flat_items):
            return None
        item = self._flat_items[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return item
        return None

    def parent_widget(self) -> Any:
        return self._parent_widget

    def calculate_group_status(self, group_id: Any) -> tuple[int, int, int]:
        """
        Calculates group status for coloring logic.
        Returns:
            (marked_files, effective_unmarked, total_files)
        """
        group_files = self._group_files_cache.get(group_id, [])
        if not group_files:
            return 0, 0, 0
        
        total_files = len(group_files)
        marked_files = sum(1 for f in group_files if f.get('is_marked', 0) == 1)
        unmarked_files = total_files - marked_files
        
        # Считаем количество защищенных файлов среди невыделенных
        unmarked_protected = sum(1 for f in group_files if f.get('is_marked', 0) == 0 and f.get('is_protected', False))
        
        # Эффективное число спасенных файлов (все защищенные сжимаются до одного)
        if unmarked_protected > 0:
            effective_unmarked = (unmarked_files - unmarked_protected) + 1
        else:
            effective_unmarked = unmarked_files
            
        return marked_files, effective_unmarked, total_files


class DuplicateDelegate(QStyledItemDelegate):
    def __init__(self, parent: Any = None, is_similar_mode: bool = False) -> None:
        super().__init__(parent)
        self.is_similar_mode = is_similar_mode
        self.icons_dir = AppContext.find_resource_dir("icons")
        self.renderers = {}

    def get_renderer(self, name: str) -> QSvgRenderer:
        if name not in self.renderers:
            path = os.path.join(self.icons_dir, name)
            self.renderers[name] = QSvgRenderer(path)
        return self.renderers[name]

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(100, 32)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        if not index.isValid():
            return
        
        item = index.data(Qt.ItemDataRole.UserRole)
        if not item:
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = option.rect
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)

        if item['type'] == 'group':
            # --- Paint Group Header ---
            # Вычисляем состояние выделения файлов в этой группе через модель (тестируемая логика)
            marked_files, effective_unmarked, total_files = index.model().calculate_group_status(item['id'])
            
            # Подбираем цвет фона в зависимости от статуса группы
            if self.is_similar_mode:
                bg_color = QColor("#2a2a2a") if not is_hovered else QColor("#333333")
            else:
                if marked_files == 0:
                    # Стандартный темно-серый
                    bg_color = QColor("#2a2a2a") if not is_hovered else QColor("#333333")
                elif effective_unmarked == 1:
                    # Зеленоватый приглушенный (выделено все, кроме одного логического файла)
                    bg_color = QColor("#1e3a24") if not is_hovered else QColor("#274d30")
                else:
                    # Красноватый приглушенный (выделены некоторые, но осталось больше одного логического файла)
                    bg_color = QColor("#3c1e1e") if not is_hovered else QColor("#4f2727")
                
            painter.fillRect(rect, bg_color)
            
            # Левая акцентная полоска для яркого визуального индикатора
            if marked_files > 0 and not self.is_similar_mode:
                accent_color = QColor("#10b981") if effective_unmarked == 1 else QColor("#ef4444")
                painter.fillRect(rect.left(), rect.top(), 4, rect.height(), accent_color)
            
            # Bottom border
            painter.setPen(QPen(QColor("#1a1a1a"), 1))
            painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

            # Expand/Collapse Chevron
            is_expanded = item['id'] in index.model()._expanded_groups
            arrow_str = "▼" if is_expanded else "▶"
            painter.setPen(QPen(QColor("#888888")))
            font_arrow = QFont("Segoe UI", 9)
            painter.setFont(font_arrow)
            painter.drawText(QRect(rect.left() + 8, rect.top() + (rect.height() - 14) // 2, 14, 14), Qt.AlignmentFlag.AlignCenter, arrow_str)

            # Checkbox
            cb_size = 16
            cb_x = rect.left() + 28
            cb_y = rect.top() + (rect.height() - cb_size) // 2
            cb_rect = QRect(cb_x, cb_y, cb_size, cb_size)
            
            painter.setPen(QPen(QColor("#666666"), 1))
            painter.setBrush(QBrush(QColor("#333333")))
            painter.drawRoundedRect(cb_rect, 3, 3)
            
            if marked_files > 0:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor("#3b82f6")))
                painter.drawRoundedRect(cb_rect, 3, 3)
                
                painter.setPen(QPen(QColor("#ffffff"), 2))
                if effective_unmarked > 0:
                    painter.drawLine(cb_x + 4, cb_y + cb_size // 2, cb_x + cb_size - 4, cb_y + cb_size // 2)
                else:
                    painter.drawLine(cb_x + 4, cb_y + 8, cb_x + 7, cb_y + 11)
                    painter.drawLine(cb_x + 7, cb_y + 11, cb_x + 12, cb_y + 4)

            # Name and wasted stats
            name_font = QFont("Segoe UI", 10)
            name_font.setBold(True)
            painter.setFont(name_font)
            painter.setPen(QPen(QColor("#eeeeee")))
            
            display_name = item.get('display_name')
            group_files = index.model()._group_files_cache.get(item['id'], [])
            first_file = "Unknown"
            if group_files:
                first_file = os.path.basename(group_files[0].get('path', 'Unknown'))
            
            is_ru = (AppContext.LANG == "RU")
            if getattr(index.model(), 'is_similar_mode', False):
                display_name = f"Похожие на: {first_file}" if is_ru else f"Similar to: {first_file}"
            elif not display_name:
                display_name = f"Копии: {first_file}" if is_ru else f"Copies: {first_file}"
            
            # Formatted text e.g. (5 / 6.5mb)
            try:
                g_size = item.get('size')
                if not g_size:
                    display_text = f"{display_name}  ({item.get('file_count', 0)})"
                else:
                    if getattr(index.model(), 'is_similar_mode', False):
                        size_fmt = format_size(g_size)
                    else:
                        size_fmt = format_size(g_size * item.get('file_count', 0))
                    display_text = f"{display_name}  ({item.get('file_count', 0)} / {size_fmt})"
                
                text_rect = QRect(rect.left() + 50, rect.top(), 600, rect.height())
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(display_text))
            except Exception as e:
                logging.error(f"Draw Group Text Error: {e}")

            # Draw participating color indicators
            indicators_x = rect.right() - 120
            # Resolve participating colors for this group
            colors: list[str] = []
            has_ref = False
            has_prot = False
            group_files = index.model()._group_files_cache.get(item['id'], [])
            for child in group_files:
                if child.get('is_reference'): has_ref = True
                elif child.get('is_protected'): has_prot = True
                elif child.get('color') and child['color'] not in colors:
                    colors.append(child['color'])
            
            # Paint indicators
            indicator_y = rect.top() + (rect.height() - 12) // 2
            curr_x = indicators_x
            if has_ref:
                # Star
                r = self.get_renderer("star-color.svg")
                r_size = 14
                ry = rect.top() + (rect.height() - r_size) // 2
                r.render(painter, QRectF(curr_x, ry, r_size, r_size))
                curr_x += 18
            if has_prot:
                # Lock
                r = self.get_renderer("lock-color.svg")
                r_size = 14
                ry = rect.top() + (rect.height() - r_size) // 2
                r.render(painter, QRectF(curr_x, ry, r_size, r_size))
                curr_x += 18
            for col in colors:
                painter.setBrush(QBrush(QColor(col)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(curr_x, indicator_y + 2, 8, 8)
                curr_x += 12

        elif item['type'] == 'file':
            # --- Paint File Row ---
            is_protected = item.get('is_protected', False)
            bg_color = QColor("#2d2d2d") if not is_protected else QColor("#3a3420")
            if is_hovered:
                bg_color = QColor("#363636") if not is_protected else QColor("#443c25")
            if is_selected:
                bg_color = QColor("#3b82f6") if not is_protected else QColor("#544b30")
                
            painter.fillRect(rect, bg_color)
            
            # Bottom border
            painter.setPen(QPen(QColor("#232323"), 1))
            painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

            # Checkbox
            if not is_protected:
                cb_size = 16
                cb_x = rect.left() + 30
                cb_y = rect.top() + (rect.height() - cb_size) // 2
                cb_rect = QRect(cb_x, cb_y, cb_size, cb_size)
                
                # Checkbox background and border
                painter.setPen(QPen(QColor("#666666"), 1))
                painter.setBrush(QBrush(QColor("#333333")))
                painter.drawRoundedRect(cb_rect, 3, 3)
                
                if item.get('is_marked', 0):
                    # Draw accent fill and checkmark
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QBrush(QColor("#3b82f6")))
                    painter.drawRoundedRect(cb_rect, 3, 3)
                    
                    painter.setPen(QPen(QColor("#ffffff"), 2))
                    painter.drawLine(cb_x + 4, cb_y + 8, cb_x + 7, cb_y + 11)
                    painter.drawLine(cb_x + 7, cb_y + 11, cb_x + 12, cb_y + 4)

            # Star/Lock indicator inside the row
            icon_x = rect.left() + 50
            if is_protected:
                is_reference = item.get('is_reference', False)
                icon_name = "star-color.svg" if is_reference else "lock-color.svg"
                r = self.get_renderer(icon_name)
                r_size = 14
                ry = rect.top() + (rect.height() - r_size) // 2
                r.render(painter, QRectF(icon_x, ry, r_size, r_size))
            else:
                # Color Dot indicating source folder
                dot_color = item.get('color', '#555')
                painter.setBrush(QBrush(QColor(dot_color)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(icon_x + 3, rect.top() + (rect.height() - 10) // 2, 10, 10)

            # Name and Folder Path
            name_font = QFont("Segoe UI", 9)
            name_font.setBold(True)
            painter.setFont(name_font)
            name_color = QColor("#fbbf24") if is_protected else QColor("#eeeeee")
            painter.setPen(QPen(name_color))
            
            filename = os.path.basename(item['path'])
            folder = os.path.dirname(item['path'])
            
            # Draw file name
            painter.drawText(rect.left() + 75, rect.top(), 230, rect.height(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, filename)
            
            # Draw similarity percentage + size if in similar mode
            if getattr(index.model(), 'is_similar_mode', False):
                pct = item.get('similarity_pct', 100)
                pct_str = f"{pct}%"
                pct_font = QFont("Segoe UI", 9)
                pct_font.setBold(True)
                painter.setFont(pct_font)
                
                if pct == 100:
                    pct_color = QColor("#10b981")
                elif pct >= 90:
                    pct_color = QColor("#3b82f6")
                else:
                    pct_color = QColor("#f59e0b")
                    
                painter.setPen(QPen(pct_color))
                painter.drawText(rect.left() + 315, rect.top(), 45, rect.height(),
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, pct_str)

                # Размер файла после процента
                size_str = format_size(item.get('size', 0))
                size_font = QFont("Segoe UI", 9)
                painter.setFont(size_font)
                painter.setPen(QPen(QColor("#cccccc")))
                painter.drawText(rect.left() + 363, rect.top(), 60, rect.height(),
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, size_str)

                # Метаданные (например, разрешение 1920x1080 | 5000 kbps)
                meta_str = item.get('metadata', '')
                if meta_str:
                    meta_font = QFont("Segoe UI", 8)
                    painter.setFont(meta_font)
                    painter.setPen(QPen(QColor("#8b5cf6"))) # Светло-фиолетовый акцент для метаданных
                    painter.drawText(rect.left() + 425, rect.top(), 130, rect.height(),
                                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, meta_str)

                # Путь к папке (еще правее в similar-режиме)
                path_font = QFont("Consolas", 8)
                painter.setFont(path_font)
                painter.setPen(QPen(QColor("#888888")))
                painter.drawText(rect.left() + 555, rect.top(), rect.width() - 565, rect.height(),
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, folder)
            else:
                # Draw folder path (обычный режим дублей)
                path_font = QFont("Consolas", 8)
                painter.setFont(path_font)
                painter.setPen(QPen(QColor("#aaaaaa")))
                painter.drawText(rect.left() + 375, rect.top(), rect.width() - 385, rect.height(),
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, folder)

        elif item['type'] == 'empty_folder':
            # --- Paint Empty Folder ---
            bg_color = QColor("#222222") if not is_hovered else QColor("#2a2a2a")
            if is_selected:
                bg_color = QColor("#3b82f6")
            painter.fillRect(rect, bg_color)
            
            painter.setPen(QPen(QColor("#2b2b2b"), 1))
            painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

            # Checkbox
            cb_size = 16
            cb_x = rect.left() + 10
            cb_y = rect.top() + (rect.height() - cb_size) // 2
            cb_rect = QRect(cb_x, cb_y, cb_size, cb_size)
            
            painter.setPen(QPen(QColor("#666666"), 1))
            painter.setBrush(QBrush(QColor("#333333")))
            painter.drawRoundedRect(cb_rect, 3, 3)
            
            if item.get('is_marked', 0):
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor("#3b82f6")))
                painter.drawRoundedRect(cb_rect, 3, 3)
                
                painter.setPen(QPen(QColor("#ffffff"), 2))
                painter.drawLine(cb_x + 4, cb_y + 8, cb_x + 7, cb_y + 11)
                painter.drawLine(cb_x + 7, cb_y + 11, cb_x + 12, cb_y + 4)

            # Folder Icon (Simulated or painted)
            r = self.get_renderer("folder-color.svg")
            r_size = 14
            ry = rect.top() + (rect.height() - r_size) // 2
            r.render(painter, QRectF(rect.left() + 32, ry, r_size, r_size))

            # Path
            path_font = QFont("Consolas", 9)
            painter.setFont(path_font)
            painter.setPen(QPen(QColor("#cccccc")))
            painter.drawText(rect.left() + 54, rect.top(), rect.width() - 64, rect.height(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, item['path'])

        painter.restore()

    def editorEvent(self, event: Any, model: Any, option: QStyleOptionViewItem, index: QModelIndex) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            item = index.data(Qt.ItemDataRole.UserRole)
            if not item:
                return False

            if item['type'] == 'group':
                model.toggle_group_expand(item['id'])
                return True

        return False
