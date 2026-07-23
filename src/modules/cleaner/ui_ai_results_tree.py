import os
import logging
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem, QMenu, QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, pyqtSignal
from config import AppContext
from utils_common import format_size

class AiResultsTreeWidget(QWidget):
    """
    Виджет отображения ИИ-результатов в виде дерева с поддержкой 
    мгновенной динамической фильтрации по порогу схожести без пересборки.
    """
    selection_changed_signal = pyqtSignal(int, int)  # count, total_bytes
    item_preview_signal = pyqtSignal(str)           # filepath

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_cluster_results = False
        self.cluster_unique_sizes = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)
        self.tree.setStyleSheet("""
            QTreeWidget {
                background-color: #1a1a1a;
                border: none;
                outline: none;
                color: #eee;
            }
            QTreeWidget::item {
                padding: 6px;
                border-bottom: 1px solid #222;
            }
            QTreeWidget::item:selected {
                background-color: #2b2b2b;
                color: white;
            }
            QTreeWidget::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #666;
                border-radius: 3px;
                background-color: #2b2b2b;
            }
            QTreeWidget::indicator:hover {
                border-color: #3b82f6;
            }
            QTreeWidget::indicator:checked {
                background-color: #3b82f6;
                border: 1px solid #2563eb;
            }
            QTreeWidget::indicator:unchecked {
                background-color: #2b2b2b;
            }
        """)

        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)

        layout.addWidget(self.tree)

    def clear(self):
        self.tree.clear()
        self.is_cluster_results = False
        self.cluster_unique_sizes = []

    def apply_threshold_filter(self, target_similarity: float):
        """
        Мгновенно фильтрует элементы дерева по заданному порогу 
        без необходимости повторного сканирования или пересборки дерева.
        """
        root = self.tree.invisibleRootItem()
        self.tree.blockSignals(True)
        try:
            for i in range(root.childCount()):
                group_item = root.child(i)
                group_visible_children = 0

                if self.is_cluster_results:
                    target_size = int(target_similarity)
                    actual_size = group_item.childCount()
                    if actual_size < target_size:
                        group_item.setHidden(True)
                        for j in range(actual_size):
                            child = group_item.child(j)
                            if child.checkState(0) == Qt.CheckState.Checked:
                                child.setCheckState(0, Qt.CheckState.Unchecked)
                        if group_item.checkState(0) == Qt.CheckState.Checked:
                            group_item.setCheckState(0, Qt.CheckState.Unchecked)
                    else:
                        group_item.setHidden(False)
                else:
                    for j in range(group_item.childCount()):
                        child = group_item.child(j)
                        data = child.data(0, Qt.ItemDataRole.UserRole)
                        if data:
                            sim = data.get("confidence", 0.0)
                            if sim < target_similarity:
                                child.setHidden(True)
                                if child.checkState(0) == Qt.CheckState.Checked:
                                    child.setCheckState(0, Qt.CheckState.Unchecked)
                            else:
                                child.setHidden(False)
                                group_visible_children += 1

                    if group_visible_children == 0:
                        group_item.setHidden(True)
                        if group_item.checkState(0) == Qt.CheckState.Checked:
                            group_item.setCheckState(0, Qt.CheckState.Unchecked)
                    else:
                        group_item.setHidden(False)
        finally:
            self.tree.blockSignals(False)

        return self.get_visible_stats()

    def get_visible_stats(self):
        """Возвращает статистику по видимым элементам (групп, файлов, байтов)."""
        root = self.tree.invisibleRootItem()
        visible_groups = 0
        visible_files = 0
        visible_bytes = 0
        for i in range(root.childCount()):
            group_item = root.child(i)
            if not group_item.isHidden():
                visible_groups += 1
                for j in range(group_item.childCount()):
                    child = group_item.child(j)
                    if not child.isHidden():
                        visible_files += 1
                        data = child.data(0, Qt.ItemDataRole.UserRole)
                        if data and 'size' in data:
                            visible_bytes += data['size']
        return visible_groups, visible_files, visible_bytes

    def _on_selection_changed(self):
        items = self.tree.selectedItems()
        if items:
            item = items[0]
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and "path" in data:
                self.item_preview_signal.emit(data["path"])

    def _on_item_changed(self, item, column):
        """Обрабатывает изменение галочек группового выделения."""
        self.tree.blockSignals(True)
        try:
            if item.childCount() > 0:  # Группа
                state = item.checkState(0)
                for i in range(item.childCount()):
                    child = item.child(i)
                    if not child.isHidden():
                        child.setCheckState(0, state)
            else:  # Файл
                parent = item.parent()
                if parent:
                    all_checked = all(parent.child(i).checkState(0) == Qt.CheckState.Checked for i in range(parent.childCount()) if not parent.child(i).isHidden())
                    any_checked = any(parent.child(i).checkState(0) == Qt.CheckState.Checked for i in range(parent.childCount()) if not parent.child(i).isHidden())
                    if all_checked:
                        parent.setCheckState(0, Qt.CheckState.Checked)
                    elif any_checked:
                        parent.setCheckState(0, Qt.CheckState.PartiallyChecked)
                    else:
                        parent.setCheckState(0, Qt.CheckState.Unchecked)
        finally:
            self.tree.blockSignals(False)

        self._emit_selection_stats()

    def _emit_selection_stats(self):
        root = self.tree.invisibleRootItem()
        count = 0
        total_bytes = 0
        for i in range(root.childCount()):
            group = root.child(i)
            if group.isHidden(): continue
            for j in range(group.childCount()):
                child = group.child(j)
                if not child.isHidden() and child.checkState(0) == Qt.CheckState.Checked:
                    count += 1
                    data = child.data(0, Qt.ItemDataRole.UserRole)
                    if data and "size" in data:
                        total_bytes += data["size"]
        self.selection_changed_signal.emit(count, total_bytes)

    def _on_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item: return

        menu = QMenu(self)
        is_ru = AppContext.is_ru()

        if item.childCount() > 0:  # Заголовок группы
            act_select_all = menu.addAction("Выделить все файлы в группе" if is_ru else "Select all files in group")
            act_deselect_all = menu.addAction("Снять выделение со всех файлов" if is_ru else "Deselect all files")
            act_invert = menu.addAction("Инвертировать выделение в группе" if is_ru else "Invert group selection")
            
            action = menu.exec(self.tree.viewport().mapToGlobal(pos))
            if action == act_select_all:
                self._set_group_checkstate(item, Qt.CheckState.Checked)
            elif action == act_deselect_all:
                self._set_group_checkstate(item, Qt.CheckState.Unchecked)
            elif action == act_invert:
                self._invert_group_selection(item)
        else:  # Отдельный файл
            data = item.data(0, Qt.ItemDataRole.UserRole)
            filepath = data.get("path") if data else None

            if filepath:
                act_open = menu.addAction("Открыть файл" if is_ru else "Open File")
                act_show = menu.addAction("Показать в папке" if is_ru else "Show in Folder")
                menu.addSeparator()
                act_invert_parent = menu.addAction("Инвертировать выделение в группе" if is_ru else "Invert group selection")

                action = menu.exec(self.tree.viewport().mapToGlobal(pos))
                if action == act_open:
                    from utils_io import open_file
                    open_file(filepath)
                elif action == act_show:
                    from utils_io import reveal_in_explorer
                    reveal_in_explorer(filepath)
                elif action == act_invert_parent and item.parent():
                    self._invert_group_selection(item.parent())

    def _set_group_checkstate(self, group_item, state):
        self.tree.blockSignals(True)
        try:
            group_item.setCheckState(0, state)
            for i in range(group_item.childCount()):
                child = group_item.child(i)
                if not child.isHidden():
                    child.setCheckState(0, state)
        finally:
            self.tree.blockSignals(False)
        self._emit_selection_stats()

    def _invert_group_selection(self, group_item):
        self.tree.blockSignals(True)
        try:
            for i in range(group_item.childCount()):
                child = group_item.child(i)
                if not child.isHidden():
                    new_state = Qt.CheckState.Unchecked if child.checkState(0) == Qt.CheckState.Checked else Qt.CheckState.Checked
                    child.setCheckState(0, new_state)
        finally:
            self.tree.blockSignals(False)
        self._emit_selection_stats()
