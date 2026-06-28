
import os
import configparser
import logging
from config import APP_DESIGN

class ConfigManager:
    DEFAULT_CONFIG = {
        "path_unsort": "", # Empty by default for safety
        "path_sort": "",
        "path_todel": "",
        "max_nesting": 10,
        "scan_subfolders": False, 
        "filter_mode": "include",
        "filter_extensions": "", 
        "affix_mode": "prefix",
        "affix_separator": "_",
        "affix_text": "<Work>, <Family>, <Humor>, <%date_%time>",
        "temp_roots": "",
        "sort_type": "type_asc",
        "hover_delay": 0.4,
        "session_loop": False,
        "session_all_videos_active": False,
        "collapse_groups": False
    }
    
    @staticmethod
    def get_config_path():
        from logic_paths import get_app_data_dir
        return os.path.join(get_app_data_dir(), "settings.ini")

    @staticmethod
    def get_base_dir():
        from logic_paths import get_app_data_dir
        return os.path.dirname(get_app_data_dir())

    @staticmethod
    def load():
        config = ConfigManager.DEFAULT_CONFIG.copy()
        path = ConfigManager.get_config_path()
        logging.info(f"Загрузка конфигурации из файла: {path}")
        
        if os.path.exists(path):
            cp = configparser.ConfigParser(interpolation=None)
            try:
                cp.read(path, encoding='utf-8')
                if "Main" in cp:
                    for k, v in cp["Main"].items():
                        if k in config:
                            if k == "scan_subfolders":
                                config[k] = (v.lower() == "true")
                            elif k == "max_nesting":
                                try: 
                                    config[k] = int(v)
                                except ValueError: 
                                    config[k] = 10
                                    logging.warning(f"Некорректное значение для '{k}' в settings.ini: '{v}'. Используется значение по умолчанию 10.")
                            elif k == "hover_delay":
                                try:
                                    config[k] = float(v)
                                except ValueError:
                                    config[k] = 0.4
                                    logging.warning(f"Некорректное значение для '{k}' в settings.ini: '{v}'. Используется значение по умолчанию 0.4.")
                            elif k == "session_loop":
                                config[k] = (v.lower() == "true")
                            elif k == "session_all_videos_active":
                                config[k] = (v.lower() == "true")
                            elif k == "collapse_groups":
                                config[k] = (v.lower() == "true")
                            else:
                                config[k] = v
                
                # Загружаем другие секции (например, переопределения горячих клавиш)
                for section in cp.sections():
                    if section.lower().startswith("hotkeys_"):
                        scope = section[len("hotkeys_"):].lower()
                        config[f"hotkeys_{scope}"] = dict(cp[section])
                        
                logging.info("Файл settings.ini успешно загружен и обработан.")
            except Exception as e:
                logging.error(f"Ошибка при чтении settings.ini: {e}", exc_info=True)
        else:
            logging.warning("Файл settings.ini не найден. Будут использованы настройки по умолчанию.")
        
        # Reset paths if they don't exist instead of creating them
        for k in ["path_unsort", "path_sort", "path_todel"]:
            if config[k] and not os.path.exists(config[k]):
                logging.warning(f"Директория из конфигурации не существует и будет сброшена: {config[k]}")
                config[k] = ""
        
        # Clean up temp_roots
        if config.get("temp_roots"):
            valid = []
            for p in config["temp_roots"].split("|"):
                p = p.strip()
                if p and os.path.exists(p):
                    valid.append(p)
            config["temp_roots"] = "|".join(valid)
            
        from config import AppContext
        AppContext.session_loop = config.get("session_loop", False)
        AppContext.session_all_videos_active = config.get("session_all_videos_active", False)
                 
        return config

    @staticmethod
    def save(config):
        from config import AppContext
        config["session_loop"] = AppContext.session_loop
        config["session_all_videos_active"] = AppContext.session_all_videos_active
        
        path = ConfigManager.get_config_path()
        logging.info(f"Сохранение конфигурации в файл: {path}")
        cp = configparser.ConfigParser(interpolation=None)
        if os.path.exists(path):
            try:
                cp.read(path, encoding='utf-8')
            except Exception as e:
                logging.error(f"Ошибка чтения settings.ini перед сохранением: {e}")
        
        # Разделяем основные настройки и секции горячих клавиш
        main_settings = {}
        hotkeys_sections = {}
        
        for k, v in config.items():
            if k.startswith("hotkeys_"):
                scope = k[len("hotkeys_"):]
                if isinstance(v, dict) and v:
                    hotkeys_sections[f"Hotkeys_{scope}"] = v
            else:
                main_settings[k] = v
                
        # Очистим старые секции горячих клавиш из файла
        for s in list(cp.sections()):
            if s.lower().startswith("hotkeys_"):
                cp.remove_section(s)
                
        cp["Main"] = {k: str(v) for k, v in main_settings.items()}
        
        for section_name, section_dict in hotkeys_sections.items():
            cp[section_name] = {k: str(v) for k, v in section_dict.items()}
            
        try:
            with open(path, 'w', encoding='utf-8') as f:
                cp.write(f)
            logging.info("Конфигурация успешно сохранена.")
        except Exception as e:
            logging.error(f"Ошибка при сохранении settings.ini: {e}", exc_info=True)

