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
            if not os.path.exists(cfg_path):
                return

            cp = configparser.ConfigParser()
            cp.read(cfg_path, encoding='utf-8')
            
            if "Main" in cp and cp.getboolean("Main", "use_directml", fallback=False):
                target_dir = get_directml_dir()
                if not os.path.exists(target_dir):
                    DirectMLManager.is_ready = False
                    DirectMLManager.error_msg = "Библиотека не установлена."
                    return

                # Проверяем, был ли уже успешный тест
                is_tested_ok = cp.getboolean("Main", "directml_tested_ok", fallback=False)
                
                if not is_tested_ok:
                    logging.info("DirectML: Выполнение первичного тестирования совместимости...")
                    success, msg = DirectMLManager.run_test_sync(target_dir)
                    if success:
                        # Сохраняем успешный статус, чтобы не тестировать каждый раз
                        cp["Main"]["directml_tested_ok"] = "true"
                        with open(cfg_path, "w", encoding="utf-8") as f:
                            cp.write(f)
                        DirectMLManager.is_ready = True
                        sys.path.insert(0, target_dir)
                        import onnxruntime
                    else:
                        DirectMLManager.is_ready = False
                        DirectMLManager.error_msg = msg
                else:
                    # Уже протестировано ранее, просто загружаем
                    DirectMLManager.is_ready = True
                    sys.path.insert(0, target_dir)
                    import onnxruntime
        except Exception as e:
            DirectMLManager.is_ready = False
            DirectMLManager.error_msg = f"Ошибка инициализации DirectML: {e}"
            print(DirectMLManager.error_msg)

    @staticmethod
    def run_test_sync(target_dir):
        """Синхронно тестирует библиотеку через скрытый subprocess"""
        try:
            test_script = os.path.join(target_dir, "test_dml.py")
            with open(test_script, "w", encoding="utf-8") as f:
                f.write(f"import sys\nsys.path.insert(0, r'{target_dir}')\nimport onnxruntime as ort\n"
                        "if 'DmlExecutionProvider' in ort.get_available_providers():\n    sys.exit(0)\n"
                        "else:\n    sys.exit(1)\n")
            
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            test_cmd = [sys.executable, test_script]
            test_process = subprocess.run(test_cmd, capture_output=True, text=True, creationflags=creationflags)
            
            if test_process.returncode == 0:
                return True, "DirectML поддерживается!"
            else:
                return False, "Библиотека установлена, но видеокарта не поддерживает DirectML или драйвер устарел."
        except Exception as e:
            return False, str(e)
