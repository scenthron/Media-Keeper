
import os
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

class SimilarScanWorker(QThread):
    progress = pyqtSignal(int, float, str, int, int, object, object, int, int)
    finished = pyqtSignal(dict)
    
    def __init__(self, folders_dict, use_cache=True, filter_config=None, size_limits=(0, 0), media_type=0, threshold=90, hash_size=16, algorithm="phash", monotone_filter=False, monotone_threshold=15.0):
        super().__init__()
        self.folders_dict = folders_dict
        self.folders = list(folders_dict.keys())
        self.use_cache = use_cache
        self.filter_config = filter_config
        self.min_size = size_limits[0]
        self.max_size = size_limits[1]
        self.media_type = media_type # 0: Images, 1: Audio, 2: Video
        self.threshold = threshold
        self.hash_size = hash_size
        self.algorithm = algorithm.lower()
        self.monotone_filter = monotone_filter
        self.monotone_threshold = monotone_threshold
        
        if media_type == 0 and self.algorithm == "phash":
            self.total_bits = self.hash_size * self.hash_size - 1
        else:
            self.total_bits = self.hash_size * self.hash_size
            
        self.reference_path = None
        self.is_running = True
        
        from .db_cache import SimilarDB
        self.db = SimilarDB(hash_size=self.hash_size, algorithm=self.algorithm) if use_cache else None

    def stop(self):
        self.is_running = False

    def is_extension_allowed(self, filename):
        ext = os.path.splitext(filename)[1].lower()
        if self.media_type == 0:
            allowed_exts = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.heic', '.heif'}
        elif self.media_type == 1:
            allowed_exts = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma'}
        else:
            allowed_exts = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm'}
            
        if ext not in allowed_exts:
            return False
            
        if not self.filter_config:
            return True
            
        mode = self.filter_config['mode']
        target_exts = self.filter_config['exts']
        if not target_exts:
            return (True if mode != 'include' else False)
            
        if mode == 'include':
            return ext in target_exts
        elif mode == 'exclude':
            return ext not in target_exts
        return True

    def run(self):
        valid_files = []
        scanned_files = 0
        scanned_bytes = 0
        last_emit_time = 0
        emit_interval = 0.1
        
        self.progress.emit(STAGE_SCANNING, 0.0, "Сканирование файлов...", 0, 0, 0, 0, 0, 0)
        
        for folder in self.folders:
            if not self.is_running: break
            norm_folder = os.path.normpath(folder)
            scan_path = ensure_win_path(norm_folder)
            if not os.path.exists(scan_path): continue
            
            try:
                for root, dirs, files in os.walk(scan_path):
                    if not self.is_running: break
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
                                self.progress.emit(STAGE_SCANNING, 0.0, path, scanned_files, 0, 0, scanned_bytes, 0, 0)
                                last_emit_time = current_time
                                
                            if not self.is_extension_allowed(f): continue
                            if size == 0: continue
                            if self.min_size > 0 and size < self.min_size: continue
                            if self.max_size > 0 and size > self.max_size: continue
                            
                            display_path = path
                            if display_path.startswith('\\\\?\\'): display_path = display_path[4:]
                            valid_files.append({
                                'path': display_path,
                                'real_path': path,
                                'size': size,
                                'mtime': stat.st_mtime,
                                'source_root': norm_folder,
                                'signature': None
                            })
                        except OSError: pass
            except Exception: pass
            
        if not self.is_running:
            self.finished.emit({'groups': [], 'zero_files': [], 'empty_folders': []})
            return

        total_files = len(valid_files)
        self.progress.emit(STAGE_ANALYSIS, 10.0, f"Анализ {total_files} медиафайлов...", scanned_files, 0, 0, scanned_bytes, 0, 0)
        
        # 1. Сбор хэшей (подпись)
        processed_count = 0
        files_with_signatures = []
        for file_data in valid_files:
            if not self.is_running: break
            processed_count += 1
            
            current_time = time.time()
            if current_time - last_emit_time > emit_interval:
                percent = 10.0 + (processed_count / max(1, total_files)) * 70.0
                self.progress.emit(STAGE_ANALYSIS, percent, file_data['real_path'], scanned_files, 0, 0, scanned_bytes, 0, 0)
                last_emit_time = current_time
                
            sig = None
            meta = ""
            std_dev = 999.0
            if self.use_cache:
                cached_sig = self.db.get_cached_signature(file_data['real_path'], file_data['size'], file_data['mtime'])
                if cached_sig:
                    if self.media_type == 0 and ':' in cached_sig:
                        sig, std_dev_str = cached_sig.split(':', 1)
                        try: std_dev = float(std_dev_str)
                        except: std_dev = 999.0
                    else:
                        sig = cached_sig
                        
                    if sig and self.media_type == 0:
                        try:
                            from PIL import Image
                            with Image.open(file_data['real_path']) as img:
                                meta = f"{img.size[0]}x{img.size[1]}"
                        except:
                            pass
                elif sig and self.media_type == 1:
                    from logic_paths import get_ffprobe_exe
                    ffprobe_exe = get_ffprobe_exe()
                    if os.path.exists(ffprobe_exe):
                        import subprocess
                        cmd = [ffprobe_exe, "-v", "error", "-show_entries", "format=bit_rate", "-of", "default=noprint_wrappers=1:nokey=1", file_data['real_path']]
                        try:
                            cr_flags = 0x08000000 if os.name == 'nt' else 0
                            res = subprocess.run(cmd, capture_output=True, text=True, creationflags=cr_flags, timeout=5)
                            if res.returncode == 0 and res.stdout.strip() and res.stdout.strip() != "N/A":
                                bitrate_bps = int(res.stdout.strip())
                                meta = f"{bitrate_bps // 1000} kbps"
                        except Exception:
                            pass
                elif sig and self.media_type == 2:
                    try:
                        from .vhash import get_video_resolution, get_video_bitrate
                        from logic_paths import get_ffprobe_exe
                        ffprobe_exe = get_ffprobe_exe()
                        if os.path.exists(ffprobe_exe):
                            res_str = get_video_resolution(file_data['real_path'], ffprobe_exe)
                            bit_str = get_video_bitrate(file_data['real_path'], ffprobe_exe)
                            if bit_str:
                                res_str = f"{res_str} | {bit_str}"
                            meta = res_str
                    except Exception as e:
                        logging.error(f"Error loading cached metadata for video {file_data['real_path']}: {e}")
                 
            if not sig:
                if self.media_type == 0: # Изображения
                    if self.algorithm == "dhash":
                        from .dhash import get_image_dhash
                        res = get_image_dhash(file_data['real_path'], hash_size=self.hash_size)
                    elif self.algorithm == "phash":
                        from .dhash import get_image_phash
                        res = get_image_phash(file_data['real_path'], hash_size=self.hash_size)
                    else:
                        from .dhash import get_image_ahash
                        res = get_image_ahash(file_data['real_path'], hash_size=self.hash_size)
                        
                    if res:
                        sig, meta, std_dev = res
                elif self.media_type == 1: # Аудио
                    try:
                        from .ahash_audio import extract_audio_fingerprint
                        from logic_paths import get_fpcalc_exe, get_ffprobe_exe
                        fp_exe = get_fpcalc_exe()
                        fp = extract_audio_fingerprint(file_data['real_path'], fp_exe)
                    except Exception as e:
                        logging.error(f"Error extracting audio fingerprint for {file_data['real_path']}: {e}")
                        fp = None
                    
                    ffprobe_exe = get_ffprobe_exe()
                    if os.path.exists(ffprobe_exe):
                        import subprocess
                        cmd = [ffprobe_exe, "-v", "error", "-show_entries", "format=bit_rate", "-of", "default=noprint_wrappers=1:nokey=1", file_data['real_path']]
                        try:
                            cr_flags = 0x08000000 if os.name == 'nt' else 0
                            res = subprocess.run(cmd, capture_output=True, text=True, creationflags=cr_flags, timeout=5)
                            if res.returncode == 0 and res.stdout.strip() and res.stdout.strip() != "N/A":
                                bitrate_bps = int(res.stdout.strip())
                                meta = f"{bitrate_bps // 1000} kbps"
                        except Exception:
                            pass
                    
                    if fp:
                        import json
                        sig = json.dumps(fp)
                elif self.media_type == 2: # Видео
                    try:
                        from .vhash import extract_video_fingerprint
                        from logic_paths import get_ffmpeg_exe, get_ffprobe_exe
                        res = extract_video_fingerprint(file_data['real_path'], get_ffmpeg_exe(), get_ffprobe_exe(), self.hash_size)
                        if res:
                            fp_list, meta = res
                            if fp_list:
                                import json
                                sig = json.dumps(fp_list)
                    except Exception as e:
                        logging.error(f"Error extracting video fingerprint for {file_data['real_path']}: {e}")

                if sig and self.use_cache:
                    if self.media_type == 0:
                        sig_to_store = f"{sig}:{std_dev}"
                    else:
                        sig_to_store = sig
                    self.db.upsert_signature(file_data['real_path'], file_data['size'], file_data['mtime'], sig_to_store)
                    
            if sig:
                file_data['signature'] = sig
                file_data['metadata'] = meta
                file_data['std_dev'] = std_dev
                
                # Подготавливаем хэш для быстрого сравнения в зависимости от типа медиа
                if self.media_type == 0:
                    parsed_hash = int(sig, 16)
                else:
                    import json
                    parsed_hash = json.loads(sig)
                    
                files_with_signatures.append((file_data, parsed_hash))

        if not self.is_running:
            self.finished.emit({'groups': [], 'zero_files': [], 'empty_folders': []})
            return

        # 2. Группировка по сходству (расстояние Хэмминга / BER)
        groups = []
        visited = set()
        
        protected_folders = [os.path.normcase(os.path.normpath(p)) for p, d in self.folders_dict.items() if d.get('protected')]
        norm_ref = None
        if self.reference_path:
            norm_ref = os.path.normcase(os.path.normpath(self.reference_path))
            
        found_matches_count = 0
        current_wasted_bytes = 0
        total_sigs = len(files_with_signatures)
        
        # Заранее импортируем функции сравнения
        try:
            if self.media_type == 1:
                from .ahash_audio import compare_audio_fingerprints
            elif self.media_type == 2:
                from .vhash import compare_video_fingerprints
        except ImportError as e:
            logging.error(f"Failed to import comparison module for media_type {self.media_type}: {e}")
            self.finished.emit({})
            return

        if self.media_type != 1 and self.media_type != 2:
            threshold_bits = int((100 - self.threshold) / 100.0 * self.total_bits)
        
        for i in range(total_sigs):
            if not self.is_running: break
            
            # Эмитим прогресс от 80% до 100%
            current_time = time.time()
            if current_time - last_emit_time > emit_interval:
                percent = 80.0 + (i / max(1, total_sigs)) * 20.0
                self.progress.emit(STAGE_ANALYSIS, percent, "Группировка результатов...", scanned_files, 0, 0, scanned_bytes, 0, 0)
                last_emit_time = current_time
                
            if i in visited: continue
            
            f1, h1 = files_with_signatures[i]
            current_group = [f1]
            
            for j in range(i + 1, total_sigs):
                if j in visited: continue
                f2, h2 = files_with_signatures[j]
                
                sim = 0.0
                current_threshold_bits = threshold_bits
                if self.media_type == 0:
                    dist = bin(h1 ^ h2).count('1')
                    
                    # Проверка на монотонность (дисперсию)
                    if self.monotone_filter:
                        dev1 = f1.get('std_dev', 999.0)
                        dev2 = f2.get('std_dev', 999.0)
                        if dev1 < self.monotone_threshold or dev2 < self.monotone_threshold:
                            # Для монотонных изображений требуем строгое совпадение (>= 99.0%)
                            current_threshold_bits = int((100.0 - 99.0) / 100.0 * self.total_bits)
                            
                    if dist <= current_threshold_bits:
                        sim = (self.total_bits - dist) / self.total_bits * 100.0
                elif self.media_type == 1:
                    sim = compare_audio_fingerprints(h1, h2)
                elif self.media_type == 2:
                    sim = compare_video_fingerprints(h1, h2, self.hash_size)
                    
                if self.media_type != 0 and sim >= self.threshold:
                    current_group.append(f2)
                    visited.add(j)
                elif self.media_type == 0 and dist <= current_threshold_bits:
                    current_group.append(f2)
                    visited.add(j)
                    
            if len(current_group) > 1:
                visited.add(i)
                
                def get_sort_key(f):
                    path_norm = os.path.normcase(os.path.normpath(f['path']))
                    is_ref = norm_ref and is_subpath(path_norm, norm_ref)
                    is_prot = any(is_subpath(path_norm, p) for p in protected_folders)
                    return (0 if is_ref else 1, 0 if is_prot else 1, -f['size'])
                    
                current_group.sort(key=get_sort_key)
                
                # Задаем проценты схожести относительно первого файла (оригинала)
                base_file = current_group[0]
                base_file['similarity_pct'] = 100.0
                base_hash = [h for f, h in files_with_signatures if f == base_file][0]
                
                for other in current_group[1:]:
                    other_hash = [h for f, h in files_with_signatures if f == other][0]
                    sim = 0.0
                    if self.media_type == 0:
                        dist = bin(base_hash ^ other_hash).count('1')
                        sim = (self.total_bits - dist) / float(self.total_bits) * 100.0
                    elif self.media_type == 1:
                        sim = compare_audio_fingerprints(base_hash, other_hash)
                    elif self.media_type == 2:
                        sim = compare_video_fingerprints(base_hash, other_hash, self.hash_size)
                    other['similarity_pct'] = round(sim, 2)
                    
                # Фильтруем группу по эталону
                if norm_ref:
                    has_ref = False
                    subset_outside_ref = 0
                    for f in current_group:
                        path_norm = os.path.normcase(os.path.normpath(f['path']))
                        if is_subpath(path_norm, norm_ref):
                            has_ref = True
                        else:
                            subset_outside_ref += 1
                    if has_ref and subset_outside_ref > 0:
                        groups.append({ 'hash': base_file['signature'], 'size': base_file['size'], 'files': current_group })
                        found_matches_count += subset_outside_ref
                        current_wasted_bytes += sum(f['size'] for f in current_group if not is_subpath(os.path.normcase(os.path.normpath(f['path'])), norm_ref))
                else:
                    groups.append({ 'hash': base_file['signature'], 'size': base_file['size'], 'files': current_group })
                    dupes_in_group = len(current_group) - 1
                    found_matches_count += dupes_in_group
                    current_wasted_bytes += sum(f['size'] for f in current_group[1:])
                    
        # Сортируем группы по общему объему "лишних" файлов
        groups.sort(key=lambda g: g['size'] * (len(g['files']) - 1), reverse=True)
        
        if self.is_running:
            self.progress.emit(STAGE_ANALYSIS, 100.0, "Готово", scanned_files, found_matches_count, current_wasted_bytes, scanned_bytes, 0, 0)
            
        self.finished.emit({'groups': groups, 'zero_files': [], 'empty_folders': []})

class AiScanWorker(QThread):
    # Сигналы: stage, percent, status_text, scanned_files, groups_found, wasted_bytes, scanned_bytes, zero, empty
    progress = pyqtSignal(int, float, str, int, int, int, int, int, int)
    # finished: { group_name: [ { 'path': ..., 'size': ..., 'confidence': ..., 'type': ... }, ... ] }
    finished = pyqtSignal(dict)
    
    def __init__(self, folders, classifier, threshold=75.0, filter_config=None, match_mode="centroid", use_cache=True, use_gpu=True, is_cluster=False, cluster_type="face"):
        super().__init__()
        self.folders = folders
        self.classifier = classifier
        self.threshold = threshold
        self.filter_config = filter_config
        self.match_mode = match_mode
        self.use_cache = use_cache
        self.use_gpu = use_gpu
        self.is_cluster = is_cluster
        self.cluster_type = cluster_type
        self.is_running = True

    def stop(self):
        self.is_running = False

    def is_extension_allowed(self, filename):
        ext = os.path.splitext(filename)[1].lower()
        allowed_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
        if ext not in allowed_exts:
            return False
            
        if not self.filter_config:
            return True
            
        mode = self.filter_config['mode']
        target_exts = self.filter_config['exts']
        if not target_exts:
            return (True if mode != 'include' else False)
            
        if mode == 'include':
            return ext in target_exts
        elif mode == 'exclude':
            return ext not in target_exts
        return True

    def run(self):
        logging.info("AiScanWorker запущен")
        if not getattr(self, "is_cluster", False):
            if not self.classifier.load_active_references():
                logging.warning("Нет активных эталонов для ИИ-поиска")
                self.finished.emit({})
                return
                
        # 2. Сканируем файлы
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
                    
                    # Исключаем системную папку
                    if '.mediakeeper' in dirs:
                        dirs.remove('.mediakeeper')
                        
                    for f in files_list:
                        if not self.is_running: break
                        if self.is_extension_allowed(f):
                            fp = os.path.join(root, f)
                            valid_files.append(fp)
                            
                        scanned_files += 1
                        if scanned_files % 100 == 0:
                            self.progress.emit(STAGE_SCANNING, 0.0, f"Найдено: {len(valid_files)} изображений...", scanned_files, 0, 0, scanned_bytes, 0, 0)
            except Exception as e:
                logging.error(f"Ошибка при обходе папки {folder}: {e}")

        total_files = len(valid_files)
        if total_files == 0:
            self.finished.emit({})
            return
            
        results = {}
        processed_files = 0
        groups_found = 0
        wasted_bytes = 0 # Суммарный размер найденных файлов
        
        self.progress.emit(STAGE_ANALYSIS, 0.0, f"ИИ Анализ: {total_files} файлов...", scanned_files, 0, 0, scanned_bytes, 0, 0)
        
        # Убедимся, что сессии ONNX инициализированы
        if not self.classifier.ai.initialize_sessions(use_gpu=getattr(self, "use_gpu", True)):
            self.finished.emit({})
            return
            
        cluster_data = []
            
        for fp in valid_files:
            if not self.is_running: break
            
            try:
                stat = os.stat(fp)
                mtime = stat.st_mtime
                size = stat.st_size
                
                if getattr(self, "is_cluster", False):
                    import numpy as np
                    
                    if getattr(self, "cluster_type", "face") == "face":
                        faces = None
                        if self.use_cache:
                            faces = self.classifier.cache.get_file_faces(fp, mtime, size)
                        if faces is None:
                            faces = self.classifier.ai.detect_and_extract_faces(fp)
                            if self.use_cache and faces is not None:
                                self.classifier.cache.save_file_faces(fp, mtime, size, faces)
                                
                        if faces:
                            for face in faces:
                                emb = face["descriptor"]
                                matched = False
                                for cluster in cluster_data:
                                    sim = float(np.dot(emb, cluster["centroid"]))
                                    if sim >= (self.threshold / 100.0):
                                        if not any(m["path"] == fp for m in cluster["members"]):
                                            cluster["members"].append({"path": fp, "size": size, "confidence": sim * 100.0, "type": "face"})
                                        
                                        new_centroid = np.mean([c["emb"] for c in cluster["raw_embs"]] + [emb], axis=0)
                                        norm = np.linalg.norm(new_centroid)
                                        if norm > 0:
                                            new_centroid /= norm
                                        cluster["centroid"] = new_centroid
                                        cluster["raw_embs"].append({"emb": emb})
                                        matched = True
                                        break
                                if not matched:
                                    cluster_data.append({
                                        "centroid": emb,
                                        "raw_embs": [{"emb": emb}],
                                        "members": [{"path": fp, "size": size, "confidence": 100.0, "type": "face"}]
                                    })
                    else:
                        # General clustering
                        emb = None
                        if self.use_cache:
                            emb = self.classifier.cache.get_file_general_embedding(fp, mtime, size)
                        if emb is None:
                            emb = self.classifier.ai.get_general_embedding(fp)
                            if self.use_cache and emb is not None:
                                self.classifier.cache.save_file_general_embedding(fp, mtime, size, emb)
                                
                        if emb is not None:
                            matched = False
                            for cluster in cluster_data:
                                sim = float(np.dot(emb, cluster["centroid"]))
                                if sim >= (self.threshold / 100.0):
                                    if not any(m["path"] == fp for m in cluster["members"]):
                                        cluster["members"].append({"path": fp, "size": size, "confidence": sim * 100.0, "type": "general"})
                                    
                                    new_centroid = np.mean([c["emb"] for c in cluster["raw_embs"]] + [emb], axis=0)
                                    norm = np.linalg.norm(new_centroid)
                                    if norm > 0:
                                        new_centroid /= norm
                                    cluster["centroid"] = new_centroid
                                    cluster["raw_embs"].append({"emb": emb})
                                    matched = True
                                    break
                            if not matched:
                                cluster_data.append({
                                    "centroid": emb,
                                    "raw_embs": [{"emb": emb}],
                                    "members": [{"path": fp, "size": size, "confidence": 100.0, "type": "face"}]
                                })
                else:
                    # Запускаем ИИ сопоставление
                    best_group, confidence, details = self.classifier.match_image(fp, mtime, size, match_mode=self.match_mode, threshold=self.threshold, use_cache=self.use_cache)
                    
                    if best_group and confidence >= self.threshold:
                        if best_group not in results:
                            results[best_group] = []
                            groups_found += 1
                            
                        results[best_group].append({
                            "path": fp,
                            "size": size,
                            "confidence": confidence,
                            "type": details.get("type", "general")
                        })
                        wasted_bytes += size
                    
            except Exception as e:
                logging.error(f"Ошибка ИИ-анализа файла {fp}: {e}")
                
            processed_files += 1
            scanned_bytes += size
            percent = (processed_files / total_files) * 100.0
            
            if processed_files % 5 == 0 or processed_files == total_files:
                self.progress.emit(STAGE_ANALYSIS, percent, f"[{processed_files} / {total_files}]", scanned_files, groups_found, wasted_bytes, scanned_bytes, 0, 0)

        if getattr(self, "is_cluster", False):
            import numpy as np
            
            # Deep merge algorithm (if enabled for face clusters)
            if getattr(self, "cluster_type", "face") == "face":
                from .logic_ai_classifier import load_ai_settings
                settings = load_ai_settings()
                if settings.get("deep_merge_enabled", True):
                    merge_threshold = settings.get("deep_merge_threshold", 75.0) / 100.0
                    merged = True
                    while merged:
                        merged = False
                        for i in range(len(cluster_data)):
                            for j in range(i + 1, len(cluster_data)):
                                sim = float(np.dot(cluster_data[i]["centroid"], cluster_data[j]["centroid"]))
                                if sim >= merge_threshold:
                                    # Merge j into i
                                    cluster_data[i]["members"].extend([m for m in cluster_data[j]["members"] if m["path"] not in [om["path"] for om in cluster_data[i]["members"]]])
                                    cluster_data[i]["raw_embs"].extend(cluster_data[j]["raw_embs"])
                                    
                                    new_centroid = np.mean([c["emb"] for c in cluster_data[i]["raw_embs"]], axis=0)
                                    norm = np.linalg.norm(new_centroid)
                                    if norm > 0:
                                        new_centroid /= norm
                                    cluster_data[i]["centroid"] = new_centroid
                                    
                                    del cluster_data[j]
                                    merged = True
                                    break
                            if merged:
                                break

            # Sort clusters by size
            cluster_data.sort(key=lambda c: len(c["members"]), reverse=True)
            prefix = "Лицо" if getattr(self, "cluster_type", "face") == "face" else "Изображение"
            if not AppContext.is_ru():
                prefix = "Face" if getattr(self, "cluster_type", "face") == "face" else "Image"
                
            for i, cluster in enumerate(cluster_data):
                if len(cluster["members"]) >= 1:
                    group_name = f"{prefix} {i+1}"
                    results[group_name] = cluster["members"]
                    groups_found += 1
                    wasted_bytes += sum(m["size"] for m in cluster["members"])

        # Сортируем результаты в каждой группе по убыванию процентов
        for g in results:
            results[g].sort(key=lambda x: x["confidence"], reverse=True)
            
        if self.is_running:
            self.progress.emit(STAGE_ANALYSIS, 100.0, "Готово", scanned_files, groups_found, wasted_bytes, scanned_bytes, 0, 0)
        self.finished.emit(results)
