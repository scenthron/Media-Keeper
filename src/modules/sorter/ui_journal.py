import os
import sys
import subprocess
import datetime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QTableWidget, QTableWidgetItem, QHeaderView, QMenu, QAbstractItemView, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QPoint, QEvent
from PyQt6.QtGui import QIcon, QPixmap, QColor, QClipboard

from config import AppContext
from utils_common import format_size
from logic_paths import get_app_data_dir
from .logic_journal import MoveJournal

class JournalDialog(QDialog):
    do_undo_entry = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Журнал перемещений")
        # Окно будет поверх родительского окна (Media Keeper), но не поверх других программ
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
        self.resize(850, 500)
        self.journal = MoveJournal.inst()
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Дата/Время", "Файлы", "Откуда", "Куда", "", "Действие"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents) # Кнопка удаления
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents) # Кнопка возврата
        
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.cellDoubleClicked.connect(self._handle_double_click)
        self.table.viewport().installEventFilter(self)
        
        layout.addWidget(self.table)
        
        hint_lbl = QLabel(
            "Подсказка: <b>Двойной клик</b> по зеленому файлу — открыть файл. "
            "<b>Средняя кнопка (колесико)</b> по строке — открыть папку. "
            "<b>ПКМ</b> — меню копирования."
        )
        hint_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(hint_lbl)
        
        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("Обновить проверку")
        self.btn_refresh.clicked.connect(self._load_data)
        self.btn_clear = QPushButton("Очистить журнал")
        self.btn_clear.clicked.connect(self._clear_journal)
        self.btn_close = QPushButton("Закрыть")
        self.btn_close.clicked.connect(self.close)
        
        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_clear)
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
            item_files.setData(Qt.ItemDataRole.UserRole, entry)
            
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
            item_src = QTableWidgetItem(self._abbrev_path(src_dir))
            item_src.setToolTip(src_dir)
            if not os.path.exists(src_dir):
                item_src.setForeground(QColor("red"))
                item_src.setToolTip(f"Папка отсутствует (будет создана при возврате)\n{src_dir}")
            else:
                item_src.setForeground(QColor("green"))
            self.table.setItem(row, 2, item_src)
            
            # 4. Куда
            dst_dir = os.path.dirname(pairs[0]["dst"]) if pairs else ""
            item_dst = QTableWidgetItem(self._abbrev_path(dst_dir))
            item_dst.setToolTip(dst_dir)
            if not os.path.exists(dst_dir):
                item_dst.setForeground(QColor("red"))
            else:
                item_dst.setForeground(QColor("green"))
            self.table.setItem(row, 3, item_dst)
            
            # 5. Кнопка удаления записи (Крестик)
            btn_del = QPushButton("✖")
            btn_del.setToolTip("Удалить запись из журнала (файлы останутся на местах)")
            btn_del.setStyleSheet("QPushButton { color: #f44336; border: 1px solid #444; border-radius: 3px; max-width: 25px; min-width: 25px; padding: 2px; } QPushButton:hover { background-color: #f44336; color: white; }")
            btn_del.clicked.connect(lambda checked, e_id=entry.get("id"): self._remove_entry(e_id))
            self.table.setCellWidget(row, 4, btn_del)
            
            # 6. Действие
            status = entry.get("status", "valid")
            if status == "done":
                lbl = QLabel("Выполнено")
                lbl.setStyleSheet("color: #4CAF50; font-weight: bold;")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setCellWidget(row, 5, lbl)
            elif found_count == 0:
                lbl = QLabel("Файлы не найдены")
                lbl.setStyleSheet("color: #F44336;")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setCellWidget(row, 5, lbl)
            else:
                text = "Вернуть файлы" if found_count == len(pairs) else f"Вернуть {found_count}/{len(pairs)}"
                btn_action = QPushButton(text)
                btn_action.clicked.connect(lambda checked, e=entry: self._trigger_undo(e))
                self.table.setCellWidget(row, 5, btn_action)

    def _trigger_undo(self, entry):
        self.do_undo_entry.emit(entry)
        self.close()

    def _clear_journal(self):
        self.journal.clear()
        self._load_data()
        
    def _remove_entry(self, entry_id):
        self.journal.remove_entry(entry_id)
        self._load_data()

    def _abbrev_path(self, path):
        if not path: return ""
        from utils_io import strip_long_path_prefix
        path = strip_long_path_prefix(path)
        parts = path.replace("\\", "/").split("/")
        if len(parts) > 2:
            return f"{parts[0]}/.../{parts[-1]}"
        return path

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

    def eventFilter(self, source, event):
        if source is self.table.viewport() and event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.MiddleButton:
                pos = event.pos()
                item = self.table.itemAt(pos)
                if item:
                    self._handle_middle_click(item)
        return super().eventFilter(source, event)
        
    def _handle_double_click(self, row, col):
        item_files = self.table.item(row, 1)
        entry = item_files.data(Qt.ItemDataRole.UserRole)
        if not entry: return
        
        pairs = entry.get("pairs", [])
        if len(pairs) != 1: return # Игнорируем двойной клик по группе
        
        path = pairs[0]["dst"]
        if os.path.exists(path):
            try:
                os.startfile(path)
            except Exception as e:
                pass
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Файл не найден", "Этот файл физически отсутствует на диске или был удален/перемещен.")
        
    def _handle_middle_click(self, item):
        row = item.row()
        col = item.column()
        item_files = self.table.item(row, 1)
        entry = item_files.data(Qt.ItemDataRole.UserRole)
        if not entry: return
        
        pairs = entry.get("pairs", [])
        if not pairs: return
        
        # Если кликнули по колонке "Откуда" (2), открываем src папку
        if col == 2:
            src_dir = os.path.dirname(pairs[0]["src"])
            if os.path.exists(src_dir):
                self._open_in_explorer(src_dir)
            return
                
        # Если кликнули по колонке "Куда" (3), открываем dst папку
        if col == 3:
            dst_dir = os.path.dirname(pairs[0]["dst"])
            if os.path.exists(dst_dir):
                self._open_in_explorer(dst_dir)
            return
            
        # Иначе (например, клик по файлу)
        if len(pairs) == 1:
            path = pairs[0]["dst"]
            if os.path.exists(path):
                self._open_and_select_in_explorer(path)
            else:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(self, "Файл не найден", "Этот файл физически отсутствует на диске.")
        else:
            dst_dir = os.path.dirname(pairs[0]["dst"])
            if os.path.exists(dst_dir):
                self._open_in_explorer(dst_dir)
                
    def _open_in_explorer(self, path):
        try:
            os.startfile(path)
        except Exception:
            pass

    def _open_and_select_in_explorer(self, path):
        from utils_common import reveal_in_explorer
        reveal_in_explorer(path)
