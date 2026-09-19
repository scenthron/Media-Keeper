
import os
import shutil
import time
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QMessageBox, QSlider, QTreeWidget, QTreeWidgetItem, QProgressBar,
    QSplitter, QSizePolicy, QCheckBox, QScrollArea, QMenu
, QTabWidget)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QThread, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QColor, QCursor, QAction

from .ui_widgets import CleanerTreeWidget

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
    
    def __init__(self, dirs_to_scan, target_frag_path, crop_rect, tolerance, use_cache, algorithm="pixel", max_features=10000, filter_config=None, optimize_bw=False):
        super().__init__()
        self.dirs_to_scan = dirs_to_scan
        self.filter_config = filter_config or {'mode': 'all', 'exts': []}
        self.target_frag_path = target_frag_path
        self.crop_rect = crop_rect
        self.tolerance = tolerance # 0-100%
        self.use_cache = use_cache
        self.algorithm = algorithm
        self.max_features = max_features
        self.optimize_bw = optimize_bw
        self.is_running = True
        
    def run(self):
        try:
            import os
            from utils_io import safe_cv2_imread
            engine = OrbEngine()
            cache = OrbCacheManager()
            
            import cv2
            img = safe_cv2_imread(self.target_frag_path)
            if img is None:
                self.finished_signal.emit(False, [])
                return
                
            if self.crop_rect:
                x, y = int(self.crop_rect.x()), int(self.crop_rect.y())
                w, h = int(self.crop_rect.width()), int(self.crop_rect.height())
                frag_img = img[y:y+h, x:x+w]
            else:
                frag_img = img
                
            f_kp, f_desc, f_shape, f_scale = engine.extract_features_from_img(frag_img, max_dim=99999)
            
            all_files = []
            for d in self.dirs_to_scan:
                if not os.path.exists(d): continue
                for root, _, files in os.walk(d):
                    for f in files:
                        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff')):
                            all_files.append(os.path.join(root, f))
            
            total = len(all_files)
            results = []
            
            # Slider: 100% (Strict), 0% (Loose)
            ratio_thresh = 0.85 - (self.tolerance / 100.0) * 0.30
            min_match = max(4, int(4 + (7 - 4) * (self.tolerance / 100.0)))
            
            import time
            last_progress_time = time.time()
            
            for idx, filepath in enumerate(all_files):
                if not self.is_running:
                    break
                    
                current_time = time.time()
                if current_time - last_progress_time > 0.2 or idx == total - 1:
                    import os
                    self.progress_update.emit(idx + 1, total, f"Найдено: {len(results)} | {os.path.basename(filepath)}")
                    last_progress_time = current_time
                
                if self.algorithm == "pixel":
                    from utils_io import safe_cv2_imread
                    t_img = safe_cv2_imread(filepath)
                    if t_img is not None:
                        found, bbox, score_raw = engine.match_template(frag_img, t_img, self.tolerance, getattr(self, 'optimize_bw', False))
                        if found:
                            score = min(100, int(score_raw * 100))
                            results.append((filepath, score, bbox))
                        del t_img
                else:
                    t_kp, t_desc, t_scale = None, None, 1.0
                    if self.use_cache:
                        t_kp, t_desc, t_scale = cache.load_cache(filepath)
                        
                    if t_desc is None:
                        t_kp, t_desc, t_shape, t_scale = engine.extract_features(filepath, max_dim=99999)
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
        self.setFixedSize(180, 180)
        self.btn_del_img = None
        
    def enterEvent(self, event):
        if self.btn_del_img and not self.btn_del_img.isHidden() and getattr(self, 'has_image', False):
            self.btn_del_img.show()
        elif self.btn_del_img and getattr(self, 'has_image', False):
            self.btn_del_img.show()
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        if self.btn_del_img:
            self.btn_del_img.hide()
        super().leaveEvent(event)
        
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
        self.top_settings.setFixedHeight(260)
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
        self.drop_zone.lbl_text.setText("Перетащите 1 фото\nдля поиска фрагмента" if AppContext.is_ru() else "Drop 1 photo\nto search for fragment")
        self.drop_zone.file_dropped.connect(self.on_file_dropped)
        self.drop_zone.clicked.connect(self.browse_fragment_image)
        frag_layout.addWidget(self.drop_zone)
        frag_layout.addStretch()
        col_ref.addLayout(frag_layout)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_crop = QPushButton("Выбрать фрагмент" if AppContext.is_ru() else "Select fragment")
        self.btn_crop.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_crop.setStyleSheet("QPushButton { background-color: #2b2b2b; color: white; border: 1px solid #444; border-radius: 4px; padding: 4px 8px; } QPushButton:hover { background-color: #333; }")
        self.btn_crop.clicked.connect(self.open_crop_dialog)
        self.btn_crop.setEnabled(False)
        
        self.btn_clear_frag = QPushButton("Очистить" if AppContext.is_ru() else "Clear")
        self.btn_clear_frag.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_clear_frag.setStyleSheet("QPushButton { background-color: #2b2b2b; color: #ef4444; border: 1px solid #444; border-radius: 4px; padding: 4px 8px; } QPushButton:hover { background-color: #333; }")
        self.btn_clear_frag.clicked.connect(self.clear_fragment)
        self.btn_clear_frag.setEnabled(False)
        
        btn_layout.addWidget(self.btn_crop)
        btn_layout.addWidget(self.btn_clear_frag)
        btn_layout.addStretch()
        col_ref.addLayout(btn_layout)
        col_ref.addStretch()
        top_layout.addLayout(col_ref, 3)
        
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
        
        # Filter Layout
        filter_layout = QHBoxLayout()
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(8)
        
        import os
        
        
        from .ui_panels import load_svg_icon
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
        
        self.btn_filter = QPushButton("Сканировать типы файлов" if AppContext.is_ru() else "Scan file types")
        self.btn_filter.setIcon(load_svg_icon(os.path.join(icons_dir, "loupe-color.svg"), QSize(16, 16)))
        self.btn_filter.setIconSize(QSize(16, 16))
        self.btn_filter.setFixedHeight(36)
        self.btn_filter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_filter.setStyleSheet("QPushButton { background-color: #444; color: #fff; border: 1px solid #666; padding: 0 10px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #555; color: white; border-color: #888; }")
        self.btn_filter.clicked.connect(self.open_filter_dialog)
        
        self.lbl_filter_status = QLabel("Фильтр: Все файлы" if AppContext.is_ru() else "Filter: All files")
        self.lbl_filter_status.setStyleSheet("color: #aaa; font-size: 11px;")
        self.lbl_filter_status.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        filter_layout.addWidget(self.btn_filter)
        filter_layout.addWidget(self.lbl_filter_status)
        filter_layout.addStretch()
        
        col_dirs.addLayout(filter_layout)
        
        self.fragment_filter_config = {'mode': 'all', 'exts': []}
        
        top_layout.addLayout(col_dirs, 4)
        
        # COL 3: PARAMS
        col_params = QVBoxLayout()
        col_params.setContentsMargins(0, 0, 0, 0)
        col_params.setSpacing(4)
        
        lbl_params_title = QLabel("Настройки поиска:" if AppContext.is_ru() else "Search Settings:")
        lbl_params_title.setStyleSheet("color: #aaa; font-weight: bold; font-size: 11px;")
        col_params.addWidget(lbl_params_title)
        
        self.settings_tabs = QTabWidget()
        self.settings_tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #444; border-radius: 6px; background-color: #2b2b2b; }
            QTabBar::tab { background-color: #1e1e1e; color: #888; padding: 6px 12px; border: 1px solid #444; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; }
            QTabBar::tab:selected { background-color: #2b2b2b; color: white; font-weight: bold; }
        """)
        
        slider_style = "QSlider::groove:horizontal { height: 4px; background: #555; border-radius: 2px; } QSlider::handle:horizontal { background: #3b82f6; width: 14px; height: 14px; margin-top: -5px; margin-bottom: -5px; border-radius: 7px; }"
        
        # ==========================================
        # TAB 1: PIXEL MATCHING
        # ==========================================
        tab_pixel = QWidget()
        tab_pixel_layout = QVBoxLayout(tab_pixel)
        
        lbl_sim_pixel = QLabel("Схожесть (Пиксели):" if AppContext.is_ru() else "Similarity (Pixels):")
        lbl_sim_pixel.setStyleSheet("color: #eee; font-weight: bold; font-size: 12px; margin-top: 5px;")
        tab_pixel_layout.addWidget(lbl_sim_pixel)
        
        sim_layout_pixel = QHBoxLayout()
        self.slider_pixel = QSlider(Qt.Orientation.Horizontal)
        self.slider_pixel.setRange(0, 100)
        self.slider_pixel.setValue(80)
        self.slider_pixel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider_pixel.setStyleSheet(slider_style)
        
        self.lbl_pixel_val = QLabel("80%")
        self.lbl_pixel_val.setFixedWidth(40)
        self.lbl_pixel_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_pixel_val.setStyleSheet("color: #3b82f6; font-weight: bold;")
        self.slider_pixel.valueChanged.connect(lambda v: self.lbl_pixel_val.setText(f"{v}%"))
        
        sim_layout_pixel.addWidget(self.slider_pixel)
        sim_layout_pixel.addWidget(self.lbl_pixel_val)
        tab_pixel_layout.addLayout(sim_layout_pixel)
        
        desc_pixel = QLabel("Мгновенный поиск. Чувствителен к изменению масштаба." if AppContext.is_ru() else "Instant search. Sensitive to scale changes.")
        desc_pixel.setStyleSheet("color: #888; font-size: 11px;")
        desc_pixel.setWordWrap(True)
        tab_pixel_layout.addWidget(desc_pixel)
        
        self.chk_pixel_bw = QCheckBox("Черно-белый режим (Ускорение x3)" if AppContext.is_ru() else "Grayscale mode (3x speedup)")
        self.chk_pixel_bw.setStyleSheet("QCheckBox { color: #ccc; font-weight: bold; font-size: 11px; margin-top: 5px; } QCheckBox::indicator { width: 14px; height: 14px; border-radius: 3px; border: 1px solid #555; background: #111; } QCheckBox::indicator:checked { background-color: #3b82f6; border-color: #3b82f6; }")
        self.chk_pixel_bw.setChecked(False)
        tab_pixel_layout.addWidget(self.chk_pixel_bw)
        
        tab_pixel_layout.addStretch()
        self.settings_tabs.addTab(tab_pixel, "Пиксельный" if AppContext.is_ru() else "Pixel")
        
        # ==========================================
        # TAB 2: SIFT MATCHING
        # ==========================================
        tab_sift = QWidget()
        tab_sift_layout = QVBoxLayout(tab_sift)
        
        cache_layout = QHBoxLayout()
        self.chk_use_cache = QCheckBox("Использовать кэш" if AppContext.is_ru() else "Use Cache")
        self.chk_use_cache.setChecked(True)
        self.chk_use_cache.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_use_cache.setStyleSheet("""
            QCheckBox { color: white; font-weight: bold; font-size: 13px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 3px; border: 1px solid #555; background: #111; }
            QCheckBox::indicator:checked { background-color: #3b82f6; border-color: #3b82f6; }
        """)
        cache_layout.addWidget(self.chk_use_cache)
        cache_layout.addStretch()
        
        self.lbl_cache_info_fragment = QLabel("0 B")
        self.lbl_cache_info_fragment.setStyleSheet("color: #888; font-size: 12px; margin-right: 5px;")
        cache_layout.addWidget(self.lbl_cache_info_fragment)
        
        from .ui_panels import load_svg_icon
        self.btn_clear_cache_fragment = QPushButton()
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
        self.btn_clear_cache_fragment.setIcon(load_svg_icon(os.path.join(icons_dir, "trash-color.svg"), QSize(16, 16)))
        self.btn_clear_cache_fragment.setIconSize(QSize(16, 16))
        self.btn_clear_cache_fragment.setToolTip("Очистить кэш" if AppContext.is_ru() else "Clear Cache")
        self.btn_clear_cache_fragment.setFixedSize(32, 32)
        self.btn_clear_cache_fragment.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_cache_fragment.setStyleSheet("""
            QPushButton { background-color: #2b2b2b; border: 1px solid #444; border-radius: 16px; padding: 0px; }
            QPushButton:hover { background-color: #444; border-color: #666; }
        """)
        self.btn_clear_cache_fragment.clicked.connect(self.clear_orb_cache)
        cache_layout.addWidget(self.btn_clear_cache_fragment)
        tab_sift_layout.addLayout(cache_layout)
        
        # SIFT Similarity
        lbl_sim = QLabel("Схожесть (Векторы):" if AppContext.is_ru() else "Similarity (Vectors):")
        lbl_sim.setStyleSheet("color: #eee; font-weight: bold; font-size: 12px; margin-top: 5px;")
        tab_sift_layout.addWidget(lbl_sim)
        
        sim_layout = QHBoxLayout()
        self.slider_tolerance = QSlider(Qt.Orientation.Horizontal)
        self.slider_tolerance.setRange(0, 100)
        self.slider_tolerance.setValue(50)
        self.slider_tolerance.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider_tolerance.setStyleSheet(slider_style)
        
        self.lbl_tolerance_val = QLabel("50%")
        self.lbl_tolerance_val.setFixedWidth(40)
        self.lbl_tolerance_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_tolerance_val.setStyleSheet("color: #3b82f6; font-weight: bold;")
        self.slider_tolerance.valueChanged.connect(lambda v: self.lbl_tolerance_val.setText(f"{v}%"))
        
        sim_layout.addWidget(self.slider_tolerance)
        sim_layout.addWidget(self.lbl_tolerance_val)
        tab_sift_layout.addLayout(sim_layout)
        
        # SIFT Features limit
        from PyQt6.QtWidgets import QComboBox
        features_layout = QHBoxLayout()
        lbl_features = QLabel("Точек сканирования:" if AppContext.is_ru() else "Features limit:")
        lbl_features.setStyleSheet("color: #ccc; font-size: 11px;")
        features_layout.addWidget(lbl_features)
        
        self.combo_features = QComboBox()
        self.combo_features.addItems(["1000", "5000", "10000", "50000"])
        self.combo_features.setCurrentText("10000")
        self.combo_features.setStyleSheet("QComboBox { background-color: #222; color: #eee; border: 1px solid #444; border-radius: 4px; padding: 2px 5px; font-size: 11px; }")
        features_layout.addWidget(self.combo_features)
        features_layout.addStretch()
        tab_sift_layout.addLayout(features_layout)
        
        desc_sift = QLabel("Игнорирует масштаб и фильтры. Медленно." if AppContext.is_ru() else "Scale/filter invariant. Slow.")
        desc_sift.setStyleSheet("color: #888; font-size: 11px;")
        desc_sift.setWordWrap(True)
        tab_sift_layout.addWidget(desc_sift)
        
        self.settings_tabs.addTab(tab_sift, "Векторный (SIFT)" if AppContext.is_ru() else "Vector (SIFT)")
        
        col_params.addWidget(self.settings_tabs)
        
        self.btn_start = QPushButton(" Начать поиск" if AppContext.is_ru() else " Start Scan")
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
        self.btn_start.setIcon(QIcon(os.path.join(icons_dir, "play.svg")))
        self.btn_start.setFixedHeight(36)
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.setStyleSheet("QPushButton { background-color: #15803d; color: white; font-weight: 900; font-size: 14px; border: 1px solid #16a34a; border-radius: 6px; } QPushButton:hover { background-color: #16a34a; }")
        self.btn_start.clicked.connect(self.start_scan)
        
        col_params.addWidget(self.btn_start)
        
        top_layout.addLayout(col_params, 3)
        self.main_splitter.addWidget(self.top_settings)
        
        # BOTTOM: RESULTS & PREVIEW
        bottom_widget = QWidget()
        bot_layout = QVBoxLayout(bottom_widget)
        bot_layout.setContentsMargins(0, 0, 0, 0)
        bot_layout.setSpacing(0)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: none; background-color: #151515; text-align: center; color: white; font-size: 11px; }
            QProgressBar::chunk { background-color: #3b82f6; }
        """)
        self.progress_bar.hide()
        bot_layout.addWidget(self.progress_bar)
        
        self.lbl_stats = QLabel("")
        self.lbl_stats.setStyleSheet("color: #4ade80; font-weight: bold; font-size: 12px; border: none; padding: 4px 15px; background-color: #1e1e1e;")
        bot_layout.addWidget(self.lbl_stats)
        
        from .ui_panels import CleanerActionBar
        self.action_bar = CleanerActionBar()
        self.action_bar.is_similar_mode = False
        self.action_bar.combo_autoselect.hide()
        self.action_bar.btn_select_all.hide()
        self.action_bar.btn_deselect.hide()
        self.action_bar.chk_preserve.hide()
        self.action_bar.combo_collision.hide()
        bot_layout.addWidget(self.action_bar)

        # --- Тулбар таблицы (над таблицей) ---
        tt_bar = QFrame()
        tt_bar.setFixedHeight(34)
        tt_bar.setStyleSheet("QFrame { background-color: #1a1a1a; border-top: 1px solid #2a2a2a; border-bottom: 1px solid #2a2a2a; }")
        tt_layout = QHBoxLayout(tt_bar)
        tt_layout.setContentsMargins(10, 0, 10, 0)
        tt_layout.setSpacing(6)
        tt_layout.addStretch(1)

        self.lbl_selection_info = QLabel("Выбрано: 0 файлов • 0 B" if AppContext.is_ru() else "Selected: 0 files • 0 B")
        self.lbl_selection_info.setStyleSheet("color: #93c5fd; font-size: 11px; font-weight: bold;")
        tt_layout.addWidget(self.lbl_selection_info)

        bot_layout.addWidget(tt_bar)

        
        self.right_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.right_splitter.setHandleWidth(2)
        self.right_splitter.setStyleSheet("QSplitter::handle { background-color: #2d2d2d; }")
        
        self.tree_results = CleanerTreeWidget()
        self.tree_results.setColumnCount(4)
        self.tree_results.setHeaderLabels(["Файл", "Сходство (%)", "Размер", "Путь"] if AppContext.is_ru() else ["File", "Similarity (%)", "Size", "Path"])
        self.tree_results.setColumnWidth(0, 240)
        self.tree_results.setColumnWidth(1, 100)
        self.tree_results.setColumnWidth(2, 90)
        self.tree_results.setStyleSheet('''
            QTreeWidget { background-color: #1a1a1a; border: none; outline: none; color: #eee; } 
            QTreeWidget::item { padding: 6px; border-bottom: 1px solid #222; } 
            QTreeWidget::item:selected { background-color: #2b2b2b; color: white; }
            QTreeWidget::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #666;
                border-radius: 3px;
                background-color: #2b2b2b;
            }
            QTreeWidget::indicator:hover { border-color: #3b82f6; }
            QTreeWidget::indicator:checked {
                background-color: #3b82f6;
                border: 1px solid #2563eb;
            }
            QTreeWidget::indicator:unchecked { background-color: #2b2b2b; }
        ''')
        self.tree_results.itemSelectionChanged.connect(self.on_tree_selection_changed)
        self.tree_results.itemChanged.connect(self.on_tree_item_changed)
        self.tree_results.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_results.customContextMenuRequested.connect(self.show_context_menu)
        
        self.right_splitter.addWidget(self.tree_results)
        
        from .ui_preview import CleanerPreviewWidget
        self.preview_widget = CleanerPreviewWidget()
        self.preview_widget.show_empty("Выберите файл для предпросмотра" if AppContext.is_ru() else "Select a file for preview")
        self.right_splitter.addWidget(self.preview_widget)
        
        self.right_splitter.setSizes([650, 350])
        bot_layout.addWidget(self.right_splitter, 1)
        
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
            size = 0
            if os.path.exists(cache.cache_dir):
                for f in os.listdir(cache.cache_dir):
                    fp = os.path.join(cache.cache_dir, f)
                    if os.path.isfile(fp):
                        size += os.path.getsize(fp)
                self.lbl_cache_info_fragment.setText(f"{format_size(size)}")
            else:
                self.lbl_cache_info_fragment.setText("0 B")
        except Exception as e:
            self.lbl_cache_info_fragment.setText("0 B")

    def browse_fragment_image(self):
        from PyQt6.QtWidgets import QFileDialog
        title = "Выберите изображение" if AppContext.is_ru() else "Select Image"
        f, _ = QFileDialog.getOpenFileName(self, title, "", "Images (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff)")
        if f:
            self.on_file_dropped(f)

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
            self.drop_zone.has_image = False
            self.drop_zone.lbl_text.setText("Перетащите 1 фото\nдля поиска фрагмента" if AppContext.is_ru() else "Drop 1 photo\nto search for fragment")
            self.drop_zone.lbl_text.show()
            self.drop_zone.btn_add.show()
            self.drop_zone.setStyleSheet(self.drop_zone.styleSheet().replace("border-color: #3b82f6;", ""))
            if hasattr(self.drop_zone, 'img_label'):
                self.drop_zone.img_label.hide()
            if hasattr(self.drop_zone, 'btn_del_img') and self.drop_zone.btn_del_img:
                self.drop_zone.btn_del_img.hide()
            # Restore icon if exists
            for i in range(self.drop_zone.layout().count()):
                w = self.drop_zone.layout().itemAt(i).widget()
                if isinstance(w, QLabel) and w != self.drop_zone.lbl_text and w != getattr(self.drop_zone, 'img_label', None):
                    w.show()
            return
            
        self.drop_zone.has_image = True
        pixmap = QPixmap(self.target_image_path)
        if self.crop_rect and not self.crop_rect.isNull():
            pixmap = pixmap.copy(self.crop_rect.toRect())
            
        # Symmetrical margins (3px)
        target_size = self.drop_zone.size()
        target_size.setWidth(target_size.width() - 6)
        target_size.height()
        scaled = pixmap.scaled(target_size.width(), target_size.height() - 6, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.drop_zone.lbl_text.hide()
        self.drop_zone.btn_add.hide()
        
        # Hide the icon label (which is the first widget)
        for i in range(self.drop_zone.layout().count()):
            w = self.drop_zone.layout().itemAt(i).widget()
            if isinstance(w, QLabel) and w != self.drop_zone.lbl_text and w != getattr(self.drop_zone, 'img_label', None):
                w.hide()
        
        if not hasattr(self.drop_zone, 'img_label'):
            self.drop_zone.img_label = QLabel(self.drop_zone)
            self.drop_zone.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.drop_zone.img_label.setCursor(Qt.CursorShape.PointingHandCursor)
            self.drop_zone.img_label.mousePressEvent = lambda e: self.open_crop_dialog()
            # Absolute positioning to avoid layout stretches
            self.drop_zone.img_label.setGeometry(3, 3, self.drop_zone.width()-6, self.drop_zone.height()-6)
            
        if not self.drop_zone.btn_del_img:
            self.drop_zone.btn_del_img = QPushButton("✕", self.drop_zone)
            self.drop_zone.btn_del_img.setFixedSize(24, 24)
            self.drop_zone.btn_del_img.setCursor(Qt.CursorShape.PointingHandCursor)
            self.drop_zone.btn_del_img.setStyleSheet("QPushButton { background-color: rgba(239, 68, 68, 0.85); color: white; border-radius: 12px; font-weight: bold; font-size: 14px; padding-bottom: 2px;} QPushButton:hover { background-color: #dc2626; }")
            self.drop_zone.btn_del_img.move(self.drop_zone.width() - 30, 6)
            self.drop_zone.btn_del_img.clicked.connect(self.clear_fragment)
            self.drop_zone.btn_del_img.hide()
            
        self.drop_zone.img_label.setPixmap(scaled)
        self.drop_zone.img_label.show()
        if self.drop_zone.underMouse():
            self.drop_zone.btn_del_img.show()
        if "border-color: #3b82f6;" not in self.drop_zone.styleSheet():
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
        reply = QMessageBox.question(self, "Очистить кэш" if AppContext.is_ru() else "Clear Cache", "Очистить кэш-дескрипторов?" if AppContext.is_ru() else "Clear descriptor cache?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            OrbCacheManager().clear_disk_cache()
            self.update_cache_info_fragment()

    def open_filter_dialog(self):
        dirs = list(self.cleaner.source_folders.keys()) if hasattr(self.cleaner, 'source_folders') else []
            
        if not dirs:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Ошибка" if AppContext.is_ru() else "Error", "Сначала добавьте папки для сканирования." if AppContext.is_ru() else "Please add folders to scan first.")
            return
            
        self.btn_filter.setEnabled(False)
        self.btn_filter.setText("Сканирование..." if AppContext.is_ru() else "Scanning...")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, lambda: self._run_extension_scan(dirs))

    def _run_extension_scan(self, folders):
        from .workers import ExtensionScannerWorker
        self.ext_scanner = ExtensionScannerWorker(folders)
        self.ext_scanner.finished.connect(self._on_ext_scan_finished)
        self.ext_scanner.start()

    def _on_ext_scan_finished(self, stats: dict):
        self.btn_filter.setEnabled(True)
        self.btn_filter.setText("Фильтр файлов" if AppContext.is_ru() else "File Filter")
        
        from .ui_dialogs import MatrixFilterDialog
        dlg = MatrixFilterDialog(stats, self)
        if dlg.exec():
            res = dlg.get_result()
            self.fragment_filter_config = {'mode': res['mode'], 'exts': res['exts']}
            
            if res['mode'] == 'all':
                self.lbl_filter_status.setText("Все картинки" if AppContext.is_ru() else "All Images")
                self.lbl_filter_status.setStyleSheet("color: #aaa; font-size: 11px;")
            elif res['mode'] == 'include':
                self.lbl_filter_status.setText(f"Только: {', '.join(res['exts'])}" if AppContext.is_ru() else f"Only: {', '.join(res['exts'])}")
                self.lbl_filter_status.setStyleSheet("color: #4ade80; font-size: 11px;")
            else:
                self.lbl_filter_status.setText(f"Кроме: {', '.join(res['exts'])}" if AppContext.is_ru() else f"Except: {', '.join(res['exts'])}")
                self.lbl_filter_status.setStyleSheet("color: #f87171; font-size: 11px;")

    def start_scan(self):
        if self.active_worker and self.active_worker.isRunning():
            self.active_worker.is_running = False
            self.btn_start.setText(" Начать Поиск" if AppContext.is_ru() else " Start Search")
            return
            
        dirs = list(self.cleaner.source_folders.keys()) if hasattr(self.cleaner, 'source_folders') else []
        if not dirs:
            QMessageBox.warning(self, "Ошибка" if AppContext.is_ru() else "Error", "Добавьте папки для поиска." if AppContext.is_ru() else "Please add folders to search.")
            return
            
        if not self.target_image_path:
            QMessageBox.warning(self, "Ошибка" if AppContext.is_ru() else "Error", "Добавьте изображение-фрагмент." if AppContext.is_ru() else "Please add a fragment image.")
            return
            
        self.tree_results.clear()
        self.lbl_selection_info.setText("Выбрано: 0 файлов • 0 B" if AppContext.is_ru() else "Selected: 0 files • 0 B")
        self.lbl_stats.hide()
        self.progress_bar.show()
        self.progress_bar.setFormat("Подготовка к сканированию..." if AppContext.is_ru() else "Preparing for scan...")
        self.btn_start.setText(" Остановить" if AppContext.is_ru() else " Stop")
        self.preview_widget.show_empty("Сканирование..." if AppContext.is_ru() else "Scanning...")
        
        alg = "pixel" if self.settings_tabs.currentIndex() == 0 else "vector"
        tol = self.slider_pixel.value() if alg == "pixel" else self.slider_tolerance.value()
        
        self.active_worker = FragmentScannerThread(
            dirs, 
            self.target_image_path, 
            self.crop_rect,
            tol,
            self.chk_use_cache.isChecked(),
            algorithm=alg,
            max_features=int(self.combo_features.currentText()) if hasattr(self, 'combo_features') else 10000,
            optimize_bw=getattr(self, 'chk_pixel_bw', None) and self.chk_pixel_bw.isChecked() if alg == "pixel" else False
        )
        self.active_worker.progress_update.connect(self._on_progress)
        self.active_worker.finished_signal.connect(self._on_scan_finished)
        self.active_worker.start()
        self.scan_started.emit()

    def _on_progress(self, current, total, text):
        if not self.progress_bar.isVisible():
            self.progress_bar.show()
            self.lbl_stats.hide()
            
        if total > 0:
            percent = (current / total) * 100
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
            self.progress_bar.setFormat(f"Сканирование: {current}/{total} файлов ({int(percent)}%) - {text}" if AppContext.is_ru() else f"Scanning: {current}/{total} files ({int(percent)}%) - {text}")
            


    def _on_scan_finished(self, success, results):
        self.btn_start.setText(" Начать Поиск" if AppContext.is_ru() else " Start Search")
        self.update_cache_info_fragment()
        
        if success:
            self.progress_bar.hide()
            self.lbl_stats.show()
            self.lbl_stats.setText(f"Поиск завершен. Найдено файлов: {len(results)}" if AppContext.is_ru() else f"Search completed. Found files: {len(results)}")
            for filepath, score, bbox in results:
                size_str = format_size(os.path.getsize(filepath)) if os.path.exists(filepath) else "0 B"
                item = QTreeWidgetItem([os.path.basename(filepath), f"{score}%", size_str, filepath])
                item.setData(0, Qt.ItemDataRole.UserRole, {"path": filepath, "bbox": bbox})
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Unchecked)
                self.tree_results.addTopLevelItem(item)
        else:
            self.progress_bar.hide()
            self.lbl_stats.show()
            self.lbl_stats.setText("Поиск остановлен или произошла ошибка." if AppContext.is_ru() else "Search stopped or an error occurred.")
        self.scan_finished.emit()

    def on_tree_item_changed(self, item, column):
        self.update_action_bar_info()
        
    def show_context_menu(self, pos):
        item = self.tree_results.itemAt(pos)
        
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #2b2b2b; color: #eee; border: 1px solid #444; } QMenu::item { padding: 6px 20px; } QMenu::item:selected { background-color: #3b82f6; color: white; }")
        
        action_select_all = QAction("Выделить всё", self)
        action_select_all.triggered.connect(lambda: self.select_all_results(True))
        menu.addAction(action_select_all)
        
        action_deselect_all = QAction("Снять выделение со всех", self)
        action_deselect_all.triggered.connect(lambda: self.select_all_results(False))
        menu.addAction(action_deselect_all)
        
        menu.addSeparator()
        
        action_send_sorter = QAction("Отправить выделенные в сортировщик", self)
        action_send_sorter.triggered.connect(lambda: self.action_bar.btn_move.clicked.emit())
        menu.addAction(action_send_sorter)
        
        if item:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and "path" in data:
                path = data["path"]
                menu.addSeparator()
                
                action_open_dir = QAction("Открыть папку с файлом", self)
                action_open_dir.triggered.connect(lambda p=path: self.reveal_in_explorer(p))
                menu.addAction(action_open_dir)
                
                action_open_file = QAction("Открыть файл", self)
                action_open_file.triggered.connect(lambda p=path: self.open_file_default(p))
                menu.addAction(action_open_file)
                
        menu.exec(self.tree_results.viewport().mapToGlobal(pos))
        
    def reveal_in_explorer(self, path):
        import os
        from utils_common import reveal_in_explorer
        if os.path.exists(path):
            reveal_in_explorer(path)
            
    def open_file_default(self, path):
        import os
        if os.path.exists(path):
            os.startfile(path)

    def on_tree_selection_changed(self):
        self.update_action_bar_info()
        items = self.tree_results.selectedItems()
        if not items:
            self.preview_widget.show_empty("Выберите файл для предпросмотра" if AppContext.is_ru() else "Select a file for preview")
            self.file_selected.emit("")
            return
            
        item = items[0]
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and "path" in data:
            path = data["path"]
            self.preview_widget.load_file(path)
            # Draw bbox if exists
            bbox = data.get("bbox")
            if bbox is not None and hasattr(self.preview_widget, "draw_polygon"):
                self.preview_widget.draw_polygon(bbox)
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
        
        self.lbl_selection_info.setStyleSheet("color: #93c5fd; font-size: 11px; font-weight: bold;")
        self.lbl_selection_info.setText(f"Выбрано: {count} файлов • {size_str}" if AppContext.is_ru() else f"Selected: {count} files • {size_str}")
        
        has_selection = (count > 0)
        has_path = bool(self.action_bar.drop_zone.get_path())
        self.action_bar.set_delete_button_enabled(has_selection)
        self.action_bar.set_move_button_enabled(has_selection and has_path, move_to_enabled=has_selection)
        
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
                
        self.preview_widget.show_empty("Выберите файл для предпросмотра" if AppContext.is_ru() else "Select a file for preview")
        self.update_action_bar_info()

    def set_scan_enabled(self, enabled: bool):
        pass # UI state is handled internally for now
