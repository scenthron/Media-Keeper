import os
import shutil
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QSlider,
    QTreeWidget, QTreeWidgetItem, QProgressBar, QDialog, QLineEdit,
    QRadioButton, QButtonGroup, QAbstractItemView, QMenu, QSplitter,
    QScrollArea, QSizePolicy, QComboBox, QCheckBox, QTabWidget, QDoubleSpinBox,
    QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer, QPoint, QEvent, QThread
from PyQt6.QtGui import QIcon, QPixmap, QColor, QAction, QCursor, QFont, QPainter, QPen, QDragEnterEvent, QDropEvent

from config import AppContext, APP_DESIGN
from ui_widgets_base import DropZoneWidget, FlowLayout
from .logic_ai_tags import AiTextTagsManager, parse_multi_tags, MultiTagHighlighter
from .ui_ai_tags_dialog import AiTagManagerDialog
from .logic_ai import AiEngine
from .logic_ai_cache import AiCacheManager
from .logic_ai_classifier import AiClassifier, load_ai_settings, save_ai_settings, get_ai_assets_dir
from .workers import STAGE_SCANNING, STAGE_ANALYSIS
from .ai_facade import AiServiceFacade, AiSearchRequest, AiTaskType, AiTarget, AiSearchResponse, AiMatchFile, AiGroup
from .ui_widgets import ImageHoverToolTip, RefImagesListWidget
from .ui_ai_results_tree import AiResultsTreeWidget
from .ui_ai_references_panel import RefDropContainer, AiGroupChipWidget


# -----------------------------------------------------------------------------
# Диалог настроек группы Образцов (вызывается при клике по шестеренке)
# -----------------------------------------------------------------------------
from .ui_ai_group_dialog import AiGroupSettingsDialog

from .ui_widgets import CleanSpinBox
from PyQt6.QtWidgets import QStackedWidget

class SearchTextEdit(QTextEdit):
    returnPressed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setFixedHeight(36)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                event.accept()
                QTimer.singleShot(0, self.returnPressed.emit)
        else:
            super().keyPressEvent(event)
        
class AiFolderDropContainer(QWidget):
    folder_dropped = pyqtSignal(str)
    files_dropped = pyqtSignal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dropEvent(self, event: QDropEvent):
        paths = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            import os
            if os.path.exists(path):
                if os.path.isdir(path):
                    self.folder_dropped.emit(path)
                else:
                    paths.append(path)
        if paths:
            self.files_dropped.emit(paths)


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

# -----------------------------------------------------------------------------
# Основная вкладка ИИ-классификации
# -----------------------------------------------------------------------------
class AiClassificationTab(QWidget):
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
        self.chips_map = {}
        self.ai_filter_config = None
        
        self.tags_manager = AiTextTagsManager()
        self.active_tag_buttons = {}
        
        self._init_ui()
        self.reload_groups()
        self.check_models_status()

    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # =====================================================================
        # ЭКРАН-ЗАГЛУШКА ДЛЯ СКАЧИВАНИЯ МОДЕЛЕЙ (ПО УМОЛЧАНИЮ СКРЫТ)
        # =====================================================================
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
        
        lbl_title = QLabel("Требуется инициализация ИИ-моделей" if AppContext.is_ru() else "AI Models Initialization Required")
        lbl_title.setStyleSheet("font-weight: bold; color: white; font-size: 16px; background: transparent; border: none;")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_layout.addWidget(lbl_title)
        
        lbl_desc = QLabel(
            "Для работы сверхточного ИИ-поиска необходимо наличие моделей CLIP и InsightFace (~1 ГБ).\n"
            "Загрузка выполняется один раз, после чего ИИ работает полностью автономно без подключения к интернету."
            if AppContext.is_ru() else
            "To use advanced AI classification and face recognition, CLIP and InsightFace models (~1 GB) are required.\n"
            "This download is done once, and then the AI runs completely offline."
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setFixedWidth(400)
        lbl_desc.setStyleSheet("color: #aaa; font-size: 12px; background: transparent; border: none; line-height: 1.5;")
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        desc_layout = QHBoxLayout()
        desc_layout.addStretch(1)
        desc_layout.addWidget(lbl_desc)
        desc_layout.addStretch(1)
        ph_layout.addLayout(desc_layout)
        
        self.btn_download_models = QPushButton("Загрузить модели ИИ" if AppContext.is_ru() else "Download AI Models")
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
            QPushButton:hover {
                background-color: #2563eb;
            }
            QPushButton:disabled {
                background-color: #333;
                color: #666;
            }
        """)
        self.btn_download_models.clicked.connect(self.start_placeholder_download)
        
        self.btn_stop_download = QPushButton("⏹ Отмена" if AppContext.is_ru() else "⏹ Cancel")
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
            QPushButton:hover {
                background-color: #dc2626;
            }
            QPushButton:disabled {
                background-color: #333;
                color: #666;
            }
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
            QProgressBar::chunk {
                background-color: #3b82f6;
            }
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
        
        # =====================================================================
        # ГЛАВНЫЙ КОНТЕНТ ВКЛАДКИ (НАСТРОЙКИ СВЕРХУ, ТАБЛИЦА СНИЗУ В SPLITTER)
        # =====================================================================
        self.main_content_widget = QWidget(self)
        content_layout = QVBoxLayout(self.main_content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # Создаем вертикальный сплиттер, чтобы область настроек можно было расширять/сжимать
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.setHandleWidth(2)
        self.main_splitter.setStyleSheet("QSplitter::handle { background-color: #2d2d2d; }")
        
        # Верхняя панель настроек (со свободным изменением высоты от 130 до 280)
        # Верхняя панель настроек (со свободным изменением высоты от 220 до 600)
        self.top_settings = QFrame()
        self.top_settings.setMinimumHeight(220)
        self.top_settings.setMaximumHeight(600)
        self.top_settings.setStyleSheet("background-color: #1e1e1e; border-bottom: 1px solid #2d2d2d;")
        top_layout = QHBoxLayout(self.top_settings)
        top_layout.setContentsMargins(15, 6, 15, 6)
        top_layout.setSpacing(12)
        
        # КОЛОНКА 1: Группы Образцов
        col_ref = QVBoxLayout()
        col_ref.setContentsMargins(0, 0, 0, 0)
        col_ref.setSpacing(4)

        mode_header = QHBoxLayout()
        
        self.btn_mode_ref = QPushButton("Поиск по образцам" if AppContext.is_ru() else "Search by Samples")
        self.btn_mode_text = QPushButton("Поиск по тексту" if AppContext.is_ru() else "Search by Text")
        
        mode_style = """
            QPushButton {
                background-color: #2b2b2b;
                color: #888;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:checked {
                background-color: #3b82f6;
                color: white;
                border-color: #2563eb;
            }
        """
        self.btn_mode_ref.setCheckable(True)
        self.btn_mode_text.setCheckable(True)
        self.btn_mode_ref.setStyleSheet(mode_style)
        self.btn_mode_text.setStyleSheet(mode_style)
        self.btn_mode_ref.setChecked(True)
        self.btn_mode_ref.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mode_text.setCursor(Qt.CursorShape.PointingHandCursor)
        
        mode_header.addWidget(self.btn_mode_ref)
        mode_header.addWidget(self.btn_mode_text)
        col_ref.addLayout(mode_header)
        
        self.mode_stack = QStackedWidget()
        col_ref.addWidget(self.mode_stack)
        
        # Page 1: References
        self.page_ref = QWidget()
        page_ref_layout = QVBoxLayout(self.page_ref)
        page_ref_layout.setContentsMargins(0, 0, 0, 0)
        page_ref_layout.setSpacing(4)

        
        ref_header = QHBoxLayout()
        page_ref_layout.addLayout(ref_header)
        ref_title = QLabel("Группы Образцов" if AppContext.is_ru() else "Reference Groups")
        ref_title.setStyleSheet("font-weight: bold; color: #888; font-size: 11px; font-family: 'Segoe UI';")
        ref_header.addWidget(ref_title)
        
        ref_header.addStretch()
        
        self.btn_create_ref = QPushButton("[+] Создать" if AppContext.is_ru() else "[+] Create")
        self.btn_create_ref.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_create_ref.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6; 
                color: white; 
                border: none; 
                padding: 2px 8px; 
                border-radius: 3px; 
                font-weight: bold; 
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
        """)
        self.btn_create_ref.clicked.connect(self.create_group)
        ref_header.addWidget(self.btn_create_ref)
        
        
        self.scroll_ref = QScrollArea()
        self.scroll_ref.setWidgetResizable(True)
        self.scroll_ref.setStyleSheet("QScrollArea { border: 1px solid #333; background-color: #111; border-radius: 4px; }")
        
        self.ref_container = RefDropContainer()
        self.ref_container.dump_dropped.connect(self.add_external_dump)
        self.ref_container.setStyleSheet("background-color: #111;")
        self.group_list_layout_ai = QVBoxLayout(self.ref_container)
        self.group_list_layout_ai.setContentsMargins(5, 5, 5, 5)
        self.group_list_layout_ai.setSpacing(4)
        self.group_list_layout_ai.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.scroll_ref.setWidget(self.ref_container)
        page_ref_layout.addWidget(self.scroll_ref)
        self.mode_stack.addWidget(self.page_ref)
        
        # Page 2: Text Search
        self.page_text = QWidget()
        page_text_layout = QVBoxLayout(self.page_text)
        page_text_layout.setContentsMargins(0, 5, 0, 0)
        page_text_layout.setSpacing(8)
        page_text_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        lbl_text_search = QLabel("Введите текстовый запрос для поиска:" if AppContext.is_ru() else "Enter text query for search:")
        lbl_text_search.setStyleSheet("color: #ccc; font-size: 12px;")
        page_text_layout.addWidget(lbl_text_search)
        
        self.line_text_search = SearchTextEdit()
        self.line_text_search.setPlaceholderText("Например: кот сидит на столе" if AppContext.is_ru() else "E.g.: a cat sitting on a table")
        self.line_text_search.setStyleSheet("""
            QTextEdit {
                background-color: #222;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px;
                color: white;
                font-family: 'Consolas', 'Courier New';
                font-size: 13px;
            }
            QTextEdit:focus { border-color: #3b82f6; }
        """)
        self.text_highlighter = MultiTagHighlighter(self.line_text_search.document())
        page_text_layout.addWidget(self.line_text_search)
        
        # Action row for tags + Search button
        tags_action_layout = QHBoxLayout()
        is_ru = AppContext.is_ru()
        self.btn_manage_tags = QPushButton("⚙️ " + ("Теги" if is_ru else "Tags"))
        self.btn_manage_tags.setToolTip("Управление текстовыми тегами" if is_ru else "Manage text tags")
        self.btn_manage_tags.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_manage_tags.setStyleSheet("""
            QPushButton { background-color: #333; border: 1px solid #555; border-radius: 4px; padding: 4px 8px; color: #ccc; }
            QPushButton:hover { background-color: #444; color: white; }
        """)
        self.btn_manage_tags.clicked.connect(self.open_tag_manager)
        
        self.btn_info_tags = QPushButton("ℹ️")
        self.btn_info_tags.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_info_tags.setStyleSheet("QPushButton { background: transparent; border: none; font-size: 16px; }")
        self.btn_info_tags.clicked.connect(self.show_tags_info)
        
        self.btn_text_search = QPushButton("Найти" if AppContext.is_ru() else "Find")
        self.btn_text_search.setFixedHeight(32)
        self.btn_text_search.setFixedWidth(100)
        self.btn_text_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_text_search.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #2563eb; }
        """)
        
        tags_action_layout.addWidget(self.btn_manage_tags)
        tags_action_layout.addWidget(self.btn_info_tags)
        tags_action_layout.addStretch()
        tags_action_layout.addWidget(self.btn_text_search)
        
        page_text_layout.addLayout(tags_action_layout)
        
        # Tags container
        self.tags_scroll = QScrollArea()
        self.tags_scroll.setWidgetResizable(True)
        self.tags_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        self.tags_container = QWidget()
        self.tags_container.setStyleSheet("background: transparent;")
        self.tags_flow = FlowLayout(self.tags_container, margin=0, spacing=6)
        self.tags_scroll.setWidget(self.tags_container)
        
        page_text_layout.addWidget(self.tags_scroll)
        
        self.mode_stack.addWidget(self.page_text)
        
        self.refresh_tag_chips()
        
        self.btn_mode_ref.clicked.connect(lambda: self._switch_mode(0))
        self.btn_mode_text.clicked.connect(lambda: self._switch_mode(1))
        
        self.line_text_search.returnPressed.connect(self.start_text_search)
        self.btn_text_search.clicked.connect(self.start_text_search)

        top_layout.addLayout(col_ref, 1)
        
        # КОЛОНКА 2: Каталоги для поиска (ДРОП-ЗОНА НА ВСЮ ШИРИНУ В СТИЛЕ CLEANER)
        col_dirs = QVBoxLayout()
        col_dirs.setContentsMargins(0, 0, 0, 0)
        col_dirs.setSpacing(4)
        
        dirs_header = QHBoxLayout()
        dirs_title = QLabel("Каталоги для поиска" if AppContext.is_ru() else "Folders to Search")
        dirs_title.setStyleSheet("font-weight: bold; color: #888; font-size: 11px; font-family: 'Segoe UI';")
        dirs_header.addWidget(dirs_title)
        dirs_header.addStretch()
        col_dirs.addLayout(dirs_header)
        
        # Scroll area для тождественного отображения каталогов Cleaner
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
        
        # ТОЖДЕСТВЕННЫЙ DROP ZONE WIDGET НА ВСЮ ОБЛАСТЬ
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
        
        # Фильтр типов файлов (по аналогии с CleanerSettingsPanel)
        filter_layout_ai = QHBoxLayout()
        filter_layout_ai.setContentsMargins(0, 0, 0, 0)
        filter_layout_ai.setSpacing(8)
        
        from .ui_panels import load_svg_icon
        icons_dir_ai = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
        
        self.btn_filter_ai = QPushButton(AppContext.tr("cln_btn_scan_types") if AppContext.is_ru() else "Scan File Types")
        self.btn_filter_ai.setIcon(load_svg_icon(os.path.join(icons_dir_ai, "loupe-color.svg"), QSize(16, 16)))
        self.btn_filter_ai.setIconSize(QSize(16, 16))
        self.btn_filter_ai.setFixedHeight(36)
        self.btn_filter_ai.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_filter_ai.setStyleSheet("QPushButton { background-color: #444; color: #fff; border: 1px solid #666; padding: 0 10px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #555; color: white; border-color: #888; }")
        self.btn_filter_ai.clicked.connect(self.open_filter_dialog_ai)
        
        self.lbl_filter_status_ai = QLabel(AppContext.tr("cln_filter_all") if AppContext.is_ru() else "All images")
        self.lbl_filter_status_ai.setStyleSheet("color: #aaa; font-size: 11px;")
        self.lbl_filter_status_ai.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        filter_layout_ai.addWidget(self.btn_filter_ai)
        filter_layout_ai.addWidget(self.lbl_filter_status_ai)
        filter_layout_ai.addStretch()
        
        col_dirs.addLayout(filter_layout_ai)
        
        top_layout.addLayout(col_dirs, 1)
        
        # КОЛОНКА 3: Параметры поиска (С КНОПКОЙ-ИНФОРМАЦИЕЙ ℹ️)
        col_params = QVBoxLayout()
        col_params.setContentsMargins(0, 0, 0, 0)
        col_params.setSpacing(4)
        
        params_header = QHBoxLayout()
        params_title = QLabel("Параметры ИИ поиска" if AppContext.is_ru() else "AI Search Parameters")
        params_title.setStyleSheet("font-weight: bold; color: #888; font-size: 11px; font-family: 'Segoe UI';")
        params_header.addWidget(params_title)
        
        self.lbl_info_icon = QLabel("ℹ️")
        self.lbl_info_icon.setCursor(Qt.CursorShape.WhatsThisCursor)
        self.lbl_info_icon.setStyleSheet("""
            QLabel { color: #3b82f6; font-size: 12px; margin-left: 4px; background: transparent; border: none; }
            QToolTip { color: white; background-color: #2b2b2b; border: 1px solid #555; font-size: 12px; padding: 4px; border-radius: 4px; }
        """)
        
        info_text = (
            "🧠 КАК РАБОТАЕТ ИИ-ПОИСК:\n\n"
            "1. Типы анализа:\n"
            "   • Общее сходство: Используется модель OpenAI CLIP (ViT-B/32) для сравнения смысловой нагрузки, объектов и цветовой гаммы.\n"
            "   • Поиск лиц: Используется модель InsightFace для точного обнаружения лиц и их сопоставления.\n\n"
            "2. Сколько картинок-примеров добавлять:\n"
            "   • Для лиц: достаточно 1-3 четких фото лица под разными углами.\n"
            "   • Для общего поиска: достаточно 2-5 характерных скриншотов/картинок.\n\n"
            "3. Порог схожести (Confidence):\n"
            "   • 85% - 100%: Строгий поиск (тот же человек, почти идентичные скриншоты).\n"
            "   • 70% - 85%: Умеренное сходство (тот же человек в другой одежде, похожие сцены).\n"
            "   • 50% - 70%: Широкий поиск (похожие по цветам и структуре изображения).\n\n"
            "💡 Совет: Для лучшего результата используйте четкие примеры и отключайте ненужные группы Образцов."
            if AppContext.is_ru() else
            "🧠 HOW AI SEARCH WORKS:\n\n"
            "1. Analysis Types:\n"
            "   • General Similarity: Compares colors, composition, and objects.\n"
            "   • Face Recognition: Detects human faces and matches facial features.\n\n"
            "2. Number of Reference Images:\n"
            "   • For Faces: 1-3 clear photos from different angles are enough.\n"
            "   • For General: 2-5 typical screenshots or images.\n\n"
            "3. Similarity Threshold (Confidence):\n"
            "   • 85% - 100%: Strict match (same person, nearly identical screenshots).\n"
            "   • 70% - 85%: Medium match (same person in other clothes, similar scenes).\n"
            "   • 50% - 70%: Broad match (similar colors and structure).\n\n"
            "💡 Tip: Disable unused reference groups to speed up scanning."
        )
        self.lbl_info_icon.setToolTip(info_text)
        params_header.addWidget(self.lbl_info_icon)
        params_header.addStretch()
        col_params.addLayout(params_header)
        
        params_container = QFrame()
        params_container.setStyleSheet("QFrame { background-color: #1a1a1a; border: none; }")
        params_main_layout = QVBoxLayout(params_container)
        params_main_layout.setContentsMargins(8, 8, 8, 8)
        
        params_sub_layout = QVBoxLayout()
        params_sub_layout.setContentsMargins(0, 0, 0, 0)
        params_sub_layout.setSpacing(8)
        params_main_layout.addLayout(params_sub_layout)
        
        # Панель размера и очистки кэша
        cache_layout = QHBoxLayout()
        cache_layout.setContentsMargins(0, 0, 0, 0)
        
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
        
        self.lbl_cache_info_ai = QLabel("0 B")
        self.lbl_cache_info_ai.setStyleSheet("color: #888; font-size: 12px; margin-right: 5px;")
        cache_layout.addWidget(self.lbl_cache_info_ai)
        
        from .ui_panels import load_svg_icon
        self.btn_clear_cache_ai = QPushButton("")
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
        self.btn_clear_cache_ai.setIcon(load_svg_icon(os.path.join(icons_dir, "trash-color.svg"), QSize(16, 16)))
        self.btn_clear_cache_ai.setIconSize(QSize(16, 16))
        self.btn_clear_cache_ai.setToolTip("Очистить кэш ИИ" if AppContext.is_ru() else "Clear AI Cache")
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
        
        params_sub_layout.addLayout(cache_layout)
        
        # (Разделитель удален по просьбе пользователя)
        self.lbl_threshold = QLabel("Схожесть:" if AppContext.is_ru() else "Similarity:")
        tooltip_thresh = ("Базовый порог первичной группировки (до объединения).\n"
                          "Меньшие значения (50-60%): Образуются широкие группы с множеством потенциально похожих фото.\n"
                          "Оптимально (75-80%): Хороший баланс для старта.\n"
                          "Большие значения (90%+): В группу попадают только почти идентичные фото.")
        self.lbl_threshold.setToolTip(tooltip_thresh)
        self.lbl_threshold.setStyleSheet("color: #ccc; font-weight: bold; font-size: 11px; border: none; background: transparent;")
        params_sub_layout.addWidget(self.lbl_threshold)
        
        slider_layout = QHBoxLayout()
        self.slider_threshold = QSlider(Qt.Orientation.Horizontal)
        self.slider_threshold.setToolTip(tooltip_thresh)
        self.slider_threshold.setRange(0, 10000)
        self.slider_threshold.setValue(5000)
        self.slider_threshold.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #333; border-radius: 2px; }
            QSlider::handle:horizontal { background: #3b82f6; width: 12px; height: 12px; margin-top: -4px; margin-bottom: -4px; border-radius: 6px; }
        """)
        
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
        
        self.btn_up_sim.clicked.connect(self.spin_threshold.stepUp)
        self.btn_down_sim.clicked.connect(self.spin_threshold.stepDown)
        
        self.slider_threshold.valueChanged.connect(lambda v: self.spin_threshold.setValue(v / 100.0))
        self.spin_threshold.valueChanged.connect(lambda v: self.slider_threshold.setValue(int(v * 100)))
        
        slider_layout.addWidget(self.slider_threshold)
        slider_layout.addWidget(spin_container)
        params_sub_layout.addLayout(slider_layout)
        
        self.chk_auto_cluster = QCheckBox("Умный поиск" if AppContext.is_ru() else "Smart Search")
        self.chk_auto_cluster.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_auto_cluster.setStyleSheet("""
            QCheckBox { color: white; font-weight: bold; font-size: 13px; margin-top: 2px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 3px; border: 1px solid #555; background: #111; margin-top: 2px; }
            QCheckBox::indicator:checked { background-color: #3b82f6; border-color: #3b82f6; }
        """)
        self.chk_auto_cluster.setToolTip("Искать похожие объекты без Образцов и группировать их автоматически." if AppContext.is_ru() else "Group objects automatically without references.")
        self.chk_auto_cluster.stateChanged.connect(self.on_auto_cluster_changed)
        
        self.combo_auto_type = QComboBox()
        self.combo_auto_type.addItem("По людям" if AppContext.is_ru() else "By People", "face")
        self.combo_auto_type.addItem("По изображениям" if AppContext.is_ru() else "By Images", "general")
        self.combo_auto_type.setStyleSheet("QComboBox { background-color: #2b2b2b; color: white; border: 1px solid #444; border-radius: 4px; padding: 2px 5px; font-size: 11px; height: 22px; }")
        self.combo_auto_type.setFixedWidth(130)
        
        auto_h = QHBoxLayout()
        auto_h.addWidget(self.chk_auto_cluster)
        auto_h.addStretch()
        auto_h.addWidget(self.combo_auto_type)
        params_sub_layout.addLayout(auto_h)
        
        self.chk_use_gpu = QCheckBox("Аппаратное ускорение (GPU)" if AppContext.is_ru() else "Hardware Acceleration (GPU)")
        self.chk_use_gpu.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_use_gpu.setStyleSheet("""
            QCheckBox { color: white; font-weight: bold; font-size: 13px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 3px; border: 1px solid #555; background: #111; }
            QCheckBox::indicator:checked { background-color: #3b82f6; border-color: #3b82f6; }
        """)
        self.chk_use_gpu.setToolTip("Использовать CUDA/DirectML для ускорения ИИ (если доступно)." if AppContext.is_ru() else "Use CUDA/DirectML to accelerate AI (if available).")
        self.chk_use_gpu.setChecked(True)
        params_sub_layout.addWidget(self.chk_use_gpu)
        
        # Пружинка для выравнивания настроек по верхнему краю и прижатия кнопки вниз
        params_sub_layout.addStretch()
        
        # Инициализируем размер кэша
        QTimer.singleShot(100, self.update_cache_info_ai)
        
        self.btn_start_scan = QPushButton(" Начать ИИ Поиск" if AppContext.is_ru() else " Start AI Search")
        self.btn_start_scan.setFixedHeight(40)
        self.btn_start_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start_scan.setStyleSheet("""
            QPushButton { background-color: #15803d; color: white; font-weight: 900; font-size: 14px; border: 1px solid #16a34a; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
            QPushButton:hover { background-color: #16a34a; }
            QPushButton:disabled { background-color: #222; color: #555; font-weight: 900; font-size: 14px; border: 1px solid #333; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
        """)
        self.btn_start_scan.clicked.connect(self.on_btn_start_scan_clicked)
        params_sub_layout.addWidget(self.btn_start_scan)
        

        
        col_params.addWidget(params_container)
        top_layout.addLayout(col_params, 1)
        
        self.main_splitter.addWidget(self.top_settings)
        
        # Нижняя часть (таблица, превью, воркеры и кнопки действий)
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
        
        from .ui_panels import CleanerActionBar
        self.action_bar = CleanerActionBar()
        self.action_bar.is_similar_mode = False
        self.action_bar.combo_autoselect.hide()
        self.action_bar.btn_select_all.hide()
        self.action_bar.btn_deselect.hide()
        self.action_bar.chk_preserve.hide()
        self.action_bar.combo_collision.hide()
        post_filter_layout = QHBoxLayout()
        
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
        self.btn_exp_ai = QPushButton()
        self.btn_exp_ai.setIcon(QIcon(os.path.join(icons_dir, "square-chevron-down.svg")))
        self.btn_exp_ai.setIconSize(QSize(18, 18))
        self.btn_exp_ai.setToolTip(AppContext.tr("cln_btn_expand") if hasattr(AppContext, "tr") else "Развернуть все группы")
        
        self.btn_col_ai = QPushButton()
        self.btn_col_ai.setIcon(QIcon(os.path.join(icons_dir, "square-chevron-up.svg")))
        self.btn_col_ai.setIconSize(QSize(18, 18))
        self.btn_col_ai.setToolTip(AppContext.tr("cln_btn_collapse") if hasattr(AppContext, "tr") else "Свернуть все группы")
        
        for b in [self.btn_exp_ai, self.btn_col_ai]:
            b.setFixedWidth(30)
            b.setStyleSheet("QPushButton { background: #333; border: 1px solid #444; border-radius: 3px; } QPushButton:hover { background: #444; }")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            
        self.btn_exp_ai.clicked.connect(lambda: hasattr(self, "tree_results") and self.tree_results.expandAll())
        self.btn_col_ai.clicked.connect(lambda: hasattr(self, "tree_results") and self.tree_results.collapseAll())
        
        post_filter_layout.addWidget(self.btn_exp_ai)
        post_filter_layout.addWidget(self.btn_col_ai)
        post_filter_layout.addSpacing(10)
        
        self.lbl_post_filter = QLabel("Быстрый фильтр:" if AppContext.is_ru() else "Quick Filter:")
        tooltip_post = ("Скрывает из таблицы файлы, чья схожесть с лидером группы ниже выбранного процента.\n"
                        "Это НЕ удаляет файлы из списка результатов навсегда, а лишь временно скрывает их,\n"
                        "помогая сфокусироваться только на самых похожих фото.")
        self.lbl_post_filter.setToolTip(tooltip_post)
        self.lbl_post_filter.setStyleSheet("color: #ccc; font-size: 11px; font-weight: bold;")
        self.slider_post_filter = QSlider(Qt.Orientation.Horizontal)
        self.slider_post_filter.setToolTip(tooltip_post)
        self.slider_post_filter.setRange(0, 10000)
        self.slider_post_filter.setValue(0)
        self.slider_post_filter.setStyleSheet("""
            QSlider { border: none; background: transparent; }
            QSlider::groove:horizontal { height: 4px; background: #333; border-radius: 2px; border: none; }
            QSlider::handle:horizontal { background: #10b981; width: 12px; height: 12px; margin-top: -4px; margin-bottom: -4px; border-radius: 6px; border: none; }
        """)
        self.spin_post_filter = CleanSpinBox()
        self.spin_post_filter.setRange(0.0, 100.0)
        self.spin_post_filter.setDecimals(2)
        self.spin_post_filter.setSingleStep(0.01)
        self.spin_post_filter.setSuffix("%")
        self.spin_post_filter.setFixedWidth(65)
        self.spin_post_filter.setStyleSheet("border: none; background: transparent; color: #f0f0f0; font-weight: bold; font-size: 12px; padding: 0 4px;")
        
        self.slider_post_filter.valueChanged.connect(self._on_slider_moved)
        self.spin_post_filter.valueChanged.connect(self._on_spin_changed)
        self.spin_post_filter.valueChanged.connect(self.on_post_filter_changed)
        
        post_filter_layout.addWidget(self.lbl_post_filter)
        post_filter_layout.addWidget(self.slider_post_filter)
        post_filter_layout.addWidget(self.spin_post_filter)
        
        self.post_filter_widget = QWidget()
        self.post_filter_widget.setStyleSheet("border: none;")
        self.post_filter_widget.setLayout(post_filter_layout)
        self.post_filter_widget.hide() # Hidden until scan is done
        self.action_bar.layout().insertWidget(0, self.post_filter_widget)
        
        # Динамически добавляем лейбл выделения в CleanerActionBar для вкладки ИИ
        self.action_bar.lbl_selection_info = QLabel("Выбрано: 0 файлов • 0 B" if AppContext.is_ru() else "Selected: 0 files • 0 B")
        self.action_bar.lbl_selection_info.setStyleSheet("color: #93c5fd; font-size: 11px; font-weight: bold;")
        ab_layout = self.action_bar.layout()
        if ab_layout:
            ab_layout.insertWidget(3, self.action_bar.lbl_selection_info)
            
        self.action_bar.deselect_clicked.connect(lambda: self.select_all_results(False))
        self.action_bar.select_all_clicked.connect(lambda: self.select_all_results(True))
        
        self.action_bar.move_clicked.connect(self.cleaner.move_selected)
        self.action_bar.move_to_clicked.connect(self.cleaner.prompt_move_selected)
        self.action_bar.delete_clicked.connect(self.cleaner.delete_selected)
        self.action_bar.browse_clicked.connect(self.cleaner.browse_dest)
        self.action_bar.drop_zone.path_changed.connect(self.cleaner.validate_move_state)
        bot_layout.addWidget(self.action_bar)
        
        self.right_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.right_splitter.setHandleWidth(2)
        self.right_splitter.setStyleSheet("QSplitter::handle { background-color: #2d2d2d; }")
        
        self.tree_results = QTreeWidget()
        self.tree_results.setColumnCount(4)
        self.tree_results.setHeaderLabels([
            "Имя файла" if AppContext.is_ru() else "File Name",
            "Сходство (%)" if AppContext.is_ru() else "Similarity (%)",
            "Размер" if AppContext.is_ru() else "Size",
            "Путь" if AppContext.is_ru() else "Path"
        ])
        self.tree_results.setColumnWidth(0, 240)
        self.tree_results.setColumnWidth(1, 100)
        self.tree_results.setColumnWidth(2, 90)
        
        # ЗАМЕТНЫЕ ЧЕКБОКСЫ QTreeWidget (дизайн тождественный)
        self.tree_results.setStyleSheet("""
            QTreeWidget {
                background-color: #1a1a1a;
                border: none;
                outline: none;
                color: #eee;
            }
            QTreeWidget::item {
                padding: 6px;
                border-bottom: 1px solid #222;
            }
            QTreeWidget::item:selected {
                background-color: #2b2b2b;
                color: white;
            }
            QTreeWidget::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #666;
                border-radius: 3px;
                background-color: #2b2b2b;
            }
            QTreeWidget::indicator:hover {
                border-color: #3b82f6;
            }
            QTreeWidget::indicator:checked {
                background-color: #3b82f6;
                border: 1px solid #2563eb;
            }
            QTreeWidget::indicator:unchecked {
                background-color: #2b2b2b;
            }
        """)
        self.tree_results.itemSelectionChanged.connect(self.on_tree_selection_changed)
        self.tree_results.itemChanged.connect(self.on_tree_item_changed)
        
        # Поддержка контекстного меню по заголовку группы
        self.tree_results.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_results.customContextMenuRequested.connect(self.show_results_context_menu)
        
        tree_container = QWidget()
        tree_layout = QVBoxLayout(tree_container)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(4)
        
        
        tree_layout.addWidget(self.tree_results)
        
        self.right_splitter.addWidget(tree_container)
        
        from .ui_preview import CleanerPreviewWidget
        self.preview_widget = CleanerPreviewWidget()
        self.preview_widget.show_empty("Выберите файл для предпросмотра" if AppContext.is_ru() else "Select a file to preview")
        self.right_splitter.addWidget(self.preview_widget)
        
        self.right_splitter.setSizes([650, 350])
        bot_layout.addWidget(self.right_splitter, 1)
        
        self.main_splitter.addWidget(self.bottom_container)
        
        # Начальные размеры вертикального сплиттера: ~220px под настройки, остальное под таблицу
        self.main_splitter.setSizes([220, 400])
        
        content_layout.addWidget(self.main_splitter, 1)
        self.main_layout.addWidget(self.main_content_widget, 1)

    def check_models_status(self):
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
        self.placeholder_status.setText("Подключение..." if AppContext.is_ru() else "Connecting...")
        
        is_ru = AppContext.is_ru()
        
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
                self.placeholder_status.setText("Загрузка остановлена пользователем." if is_ru else "Download stopped by user.")
                return

            if success:
                self.placeholder_status.setStyleSheet("color: #4ade80;")
                self.placeholder_status.setText("Инициализация..." if is_ru else "Initializing...")
                
                if self.ai.initialize_sessions():
                    self.placeholder_status.setText("Успешно!" if is_ru else "Success!")
                    self.download_placeholder.hide()
                    self.main_content_widget.show()
                else:
                    self.placeholder_status.setStyleSheet("color: #ef4444;")
                    self.placeholder_status.setText("Ошибка инициализации!" if is_ru else "Initialization failed!")
            else:
                self.placeholder_status.setStyleSheet("color: #ef4444;")
                self.placeholder_status.setText("Ошибка при скачивании моделей!" if is_ru else "Failed to download models!")

        self.dl_thread.progress_signal.connect(on_progress)
        self.dl_thread.finished_signal.connect(on_finished)
        self.dl_thread.start()

    def stop_placeholder_download(self):
        if hasattr(self, 'dl_thread') and self.dl_thread and self.dl_thread.isRunning():
            self.btn_stop_download.setEnabled(False)
            self.placeholder_status.setStyleSheet("color: #f59e0b;")
            self.placeholder_status.setText("Отмена загрузки..." if AppContext.is_ru() else "Cancelling download...")
            self.dl_thread.stop()

    def reload_groups(self):
        self.chips_map.clear()
        while self.group_list_layout_ai.count():
            item = self.group_list_layout_ai.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        settings = load_ai_settings()
        groups = settings.get("groups", {})
        
        import os
        to_delete = []
        for name, info in groups.items():
            path = info.get("path")
            if not path or not os.path.exists(path):
                to_delete.append(name)
                
        if to_delete:
            for name in to_delete:
                del groups[name]
            settings["groups"] = groups
            save_ai_settings(settings)
            
        # Авто-добавление из системной директории
        from .logic_ai_classifier import get_ai_assets_dir
        assets_dir = get_ai_assets_dir()
        added_new = False
        if os.path.exists(assets_dir):
            for f in os.listdir(assets_dir):
                if f.lower().endswith(".mkaidump"):
                    path = os.path.join(assets_dir, f)
                    path_norm = os.path.normpath(path).lower()
                    found = any(os.path.normpath(info.get("path", "")).lower() == path_norm for info in groups.values())
                    if not found:
                        name = f.replace(".hash.mkaidump", "").replace(".mkaidump", "")
                        orig_name = name
                        c = 1
                        while name in groups:
                            name = f"{orig_name}_{c}"
                            c += 1
                        groups[name] = {"enabled": True, "path": path}
                        added_new = True
        
        if added_new:
            settings["groups"] = groups
            save_ai_settings(settings)
        
        # Сортируем: включенные сверху, затем по алфавиту
        sorted_groups = sorted(groups.items(), key=lambda item: (not item[1].get("enabled", True), item[0].lower()))
        
        for name, info in sorted_groups:
            status, count = self.classifier.get_group_status(name)
            is_face = info.get("type") == "face"
            is_enabled = info.get("enabled", True)
            
            # Check if it's a hash dump
            is_hash = info.get("is_hash_only", False)
            if not is_hash:
                import os
                if info.get("path") and os.path.exists(info.get("path")):
                    from .logic_ai_dump import load_dump_info
                    dump_info = load_dump_info(info["path"])
                    is_hash = dump_info.get("is_hash_only", False)
                    is_face = dump_info.get("type", "face") == "face"
                    
            display_name = f"[Hash] {name}" if is_hash else name
            
            from .logic_ai_classifier import get_ai_assets_dir
            assets_dir = os.path.normpath(get_ai_assets_dir()).lower()
            path_norm = os.path.normpath(info.get("path", "")).lower() if info.get("path") else ""
            is_external = not (path_norm and path_norm.startswith(assets_dir))
            
            widget = AiGroupChipWidget(display_name, is_enabled, is_face, status, count, is_external=is_external, parent=self)
            widget.state_changed.connect(self.on_group_state_changed)
            widget.settings_clicked.connect(lambda n=name: self.open_edit_group_dialog(n))
            widget.remove_clicked.connect(self.remove_group_from_list)
            self.group_list_layout_ai.addWidget(widget)
            self.chips_map[name] = widget
            
        self.update_scan_button_state()

    def remove_group_from_list(self, group_name: str):
        settings = load_ai_settings()
        if "groups" in settings and group_name in settings["groups"]:
            del settings["groups"][group_name]
            save_ai_settings(settings)
        self.reload_groups()

    def on_group_state_changed(self, group_name: str, is_enabled: bool):
        settings = load_ai_settings()
        if group_name in settings.get("groups", {}):
            settings["groups"][group_name]["enabled"] = is_enabled
            save_ai_settings(settings)
            
        if group_name in self.chips_map:
            self.chips_map[group_name].set_error_highlight(False)
            
        self.update_scan_button_state()

    def open_edit_group_dialog(self, group_name: str):
        dlg = AiGroupSettingsDialog(self.classifier, group_name, self)
        dlg.exec()
        self.reload_groups()

    

    
    def add_external_dump(self, path: str):
        settings = load_ai_settings()
        groups = settings.get("groups", {})
        
        name = os.path.basename(path).replace(".hash.mkaidump", "").replace(".mkaidump", "")
        
        original_name = name
        counter = 1
        while name in groups:
            name = f"{original_name}_{counter}"
            counter += 1
            
        groups[name] = {"enabled": True, "path": path}
        settings["groups"] = groups
        save_ai_settings(settings)
        
        self.reload_groups()

    def create_group(self):
        dlg = AiGroupSettingsDialog(self.classifier, None, self)
        dlg.exec()
        self.reload_groups()

    def on_threshold_changed(self, value):
        pass

    def on_auto_cluster_changed(self, state):
        is_cluster = (state == Qt.CheckState.Checked.value)
        # Disable reference groups container if clustering is enabled
        self.ref_container.setEnabled(not is_cluster)
        self.scroll_ref.setEnabled(not is_cluster)
        if is_cluster:
            self.scroll_ref.setStyleSheet("QScrollArea { border: 1px solid #333; background-color: #1e1e1e; border-radius: 4px; }")
            self.ref_container.setStyleSheet("background-color: #1e1e1e; opacity: 0.5;")
        else:
            self.scroll_ref.setStyleSheet("QScrollArea { border: 1px solid #333; background-color: #111; border-radius: 4px; }")
            self.ref_container.setStyleSheet("background-color: #111;")
        
        self.update_scan_button_state()



    def _on_slider_moved(self, value):
        if getattr(self, "is_cluster_results", False) and hasattr(self, "cluster_unique_sizes"):
            if 0 <= value < len(self.cluster_unique_sizes):
                self.spin_post_filter.setValue(float(self.cluster_unique_sizes[value]))
        else:
            self.spin_post_filter.setValue(value / 100.0)

    def _on_spin_changed(self, value):
        self.slider_post_filter.blockSignals(True)
        if getattr(self, "is_cluster_results", False) and hasattr(self, "cluster_unique_sizes"):
            try:
                closest_idx = min(range(len(self.cluster_unique_sizes)), key=lambda i: abs(self.cluster_unique_sizes[i] - value))
                self.slider_post_filter.setValue(closest_idx)
            except ValueError:
                pass
        else:
            self.slider_post_filter.setValue(int(value * 100))
        self.slider_post_filter.blockSignals(False)

    def on_post_filter_changed(self, value):
        root = self.tree_results.invisibleRootItem()
        self.tree_results.blockSignals(True)
        try:
            for i in range(root.childCount()):
                group_item = root.child(i)
                group_visible_children = 0
                
                if getattr(self, "is_cluster_results", False):
                    target_size = int(value)
                    actual_size = group_item.childCount()
                    if actual_size < target_size:
                        group_item.setHidden(True)
                        for j in range(actual_size):
                            child = group_item.child(j)
                            if child.checkState(0) == Qt.CheckState.Checked:
                                child.setCheckState(0, Qt.CheckState.Unchecked)
                        if group_item.checkState(0) == Qt.CheckState.Checked:
                            group_item.setCheckState(0, Qt.CheckState.Unchecked)
                    else:
                        group_item.setHidden(False)
                else:
                    target_similarity = float(value)
                    for j in range(group_item.childCount()):
                        child = group_item.child(j)
                        data = child.data(0, Qt.ItemDataRole.UserRole)
                        if data:
                            sim = data.get("confidence", 0.0) * 100.0
                            if sim < target_similarity:
                                child.setHidden(True)
                                if child.checkState(0) == Qt.CheckState.Checked:
                                    child.setCheckState(0, Qt.CheckState.Unchecked)
                            else:
                                child.setHidden(False)
                                group_visible_children += 1
                    
                    if group_visible_children == 0:
                        group_item.setHidden(True)
                        if group_item.checkState(0) == Qt.CheckState.Checked:
                            group_item.setCheckState(0, Qt.CheckState.Unchecked)
                    else:
                        group_item.setHidden(False)
        finally:
            self.tree_results.blockSignals(False)
            
        visible_groups = 0
        visible_files = 0
        visible_bytes = 0
        for i in range(root.childCount()):
            group_item = root.child(i)
            if not group_item.isHidden():
                visible_groups += 1
                for j in range(group_item.childCount()):
                    child = group_item.child(j)
                    if not child.isHidden():
                        visible_files += 1
                        data = child.data(0, Qt.ItemDataRole.UserRole)
                        if data and 'size' in data:
                            visible_bytes += data['size']
                            
        from utils_common import format_size
        self.lbl_stats.setText(
            f"Отображено: {visible_groups} групп, {visible_files} файлов, {visible_bytes // (1024*1024) if visible_bytes else 0} MB" if AppContext.is_ru()
            else f"Displayed: {visible_groups} groups, {visible_files} files, {format_size(visible_bytes)}"
        )
            
        self.update_cleaner_action_bar_info()


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
            import logging
            logging.error(f"Ошибка получения размера ИИ-кэша: {e}")
            self.lbl_cache_info_ai.setText("0 B")

    def clear_ai_cache_ui(self):
        is_ru = AppContext.is_ru()
        reply = QMessageBox.question(
            self,
            "Очистить кэш ИИ" if is_ru else "Clear AI Cache",
            "Вы уверены, что хотите полностью очистить кэш ИИ? Это сбросит кэшированные признаки всех изображений и при повторном сканировании потребуется их полный анализ."
            if is_ru else
            "Are you sure you want to clear the AI cache? This will reset all cached features and require full analysis next time.",
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
        # 1. Очищаем старые виджеты из макета
        while self.folder_list_layout_ai.count():
            item = self.folder_list_layout_ai.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
                
        # 2. Добавляем папки заново
        from .ui_widgets import SourceListItem
        
        for idx, path in enumerate(folders):
            color = "#3b82f6"
            is_system = False
            if path in self.cleaner.source_folders:
                color = self.cleaner.source_folders[path].get('color', color)
                is_system = self.cleaner.source_folders[path].get('is_system', False)
                
            # Проверяем наличие ИИ-кэша для папки
            is_cached, is_face_cached = self.cache.has_cached_files_for_folder(path)
            
            item_widget = SourceListItem(path, color, is_cached=is_cached, is_face_cached=is_face_cached)
            if is_system:
                item_widget.set_system_error_state()
                
            item_widget.removed.connect(self.cleaner.remove_folder)
            item_widget.context_menu_requested.connect(self.cleaner.show_source_menu)
            
            self.folder_list_layout_ai.addWidget(item_widget)
            
        self.update_scan_button_state()

    

    def open_tag_manager(self):
        dlg = AiTagManagerDialog(self.tags_manager, self)
        dlg.tags_changed.connect(self.refresh_tag_chips)
        dlg.exec()

    def show_tags_info(self):
        from PyQt6.QtWidgets import QMessageBox
        msg = QMessageBox(self)
        msg.setWindowTitle("Справка по текстовым тегам" if AppContext.is_ru() else "Text Tags Help")
        
        ru_text = (
            "<b>Сложные поисковые запросы (Мультитеги):</b><br>"
            "Вы можете вводить сложные запросы прямо в строку поиска, используя круглые скобки и двоеточие.<br>"
            "Синтаксис: <b>(Заголовок: запрос 1, запрос 2, ...)</b><br>"
            "<i>Пример:</i> запрос <b>(Домашние животные: кошка, собака, попугай)</b> создаст одну колонку результатов "
            "с именем «Домашние животные», в которой будут собраны все 3 вида животных.<br><br>"
            "<b>Система сохраненных тегов:</b><br>"
            "Теги — это удобные закладки для ваших частых запросов.<br>"
            "Заголовок тега формирует название группы результатов, в которую будет выводиться поиск:<br>"
            "• По <i>одиночному тегу</i> (например, «Собака») — группа будет называться так же.<br>"
            "• По <i>мультитегу</i> — заголовок тега станет именем группы для множественного запроса.<br><br>"
            "Вы можете комбинировать обычный текст в строке поиска с выбранными тегами. Каждый отдельный тег или запрос "
            "создает свою независимую колонку результатов.<br><br>"
            "<i>💡 Подсказка: Если поиск на русском языке не выдает нужный результат или путает объекты, "
            "попробуйте ввести запрос на английском языке — базовая модель распознает его более качественно.</i>"
        )
        
        en_text = (
            "<b>Complex Search Queries (Multi-tags):</b><br>"
            "You can enter complex queries directly into the search bar using parentheses and a colon.<br>"
            "Syntax: <b>(Header: query 1, query 2, ...)</b><br>"
            "<i>Example:</i> query <b>(Pets: cat, dog, parrot)</b> creates a single result group "
            "named 'Pets' containing all 3 types of animals.<br><br>"
            "<b>Saved Tags System:</b><br>"
            "Tags are convenient bookmarks for your frequent queries.<br>"
            "The tag header sets the name of the result group for the search:<br>"
            "• For a <i>single tag</i> (e.g., 'Dog') — the group will have the same name.<br>"
            "• For a <i>multi-tag</i> — the tag header becomes the group name for multiple queries.<br><br>"
            "You can combine plain text in the search bar with selected tags. Each individual tag or query "
            "creates its own independent result column."
        )
        
        msg.setText(ru_text if AppContext.is_ru() else en_text)
        msg.exec()

    def refresh_tag_chips(self):
        # Clear existing
        while self.tags_flow.count():
            item = self.tags_flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        self.active_tag_buttons.clear()
        
        tags = self.tags_manager.get_tags()
        for name, body in tags.items():
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            
            is_multi = "," in body
            base_color = "#d97706" if is_multi else "#166534"
            hover_color = "#f59e0b" if is_multi else "#15803d"
            
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: #888;
                    border: 1px solid #444;
                    border-radius: 12px;
                    padding: 4px 10px;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    border-color: {hover_color};
                    color: #eee;
                }}
                QPushButton:checked {{
                    background-color: {base_color};
                    color: white;
                    border: 1px solid {hover_color};
                }}
            """)
            
            self.active_tag_buttons[name] = btn
            self.tags_flow.addWidget(btn)

    def _switch_mode(self, index):
        self.mode_stack.setCurrentIndex(index)
        self.btn_mode_ref.setChecked(index == 0)
        self.btn_mode_text.setChecked(index == 1)
        self.update_scan_button_state()

    def start_text_search(self):
        # Trigger scanning
        query = self.line_text_search.toPlainText().strip()
        
        active_tags = []
        for name, btn in self.active_tag_buttons.items():
            if btn.isChecked():
                body = self.tags_manager.get_tags().get(name)
                if body:
                    # Format as multi-tag group so parse_multi_tags handles it correctly
                    # A tag like 'собака' with body 'собака' becomes (собака: собака)
                    active_tags.append(f"({name}: {body})")
                    
        combined_query = ", ".join(filter(None, [query] + active_tags))
        
        if not combined_query:
            from PyQt6.QtWidgets import QMessageBox
            from config import AppContext
            QMessageBox.warning(self, "Внимание" if AppContext.is_ru() else "Warning", "Введите текстовый запрос или выберите тег." if AppContext.is_ru() else "Please enter a query or select a tag.")
            return
        
        self.toggle_scan(text_query=combined_query)

    def update_scan_button_state(self):
        folders = self.cleaner.get_active_source_folders() if hasattr(self, 'cleaner') else []
        has_folders = len(folders) > 0
        has_enabled_groups = any(widget.chk.isChecked() for widget in self.chips_map.values())
        is_cluster = self.chk_auto_cluster.isChecked()
        is_text_mode = hasattr(self, 'mode_stack') and self.mode_stack.currentIndex() == 1
        
        # _is_ok default to True because logic_actions will pass False if there is a nested/system error
        is_ok = getattr(self, '_is_ok', True) 
        
        if is_text_mode:
            can_run = has_folders and is_ok
        else:
            can_run = has_folders and (has_enabled_groups or is_cluster) and is_ok
            
        self.btn_start_scan.setEnabled(can_run)
        
        base_text = " Начать ИИ Поиск" if AppContext.is_ru() else " Start AI Search"
        self.btn_start_scan.setText(base_text)



    def on_btn_start_scan_clicked(self):
        if hasattr(self, 'mode_stack') and self.mode_stack.currentIndex() == 1:
            self.start_text_search()
        else:
            self.toggle_scan()

    def toggle_scan(self, text_query=None):
        if hasattr(self, 'facade') and self.facade.active_worker:
            self.facade.cancel_search()
            self.progress_bar.hide()
            self.btn_start_scan.setText(" Начать ИИ Поиск" if AppContext.is_ru() else " Start AI Search")
            self.btn_start_scan.setStyleSheet("""
                QPushButton { background-color: #15803d; color: white; font-weight: 900; font-size: 14px; border: 1px solid #16a34a; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
                QPushButton:hover { background-color: #16a34a; }
                QPushButton:disabled { background-color: #222; color: #555; font-weight: 900; font-size: 14px; border: 1px solid #333; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
            """)
            self.scan_finished.emit()
            return
            
        folders = self.cleaner.get_active_source_folders()
        if not folders:
            return
            
        for widget in self.chips_map.values():
            widget.set_error_highlight(False)
            
        is_cluster = self.chk_auto_cluster.isChecked()
        if not is_cluster and not text_query:
            settings = load_ai_settings()
            enabled_groups = [name for name, info in settings.get("groups", {}).items() if info.get("enabled", True)]
            
            if not enabled_groups:
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Icon.NoIcon)
                msg.setWindowTitle("Ошибка" if AppContext.is_ru() else "Error")
                msg.setText("Выберите хотя бы одну группу Образцов для поиска!" if AppContext.is_ru() else "Select at least one reference group to search!")
                msg.exec()
                return
                
            for name in enabled_groups:
                status, count = self.classifier.get_group_status(name)
                if status == "gray":
                    if name in self.chips_map:
                        self.chips_map[name].set_error_highlight(True)
                    msg = QMessageBox(self)
                    msg.setIcon(QMessageBox.Icon.NoIcon)
                    msg.setWindowTitle("Ошибка" if AppContext.is_ru() else "Error")
                    msg.setText(f"Группа '{name}' включена в поиск, но не содержит картинок-примеров! Загрузите картинки или выключите группу." if AppContext.is_ru()
                                else f"Group '{name}' is enabled but contains no reference images! Load images or disable the group.")
                    msg.exec()
                    return
                    
            needs_training = []
            for name in enabled_groups:
                status, count = self.classifier.get_group_status(name)
                if status == "orange":
                    needs_training.append(name)
                    
            if needs_training:
                if not self.check_and_download_models_ui():
                    return
                
            dlg = QDialog(self)
            dlg.setWindowTitle("Автоматическое обучение ИИ" if AppContext.is_ru() else "AI Auto-training")
            dlg.setFixedSize(300, 100)
            dlg_layout = QVBoxLayout(dlg)
            
            lbl_title = QLabel("Идет подготовка Образцов..." if AppContext.is_ru() else "Preparing reference groups...")
            bar = QProgressBar()
            bar.setRange(0, len(needs_training))
            
            dlg_layout.addWidget(lbl_title)
            dlg_layout.addWidget(bar)
            dlg.show()
            
            for idx, name in enumerate(needs_training):
                lbl_title.setText(f"Обучение Образца ({idx + 1}/{len(needs_training)}): {name}")
                from PyQt6.QtWidgets import QApplication
                QApplication.processEvents()
                
                success = self.classifier.train_group(name)
                if not success:
                    dlg.close()
                    QMessageBox.critical(self, "Ошибка" if AppContext.is_ru() else "Error", 
                                         f"Не удалось обучить группу '{name}'!" if AppContext.is_ru() else f"Failed to train group '{name}'!")
                    return
                bar.setValue(idx + 1)
                
            dlg.close()
            self.reload_groups()
            
        self.scan_started.emit()
        self.btn_start_scan.setText(" Остановить" if AppContext.is_ru() else " Stop")
        self.btn_start_scan.setStyleSheet("""
            QPushButton { background-color: #991b1b; color: white; font-weight: 900; font-size: 14px; border: 1px solid #7f1d1d; border-radius: 6px; font-family: 'Segoe UI'; padding: 4px; }
            QPushButton:hover { background-color: #b91c1c; }
        """)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.tree_results.clear()
        self.lbl_stats.setText("")
        
        filter_cfg = self.ai_filter_config
        threshold = float(self.spin_threshold.value())
        
        match_mode = "centroid"
        use_cache = self.chk_use_cache.isChecked()
        use_gpu = self.chk_use_gpu.isChecked()
        is_cluster = self.chk_auto_cluster.isChecked()
        cluster_type = self.combo_auto_type.currentData() if hasattr(self, 'combo_auto_type') else 'face'
        
        task_type = AiTaskType.TEXT_TO_IMAGE if text_query else (AiTaskType.AUTO_CLUSTER if is_cluster else AiTaskType.FIND_BY_REFERENCES)
        if task_type == AiTaskType.FIND_BY_REFERENCES:
            analysis_target = AiTarget.BOTH
        elif task_type == AiTaskType.TEXT_TO_IMAGE:
            analysis_target = AiTarget.IMAGES
        else:
            analysis_target = AiTarget.FACES if cluster_type == 'face' else AiTarget.IMAGES
        
        text_queries_dict = {}
        if text_query:
            parsed = parse_multi_tags(text_query)
            if parsed:
                text_queries_dict = parsed
            else:
                text_queries_dict["Текст"] = [text_query]
            
        scan_threshold = min(20.0, threshold) if task_type == AiTaskType.TEXT_TO_IMAGE else threshold
        request = AiSearchRequest(
            target_paths=folders,
            task_type=task_type,
            analysis_target=analysis_target,
            threshold=scan_threshold,
            file_filter_config=filter_cfg,
            text_queries=text_queries_dict,
            use_cache=use_cache,
            use_gpu=use_gpu
        )
        
        if not hasattr(self, 'facade'):
            self.facade = AiServiceFacade()
            self.facade.cache = self.cache
            
        self.facade.search(
            request,
            progress_callback=self.on_scan_progress,
            result_callback=self.on_scan_finished,
            error_callback=self.on_scan_error,
            classifier=self.classifier
        )

    def on_scan_error(self, error_msg):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(self, "Ошибка ИИ" if AppContext.is_ru() else "AI Error", error_msg)
        self.progress_bar.hide()
        self.btn_start_scan.setText(" Начать ИИ Поиск" if AppContext.is_ru() else " Start AI Search")
        self.btn_start_scan.setStyleSheet("""
            QPushButton { background-color: #15803d; color: white; font-weight: 900; font-size: 14px; border: 1px solid #16a34a; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
            QPushButton:hover { background-color: #16a34a; }
            QPushButton:disabled { background-color: #222; color: #555; font-weight: 900; font-size: 14px; border: 1px solid #333; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
        """)
        self.scan_finished.emit()

    def on_scan_progress(self, stage, percent, text, scanned_files, groups_found, wasted_bytes, scanned_bytes, files_found, empty):
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(int(percent))
        self.progress_bar.setFormat(f"{text} ({int(percent)}%)" if "%" not in text else text)
        
        # Меняем цвет полосы в зависимости от этапа
        if stage == STAGE_SCANNING:
            self.progress_bar.setStyleSheet("QProgressBar { border: none; background-color: #151515; text-align: center; color: white; font-size: 11px; } QProgressBar::chunk { background-color: #3b82f6; }")
        else:
            self.progress_bar.setStyleSheet("QProgressBar { border: none; background-color: #151515; text-align: center; color: white; font-size: 11px; } QProgressBar::chunk { background-color: #22c55e; }")
            
        from utils_common import format_size
        self.lbl_stats.setText(
            f"Найдено совпадений: {groups_found} групп, {files_found} файлов, {wasted_bytes // (1024*1024) if wasted_bytes else 0} MB" if AppContext.is_ru()
            else f"Matches found: {groups_found} groups, {files_found} files, {format_size(wasted_bytes)}"
        )

    def on_scan_finished(self, response: AiSearchResponse):
        from PyQt6.QtWidgets import QApplication
        self.progress_bar.setFormat("Формирование таблицы... (100%)" if AppContext.is_ru() else "Building table... (100%)")
        QApplication.processEvents()
        
        # Конвертируем response в старый формат dict для populate_results
        results_dict = {}
        for group in response.groups:
            results_dict[group.group_name] = []
            for mf in group.files:
                try:
                    import os
                    size = os.path.getsize(mf.path)
                except:
                    size = 0
                bbox_list = None
                if mf.matched_bbox:
                    bbox_list = [mf.matched_bbox.x1, mf.matched_bbox.y1, mf.matched_bbox.x2, mf.matched_bbox.y2]
                    
                results_dict[group.group_name].append({
                    "path": mf.path,
                    "confidence": mf.score,
                    "size": size,
                    "matched_bbox": bbox_list,
                    "type": "face" if mf.matched_bbox else "general"
                })
                
        self.populate_results(results_dict)
        
        self.progress_bar.hide()
        self.btn_start_scan.setText(" Начать ИИ Поиск" if AppContext.is_ru() else " Start AI Search")
        self.btn_start_scan.setStyleSheet("""
            QPushButton { background-color: #15803d; color: white; font-weight: 900; font-size: 14px; border: 1px solid #16a34a; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
            QPushButton:hover { background-color: #16a34a; }
            QPushButton:disabled { background-color: #222; color: #555; font-weight: 900; font-size: 14px; border: 1px solid #333; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
        """)
        
        self.scan_finished.emit()
        self.update_cache_info_ai()
        if hasattr(self, 'cleaner'):
            self.update_folders_label(self.cleaner.get_active_source_folders())



    def populate_results(self, results):
        self.tree_results.clear()
        msg = "Файл не выбран" if AppContext.is_ru() else "No file selected"
        self.preview_widget.show_empty(msg)
        self.file_selected.emit("")
        if not results:
            self.post_filter_widget.hide()
            return
            
        from utils_common import format_size
        
        self.is_cluster_results = self.chk_auto_cluster.isChecked()
        
        unique_sizes = set()
        
        for group_name, files in results.items():
            if not files:
                continue
                
            group_size = sum(f["size"] for f in files)
            num_files = len(files)
            unique_sizes.add(num_files)
            
            group_item = QTreeWidgetItem(self.tree_results)
            group_item.setText(0, f"Группа: {group_name} ({num_files} файлов)" if AppContext.is_ru() else f"Group: {group_name} ({num_files} files)")
            group_item.setText(2, format_size(group_size))
            group_item.setData(0, Qt.ItemDataRole.UserRole, {"is_group": True, "name": group_name})
            
            font = group_item.font(0)
            font.setBold(True)
            group_item.setFont(0, font)
            group_item.setFont(2, font)
            
            for f in files:
                file_item = QTreeWidgetItem(group_item)
                file_item.setCheckState(0, Qt.CheckState.Unchecked)
                file_item.setText(0, os.path.basename(f["path"]))
                file_item.setText(1, f"{f['confidence']:.1f}%")
                file_item.setText(2, format_size(f["size"]))
                file_item.setText(3, f["path"])
                file_item.setData(0, Qt.ItemDataRole.UserRole, {"is_group": False, "path": f["path"], "size": f["size"], "confidence": f.get("confidence", 0.0) / 100.0, "matched_bbox": f.get("matched_bbox"), "type": f.get("type", "face")})
                
            group_item.setExpanded(True)
            
        self.spin_post_filter.blockSignals(True)
        self.slider_post_filter.blockSignals(True)
        if self.is_cluster_results:
            sizes = sorted(list(unique_sizes))
            self.cluster_unique_sizes = sizes
            min_size = min(sizes) if sizes else 1
            max_size = max(sizes) if sizes else 100
            self.spin_post_filter.setSuffix(" ф." if AppContext.is_ru() else " f.")
            self.spin_post_filter.setDecimals(0)
            self.spin_post_filter.setSingleStep(1.0)
            self.spin_post_filter.setRange(float(min_size), float(max_size))
            self.slider_post_filter.setRange(0, len(sizes) - 1 if sizes else 0)
            default_val = 2.0
            if max_size < 2:
                default_val = float(max_size)
            self.spin_post_filter.setValue(default_val)
            try:
                idx = min(range(len(sizes)), key=lambda i: abs(sizes[i] - default_val))
                self.slider_post_filter.setValue(idx)
            except ValueError:
                pass
        else:
            self.spin_post_filter.setSuffix("%")
            self.spin_post_filter.setDecimals(2)
            self.spin_post_filter.setSingleStep(0.01)
            scan_threshold = self.spin_threshold.value()
            self.spin_post_filter.setRange(scan_threshold, 100.0)
            self.slider_post_filter.setRange(int(scan_threshold * 100), 10000)
            self.spin_post_filter.setValue(scan_threshold)
            
        self.spin_post_filter.blockSignals(False)
        self.slider_post_filter.blockSignals(False)
        
        self.post_filter_widget.show()
        if self.is_cluster_results:
            self.on_post_filter_changed(self.spin_post_filter.value())

    def on_tree_selection_changed(self):
        selected_items = self.tree_results.selectedItems()
        if not selected_items:
            msg = "Файл не выбран" if AppContext.is_ru() else "No file selected"
            self.preview_widget.show_empty(msg)
            self.file_selected.emit("")
            return
            
        item = selected_items[0]
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and not data.get("is_group", False):
            path = data.get("path")
            if path and os.path.exists(path):
                self.preview_widget.load_file(path)
                
                # Попытка извлечь лица из кэша и нарисовать их (зелёным — целевое лицо, красным — остальные)
                try:
                    stat = os.stat(path)
                    mtime = stat.st_mtime
                    size = stat.st_size
                    faces = self.classifier.cache.get_file_faces(path, mtime, size)
                    if faces:
                        bboxes = [f.get("bbox") for f in faces if f.get("bbox")]
                        matched_bbox = data.get("matched_bbox") if data else None
                        if hasattr(self.preview_widget, "draw_faces"):
                            self.preview_widget.draw_faces(bboxes, matched_bbox=matched_bbox)
                except Exception as e:
                    import logging
                    logging.error(f"Ошибка получения лиц для предпросмотра: {e}")
                        
                self.file_selected.emit(path)
        else:
            msg = "Файл не выбран" if AppContext.is_ru() else "No file selected"
            self.preview_widget.show_empty(msg)
            self.file_selected.emit("")

    def on_tree_item_changed(self, item, column):
        if column != 0:
            return
            
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
            
        self.tree_results.blockSignals(True)
        try:
            target_paths = []
            target_state = item.checkState(0)
            
            if data.get("is_group", False):
                for i in range(item.childCount()):
                    child = item.child(i)
                    if not child.isHidden():
                        child.setCheckState(0, target_state)
                        child_data = child.data(0, Qt.ItemDataRole.UserRole)
                        if child_data:
                            target_paths.append(child_data.get("path"))
            else:
                target_paths.append(data.get("path"))
                parent = item.parent()
                if parent:
                    all_checked = True
                    any_checked = False
                    visible_count = 0
                    for i in range(parent.childCount()):
                        if parent.child(i).isHidden(): continue
                        visible_count += 1
                        c_state = parent.child(i).checkState(0)
                        if c_state == Qt.CheckState.Checked:
                            any_checked = True
                        else:
                            all_checked = False
                            
                    if visible_count > 0:
                        if all_checked:
                            parent.setCheckState(0, Qt.CheckState.Checked)
                        elif any_checked:
                            parent.setCheckState(0, Qt.CheckState.PartiallyChecked)
                        else:
                            parent.setCheckState(0, Qt.CheckState.Unchecked)
                            
            if getattr(self, "is_cluster_results", False) and target_paths:
                root = self.tree_results.invisibleRootItem()
                target_paths_set = set(target_paths)
                for i in range(root.childCount()):
                    g_item = root.child(i)
                    needs_parent_update = False
                    for j in range(g_item.childCount()):
                        c_item = g_item.child(j)
                        if c_item.isHidden() or c_item == item:
                            continue
                        c_data = c_item.data(0, Qt.ItemDataRole.UserRole)
                        if c_data and c_data.get("path") in target_paths_set:
                            c_item.setCheckState(0, target_state)
                            needs_parent_update = True
                            
                    if needs_parent_update:
                        all_checked = True
                        any_checked = False
                        visible_count = 0
                        for k in range(g_item.childCount()):
                            if g_item.child(k).isHidden(): continue
                            visible_count += 1
                            cs = g_item.child(k).checkState(0)
                            if cs == Qt.CheckState.Checked:
                                any_checked = True
                            else:
                                all_checked = False
                        if visible_count > 0:
                            if all_checked:
                                g_item.setCheckState(0, Qt.CheckState.Checked)
                            elif any_checked:
                                g_item.setCheckState(0, Qt.CheckState.PartiallyChecked)
                            else:
                                g_item.setCheckState(0, Qt.CheckState.Unchecked)
        finally:
            self.tree_results.blockSignals(False)
            
        self.update_cleaner_action_bar_info()

    def get_selected_files_paths(self) -> list:
        paths = []
        root = self.tree_results.invisibleRootItem()
        for i in range(root.childCount()):
            group_item = root.child(i)
            for j in range(group_item.childCount()):
                file_item = group_item.child(j)
                if file_item.checkState(0) == Qt.CheckState.Checked:
                    data = file_item.data(0, Qt.ItemDataRole.UserRole)
                    if data and data.get("path"):
                        paths.append(data["path"])
        return paths

    def select_all_results(self, checked: bool):
        self.tree_results.blockSignals(True)
        try:
            root = self.tree_results.invisibleRootItem()
            state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            for i in range(root.childCount()):
                group_item = root.child(i)
                if checked and group_item.isHidden():
                    continue
                group_item.setCheckState(0, state)
                for j in range(group_item.childCount()):
                    child = group_item.child(j)
                    if checked and child.isHidden():
                        continue
                    child.setCheckState(0, state)
        finally:
            self.tree_results.blockSignals(False)
        self.update_cleaner_action_bar_info()

    def update_cleaner_action_bar_info(self):
        selected_paths = self.get_selected_files_paths()
        count = len(selected_paths)
        size = sum(os.path.getsize(p) for p in selected_paths if os.path.exists(p))
        
        from utils_common import format_size
        size_str = format_size(size)
        
        self.action_bar.lbl_selection_info.setStyleSheet("color: #93c5fd; font-size: 11px; font-weight: bold;")
        self.action_bar.lbl_selection_info.setText(f"Выбрано: {count} файлов • {size_str}")
        self.action_bar.lbl_selection_info.setToolTip(f"Выбрано файлов: {count}\nРазмер: {size_str}")
        
        has_selection = (count > 0)
        self.action_bar.btn_delete.setEnabled(has_selection)
        self.action_bar.btn_move.setEnabled(has_selection and bool(self.action_bar.drop_zone.get_path()))
        self.action_bar.btn_move_to.setEnabled(has_selection)

    def remove_processed_files(self, paths: list[str]):
        paths_set = set(os.path.normpath(p) for p in paths)
        root = self.tree_results.invisibleRootItem()
        
        for i in range(root.childCount() - 1, -1, -1):
            group_item = root.child(i)
            for j in range(group_item.childCount() - 1, -1, -1):
                file_item = group_item.child(j)
                data = file_item.data(0, Qt.ItemDataRole.UserRole)
                if data and data.get("path") and os.path.normpath(data["path"]) in paths_set:
                    group_item.removeChild(file_item)
                    
            if group_item.childCount() == 0:
                root.removeChild(group_item)
                
        self.preview_widget.show_empty("Выберите файл для предпросмотра" if AppContext.is_ru() else "Select a file to preview")
        self.update_cleaner_action_bar_info()

    def show_results_context_menu(self, pos: QPoint):
        """Контекстное меню по заголовку группы результатов."""
        item = self.tree_results.itemAt(pos)
        if not item:
            return
            
        data = item.data(0, Qt.ItemDataRole.UserRole)
        is_ru = AppContext.is_ru()
        if data and data.get("is_group", False):
            menu = QMenu(self)
            menu.setStyleSheet("QMenu { background-color: #2b2b2b; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #3b82f6; } QMenu::separator { height: 1px; background: #666; margin: 4px 8px; }")
            
            act_select = QAction("Выделить все файлы в этой группе" if is_ru else "Select all files in this group", self)
            act_deselect = QAction("Снять выделение со всех файлов в группе" if is_ru else "Deselect all files in this group", self)
            act_invert = QAction("Инвертировать выделение" if is_ru else "Invert Selection", self)
            
            act_select.triggered.connect(lambda: self.set_group_selection_state(item, Qt.CheckState.Checked))
            act_deselect.triggered.connect(lambda: self.set_group_selection_state(item, Qt.CheckState.Unchecked))
            act_invert.triggered.connect(lambda: self.invert_group_selection(item))
            
            menu.addAction(act_select)
            menu.addAction(act_deselect)
            menu.addAction(act_invert)
            
            menu.addSeparator()
            act_send_sorter = QAction("Отправить эту группу в Сортировщик", self)
            act_send_sorter.triggered.connect(lambda checked, gi=item: self._send_group_to_sorter(gi))
            menu.addAction(act_send_sorter)
            
            menu.addSeparator()
            act_expand_all = QAction("Развернуть все группы" if is_ru else "Expand all groups", self)
            act_collapse_all = QAction("Свернуть все группы" if is_ru else "Collapse all groups", self)
            act_expand_all.triggered.connect(self.tree_results.expandAll)
            act_collapse_all.triggered.connect(self.tree_results.collapseAll)
            menu.addAction(act_expand_all)
            menu.addAction(act_collapse_all)
            
            menu.exec(self.tree_results.mapToGlobal(pos))
        elif data and not data.get("is_group", False):
            menu = QMenu(self)
            menu.setStyleSheet("QMenu { background-color: #2b2b2b; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #3b82f6; } QMenu::separator { height: 1px; background: #666; margin: 4px 8px; }")
            path = data.get("path")
            
            act_open = QAction("Открыть файл" if is_ru else "Open File", self)
            act_open.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
            menu.addAction(act_open)
            
            act_reveal = QAction("Показать в папке" if is_ru else "Show in folder", self)
            from utils_common import reveal_in_explorer
            act_reveal.triggered.connect(lambda: reveal_in_explorer(path))
            menu.addAction(act_reveal)
            
            menu.addSeparator()
            
            group_item = item.parent()
            act_select = QAction("Выделить все файлы в этой группе" if is_ru else "Select all files in this group", self)
            act_deselect = QAction("Снять выделение со всех файлов в группе" if is_ru else "Deselect all files in this group", self)
            act_invert = QAction("Инвертировать выделение в группе" if is_ru else "Invert Selection in group", self)
            
            act_select.triggered.connect(lambda: self.set_group_selection_state(group_item, Qt.CheckState.Checked))
            act_deselect.triggered.connect(lambda: self.set_group_selection_state(group_item, Qt.CheckState.Unchecked))
            act_invert.triggered.connect(lambda: self.invert_group_selection(group_item))
            
            menu.addAction(act_select)
            menu.addAction(act_deselect)
            menu.addAction(act_invert)
            
            menu.addSeparator()
            act_send_sorter = QAction("Отправить эту группу в Сортировщик", self)
            act_send_sorter.triggered.connect(lambda checked, gi=group_item: self._send_group_to_sorter(gi))
            menu.addAction(act_send_sorter)
            
            menu.addSeparator()
            act_expand_all = QAction("Развернуть все группы" if is_ru else "Expand all groups", self)
            act_collapse_all = QAction("Свернуть все группы" if is_ru else "Collapse all groups", self)
            act_expand_all.triggered.connect(self.tree_results.expandAll)
            act_collapse_all.triggered.connect(self.tree_results.collapseAll)
            menu.addAction(act_expand_all)
            menu.addAction(act_collapse_all)
            
            menu.exec(self.tree_results.mapToGlobal(pos))

    def set_group_selection_state(self, group_item, state):
        self.tree_results.blockSignals(True)
        try:
            group_item.setCheckState(0, state)
            for i in range(group_item.childCount()):
                group_item.child(i).setCheckState(0, state)
        finally:
            self.tree_results.blockSignals(False)
        self.update_cleaner_action_bar_info()

    def invert_group_selection(self, group_item):
        if not group_item: return
        self.tree_results.blockSignals(True)
        try:
            checked_count = 0
            for i in range(group_item.childCount()):
                child = group_item.child(i)
                new_state = Qt.CheckState.Checked if child.checkState(0) == Qt.CheckState.Unchecked else Qt.CheckState.Unchecked
                child.setCheckState(0, new_state)
                if new_state == Qt.CheckState.Checked:
                    checked_count += 1
            
            if checked_count == 0:
                group_item.setCheckState(0, Qt.CheckState.Unchecked)
            elif checked_count == group_item.childCount():
                group_item.setCheckState(0, Qt.CheckState.Checked)
            else:
                group_item.setCheckState(0, Qt.CheckState.PartiallyChecked)
        finally:
            self.tree_results.blockSignals(False)
        self.update_cleaner_action_bar_info()

    def _send_group_to_sorter(self, group_item):
        if not group_item: return
        data = group_item.data(0, Qt.ItemDataRole.UserRole)
        if not data or not data.get("is_group", False): return
        
        group_name = data.get("name", "Unknown")
        
        files = []
        total_size = 0
        
        for i in range(group_item.childCount()):
            child = group_item.child(i)
            c_data = child.data(0, Qt.ItemDataRole.UserRole)
            if c_data:
                path = c_data.get("path")
                if path and os.path.exists(path):
                    files.append(path)
                    total_size += c_data.get("size", 0)
                    
        if not files: return
        
        virtual_name = "ИИ Поиск"
        
        main_win = self.window()
        if hasattr(main_win, 'sorter_tab') and hasattr(main_win, 'switch_tab'):
            main_win.sorter_tab.load_virtual_files(files, virtual_name)
            main_win.switch_tab(0)



# -----------------------------------------------------------------------------
# Кнопка чекбокса, использующаяся в чипах Образцов
# -----------------------------------------------------------------------------

    def open_filter_dialog_ai(self):
        self.btn_filter_ai.setEnabled(False)
        self.btn_filter_ai.setText("Сканирование..." if AppContext.is_ru() else "Scanning...")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, self._run_extension_scan_ai)

    def _run_extension_scan_ai(self):
        folders = list(self.cleaner.source_folders.keys())
        if not folders:
            self.btn_filter_ai.setEnabled(True)
            self.btn_filter_ai.setText(AppContext.tr("cln_btn_scan_types") if AppContext.is_ru() else "Scan File Types")
            return

        from .workers import ExtensionScannerWorker
        self.ext_scanner_ai = ExtensionScannerWorker(folders)
        self.ext_scanner_ai.finished.connect(self._on_ext_scan_finished_ai)
        self.ext_scanner_ai.start()

    def _on_ext_scan_finished_ai(self, stats: dict):
        self.btn_filter_ai.setEnabled(True)
        self.btn_filter_ai.setText(AppContext.tr("cln_btn_scan_types") if AppContext.is_ru() else "Scan File Types")
        
        from .ui_dialogs import MatrixFilterDialog
        dlg = MatrixFilterDialog(stats, self)
        if dlg.exec():
            res = dlg.get_result()
            self.ai_filter_config = {'mode': res['mode'], 'exts': res['exts']}
            
            count = len(res['exts'])
            if count == 0:
                self.lbl_filter_status_ai.setText(AppContext.tr("cln_filter_all") if AppContext.is_ru() else "All images")
            else:
                key = "Вкл" if res['mode'] == 'include' else "Искл"
                self.lbl_filter_status_ai.setText(f"Фильтр: {key} {count} типов" if AppContext.is_ru() else f"Filter: {key} {count} types")


class QCheckBoxCustom(QPushButton):
    toggled = pyqtSignal(bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(16, 16)
        self.clicked.connect(self._on_clicked)
        self.update_style()
        
    def _on_clicked(self):
        self.toggled.emit(self.isChecked())
        self.update_style()
        
    def setChecked(self, checked):
        super().setChecked(checked)
        self.update_style()
        
    def update_style(self):
        if self.isChecked():
            self.setStyleSheet("background-color: #3b82f6; border: 1px solid #2563eb; border-radius: 3px; color: white; font-size: 10px; font-weight: bold;")
            self.setText("✓")
        else:
            self.setStyleSheet("background-color: #333; border: 1px solid #555; border-radius: 3px;")
            self.setText("")
