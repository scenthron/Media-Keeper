
import os
from utils_extensions import VIDEO_EXTS, AUDIO_EXTS, IMAGE_EXTS, get_filtered_exts
import hashlib
from utils_common import is_subpath
from config import AppContext
import time
import logging
from typing import Any
from PyQt6.QtCore import QThread, pyqtSignal
from .db_cache import CleanerDB

STAGE_SCANNING = 1
STAGE_ANALYSIS = 2
LARGE_FILE_THRESHOLD = 30 * 1024 * 1024 

EXT_GROUPS = {
    "Images": {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.raw', '.heic', '.heif', '.svg', '.ico', '.tga', '.psd', '.apng'},
    "Video": VIDEO_EXTS,
    "Audio": {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.opus', '.aiff', '.amr', '.mid', '.midi'},
    "Documents": {'.pdf', '.doc', '.docx', '.txt', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.rtf'},
    "Archives": {'.zip', '.rar', '.7z', '.tar', '.gz', '.iso'},
    "Code": {'.html', '.mhtml', '.css', '.js', '.py', '.json', '.xml', '.cpp', '.h', '.java', '.php'},
    "Other": set() 
}

MEDIA_EXTS = EXT_GROUPS["Images"].union(EXT_GROUPS["Video"]).union(EXT_GROUPS["Audio"])

def ensure_win_path(path):
    if os.name == 'nt' and len(path) > 240 and not path.startswith('\\\\?\\'):
        return '\\\\?\\' + os.path.abspath(path)
    return path

class ExtensionScannerWorker(QThread):
    finished = pyqtSignal(dict) 
    def __init__(self, folders):
        super().__init__()
        self.folders = folders
    def run(self):
        logging.info("AiScanWorker запущен")
        if not getattr(self, "is_cluster", False):
            if not getattr(self, "text_query", None):
                if not self.classifier.load_active_references():
                    logging.warning("Нет активных эталонов для ИИ-поиска")
                    self.finished.emit({})
                    return
                
        # 1. Сканируем файлы и строим кэш (СИНИЙ ЭТАП)
        valid_files = []
        scanned_files = 0
        scanned_bytes = 0
        
        self.progress.emit(STAGE_SCANNING, 0.0, "Поиск изображений...", 0, 0, 0, 0, 0, 0)
        
        for folder in self.folders:
            if not self.is_running: break
            norm_folder = os.path.normpath(folder)
            if not os.path.exists(norm_folder): continue
            
            try:
                for root, dirs, files_list in os.walk(norm_folder):
                    if not self.is_running: break
                    
                    if '.mediakeeper' in dirs:
                        dirs.remove('.mediakeeper')
                        
                    for f in files_list:
                        if not self.is_running: break
                        if self.is_extension_allowed(f):
                            fp = os.path.join(root, f)
                            valid_files.append(fp)
                            
                        scanned_files += 1
            except Exception as e:
                logging.error(f"Ошибка при обходе папки {folder}: {e}")

        total_files = len(valid_files)
        if total_files == 0:
            self.finished.emit({})
            return
            
        # Убедимся, что сессии ONNX инициализированы
        if not self.classifier.ai.initialize_sessions(use_gpu=getattr(self, "use_gpu", True)):
            self.finished.emit({})
            return

        # ЭТАП 1: КЭШИРОВАНИЕ (Синий прогресс-бар)
        processed_files = 0
        for fp in valid_files:
            if not self.is_running: break
            try:
                stat = os.stat(fp)
                mtime = stat.st_mtime
                size = stat.st_size
                
                if self.use_cache:
                    clip_emb = self.classifier.cache.get_image_embedding(fp, mtime, size)
                    if clip_emb is None:
                        clip_emb = self.classifier.ai.extract_clip_embedding(fp)
                        if clip_emb is not None:
                            self.classifier.cache.save_image_embedding(fp, mtime, size, clip_emb)
                    
                    faces = self.classifier.cache.get_file_faces(fp, mtime, size)
                    if faces is None:
                        faces = self.classifier.ai.extract_faces(fp)
                        if faces is not None:
                            self.classifier.cache.save_file_faces(fp, mtime, size, faces)
                            
                scanned_bytes += size
            except Exception as e:
                logging.error(f"Ошибка кэширования {fp}: {e}")
                
            processed_files += 1
            percent = (processed_files / total_files) * 100.0
            if processed_files % 10 == 0 or processed_files == total_files:
                self.progress.emit(STAGE_SCANNING, percent, f"Сканирование каталога 1/2 [{processed_files} / {total_files}]", scanned_files, 0, 0, scanned_bytes, 0, 0)
        
        if not self.is_running:
            self.finished.emit({})
            return

        # ЭТАП 2: ПОИСК СОВПАДЕНИЙ (Зеленый прогресс-бар)
        results = {}
        processed_files = 0
        groups_found = 0
        files_found = 0
        wasted_bytes = 0
        
        self.progress.emit(STAGE_ANALYSIS, 0.0, f"Поиск совпадений 2/2 [0 / {total_files}]", scanned_files, 0, 0, scanned_bytes, 0, 0)
        
        for fp in valid_files:
            if not self.is_running: break
            try:
                stat = os.stat(fp)
                size = stat.st_size
                mtime = stat.st_mtime
                
                best_group = None
                best_confidence = 0.0
                
                if getattr(self, "text_query", None):
                    import numpy as np
                    text_emb = self.classifier.ai.extract_text_embedding(self.text_query)
                    clip_emb = self.classifier.cache.get_image_embedding(fp, mtime, size) if self.use_cache else self.classifier.ai.extract_clip_embedding(fp)
                    if text_emb is not None and clip_emb is not None:
                        score_raw = np.dot(text_emb, clip_emb)
                        mapped_score = (score_raw - 0.20) / (0.32 - 0.20)
                        best_confidence = max(0.0, min(1.0, float(mapped_score)))
                        best_group = f"[Текст] {self.text_query}"
                else:
                    results_dict = self.classifier.classify_file(fp)
                    for g_name, conf in results_dict.items():
                        if conf > best_confidence:
                            best_confidence = conf
                            best_group = g_name
                            
                if best_group and (best_confidence * 100.0) >= self.threshold:
                    if best_group not in results:
                        results[best_group] = []
                        groups_found += 1
                        
                    results[best_group].append({
                        "path": fp,
                        "size": size,
                        "confidence": best_confidence * 100.0,
                        "type": "AI"
                    })
                    wasted_bytes += size
                    files_found += 1
            except Exception as e:
                logging.error(f"Ошибка сопоставления {fp}: {e}")
                
            processed_files += 1
            percent = (processed_files / total_files) * 100.0
            if processed_files % 50 == 0 or processed_files == total_files:
                self.progress.emit(STAGE_ANALYSIS, percent, f"Поиск совпадений 2/2 [{processed_files} / {total_files}]", scanned_files, groups_found, wasted_bytes, scanned_bytes, files_found, 0)
        
        for g in results:
            results[g].sort(key=lambda x: x["confidence"], reverse=True)
            
        if self.is_running:
            self.progress.emit(STAGE_ANALYSIS, 100.0, "Готово", scanned_files, groups_found, wasted_bytes, scanned_bytes, files_found, 0)
        self.finished.emit(results)



import sqlite3

class CreateDumpWorker(QThread):
    progress = pyqtSignal(int, float, str, int, int, object, object, int, int) 
    finished = pyqtSignal(bool, str) 
    
    def __init__(self, folders, dump_path, use_cache=True):
        super().__init__()
        self.folders = folders
        self.dump_path = dump_path
        self.use_cache = use_cache
        self.is_running = True
        self.db = CleanerDB() if use_cache else None

    def stop(self): self.is_running = False

    def get_partial_hash(self, path):
        try:
            size = os.path.getsize(path)
            with open(path, 'rb') as f:
                if size <= 8192:
                    return hashlib.md5(f.read()).hexdigest()
                else:
                    start = f.read(4096)
                    f.seek(-4096, 2)
                    hasher = hashlib.md5()
                    hasher.update(start)
                    hasher.update(f.read(4096))
                    return hasher.hexdigest()
        except: return None

    def get_full_hash(self, path, size):
        try:
            if size > LARGE_FILE_THRESHOLD:
                hasher = hashlib.sha256()
                chunk_size = 4096 
                with open(path, 'rb') as f:
                    f.seek(0)
                    hasher.update(f.read(chunk_size))
                    if not self.is_running: return None
                    pos_25 = int(size * 0.25)
                    f.seek(pos_25)
                    hasher.update(f.read(chunk_size))
                    pos_50 = int(size * 0.50)
                    f.seek(pos_50)
                    hasher.update(f.read(chunk_size))
                    if not self.is_running: return None
                    pos_75 = int(size * 0.75)
                    f.seek(pos_75)
                    hasher.update(f.read(chunk_size))
                    if size > chunk_size:
                        f.seek(-chunk_size, 2)
                        hasher.update(f.read(chunk_size))
                return "sparse_" + hasher.hexdigest()
            else:
                hasher = hashlib.sha256() 
                with open(path, 'rb') as f:
                    while True:
                        if not self.is_running: return None
                        chunk = f.read(65536)
                        if not chunk: break
                        hasher.update(chunk)
                return hasher.hexdigest()
        except: return None

    def run(self):
        try:
            hashes_to_save = set()
            scanned_files = 0
            scanned_bytes = 0
            
            for folder in self.folders:
                if folder.lower().endswith(".mkdump") and os.path.exists(folder):
                    try:
                        conn = sqlite3.connect(folder)
                        cur = conn.cursor()
                        cur.execute("SELECT hash, size FROM groups")
                        for row in cur.fetchall():
                            hashes_to_save.add((row[0], row[1]))
                        conn.close()
                    except: pass
            
            real_folders = [f for f in self.folders if not f.lower().endswith(".mkdump")]
            all_files = []
            
            self.progress.emit(STAGE_SCANNING, 0.0, "Поиск файлов...", 0, 0, 0, 0, 0, 0)
            for folder in real_folders:
                if not self.is_running: break
                scan_path = ensure_win_path(os.path.normpath(folder))
                if not os.path.exists(scan_path): continue
                for root, _, files in os.walk(scan_path):
                    if not self.is_running: break
                    for f in files:
                        path = os.path.join(root, f)
                        all_files.append(path)
                        
            total_files = len(all_files)
            last_emit_time = 0
            
            for i, path in enumerate(all_files):
                if not self.is_running: break
                try:
                    stat = os.stat(path)
                    size = stat.st_size
                    if size == 0: continue
                    
                    scanned_files += 1
                    scanned_bytes += size
                    
                    current_time = time.time()
                    if current_time - last_emit_time > 0.1:
                        pct = (i / total_files) * 100
                        self.progress.emit(STAGE_ANALYSIS, pct, path, scanned_files, len(hashes_to_save), 0, scanned_bytes, 0, 0)
                        last_emit_time = current_time
                    
                    mtime = stat.st_mtime
                    p_hash, f_hash = None, None
                    if self.use_cache:
                        cached = self.db.get_cached_data(path, size, mtime)
                        if cached: p_hash, f_hash = cached
                    if not p_hash:
                        p_hash = self.get_partial_hash(path)
                    if not p_hash: continue
                    
                    if not f_hash:
                        f_hash = self.get_full_hash(path, size)
                        if self.use_cache and f_hash:
                            self.db.upsert_hash(path, size, mtime, p_hash, f_hash)
                            
                    if f_hash:
                        hashes_to_save.add((f_hash, size))
                except: pass

            if not self.is_running:
                self.finished.emit(False, "Остановлено пользователем")
                return

            self.progress.emit(STAGE_ANALYSIS, 100.0, "Сохранение файла дампа...", scanned_files, len(hashes_to_save), 0, scanned_bytes, 0, 0)
            
            if os.path.exists(self.dump_path):
                os.remove(self.dump_path)
            conn = sqlite3.connect(self.dump_path)
            cur = conn.cursor()
            cur.execute('CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT)')
            cur.execute('INSERT INTO metadata (key, value) VALUES ("version", "1.0")')
            cur.execute('CREATE TABLE groups (id INTEGER PRIMARY KEY AUTOINCREMENT, hash TEXT, size INTEGER)')
            
            cur.executemany('INSERT INTO groups (hash, size) VALUES (?, ?)', list(hashes_to_save))
            conn.commit()
            conn.close()
            
            self.finished.emit(True, "")
        except Exception as e:
            self.finished.emit(False, str(e))
