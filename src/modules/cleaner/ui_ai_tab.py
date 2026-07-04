import os
import shutil
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QSlider,
    QTreeWidget, QTreeWidgetItem, QProgressBar, QDialog, QLineEdit,
    QRadioButton, QButtonGroup, QAbstractItemView, QMenu, QSplitter,
    QScrollArea, QSizePolicy, QComboBox, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer, QPoint, QEvent
from PyQt6.QtGui import QIcon, QPixmap, QColor, QAction, QCursor, QFont, QPainter, QPen

from config import AppContext, APP_DESIGN
from ui_widgets_base import DropZoneWidget
from .logic_ai import AiEngine
from .logic_ai_cache import AiCacheManager
from .logic_ai_classifier import AiClassifier, load_ai_settings, save_ai_settings, get_ai_assets_dir
from .workers import AiScanWorker, STAGE_SCANNING, STAGE_ANALYSIS

from .ui_widgets import ImageHoverToolTip, RefImagesListWidget


# -----------------------------------------------------------------------------
# Диалог настроек группы эталонов (вызывается при клике по шестеренке)
# -----------------------------------------------------------------------------
from .ui_ai_group_dialog import AiGroupSettingsDialog

from .ui_widgets import CleanSpinBox
        
class AiAdvancedSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки ИИ" if AppContext.is_ru() else "AI Settings")
        self.setFixedSize(400, 320)
        self.setStyleSheet("QDialog { background-color: #1e1e1e; } QLabel { color: #f0f0f0; }")
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        self.settings = load_ai_settings()
        
        # Юнет
        l_det = QLabel("Порог детектора лиц (YuNet):")
        tooltip_det = ("Определяет, насколько 'похожим на лицо' должен быть объект, чтобы нейросеть его захватила.\n"
                       "Меньшие значения (0.50): Находит даже размытые/мелкие лица в толпе, но может принять за лицо случайные предметы.\n"
                       "Высокие значения (0.80+): Захватывает только очень четкие, крупные лица анфас.\n"
                       "Изменение этой настройки автоматически очистит кэш лиц для пересканирования.")
        l_det.setToolTip(tooltip_det)
        self.slider_det = QSlider(Qt.Orientation.Horizontal)
        self.slider_det.setRange(0, 100)
        self.slider_det.setToolTip(tooltip_det)
        self.slider_det.setValue(int(self.settings.get("face_det_threshold", 65.0)))
        self.slider_det.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #333; border-radius: 2px; }
            QSlider::handle:horizontal { background: #3b82f6; width: 12px; height: 12px; margin-top: -4px; margin-bottom: -4px; border-radius: 6px; }
        """)
        
        self.spin_det = CleanSpinBox()
        self.spin_det.setRange(0.0, 1.0)
        self.spin_det.setDecimals(2)
        self.spin_det.setSingleStep(0.01)
        self.spin_det.setValue(float(self.settings.get("face_det_threshold", 65.0)) / 100.0)
        self.spin_det.setFixedWidth(65)
        self.spin_det.setStyleSheet("border: none; background: transparent; color: #f0f0f0; font-weight: bold; font-size: 12px; padding: 0 4px;")
        
        self.slider_det.valueChanged.connect(lambda v: self.spin_det.setValue(v / 100.0))
        self.spin_det.valueChanged.connect(lambda v: self.slider_det.setValue(int(v * 100.0)))
        
        h1 = QHBoxLayout()
        h1.addWidget(l_det)
        h1.addStretch()
        h1.addWidget(self.spin_det)
        layout.addLayout(h1)
        layout.addWidget(self.slider_det)
        
        # SFace
        l_match = QLabel("Строгость совпадения лиц (SFace L2-norm):")
        tooltip_match = ("Математическое расстояние между лицами для признания их одним человеком.\n"
                         "Меньшие значения (например, 0.7 - 0.9): Очень строгий поиск, почти идентичные фото.\n"
                         "Значение по умолчанию (1.128): Оптимальный порог SFace для разных ракурсов и освещения.\n"
                         "Высокие значения (1.3+): Объединяет в одну группу даже отдаленно похожих людей.\n"
                         "Изменение не требует пересканирования (кэш не сбрасывается).")
        l_match.setToolTip(tooltip_match)
        self.slider_match = QSlider(Qt.Orientation.Horizontal)
        self.slider_match.setRange(500, 1500)
        self.slider_match.setToolTip(tooltip_match)
        
        current_sface = self.settings.get("face_match_threshold", 1.128)
        if current_sface > 2.0: current_sface = 1.128
        
        self.slider_match.setValue(int(current_sface * 1000))
        self.slider_match.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #333; border-radius: 2px; }
            QSlider::handle:horizontal { background: #10b981; width: 12px; height: 12px; margin-top: -4px; margin-bottom: -4px; border-radius: 6px; }
        """)
        
        self.spin_match = CleanSpinBox()
        self.spin_match.setRange(0.50, 1.50)
        self.spin_match.setDecimals(3)
        self.spin_match.setSingleStep(0.01)
        self.spin_match.setValue(current_sface)
        self.spin_match.setFixedWidth(65)
        self.spin_match.setStyleSheet("border: none; background: transparent; color: #f0f0f0; font-weight: bold; font-size: 12px; padding: 0 4px;")
        
        self.slider_match.valueChanged.connect(lambda v: self.spin_match.setValue(v / 1000.0))
        self.spin_match.valueChanged.connect(lambda v: self.slider_match.setValue(int(v * 1000.0)))
        
        h2 = QHBoxLayout()
        h2.addWidget(l_match)
        h2.addStretch()
        h2.addWidget(self.spin_match)
        layout.addLayout(h2)
        layout.addWidget(self.slider_match)
        
        # Deep Merge
        self.chk_merge = QCheckBox("Глубокое объединение групп (Deep Merge)")
        self.chk_merge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_merge.setStyleSheet("""
            QCheckBox { color: white; font-weight: bold; font-size: 12px; margin-top: 2px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 3px; border: 1px solid #555; background: #111; margin-top: 2px; }
            QCheckBox::indicator:checked { background-color: #3b82f6; border-color: #3b82f6; }
        """)
        self.chk_merge.setChecked(self.settings.get("deep_merge_enabled", True))
        
        lbl_desc = QLabel("Если включено, ИИ сделает второй проход и объединит группы одного\nчеловека, снятые с разных ракурсов.")
        lbl_desc.setStyleSheet("color: #aaa; font-size: 11px;")
        
        layout.addWidget(self.chk_merge)
        layout.addWidget(lbl_desc)
        
        # Deep Merge Threshold
        l_merge_thresh = QLabel("Сила объединения (чем меньше, тем строже):")
        l_merge_thresh.setStyleSheet("color: #ccc; font-size: 11px;")
        
        self.slider_merge = QSlider(Qt.Orientation.Horizontal)
        self.slider_merge.setRange(0, 100)
        self.slider_merge.setValue(int(self.settings.get("deep_merge_threshold", 75.0)))
        self.slider_merge.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #333; border-radius: 2px; }
            QSlider::handle:horizontal { background: #8b5cf6; width: 12px; height: 12px; margin-top: -4px; margin-bottom: -4px; border-radius: 6px; }
        """)
        
        self.spin_merge = CleanSpinBox()
        self.spin_merge.setRange(0.0, 1.0)
        self.spin_merge.setDecimals(2)
        self.spin_merge.setSingleStep(0.01)
        self.spin_merge.setValue(float(self.settings.get("deep_merge_threshold", 75.0)) / 100.0)
        self.spin_merge.setFixedWidth(65)
        self.spin_merge.setStyleSheet("border: none; background: transparent; color: #f0f0f0; font-weight: bold; font-size: 12px; padding: 0 4px;")
        
        self.slider_merge.valueChanged.connect(lambda v: self.spin_merge.setValue(v / 100.0))
        self.spin_merge.valueChanged.connect(lambda v: self.slider_merge.setValue(int(v * 100.0)))
        
        h3 = QHBoxLayout()
        h3.addWidget(l_merge_thresh)
        h3.addStretch()
        h3.addWidget(self.spin_merge)
        
        layout.addLayout(h3)
        layout.addWidget(self.slider_merge)
        
        layout.addStretch()
        
        btn_box = QHBoxLayout()
        btn_default = QPushButton("По умолчанию")
        btn_default.setStyleSheet("background-color: #444; color: white; padding: 6px 15px; border-radius: 4px; font-weight: bold;")
        btn_default.clicked.connect(self.reset_to_defaults)
        
        btn_save = QPushButton("Сохранить")
        btn_save.setStyleSheet("background-color: #3b82f6; color: white; padding: 6px 20px; border-radius: 4px; font-weight: bold;")
        btn_save.clicked.connect(self.save_and_close)
        
        btn_box.addWidget(btn_default)
        btn_box.addStretch()
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)
        
    def reset_to_defaults(self):
        self.slider_det.setValue(65)
        self.slider_match.setValue(1128)
        self.chk_merge.setChecked(True)
        self.slider_merge.setValue(75)
        
    def save_and_close(self):
        old_det = float(self.settings.get("face_det_threshold", 65.0))
        new_det = float(self.slider_det.value())
        
        self.settings["face_det_threshold"] = new_det
        self.settings["face_match_threshold"] = float(self.slider_match.value()) / 1000.0
        self.settings["deep_merge_enabled"] = self.chk_merge.isChecked()
        self.settings["deep_merge_threshold"] = float(self.slider_merge.value())
        save_ai_settings(self.settings)
        
        # Auto-clear cache if detection threshold changed
        if old_det != new_det and hasattr(self.parent(), 'cache'):
            self.parent().cache.clear_cache()
            if hasattr(self.parent(), 'update_cache_info_ai'):
                self.parent().update_cache_info_ai()
                
        self.accept()


class AiGroupChipWidget(QFrame):
    state_changed = pyqtSignal(str, bool)
    settings_clicked = pyqtSignal(str)
    
    def __init__(self, name: str, is_enabled: bool, is_face: bool, status_color: str, count: int, parent=None):
        super().__init__(parent)
        self.group_name = name
        
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #2b2b2b;
                border: 1px solid #444;
                border-radius: 4px;
            }
        """)
        self.setFixedHeight(30)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(6)
        
        self.chk = QCheckBoxCustom()
        self.chk.setChecked(is_enabled)
        self.chk.toggled.connect(lambda checked: self.state_changed.emit(self.group_name, checked))
        layout.addWidget(self.chk)
        
        self.lbl_icon = QLabel()
        self.lbl_icon.setFixedSize(14, 14)
        self.lbl_icon.setText("👤" if is_face else "🖼️")
        self.lbl_icon.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(self.lbl_icon)
        
        self.lbl_name = QLabel(f"{name} [{count}]")
        self.lbl_name.setStyleSheet("font-weight: bold; color: #eee; font-size: 12px; border: none; background: transparent;")
        layout.addWidget(self.lbl_name)
        
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(8, 8)
        self.update_status_dot(status_color)
        layout.addWidget(self.status_dot)
        
        self.btn_gear = QPushButton("⚙️")
        self.btn_gear.setFixedSize(18, 18)
        self.btn_gear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_gear.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #aaa;
                font-size: 12px;
            }
            QPushButton:hover {
                color: #3b82f6;
            }
        """)
        self.btn_gear.clicked.connect(lambda: self.settings_clicked.emit(self.group_name))
        layout.addWidget(self.btn_gear)

    def update_status_dot(self, color: str):
        hex_color = "#888888" # gray
        if color == "orange":
            hex_color = "#f97316" # orange
        elif color == "green":
            hex_color = "#22c55e" # green
            
        self.status_dot.setStyleSheet(f"""
            background-color: {hex_color};
            border-radius: 4px;
            border: 1px solid rgba(0,0,0,0.5);
        """)

    def set_error_highlight(self, enabled: bool):
        if enabled:
            self.setStyleSheet("""
                QFrame {
                    background-color: #2d1e1e;
                    border: 1.5px solid #ef4444;
                    border-radius: 4px;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame {
                    background-color: #2b2b2b;
                    border: 1px solid #444;
                    border-radius: 4px;
                }
            """)


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
            "Для работы локального классификатора и поиска по лицам необходимо загрузить модели нейросети (~57 МБ).\n"
            "Загрузка выполняется один раз, после чего ИИ работает полностью автономно без подключения к интернету."
            if AppContext.is_ru() else
            "To use local AI classification and face recognition, neural network models (~57 MB) need to be downloaded.\n"
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
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        btn_layout.addWidget(self.btn_download_models)
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
        
        # КОЛОНКА 1: Группы эталонов
        col_ref = QVBoxLayout()
        col_ref.setContentsMargins(0, 0, 0, 0)
        col_ref.setSpacing(4)
        
        ref_header = QHBoxLayout()
        ref_title = QLabel("Группы эталонов" if AppContext.is_ru() else "Reference Groups")
        ref_title.setStyleSheet("font-weight: bold; color: #888; font-size: 11px; font-family: 'Segoe UI';")
        ref_header.addWidget(ref_title)
        
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
        
        ref_header.addStretch()
        
        self.btn_ai_settings = QPushButton("⚙")
        self.btn_ai_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ai_settings.setStyleSheet("QPushButton { background-color: transparent; border: none; color: #888; font-size: 16px; margin-top: -2px; } QPushButton:hover { color: #fff; }")
        self.btn_ai_settings.setToolTip("Настройки ИИ" if AppContext.is_ru() else "AI Settings")
        self.btn_ai_settings.clicked.connect(self.open_ai_settings)
        ref_header.addWidget(self.btn_ai_settings)
        
        col_ref.addLayout(ref_header)
        
        self.scroll_ref = QScrollArea()
        self.scroll_ref.setWidgetResizable(True)
        self.scroll_ref.setStyleSheet("QScrollArea { border: 1px solid #333; background-color: #111; border-radius: 4px; }")
        
        self.ref_container = QWidget()
        self.ref_container.setStyleSheet("background-color: #111;")
        self.group_list_layout_ai = QVBoxLayout(self.ref_container)
        self.group_list_layout_ai.setContentsMargins(5, 5, 5, 5)
        self.group_list_layout_ai.setSpacing(4)
        self.group_list_layout_ai.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.scroll_ref.setWidget(self.ref_container)
        col_ref.addWidget(self.scroll_ref)
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
        
        self.sources_list_widget_ai = QWidget()
        self.sources_list_widget_ai.setStyleSheet("background-color: #111111;")
        
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
            "   • Общее сходство: ИИ сравнивает цветовую гамму, композицию и объекты.\n"
            "   • Поиск лиц: ИИ находит на фото человеческие лица и сравнивает их черты.\n\n"
            "2. Сколько картинок-примеров добавлять:\n"
            "   • Для лиц: достаточно 1-3 четких фото лица под разными углами.\n"
            "   • Для общего поиска: достаточно 2-5 характерных скриншотов/картинок.\n\n"
            "3. Порог схожести (Confidence):\n"
            "   • 85% - 100%: Строгий поиск (тот же человек, почти идентичные скриншоты).\n"
            "   • 70% - 85%: Умеренное сходство (тот же человек в другой одежде, похожие сцены).\n"
            "   • 50% - 70%: Широкий поиск (похожие по цветам и структуре изображения).\n\n"
            "💡 Совет: Для лучшего результата используйте четкие примеры и отключайте ненужные группы эталонов."
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
        params_container.setStyleSheet("QFrame { background-color: #1a1a1a; border: 1px solid #333; border-radius: 6px; }")
        params_sub_layout = QVBoxLayout(params_container)
        params_sub_layout.setContentsMargins(8, 8, 8, 8)
        params_sub_layout.setSpacing(8)
        
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
        self.lbl_threshold.setStyleSheet("color: #ccc; font-weight: bold; font-size: 11px; border: none; background: transparent;")
        params_sub_layout.addWidget(self.lbl_threshold)
        
        slider_layout = QHBoxLayout()
        self.slider_threshold = QSlider(Qt.Orientation.Horizontal)
        self.slider_threshold.setRange(0, 10000)
        self.slider_threshold.setValue(7500)
        self.slider_threshold.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #333; border-radius: 2px; }
            QSlider::handle:horizontal { background: #3b82f6; width: 12px; height: 12px; margin-top: -4px; margin-bottom: -4px; border-radius: 6px; }
        """)
        
        self.spin_threshold = CleanSpinBox()
        self.spin_threshold.setRange(0.0, 100.0)
        self.spin_threshold.setDecimals(2)
        self.spin_threshold.setSingleStep(0.01)
        self.spin_threshold.setValue(75.0)
        self.spin_threshold.setSuffix("%")
        self.spin_threshold.setFixedWidth(65)
        self.spin_threshold.setStyleSheet("border: none; background: transparent; color: #f0f0f0; font-weight: bold; font-size: 12px; padding: 0 4px;")
        
        self.slider_threshold.valueChanged.connect(lambda v: self.spin_threshold.setValue(v / 100.0))
        self.spin_threshold.valueChanged.connect(lambda v: self.slider_threshold.setValue(int(v * 100)))
        
        slider_layout.addWidget(self.slider_threshold)
        slider_layout.addWidget(self.spin_threshold)
        params_sub_layout.addLayout(slider_layout)
        
        # Выбор режима сопоставления
        self.lbl_match_mode = QLabel("Режим сопоставления:" if AppContext.is_ru() else "Matching Mode:")
        self.lbl_match_mode.setStyleSheet("color: #ccc; font-weight: bold; font-size: 11px; border: none; background: transparent; margin-top: 4px;")
        params_sub_layout.addWidget(self.lbl_match_mode)
        
        self.combo_match_mode = QComboBox()
        self.combo_match_mode.setMinimumHeight(24)
        self.combo_match_mode.setStyleSheet("""
            QComboBox {
                background-color: #2b2b2b;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 2px 8px;
                color: white;
                font-size: 11px;
            }
            QComboBox:hover {
                border-color: #555;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #2b2b2b;
                color: white;
                selection-background-color: #3b82f6;
            }
        """)
        
        is_ru = AppContext.is_ru()
        self.combo_match_mode.addItem("Средний образ" if is_ru else "Average Centroid", "centroid")
        self.combo_match_mode.setItemData(0, 
            "Сравнивает изображение со средним арифметическим всех эталонов.\nПодходит для поиска однотипных скриншотов или портретов одного человека."
            if is_ru else
            "Compares with the average vector of all references.\nBest for uniform images (e.g. same face, same UI).",
            Qt.ItemDataRole.ToolTipRole
        )
        
        self.combo_match_mode.addItem("Любое совпадение" if is_ru else "Best Match (Any)", "best_match")
        self.combo_match_mode.setItemData(1, 
            "Сравнивает с каждым эталоном отдельно и берет максимальное сходство.\nПозволяет искать разнородные объекты в одной группе (разные ракурсы, цвета, машины)."
            if is_ru else
            "Compares with each reference individually and takes the maximum similarity.\nBest for diverse images in one group.",
            Qt.ItemDataRole.ToolTipRole
        )
        
        self.combo_match_mode.addItem("Большинство совпадений" if is_ru else "Majority Match", "majority")
        self.combo_match_mode.setItemData(2, 
            "Файл должен быть похож минимум на половину (50%) всех эталонов в группе.\nИсключает случайные ложные совпадения."
            if is_ru else
            "Requires the file to match at least 50% of the reference images.\nPrevents accidental false positives.",
            Qt.ItemDataRole.ToolTipRole
        )
        
        # Загружаем сохраненный режим из настроек
        settings = load_ai_settings()
        saved_mode = settings.get("match_mode", "centroid")
        idx = self.combo_match_mode.findData(saved_mode)
        if idx >= 0:
            self.combo_match_mode.setCurrentIndex(idx)
            
        self.combo_match_mode.currentIndexChanged.connect(self.on_match_mode_changed)
        params_sub_layout.addWidget(self.combo_match_mode)
        
        self.chk_auto_cluster = QCheckBox("Умный поиск" if AppContext.is_ru() else "Smart Search")
        self.chk_auto_cluster.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_auto_cluster.setStyleSheet("""
            QCheckBox { color: white; font-weight: bold; font-size: 13px; margin-top: 2px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 3px; border: 1px solid #555; background: #111; margin-top: 2px; }
            QCheckBox::indicator:checked { background-color: #3b82f6; border-color: #3b82f6; }
        """)
        self.chk_auto_cluster.setToolTip("Искать похожие объекты без эталонов и группировать их автоматически." if AppContext.is_ru() else "Group objects automatically without references.")
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
        
        # Moved cache layout to the top of the block
        
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
        self.btn_start_scan.clicked.connect(self.toggle_scan)
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
        self.lbl_post_filter = QLabel("Быстрый фильтр:" if AppContext.is_ru() else "Quick Filter:")
        self.lbl_post_filter.setStyleSheet("color: #ccc; font-size: 11px; font-weight: bold;")
        self.slider_post_filter = QSlider(Qt.Orientation.Horizontal)
        self.slider_post_filter.setRange(0, 10000)
        self.slider_post_filter.setValue(0)
        self.slider_post_filter.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #333; border-radius: 2px; }
            QSlider::handle:horizontal { background: #10b981; width: 12px; height: 12px; margin-top: -4px; margin-bottom: -4px; border-radius: 6px; }
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
            if not self.ai._is_initialized:
                self.ai.initialize_sessions()
            self.download_placeholder.hide()
            self.main_content_widget.show()
        else:
            self.download_placeholder.show()
            self.main_content_widget.hide()

    def start_placeholder_download(self):
        self.btn_download_models.setEnabled(False)
        self.placeholder_progress.show()
        self.placeholder_progress.setValue(0)
        self.placeholder_status.setStyleSheet("color: #93c5fd;")
        self.placeholder_status.setText("Подключение..." if AppContext.is_ru() else "Connecting...")
        
        is_ru = AppContext.is_ru()
        
        def on_progress(filename, downloaded, total_size):
            if total_size > 0:
                pct = int((downloaded / total_size) * 100.0)
                self.placeholder_progress.setValue(pct)
                self.placeholder_status.setText(f"Загрузка {filename}: {downloaded // 1024} KB / {total_size // 1024} KB")
            else:
                self.placeholder_status.setText(f"Загрузка {filename}: {downloaded // 1024} KB")
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            
        success = self.ai.download_models(progress_callback=on_progress)
        
        if success:
            self.placeholder_status.setStyleSheet("color: #4ade80;")
            self.placeholder_status.setText("Инициализация..." if is_ru else "Initializing...")
            
            if self.ai.initialize_sessions():
                self.placeholder_status.setText("Успешно!" if is_ru else "Success!")
                self.download_placeholder.hide()
                self.main_content_widget.show()
            else:
                self.btn_download_models.setEnabled(True)
                self.placeholder_status.setStyleSheet("color: #ef4444;")
                self.placeholder_status.setText("Ошибка инициализации!" if is_ru else "Initialization failed!")
        else:
            self.btn_download_models.setEnabled(True)
            self.placeholder_status.setStyleSheet("color: #ef4444;")
            self.placeholder_status.setText("Ошибка при скачивании моделей!" if is_ru else "Failed to download models!")

    def reload_groups(self):
        self.chips_map.clear()
        while self.group_list_layout_ai.count():
            item = self.group_list_layout_ai.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        settings = load_ai_settings()
        groups = settings.get("groups", {})
        
        # Сортируем: включенные сверху, затем по алфавиту
        sorted_groups = sorted(groups.items(), key=lambda item: (not item[1].get("enabled", True), item[0].lower()))
        
        for name, info in sorted_groups:
            status, count = self.classifier.get_group_status(name)
            is_face = info.get("type") == "face"
            is_enabled = info.get("enabled", True)
            
            widget = AiGroupChipWidget(name, is_enabled, is_face, status, count, self)
            widget.state_changed.connect(self.on_group_state_changed)
            widget.settings_clicked.connect(self.open_edit_group_dialog)
            self.group_list_layout_ai.addWidget(widget)
            self.chips_map[name] = widget
            
        self.update_scan_button_state()

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
        if dlg.exec():
            self.reload_groups()

    def open_ai_settings(self):
        dlg = AiAdvancedSettingsDialog(self)
        dlg.exec()

    def create_group(self):
        dlg = AiGroupSettingsDialog(self.classifier, None, self)
        if dlg.exec():
            name = dlg.txt_name.text().strip()
            if not name:
                return
                
            name = "".join(c for c in name if c.isalnum() or c in " _-").strip()
            if not name:
                return
                
            settings = load_ai_settings()
            if name in settings.get("groups", {}):
                QMessageBox.warning(self, "Ошибка" if AppContext.is_ru() else "Error", 
                                    "Группа с таким именем уже существует!" if AppContext.is_ru() else "Group already exists!")
                return
                
            group_type = "face" if dlg.rad_face.isChecked() else "general"
            
            group_dir = os.path.join(get_ai_assets_dir(), name)
            os.makedirs(group_dir, exist_ok=True)
            
            import shutil
            for fp in dlg.pending_files:
                if os.path.exists(fp):
                    try:
                        shutil.copy2(fp, group_dir)
                    except Exception as e:
                        logging.error(f"Failed to copy {fp} to {group_dir}: {e}")
            
            settings["groups"][name] = {
                "type": group_type,
                "enabled": True
            }
            save_ai_settings(settings)
            
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
        self.update_cleaner_action_bar_info()

    def on_match_mode_changed(self, index):
        mode = self.combo_match_mode.itemData(index)
        settings = load_ai_settings()
        settings["match_mode"] = mode
        save_ai_settings(settings)

    def update_cache_info_ai(self):
        try:
            db_path = self.cache.db_path
            if os.path.exists(db_path):
                size = os.path.getsize(db_path)
                from utils_common import format_size
                self.lbl_cache_info_ai.setText(f"{format_size(size)}")
            else:
                self.lbl_cache_info_ai.setText("0 B")
        except Exception as e:
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

    def update_scan_button_state(self):
        folders = self.cleaner.get_active_source_folders() if hasattr(self, 'cleaner') else []
        has_folders = len(folders) > 0
        has_enabled_groups = any(widget.chk.isChecked() for widget in self.chips_map.values())
        is_cluster = self.chk_auto_cluster.isChecked()
        
        # _is_ok default to True because logic_actions will pass False if there is a nested/system error
        is_ok = getattr(self, '_is_ok', True) 
        
        can_run = has_folders and (has_enabled_groups or is_cluster) and is_ok
        self.btn_start_scan.setEnabled(can_run)
        
        base_text = " Начать ИИ Поиск" if AppContext.is_ru() else " Start AI Search"
        self.btn_start_scan.setText(base_text)

    def toggle_scan(self):
        if self.active_worker and self.active_worker.isRunning():
            self.active_worker.stop()
            return
            
        folders = self.cleaner.get_active_source_folders()
        if not folders:
            return
            
        for widget in self.chips_map.values():
            widget.set_error_highlight(False)
            
        is_cluster = self.chk_auto_cluster.isChecked()
        if not is_cluster:
            settings = load_ai_settings()
            enabled_groups = [name for name, info in settings.get("groups", {}).items() if info.get("enabled", True)]
            
            if not enabled_groups:
                QMessageBox.warning(self, "Ошибка" if AppContext.is_ru() else "Error", 
                                    "Выберите хотя бы одну группу эталонов для поиска!" if AppContext.is_ru() else "Select at least one reference group to search!")
                return
                
            for name in enabled_groups:
                status, count = self.classifier.get_group_status(name)
                if status == "gray":
                    if name in self.chips_map:
                        self.chips_map[name].set_error_highlight(True)
                    QMessageBox.critical(
                        self, 
                        "Ошибка" if AppContext.is_ru() else "Error", 
                        f"Группа '{name}' включена в поиск, но не содержит картинок-примеров! Загрузите картинки или выключите группу." if AppContext.is_ru()
                        else f"Group '{name}' is enabled but contains no reference images! Load images or disable the group."
                    )
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
            
            lbl_title = QLabel("Идет подготовка эталонов..." if AppContext.is_ru() else "Preparing reference groups...")
            bar = QProgressBar()
            bar.setRange(0, len(needs_training))
            
            dlg_layout.addWidget(lbl_title)
            dlg_layout.addWidget(bar)
            dlg.show()
            
            for idx, name in enumerate(needs_training):
                lbl_title.setText(f"Обучение эталона ({idx + 1}/{len(needs_training)}): {name}")
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
        
        match_mode = self.combo_match_mode.currentData() or "centroid"
        use_cache = self.chk_use_cache.isChecked()
        use_gpu = self.chk_use_gpu.isChecked()
        is_cluster = self.chk_auto_cluster.isChecked()
        
        self.active_worker = AiScanWorker(
            folders, self.classifier, 
            threshold=threshold, filter_config=filter_cfg, 
            match_mode=match_mode, use_cache=use_cache,
            use_gpu=use_gpu, is_cluster=is_cluster
        )
        self.active_worker.progress.connect(self.on_scan_progress)
        self.active_worker.finished.connect(self.on_scan_finished)
        self.active_worker.start()

    def on_scan_progress(self, stage, percent, text, scanned_files, groups_found, wasted_bytes, scanned_bytes, zero, empty):
        if stage == STAGE_SCANNING:
            self.progress_bar.setMaximum(0)
            self.progress_bar.setFormat(text)
        else:
            self.progress_bar.setMaximum(100)
            self.progress_bar.setValue(int(percent))
            self.progress_bar.setFormat(f"{text} ({int(percent)}%)")
            
        from utils_common import format_size
        self.lbl_stats.setText(
            f"Найдено совпадений: {groups_found} групп, {wasted_bytes // (1024*1024) if wasted_bytes else 0} MB" if AppContext.is_ru()
            else f"Matches found: {groups_found} groups, {format_size(wasted_bytes)}"
        )

    def on_scan_finished(self, results):
        self.progress_bar.hide()
        self.btn_start_scan.setText(" Начать ИИ Поиск" if AppContext.is_ru() else " Start AI Search")
        self.btn_start_scan.setStyleSheet("""
            QPushButton { background-color: #15803d; color: white; font-weight: 900; font-size: 14px; border: 1px solid #16a34a; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
            QPushButton:hover { background-color: #16a34a; }
            QPushButton:disabled { background-color: #222; color: #555; font-weight: 900; font-size: 14px; border: 1px solid #333; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
        """)
        
        if self.active_worker:
            self.active_worker.deleteLater()
        self.active_worker = None
        self.scan_finished.emit()
        self.update_cache_info_ai()
        if hasattr(self, 'cleaner'):
            self.update_folders_label(self.cleaner.get_active_source_folders())
        
        self.populate_results(results)

    def populate_results(self, results):
        self.tree_results.clear()
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
                file_item.setData(0, Qt.ItemDataRole.UserRole, {"is_group": False, "path": f["path"], "size": f["size"], "confidence": f.get("confidence", 0.0) / 100.0})
                
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
            return
            
        item = selected_items[0]
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and not data.get("is_group", False):
            path = data.get("path")
            if path and os.path.exists(path):
                self.preview_widget.load_file(path)
                self.file_selected.emit(path)

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
        if data and data.get("is_group", False):
            menu = QMenu(self)
            menu.setStyleSheet("QMenu { background-color: #2b2b2b; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #3b82f6; }")
            
            act_select = QAction("Выделить все файлы в этой группе" if AppContext.is_ru() else "Select all files in this group", self)
            act_deselect = QAction("Снять выделение со всех файлов в группе" if AppContext.is_ru() else "Deselect all files in this group", self)
            act_invert = QAction("Инвертировать выделение" if AppContext.is_ru() else "Invert Selection", self)
            
            act_select.triggered.connect(lambda: self.set_group_selection_state(item, Qt.CheckState.Checked))
            act_deselect.triggered.connect(lambda: self.set_group_selection_state(item, Qt.CheckState.Unchecked))
            act_invert.triggered.connect(lambda: self.invert_group_selection(item))
            
            menu.addAction(act_select)
            menu.addAction(act_deselect)
            menu.addAction(act_invert)
            menu.exec(self.tree_results.mapToGlobal(pos))
        elif data and not data.get("is_group", False):
            menu = QMenu(self)
            menu.setStyleSheet("QMenu { background-color: #2b2b2b; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #3b82f6; } QMenu::separator { height: 1px; background: #666; margin: 4px 8px; }")
            path = data.get("path")
            
            act_open = QAction("Открыть файл" if AppContext.is_ru() else "Open File", self)
            act_open.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
            menu.addAction(act_open)
            
            act_reveal = QAction("Показать в папке" if AppContext.is_ru() else "Show in folder", self)
            from utils_common import reveal_in_explorer
            act_reveal.triggered.connect(lambda: reveal_in_explorer(path))
            menu.addAction(act_reveal)
            
            menu.addSeparator()
            act_invert = QAction("Инвертировать выделение в группе" if AppContext.is_ru() else "Invert Selection in group", self)
            act_invert.triggered.connect(lambda: self.invert_group_selection(item.parent()))
            menu.addAction(act_invert)
            
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


# -----------------------------------------------------------------------------
# Кнопка чекбокса, использующаяся в чипах эталонов
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
