import os
import sys
import subprocess
import logging
import shutil
from logic_paths import get_app_data_dir

def get_directml_dir():
    return os.path.join(get_app_data_dir(), "models", "onnx_directml")

class DirectMLManager:
    is_ready = False
    error_msg = ""
    is_testing = False

    @staticmethod
    def initialize():
        """Вызывается при старте программы (ДО импорта PyQt6)"""
        try:
            import configparser
            cfg_path = os.path.join(get_app_data_dir(), "settings.ini")
            
            cp = configparser.ConfigParser()
            if os.path.exists(cfg_path):
                cp.read(cfg_path, encoding='utf-8')
            
            # По умолчанию включено
            if "Main" not in cp:
                use_directml = True
            else:
                use_directml = cp.getboolean("Main", "use_directml", fallback=True)
                
            if use_directml:
                target_dir = get_directml_dir()
                # Проверяем наличие onnxruntime внутри папки загрузок
                ort_dir = os.path.join(target_dir, "onnxruntime")
                if not os.path.exists(ort_dir):
                    DirectMLManager.is_ready = False
                    DirectMLManager.error_msg = "Библиотека не установлена."
                    return

                # Просто добавляем путь и импортируем, без subprocess тестирования
                sys.path.insert(0, target_dir)
                try:
                    import onnxruntime
                    DirectMLManager.is_ready = True
                except Exception as e:
                    DirectMLManager.is_ready = False
                    DirectMLManager.error_msg = f"Ошибка загрузки библиотеки DirectML: {e}"
        except Exception as e:
            DirectMLManager.is_ready = False
            DirectMLManager.error_msg = f"Ошибка инициализации DirectML: {e}"
            print(DirectMLManager.error_msg)
