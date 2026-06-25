import os
import sys
import logging
import tempfile
from main import global_excepthook

def test_excepthook_logging():
    # Создаем временный файл лога
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "test_media_keeper.log")
        
        # Настраиваем логирование с временным файлом
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        root_logger.setLevel(logging.DEBUG)
        
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(log_path, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter('%(message)s'))
        root_logger.addHandler(file_handler)
        
        # Имитируем вызов excepthook
        try:
            raise ValueError("Test error for excepthook")
        except ValueError as e:
            exctype, value, tb = sys.exc_info()
            global_excepthook(exctype, value, tb)
            
        # Сбрасываем хендлер
        file_handler.close()
        root_logger.handlers.clear()
        
        # Проверяем, что в логе записана наша ошибка
        assert os.path.exists(log_path)
        with open(log_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        assert "Unhandled Python exception" in content
        assert "ValueError: Test error for excepthook" in content
