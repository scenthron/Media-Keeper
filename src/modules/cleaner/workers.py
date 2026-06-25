
import os
import hashlib
from utils_common import is_subpath
import time
import logging
from typing import Any
from PyQt6.QtCore import QThread, pyqtSignal
from .db_cache import CleanerDB

STAGE_SCANNING = 1
STAGE_ANALYSIS = 2
LARGE_FILE_THRESHOLD = 50 * 1024 * 1024 

EXT_GROUPS = {
    "Images": {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.raw', '.heic', '.heif', '.svg', '.ico', '.tga', '.psd', '.apng'},
    "Video": {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.3g2', '.mpg', '.mpeg', '.ts', '.m2ts', '.vob', '.asf', '.rm', '.rmvb'},
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
        stats = {} 
        for folder in self.folders:
            path_to_scan = ensure_win_path(folder)
            if not os.path.exists(path_to_scan): continue
            for root, _, files in os.walk(path_to_scan):
                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if not ext: continue
                    stats[ext] = stats.get(ext, 0) + 1
        grouped_results = {}
        for group_name in EXT_GROUPS.keys():
            grouped_results[group_name] = []
        other_list = []
        for ext, count in stats.items():
            found = False
            for group_name, ext_set in EXT_GROUPS.items():
                if ext in ext_set:
                    grouped_results[group_name].append({'ext': ext, 'count': count})
                    found = True
                    break
            if not found: other_list.append({'ext': ext, 'count': count})
        if other_list: grouped_results["Other"] = other_list
        final_results = {k: v for k, v in grouped_results.items() if v}
        for k in final_results: final_results[k].sort(key=lambda x: x['count'], reverse=True)
        self.finished.emit(final_results)

class DuplicateFinderWorker(QThread):
    progress = pyqtSignal(int, float, str, int, int, object, object, int, int) 
    finished = pyqtSignal(dict) 
    
    def __init__(self, folders, use_cache=True, filter_config=None, size_limits=(0, 0), safe_scan=False):
        super().__init__()
        self.folders = folders
        self.use_cache = use_cache
        self.filter_config = filter_config
        self.min_size = size_limits[0]
        self.max_size = size_limits[1]
        self.safe_scan = safe_scan
        self.reference_path = None # Will be set from cleaner module
        self.is_running = True
        self.db = CleanerDB() if use_cache else None

    def stop(self): self.is_running = False

    def get_partial_hash(self, path):
        try:
            size = os.path.getsize(path)
            with open(path, 'rb') as f:
                if size <= 8192:
                    data = f.read()
                    return hashlib.md5(data).hexdigest()
                else:
                    start = f.read(4096)
                    f.seek(-4096, 2)
                    end = f.read(4096)
                    hasher = hashlib.md5()
                    hasher.update(start)
                    hasher.update(end)
                    return hasher.hexdigest()
        except: return None

    def get_full_hash(self, path):
        try:
            hasher = hashlib.sha256() 
            with open(path, 'rb') as f:
                while True:
                    if not self.is_running: return None
                    chunk = f.read(65536)
                    if not chunk: break
                    hasher.update(chunk)
            return hasher.hexdigest()
        except: return None

    def get_sparse_hash(self, path, size):
        try:
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
        except: return None

    def is_extension_allowed(self, filename):
        ext = os.path.splitext(filename)[1].lower()
        if self.safe_scan:
            return ext in MEDIA_EXTS
        if not self.filter_config: return True
        mode = self.filter_config['mode']
        target_exts = self.filter_config['exts']
        if not target_exts: return (True if mode != 'include' else False)
        if mode == 'include': return ext in target_exts
        elif mode == 'exclude': return ext not in target_exts
        return True

    def run(self):
        files_by_size = {}
        zero_files = []
        empty_folders = []
        scanned_files = 0
        scanned_bytes = 0
        last_emit_time = 0
        emit_interval = 0.1 
        self.progress.emit(STAGE_SCANNING, 0.0, "Сканирование файловой системы...", 0, 0, 0, 0, 0, 0)
        
        deeply_empty_dirs = set()
        non_empty_dirs = set()

        for folder in self.folders:
            if not self.is_running: break
            norm_folder = os.path.normpath(folder)
            scan_path = ensure_win_path(norm_folder)
            if not os.path.exists(scan_path): continue
            try:
                for root, dirs, files in os.walk(scan_path, topdown=False):
                    if not self.is_running: break
                    
                    is_deeply_empty = True
                    if files:
                        is_deeply_empty = False
                    else:
                        for d in dirs:
                            if os.path.join(root, d) in non_empty_dirs:
                                is_deeply_empty = False
                                break
                                
                    if is_deeply_empty:
                        deeply_empty_dirs.add(root)
                    else:
                        non_empty_dirs.add(root)

                    for f in files:
                        if not self.is_running: break
                        path = os.path.join(root, f)
                        try:
                            stat = os.stat(path)
                            size = stat.st_size
                            scanned_files += 1
                            scanned_bytes += size
                            current_time = time.time()
                            if current_time - last_emit_time > emit_interval:
                                self.progress.emit(STAGE_SCANNING, 0.0, path, scanned_files, 0, 0, scanned_bytes, len(zero_files), len(empty_folders))
                                last_emit_time = current_time
                            if not self.is_extension_allowed(f): continue
                            if size == 0: 
                                display_path = path
                                if display_path.startswith('\\\\?\\'): display_path = display_path[4:]
                                zero_files.append(display_path)
                                continue
                            if self.min_size > 0 and size < self.min_size: continue
                            if self.max_size > 0 and size > self.max_size: continue
                            if size not in files_by_size: files_by_size[size] = []
                            display_path = path
                            if display_path.startswith('\\\\?\\'): display_path = display_path[4:]
                            files_by_size[size].append({ 'path': display_path, 'real_path': path, 'size': size, 'mtime': stat.st_mtime, 'source_root': norm_folder })
                        except OSError: pass
            except Exception: pass

        for d in deeply_empty_dirs:
            parent = os.path.dirname(d)
            if parent not in deeply_empty_dirs and parent != d:
                display_path = d
                if display_path.startswith('\\\\?\\'): display_path = display_path[4:]
                empty_folders.append(display_path)

        if not self.is_running:
            self.finished.emit({'groups': [], 'zero_files': [], 'empty_folders': []})
            return

        candidates_size = {s: files for s, files in files_by_size.items() if len(files) > 1}
        if not candidates_size:
            if self.is_running:
                self.progress.emit(STAGE_ANALYSIS, 100.0, "Готово", scanned_files, 0, 0, scanned_bytes, len(zero_files), len(empty_folders))
            self.finished.emit({'groups': [], 'zero_files': zero_files, 'empty_folders': empty_folders})
            return

        final_groups = []
        processed_count = 0
        total_candidates = sum(len(files) for files in candidates_size.values())
        found_matches_count = 0 
        current_wasted_bytes = 0
        self.progress.emit(STAGE_ANALYSIS, 10.0, f"Анализ {total_candidates} кандидатов...", scanned_files, 0, 0, scanned_bytes, len(zero_files), len(empty_folders))

        # Prepare reference path for fast check
        norm_ref = None
        if self.reference_path:
            norm_ref = os.path.normcase(os.path.normpath(self.reference_path))

        for size, files in candidates_size.items():
            if not self.is_running: break
            by_partial = {}
            for file_data in files:
                if not self.is_running: break
                processed_count += 1
                real_path = file_data['real_path']
                current_time = time.time()
                if current_time - last_emit_time > emit_interval:
                    percent = 10.0 + (processed_count / total_candidates) * 80.0
                    self.progress.emit(STAGE_ANALYSIS, percent, real_path, scanned_files, found_matches_count, current_wasted_bytes, scanned_bytes, len(zero_files), len(empty_folders))
                    last_emit_time = current_time
                mtime = file_data['mtime']
                p_hash, f_hash = None, None
                if self.use_cache:
                    cached = self.db.get_cached_data(real_path, size, mtime)
                    if cached: p_hash, f_hash = cached
                if not p_hash:
                    p_hash = self.get_partial_hash(real_path)
                    if not p_hash: continue 
                if p_hash not in by_partial: by_partial[p_hash] = []
                file_data['partial_hash'] = p_hash
                file_data['full_hash'] = f_hash
                by_partial[p_hash].append(file_data)

            for p_hash, p_files in by_partial.items():
                if len(p_files) < 2: continue
                by_full = {}
                for file_data in p_files:
                    if not self.is_running: break
                    real_path = file_data['real_path']
                    f_hash = file_data.get('full_hash')
                    if not f_hash:
                        if size > LARGE_FILE_THRESHOLD: f_hash = self.get_sparse_hash(real_path, size)
                        else: f_hash = self.get_full_hash(real_path)
                        if self.use_cache and f_hash: self.db.upsert_hash(real_path, file_data['size'], file_data['mtime'], p_hash, f_hash)
                    if f_hash:
                        if f_hash not in by_full: by_full[f_hash] = []
                        by_full[f_hash].append(file_data)
                
                for f_hash, f_files in by_full.items():
                    if len(f_files) > 1:
                        # --- ON-THE-FLY REFERENCE FILTERING ---
                        if norm_ref:
                            has_ref = False
                            subset_outside_ref = 0
                            for f in f_files:
                                if is_subpath(f['path'], norm_ref):
                                    has_ref = True
                                else:
                                    subset_outside_ref += 1
                            
                            # Valid group only if it has reference AND at least one dupe outside
                            if has_ref and subset_outside_ref > 0:
                                final_groups.append({ 'hash': f_hash, 'size': size, 'files': f_files })
                                found_matches_count += subset_outside_ref
                                current_wasted_bytes += size * subset_outside_ref
                        else:
                            # Normal mode: all files except first are duplicates
                            final_groups.append({ 'hash': f_hash, 'size': size, 'files': f_files })
                            dupes_in_group = len(f_files) - 1
                            found_matches_count += dupes_in_group
                            current_wasted_bytes += size * dupes_in_group
                        
                        current_time = time.time()
                        if current_time - last_emit_time > emit_interval:
                            self.progress.emit(STAGE_ANALYSIS, -1.0, "Найдено совпадение", scanned_files, found_matches_count, current_wasted_bytes, scanned_bytes, len(zero_files), len(empty_folders))
                            last_emit_time = current_time

        if self.is_running:
            msg = "Готово (Фильтр эталона)" if norm_ref else "Готово"
            self.progress.emit(STAGE_ANALYSIS, 100.0, msg, scanned_files, found_matches_count, current_wasted_bytes, scanned_bytes, len(zero_files), len(empty_folders))

        final_groups.sort(key=lambda g: g['size'] * (len(g['files']) - 1), reverse=True)
        self.finished.emit({'groups': final_groups, 'zero_files': zero_files, 'empty_folders': empty_folders})


class DBLoadWorker(QThread):
    """
    Фоновый воркер для чтения сессионной базы данных SQLite и обогащения метаданными (Enrich & Cache).
    Полностью устраняет зависания GUI-потока при считывании и сопоставлении 200 000+ элементов.
    """
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(list, dict)

    def __init__(
        self,
        session_db: Any,
        current_view_mode: int,
        source_folders: dict[str, Any],
        view_filter_exts: list[str] | None = None,
        view_filter_mode: str = 'include'
    ) -> None:
        super().__init__()
        self.session_db = session_db
        self.current_view_mode = current_view_mode
        self.source_folders = source_folders
        self.view_filter_exts = view_filter_exts
        self.view_filter_mode = view_filter_mode
        self.is_running = True

    def stop(self) -> None:
        self.is_running = False

    def run(self) -> None:
        logging.info("[DBLoadWorker] Запуск фонового потока чтения СУБД...")
        flat_items: list[dict[str, Any]] = []

        def progress_cb(current: int, total: int) -> None:
            if not self.is_running:
                return
            self.progress.emit(current, total)

        try:
            if self.current_view_mode == 0:  # Duples
                flat_items = self.session_db.fetch_all_flat_items(
                    filter_exts=self.view_filter_exts,
                    filter_mode=self.view_filter_mode,
                    progress_callback=progress_cb
                )
            elif self.current_view_mode == 1:  # Zero
                flat_items = self.session_db.fetch_all_flat_zero_items()
            elif self.current_view_mode == 2:  # Empty
                flat_items = self.session_db.fetch_all_flat_empty_folders()

            if not self.is_running:
                logging.info("[DBLoadWorker] Чтение БД прервано во время выполнения.")
                self.finished.emit([], {})
                return

            logging.info(f"[DBLoadWorker] Чтение СУБД завершено. Получено элементов: {len(flat_items)}. Запуск Enrich & Cache...")
            
            group_files_cache: dict[Any, list[dict[str, Any]]] = {}

            # Предварительно сортируем папки по длине пути для корректного Enrich
            sorted_folders = sorted(
                self.source_folders.items(),
                key=lambda x: len(x[0]),
                reverse=True
            )

            for idx, item in enumerate(flat_items):
                if not self.is_running:
                    logging.info("[DBLoadWorker] Обогащение данных прервано пользователем.")
                    self.finished.emit([], {})
                    return

                if item['type'] == 'file':
                    path: str = item['path']
                    is_protected = False
                    is_reference = False
                    color = "#555"
                    
                    # Быстрое сопоставление по отсортированному списку папок
                    for src_path, data in sorted_folders:
                        if is_subpath(path, src_path):
                            is_reference = data.get('reference', False)
                            is_protected = data.get('protected', False) or is_reference
                            color = data.get('color', '#555')
                            break
                            
                    item['is_protected'] = is_protected
                    item['is_reference'] = is_reference
                    item['color'] = color

                    # Добавляем в кэш группы
                    g_id = item['group_id']
                    if g_id not in group_files_cache:
                        group_files_cache[g_id] = []
                    group_files_cache[g_id].append(item)

                # Периодически отпускаем GIL (каждые 2000 элементов) для плавной отрисовки GUI
                if idx % 2000 == 0:
                    time.sleep(0.00005)

            if not self.is_running:
                self.finished.emit([], {})
                return

            logging.info("[DBLoadWorker] Фоновое обогащение данных полностью завершено.")
            self.finished.emit(flat_items, group_files_cache)

        except Exception as e:
            logging.error(f"[DBLoadWorker] Ошибка при фоновом чтении БД: {e}")
            self.finished.emit([], {})
