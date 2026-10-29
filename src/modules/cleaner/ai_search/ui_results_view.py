import os
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QSplitter, QTreeWidgetItem, QMenu, QSlider, QTreeWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QSize, QUrl
from PyQt6.QtGui import QIcon, QPixmap, QColor, QAction, QPainter, QDesktopServices

from config import AppContext
from utils_common import format_size, reveal_in_explorer
from ..ui_widgets import CleanerTreeWidget, CleanSpinBox
from ..ui_preview import CleanerPreviewWidget


class AiResultsView(QWidget):
    """
    Виджет отображения результатов ИИ-поиска.
    Объединяет дерево результатов, тулбар выбора, быстрый пост-фильтр и панель предпросмотра с лицами.
    """
    file_selected = pyqtSignal(str)
    selection_changed = pyqtSignal(int, int)  # count, total_bytes
    stats_updated = pyqtSignal(str)
    send_group_to_sorter_requested = pyqtSignal(object)  # group_item

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_cluster_results = False
        self.cluster_unique_sizes = []
        self.cache_manager = None
        self.chk_show_faces_supplier = lambda: True
        self.source_folders_supplier = lambda: {}

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Пост-фильтр (встраивается или отображается над деревом)
        self.post_filter_widget = QWidget()
        self.post_filter_widget.setStyleSheet("border: none;")
        post_filter_layout = QHBoxLayout(self.post_filter_widget)
        post_filter_layout.setContentsMargins(0, 4, 0, 4)
        post_filter_layout.setSpacing(8)

        icons_dir = AppContext.find_resource_dir("icons") or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "icons")
        self.btn_exp_ai = QPushButton()
        self.btn_exp_ai.setIcon(QIcon(os.path.join(icons_dir, "square-chevron-down.svg")))
        self.btn_exp_ai.setIconSize(QSize(18, 18))
        self.btn_exp_ai.setToolTip(AppContext.tr("cln_btn_expand") if hasattr(AppContext, "tr") else "Развернуть все группы")

        self.btn_col_ai = QPushButton()
        self.btn_col_ai.setIcon(QIcon(os.path.join(icons_dir, "square-chevron-up.svg")))
        self.btn_col_ai.setIconSize(QSize(18, 18))
        self.btn_col_ai.setToolTip(AppContext.tr("cln_btn_collapse") if hasattr(AppContext, "tr") else "Свернуть все группы")

        for b in (self.btn_exp_ai, self.btn_col_ai):
            b.setFixedWidth(30)
            b.setStyleSheet("QPushButton { background: #333; border: 1px solid #444; border-radius: 3px; } QPushButton:hover { background: #444; }")
            b.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_exp_ai.clicked.connect(lambda: self.tree_results.expandAll())
        self.btn_col_ai.clicked.connect(lambda: self.tree_results.collapseAll())

        post_filter_layout.addWidget(self.btn_exp_ai)
        post_filter_layout.addWidget(self.btn_col_ai)
        post_filter_layout.addSpacing(10)

        self.lbl_post_filter = QLabel("Быстрый фильтр:" if AppContext.is_ru() else "Quick Filter:")
        tooltip_post = (
            "Скрывает из таблицы файлы, чья схожесть с лидером группы ниже выбранного процента.\n"
            "Это НЕ удаляет файлы из списка результатов навсегда, а лишь временно скрывает их,\n"
            "помогая сфокусироваться только на самых похожих фото."
        )
        self.lbl_post_filter.setToolTip(tooltip_post)
        self.lbl_post_filter.setStyleSheet("color: #ccc; font-size: 11px; font-weight: bold;")
        post_filter_layout.addWidget(self.lbl_post_filter)

        self.slider_post_filter = QSlider(Qt.Orientation.Horizontal)
        self.slider_post_filter.setToolTip(tooltip_post)
        self.slider_post_filter.setRange(0, 10000)
        self.slider_post_filter.setValue(0)
        self.slider_post_filter.setStyleSheet("""
            QSlider { border: none; background: transparent; }
            QSlider::groove:horizontal { height: 4px; background: #333; border-radius: 2px; border: none; }
            QSlider::handle:horizontal { background: #10b981; width: 12px; height: 12px; margin-top: -4px; margin-bottom: -4px; border-radius: 6px; border: none; }
        """)
        post_filter_layout.addWidget(self.slider_post_filter)

        self.spin_post_filter = CleanSpinBox()
        self.spin_post_filter.setRange(0.0, 100.0)
        self.spin_post_filter.setDecimals(2)
        self.spin_post_filter.setSingleStep(0.01)
        self.spin_post_filter.setSuffix("%")
        self.spin_post_filter.setFixedWidth(65)
        self.spin_post_filter.setStyleSheet("border: none; background: transparent; color: #f0f0f0; font-weight: bold; font-size: 12px; padding: 0 4px;")
        post_filter_layout.addWidget(self.spin_post_filter)

        self.slider_post_filter.valueChanged.connect(self._on_slider_moved)
        self.spin_post_filter.valueChanged.connect(self._on_spin_changed)
        self.spin_post_filter.valueChanged.connect(self.on_post_filter_changed)

        self.post_filter_widget.hide()

        # 2. Сплиттер таблицы и превью
        self.right_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.right_splitter.setHandleWidth(2)
        self.right_splitter.setStyleSheet("QSplitter::handle { background-color: #2d2d2d; }")

        tree_container = QWidget()
        tree_layout = QVBoxLayout(tree_container)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(0)

        tt_bar = QFrame()
        tt_bar.setFixedHeight(40)
        tt_bar.setStyleSheet("background: #2a2a2a; border-bottom: 1px solid #333;")
        tt_layout = QHBoxLayout(tt_bar)
        tt_layout.setContentsMargins(10, 0, 10, 0)
        tt_layout.setSpacing(10)
        tt_layout.addStretch(1)

        self.lbl_selection_info = QLabel("Выбрано: 0 файлов • 0 B" if AppContext.is_ru() else "Selected: 0 files • 0 B")
        self.lbl_selection_info.setStyleSheet("color: #93c5fd; font-size: 11px; font-weight: bold;")
        tt_layout.addWidget(self.lbl_selection_info)
        tree_layout.addWidget(tt_bar)

        self.tree_results = CleanerTreeWidget()
        self.tree_results.setColumnCount(4)
        self.tree_results.setHeaderLabels([
            "Имя файла" if AppContext.is_ru() else "File Name",
            "Сходство (%)" if AppContext.is_ru() else "Similarity (%)",
            "Размер" if AppContext.is_ru() else "Size",
            "Путь" if AppContext.is_ru() else "Path"
        ])
        self.tree_results.setColumnWidth(0, 240)
        self.tree_results.setColumnWidth(1, 100)
        self.tree_results.setColumnWidth(2, 90)
        self.tree_results.setStyleSheet("""
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
        self.tree_results.itemSelectionChanged.connect(self.on_tree_selection_changed)
        self.tree_results.itemChanged.connect(self.on_tree_item_changed)
        self.tree_results.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_results.customContextMenuRequested.connect(self.show_results_context_menu)
        tree_layout.addWidget(self.tree_results)

        self.right_splitter.addWidget(tree_container)

        self.preview_widget = CleanerPreviewWidget()
        self.preview_widget.show_empty("Выберите файл для предпросмотра" if AppContext.is_ru() else "Select a file to preview")
        self.right_splitter.addWidget(self.preview_widget)
        self.right_splitter.setSizes([650, 350])

        main_layout.addWidget(self.right_splitter, 1)

    def _on_slider_moved(self, value):
        if self.is_cluster_results and self.cluster_unique_sizes:
            if 0 <= value < len(self.cluster_unique_sizes):
                self.spin_post_filter.setValue(float(self.cluster_unique_sizes[value]))
        else:
            self.spin_post_filter.setValue(value / 100.0)

    def _on_spin_changed(self, value):
        self.slider_post_filter.blockSignals(True)
        if self.is_cluster_results and self.cluster_unique_sizes:
            try:
                closest_idx = min(range(len(self.cluster_unique_sizes)), key=lambda i: abs(self.cluster_unique_sizes[i] - value))
                self.slider_post_filter.setValue(closest_idx)
            except ValueError:
                pass
        else:
            self.slider_post_filter.setValue(int(value * 100))
        self.slider_post_filter.blockSignals(False)

    def on_post_filter_changed(self, value):
        root = self.tree_results.invisibleRootItem()
        self.tree_results.blockSignals(True)
        try:
            for i in range(root.childCount()):
                group_item = root.child(i)
                group_visible_children = 0

                g_data = group_item.data(0, Qt.ItemDataRole.UserRole)
                g_name = g_data.get("name", "Unknown") if g_data else "Unknown"

                if self.is_cluster_results:
                    target_size = int(value)
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
                        group_item.setText(0, f"Группа: {g_name} ({actual_size} файлов)" if AppContext.is_ru() else f"Group: {g_name} ({actual_size} files)")
                else:
                    target_similarity = float(value)
                    for j in range(group_item.childCount()):
                        child = group_item.child(j)
                        data = child.data(0, Qt.ItemDataRole.UserRole)
                        if data:
                            sim = data.get("confidence", 0.0) * 100.0
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
                        group_item.setText(0, f"Группа: {g_name} ({group_visible_children} файлов)" if AppContext.is_ru() else f"Group: {g_name} ({group_visible_children} files)")
        finally:
            self.tree_results.blockSignals(False)

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

        stats_text = (
            f"Отображено: {visible_groups} групп, {visible_files} файлов, {visible_bytes // (1024*1024) if visible_bytes else 0} MB" if AppContext.is_ru()
            else f"Displayed: {visible_groups} groups, {visible_files} files, {format_size(visible_bytes)}"
        )
        self.stats_updated.emit(stats_text)
        self._emit_selection_stats()

    def clear_results(self):
        self.tree_results.clear()
        self.post_filter_widget.hide()
        self.preview_widget.show_empty("Файл не выбран" if AppContext.is_ru() else "No file selected")
        self.file_selected.emit("")
        self._emit_selection_stats()

    def populate_results(self, results: dict, is_cluster: bool = False, scan_threshold: float = 50.0, source_folders: dict = None):
        self.tree_results.setUpdatesEnabled(False)
        self.tree_results.blockSignals(True)
        try:
            self.clear_results()
            if not results:
                return

            self.is_cluster_results = is_cluster
            unique_sizes = set()
            top_level_items = []
            folders = source_folders if source_folders is not None else self.source_folders_supplier()

            for group_name, files in results.items():
                if not files:
                    continue

                group_size = sum(f["size"] for f in files)
                num_files = len(files)
                unique_sizes.add(num_files)

                group_item = QTreeWidgetItem()
                group_item.setCheckState(0, Qt.CheckState.Unchecked)
                group_item.setText(0, f"Группа: {group_name} ({num_files} файлов)" if AppContext.is_ru() else f"Group: {group_name} ({num_files} files)")
                group_item.setText(2, format_size(group_size))
                group_item.setData(0, Qt.ItemDataRole.UserRole, {"is_group": True, "name": group_name})

                font = group_item.font(0)
                font.setBold(True)
                group_item.setFont(0, font)
                group_item.setFont(2, font)

                child_items = []
                for f in files:
                    file_item = QTreeWidgetItem()
                    file_item.setCheckState(0, Qt.CheckState.Unchecked)
                    file_item.setText(0, os.path.basename(f["path"]))
                    file_item.setText(1, f"{f['confidence']:.1f}%")
                    file_item.setText(2, format_size(f["size"]))
                    file_item.setText(3, f["path"])
                    file_item.setData(0, Qt.ItemDataRole.UserRole, {
                        "is_group": False,
                        "path": f["path"],
                        "size": f["size"],
                        "confidence": f.get("confidence", 0.0) / 100.0,
                        "matched_bbox": f.get("matched_bbox"),
                        "type": f.get("type", "face"),
                        "tag_scores": f.get("tag_scores", {})
                    })

                    color_hex = "#555"
                    if folders:
                        for src_path, data in folders.items():
                            if f["path"].startswith(src_path):
                                color_hex = data.get('color', "#555")
                                break

                    if color_hex:
                        pixmap = QPixmap(12, 12)
                        pixmap.fill(Qt.GlobalColor.transparent)
                        painter = QPainter(pixmap)
                        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.setBrush(QColor(color_hex))
                        painter.drawEllipse(1, 1, 10, 10)
                        painter.end()
                        file_item.setIcon(0, QIcon(pixmap))

                    child_items.append(file_item)

                group_item.addChildren(child_items)
                group_item.setExpanded(True)
                top_level_items.append(group_item)

            self.tree_results.addTopLevelItems(top_level_items)

            self.spin_post_filter.blockSignals(True)
            self.slider_post_filter.blockSignals(True)
            if self.is_cluster_results:
                sizes = sorted(list(unique_sizes))
                self.cluster_unique_sizes = sizes
                min_size = min(sizes) if sizes else 1
                max_size = max(sizes) if sizes else 100
                self.spin_post_filter.setSuffix(" ф." if AppContext.is_ru() else " f.")
                self.spin_post_filter.setDecimals(0)
                self.spin_post_filter.setSingleStep(1.0)
                self.spin_post_filter.setRange(float(min_size), float(max_size))
                self.slider_post_filter.setRange(0, len(sizes) - 1 if sizes else 0)
                default_val = 2.0
                if max_size < 2:
                    default_val = float(max_size)
                self.spin_post_filter.setValue(default_val)
                try:
                    idx = min(range(len(sizes)), key=lambda i: abs(sizes[i] - default_val))
                    self.slider_post_filter.setValue(idx)
                except ValueError:
                    pass
            else:
                self.spin_post_filter.setSuffix("%")
                self.spin_post_filter.setDecimals(2)
                self.spin_post_filter.setSingleStep(0.01)
                self.spin_post_filter.setRange(scan_threshold, 100.0)
                self.slider_post_filter.setRange(int(scan_threshold * 100), 10000)
                self.spin_post_filter.setValue(scan_threshold)

            self.spin_post_filter.blockSignals(False)
            self.slider_post_filter.blockSignals(False)

            self.post_filter_widget.show()
            self.on_post_filter_changed(self.spin_post_filter.value())
        finally:
            self.tree_results.blockSignals(False)
            self.tree_results.setUpdatesEnabled(True)

    def on_tree_selection_changed(self):
        selected_items = self.tree_results.selectedItems()
        if not selected_items:
            self.preview_widget.show_empty("Файл не выбран" if AppContext.is_ru() else "No file selected")
            self.file_selected.emit("")
            return

        item = selected_items[0]
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and not data.get("is_group", False):
            path = data.get("path")
            group_item = item.parent()
            group_name = None
            if group_item:
                g_data = group_item.data(0, Qt.ItemDataRole.UserRole)
                if g_data:
                    group_name = g_data.get("name")

            if path and os.path.exists(path):
                self.preview_widget.load_file(path)
                tag_scores = data.get("tag_scores")
                if hasattr(self.preview_widget, "set_ai_info"):
                    self.preview_widget.set_ai_info(tag_scores, group_name=group_name)

                # Отрисовка рамок лиц из кэша
                try:
                    faces = None
                    if self.cache_manager is not None:
                        stat = os.stat(path)
                        faces = self.cache_manager.get_file_faces(path, stat.st_mtime, stat.st_size)

                    matched_bbox = data.get("matched_bbox")
                    bboxes = []
                    if faces:
                        bboxes = [f.get("bbox") for f in faces if f.get("bbox")]
                    if not bboxes and matched_bbox:
                        bboxes = [matched_bbox]

                    show_faces = self.chk_show_faces_supplier()
                    if hasattr(self.preview_widget, "draw_faces") and show_faces:
                        self.preview_widget.draw_faces(bboxes, matched_bbox=matched_bbox)
                    elif hasattr(self.preview_widget, "clear_faces"):
                        self.preview_widget.clear_faces()
                except Exception as e:
                    logging.error(f"Ошибка получения лиц для предпросмотра: {e}", exc_info=True)

                self.file_selected.emit(path)
        else:
            self.preview_widget.show_empty("Файл не выбран" if AppContext.is_ru() else "No file selected")
            self.file_selected.emit("")

    def refresh_preview_faces(self):
        if self.tree_results.selectedItems():
            self.on_tree_selection_changed()

    def on_tree_item_changed(self, item, column):
        if column != 0:
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        self.tree_results.blockSignals(True)
        try:
            target_paths = []
            target_state = item.checkState(0)

            if data.get("is_group", False):
                for i in range(item.childCount()):
                    child = item.child(i)
                    if not child.isHidden():
                        child.setCheckState(0, target_state)
                        child_data = child.data(0, Qt.ItemDataRole.UserRole)
                        if child_data:
                            target_paths.append(child_data.get("path"))
            else:
                target_paths.append(data.get("path"))
                parent = item.parent()
                if parent:
                    all_checked = True
                    any_checked = False
                    visible_count = 0
                    for i in range(parent.childCount()):
                        if parent.child(i).isHidden():
                            continue
                        visible_count += 1
                        c_state = parent.child(i).checkState(0)
                        if c_state == Qt.CheckState.Checked:
                            any_checked = True
                        else:
                            all_checked = False

                    if visible_count > 0:
                        if all_checked:
                            parent.setCheckState(0, Qt.CheckState.Checked)
                        elif any_checked:
                            parent.setCheckState(0, Qt.CheckState.PartiallyChecked)
                        else:
                            parent.setCheckState(0, Qt.CheckState.Unchecked)

            if self.is_cluster_results and target_paths:
                root = self.tree_results.invisibleRootItem()
                target_paths_set = set(target_paths)
                for i in range(root.childCount()):
                    g_item = root.child(i)
                    needs_parent_update = False
                    for j in range(g_item.childCount()):
                        c_item = g_item.child(j)
                        if c_item.isHidden() or c_item == item:
                            continue
                        c_data = c_item.data(0, Qt.ItemDataRole.UserRole)
                        if c_data and c_data.get("path") in target_paths_set:
                            c_item.setCheckState(0, target_state)
                            needs_parent_update = True

                    if needs_parent_update:
                        all_checked = True
                        any_checked = False
                        visible_count = 0
                        for k in range(g_item.childCount()):
                            if g_item.child(k).isHidden():
                                continue
                            visible_count += 1
                            cs = g_item.child(k).checkState(0)
                            if cs == Qt.CheckState.Checked:
                                any_checked = True
                            else:
                                all_checked = False
                        if visible_count > 0:
                            if all_checked:
                                g_item.setCheckState(0, Qt.CheckState.Checked)
                            elif any_checked:
                                g_item.setCheckState(0, Qt.CheckState.PartiallyChecked)
                            else:
                                g_item.setCheckState(0, Qt.CheckState.Unchecked)
        finally:
            self.tree_results.blockSignals(False)

        self._emit_selection_stats()

    def get_selected_files_paths(self) -> list:
        paths = []
        root = self.tree_results.invisibleRootItem()
        for i in range(root.childCount()):
            group_item = root.child(i)
            if group_item.isHidden():
                continue
            for j in range(group_item.childCount()):
                file_item = group_item.child(j)
                if not file_item.isHidden() and file_item.checkState(0) == Qt.CheckState.Checked:
                    data = file_item.data(0, Qt.ItemDataRole.UserRole)
                    if data and data.get("path"):
                        paths.append(data["path"])
        return paths

    def get_selected_files_size(self) -> int:
        selected_paths = self.get_selected_files_paths()
        return sum(os.path.getsize(p) for p in selected_paths if os.path.exists(p))

    def select_all_results(self, checked: bool):
        self.tree_results.blockSignals(True)
        try:
            root = self.tree_results.invisibleRootItem()
            state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            for i in range(root.childCount()):
                group_item = root.child(i)
                if checked and group_item.isHidden():
                    continue
                group_item.setCheckState(0, state)
                for j in range(group_item.childCount()):
                    child = group_item.child(j)
                    if checked and child.isHidden():
                        continue
                    child.setCheckState(0, state)
        finally:
            self.tree_results.blockSignals(False)
        self._emit_selection_stats()

    def set_group_selection_state(self, group_item, state):
        self.tree_results.blockSignals(True)
        try:
            group_item.setCheckState(0, state)
            for i in range(group_item.childCount()):
                child = group_item.child(i)
                if not child.isHidden():
                    child.setCheckState(0, state)
        finally:
            self.tree_results.blockSignals(False)
        self._emit_selection_stats()

    def invert_group_selection(self, group_item):
        if not group_item:
            return
        self.tree_results.blockSignals(True)
        try:
            checked_count = 0
            visible_count = 0
            for i in range(group_item.childCount()):
                child = group_item.child(i)
                if not child.isHidden():
                    visible_count += 1
                    new_state = Qt.CheckState.Checked if child.checkState(0) == Qt.CheckState.Unchecked else Qt.CheckState.Unchecked
                    child.setCheckState(0, new_state)
                    if new_state == Qt.CheckState.Checked:
                        checked_count += 1

            if checked_count == 0:
                group_item.setCheckState(0, Qt.CheckState.Unchecked)
            elif checked_count == visible_count and visible_count > 0:
                group_item.setCheckState(0, Qt.CheckState.Checked)
            else:
                group_item.setCheckState(0, Qt.CheckState.PartiallyChecked)
        finally:
            self.tree_results.blockSignals(False)
        self._emit_selection_stats()

    def remove_processed_files(self, paths: list[str]):
        paths_set = set(os.path.normpath(p) for p in paths)
        root = self.tree_results.invisibleRootItem()

        for i in range(root.childCount() - 1, -1, -1):
            group_item = root.child(i)
            for j in range(group_item.childCount() - 1, -1, -1):
                file_item = group_item.child(j)
                data = file_item.data(0, Qt.ItemDataRole.UserRole)
                if data and data.get("path") and os.path.normpath(data["path"]) in paths_set:
                    group_item.removeChild(file_item)

            if group_item.childCount() == 0:
                root.removeChild(group_item)

        self.preview_widget.show_empty("Выберите файл для предпросмотра" if AppContext.is_ru() else "Select a file to preview")
        self._emit_selection_stats()

    def _emit_selection_stats(self):
        selected_paths = self.get_selected_files_paths()
        count = len(selected_paths)
        size = sum(os.path.getsize(p) for p in selected_paths if os.path.exists(p))
        size_str = format_size(size)

        self.lbl_selection_info.setStyleSheet("color: #93c5fd; font-size: 11px; font-weight: bold;")
        self.lbl_selection_info.setText(f"Выбрано: {count} файлов • {size_str}" if AppContext.is_ru() else f"Selected: {count} files • {size_str}")
        self.lbl_selection_info.setToolTip(f"Выбрано файлов: {count}\nРазмер: {size_str}")
        self.selection_changed.emit(count, size)

    def show_results_context_menu(self, pos: QPoint):
        item = self.tree_results.itemAt(pos)
        if not item:
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        is_ru = AppContext.is_ru()
        if data and data.get("is_group", False):
            menu = QMenu(self)
            menu.setStyleSheet("QMenu { background-color: #2b2b2b; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #3b82f6; } QMenu::separator { height: 1px; background: #666; margin: 4px 8px; }")

            act_select = QAction("Выделить все файлы в этой группе" if is_ru else "Select all files in this group", self)
            act_deselect = QAction("Снять выделение со всех файлов в группе" if is_ru else "Deselect all files in this group", self)
            act_invert = QAction("Инвертировать выделение" if is_ru else "Invert Selection", self)

            act_select.triggered.connect(lambda: self.set_group_selection_state(item, Qt.CheckState.Checked))
            act_deselect.triggered.connect(lambda: self.set_group_selection_state(item, Qt.CheckState.Unchecked))
            act_invert.triggered.connect(lambda: self.invert_group_selection(item))

            menu.addAction(act_select)
            menu.addAction(act_deselect)
            menu.addAction(act_invert)

            menu.addSeparator()
            act_send_sorter = QAction("Отправить эту группу в Сортировщик", self)
            act_send_sorter.triggered.connect(lambda checked, gi=item: self.send_group_to_sorter_requested.emit(gi))
            menu.addAction(act_send_sorter)

            menu.addSeparator()
            act_expand_all = QAction("Развернуть все группы" if is_ru else "Expand all groups", self)
            act_collapse_all = QAction("Свернуть все группы" if is_ru else "Collapse all groups", self)
            act_expand_all.triggered.connect(self.tree_results.expandAll)
            act_collapse_all.triggered.connect(self.tree_results.collapseAll)
            menu.addAction(act_expand_all)
            menu.addAction(act_collapse_all)

            menu.exec(self.tree_results.mapToGlobal(pos))
        elif data and not data.get("is_group", False):
            menu = QMenu(self)
            menu.setStyleSheet("QMenu { background-color: #2b2b2b; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #3b82f6; } QMenu::separator { height: 1px; background: #666; margin: 4px 8px; }")
            path = data.get("path")

            act_open = QAction("Открыть файл" if is_ru else "Open File", self)
            act_open.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
            menu.addAction(act_open)

            act_reveal = QAction("Показать в папке" if is_ru else "Show in folder", self)
            act_reveal.triggered.connect(lambda: reveal_in_explorer(path))
            menu.addAction(act_reveal)

            menu.addSeparator()

            group_item = item.parent()
            act_select = QAction("Выделить все файлы в этой группе" if is_ru else "Select all files in this group", self)
            act_deselect = QAction("Снять выделение со всех файлов в группе" if is_ru else "Deselect all files in this group", self)
            act_invert = QAction("Инвертировать выделение в группе" if is_ru else "Invert Selection in group", self)

            act_select.triggered.connect(lambda: self.set_group_selection_state(group_item, Qt.CheckState.Checked))
            act_deselect.triggered.connect(lambda: self.set_group_selection_state(group_item, Qt.CheckState.Unchecked))
            act_invert.triggered.connect(lambda: self.invert_group_selection(group_item))

            menu.addAction(act_select)
            menu.addAction(act_deselect)
            menu.addAction(act_invert)

            menu.addSeparator()
            act_send_sorter = QAction("Отправить эту группу в Сортировщик", self)
            act_send_sorter.triggered.connect(lambda checked, gi=group_item: self.send_group_to_sorter_requested.emit(gi))
            menu.addAction(act_send_sorter)

            menu.addSeparator()
            act_expand_all = QAction("Развернуть все группы" if is_ru else "Expand all groups", self)
            act_collapse_all = QAction("Свернуть все группы" if is_ru else "Collapse all groups", self)
            act_expand_all.triggered.connect(self.tree_results.expandAll)
            act_collapse_all.triggered.connect(self.tree_results.collapseAll)
            menu.addAction(act_expand_all)
            menu.addAction(act_collapse_all)

            menu.exec(self.tree_results.mapToGlobal(pos))
