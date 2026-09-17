import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QLabel, QSplitter, QAbstractItemView, QFrame, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QUrl, QTimer
from PyQt6.QtGui import QIcon, QColor, QFont
import time
from config import AppContext, VIEWER_DESIGN
from utils_common import format_size
from utils_extensions import IMAGE_EXTS, VIDEO_EXTS, AUDIO_EXTS
from modules.cleaner.ui_preview import CleanerPreviewWidget
from utils_io import ensure_long_path, strip_long_path_prefix

class TableActionHeader(QFrame):
    """Панель над таблицей со счетчиком и кнопками управления выделением."""
    select_all_requested = pyqtSignal()
    deselect_all_requested = pyqtSignal()
    invert_selection_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setStyleSheet(f"background-color: {VIEWER_DESIGN['player_bg']}; border-bottom: 1px solid #333;")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        
        self.lbl_stats = QLabel("Выбрано: 0 из 0 (0 Б)")
        self.lbl_stats.setStyleSheet("color: #ccc; font-size: 13px; font-weight: bold; border: none;")
        
        btn_style = """
            QPushButton {
                background-color: #333; color: white; border-radius: 4px; padding: 4px 10px; font-size: 12px;
            }
            QPushButton:hover { background-color: #444; }
            QPushButton:pressed { background-color: #555; }
        """
        
        self.btn_select_all = QPushButton("Выбрать всё")
        self.btn_select_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_select_all.setStyleSheet(btn_style)
        self.btn_select_all.clicked.connect(self.select_all_requested.emit)
        
        self.btn_deselect_all = QPushButton("Снять всё")
        self.btn_deselect_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_deselect_all.setStyleSheet(btn_style)
        self.btn_deselect_all.clicked.connect(self.deselect_all_requested.emit)
        
        self.btn_invert = QPushButton("Инвертировать")
        self.btn_invert.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_invert.setStyleSheet(btn_style)
        self.btn_invert.clicked.connect(self.invert_selection_requested.emit)
        
        layout.addWidget(self.btn_select_all)
        layout.addWidget(self.btn_deselect_all)
        layout.addWidget(self.btn_invert)
        layout.addStretch()
        layout.addWidget(self.lbl_stats)

    def update_stats(self, count: int, total: int, size_bytes: int):
        self.lbl_stats.setText(f"Выбрано: {count} из {total} ({format_size(size_bytes)})")


class SorterTableView(QTableWidget):
    """Высокопроизводительная таблица для Сортировщика."""
    itemSelectionChanged = pyqtSignal()
    item_double_clicked = pyqtSignal(str) # Emits full path
    current_item_changed = pyqtSignal(str) # Emits full path when row changes
    send_to_editor_requested = pyqtSignal(str, list)
    delete_files_requested = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(["[X]", "Имя", "Тип", "Размер", "Дата"])
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        
        self.setColumnWidth(0, 40)
        self.setColumnWidth(2, 60)
        self.setColumnWidth(3, 80)
        self.setColumnWidth(4, 130)
        
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAlternatingRowColors(True)
        
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        
        self.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e1e;
                alternate-background-color: #252525;
                color: #ddd;
                border: none;
                outline: none;
            }
            QTableWidget::item { padding: 4px; border: none; }
            QTableWidget::item:selected { background-color: #3b82f6; color: white; }
            QHeaderView::section {
                background-color: #2b2b2b;
                color: #aaa;
                padding: 4px;
                border: none;
                border-bottom: 1px solid #444;
                border-right: 1px solid #333;
                font-weight: bold;
            }
            QTableWidget::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #666;
                border-radius: 3px;
                background-color: #2b2b2b;
            }
            QTableWidget::indicator:hover {
                border-color: #3b82f6;
            }
            QTableWidget::indicator:checked {
                background-color: #3b82f6;
                border: 1px solid #2563eb;
                image: url(src/assets/icons/check.svg);
            }
            QTableWidget::indicator:unchecked {
                background-color: #2b2b2b;
            }
        """)
        
        self.cellDoubleClicked.connect(self._on_double_clicked)
        self.currentItemChanged.connect(self._on_current_changed)
        self.cellClicked.connect(self._on_cell_clicked)
        
        self.all_files = [] 
        
    def populate(self, files):
        self.all_files = files
        self.setUpdatesEnabled(False)
        self.setRowCount(0)
        self.setRowCount(len(files))
        
        from datetime import datetime
        
        for row, f in enumerate(files):
            path, mtime, size = f
            
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            chk_item.setCheckState(Qt.CheckState.Unchecked)
            chk_item.setData(Qt.ItemDataRole.UserRole, path)
            self.setItem(row, 0, chk_item)
            
            name = os.path.basename(path)
            name_item = QTableWidgetItem(name)
            self.setItem(row, 1, name_item)
            
            ext = os.path.splitext(name)[1].lower()
            type_item = QTableWidgetItem(ext)
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row, 2, type_item)
            
            size_item = QTableWidgetItem(format_size(size))
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.setItem(row, 3, size_item)
            
            try:
                dt_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            except:
                dt_str = ""
            date_item = QTableWidgetItem(dt_str)
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row, 4, date_item)
            
        self.setUpdatesEnabled(True)
        self.scrollToTop()
        self.itemSelectionChanged.emit()


    def insert_file(self, row, path):
        self.setUpdatesEnabled(False)
        self.insertRow(row)
        
        try:
            stat = os.stat(path)
            mtime = stat.st_mtime
            size = stat.st_size
        except:
            mtime = 0.0
            size = 0
            
        from datetime import datetime
        from utils_io import format_size
        
        chk_item = QTableWidgetItem()
        chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        chk_item.setCheckState(Qt.CheckState.Unchecked)
        chk_item.setData(Qt.ItemDataRole.UserRole, path)
        self.setItem(row, 0, chk_item)
        
        name = os.path.basename(path)
        name_item = QTableWidgetItem(name)
        self.setItem(row, 1, name_item)
        
        ext = os.path.splitext(name)[1].lower()
        type_item = QTableWidgetItem(ext)
        type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 2, type_item)
        
        size_item = QTableWidgetItem(format_size(size))
        size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setItem(row, 3, size_item)
        
        try:
            dt_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        except:
            dt_str = ""
        date_item = QTableWidgetItem(dt_str)
        date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 4, date_item)
        
        self.setUpdatesEnabled(True)
    def remove_files(self, paths):
        from utils_io import strip_long_path_prefix
        paths_set = set(os.path.normpath(strip_long_path_prefix(p)) for p in paths)
        
        rows_to_delete = []
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item:
                path = item.data(Qt.ItemDataRole.UserRole)
                if path and os.path.normpath(strip_long_path_prefix(path)) in paths_set:
                    rows_to_delete.append(row)
                    
        self.setUpdatesEnabled(False)
        for row in sorted(rows_to_delete, reverse=True):
            self.removeRow(row)
        self.setUpdatesEnabled(True)
        self.itemSelectionChanged.emit()

    def get_checked_files(self):
        checked = []
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                checked.append(item.data(Qt.ItemDataRole.UserRole))
        return checked

    def get_checked_size(self):
        total_size = 0
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                if row < len(self.all_files):
                    total_size += self.all_files[row][2]
        return total_size

    def select_all_rows(self, state=True):
        self.setUpdatesEnabled(False)
        st = Qt.CheckState.Checked if state else Qt.CheckState.Unchecked
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item:
                item.setCheckState(st)
        self.setUpdatesEnabled(True)
        self.itemSelectionChanged.emit()
        
    def invert_selection(self):
        self.setUpdatesEnabled(False)
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item:
                st = Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
                item.setCheckState(st)
        self.setUpdatesEnabled(True)
        self.itemSelectionChanged.emit()

    def _on_double_clicked(self, row, col):
        item = self.item(row, 0)
        if item:
            path = item.data(Qt.ItemDataRole.UserRole)
            self.item_double_clicked.emit(path)

    def _on_current_changed(self, current, previous):
        if current:
            item = self.item(current.row(), 0)
            if item:
                path = item.data(Qt.ItemDataRole.UserRole)
                self.current_item_changed.emit(path)

    def _on_cell_clicked(self, row, col):
        if col == 0:
            self.itemSelectionChanged.emit()
            if row + 1 < self.rowCount():
                self.setCurrentCell(row + 1, 0)
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            item = self.itemAt(event.pos())
            if item:
                row = item.row()
                chk_item = self.item(row, 0)
                if chk_item:
                    path = chk_item.data(Qt.ItemDataRole.UserRole)
                    if path:
                        self._open_folder_with_focus(path)
            event.accept()
            return
        super().mousePressEvent(event)


    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            row = self.currentRow()
            if row >= 0:
                item = self.item(row, 0)
                if item:
                    st = Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
                    item.setCheckState(st)
                    self.itemSelectionChanged.emit()
                    if row + 1 < self.rowCount():
                        self.setCurrentCell(row + 1, 1)
            event.accept()
            return
        super().keyPressEvent(event)



    def _on_context_menu(self, pos):
        item = self.itemAt(pos)
        if not item:
            return
            
        row = item.row()
        
        # Determine paths
        # If there are checked items, use them, otherwise use the selected row
        checked = self.get_checked_files()
        if checked:
            paths = checked
        else:
            chk_item = self.item(row, 0)
            if chk_item:
                paths = [chk_item.data(Qt.ItemDataRole.UserRole)]
            else:
                paths = []
                
        paths = [p for p in paths if os.path.exists(p)]
        if not paths:
            return
            
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction
        
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
        
        if len(paths) == 1:
            path = paths[0]
            ext = os.path.splitext(path)[1].lower()
            
            act_open = QAction(AppContext.tr("srt_ctx_open_file"), self)
            act_open.triggered.connect(lambda Checked, p=path: self._open_file(p))
            menu.addAction(act_open)

            act_folder = QAction(AppContext.tr("srt_ctx_open_folder"), self)
            act_folder.triggered.connect(lambda Checked, p=path: self._open_folder_with_focus(p))
            menu.addAction(act_folder)
            
            if ext in VIDEO_EXTS:
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
                
            elif ext in AUDIO_EXTS:
                menu.addSeparator()
                act_aconv = QAction(AppContext.tr("srt_ctx_convert_audio"), self)
                act_aconv.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("audio_conv", p))
                menu.addAction(act_aconv)
                
                act_aedit = QAction(AppContext.tr("srt_ctx_edit_audio"), self)
                act_aedit.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("audio_edit", p))
                menu.addAction(act_aedit)
                
            elif ext in IMAGE_EXTS:
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
            is_all_video = all(os.path.splitext(p)[1].lower() in VIDEO_EXTS for p in paths)
            is_all_audio = all(os.path.splitext(p)[1].lower() in AUDIO_EXTS for p in paths)
            is_all_image = all(os.path.splitext(p)[1].lower() in IMAGE_EXTS for p in paths)
            
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
        act_delete.triggered.connect(lambda checked, p=paths: self.delete_files_requested.emit(p))
        menu.addAction(act_delete)

        if menu.actions():
            menu.exec(self.mapToGlobal(pos))
            
    def _open_file(self, path):
        import logging
        try:
            os.startfile(os.path.normpath(path))
        except Exception as e:
            logging.error(f"Cannot open file '{path}': {e}")

    def _open_folder_with_focus(self, path):
        import logging
        try:
            from utils_common import reveal_in_explorer
            reveal_in_explorer(path)
        except Exception as e:
            logging.error(f"Cannot open folder for '{path}': {e}")

class TableModeContainer(QWidget):
    """Общий контейнер для табличного режима (Превью сверху, Таблица снизу)."""
    items_dropped = pyqtSignal(list, bool)
    itemSelectionChanged = pyqtSignal()
    send_to_editor_requested = pyqtSignal(str, list)
    item_double_clicked = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #111;")
        self.setAcceptDrops(True)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(self.splitter)
        
        self.preview_container = QFrame()
        self.preview_container.setStyleSheet("background-color: #0a0a0a;")
        preview_layout = QVBoxLayout(self.preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_widget = CleanerPreviewWidget(self)
        self.preview_widget.setAcceptDrops(False)
        preview_layout.addWidget(self.preview_widget)
        
        bottom_container = QWidget()
        bottom_layout = QVBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)
        
        self.header = TableActionHeader()
        self.table = SorterTableView()
        self.table.setAcceptDrops(False)
        
        bottom_layout.addWidget(self.header)
        bottom_layout.addWidget(self.table)
        
        self.splitter.addWidget(self.preview_container)
        self.splitter.addWidget(bottom_container)
        
        self.splitter.setSizes([500, 500])
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        
        self.header.select_all_requested.connect(lambda: self.table.select_all_rows(True))
        self.header.deselect_all_requested.connect(lambda: self.table.select_all_rows(False))
        self.header.invert_selection_requested.connect(self.table.invert_selection)
        
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.table.current_item_changed.connect(self._on_current_item_changed)
        self.table.item_double_clicked.connect(self.item_double_clicked.emit)
        self.table.send_to_editor_requested.connect(self.send_to_editor_requested.emit)
        self.table.delete_files_requested.connect(self._on_delete_requested)


    def _on_delete_requested(self, file_paths):
        p = self.get_viewer_area()
        if p:
            main_app = p.get_main_app()
            if main_app and hasattr(main_app, 'delete_files_permanently'):
                main_app.delete_files_permanently(file_paths)
    def _on_table_selection_changed(self):
        checked = self.table.get_checked_files()
        checked_size = self.table.get_checked_size()
        total = self.table.rowCount()
        self.header.update_stats(len(checked), total, checked_size)
        self.itemSelectionChanged.emit()

    def _on_current_item_changed(self, path):
        self.preview_widget.load_file(path)

    # --- Dummy methods to absorb QListWidget calls from SorterViewerArea ---
    @property
    def icon_size(self): return 0
    
    def addItem(self, item): pass
    def insertItem(self, idx, item): pass
    def setItemWidget(self, item, widget): pass
    def itemWidget(self, item): return None
    def doItemsLayout(self): pass
    def count(self): return 0
    def item(self, i): return None
    def removeItemWidget(self, item): pass
    def clearSelection(self): self.table.clearSelection()
    def setCurrentItem(self, item): pass
    def scrollToItem(self, item): pass
    def verticalScrollBar(self): return self.table.verticalScrollBar()
    def check_hover_under_mouse(self): pass
    def blockSignals(self, b): return super().blockSignals(b)
    # -----------------------------------------------------------------------

    def _stop_hover_playback(self, force=False):
        pass
        
    def setUpdatesEnabled(self, enabled):
        self.table.setUpdatesEnabled(enabled)
        
    def clear(self):
        self.table.setRowCount(0)
        self.table.all_files = []
        self.preview_widget.stop_playback(True)
        self.preview_widget.show_empty("Превью")
        
    def populate(self, files):
        self.table.populate(files)

    def get_viewer_area(self):
        p = self.parent()
        while p:
            if hasattr(p, 'grid_view') and hasattr(p, 'list_view'):
                return p
            p = p.parent()
        return None


    def insert_file(self, row, path):
        self.table.insert_file(row, path)
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            paths = [url.toLocalFile() for url in event.mimeData().urls()]
            if paths:
                self.items_dropped.emit(paths, False)
                event.acceptProposedAction()
                return
        super().dropEvent(event)
