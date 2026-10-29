import os
import cv2
import numpy as np
import logging
import sqlite3
import threading
import contextlib
import zlib
from collections import OrderedDict

from logic_paths import get_app_data_dir
from utils_io import safe_cv2_imread, ensure_long_path, strip_long_path_prefix

CURRENT_CACHE_VERSION = 1
MAX_MEMORY_CACHE_ITEMS = 150

class OrbEngine:
    def match_template(self, frag_bgr, target_bgr, tolerance, optimize_bw=False):
        # Пиксельный поиск через cv2.matchTemplate
        try:
            if frag_bgr is None or target_bgr is None:
                return False, None, 0
                
            frag_h, frag_w = frag_bgr.shape[:2]
            target_h, target_w = target_bgr.shape[:2]
            
            if frag_h > target_h or frag_w > target_w:
                return False, None, 0
                
            if optimize_bw:
                if len(frag_bgr.shape) == 3:
                    frag_img = cv2.cvtColor(frag_bgr, cv2.COLOR_BGR2GRAY)
                else:
                    frag_img = frag_bgr
                if len(target_bgr.shape) == 3:
                    target_img = cv2.cvtColor(target_bgr, cv2.COLOR_BGR2GRAY)
                else:
                    target_img = target_bgr
            else:
                frag_img = frag_bgr
                target_img = target_bgr
                
            res = cv2.matchTemplate(target_img, frag_img, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            
            # tolerance в UI от 0 до 100. 100 = 0.99, 0 = 0.70
            threshold = 0.7 + (tolerance / 100.0) * 0.29
            
            if max_val >= threshold:
                x, y = max_loc
                # Возвращаем рамку как полигон
                bbox = np.int32([[[x, y]], [[x, y + frag_h]], [[x + frag_w, y + frag_h]], [[x + frag_w, y]]])
                return True, bbox, int(max_val * 100)
            return False, None, 0
        except Exception as e:
            logging.error(f"[TemplateMatch] Error: {e}")
            return False, None, 0

    """Движок для поиска фрагментов на основе ORB/SIFT Feature Matching."""
    
    def __init__(self, max_features=0):
        # Инициализация SIFT (работает гораздо точнее для вырезанных фрагментов)
        self.orb = cv2.SIFT_create(nfeatures=10000)
        
        # Настройка матчера (для SIFT используется NORM_L2)
        self.matcher = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
        
    def _resize_if_needed(self, img, max_dim=1920):
        """Уменьшает изображение, если оно слишком большое, для скорости."""
        h, w = img.shape[:2]
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            new_w, new_h = int(w * scale), int(h * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            return img, scale
        return img, 1.0

    def extract_features(self, image_path, max_dim=1920):
        """Извлекает ключевые точки и дескрипторы из изображения."""
        img = safe_cv2_imread(image_path)
        if img is None:
            return None, None, None, 1.0
            
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray, scale = self._resize_if_needed(gray, max_dim)
        
        # Извлекаем ключевые точки и дескрипторы
        keypoints, descriptors = self.orb.detectAndCompute(gray, None)
        return keypoints, descriptors, img.shape[:2], scale

    def extract_features_from_img(self, img_bgr, max_dim=1920):
        """Извлекает признаки напрямую из BGR numpy массива (используется для вырезанного фрагмента)."""
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        gray, scale = self._resize_if_needed(gray, max_dim)
        keypoints, descriptors = self.orb.detectAndCompute(gray, None)
        return keypoints, descriptors, img_bgr.shape[:2], scale

    def match(self, frag_kp, frag_desc, frag_shape, target_kp, target_desc, target_scale=1.0, 
              ratio_thresh=0.75, min_match_count=10):
        """
        Ищет фрагмент в целевом изображении.
        Возвращает: (успех (bool), рамка (tuple of points) или None, кол-во хороших совпадений)
        """
        if frag_desc is None or target_desc is None or len(frag_desc) < 2 or len(target_desc) < 2:
            return False, None, 0
            
        try:
            # Ищем 2 лучших совпадения для каждой точки
            matches = self.matcher.knnMatch(frag_desc, target_desc, k=2)
            
            # Применяем Lowe's ratio test
            good_matches = []
            for m_n in matches:
                if len(m_n) != 2:
                    continue
                m, n = m_n
                if m.distance < ratio_thresh * n.distance:
                    good_matches.append(m)
                    
            if len(good_matches) >= min_match_count:
                # Находим координаты ключевых точек
                src_pts = np.float32([frag_kp[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
                dst_pts = np.float32([target_kp[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
                
                # Ищем гомографию (перспективное преобразование)
                M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
                
                if M is not None:
                    h, w = frag_shape[:2]
                    # Точки углов фрагмента
                    pts = np.float32([[0, 0], [0, h - 1], [w - 1, h - 1], [w - 1, 0]]).reshape(-1, 1, 2)
                    
                    # Трансформируем углы фрагмента на целевое изображение
                    dst = cv2.perspectiveTransform(pts, M)
                    
                    # Возвращаем рамку с учетом скейла целевого изображения
                    # target_scale - это во сколько раз мы уменьшили картинку при извлечении.
                    # Чтобы получить координаты на оригинале, делим на target_scale
                    if target_scale != 1.0 and target_scale > 0:
                        dst = dst / target_scale
                        
                    # Преобразуем в целые координаты
                    bounding_box = np.int32(dst)
                    return True, bounding_box, len(good_matches)
                    
            return False, None, len(good_matches)
        except Exception as e:
            logging.error(f"[ORB] Matcher error: {e}")
            return False, None, 0


class OrbCacheManager:
    """
    Менеджер для сохранения и загрузки дескрипторов SIFT/ORB в компактную базу SQLite.
    Поддерживает WAL-режим, сжатие дескрипторов через zlib и строгий LRU-кэш в ОЗУ.
    """
    DB_NAME = "sift_cache.db"

    def __init__(self, max_memory_items: int = MAX_MEMORY_CACHE_ITEMS):
        self.cache_dir = os.path.join(get_app_data_dir(), "cache", "orb")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.db_path = os.path.join(self.cache_dir, self.DB_NAME)

        self._lock = threading.Lock()
        self._local_conn = None
        self.max_memory_items = max_memory_items
        self.memory_cache = OrderedDict()

        self.init_db()
        self._cleanup_legacy_pkl_files()

    def _get_connection(self):
        if self._local_conn is None:
            self._local_conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
            self._local_conn.execute("PRAGMA journal_mode=WAL;")
            self._local_conn.execute("PRAGMA synchronous=NORMAL;")
        return self._local_conn

    @contextlib.contextmanager
    def _conn(self):
        with self._lock:
            conn = self._get_connection()
            try:
                yield conn
            except Exception:
                conn.rollback()
                raise

    def init_db(self):
        """Инициализирует структуру SQLite-базы кэша и проверяет версию."""
        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sys_meta (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                """)
                cursor.execute("SELECT value FROM sys_meta WHERE key = 'cache_version'")
                row = cursor.fetchone()
                db_version = int(row[0]) if row and row[0] is not None and str(row[0]).isdigit() else 0

                if db_version != CURRENT_CACHE_VERSION:
                    logging.warning(f"OrbCacheManager cache version mismatch ({db_version} != {CURRENT_CACHE_VERSION}). Resetting cache...")
                    cursor.execute("DROP TABLE IF EXISTS sift_features")
                    cursor.execute("INSERT OR REPLACE INTO sys_meta (key, value) VALUES ('cache_version', ?)", (str(CURRENT_CACHE_VERSION),))

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sift_features (
                        filepath TEXT PRIMARY KEY,
                        size INTEGER,
                        mtime REAL,
                        scale REAL,
                        kp_data BLOB,
                        desc_shape TEXT,
                        desc_dtype TEXT,
                        desc_data BLOB
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_sift_mtime ON sift_features(mtime)")
                conn.commit()
        except Exception as e:
            logging.error(f"[OrbCacheManager] Init DB error: {e}", exc_info=True)

    def _cleanup_legacy_pkl_files(self):
        """Асинхронно удаляет старые .pkl файлы в фоновом потоке, не замедляя UI."""
        def _cleanup():
            try:
                if not os.path.exists(self.cache_dir):
                    return
                for fname in os.listdir(self.cache_dir):
                    if fname.lower().endswith(".pkl"):
                        fpath = os.path.join(self.cache_dir, fname)
                        try:
                            os.remove(fpath)
                        except Exception as err:
                            logging.debug(f"[OrbCacheManager] Failed to remove legacy pkl {fpath}: {err}")
            except Exception as e:
                logging.debug(f"[OrbCacheManager] Legacy cleanup notice: {e}")

        t = threading.Thread(target=_cleanup, daemon=True, name="OrbLegacyPklCleanup")
        t.start()

    def _put_memory_cache(self, key: str, val):
        """Сохраняет элемент в LRU RAM кэш, вытесняя старые при превышении лимита."""
        with self._lock:
            self.memory_cache[key] = val
            self.memory_cache.move_to_end(key)
            if len(self.memory_cache) > self.max_memory_items:
                self.memory_cache.popitem(last=False)

    def load_cache(self, filepath: str):
        """
        Загружает кэш (keypoints, descriptors, scale) для файла.
        Сначала проверяет LRU-кэш в ОЗУ, затем сжатую базу SQLite.
        Проверяет размер и mtime: при изменении файла на диске возвращает (None, None, 1.0).
        """
        clean_path = os.path.normcase(os.path.normpath(strip_long_path_prefix(filepath)))

        # 1. Проверка LRU RAM кэша
        with self._lock:
            if clean_path in self.memory_cache:
                self.memory_cache.move_to_end(clean_path)
                return self.memory_cache[clean_path]

        # 2. Проверка соответствия размера и даты файла
        try:
            stat = os.stat(ensure_long_path(filepath))
            cur_size = stat.st_size
            cur_mtime = stat.st_mtime
        except Exception:
            return None, None, 1.0

        # 3. Чтение из SQLite
        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT size, mtime, scale, kp_data, desc_shape, desc_dtype, desc_data
                    FROM sift_features
                    WHERE filepath = ?
                """, (clean_path,))
                row = cursor.fetchone()

            if not row:
                return None, None, 1.0

            cached_size, cached_mtime, scale, kp_data, desc_shape_str, desc_dtype, desc_data = row
            if cached_size != cur_size or abs(cached_mtime - cur_mtime) >= 0.001:
                return None, None, 1.0

            # Десериализация ключевых точек
            if kp_data:
                raw_kp = zlib.decompress(kp_data)
                arr = np.frombuffer(raw_kp, dtype=np.float32).reshape(-1, 7)
                keypoints = [
                    cv2.KeyPoint(
                        x=float(r[0]),
                        y=float(r[1]),
                        size=float(r[2]),
                        angle=float(r[3]),
                        response=float(r[4]),
                        octave=int(r[5]),
                        class_id=int(r[6])
                    )
                    for r in arr
                ]
            else:
                keypoints = []

            # Десериализация дескрипторов
            if desc_data and desc_shape_str:
                shape = tuple(int(s) for s in desc_shape_str.split(","))
                raw_desc = zlib.decompress(desc_data)
                descriptors = np.frombuffer(raw_desc, dtype=desc_dtype).reshape(shape)
            else:
                descriptors = None

            val = (keypoints, descriptors, scale)
            self._put_memory_cache(clean_path, val)
            return val
        except Exception as e:
            logging.error(f"[OrbCacheManager] Failed to load cache for {filepath}: {e}")
            return None, None, 1.0

    def save_cache(self, filepath: str, keypoints, descriptors, scale: float):
        """Сохраняет признаки в SQLite со сжатием zlib и обновляет LRU RAM кэш."""
        if descriptors is None:
            return

        clean_path = os.path.normcase(os.path.normpath(strip_long_path_prefix(filepath)))
        try:
            stat = os.stat(ensure_long_path(filepath))
            cur_size = stat.st_size
            cur_mtime = stat.st_mtime
        except Exception:
            cur_size = 0
            cur_mtime = 0.0

        # Сериализация ключевых точек в бинарный буфер
        if keypoints:
            N = len(keypoints)
            arr = np.empty((N, 7), dtype=np.float32)
            for i, kp in enumerate(keypoints):
                arr[i] = (kp.pt[0], kp.pt[1], kp.size, kp.angle, kp.response, kp.octave, kp.class_id)
            kp_data = zlib.compress(arr.tobytes(), level=1)
        else:
            kp_data = b""

        # Сериализация дескрипторов в сжатый буфер
        desc_shape_str = ",".join(str(s) for s in descriptors.shape)
        desc_dtype = descriptors.dtype.str
        desc_data = zlib.compress(descriptors.tobytes(), level=1)

        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO sift_features
                    (filepath, size, mtime, scale, kp_data, desc_shape, desc_dtype, desc_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (clean_path, cur_size, cur_mtime, scale, kp_data, desc_shape_str, desc_dtype, desc_data))
                conn.commit()
        except Exception as e:
            logging.error(f"[OrbCacheManager] Failed to save cache for {filepath}: {e}")

        # Добавляем в оперативный LRU-кэш
        self._put_memory_cache(clean_path, (keypoints, descriptors, scale))

    def clear_memory(self):
        """Очищает оперативную память."""
        with self._lock:
            self.memory_cache.clear()

    def clear_disk_cache(self):
        """Очищает кэш на диске (TRUNCATE + VACUUM) и очищает RAM-кэш."""
        self.clear_memory()
        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM sift_features;")
                conn.commit()
                cursor.execute("VACUUM;")
                cursor.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                conn.commit()
            logging.info("[ORB Cache] Disk cache SQLite cleared and vacuumed.")
        except Exception as e:
            logging.error(f"[ORB Cache] Clear disk cache failed: {e}")
            self.close()
            for p in [self.db_path, f"{self.db_path}-wal", f"{self.db_path}-shm"]:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            self.init_db()

        # Также удаляем любые оставшиеся устаревшие .pkl
        try:
            if os.path.exists(self.cache_dir):
                for f in os.listdir(self.cache_dir):
                    if f.lower().endswith(".pkl"):
                        try:
                            os.remove(os.path.join(self.cache_dir, f))
                        except Exception:
                            pass
        except Exception:
            pass

    def get_cache_size(self) -> int:
        """Возвращает суммарный размер файлов кэша на диске в байтах."""
        total = 0
        try:
            for p in [self.db_path, f"{self.db_path}-wal", f"{self.db_path}-shm"]:
                if os.path.exists(p):
                    total += os.path.getsize(p)
        except Exception:
            pass
        return total

    def close(self):
        """Закрывает открытое соединение SQLite."""
        with self._lock:
            if self._local_conn is not None:
                try:
                    self._local_conn.close()
                except Exception:
                    pass
                self._local_conn = None

    def __del__(self):
        self.close()
