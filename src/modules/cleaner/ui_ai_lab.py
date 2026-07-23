import os
import re
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QLineEdit, QSplitter, QFrame, QProgressBar, QCheckBox,
    QFileDialog, QMessageBox, QComboBox, QTreeWidget, QTreeWidgetItem,
    QTextEdit, QListWidget, QAbstractItemView, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize, QThreadPool, QTimer
from PyQt6.QtGui import QFont, QColor, QSyntaxHighlighter, QTextCharFormat, QCursor
from config import AppContext
from .logic_ai_lab import AILabWorker
from utils_common import format_size, reveal_in_explorer
from .ui_preview import CleanerPreviewWidget

class MultiTagHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.rules = []

        # White for components inside parentheses after colon
        format_components = QTextCharFormat()
        format_components.setForeground(QColor("#ffffff"))

        # Orange for group name inside parentheses before colon
        format_group = QTextCharFormat()
        format_group.setForeground(QColor("#f59e0b"))
        format_group.setFontWeight(QFont.Weight.Bold)

        # Green for normal tags outside parentheses
        format_normal = QTextCharFormat()
        format_normal.setForeground(QColor("#10b981"))
        
        # Gray for punctuation
        format_punct = QTextCharFormat()
        format_punct.setForeground(QColor("#888888"))

        self.rules.append((re.compile(r'[\(\):,]'), format_punct))

    def highlightBlock(self, text):
        # 1. Base color (Normal tags are green)
        self.setFormat(0, len(text), QColor("#10b981"))
        
        # 2. Find parentheses blocks
        pattern = re.compile(r'\((.*?)\)')
        for match in pattern.finditer(text):
            start = match.start()
            length = match.end() - start
            inner_text = match.group(1)
            
            # Color everything inside parentheses as white by default
            self.setFormat(start + 1, length - 2, QColor("#ffffff"))
            
            # If there's a colon, color the left part as orange
            colon_idx = inner_text.find(':')
            if colon_idx != -1:
                self.setFormat(start + 1, colon_idx, QColor("#f59e0b"))
                
                # Make group name bold
                fmt = QTextCharFormat()
                fmt.setForeground(QColor("#f59e0b"))
                fmt.setFontWeight(QFont.Weight.Bold)
                self.setFormat(start + 1, colon_idx, fmt)

        # 3. Punctuation colors
        punct_pattern = re.compile(r'[\(\):,]')
        for match in punct_pattern.finditer(text):
            self.setFormat(match.start(), 1, QColor("#888888"))

class FolderDropListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setStyleSheet("""
            QListWidget {
                background-color: #1e1e1e;
                border: 1px solid #444;
                border-radius: 4px;
                color: #ccc;
            }
        """)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile() and os.path.isdir(url.toLocalFile()):
                    event.acceptProposedAction()
                    return
        event.ignore()
        
    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()
            
    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                if os.path.isdir(path):
                    # check if already exists
                    exists = False
                    for i in range(self.count()):
                        if self.item(i).text() == path:
                            exists = True
                            break
                    if not exists:
                        self.addItem(path)
        event.acceptProposedAction()

class AILabTab(QWidget):

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.is_ru = AppContext.LANG == "RU"
        self._init_ui()

    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)
        
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.setHandleWidth(2)
        self.main_splitter.setStyleSheet("QSplitter::handle { background-color: #2d2d2d; }")

        # --- TOP PANEL (Settings) ---
        self.top_panel = QWidget()
        self.top_panel.setStyleSheet("background-color: #2b2b2b; border-radius: 6px;")
        top_layout = QHBoxLayout(self.top_panel)
        top_layout.setContentsMargins(15, 15, 15, 15)
        top_layout.setSpacing(20)

        # Left Column: Folders
        folders_col = QVBoxLayout()
        folders_col.setSpacing(5)
        
        lbl_folders = QLabel("Папки для сканирования:" if self.is_ru else "Target Folders:")
        lbl_folders.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_folders.setStyleSheet("color: white;")
        folders_col.addWidget(lbl_folders)
        
        self.list_folders = FolderDropListWidget()
        self.list_folders.setToolTip("Перетащите папки сюда" if self.is_ru else "Drop folders here")
        folders_col.addWidget(self.list_folders)
        
        btn_add_folder = QPushButton("Добавить папку" if self.is_ru else "Add Folder")
        btn_add_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_folder.setStyleSheet("background-color: #444; color: white; border-radius: 4px; padding: 4px;")
        btn_add_folder.clicked.connect(self.select_folder)
        
        btn_clear_folders = QPushButton("Очистить список" if self.is_ru else "Clear List")
        btn_clear_folders.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear_folders.setStyleSheet("background-color: #ef4444; color: white; border-radius: 4px; padding: 4px;")
        btn_clear_folders.clicked.connect(self.list_folders.clear)
        
        fbtns_layout = QHBoxLayout()
        fbtns_layout.addWidget(btn_add_folder)
        fbtns_layout.addWidget(btn_clear_folders)
        folders_col.addLayout(fbtns_layout)
        top_layout.addLayout(folders_col, 1)

        # Right Column: Query & Settings
        settings_col = QVBoxLayout()
        settings_col.setSpacing(10)
        
        lbl_query = QLabel("Мультитеги и запрос (CLIP):" if self.is_ru else "Multi-tags and Query (CLIP):")
        lbl_query.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_query.setStyleSheet("color: white;")
        settings_col.addWidget(lbl_query)
        
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("Например: Собака, Кошка, (Рептилии: крокодил, ящерица, змея)" if self.is_ru else "e.g., Dog, Cat, (Reptiles: crocodile, lizard, snake)")
        self.input_text.setStyleSheet("background-color: #1e1e1e; color: white; border: 1px solid #444; border-radius: 4px; font-family: 'Consolas', 'Courier New'; font-size: 13px;")
        self.input_text.setAcceptRichText(False)
        self.input_text.setFixedHeight(60)
        self.highlighter = MultiTagHighlighter(self.input_text.document())
        settings_col.addWidget(self.input_text)
        
        # Threshold
        from PyQt6.QtWidgets import QSlider
        threshold_layout = QHBoxLayout()
        lbl_thresh = QLabel("Порог сходства:" if self.is_ru else "Similarity threshold:")
        lbl_thresh.setStyleSheet("color: white;")
        self.slider_thresh = QSlider(Qt.Orientation.Horizontal)
        self.slider_thresh.setRange(0, 100)
        self.slider_thresh.setValue(50)
        self.lbl_thresh_val = QLabel("50%")
        self.lbl_thresh_val.setStyleSheet("color: #3b82f6; font-weight: bold; width: 40px;")
        threshold_layout.addWidget(lbl_thresh)
        threshold_layout.addWidget(self.slider_thresh)
        threshold_layout.addWidget(self.lbl_thresh_val)
        settings_col.addLayout(threshold_layout)
        
        # Start button
        self.btn_search = QPushButton("Начать семантический поиск" if self.is_ru else "Start Semantic Search")
        self.btn_search.setFixedHeight(35)
        self.btn_search.setStyleSheet("background-color: #10b981; color: black; border-radius: 4px; font-weight: bold; font-size: 14px;")
        self.btn_search.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_col.addWidget(self.btn_search)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("QProgressBar { background: transparent; border: none; } QProgressBar::chunk { background: #3b82f6; }")
        self.progress_bar.hide()
        settings_col.addWidget(self.progress_bar)
        
        top_layout.addLayout(settings_col, 2)
        
        self.main_splitter.addWidget(self.top_panel)

        # --- BOTTOM PANEL (Results & Preview) ---
        self.bottom_panel = QWidget()
        bot_layout = QVBoxLayout(self.bottom_panel)
        bot_layout.setContentsMargins(0, 0, 0, 0)
        
        self.right_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.right_splitter.setHandleWidth(2)
        self.right_splitter.setStyleSheet("QSplitter::handle { background-color: #2d2d2d; }")
        
        self.tree_results = QTreeWidget()
        self.tree_results.setColumnCount(3)
        self.tree_results.setHeaderLabels([
            "Имя файла" if self.is_ru else "File Name",
            "Сходство (%)" if self.is_ru else "Similarity (%)",
            "Размер" if self.is_ru else "Size"
        ])
        self.tree_results.setColumnWidth(0, 300)
        self.tree_results.setColumnWidth(1, 100)
        self.tree_results.setStyleSheet("""
            QTreeWidget {
                background-color: #1a1a1a;
                color: #ccc;
                border: none;
            }
            QTreeWidget::item:selected {
                background-color: #3b82f6;
                color: white;
            }
        """)
        self.right_splitter.addWidget(self.tree_results)
        
        self.preview_widget = CleanerPreviewWidget()
        self.preview_widget.show_empty("Выберите файл для предпросмотра" if self.is_ru else "Select a file to preview")
        self.right_splitter.addWidget(self.preview_widget)
        
        self.right_splitter.setSizes([600, 400])
        bot_layout.addWidget(self.right_splitter)
        
        self.main_splitter.addWidget(self.bottom_panel)
        
        self.main_layout.addWidget(self.main_splitter)

        # Sizes
        self.main_splitter.setSizes([200, 600])

        # Connect signals
        self.btn_search.clicked.connect(self.on_btn_search_clicked)
        self.slider_thresh.valueChanged.connect(self.update_results_filter)
        self.tree_results.itemSelectionChanged.connect(self.on_tree_selection_changed)
        self.tree_results.itemDoubleClicked.connect(self.on_item_double_clicked)
        
        self.results = []
        self.worker = None
        self.feature_cache = {'face': {}, 'text': {}} 
        self.models_cache = {} 
        
        self.slider_timer = QTimer()
        self.slider_timer.setSingleShot(True)
        self.slider_timer.timeout.connect(self.apply_results_filter)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для сканирования")
        if folder:
            # check if exists
            exists = False
            for i in range(self.list_folders.count()):
                if self.list_folders.item(i).text() == folder:
                    exists = True
                    break
            if not exists:
                self.list_folders.addItem(folder)

    def on_tree_selection_changed(self):
        selected = self.tree_results.selectedItems()
        if not selected:
            return
        item = selected[0]
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        if file_path and os.path.exists(file_path):
            self.preview_widget.preview_file(file_path)

    def on_item_double_clicked(self, item):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path and os.path.exists(path):
            reveal_in_explorer(os.path.normpath(path))

    def on_btn_search_clicked(self):
        if self.worker and not self.worker.is_cancelled:
            self.stop_search()
        else:
            self.start_search()

    def start_search(self):
        text_query = self.input_text.toPlainText().strip()
        if not text_query:
            QMessageBox.warning(self, "Ошибка", "Введите поисковый запрос!")
            return

        if self.list_folders.count() == 0:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите хотя бы одну папку для поиска!")
            return
            
        folders = [self.list_folders.item(i).text() for i in range(self.list_folders.count())]
        # Для прототипа берем первую папку (worker_ai_lab пока принимает одну)
        # Если хотим несколько, нужно было бы переписать AILabWorker, но пока скармливаем первую
        selected_folder = folders[0]

        self.btn_search.setText("Стоп (Остановить поиск)" if self.is_ru else "Stop Search")
        self.btn_search.setStyleSheet("background-color: #ef4444; color: white; border-radius: 4px; font-weight: bold; font-size: 14px;")
        self.input_text.setEnabled(False)
        self.list_folders.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.show()

        self.tree_results.clear()
        self.results = []

        self.worker = AILabWorker(
            folder_path=selected_folder, 
            search_mode='text',
            action='scan_and_search',
            text_query=text_query,
            cache=self.feature_cache,
            models_cache=self.models_cache
        )
        self.worker.signals.progress.connect(self.update_progress)
        self.worker.signals.result_found.connect(self.on_result_found)
        self.worker.signals.finished.connect(self.on_search_finished)
        self.worker.signals.error.connect(self.on_search_error)

        QThreadPool.globalInstance().start(self.worker)

    def stop_search(self):
        if self.worker:
            self.worker.is_cancelled = True
        self.btn_search.setEnabled(False)
        self.btn_search.setText("Останавливаем..." if self.is_ru else "Stopping...")

    def reset_search_button(self):
        self.btn_search.setEnabled(True)
        self.btn_search.setText("Начать семантический поиск" if self.is_ru else "Start Semantic Search")
        self.btn_search.setStyleSheet("background-color: #10b981; color: black; border-radius: 4px; font-weight: bold; font-size: 14px;")
        self.input_text.setEnabled(True)
        self.list_folders.setEnabled(True)

    def update_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def update_results_filter(self):
        self.lbl_thresh_val.setText(f"{self.slider_thresh.value()}%")
        self.slider_timer.start(500)

    def apply_results_filter(self):
        if not self.worker or not self.worker.isRunning():
            self.render_results()

    def render_results(self):
        self.tree_results.clear()
        threshold = self.slider_thresh.value()
        
        # Group by matched_group_name
        groups = {}
        for file_path, score, group_name in self.results:
            if score >= threshold:
                if group_name not in groups:
                    groups[group_name] = []
                groups[group_name].append((file_path, score))
                
        # Build tree
        for group_name, items in groups.items():
            # Sort items by score descending
            items.sort(key=lambda x: x[1], reverse=True)
            
            group_item = QTreeWidgetItem(self.tree_results)
            group_item.setText(0, f"Группа: {group_name} ({len(items)} файлов)")
            group_item.setForeground(0, QColor("#10b981"))
            group_item.setFont(0, QFont("Segoe UI", 10, QFont.Weight.Bold))
            
            for file_path, score in items:
                file_item = QTreeWidgetItem(group_item)
                file_item.setText(0, os.path.basename(file_path))
                file_item.setText(1, f"{int(score)}%")
                try:
                    size = os.path.getsize(file_path)
                    file_item.setText(2, format_size(size))
                except:
                    file_item.setText(2, "")
                    
                file_item.setData(0, Qt.ItemDataRole.UserRole, file_path)
                
        self.tree_results.expandAll()

    def on_result_found(self, file_path, score, group_name):
        self.results.append((file_path, score, group_name))

    def on_search_finished(self):
        self.worker = None
        self.progress_bar.hide()
        self.reset_search_button()
        self.render_results()

    def on_search_error(self, err_msg):
        self.worker = None
        self.progress_bar.hide()
        self.reset_search_button()
        QMessageBox.critical(self, "Ошибка", err_msg)
