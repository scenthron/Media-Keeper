import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QLineEdit, QSplitter, QFrame, QScrollArea, QProgressBar, QCheckBox,
    QFileDialog, QMessageBox, QComboBox
)
from PyQt6.QtCore import Qt, QSize, QThreadPool
from PyQt6.QtGui import QFont, QColor
from config import AppContext
from .logic_ai_lab import AILabWorker

class ImageDropZone(QFrame):
    def __init__(self, placeholder_text):
        super().__init__()
        self.setAcceptDrops(True)
        self.setStyleSheet("QFrame { background-color: rgba(255, 255, 255, 0.05); border: 2px dashed #555; border-radius: 6px; } QFrame:hover { border-color: #3b82f6; }")
        self.layout = QVBoxLayout(self)
        self.lbl_info = QLabel(placeholder_text)
        self.lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_info.setStyleSheet("color: #aaa; border: none;")
        self.layout.addWidget(self.lbl_info)
        self.current_paths = []

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet("QFrame { background-color: rgba(59, 130, 246, 0.15); border: 2px dashed #3b82f6; border-radius: 6px; }")
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet("QFrame { background-color: rgba(255, 255, 255, 0.05); border: 2px dashed #555; border-radius: 6px; }")
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        valid_exts = {'.jpg', '.jpeg', '.png', '.bmp'}
        
        new_paths = []
        for url in urls:
            path = url.toLocalFile()
            if os.path.splitext(path)[1].lower() in valid_exts:
                new_paths.append(path)
                
        if new_paths:
            # We can overwrite or append. Let's overwrite for simplicity of starting fresh
            self.current_paths = new_paths
            if len(self.current_paths) == 1:
                self.lbl_info.setText(f"Выбрано: {os.path.basename(self.current_paths[0])}")
            else:
                self.lbl_info.setText(f"Загружено эталонов: {len(self.current_paths)}")
            event.acceptProposedAction()
            
        self.setStyleSheet("QFrame { background-color: rgba(255, 255, 255, 0.05); border: 2px dashed #555; border-radius: 6px; }")

    def get_dropped_file(self):
        # Return list of paths instead of a single string
        return self.current_paths

class AILabResultTile(QFrame):
    def __init__(self, file_path, score):
        super().__init__()
        self.file_path = file_path
        from PyQt6.QtWidgets import QVBoxLayout, QLabel
        from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont
        from PyQt6.QtCore import Qt, QRect
        import os
        self.setStyleSheet("QFrame { background-color: #2a2a2a; border-radius: 6px; }")
        self.setFixedSize(140, 180)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        
        # Image preview
        self.lbl_img = QLabel()
        pixmap = QPixmap(file_path).scaled(132, 132, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        
        # Draw score on top of pixmap
        painter = QPainter(pixmap)
        painter.setBrush(QColor(0, 0, 0, 150))
        painter.setPen(Qt.PenStyle.NoPen)
        badge_w, badge_h = 40, 20
        badge_rect = QRect(132 - badge_w - 4, 132 - badge_h - 4, badge_w, badge_h)
        painter.drawRoundedRect(badge_rect, 4, 4)
        
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, f"{int(score)}%")
        painter.end()
        
        self.lbl_img.setPixmap(pixmap)
        self.lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_img)
        
        # Name label
        self.lbl_name = QLabel(os.path.basename(file_path))
        self.lbl_name.setStyleSheet("color: #ccc; font-size: 11px; background: transparent;")
        self.lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fontMetrics = self.lbl_name.fontMetrics()
        elidedText = fontMetrics.elidedText(self.lbl_name.text(), Qt.TextElideMode.ElideRight, 132)
        self.lbl_name.setText(elidedText)
        layout.addWidget(self.lbl_name)

    def mousePressEvent(self, event):
        from PyQt6.QtCore import Qt
        import os
        from utils_common import reveal_in_explorer
        if event.button() == Qt.MouseButton.MiddleButton:
            path = os.path.normpath(self.file_path)
            reveal_in_explorer(path)
        super().mousePressEvent(event)


class FolderDropButton(QPushButton):
    def __init__(self, text, drop_callback, parent=None):
        super().__init__(text, parent)
        self.drop_callback = drop_callback
        self.setAcceptDrops(True)
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile() and os.path.isdir(url.toLocalFile()):
                    event.acceptProposedAction()
                    return
        event.ignore()
        
    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                if os.path.isdir(path):
                    self.drop_callback(path)
                    return

class AILabTab(QWidget):

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.is_ru = AppContext.LANG == "RU"
        self._init_ui()

    def _init_ui(self):
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Left panel (Settings / Input)
        self.left_panel = QWidget()
        self.left_panel.setFixedWidth(400)
        self.left_panel.setStyleSheet("background-color: #2b2b2b;")
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(15)

        # Title
        lbl_title = QLabel("AI Lab (Прототип)" if self.is_ru else "AI Lab (Prototype)")
        lbl_title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        lbl_title.setStyleSheet("color: white;")
        left_layout.addWidget(lbl_title)

        lbl_desc = QLabel(
            "Экспериментальный семантический поиск (CLIP) и поиск лиц (InsightFace)." if self.is_ru else 
            "Experimental semantic search (CLIP) and face search (InsightFace)."
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("color: #aaa; margin-bottom: 10px;")
        left_layout.addWidget(lbl_desc)

        # Download models button (Hidden for prototype since we use local YuNet/SFace)
        # self.btn_download = ...

        # Mode Selection
        lbl_mode = QLabel("Режим поиска:" if self.is_ru else "Search Mode:")
        lbl_mode.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_mode.setStyleSheet("color: white; margin-top: 10px;")
        left_layout.addWidget(lbl_mode)

        self.combo_mode = QComboBox()
        self.combo_mode.addItem("Поиск по лицу (InsightFace)" if self.is_ru else "Face Search (InsightFace)", "face")
        self.combo_mode.addItem("Семантический поиск (CLIP Text-to-Image)" if self.is_ru else "Semantic Search (CLIP)", "text")
        self.combo_mode.setFixedHeight(35)
        self.combo_mode.setStyleSheet("background-color: #1e1e1e; color: white; border: 1px solid #444; border-radius: 4px; padding: 0 10px;")
        left_layout.addWidget(self.combo_mode)

        # ----------------- SEMANTIC UI -----------------
        self.semantic_widget = QWidget()
        sem_layout = QVBoxLayout(self.semantic_widget)
        sem_layout.setContentsMargins(0, 0, 0, 0)
        
        lbl_text = QLabel("Текстовый запрос:" if self.is_ru else "Text Query:")
        lbl_text.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_text.setStyleSheet("color: white; margin-top: 10px;")
        sem_layout.addWidget(lbl_text)

        self.input_text = QLineEdit()
        self.input_text.setPlaceholderText("Например: кот на диване" if self.is_ru else "e.g., cat on sofa")
        self.input_text.setFixedHeight(35)
        self.input_text.setStyleSheet("background-color: #1e1e1e; color: white; border: 1px solid #444; border-radius: 4px; padding: 0 10px;")
        
        self.btn_search_text = QPushButton("Найти" if self.is_ru else "Search")
        self.btn_search_text.setFixedHeight(35)
        self.btn_search_text.setStyleSheet("background-color: #3b82f6; color: white; border-radius: 4px; font-weight: bold;")
        self.btn_search_text.setCursor(Qt.CursorShape.PointingHandCursor)
        
        text_input_layout = QHBoxLayout()
        text_input_layout.setContentsMargins(0, 0, 0, 0)
        text_input_layout.addWidget(self.input_text)
        text_input_layout.addWidget(self.btn_search_text)
        
        sem_layout.addLayout(text_input_layout)
        left_layout.addWidget(self.semantic_widget)

        # ----------------- FACE UI -----------------
        self.face_widget = QWidget()
        face_layout = QVBoxLayout(self.face_widget)
        face_layout.setContentsMargins(0, 0, 0, 0)
        
        lbl_face = QLabel("Поиск по эталону:" if self.is_ru else "Reference Search:")
        lbl_face.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_face.setStyleSheet("color: white; margin-top: 10px;")
        face_layout.addWidget(lbl_face)

        self.face_drop_zone = ImageDropZone("Перетащите фото (Эталон)" if self.is_ru else "Drop reference photo here")
        self.face_drop_zone.setFixedHeight(120)
        face_layout.addWidget(self.face_drop_zone)

        lbl_neg = QLabel("Исключить это лицо (Негатив):" if self.is_ru else "Exclude this face (Negative):")
        lbl_neg.setStyleSheet("color: #aaa; margin-top: 5px;")
        face_layout.addWidget(lbl_neg)
        
        self.neg_face_drop_zone = ImageDropZone("Перетащите фото (Исключение)" if self.is_ru else "Drop negative photo here")
        self.neg_face_drop_zone.setFixedHeight(120)
        face_layout.addWidget(self.neg_face_drop_zone)
        
        self.btn_search_face = QPushButton("Найти (По Лицу)" if self.is_ru else "Search (Face)")
        self.btn_search_face.setFixedHeight(35)
        self.btn_search_face.setStyleSheet("background-color: #3b82f6; color: white; border-radius: 4px; font-weight: bold; margin-top: 10px;")
        self.btn_search_face.setCursor(Qt.CursorShape.PointingHandCursor)
        face_layout.addWidget(self.btn_search_face)
        
        left_layout.addWidget(self.face_widget)

        # ----------------- CACHE UI -----------------
        cache_layout = QHBoxLayout()
        self.chk_cache = QCheckBox("Использовать кэш" if self.is_ru else "Use Cache")
        self.chk_cache.setChecked(True)
        self.chk_cache.setStyleSheet("color: white;")
        cache_layout.addWidget(self.chk_cache)
        
        self.lbl_cache_info = QLabel("Размер: 0 (0)" if self.is_ru else "Size: 0 (0)")
        self.lbl_cache_info.setStyleSheet("color: #aaa; font-size: 11px;")
        cache_layout.addWidget(self.lbl_cache_info)
        
        cache_layout.addStretch()
        self.btn_clear_cache = QPushButton("Очистить кэш" if self.is_ru else "Clear Cache")
        self.btn_clear_cache.setStyleSheet("background-color: #444; color: white; border-radius: 4px; padding: 4px 8px;")
        self.btn_clear_cache.setCursor(Qt.CursorShape.PointingHandCursor)
        cache_layout.addWidget(self.btn_clear_cache)
        left_layout.addLayout(cache_layout)

        left_layout.addStretch()

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("QProgressBar { background: #1e1e1e; border: none; } QProgressBar::chunk { background: #3b82f6; }")
        self.progress_bar.hide()
        left_layout.addWidget(self.progress_bar)

        self.btn_select_folder = FolderDropButton("Выбрать папку" if self.is_ru else "Select Folder", self.set_selected_folder)
        self.btn_select_folder.setFixedHeight(35)
        self.btn_select_folder.setStyleSheet("background-color: #3b82f6; color: white; border-radius: 4px; font-weight: bold;")
        self.btn_select_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        left_layout.addWidget(self.btn_select_folder)

        self.lbl_selected_folder = QLabel("")
        self.lbl_selected_folder.setStyleSheet("color: #aaa; font-size: 11px;")
        self.lbl_selected_folder.setWordWrap(True)
        left_layout.addWidget(self.lbl_selected_folder)

        self.btn_search = QPushButton("Сканировать директорию" if self.is_ru else "Scan Directory")
        self.btn_search.setFixedHeight(45)
        self.btn_search.setStyleSheet("background-color: #10b981; color: black; border-radius: 4px; font-weight: bold; font-size: 14px;")
        self.btn_search.setCursor(Qt.CursorShape.PointingHandCursor)
        left_layout.addWidget(self.btn_search)

        self.main_layout.addWidget(self.left_panel)

        # Right panel (Results Grid)
        self.right_panel = QWidget()
        self.right_panel.setStyleSheet("background-color: #1e1e1e;")
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Threshold controls
        from PyQt6.QtWidgets import QSlider
        threshold_layout = QHBoxLayout()
        lbl_thresh = QLabel("Порог сходства:" if self.is_ru else "Similarity threshold:")
        lbl_thresh.setStyleSheet("color: white; font-weight: bold;")
        self.slider_thresh = QSlider(Qt.Orientation.Horizontal)
        self.slider_thresh.setRange(0, 100)
        self.slider_thresh.setValue(20) # Default 20%
        self.slider_thresh.setFixedWidth(200)
        self.lbl_thresh_val = QLabel("20%")
        self.lbl_thresh_val.setStyleSheet("color: #3b82f6; font-weight: bold; width: 40px;")
        
        threshold_layout.addWidget(lbl_thresh)
        threshold_layout.addWidget(self.slider_thresh)
        threshold_layout.addWidget(self.lbl_thresh_val)
        threshold_layout.addStretch()
        
        right_layout.addLayout(threshold_layout)

        # Use QListWidget in IconMode for a simple responsive grid
        from PyQt6.QtWidgets import QListWidget, QListWidgetItem
        from PyQt6.QtGui import QIcon
        from PyQt6.QtCore import QSize
        
        self.results_list = QListWidget()
        self.results_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.results_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.results_list.setSpacing(10)
        self.results_list.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.results_list.setStyleSheet("QListWidget { background-color: #1e1e1e; border: none; } QListWidget::item { background-color: transparent; }")
        
        right_layout.addWidget(self.results_list)

        self.main_layout.addWidget(self.right_panel, 1)

        # Connect signals
        self.btn_select_folder.clicked.connect(self.select_folder)
        self.btn_search.clicked.connect(lambda: self.on_btn_search_clicked(action='scan'))
        self.slider_thresh.valueChanged.connect(self.update_results_filter)
        self.combo_mode.currentIndexChanged.connect(self.on_mode_changed)
        self.btn_search_text.clicked.connect(lambda: self.on_btn_search_clicked(action='search'))
        self.btn_search_face.clicked.connect(lambda: self.on_btn_search_clicked(action='search'))
        self.input_text.returnPressed.connect(self.btn_search_text.click)
        
        self.selected_folder = ""
        self.results = []
        self.worker = None
        self.feature_cache = {'face': {}, 'text': {}} # Cache instance tied to this tab
        self.models_cache = {} # Cache for loaded ONNX models (to prevent reloading)
        self.scanned_folders = {'face': set(), 'text': set()}
        
        # Init UI state
        self.on_mode_changed()

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для сканирования")
        if folder:
            self.set_selected_folder(folder)

    def set_selected_folder(self, folder):
        self.selected_folder = folder
        self.lbl_selected_folder.setText(folder)

    def on_item_double_clicked(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and os.path.exists(path):
            os.startfile(path)

    def on_btn_search_clicked(self, action='scan'):
        if self.worker and not self.worker.is_cancelled:
            self.stop_search()
        else:
            self.start_search(action)

    def on_mode_changed(self):
        mode = self.combo_mode.currentData()
        if mode == 'face':
            self.semantic_widget.hide()
            self.face_widget.show()
        else:
            self.face_widget.hide()
            self.semantic_widget.show()
            
    def on_clear_cache(self):
        self.feature_cache = {'face': {}, 'text': {}}
        self.scanned_folders = {'face': set(), 'text': set()}
        self.update_cache_label()
        
    def update_cache_label(self):
        face_len = len(self.feature_cache['face'])
        text_len = len(self.feature_cache['text'])
        mode = self.combo_mode.currentData()
        if mode == 'face':
            self.lbl_cache_info.setText(f"В кэше лиц: {face_len}" if self.is_ru else f"Face Cache: {face_len}")
        else:
            self.lbl_cache_info.setText(f"В кэше CLIP: {text_len}" if self.is_ru else f"CLIP Cache: {text_len}")

    def start_search(self):
        mode = self.combo_mode.currentData()
        
        ref_paths = None
        neg_paths = None
        text_query = None
        
        if mode == 'face':
            ref_paths = self.face_drop_zone.get_dropped_file()
            if not ref_paths:
                QMessageBox.warning(self, "Ошибка", "Сначала перетащите эталонное фото!")
                return
            neg_paths_list = self.neg_face_drop_zone.get_dropped_file()
            neg_paths = neg_paths_list[0] if neg_paths_list else None
        else:
            text_query = self.input_text.text().strip()
            if not text_query:
                QMessageBox.warning(self, "Ошибка", "Введите поисковый запрос!")
                return

        if not self.selected_folder:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите папку для поиска!")
            return

        is_scanned = self.selected_folder in self.scanned_folders[mode]
        if action == 'search' and is_scanned:
            worker_action = 'search_only'
        elif action == 'search' and not is_scanned:
            worker_action = 'scan_and_search'
        else:
            worker_action = 'scan_only'

        if worker_action in ['scan_only', 'scan_and_search']:
            self.btn_search.setText("Стоп (Остановить поиск)" if self.is_ru else "Stop Search")
            self.btn_search.setStyleSheet("background-color: #ef4444; color: white; border-radius: 4px; font-weight: bold; font-size: 14px;")
            self.btn_select_folder.setEnabled(False)
            self.combo_mode.setEnabled(False)
            self.btn_clear_cache.setEnabled(False)
            self.btn_search_text.setEnabled(False)
            self.btn_search_face.setEnabled(False)
            self.progress_bar.setValue(0)
            self.progress_bar.show()

        self.results_list.clear()
        self.results = []
        
        self.current_worker_action = worker_action

        cache_obj = self.feature_cache if self.chk_cache.isChecked() else {'face': {}, 'text': {}}

        self.worker = AILabWorker(
            folder_path=self.selected_folder, 
            search_mode=mode,
            action=worker_action,
            ref_image_path=ref_paths,
            neg_image_path=neg_paths,
            text_query=text_query,
            cache=cache_obj,
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
        self.btn_search.setText("Сканировать директорию" if self.is_ru else "Scan Directory")
        self.btn_search.setStyleSheet("background-color: #10b981; color: black; border-radius: 4px; font-weight: bold; font-size: 14px;")
        self.btn_select_folder.setEnabled(True)
        self.btn_search_text.setEnabled(True)
        self.btn_search_face.setEnabled(True)

    def update_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def update_results_filter(self):
        self.lbl_thresh_val.setText(f"{self.slider_thresh.value()}%")
        if not self.worker or not self.worker.isRunning():
            self.render_results()

    def render_results(self):
        self.results_list.clear()
        threshold = self.slider_thresh.value()
        
        sorted_res = sorted(self.results, key=lambda x: x[1], reverse=True)
        from PyQt6.QtWidgets import QListWidgetItem
        
        for file_path, score in sorted_res:
            if score >= threshold:
                item = QListWidgetItem()
                item.setSizeHint(QSize(140, 180))
                tile = AILabResultTile(file_path, score)
                item.setData(Qt.ItemDataRole.UserRole, file_path)
                self.results_list.addItem(item)
                self.results_list.setItemWidget(item, tile)

        if self.results_list.count() == 0 and not (self.worker and self.worker.isRunning()):
            item = QListWidgetItem("Нет совпадений подходящих под порог" if self.is_ru else "No matches above threshold")
            self.results_list.addItem(item)

    def on_result_found(self, file_path, score):
        self.results.append((file_path, score))
        if score >= self.slider_thresh.value():
            from PyQt6.QtWidgets import QListWidgetItem
            item = QListWidgetItem()
            item.setSizeHint(QSize(140, 180))
            tile = AILabResultTile(file_path, score)
            self.results_list.addItem(item)
            self.results_list.setItemWidget(item, tile)

    def on_search_finished(self):
        if self.current_worker_action in ['scan_only', 'scan_and_search']:
            mode = self.combo_mode.currentData()
            self.scanned_folders[mode].add(self.selected_folder)
            
        self.worker = None
        self.progress_bar.hide()
        self.update_cache_label()
        self.reset_search_button()
        self.combo_mode.setEnabled(True)
        self.btn_clear_cache.setEnabled(True)
        
        if self.current_worker_action != 'scan_only':
            self.render_results()

    def on_search_error(self, err_msg):
        self.worker = None
        self.progress_bar.hide()
        self.update_cache_label()
        self.reset_search_button()
        self.combo_mode.setEnabled(True)
        self.btn_clear_cache.setEnabled(True)
        QMessageBox.critical(self, "Ошибка", err_msg)

    def update_folders_label(self, folders):
        pass
