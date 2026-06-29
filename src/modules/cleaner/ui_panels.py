
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, 
    QScrollArea, QCheckBox, QComboBox, QLineEdit, QGridLayout, QSizePolicy,
    QListView, QMenu, QSlider
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QEvent
from PyQt6.QtGui import QIcon, QPixmap, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer
from config import AppContext
from ui_widgets_base import DropZoneWidget, SizeFilterWidget
from utils_common import format_size
from .ui_widgets import SourceListItem, CleanSpinBox, ModeBadgeButton, CompactDropZone

def load_svg_pixmap(file_path: str, size: QSize, mirror_horizontal: bool = False) -> QPixmap:
    renderer = QSvgRenderer(file_path)
    if not renderer.isValid():
        return QPixmap()
    pixmap = QPixmap(size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    if mirror_horizontal:
        image = pixmap.toImage()
        mirrored_image = image.mirrored(True, False)
        pixmap = QPixmap.fromImage(mirrored_image)
    return pixmap

def load_svg_icon(file_path: str, size: QSize, mirror_horizontal: bool = False) -> QIcon:
    pixmap = load_svg_pixmap(file_path, size, mirror_horizontal)
    return QIcon(pixmap)

class CleanerSettingsPanel(QWidget):
    add_folder_clicked = pyqtSignal()
    folder_dropped = pyqtSignal(str)
    clear_folders_clicked = pyqtSignal()
    open_filter_clicked = pyqtSignal()
    start_scan_clicked = pyqtSignal()
    mode_duples_clicked = pyqtSignal()
    mode_zero_clicked = pyqtSignal()
    mode_empty_clicked = pyqtSignal()
    clear_cache_clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setStyleSheet("background-color: #1e1e1e;")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(15, 4, 15, 4)
        self.layout.setSpacing(12)
        
        # COL 1: Sources
        col_src = QVBoxLayout()
        col_src.setContentsMargins(0, 0, 0, 0)
        col_src.setSpacing(4)
        src_header = QHBoxLayout()
        src_header.setContentsMargins(0, 0, 0, 0)
        src_header.setSpacing(5)
        self.lbl_src_icon = QLabel()
        self.lbl_src_icon.setFixedSize(16, 16)
        self.lbl_src_icon.setStyleSheet("background: transparent; border: none;")
        self.lbl_src = QLabel()
        self.lbl_src.setStyleSheet("font-weight: bold; color: #888; font-size: 11px; font-family: 'Segoe UI'; padding: 2px 0px;")
        src_header.addWidget(self.lbl_src_icon)
        src_header.addWidget(self.lbl_src)
        src_header.addStretch()
        col_src.addLayout(src_header)
        
        self.sources_list_widget = QWidget()
        self.sources_list_widget.setStyleSheet("QWidget { background-color: #111111; }") 
        self.folder_list_layout = QVBoxLayout()
        self.folder_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        list_container_layout = QVBoxLayout(self.sources_list_widget)
        list_container_layout.setContentsMargins(0,0,0,0)
        list_container_layout.addLayout(self.folder_list_layout)
        list_container_layout.addStretch(1)
        
        self.drop_zone = DropZoneWidget()
        self.drop_zone.clicked.connect(self.add_folder_clicked.emit)
        self.drop_zone.folder_dropped.connect(self.folder_dropped.emit)
        self.drop_zone.clear_default_requested.connect(self.clear_folders_clicked.emit)
        self.drop_zone.btn_clear.show()
        self.drop_zone.setStyleSheet(self.drop_zone.styleSheet() + "margin: 10px;")
        
        # Warning Label
        self.lbl_warn = QLabel(AppContext.tr("cln_warn_system_folders"))
        self.lbl_warn.setWordWrap(True)
        self.lbl_warn.setStyleSheet("color: #777; font-size: 11px; margin: 0 15px 5px 15px; font-style: italic;")
        self.lbl_warn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        list_container_layout.addWidget(self.lbl_warn)
        
        list_container_layout.addWidget(self.drop_zone)
        
        scroll_src = QScrollArea()
        scroll_src.setWidgetResizable(True)
        scroll_src.setWidget(self.sources_list_widget)
        scroll_src.setStyleSheet("QScrollArea { background-color: #111; border: 1px solid #333; border-radius: 6px; }")
        
        col_src.addWidget(scroll_src, 1)
        self.layout.addLayout(col_src, stretch=4)
        
        # COL 2: Filters
        col_filters = QVBoxLayout()
        col_filters.setContentsMargins(0, 0, 0, 0)
        col_filters.setSpacing(4)
        algo_header = QHBoxLayout()
        algo_header.setContentsMargins(0, 0, 0, 0)
        algo_header.setSpacing(5)
        self.lbl_algo_icon = QLabel()
        self.lbl_algo_icon.setFixedSize(16, 16)
        self.lbl_algo_icon.setStyleSheet("background: transparent; border: none;")
        self.lbl_algo = QLabel()
        self.lbl_algo.setStyleSheet("font-weight: bold; color: #888; font-size: 11px; font-family: 'Segoe UI'; padding: 2px 0px;")
        algo_header.addWidget(self.lbl_algo_icon)
        algo_header.addWidget(self.lbl_algo)
        algo_header.addStretch()
        col_filters.addLayout(algo_header)
        
        algo_frame = QFrame()
        algo_frame.setObjectName("algo_frame")
        algo_frame.setStyleSheet("QFrame#algo_frame { background-color: #252526; border: 1px solid #3e3e42; border-radius: 4px; }")
        algo_layout = QVBoxLayout(algo_frame)
        algo_layout.setContentsMargins(6, 6, 6, 6)
        algo_layout.setSpacing(6)
        
        cache_layout = QHBoxLayout()
        cache_layout.setContentsMargins(0, 0, 0, 0)
        
        self.chk_cache = QCheckBox(AppContext.tr("cln_chk_cache"))
        self.chk_cache.setChecked(True) 
        self.chk_cache.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_cache.setStyleSheet("""
            QCheckBox { color: white; font-weight: bold; font-size: 13px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 3px; border: 1px solid #555; background: #111; }
            QCheckBox::indicator:checked { background-color: #3b82f6; border-color: #3b82f6; }
        """)
        cache_layout.addWidget(self.chk_cache)
        cache_layout.addStretch()
        
        self.lbl_cache_size = QLabel("0 B")
        self.lbl_cache_size.setStyleSheet("color: #888; font-size: 12px; margin-right: 5px;")
        cache_layout.addWidget(self.lbl_cache_size)
        
        self.btn_clear_cache = QPushButton("")
        self.btn_clear_cache.setIcon(load_svg_icon(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons", "trash-color.svg"), QSize(16, 16)))
        self.btn_clear_cache.setIconSize(QSize(16, 16))
        self.btn_clear_cache.setToolTip(AppContext.tr("cln_tip_clear_cache"))
        self.btn_clear_cache.setFixedSize(32, 32)
        self.btn_clear_cache.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_cache.setStyleSheet("""
            QPushButton { 
                background-color: transparent; 
                border: 1px solid #555; 
                border-radius: 16px; 
                padding: 0px;
            }
            QPushButton:hover { 
                background-color: #444; 
                border-color: #ef4444; 
            }
        """)
        self.btn_clear_cache.clicked.connect(self.clear_cache_clicked.emit)
        cache_layout.addWidget(self.btn_clear_cache)
        
        algo_layout.addLayout(cache_layout)

        self.chk_safe_scan = QCheckBox(AppContext.tr("cln_chk_safe_scan"))
        self.chk_safe_scan.setChecked(True)
        self.chk_safe_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_safe_scan.setToolTip(AppContext.tr("cln_tip_safe_scan"))
        self.chk_safe_scan.setStyleSheet(self.chk_cache.styleSheet())
        algo_layout.addWidget(self.chk_safe_scan)
        
        # Size Filters
        size_widget = QWidget()
        size_layout = QHBoxLayout(size_widget)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_layout.setSpacing(6)
        
        self.lbl_size = QLabel(AppContext.tr("cln_size_filter"))
        self.lbl_size.setStyleSheet("color: #ccc; font-size: 12px; font-weight: bold;")
        size_layout.addWidget(self.lbl_size)
        
        self.size_widget = SizeFilterWidget()
        self.size_widget.valueChanged.connect(self.validate_size_inputs)
        size_layout.addWidget(self.size_widget)
        size_layout.addStretch()
        
        algo_layout.addWidget(size_widget)
        
        self.lbl_shield = QLabel(AppContext.tr("cln_lbl_method_info"))
        self.lbl_shield.setStyleSheet("color: #ccc; font-size: 12px; line-height: 140%;")
        self.lbl_shield.setTextFormat(Qt.TextFormat.RichText)
        algo_layout.addWidget(self.lbl_shield)
        col_filters.addWidget(algo_frame)
        
        self.lbl_filter_status = QLabel(AppContext.tr("cln_filter_all"))
        self.lbl_filter_status.setStyleSheet("font-size: 12px; color: #ccc; margin-left: 2px; font-weight: bold; margin-top: 2px;")
        col_filters.addWidget(self.lbl_filter_status)
        col_filters.addStretch()

        self.btn_filter = QPushButton()
        self.btn_filter.setIcon(load_svg_icon(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons", "loupe-color.svg"), QSize(16, 16)))
        self.btn_filter.setIconSize(QSize(16, 16))
        self.btn_filter.setFixedHeight(36)
        self.btn_filter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_filter.setEnabled(False) # Блокируем при старте, пока нет папок-источников
        self.btn_filter.clicked.connect(self.open_filter_clicked.emit)
        self.btn_filter.setStyleSheet("QPushButton { background-color: #444; color: #fff; border: 1px solid #666; padding: 0 10px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #555; color: white; border-color: #888; }")
        col_filters.addWidget(self.btn_filter)
        self.layout.addLayout(col_filters, stretch=3)
        
        # COL 3: Progress
        self.col_prog = QVBoxLayout()
        self.col_prog.setContentsMargins(0, 0, 0, 0)
        self.col_prog.setSpacing(4)
        prog_header = QHBoxLayout()
        prog_header.setContentsMargins(0, 0, 0, 0)
        prog_header.setSpacing(5)
        self.lbl_prog_icon = QLabel()
        self.lbl_prog_icon.setFixedSize(16, 16)
        self.lbl_prog_icon.setStyleSheet("background: transparent; border: none;")
        self.lbl_prog_header = QLabel()
        self.lbl_prog_header.setStyleSheet("font-weight: bold; color: #888; font-size: 11px; font-family: 'Segoe UI'; padding: 2px 0px;")
        prog_header.addWidget(self.lbl_prog_icon)
        prog_header.addWidget(self.lbl_prog_header)
        prog_header.addStretch()
        self.col_prog.addLayout(prog_header)
        
        metrics_frame = QFrame()
        metrics_frame.setObjectName("metrics_frame")
        metrics_frame.setStyleSheet("QFrame#metrics_frame { background: #252526; border: 1px solid #333; border-radius: 4px; }")
        gl = QGridLayout(metrics_frame)
        gl.setSpacing(6)
        gl.setContentsMargins(8, 8, 8, 8)
        
        lbl_style = "color: #cccccc; font-size: 13px;"
        val_style = "color: #cccccc; font-weight: bold; font-size: 13px;"
        
        self.lbl_scanned = QLabel(AppContext.tr("cln_lbl_scanned")); self.lbl_scanned.setStyleSheet(lbl_style)
        self.val_scanned = QLabel("0"); self.val_scanned.setStyleSheet(val_style); self.val_scanned.setAlignment(Qt.AlignmentFlag.AlignRight)
        gl.addWidget(self.lbl_scanned, 0, 0); gl.addWidget(self.val_scanned, 0, 1)
        
        self.lbl_percent = QLabel(""); self.lbl_percent.hide()
        self.lbl_dup = QLabel(AppContext.tr("cln_lbl_duplicates")); self.lbl_dup.setStyleSheet(lbl_style)
        self.btn_duples = ModeBadgeButton("0"); self.btn_duples.set_mode('disabled')
        self.btn_duples.clicked.connect(self.mode_duples_clicked.emit)
        cont_dup = QWidget(); l_dup = QHBoxLayout(cont_dup); l_dup.setContentsMargins(0,0,0,0); l_dup.addStretch(); l_dup.addWidget(self.lbl_percent); l_dup.addWidget(self.btn_duples)
        gl.addWidget(self.lbl_dup, 1, 0); gl.addWidget(cont_dup, 1, 1)
        
        self.lbl_wasted = QLabel(AppContext.tr("cln_lbl_wasted")); self.lbl_wasted.setStyleSheet(lbl_style)
        self.val_wasted = QLabel("0 B"); self.val_wasted.setStyleSheet(val_style); self.val_wasted.setAlignment(Qt.AlignmentFlag.AlignRight)
        gl.addWidget(self.lbl_wasted, 2, 0); gl.addWidget(self.val_wasted, 2, 1)
        
        self.lbl_zero = QLabel(AppContext.tr("cln_lbl_zero_files")); self.lbl_zero.setStyleSheet(lbl_style)
        self.btn_zero = ModeBadgeButton("0"); self.btn_zero.set_mode('disabled'); self.btn_zero.clicked.connect(self.mode_zero_clicked.emit)
        cont_zero = QWidget(); l_zero = QHBoxLayout(cont_zero); l_zero.setContentsMargins(0,0,0,0); l_zero.addStretch(); l_zero.addWidget(self.btn_zero)
        gl.addWidget(self.lbl_zero, 3, 0); gl.addWidget(cont_zero, 3, 1)
        
        self.lbl_empty = QLabel(AppContext.tr("cln_lbl_empty_folders")); self.lbl_empty.setStyleSheet(lbl_style)
        self.btn_empty = ModeBadgeButton("0"); self.btn_empty.set_mode('disabled'); self.btn_empty.clicked.connect(self.mode_empty_clicked.emit)
        cont_empty = QWidget(); l_empty = QHBoxLayout(cont_empty); l_empty.setContentsMargins(0,0,0,0); l_empty.addStretch(); l_empty.addWidget(self.btn_empty)
        gl.addWidget(self.lbl_empty, 4, 0); gl.addWidget(cont_empty, 4, 1)
        
        self.val_curr_path = QLabel("...")
        self.val_curr_path.setStyleSheet("color: #888; font-style: italic; font-size: 12px;")
        self.val_curr_path.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.val_curr_path.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        gl.addWidget(self.val_curr_path, 5, 0, 1, 2)
        
        self.lbl_time = QLabel(AppContext.tr("cln_lbl_time")); self.lbl_time.setStyleSheet(lbl_style)
        self.val_time = QLabel("00:00.000"); self.val_time.setStyleSheet(val_style); self.val_time.setAlignment(Qt.AlignmentFlag.AlignRight)
        gl.addWidget(self.lbl_time, 6, 0); gl.addWidget(self.val_time, 6, 1)
        
        self.col_prog.addWidget(metrics_frame)
        self.col_prog.addStretch()
        
        self.btn_scan = QPushButton(" " + AppContext.tr("cln_btn_start"))
        self.btn_scan.setFixedHeight(36)
        self.btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_scan.clicked.connect(self.start_scan_clicked.emit)
        self.btn_scan.setProperty("has_folders", False)
        
        self.col_prog.addWidget(self.btn_scan)
        self.layout.addLayout(self.col_prog, stretch=3)
        
        self.scan_stale = False
        self.update_ui_text()
        self.validate_size_inputs()

    def update_ui_text(self):
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
        
        self.lbl_src_icon.setPixmap(load_svg_pixmap(os.path.join(icons_dir, "folder-color.svg"), QSize(16, 16)))
        self.lbl_algo_icon.setPixmap(load_svg_pixmap(os.path.join(icons_dir, "gear-color.svg"), QSize(16, 16)))
        self.lbl_prog_icon.setPixmap(load_svg_pixmap(os.path.join(icons_dir, "loupe-color.svg"), QSize(16, 16), mirror_horizontal=True))

        raw_title = AppContext.tr("cln_src_title")
        clean_title = raw_title.replace("1.", "").strip() if raw_title.startswith("1.") else raw_title
        self.lbl_src.setText(f"1. {clean_title}")
        
        self.drop_zone.update_ui_text()
        
        self.lbl_warn.setText(AppContext.tr("cln_warn_system_folders"))
        
        raw_algo = AppContext.tr("cln_algo_title")
        clean = raw_algo.replace("2.", "").strip() if raw_algo.startswith("2.") else raw_algo
        self.lbl_algo.setText(f"2. {clean}")

        self.chk_cache.setText(AppContext.tr("cln_chk_cache"))
        self.lbl_shield.setText(AppContext.tr("cln_lbl_method_info"))
        self.chk_safe_scan.setText(AppContext.tr("cln_chk_safe_scan"))
        self.chk_safe_scan.setToolTip(AppContext.tr("cln_tip_safe_scan"))
        self.btn_clear_cache.setToolTip(AppContext.tr("cln_tip_clear_cache"))
        self.btn_clear_cache.setIcon(load_svg_icon(os.path.join(icons_dir, "trash-color.svg"), QSize(16, 16)))
        self.btn_clear_cache.setIconSize(QSize(16, 16))
        
        self.btn_filter.setText(AppContext.tr("cln_btn_scan_types"))
        
        raw_prog = AppContext.tr("cln_prog_title")
        clean = raw_prog.replace("3.", "").strip() if raw_prog.startswith("3.") else raw_prog
        self.lbl_prog_header.setText(f"3. {clean}")

        self.lbl_scanned.setText(AppContext.tr("cln_lbl_scanned"))
        self.lbl_wasted.setText(AppContext.tr("cln_lbl_wasted"))
        self.lbl_time.setText(AppContext.tr("cln_lbl_time"))
        self.lbl_size.setText(AppContext.tr("cln_size_filter"))
        
        self.lbl_dup.setText(AppContext.tr("cln_lbl_duplicates"))
        self.lbl_zero.setText(AppContext.tr("cln_lbl_zero_files"))
        self.lbl_empty.setText(AppContext.tr("cln_lbl_empty_folders"))
        
        if hasattr(self, 'btn_abort') and self.btn_abort:
            self.btn_abort.setText(AppContext.tr("cln_btn_abort"))
            self.btn_abort.setToolTip(AppContext.tr("cln_tip_abort"))
        if hasattr(self, 'btn_stop_scan') and self.btn_stop_scan:
            self.btn_stop_scan.setText(AppContext.tr("cln_btn_reset"))
            self.btn_stop_scan.setToolTip(AppContext.tr("cln_tip_reset"))

        # NOTE: btn_scan text update is handled in CleanerModule to respect scanning state.

    def validate_size_inputs(self):
        is_error = self.size_widget.has_error()
        
        has_folders = self.btn_scan.property("has_folders")
        should_enable = has_folders and not is_error
        self.btn_scan.setEnabled(should_enable)
        
        if should_enable:
            if getattr(self, 'scan_stale', False):
                self.btn_scan.setStyleSheet("""
                    QPushButton { background-color: #ea580c; color: white; font-weight: 900; font-size: 14px; border: 1px solid #f97316; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
                    QPushButton:hover { background-color: #f97316; }
                """)
            else:
                self.btn_scan.setStyleSheet("""
                    QPushButton { background-color: #15803d; color: white; font-weight: 900; font-size: 14px; border: 1px solid #16a34a; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
                    QPushButton:hover { background-color: #16a34a; }
                """)
        else:
            self.btn_scan.setStyleSheet("""
                QPushButton { background-color: #222; color: #555; font-weight: 900; font-size: 14px; border: 1px solid #333; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
            """)

    def get_size_limits(self):
        return self.size_widget.get_min_bytes(), self.size_widget.get_max_bytes()

    def set_scan_enabled(self, enabled):
        self.btn_scan.setProperty("has_folders", enabled)
        self.validate_size_inputs()

    def set_current_path(self, path: str) -> None:
        if not path:
            self.val_curr_path.setText("...")
            self.val_curr_path.setToolTip("")
            return
            
        # Проверяем, является ли строка путем к файлу (содержит разделители пути)
        is_path = '/' in path or '\\' in path
        
        if not is_path:
            # Если это служебное сообщение (например, "Найдено совпадение", "Хеширование..." и т.д.),
            # мы НЕ затираем текущий отображаемый путь, если он уже установлен.
            if self.val_curr_path.text() != "...":
                return
            else:
                self.val_curr_path.setText("...")
                self.val_curr_path.setToolTip("")
                return
        
        path_clean = path.replace('\\', '/')
        if len(path_clean) > 42:
            shrunk = path_clean[:12] + "..." + path_clean[-27:]
        else:
            shrunk = path_clean
            
        self.val_curr_path.setText(shrunk)
        self.val_curr_path.setToolTip(AppContext.tr("cln_tip_curr_scanning").format(path))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
        else: event.ignore()

    def update_cache_info(self, size_str):
        self.lbl_cache_size.setText(size_str)
        self.btn_clear_cache.setEnabled(size_str != "0 B")

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            for url in urls:
                path = url.toLocalFile()
                if os.path.isdir(path): self.folder_dropped.emit(path)
            event.acceptProposedAction()
        else: event.ignore()
    
    def refresh_list_alignment(self):
        layout = self.folder_list_layout
        count = layout.count()
        if count == 0: return
        max_w = 0
        items = []
        for i in range(count):
            item = layout.itemAt(i)
            w = item.widget()
            if w and hasattr(w, 'get_ideal_name_width'):
                items.append(w)
                max_w = max(max_w, w.get_ideal_name_width())
        container_w = self.sources_list_widget.width()
        if container_w <= 0: container_w = 400
        limit = int(container_w * 0.5)
        target_w = min(max_w, limit)
        for w in items: w.set_name_label_width(target_w)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh_list_alignment()

    def setup_scan_buttons(self, on_abort_click, on_stop_click) -> None:
        self.btn_scan.hide()
        
        if not hasattr(self, 'scan_buttons_widget'):
            self.scan_buttons_widget = QWidget()
            layout = QHBoxLayout(self.scan_buttons_widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(10)
            
            self.btn_abort = QPushButton(AppContext.tr("cln_btn_abort"))
            self.btn_abort.setFixedHeight(36)
            self.btn_abort.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_abort.setToolTip(AppContext.tr("cln_tip_abort"))
            self.btn_abort.setStyleSheet("""
                QPushButton { background-color: #c2410c; color: white; font-weight: 900; font-size: 14px; border: 1px solid #9a3412; border-radius: 6px; font-family: 'Segoe UI'; padding: 4px; }
                QPushButton:hover { background-color: #ea580c; }
                QPushButton:disabled { background-color: #222; color: #555; border-color: #333; }
            """)
            self.btn_abort.clicked.connect(on_abort_click)
            
            self.btn_stop_scan = QPushButton(AppContext.tr("cln_btn_reset"))
            self.btn_stop_scan.setFixedHeight(36)
            self.btn_stop_scan.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_stop_scan.setToolTip(AppContext.tr("cln_tip_reset"))
            self.btn_stop_scan.setStyleSheet("""
                QPushButton { background-color: #991b1b; color: white; font-weight: 900; font-size: 14px; border: 1px solid #7f1d1d; border-radius: 6px; font-family: 'Segoe UI'; padding: 4px; }
                QPushButton:hover { background-color: #b91c1c; }
                QPushButton:disabled { background-color: #222; color: #555; border-color: #333; }
            """)
            self.btn_stop_scan.clicked.connect(on_stop_click)
            
            layout.addWidget(self.btn_abort, 1)
            layout.addWidget(self.btn_stop_scan, 1)
            
            self.col_prog.addWidget(self.scan_buttons_widget)
        
        self.btn_abort.setEnabled(True)
        self.btn_abort.setText(AppContext.tr("cln_btn_abort"))
        self.btn_abort.setToolTip(AppContext.tr("cln_tip_abort"))
        self.btn_stop_scan.setEnabled(True)
        self.btn_stop_scan.setText(AppContext.tr("cln_btn_reset"))
        self.btn_stop_scan.setToolTip(AppContext.tr("cln_tip_reset"))
        self.scan_buttons_widget.show()

    def restore_scan_buttons(self) -> None:
        if hasattr(self, 'scan_buttons_widget'):
            self.scan_buttons_widget.hide()
        self.btn_scan.show()

class CollisionComboBox(QComboBox):
    def showPopup(self):
        view = self.view()
        # Принудительно применяем QSS для точного расчета высоты элементов
        view.style().polish(view)
        
        # Рассчитываем необходимую высоту под 3 пункта
        count = self.count()
        total_h = 0
        for i in range(count):
            h = view.sizeHintForRow(i)
            if h <= 0:
                h = 24
            total_h += h
        total_h += 4  # Отступы рамок
        
        # Задаем высоту представления до показа popup
        view.setMinimumHeight(total_h)
        view.setMaximumHeight(total_h)
        
        # Блокируем прокрутку
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Показываем popup уже правильного размера
        super().showPopup()

class CleanerActionBar(QFrame):
    autoselect_changed = pyqtSignal(int)
    deselect_clicked = pyqtSignal()
    select_all_clicked = pyqtSignal()
    move_clicked = pyqtSignal()
    move_to_clicked = pyqtSignal()
    browse_clicked = pyqtSignal()
    delete_clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup_configured = False
        self._collision_popup_configured = False
        self.setFixedHeight(48) 
        self.setStyleSheet("background-color: #262626; border-bottom: 1px solid #444; border-top: 1px solid #333;")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 15, 0)
        layout.setSpacing(10)
        
        self.combo_autoselect = QComboBox()
        view = QListView(self.combo_autoselect)
        view.setFrameShape(QFrame.Shape.NoFrame) 
        self.combo_autoselect.setView(view)
        self.combo_autoselect.view().installEventFilter(self)
        
        self.update_autoselect_items()
        self.combo_autoselect.currentIndexChanged.connect(self.autoselect_changed.emit)
        self.combo_autoselect.setFixedWidth(240) 
        
        self.combo_autoselect.setStyleSheet("""
            QComboBox { background: #333; color: white; border: 1px solid #555; padding: 4px; border-radius: 4px; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { border: 0px solid transparent; background-color: #333; color: white; outline: none; padding: 0px; margin: 0px; }
            QComboBox QAbstractItemView::item { padding: 2px 5px; border: none; background-color: #333; }
            QComboBox QAbstractItemView::item:hover { background-color: #444; }
            QComboBox QAbstractItemView::item:selected { background-color: #3b82f6; }
            QComboBox QAbstractItemView::item:disabled { background: transparent; border-bottom: 1px solid #777; margin-bottom: 4px; margin-top: 4px; padding: 0px; min-height: 0px; }
        """)
        
        self.btn_select_all = QPushButton(AppContext.tr("cln_ctx_select_all"))
        self.btn_select_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_select_all.clicked.connect(self.select_all_clicked.emit)
        self.btn_select_all.setStyleSheet("QPushButton { background: #333; color: #ddd; border: 1px solid #555; padding: 5px 10px; border-radius: 4px; } QPushButton:hover { background-color: #444; border-color: #666; }")
        
        self.btn_deselect = QPushButton()
        self.btn_deselect.setFixedSize(30, 30)
        self.btn_deselect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_deselect.clicked.connect(self.deselect_clicked.emit)
        
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
        self.icon_desel_gray = os.path.join(icons_dir, "checkbox_unchecked-gray.svg").replace("\\", "/")
        self.icon_desel_white = os.path.join(icons_dir, "checkbox_unchecked.svg").replace("\\", "/")
        
        self.btn_deselect.setIconSize(QSize(16, 16))
        
        layout.addWidget(self.combo_autoselect)
        layout.addWidget(self.btn_select_all)
        layout.addWidget(self.btn_deselect)
        layout.addStretch() 
        
        self.chk_preserve = QCheckBox(AppContext.tr("cln_chk_struct"))
        self.chk_preserve.setChecked(True)
        self.chk_preserve.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_preserve.setStyleSheet("QCheckBox { color: #e0e0e0; font-weight: bold; font-size: 12px; background-color: transparent; border: none; spacing: 8px; } QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #666; background-color: #222; border-radius: 3px; } QCheckBox::indicator:checked { background-color: #3b82f6; border-color: #3b82f6; }")
        layout.addWidget(self.chk_preserve)
        
        self.combo_collision = CollisionComboBox()
        view_col = QListView(self.combo_collision)
        view_col.setFrameShape(QFrame.Shape.NoFrame)
        self.combo_collision.setView(view_col)
        self.combo_collision.view().installEventFilter(self)
        self.combo_collision.view().setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.combo_collision.view().setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.update_collision_items()
        self.combo_collision.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.combo_collision.setMinimumWidth(150)
        self.combo_collision.setCurrentIndex(0) 
        self.combo_collision.setStyleSheet("""
            QComboBox { background: #333; color: white; border: 1px solid #555; padding: 4px; border-radius: 4px; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { border: 0px solid transparent; background-color: #333; color: white; outline: none; padding: 0px; margin: 0px; }
            QComboBox QAbstractItemView::item { padding: 2px 6px; border: none; background-color: #333; }
            QComboBox QAbstractItemView::item:hover { background-color: #444; }
            QComboBox QAbstractItemView::item:selected { background-color: #3b82f6; }
        """)
        layout.addWidget(self.combo_collision)
        
        self.btn_delete = QPushButton("Удалить" if AppContext.LANG == "RU" else "Delete")
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
        self.btn_delete.setIcon(load_svg_icon(os.path.join(icons_dir, "trash-color.svg"), QSize(16, 16)))
        self.btn_delete.setIconSize(QSize(16, 16))
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_delete_button_enabled(False)
        self.btn_delete.clicked.connect(self.delete_clicked.emit)
        layout.addWidget(self.btn_delete)

        self.btn_move = QPushButton(AppContext.tr("cln_btn_move_icon") + " ")
        self.btn_move.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_move_button_enabled(False)
        self.btn_move.clicked.connect(self.move_clicked.emit)
        layout.addWidget(self.btn_move)
        
        self.btn_move_to = QPushButton("Переместить в..." if AppContext.LANG == "RU" else "Move to...")
        self.btn_move_to.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_move_to.setEnabled(False)
        self.btn_move_to.setStyleSheet("""
            QPushButton { background: #333; color: #ddd; border: 1px solid #555; padding: 5px 10px; border-radius: 4px; }
            QPushButton:hover { background-color: #444; border-color: #666; }
            QPushButton:disabled { color: #555; background: #2a2a2a; border-color: #333; }
        """)
        self.btn_move_to.clicked.connect(self.move_to_clicked.emit)
        layout.addWidget(self.btn_move_to)
        
        self.drop_zone = CompactDropZone()
        self.drop_zone.setFixedWidth(280) 
        self.drop_zone.clicked.connect(self.browse_clicked.emit) 
        layout.addWidget(self.drop_zone)
        
        self.set_deselect_button_enabled(False)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show:
            if obj == self.combo_autoselect.view() and not self._popup_configured:
                popup = self.combo_autoselect.view().window()
                if popup:
                    self._popup_configured = True
                    popup.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
                    popup.setStyleSheet("background-color: #333; border: 1px solid #555; border-radius: 4px;")
                    popup.show()
            elif obj == self.combo_collision.view():
                # Принудительно отключаем прокрутку при каждом показе
                self.combo_collision.view().setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                self.combo_collision.view().setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                if not self._collision_popup_configured:
                    popup = self.combo_collision.view().window()
                    if popup:
                        self._collision_popup_configured = True
                        popup.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
                        popup.setStyleSheet("background-color: #333; border: 1px solid #555; border-radius: 4px;")
                        # Повторно отключаем прокрутку у нового пересозданного окна
                        self.combo_collision.view().setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                        self.combo_collision.view().setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                        popup.show()
        return super().eventFilter(obj, event)

    def set_move_button_enabled(self, enabled, text=None):
        self.btn_move.setEnabled(enabled)
        self.btn_move_to.setEnabled(enabled)
        if text: self.btn_move.setText(text)
        else: self.btn_move.setText(AppContext.tr("cln_btn_move_icon") + " ")
        
        current_text = self.btn_move.text().upper()
        if "УДАЛИТЬ" in current_text or "DELETE" in current_text:
            icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
            self.btn_move.setIcon(load_svg_icon(os.path.join(icons_dir, "trash-color.svg"), QSize(16, 16)))
            self.btn_move.setIconSize(QSize(16, 16))
        else:
            self.btn_move.setIcon(QIcon())
            
        if enabled:
            if "УДАЛИТЬ" in current_text or "DELETE" in current_text:
                self.btn_move.setStyleSheet("QPushButton { background-color: #dc2626; color: white; font-weight: bold; padding: 5px 10px; border-radius: 4px; border: 1px solid #b91c1c; font-size: 12px; } QPushButton:hover { background-color: #ef4444; }")
            else:
                self.btn_move.setStyleSheet("QPushButton { background-color: #3b82f6; color: white; font-weight: bold; padding: 5px 10px; border-radius: 4px; border: 1px solid #2563eb; font-size: 12px; } QPushButton:hover { background-color: #2563eb; }")
        else:
            self.btn_move.setStyleSheet("QPushButton { background-color: #333; color: #777; font-weight: bold; padding: 5px 10px; border-radius: 4px; border: 1px solid #444; font-size: 12px; }")

    def set_delete_button_enabled(self, enabled, text=None):
        self.btn_delete.setEnabled(enabled)
        if text: self.btn_delete.setText(text.replace("🗑", "").strip())
        else: self.btn_delete.setText(AppContext.tr("btn_delete_simple") if AppContext.tr("btn_delete_simple") else ("Удалить" if AppContext.LANG == "RU" else "Delete"))
            
        if enabled:
            self.btn_delete.setStyleSheet("QPushButton { background-color: #dc2626; color: white; font-weight: bold; padding: 5px 10px; border-radius: 4px; border: 1px solid #b91c1c; font-size: 12px; } QPushButton:hover { background-color: #ef4444; }")
        else:
            self.btn_delete.setStyleSheet("QPushButton { background-color: #333; color: #777; font-weight: bold; padding: 5px 10px; border-radius: 4px; border: 1px solid #444; font-size: 12px; }")

    def set_deselect_button_enabled(self, enabled: bool) -> None:
        self.btn_deselect.setEnabled(enabled)
        if enabled:
            self.btn_deselect.setStyleSheet(f"""
                QPushButton {{ 
                    background: #333; 
                    border: 1px solid #555; 
                    border-radius: 4px; 
                    qproperty-icon: url("{self.icon_desel_gray}");
                }} 
                QPushButton:hover {{ 
                    background-color: #444; 
                    border-color: #3b82f6; 
                    qproperty-icon: url("{self.icon_desel_white}");
                }}
            """)
        else:
            self.btn_deselect.setStyleSheet(f"""
                QPushButton {{ 
                    background: #2b2b2b; 
                    border: 1px solid #3d3d3d; 
                    border-radius: 4px; 
                    qproperty-icon: url("{self.icon_desel_gray}");
                }}
            """)

    def update_autoselect_items(self):
        self.combo_autoselect.clear()
        def add_item(text, tooltip, index_val):
            self.combo_autoselect.addItem(text, index_val)
            self.combo_autoselect.setItemData(self.combo_autoselect.count() - 1, tooltip, Qt.ItemDataRole.ToolTipRole)
        def add_sep():
            self.combo_autoselect.addItem("", "separator")
            idx = self.combo_autoselect.count() - 1
            self.combo_autoselect.model().item(idx).setEnabled(False)
            self.combo_autoselect.setItemData(idx, QSize(0, 9), Qt.ItemDataRole.SizeHintRole)

        is_similar = getattr(self, 'is_similar_mode', False)
        is_ru = (AppContext.LANG == "RU")

        if is_similar:
            add_item("Автовыбор" if is_ru else "Autoselect", "Выберите условие автоматического выделения" if is_ru else "Choose autoselect condition", 0)
            add_sep()
            add_item("Оставить с наибольшим качеством (весом)" if is_ru else "Keep highest quality (size)", 
                     "Выделить все файлы в группе, кроме файла с наибольшим размером" if is_ru else "Mark all files except the one with largest size", 2)
            add_item("Оставить с наименьшим качеством (весом)" if is_ru else "Keep lowest quality (size)", 
                     "Выделить все файлы в группе, кроме файла с наименьшим размером" if is_ru else "Mark all files except the one with smallest size", 3)
            add_sep()
            add_item("Оставить самый новый" if is_ru else "Keep newest", 
                     "Выделить все файлы в группе, кроме самого свежего по дате" if is_ru else "Mark all files except the newest one", 8)
            add_item("Оставить самый старый" if is_ru else "Keep oldest", 
                     "Выделить все файлы в группе, кроме самого старого по дате" if is_ru else "Mark all files except the oldest one", 9)
        else:
            add_item(AppContext.tr("cln_sel_auto"), AppContext.tr("cln_sel_tip_none"), 0)
            add_sep()
            add_item(AppContext.tr("cln_sel_all_except_first"), AppContext.tr("cln_sel_tip_except_first"), 2)
            add_item(AppContext.tr("cln_sel_all_except_last"), AppContext.tr("cln_sel_tip_except_last"), 3)
            add_sep()
            add_item(AppContext.tr("cln_sel_shortest"), AppContext.tr("cln_sel_tip_shortest"), 5)
            add_item(AppContext.tr("cln_sel_longest"), AppContext.tr("cln_sel_tip_longest"), 6)
            add_sep()
            add_item(AppContext.tr("cln_sel_newest"), AppContext.tr("cln_sel_tip_newest"), 8)
            add_item(AppContext.tr("cln_sel_oldest"), AppContext.tr("cln_sel_tip_oldest"), 9)
            add_sep()
            add_item(AppContext.tr("cln_sel_shallow"), AppContext.tr("cln_sel_tip_shallow"), 11)
            add_item(AppContext.tr("cln_sel_deep"), AppContext.tr("cln_sel_tip_deep"), 12)
            add_sep()
            add_item(AppContext.tr("cln_sel_protected_dupes"), AppContext.tr("cln_sel_tip_protected_dupes"), 14)
            add_item(AppContext.tr("cln_sel_reference_dupes"), AppContext.tr("cln_sel_tip_reference_dupes"), 15)

    def update_collision_items(self):
        current_idx = self.combo_collision.currentIndex()
        self.combo_collision.clear()
        
        # New simplified logic
        items = [
            (AppContext.tr("cln_col_inc"), AppContext.tr("cln_col_inc_tip")), # 0
            (AppContext.tr("cln_col_mark"), AppContext.tr("cln_col_mark_tip")), # 1 (Mark Duple)
            (AppContext.tr("cln_col_hex"), AppContext.tr("cln_col_hex_tip")) # 2
        ]
        
        for i, (text, tooltip) in enumerate(items):
            self.combo_collision.addItem(text)
            self.combo_collision.setItemData(i, tooltip, Qt.ItemDataRole.ToolTipRole)
            
        if current_idx >= 0 and current_idx < len(items):
            self.combo_collision.setCurrentIndex(current_idx)
        else:
            self.combo_collision.setCurrentIndex(0)

    def update_ui_text(self):
        self.btn_deselect.setToolTip(AppContext.tr("cln_btn_deselect"))
        self.btn_select_all.setText(AppContext.tr("cln_ctx_select_all"))
        self.chk_preserve.setText(AppContext.tr("cln_chk_struct"))
        self.chk_preserve.setToolTip(AppContext.tr("cln_chk_struct_tip"))
        self.drop_zone.default_text = AppContext.tr("cln_ph_dest")
        if not self.drop_zone.get_path(): self.drop_zone.clear_path()
        if not self.btn_delete.isEnabled():
            self.btn_delete.setText("Удалить" if AppContext.LANG == "RU" else "Delete")
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
        self.btn_delete.setIcon(load_svg_icon(os.path.join(icons_dir, "trash-color.svg"), QSize(16, 16)))
        self.btn_delete.setIconSize(QSize(16, 16))
        self.update_autoselect_items()
        self.update_collision_items()

from PyQt6.QtWidgets import QToolTip

class ToolTipLabel(QLabel):
    def enterEvent(self, event):
        QToolTip.showText(event.globalPosition().toPoint(), self.toolTip(), self)
        super().enterEvent(event)

class SimilarSettingsPanel(QWidget):
    add_folder_clicked = pyqtSignal()
    folder_dropped = pyqtSignal(str)
    clear_folders_clicked = pyqtSignal()
    open_filter_clicked = pyqtSignal()
    start_scan_clicked = pyqtSignal()
    clear_cache_clicked = pyqtSignal()
    settings_changed_for_rescan = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setStyleSheet("background-color: #1e1e1e;")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(15, 4, 15, 4)
        self.layout.setSpacing(12)
        
        is_ru = (AppContext.LANG == "RU")
        
        # COL 1: Sources
        col_src = QVBoxLayout()
        col_src.setContentsMargins(0, 0, 0, 0)
        col_src.setSpacing(4)
        src_header = QHBoxLayout()
        src_header.setContentsMargins(0, 0, 0, 0)
        src_header.setSpacing(5)
        self.lbl_src_icon = QLabel()
        self.lbl_src_icon.setFixedSize(16, 16)
        self.lbl_src_icon.setStyleSheet("background: transparent; border: none;")
        self.lbl_src = QLabel()
        self.lbl_src.setStyleSheet("font-weight: bold; color: #888; font-size: 11px; font-family: 'Segoe UI'; padding: 2px 0px;")
        src_header.addWidget(self.lbl_src_icon)
        src_header.addWidget(self.lbl_src)
        src_header.addStretch()
        col_src.addLayout(src_header)
        
        self.sources_list_widget = QWidget()
        self.sources_list_widget.setStyleSheet("QWidget { background-color: #111111; }") 
        self.folder_list_layout = QVBoxLayout()
        self.folder_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        list_container_layout = QVBoxLayout(self.sources_list_widget)
        list_container_layout.setContentsMargins(0,0,0,0)
        list_container_layout.addLayout(self.folder_list_layout)
        list_container_layout.addStretch(1)
        
        self.drop_zone = DropZoneWidget()
        self.drop_zone.clicked.connect(self.add_folder_clicked.emit)
        self.drop_zone.folder_dropped.connect(self.folder_dropped.emit)
        self.drop_zone.clear_default_requested.connect(self.clear_folders_clicked.emit)
        self.drop_zone.btn_clear.show()
        self.drop_zone.setStyleSheet(self.drop_zone.styleSheet() + "margin: 10px;")
        
        # Warning Label
        self.lbl_warn = QLabel(AppContext.tr("cln_warn_system_folders"))
        self.lbl_warn.setWordWrap(True)
        self.lbl_warn.setStyleSheet("color: #777; font-size: 11px; margin: 0 15px 5px 15px; font-style: italic;")
        self.lbl_warn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        list_container_layout.addWidget(self.lbl_warn)
        list_container_layout.addWidget(self.drop_zone)
        
        scroll_src = QScrollArea()
        scroll_src.setWidgetResizable(True)
        scroll_src.setWidget(self.sources_list_widget)
        scroll_src.setStyleSheet("QScrollArea { background-color: #111; border: 1px solid #333; border-radius: 6px; }")
        
        col_src.addWidget(scroll_src, 1)
        self.layout.addLayout(col_src, stretch=4)
        
        # COL 2: Filters
        col_filters = QVBoxLayout()
        col_filters.setContentsMargins(0, 0, 0, 0)
        col_filters.setSpacing(4)
        algo_header = QHBoxLayout()
        algo_header.setContentsMargins(0, 0, 0, 0)
        algo_header.setSpacing(5)
        self.lbl_algo_icon = QLabel()
        self.lbl_algo_icon.setFixedSize(16, 16)
        self.lbl_algo_icon.setStyleSheet("background: transparent; border: none;")
        self.lbl_algo = QLabel()
        self.lbl_algo.setStyleSheet("font-weight: bold; color: #888; font-size: 11px; font-family: 'Segoe UI'; padding: 2px 0px;")
        algo_header.addWidget(self.lbl_algo_icon)
        algo_header.addWidget(self.lbl_algo)
        algo_header.addStretch()
        col_filters.addLayout(algo_header)
        
        algo_frame = QFrame()
        algo_frame.setObjectName("algo_frame")
        algo_frame.setStyleSheet("QFrame#algo_frame { background-color: #252526; border: 1px solid #3e3e42; border-radius: 4px; }")
        algo_layout = QVBoxLayout(algo_frame)
        algo_layout.setContentsMargins(6, 6, 6, 6)
        algo_layout.setSpacing(6)
        
        # Cache line
        cache_layout = QHBoxLayout()
        cache_layout.setContentsMargins(0, 0, 0, 0)
        self.chk_cache = QCheckBox(AppContext.tr("cln_chk_cache"))
        self.chk_cache.setChecked(True) 
        self.chk_cache.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_cache.setStyleSheet("""
            QCheckBox { color: white; font-weight: bold; font-size: 13px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 3px; border: 1px solid #555; background: #111; }
            QCheckBox::indicator:checked { background-color: #3b82f6; border-color: #3b82f6; }
        """)
        cache_layout.addWidget(self.chk_cache)
        cache_layout.addStretch()
        
        self.lbl_cache_size = QLabel("0 B")
        self.lbl_cache_size.setStyleSheet("color: #888; font-size: 12px; margin-right: 5px;")
        cache_layout.addWidget(self.lbl_cache_size)
        
        self.btn_clear_cache = QPushButton("")
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
        self.btn_clear_cache.setIcon(load_svg_icon(os.path.join(icons_dir, "trash-color.svg"), QSize(16, 16)))
        self.btn_clear_cache.setIconSize(QSize(16, 16))
        self.btn_clear_cache.setToolTip(AppContext.tr("cln_tip_clear_cache"))
        self.btn_clear_cache.setFixedSize(32, 32)
        self.btn_clear_cache.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_cache.setStyleSheet("""
            QPushButton { background-color: transparent; border: 1px solid #555; border-radius: 16px; padding: 0px; }
            QPushButton:hover { background-color: #444; border-color: #ef4444; }
        """)
        self.btn_clear_cache.clicked.connect(self.clear_cache_clicked.emit)
        cache_layout.addWidget(self.btn_clear_cache)
        algo_layout.addLayout(cache_layout)
        
        # Media Type Selection Line
        media_layout = QHBoxLayout()
        media_layout.setContentsMargins(0, 0, 0, 0)
        media_layout.setSpacing(6)
        
        self.lbl_media_type = QLabel("Анализ:" if is_ru else "Analysis:")
        self.lbl_media_type.setStyleSheet("color: white; font-weight: bold; font-size: 13px;")
        media_layout.addWidget(self.lbl_media_type)
        
        self.combo_media_type = QComboBox()
        self.combo_media_type.addItems(["Изображения", "Аудио", "Видео"] if is_ru else ["Images", "Audio", "Video"])
        
        from logic_paths import get_fpcalc_exe, get_ffmpeg_exe
        
        has_audio = os.path.exists(get_fpcalc_exe())
        has_video = os.path.exists(get_ffmpeg_exe())
        model = self.combo_media_type.model()
        
        if not has_audio:
            item = model.item(1)
            if item:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                item.setToolTip("Требуется fpcalc.exe в папке src/bin/" if is_ru else "fpcalc.exe is required in src/bin/")
                
        if not has_video:
            item = model.item(2)
            if item:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                item.setToolTip("Требуется ffmpeg.exe в системе" if is_ru else "ffmpeg.exe is required")
                
        self.combo_media_type.setFixedHeight(24)
        self.combo_media_type.setFixedWidth(135)
        self.combo_media_type.setStyleSheet("""
            QComboBox { background-color: #333; color: white; border: 1px solid #555; border-radius: 4px; padding-left: 5px; font-weight: bold; }
            QComboBox QAbstractItemView { background-color: #222; color: white; selection-background-color: #3b82f6; }
        """)
        media_layout.addWidget(self.combo_media_type)
        
        self.lbl_resolution = QLabel("Точность:" if is_ru else "Depth:")
        self.lbl_resolution.setStyleSheet("color: white; font-weight: bold; font-size: 13px; margin-left: 10px;")
        media_layout.addWidget(self.lbl_resolution)
        
        self.combo_resolution = QComboBox()
        self.combo_resolution.addItems(["3x3", "8x8", "16x16", "32x32", "64x64"])
        self.combo_resolution.setCurrentIndex(1) # 8x8 by default (теперь это индекс 1)
        self.combo_resolution.setFixedHeight(24)
        self.combo_resolution.setFixedWidth(70)
        self.combo_resolution.setStyleSheet(self.combo_media_type.styleSheet())
        media_layout.addWidget(self.combo_resolution)
        
        # Info icon
        self.lbl_info_icon = ToolTipLabel("?")
        self.lbl_info_icon.setFixedSize(18, 18)
        self.lbl_info_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_info_icon.setStyleSheet("""
            QLabel { background-color: #3b82f6; color: white; border-radius: 4px; font-weight: bold; font-size: 13px; font-family: 'Segoe UI', Arial; margin-left: 5px; }
            QLabel:hover { background-color: #2563eb; }
        """)
        self.lbl_info_icon.setToolTip(
            "<b>Точность (Глубина):</b><br>"
            "3x3 — Сверхбыстро (только общие очертания).<br>"
            "8x8 — Очень быстро, грубый поиск (64 бит).<br>"
            "16x16 — Баланс, стандарт (256 бит).<br>"
            "32x32 — Высокая детализация (1024 бит).<br>"
            "64x64 — Экстремальная точность (4096 бит).<br><br>"
            "<i>Примечание: Данная настройка влияет на Изображения и Видео (анализ кадров). Для Аудио применяется универсальный акустический слепок.</i>"
        )
        media_layout.addWidget(self.lbl_info_icon)
        media_layout.addStretch()
        algo_layout.addLayout(media_layout)
        
        # Range and Details Line
        range_layout = QHBoxLayout()
        range_layout.setContentsMargins(0, 0, 0, 0)
        range_layout.setSpacing(6)
        
        self.lbl_range = QLabel("Диапазон:" if is_ru else "Range:")
        self.lbl_range.setStyleSheet("color: white; font-weight: bold; font-size: 13px;")
        range_layout.addWidget(self.lbl_range)
        
        self.combo_range = QComboBox()
        self.combo_range.addItems(["5%", "10%", "20%", "30%", "100%"])
        self.combo_range.setCurrentIndex(0) # 5%
        self.combo_range.setFixedHeight(24)
        self.combo_range.setFixedWidth(70)
        self.combo_range.setStyleSheet(self.combo_media_type.styleSheet())
        range_layout.addWidget(self.combo_range)
        range_layout.addStretch()
        algo_layout.addLayout(range_layout)
        
        # Wide Slider Line
        slider_layout = QHBoxLayout()
        slider_layout.setContentsMargins(0, 0, 0, 0)
        slider_layout.setSpacing(6)
        
        self.slider_similarity = QSlider(Qt.Orientation.Horizontal)
        self.slider_similarity.setRange(0, 500) # 0 to 500 mapped dynamically
        self.slider_similarity.setValue(250) # default 95% + 2.5% = 97.5%
        self.slider_similarity.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider_similarity.setStyleSheet("""
            QSlider::groove:horizontal { border: 1px solid #444; height: 6px; background: #222; border-radius: 3px; }
            QSlider::sub-page:horizontal { background: #3b82f6; border-radius: 3px; }
            QSlider::handle:horizontal { background: #bbb; width: 14px; height: 14px; margin: -4px 0; border-radius: 7px; }
            QSlider::handle:horizontal:hover { background: white; }
        """)
        slider_layout.addWidget(self.slider_similarity)
        
        # Custom SpinBox block for Similarity
        UP_BASE64 = b'PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiNmZmZmZmYiIHN0cm9rZS13aWR0aD0iMyIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cGF0aCBkPSJtMTggMTUtNi02LTYgNiIvPjwvc3ZnPg=='
        DOWN_BASE64 = b'PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiNmZmZmZmYiIHN0cm9rZS13aWR0aD0iMyIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cGF0aCBkPSJtNiA5IDYgNiA2LTYiLz48L3N2Zz4='
        import base64
        from PyQt6.QtGui import QPixmap, QIcon
        def get_svg_icon(svg_b64):
            pix = QPixmap()
            pix.loadFromData(base64.b64decode(svg_b64))
            return QIcon(pix)
            
        spin_container = QFrame()
        spin_container.setFixedHeight(26)
        spin_container.setFixedWidth(84)
        spin_container.setStyleSheet("QFrame { background-color: #333; border: 1px solid #555; border-radius: 4px; }")
        sc_layout = QHBoxLayout(spin_container)
        sc_layout.setContentsMargins(0, 0, 0, 0)
        sc_layout.setSpacing(0)
        
        arrows_w = QWidget()
        arrows_w.setFixedWidth(20)
        arrows_w.setFixedHeight(24)
        al = QVBoxLayout(arrows_w)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(0)
        
        self.btn_up_sim = QPushButton()
        self.btn_up_sim.setFixedHeight(12)
        self.btn_up_sim.setIcon(get_svg_icon(UP_BASE64))
        self.btn_up_sim.setIconSize(QSize(8, 8))
        self.btn_up_sim.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_up_sim.setAutoRepeat(True)
        self.btn_up_sim.setStyleSheet("QPushButton { border: none; background: rgba(0, 0, 0, 0.2); border-top-left-radius: 4px; border-bottom: 1px solid #444; } QPushButton:hover { background: rgba(255, 255, 255, 0.1); }")
        
        self.btn_down_sim = QPushButton()
        self.btn_down_sim.setFixedHeight(12)
        self.btn_down_sim.setIcon(get_svg_icon(DOWN_BASE64))
        self.btn_down_sim.setIconSize(QSize(8, 8))
        self.btn_down_sim.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_down_sim.setAutoRepeat(True)
        self.btn_down_sim.setStyleSheet("QPushButton { border: none; background: rgba(0, 0, 0, 0.2); border-bottom-left-radius: 4px; } QPushButton:hover { background: rgba(255, 255, 255, 0.1); }")
        
        al.addWidget(self.btn_up_sim)
        al.addWidget(self.btn_down_sim)
        sc_layout.addWidget(arrows_w)
        
        from PyQt6.QtWidgets import QDoubleSpinBox
        self.spin_similarity = QDoubleSpinBox()
        self.spin_similarity.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.spin_similarity.setRange(70.00, 100.00)
        self.spin_similarity.setDecimals(2)
        self.spin_similarity.setSingleStep(0.01)
        self.spin_similarity.setValue(97.50)
        self.spin_similarity.setSuffix("%")
        self.spin_similarity.setFixedWidth(64)
        self.spin_similarity.setFixedHeight(24)
        self.spin_similarity.setStyleSheet("border: none; background: transparent; color: white; font-weight: bold; font-size: 13px; padding-left: 2px;")
        sc_layout.addWidget(self.spin_similarity)
        
        self.btn_up_sim.clicked.connect(self.spin_similarity.stepUp)
        self.btn_down_sim.clicked.connect(self.spin_similarity.stepDown)
        
        slider_layout.addWidget(spin_container)
        algo_layout.addLayout(slider_layout)
        
        # Connect Range logic
        self.combo_range.currentIndexChanged.connect(self._update_slider_range)
        self.combo_range.currentIndexChanged.connect(lambda: self.settings_changed_for_rescan.emit())
        self.slider_similarity.valueChanged.connect(self._on_slider_changed)
        self.spin_similarity.valueChanged.connect(self._on_spin_changed)
        self.spin_similarity.valueChanged.connect(lambda: self.settings_changed_for_rescan.emit())
        self.combo_resolution.currentIndexChanged.connect(lambda: self.settings_changed_for_rescan.emit())
        self.combo_media_type.currentIndexChanged.connect(self._on_media_type_changed)
        self._slider_updating = False
        self._update_slider_range()
        
        # Size Filters
        size_widget = QWidget()
        size_layout = QHBoxLayout(size_widget)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_layout.setSpacing(6)
        
        self.lbl_size = QLabel(AppContext.tr("cln_size_filter"))
        self.lbl_size.setStyleSheet("color: #ccc; font-size: 12px; font-weight: bold;")
        size_layout.addWidget(self.lbl_size)
        
        self.size_widget = SizeFilterWidget()
        self.size_widget.valueChanged.connect(self.validate_size_inputs)
        size_layout.addWidget(self.size_widget)
        size_layout.addStretch()
        algo_layout.addWidget(size_widget)
        
        col_filters.addWidget(algo_frame)
        
        self.lbl_filter_status = QLabel(AppContext.tr("cln_filter_all"))
        self.lbl_filter_status.setStyleSheet("font-size: 12px; color: #ccc; margin-left: 2px; font-weight: bold; margin-top: 2px;")
        col_filters.addWidget(self.lbl_filter_status)
        col_filters.addStretch()
        
        self.btn_filter = QPushButton()
        self.btn_filter.setIcon(load_svg_icon(os.path.join(icons_dir, "loupe-color.svg"), QSize(16, 16)))
        self.btn_filter.setIconSize(QSize(16, 16))
        self.btn_filter.setFixedHeight(36)
        self.btn_filter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_filter.setEnabled(False)
        self.btn_filter.clicked.connect(self.open_filter_clicked.emit)
        self.btn_filter.setStyleSheet("QPushButton { background-color: #444; color: #fff; border: 1px solid #666; padding: 0 10px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #555; color: white; border-color: #888; }")
        col_filters.addWidget(self.btn_filter)
        self.layout.addLayout(col_filters, stretch=3)
        
        # COL 3: Progress
        self.col_prog = QVBoxLayout()
        self.col_prog.setContentsMargins(0, 0, 0, 0)
        self.col_prog.setSpacing(4)
        prog_header = QHBoxLayout()
        prog_header.setContentsMargins(0, 0, 0, 0)
        prog_header.setSpacing(5)
        self.lbl_prog_icon = QLabel()
        self.lbl_prog_icon.setFixedSize(16, 16)
        self.lbl_prog_icon.setStyleSheet("background: transparent; border: none;")
        self.lbl_prog_header = QLabel()
        self.lbl_prog_header.setStyleSheet("font-weight: bold; color: #888; font-size: 11px; font-family: 'Segoe UI'; padding: 2px 0px;")
        prog_header.addWidget(self.lbl_prog_icon)
        prog_header.addWidget(self.lbl_prog_header)
        prog_header.addStretch()
        self.col_prog.addLayout(prog_header)
        
        metrics_frame = QFrame()
        metrics_frame.setObjectName("metrics_frame")
        metrics_frame.setStyleSheet("QFrame#metrics_frame { background: #252526; border: 1px solid #333; border-radius: 4px; }")
        gl = QGridLayout(metrics_frame)
        gl.setSpacing(6)
        gl.setContentsMargins(8, 8, 8, 8)
        
        lbl_style = "color: #cccccc; font-size: 15px;"
        val_style = "color: #ffffff; font-weight: bold; font-size: 15px;"
        
        self.lbl_scanned = QLabel(AppContext.tr("cln_lbl_scanned"))
        self.lbl_scanned.setStyleSheet(lbl_style)
        self.val_scanned = QLabel("0")
        self.val_scanned.setStyleSheet(val_style)
        self.val_scanned.setAlignment(Qt.AlignmentFlag.AlignRight)
        gl.addWidget(self.lbl_scanned, 0, 0)
        gl.addWidget(self.val_scanned, 0, 1)
        
        self.lbl_percent = QLabel("")
        self.lbl_percent.hide()
        self.lbl_dup = QLabel("Найдено групп похожих:" if is_ru else "Similar groups found:")
        self.lbl_dup.setStyleSheet(lbl_style)
        self.btn_duples = ModeBadgeButton("0")
        self.btn_duples.set_mode('disabled')
        cont_dup = QWidget()
        l_dup = QHBoxLayout(cont_dup)
        l_dup.setContentsMargins(0, 0, 0, 0)
        l_dup.addStretch()
        l_dup.addWidget(self.lbl_percent)
        l_dup.addWidget(self.btn_duples)
        gl.addWidget(self.lbl_dup, 1, 0)
        gl.addWidget(cont_dup, 1, 1)
        
        self.lbl_wasted = QLabel(AppContext.tr("cln_lbl_wasted"))
        self.lbl_wasted.setStyleSheet(lbl_style)
        self.val_wasted = QLabel("0 B")
        self.val_wasted.setStyleSheet(val_style)
        self.val_wasted.setAlignment(Qt.AlignmentFlag.AlignRight)
        gl.addWidget(self.lbl_wasted, 2, 0)
        gl.addWidget(self.val_wasted, 2, 1)
        
        self.lbl_zero = QLabel("")
        self.lbl_zero.hide()
        self.btn_zero = ModeBadgeButton("0")
        self.btn_zero.hide()
        
        self.lbl_empty = QLabel("")
        self.lbl_empty.hide()
        self.btn_empty = ModeBadgeButton("0")
        self.btn_empty.hide()
        
        self.val_curr_path = QLabel("...")
        self.val_curr_path.setStyleSheet("color: #888; font-style: italic; font-size: 12px;")
        self.val_curr_path.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.val_curr_path.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        gl.addWidget(self.val_curr_path, 5, 0, 1, 2)
        
        self.lbl_time = QLabel(AppContext.tr("cln_lbl_time"))
        self.lbl_time.setStyleSheet(lbl_style)
        self.val_time = QLabel("00:00.000")
        self.val_time.setStyleSheet(val_style)
        self.val_time.setAlignment(Qt.AlignmentFlag.AlignRight)
        gl.addWidget(self.lbl_time, 6, 0)
        gl.addWidget(self.val_time, 6, 1)
        
        self.col_prog.addWidget(metrics_frame)
        self.col_prog.addStretch()
        
        self.btn_scan = QPushButton(" " + AppContext.tr("cln_btn_start"))
        self.btn_scan.setFixedHeight(36)
        self.btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_scan.clicked.connect(self.start_scan_clicked.emit)
        self.btn_scan.setProperty("has_folders", False)
        
        self.col_prog.addWidget(self.btn_scan)
        self.layout.addLayout(self.col_prog, stretch=3)
        
        self.scan_stale = False
        self.update_ui_text()
        self.validate_size_inputs()

    def update_ui_text(self):
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
        
        self.lbl_src_icon.setPixmap(load_svg_pixmap(os.path.join(icons_dir, "folder-color.svg"), QSize(16, 16)))
        self.lbl_algo_icon.setPixmap(load_svg_pixmap(os.path.join(icons_dir, "gear-color.svg"), QSize(16, 16)))
        self.lbl_prog_icon.setPixmap(load_svg_pixmap(os.path.join(icons_dir, "loupe-color.svg"), QSize(16, 16), mirror_horizontal=True))

        raw_title = AppContext.tr("cln_src_title")
        clean_title = raw_title.replace("1.", "").strip() if raw_title.startswith("1.") else raw_title
        self.lbl_src.setText(f"1. {clean_title}")
        
        self.drop_zone.update_ui_text()
        self.lbl_warn.setText(AppContext.tr("cln_warn_system_folders"))
        
        raw_algo = AppContext.tr("cln_algo_title")
        clean = raw_algo.replace("2.", "").strip() if raw_algo.startswith("2.") else raw_algo
        self.lbl_algo.setText(f"2. {clean}")

        self.chk_cache.setText(AppContext.tr("cln_chk_cache"))
        self.btn_clear_cache.setToolTip(AppContext.tr("cln_tip_clear_cache"))
        self.btn_clear_cache.setIcon(load_svg_icon(os.path.join(icons_dir, "trash-color.svg"), QSize(16, 16)))
        self.btn_clear_cache.setIconSize(QSize(16, 16))
        
        self.btn_filter.setText(AppContext.tr("cln_btn_scan_types"))
        
        raw_prog = AppContext.tr("cln_prog_title")
        clean = raw_prog.replace("3.", "").strip() if raw_prog.startswith("3.") else raw_prog
        self.lbl_prog_header.setText(f"3. {clean}")

        self.lbl_scanned.setText(AppContext.tr("cln_lbl_scanned"))
        self.lbl_wasted.setText(AppContext.tr("cln_lbl_wasted"))
        self.lbl_time.setText(AppContext.tr("cln_lbl_time"))
        self.lbl_size.setText(AppContext.tr("cln_size_filter"))
        
        if hasattr(self, 'btn_abort') and self.btn_abort:
            self.btn_abort.setText(AppContext.tr("cln_btn_abort"))
            self.btn_abort.setToolTip(AppContext.tr("cln_tip_abort"))
        if hasattr(self, 'btn_stop_scan') and self.btn_stop_scan:
            self.btn_stop_scan.setText(AppContext.tr("cln_btn_reset"))
            self.btn_stop_scan.setToolTip(AppContext.tr("cln_tip_reset"))

    def validate_size_inputs(self):
        is_error = self.size_widget.has_error()
        has_folders = self.btn_scan.property("has_folders")
        should_enable = has_folders and not is_error
        self.btn_scan.setEnabled(should_enable)
        
        if should_enable:
            if getattr(self, 'scan_stale', False):
                self.btn_scan.setStyleSheet("""
                    QPushButton { background-color: #ea580c; color: white; font-weight: 900; font-size: 14px; border: 1px solid #f97316; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
                    QPushButton:hover { background-color: #f97316; }
                """)
            else:
                self.btn_scan.setStyleSheet("""
                    QPushButton { background-color: #15803d; color: white; font-weight: 900; font-size: 14px; border: 1px solid #16a34a; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
                    QPushButton:hover { background-color: #16a34a; }
                """)
        else:
            self.btn_scan.setStyleSheet("""
                QPushButton { background-color: #222; color: #555; font-weight: 900; font-size: 14px; border: 1px solid #333; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
            """)

    def get_size_limits(self):
        return self.size_widget.get_min_bytes(), self.size_widget.get_max_bytes()

    def set_scan_enabled(self, enabled):
        self.btn_scan.setProperty("has_folders", enabled)
        self.validate_size_inputs()

    def set_current_path(self, path: str) -> None:
        if not path:
            self.val_curr_path.setText("...")
            self.val_curr_path.setToolTip("")
            return
            
        is_path = '/' in path or '\\' in path
        if not is_path:
            if self.val_curr_path.text() != "...": return
            else:
                self.val_curr_path.setText("...")
                self.val_curr_path.setToolTip("")
                return
        
        path_clean = path.replace('\\', '/')
        if len(path_clean) > 42:
            shrunk = path_clean[:12] + "..." + path_clean[-27:]
        else:
            shrunk = path_clean
            
        self.val_curr_path.setText(shrunk)
        self.val_curr_path.setToolTip(AppContext.tr("cln_tip_curr_scanning").format(path))

    def refresh_list_alignment(self):
        """Выравнивание ширины подписей папок в списке источников."""
        layout = self.folder_list_layout
        count = layout.count()
        if count == 0: return
        max_w = 0
        items = []
        for i in range(count):
            item = layout.itemAt(i)
            w = item.widget()
            if w and hasattr(w, 'get_ideal_name_width'):
                items.append(w)
                max_w = max(max_w, w.get_ideal_name_width())
        container_w = self.sources_list_widget.width()
        if container_w <= 0: container_w = 400
        limit = int(container_w * 0.5)
        target_w = min(max_w, limit)
        for w in items: w.set_name_label_width(target_w)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh_list_alignment()

    def setup_scan_buttons(self, on_abort_click, on_stop_click) -> None:
        """Заменяет кнопку Сканировать на кнопки Стоп/Сброс на время сканирования."""
        self.btn_scan.hide()
        if not hasattr(self, 'scan_buttons_widget'):
            self.scan_buttons_widget = QWidget()
            layout = QHBoxLayout(self.scan_buttons_widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(10)
            self.btn_abort = QPushButton(AppContext.tr("cln_btn_abort"))
            self.btn_abort.setFixedHeight(36)
            self.btn_abort.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_abort.setToolTip(AppContext.tr("cln_tip_abort"))
            self.btn_abort.setStyleSheet("""
                QPushButton { background-color: #c2410c; color: white; font-weight: 900; font-size: 14px; border: 1px solid #9a3412; border-radius: 6px; padding: 4px; }
                QPushButton:hover { background-color: #ea580c; }
                QPushButton:disabled { background-color: #222; color: #555; border-color: #333; }
            """)
            self.btn_abort.clicked.connect(on_abort_click)
            self.btn_abort.hide() # Скрываем кнопку Прервать для поиска похожих
            
            self.btn_stop_scan = QPushButton(AppContext.tr("cln_btn_reset"))
            self.btn_stop_scan.setFixedHeight(36)
            self.btn_stop_scan.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_stop_scan.setToolTip(AppContext.tr("cln_tip_reset"))
            self.btn_stop_scan.setStyleSheet("""
                QPushButton { background-color: #991b1b; color: white; font-weight: 900; font-size: 14px; border: 1px solid #7f1d1d; border-radius: 6px; padding: 4px; }
                QPushButton:hover { background-color: #b91c1c; }
                QPushButton:disabled { background-color: #222; color: #555; border-color: #333; }
            """)
            self.btn_stop_scan.clicked.connect(on_stop_click)
            layout.addWidget(self.btn_stop_scan, 1)
            self.col_prog.addWidget(self.scan_buttons_widget)
        self.btn_stop_scan.setEnabled(True)
        self.btn_stop_scan.setText(AppContext.tr("cln_btn_reset"))
        self.scan_buttons_widget.show()

    def restore_scan_buttons(self) -> None:
        """Возвращает исходную кнопку Сканировать."""
        if hasattr(self, 'scan_buttons_widget'):
            self.scan_buttons_widget.hide()
        self.btn_scan.show()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
        else: event.ignore()

    def update_cache_info(self, size_str):
        self.lbl_cache_size.setText(size_str)
        self.btn_clear_cache.setEnabled(size_str != "0 B")

    def _update_slider_range(self):
        idx = self.combo_range.currentIndex()
        if idx == 0: span = 5.0
        elif idx == 1: span = 10.0
        elif idx == 2: span = 20.0
        elif idx == 3: span = 30.0
        else: span = 100.0
        
        min_val = 100.0 - span
        self.spin_similarity.setRange(min_val, 100.00)
        
        curr_val = self.spin_similarity.value()
        if curr_val < min_val:
            self.spin_similarity.setValue(min_val)
            
        self._sync_slider_from_spin()

    def _on_slider_changed(self, v):
        if self._slider_updating: return
        self._slider_updating = True
        
        min_val = self.spin_similarity.minimum()
        pct = min_val + (v / 500.0) * (100.0 - min_val)
        self.spin_similarity.setValue(pct)
        self._slider_updating = False

    def _on_spin_changed(self, v):
        if self._slider_updating: return
        self._slider_updating = True
        
        min_val = self.spin_similarity.minimum()
        span = 100.0 - min_val
        if span > 0:
            sv = int(((v - min_val) / span) * 500)
            self.slider_similarity.setValue(sv)
        else:
            self.slider_similarity.setValue(500)
        self._slider_updating = False
        
    def _sync_slider_from_spin(self):
        self._on_spin_changed(self.spin_similarity.value())

    def _on_media_type_changed(self, idx):
        if idx == 1: # Аудио
            self.combo_resolution.setEnabled(False)
            self.spin_similarity.setEnabled(False)
            self.slider_similarity.setEnabled(False)
            self.combo_range.setEnabled(False)
        else:
            self.combo_resolution.setEnabled(True)
            self.spin_similarity.setEnabled(True)
            self.slider_similarity.setEnabled(True)
            self.combo_range.setEnabled(True)
            
        if idx == 2: # Видео
            self.combo_range.setCurrentIndex(3) # Диапазон 30%
            self.spin_similarity.setValue(70.0)
        elif idx == 0: # Изображения
            self.combo_range.setCurrentIndex(0) # Диапазон 5%
            self.spin_similarity.setValue(97.5)
        self.settings_changed_for_rescan.emit()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            for url in urls:
                path = url.toLocalFile()
                if os.path.isdir(path): self.folder_dropped.emit(path)
            event.acceptProposedAction()
        else: event.ignore()
