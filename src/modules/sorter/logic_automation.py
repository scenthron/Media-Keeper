
import os
import configparser
import re
import datetime
import random
import ctypes
import logging

class AutomationConfig:
    META_DIR = ".mediakeeper"
    CONF_FILE = "automation.ini"

    _config_cache = {}  # folder_path -> config_dict (or None)
    _icon_cache = {}    # folder_path -> icon_str

    @staticmethod
    def clear_cache():
        AutomationConfig._config_cache.clear()
        AutomationConfig._icon_cache.clear()
        logging.info("AutomationConfig cache cleared.")

    @staticmethod
    def get_cfg_path(folder_path):
        """Returns the standard path: folder/.mediakeeper/automation.ini"""
        return os.path.join(folder_path, AutomationConfig.META_DIR, AutomationConfig.CONF_FILE)

    @staticmethod
    def load_config(folder_path):
        """
        Loads config directly from the .mediakeeper folder.
        No legacy migration support.
        """
        folder_path = os.path.normpath(folder_path)
        if folder_path in AutomationConfig._config_cache:
            return AutomationConfig._config_cache[folder_path]

        if not os.path.exists(folder_path): 
            logging.debug(f"Путь для загрузки конфига автоматизации не существует: {folder_path}")
            AutomationConfig._config_cache[folder_path] = None
            return None

        target_path = AutomationConfig.get_cfg_path(folder_path)
        
        if not os.path.exists(target_path):
            logging.debug(f"Файл конфигурации автоматизации не найден в {target_path}")
            AutomationConfig._config_cache[folder_path] = None
            return None 

        # Load Data
        cp = configparser.ConfigParser(interpolation=None)
        try:
            cp.read(target_path, encoding='utf-8')
            if "Automation" in cp:
                config_data = {
                    "enabled": cp["Automation"].getboolean("enabled", fallback=False),
                    "template": cp["Automation"].get("template", ""),
                    "collision": cp["Automation"].get("collision", "Increment")
                }
                logging.info(f"Конфигурация автоматизации успешно загружена для {folder_path}: {config_data}")
                AutomationConfig._config_cache[folder_path] = config_data
                return config_data
        except Exception as e: 
            logging.error(f"Ошибка загрузки конфига автоматизации из {target_path}: {e}")
        
        AutomationConfig._config_cache[folder_path] = None
        return None

    @staticmethod
    def save_config(folder_path: str, enabled: bool, template: str, collision: str) -> None:
        folder_path = os.path.normpath(folder_path)
        AutomationConfig._config_cache.pop(folder_path, None)

        meta_dir = os.path.join(folder_path, AutomationConfig.META_DIR)
        
        # Ensure Meta Directory Exists
        if not os.path.exists(meta_dir):
            try:
                os.makedirs(meta_dir, exist_ok=True)
                logging.info(f"Создана мета-директория: {meta_dir}")
                # Try to hide the folder on Windows
                if os.name == 'nt':
                    try:
                        FILE_ATTRIBUTE_HIDDEN = 0x02
                        ctypes.windll.kernel32.SetFileAttributesW(meta_dir, FILE_ATTRIBUTE_HIDDEN)
                        logging.debug(f"Атрибут 'скрытый' установлен для {meta_dir}")
                    except Exception as hide_e:
                        logging.warning(f"Не удалось скрыть мета-директорию {meta_dir}: {hide_e}")
            except Exception as e:
                logging.error(f"Не удалось создать мета-директорию {meta_dir}: {e}")
                return

        cfg_path = os.path.join(meta_dir, AutomationConfig.CONF_FILE)
        
        cp = configparser.ConfigParser(interpolation=None)
        if os.path.exists(cfg_path):
            try:
                cp.read(cfg_path, encoding='utf-8')
            except Exception as e:
                logging.error(f"Ошибка чтения существующего конфига при сохранении: {e}")

        if "Automation" not in cp:
            cp["Automation"] = {}
            
        cp["Automation"]["enabled"] = str(enabled)
        cp["Automation"]["template"] = template
        cp["Automation"]["collision"] = collision
        
        try:
            with open(cfg_path, 'w', encoding='utf-8') as f:
                cp.write(f)
            logging.info(f"Конфигурация автоматизации сохранена в {cfg_path}")
        except Exception as e:
            logging.error(f"Ошибка сохранения конфига автоматизации в {cfg_path}: {e}")

    @staticmethod
    def load_icon(folder_path: str) -> str:
        """Loads custom folder icon from automation.ini"""
        folder_path = os.path.normpath(folder_path)
        if folder_path in AutomationConfig._icon_cache:
            return AutomationConfig._icon_cache[folder_path]

        if not os.path.exists(folder_path):
            AutomationConfig._icon_cache[folder_path] = ""
            return ""
            
        target_path = AutomationConfig.get_cfg_path(folder_path)
        if not os.path.exists(target_path):
            AutomationConfig._icon_cache[folder_path] = ""
            return ""
            
        cp = configparser.ConfigParser(interpolation=None)
        try:
            cp.read(target_path, encoding='utf-8')
            if "Automation" in cp:
                icon_symbol = cp["Automation"].get("icon", "")
                AutomationConfig._icon_cache[folder_path] = icon_symbol
                return icon_symbol
        except Exception as e:
            logging.error(f"Ошибка загрузки иконки из {target_path}: {e}")
            
        AutomationConfig._icon_cache[folder_path] = ""
        return ""

    @staticmethod
    def save_icon(folder_path: str, icon_symbol: str) -> None:
        """Saves custom folder icon to automation.ini"""
        folder_path = os.path.normpath(folder_path)
        AutomationConfig._icon_cache.pop(folder_path, None)
        meta_dir = os.path.join(folder_path, AutomationConfig.META_DIR)
        
        if not os.path.exists(meta_dir):
            try:
                os.makedirs(meta_dir, exist_ok=True)
                if os.name == 'nt':
                    try:
                        FILE_ATTRIBUTE_HIDDEN = 0x02
                        ctypes.windll.kernel32.SetFileAttributesW(meta_dir, FILE_ATTRIBUTE_HIDDEN)
                    except Exception as hide_e:
                        logging.warning(f"Не удалось скрыть мета-директорию {meta_dir}: {hide_e}")
            except Exception as e:
                logging.error(f"Не удалось создать мета-директорию {meta_dir}: {e}")
                return

        cfg_path = os.path.join(meta_dir, AutomationConfig.CONF_FILE)
        cp = configparser.ConfigParser(interpolation=None)
        
        if os.path.exists(cfg_path):
            try:
                cp.read(cfg_path, encoding='utf-8')
            except Exception as e:
                logging.error(f"Ошибка чтения существующего конфига при сохранении иконки: {e}")

        if "Automation" not in cp:
            cp["Automation"] = {}

        if icon_symbol:
            cp["Automation"]["icon"] = icon_symbol
        else:
            if "icon" in cp["Automation"]:
                del cp["Automation"]["icon"]

        try:
            with open(cfg_path, 'w', encoding='utf-8') as f:
                cp.write(f)
            logging.info(f"Кастомная иконка '{icon_symbol}' сохранена для {folder_path}")
        except Exception as e:
            logging.error(f"Ошибка сохранения иконки в {cfg_path}: {e}")

class TemplateEngine:
    @staticmethod
    def parse_template(template, original_name, parent_folder_name, iterator=None):
        now = datetime.datetime.now()
        name_no_ext = os.path.splitext(original_name)[0]
        logging.debug(f"Парсинг шаблона: '{template}' с именем '{original_name}' и итератором {iterator}")
        
        res = template.replace("%date", now.strftime("%Y-%m-%d"))
        res = res.replace("%time", now.strftime("%H.%M.%S"))
        res = res.replace("%name", name_no_ext)
        res = res.replace("%parent", parent_folder_name)
        
        if re.search(r'%seq', res, re.IGNORECASE):
            val = f"{iterator:03d}" if iterator is not None else "001"
            res = re.sub(r'%seq', val, res, flags=re.IGNORECASE)
            logging.debug(f"Тег %seq заменен на '{val}'")

        def repl_rand(match):
            n = int(match.group(1))
            rand_val = ''.join(random.choices('0123456789ABCDEF', k=n))
            logging.debug(f"Тег %rand[{n}] заменен на '{rand_val}'")
            return rand_val
        res = re.sub(r'%rand\[(\d+)\]', repl_rand, res)

        def repl_rand_num(match):
            n = int(match.group(1))
            rand_num_val = ''.join(random.choices('0123456789', k=n))
            logging.debug(f"Тег %randNum[{n}] заменен на '{rand_num_val}'")
            return rand_num_val
        res = re.sub(r'%randNum\[(\d+)\]', repl_rand_num, res)
        
        logging.info(f"Результат парсинга шаблона: '{res}'")
        return res

    @staticmethod
    def get_unique_target(dest_dir, template, original_filename, ext, collision_policy="Increment", iterator=None):
        parent_name = os.path.basename(dest_dir)
        clean_template = template
        
        match_dell = re.match(r'^%dell\[(.*)\]$', template)
        if match_dell:
            clean_template = match_dell.group(1)
            logging.debug(f"Обнаружен тег %dell, используется шаблон '{clean_template}'")
        elif "%dell" in template:
            clean_template = template.replace("%dell", "")
            logging.warning(f"Тег %dell использован некорректно, используется шаблон '{clean_template}'")
            
        base_name = TemplateEngine.parse_template(clean_template, original_filename, parent_name, iterator)
        base_name = re.sub(r'[<>:"/\\|?*]', '_', base_name)
        base_name = base_name.strip()
        
        full_path = os.path.join(dest_dir, base_name + ext)
        logging.debug(f"Сгенерирован первоначальный путь: {full_path}")
        
        if not os.path.exists(full_path):
            logging.info(f"Путь {full_path} свободен, используется он.")
            return full_path
            
        logging.warning(f"Конфликт имени файла! Путь {full_path} занят. Политика разрешения: {collision_policy}")
        if collision_policy == "Random":
            while os.path.exists(full_path):
                suffix = ''.join(random.choices('0123456789', k=4))
                full_path = os.path.join(dest_dir, f"{base_name}_{suffix}{ext}")
                logging.debug(f"Попытка нового имени (Random): {full_path}")
        else: # Increment
            c = 1
            while os.path.exists(full_path):
                full_path = os.path.join(dest_dir, f"{base_name}_{c}{ext}")
                logging.debug(f"Попытка нового имени (Increment): {full_path}")
                c += 1
                
        logging.info(f"Уникальное имя файла успешно сгенерировано: {full_path}")
        return full_path
