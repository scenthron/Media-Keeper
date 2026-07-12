


import os
import subprocess
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QTableWidget, QTableWidgetItem, 
    QHeaderView, QAbstractItemView, QMenu, QLabel, QStyledItemDelegate, QStyle,
    QStyleOptionViewItem, QApplication, QTreeWidget, QTreeWidgetItem
)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl, QPoint, QSize
from PyQt6.QtGui import QAction, QDesktopServices, QCursor, QPalette, QColor, QBrush, QIcon

from utils_common import format_size
from .ui_chart import get_color_for_ext
from config import AppContext

class ColorBlockWidget(QWidget):
    def __init__(self, color_hex):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        frame = QFrame()
        frame.setStyleSheet(f"background-color: {color_hex}; border-radius: 2px; border: 1px solid #ffffff30;")
        frame.setFixedSize(14, 14)
        layout.addWidget(frame)
        layout.addStretch()

class TableTooltipWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.ToolTip | 
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) 
        
        self.setStyleSheet("""
            TableTooltipWidget {
                background-color: #111111;
                border: 1px solid #444444;
                border-radius: 4px;
            }
            QLabel { color: #eeeeee; border: none; background: transparent; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        
        self.lbl_name = QLabel()
        self.lbl_name.setStyleSheet("font-size: 13px; font-weight: bold; color: #ffffff;")
        layout.addWidget(self.lbl_name)
        
        self.lbl_path = QLabel()
        self.lbl_path.setStyleSheet("font-size: 11px; color: #999999; font-family: monospace;")
        self.lbl_path.setWordWrap(False) 
        layout.addWidget(self.lbl_path)
        
        self.lbl_size = QLabel()
        self.lbl_size.setStyleSheet("font-size: 12px; color: #dddddd; font-weight: bold;")
        layout.addWidget(self.lbl_size)
        
        self.adjustSize()

    def update_data(self, name, path, size_str):
        self.lbl_name.setText(name)
        display_path = path
        if len(display_path) > 80:
            display_path = "..." + display_path[-77:]
        self.lbl_path.setText(f"📂 {display_path}")
        self.lbl_size.setText(size_str)
        self.adjustSize()

class SortableTableWidgetItem(QTableWidgetItem):
    def __init__(self, display_text, sort_value):
        super().__init__(display_text)
        self.sort_value = sort_value

    def __lt__(self, other):
        return self.sort_value < other.sort_value

class SortableTreeWidgetItem(QTreeWidgetItem):
    def __init__(self, parent=None):
        super().__init__(parent)
    
    def __lt__(self, other):
        col = self.treeWidget().sortColumn()
        val1 = self.data(col, Qt.ItemDataRole.UserRole)
        val2 = other.data(col, Qt.ItemDataRole.UserRole)
        # If user data is set (for numeric sorting of size), use it
        if val1 is not None and val2 is not None:
            return val1 < val2
        return super().__lt__(other)

class TableHighlightDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        # Если элемент выделен, рисуем стандартное выделение из QSS
        if option.state & QStyle.StateFlag.State_Selected:
            super().paint(painter, option, index)
            return

        # Если задан пользовательский фон, рисуем его
        bg_brush = index.data(Qt.ItemDataRole.BackgroundRole)
        if bg_brush and bg_brush.style() != Qt.BrushStyle.NoBrush:
            painter.save()
            painter.fillRect(option.rect, bg_brush)
            painter.restore()

        super().paint(painter, option, index)

class SummaryTable(QTableWidget):
    row_clicked = pyqtSignal(str) 
    row_hovered = pyqtSignal(str) # Новый сигнал для ховера

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(3)
        self.init_headers()
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(0, 25)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        
        self.setStyleSheet("""
            QTableWidget { background-color: transparent; border: none; }
            QTableWidget::item { padding: 4px; border-bottom: 1px solid #333; color: #ddd; }
            QTableWidget::item:selected { background-color: #3b82f6; color: white; }
            QTableWidget::item:hover { background-color: #2a2a2a; }
            QHeaderView::section { background-color: #2b2b2b; color: #aaa; border: none; font-weight: bold; }
        """)
        
        self.cellClicked.connect(self.on_cell_clicked)
        self.setMouseTracking(True)
        self.entered.connect(self.on_item_entered)
        self._init_tracking()
        self.setItemDelegate(TableHighlightDelegate(self))

    def init_headers(self):
        self.setHorizontalHeaderLabels(["", AppContext.tr("anl_tbl_ext"), AppContext.tr("anl_tbl_size")])

    def update_ui_text(self):
        self.init_headers()

    def populate(self, stats_map):
        self.setSortingEnabled(False) 
        self.setRowCount(0)
        
        sorted_exts = sorted(stats_map.keys(), key=lambda k: stats_map[k]['size'], reverse=True)
        self.setRowCount(len(sorted_exts))
        
        for i, ext in enumerate(sorted_exts):
            data = stats_map[ext]
            color = get_color_for_ext(ext)
            
            self.setCellWidget(i, 0, ColorBlockWidget(color))
            
            lbl = f"{ext} ({data['count']})" if ext else "No Ext"
            self.setItem(i, 1, QTableWidgetItem(lbl))
            
            raw_bytes = data['size']
            sz_str = format_size(raw_bytes)
            
            item_sz = SortableTableWidgetItem(sz_str, raw_bytes)
            self.setItem(i, 2, item_sz)
            
            self.item(i, 1).setData(Qt.ItemDataRole.UserRole, ext)
        
        self.setSortingEnabled(True)

    def on_cell_clicked(self, row, col):
        item = self.item(row, 1)
        if item:
            ext = item.data(Qt.ItemDataRole.UserRole)
            
            # Check if already selected to allow deselect
            if self.currentRow() == self._last_row:
                self.clearSelection()
                self.clearFocus()
                self.setCurrentItem(None)
                self._last_row = -1
                self.row_clicked.emit("") # Signal empty to show all
            else:
                self._last_row = row
                self.row_clicked.emit(ext)

    def _init_tracking(self):
        self._last_row = -1
        self.itemSelectionChanged.connect(self._on_sel_change)

    def _on_sel_change(self):
        if not self.selectedItems():
            self._last_row = -1

    def on_item_entered(self, index):
        item = self.item(index.row(), 1)
        if item:
            ext = item.data(Qt.ItemDataRole.UserRole)
            self.row_hovered.emit(ext if ext else "")

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.row_hovered.emit("")

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        index = self.indexAt(event.pos())
        if not index.isValid():
            self.row_hovered.emit("")

    def select_ext_row(self, ext):
        self.clearSelection()
        if not ext:
            self._last_row = -1
            return
        ext_clean = ext.lower().replace('.', '')
        for r in range(self.rowCount()):
            item_ext_obj = self.item(r, 1)
            if item_ext_obj:
                row_ext = item_ext_obj.data(Qt.ItemDataRole.UserRole)
                if row_ext and row_ext.lower().replace('.', '') == ext_clean:
                    self.blockSignals(True)
                    try:
                        self.selectRow(r)
                        self.setCurrentItem(item_ext_obj)
                        self._last_row = r
                    finally:
                        self.blockSignals(False)
                    break

    def highlight_ext_row(self, ext):
        for r in range(self.rowCount()):
            for c in range(1, self.columnCount()):
                item = self.item(r, c)
                if item:
                    item.setBackground(QBrush(Qt.BrushStyle.NoBrush))
        
        if not ext:
            self.viewport().update()
            return
            
        ext_clean = ext.lower().replace('.', '')
        for r in range(self.rowCount()):
            item_ext_obj = self.item(r, 1)
            if item_ext_obj:
                row_ext = item_ext_obj.data(Qt.ItemDataRole.UserRole)
                if row_ext and row_ext.lower().replace('.', '') == ext_clean:
                    for c in range(1, self.columnCount()):
                        cell_item = self.item(r, c)
                        if cell_item:
                            cell_item.setBackground(QBrush(QColor("#3a3a3a")))
                    break
        self.viewport().update()

class FileDetailTree(QTreeWidget):
    delete_requested = pyqtSignal(str) # path
    move_requested = pyqtSignal(str)   # path
    item_hovered = pyqtSignal(str)     # path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(4)
        self.init_headers()
        h = self.header()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(0, 50) 
        
        # Enable Manual Resizing
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        
        # Set initial comfortable widths
        self.setColumnWidth(1, 300) # Name
        self.setColumnWidth(2, 90)  # Size
        self.setColumnWidth(3, 400) # Path
        
        h.setStretchLastSection(True)
        
        self.setSortingEnabled(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        self.setMouseTracking(True)
        self.setIndentation(12) # Smaller indentation to keep indicator separate from icon
        self.setRootIsDecorated(True)
        
        self.setStyleSheet("""
            QTreeWidget { background-color: #1e1e1e; border: none; }
            QTreeWidget::item { padding: 4px; border-bottom: 1px solid #333; color: #ccc; }
            QTreeWidget::item:selected { background-color: #3b82f6; color: white; }
            QTreeWidget::item:hover { background-color: #2a2a2a; }
            QHeaderView::section { background-color: #333; color: white; padding: 4px; border: none; }
            
            QTreeWidget::indicator { 
                width: 18px; 
                height: 18px; 
                border-radius: 4px; 
                border: 1px solid #666; 
                background: #333; 
                margin-left: 2px;
            }
            QTreeWidget::indicator:checked { background-color: #3b82f6; border-color: #3b82f6; image: url(disabled); }
            QTreeWidget::indicator:unchecked:hover { border-color: #888; }
        """)
        
        self.itemDoubleClicked.connect(self.on_double_click)
        self.itemClicked.connect(self.on_item_clicked)
        self.itemChanged.connect(self.on_item_changed)
        self.itemEntered.connect(self.on_item_entered)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.open_menu)
        
        self.custom_tooltip = TableTooltipWidget(None)
        self._is_updating_checks = False
        self.setItemDelegate(TableHighlightDelegate(self))

    def init_headers(self):
        self.setHeaderLabels(["", AppContext.tr("anl_tbl_name"), AppContext.tr("anl_tbl_size"), AppContext.tr("anl_tbl_path")])

    def update_ui_text(self):
        self.init_headers()
        # Idle message is completely removed per user request, tree remains empty

    def show_idle_message(self, msg=None):
        self.clear()
        self.header().hide()

    def load_files(self, file_list, group_by_dir=False):
        self.setUpdatesEnabled(False)
        self.blockSignals(True)
        try:
            self.header().show()
            self.setSortingEnabled(False)
            self.clear()
            
            # Prepare standard file icon
            icons_dir = AppContext.find_resource_dir("icons")
            file_icon = QIcon(os.path.join(icons_dir, "file.svg"))
            # Background for grouped files: #262626 (Slightly lighter than #1e1e1e)
            group_bg = QBrush(QColor("#262626"))
            
            if group_by_dir:
                # Group Logic
                groups = {}
                for f in file_list:
                    parent_dir = os.path.dirname(f['path'])
                    if parent_dir not in groups:
                        groups[parent_dir] = {'size': 0, 'files': []}
                    groups[parent_dir]['size'] += f['size']
                    groups[parent_dir]['files'].append(f)
                
                # Create Tree Items
                root_items = []
                for folder_path, data in groups.items():
                    folder_name = os.path.basename(folder_path) or folder_path
                    
                    # Root Item (Folder)
                    root = SortableTreeWidgetItem()
                    root.setCheckState(0, Qt.CheckState.Unchecked)
                    root.setText(1, f"📂 {folder_name} ({len(data['files'])})")
                    root.setData(1, Qt.ItemDataRole.UserRole, folder_name) # Sort by name
                    
                    total_size = data['size']
                    root.setText(2, format_size(total_size))
                    root.setData(2, Qt.ItemDataRole.UserRole, total_size) # Sort by size numeric
                    
                    root.setText(3, folder_path)
                    root.setData(3, Qt.ItemDataRole.UserRole, folder_path)
                    
                    root.setExpanded(False)
                    
                    # Children (Files)
                    children = []
                    for f in data['files']:
                        child = SortableTreeWidgetItem()
                        child.setCheckState(0, Qt.CheckState.Unchecked)
                        child.setText(1, f['name'])
                        child.setIcon(1, file_icon) # Add Icon
                        child.setData(1, Qt.ItemDataRole.UserRole, f['name'])
                        child.setData(1, Qt.ItemDataRole.UserRole + 1, f['path']) # Store full path
                        
                        child.setText(2, format_size(f['size']))
                        child.setData(2, Qt.ItemDataRole.UserRole, f['size'])
                        
                        child.setText(3, "-") # Path redundant inside group
                        child.setData(3, Qt.ItemDataRole.UserRole, "")
                        
                        # Highlight background for items in group
                        for c in range(4):
                            child.setBackground(c, group_bg)
                        children.append(child)
                    
                    root.addChildren(children)
                    root_items.append(root)
                
                self.addTopLevelItems(root_items)
                
            else:
                # Flat Logic
                flat_items = []
                for f in file_list:
                    item = SortableTreeWidgetItem()
                    item.setCheckState(0, Qt.CheckState.Unchecked)
                    item.setText(1, f['name'])
                    item.setIcon(1, file_icon) # Add Icon
                    item.setData(1, Qt.ItemDataRole.UserRole, f['name'])
                    item.setData(1, Qt.ItemDataRole.UserRole + 1, f['path']) # Store full path
                    
                    item.setText(2, format_size(f['size']))
                    item.setData(2, Qt.ItemDataRole.UserRole, f['size'])
                    
                    folder_path = os.path.dirname(f['path'])
                    item.setText(3, folder_path)
                    item.setData(3, Qt.ItemDataRole.UserRole, folder_path)
                    flat_items.append(item)
                
                self.addTopLevelItems(flat_items)
                
            self.setSortingEnabled(True)
            # Default sort by size descending
            self.sortItems(2, Qt.SortOrder.DescendingOrder)
        finally:
            self.blockSignals(False)
            self.setUpdatesEnabled(True)

    def on_item_changed(self, item, column):
        if column != 0 or self._is_updating_checks:
            return
        
        self._is_updating_checks = True
        state = item.checkState(0)
        
        # If folder checked, check all children
        if item.childCount() > 0:
            for i in range(item.childCount()):
                item.child(i).setCheckState(0, state)
        
        # If child changed, update parent
        parent = item.parent()
        if parent:
            all_checked = True
            all_unchecked = True
            for i in range(parent.childCount()):
                if parent.child(i).checkState(0) == Qt.CheckState.Checked:
                    all_unchecked = False
                else:
                    all_checked = False
            
            if all_checked:
                parent.setCheckState(0, Qt.CheckState.Checked)
            elif all_unchecked:
                parent.setCheckState(0, Qt.CheckState.Unchecked)
            else:
                parent.setCheckState(0, Qt.CheckState.PartiallyChecked)
                
        self._is_updating_checks = False

    def select_all(self, select=True):
        self._is_updating_checks = True
        state = Qt.CheckState.Checked if select else Qt.CheckState.Unchecked
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            item.setCheckState(0, state)
            if item.childCount() > 0:
                for j in range(item.childCount()):
                    item.child(j).setCheckState(0, state)
        self._is_updating_checks = False

    def get_selected_files(self):
        selected = []
        # Recursive helper might be better but flat structure is simple
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.childCount() > 0:
                for j in range(item.childCount()):
                    child = item.child(j)
                    if child.checkState(0) == Qt.CheckState.Checked:
                        path = child.data(1, Qt.ItemDataRole.UserRole + 1)
                        if path: selected.append(path)
            else:
                if item.checkState(0) == Qt.CheckState.Checked:
                    path = item.data(1, Qt.ItemDataRole.UserRole + 1)
                    if path: selected.append(path)
        return selected

    def safe_open(self, path):
        try:
            if path and os.path.exists(path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception as e:
            logging.error(f"Failed to open path {path}: {e}", exc_info=True)

    def on_double_click(self, item, col):
        try:
            # Retrieve path. If grouped, path is in UserRole+1 for children. 
            # For folders (roots in grouped mode), logic differs.
            
            # Check if item is a group root (Folder) - Don't open explorer on double click per request
            if item.childCount() > 0:
                return 

            path = item.data(1, Qt.ItemDataRole.UserRole + 1)
            if not path:
                # Maybe it's a flat list item or a folder without children?
                # Check column 3
                path_col3 = item.text(3)
                if os.path.exists(path_col3) and os.path.isdir(path_col3):
                    # It's a folder. Ignore double click.
                    return
            
            if path and os.path.exists(path):
                self.safe_open(path)
        except Exception as e:
            logging.error(f"Error on double click in detail tree: {e}", exc_info=True)

    def on_item_clicked(self, item, col):
        # Click on folder row toggles expansion
        if item.childCount() > 0 and col != 0:
            item.setExpanded(not item.isExpanded())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            item = self.itemAt(event.pos())
            if item:
                path = item.data(1, Qt.ItemDataRole.UserRole + 1)
                if path and os.path.exists(path):
                    self.reveal_file(path)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if self.custom_tooltip.isVisible():
            global_pos = event.globalPosition().toPoint()
            offset = QPoint(20, 20)
            self.custom_tooltip.move(global_pos + offset)
            
        item = self.itemAt(event.pos())
        if not item:
            self.item_hovered.emit("")
        else:
            path = item.data(1, Qt.ItemDataRole.UserRole + 1)
            self.item_hovered.emit(path if path else "")

    def leaveEvent(self, event):
        self.custom_tooltip.hide()
        self.item_hovered.emit("")
        super().leaveEvent(event)

    def on_item_entered(self, item):
        if not item:
            self.item_hovered.emit("")
            return
            
        name = item.text(1)
        size_str = item.text(2)
        
        path = item.data(1, Qt.ItemDataRole.UserRole + 1)
        self.item_hovered.emit(path if path else "")
        
        if not path:
            path = item.text(3)
            
        if not path or path == "-": return
        
        self.custom_tooltip.update_data(name, path, size_str)
        
        if self.custom_tooltip.isHidden():
            self.custom_tooltip.show()
            cursor_pos = QCursor.pos()
            offset = QPoint(20, 20)
            self.custom_tooltip.move(cursor_pos + offset)

    def highlight_file_row(self, filepath):
        if not hasattr(self, '_highlighted_item'):
            self._highlighted_item = None
            
        if self._highlighted_item:
            try:
                parent_item = self._highlighted_item.parent()
                bg = QBrush(QColor("#262626")) if parent_item else QBrush(Qt.BrushStyle.NoBrush)
                for c in range(self.columnCount()):
                    self._highlighted_item.setBackground(c, bg)
            except RuntimeError:
                pass
            self._highlighted_item = None
            
        if not filepath:
            self.viewport().update()
            return
            
        norm_path = os.path.normcase(os.path.normpath(filepath))
        
        def find_and_highlight(parent):
            count = parent.childCount() if isinstance(parent, QTreeWidgetItem) else parent.topLevelItemCount()
            for i in range(count):
                item = parent.child(i) if isinstance(parent, QTreeWidgetItem) else parent.topLevelItem(i)
                item_path = item.data(1, Qt.ItemDataRole.UserRole + 1)
                if item_path and os.path.normcase(os.path.normpath(item_path)) == norm_path:
                    for c in range(self.columnCount()):
                        item.setBackground(c, QBrush(QColor("#3a3a3a")))
                    self._highlighted_item = item
                    p = item.parent()
                    if p:
                        p.setExpanded(True)
                    return True
                if item.childCount() > 0:
                    if find_and_highlight(item):
                        return True
            return False
            
        find_and_highlight(self)
        self.viewport().update()

    def select_file_row(self, filepath):
        self.blockSignals(True)
        try:
            self.clearSelection()
            if not filepath:
                return False
            norm_path = os.path.normcase(os.path.normpath(filepath))
            
            def find_and_select(parent):
                count = parent.childCount() if isinstance(parent, QTreeWidgetItem) else parent.topLevelItemCount()
                for i in range(count):
                    item = parent.child(i) if isinstance(parent, QTreeWidgetItem) else parent.topLevelItem(i)
                    item_path = item.data(1, Qt.ItemDataRole.UserRole + 1)
                    if item_path and os.path.normcase(os.path.normpath(item_path)) == norm_path:
                        item.setSelected(True)
                        self.setCurrentItem(item)
                        p = item.parent()
                        if p:
                            p.setExpanded(True)
                        self.scrollToItem(item)
                        return True
                    if item.childCount() > 0:
                        if find_and_select(item):
                            return True
                return False
            return find_and_select(self)
        finally:
            self.blockSignals(False)

    def reveal_file(self, path):
        try:
            if path and os.path.exists(path):
                from utils_common import reveal_in_explorer
                reveal_in_explorer(path)
        except Exception as e:
            logging.error(f"Failed to reveal file {path}: {e}", exc_info=True)
    def trigger_disassemble(self, folder_path):
        if not folder_path or not os.path.exists(folder_path):
            return
        shell = self.window()
        if shell and hasattr(shell, "sorter_tab") and hasattr(shell, "switch_tab"):
            shell.sorter_tab.set_session_inbox(folder_path)
            shell.switch_tab(0)

    def _send_all_to_sorter(self):
        files = []
        total_size = 0
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.childCount() > 0:
                for j in range(item.childCount()):
                    child = item.child(j)
                    path = child.data(1, Qt.ItemDataRole.UserRole + 1)
                    if path and os.path.exists(path):
                        files.append(path)
                        size_val = child.data(2, Qt.ItemDataRole.UserRole)
                        if isinstance(size_val, (int, float)):
                            total_size += size_val
            else:
                path = item.data(1, Qt.ItemDataRole.UserRole + 1)
                if path and os.path.exists(path):
                    files.append(path)
                    size_val = item.data(2, Qt.ItemDataRole.UserRole)
                    if isinstance(size_val, (int, float)):
                        total_size += size_val
                    
        if not files: return
        
        from utils_common import format_size
        virtual_name = f"Анализатор диска ({len(files)} файлов, {format_size(total_size)})"
        
        shell = self.window()
        if shell and hasattr(shell, 'sorter_tab') and hasattr(shell, 'switch_tab'):
            shell.sorter_tab.load_virtual_files(files, virtual_name)
            shell.switch_tab(0)


    def open_menu(self, pos):
        item = self.itemAt(pos)
        if not item: return
        
        path = item.data(1, Qt.ItemDataRole.UserRole + 1) # File path
        is_folder = False
        
        if not path:
            # Try folder path from col 3 (path display) or UserRole of col 3
            path = item.data(3, Qt.ItemDataRole.UserRole)
            is_folder = True
            
        if not path or not os.path.exists(path): return
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: #2b2b2b; color: white; border: 1px solid #444; padding: 4px; }
            QMenu::item { padding: 4px 20px; border-radius: 4px; }
            QMenu::item:selected { background: #3b82f6; }
            QMenu::item:disabled { color: #555; }
            QMenu::separator { height: 1px; background: #444; margin: 4px 0; }
        """)
        
        if not is_folder:
            # 1. Open File
            a_open = QAction(f"📄 {AppContext.tr('anl_ctx_file_open')}", self)
            a_open.triggered.connect(lambda: self.safe_open(path))
            menu.addAction(a_open)

            # 2. Show in folder (REVEAL with focus)
            a_reveal = QAction(f"🔍 {AppContext.tr('anl_ctx_reveal')}", self)
            a_reveal.triggered.connect(lambda: self.reveal_file(path))
            menu.addAction(a_reveal)

            menu.addSeparator()

            # 3. Move
            a_move = QAction(f"📦 {AppContext.tr('anl_btn_move')}", self)
            from .ui_main import AnalyzerWidget
            p = self.parent()
            while p and not isinstance(p, AnalyzerWidget): p = p.parent()

            move_enabled = p.btn_move_files.isEnabled() if p else False
            a_move.setEnabled(move_enabled)
            a_move.triggered.connect(lambda: self.move_requested.emit(path))
            menu.addAction(a_move)

            # 3.5 Move to (select folder)
            a_move_to = QAction(f"📂 {AppContext.tr('anl_ctx_move_to')}", self)
            move_to_enabled = p.btn_move_to.isEnabled() if p else False
            a_move_to.setEnabled(move_to_enabled)
            if p:
                a_move_to.triggered.connect(p.on_move_to_clicked)
            menu.addAction(a_move_to)

            menu.addSeparator()

            # 4. Delete
            a_del = QAction(f"🗑️ {AppContext.tr('anl_btn_delete')}", self)
            a_del.setProperty("is_danger", True)
            a_del.triggered.connect(lambda: self.delete_requested.emit(path))
            menu.addAction(a_del)

            menu.setStyleSheet(menu.styleSheet() + """
                QMenu::item[is_danger="true"]:selected { background: #dc2626; color: white; }
            """)
        else:
            # Folder actions
            a_open_dir = QAction(f"📂 {AppContext.tr('anl_ctx_open')}", self)
            a_open_dir.triggered.connect(lambda: self.safe_open(path))
            menu.addAction(a_open_dir)

            a_reveal_dir = QAction(f"🔍 {AppContext.tr('anl_ctx_folder_select')}", self)
            a_reveal_dir.triggered.connect(lambda: self.reveal_file(path))
            menu.addAction(a_reveal_dir)

            # Disassemble in Sorter
            menu.addSeparator()
            a_disassemble = QAction(f"⚡ {AppContext.tr('anl_ctx_disassemble')}", self)
            a_disassemble.triggered.connect(lambda: self.trigger_disassemble(path))
            menu.addAction(a_disassemble)

        menu.addSeparator()
        a_send_all = QAction("📤 Отправить список в Сортировщик", self)
        a_send_all.triggered.connect(self._send_all_to_sorter)
        menu.addAction(a_send_all)

        menu.exec(self.mapToGlobal(pos))