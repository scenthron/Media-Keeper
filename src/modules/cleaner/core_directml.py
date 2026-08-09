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
                dml_ok = os.path.exists(ort_dir)
                if not dml_ok:
                    DirectMLManager.is_ready = False
                    DirectMLManager.error_msg = "Библиотека не установлена."
                    return

                # Добавляем путь и импортируем, используя кастомный загрузчик
                # чтобы обойти FrozenImporter от PyInstaller, который иначе загрузит CPU-версию
                import importlib.machinery
                class OverrideImporter:
                    def find_spec(self, fullname, path, target=None):
                        if fullname.startswith('onnxruntime'):
                            return importlib.machinery.PathFinder.find_spec(fullname, [target_dir] + (path or []))
                        return None
                
                override_importer = OverrideImporter()
                sys.meta_path.insert(0, override_importer)
                
                try:
                    # В Python 3.8+ на Windows необходимо явно добавлять пути к DLL
                    if hasattr(os, "add_dll_directory"):
                        try:
                            os.add_dll_directory(os.path.join(target_dir, "onnxruntime", "capi"))
                        except Exception:
                            pass
                    else:
                        os.environ["PATH"] = os.path.join(target_dir, "onnxruntime", "capi") + os.pathsep + os.environ.get("PATH", "")

                    import onnxruntime
                    # Проверяем, действительно ли загрузился DirectML провайдер
                    if 'DmlExecutionProvider' in onnxruntime.get_available_providers():
                        DirectMLManager.is_ready = True
                    else:
                        DirectMLManager.is_ready = False
                        DirectMLManager.error_msg = "Провайдер DML не найден. Возможно, видеокарта не поддерживает DirectML."
                        
                    # Если инициализация провалилась, откатываем импортер, чтобы не сломать остальную программу
                    if not DirectMLManager.is_ready:
                        if override_importer in sys.meta_path:
                            sys.meta_path.remove(override_importer)
                        for k in list(sys.modules.keys()):
                            if k == 'onnxruntime' or k.startswith('onnxruntime.'):
                                del sys.modules[k]
                            
                except Exception as e:
                    if override_importer in sys.meta_path:
                        sys.meta_path.remove(override_importer)
                    for k in list(sys.modules.keys()):
                        if k == 'onnxruntime' or k.startswith('onnxruntime.'):
                            del sys.modules[k]
                    DirectMLManager.is_ready = False
                    DirectMLManager.error_msg = f"Ошибка загрузки библиотеки DirectML: {e}"
        except Exception as e:
            DirectMLManager.is_ready = False
            DirectMLManager.error_msg = f"Ошибка инициализации DirectML: {e}"
            print(DirectMLManager.error_msg)
