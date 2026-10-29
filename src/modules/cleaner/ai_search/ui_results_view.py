import os
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QSplitter, QTreeWidgetItem, QMenu, QSlider, QStackedWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QSize, QUrl, QItemSelectionModel, QModelIndex
from PyQt6.QtGui import QIcon, QPixmap, QColor, QAction, QPainter, QDesktopServices, QShortcut, QKeySequence

from config import AppContext
from modules.shared import ui_theme
from utils_common import format_size, reveal_in_explorer
from ..ui_widgets import CleanerTreeWidget, CleanSpinBox
from ..ui_preview import CleanerPreviewWidget
from .ui_grid_view import (
    AiResultsGridView, AiResultsListModel, AiResultsFilterProxyModel,
    AiGridItem, HoverSettingsDialog
)


class AiResultsView(QWidget):
    """
    Виджет отображения результатов ИИ-поиска.
    Объединяет:
      - Режим «Дерево» (CleanerTreeWidget)
      - Режим «Сетка миниатюр» (AiResultsGridView)
      - Тулбар переключения режимов, зума и быстрого просмотра (Hover Preview)
      - Быстрый пост-фильтр по схожести
      - Панель предпросмотра с лицами и метаданными
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
        self.current_view_mode = "tree"

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        icons_dir = AppContext.find_resource_dir("icons") or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "icons"
        )

        # 1. Пост-фильтр (встраивается в action_bar или отображается над результатами)
        self.post_filter_widget = QWidget(self)
        self.post_filter_widget.setStyleSheet("border: none;")
        post_filter_layout = QHBoxLayout(self.post_filter_widget)
        post_filter_layout.setContentsMargins(0, 4, 0, 4)
        post_filter_layout.setSpacing(8)

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

        self.lbl_post_filter = QLabel(AppContext.tr("cln_ai_quick_filter"))
        tooltip_post = AppContext.tr("cln_ai_quick_filter_tip")
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

        # 2. Сплиттер представления результатов и превью
        self.right_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.right_splitter.setHandleWidth(2)
        self.right_splitter.setStyleSheet(ui_theme.STYLE_SPLITTER)

        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # Тулбар над результатами (переключатель режимов, зум, ховер, счетчик выделения)
        tt_bar = QFrame()
        tt_bar.setFixedHeight(40)
        tt_bar.setStyleSheet("background: #2a2a2a; border-bottom: 1px solid #333;")
        tt_layout = QHBoxLayout(tt_bar)
        tt_layout.setContentsMargins(8, 0, 8, 0)
        tt_layout.setSpacing(6)

        # Переключатель видов: Дерево / Сетка
        self.btn_view_tree = QPushButton()
        self.btn_view_tree.setIcon(QIcon(os.path.join(icons_dir, "view_list.svg")))
        self.btn_view_tree.setIconSize(QSize(18, 18))
        self.btn_view_tree.setFixedSize(30, 28)
        self.btn_view_tree.setCheckable(True)
        self.btn_view_tree.setChecked(True)
        self.btn_view_tree.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_tree.setToolTip(AppContext.tr("cln_ai_view_tree"))

        self.btn_view_grid = QPushButton()
        self.btn_view_grid.setIcon(QIcon(os.path.join(icons_dir, "view_grid.svg")))
        self.btn_view_grid.setIconSize(QSize(18, 18))
        self.btn_view_grid.setFixedSize(30, 28)
        self.btn_view_grid.setCheckable(True)
        self.btn_view_grid.setChecked(False)
        self.btn_view_grid.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_grid.setToolTip(AppContext.tr("cln_ai_view_grid"))

        btn_mode_style = """
            QPushButton {
                background: #333;
                border: 1px solid #444;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #444;
            }
            QPushButton:checked {
                background: #2563eb;
                border: 1px solid #3b82f6;
            }
        """
        self.btn_view_tree.setStyleSheet(btn_mode_style)
        self.btn_view_grid.setStyleSheet(btn_mode_style)

        self.btn_view_tree.clicked.connect(lambda: self.set_view_mode("tree"))
        self.btn_view_grid.clicked.connect(lambda: self.set_view_mode("grid"))

        tt_layout.addWidget(self.btn_view_tree)
        tt_layout.addWidget(self.btn_view_grid)
        tt_layout.addSpacing(6)

        # Ползунок масштабирования плиток (для сетки)
        self.slider_zoom = QSlider(Qt.Orientation.Horizontal)
        self.slider_zoom.setRange(80, 260)
        self.slider_zoom.setValue(130)
        self.slider_zoom.setFixedWidth(100)
        self.slider_zoom.setToolTip(AppContext.tr("cln_ai_zoom_tip"))
        self.slider_zoom.setStyleSheet("""
            QSlider { border: none; background: transparent; }
            QSlider::groove:horizontal { height: 4px; background: #333; border-radius: 2px; }
            QSlider::handle:horizontal { background: #3b82f6; width: 12px; height: 12px; margin-top: -4px; margin-bottom: -4px; border-radius: 6px; }
        """)
        self.slider_zoom.hide()
        self.slider_zoom.valueChanged.connect(self._on_zoom_slider_changed)
        tt_layout.addWidget(self.slider_zoom)
        tt_layout.addSpacing(4)

        # Кнопка быстрого просмотра при наведении (👁)
        self.btn_hover_preview = QPushButton("👁")
        self.btn_hover_preview.setFixedSize(30, 28)
        self.btn_hover_preview.setCheckable(True)
        self.btn_hover_preview.setChecked(True)
        self.btn_hover_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_hover_btn_style(True)
        self.btn_hover_preview.clicked.connect(self._on_toggle_hover_preview)
        tt_layout.addWidget(self.btn_hover_preview)

        # Кнопка настроек быстрого просмотра (⚙️)
        self.btn_hover_settings = QPushButton()
        self.btn_hover_settings.setIcon(QIcon(os.path.join(icons_dir, "settings.svg")))
        self.btn_hover_settings.setIconSize(QSize(16, 16))
        self.btn_hover_settings.setFixedSize(28, 28)
        self.btn_hover_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_hover_settings.setStyleSheet("QPushButton { background: #333; border: 1px solid #444; border-radius: 4px; } QPushButton:hover { background: #444; }")
        self.btn_hover_settings.setToolTip(AppContext.tr("cln_ai_hover_settings"))
        self.btn_hover_settings.clicked.connect(self._open_hover_settings)
        tt_layout.addWidget(self.btn_hover_settings)

        tt_layout.addStretch(1)

        self.lbl_selection_info = QLabel(AppContext.tr("cln_frag_sel_info_empty"))
        self.lbl_selection_info.setStyleSheet("color: #93c5fd; font-size: 11px; font-weight: bold;")
        tt_layout.addWidget(self.lbl_selection_info)
        left_layout.addWidget(tt_bar)

        # Стек представлений: 0 -> Дерево, 1 -> Сетка
        self.view_stack = QStackedWidget()

        # 2a. Дерево результатов
        self.tree_results = CleanerTreeWidget()
        self.tree_results.setColumnCount(4)
        self.tree_results.setHeaderLabels([
            AppContext.tr("cln_ai_col_filename"),
            AppContext.tr("cln_frag_col_sim"),
            AppContext.tr("cln_frag_col_size"),
            AppContext.tr("cln_frag_col_path")
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
        self.view_stack.addWidget(self.tree_results)

        # 2b. Виртуальная сетка результатов
        self.grid_model = AiResultsListModel(self)
        self.grid_proxy = AiResultsFilterProxyModel(self)
        self.grid_proxy.setSourceModel(self.grid_model)

        self.grid_results = AiResultsGridView(self)
        self.grid_results.setModel(self.grid_proxy)
        self.grid_results.selectionModel().currentChanged.connect(self.on_grid_current_changed)
        self.grid_results.zoom_changed.connect(self.slider_zoom.setValue)
        self.grid_model.check_state_changed.connect(self._on_grid_item_check_state_changed)
        self.grid_results.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.grid_results.customContextMenuRequested.connect(self.show_grid_context_menu)
        self.grid_results.item_double_clicked.connect(lambda p: QDesktopServices.openUrl(QUrl.fromLocalFile(p)))

        self.view_stack.addWidget(self.grid_results)
        left_layout.addWidget(self.view_stack, 1)

        self.right_splitter.addWidget(left_container)

        # 3. Панель предпросмотра
        self.preview_widget = CleanerPreviewWidget()
        self.preview_widget.show_empty(AppContext.tr("cln_ai_select_file_preview"))
        self.right_splitter.addWidget(self.preview_widget)
        self.right_splitter.setSizes([650, 350])

        main_layout.addWidget(self.right_splitter, 1)

        # Горячая клавиша F1 для переключения быстрого просмотра
        self.shortcut_hover = QShortcut(QKeySequence("F1"), self)
        self.shortcut_hover.activated.connect(self.btn_hover_preview.click)

    # -------------------------------------------------------------------------
    # Переключение режимов отображения (Дерево / Сетка)
    # -------------------------------------------------------------------------
    def set_view_mode(self, mode: str):
        self.grid_results._stop_hover()
        if mode == "grid":
            self.current_view_mode = "grid"
            self.btn_view_tree.setChecked(False)
            self.btn_view_grid.setChecked(True)
            self.slider_zoom.show()
            self.view_stack.setCurrentIndex(1)

            # Синхронизация текущего выделения из дерева в сетку
            selected = self.tree_results.selectedItems()
            if selected:
                self._select_grid_item_by_tree_item(selected[0])
        else:
            self.current_view_mode = "tree"
            self.btn_view_tree.setChecked(True)
            self.btn_view_grid.setChecked(False)
            self.slider_zoom.hide()
            self.view_stack.setCurrentIndex(0)

            # Синхронизация текущего выделения из сетки в дерево
            cur_idx = self.grid_results.currentIndex()
            if cur_idx.isValid():
                grid_item: AiGridItem = cur_idx.data(Qt.ItemDataRole.UserRole)
                if grid_item and grid_item.tree_item:
                    self.tree_results.blockSignals(True)
                    self.tree_results.clearSelection()
                    grid_item.tree_item.setSelected(True)
                    self.tree_results.setCurrentItem(grid_item.tree_item)
                    self.tree_results.scrollToItem(grid_item.tree_item)
                    self.tree_results.blockSignals(False)

    def _on_zoom_slider_changed(self, val: int):
        self.grid_results.set_thumbnail_size(val)

    def _on_toggle_hover_preview(self):
        is_enabled = self.btn_hover_preview.isChecked()
        self.grid_results.set_hover_enabled(is_enabled)
        self._update_hover_btn_style(is_enabled)

    def _update_hover_btn_style(self, enabled: bool):
        if enabled:
            self.btn_hover_preview.setStyleSheet("""
                QPushButton {
                    background: #333;
                    color: #e0e0e0;
                    border: 1px solid #444;
                    border-radius: 4px;
                    font-size: 16px;
                    padding: 0;
                }
                QPushButton:hover {
                    background: #444;
                    border-color: #3b82f6;
                }
            """)
            self.btn_hover_preview.setToolTip(AppContext.tr("cln_ai_hover_tip_on"))
        else:
            self.btn_hover_preview.setStyleSheet("""
                QPushButton {
                    background: rgba(239, 68, 68, 0.4);
                    color: #ffffff;
                    border: 1px solid #ef4444;
                    border-radius: 4px;
                    font-size: 16px;
                    padding: 0;
                }
                QPushButton:hover {
                    background: rgba(239, 68, 68, 0.6);
                }
            """)
            self.btn_hover_preview.setToolTip(AppContext.tr("cln_ai_hover_tip_off"))

    def _open_hover_settings(self):
        dlg = HoverSettingsDialog(
            self,
            initial_delay=self.grid_results.hover_delay,
            initial_size=self.grid_results.popup_size
        )
        dlg.settings_saved.connect(self.grid_results.set_hover_params)
        dlg.exec()

    # -------------------------------------------------------------------------
    # Управление фильтром
    # -------------------------------------------------------------------------
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
        self.grid_results._stop_hover()
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
                        group_item.setText(0, AppContext.tr("cln_ai_group_title").format(g_name, actual_size))
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
                        group_item.setText(0, AppContext.tr("cln_ai_group_title").format(g_name, group_visible_children))
        finally:
            self.tree_results.blockSignals(False)

        # Обновляем видимость в сетке результатов
        self.grid_proxy.invalidateFilter()

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

        stats_text = AppContext.tr("cln_ai_stats_displayed").format(
            visible_groups, visible_files, visible_bytes // (1024 * 1024) if visible_bytes else 0
        )
        self.stats_updated.emit(stats_text)
        self._emit_selection_stats()

    def clear_results(self):
        self.grid_results._stop_hover()
        self.tree_results.clear()
        self.grid_model.clear()
        self.grid_proxy.invalidateFilter()
        self.post_filter_widget.hide()
        self.preview_widget.show_empty(AppContext.tr("cln_ai_no_file_selected"))
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
                group_item.setText(0, AppContext.tr("cln_ai_group_title").format(group_name, num_files))
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

                    color_hex = "#555"
                    if folders:
                        for src_path, data in folders.items():
                            if f["path"].startswith(src_path):
                                color_hex = data.get('color', "#555")
                                break

                    file_item.setData(0, Qt.ItemDataRole.UserRole, {
                        "is_group": False,
                        "path": f["path"],
                        "size": f["size"],
                        "confidence": f.get("confidence", 0.0) / 100.0,
                        "matched_bbox": f.get("matched_bbox"),
                        "type": f.get("type", "face"),
                        "tag_scores": f.get("tag_scores", {}),
                        "color_hex": color_hex
                    })

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

            # Заполнение модели сетки результатами
            grid_items = []
            for group_item in top_level_items:
                for j in range(group_item.childCount()):
                    child = group_item.child(j)
                    c_data = child.data(0, Qt.ItemDataRole.UserRole) or {}
                    grid_items.append(AiGridItem(
                        path=c_data.get("path", ""),
                        name=child.text(0),
                        size=c_data.get("size", 0),
                        confidence=float(c_data.get("confidence", 0.0) * 100.0),
                        tree_item=child,
                        bbox=c_data.get("matched_bbox"),
                        item_type=c_data.get("type", "face"),
                        tag_scores=c_data.get("tag_scores"),
                        color_hex=c_data.get("color_hex", "#555")
                    ))
            self.grid_model.set_items(grid_items)
            self.grid_proxy.invalidateFilter()

            self.spin_post_filter.blockSignals(True)
            self.slider_post_filter.blockSignals(True)
            if self.is_cluster_results:
                sizes = sorted(list(unique_sizes))
                self.cluster_unique_sizes = sizes
                min_size = min(sizes) if sizes else 1
                max_size = max(sizes) if sizes else 100
                self.spin_post_filter.setSuffix(AppContext.tr("cln_ai_suffix_files"))
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

            if not self.post_filter_widget.isWindow():
                self.post_filter_widget.show()
            self.on_post_filter_changed(self.spin_post_filter.value())
        finally:
            self.tree_results.blockSignals(False)
            self.tree_results.setUpdatesEnabled(True)

    # -------------------------------------------------------------------------
    # Синхронизация выделения и отображение предпросмотра
    # -------------------------------------------------------------------------
    def _display_file_preview(self, path: str, tag_scores: dict = None, matched_bbox: list = None, group_name: str = None):
        if path and os.path.exists(path):
            self.preview_widget.load_file(path)
            if hasattr(self.preview_widget, "set_ai_info"):
                self.preview_widget.set_ai_info(tag_scores, group_name=group_name)

            try:
                faces = None
                if self.cache_manager is not None:
                    stat = os.stat(path)
                    faces = self.cache_manager.get_file_faces(path, stat.st_mtime, stat.st_size)

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
            self.preview_widget.show_empty(AppContext.tr("cln_ai_no_file_selected"))
            self.file_selected.emit("")

    def on_tree_selection_changed(self):
        selected_items = self.tree_results.selectedItems()
        if not selected_items:
            self.preview_widget.show_empty(AppContext.tr("cln_ai_no_file_selected"))
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

            self._display_file_preview(path, data.get("tag_scores"), data.get("matched_bbox"), group_name)
            self._select_grid_item_by_tree_item(item)
        else:
            self.preview_widget.show_empty(AppContext.tr("cln_ai_no_file_selected"))
            self.file_selected.emit("")

    def on_grid_current_changed(self, current: QModelIndex, previous: QModelIndex):
        if not current.isValid():
            return

        item: AiGridItem = current.data(Qt.ItemDataRole.UserRole)
        if item and item.path:
            group_name = None
            if item.tree_item and item.tree_item.parent():
                g_data = item.tree_item.parent().data(0, Qt.ItemDataRole.UserRole)
                if g_data:
                    group_name = g_data.get("name")

            self._display_file_preview(item.path, item.tag_scores, item.bbox, group_name)

            # Синхронизация выделения строки в дереве
            if item.tree_item:
                self.tree_results.blockSignals(True)
                self.tree_results.clearSelection()
                item.tree_item.setSelected(True)
                self.tree_results.setCurrentItem(item.tree_item)
                self.tree_results.scrollToItem(item.tree_item)
                self.tree_results.blockSignals(False)

    def _select_grid_item_by_tree_item(self, tree_item):
        if not tree_item:
            return
        for r in range(self.grid_proxy.rowCount()):
            idx = self.grid_proxy.index(r, 0)
            grid_item: AiGridItem = idx.data(Qt.ItemDataRole.UserRole)
            if grid_item and grid_item.tree_item == tree_item:
                self.grid_results.selectionModel().blockSignals(True)
                self.grid_results.setCurrentIndex(idx)
                self.grid_results.selectionModel().select(idx, QItemSelectionModel.SelectionFlag.ClearAndSelect)
                self.grid_results.scrollTo(idx)
                self.grid_results.selectionModel().blockSignals(False)
                break

    def refresh_preview_faces(self):
        if self.tree_results.selectedItems():
            self.on_tree_selection_changed()
        elif self.grid_results.currentIndex().isValid():
            self.on_grid_current_changed(self.grid_results.currentIndex(), QModelIndex())

    # -------------------------------------------------------------------------
    # Синхронизация отметок чекбоксов
    # -------------------------------------------------------------------------
    def _on_grid_item_check_state_changed(self, tree_item, new_state):
        if tree_item:
            self.on_tree_item_changed(tree_item, 0)

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

        # Синхронизируем состояние чекбоксов в сетке
        self.grid_model.notify_all_changed()
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

        self.grid_model.notify_all_changed()
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

        self.grid_model.notify_all_changed()
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

        self.grid_model.notify_all_changed()
        self._emit_selection_stats()

    def remove_processed_files(self, paths: list[str]):
        self.grid_results._stop_hover()
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

        self.grid_model.remove_paths(paths_set)
        self.grid_proxy.invalidateFilter()
        self.preview_widget.show_empty(AppContext.tr("cln_ai_select_file_preview"))
        self._emit_selection_stats()

    def _emit_selection_stats(self):
        selected_paths = self.get_selected_files_paths()
        count = len(selected_paths)
        size = sum(os.path.getsize(p) for p in selected_paths if os.path.exists(p))
        size_str = format_size(size)

        self.lbl_selection_info.setStyleSheet("color: #93c5fd; font-size: 11px; font-weight: bold;")
        self.lbl_selection_info.setText(AppContext.tr("cln_ai_selected_files_info").format(count, size_str))
        self.lbl_selection_info.setToolTip(f"Выбрано файлов: {count}\nРазмер: {size_str}")
        self.selection_changed.emit(count, size)

    # -------------------------------------------------------------------------
    # Контекстные меню (Дерево и Сетка)
    # -------------------------------------------------------------------------
    def show_results_context_menu(self, pos: QPoint):
        item = self.tree_results.itemAt(pos)
        if not item:
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get("is_group", False):
            self._show_group_context_menu(item, self.tree_results.mapToGlobal(pos))
        elif data and not data.get("is_group", False):
            self._show_file_context_menu(data.get("path"), item.parent(), self.tree_results.mapToGlobal(pos))

    def show_grid_context_menu(self, pos: QPoint):
        idx = self.grid_results.indexAt(pos)
        if not idx.isValid():
            return
        grid_item: AiGridItem = idx.data(Qt.ItemDataRole.UserRole)
        if not grid_item or not grid_item.tree_item:
            return
        self._show_file_context_menu(grid_item.path, grid_item.tree_item.parent(), self.grid_results.mapToGlobal(pos))

    def _show_group_context_menu(self, group_item, global_pos: QPoint):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #2b2b2b; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #3b82f6; } QMenu::separator { height: 1px; background: #666; margin: 4px 8px; }")

        act_select = QAction(AppContext.tr("cln_ai_act_select_group"), self)
        act_deselect = QAction(AppContext.tr("cln_ai_act_deselect_group"), self)
        act_invert = QAction(AppContext.tr("cln_ai_act_invert_selection"), self)

        act_select.triggered.connect(lambda: self.set_group_selection_state(group_item, Qt.CheckState.Checked))
        act_deselect.triggered.connect(lambda: self.set_group_selection_state(group_item, Qt.CheckState.Unchecked))
        act_invert.triggered.connect(lambda: self.invert_group_selection(group_item))

        menu.addAction(act_select)
        menu.addAction(act_deselect)
        menu.addAction(act_invert)

        menu.addSeparator()
        act_send_sorter = QAction(AppContext.tr("cln_ai_act_send_group_sorter"), self)
        act_send_sorter.triggered.connect(lambda checked, gi=group_item: self.send_group_to_sorter_requested.emit(gi))
        menu.addAction(act_send_sorter)

        menu.addSeparator()
        act_expand_all = QAction(AppContext.tr("cln_ai_act_expand_all"), self)
        act_collapse_all = QAction(AppContext.tr("cln_ai_act_collapse_all"), self)
        act_expand_all.triggered.connect(self.tree_results.expandAll)
        act_collapse_all.triggered.connect(self.tree_results.collapseAll)
        menu.addAction(act_expand_all)
        menu.addAction(act_collapse_all)

        menu.exec(global_pos)

    def _show_file_context_menu(self, path: str, group_item, global_pos: QPoint):
        if not path:
            return

        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #2b2b2b; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #3b82f6; } QMenu::separator { height: 1px; background: #666; margin: 4px 8px; }")

        act_open = QAction(AppContext.tr("cln_ai_act_open_file"), self)
        act_open.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
        menu.addAction(act_open)

        act_reveal = QAction(AppContext.tr("cln_ai_act_reveal"), self)
        act_reveal.triggered.connect(lambda: reveal_in_explorer(path))
        menu.addAction(act_reveal)

        if group_item:
            menu.addSeparator()

            act_select = QAction(AppContext.tr("cln_ai_act_select_group"), self)
            act_deselect = QAction(AppContext.tr("cln_ai_act_deselect_group"), self)
            act_invert = QAction(AppContext.tr("cln_ai_act_invert_group"), self)

            act_select.triggered.connect(lambda: self.set_group_selection_state(group_item, Qt.CheckState.Checked))
            act_deselect.triggered.connect(lambda: self.set_group_selection_state(group_item, Qt.CheckState.Unchecked))
            act_invert.triggered.connect(lambda: self.invert_group_selection(group_item))

            menu.addAction(act_select)
            menu.addAction(act_deselect)
            menu.addAction(act_invert)

            menu.addSeparator()
            act_send_sorter = QAction(AppContext.tr("cln_ai_act_send_group_sorter"), self)
            act_send_sorter.triggered.connect(lambda checked, gi=group_item: self.send_group_to_sorter_requested.emit(gi))
            menu.addAction(act_send_sorter)

        menu.addSeparator()
        act_expand_all = QAction(AppContext.tr("cln_ai_act_expand_all"), self)
        act_collapse_all = QAction(AppContext.tr("cln_ai_act_collapse_all"), self)
        act_expand_all.triggered.connect(self.tree_results.expandAll)
        act_collapse_all.triggered.connect(self.tree_results.collapseAll)
        menu.addAction(act_expand_all)
        menu.addAction(act_collapse_all)

        menu.exec(global_pos)

    def retranslate_ui(self):
        """Обновление локализованных текстов при смене языка."""
        self.tree_results.setHeaderLabels([
            AppContext.tr("cln_ai_col_filename"),
            AppContext.tr("cln_frag_col_sim"),
            AppContext.tr("cln_frag_col_size"),
            AppContext.tr("cln_frag_col_path")
        ])
        if hasattr(self, 'btn_view_tree'):
            self.btn_view_tree.setToolTip(AppContext.tr("cln_ai_view_tree"))
        if hasattr(self, 'btn_view_grid'):
            self.btn_view_grid.setToolTip(AppContext.tr("cln_ai_view_grid"))
        if hasattr(self, 'slider_zoom'):
            self.slider_zoom.setToolTip(AppContext.tr("cln_ai_zoom_tip"))
        if hasattr(self, 'btn_hover_preview'):
            is_enabled = self.btn_hover_preview.isChecked()
            self._update_hover_btn_style(is_enabled)
        if hasattr(self, 'btn_hover_settings'):
            self.btn_hover_settings.setToolTip(AppContext.tr("cln_ai_hover_settings"))
        if hasattr(self, 'lbl_post_filter'):
            self.lbl_post_filter.setText(AppContext.tr("cln_ai_quick_filter"))
            self.lbl_post_filter.setToolTip(AppContext.tr("cln_ai_quick_filter_tip"))
        if hasattr(self, 'slider_post_filter'):
            self.slider_post_filter.setToolTip(AppContext.tr("cln_ai_quick_filter_tip"))
        if hasattr(self, 'preview_widget') and hasattr(self.preview_widget, 'update_ui_text'):
            self.preview_widget.update_ui_text()
        self._emit_selection_stats()
