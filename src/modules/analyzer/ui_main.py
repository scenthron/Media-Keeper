


import os
import subprocess
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, 
    QLineEdit, QSplitter, QMenu, QFileDialog, QComboBox, QCheckBox, QScrollArea, QTextEdit,
    QCompleter
)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl, QTimer, QStringListModel, QSize
from PyQt6.QtGui import QAction, QDesktopServices, QKeyEvent, QIcon, QPixmap, QPainter, QPen, QBrush, QColor, QPainterPath, QTransform

from config import AppContext, APP_DESIGN
from .worker import AnalyzerWorker
from .ui_chart import AnalyzerPieChart
from .ui_tables import SummaryTable, FileDetailTree
from modules.cleaner.ui_widgets import CompactDropZone
from modules.cleaner.ui_preview import CleanerPreviewWidget
from utils_io import smart_move_file
from utils_common import format_size
import shutil
from PyQt6.QtWidgets import QMessageBox

def create_hamburger_pixmap(color: QColor, width=16, height=16) -> QPixmap:
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    pen = QPen(color, 2)
    painter.setPen(pen)
    painter.drawLine(2, 3, width - 3, 3)
    painter.drawLine(2, 8, width - 3, 8)
    painter.drawLine(2, 13, width - 3, 13)
    painter.end()
    return pixmap

def get_hamburger_icon() -> QIcon:
    icon = QIcon()
    icon.addPixmap(create_hamburger_pixmap(QColor("#888888")), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(create_hamburger_pixmap(QColor("#cccccc")), QIcon.Mode.Active, QIcon.State.Off)
    icon.addPixmap(create_hamburger_pixmap(QColor("#ffffff")), QIcon.Mode.Normal, QIcon.State.On)
    icon.addPixmap(create_hamburger_pixmap(QColor("#ffffff")), QIcon.Mode.Active, QIcon.State.On)
    return icon



class AnalyzerWidget(QWidget):
    back_requested = pyqtSignal() # Request to go back to Sorter tab
    sort_folder_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.icons_dir = AppContext.find_resource_dir("icons")
        self.current_scanned_path = "" 
        self.current_view_path = ""    
        self.nav_history = []          
        self.worker = None
        self.full_stats = {} 
        self.full_root_node = None
        
        # Search autocomplete
        self.completer = QCompleter()
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setFilterMode(Qt.MatchFlag.MatchStartsWith) # Changed from MatchContains for proper prefix matching
        self.completer.setMaxVisibleItems(10)
        self.completer.activated.connect(self.on_completer_activated)
        
        # Style for completer popup
        popup = self.completer.popup()
        popup.setStyleSheet("""
            QAbstractItemView {
                background-color: #2b2b2b;
                color: #ccc;
                border: 1px solid #444;
                selection-background-color: #3b82f6;
                selection-color: white;
                outline: none;
            }
        """)
        
        self.current_detail_ext = None # Store current extension for updating detail title
        self.category_colors_cache = {}
        self.undo_history = []
        self.last_move_to_dir = None
        
        # Enable focus to catch KeyPress events (Backspace)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # 1. Main Top Toolbar (Title Only)
        self.title_toolbar = QFrame()
        self.title_toolbar.setFixedHeight(40)
        self.title_toolbar.setStyleSheet("background-color: #2b2b2b;")
        ttl_layout = QHBoxLayout(self.title_toolbar)
        # Increased Left Margin to 70px to clear the Hamburger Button
        ttl_layout.setContentsMargins(70, 0, 10, 0)
        
        self.lbl_title = QLabel(AppContext.tr("anl_toolbar_title"))
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: 900; color: #eee; letter-spacing: 1px;")
        ttl_layout.addWidget(self.lbl_title)
        
        # Initialize btn_back_tab FIRST
        self.btn_back_tab = QPushButton(AppContext.tr("anl_btn_back"))
        self.btn_back_tab.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 4px 8px; border-radius: 4px;")
        self.btn_back_tab.clicked.connect(self.back_requested.emit)
        self.btn_back_tab.hide()
        
        ttl_layout.addStretch()
        ttl_layout.addWidget(self.btn_back_tab)
        
        self.layout.addWidget(self.title_toolbar)
 
        # 2. Secondary Toolbar
        self.func_toolbar = QFrame()
        self.func_toolbar.setObjectName("func_toolbar")
        self.func_toolbar.setFixedHeight(40)
        self.func_toolbar.setStyleSheet("#func_toolbar { background-color: #1e1e1e; border-bottom: 1px solid #333; }")
        ft_layout = QHBoxLayout(self.func_toolbar)
        ft_layout.setContentsMargins(10, 4, 10, 4)
        ft_layout.setSpacing(10)
        
        # 1. Загрузка векторной иконки навигации
        icons_dir = AppContext.find_resource_dir("icons")
        icon_path = os.path.join(icons_dir, "arrow-right-color.svg")
        icon_size = QSize(20, 20)

        def create_toolbar_icon(path, angle, flip_h=False, flip_v=False):
            temp_icon = QIcon(path)
            pm = temp_icon.pixmap(24, 24)
            transform = QTransform()
            if angle != 0:
                transform.rotate(angle)
            if flip_h:
                transform.scale(-1, 1)
            if flip_v:
                transform.scale(1, -1)
            if angle != 0 or flip_h or flip_v:
                pm = pm.transformed(transform, Qt.TransformationMode.SmoothTransformation)
            
            dimmed = QPixmap(pm.size())
            dimmed.setDevicePixelRatio(pm.devicePixelRatio())
            dimmed.fill(Qt.GlobalColor.transparent)
            painter = QPainter(dimmed)
            painter.setOpacity(0.2)
            painter.drawPixmap(0, 0, pm)
            painter.end()
            
            icon = QIcon()
            icon.addPixmap(pm, QIcon.Mode.Normal)
            icon.addPixmap(dimmed, QIcon.Mode.Disabled)
            return icon

        back_icon = create_toolbar_icon(icon_path, 180, flip_h=True) # Поворот 180 + флип по горизонтали (указывает влево)
        up_icon = create_toolbar_icon(icon_path, 90)   # Поворот 90 (указывает вверх)

        btn_nav_style = """
            QPushButton { 
                background-color: #2b2b2b; 
                border: 1px solid #444; 
                border-radius: 14px;
                padding: 0px;
            }
            QPushButton:hover { 
                background-color: #383838; 
                border-color: #555; 
            }
            QPushButton:pressed { 
                background-color: #444; 
            }
            QPushButton:disabled { 
                background-color: #222; 
                border-color: #333; 
            }
        """

        # 1. Кнопка Назад (История)
        self.btn_nav_back = QPushButton(self)
        self.btn_nav_back.setFixedSize(28, 28)
        self.btn_nav_back.setIcon(back_icon)
        self.btn_nav_back.setIconSize(icon_size)
        self.btn_nav_back.setToolTip(AppContext.tr("anl_btn_back")) 
        self.btn_nav_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_nav_back.setStyleSheet(btn_nav_style)
        self.btn_nav_back.clicked.connect(self.navigate_history_back)
        self.btn_nav_back.setEnabled(False)

        # 2. Кнопка Вверх (На уровень выше)
        self.btn_nav_up = QPushButton(self)
        self.btn_nav_up.setFixedSize(28, 28)
        self.btn_nav_up.setIcon(up_icon)
        self.btn_nav_up.setIconSize(icon_size)
        self.btn_nav_up.setToolTip(AppContext.tr("anl_btn_up"))
        self.btn_nav_up.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_nav_up.setStyleSheet(btn_nav_style)
        self.btn_nav_up.clicked.connect(self.go_up_level)
        self.btn_nav_up.setEnabled(False)

        self.path_container = QFrame()
        self.path_container.setFixedHeight(32)
        self.path_container.setStyleSheet("QFrame { background: #333; border: 1px solid #555; border-radius: 4px; }")
        pc_layout = QHBoxLayout(self.path_container)
        pc_layout.setContentsMargins(2, 2, 2, 2)
        pc_layout.setSpacing(2)
        
        # Добавляем кнопки навигации в строку пути
        pc_layout.addWidget(self.btn_nav_back)
        pc_layout.addWidget(self.btn_nav_up)
        
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText(AppContext.tr("anl_placeholder_path"))
        self.path_input.setStyleSheet("QLineEdit { background: transparent; color: white; border: none; padding: 0px 8px; }")
        self.path_input.returnPressed.connect(self.on_path_entered)
        pc_layout.addWidget(self.path_input, 1)
        

        
        # Лейбл для отображения размера текущей папки
        self.lbl_path_size = QLabel("")
        self.lbl_path_size.setStyleSheet("""
            QLabel {
                color: #a0aec0;
                font-size: 11px;
                font-weight: bold;
                background: transparent;
                border: none;
                padding-right: 6px;
            }
        """)
        pc_layout.addWidget(self.lbl_path_size)
        
        self.btn_browse = QPushButton()
        from PyQt6.QtWidgets import QSizePolicy
        self.btn_browse.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self.btn_browse.setIcon(QIcon(os.path.join(self.icons_dir, "folder-color.svg")))
        self.btn_browse.setIconSize(QSize(18, 18))
        self.btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse.setToolTip(AppContext.tr("anl_btn_browse"))
        self.btn_browse.setStyleSheet("""
            QPushButton { 
                background: transparent; 
                border: none; 
                border-top-right-radius: 3px; 
                border-bottom-right-radius: 3px; 
                padding: 0px 12px; 
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); }
            QPushButton:pressed { background-color: rgba(255, 255, 255, 0.2); }
        """)
        self.btn_browse.clicked.connect(self.browse_folder)
        pc_layout.addWidget(self.btn_browse)
        
        ft_layout.addWidget(self.path_container, 1) 
        
        # Кнопка переключения вида диаграммы (Sunburst / TreeMap)
        self.btn_chart_mode = QPushButton()
        self.btn_chart_mode.setFixedSize(32, 32)
        self.btn_chart_mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_chart_mode.setIcon(QIcon(os.path.join(self.icons_dir, "diagram-pie-color.svg")))
        self.btn_chart_mode.setIconSize(QSize(18, 18))
        self.btn_chart_mode.setToolTip(AppContext.tr("anl_tip_chart_mode_sunburst"))
        self.btn_chart_mode.setStyleSheet("""
            QPushButton { 
                background-color: #333; 
                border-radius: 4px; 
                border: 1px solid #444; 
            }
            QPushButton:hover { 
                background-color: #3b82f6; 
                border-color: #3b82f6; 
            }
        """)
        self.btn_chart_mode.clicked.connect(self.toggle_chart_mode)
        ft_layout.addWidget(self.btn_chart_mode)
        
        # Кнопка смены цветовой палитры файлов
        self.btn_reset_colors = QPushButton()
        self.btn_reset_colors.setFixedSize(32, 32)
        self.btn_reset_colors.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_colors.setIcon(QIcon(os.path.join(self.icons_dir, "video-editor-color.svg")))
        self.btn_reset_colors.setIconSize(QSize(18, 18))
        self.btn_reset_colors.setToolTip(AppContext.tr("anl_btn_reset_colors"))
        self.btn_reset_colors.setStyleSheet("""
            QPushButton { 
                background-color: #333; 
                border-radius: 4px; 
                border: 1px solid #444; 
            }
            QPushButton:hover { 
                background-color: #3b82f6; 
                border-color: #3b82f6; 
            }
        """)
        self.btn_reset_colors.clicked.connect(lambda: self.chart.regenerate_extension_colors())
        ft_layout.addWidget(self.btn_reset_colors)
        
        self.lbl_nesting = QLabel(AppContext.tr("lbl_nesting"))
        ft_layout.addWidget(self.lbl_nesting)
        
        self.cb_depth = QComboBox()
        self.cb_depth.addItems(["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"])
        self.cb_depth.setCurrentIndex(4) # Default 5
        self.cb_depth.setStyleSheet("background: #333; color: white; padding: 4px;")
        self.cb_depth.currentIndexChanged.connect(self.on_depth_changed)
        ft_layout.addWidget(self.cb_depth)
        
        self.btn_scan = QPushButton(AppContext.tr("anl_btn_scan"))
        self.btn_scan.setMinimumWidth(110)
        self.btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_scan.setStyleSheet("""
            QPushButton { background-color: #15803d; color: white; font-weight: bold; border-radius: 4px; padding: 6px; }
            QPushButton:hover { background-color: #16a34a; }
            QPushButton:disabled { background-color: #333; color: #555; }
        """)
        self.btn_scan.clicked.connect(self.on_scan_clicked)
        self.btn_scan.setEnabled(False)
        ft_layout.addWidget(self.btn_scan)
 
        self.layout.addWidget(self.func_toolbar)


        # Content Area (Splitter V: Chart/Table + Progress)
        self.content_area = QWidget()
        content_layout = QVBoxLayout(self.content_area)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        self.v_splitter = QSplitter(Qt.Orientation.Vertical)
        self.v_splitter.setHandleWidth(8)
        self.v_splitter.setStyleSheet("QSplitter::handle { background-color: #333; }")
        
        self.h_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.h_splitter.setStyleSheet("QSplitter::handle { border-left: 1px solid #444; border-right: 1px solid #444; }")
        
        # Left container for Chart + Progress
        chart_container = QWidget()
        chart_layout = QVBoxLayout(chart_container)
        chart_layout.setContentsMargins(0,0,0,0)
        chart_layout.setSpacing(0)
        
        self.chart = AnalyzerPieChart()
        # Drop should save history of where we came from
        self.chart.folder_dropped.connect(lambda p: self.start_analysis(p, push_history=True))
        
        # CRITICAL FIX: Defer all signals that might trigger scene.clear() to prevent crashes
        # when a widget inside the scene (like Stop button) triggers its own destruction.
        self.chart.node_clicked.connect(lambda node: QTimer.singleShot(0, lambda: self.on_chart_click(node)))
        self.chart.file_clicked.connect(self.on_chart_file_clicked)
        self.chart.slice_context_menu.connect(self.on_chart_context_menu)
        self.chart.slice_hovered.connect(self.on_chart_slice_hovered)
        self.chart.browse_requested.connect(self.browse_folder) 
        self.chart.center_clicked.connect(self.open_current_folder)
        
        # Connect Center Buttons from Chart (Deferred)
        self.chart.nav_back_clicked.connect(lambda: QTimer.singleShot(0, self.navigate_history_back))
        self.chart.nav_up_clicked.connect(lambda: QTimer.singleShot(0, self.go_up_level))
        self.chart.stop_scan_clicked.connect(lambda: QTimer.singleShot(0, self.on_scan_clicked))
        
        chart_layout.addWidget(self.chart)
        

        self.lbl_progress = QLabel("")
        self.lbl_progress.setStyleSheet("""
            QLabel {
                background-color: transparent; 
                color: #cccccc; 
                padding: 10px; 
                font-size: 16px; 
                font-weight: bold;
            }
        """)
        self.lbl_progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_progress.hide()
        chart_layout.addWidget(self.lbl_progress)
        
        self.h_splitter.addWidget(chart_container)
        
        self.summary_table = SummaryTable()
        self.summary_table.row_clicked.connect(self.show_details)
        self.summary_table.row_hovered.connect(self.on_summary_row_hovered)
        self.h_splitter.addWidget(self.summary_table)
        
        self.h_splitter.setCollapsible(0, False)
        self.h_splitter.setCollapsible(1, False)
        
        self.v_splitter.addWidget(self.h_splitter)
        
        # Details Panel
        self.detail_container = QWidget()
        # Header is now always visible as per user request
        dc_layout = QVBoxLayout(self.detail_container)
        dc_layout.setContentsMargins(0, 0, 0, 0)
        dc_layout.setSpacing(0)
        
        # Header Row for Details
        det_header = QWidget()
        det_header.setStyleSheet("background-color: #333; border: none;")
        dh_layout = QHBoxLayout(det_header)
        dh_layout.setContentsMargins(10, 5, 10, 5)
        
        # Toggle button "Show in directories" before title
        self.btn_group_dir = QPushButton()
        self.btn_group_dir.setCheckable(True)
        self.btn_group_dir.setFixedSize(26, 24)
        self.btn_group_dir.setIcon(get_hamburger_icon())
        self.btn_group_dir.setIconSize(QSize(16, 16))
        self.btn_group_dir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_group_dir.setToolTip(AppContext.tr("anl_chk_group_dir"))
        self.btn_group_dir.setStyleSheet("""
            QPushButton { 
                background-color: #2b2b2b; 
                border: 1px solid #444; 
                border-radius: 4px; 
            }
            QPushButton:hover { 
                background-color: #383838; 
                border-color: #555; 
            }
            QPushButton:checked { 
                background-color: #3b82f6; 
                border-color: #3b82f6; 
            }
        """)
        self.btn_group_dir.toggled.connect(self.reload_details)
        dh_layout.addWidget(self.btn_group_dir)
        
        self.lbl_detail_title = QLabel(AppContext.tr("anl_msg_idle_details"))
        self.lbl_detail_title.setStyleSheet("color: white; font-weight: bold; font-size: 11px;")
        dh_layout.addWidget(self.lbl_detail_title)
        
        dh_layout.addSpacing(10)
        
        # Selection Buttons with Checkbox Icons
        self.btn_sel_all = QPushButton()
        self.btn_sel_all.setFixedSize(30, 24)
        self.btn_sel_all.setIcon(QIcon(os.path.join(self.icons_dir, "checkbox_checked.svg")))
        self.btn_sel_all.setIconSize(QSize(14, 14))
        self.btn_sel_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sel_all.setToolTip(AppContext.tr("anl_btn_sel_all"))
        self.btn_sel_all.setStyleSheet("""
            QPushButton { 
                background-color: #444; 
                border: 1px solid #555; 
                border-radius: 4px; 
            } 
            QPushButton:hover { 
                background-color: #555; 
            }
        """)
        self.btn_sel_all.clicked.connect(self.on_select_all_clicked)
        dh_layout.addWidget(self.btn_sel_all)
        
        self.btn_sel_none = QPushButton()
        self.btn_sel_none.setFixedSize(30, 24)
        self.btn_sel_none.setIcon(QIcon(os.path.join(self.icons_dir, "checkbox_unchecked.svg")))
        self.btn_sel_none.setIconSize(QSize(14, 14))
        self.btn_sel_none.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sel_none.setToolTip(AppContext.tr("anl_btn_sel_none"))
        self.btn_sel_none.setStyleSheet("""
            QPushButton { 
                background-color: #444; 
                border: 1px solid #555; 
                border-radius: 4px; 
            } 
            QPushButton:hover { 
                background-color: #555; 
            }
        """)
        self.btn_sel_none.clicked.connect(self.on_select_none_clicked)
        dh_layout.addWidget(self.btn_sel_none)
        
        # Add a stretch spacer (spring) to push search and action buttons to the right
        dh_layout.addStretch(1)
        
        # New: Search Filter Section (Next to action buttons)
        self.search_frame = QFrame()
        self.search_frame.setStyleSheet("background: #222; border-radius: 4px; border: 1px solid #444;")
        sf_layout = QHBoxLayout(self.search_frame)
        sf_layout.setContentsMargins(0, 2, 4, 2) # 0 margin on left for text
        sf_layout.setSpacing(2)
        
        self.txt_filter = QLineEdit()
        self.txt_filter.setPlaceholderText(AppContext.tr("anl_ph_filter_all"))
        self.txt_filter.setCompleter(self.completer) # Attach completer
        from PyQt6.QtWidgets import QSizePolicy
        self.txt_filter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.txt_filter.setStyleSheet("""
            QLineEdit { 
                background: transparent; 
                color: white; 
                border: none; 
                font-size: 13px; 
                padding-left: 12px; 
            }
        """)
        self.txt_filter.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.txt_filter.returnPressed.connect(self.reload_details)
        self.txt_filter.textChanged.connect(self.on_filter_text_changed)
        sf_layout.addWidget(self.txt_filter)
        
        # Container for clear button to keep OK button position fixed
        self.clear_area = QWidget()
        self.clear_area.setFixedWidth(24)
        self.clear_area.setStyleSheet("background: transparent; border: none;") # Force no border
        ca_layout = QHBoxLayout(self.clear_area)
        ca_layout.setContentsMargins(0,0,0,0)
        
        self.btn_clear_filter = QPushButton()
        self.btn_clear_filter.setIcon(QIcon(os.path.join(self.icons_dir, "cross.svg")))
        self.btn_clear_filter.setIconSize(QSize(10, 10))
        self.btn_clear_filter.setFixedSize(20, 20)
        self.btn_clear_filter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_filter.setStyleSheet("""
            QPushButton { 
                background: transparent; 
                border: none; 
                outline: none; 
                padding: 0px;
            } 
            QPushButton:hover { background-color: rgba(255,255,255,0.1); border-radius: 2px; }
        """)
        self.btn_clear_filter.clicked.connect(self.clear_filter)
        self.btn_clear_filter.hide() # Hidden by default
        ca_layout.addWidget(self.btn_clear_filter)
        sf_layout.addWidget(self.clear_area)
        
        # Connect text change to visibility of clear button
        self.txt_filter.textChanged.connect(lambda t: self.btn_clear_filter.setVisible(bool(t.strip())))
        
        self.btn_apply_filter = QPushButton("OK")
        self.btn_apply_filter.setFixedSize(40, 20)
        self.btn_apply_filter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply_filter.setStyleSheet("QPushButton { background: #333; color: #aaa; border: 1px solid #444; border-radius: 3px; font-size: 10px; font-weight: bold; } QPushButton:hover { background: #444; color: white; border-color: #555; }")
        self.btn_apply_filter.clicked.connect(self.reload_details)
        sf_layout.addWidget(self.btn_apply_filter)
        
        self.search_frame.setMinimumWidth(150)
        self.search_frame.setMaximumWidth(280)
        self.search_frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.search_frame.sizeHint = lambda: QSize(280, 24)
        dh_layout.addWidget(self.search_frame)
        
        # Action Buttons
        self.btn_delete_files = QPushButton(AppContext.tr("anl_btn_delete"))
        self.btn_delete_files.setIcon(QIcon(os.path.join(self.icons_dir, "trash-color.svg")))
        self.btn_delete_files.setIconSize(QSize(14, 14))
        self.btn_delete_files.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete_files.setStyleSheet("""
            QPushButton { 
                background-color: #dc2626; 
                color: white; 
                font-weight: bold; 
                border-radius: 4px; 
                padding: 4px 10px; 
                padding-left: 6px;
                border: 1px solid #b91c1c; 
            }
            QPushButton:hover { background-color: #ef4444; }
            QPushButton:disabled { background-color: #333; color: #555; border-color: #444; }
        """)
        self.btn_delete_files.setEnabled(False) # Disabled by default
        self.btn_delete_files.clicked.connect(self.on_delete_clicked)
        dh_layout.addWidget(self.btn_delete_files)
        
        self.btn_move_to = QPushButton(AppContext.tr("anl_btn_move_to"))
        self.btn_move_to.setIcon(QIcon(os.path.join(self.icons_dir, "folder-color.svg")))
        self.btn_move_to.setIconSize(QSize(14, 14))
        self.btn_move_to.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_move_to.setStyleSheet("""
            QPushButton { background-color: #10b981; color: white; font-weight: bold; border-radius: 4px; padding: 4px 10px; border: 1px solid #059669; }
            QPushButton:hover { background-color: #059669; }
            QPushButton:disabled { background-color: #333; color: #555; border-color: #444; }
        """)
        self.btn_move_to.setEnabled(False) # Disabled by default
        self.btn_move_to.clicked.connect(self.on_move_to_clicked)
        dh_layout.addWidget(self.btn_move_to)
        
        self.btn_move_files = QPushButton(AppContext.tr("anl_btn_move"))
        self.btn_move_files.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_move_files.setStyleSheet("""
            QPushButton { background-color: #3b82f6; color: white; font-weight: bold; border-radius: 4px; padding: 4px 10px; border: 1px solid #2563eb; }
            QPushButton:hover { background-color: #2563eb; }
            QPushButton:disabled { background-color: #333; color: #555; border-color: #444; }
        """)
        self.btn_move_files.setEnabled(False) # Disabled by default
        self.btn_move_files.clicked.connect(self.on_move_clicked)
        dh_layout.addWidget(self.btn_move_files)
        
        self.drop_zone = CompactDropZone()
        self.drop_zone.setMinimumWidth(120)
        self.drop_zone.setMaximumWidth(400)
        self.drop_zone.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.drop_zone.path_changed.connect(self.on_dest_path_changed)
        self.drop_zone.clicked.connect(self.browse_dest_folder) # Fix browse button
        dh_layout.addWidget(self.drop_zone, 1)
        

        
        dc_layout.addWidget(det_header, 0)
        
        # New: Splitter for Results and Preview
        self.det_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.det_splitter.setHandleWidth(1)
        self.det_splitter.setStyleSheet("QSplitter::handle { background-color: #444; }")
        
        # Bottom side - details
        self.detail_table = FileDetailTree()
        self.detail_table.itemClicked.connect(self.on_detail_item_clicked)
        self.detail_table.itemSelectionChanged.connect(self.on_detail_selection_changed)
        self.detail_table.itemChanged.connect(self.update_action_buttons)
        self.detail_table.delete_requested.connect(lambda p: self.handle_single_action(p, 'delete'))
        self.detail_table.move_requested.connect(lambda p: self.handle_single_action(p, 'move'))
        self.detail_table.item_hovered.connect(self.on_detail_row_hovered)
        self.det_splitter.addWidget(self.detail_table)
        
        # Preview side
        self.preview_container = QWidget()
        self.preview_container.setStyleSheet("background-color: #000;")
        prev_l = QVBoxLayout(self.preview_container)
        prev_l.setContentsMargins(0, 0, 0, 0)
        prev_l.setSpacing(0)
        
        prev_header = QWidget()
        prev_header.setStyleSheet("background-color: #2b2b2b; border-bottom: 1px solid #444;")
        phl = QHBoxLayout(prev_header)
        phl.setContentsMargins(5, 5, 5, 5)
        
        self.btn_info_toggle = QPushButton(AppContext.tr("cln_btn_info"))
        self.btn_info_toggle.setCheckable(True)
        self.btn_info_toggle.setFixedHeight(24)
        self.btn_info_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_info_toggle.setStyleSheet("""
            QPushButton { background-color: #333; color: #aaa; border: 1px solid #444; border-radius: 4px; padding: 0 8px; font-weight: bold; }
            QPushButton:checked { background-color: #3b82f6; color: white; border-color: #3b82f6; }
            QPushButton:hover { background-color: #444; color: white; }
        """)
        self.btn_info_toggle.clicked.connect(self.toggle_info_panel)

        self.lbl_prev_title = QLabel(AppContext.tr("cln_preview_title"))
        self.lbl_prev_title.setStyleSheet("color: #888; font-size: 11px; font-weight: bold; border: none; background: transparent; margin-left: 5px;")
        phl.addWidget(self.lbl_prev_title)
        
        phl.addStretch()
        phl.addWidget(self.btn_info_toggle)
        
        prev_l.addWidget(prev_header)
        
        self.preview_widget = CleanerPreviewWidget()
        if hasattr(self.preview_widget, 'splitter'):
            self.preview_widget.splitter.setSizes([200, 150])
        prev_l.addWidget(self.preview_widget)
        
        self.info_panel = QTextEdit()
        self.info_panel.setReadOnly(True)
        self.info_panel.setVisible(False)
        self.info_panel.setMaximumHeight(150)
        self.info_panel.setStyleSheet("QTextEdit { background-color: #222; color: #ccc; border-top: 1px solid #444; font-size: 12px; padding: 5px; border-bottom: none; border-left: none; border-right: none; }")
        prev_l.addWidget(self.info_panel)
        
        self.det_splitter.addWidget(self.preview_container)
        self.det_splitter.setSizes([800, 350])
        
        dc_layout.addWidget(self.det_splitter, 1)
        
        self.v_splitter.addWidget(self.detail_container)
        content_layout.addWidget(self.v_splitter)
        self.layout.addWidget(self.content_area)
        
        self.v_splitter.setCollapsible(0, False)
        self.v_splitter.setCollapsible(1, False)

    def update_search_placeholder(self):
        if not hasattr(self, 'txt_filter') or not self.txt_filter:
            return
        if not self.current_detail_ext:
            self.txt_filter.setPlaceholderText(AppContext.tr("anl_ph_filter_all"))
        else:
            self.txt_filter.setPlaceholderText(AppContext.tr("anl_ph_filter"))

    def update_ui_text(self):
        """Updates all text elements to the current language."""
        self.lbl_title.setText(AppContext.tr("anl_toolbar_title"))
        self.btn_back_tab.setText(AppContext.tr("anl_btn_back"))
        self.path_input.setPlaceholderText(AppContext.tr("anl_placeholder_path"))
        if hasattr(self, 'btn_browse'):
            self.btn_browse.setToolTip(AppContext.tr("anl_btn_browse"))
        self.btn_nav_back.setToolTip(AppContext.tr("anl_btn_back"))
        self.btn_nav_up.setToolTip(AppContext.tr("anl_btn_up"))
        if hasattr(self, 'btn_reset_colors'):
            self.btn_reset_colors.setToolTip(AppContext.tr("anl_btn_reset_colors"))
        self.lbl_nesting.setText(AppContext.tr("lbl_nesting"))
        # Update Scan/Stop button based on state
        if self.worker and self.worker.isRunning():
            self.btn_scan.setText(AppContext.tr("anl_btn_stop"))
        else:
            self.btn_scan.setText(AppContext.tr("anl_btn_scan"))
            
        # Update Child Widgets
        self.chart.update_ui_text()
        self.summary_table.update_ui_text()
        self.detail_table.update_ui_text()
        # Preview
        if hasattr(self, 'lbl_prev_title'):
            self.lbl_prev_title.setText(AppContext.tr("cln_preview_title"))
        if hasattr(self, 'preview_widget') and hasattr(self.preview_widget, 'update_ui_text'):
            self.preview_widget.update_ui_text()
        
        if hasattr(self, 'btn_info_toggle'):
            self.btn_info_toggle.setText(AppContext.tr("cln_btn_info"))
            
        if hasattr(self, 'drop_zone'):
            self.drop_zone.update_ui_text()
        
        self.update_search_placeholder()
        
        if not self.current_detail_ext:
            if self.full_stats:
                self.detail_table.clear()
                self.detail_table.header().show()
                self.lbl_detail_title.setText(AppContext.tr("anl_lbl_files").upper())
            else:
                self.detail_table.clear()
                self.detail_table.header().hide()
                self.lbl_detail_title.setText(AppContext.tr("anl_msg_idle_details"))
        else:
            count = len(self.full_stats.get(self.current_detail_ext, {}).get('files', []))
            self.lbl_detail_title.setText(f"{AppContext.tr('anl_lbl_files').upper()} ({self.current_detail_ext}: {count})")

    def on_tab_enter(self):
        """Called when switching to this tab. Syncs config from other modules."""
        pass

    def pause_playback(self):
        if hasattr(self, 'preview_widget') and self.preview_widget:
            self.preview_widget.pause_playback()

    def stop_playback(self):
        if hasattr(self, 'preview_widget') and self.preview_widget:
            self.preview_widget.stop_playback()

    def move_selected_files(self, destination_dir):
        if not destination_dir or not os.path.exists(destination_dir):
            self.silent_info(AppContext.tr("anl_toolbar_title"), AppContext.tr("msg_trash_not_set") if "todel" in str(destination_dir) else AppContext.tr("anl_msg_select_folder"))
            return
            
        selected = self.detail_table.get_selected_files()
        if not selected:
            self.silent_info(AppContext.tr("anl_toolbar_title"), AppContext.tr("anl_msg_no_selection"))
            return
            
        moved_pairs = []
        errors = 0
        for src_path in selected:
            if not os.path.exists(src_path): continue
            dest_path = self.get_safe_dest_path(destination_dir, src_path)
            try:
                if smart_move_file(src_path, dest_path):
                    moved_pairs.append((dest_path, src_path))
                else:
                    shutil.move(src_path, dest_path)
                    moved_pairs.append((dest_path, src_path))
            except Exception as e:
                logging.error(f"Failed to move {src_path}: {e}")
                errors += 1
        
        if moved_pairs:
            # Add to local undo history
            if not hasattr(self, 'undo_history'): self.undo_history = []
            self.undo_history.append(moved_pairs)
            self.btn_undo.setEnabled(True)
            
            # Update UI and Memory
            self.remove_paths_from_memory([p[1] for p in moved_pairs])
            
            res_msg = AppContext.tr("anl_msg_move_success").format(len(moved_pairs))
            if errors > 0: res_msg += "\n" + AppContext.tr("anl_errors_count").format(errors)
            self.silent_info(AppContext.tr("anl_toolbar_title"), res_msg)

    def undo_move(self):
        if not hasattr(self, 'undo_history') or not self.undo_history: return
        last_action = self.undo_history.pop()
        
        undone_count = 0
        for current_path, original_path in last_action:
            if os.path.exists(current_path):
                try:
                    os.makedirs(os.path.dirname(original_path), exist_ok=True)
                    shutil.move(current_path, original_path)
                    undone_count += 1
                except Exception as e:
                    logging.error(f"Undo failed for {current_path}: {e}")
        
        self.btn_undo.setEnabled(len(self.undo_history) > 0)
        self.silent_info(AppContext.tr("anl_btn_undo"), AppContext.tr("anl_msg_undone_format").format(undone_count))
        # Trigger full rescan to be safe
        if self.current_scanned_path:
            self.start_analysis(self.current_scanned_path)

    def on_internal_reorder(self, *args):
        # Placeholder for compatibility with Sidebar widgets
        pass

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Backspace:
            if self.btn_nav_back.isEnabled():
                self.navigate_history_back()
            event.accept()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        min_w = int(w * 0.25)
        self.h_splitter.widget(0).setMinimumWidth(min_w)
        self.h_splitter.widget(1).setMinimumWidth(min_w)
        
        h = self.height()
        min_h = int(h * 0.25)
        self.v_splitter.widget(0).setMinimumHeight(min_h)
        if self.detail_container.isVisible():
            self.detail_container.setMinimumHeight(min_h)

    def showEvent(self, event):
        super().showEvent(event)
        w = self.width()
        self.h_splitter.setSizes([w * 2 // 3, w // 3])
        
        # Default vertical split 50/50 (User request)
        # This will apply on first show, then user can resize manually
        if not hasattr(self, "_splitter_initialized"):
            h = self.height()
            self.v_splitter.setSizes([h//2, h//2])
            self._splitter_initialized = True

    def start_analysis(self, path, from_sorter=False, push_history=False, preserve_history=False):
        """
        Starts analysis of a directory.
        :param path: Directory to scan
        :param from_sorter: Boolean, show back button to sorter tab
        :param push_history: If True, pushes CURRENT view path to history before scanning new one.
        :param preserve_history: If True, does NOT clear history. Used when navigating back to a root.
        """
        if not path or not os.path.exists(path): return
        logging.info(f"Analyzer: Starting analysis for {path} (PushHist={push_history}, PresHist={preserve_history})")
        
        if push_history and self.current_view_path:
            self.nav_history.append(self.current_view_path)
        
        if not preserve_history and not push_history:
            # New fresh scan, clear old history
            self.nav_history = [] 
            
        self.current_scanned_path = os.path.normpath(path)
        self.current_view_path = self.current_scanned_path
        self.current_detail_ext = None 
        
        self.path_input.setText(path)
        self.lbl_path_size.setText("")
        self.btn_back_tab.setVisible(from_sorter)
        
        # UI State for Scanning
        self.btn_nav_up.setEnabled(True)
        # Enable back button if there is history
        self.btn_nav_back.setEnabled(len(self.nav_history) > 0)
        self.btn_scan.setEnabled(True)
        self.chart.set_nav_buttons_state(self.btn_nav_back.isEnabled(), True)
        
        # Change Button to STOP
        self.btn_scan.setText(AppContext.tr("anl_btn_stop"))
        self.btn_scan.setStyleSheet("""
            QPushButton { background-color: #dc2626; color: white; font-weight: bold; border-radius: 4px; padding: 6px; }
            QPushButton:hover { background-color: #ef4444; }
        """)
        
        if self.worker: 
            try:
                self.worker.finished_analysis.disconnect() # Disconnect safely
                self.worker.stop()
                self.worker.terminate()
            except Exception as e:
                logging.error(f"Error stopping previous worker: {e}")
            
        self.path_input.setEnabled(False)
        
        self.chart.show_empty_state(AppContext.tr("anl_scanning").format(""), show_back=self.btn_nav_back.isEnabled())
        self.summary_table.setRowCount(0)
        # self.detail_container.hide() - Do not hide anymore, keep visible with placeholder
        
        self.lbl_progress.show()
        self.lbl_progress.setText(AppContext.tr("anl_scanning").format(0))
        
        self.worker = AnalyzerWorker(path)
        self.worker.finished_analysis.connect(self.on_finished)
        self.worker.progress_update.connect(self.update_progress)
        self.worker.start()
        
        # Ensure we have focus for hotkeys
        self.setFocus()

    def update_progress(self, count):
        self.lbl_progress.setText(AppContext.tr("anl_scanning").format(count))

    def on_finished(self, root_node, stats_map):
        logging.info("Analyzer: Scan finished")
        self.path_input.setEnabled(True)
        
        # Reset Button to SCAN
        self.btn_scan.setText(AppContext.tr("anl_btn_scan"))
        self.btn_scan.setStyleSheet("""
            QPushButton { background-color: #15803d; color: white; font-weight: bold; border-radius: 4px; padding: 6px; }
            QPushButton:hover { background-color: #16a34a; }
            QPushButton:disabled { background-color: #333; color: #555; }
        """)
        
        self.lbl_progress.hide()
        
        if not root_node and self.worker.scanned_count == 0:
            self.chart.show_empty_state(AppContext.tr("anl_failed"), show_back=self.btn_nav_back.isEnabled())
            return
        
        try:
            self.full_root_node = root_node 
            self.update_chart_with_node(root_node)
            
            self.full_stats = stats_map
            self.summary_table.populate(stats_map)
            
            # Update search suggestions after scan is fully processed
            self.update_search_completer()
            self.reload_details()
            
            self.setFocus()
        except Exception as e:
            logging.error(f"Analyzer: Error processing finished data: {e}", exc_info=True)

    def update_scan_button_state(self):
        """Updates scan button appearance: green 'Scan' when viewing scanned folder, orange 'Rescan' when navigated away."""
        if not self.current_scanned_path or not self.current_view_path:
            return
        if self.worker and self.worker.isRunning():
            return  # Don't change while scanning
            
        view_norm = os.path.normpath(self.current_view_path)
        scan_norm = os.path.normpath(self.current_scanned_path)
        
        if view_norm == scan_norm:
            # We're viewing the scanned folder — green "Scan"
            self.btn_scan.setText(AppContext.tr("anl_btn_scan"))
            self.btn_scan.setStyleSheet("""
                QPushButton { background-color: #15803d; color: white; font-weight: bold; border-radius: 4px; padding: 6px; }
                QPushButton:hover { background-color: #16a34a; }
                QPushButton:disabled { background-color: #333; color: #555; }
            """)
            self.btn_scan.setToolTip("")
        else:
            # Navigated to a different folder — orange "Rescan"
            self.btn_scan.setText(AppContext.tr("anl_btn_rescan"))
            self.btn_scan.setStyleSheet("""
                QPushButton { background-color: #c2710c; color: white; font-weight: bold; border-radius: 4px; padding: 6px; }
                QPushButton:hover { background-color: #d97706; }
                QPushButton:disabled { background-color: #333; color: #555; }
            """)
            self.btn_scan.setToolTip(AppContext.tr("anl_tip_rescan").format(os.path.basename(scan_norm)))

    def update_search_completer(self):
        """Extracts unique words contextually based on already typed words."""
        if not self.full_stats:
            self.completer.setModel(QStringListModel([]))
            return
            
        current_text = self.txt_filter.text().lower()
        import re
        # Delimiters for filenames: treat everything non-alphanumeric except some essentials as splitters
        delimiters = r'[\s\.\-_\(\)\[\]!@#$%^&+=,;]+'
        
        # Determine our "context" words (all words except the one being currently typed)
        all_typed_words = current_text.split()
        if not current_text.endswith(' ') and len(all_typed_words) > 0:
            context_words = all_typed_words[:-1]
        else:
            context_words = all_typed_words
            
        # 1. Gather files that match current context
        if self.current_detail_ext:
            files_pool = self.full_stats.get(self.current_detail_ext, {}).get('files', [])
        else:
            files_pool = []
            for ext_data in self.full_stats.values():
                files_pool.extend(ext_data.get('files', []))
        
        # Filter pool by context words (AND logic)
        if context_words:
            matched_files = [
                f for f in files_pool
                if all(cw in f['name'].lower() for cw in context_words)
            ]
        else:
            matched_files = files_pool
            
        # 2. Extract unique words from matched files
        words = set()
        for f in matched_files:
            name = f['name'].lower()
            parts = re.split(delimiters, name)
            for part in parts:
                if len(part) >= 2:
                    words.add(part)
        
        # 3. Update model
        # Optimization: if too many words, maybe trim, but for 100k files it should be okay in memory
        sorted_words = sorted(list(words))
        self.completer.setModel(QStringListModel(sorted_words))

    def update_chart_with_node(self, node):
        try:
            self.chart.current_view_node = node
            depth_limit = int(self.cb_depth.currentText())
            self.chart.load_tree(node, depth_limit)
            
            if node and 'path' in node:
                self.path_input.setText(node['path'])
                self.current_view_path = node['path']
                if 'size' in node:
                    from utils_common import format_size
                    self.lbl_path_size.setText(format_size(node['size']))
                else:
                    self.lbl_path_size.setText("")
                
            # Update Chart buttons state
            self.chart.set_nav_buttons_state(self.btn_nav_back.isEnabled(), self.btn_nav_up.isEnabled())
            
            # Update scan button appearance based on navigation state
            self.update_scan_button_state()
        except Exception as e:
            logging.error(f"Analyzer: Error updating chart: {e}", exc_info=True)

    def find_node_by_path(self, target_path, current_node):
        if not current_node: return None
        if os.path.normpath(current_node['path']) == os.path.normpath(target_path):
            return current_node
        
        if 'children' in current_node:
            for child in current_node['children']:
                if child['type'] == 'dir':
                    if os.path.normpath(target_path).startswith(os.path.normpath(child['path'])):
                        res = self.find_node_by_path(target_path, child)
                        if res: return res
        return None

    def on_depth_changed(self):
        if self.chart.current_view_node:
             depth_limit = int(self.cb_depth.currentText())
             self.chart.load_tree(self.chart.current_view_node, depth_limit)

    def toggle_chart_mode(self):
        try:
            if self.chart.chart_mode == 'sunburst':
                self.chart.chart_mode = 'treemap'
                self.btn_chart_mode.setIcon(QIcon(os.path.join(self.icons_dir, "diagram-pie-color.svg")))
                self.btn_chart_mode.setToolTip(AppContext.tr("anl_tip_chart_mode_sunburst"))
            else:
                self.chart.chart_mode = 'sunburst'
                self.btn_chart_mode.setIcon(QIcon(os.path.join(self.icons_dir, "tiles.svg")))
                self.btn_chart_mode.setToolTip(AppContext.tr("anl_tip_chart_mode_treemap"))

            self.chart.refresh_chart()

            w = self.h_splitter.width()
            if self.chart.chart_mode == 'treemap':
                self.h_splitter.setSizes([w * 2 // 3, w // 3])
            else:
                self.h_splitter.setSizes([w // 2, w // 2])
        except Exception as e:
            logging.error(f"Analyzer: Error toggling chart mode: {e}", exc_info=True)

    def browse_folder(self):
        start = self.current_scanned_path if self.current_scanned_path else ""
        d = QFileDialog.getExistingDirectory(self, AppContext.tr("dlg_browse"), start)
        if d: self.start_analysis(d, push_history=True)

    def on_path_entered(self):
        self.start_analysis(self.path_input.text(), push_history=True)

    def on_scan_clicked(self):
        logging.info("Analyzer: Scan/Stop clicked")
        if self.worker and self.worker.isRunning():
            try:
                # Force Stop logic
                self.worker.finished_analysis.disconnect() # Prevent callbacks
                self.worker.progress_update.disconnect()
                self.worker.stop()
                self.worker.terminate()
                self.worker = None
            except Exception as e:
                logging.error(f"Error forcibly stopping worker: {e}")
            
            # Reset UI state
            self.lbl_progress.hide()
            self.btn_scan.setText(AppContext.tr("anl_btn_scan"))
            self.btn_scan.setStyleSheet("""
                QPushButton { background-color: #15803d; color: white; font-weight: bold; border-radius: 4px; padding: 6px; }
                QPushButton:hover { background-color: #16a34a; }
                QPushButton:disabled { background-color: #333; color: #555; }
            """)
            self.btn_scan.setEnabled(True)
            self.path_input.setEnabled(True)
            
            # If we have history, go back immediately
            if self.nav_history:
                # Use QTimer to defer navigation to prevent crash if triggered from scene item
                QTimer.singleShot(0, self.navigate_history_back)
            else:
                self.chart.show_empty_state(AppContext.tr("anl_status_cancelled"), show_back=False)
        else:
            self.start_analysis(self.path_input.text(), push_history=True)

    def on_chart_click(self, node_data):
        if node_data['type'] != 'dir': return
        try:
            self.nav_history.append(self.current_view_path)
            self.btn_nav_back.setEnabled(True)
            self.update_chart_with_node(node_data)
        except Exception as e:
            logging.error(f"Analyzer: Chart click error: {e}", exc_info=True)

    def navigate_history_back(self):
        try:
            if not self.nav_history: return
            prev_path = self.nav_history.pop()
            
            # Update button state early
            self.btn_nav_back.setEnabled(len(self.nav_history) > 0)
            
            # Try to find node in current tree
            node = self.find_node_by_path(prev_path, self.full_root_node)
            if node:
                self.update_chart_with_node(node)
            else:
                logging.warning(f"Analyzer: Could not find node for history path: {prev_path}. Rescanning.")
                # Rescan, preserving the rest of history
                self.start_analysis(prev_path, push_history=False, preserve_history=True) 
        except Exception as e:
            logging.error(f"Analyzer: Error in navigate_history_back: {e}", exc_info=True)
            # Safe reset if crash
            self.nav_history = []
            self.btn_nav_back.setEnabled(False)

    def go_up_level(self):
        try:
            if not self.current_view_path: return
            parent_path = os.path.dirname(self.current_view_path)
            if not parent_path or not os.path.exists(parent_path): return

            target = os.path.normpath(parent_path)
            
            # Try to find node in current tree
            node = self.find_node_by_path(target, self.full_root_node)
            
            if node:
                # We are inside the scanned tree, just navigate up
                self.nav_history.append(self.current_view_path)
                self.btn_nav_back.setEnabled(True)
                self.update_chart_with_node(node)
            else:
                # We are going ABOVE the scanned root. Trigger Auto-Scan of parent.
                logging.info(f"Analyzer: Going up beyond root. Scanning parent: {parent_path}")
                # Save current path to history before jumping up
                self.start_analysis(parent_path, push_history=True)
        except Exception as e:
            logging.error(f"Analyzer: Error in go_up_level: {e}", exc_info=True)

    def open_current_folder(self):
        if self.current_view_path and os.path.exists(self.current_view_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.current_view_path))

    def on_detail_item_clicked(self, item, column):
        """Handle selection in detail tree for preview"""
        # Path is stored in UserRole + 1 in Column 1 (Name column)
        path = item.data(1, Qt.ItemDataRole.UserRole + 1)
        if path and os.path.isfile(path):
            self.preview_widget.load_file(path)
            self.update_file_info(path)

    def toggle_info_panel(self, checked):
        self.info_panel.setVisible(checked)
        
    def update_file_info(self, path):
        if not path or not os.path.exists(path):
            self.info_panel.clear()
            return

        try:
            stat = os.stat(path)
            size_str = format_size(stat.st_size)
            import datetime
            dt_cal = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            dt_cre = datetime.datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
            
            html = f"""<div style='line-height: 1.4; color: #ccc;'>
                <b style='color: #fff; font-size: 13px;'>{os.path.basename(path)}</b><br>
                <span style='color: #888;'>{AppContext.tr("cln_meta_path")}:</span> {os.path.dirname(path)}<br>
                <span style='color: #888;'>{AppContext.tr("cln_meta_size")}:</span> <span style='color: #4ade80;'>{size_str}</span><br>
                <span style='color: #888;'>{AppContext.tr("cln_meta_date")}:</span> {dt_cal}<br>
                <span style='color: #888;'>{AppContext.tr("cln_meta_created")}:</span> {dt_cre}
            </div>"""
            self.info_panel.setHtml(html)
        except Exception as e:
            self.info_panel.setText(f"{AppContext.tr('msg_error_file')}: {e}")

    def on_chart_context_menu(self, data, pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: #2b2b2b; color: white; border: 1px solid #444; padding: 4px; }
            QMenu::item { padding: 5px 20px; border-radius: 4px; }
            QMenu::item:selected { background: #3b82f6; }
            QMenu::item:disabled { color: #555; }
            QMenu::separator { height: 1px; background: #444; margin: 4px 0; }
        """)

        # Bucket handling (group of small folders/files)
        if data['type'] in ['dir_group', 'file_group_ext', 'file_group_misc']:
            path_to_open = data['path']
            a_explorer = QAction(f"📂 {AppContext.tr('menu_open_explorer')}", self)
            a_explorer.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path_to_open)))
            menu.addAction(a_explorer)

        elif data['type'] == 'dir':
            path_to_open = data['path']
            a_explorer = QAction(f"📂 {AppContext.tr('menu_open_explorer')}", self)
            a_explorer.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path_to_open)))
            menu.addAction(a_explorer)

            menu.addSeparator()

            name_dis = AppContext.tr('anl_ctx_disassemble_with_switch')
            a_disassemble = QAction(name_dis, self)
            a_disassemble.setToolTip(AppContext.tr("anl_ctx_disassemble_tip"))
            a_disassemble.setStatusTip(AppContext.tr("anl_ctx_disassemble_tip"))
            a_disassemble.triggered.connect(lambda: self.disassemble_folder(path_to_open))
            menu.addAction(a_disassemble)

            a_permanent_inbox = QAction(AppContext.tr("anl_ctx_set_sorter_inbox"), self)
            a_permanent_inbox.setToolTip(AppContext.tr("anl_ctx_set_sorter_inbox_tip"))
            a_permanent_inbox.setStatusTip(AppContext.tr("anl_ctx_set_sorter_inbox_tip"))
            a_permanent_inbox.triggered.connect(lambda: self.set_sorter_permanent_inbox(path_to_open))
            menu.addAction(a_permanent_inbox)

            a_cleaner_dups = QAction(AppContext.tr("anl_ctx_search_dupes"), self)
            a_cleaner_dups.triggered.connect(lambda: self.analyze_duplicates_in_cleaner(path_to_open))
            menu.addAction(a_cleaner_dups)

        elif data['type'] == 'file':
            path = data['path']
            a_open_file = QAction(f"📄 {AppContext.tr('anl_ctx_open_file')}", self)
            a_open_file.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
            menu.addAction(a_open_file)

            a_reveal = QAction(f"🔍 {AppContext.tr('anl_ctx_reveal')}", self)
            a_reveal.triggered.connect(lambda: self.reveal_file(path))
            menu.addAction(a_reveal)

            a_analyze_parent = QAction(f"📊 {AppContext.tr('anl_ctx_analyze_parent')}", self)
            a_analyze_parent.triggered.connect(lambda: self.analyze_parent_folder(path))
            menu.addAction(a_analyze_parent)

            menu.addSeparator()

            a_delete = QAction(AppContext.tr("anl_ctx_delete_trash"), self)
            a_delete.triggered.connect(lambda: self.handle_single_action(path, 'delete'))
            menu.addAction(a_delete)

            dest_dir = self.drop_zone.get_path()
            has_dest = bool(dest_dir and os.path.exists(dest_dir))
            move_sel_txt = AppContext.tr("anl_ctx_move_selected_dir")
            if has_dest:
                move_sel_txt += f" ({os.path.basename(dest_dir)})"
            a_move_sel = QAction(move_sel_txt, self)
            a_move_sel.setEnabled(has_dest)
            a_move_sel.triggered.connect(lambda: self.move_single_file_to_selected(path))
            menu.addAction(a_move_sel)

            a_move_to = QAction(AppContext.tr("anl_ctx_move_to_prompt"), self)
            a_move_to.triggered.connect(lambda: self.move_single_file_to(path))
            menu.addAction(a_move_to)

            ext = os.path.splitext(path)[1].lower().replace('.', '')
            shell = self.window()
            if shell:
                video_exts = {'mp4', 'avi', 'mov', 'mkv', 'webm', 'wmv', 'flv'}
                audio_exts = {'mp3', 'wav', 'flac', 'ogg', 'm4a', 'aac', 'wma'}
                image_exts = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'tiff'}

                if ext in video_exts:
                    menu.addSeparator()
                    if hasattr(shell, 'send_to_video_editor'):
                        a_editor = QAction(AppContext.tr("anl_ctx_edit_video"), self)
                        a_editor.triggered.connect(lambda: shell.send_to_video_editor(path))
                        menu.addAction(a_editor)
                    if hasattr(shell, 'send_to_video_converter'):
                        a_conv = QAction(AppContext.tr("anl_ctx_convert_video"), self)
                        a_conv.triggered.connect(lambda: shell.send_to_video_converter([path]))
                        menu.addAction(a_conv)
                elif ext in audio_exts:
                    if hasattr(shell, 'send_to_audio_converter'):
                        menu.addSeparator()
                        a_conv = QAction(AppContext.tr("anl_ctx_convert_audio"), self)
                        a_conv.triggered.connect(lambda: shell.send_to_audio_converter([path]))
                        menu.addAction(a_conv)
                elif ext in image_exts:
                    if hasattr(shell, 'send_to_image_converter'):
                        menu.addSeparator()
                        a_conv = QAction(AppContext.tr("anl_ctx_convert_image"), self)
                        a_conv.triggered.connect(lambda: shell.send_to_image_converter([path]))
                        menu.addAction(a_conv)

        menu.exec(pos)

    def disassemble_folder(self, folder_path):
        if not folder_path or not os.path.exists(folder_path):
            return
        shell = self.window()
        if shell and hasattr(shell, "sorter_tab") and hasattr(shell, "switch_tab"):
            logging.info(f"Analyzer: Requesting Sorter disassembly for {folder_path}")
            shell.sorter_tab.set_session_inbox(folder_path)
            shell.switch_tab(0)

    def reveal_file(self, path):
        try:
            if not os.path.exists(path): return
            from utils_common import reveal_in_explorer
            reveal_in_explorer(path)
        except Exception as e:
            logging.error(f"Failed to reveal file {path}: {e}", exc_info=True)

    def analyze_parent_folder(self, file_path):
        if not file_path:
            return
        try:
            parent_path = os.path.normpath(os.path.dirname(file_path))
            if not os.path.exists(parent_path):
                return
                
            node = None
            if hasattr(self, 'full_root_node') and self.full_root_node:
                node = self.find_node_by_path(parent_path, self.full_root_node)
                
            if node:
                self.nav_history.append(self.current_view_path)
                self.btn_nav_back.setEnabled(True)
                self.update_chart_with_node(node)
            else:
                self.start_analysis(parent_path, push_history=True)
        except Exception as e:
            logging.error(f"Analyzer: Error in analyze_parent_folder: {e}", exc_info=True)
    def clear_filter(self):
        self.txt_filter.clear()
        # No heavy reload here to prevent lag as per user request

    def on_completer_activated(self, text):
        """Handle selection of a word from autocomplete."""
        current_text = self.txt_filter.text()
        cursor_pos = self.txt_filter.cursorPosition()
        
        # Find where the current word starts
        text_before = current_text[:cursor_pos]
        import re
        words_before = re.split(r'\s+', text_before.rstrip())
        
        if len(words_before) > 0 and not text_before.endswith(' '):
            # Replace the last word
            words_before[-1] = text
            new_text_before = " ".join(words_before) + " "
        else:
            # Just append
            new_text_before = text_before + text + " "
            
        new_text = new_text_before + current_text[cursor_pos:].lstrip()
        self.txt_filter.setText(new_text)
        self.txt_filter.setCursorPosition(len(new_text_before))
        
        # Auto-trigger search
        self.reload_details()

    def on_filter_text_changed(self, text):
        """Update completer model contextually or handle empty state."""
        # 1. Update clear button visibility
        self.btn_clear_filter.setVisible(bool(text.strip()))
        
        # 2. Update completion prefix (CRITICAL for multi-word support)
        # If we skip this, completer compares the WHOLE STRING with model items
        cursor_pos = self.txt_filter.cursorPosition()
        text_before = text[:cursor_pos]
        current_word = text_before.split()[-1] if text_before.strip() else ""
        if text_before.endswith(' '): current_word = "" # New word starting
        
        self.completer.setCompletionPrefix(current_word)
        
        # 3. Update completer model based on context (already typed words)
        if hasattr(self, '_completer_timer'):
            self._completer_timer.stop()
        else:
            self._completer_timer = QTimer()
            self._completer_timer.setSingleShot(True)
            self._completer_timer.timeout.connect(self._update_completer_and_show)
            
        self._completer_timer.start(100) # Small debounce to avoid lag
    
    def _update_completer_and_show(self):
        """Update model and force popup to show."""
        self.update_search_completer()
        
        # Force popup to show if there's a valid prefix and model has items
        prefix = self.completer.completionPrefix()
        if prefix and len(prefix) >= 1:  # Show after 1 character
            model = self.completer.model()
            if model and model.rowCount() > 0:
                # Explicitly show popup at the correct position
                rect = self.txt_filter.cursorRect()
                rect.setWidth(self.completer.popup().sizeHintForColumn(0) + 
                             self.completer.popup().verticalScrollBar().sizeHint().width())
                self.completer.complete(rect)

    def show_details(self, ext):
        # Support empty string for "Deselect" mode
        self.current_detail_ext = ext
        self.update_search_placeholder()
        self.reload_details()
        self.detail_container.show()
        # Only force initial 50/50 size if it's completely hidden
        if self.v_splitter.sizes()[1] <= 1: 
             h = self.v_splitter.height()
             self.v_splitter.setSizes([h // 2, h // 2])

    def reload_details(self):
        if not self.full_stats:
            self.lbl_detail_title.setText(AppContext.tr("anl_msg_idle_details"))
            self.detail_table.clear()
            self.detail_table.header().hide()
            return
            
        query = self.txt_filter.text().strip().lower()
        
        # Guard: If No category and No filter -> Don't load anything (prevent hang)
        if not self.current_detail_ext and not query:
            self.lbl_detail_title.setText(AppContext.tr("anl_lbl_files").upper())
            self.detail_table.clear()
            self.detail_table.header().show()
            self.update_search_placeholder()
            return

        # 1. Gather files based on current category or global view
        if self.current_detail_ext:
            files = self.full_stats.get(self.current_detail_ext, {}).get('files', []).copy()
            cat_name = self.current_detail_ext
        else:
            files = []
            for ext_data in self.full_stats.values():
                files.extend(ext_data.get('files', []))
            cat_name = "ВСЕ ФАЙЛЫ" if AppContext.LANG == "RU" else "ALL FILES"

        # 2. Smart Text Filter (Multi-word search)
        if query:
            search_words = query.split()
            files = [
                f for f in files 
                if all(word in f['name'].lower() for word in search_words)
            ]

        # 3. Update UI Table
        group_by = self.btn_group_dir.isChecked()
        title = f"{AppContext.tr('anl_lbl_files').upper()}: {cat_name} ({len(files)})"
        if query:
            title += f" [🔍 {query}]"
        
        self.lbl_detail_title.setText(title)
        self.detail_table.load_files(files, group_by_dir=group_by)
        self.update_action_buttons()

    def silent_confirm(self, title, msg):
        """Silent confirmation box without Windows sounds."""
        mb = QMessageBox(self)
        mb.setWindowTitle(title)
        mb.setText(msg)
        mb.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        mb.setDefaultButton(QMessageBox.StandardButton.No)
        # Avoid setIcon to prevent sounds. We could use iconPixmap if needed.
        return mb.exec() == QMessageBox.StandardButton.Yes

    def silent_info(self, title, msg):
        """Silent information box without Windows sounds."""
        mb = QMessageBox(self)
        mb.setWindowTitle(title)
        mb.setText(msg)
        mb.setStandardButtons(QMessageBox.StandardButton.Ok)
        mb.exec()

    def on_dest_path_changed(self, path):
        self.update_action_buttons()

    def on_select_all_clicked(self):
        self.detail_table.select_all(True)
        self.update_action_buttons()

    def on_select_none_clicked(self):
        self.detail_table.select_all(False)
        self.update_action_buttons()

    def update_action_buttons(self, *args):
        selected = self.detail_table.get_selected_files()
        has_selection = bool(selected)
        self.btn_delete_files.setEnabled(has_selection)
        self.btn_move_to.setEnabled(has_selection)
        dest_dir = self.drop_zone.get_path()
        self.btn_move_files.setEnabled(has_selection and bool(dest_dir))

    def browse_dest_folder(self):
        d = QFileDialog.getExistingDirectory(self, AppContext.tr("dlg_browse"))
        if d: self.drop_zone.set_path(d)

    def handle_single_action(self, path, action):
        if action == 'delete':
            from PyQt6.QtWidgets import QDialog
            from ui_dialogs_generic import FileDeletionConfirmDialog
            dlg = FileDeletionConfirmDialog([path], self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                        self.remove_paths_from_memory([path])
                        msg = f"{AppContext.tr('anl_delete_success')}.\n\n{AppContext.tr('anl_rescan_recommended')}"
                        self.silent_info(AppContext.tr("anl_toolbar_title"), msg)
                except Exception as e:
                    logging.error(f"Failed to delete {path}: {e}")
                    self.silent_info(AppContext.tr("anl_toolbar_title"), AppContext.tr("anl_err_delete").format(e))
        elif action == 'move':
            dest_dir = self.drop_zone.get_path()
            if not dest_dir or not os.path.exists(dest_dir):
                self.silent_info(AppContext.tr("anl_toolbar_title"), AppContext.tr("anl_msg_select_dest"))
                return
            
            dest_path = self.get_safe_dest_path(dest_dir, path)
            try:
                if smart_move_file(path, dest_path):
                    self.remove_paths_from_memory([path])
                    msg = f"{AppContext.tr('anl_move_success')}.\n\n{AppContext.tr('anl_rescan_recommended')}"
                    self.silent_info(AppContext.tr("anl_toolbar_title"), msg)
                else:
                    shutil.move(path, dest_path)
                    self.remove_paths_from_memory([path])
                    msg = f"{AppContext.tr('anl_move_success')}.\n\n{AppContext.tr('anl_rescan_recommended')}"
                    self.silent_info(AppContext.tr("anl_toolbar_title"), msg)
            except Exception as e:
                logging.error(f"Failed to move {path}: {e}")
                self.silent_info(AppContext.tr("anl_toolbar_title"), AppContext.tr("anl_err_move").format(e))

    def on_delete_clicked(self):
        selected = self.detail_table.get_selected_files()
        if not selected:
            self.silent_info(AppContext.tr("anl_toolbar_title"), AppContext.tr("anl_msg_no_selection"))
            return
            
        from PyQt6.QtWidgets import QDialog
        from ui_dialogs_generic import FileDeletionConfirmDialog
        dlg = FileDeletionConfirmDialog(selected, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            removed = []
            errors = 0
            for path in selected:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                        removed.append(path)
                except Exception as e:
                    logging.error(f"Failed to delete {path}: {e}")
                    errors += 1
            
            if removed or errors > 0:
                self.remove_paths_from_memory(removed)
                res_msg = AppContext.tr("anl_processed_files").format(len(removed))
                if errors > 0:
                    res_msg += f"\n{AppContext.tr('anl_errors_count').format(errors)}"
                res_msg += f"\n\n{AppContext.tr('anl_rescan_recommended')}"
                self.silent_info(AppContext.tr("anl_toolbar_title"), res_msg)

    def on_move_to_clicked(self):
        selected = self.detail_table.get_selected_files()
        if not selected:
            self.silent_info(AppContext.tr("anl_toolbar_title"), AppContext.tr("anl_msg_no_selection"))
            return

        # 1. Определяем начальную директорию
        start = ""
        if hasattr(self, 'last_move_to_dir') and self.last_move_to_dir and os.path.exists(self.last_move_to_dir):
            start = self.last_move_to_dir
        else:
            shell = self.window()
            if shell and hasattr(shell, "sorter_tab"):
                sorter = shell.sorter_tab
                if hasattr(sorter, "SORT_DIR") and sorter.SORT_DIR and os.path.exists(sorter.SORT_DIR):
                    start = sorter.SORT_DIR
            
            if not start:
                import sys
                if getattr(sys, 'frozen', False):
                    start = os.path.dirname(sys.executable)
                else:
                    start = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        # 2. Открываем QFileDialog
        title = AppContext.tr("anl_ctx_move_to") if AppContext.tr("anl_ctx_move_to") else "Переместить в..."
        d = QFileDialog.getExistingDirectory(self, title, start)
        if d:
            # Запоминаем путь в рамках сессии
            self.last_move_to_dir = d
            # Перемещаем отмеченные галочками файлы
            self.move_selected_files(d)

    def on_move_clicked(self):
        dest_dir = self.drop_zone.get_path()
        if not dest_dir or not os.path.exists(dest_dir):
            self.silent_info(AppContext.tr("anl_toolbar_title"), AppContext.tr("anl_msg_select_dest"))
            return
            
        selected = self.detail_table.get_selected_files()
        if not selected:
            self.silent_info(AppContext.tr("anl_toolbar_title"), AppContext.tr("anl_msg_no_selection"))
            return
            
        moved = []
        errors = 0
        for path in selected:
            if not os.path.exists(path): continue
            dest_path = self.get_safe_dest_path(dest_dir, path)
                
            try:
                if smart_move_file(path, dest_path):
                    moved.append(path)
                else:
                    shutil.move(path, dest_path)
                    moved.append(path)
            except Exception as e:
                logging.error(f"Failed to move {path} to {dest_path}: {e}")
                errors += 1
        
        if moved or errors > 0:
            self.remove_paths_from_memory(moved)
            res_msg = AppContext.tr("anl_msg_move_success").format(len(moved))
            if errors > 0:
                res_msg += f"\n{AppContext.tr('anl_errors_count').format(errors)}"
            res_msg += f"\n\n{AppContext.tr('anl_rescan_recommended')}"
            self.silent_info(AppContext.tr("anl_toolbar_title"), res_msg)

    def get_safe_dest_path(self, dest_dir, src_path):
        dest_path = os.path.join(dest_dir, os.path.basename(src_path))
        base, ext = os.path.splitext(dest_path)
        counter = 1
        while os.path.exists(dest_path):
            dest_path = f"{base}_{counter}{ext}"
            counter += 1
        return dest_path

    def remove_paths_from_memory(self, paths):
        """Optimized update: removes paths from memory structures and updates UI."""
        if not paths: return
        
        path_set = set(os.path.normpath(p) for p in paths)
        
        # 1. Update full_stats
        for ext, data in self.full_stats.items():
            initial_count = len(data['files'])
            data['files'] = [f for f in data['files'] if os.path.normpath(f['path']) not in path_set]
            if len(data['files']) != initial_count:
                # Recalculate size
                data['size'] = sum(f['size'] for f in data['files'])
                data['count'] = len(data['files'])

        # 2. Update full_root_node recursively
        def remove_from_node(node):
            if 'children' not in node: return 0
            
            removed_size = 0
            new_children = []
            for child in node['children']:
                if child['type'] == 'file':
                    if os.path.normpath(child['path']) in path_set:
                        removed_size += child['size']
                    else:
                        new_children.append(child)
                else:
                    # It's a directory
                    child_removed = remove_from_node(child)
                    removed_size += child_removed
                    new_children.append(child)
            
            node['children'] = new_children
            node['size'] -= removed_size
            return removed_size

        remove_from_node(self.full_root_node)

        # 3. Refresh UI
        self.summary_table.populate(self.full_stats)
        if self.chart.current_view_node:
            # Find the same node in updated tree or use root
            updated_node = self.find_node_by_path(self.chart.current_view_node['path'], self.full_root_node)
            if updated_node:
                self.update_chart_with_node(updated_node)
            else:
                self.update_chart_with_node(self.full_root_node)
        
        self.reload_details()

    def on_chart_file_clicked(self, file_data):
        path = file_data.get('path', '')
        if not path or not os.path.exists(path):
            return
        self.preview_widget.load_file(path)
        self.update_file_info(path)
        
        self.detail_table.select_file_row(path)
        self.chart.highlight_file_on_chart(path)
        
        ext = os.path.splitext(file_data.get('name', ''))[1]
        self.summary_table.highlight_ext_row(ext)

    def on_summary_row_hovered(self, ext):
        self.chart.highlight_by_ext(ext)

    def on_detail_row_hovered(self, path):
        self.chart.set_hovered_file_on_chart(path)

    def on_chart_slice_hovered(self, data):
        active_item = getattr(self.chart, 'hovered_slice_item', None)
        active_data = active_item.data if active_item else data
        
        if active_data:
            t = active_data.get('type')
            ext = ""
            if t == 'file':
                ext = os.path.splitext(active_data.get('name', ''))[1]
            elif t == 'file_group_ext':
                ext = active_data.get('ext', '')
                
            if ext:
                self.summary_table.highlight_ext_row(ext)
            else:
                self._highlight_selected_ext_or_clear()
                
            if t == 'file':
                self.detail_table.highlight_file_row(active_data.get('path', ''))
            else:
                self.detail_table.highlight_file_row("")
        else:
            self._highlight_selected_ext_or_clear()
            self.detail_table.highlight_file_row("")

    def _highlight_selected_ext_or_clear(self):
        selected_path = getattr(self.chart, 'selected_file_path', '')
        if selected_path and os.path.exists(selected_path):
            ext = os.path.splitext(selected_path)[1]
            self.summary_table.highlight_ext_row(ext)
        else:
            self.summary_table.highlight_ext_row("")

    def on_detail_selection_changed(self):
        selected_items = self.detail_table.selectedItems()
        if not selected_items:
            self.chart.highlight_file_on_chart("")
            self.summary_table.highlight_ext_row("")
            return
        item = selected_items[0]
        path = item.data(1, Qt.ItemDataRole.UserRole + 1)
        if path:
            self.chart.highlight_file_on_chart(path)
            ext = os.path.splitext(path)[1]
            self.summary_table.highlight_ext_row(ext)
        else:
            self.chart.highlight_file_on_chart("")
            self.summary_table.highlight_ext_row("")

    def move_single_file_to(self, path):
        if not path or not os.path.exists(path):
            return
            
        start = ""
        if hasattr(self, 'last_move_to_dir') and self.last_move_to_dir and os.path.exists(self.last_move_to_dir):
            start = self.last_move_to_dir
        else:
            shell = self.window()
            if shell and hasattr(shell, "sorter_tab"):
                sorter = shell.sorter_tab
                if hasattr(sorter, "SORT_DIR") and sorter.SORT_DIR and os.path.exists(sorter.SORT_DIR):
                    start = sorter.SORT_DIR
            
            if not start:
                import sys
                if getattr(sys, 'frozen', False):
                    start = os.path.dirname(sys.executable)
                else:
                    start = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        title = AppContext.tr("anl_ctx_move_to") if AppContext.tr("anl_ctx_move_to") else "Переместить в..."
        d = QFileDialog.getExistingDirectory(self, title, start)
        if d:
            self.last_move_to_dir = d
            self.move_single_file_to_dir(path, d)

    def move_single_file_to_selected(self, path):
        dest_dir = self.drop_zone.get_path()
        if not dest_dir or not os.path.exists(dest_dir):
            self.silent_info(AppContext.tr("anl_toolbar_title"), AppContext.tr("anl_msg_select_dest"))
            return
        self.move_single_file_to_dir(path, dest_dir)

    def move_single_file_to_dir(self, src_path, destination_dir):
        if not os.path.exists(src_path):
            return
        dest_path = self.get_safe_dest_path(destination_dir, src_path)
        try:
            if smart_move_file(src_path, dest_path):
                moved = (dest_path, src_path)
            else:
                shutil.move(src_path, dest_path)
                moved = (dest_path, src_path)
                
            if not hasattr(self, 'undo_history'):
                self.undo_history = []
            self.undo_history.append([moved])
            self.btn_undo.setEnabled(True)
            
            self.remove_paths_from_memory([src_path])
            self.silent_info(AppContext.tr("anl_toolbar_title"), AppContext.tr("anl_msg_file_moved").format(destination_dir))
        except Exception as e:
            logging.error(f"Failed to move {src_path} to {destination_dir}: {e}")
            self.silent_info(AppContext.tr("anl_toolbar_title"), AppContext.tr("anl_err_move").format(e))

    def analyze_duplicates_in_cleaner(self, path):
        if not path or not os.path.exists(path):
            return
        shell = self.window()
        if not shell or not hasattr(shell, 'cleaner_tab'):
            return
        cleaner = shell.cleaner_tab
        cleaner.clear_folders()
        cleaner.add_folder_path(path)
        if hasattr(shell, 'switch_tab'):
            shell.switch_tab(2)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(300, cleaner.start_scan)

    def set_sorter_permanent_inbox(self, path):
        if not path or not os.path.exists(path):
            return
        shell = self.window()
        if shell and hasattr(shell, "sorter_tab"):
            shell.sorter_tab.set_permanent_inbox(path)
