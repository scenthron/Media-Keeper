import os
import time
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QProgressBar, QDialog, QSplitter, QScrollArea, QTabWidget,
    QDoubleSpinBox, QCheckBox, QMessageBox, QSlider
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer, QThread
from PyQt6.QtGui import QIcon, QPixmap

from config import AppContext, APP_DESIGN
from modules.shared import ui_theme
from ui_widgets_base import DropZoneWidget
from ui_dialogs_generic import silent_info, silent_warning, silent_question
from ..workers import STAGE_SCANNING, STAGE_ANALYSIS
from ..ai_facade import (
    AiServiceFacade, AiSearchRequest, AiTaskType, AiTarget,
    AiSearchResponse, AiMatchFile, AiGroup
)
from ..logic_ai import AiEngine
from ..logic_ai_cache import AiCacheManager
from ..logic_ai_classifier import AiClassifier, load_ai_settings, save_ai_settings, get_ai_assets_dir
from ..logic_ai_tags import parse_multi_tags, parse_tag_weight

from .ui_samples_panel import (
    AiSamplesPanel, SearchTextEdit, AiFolderDropContainer, QCheckBoxCustom
)
from .ui_results_view import AiResultsView
from .logic_ai_actions import AiActionsController


class AiModelDownloaderThread(QThread):
    progress_signal = pyqtSignal(str, int, int)
    finished_signal = pyqtSignal(bool)

    def __init__(self, ai_engine, parent=None):
        super().__init__(parent)
        self.ai_engine = ai_engine
        self._is_stopped = False

    def stop(self):
        self._is_stopped = True

    def run(self):
        def on_progress(filename, downloaded, total_size):
            if not self._is_stopped:
                self.progress_signal.emit(filename, downloaded, total_size)

        success = self.ai_engine.download_models(
            progress_callback=on_progress,
            stop_checker=lambda: self._is_stopped
        )
        self.finished_signal.emit(success)


class AiClassificationTab(QWidget):
    """
    Главный координатор вкладки ИИ-поиска и классификации медиафайлов.
    Собирает панель образцов, каталоги сканирования, параметры ИИ, результаты и действия.
    """
    scan_started = pyqtSignal()
    scan_finished = pyqtSignal()
    file_selected = pyqtSignal(str)

    def __init__(self, cleaner_module, parent=None):
        super().__init__(parent)
        self.cleaner = cleaner_module

        # Бэкенд
        self.ai = AiEngine()
        self.cache = AiCacheManager()
        self.classifier = AiClassifier(self.cache, self.ai)

        self.active_worker = None
        self.ai_filter_config = None
        self._is_ok = True

        self._init_ui()
        self.reload_groups()
        self.check_models_status()

    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 1. Экран-заглушка для скачивания моделей
        self._init_download_placeholder()

        # 2. Главный контент вкладки
        self.main_content_widget = QWidget(self)
        content_layout = QVBoxLayout(self.main_content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.setHandleWidth(2)
        self.main_splitter.setStyleSheet(ui_theme.STYLE_SPLITTER)

        # Верхняя панель настроек (3 колонки)
        self._init_top_settings()
        self.main_splitter.addWidget(self.top_settings)

        # Нижняя панель (прогресс, статистика, панель действий, таблица и превью)
        self._init_bottom_panel()
        self.main_splitter.addWidget(self.bottom_container)

        self.main_splitter.setSizes([220, 400])
        content_layout.addWidget(self.main_splitter, 1)
        self.main_layout.addWidget(self.main_content_widget, 1)

    def _init_download_placeholder(self):
        self.download_placeholder = QFrame()
        self.download_placeholder.setStyleSheet("QFrame { background-color: #1e1e1e; border: none; }")

        ph_layout = QVBoxLayout(self.download_placeholder)
        ph_layout.setContentsMargins(40, 40, 40, 40)
        ph_layout.setSpacing(18)
        ph_layout.addStretch(1)

        lbl_brain = QLabel("🧠")
        lbl_brain.setStyleSheet("font-size: 48px; background: transparent; border: none;")
        lbl_brain.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_layout.addWidget(lbl_brain)

        self.lbl_title_placeholder = QLabel(AppContext.tr("cln_ai_models_init_title"))
        lbl_title = self.lbl_title_placeholder
        lbl_title.setStyleSheet("font-weight: bold; color: white; font-size: 16px; background: transparent; border: none;")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_layout.addWidget(lbl_title)

        self.lbl_desc_placeholder = QLabel(AppContext.tr("cln_ai_models_init_desc"))
        lbl_desc = self.lbl_desc_placeholder
        lbl_desc.setWordWrap(True)
        lbl_desc.setFixedWidth(400)
        lbl_desc.setStyleSheet("color: #aaa; font-size: 12px; background: transparent; border: none; line-height: 1.5;")
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)

        desc_layout = QHBoxLayout()
        desc_layout.addStretch(1)
        desc_layout.addWidget(lbl_desc)
        desc_layout.addStretch(1)
        ph_layout.addLayout(desc_layout)

        self.btn_download_models = QPushButton(AppContext.tr("cln_ai_btn_download_models"))
        self.btn_download_models.setFixedSize(200, 36)
        self.btn_download_models.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_download_models.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6; 
                color: white; 
                border: none; 
                border-radius: 4px; 
                font-weight: bold; 
                font-size: 13px;
            }
            QPushButton:hover { background-color: #2563eb; }
            QPushButton:disabled { background-color: #333; color: #666; }
        """)
        self.btn_download_models.clicked.connect(self.start_placeholder_download)

        self.btn_stop_download = QPushButton(AppContext.tr("cln_ai_btn_stop_download"))
        self.btn_stop_download.setFixedSize(120, 36)
        self.btn_stop_download.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stop_download.setStyleSheet("""
            QPushButton {
                background-color: #ef4444; 
                color: white; 
                border: none; 
                border-radius: 4px; 
                font-weight: bold; 
                font-size: 13px;
            }
            QPushButton:hover { background-color: #dc2626; }
            QPushButton:disabled { background-color: #333; color: #666; }
        """)
        self.btn_stop_download.hide()
        self.btn_stop_download.clicked.connect(self.stop_placeholder_download)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        btn_layout.addWidget(self.btn_download_models)
        btn_layout.addWidget(self.btn_stop_download)
        btn_layout.addStretch(1)
        ph_layout.addLayout(btn_layout)

        self.placeholder_progress = QProgressBar()
        self.placeholder_progress.setFixedSize(300, 16)
        self.placeholder_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #444;
                border-radius: 4px;
                background-color: #111;
                text-align: center;
                color: white;
                font-size: 10px;
            }
            QProgressBar::chunk { background-color: #3b82f6; }
        """)
        self.placeholder_progress.hide()

        progress_layout = QHBoxLayout()
        progress_layout.addStretch(1)
        progress_layout.addWidget(self.placeholder_progress)
        progress_layout.addStretch(1)
        ph_layout.addLayout(progress_layout)

        self.placeholder_status = QLabel("")
        self.placeholder_status.setStyleSheet("color: #ef4444; font-size: 11px; background: transparent; border: none;")
        self.placeholder_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_layout.addWidget(self.placeholder_status)
        ph_layout.addStretch(1)

        self.main_layout.addWidget(self.download_placeholder)

    def _init_top_settings(self):
        self.top_settings = QFrame()
        self.top_settings.setMinimumHeight(220)
        self.top_settings.setMaximumHeight(600)
        self.top_settings.setStyleSheet("background-color: #1e1e1e; border-bottom: 1px solid #2d2d2d;")
        top_layout = QHBoxLayout(self.top_settings)
        top_layout.setContentsMargins(15, 6, 15, 6)
        top_layout.setSpacing(12)

        # Колонка 1: Панель образцов, тегов и авто-поиска
        self.samples_panel = AiSamplesPanel(self.classifier, self)
        self.samples_panel.mode_changed.connect(lambda idx: self.update_scan_button_state())
        self.samples_panel.search_state_changed.connect(self.update_scan_button_state)
        self.samples_panel.text_search_requested.connect(lambda query: self.toggle_scan(text_query=query))
        top_layout.addWidget(self.samples_panel, 1)

        # Колонка 2: Каталоги для поиска
        col_dirs = QVBoxLayout()
        col_dirs.setContentsMargins(0, 0, 0, 0)
        col_dirs.setSpacing(4)

        dirs_header = QHBoxLayout()
        self.lbl_dirs_title = QLabel(AppContext.tr("cln_ai_dirs_title"))
        dirs_title = self.lbl_dirs_title
        dirs_title.setStyleSheet("font-weight: bold; color: #888; font-size: 11px; font-family: 'Segoe UI';")
        dirs_header.addWidget(dirs_title)
        dirs_header.addStretch()
        col_dirs.addLayout(dirs_header)

        scroll_dirs = QScrollArea()
        scroll_dirs.setWidgetResizable(True)
        scroll_dirs.setStyleSheet("QScrollArea { border: 1px solid #333; background-color: #111; border-radius: 4px; }")

        self.sources_list_widget_ai = AiFolderDropContainer()
        self.sources_list_widget_ai.setStyleSheet("background-color: #111111;")
        self.sources_list_widget_ai.folder_dropped.connect(self.cleaner.add_folder_path)
        if hasattr(self.cleaner, 'add_folder_paths'):
            self.sources_list_widget_ai.files_dropped.connect(self.cleaner.add_folder_paths)

        dirs_container_layout = QVBoxLayout(self.sources_list_widget_ai)
        dirs_container_layout.setContentsMargins(5, 5, 5, 5)
        dirs_container_layout.setSpacing(4)
        dirs_container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.folder_list_layout_ai = QVBoxLayout()
        self.folder_list_layout_ai.setContentsMargins(0, 0, 0, 0)
        self.folder_list_layout_ai.setSpacing(4)
        self.folder_list_layout_ai.setAlignment(Qt.AlignmentFlag.AlignTop)
        dirs_container_layout.addLayout(self.folder_list_layout_ai)

        self.drop_zone_ai = DropZoneWidget()
        self.drop_zone_ai.clicked.connect(self.cleaner.add_folder)
        self.drop_zone_ai.folder_dropped.connect(self.cleaner.add_folder_path)
        if hasattr(self.drop_zone_ai, 'files_dropped') and hasattr(self.cleaner, 'add_folder_paths'):
            self.drop_zone_ai.files_dropped.connect(self.cleaner.add_folder_paths)
        self.drop_zone_ai.clear_default_requested.connect(self.cleaner.clear_folders)
        self.drop_zone_ai.btn_clear.show()
        self.drop_zone_ai.setStyleSheet(self.drop_zone_ai.styleSheet() + "margin: 0px; padding: 2px;")
        dirs_container_layout.addWidget(self.drop_zone_ai)

        scroll_dirs.setWidget(self.sources_list_widget_ai)
        col_dirs.addWidget(scroll_dirs)

        # Фильтр типов файлов
        filter_layout_ai = QHBoxLayout()
        filter_layout_ai.setContentsMargins(0, 0, 0, 0)
        filter_layout_ai.setSpacing(8)

        from ..ui_panels import load_svg_icon
        icons_dir_ai = AppContext.find_resource_dir("icons") or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "icons")

        self.btn_filter_ai = QPushButton(AppContext.tr("cln_btn_scan_types"))
        self.btn_filter_ai.setIcon(load_svg_icon(os.path.join(icons_dir_ai, "loupe-color.svg"), QSize(16, 16)))
        self.btn_filter_ai.setIconSize(QSize(16, 16))
        self.btn_filter_ai.setFixedHeight(36)
        self.btn_filter_ai.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_filter_ai.setStyleSheet("QPushButton { background-color: #444; color: #fff; border: 1px solid #666; padding: 0 10px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #555; color: white; border-color: #888; }")
        self.btn_filter_ai.clicked.connect(self.open_filter_dialog_ai)

        self.lbl_filter_status_ai = QLabel(AppContext.tr("cln_filter_all"))
        self.lbl_filter_status_ai.setStyleSheet("color: #aaa; font-size: 11px;")
        self.lbl_filter_status_ai.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        filter_layout_ai.addWidget(self.btn_filter_ai)
        filter_layout_ai.addWidget(self.lbl_filter_status_ai)
        filter_layout_ai.addStretch()
        col_dirs.addLayout(filter_layout_ai)

        top_layout.addLayout(col_dirs, 1)

        # Колонка 3: Параметры ИИ поиска
        self._init_params_column(top_layout)

    def _init_params_column(self, top_layout):
        col_params = QVBoxLayout()
        col_params.setContentsMargins(0, 0, 0, 0)
        col_params.setSpacing(4)

        params_header = QHBoxLayout()
        self.lbl_params_title = QLabel(AppContext.tr("cln_ai_params_title"))
        params_title = self.lbl_params_title
        params_title.setStyleSheet("font-weight: bold; color: #888; font-size: 11px; font-family: 'Segoe UI';")
        params_header.addWidget(params_title)

        self.lbl_info_icon = QLabel("ℹ️")
        self.lbl_info_icon.setCursor(Qt.CursorShape.WhatsThisCursor)
        self.lbl_info_icon.setStyleSheet("""
            QLabel { color: #3b82f6; font-size: 12px; margin-left: 4px; background: transparent; border: none; }
            QToolTip { color: white; background-color: #2b2b2b; border: 1px solid #555; font-size: 12px; padding: 4px; border-radius: 4px; }
        """)

        self.lbl_info_icon.setToolTip(AppContext.tr("cln_ai_info_tooltip"))
        params_header.addWidget(self.lbl_info_icon)
        params_header.addStretch()
        col_params.addLayout(params_header)

        params_container = QFrame()
        params_container.setStyleSheet("QFrame { background-color: #1a1a1a; border: none; }")
        params_main_layout = QVBoxLayout(params_container)
        params_main_layout.setContentsMargins(8, 8, 8, 8)

        self.params_tabs = QTabWidget()
        self.params_tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #333; background: #111; border-radius: 4px; }
            QTabBar::tab { background: #222; color: #888; border: 1px solid #333; border-bottom: none; padding: 4px 8px; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:selected { background: #111; color: white; font-weight: bold; }
        """)

        tab_general = QWidget()
        tab_general_layout = QVBoxLayout(tab_general)
        tab_general_layout.setContentsMargins(8, 8, 8, 8)
        tab_general_layout.setSpacing(8)

        tab_advanced = QWidget()
        tab_advanced_layout = QVBoxLayout(tab_advanced)
        tab_advanced_layout.setContentsMargins(8, 8, 8, 8)
        tab_advanced_layout.setSpacing(8)

        self.params_tabs.addTab(tab_general, AppContext.tr("cln_ai_tab_general"))
        self.params_tabs.addTab(tab_advanced, AppContext.tr("cln_ai_tab_advanced"))
        params_main_layout.addWidget(self.params_tabs)

        # Панель размера и очистки кэша
        cache_layout = QHBoxLayout()
        cache_layout.setContentsMargins(0, 0, 0, 0)

        self.chk_use_cache = QCheckBox(AppContext.tr("cln_ai_chk_use_cache"))
        self.chk_use_cache.setChecked(True)
        self.chk_use_cache.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_use_cache.setStyleSheet("""
            QCheckBox { color: white; font-weight: bold; font-size: 13px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 3px; border: 1px solid #555; background: #111; }
            QCheckBox::indicator:checked { background-color: #3b82f6; border-color: #3b82f6; }
        """)
        cache_layout.addWidget(self.chk_use_cache)
        cache_layout.addStretch()

        self.lbl_cache_info_ai = QLabel("0 B")
        self.lbl_cache_info_ai.setStyleSheet("color: #888; font-size: 12px; margin-right: 5px;")
        cache_layout.addWidget(self.lbl_cache_info_ai)

        from ..ui_panels import load_svg_icon
        self.btn_clear_cache_ai = QPushButton("")
        icons_dir = AppContext.find_resource_dir("icons") or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "icons")
        self.btn_clear_cache_ai.setIcon(load_svg_icon(os.path.join(icons_dir, "trash-color.svg"), QSize(16, 16)))
        self.btn_clear_cache_ai.setIconSize(QSize(16, 16))
        self.btn_clear_cache_ai.setToolTip(AppContext.tr("cln_ai_tip_clear_cache"))
        self.btn_clear_cache_ai.setFixedSize(32, 32)
        self.btn_clear_cache_ai.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_cache_ai.setStyleSheet("""
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
        self.btn_clear_cache_ai.clicked.connect(self.clear_ai_cache_ui)
        cache_layout.addWidget(self.btn_clear_cache_ai)
        tab_general_layout.addLayout(cache_layout)

        # Слайдер схожести
        self.lbl_threshold = QLabel(AppContext.tr("cln_ai_lbl_threshold"))
        tooltip_thresh = (
            "Базовый порог первичной группировки (до объединения).\n"
            "Меньшие значения (50-60%): Образуются широкие группы с множеством потенциально похожих фото.\n"
            "Оптимально (75-80%): Хороший баланс для старта.\n"
            "Большие значения (90%+): В группу попадают только почти идентичные фото."
        )
        self.lbl_threshold.setToolTip(tooltip_thresh)
        self.lbl_threshold.setStyleSheet("color: #ccc; font-weight: bold; font-size: 11px; border: none; background: transparent;")
        tab_general_layout.addWidget(self.lbl_threshold)

        slider_layout = QHBoxLayout()
        self.slider_threshold = QSlider(Qt.Orientation.Horizontal)
        self.slider_threshold.setToolTip(tooltip_thresh)
        self.slider_threshold.setRange(0, 10000)
        self.slider_threshold.setValue(5000)
        self.slider_threshold.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #333; border-radius: 2px; }
            QSlider::handle:horizontal { background: #3b82f6; width: 12px; height: 12px; margin-top: -4px; margin-bottom: -4px; border-radius: 6px; }
        """)

        spin_container = QFrame()
        spin_container.setFixedHeight(26)
        spin_container.setFixedWidth(84)
        spin_container.setStyleSheet("QFrame { background-color: #333; border: 1px solid #555; border-radius: 4px; }")
        sc_layout = QHBoxLayout(spin_container)
        sc_layout.setContentsMargins(0, 0, 0, 0)
        sc_layout.setSpacing(0)

        self.spin_threshold = QDoubleSpinBox()
        self.spin_threshold.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.spin_threshold.setRange(0.0, 100.0)
        self.spin_threshold.setDecimals(1)
        self.spin_threshold.setSingleStep(0.1)
        self.spin_threshold.setValue(50.0)
        self.spin_threshold.setSuffix("%")
        self.spin_threshold.setFixedWidth(64)
        self.spin_threshold.setFixedHeight(24)
        self.spin_threshold.setStyleSheet("border: none; background: transparent; color: white; font-weight: bold; font-size: 13px; padding-left: 2px;")
        sc_layout.addWidget(self.spin_threshold)

        self.slider_threshold.valueChanged.connect(lambda v: self.spin_threshold.setValue(v / 100.0))
        self.spin_threshold.valueChanged.connect(lambda v: self.slider_threshold.setValue(int(v * 100)))

        slider_layout.addWidget(self.slider_threshold)
        slider_layout.addWidget(spin_container)
        tab_general_layout.addLayout(slider_layout)

        # Негативный порог
        self.lbl_neg_threshold = QLabel(AppContext.tr("cln_ai_lbl_neg_threshold"))
        tooltip_neg = (
            "Порог толерантности для картинок, содержащих минус-слова (антипаттерны).\n"
            "Меньшие значения (30-40%): Очень строгий фильтр, удаляет почти всё подозрительное.\n"
            "Оптимально (50-60%): Золотая середина.\n"
            "Большие значения (70%+): Удаляет только те фото, где нейросеть абсолютно уверена в наличии антипаттерна."
        )
        self.lbl_neg_threshold.setToolTip(tooltip_neg)
        self.lbl_neg_threshold.setStyleSheet("color: #ccc; font-weight: bold; font-size: 11px; border: none; background: transparent; margin-top: 8px;")
        tab_general_layout.addWidget(self.lbl_neg_threshold)

        neg_slider_layout = QHBoxLayout()
        self.slider_neg_threshold = QSlider(Qt.Orientation.Horizontal)
        self.slider_neg_threshold.setToolTip(tooltip_neg)
        self.slider_neg_threshold.setRange(0, 10000)
        self.slider_neg_threshold.setValue(5000)
        self.slider_neg_threshold.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #333; border-radius: 2px; }
            QSlider::handle:horizontal { background: #ef4444; width: 12px; height: 12px; margin-top: -4px; margin-bottom: -4px; border-radius: 6px; }
        """)

        neg_spin_container = QFrame()
        neg_spin_container.setFixedHeight(26)
        neg_spin_container.setFixedWidth(84)
        neg_spin_container.setStyleSheet("QFrame { background-color: #333; border: 1px solid #555; border-radius: 4px; }")
        nsc_layout = QHBoxLayout(neg_spin_container)
        nsc_layout.setContentsMargins(0, 0, 0, 0)
        nsc_layout.setSpacing(0)

        self.spin_neg_threshold = QDoubleSpinBox()
        self.spin_neg_threshold.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.spin_neg_threshold.setRange(0.0, 100.0)
        self.spin_neg_threshold.setDecimals(1)
        self.spin_neg_threshold.setSingleStep(0.1)
        self.spin_neg_threshold.setValue(50.0)
        self.spin_neg_threshold.setSuffix("%")
        self.spin_neg_threshold.setFixedWidth(64)
        self.spin_neg_threshold.setFixedHeight(24)
        self.spin_neg_threshold.setStyleSheet("border: none; background: transparent; color: white; font-weight: bold; font-size: 13px; padding-left: 2px;")
        nsc_layout.addWidget(self.spin_neg_threshold)

        self.slider_neg_threshold.valueChanged.connect(lambda v: self.spin_neg_threshold.setValue(v / 100.0))
        self.spin_neg_threshold.valueChanged.connect(lambda v: self.slider_neg_threshold.setValue(int(v * 100)))

        self.slider_threshold.sliderReleased.connect(self.on_slider_re_scan)
        self.slider_neg_threshold.sliderReleased.connect(self.on_slider_re_scan)

        neg_slider_layout.addWidget(self.slider_neg_threshold)
        neg_slider_layout.addWidget(neg_spin_container)
        tab_general_layout.addLayout(neg_slider_layout)

        # Продвинутые настройки (DirectML, лица)
        self._init_advanced_tab(tab_advanced_layout)

        tab_general_layout.addStretch()
        tab_advanced_layout.addStretch()

        QTimer.singleShot(100, self.update_cache_info_ai)

        self.btn_start_scan = QPushButton(AppContext.tr("cln_ai_btn_start_scan"))
        self.btn_start_scan.setFixedHeight(40)
        self.btn_start_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start_scan.setStyleSheet("""
            QPushButton { background-color: #15803d; color: white; font-weight: 900; font-size: 14px; border: 1px solid #16a34a; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
            QPushButton:hover { background-color: #16a34a; }
            QPushButton:disabled { background-color: #222; color: #555; font-weight: 900; font-size: 14px; border: 1px solid #333; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
        """)
        self.btn_start_scan.clicked.connect(self.on_btn_start_scan_clicked)
        params_main_layout.addWidget(self.btn_start_scan)

        col_params.addWidget(params_container)
        top_layout.addLayout(col_params, 1)

    def _init_advanced_tab(self, tab_advanced_layout):
        self.chk_use_gpu = QCheckBox(AppContext.tr("cln_ai_chk_use_gpu"))
        self.chk_use_gpu.setCursor(Qt.CursorShape.PointingHandCursor)

        from modules.cleaner.core_directml import DirectMLManager
        from modules.sorter.logic_config import ConfigManager

        _use_dml = ConfigManager.load().get("use_directml", True)

        if _use_dml and not DirectMLManager.is_ready:
            self.chk_use_gpu.setStyleSheet("""
                QCheckBox { color: #ef4444; font-weight: bold; font-size: 13px; }
                QCheckBox::indicator { width: 18px; height: 18px; border-radius: 3px; border: 1px solid #555; background: #111; }
                QCheckBox::indicator:checked { background-color: #ef4444; border-color: #ef4444; }
            """)
            err = DirectMLManager.error_msg or "Неизвестная ошибка совместимости."
            self.chk_use_gpu.setToolTip(f"Включение отменено из-за ошибки:\n{err}")
            self.chk_use_gpu.setChecked(False)
        else:
            self.chk_use_gpu.setStyleSheet("""
                QCheckBox { color: white; font-weight: bold; font-size: 13px; }
                QCheckBox::indicator { width: 18px; height: 18px; border-radius: 3px; border: 1px solid #555; background: #111; }
                QCheckBox::indicator:checked { background-color: #3b82f6; border-color: #3b82f6; }
            """)
            self.chk_use_gpu.setToolTip(AppContext.tr("cln_ai_tip_use_gpu"))
            self.chk_use_gpu.setChecked(_use_dml)

        self.chk_use_gpu.clicked.connect(self._on_directml_clicked)
        tab_advanced_layout.addWidget(self.chk_use_gpu)

        self.chk_show_faces = QCheckBox(AppContext.tr("cln_ai_chk_show_faces"))
        self.chk_show_faces.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_show_faces.setStyleSheet("""
            QCheckBox { color: white; font-weight: bold; font-size: 13px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 3px; border: 1px solid #555; background: #111; }
            QCheckBox::indicator:checked { background-color: #3b82f6; border-color: #3b82f6; }
        """)
        self.chk_show_faces.setChecked(True)
        self.chk_show_faces.toggled.connect(self._on_chk_show_faces_toggled)
        tab_advanced_layout.addWidget(self.chk_show_faces)

        face_conf_wrapper = QVBoxLayout()
        face_conf_wrapper.setSpacing(2)

        face_conf_title_layout = QHBoxLayout()
        self.lbl_face_conf_title = QLabel(AppContext.tr("cln_ai_face_conf_title"))
        lbl_face_conf_title = self.lbl_face_conf_title
        lbl_face_conf_title.setStyleSheet("color: white; font-weight: bold; font-size: 13px;")

        self.btn_face_conf_default = QPushButton(AppContext.tr("cln_ai_btn_face_conf_default"))
        btn_face_conf_default = self.btn_face_conf_default
        btn_face_conf_default.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_face_conf_default.setStyleSheet("""
            QPushButton { background-color: #333; color: #ccc; font-size: 11px; padding: 2px 8px; border-radius: 4px; border: 1px solid #444; }
            QPushButton:hover { background-color: #444; color: white; border-color: #555; }
        """)

        face_conf_title_layout.addWidget(lbl_face_conf_title)
        face_conf_title_layout.addWidget(btn_face_conf_default)
        face_conf_title_layout.addStretch()

        self.face_conf_layout = QHBoxLayout()
        self.face_conf_layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_face_conf_left = QLabel(AppContext.tr("cln_ai_face_conf_left"))
        lbl_face_conf_left = self.lbl_face_conf_left
        lbl_face_conf_left.setStyleSheet("color: #aaa; font-size: 11px;")

        self.slider_face_conf = QSlider(Qt.Orientation.Horizontal)
        self.slider_face_conf.setRange(10, 100)

        saved_thresh = 70
        if hasattr(self.cleaner, 'cache') and self.cleaner.cache:
            try:
                saved_thresh = int(self.cleaner.cache.get_last_face_conf_thresh(0.70) * 100)
            except Exception:
                pass

        self.slider_face_conf.setValue(saved_thresh)
        self.ai.current_face_conf_thresh = saved_thresh / 100.0

        self.slider_face_conf.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider_face_conf.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #333; border-radius: 2px; }
            QSlider::handle:horizontal { background: #3b82f6; width: 12px; height: 12px; margin-top: -4px; margin-bottom: -4px; border-radius: 6px; }
        """)

        self.lbl_face_conf_right = QLabel(AppContext.tr("cln_ai_face_conf_right"))
        lbl_face_conf_right = self.lbl_face_conf_right
        lbl_face_conf_right.setStyleSheet("color: #aaa; font-size: 11px;")

        self.lbl_face_conf_val = QLabel(f"{saved_thresh}%")
        self.lbl_face_conf_val.setFixedWidth(35)
        self.lbl_face_conf_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_face_conf_val.setStyleSheet("color: white; font-weight: bold; font-size: 13px;")

        def on_face_conf_changed(v):
            self.lbl_face_conf_val.setText(f"{v}%")
            self.ai.current_face_conf_thresh = v / 100.0
            if hasattr(self.cleaner, 'cache') and self.cleaner.cache:
                self.cleaner.cache.set_last_face_conf_thresh(v / 100.0)

        self.slider_face_conf.valueChanged.connect(on_face_conf_changed)
        btn_face_conf_default.clicked.connect(lambda: self.slider_face_conf.setValue(70))

        self.face_conf_layout.addWidget(lbl_face_conf_left)
        self.face_conf_layout.addWidget(self.slider_face_conf)
        self.face_conf_layout.addWidget(lbl_face_conf_right)
        self.face_conf_layout.addWidget(self.lbl_face_conf_val)

        face_conf_wrapper.addLayout(face_conf_title_layout)
        face_conf_wrapper.addLayout(self.face_conf_layout)
        tab_advanced_layout.addLayout(face_conf_wrapper)

    def _init_bottom_panel(self):
        self.bottom_container = QWidget()
        bot_layout = QVBoxLayout(self.bottom_container)
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

        from ..ui_panels import CleanerActionBar
        self.action_bar = CleanerActionBar()
        self.action_bar.is_similar_mode = False
        self.action_bar.combo_autoselect.hide()
        self.action_bar.btn_select_all.hide()
        self.action_bar.btn_deselect.hide()
        self.action_bar.chk_preserve.hide()
        self.action_bar.combo_collision.hide()

        # 3. Виджет результатов (таблица + предпросмотр)
        self.results_view = AiResultsView(self)
        self.results_view.cache_manager = self.cache
        self.results_view.chk_show_faces_supplier = lambda: self.chk_show_faces.isChecked()
        self.results_view.source_folders_supplier = lambda: getattr(self.cleaner, 'source_folders', {})

        self.results_view.file_selected.connect(self.file_selected.emit)
        self.results_view.selection_changed.connect(self.update_cleaner_action_bar_info)
        self.results_view.stats_updated.connect(self.lbl_stats.setText)
        self.results_view.send_group_to_sorter_requested.connect(
            lambda group_item: AiActionsController.send_group_to_sorter(group_item, self)
        )

        # Вставляем виджет пост-фильтра результатов в тулбар action_bar
        self.action_bar.layout().insertWidget(0, self.results_view.post_filter_widget)

        self.action_bar.deselect_clicked.connect(lambda: self.results_view.select_all_results(False))
        self.action_bar.select_all_clicked.connect(lambda: self.results_view.select_all_results(True))
        self.action_bar.move_clicked.connect(self.cleaner.move_selected)
        self.action_bar.move_to_clicked.connect(self.cleaner.prompt_move_selected)
        self.action_bar.delete_clicked.connect(self.cleaner.delete_selected)
        self.action_bar.browse_clicked.connect(self.cleaner.browse_dest)
        self.action_bar.drop_zone.path_changed.connect(self.update_cleaner_action_bar_info)

        bot_layout.addWidget(self.action_bar)
        bot_layout.addWidget(self.results_view, 1)

    # -------------------------------------------------------------------------
    # Прокси-свойства для обратной совместимости с cleaner и другими модулями
    # -------------------------------------------------------------------------
    @property
    def tree_results(self):
        return self.results_view.tree_results

    @property
    def preview_widget(self):
        return self.results_view.preview_widget

    @property
    def lbl_selection_info(self):
        return self.results_view.lbl_selection_info

    @property
    def page_ref(self):
        return self.samples_panel.page_ref

    @property
    def fast_search_widget(self):
        return self.samples_panel.fast_search_widget

    @property
    def chips_map(self):
        return self.samples_panel.chips_map

    def get_selected_files_paths(self) -> list:
        return self.results_view.get_selected_files_paths()

    def get_selected_files_size(self) -> int:
        return self.results_view.get_selected_files_size()

    def select_all_results(self, checked: bool):
        self.results_view.select_all_results(checked)

    def remove_processed_files(self, paths: list[str]):
        self.results_view.remove_processed_files(paths)

    def reload_groups(self):
        self.samples_panel.reload_groups()

    def create_group(self):
        self.samples_panel.create_group()

    def add_external_dump(self, path: str):
        self.samples_panel.add_external_dump(path)

    def open_edit_group_dialog(self, group_name: str):
        self.samples_panel.open_edit_group_dialog(group_name)

    def open_tag_manager(self):
        self.samples_panel.open_tag_manager()

    def show_tags_info(self):
        self.samples_panel.show_tags_info()

    def refresh_tag_chips(self):
        self.samples_panel.refresh_tag_chips()

    def populate_results(self, results):
        is_cluster = (self.samples_panel.mode_stack.currentIndex() == 2)
        scan_thresh = self.spin_threshold.value()
        self.results_view.populate_results(
            results,
            is_cluster=is_cluster,
            scan_threshold=scan_thresh,
            source_folders=getattr(self.cleaner, 'source_folders', {})
        )

    # -------------------------------------------------------------------------
    # Управление моделями, кэшем и состоянием
    # -------------------------------------------------------------------------
    def check_models_status(self):
        legacy = self.ai.check_legacy_models()
        if legacy:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.NoIcon)
            msg.setWindowTitle(AppContext.tr("cln_ai_legacy_models_title"))

            total_size = sum(os.path.getsize(f) for f in legacy) // (1024 * 1024)
            text = AppContext.tr("cln_ai_legacy_models_body").format(total_size)

            msg.setText(text)
            msg.setDetailedText("\n".join(legacy))

            btn_yes = msg.addButton(AppContext.tr("cln_ai_btn_delete"), QMessageBox.ButtonRole.YesRole)
            btn_no = msg.addButton(AppContext.tr("cln_ai_btn_cancel"), QMessageBox.ButtonRole.NoRole)
            msg.setDefaultButton(btn_yes)
            msg.exec()

            if msg.clickedButton() == btn_yes:
                freed = self.ai.clean_legacy_models(legacy)
                silent_info(self, AppContext.tr("cln_ai_title_success"), AppContext.tr("cln_ai_freed_mb").format(freed // (1024*1024)))

        if self.ai.are_models_present():
            self.download_placeholder.hide()
            self.main_content_widget.show()
        else:
            self.download_placeholder.show()
            self.main_content_widget.hide()

    def start_placeholder_download(self):
        self.btn_download_models.hide()
        self.btn_stop_download.show()
        self.btn_stop_download.setEnabled(True)
        self.placeholder_progress.show()
        self.placeholder_progress.setValue(0)
        self.placeholder_status.setStyleSheet("color: #93c5fd;")
        self.placeholder_status.setText(AppContext.tr("cln_ai_status_connecting"))

        self.dl_thread = AiModelDownloaderThread(self.ai, self)

        def on_progress(filename, downloaded, total_size):
            if total_size > 0:
                pct = int((downloaded / total_size) * 100.0)
                self.placeholder_progress.setValue(pct)
                self.placeholder_status.setText(f"Загрузка {filename}: {downloaded // 1024} KB / {total_size // 1024} KB")
            else:
                self.placeholder_status.setText(f"Загрузка {filename}: {downloaded // 1024} KB")

        def on_finished(success):
            self.btn_stop_download.hide()
            self.btn_download_models.show()
            self.btn_download_models.setEnabled(True)

            if hasattr(self, 'dl_thread') and self.dl_thread and self.dl_thread._is_stopped:
                self.placeholder_status.setStyleSheet("color: #f59e0b;")
                self.placeholder_status.setText(AppContext.tr("cln_ai_status_download_stopped"))
                return

            if success:
                self.placeholder_status.setStyleSheet("color: #4ade80;")
                self.placeholder_status.setText(AppContext.tr("cln_ai_status_initializing"))

                if self.ai.initialize_sessions():
                    self.placeholder_status.setText(AppContext.tr("cln_ai_status_success"))
                    self.download_placeholder.hide()
                    self.main_content_widget.show()
                else:
                    self.placeholder_status.setStyleSheet("color: #ef4444;")
                    self.placeholder_status.setText(AppContext.tr("cln_ai_status_init_failed"))
            else:
                self.placeholder_status.setStyleSheet("color: #ef4444;")
                self.placeholder_status.setText(AppContext.tr("cln_ai_status_download_failed"))

        self.dl_thread.progress_signal.connect(on_progress)
        self.dl_thread.finished_signal.connect(on_finished)
        self.dl_thread.start()

    def stop_placeholder_download(self):
        if hasattr(self, 'dl_thread') and self.dl_thread and self.dl_thread.isRunning():
            self.btn_stop_download.setEnabled(False)
            self.placeholder_status.setStyleSheet("color: #f59e0b;")
            self.placeholder_status.setText(AppContext.tr("cln_ai_status_cancelling"))
            self.dl_thread.stop()

    def update_cache_info_ai(self):
        try:
            db_path = self.cache.db_path
            from utils_common import format_size
            if os.path.exists(db_path):
                size = os.path.getsize(db_path)
                wal_path = db_path + "-wal"
                shm_path = db_path + "-shm"
                if os.path.exists(wal_path):
                    size += os.path.getsize(wal_path)
                if os.path.exists(shm_path):
                    size += os.path.getsize(shm_path)
                self.lbl_cache_info_ai.setText(f"{format_size(size)}")
            else:
                self.lbl_cache_info_ai.setText("0 B")
        except Exception as e:
            logging.error(f"Ошибка получения размера ИИ-кэша: {e}")
            self.lbl_cache_info_ai.setText("0 B")

    def clear_ai_cache_ui(self):
        reply = silent_question(
            self,
            AppContext.tr("cln_ai_clear_cache_title"),
            AppContext.tr("cln_ai_clear_cache_prompt"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.cache.clear_cache()
            self.update_cache_info_ai()
            self.reload_groups()

    def set_scan_enabled(self, enabled: bool):
        self._is_ok = enabled
        self.update_scan_button_state()

    def check_and_download_models_ui(self) -> bool:
        if self.ai.are_models_present():
            return True
        self.check_models_status()
        return False

    def update_folders_label(self, folders: list):
        while self.folder_list_layout_ai.count():
            item = self.folder_list_layout_ai.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        from ..ui_widgets import SourceListItem

        for idx, path in enumerate(folders):
            color = "#3b82f6"
            is_system = False
            if hasattr(self.cleaner, 'source_folders') and path in self.cleaner.source_folders:
                color = self.cleaner.source_folders[path].get('color', color)
                is_system = self.cleaner.source_folders[path].get('is_system', False)

            is_cached, is_face_cached = self.cache.has_cached_files_for_folder(path)
            item_widget = SourceListItem(path, color, is_cached=is_cached, is_face_cached=is_face_cached)
            if is_system:
                item_widget.set_system_error_state()

            item_widget.removed.connect(self.cleaner.remove_folder)
            item_widget.context_menu_requested.connect(self.cleaner.show_source_menu)
            self.folder_list_layout_ai.addWidget(item_widget)

        self.update_scan_button_state()

    def update_scan_button_state(self):
        folders = self.cleaner.get_active_source_folders() if hasattr(self.cleaner, 'get_active_source_folders') else []
        has_folders = len(folders) > 0

        mode_idx = self.samples_panel.mode_stack.currentIndex()
        is_ref_mode = (mode_idx == 0)
        is_text_mode = (mode_idx == 1)
        is_cluster = (mode_idx == 2)

        has_enabled_groups = self.samples_panel.has_enabled_groups()
        is_ok = getattr(self, '_is_ok', True)

        if is_text_mode:
            can_run = has_folders and is_ok
        else:
            can_run = has_folders and (has_enabled_groups or is_cluster) and is_ok

        logging.info(f"[AI_SCAN_BTN] folders={has_folders}({len(folders)}), groups={has_enabled_groups}, is_ok={is_ok} -> can_run={can_run}")

        if has_folders and has_enabled_groups and not can_run and not is_text_mode and not is_cluster:
            logging.warning("[AI_SCAN_BTN] is_ok flag was incorrectly False. Forcing to True.")
            is_ok = True
            can_run = True
            self._is_ok = True

        self.btn_start_scan.setEnabled(can_run)
        self.btn_start_scan.setText(AppContext.tr("cln_ai_btn_start_scan"))

    def update_cleaner_action_bar_info(self, count=None, total_size=None):
        if count is None:
            paths = self.results_view.get_selected_files_paths()
            count = len(paths)
        has_destination = bool(self.action_bar.drop_zone.get_path())
        AiActionsController.update_action_bar_state(self.action_bar, count, has_destination)

    def on_slider_re_scan(self):
        if hasattr(self, 'facade') and self.chk_use_cache.isChecked():
            if self.tree_results.topLevelItemCount() > 0 or self.lbl_stats.text() != "":
                self.on_btn_start_scan_clicked()

    def on_btn_start_scan_clicked(self):
        if self.samples_panel.mode_stack.currentIndex() == 1:
            query = self.samples_panel.get_active_text_query()
            if not query:
                silent_warning(self, AppContext.tr("cln_ai_warning_title"), AppContext.tr("cln_ai_warning_enter_query"))
                return
            self.toggle_scan(text_query=query)
        else:
            self.toggle_scan()

    def toggle_scan(self, text_query=None):
        if hasattr(self, 'facade') and self.facade.active_worker:
            self.facade.cancel_search()
            self.progress_bar.hide()
            self.btn_start_scan.setText(AppContext.tr("cln_ai_btn_start_scan"))
            self.btn_start_scan.setStyleSheet("""
                QPushButton { background-color: #15803d; color: white; font-weight: 900; font-size: 14px; border: 1px solid #16a34a; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
                QPushButton:hover { background-color: #16a34a; }
                QPushButton:disabled { background-color: #222; color: #555; font-weight: 900; font-size: 14px; border: 1px solid #333; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
            """)
            self.scan_finished.emit()
            return

        folders = self.cleaner.get_active_source_folders() if hasattr(self.cleaner, 'get_active_source_folders') else []
        if not folders:
            return

        for widget in self.samples_panel.chips_map.values():
            widget.set_error_highlight(False)

        mode_idx = self.samples_panel.mode_stack.currentIndex()
        is_ref_mode = (mode_idx == 0)
        is_fast_search = is_ref_mode and (self.samples_panel.page_ref.currentIndex() == 0)
        is_cluster = (mode_idx == 2)
        fast_search_dump = None

        if is_fast_search:
            pos_paths = self.samples_panel.fast_search_widget.get_pos_paths()
            if not pos_paths:
                silent_warning(self, AppContext.tr("cln_frag_err_title"), AppContext.tr("cln_ai_err_add_pos_sample"))
                return

            missing_files = [p for p in pos_paths if not os.path.exists(p)]
            if len(missing_files) == len(pos_paths):
                silent_warning(self, AppContext.tr("cln_ai_err_missing_samples_title"), AppContext.tr("cln_ai_err_missing_samples_desc"))
                return

            fast_search_dump = self.samples_panel.fast_search_widget.generate_temp_dump()
            self.samples_panel.fast_search_widget.pos_area.set_defective_paths([])
            self.samples_panel.fast_search_widget.neg_area.set_defective_paths([])
        elif is_ref_mode and not text_query:
            settings = load_ai_settings()
            enabled_groups = [name for name, info in settings.get("groups", {}).items() if info.get("enabled", True)]

            if not enabled_groups:
                silent_warning(self, AppContext.tr("cln_frag_err_title"), AppContext.tr("cln_ai_err_no_groups_selected"))
                return

            for name in enabled_groups:
                status, count = self.classifier.get_group_status(name)
                if status == "gray":
                    if name in self.samples_panel.chips_map:
                        self.samples_panel.chips_map[name].set_error_highlight(True)
                    silent_warning(self, AppContext.tr("cln_frag_err_title"), AppContext.tr("cln_ai_err_group_empty").format(name))
                    return

            needs_training = [name for name in enabled_groups if self.classifier.get_group_status(name)[0] == "orange"]
            if needs_training:
                if not self.check_and_download_models_ui():
                    return
                dlg = QDialog(self)
                dlg.setWindowTitle(AppContext.tr("cln_ai_autotrain_title"))
                dlg.setFixedSize(300, 100)
                dlg_layout = QVBoxLayout(dlg)
                lbl_title = QLabel(AppContext.tr("cln_ai_autotrain_prep"))
                bar = QProgressBar()
                bar.setRange(0, len(needs_training))
                dlg_layout.addWidget(lbl_title)
                dlg_layout.addWidget(bar)
                dlg.show()

                for idx, name in enumerate(needs_training):
                    lbl_title.setText(AppContext.tr("cln_ai_autotrain_step").format(idx + 1, len(needs_training), name))
                    from PyQt6.QtWidgets import QApplication
                    QApplication.processEvents()
                    success = self.classifier.train_group(name)
                    if not success:
                        dlg.close()
                        QMessageBox.critical(self, AppContext.tr("cln_frag_err_title"), AppContext.tr("cln_ai_autotrain_failed").format(name))
                        return
                    bar.setValue(idx + 1)
                dlg.close()
                self.reload_groups()

        self.scan_started.emit()
        self.btn_start_scan.setText(AppContext.tr("cln_ai_btn_stop_scan"))
        self.btn_start_scan.setStyleSheet("""
            QPushButton { background-color: #991b1b; color: white; font-weight: 900; font-size: 14px; border: 1px solid #7f1d1d; border-radius: 6px; font-family: 'Segoe UI'; padding: 4px; }
            QPushButton:hover { background-color: #b91c1c; }
        """)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.results_view.clear_results()
        self.lbl_stats.setText("")

        threshold = float(self.spin_threshold.value())
        use_cache = self.chk_use_cache.isChecked()
        use_gpu = self.chk_use_gpu.isChecked()
        cluster_type = self.samples_panel.combo_auto_type.currentData() if hasattr(self.samples_panel, 'combo_auto_type') else 'face'

        task_type = AiTaskType.TEXT_TO_IMAGE if text_query else (AiTaskType.AUTO_CLUSTER if is_cluster else AiTaskType.FIND_BY_REFERENCES)
        if task_type == AiTaskType.FIND_BY_REFERENCES:
            analysis_target = AiTarget.BOTH
        elif task_type == AiTaskType.TEXT_TO_IMAGE:
            analysis_target = AiTarget.IMAGES
        else:
            analysis_target = AiTarget.FACES if cluster_type == 'face' else AiTarget.IMAGES

        text_queries_dict = {}
        negative_queries = {}
        global_negatives = []
        if text_query:
            parsed = parse_multi_tags(text_query)
            if parsed:
                for group, tags in parsed.items():
                    if group.startswith('-'):
                        for t in tags:
                            tt = t[1:].strip() if t.startswith('-') else t
                            global_negatives.append(parse_tag_weight(tt))
                    else:
                        pos, neg = [], []
                        for t in tags:
                            if t.startswith('-'):
                                neg.append(parse_tag_weight(t[1:].strip()))
                            else:
                                pos.append(parse_tag_weight(t))
                        if pos:
                            text_queries_dict[group] = pos
                        if neg:
                            negative_queries[group] = neg
            else:
                if text_query.startswith('-'):
                    global_negatives.append(parse_tag_weight(text_query[1:].strip()))
                else:
                    text_queries_dict["Текст"] = [parse_tag_weight(text_query)]

            if global_negatives:
                negative_queries["__global__"] = global_negatives

        scan_threshold = min(20.0, threshold) if task_type == AiTaskType.TEXT_TO_IMAGE else threshold
        request = AiSearchRequest(
            target_paths=folders,
            task_type=task_type,
            analysis_target=analysis_target,
            threshold=scan_threshold,
            neg_threshold=float(self.spin_neg_threshold.value()),
            file_filter_config=self.ai_filter_config,
            text_queries=text_queries_dict,
            negative_queries=negative_queries,
            use_cache=use_cache,
            use_gpu=use_gpu,
            fast_search_dump=fast_search_dump,
            face_conf_thresh=self.slider_face_conf.value() / 100.0
        )

        if not hasattr(self, 'facade'):
            self.facade = AiServiceFacade()
            self.facade.cache = self.cache
            self.facade.engine = self.ai

        self.scan_start_time = time.time()
        self.facade.search(
            request,
            progress_callback=self.on_scan_progress,
            result_callback=self.on_scan_finished,
            error_callback=self.on_scan_error,
            classifier=self.classifier,
            defective_callback=self.on_defective_faces
        )

    def on_defective_faces(self, temp_defective_paths: list):
        mode_idx = self.samples_panel.mode_stack.currentIndex()
        is_fast_search = (mode_idx == 0) and (self.samples_panel.page_ref.currentIndex() == 0)
        if not is_fast_search or not temp_defective_paths:
            return

        defective_basenames = set()
        for dp in temp_defective_paths:
            bn = os.path.basename(dp)
            if bn.startswith("pos_") or bn.startswith("neg_"):
                bn = bn[4:]
            defective_basenames.add(bn.lower())

        original_defective = []
        for orig_path in self.samples_panel.fast_search_widget.pos_area.paths + self.samples_panel.fast_search_widget.neg_area.paths:
            if os.path.basename(orig_path).lower() in defective_basenames:
                original_defective.append(orig_path)

        logging.info(f"[FastSearch] Дефектные (без лиц): {len(original_defective)}")
        if original_defective:
            self.samples_panel.fast_search_widget.pos_area.set_defective_paths(original_defective)
            self.samples_panel.fast_search_widget.neg_area.set_defective_paths(original_defective)

    def on_scan_error(self, error_msg: str):
        QMessageBox.critical(self, AppContext.tr("cln_ai_err_title"), error_msg)
        self.progress_bar.hide()
        self.btn_start_scan.setText(AppContext.tr("cln_ai_btn_start_scan"))
        self.btn_start_scan.setStyleSheet("""
            QPushButton { background-color: #15803d; color: white; font-weight: 900; font-size: 14px; border: 1px solid #16a34a; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
            QPushButton:hover { background-color: #16a34a; }
            QPushButton:disabled { background-color: #222; color: #555; font-weight: 900; font-size: 14px; border: 1px solid #333; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
        """)
        self.scan_finished.emit()

    def on_scan_progress(self, stage, percent, text, scanned_files, groups_found, wasted_bytes, scanned_bytes, files_found, empty):
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(int(percent))

        elapsed_sec = int(time.time() - getattr(self, 'scan_start_time', time.time()))
        m, s = divmod(elapsed_sec, 60)
        time_str = f" [{m:02d}:{s:02d}]"
        base_text = f"{text} ({int(percent)}%)" if "%" not in text else text
        self.progress_bar.setFormat(base_text + time_str)

        if stage == STAGE_SCANNING:
            self.progress_bar.setStyleSheet("QProgressBar { border: none; background-color: #151515; text-align: center; color: white; font-size: 11px; } QProgressBar::chunk { background-color: #3b82f6; }")
        else:
            self.progress_bar.setStyleSheet("QProgressBar { border: none; background-color: #151515; text-align: center; color: white; font-size: 11px; } QProgressBar::chunk { background-color: #22c55e; }")

        from utils_common import format_size
        size_str = format_size(wasted_bytes) if wasted_bytes else "0 MB"
        self.lbl_stats.setText(AppContext.tr("cln_ai_stats_matches").format(groups_found, files_found, size_str, m, s))

    def on_scan_finished(self, response: AiSearchResponse):
        from PyQt6.QtWidgets import QApplication
        self.progress_bar.setFormat(AppContext.tr("cln_ai_table_building"))
        QApplication.processEvents()

        results_dict = {}
        sorted_groups = sorted(response.groups, key=lambda g: len(g.files), reverse=True)
        for group in sorted_groups:
            results_dict[group.group_name] = []
            for mf in group.files:
                try:
                    size = os.path.getsize(mf.path)
                except Exception:
                    size = 0
                bbox_list = [mf.matched_bbox.x1, mf.matched_bbox.y1, mf.matched_bbox.x2, mf.matched_bbox.y2] if mf.matched_bbox else None
                results_dict[group.group_name].append({
                    "path": mf.path,
                    "confidence": mf.score,
                    "size": size,
                    "matched_bbox": bbox_list,
                    "type": "face" if mf.matched_bbox else "general",
                    "tag_scores": mf.tag_scores
                })

        self.populate_results(results_dict)

        self.progress_bar.hide()
        self.btn_start_scan.setText(AppContext.tr("cln_ai_btn_start_scan"))
        self.btn_start_scan.setStyleSheet("""
            QPushButton { background-color: #15803d; color: white; font-weight: 900; font-size: 14px; border: 1px solid #16a34a; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
            QPushButton:hover { background-color: #16a34a; }
            QPushButton:disabled { background-color: #222; color: #555; font-weight: 900; font-size: 14px; border: 1px solid #333; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
        """)

        self.scan_finished.emit()
        self.update_cache_info_ai()
        if hasattr(self.cleaner, 'get_active_source_folders'):
            self.update_folders_label(self.cleaner.get_active_source_folders())

    def _on_chk_show_faces_toggled(self, checked):
        self.results_view.refresh_preview_faces()

    def _on_directml_clicked(self, checked):
        from logic_paths import get_app_data_dir
        import configparser

        path = os.path.join(get_app_data_dir(), "settings.ini")
        cp = configparser.ConfigParser(interpolation=None)
        if os.path.exists(path):
            cp.read(path, encoding='utf-8')
        if "Main" not in cp:
            cp["Main"] = {}

        cp["Main"]["use_directml"] = "true" if checked else "false"
        with open(path, "w", encoding="utf-8") as f:
            cp.write(f)

        self.chk_use_gpu.setStyleSheet("""
            QCheckBox { color: white; font-weight: bold; font-size: 13px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 3px; border: 1px solid #555; background: #111; }
            QCheckBox::indicator:checked { background-color: #3b82f6; border-color: #3b82f6; }
        """)

        msg = QMessageBox(self)
        msg.setWindowTitle(AppContext.tr("cln_ai_gpu_dialog_title"))
        msg.setIcon(QMessageBox.Icon.NoIcon)
        msg.setText(AppContext.tr("cln_ai_gpu_restart_notice"))
        msg.exec()

    def open_filter_dialog_ai(self):
        self.btn_filter_ai.setEnabled(False)
        self.btn_filter_ai.setText(AppContext.tr("cln_frag_btn_scanning"))

        def on_applied(filter_config, status_text):
            self.ai_filter_config = filter_config
            self.lbl_filter_status_ai.setText(status_text)
            self.btn_filter_ai.setEnabled(True)
            self.btn_filter_ai.setText(AppContext.tr("cln_btn_scan_types"))

        worker = AiActionsController.run_extension_scan_ai(self.cleaner, self, on_applied)
        if not worker:
            self.btn_filter_ai.setEnabled(True)
            self.btn_filter_ai.setText(AppContext.tr("cln_btn_scan_types"))



    def retranslate_ui(self):
        """Update AI tab strings dynamically on language switch."""
        if hasattr(self, 'lbl_title_placeholder'):
            self.lbl_title_placeholder.setText(AppContext.tr("cln_ai_models_init_title"))
        if hasattr(self, 'lbl_desc_placeholder'):
            self.lbl_desc_placeholder.setText(AppContext.tr("cln_ai_models_init_desc"))
        if hasattr(self, 'btn_download_models'):
            self.btn_download_models.setText(AppContext.tr("cln_ai_btn_download_models"))
        if hasattr(self, 'btn_stop_download'):
            self.btn_stop_download.setText(AppContext.tr("cln_ai_btn_stop_download"))
        if hasattr(self, 'lbl_dirs_title'):
            self.lbl_dirs_title.setText(AppContext.tr("cln_ai_dirs_title"))
        if hasattr(self, 'btn_filter_ai'):
            self.btn_filter_ai.setText(AppContext.tr("cln_btn_scan_types"))
        if hasattr(self, 'lbl_filter_status_ai'):
            if (getattr(self, 'ai_filter_config', None) or {}).get('mode', 'all') == 'all':
                self.lbl_filter_status_ai.setText(AppContext.tr("cln_filter_all"))
        if hasattr(self, 'lbl_params_title'):
            self.lbl_params_title.setText(AppContext.tr("cln_ai_params_title"))
        if hasattr(self, 'lbl_info_icon'):
            self.lbl_info_icon.setToolTip(AppContext.tr("cln_ai_info_tooltip"))
        if hasattr(self, 'params_tabs'):
            self.params_tabs.setTabText(0, AppContext.tr("cln_ai_tab_general"))
            self.params_tabs.setTabText(1, AppContext.tr("cln_ai_tab_advanced"))
        if hasattr(self, 'chk_use_cache'):
            self.chk_use_cache.setText(AppContext.tr("cln_ai_chk_use_cache"))
        if hasattr(self, 'btn_clear_cache_ai'):
            self.btn_clear_cache_ai.setToolTip(AppContext.tr("cln_ai_tip_clear_cache"))
        if hasattr(self, 'lbl_threshold'):
            self.lbl_threshold.setText(AppContext.tr("cln_ai_lbl_threshold"))
        if hasattr(self, 'lbl_neg_threshold'):
            self.lbl_neg_threshold.setText(AppContext.tr("cln_ai_lbl_neg_threshold"))
        if hasattr(self, 'btn_start_scan'):
            if hasattr(self, 'facade') and getattr(self.facade, 'active_worker', None):
                self.btn_start_scan.setText(AppContext.tr("cln_ai_btn_stop_scan"))
            else:
                self.btn_start_scan.setText(AppContext.tr("cln_ai_btn_start_scan"))
        if hasattr(self, 'chk_use_gpu'):
            self.chk_use_gpu.setText(AppContext.tr("cln_ai_chk_use_gpu"))
            self.chk_use_gpu.setToolTip(AppContext.tr("cln_ai_tip_use_gpu"))
        if hasattr(self, 'chk_show_faces'):
            self.chk_show_faces.setText(AppContext.tr("cln_ai_chk_show_faces"))
        if hasattr(self, 'lbl_face_conf_title'):
            self.lbl_face_conf_title.setText(AppContext.tr("cln_ai_face_conf_title"))
        if hasattr(self, 'btn_face_conf_default'):
            self.btn_face_conf_default.setText(AppContext.tr("cln_ai_btn_face_conf_default"))
        if hasattr(self, 'lbl_face_conf_left'):
            self.lbl_face_conf_left.setText(AppContext.tr("cln_ai_face_conf_left"))
        if hasattr(self, 'lbl_face_conf_right'):
            self.lbl_face_conf_right.setText(AppContext.tr("cln_ai_face_conf_right"))
        if hasattr(self, 'samples_panel') and hasattr(self.samples_panel, 'retranslate_ui'):
            self.samples_panel.retranslate_ui()
        if hasattr(self, 'results_view') and hasattr(self.results_view, 'retranslate_ui'):
            self.results_view.retranslate_ui()

    def update_ui_text(self):
        """Compatibility alias for cleaner main tab."""
        self.retranslate_ui()


# Псевдоним класса для обратной совместимости
AiSearchTab = AiClassificationTab
