
import os
import subprocess
from PyQt6.QtWidgets import (QTableWidget, QStyledItemDelegate, QStyle, QAbstractItemView, QMenu, QHeaderView, QTableWidgetItem)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QCursor
from config import AppContext
from .helpers import format_file_info

class DeleteRowDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        
    def paint(self, painter, option, index):
        # Get table and check row state
        table = self.parent()
        row = index.row()
        is_hovered = False
        if hasattr(table, 'hovered_row'):
            is_hovered = (table.hovered_row == row)
        
        # Check conversion status from parent widget
        parent_widget = table.parent()
        while parent_widget and not hasattr(parent_widget, 'files'):
            parent_widget = parent_widget.parent()
        
        status = None
        progress = None
        if parent_widget and hasattr(parent_widget, 'files'):
            if row < len(parent_widget.files):
                status = parent_widget.files[row].get('status', 'Wait')
                progress = parent_widget.files[row].get('progress', None)
        
        painter.save()
        
        # Draw background based on status
        if status == 'Done':
            # Green background
            painter.fillRect(option.rect, QColor(34, 197, 94))  # Green
        elif status == 'Error':
            # Red background
            painter.fillRect(option.rect, QColor(239, 68, 68))  # Red
        elif status == 'Converting' and progress is not None:
            # Show progress percentage (no special background)
            pass
        
        # Draw content
        if status == 'Converting' and progress is not None:
            # Show progress percentage
            painter.setPen(QColor("white"))
            font = painter.font()
            font.setPixelSize(12)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, f"{progress}%")
        elif is_hovered and status != 'Converting':
            # Show red cross for all except Converting
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            cross_color = QColor("#ef4444")
            if option.state & QStyle.StateFlag.State_MouseOver:
                cross_color = QColor("#ff6666")
            painter.setPen(cross_color)
            font = painter.font()
            font.setPixelSize(14)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, "✖")
        else:
            # Draw standard index number
            super().paint(painter, option, index)
        
        painter.restore()

    def editorEvent(self, event, model, option, index):
        # Only allow delete if not converting
        if event.type() == event.Type.MouseButtonRelease:
            table = self.parent()
            row = index.row()
            
            # Check if file is converting
            parent_widget = table.parent()
            while parent_widget and not hasattr(parent_widget, 'files'):
                parent_widget = parent_widget.parent()
            
            if parent_widget and hasattr(parent_widget, 'files'):
                if row < len(parent_widget.files):
                    status = parent_widget.files[row].get('status', 'Wait')
                    if status == 'Converting':
                        return False  # Don't allow delete during conversion
            
            if hasattr(table, 'hovered_row') and table.hovered_row == row:
                if hasattr(table, 'delete_request_signal'):
                    table.delete_request_signal.emit(row)
                    return True
        return super().editorEvent(event, model, option, index)

class FileDropTable(QTableWidget):
    files_dropped = pyqtSignal(list)
    delete_request_signal = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setDropIndicatorShown(True)
        self.setMouseTracking(True)
        self.hovered_row = -1

    def mouseDoubleClickEvent(self, event):
        # Double-click opens file
        item = self.itemAt(event.pos())
        if item:
            row = item.row()
            col = item.column()
            # Get parent widget to access files list
            parent_widget = self.parent()
            while parent_widget and not hasattr(parent_widget, 'files'):
                parent_widget = parent_widget.parent()
            
            if parent_widget and hasattr(parent_widget, 'files'):
                if row < len(parent_widget.files):
                    # Column 1 = source, Column 2 = result
                    if col == 2:  # Result column
                        file_path = parent_widget.files[row].get('output_path', '')
                    else:  # Source or any other column
                        file_path = parent_widget.files[row]['path']
                    
                    if file_path:
                        paths = [p.strip() for p in file_path.split(';') if p.strip()]
                        for fp in paths:
                            if os.path.exists(fp):
                                try:
                                    os.startfile(os.path.normpath(fp))
                                except Exception as e:
                                    print(f"Error opening file: {e}")
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        """Middle button opens folder containing the file"""
        if event.button() == Qt.MouseButton.MiddleButton:
            item = self.itemAt(event.pos())
            if item:
                row = item.row()
                col = item.column()
                # Get parent widget to access files list
                parent_widget = self.parent()
                while parent_widget and not hasattr(parent_widget, 'files'):
                    parent_widget = parent_widget.parent()
                
                if parent_widget and hasattr(parent_widget, 'files'):
                    if row < len(parent_widget.files):
                        # Column 1 = source, Column 2 = result
                        if col == 2:  # Result column
                            file_path = parent_widget.files[row].get('output_path', '')
                        else:  # Source or any other column
                            file_path = parent_widget.files[row]['path']
                        
                        # Open folder and select file
                        if file_path:
                            paths = [p.strip() for p in file_path.split(';') if p.strip()]
                            for fp in paths:
                                if os.path.exists(fp):
                                     try:
                                         from utils_common import reveal_in_explorer
                                         reveal_in_explorer(fp)
                                         break
                                     except Exception as e:
                                        print(f"Error opening folder: {e}")
            return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        """Right click shows context menu"""
        item = self.itemAt(event.pos())
        if item:
            row = item.row()
            col = item.column()
            # Get parent widget to access files list
            parent_widget = self.parent()
            while parent_widget and not hasattr(parent_widget, 'files'):
                parent_widget = parent_widget.parent()
            
            if parent_widget and hasattr(parent_widget, 'files'):
                if row < len(parent_widget.files):
                    if col == 2:  # Result column
                        file_path = parent_widget.files[row].get('output_path', '')
                    else:  # Source or any other column
                        file_path = parent_widget.files[row]['path']
                    
                    # Create context menu
                    menu = QMenu(self)
                    menu.setStyleSheet("""
                        QMenu {
                            background-color: #2b2b2b;
                            color: #eee;
                            border: 1px solid #555;
                        }
                        QMenu::item:selected {
                            background-color: #3b82f6;
                        }
                    """)
                    
                    paths = [p.strip() for p in file_path.split(';') if p.strip()] if file_path else []
                    existing_paths = [p for p in paths if os.path.exists(p)]
                    
                    action_open = menu.addAction(AppContext.tr("ctx_open_file"))
                    action_folder = menu.addAction(AppContext.tr("ctx_open_folder"))
                    
                    if not existing_paths:
                        action_open.setEnabled(False)
                        action_folder.setEnabled(False)
                        
                    menu.addSeparator()
                    action_delete = menu.addAction(AppContext.tr("ctx_delete_from_list"))
                    
                    # Show menu and handle action
                    action = menu.exec(QCursor.pos())
                    
                    if action == action_open:
                        for fp in existing_paths:
                            try:
                                os.startfile(os.path.normpath(fp))
                            except Exception as e:
                                print(f"Error opening file: {e}")
                    elif action == action_folder:
                        for fp in existing_paths:
                            try:
                                from utils_common import reveal_in_explorer
                                reveal_in_explorer(fp)
                                break
                            except Exception as e:
                                print(f"Error opening folder: {e}")
                    elif action == action_delete:
                        self.delete_request_signal.emit(row)

    def mouseMoveEvent(self, event):
        item = self.itemAt(event.pos())
        old_hover = self.hovered_row
        if item:
            self.hovered_row = item.row()
        else:
            # Maybe we are in empty space
            self.hovered_row = -1
            
        if self.hovered_row != old_hover:
            self.viewport().update()
            
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.hovered_row = -1
        self.viewport().update()
        super().leaveEvent(event)

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
            urls = event.mimeData().urls()
            paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
