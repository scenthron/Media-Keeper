"""
Global Settings & Cache Manager Dialog for Media Keeper.
Provides centralized management for:
- Tab 1: General (Interface language, DirectML GPU acceleration, AI models status & downloader, FFmpeg status & downloader, System logs)
- Tab 2: Sorter (Directories, recursion, max depth, pagination, auto-collapse groups, list delay, extension filters, affixes)
- Tab 3: Hotkeys (Full hotkey remapping table, capture buttons, conflict resolution, reset to defaults)
- Tab 4: Cache & Databases (Visual table of all project caches, disk usage with WAL/SHM, background clearing)
"""

import os
import sys
import logging
import sqlite3
import configparser
from typing import Dict, List, Any, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget,
    QWidget, QLabel, QPushButton, QComboBox, QCheckBox, QSpinBox, QDoubleSpinBox,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QProgressBar, QFileDialog, QFrame, QScrollArea, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QSize
from PyQt6.QtGui import QDesktopServices, QIcon, QFont, QKeySequence

from config import AppContext, APP_VERSION
from utils_common import format_size
from utils_io import safe_path_exists, ensure_long_path
from logic_paths import get_app_data_dir, get_models_dir, get_ffmpeg_bin_dir
from ui_dialogs_generic import silent_info, silent_warning, silent_question, ProgressDialog
from modules.shared.ui_theme import (
    BG_MAIN, BG_PANEL, BG_CONTAINER, BG_DARK, BG_INPUT, BG_HOVER, BG_SELECTED,
    BORDER_DEFAULT, BORDER_MEDIUM, BORDER_FOCUS,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_BODY, TEXT_MUTED,
    COLOR_PRIMARY, COLOR_PRIMARY_HOVER, COLOR_SUCCESS, COLOR_SUCCESS_HOVER,
    COLOR_DANGER, COLOR_DANGER_HOVER, COLOR_WARNING
)
from modules.sorter.ui_dialog_settings import HotkeyCaptureButton
from modules.sorter.logic_hotkeys import HotkeyRegistry, _SORTER_ACTIONS
from modules.editor.ffmpeg_downloader import check_ffmpeg_available, FFmpegDownloaderWorker
from modules.cleaner.logic_ai import AiEngine


# Cache Definition items
def get_cache_definitions() -> List[Dict[str, Any]]:
    app_data = get_app_data_dir()
    return [
        {
            "id": "cleaner_db",
            "name_ru": "Хэши дубликатов",
            "name_en": "Duplicate Hashes",
            "desc_ru": "Кэш хэшей файлов для мгновенного поиска точных копий и дубликатов",
            "desc_en": "File hash cache for instant duplicate file detection",
            "filename": "cleaner_cache.db",
            "path": os.path.join(app_data, "cleaner_cache.db"),
            "type": "sqlite",
            "main_table": "file_hashes"
        },
        {
            "id": "similar_db",
            "name_ru": "Сигнатуры похожих",
            "name_en": "Similar Signatures",
            "desc_ru": "Кэш визуальных хэшей (dHash, pHash, wHash) для поиска визуально схожих фото",
            "desc_en": "Perceptual image signatures cache for similar photos discovery",
            "filename": "similar_cache.db",
            "path": os.path.join(app_data, "similar_cache.db"),
            "type": "sqlite",
            "main_table": None
        },
        {
            "id": "ai_multi_db",
            "name_ru": "Векторы ИИ",
            "name_en": "AI Embeddings",
            "desc_ru": "Кэш векторных эмбеддингов нейросетей CLIP и распознавания лиц InsightFace",
            "desc_en": "Deep learning embeddings cache for CLIP and InsightFace face recognition",
            "filename": "ai_cache_multi.db",
            "path": os.path.join(app_data, "ai_cache_multi.db"),
            "type": "sqlite",
            "main_table": None
        },
        {
            "id": "sift_db",
            "name_ru": "Дескрипторы SIFT",
            "name_en": "SIFT Descriptors",
            "desc_ru": "Кэш ключевых точек и дескрипторов SIFT/ORB для поиска по фрагменту изображения",
            "desc_en": "SIFT/ORB keypoints and descriptors cache for partial image match",
            "filename": "sift_cache.db",
            "path": os.path.join(app_data, "cache", "orb", "sift_cache.db"),
            "type": "sqlite",
            "main_table": "sift_features"
        },
        {
            "id": "session_cleaner",
            "name_ru": "Сессия дубликатов",
            "name_en": "Duplicates Session",
            "desc_ru": "Временная база данных текущих результатов сканирования точных дубликатов",
            "desc_en": "Temporary database holding duplicate scan results for current session",
            "filename": "session_cleaner.db",
            "path": os.path.join(app_data, "session_cleaner.db"),
            "type": "sqlite",
            "main_table": None
        },
        {
            "id": "session_similar",
            "name_ru": "Сессия похожих",
            "name_en": "Similar Session",
            "desc_ru": "Временная база данных текущих результатов сканирования похожих изображений",
            "desc_en": "Temporary database holding similar scan results for current session",
            "filename": "session_similar.db",
            "path": os.path.join(app_data, "session_similar.db"),
            "type": "sqlite",
            "main_table": None
        },
        {
            "id": "ram_thumbnails",
            "name_ru": "Миниатюры (RAM)",
            "name_en": "Thumbnails (RAM)",
            "desc_ru": "Кэш предзагруженных миниатюр в оперативной памяти (быстрая прокрутка сетки)",
            "desc_en": "Pre-rendered thumbnail images stored in RAM for fast scrolling",
            "filename": "Оперативная память (RAM)",
            "path": "RAM Memory",
            "type": "ram",
            "main_table": None
        }
    ]


def get_sqlite_file_size(db_path: str) -> int:
    """Calculate total on-disk size for an SQLite DB including WAL and SHM files."""
    if not safe_path_exists(db_path):
        return 0
    total = 0
    for p in [db_path, f"{db_path}-wal", f"{db_path}-shm"]:
        if safe_path_exists(p):
            try:
                total += os.path.getsize(p)
            except Exception:
                pass
    return total


def clear_sqlite_db(db_path: str, specific_table: Optional[str] = None) -> None:
    """Clear data tables in SQLite database without removing sys_meta, then VACUUM to shrink file."""
    if not safe_path_exists(db_path):
        return
    with sqlite3.connect(db_path, timeout=15.0) as conn:
        cursor = conn.cursor()
        if specific_table:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
                (specific_table,)
            )
            if cursor.fetchone():
                cursor.execute(f"DELETE FROM [{specific_table}]")
        else:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'sys_meta'"
            )
            tables = [r[0] for r in cursor.fetchall()]
            for tbl in tables:
                try:
                    cursor.execute(f"DELETE FROM [{tbl}]")
                except Exception:
                    pass
        conn.commit()
        try:
            cursor.execute("VACUUM")
        except Exception:
            pass


def calc_folder_size(folder_path: str) -> int:
    """Recursively calculate the total size of files in a directory."""
    if not safe_path_exists(folder_path):
        return 0
    total = 0
    try:
        for root, _, files in os.walk(folder_path):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    total += os.path.getsize(fp)
                except Exception:
                    pass
    except Exception as e:
        logging.debug(f"[GlobalSettings] calc_folder_size error: {e}")
    return total


def get_log_file_path() -> str:
    """Locate the media_keeper.log file in app data or src/root."""
    app_data_log = os.path.join(get_app_data_dir(), "media_keeper.log")
    if safe_path_exists(app_data_log):
        return app_data_log
    cwd_log = os.path.abspath("media_keeper.log")
    if safe_path_exists(cwd_log):
        return cwd_log
    src_log = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "media_keeper.log"))
    if safe_path_exists(src_log):
        return src_log
    return app_data_log


def is_scanner_active(parent_widget=None) -> bool:
    """Check if any background file scanning or heavy processing is currently active."""
    if not parent_widget:
        return False
    # Check parent (MediaKeeperShell)
    cleaner = getattr(parent_widget, "_cleaner_tab", None)
    if cleaner:
        if getattr(cleaner, "finder_dupes", None) and cleaner.finder_dupes.isRunning():
            return True
        if getattr(cleaner, "finder_similar", None) and cleaner.finder_similar.isRunning():
            return True
        if getattr(cleaner, "session_move_worker", None) and cleaner.session_move_worker.isRunning():
            return True
        page_ai = getattr(cleaner, "page_ai", None)
        if page_ai:
            if getattr(page_ai, "active_worker", None) and getattr(page_ai.active_worker, "isRunning", lambda: False)():
                return True
            facade = getattr(page_ai, "facade", None)
            if facade and getattr(facade, "active_worker", None) and getattr(facade.active_worker, "isRunning", lambda: False)():
                return True
            dl_thread = getattr(page_ai, "dl_thread", None)
            if dl_thread and dl_thread.isRunning():
                return True
        page_frag = getattr(cleaner, "page_fragment", None)
        if page_frag:
            if getattr(page_frag, "active_worker", None) and getattr(page_frag.active_worker, "isRunning", lambda: False)():
                return True
    return False


class CacheWorker(QThread):
    """Background worker for cache statistics calculation and clearing."""
    stats_ready = pyqtSignal(list, int)             # (items_data, total_size_bytes)
    operation_finished = pyqtSignal(str, bool, str) # (action, success, message)
    progress_update = pyqtSignal(str)

    def __init__(self, action: str, target_id: Optional[str] = None):
        super().__init__()
        self.action = action
        self.target_id = target_id

    def run(self):
        try:
            if self.action == "calculate":
                self._calculate_stats()
            elif self.action == "clear_one":
                self._clear_one(self.target_id)
            elif self.action == "clear_all":
                self._clear_all()
        except Exception as e:
            logging.error(f"[CacheWorker] Unexpected error in {self.action}: {e}", exc_info=True)
            self.operation_finished.emit(self.action, False, str(e))

    def _calculate_stats(self):
        definitions = get_cache_definitions()
        results = []
        total_size = 0
        for item in definitions:
            ctype = item["type"]
            cpath = item["path"]

            if ctype == "sqlite":
                size = get_sqlite_file_size(cpath)
                total_size += size
            else:
                size = 0

            res_item = dict(item)
            res_item["size_bytes"] = size
            results.append(res_item)

        self.stats_ready.emit(results, total_size)

    def _clear_one(self, target_id: str):
        definitions = {d["id"]: d for d in get_cache_definitions()}
        if target_id not in definitions:
            self.operation_finished.emit("clear_one", False, f"Unknown cache id: {target_id}")
            return
        item = definitions[target_id]
        self.progress_update.emit(f"Очистка {item['filename']}...")
        if item["type"] == "sqlite":
            clear_sqlite_db(item["path"], item["main_table"])
        else:
            try:
                from modules.sorter.thumbnail_loader import ThumbnailLoader
                ThumbnailLoader.inst().clear_cache()
            except Exception as e:
                logging.debug(f"[CacheWorker] Clear RAM error: {e}")

        self.operation_finished.emit("clear_one", True, item["filename"])

    def _clear_all(self):
        definitions = get_cache_definitions()
        for item in definitions:
            self.progress_update.emit(f"Очистка {item['filename']}...")
            if item["type"] == "sqlite":
                clear_sqlite_db(item["path"], item["main_table"])
            else:
                try:
                    from modules.sorter.thumbnail_loader import ThumbnailLoader
                    ThumbnailLoader.inst().clear_cache()
                except Exception as e:
                    logging.debug(f"[CacheWorker] Clear RAM error: {e}")
        self.operation_finished.emit("clear_all", True, "All caches cleared successfully.")


class GlobalSettingsDialog(QDialog):
    """Unified Global Settings & Cache Manager Dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(AppContext.tr("glob_settings_title"))
        self.resize(850, 680)
        self.setMinimumSize(750, 560)

        # Worker & state
        self.cache_worker: Optional[CacheWorker] = None
        self._cached_table_data: List[Dict[str, Any]] = []

        # Load sorter config
        from modules.sorter.logic_config import ConfigManager
        self.sorter_config = ConfigManager.load()

        # Initialize hotkey registry
        self._init_registry()

        self._setup_ui()
        self._load_general_settings()
        self._load_sorter_settings()
        self._populate_hotkeys_table()
        self.refresh_cache_stats()

    def _init_registry(self):
        """Retrieve existing HotkeyRegistry from parent sorter tab or create a local copy."""
        parent = self.parent()
        registry = None
        if parent:
            if hasattr(parent, "sorter_tab") and hasattr(parent.sorter_tab, "_hotkey_registry"):
                registry = parent.sorter_tab._hotkey_registry
            elif hasattr(parent, "_hotkey_registry"):
                registry = parent._hotkey_registry

        if registry:
            self.registry = registry
        else:
            # Standalone fallback registry
            self.registry = HotkeyRegistry("sorter")
            for action in _SORTER_ACTIONS:
                self.registry.register(action)
            self.registry.load_overrides(self.sorter_config.get("hotkeys_sorter", {}))

    def _setup_ui(self):
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BG_MAIN};
                color: {TEXT_PRIMARY};
            }}
            QLabel {{
                color: {TEXT_PRIMARY};
                font-size: 13px;
                background-color: transparent;
            }}
            QLineEdit {{
                color: {TEXT_PRIMARY};
                background-color: {BG_INPUT};
                border: 1px solid {BORDER_MEDIUM};
                padding: 6px 8px;
                border-radius: 4px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {BORDER_FOCUS};
            }}
            QComboBox {{
                background-color: {BG_INPUT};
                color: {TEXT_PRIMARY};
                padding: 6px 10px;
                border: 1px solid {BORDER_MEDIUM};
                border-radius: 4px;
                font-size: 13px;
                min-width: 140px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                color: {TEXT_PRIMARY};
                background-color: {BG_INPUT};
                selection-background-color: {COLOR_PRIMARY};
                outline: 0;
            }}
            QSpinBox, QDoubleSpinBox {{
                background-color: {BG_INPUT};
                color: {TEXT_PRIMARY};
                padding: 5px 8px;
                border: 1px solid {BORDER_MEDIUM};
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
            }}
            QCheckBox {{
                color: {TEXT_PRIMARY};
                font-size: 13px;
                font-weight: bold;
                spacing: 8px;
                background: transparent;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid #6b7280;
                border-radius: 3px;
                background-color: #374151;
            }}
            QCheckBox::indicator:hover {{
                border-color: {COLOR_PRIMARY};
                background-color: #4b5563;
            }}
            QCheckBox::indicator:checked {{
                background-color: {COLOR_PRIMARY};
                border-color: {COLOR_PRIMARY};
                image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxNiAxNiIgZmlsbD0id2hpdGUiPjxwYXRoIGQ9Ik0xMy44NiAzLjY2YS41LjUgMCAwIDEgLjA4LjdsLTcgOGEuNS41IDAgMCAxLS43MiAwbC0zLjUtNGEuNS41IDAgMSAxIC43Ni0uNjRMNi41IDExLjIybDYuNjYtNy42YS41LjUgMCAwIDEgLjctLjA2eiIvPjwvc3ZnPg==);
            }}
            QTabWidget::panel {{
                border: 1px solid {BORDER_DEFAULT};
                background-color: {BG_PANEL};
                border-radius: 4px;
            }}
            QTabBar::tab {{
                background-color: {BG_CONTAINER};
                color: {TEXT_MUTED};
                border: 1px solid {BORDER_DEFAULT};
                border-bottom: none;
                padding: 8px 18px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-weight: bold;
                font-size: 13px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background-color: {BG_PANEL};
                color: {TEXT_PRIMARY};
                border-bottom: 1px solid {BG_PANEL};
            }}
            QTabBar::tab:hover {{
                background-color: {BG_HOVER};
                color: {TEXT_PRIMARY};
            }}
            QTableWidget {{
                background-color: {BG_CONTAINER};
                color: {TEXT_PRIMARY};
                gridline-color: {BORDER_DEFAULT};
                border: 1px solid {BORDER_DEFAULT};
                border-radius: 4px;
            }}
            QTableWidget::item {{
                padding: 6px 10px;
                border-bottom: 1px solid {BORDER_DEFAULT};
            }}
            QTableWidget::item:selected {{
                background-color: {BG_SELECTED};
                color: {TEXT_PRIMARY};
            }}
            QHeaderView::section {{
                background-color: {BG_DARK};
                color: {TEXT_MUTED};
                padding: 6px;
                border: 1px solid {BORDER_DEFAULT};
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton {{
                color: {TEXT_PRIMARY};
                background-color: {BG_INPUT};
                border: 1px solid {BORDER_MEDIUM};
                padding: 6px 14px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {BG_HOVER};
                border-color: {BORDER_FOCUS};
            }}
            QPushButton:pressed {{
                background-color: {BG_CONTAINER};
            }}
            QPushButton#BtnPrimary {{
                background-color: {COLOR_PRIMARY};
                border: 1px solid {COLOR_PRIMARY_HOVER};
            }}
            QPushButton#BtnPrimary:hover {{
                background-color: {COLOR_PRIMARY_HOVER};
            }}
            QPushButton#BtnDanger {{
                background-color: {COLOR_DANGER};
                border: 1px solid {COLOR_DANGER_HOVER};
            }}
            QPushButton#BtnDanger:hover {{
                background-color: {COLOR_DANGER_HOVER};
            }}
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Tab widget with 4 tabs
        self.tab_widget = QTabWidget(self)
        main_layout.addWidget(self.tab_widget, stretch=1)

        # 1. Tab: General
        self.tab_general = QWidget()
        self._init_general_tab()
        self.tab_widget.addTab(self.tab_general, AppContext.tr("glob_tab_general"))

        # 2. Tab: Sorter
        self.tab_sorter = QWidget()
        self._init_sorter_tab()
        self.tab_widget.addTab(self.tab_sorter, AppContext.tr("glob_tab_sorter"))

        # 3. Tab: Hotkeys
        self.tab_hotkeys = QWidget()
        self._init_hotkeys_tab()
        self.tab_widget.addTab(self.tab_hotkeys, AppContext.tr("glob_tab_hotkeys"))

        # 4. Tab: Cache & Databases
        self.tab_cache = QWidget()
        self._init_cache_tab()
        self.tab_widget.addTab(self.tab_cache, AppContext.tr("glob_tab_cache"))

        # Bottom Controls
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        bottom_layout.addWidget(self.lbl_status, stretch=1)

        self.btn_save = QPushButton(AppContext.tr("btn_save"))
        self.btn_save.setObjectName("BtnPrimary")
        self.btn_save.setMinimumWidth(110)
        self.btn_save.clicked.connect(self.save_settings)
        bottom_layout.addWidget(self.btn_save)

        self.btn_close = QPushButton(AppContext.tr("btn_close"))
        self.btn_close.setMinimumWidth(90)
        self.btn_close.clicked.connect(self.reject)
        bottom_layout.addWidget(self.btn_close)

        main_layout.addLayout(bottom_layout)

    # -------------------------------------------------------------------------
    # TAB 1: GENERAL
    # -------------------------------------------------------------------------
    def _init_general_tab(self):
        scroll = QScrollArea(self.tab_general)
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 1. Interface Language
        sec_lang = QVBoxLayout()
        sec_lang.setSpacing(6)
        lbl_lang_header = QLabel(AppContext.tr("glob_lang_title"))
        lbl_lang_header.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {COLOR_PRIMARY};")
        sec_lang.addWidget(lbl_lang_header)

        row_lang = QHBoxLayout()
        row_lang.setSpacing(10)
        self.cb_language = QComboBox()
        self.cb_language.addItem("Русский (RU)", "RU")
        self.cb_language.addItem("English (EN)", "EN")
        row_lang.addWidget(self.cb_language)
        row_lang.addStretch()
        sec_lang.addLayout(row_lang)
        layout.addLayout(sec_lang)

        self._add_separator(layout)

        # 2. AI Hardware Acceleration (DirectML GPU)
        sec_gpu = QVBoxLayout()
        sec_gpu.setSpacing(6)
        lbl_gpu_header = QLabel(AppContext.tr("glob_gpu_title"))
        lbl_gpu_header.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {COLOR_PRIMARY};")
        sec_gpu.addWidget(lbl_gpu_header)

        self.chk_directml = QCheckBox(AppContext.tr("glob_gpu_checkbox"))
        sec_gpu.addWidget(self.chk_directml)

        self.lbl_gpu_status = QLabel("")
        self.lbl_gpu_status.setStyleSheet("font-size: 12px; margin-left: 24px;")
        sec_gpu.addWidget(self.lbl_gpu_status)
        layout.addLayout(sec_gpu)

        self._add_separator(layout)

        # 3. AI Neural Models
        sec_models = QVBoxLayout()
        sec_models.setSpacing(6)
        lbl_models_header = QLabel(AppContext.tr("glob_models_title"))
        lbl_models_header.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {COLOR_PRIMARY};")
        sec_models.addWidget(lbl_models_header)

        self.lbl_models_status = QLabel("")
        self.lbl_models_status.setStyleSheet(f"font-size: 13px; color: {TEXT_BODY};")
        sec_models.addWidget(self.lbl_models_status)

        row_models = QHBoxLayout()
        row_models.setSpacing(10)
        self.btn_download_models = QPushButton(AppContext.tr("glob_models_download"))
        self.btn_download_models.setObjectName("BtnPrimary")
        self.btn_download_models.clicked.connect(self._download_models)
        row_models.addWidget(self.btn_download_models)

        self.btn_open_models = QPushButton(AppContext.tr("glob_models_open"))
        self.btn_open_models.clicked.connect(self._open_models_folder)
        row_models.addWidget(self.btn_open_models)
        row_models.addStretch()
        sec_models.addLayout(row_models)
        layout.addLayout(sec_models)

        self._add_separator(layout)

        # 4. FFmpeg Codecs
        sec_ffmpeg = QVBoxLayout()
        sec_ffmpeg.setSpacing(6)
        lbl_ffmpeg_header = QLabel(AppContext.tr("glob_ffmpeg_title"))
        lbl_ffmpeg_header.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {COLOR_PRIMARY};")
        sec_ffmpeg.addWidget(lbl_ffmpeg_header)

        self.lbl_ffmpeg_status = QLabel("")
        self.lbl_ffmpeg_status.setStyleSheet(f"font-size: 13px; color: {TEXT_BODY};")
        sec_ffmpeg.addWidget(self.lbl_ffmpeg_status)

        row_ffmpeg = QHBoxLayout()
        row_ffmpeg.setSpacing(10)
        self.btn_download_ffmpeg = QPushButton(AppContext.tr("glob_ffmpeg_download"))
        self.btn_download_ffmpeg.setObjectName("BtnPrimary")
        self.btn_download_ffmpeg.clicked.connect(self._download_ffmpeg)
        row_ffmpeg.addWidget(self.btn_download_ffmpeg)

        self.btn_open_ffmpeg = QPushButton(AppContext.tr("glob_ffmpeg_open"))
        self.btn_open_ffmpeg.clicked.connect(self._open_ffmpeg_folder)
        row_ffmpeg.addWidget(self.btn_open_ffmpeg)
        row_ffmpeg.addStretch()
        sec_ffmpeg.addLayout(row_ffmpeg)
        layout.addLayout(sec_ffmpeg)

        self._add_separator(layout)

        # 5. System Logs
        sec_logs = QVBoxLayout()
        sec_logs.setSpacing(6)
        lbl_logs_header = QLabel(AppContext.tr("glob_logs_title"))
        lbl_logs_header.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {COLOR_PRIMARY};")
        sec_logs.addWidget(lbl_logs_header)

        self.lbl_logs_size = QLabel(f"{AppContext.tr('glob_logs_size')} ...")
        self.lbl_logs_size.setStyleSheet(f"color: {TEXT_BODY}; font-size: 13px;")
        sec_logs.addWidget(self.lbl_logs_size)

        row_logs = QHBoxLayout()
        row_logs.setSpacing(10)
        self.btn_open_logs = QPushButton(AppContext.tr("glob_logs_open"))
        self.btn_open_logs.clicked.connect(self._open_logs_folder)
        row_logs.addWidget(self.btn_open_logs)

        self.btn_clear_logs = QPushButton(AppContext.tr("glob_logs_clear"))
        self.btn_clear_logs.clicked.connect(self._clear_logs_file)
        row_logs.addWidget(self.btn_clear_logs)
        row_logs.addStretch()
        sec_logs.addLayout(row_logs)
        layout.addLayout(sec_logs)

        layout.addStretch()

        outer_l = QVBoxLayout(self.tab_general)
        outer_l.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(container)
        outer_l.addWidget(scroll)

    def _add_separator(self, layout):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet(f"color: {BORDER_DEFAULT};")
        layout.addWidget(line)

    def _load_general_settings(self):
        # Language
        current_lang = AppContext.LANG
        for i in range(self.cb_language.count()):
            if self.cb_language.itemData(i) == current_lang:
                self.cb_language.setCurrentIndex(i)
                break

        # DirectML GPU status
        from modules.cleaner.core_directml import DirectMLManager
        use_dml = self.sorter_config.get("use_directml", True)
        self.chk_directml.setChecked(bool(use_dml))

        if DirectMLManager.is_ready:
            self.lbl_gpu_status.setText(AppContext.tr("glob_gpu_status_active"))
            self.lbl_gpu_status.setStyleSheet(f"color: {COLOR_SUCCESS}; font-size: 12px; margin-left: 24px; font-weight: bold;")
        else:
            err = f" ({DirectMLManager.error_msg})" if DirectMLManager.error_msg else ""
            self.lbl_gpu_status.setText(f"{AppContext.tr('glob_gpu_status_inactive')}{err}")
            self.lbl_gpu_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; margin-left: 24px;")

        # AI Models status
        self._refresh_models_status()

        # FFmpeg status
        self._refresh_ffmpeg_status()

        # Logs disk size
        self._refresh_logs_size()

    def _refresh_models_status(self):
        engine = AiEngine()
        models_present = engine.are_models_present()
        models_dir = get_models_dir()
        models_size = calc_folder_size(models_dir)

        if models_present:
            size_str = format_size(models_size) if models_size > 0 else "OK"
            self.lbl_models_status.setText(f"✅ {AppContext.tr('glob_models_size')} {size_str}")
            self.lbl_models_status.setStyleSheet(f"color: {COLOR_SUCCESS}; font-weight: bold; font-size: 13px;")
            self.btn_download_models.hide()
        else:
            self.lbl_models_status.setText(AppContext.tr("glob_models_not_downloaded"))
            self.lbl_models_status.setStyleSheet(f"color: {COLOR_DANGER}; font-weight: bold; font-size: 13px;")
            self.btn_download_models.show()

    def _refresh_ffmpeg_status(self):
        is_ready, _ = check_ffmpeg_available()
        if is_ready:
            self.lbl_ffmpeg_status.setText(AppContext.tr("glob_ffmpeg_ready"))
            self.lbl_ffmpeg_status.setStyleSheet(f"color: {COLOR_SUCCESS}; font-weight: bold; font-size: 13px;")
            self.btn_download_ffmpeg.hide()
        else:
            self.lbl_ffmpeg_status.setText(AppContext.tr("glob_ffmpeg_not_found"))
            self.lbl_ffmpeg_status.setStyleSheet(f"color: {COLOR_DANGER}; font-weight: bold; font-size: 13px;")
            self.btn_download_ffmpeg.show()

    def _download_models(self):
        from modules.cleaner.ai_search.ui_ai_tab import AiModelDownloaderThread
        dlg = ProgressDialog("Загрузка моделей нейросетей..." if AppContext.is_ru() else "Downloading AI models...", self, show_cancel=True)
        engine = AiEngine()
        downloader = AiModelDownloaderThread(engine, self)

        def on_progress(filename, downloaded, total_size):
            if total_size > 0:
                percent = int((downloaded / total_size) * 100)
                dlg.bar_total.setValue(percent)
                dlg.lbl_total.setText(f"{filename}: {format_size(downloaded)} / {format_size(total_size)}")
            else:
                dlg.lbl_total.setText(f"{filename}: {format_size(downloaded)}")

        def on_finished(success):
            dlg.accept()
            if success:
                silent_info(self, AppContext.tr("dlg_settings_title"), "Модели нейросетей успешно скачаны и готовы к работе!" if AppContext.is_ru() else "AI models successfully downloaded!")
            else:
                silent_warning(self, "Ошибка загрузки" if AppContext.is_ru() else "Download Error", "Не удалось загрузить модели нейросетей. Проверьте интернет-соединение." if AppContext.is_ru() else "Failed to download AI models.")
            self._refresh_models_status()

        dlg.cancelled.connect(downloader.stop)
        downloader.progress_signal.connect(on_progress)
        downloader.finished_signal.connect(on_finished)
        downloader.start()
        dlg.exec()

    def _download_ffmpeg(self):
        dlg = ProgressDialog("Загрузка кодеков FFmpeg..." if AppContext.is_ru() else "Downloading FFmpeg...", self, show_cancel=True)
        worker = FFmpegDownloaderWorker()

        def on_progress(percent):
            dlg.bar_total.setValue(percent)

        def on_status(msg):
            dlg.lbl_title.setText(msg)

        def on_finished(success, err_msg):
            dlg.accept()
            if success:
                silent_info(self, AppContext.tr("dlg_settings_title"), "Кодеки FFmpeg успешно скачаны и установлены!" if AppContext.is_ru() else "FFmpeg codecs successfully installed!")
                parent = self.parent()
                if parent and hasattr(parent, 'on_ffmpeg_downloaded'):
                    parent.on_ffmpeg_downloaded()
            else:
                silent_warning(self, "Ошибка загрузки" if AppContext.is_ru() else "Download Error", f"Не удалось загрузить FFmpeg: {err_msg}")
            self._refresh_ffmpeg_status()

        dlg.cancelled.connect(worker.stop)
        worker.progress_updated.connect(on_progress)
        worker.status_message.connect(on_status)
        worker.finished.connect(on_finished)
        worker.start()
        dlg.exec()

    def _refresh_logs_size(self):
        log_path = get_log_file_path()
        if safe_path_exists(log_path):
            try:
                log_size = os.path.getsize(log_path)
                size_str = format_size(log_size)
            except Exception:
                size_str = "0 Б"
        else:
            size_str = "0 Б"
        self.lbl_logs_size.setText(f"{AppContext.tr('glob_logs_size')} {size_str}")

    def _open_models_folder(self):
        models_dir = get_models_dir()
        if not safe_path_exists(models_dir):
            try:
                os.makedirs(models_dir, exist_ok=True)
            except Exception:
                pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(models_dir)))

    def _open_ffmpeg_folder(self):
        bin_dir = get_ffmpeg_bin_dir()
        if not safe_path_exists(bin_dir):
            try:
                os.makedirs(bin_dir, exist_ok=True)
            except Exception:
                pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(bin_dir)))

    def _open_logs_folder(self):
        log_path = get_log_file_path()
        log_dir = os.path.dirname(os.path.abspath(log_path))
        if not safe_path_exists(log_dir):
            try:
                os.makedirs(log_dir, exist_ok=True)
            except Exception:
                pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(log_dir))

    def _clear_logs_file(self):
        log_path = get_log_file_path()
        if safe_path_exists(log_path):
            try:
                with open(log_path, 'r+', encoding='utf-8', errors='ignore') as f:
                    f.truncate(0)
                logging.info("[GlobalSettings] media_keeper.log cleared by user.")
            except Exception as e:
                logging.warning(f"[GlobalSettings] Failed to truncate log file: {e}")
        self._refresh_logs_size()

    # -------------------------------------------------------------------------
    # TAB 2: SORTER
    # -------------------------------------------------------------------------
    def _init_sorter_tab(self):
        scroll = QScrollArea(self.tab_sorter)
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 1. Directories Section
        lbl_paths_header = QLabel(AppContext.tr("glob_sorter_paths_title"))
        lbl_paths_header.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {COLOR_PRIMARY};")
        layout.addWidget(lbl_paths_header)

        # Sort Path
        lbl_sort = QLabel(AppContext.tr("glob_sorter_sort_path"))
        layout.addWidget(lbl_sort)
        row_sort = QHBoxLayout()
        row_sort.setSpacing(6)
        self.e_sort_path = QLineEdit()
        row_sort.addWidget(self.e_sort_path, stretch=1)
        btn_browse_sort = QPushButton(AppContext.tr("btn_browse"))
        btn_browse_sort.clicked.connect(self._browse_sort_path)
        row_sort.addWidget(btn_browse_sort)
        btn_clear_sort = QPushButton("🗑️")
        btn_clear_sort.setFixedWidth(36)
        btn_clear_sort.setToolTip("Очистить путь" if AppContext.is_ru() else "Clear path")
        btn_clear_sort.clicked.connect(lambda: self.e_sort_path.setText(""))
        row_sort.addWidget(btn_clear_sort)
        layout.addLayout(row_sort)

        # Trash Path
        lbl_todel = QLabel(AppContext.tr("glob_sorter_todel_path"))
        layout.addWidget(lbl_todel)
        row_todel = QHBoxLayout()
        row_todel.setSpacing(6)
        self.e_todel_path = QLineEdit()
        row_todel.addWidget(self.e_todel_path, stretch=1)
        btn_browse_todel = QPushButton(AppContext.tr("btn_browse"))
        btn_browse_todel.clicked.connect(self._browse_todel_path)
        row_todel.addWidget(btn_browse_todel)
        btn_clear_todel = QPushButton("🗑️")
        btn_clear_todel.setFixedWidth(36)
        btn_clear_todel.setToolTip("Очистить путь" if AppContext.is_ru() else "Clear path")
        btn_clear_todel.clicked.connect(lambda: self.e_todel_path.setText(""))
        row_todel.addWidget(btn_clear_todel)
        layout.addLayout(row_todel)

        self._add_separator(layout)

        # 2. Scanning & Pagination
        grid_opts = QGridLayout()
        grid_opts.setHorizontalSpacing(16)
        grid_opts.setVerticalSpacing(12)

        self.chk_scan_subfolders = QCheckBox(AppContext.tr("glob_sorter_scan_subfolders"))
        grid_opts.addWidget(self.chk_scan_subfolders, 0, 0)

        row_depth = QHBoxLayout()
        row_depth.setSpacing(8)
        lbl_depth = QLabel(AppContext.tr("glob_sorter_nesting_depth"))
        row_depth.addWidget(lbl_depth)
        self.spin_depth = QSpinBox()
        self.spin_depth.setRange(1, 50)
        self.spin_depth.setFixedWidth(90)
        row_depth.addWidget(self.spin_depth)
        row_depth.addStretch()
        grid_opts.addLayout(row_depth, 0, 1)

        self.chk_auto_collapse = QCheckBox(AppContext.tr("glob_sorter_collapse_groups"))
        grid_opts.addWidget(self.chk_auto_collapse, 1, 0)

        row_pag = QHBoxLayout()
        row_pag.setSpacing(8)
        lbl_pag = QLabel(AppContext.tr("glob_sorter_pagination"))
        row_pag.addWidget(lbl_pag)
        self.spin_pagination = QSpinBox()
        self.spin_pagination.setRange(50, 5000)
        self.spin_pagination.setSingleStep(100)
        self.spin_pagination.setFixedWidth(90)
        row_pag.addWidget(self.spin_pagination)
        row_pag.addStretch()
        grid_opts.addLayout(row_pag, 1, 1)

        row_delay = QHBoxLayout()
        row_delay.setSpacing(8)
        lbl_delay = QLabel(AppContext.tr("glob_sorter_list_delay"))
        row_delay.addWidget(lbl_delay)
        self.spin_list_delay = QDoubleSpinBox()
        self.spin_list_delay.setRange(0.0, 10.0)
        self.spin_list_delay.setSingleStep(0.1)
        self.spin_list_delay.setDecimals(2)
        self.spin_list_delay.setFixedWidth(90)
        row_delay.addWidget(self.spin_list_delay)
        row_delay.addStretch()
        grid_opts.addLayout(row_delay, 2, 0, 1, 2)

        layout.addLayout(grid_opts)

        self._add_separator(layout)

        # 3. Filters Section
        lbl_filter_header = QLabel("Фильтрация файлов" if AppContext.is_ru() else "File Filtering")
        lbl_filter_header.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {COLOR_PRIMARY};")
        layout.addWidget(lbl_filter_header)

        row_filter = QHBoxLayout()
        row_filter.setSpacing(10)
        lbl_filter_exts = QLabel(AppContext.tr("glob_sorter_filter_exts"))
        row_filter.addWidget(lbl_filter_exts)
        self.e_filter_exts = QLineEdit()
        self.e_filter_exts.setPlaceholderText("например: png, jpg, mp4" if AppContext.is_ru() else "e.g. png, jpg, mp4")
        row_filter.addWidget(self.e_filter_exts, stretch=1)

        self.cb_filter_mode = QComboBox()
        self.cb_filter_mode.addItem(AppContext.tr("glob_sorter_filter_inc"), "include")
        self.cb_filter_mode.addItem(AppContext.tr("glob_sorter_filter_exc"), "exclude")
        row_filter.addWidget(self.cb_filter_mode)
        layout.addLayout(row_filter)

        self._add_separator(layout)

        # 4. Affix Section
        lbl_affix_header = QLabel(AppContext.tr("glob_sorter_affix_title"))
        lbl_affix_header.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {COLOR_PRIMARY};")
        layout.addWidget(lbl_affix_header)

        row_affix = QHBoxLayout()
        row_affix.setSpacing(10)
        self.cb_affix_mode = QComboBox()
        self.cb_affix_mode.addItem("Префикс" if AppContext.is_ru() else "Prefix", "prefix")
        self.cb_affix_mode.addItem("Суффикс" if AppContext.is_ru() else "Suffix", "suffix")
        row_affix.addWidget(self.cb_affix_mode)

        self.e_affix_text = QLineEdit()
        self.e_affix_text.setPlaceholderText("Текст аффикса..." if AppContext.is_ru() else "Affix text...")
        row_affix.addWidget(self.e_affix_text, stretch=1)
        layout.addLayout(row_affix)

        layout.addStretch()

        outer_l = QVBoxLayout(self.tab_sorter)
        outer_l.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(container)
        outer_l.addWidget(scroll)

    def _load_sorter_settings(self):
        self.e_sort_path.setText(self.sorter_config.get("path_sort", ""))
        self.e_todel_path.setText(self.sorter_config.get("path_todel", ""))
        self.chk_scan_subfolders.setChecked(bool(self.sorter_config.get("scan_subfolders", False)))
        self.spin_depth.setValue(int(self.sorter_config.get("max_nesting_depth", 5)))
        self.spin_pagination.setValue(int(self.sorter_config.get("pagination_size", 1000)))
        self.chk_auto_collapse.setChecked(bool(self.sorter_config.get("auto_collapse_groups", True)))
        self.spin_list_delay.setValue(float(self.sorter_config.get("list_view_delay", 0.0)))

        self.e_filter_exts.setText(self.sorter_config.get("filter_extensions", ""))
        f_mode = self.sorter_config.get("filter_mode", "include")
        for i in range(self.cb_filter_mode.count()):
            if self.cb_filter_mode.itemData(i) == f_mode:
                self.cb_filter_mode.setCurrentIndex(i)
                break

        a_mode = self.sorter_config.get("affix_mode", "prefix")
        for i in range(self.cb_affix_mode.count()):
            if self.cb_affix_mode.itemData(i) == a_mode:
                self.cb_affix_mode.setCurrentIndex(i)
                break
        self.e_affix_text.setText(self.sorter_config.get("affix_text", ""))

    def _browse_sort_path(self):
        cur = self.e_sort_path.text() or ""
        folder = QFileDialog.getExistingDirectory(self, AppContext.tr("btn_browse"), cur)
        if folder:
            self.e_sort_path.setText(folder)

    def _browse_todel_path(self):
        cur = self.e_todel_path.text() or ""
        folder = QFileDialog.getExistingDirectory(self, AppContext.tr("btn_browse"), cur)
        if folder:
            self.e_todel_path.setText(folder)

    # -------------------------------------------------------------------------
    # TAB 3: HOTKEYS
    # -------------------------------------------------------------------------
    def _init_hotkeys_tab(self):
        layout = QVBoxLayout(self.tab_hotkeys)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        lbl_hint = QLabel(AppContext.tr("glob_hotkeys_hint"))
        lbl_hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; font-style: italic;")
        layout.addWidget(lbl_hint)

        self.table_hotkeys = QTableWidget()
        self.table_hotkeys.setColumnCount(2)
        headers = [
            AppContext.tr("glob_hotkeys_col_action"),
            AppContext.tr("glob_hotkeys_col_key")
        ]
        self.table_hotkeys.setHorizontalHeaderLabels(headers)
        self.table_hotkeys.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_hotkeys.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table_hotkeys.setColumnWidth(1, 180)
        self.table_hotkeys.verticalHeader().setVisible(False)
        self.table_hotkeys.verticalHeader().setDefaultSectionSize(38)
        self.table_hotkeys.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        layout.addWidget(self.table_hotkeys, stretch=1)

        row_bottom = QHBoxLayout()
        self.btn_reset_hotkeys = QPushButton(AppContext.tr("glob_hotkeys_reset"))
        self.btn_reset_hotkeys.setStyleSheet(f"background-color: #991b1b; color: white; font-weight: bold;")
        self.btn_reset_hotkeys.clicked.connect(self._reset_all_hotkeys)
        row_bottom.addWidget(self.btn_reset_hotkeys)
        row_bottom.addStretch()
        layout.addLayout(row_bottom)

    def _populate_hotkeys_table(self):
        if not self.registry:
            return
        actions = self.registry.get_all_actions()
        is_ru = AppContext.is_ru()
        group_names = {
            "navigation": "Навигация" if is_ru else "Navigation",
            "file": "Операции с файлами" if is_ru else "File Operations",
            "playback": "Плеер" if is_ru else "Playback",
            "view": "Режимы просмотра" if is_ru else "View Modes"
        }

        sorted_actions = sorted(actions, key=lambda a: (a.group, a.action_id))
        self.table_hotkeys.setRowCount(len(sorted_actions))

        for idx, action in enumerate(sorted_actions):
            lbl_desc = QLabel(action.label_ru if is_ru else action.label_en)
            lbl_desc.setStyleSheet("padding: 4px; font-weight: bold;")
            group_lbl = group_names.get(action.group, action.group)
            lbl_desc.setText(f"[{group_lbl}] {lbl_desc.text()}")
            self.table_hotkeys.setCellWidget(idx, 0, lbl_desc)

            current_key = self.registry.get_effective_key(action.action_id)
            btn_capture = HotkeyCaptureButton(current_key)
            btn_capture.hotkey_captured.connect(
                lambda key_str, act_id=action.action_id, btn=btn_capture: self._on_hotkey_changed(act_id, key_str, btn)
            )
            self.table_hotkeys.setCellWidget(idx, 1, btn_capture)

    def _on_hotkey_changed(self, action_id: str, key_str: str, btn_widget: HotkeyCaptureButton):
        if not self.registry:
            return

        conflict_action = None
        for act in self.registry.get_all_actions():
            if act.action_id != action_id:
                effective_key = self.registry.get_effective_key(act.action_id)
                if effective_key == key_str and key_str != "":
                    conflict_action = act
                    break

        if conflict_action:
            is_ru = AppContext.is_ru()
            conflict_name = conflict_action.label_ru if is_ru else conflict_action.label_en
            current_name = self.registry._actions[action_id].label_ru if is_ru else self.registry._actions[action_id].label_en

            reply = silent_question(
                self,
                "Конфликт горячих клавиш" if is_ru else "Hotkey Conflict",
                f"Сочетание '{key_str}' уже используется для действия:\n「{conflict_name}」.\n\nНазначить его для «{current_name}» и очистить старое действие?" if is_ru
                else f"Shortcut '{key_str}' is already assigned to:\n\"{conflict_name}\".\n\nAssign it to \"{current_name}\" and clear conflicting action?"
            )
            if reply == silent_question.__globals__["QMessageBox"].StandardButton.Yes:
                self.registry.set_key(conflict_action.action_id, "")
                self.registry.set_key(action_id, key_str)
                self._populate_hotkeys_table()
            else:
                btn_widget.current_key = self.registry.get_effective_key(action_id)
                btn_widget.update_button_text()
        else:
            self.registry.set_key(action_id, key_str)
            btn_widget.current_key = key_str
            btn_widget.update_button_text()

    def _reset_all_hotkeys(self):
        reply = silent_question(
            self,
            "Сброс горячих клавиш" if AppContext.is_ru() else "Reset Hotkeys",
            "Вы уверены, что хотите сбросить все горячие клавиши к значениям по умолчанию?" if AppContext.is_ru()
            else "Are you sure you want to reset all hotkeys to their default values?"
        )
        if reply == silent_question.__globals__["QMessageBox"].StandardButton.Yes:
            if self.registry:
                self.registry.reset_to_defaults()
                self._populate_hotkeys_table()

    # -------------------------------------------------------------------------
    # TAB 4: CACHE & DATABASES
    # -------------------------------------------------------------------------
    def _init_cache_tab(self):
        layout = QVBoxLayout(self.tab_cache)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Warning banner if scanning
        self.banner_scan_running = QFrame()
        self.banner_scan_running.setStyleSheet(f"""
            QFrame {{
                background-color: #3f1a1a;
                border: 1px solid {COLOR_DANGER};
                border-radius: 6px;
                padding: 4px;
            }}
        """)
        banner_layout = QHBoxLayout(self.banner_scan_running)
        banner_layout.setContentsMargins(10, 8, 10, 8)
        self.lbl_banner = QLabel(f"⚠️ {AppContext.tr('glob_scan_running_warn')}")
        self.lbl_banner.setWordWrap(True)
        self.lbl_banner.setStyleSheet(f"color: #fca5a5; font-size: 12px; font-weight: bold;")
        banner_layout.addWidget(self.lbl_banner)
        layout.addWidget(self.banner_scan_running)
        self.banner_scan_running.hide()

        # Cache Table (4 columns: Name, File, Disk Size, Actions)
        self.table_cache = QTableWidget()
        self.table_cache.setColumnCount(4)
        headers = [
            AppContext.tr("glob_col_cache_name"),
            AppContext.tr("glob_col_file"),
            AppContext.tr("glob_col_size"),
            AppContext.tr("glob_col_actions")
        ]
        self.table_cache.setHorizontalHeaderLabels(headers)
        self.table_cache.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_cache.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_cache.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_cache.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table_cache.setColumnWidth(3, 140)
        self.table_cache.verticalHeader().setVisible(False)
        self.table_cache.verticalHeader().setDefaultSectionSize(40)
        self.table_cache.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_cache.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table_cache, stretch=1)

        # Bottom info and actions
        row_bottom = QHBoxLayout()
        row_bottom.setSpacing(10)

        self.lbl_total_cache = QLabel(AppContext.tr("glob_total_cache_size").format("0 Б"))
        self.lbl_total_cache.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {COLOR_PRIMARY};")
        row_bottom.addWidget(self.lbl_total_cache, stretch=1)

        self.btn_refresh_cache = QPushButton(AppContext.tr("glob_btn_refresh"))
        self.btn_refresh_cache.clicked.connect(self.refresh_cache_stats)
        row_bottom.addWidget(self.btn_refresh_cache)

        self.btn_clear_all = QPushButton(AppContext.tr("glob_btn_clear_all"))
        self.btn_clear_all.setObjectName("BtnDanger")
        self.btn_clear_all.clicked.connect(self._on_clear_all_clicked)
        row_bottom.addWidget(self.btn_clear_all)

        layout.addLayout(row_bottom)

    def refresh_cache_stats(self):
        """Asynchronously recalculate all cache sizes."""
        scanner_busy = is_scanner_active(self.parent())
        self.banner_scan_running.setVisible(scanner_busy)
        self.btn_clear_all.setEnabled(not scanner_busy)

        self.lbl_status.setText("Вычисление размеров кэша..." if AppContext.is_ru() else "Calculating cache sizes...")
        self.btn_refresh_cache.setEnabled(False)

        self.cache_worker = CacheWorker("calculate")
        self.cache_worker.stats_ready.connect(self._on_cache_stats_ready)
        self.cache_worker.start()

    def _on_cache_stats_ready(self, items: List[Dict[str, Any]], total_bytes: int):
        self.btn_refresh_cache.setEnabled(True)
        self.lbl_status.setText("")
        self._cached_table_data = items

        scanner_busy = is_scanner_active(self.parent())

        size_str = format_size(total_bytes) if total_bytes > 0 else ("0 Б" if AppContext.is_ru() else "0 B")
        self.lbl_total_cache.setText(AppContext.tr("glob_total_cache_size").format(size_str))

        self.table_cache.setRowCount(len(items))
        for row_idx, item in enumerate(items):
            is_ru = AppContext.is_ru()
            short_name = item["name_ru"] if is_ru else item["name_en"]
            full_desc = item["desc_ru"] if is_ru else item["desc_en"]
            fname = item["filename"]
            fpath = item["path"]
            size_bytes = item["size_bytes"]
            ctype = item["type"]

            # Tooltip: Full description on line 1, full path on line 2
            tooltip_str = f"{full_desc}\nПуть: {fpath}" if is_ru else f"{full_desc}\nPath: {fpath}"

            # Col 0: Name (Short name with rich tooltip)
            item_name = QTableWidgetItem(short_name)
            item_name.setToolTip(tooltip_str)
            item_name.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            self.table_cache.setItem(row_idx, 0, item_name)

            # Col 1: File
            item_file = QTableWidgetItem(fname)
            item_file.setToolTip(tooltip_str)
            item_file.setForeground(Qt.GlobalColor.gray)
            self.table_cache.setItem(row_idx, 1, item_file)

            # Col 2: Size
            if ctype == "sqlite":
                s_str = format_size(size_bytes) if size_bytes > 0 else ("0 Б" if is_ru else "0 B")
            else:
                s_str = "В ОЗУ" if is_ru else "In RAM"
            item_size = QTableWidgetItem(s_str)
            item_size.setToolTip(tooltip_str)
            item_size.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_cache.setItem(row_idx, 2, item_size)

            # Col 3: Action button (Single clean wide button)
            cell_widget = QWidget()
            cell_layout = QHBoxLayout(cell_widget)
            cell_layout.setContentsMargins(4, 2, 4, 2)
            cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            btn_clr = QPushButton(f"🗑️ {AppContext.tr('glob_btn_clear')}")
            btn_clr.setStyleSheet(f"""
                QPushButton {{
                    color: #fca5a5;
                    border: 1px solid {COLOR_DANGER};
                    background-color: #2a1515;
                    padding: 5px 14px;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: bold;
                    min-width: 100px;
                }}
                QPushButton:hover {{
                    background-color: {COLOR_DANGER};
                    color: white;
                }}
            """)
            btn_clr.setEnabled(not scanner_busy)
            btn_clr.clicked.connect(lambda checked=False, cid=item["id"], cname=short_name: self._on_clear_one_clicked(cid, cname))
            cell_layout.addWidget(btn_clr)

            self.table_cache.setCellWidget(row_idx, 3, cell_widget)

    def _on_clear_one_clicked(self, cache_id: str, cache_name: str):
        if is_scanner_active(self.parent()):
            silent_warning(self, AppContext.tr("glob_cache_cleared_title"), AppContext.tr("glob_scan_running_warn"))
            return

        msg = AppContext.tr("glob_confirm_clear_one_msg").format(cache_name)
        res = silent_question(self, AppContext.tr("glob_confirm_clear_all_title"), msg)
        if res != silent_question.__globals__["QMessageBox"].StandardButton.Yes:
            return

        self.lbl_status.setText("Выполняется очистка кэша..." if AppContext.is_ru() else "Clearing cache...")
        self._set_cache_actions_enabled(False)
        self.cache_worker = CacheWorker("clear_one", target_id=cache_id)
        self.cache_worker.operation_finished.connect(self._on_operation_finished)
        self.cache_worker.start()

    def _on_clear_all_clicked(self):
        if is_scanner_active(self.parent()):
            silent_warning(self, AppContext.tr("glob_cache_cleared_title"), AppContext.tr("glob_scan_running_warn"))
            return

        msg = AppContext.tr("glob_confirm_clear_all_msg")
        res = silent_question(self, AppContext.tr("glob_confirm_clear_all_title"), msg)
        if res != silent_question.__globals__["QMessageBox"].StandardButton.Yes:
            return

        self.lbl_status.setText("Выполняется очистка всех кэшей..." if AppContext.is_ru() else "Clearing all caches...")
        self._set_cache_actions_enabled(False)
        self.cache_worker = CacheWorker("clear_all")
        self.cache_worker.operation_finished.connect(self._on_operation_finished)
        self.cache_worker.start()

    def _on_operation_finished(self, action: str, success: bool, message: str):
        self._set_cache_actions_enabled(True)
        self.lbl_status.setText("")

        if success:
            silent_info(self, AppContext.tr("glob_cache_cleared_title"), AppContext.tr("glob_cache_cleared_msg"))
        else:
            silent_warning(self, "Ошибка", f"Не удалось выполнить операцию: {message}")

        self.refresh_cache_stats()

    def _set_cache_actions_enabled(self, enabled: bool):
        self.btn_refresh_cache.setEnabled(enabled)
        self.btn_clear_all.setEnabled(enabled)
        self.table_cache.setEnabled(enabled)

    # -------------------------------------------------------------------------
    # SAVE & RETRANSLATE
    # -------------------------------------------------------------------------
    def save_settings(self):
        """Save settings across General, Sorter, and Hotkeys, update AppContext, apply language change."""
        settings_path = os.path.join(get_app_data_dir(), "settings.ini")
        cp = configparser.ConfigParser(interpolation=None)
        if safe_path_exists(settings_path):
            try:
                cp.read(settings_path, encoding='utf-8')
            except Exception as e:
                logging.error(f"[GlobalSettings] Failed to read settings.ini: {e}")

        # 1. Save Language
        selected_lang = self.cb_language.currentData()
        lang_changed = (selected_lang != AppContext.LANG)
        if "General" not in cp:
            cp["General"] = {}
        cp["General"]["Language"] = selected_lang

        # 2. Save DirectML toggle
        use_dml = self.chk_directml.isChecked()
        if "Main" not in cp:
            cp["Main"] = {}
        cp["Main"]["use_directml"] = str(use_dml)
        self.sorter_config["use_directml"] = use_dml

        # 3. Save Sorter settings
        self.sorter_config["path_sort"] = self.e_sort_path.text().strip()
        self.sorter_config["path_todel"] = self.e_todel_path.text().strip()
        self.sorter_config["scan_subfolders"] = self.chk_scan_subfolders.isChecked()
        self.sorter_config["max_nesting_depth"] = self.spin_depth.value()
        self.sorter_config["pagination_size"] = self.spin_pagination.value()
        self.sorter_config["auto_collapse_groups"] = self.chk_auto_collapse.isChecked()
        self.sorter_config["list_view_delay"] = self.spin_list_delay.value()
        self.sorter_config["filter_extensions"] = self.e_filter_exts.text().strip()
        self.sorter_config["filter_mode"] = self.cb_filter_mode.currentData()
        self.sorter_config["affix_mode"] = self.cb_affix_mode.currentData()
        self.sorter_config["affix_text"] = self.e_affix_text.text().strip()

        # 4. Save Hotkeys overrides
        if self.registry:
            hotkey_overrides = self.registry.save_overrides()
            self.sorter_config["hotkeys_sorter"] = hotkey_overrides
            if hotkey_overrides:
                cp["Hotkeys_sorter"] = {k: str(v) for k, v in hotkey_overrides.items()}
            elif "Hotkeys_sorter" in cp:
                cp.remove_section("Hotkeys_sorter")

        for k, v in self.sorter_config.items():
            if not k.startswith("hotkeys_"):
                cp["Main"][k] = str(v)

        try:
            with open(settings_path, 'w', encoding='utf-8') as f:
                cp.write(f)
            logging.info("[GlobalSettings] settings.ini successfully saved.")
        except Exception as e:
            logging.error(f"[GlobalSettings] Error writing settings.ini: {e}", exc_info=True)

        # Apply language update across application
        if lang_changed:
            AppContext.LANG = selected_lang
            AppContext.load_languages()
            self.retranslate_ui()
            parent = self.parent()
            if parent and hasattr(parent, "update_ui_text"):
                parent.update_ui_text()

        # Update parent sorter tab config & hotkeys if available
        parent = self.parent()
        if parent and hasattr(parent, "sorter_tab"):
            if hasattr(parent.sorter_tab, "config"):
                parent.sorter_tab.config.update(self.sorter_config)
            if hasattr(parent.sorter_tab, "_hotkey_registry"):
                parent.sorter_tab._hotkey_registry.apply_all(parent.sorter_tab)

        save_msg = "Настройки успешно сохранены!" if AppContext.is_ru() else "Settings successfully saved!"
        silent_info(self, AppContext.tr("dlg_settings_title"), save_msg)
        self.accept()

    def retranslate_ui(self):
        """Update dialog labels and headers when language is switched."""
        self.setWindowTitle(AppContext.tr("glob_settings_title"))
        self.tab_widget.setTabText(0, AppContext.tr("glob_tab_general"))
        self.tab_widget.setTabText(1, AppContext.tr("glob_tab_sorter"))
        self.tab_widget.setTabText(2, AppContext.tr("glob_tab_hotkeys"))
        self.tab_widget.setTabText(3, AppContext.tr("glob_tab_cache"))

        self.btn_save.setText(AppContext.tr("btn_save"))
        self.btn_close.setText(AppContext.tr("btn_close"))
        self.chk_directml.setText(AppContext.tr("glob_gpu_checkbox"))
        self.btn_open_models.setText(AppContext.tr("glob_models_open"))
        self.btn_download_models.setText(AppContext.tr("glob_models_download"))
        self.btn_open_ffmpeg.setText(AppContext.tr("glob_ffmpeg_open"))
        self.btn_download_ffmpeg.setText(AppContext.tr("glob_ffmpeg_download"))
        self.btn_open_logs.setText(AppContext.tr("glob_logs_open"))
        self.btn_clear_logs.setText(AppContext.tr("glob_logs_clear"))

        self.btn_reset_hotkeys.setText(AppContext.tr("glob_hotkeys_reset"))
        self.table_hotkeys.setHorizontalHeaderLabels([
            AppContext.tr("glob_hotkeys_col_action"),
            AppContext.tr("glob_hotkeys_col_key")
        ])
        self._populate_hotkeys_table()

        self.btn_refresh_cache.setText(AppContext.tr("glob_btn_refresh"))
        self.btn_clear_all.setText(AppContext.tr("glob_btn_clear_all"))

        headers = [
            AppContext.tr("glob_col_cache_name"),
            AppContext.tr("glob_col_file"),
            AppContext.tr("glob_col_size"),
            AppContext.tr("glob_col_actions")
        ]
        self.table_cache.setHorizontalHeaderLabels(headers)

    def closeEvent(self, event):
        """Cleanly terminate worker thread if running before closing."""
        if self.cache_worker and self.cache_worker.isRunning():
            self.cache_worker.wait(1500)
        super().closeEvent(event)
