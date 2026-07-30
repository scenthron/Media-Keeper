import os
import datetime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QTableWidget, QTableWidgetItem, QHeaderView, QMenu, QAbstractItemView, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QPoint
from PyQt6.QtGui import QIcon, QPixmap, QColor, QClipboard

from config import AppContext
from utils_common import format_size
from logic_paths import get_app_data_dir
from .logic_journal import MoveJournal

class JournalDialog(QDialog):
    do_undo_entry = pyqtSignal(dict) # Эмитит весь словарь entry

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Журнал перемещений")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(800, 500)
        self.journal = MoveJournal.inst()
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Дата/Время", "Файлы", "Откуда", "Куда", "Действие"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        
        layout.addWidget(self.table)
        
        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("Обновить проверку")
        self.btn_refresh.clicked.connect(self._load_data)
        self.btn_close = QPushButton("Закрыть")
        self.btn_close.clicked.connect(self.close)
        
        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        
        layout.addLayout(btn_layout)

    def _load_data(self):
        self.table.setRowCount(0)
        entries = self.journal.get_entries()
        
        for row, entry in enumerate(entries):
            self.table.insertRow(row)
            
            # 1. Время
            dt = datetime.datetime.fromtimestamp(entry.get("timestamp", 0))
            time_str = dt.strftime("%H:%M:%S %d.%m.%y")
            item_time = QTableWidgetItem(time_str)
            item_time.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, item_time)
            
            # 2. Файлы
            pairs = entry.get("pairs", [])
            is_group = len(pairs) > 1
            if is_group:
                file_text = f"Группа файлов ({len(pairs)} шт.)"
                tooltip = "Перемещена группа файлов:\n" + "\n".join(os.path.basename(p["src"]) for p in pairs[:5])
                if len(pairs) > 5: tooltip += "\n..."
            else:
                file_text = os.path.basename(pairs[0]["src"]) if pairs else "Неизвестно"
                tooltip = file_text
                
            item_files = QTableWidgetItem(file_text)
            item_files.setToolTip(tooltip)
            item_files.setData(Qt.ItemDataRole.UserRole, entry) # сохраняем entry
            
            # Проверка существования файлов по новому пути
            found_count = 0
            for p in pairs:
                if os.path.exists(p["dst"]):
                    found_count += 1
                    
            if found_count == 0:
                item_files.setForeground(QColor("red"))
            elif found_count < len(pairs):
                item_files.setForeground(QColor("orange"))
            else:
                item_files.setForeground(QColor("green"))
                
            self.table.setItem(row, 1, item_files)
            
            # 3. Откуда
            src_dir = os.path.dirname(pairs[0]["src"]) if pairs else ""
            item_src = QTableWidgetItem(src_dir)
            if not os.path.exists(src_dir):
                item_src.setForeground(QColor("red"))
                item_src.setToolTip("Папка отсутствует (будет создана при возврате)")
            else:
                item_src.setForeground(QColor("green"))
            self.table.setItem(row, 2, item_src)
            
            # 4. Куда
            dst_dir = os.path.dirname(pairs[0]["dst"]) if pairs else ""
            item_dst = QTableWidgetItem(dst_dir)
            if not os.path.exists(dst_dir):
                item_dst.setForeground(QColor("red"))
            else:
                item_dst.setForeground(QColor("green"))
            self.table.setItem(row, 3, item_dst)
            
            # 5. Действие
            status = entry.get("status", "valid")
            if status == "done":
                btn_action = QPushButton("Выполнено")
                btn_action.setEnabled(False)
            elif found_count == 0:
                btn_action = QPushButton("Файлы не найдены")
                btn_action.setEnabled(False)
            else:
                text = "Вернуть файлы" if found_count == len(pairs) else f"Вернуть {found_count}/{len(pairs)}"
                btn_action = QPushButton(text)
                btn_action.clicked.connect(lambda checked, e=entry: self._trigger_undo(e))
                
            self.table.setCellWidget(row, 4, btn_action)

    def _trigger_undo(self, entry):
        self.do_undo_entry.emit(entry)
        self.close()

    def _show_context_menu(self, pos: QPoint):
        item = self.table.itemAt(pos)
        if not item: return
        
        row = item.row()
        item_files = self.table.item(row, 1)
        entry = item_files.data(Qt.ItemDataRole.UserRole)
        if not entry: return
        
        menu = QMenu(self)
        action_copy = menu.addAction("Копировать пути (новое расположение)")
        
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == action_copy:
            pairs = entry.get("pairs", [])
            text = "\n".join(p["dst"] for p in pairs)
            QApplication.clipboard().setText(text)
