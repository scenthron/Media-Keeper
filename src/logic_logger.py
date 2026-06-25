
# -*- coding: utf-8 -*-
import logging
import os
import sys
import queue
from logging.handlers import RotatingFileHandler, QueueHandler, QueueListener

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
        file_log_level = logging.WARNING
    else:
        log_path = "media_keeper.log"
        file_log_level = logging.DEBUG
        
    root_logger.setLevel(logging.DEBUG if not getattr(sys, 'frozen', False) else logging.WARNING)

    # 2. Форматтер
    log_formatter = logging.Formatter(
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
