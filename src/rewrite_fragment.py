import os

code = """
import os
import shutil
import time
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QMessageBox, QSlider, QTreeWidget, QTreeWidgetItem, QProgressBar,
    QSplitter, QSizePolicy, QCheckBox, QScrollArea, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QThread, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QColor, QCursor, QAction

from config import AppContext
from ui_widgets_base import DropZoneWidget
from logic_paths import get_app_data_dir

from .logic_orb import OrbEngine, OrbCacheManager
from .ui_crop_dialog import CropDialog
from .ui_panels import CleanerActionBar
from .ui_preview import CleanerPreviewWidget
from utils_common import format_size
from .ui_widgets import SourceListItem

class FragmentScannerThread(QThread):
    progress_update = pyqtSignal(int, int, str)
    finished_signal = pyqtSignal(bool, object)
    
    def __init__(self, dirs_to_scan, target_frag_path, crop_rect, tolerance, use_cache):
        super().__init__()
        self.dirs_to_scan = dirs_to_scan
        self.target_frag_path = target_frag_path
        self.crop_rect = crop_rect
        self.tolerance = tolerance # 0-100%
        self.use_cache = use_cache
        self.is_running = True
        
    def run(self):
        try:
            from utils_io import safe_cv2_imread
            engine = OrbEngine()
            cache = OrbCacheManager()
            
            img = safe_cv2_imread(self.target_frag_path)
            if img is None:
                self.finished_signal.emit(False, [])
                return
                
            if self.crop_rect:
                x, y, w, h = int(self.crop_rect.x()), int(self.crop_rect.y()), int(self.crop_rect.width()), int(self.crop_rect.height())
                frag_img = img[y:y+h, x:x+w]
            else:
                frag_img = img
                
            f_kp, f_desc, f_shape, f_scale = engine.extract_features_from_img(frag_img)
            
            all_files = []
            for d in self.dirs_to_scan:
                if not os.path.exists(d): continue
                for root, _, files in os.walk(d):
                    for f in files:
                        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff')):
                            all_files.append(os.path.join(root, f))
            
            total = len(all_files)
            results = []
            
            ratio_thresh = 0.7 + (self.tolerance / 100.0) * 0.15
            min_match = max(4, int(15 * (1 - self.tolerance / 100.0)))
            
            for idx, filepath in enumerate(all_files):
                if not self.is_running:
                    break
                    
                self.progress_update.emit(idx + 1, total, filepath)
                
                t_kp, t_desc, t_scale = None, None, 1.0
                if self.use_cache:
                    t_kp, t_desc, t_scale = cache.load_cache(filepath)
                    
                if t_desc is None:
                    t_kp, t_desc, t_shape, t_scale = engine.extract_features(filepath)
                    if self.use_cache and t_desc is not None:
                        cache.save_cache(filepath, t_kp, t_desc, t_scale)
                
                if t_desc is not None:
                    found, bbox, match_count = engine.match(f_kp, f_desc, f_shape, t_kp, t_desc, t_scale, 
                                                            ratio_thresh=ratio_thresh, min_match_count=min_match)
                    if found:
                        score = min(100, int((match_count / max(1, len(f_kp))) * 100 * 2))
                        results.append((filepath, score, bbox))
                        
            results.sort(key=lambda x: x[1], reverse=True)
            self.finished_signal.emit(True, results)
        except Exception as e:
            logging.error(f"Fragment search error: {e}", exc_info=True)
            self.finished_signal.emit(False, [])

class SingleFileDropZone(DropZoneWidget):
    file_dropped = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        # Force square shape with fixed minimum size for aesthetics
        self.setFixedSize(180, 180)
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1:
                event.accept()
                self.setProperty("dragHover", True)
                self.style().unpolish(self)
                self.style().polish(self)
                return
        event.ignore()

    def dropEvent(self, event):
        self.setProperty("dragHover", False)
        self.style().unpolish(self)
        self.style().polish(self)
        
        urls = event.mimeData().urls()
        if len(urls) == 1:
            filepath = urls[0].toLocalFile()
            if filepath.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff')):
                self.file_dropped.emit(filepath)

class AiFragmentTab(QWidget):
    scan_started = pyqtSignal()
    scan_finished = pyqtSignal()
    file_selected = pyqtSignal(str)
    
    def __init__(self, cleaner_module, parent=None):
        super().__init__(parent)
        self.cleaner = cleaner_module
        
        self.active_worker = None
        self.target_image_path = None
        self.crop_rect = None
        
        self.init_ui()
        self.temp_dir = os.path.join(get_app_data_dir(), "Temp")
        os.makedirs(self.temp_dir, exist_ok=True)
        
        try:
            for f in os.listdir(self.temp_dir):
                if f.startswith("frag_"):
                    os.remove(os.path.join(self.temp_dir, f))
        except:
            pass
            
    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.setHandleWidth(2)
        self.main_splitter.setStyleSheet("QSplitter::handle { background-color: #2d2d2d; }")
        
        # TOP SETTINGS PANEL
        self.top_settings = QFrame()
        self.top_settings.setMinimumHeight(220)
        self.top_settings.setMaximumHeight(600)
        self.top_settings.setStyleSheet("background-color: #1e1e1e; border-bottom: 1px solid #2d2d2d;")
        top_layout = QHBoxLayout(self.top_settings)
        top_layout.setContentsMargins(15, 6, 15, 6)
        top_layout.setSpacing(12)
        
        # COL 1: FRAGMENT
        col_ref = QVBoxLayout()
        col_ref.setContentsMargins(0, 0, 0, 0)
        col_ref.setSpacing(8)
        
        lbl_ref_title = QLabel("Исходное изображение" if AppContext.is_ru() else "Source Image")
        lbl_ref_title.setStyleSheet("color: #aaa; font-weight: bold; font-size: 11px;")
        lbl_ref_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col_ref.addWidget(lbl_ref_title)
        
        frag_layout = QHBoxLayout()
        frag_layout.addStretch()
        self.drop_zone = SingleFileDropZone(self)
        self.drop_zone.lbl_text.setText("Перетащите 1 фото\nдля поиска фрагмента")
        self.drop_zone.file_dropped.connect(self.on_file_dropped)
        frag_layout.addWidget(self.drop_zone)
        frag_layout.addStretch()
        col_ref.addLayout(frag_layout)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_crop = QPushButton("Выбрать фрагмент")
        self.btn_crop.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_crop.setStyleSheet("QPushButton { background-color: #2b2b2b; color: white; border: 1px solid #444; border-radius: 4px; padding: 4px 8px; } QPushButton:hover { background-color: #333; }")
        self.btn_crop.clicked.connect(self.open_crop_dialog)
        self.btn_crop.setEnabled(False)
        
        self.btn_clear_frag = QPushButton("Очистить")
        self.btn_clear_frag.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_clear_frag.setStyleSheet("QPushButton { background-color: #2b2b2b; color: #ef4444; border: 1px solid #444; border-radius: 4px; padding: 4px 8px; } QPushButton:hover { background-color: #333; }")
        self.btn_clear_frag.clicked.connect(self.clear_fragment)
        self.btn_clear_frag.setEnabled(False)
        
        btn_layout.addWidget(self.btn_crop)
        btn_layout.addWidget(self.btn_clear_frag)
        btn_layout.addStretch()
        col_ref.addLayout(btn_layout)
        col_ref.addStretch()
        top_layout.addLayout(col_ref, 1)
        
        # COL 2: DIRECTORIES
        col_dirs = QVBoxLayout()
        col_dirs.setContentsMargins(0, 0, 0, 0)
        col_dirs.setSpacing(4)
        
        lbl_dirs_title = QLabel("Папки для сканирования:" if AppContext.is_ru() else "Folders to scan:")
        lbl_dirs_title.setStyleSheet("color: #aaa; font-weight: bold; font-size: 11px;")
        col_dirs.addWidget(lbl_dirs_title)
        
        scroll_dirs = QScrollArea()
        scroll_dirs.setWidgetResizable(True)
        scroll_dirs.setStyleSheet("QScrollArea { border: 1px solid #333; border-radius: 6px; background-color: #1a1a1a; }")
        
        self.sources_list_widget_fragment = QWidget()
        self.sources_list_widget_fragment.setStyleSheet("background-color: transparent;")
        dirs_container_layout = QVBoxLayout(self.sources_list_widget_fragment)
        dirs_container_layout.setContentsMargins(5, 5, 5, 5)
        dirs_container_layout.setSpacing(4)
        dirs_container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.folder_list_layout_fragment = QVBoxLayout()
        self.folder_list_layout_fragment.setContentsMargins(0, 0, 0, 0)
        self.folder_list_layout_fragment.setSpacing(4)
        self.folder_list_layout_fragment.setAlignment(Qt.AlignmentFlag.AlignTop)
        dirs_container_layout.addLayout(self.folder_list_layout_fragment)
        
        self.drop_zone_fragment = DropZoneWidget()
        self.drop_zone_fragment.clicked.connect(self.cleaner.add_folder)
        self.drop_zone_fragment.folder_dropped.connect(self.cleaner.add_folder_path)
        if hasattr(self.drop_zone_fragment, 'files_dropped') and hasattr(self.cleaner, 'add_folder_paths'):
            self.drop_zone_fragment.files_dropped.connect(self.cleaner.add_folder_paths)
        self.drop_zone_fragment.clear_default_requested.connect(self.cleaner.clear_folders)
        self.drop_zone_fragment.btn_clear.show()
        self.drop_zone_fragment.setStyleSheet(self.drop_zone_fragment.styleSheet() + "margin: 0px; padding: 2px;")
        dirs_container_layout.addWidget(self.drop_zone_fragment)
        
        scroll_dirs.setWidget(self.sources_list_widget_fragment)
        col_dirs.addWidget(scroll_dirs)
        top_layout.addLayout(col_dirs, 2)
        
        # COL 3: PARAMS
        col_params = QVBoxLayout()
        col_params.setContentsMargins(0, 0, 0, 0)
        col_params.setSpacing(4)
        
        lbl_params_title = QLabel("Настройки поиска:" if AppContext.is_ru() else "Search Settings:")
        lbl_params_title.setStyleSheet("color: #aaa; font-weight: bold; font-size: 11px;")
        col_params.addWidget(lbl_params_title)
        
        params_container = QFrame()
        params_container.setStyleSheet("QFrame { background-color: #2b2b2b; border: 1px solid #444; border-radius: 6px; }")
        params_sub_layout = QVBoxLayout(params_container)
        
        # CACHE
        cache_layout = QHBoxLayout()
        self.chk_use_cache = QCheckBox("Кэшировать анализ (ORB)" if AppContext.is_ru() else "Cache ORB Analysis")
        self.chk_use_cache.setChecked(True)
        self.chk_use_cache.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_use_cache.setStyleSheet("QCheckBox { color: #eee; font-weight: bold; font-size: 12px; }")
        cache_layout.addWidget(self.chk_use_cache)
        cache_layout.addStretch()
        
        self.lbl_cache_info_fragment = QLabel("0 B")
        self.lbl_cache_info_fragment.setStyleSheet("color: #888; font-size: 11px;")
        cache_layout.addWidget(self.lbl_cache_info_fragment)
        
        from .ui_panels import load_svg_icon
        self.btn_clear_cache_fragment = QPushButton()
        self.btn_clear_cache_fragment.setIcon(load_svg_icon("trash.svg", "#ef4444"))
        self.btn_clear_cache_fragment.setIconSize(QSize(16, 16))
        self.btn_clear_cache_fragment.setToolTip("Очистить кэш ORB")
        self.btn_clear_cache_fragment.setFixedSize(32, 32)
        self.btn_clear_cache_fragment.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_cache_fragment.setStyleSheet("QPushButton { background-color: transparent; border: 1px solid #555; border-radius: 16px; padding: 0px; } QPushButton:hover { background-color: #444; border-color: #ef4444; }")
        self.btn_clear_cache_fragment.clicked.connect(self.clear_orb_cache)
        cache_layout.addWidget(self.btn_clear_cache_fragment)
        params_sub_layout.addLayout(cache_layout)
        
        # SIMILARITY
        lbl_sim = QLabel("Похожесть:" if AppContext.is_ru() else "Similarity:")
        lbl_sim.setStyleSheet("color: #eee; font-weight: bold; font-size: 12px; margin-top: 5px;")
        params_sub_layout.addWidget(lbl_sim)
        
        sim_layout = QHBoxLayout()
        self.slider_tolerance = QSlider(Qt.Orientation.Horizontal)
        self.slider_tolerance.setRange(0, 100)
        self.slider_tolerance.setValue(50)
        self.slider_tolerance.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider_tolerance.setStyleSheet("QSlider::groove:horizontal { height: 4px; background: #555; border-radius: 2px; } QSlider::handle:horizontal { background: #3b82f6; width: 14px; height: 14px; margin-top: -5px; margin-bottom: -5px; border-radius: 7px; }")
        
        self.lbl_tolerance_val = QLabel("50%")
        self.lbl_tolerance_val.setFixedWidth(40)
        self.lbl_tolerance_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_tolerance_val.setStyleSheet("color: #3b82f6; font-weight: bold;")
        self.slider_tolerance.valueChanged.connect(lambda v: self.lbl_tolerance_val.setText(f"{v}%"))
        
        sim_layout.addWidget(self.slider_tolerance)
        sim_layout.addWidget(self.lbl_tolerance_val)
        params_sub_layout.addLayout(sim_layout)
        
        params_sub_layout.addStretch()
        
        self.btn_start = QPushButton(" Начать Поиск" if AppContext.is_ru() else " Start Search")
        self.btn_start.setFixedHeight(40)
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.setStyleSheet("QPushButton { background-color: #15803d; color: white; font-weight: 900; font-size: 14px; border: 1px solid #16a34a; border-radius: 6px; } QPushButton:hover { background-color: #16a34a; }")
        self.btn_start.clicked.connect(self.start_scan)
        params_sub_layout.addWidget(self.btn_start)
        
        col_params.addWidget(params_container)
        top_layout.addLayout(col_params, 1)
        self.main_splitter.addWidget(self.top_settings)
        
        # BOTTOM: RESULTS & PREVIEW
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)
        
        # HEADER FOR BOTTOM
        header_widget = QWidget()
        header_widget.setFixedHeight(30)
        header_widget.setStyleSheet("background-color: #2b2b2b; border-bottom: 1px solid #333;")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(15, 0, 15, 0)
        header_layout.setSpacing(10)
        
        self.lbl_stats = QLabel("Найдено файлов: 0")
        self.lbl_stats.setStyleSheet("color: #aaa; font-size: 12px; font-weight: bold;")
        header_layout.addWidget(self.lbl_stats)
        header_layout.addStretch()
        bottom_layout.addWidget(header_widget)
        
        # SPLITTER FOR TREE AND PREVIEW
        self.right_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.right_splitter.setHandleWidth(2)
        self.right_splitter.setStyleSheet("QSplitter::handle { background-color: #2d2d2d; }")
        
        self.tree_results = QTreeWidget()
        self.tree_results.setColumnCount(3)
        self.tree_results.setHeaderLabels(["Файл", "Сходство (%)", "Размер", "Путь"])
        self.tree_results.setColumnWidth(0, 240)
        self.tree_results.setColumnWidth(1, 100)
        self.tree_results.setColumnWidth(2, 90)
        self.tree_results.setStyleSheet("QTreeWidget { background-color: #1a1a1a; border: none; outline: none; color: #eee; } QTreeWidget::item { padding: 6px; border-bottom: 1px solid #222; } QTreeWidget::item:selected { background-color: #2b2b2b; color: white; } QTreeWidget::indicator { width: 14px; height: 14px; border: 1px solid #666; border-radius: 3px; background-color: #2b2b2b; } QTreeWidget::indicator:hover { border-color: #3b82f6; } QTreeWidget::indicator:checked { background-color: #3b82f6; border: 1px solid #2563eb; } QTreeWidget::indicator:unchecked { background-color: #2b2b2b; }")
        self.tree_results.itemSelectionChanged.connect(self.on_tree_selection_changed)
        
        self.action_bar = CleanerActionBar()
        self.action_bar.is_similar_mode = False
        self.action_bar.combo_autoselect.hide()
        self.action_bar.btn_select_all.hide()
        self.action_bar.btn_deselect.hide()
        self.action_bar.chk_preserve.hide()
        self.action_bar.combo_collision.hide()
        
        self.preview_widget = CleanerPreviewWidget(self)
        
        bottom_right_widget = QWidget()
        br_layout = QVBoxLayout(bottom_right_widget)
        br_layout.setContentsMargins(0, 0, 0, 0)
        br_layout.addWidget(self.tree_results, 1)
        br_layout.addWidget(self.action_bar)
        
        self.right_splitter.addWidget(bottom_right_widget)
        self.right_splitter.addWidget(self.preview_widget)
        self.right_splitter.setStretchFactor(0, 2)
        self.right_splitter.setStretchFactor(1, 1)
        
        bottom_layout.addWidget(self.right_splitter, 1)
        
        self.main_splitter.addWidget(bottom_widget)
        self.main_layout.addWidget(self.main_splitter)
        
        QTimer.singleShot(100, self.update_cache_info_fragment)

    def update_folders_label(self, folders: list):
        while self.folder_list_layout_fragment.count():
            item = self.folder_list_layout_fragment.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
                
        for path in folders:
            color = "#3b82f6"
            is_system = False
            if path in self.cleaner.source_folders:
                color = self.cleaner.source_folders[path].get('color', color)
                is_system = self.cleaner.source_folders[path].get('is_system', False)
                
            item_widget = SourceListItem(path, color, is_cached=False, is_face_cached=False)
            if is_system:
                item_widget.set_system_error_state()
                
            item_widget.removed.connect(self.cleaner.remove_folder)
            item_widget.context_menu_requested.connect(self.cleaner.show_source_menu)
            self.folder_list_layout_fragment.addWidget(item_widget)

    def update_cache_info_fragment(self):
        try:
            cache = OrbCacheManager()
            db_path = cache.db_path
            if os.path.exists(db_path):
                size = os.path.getsize(db_path)
                wal_path = db_path + "-wal"
                shm_path = db_path + "-shm"
                if os.path.exists(wal_path): size += os.path.getsize(wal_path)
                if os.path.exists(shm_path): size += os.path.getsize(shm_path)
                self.lbl_cache_info_fragment.setText(f"{format_size(size)}")
            else:
                self.lbl_cache_info_fragment.setText("0 B")
        except Exception as e:
            self.lbl_cache_info_fragment.setText("0 B")

    def on_file_dropped(self, filepath):
        ext = os.path.splitext(filepath)[1]
        temp_name = f"frag_{int(time.time())}{ext}"
        self.target_image_path = os.path.join(self.temp_dir, temp_name)
        shutil.copy2(filepath, self.target_image_path)
        
        self.crop_rect = None
        self.update_dropzone_preview()
        
        self.btn_crop.setEnabled(True)
        self.btn_clear_frag.setEnabled(True)

    def update_dropzone_preview(self):
        if not self.target_image_path:
            self.drop_zone.lbl_text.setText("Перетащите 1 фото\\nдля поиска фрагмента")
            self.drop_zone.lbl_icon.show()
            self.drop_zone.setStyleSheet(self.drop_zone.styleSheet().replace("border-color: #3b82f6;", ""))
            if hasattr(self.drop_zone, 'img_label'):
                self.drop_zone.img_label.hide()
            return
            
        pixmap = QPixmap(self.target_image_path)
        if self.crop_rect and not self.crop_rect.isNull():
            pixmap = pixmap.copy(self.crop_rect.toRect())
            
        scaled = pixmap.scaled(self.drop_zone.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.drop_zone.lbl_text.setText("")
        self.drop_zone.lbl_icon.hide()
        
        if not hasattr(self.drop_zone, 'img_label'):
            self.drop_zone.img_label = QLabel(self.drop_zone)
            self.drop_zone.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.drop_zone.layout().addWidget(self.drop_zone.img_label)
            
        self.drop_zone.img_label.setPixmap(scaled)
        self.drop_zone.img_label.show()
        self.drop_zone.setStyleSheet(self.drop_zone.styleSheet() + "border-color: #3b82f6;")

    def open_crop_dialog(self):
        if not self.target_image_path: return
        dlg = CropDialog(self.target_image_path, self, self.crop_rect)
        if dlg.exec():
            rect = dlg.get_result()
            if rect:
                self.crop_rect = rect
                self.update_dropzone_preview()

    def clear_fragment(self):
        self.target_image_path = None
        self.crop_rect = None
        self.update_dropzone_preview()
        self.btn_crop.setEnabled(False)
        self.btn_clear_frag.setEnabled(False)

    def clear_orb_cache(self):
        reply = QMessageBox.question(self, "Очистить кэш ORB", "Очистить кэш ORB-дескрипторов?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            OrbCacheManager().clear_disk_cache()
            self.update_cache_info_fragment()

    def start_scan(self):
        if self.active_worker and self.active_worker.isRunning():
            self.active_worker.is_running = False
            self.btn_start.setText(" Начать Поиск")
            return
            
        dirs = list(self.cleaner.source_folders_fragment.keys()) if hasattr(self.cleaner, 'source_folders_fragment') else []
        if not dirs:
            QMessageBox.warning(self, "Ошибка", "Добавьте папки для поиска.")
            return
            
        if not self.target_image_path:
            QMessageBox.warning(self, "Ошибка", "Добавьте изображение-фрагмент.")
            return
            
        self.tree_results.clear()
        self.action_bar.lbl_selection_info.setText("Выбрано: 0")
        self.lbl_stats.setText("Идет сканирование...")
        self.btn_start.setText(" Остановить")
        self.preview_widget.show_empty("Сканирование...")
        
        self.active_worker = FragmentScannerThread(
            dirs, 
            self.target_image_path, 
            self.crop_rect,
            self.slider_tolerance.value(),
            self.chk_use_cache.isChecked()
        )
        self.active_worker.progress_update.connect(self._on_progress)
        self.active_worker.finished_signal.connect(self._on_scan_finished)
        self.active_worker.start()
        self.scan_started.emit()

    def _on_progress(self, current, total, text):
        self.lbl_stats.setText(f"Сканирование: {current}/{total} файлов")

    def _on_scan_finished(self, success, results):
        self.btn_start.setText(" Начать Поиск")
        self.update_cache_info_fragment()
        
        if success:
            self.lbl_stats.setText(f"Поиск завершен. Найдено файлов: {len(results)}")
            for filepath, score, bbox in results:
                size_str = format_size(os.path.getsize(filepath)) if os.path.exists(filepath) else "0 B"
                item = QTreeWidgetItem([os.path.basename(filepath), f"{score}%", size_str, filepath])
                item.setData(0, Qt.ItemDataRole.UserRole, {"path": filepath, "bbox": bbox})
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Unchecked)
                self.tree_results.addTopLevelItem(item)
        else:
            self.lbl_stats.setText("Поиск остановлен или произошла ошибка.")
        self.scan_finished.emit()

    def on_tree_selection_changed(self):
        self.update_action_bar_info()
        items = self.tree_results.selectedItems()
        if not items:
            self.preview_widget.show_empty("Выберите файл для предпросмотра")
            self.file_selected.emit("")
            return
            
        item = items[0]
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and "path" in data:
            path = data["path"]
            self.preview_widget.load_preview(path)
            # Draw bbox if exists
            bbox = data.get("bbox")
            if bbox and hasattr(self.preview_widget, "draw_faces"):
                self.preview_widget.draw_faces([bbox], matched_bbox=bbox)
            self.file_selected.emit(path)

    def get_selected_files_paths(self):
        paths = []
        root = self.tree_results.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if data and "path" in data:
                    paths.append(data["path"])
        return paths

    def update_action_bar_info(self):
        selected_paths = self.get_selected_files_paths()
        count = len(selected_paths)
        size = sum(os.path.getsize(p) for p in selected_paths if os.path.exists(p))
        size_str = format_size(size)
        
        self.action_bar.lbl_selection_info.setStyleSheet("color: #93c5fd; font-size: 11px; font-weight: bold;")
        self.action_bar.lbl_selection_info.setText(f"Выбрано: {count} файлов • {size_str}")
        
        has_selection = (count > 0)
        self.action_bar.btn_delete.setEnabled(has_selection)
        self.action_bar.btn_move.setEnabled(has_selection and bool(self.action_bar.drop_zone.get_path()))
        self.action_bar.btn_move_to.setEnabled(has_selection)
        
    def select_all_results(self, checked: bool):
        self.tree_results.blockSignals(True)
        try:
            root = self.tree_results.invisibleRootItem()
            state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            for i in range(root.childCount()):
                root.child(i).setCheckState(0, state)
        finally:
            self.tree_results.blockSignals(False)
        self.update_action_bar_info()
        
    def remove_processed_files(self, paths: list[str]):
        paths_set = set(os.path.normpath(p) for p in paths)
        root = self.tree_results.invisibleRootItem()
        
        for i in range(root.childCount() - 1, -1, -1):
            item = root.child(i)
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data.get("path") and os.path.normpath(data["path"]) in paths_set:
                root.removeChild(item)
                
        self.preview_widget.show_empty("Выберите файл для предпросмотра")
        self.update_action_bar_info()

    def set_scan_enabled(self, enabled: bool):
        pass # UI state is handled internally for now
"""

with open(r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("ui_fragment_tab patched.")
