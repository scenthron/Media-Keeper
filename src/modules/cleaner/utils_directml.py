import os
import sys
import subprocess
import logging
import shutil
from PyQt6.QtCore import QThread, pyqtSignal
from logic_paths import get_app_data_dir

def get_directml_dir():
    return os.path.join(get_app_data_dir(), "models", "onnx_directml")

class DirectMLInstallerThread(QThread):
    progress_update = pyqtSignal(str)
    finished_install = pyqtSignal(bool, str)

    def run(self):
        target_dir = get_directml_dir()
        try:
            if not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)
            
            self.progress_update.emit("Скачивание и установка onnxruntime-directml... Это может занять пару минут.")
            
            # Using subprocess to run pip install
            cmd = [sys.executable, "-m", "pip", "install", "onnxruntime-directml", "--target", target_dir, "--upgrade"]
            
            # Use CREATE_NO_WINDOW to hide the console window on Windows
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=creationflags)
            
            for line in process.stdout:
                line = line.strip()
                if line:
                    logging.info(f"[DirectML Install] {line}")
                    self.progress_update.emit(line)
                    
            process.wait()
            
            if process.returncode == 0:
                self.progress_update.emit("Установка завершена. Выполнение теста совместимости...")
                
                # Create test script
                test_script = os.path.join(target_dir, "test_dml.py")
                with open(test_script, "w", encoding="utf-8") as f:
                    f.write(f"""
import sys
sys.path.insert(0, r'{target_dir}')
import onnxruntime as ort
if 'DmlExecutionProvider' in ort.get_available_providers():
    sys.exit(0)
else:
    sys.exit(1)
""")
                
                # Run test
                test_cmd = [sys.executable, test_script]
                test_process = subprocess.run(test_cmd, capture_output=True, text=True, creationflags=creationflags)
                
                if test_process.returncode == 0:
                    self.finished_install.emit(True, "DirectML успешно установлен и прошел тест!")
                else:
                    self.finished_install.emit(False, "Библиотека установлена, но видеокарта не поддерживает DirectML или драйвер устарел.")
                    # Cleanup if test failed
                    try:
                        shutil.rmtree(target_dir)
                    except:
                        pass
            else:
                self.finished_install.emit(False, "Ошибка при скачивании библиотеки. Проверьте интернет-соединение.")
                
        except Exception as e:
            logging.error(f"Error installing DirectML: {e}", exc_info=True)
            self.finished_install.emit(False, f"Произошла непредвиденная ошибка: {e}")
