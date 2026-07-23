import os
import re
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QSplitter, QFrame, QProgressBar, QCheckBox,
    QFileDialog, QMessageBox, QTreeWidget, QTreeWidgetItem,
    QTextEdit, QListWidget, QAbstractItemView, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QFont, QColor, QSyntaxHighlighter, QTextCharFormat
from config import AppContext
from utils_common import format_size, reveal_in_explorer
from .ui_preview import CleanerPreviewWidget
from .ai_facade import AiServiceFacade, AiSearchRequest, AiTaskType, AiTarget

def parse_multi_tags(text: str) -> dict:
    result = {}
    pattern_multi = r'\(([^:]+):([^\)]+)\)'
    for match in re.finditer(pattern_multi, text):
        group_name = match.group(1).strip()
        components = [c.strip() for c in match.group(2).split(',') if c.strip()]
        if components:
            result[group_name] = components
            
    text_clean = re.sub(pattern_multi, '', text)
    regular_tags = [t.strip() for t in text_clean.split(',') if t.strip()]
    for tag in regular_tags:
        result[tag] = [tag]
        
    return result

class MultiTagHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.rules = []

        format_components = QTextCharFormat()
        format_components.setForeground(QColor("#ffffff"))

        format_group = QTextCharFormat()
        format_group.setForeground(QColor("#f59e0b"))
        format_group.setFontWeight(QFont.Weight.Bold)

        format_normal = QTextCharFormat()
        format_normal.setForeground(QColor("#10b981"))
        
        format_punct = QTextCharFormat()
        format_punct.setForeground(QColor("#888888"))

        self.rules.append((re.compile(r'[\(\):,]'), format_punct))

    def highlightBlock(self, text):
        self.setFormat(0, len(text), QColor("#10b981"))
        pattern = re.compile(r'\((.*?)\)')
        for match in pattern.finditer(text):
            start = match.start()
            length = match.end() - start
            inner_text = match.group(1)
            
            self.setFormat(start + 1, length - 2, QColor("#ffffff"))
            
            colon_idx = inner_text.find(':')
            if colon_idx != -1:
                self.setFormat(start + 1, colon_idx, QColor("#f59e0b"))
                fmt = QTextCharFormat()
                fmt.setForeground(QColor("#f59e0b"))
                fmt.setFontWeight(QFont.Weight.Bold)
                self.setFormat(start + 1, colon_idx, fmt)

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
        
        # Progress label
        self.lbl_progress = QLabel()
        self.lbl_progress.setStyleSheet("color: #aaa; font-size: 11px;")
        settings_col.addWidget(self.lbl_progress)
        
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
        self.main_splitter.setSizes([200, 600])

        self.btn_search.clicked.connect(self.on_btn_search_clicked)
        self.slider_thresh.valueChanged.connect(self.update_results_filter)
        self.tree_results.itemSelectionChanged.connect(self.on_tree_selection_changed)
        self.tree_results.itemDoubleClicked.connect(self.on_item_double_clicked)
        
        self.facade = AiServiceFacade()
        self.current_response = None
        self.is_searching = False

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для сканирования")
        if folder:
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
            self.preview_widget.load_file(file_path)

    def on_item_double_clicked(self, item):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path and os.path.exists(path):
            reveal_in_explorer(os.path.normpath(path))

    def on_btn_search_clicked(self):
        if self.is_searching:
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
        queries_dict = parse_multi_tags(text_query)

        self.btn_search.setText("Стоп (Остановить поиск)" if self.is_ru else "Stop Search")
        self.btn_search.setStyleSheet("background-color: #ef4444; color: white; border-radius: 4px; font-weight: bold; font-size: 14px;")
        self.input_text.setEnabled(False)
        self.list_folders.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.lbl_progress.setText("")

        self.tree_results.clear()
        self.current_response = None
        self.is_searching = True

        request = AiSearchRequest(
            target_paths=folders,
            task_type=AiTaskType.TEXT_TO_IMAGE,
            analysis_target=AiTarget.IMAGES,
            threshold=self.slider_thresh.value(),
            text_queries=queries_dict
        )

        self.facade.search(
            request,
            progress_callback=self.update_progress,
            result_callback=self.on_result_found,
            error_callback=self.on_search_error
        )

    def stop_search(self):
        self.facade.cancel_search()
        self.is_searching = False
        self.reset_search_button()

    def reset_search_button(self):
        self.btn_search.setEnabled(True)
        self.btn_search.setText("Начать семантический поиск" if self.is_ru else "Start Semantic Search")
        self.btn_search.setStyleSheet("background-color: #10b981; color: black; border-radius: 4px; font-weight: bold; font-size: 14px;")
        self.input_text.setEnabled(True)
        self.list_folders.setEnabled(True)

    def update_progress(self, stage, percent, text, scanned_files, groups_found, wasted_bytes, scanned_bytes, files_found, dummy):
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(int(percent))
        self.lbl_progress.setText(text)

    def update_results_filter(self):
        self.lbl_thresh_val.setText(f"{self.slider_thresh.value()}%")
        self.render_results()

    def on_result_found(self, response):
        self.current_response = response
        self.is_searching = False
        self.progress_bar.hide()
        self.lbl_progress.setText("Готово" if self.is_ru else "Done")
        self.reset_search_button()
        self.render_results()

    def render_results(self):
        self.tree_results.clear()
        if not self.current_response:
            return
            
        threshold = self.slider_thresh.value()
        
        for group in self.current_response.groups:
            # Filter by threshold
            valid_files = [f for f in group.files if f.score >= threshold]
            if not valid_files:
                continue
                
            group_item = QTreeWidgetItem(self.tree_results)
            group_item.setText(0, f"Группа: {group.group_name} ({len(valid_files)} файлов)")
            group_item.setForeground(0, QColor("#10b981"))
            group_item.setFont(0, QFont("Segoe UI", 10, QFont.Weight.Bold))
            
            for file_match in valid_files:
                file_item = QTreeWidgetItem(group_item)
                file_item.setText(0, os.path.basename(file_match.path))
                file_item.setText(1, f"{int(file_match.score)}%")
                try:
                    size = os.path.getsize(file_match.path)
                    file_item.setText(2, format_size(size))
                except:
                    file_item.setText(2, "")
                    
                file_item.setData(0, Qt.ItemDataRole.UserRole, file_match.path)
                
        self.tree_results.expandAll()

    def on_search_error(self, err_msg):
        self.is_searching = False
        self.progress_bar.hide()
        self.reset_search_button()
        QMessageBox.critical(self, "Ошибка", err_msg)

    def update_folders_label(self, folders):
        pass
