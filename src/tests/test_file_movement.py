import os
import sys
import tempfile
import shutil
import time
import ctypes
import threading
import pytest
from PyQt6.QtWidgets import QApplication

# Добавляем путь к src, чтобы импортировать модули напрямую
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Инициализируем QApplication
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

from utils_io import smart_move_file, ensure_long_path
from modules.sorter.workers import MoveThread, is_file_locked, ScanThread

# Win32 CreateFileW constants
GENERIC_WRITE = 0x40000000
GENERIC_READ = 0x80000000
FILE_SHARE_NONE = 0
OPEN_EXISTING = 3

def lock_file_win32(filepath):
    if os.name != 'nt':
        # На Unix-подобных системах возвращаем обычный дескриптор файла как плейсхолдер
        return open(filepath, 'ab')
    
    # Exclusively lock file on Windows
    h = ctypes.windll.kernel32.CreateFileW(
        filepath,
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_NONE,
        None,
        OPEN_EXISTING,
        0,
        None
    )
    if h == -1 or h == 0:
        raise OSError(f"Could not exclusively lock file: {filepath}")
    return h

def unlock_file_win32(h):
    if os.name != 'nt':
        h.close()
        return
    ctypes.windll.kernel32.CloseHandle(h)

def test_is_file_locked():
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "test_lock.txt")
        with open(filepath, "w") as f:
            f.write("test data")
            
        assert is_file_locked(filepath) is False
        
        # Lock it
        h = lock_file_win32(filepath)
        try:
            assert is_file_locked(filepath) is True
        finally:
            unlock_file_win32(h)
            
        assert is_file_locked(filepath) is False

def test_smart_move_file_basic():
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "src.txt")
        dst = os.path.join(tmpdir, "dst.txt")
        
        with open(src, "w") as f:
            f.write("hello world")
            
        # Move
        success = smart_move_file(src, dst)
        assert success is True
        assert os.path.exists(dst)
        assert not os.path.exists(src)
        with open(dst, "r") as f:
            assert f.read() == "hello world"

def test_smart_move_file_locked_retry_and_success():
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "src.txt")
        dst = os.path.join(tmpdir, "dst.txt")
        
        with open(src, "w") as f:
            f.write("hello retry")
            
        # Lock the file
        h = lock_file_win32(src)
        
        # Start a thread to unlock the file after 200ms
        def unlock_later():
            time.sleep(0.2)
            unlock_file_win32(h)
            
        t = threading.Thread(target=unlock_later)
        t.start()
        
        # Move (should fail first attempt, then retry and succeed)
        success = smart_move_file(src, dst)
        assert success is True
        assert os.path.exists(dst)
        assert not os.path.exists(src)
        with open(dst, "r") as f:
            assert f.read() == "hello retry"
            
        t.join()

def test_move_thread_two_pass():
    with tempfile.TemporaryDirectory() as tmpdir:
        src1 = os.path.join(tmpdir, "src1.txt")
        dst1 = os.path.join(tmpdir, "dst1.txt")
        src2 = os.path.join(tmpdir, "src2.txt")
        dst2 = os.path.join(tmpdir, "dst2.txt")
        
        with open(src1, "w") as f:
            f.write("data 1")
        with open(src2, "w") as f:
            f.write("data 2")
            
        # Lock file 1
        h1 = lock_file_win32(src1)
        
        # Instantiate MoveThread
        pairs = [(src1, dst1), (src2, dst2)]
        thread = MoveThread(pairs)
        
        progress_events = []
        finished_events = []
        
        from PyQt6.QtCore import Qt, QCoreApplication
        
        thread.progress_update.connect(
            lambda cur, tot, name: progress_events.append((cur, tot, name)),
            Qt.ConnectionType.DirectConnection
        )
        thread.finished_move.connect(
            lambda success, err, succ, fail: finished_events.append((success, err, succ, fail)),
            Qt.ConnectionType.DirectConnection
        )
        
        # Start the thread
        thread.start()
        
        # Wait for first pass to detect the lock (takes ~100ms)
        # Unlock file 1 after 200ms so the second pass (after 500ms sleep) will succeed
        def unlock_later():
            time.sleep(0.2)
            unlock_file_win32(h1)
            
        t = threading.Thread(target=unlock_later)
        t.start()
        
        # Wait for thread to finish using event loop
        start_t = time.time()
        while thread.isRunning() and (time.time() - start_t) < 5.0:
            QCoreApplication.processEvents()
            time.sleep(0.02)
            
        thread.wait(1000)
        QCoreApplication.processEvents()
        t.join()
        
        # Assertions
        assert len(finished_events) == 1
        success, err, succ, fail = finished_events[0]
        
        # Both should be successfully moved in the end
        assert success is True
        assert len(succ) == 2
        assert len(fail) == 0
        assert os.path.exists(dst1)
        assert os.path.exists(dst2)
        assert not os.path.exists(src1)
        assert not os.path.exists(src2)
        
        # Verify progress signals were sent
        assert len(progress_events) >= 2


def test_dircache_invalidation() -> None:
    from logic_cache import DirCache
    from PyQt6.QtCore import QCoreApplication
    
    with tempfile.TemporaryDirectory() as tmpdir:
        subfolder: str = os.path.join(tmpdir, "FolderA")
        os.makedirs(subfolder, exist_ok=True)
        
        # Создаем файлы
        fp: str = os.path.join(subfolder, "photo.jpg")
        with open(fp, "w") as f:
            f.write("a")
            
        cache: DirCache = DirCache.inst()
        norm_sub: str = os.path.normpath(subfolder)
        norm_parent: str = os.path.normpath(tmpdir)
        
        # Инициализируем кэш для обеих папок
        cache.refresh_path(norm_sub)
        cache.refresh_path(norm_parent)
        
        # Ждем завершения сканирования
        start_t: float = time.time()
        while (time.time() - start_t) < 3.0:
            QCoreApplication.processEvents()
            c_sub, _ = cache.get_data(norm_sub)
            c_parent, _ = cache.get_data(norm_parent)
            if c_sub > 0 and c_parent > 0:
                break
            time.sleep(0.02)
            
        assert norm_sub in cache._cache
        assert norm_parent in cache._cache
        
        # Инвалидируем подпапку с родителями
        cache.invalidate_with_parents(norm_sub)
        
        # Кэш для подпапки и её родителя должен быть стёрт
        assert norm_sub not in cache._cache
        assert norm_parent not in cache._cache


def test_long_path_support():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Создаем очень длинное имя файла, чтобы суммарно превысить 260 символов
        long_dir_name = "dir_" + "a" * 150
        long_file_name = "file_" + "b" * 100 + ".txt"
        
        dir_path = os.path.join(tmpdir, long_dir_name)
        file_path = os.path.join(dir_path, long_file_name)
        
        # На Windows обернем пути через ensure_long_path
        long_dir_path = ensure_long_path(dir_path)
        long_file_path = ensure_long_path(file_path)
        
        # Убедимся, что общая длина пути превышает 260 символов
        assert len(os.path.abspath(file_path)) > 260
        
        os.makedirs(long_dir_path, exist_ok=True)
        with open(long_file_path, "w") as f:
            f.write("long path data")
            
        # Проверяем os.path.exists с ensure_long_path
        assert os.path.exists(long_file_path) is True
        
        # Проверяем is_file_locked
        assert is_file_locked(file_path) is False
        
        # Проверяем сканирование с помощью ScanThread
        scan_thread = ScanThread(tmpdir, recursive=True)
        scan_thread.run()
        
        found_files = scan_thread.finished_scan.emit
        # Просканируем результаты напрямую
        results = []
        scan_thread.finished_scan.connect(results.extend)
        scan_thread.run()
        
        assert len(results) == 1
        # Относительный путь должен быть найден
        assert results[0]['rel_path'].endswith(long_file_name)
        assert results[0]['size'] == len("long path data")
        
        # Проверяем smart_move_file
        dest_file_path = os.path.join(tmpdir, "moved_" + long_file_name)
        long_dest_file_path = ensure_long_path(dest_file_path)
        
        success = smart_move_file(file_path, dest_file_path)
        assert success is True
        assert os.path.exists(long_dest_file_path) is True
        assert not os.path.exists(long_file_path)

