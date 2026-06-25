
import os
import re
import time
import shutil
import logging
from PyQt6.QtCore import QThread, pyqtSignal
from utils_io import smart_move_file, ensure_long_path

class ScanThread(QThread):
    finished_scan = pyqtSignal(list)

    def __init__(self, folder, recursive, extensions=None, filter_mode="include"):
        super().__init__()
        self.folder = folder
        self.recursive = recursive
        self.extensions = extensions if extensions is not None else []
        self.filter_mode = filter_mode
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        long_folder = ensure_long_path(self.folder)
        logging.info(f"Поток сканирования запущен для папки: {long_folder}")
        result = []
        if not os.path.exists(long_folder):
            logging.error(f"Папка для сканирования не существует: {long_folder}")
            self.finished_scan.emit(result)
            return

        try:
            raw_paths = []
            if self.recursive:
                logging.debug("Рекурсивное сканирование.")
                for root, _, files in os.walk(long_folder):
                    if self._is_cancelled:
                        break
                    for f in files:
                        if self._is_cancelled:
                            break
                        if self.check_ext(f):
                            full_path = os.path.join(root, f)
                            raw_paths.append(full_path)
            else:
                logging.debug("Не рекурсивное сканирование.")
                files = os.listdir(long_folder)
                for f in files:
                    if self._is_cancelled:
                        break
                    full_path = os.path.join(long_folder, f)
                    if os.path.isfile(full_path):
                        if self.check_ext(f):
                            raw_paths.append(full_path)

            for fp in raw_paths:
                if self._is_cancelled:
                    break
                try:
                    stat = os.stat(fp)
                    size = stat.st_size
                    mtime = stat.st_mtime
                    ctime = stat.st_ctime
                except Exception:
                    size = 0
                    mtime = 0.0
                    ctime = 0.0

                rel = os.path.relpath(fp, long_folder)
                result.append({
                    'rel_path': rel,
                    'size': size,
                    'mtime': mtime,
                    'ctime': ctime
                })
        except Exception as e:
            logging.error(f"Ошибка в потоке сканирования: {e}", exc_info=True)

        logging.info(f"Поток сканирования завершен. Найдено файлов: {len(result)}")
        self.finished_scan.emit(result)

    def check_ext(self, filename):
        if not self.extensions: return True
        ext = os.path.splitext(filename)[1].lower()
        if self.filter_mode == "include":
            return ext in self.extensions
        else: # exclude
            return ext not in self.extensions

def is_file_locked(filepath: str) -> bool:
    """
    Мягко проверяет, заблокирован ли файл другим процессом.
    """
    long_fp = ensure_long_path(filepath)
    if not os.path.exists(long_fp):
        return False
    try:
        with open(long_fp, 'ab'):
            pass
        return False
    except (IOError, PermissionError):
        return True

class MoveThread(QThread):
    progress_update = pyqtSignal(int, int, str)
    finished_move = pyqtSignal(bool, str, list, list)

    def __init__(self, src, dst=None):
        super().__init__()
        if isinstance(src, list):
            self.pairs = src
        else:
            self.pairs = [(src, dst)]

    def run(self):
        logging.info(f"Поток перемещения запущен. Количество файлов: {len(self.pairs)}")
        succeeded = []
        failed = []
        
        # Даем фоновым потокам декодирования WMF время закрыть файлы перед перемещением
        time.sleep(0.25)
        
        to_retry = []
        total = len(self.pairs)
        
        # 1. Первый проход
        for idx, (src, dst) in enumerate(self.pairs):
            filename = os.path.basename(src)
            self.progress_update.emit(idx + 1, total, filename)
            
            if is_file_locked(src):
                logging.warning(f"File detected as locked on first pass, postponing: {src}")
                to_retry.append((idx, src, dst, "Файл заблокирован внешним процессом"))
                continue
                
            success = smart_move_file(src, dst)
            if success:
                succeeded.append((src, dst))
            else:
                to_retry.append((idx, src, dst, "Ошибка файлового ввода-вывода"))
                
        # 2. Пауза и второй проход (если есть неудавшиеся файлы)
        if to_retry:
            logging.info(f"Начало ожидания освобождения файлов ({len(to_retry)} шт.) перед вторым проходом...")
            time.sleep(0.5)
            
            still_failed = []
            for item_idx, (idx, src, dst, initial_err) in enumerate(to_retry):
                filename = os.path.basename(src)
                self.progress_update.emit(idx + 1, total, f"[Повтор] {filename}")
                
                success = smart_move_file(src, dst)
                if success:
                    succeeded.append((src, dst))
                else:
                    still_failed.append((src, dst, initial_err))
            failed = still_failed

        # 3. Завершение
        if not failed:
            logging.info("Перемещение всех файлов успешно завершено.")
            self.finished_move.emit(True, "", succeeded, [])
        else:
            err_msg = f"Не удалось переместить {len(failed)} из {total} файлов."
            logging.warning(err_msg)
            self.finished_move.emit(False, err_msg, succeeded, failed)
