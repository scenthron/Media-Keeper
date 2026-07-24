
# -*- coding: utf-8 -*-
import logging
import os
import sys
import queue
import re
from logging.handlers import RotatingFileHandler, QueueHandler, QueueListener

if getattr(sys, 'frozen', False):
    PROJECT_ROOT = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
else:
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class SafeFormatter(logging.Formatter):
    """
    Кастомный форматтер, маскирующий конфиденциальные данные (пути и файлы) в логах.
    Сохраняет длину названий, расширения файлов, слэши и диски, но заменяет:
    - латиницу -> i/I
    - кириллицу -> п/П
    - цифры -> 0
    """
    
    @staticmethod
    def anonymize_token(token):
        if not token:
            return token
            
        # Отделяем префиксы и суффиксы (кавычки, скобки, знаки препинания)
        prefix = ""
        suffix = ""
        
        start_idx = 0
        while start_idx < len(token) and token[start_idx] in '\'"([{<':
            start_idx += 1
        prefix = token[:start_idx]
        
        end_idx = len(token)
        while end_idx > start_idx and token[end_idx-1] in '\'")]}>,;:':
            end_idx -= 1
        suffix = token[end_idx:]
        
        inner = token[start_idx:end_idx]
        if not inner:
            return token
            
        # 1. Проверяем, является ли это путем, файлом или модулем внутри нашего проекта
        try:
            if re.match(r'^(modules|tests|languages|logic|utils|ui|config|main|bin)\b', inner.lower()):
                return token
                
            abs_path = None
            # Файлы логов, конфигураций и БД всегда подлежат анонимизации
            if not inner.lower().endswith(('.log', '.db', '.sqlite', '.ini')):
                if not os.path.isabs(inner):
                    cand = os.path.normpath(os.path.join(PROJECT_ROOT, 'src', inner))
                    if os.path.exists(cand):
                        abs_path = cand
                    else:
                        cand = os.path.normpath(os.path.join(PROJECT_ROOT, inner))
                        if os.path.exists(cand):
                            abs_path = cand
                else:
                    abs_path = os.path.normpath(inner)
                
            if abs_path:
                norm_abs = abs_path.lower()
                norm_root = os.path.normpath(PROJECT_ROOT).lower()
                if norm_abs.startswith(norm_root):
                    if os.path.isabs(inner):
                        rel_path = inner[len(PROJECT_ROOT):].lstrip('\\/')
                        sep = '\\' if '\\' in inner else '/'
                        return prefix + "<PROJECT_ROOT>" + sep + rel_path + suffix
                    else:
                        return token
        except Exception:
            pass
            
        # Проверяем, является ли токен путем или файлом
        is_path_or_file = False
        if '\\' in inner or '/' in inner:
            is_path_or_file = True
        else:
            # Проверка на наличие расширения файла (например, image.png)
            dot_idx = inner.rfind('.')
            if dot_idx > 0:
                ext = inner[dot_idx+1:]
                if 2 <= len(ext) <= 5 and ext.isalnum() and not ext.isdigit():
                    try:
                        float(inner)
                    except ValueError:
                        is_path_or_file = True
                        
        if not is_path_or_file:
            return token
            
        # Разделяем имя и расширение
        dot_idx = inner.rfind('.')
        last_slash = max(inner.rfind('\\'), inner.rfind('/'))
        if dot_idx > last_slash and dot_idx > 0:
            ext = inner[dot_idx:]
            root = inner[:dot_idx]
        else:
            ext = ""
            root = inner
            
        anonymized_root = []
        i = 0
        # Сохраняем имя диска или префикс UNC
        if len(root) >= 2 and root[1] == ':' and root[0].isalpha():
            anonymized_root.append(root[0])
            anonymized_root.append(':')
            i = 2
        elif root.startswith('\\\\?\\'):
            anonymized_root.append('\\\\?\\')
            i = 4
            
        while i < len(root):
            c = root[i]
            if c in '\\/':
                anonymized_root.append(c)
            elif c.isdigit():
                anonymized_root.append('0')
            elif 'a' <= c.lower() <= 'z':
                anonymized_root.append('i' if c.islower() else 'I')
            elif 'а' <= c.lower() <= 'я' or c.lower() == 'ё':
                anonymized_root.append('п' if c.islower() else 'П')
            else:
                anonymized_root.append(c)
            i += 1
            
        return prefix + "".join(anonymized_root) + ext + suffix

    @staticmethod
    def anonymize_path_content(inner):
        if not inner:
            return inner
            
        # 1. Проверяем, является ли это путем, файлом или модулем внутри нашего проекта
        try:
            if re.match(r'^(modules|tests|languages|logic|utils|ui|config|main|bin)\b', inner.lower()):
                return inner
                
            abs_path = None
            # Файлы логов, конфигураций и БД всегда подлежат анонимизации
            if not inner.lower().endswith(('.log', '.db', '.sqlite', '.ini')):
                if not os.path.isabs(inner):
                    cand = os.path.normpath(os.path.join(PROJECT_ROOT, 'src', inner))
                    if os.path.exists(cand):
                        abs_path = cand
                    else:
                        cand = os.path.normpath(os.path.join(PROJECT_ROOT, inner))
                        if os.path.exists(cand):
                            abs_path = cand
                else:
                    abs_path = os.path.normpath(inner)
                
            if abs_path:
                norm_abs = abs_path.lower()
                norm_root = os.path.normpath(PROJECT_ROOT).lower()
                if norm_abs.startswith(norm_root):
                    if os.path.isabs(inner):
                        rel_path = inner[len(PROJECT_ROOT):].lstrip('\\/')
                        sep = '\\' if '\\' in inner else '/'
                        return "<PROJECT_ROOT>" + sep + rel_path
                    else:
                        return inner
        except Exception:
            pass
            
        # Разделяем имя и расширение
        dot_idx = inner.rfind('.')
        last_slash = max(inner.rfind('\\'), inner.rfind('/'))
        if dot_idx > last_slash and dot_idx > 0:
            ext = inner[dot_idx:]
            root = inner[:dot_idx]
        else:
            ext = ""
            root = inner
            
        anonymized_root = []
        i = 0
        if len(root) >= 2 and root[1] == ':' and root[0].isalpha():
            anonymized_root.append(root[0])
            anonymized_root.append(':')
            i = 2
        elif root.startswith('\\\\?\\'):
            anonymized_root.append('\\\\?\\')
            i = 4
            
        while i < len(root):
            c = root[i]
            if c in '\\/':
                anonymized_root.append(c)
            elif c.isdigit():
                anonymized_root.append('0')
            elif 'a' <= c.lower() <= 'z':
                anonymized_root.append('i' if c.islower() else 'I')
            elif 'а' <= c.lower() <= 'я' or c.lower() == 'ё':
                anonymized_root.append('п' if c.islower() else 'П')
            else:
                anonymized_root.append(c)
            i += 1
            
        return "".join(anonymized_root) + ext

    @staticmethod
    def anonymize_string(message):
        if not isinstance(message, str):
            return message
            
        saved_paths = []
        
        # 1. Функция-заменитель для путей внутри одинарных кавычек
        def replacer_single(match):
            full_match = match.group(0)
            content = match.group(2)
            if '/' in content or '\\' in content or (len(content) >= 2 and content[1] == ':'):
                anon_content = SafeFormatter.anonymize_path_content(content)
                saved_paths.append("'" + anon_content + "'")
                return f"__LOG_PATH_REF_{len(saved_paths)-1}__"
            return full_match

        # 2. Функция-заменитель для путей внутри двойных кавычек
        def replacer_double(match):
            full_match = match.group(0)
            content = match.group(2)
            if '/' in content or '\\' in content or (len(content) >= 2 and content[1] == ':'):
                anon_content = SafeFormatter.anonymize_path_content(content)
                saved_paths.append('"' + anon_content + '"')
                return f"__LOG_PATH_REF_{len(saved_paths)-1}__"
            return full_match

        # 3. Функция-заменитель для путей без кавычек
        def replacer_unquoted(match):
            full_match = match.group(0)
            content = match.group(1)
            # Исключаем ложные срабатывания на короткие диски типа "C:"
            if len(content) <= 3 and content.endswith(':'):
                return full_match
            # Исключаем случайные совпадения, если в пути нет слэшей
            if '/' not in content and '\\' not in content:
                return full_match
            anon_content = SafeFormatter.anonymize_path_content(content)
            saved_paths.append(anon_content)
            return f"__LOG_PATH_REF_{len(saved_paths)-1}__"

        # Шаг 1. Маскируем пути в кавычках
        message = re.sub(r"('(.*?)')", replacer_single, message)
        message = re.sub(r'("(.*?)")', replacer_double, message)
        
        # Шаг 2. Маскируем пути БЕЗ кавычек (начинающиеся с диска или UNC-префикса)
        path_pattern = r"((?:[A-Za-z]:[\\/]|[\\/]{2})[^\'\"<>|]*?)(?=\s+-|\s+to\s+|\s+->\s+|:(?:[\s\{\[]|$)|[\'\"<>]|$)"
        message = re.sub(path_pattern, replacer_unquoted, message)
        
        # Шаг 3. Разделяем оставшийся текст по пробелам и кавычкам/скобкам
        tokens = re.split(r'(\s+|[\'\"()\[\]{}])', message)
        anonymized_tokens = []
        for token in tokens:
            if not token or not token.strip() or token in '\'"()[]{}':
                anonymized_tokens.append(token)
            else:
                anonymized_tokens.append(SafeFormatter.anonymize_token(token))
                
        anon_message = "".join(anonymized_tokens)
        
        # Шаг 4. Возвращаем замаскированные пути на место плейсхолдеров
        for idx, path in enumerate(saved_paths):
            anon_message = anon_message.replace(f"__LOG_PATH_REF_{idx}__", path)
            
        return anon_message

    def format(self, record):
        if not hasattr(self, 'last_log_time'):
            self.last_log_time = record.created
            
        elapsed = record.created - self.last_log_time
        self.last_log_time = record.created
        time_prefix = f"[+{elapsed:.3f}s] "

        if not getattr(sys, 'frozen', False):
            return time_prefix + super().format(record)
            
        orig_msg = record.msg
        orig_args = record.args
        
        # Сначала получаем форматированное сообщение
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
            
        # Маскируем сообщение
        record.msg = self.anonymize_string(message)
        record.args = ()
        if hasattr(record, 'message'):
            del record.message
            
        try:
            result = super().format(record)
        finally:
            record.msg = orig_msg
            record.args = orig_args
            
        return time_prefix + result

    def formatException(self, ei):
        if not getattr(sys, 'frozen', False):
            return super().formatException(ei)
        orig_exception_text = super().formatException(ei)
        return self.anonymize_string(orig_exception_text)

    def formatStack(self, stack_info):
        if not getattr(sys, 'frozen', False):
            return super().formatStack(stack_info)
        orig_stack_text = super().formatStack(stack_info)
        return self.anonymize_string(orig_stack_text)

# Global listener reference to prevent garbage collection
_log_listener = None

def setup_logging():
    """
    Настраивает асинхронную систему логгирования (Non-blocking I/O).
    
    Архитектура:
    Main Thread -> QueueHandler -> Queue -> QueueListener (Thread) -> File/StreamHandler
    
    Это предотвращает блокировку интерфейса при записи логов на диск.
    """
    global _log_listener
    
    # 1. Создаем корневой логгер
    root_logger = logging.getLogger()
    
    # Очистка старых хендлеров
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Определяем путь к файлу лога и уровень логирования
    if getattr(sys, 'frozen', False):
        from logic_paths import get_app_data_dir
        log_path = os.path.join(get_app_data_dir(), "media_keeper.log")
    else:
        log_path = "media_keeper.log"

    file_log_level = logging.DEBUG
    root_logger.setLevel(logging.DEBUG)

    # 2. Форматтер
    log_formatter = SafeFormatter(
        '[%(asctime)s] [%(levelname)-8s] [%(module)s.%(funcName)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 3. Создаем "Реальные" Хендлеры (Они будут работать в фоновом потоке)
    handlers = []

    # A. Консоль (INFO)
    if sys.stdout is not None:
        try:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(log_formatter)
            handlers.append(console_handler)
        except Exception:
            pass

    # B. Файл (DEBUG) с ротацией
    try:
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(file_log_level)
        file_handler.setFormatter(log_formatter)
        handlers.append(file_handler)
    except (IOError, PermissionError) as e:
        print(f"[LOG ERROR] Не удалось создать файл лога: {e}")
        # Если ротационный файл не создался, пробуем хотя бы NullHandler
        if not handlers:
            root_logger.addHandler(logging.NullHandler())
            return

    # 4. Создаем Очередь и Слушателя
    log_queue = queue.Queue(-1) # Бесконечная очередь
    
    # QueueListener автоматически запускает свой поток для обработки записей
    _log_listener = QueueListener(log_queue, *handlers, respect_handler_level=True)
    _log_listener.start()

    # 5. Подключаем QueueHandler к корневому логгеру
    # Это единственный хендлер в основном потоке. Он просто кидает задачу в очередь.
    queue_handler = QueueHandler(log_queue)
    root_logger.addHandler(queue_handler)

    logging.info("="*50)
    logging.info(f"Асинхронная система логгирования запущена. Путь: {log_path}")
    logging.info("="*50)

def shutdown_logging():
    """Корректное завершение слушателя при выходе."""
    global _log_listener
    if _log_listener:
        try:
            _log_listener.stop()
        except Exception:
            pass
        _log_listener = None
