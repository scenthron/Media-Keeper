
import os
import shutil
import logging
import time


def ensure_long_path(path):
    r"""
    Ensure the path handles Windows long paths (prefix \\?\).
    """
    if not path:
        return path
    if os.name == 'nt' and not path.startswith('\\\\?\\'):
        return '\\\\?\\' + os.path.abspath(path)
    return path

def strip_long_path_prefix(path):
    if path and path.startswith('\\\\?\\'):
        return path[4:]
    return path

def smart_move_file(src, dst, progress_callback=None, stop_event=None):
    """
    Moves a file intelligently:
    1. Tries atomic os.rename() first (instant move within same filesystem).
    2. Falls back to chunked copy-delete if filesystems differ or rename fails.
    Supports a transparent Retry mechanism if the file is temporarily locked
    by a background media player or OS preview engine.
    
    Args:
        src (str): Source path.
        dst (str): Destination path.
        progress_callback (func): Function accepting (bytes_moved, total_bytes).
        stop_event (threading.Event): Event to check for cancellation.
        
    Returns:
        bool: True if successful, False if cancelled or failed.
    """
    if os.name == 'nt':
        src_abs = os.path.normpath(os.path.abspath(src))
        dst_abs = os.path.normpath(os.path.abspath(dst))
        
        # Используем префикс длинных путей только при реальной необходимости (длина пути >= 240 символов)
        if len(src_abs) >= 240 and not src_abs.startswith('\\\\?\\'):
            src = '\\\\?\\' + src_abs
        else:
            src = src_abs
            
        if len(dst_abs) >= 240 and not dst_abs.startswith('\\\\?\\'):
            dst = '\\\\?\\' + dst_abs
        else:
            dst = dst_abs

    CHUNK_SIZE = 1024 * 1024 # 1 MB
    MAX_RETRIES = 30
    RETRY_DELAY = 0.15 # 150 ms
    
    for attempt in range(MAX_RETRIES):
        if stop_event and stop_event.is_set():
            return False
            
        try:
            file_size = os.path.getsize(src)
            dst_dir = os.path.dirname(dst)
            
            # Ensure dir exists
            os.makedirs(dst_dir, exist_ok=True)
            
            # --- STRATEGY 1: ATOMIC RENAME (INSTANT) ---
            try:
                src_dev = os.stat(src).st_dev
                dst_dev = os.stat(dst_dir).st_dev
                
                if src_dev == dst_dev:
                    if stop_event and stop_event.is_set(): 
                        return False
                    
                    logging.debug(f"Same filesystem detected ({src_dev}). Attempting atomic rename for {src}")
                    os.rename(src, dst)
                    
                    # Report 100% progress immediately for UI stats consistency
                    if progress_callback:
                        progress_callback(file_size, file_size)
                    
                    logging.info("Atomic rename successful.")
                    return True
                    
            except OSError as e:
                # If file is locked, raise error to trigger Retry loop
                if isinstance(e, PermissionError) or (hasattr(e, 'winerror') and e.winerror == 32):
                    raise e
                # errno.EXDEV (18) = Cross-device link. This is expected if drives differ.
                logging.debug(f"Atomic rename not possible or failed (will try copy): {e}")
            except Exception as e:
                logging.warning(f"Unexpected error during atomic check: {e}")

            # --- STRATEGY 2: CHUNKED COPY (SLOW, SAFE, CANCELLABLE) ---
            logging.info("Starting chunked copy-delete sequence.")
            bytes_moved = 0
            
            # If file is locked, open() will raise PermissionError, triggering the Retry loop
            with open(src, 'rb') as fsrc, open(dst, 'wb') as fdst:
                while True:
                    if stop_event and stop_event.is_set():
                        logging.info("File move cancelled by user.")
                        break 
                    
                    chunk = fsrc.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    
                    fdst.write(chunk)
                    bytes_moved += len(chunk)
                    
                    if progress_callback:
                        progress_callback(bytes_moved, file_size)
            
            # Check cancellation again (outside loop)
            if stop_event and stop_event.is_set():
                if os.path.exists(dst):
                    try: os.remove(dst)
                    except: pass
                return False
                
            # Copy metadata (timestamp, permissions)
            try:
                shutil.copystat(src, dst)
            except Exception as e:
                logging.warning(f"Failed to copy metadata: {e}")
            
            # Verify sizes match before deleting source
            if os.path.getsize(dst) == file_size:
                os.remove(src)
                return True
            else:
                logging.error("Size mismatch after copy. Source not deleted.")
                return False

        except (PermissionError, OSError) as e:
            # Check if this is a file lock error (WinError 32 or PermissionError)
            is_locked = isinstance(e, PermissionError) or (hasattr(e, 'winerror') and e.winerror == 32)
            if is_locked and attempt < MAX_RETRIES - 1:
                logging.warning(f"File locked: {src}. Retrying in {RETRY_DELAY}s (Attempt {attempt+1}/{MAX_RETRIES}). Error: {e}")
                # Remove partially copied destination file if it exists
                if os.path.exists(dst):
                    try: os.remove(dst)
                    except: pass
                time.sleep(RETRY_DELAY)
                continue
                
            # Final failure on last attempt or other fatal IO error
            logging.error(f"Smart Move Final Failure ({src} -> {dst}): {e}")
            if os.path.exists(dst):
                try: os.remove(dst)
                except: pass
            return False

    return False

def safe_cv2_imread(path: str):
    """
    Безопасное чтение изображения через OpenCV с поддержкой:
    1. Русских символов (кириллицы) в пути (через numpy.fromfile).
    2. Длинных путей Windows (через нормализацию и префикс \\?\).
    """
    import cv2
    import numpy as np
    
    path = ensure_long_path(os.path.normpath(path))
    try:
        # Чтение через байтовый поток numpy для обхода ограничений cv2.imread
        with open(path, "rb") as stream:
            bytes_array = bytearray(stream.read())
        numpyarray = np.asarray(bytes_array, dtype=np.uint8)
        img = cv2.imdecode(numpyarray, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        logging.error(f"Ошибка безопасного чтения изображения {path}: {e}")
        return None

def safe_cv2_imwrite(path: str, img) -> bool:
    """
    Безопасная запись изображения через OpenCV с поддержкой кириллицы и длинных путей.
    """
    import cv2
    import numpy as np
    
    path = ensure_long_path(os.path.normpath(path))
    try:
        ext = os.path.splitext(path)[1].lower() or '.jpg'
        success, encoded_img = cv2.imencode(ext, img)
        if success:
            with open(path, "wb") as f:
                encoded_img.tofile(f)
            return True
        return False
    except Exception as e:
        logging.error(f"Ошибка безопасной записи изображения {path}: {e}")
        return False
