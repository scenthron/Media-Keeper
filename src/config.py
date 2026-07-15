
import os
import sys
from languages.manager import LanguageManager
from logic_paths import find_resource_dir as _find_res_dir, get_base_path as _get_base, get_app_data_dir as _get_app_data

APP_VERSION = "v1.0.6"

import sys
DEBUG_MODE = not getattr(sys, 'frozen', False)

APP_DESIGN = {
    "bg_color_main": "#1e1e1e",        
    "bg_color_sidebar": "#252526",     
    "bg_color_viewer": "#000000",      
    "text_color": "#ffffff",           
    "font_size_main": 14,
    "font_size_header": 16,
    "btn_delete_bg": "#b91c1c",        
    "btn_undo_bg": "#eab308",          
    "btn_nav_bg": "#444444",           
    "btn_create_bg": "#3b82f6",
    "btn_back_bg": "#64748b",
    "max_name_len": 27,
    "menu_bg": "#444444",
    "menu_btn_hover": "#3a3a3a",
    "menu_btn_active": "#3b82f6",
    
    # New additions for Media Editor
    "btn_bg": "#444444",
    "accent_color": "#3b82f6",
    "nativelike_combo": """
        QComboBox { border: 1px solid #555; border-radius: 4px; padding: 4px; background: #333; color: white; combobox-popup: 0; } 
        QComboBox::drop-down { border: 0px; }
        QComboBox QAbstractItemView {
            background-color: #333;
            color: white;
            border: 1px solid #555;
            selection-background-color: #3b82f6;
            selection-color: white;
            padding: 0px;
            margin: 0px;
            outline: 0px;
        }
        QComboBox QListView {
            background-color: #333;
            color: white;
            border: 1px solid #555;
            selection-background-color: #3b82f6;
            selection-color: white;
            padding: 0px;
            margin: 0px;
            outline: 0px;
        }
    """,
    "nativelike_input": "QLineEdit { border: 1px solid #555; border-radius: 4px; padding: 4px; background: #333; color: white; }"
}

VIEWER_DESIGN = {
    "zoom_factor": 1.15,
    "default_bg": "#000000",
    "audio_text_color": "white",
    "audio_font": "Arial",
    "audio_font_size": 24,
    "player_bg": "#111111",
    "slider_handle_color": "#3b82f6",
    "slider_groove_color": "#333333"
}

class AppContext:
    LANG = "EN"
    
    # Global media playback session variables shared across all modules
    global_volume = 0.1
    session_video_speed = 1.0
    session_loop = False
    session_all_videos_active = False
    session_segment_view = False
    
    # Global Icon Cache to prevent thousands of disk reads and SVG parses
    _icon_cache = {}

    @staticmethod
    def get_cached_icon(icon_name: str):
        """Loads and caches QIcon from the icons directory."""
        if icon_name in AppContext._icon_cache:
            return AppContext._icon_cache[icon_name]
            
        from PyQt6.QtGui import QIcon
        icons_dir = AppContext.find_resource_dir("icons")
        icon_path = os.path.join(icons_dir, icon_name) if icons_dir else ""
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        AppContext._icon_cache[icon_name] = icon
        return icon
    
    @staticmethod
    def is_ru():
        return AppContext.LANG == "RU"
        
    @staticmethod
    def save_media_settings():
        try:
            from modules.sorter.logic_config import ConfigManager
            config = ConfigManager.load()
            config["session_loop"] = AppContext.session_loop
            config["session_all_videos_active"] = AppContext.session_all_videos_active
            config["session_segment_view"] = AppContext.session_segment_view
            ConfigManager.save(config)
            import logging
            logging.info(f"Media settings saved: loop={AppContext.session_loop}, all_videos={AppContext.session_all_videos_active}, segment_view={AppContext.session_segment_view}")
        except Exception as e:
            import logging
            logging.error(f"Failed to save media settings: {e}")
            
    @staticmethod
    def _get_base_path():
        """Delegate to logic_paths"""
        return _get_base()

    @staticmethod
    def find_resource_dir(dir_name):
        """Delegate to logic_paths"""
        return _find_res_dir(dir_name)

    @staticmethod
    def load_languages():
        """Delegate to LanguageManager"""
        LanguageManager.load_language(AppContext.LANG)

    @staticmethod
    def tr(key):
        """Delegate to LanguageManager"""
        return LanguageManager.tr(key)

    @staticmethod
    def get_manual_md():
        """Delegate to LanguageManager"""
        return LanguageManager.get_manual_md()

    @staticmethod
    def get_manual_section_md(sec):
        """Delegate to LanguageManager"""
        return LanguageManager.get_manual_section_md(sec)

    @staticmethod
    def get_sort_dir():
        try:
            from modules.sorter.logic_config import ConfigManager
            return ConfigManager.load().get("path_sort", "")
        except Exception:
            return ""

# Attempt initial load. 
# Note: If logging isn't setup yet, errors here might be printed to stdout directly by manager.
import configparser
try:
    settings_path = os.path.join(_get_app_data(), "settings.ini")
    if os.path.exists(settings_path):
        config_parser = configparser.ConfigParser()
        config_parser.read(settings_path)
        if config_parser.has_option("General", "Language"):
            AppContext.LANG = config_parser.get("General", "Language")
except Exception as e:
    print(f"Error reading settings.ini for language: {e}")

try:
    AppContext.load_languages()
except Exception as e:
    print(f"Critical error during resource loading: {e}")
