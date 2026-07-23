"""
Модуль для загрузки FFmpeg при отсутствии библиотеки.
Поддерживает работу в exe режиме (PyInstaller).
"""

import os
import sys
import zipfile
import logging
import shutil
try:
    import requests
except ImportError:
    requests = None
    logging.error("Библиотека requests не установлена. Загрузка FFmpeg невозможна.")
from PyQt6.QtCore import QThread, pyqtSignal
from logic_paths import get_ffmpeg_bin_dir, get_ffmpeg_exe, get_ffprobe_exe
from config import AppContext


class FFmpegDownloaderWorker(QThread):
    """
    Воркер для загрузки и распаковки FFmpeg.
    Работает в фоновом потоке, чтобы не блокировать UI.
    """
    progress_updated = pyqtSignal(int)  # Процент загрузки (0-100)
    status_message = pyqtSignal(str)    # Сообщение о статусе
    finished = pyqtSignal(bool, str)    # Успех, сообщение об ошибке (если есть)
    
    # Список зеркал для гарантированной загрузки FFmpeg для Windows
    FFMPEG_DOWNLOAD_URLS = [
        "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
        "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
        "https://github.com/GyanD/codexffmpeg/releases/download/6.0/ffmpeg-6.0-essentials_build.zip"
    ]
    
    def __init__(self):
        super().__init__()
        self.is_running = True
        self.download_path = None
        
    def stop(self):
        """Остановка загрузки"""
        self.is_running = False
        logging.info("Загрузка FFmpeg остановлена пользователем")
        
    def run(self):
        """Основной метод загрузки"""
        try:
            bin_dir = get_ffmpeg_bin_dir()
            os.makedirs(bin_dir, exist_ok=True)
            
            # Временный файл для загрузки
            self.download_path = os.path.join(bin_dir, "ffmpeg_temp.zip")
            
            # Удаляем старый временный файл, если есть
            if os.path.exists(self.download_path):
                try:
                    os.remove(self.download_path)
                except:
                    pass
            
            self.status_message.emit(AppContext.tr("ffmpeg_start_download"))
            
            # Загрузка файла через зеркала
            if not self._download_file():
                if self.is_running:
                    self.finished.emit(False, AppContext.tr("ffmpeg_err_download"))
                return
            
            if not self.is_running:
                self._cleanup()
                return
            
            self.status_message.emit(AppContext.tr("ffmpeg_extracting"))
            logging.info("Начало распаковки архива FFmpeg")
            
            # Распаковка
            if not self._extract_archive(bin_dir):
                if self.is_running:
                    self.finished.emit(False, AppContext.tr("ffmpeg_err_extract"))
                return
            
            if not self.is_running:
                self._cleanup()
                return
            
            # Очистка временных файлов
            self._cleanup()
            
            # Проверка результата
            ffmpeg_path = get_ffmpeg_exe()
            ffprobe_path = get_ffprobe_exe()
            
            if os.path.exists(ffmpeg_path) and os.path.exists(ffprobe_path):
                self.status_message.emit(AppContext.tr("ffmpeg_success_installed"))
                logging.info(f"FFmpeg успешно установлен: {ffmpeg_path}")
                self.finished.emit(True, "")
            else:
                self.finished.emit(False, AppContext.tr("ffmpeg_err_not_found_after"))
                
        except Exception as e:
            logging.error(f"Критическая ошибка при загрузке FFmpeg: {e}", exc_info=True)
            self.finished.emit(False, AppContext.tr("ffmpeg_err_format").format(e))
    
    def _download_file(self):
        """Загрузка zip-архива с FFmpeg с перебором зеркал и браузерным User-Agent"""
        if requests is None:
            logging.error("Библиотека requests не установлена")
            return False
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }

        for url in self.FFMPEG_DOWNLOAD_URLS:
            if not self.is_running:
                return False
            try:
                logging.info(f"Попытка загрузки FFmpeg из {url}...")
                response = requests.get(url, headers=headers, stream=True, timeout=30)
                response.raise_for_status()
                
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                block_size = 8192  # 8 KB
                
                with open(self.download_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=block_size):
                        if not self.is_running:
                            return False
                        
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            if total_size > 0:
                                percent = int((downloaded / total_size) * 100)
                                self.progress_updated.emit(percent)
                
                self.progress_updated.emit(100)
                logging.info(f"FFmpeg успешно скачан из {url}")
                return True
                
            except Exception as e:
                logging.warning(f"Ошибка загрузки FFmpeg с зеркала {url}: {e}. Пробуем следующее зеркало...")
                if os.path.exists(self.download_path):
                    try:
                        os.remove(self.download_path)
                    except:
                        pass
        
        logging.error("Все зеркала FFmpeg оказались недоступны.")
        return False
    
    def _extract_archive(self, target_dir):
        """Распаковка архива и поиск ffmpeg.exe и ffprobe.exe"""
        try:
            with zipfile.ZipFile(self.download_path, 'r') as zip_ref:
                # Получаем список файлов
                file_list = zip_ref.namelist()
                
                # Ищем ffmpeg.exe и ffprobe.exe в архиве
                ffmpeg_entry = None
                ffprobe_entry = None
                
                for entry in file_list:
                    name = os.path.basename(entry).lower()
                    if name == 'ffmpeg.exe' and not ffmpeg_entry:
                        ffmpeg_entry = entry
                    elif name == 'ffprobe.exe' and not ffprobe_entry:
                        ffprobe_entry = entry
                
                if not ffmpeg_entry or not ffprobe_entry:
                    logging.error("ffmpeg.exe или ffprobe.exe не найдены в архиве")
                    return False
                
                # Извлекаем только нужные файлы
                logging.info(f"Извлечение {ffmpeg_entry} -> {os.path.join(target_dir, 'ffmpeg.exe')}")
                
                # Извлекаем во временную директорию, чтобы сохранить структуру папок из архива
                temp_extract_dir = os.path.join(target_dir, "temp_extract")
                zip_ref.extract(ffmpeg_entry, temp_extract_dir)
                
                # Находим извлеченный файл
                extracted_ffmpeg = os.path.join(temp_extract_dir, ffmpeg_entry)
                if not os.path.exists(extracted_ffmpeg):
                    # Попробуем найти в корне temp_extract
                    for root, dirs, files in os.walk(temp_extract_dir):
                        if "ffmpeg.exe" in files:
                            extracted_ffmpeg = os.path.join(root, "ffmpeg.exe")
                            break
                
                # Перемещаем в корень bin директории
                target_ffmpeg = os.path.join(target_dir, 'ffmpeg.exe')
                if os.path.exists(target_ffmpeg):
                    os.remove(target_ffmpeg)
                if os.path.exists(extracted_ffmpeg):
                    os.rename(extracted_ffmpeg, target_ffmpeg)
                
                logging.info(f"Извлечение {ffprobe_entry} -> {os.path.join(target_dir, 'ffprobe.exe')}")
                zip_ref.extract(ffprobe_entry, temp_extract_dir)
                
                # Находим извлеченный файл
                extracted_ffprobe = os.path.join(temp_extract_dir, ffprobe_entry)
                if not os.path.exists(extracted_ffprobe):
                    # Попробуем найти в корне temp_extract
                    for root, dirs, files in os.walk(temp_extract_dir):
                        if "ffprobe.exe" in files:
                            extracted_ffprobe = os.path.join(root, "ffprobe.exe")
                            break
                
                # Перемещаем в корень bin директории
                target_ffprobe = os.path.join(target_dir, 'ffprobe.exe')
                if os.path.exists(target_ffprobe):
                    os.remove(target_ffprobe)
                if os.path.exists(extracted_ffprobe):
                    os.rename(extracted_ffprobe, target_ffprobe)
                
                # Удаляем временную директорию
                try:
                    import shutil
                    if os.path.exists(temp_extract_dir):
                        shutil.rmtree(temp_extract_dir)
                except Exception as e:
                    logging.warning(f"Не удалось удалить временную директорию: {e}")
                
                return True
                
        except zipfile.BadZipFile:
            logging.error("Архив поврежден или не является ZIP файлом")
            return False
        except Exception as e:
            logging.error(f"Ошибка распаковки архива: {e}")
            return False
    
    def _cleanup(self):
        """Удаление временных файлов"""
        if self.download_path and os.path.exists(self.download_path):
            try:
                os.remove(self.download_path)
                logging.debug("Временный файл загрузки удален")
            except Exception as e:
                logging.warning(f"Не удалось удалить временный файл: {e}")


def check_ffmpeg_available():
    """
    Проверяет наличие FFmpeg и FFprobe.
    Возвращает (bool, str) - (доступен, путь к ffmpeg)
    """
    ffmpeg_path = get_ffmpeg_exe()
    ffprobe_path = get_ffprobe_exe()
    
    if os.path.exists(ffmpeg_path) and os.path.exists(ffprobe_path):
        # Дополнительная проверка - пытаемся запустить
        try:
            import subprocess
            result = subprocess.run(
                [ffmpeg_path, '-version'],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            if result.returncode == 0:
                logging.debug(f"FFmpeg найден и работает: {ffmpeg_path}")
                return True, ffmpeg_path
        except Exception as e:
            logging.warning(f"FFmpeg найден, но не запускается: {e}")
    
    return False, None

