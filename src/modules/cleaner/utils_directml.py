import os
import sys
import subprocess
import logging
import shutil
from PyQt6.QtCore import QThread, pyqtSignal
from modules.cleaner.core_directml import DirectMLManager, get_directml_dir

class DirectMLInstallerThread(QThread):
    progress_update = pyqtSignal(str)
    finished_install = pyqtSignal(bool, str)

    def run(self):
        target_dir = get_directml_dir()
        try:
            if not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)
            
            self.progress_update.emit("Скачивание библиотеки от Microsoft... Это может занять пару минут.")
            
            cmd = [sys.executable, "-m", "pip", "install", "onnxruntime-directml", "--target", target_dir, "--upgrade"]
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=creationflags)
            
            for line in process.stdout:
                line = line.strip()
                if line:
                    logging.info(f"[DirectML Install] {line}")
                    self.progress_update.emit(line)
                    
            process.wait()
            
            if process.returncode == 0:
                self.progress_update.emit("Скачивание завершено. Запуск теста видеокарты...")
                success, msg = DirectMLManager.run_test_sync(target_dir)
                if success:
                    self.finished_install.emit(True, msg)
                else:
                    self.finished_install.emit(False, msg)
                    # Очищаем нерабочую библиотеку
                    try:
                        shutil.rmtree(target_dir)
                    except:
                        pass
            else:
                self.finished_install.emit(False, "Ошибка при скачивании библиотеки. Проверьте интернет-соединение.")
                
        except Exception as e:
            logging.error(f"Error installing DirectML: {e}", exc_info=True)
            self.finished_install.emit(False, f"Произошла непредвиденная ошибка: {e}")
