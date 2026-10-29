import sqlite3
import os
import logging
import threading
import contextlib

CURRENT_CACHE_VERSION = 1

class CleanerDB:
    DB_NAME = "cleaner_cache.db"

    def __init__(self, root_dir=None):
        self._lock = threading.Lock()
        self._local_conn = None
        if root_dir is None:
            from logic_paths import get_app_data_dir
            self.db_dir = get_app_data_dir()
        else:
            self.db_dir = os.path.join(root_dir, ".mediakeeper")
        if not os.path.exists(self.db_dir):
            try:
                os.makedirs(self.db_dir, exist_ok=True)
            except Exception as e:
                logging.error(f"Failed to create db dir: {e}")
        self.db_path = os.path.join(self.db_dir, self.DB_NAME)
        self.init_db()

    def _get_connection(self):
        if self._local_conn is None:
            self._local_conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
            self._local_conn.execute("PRAGMA journal_mode=WAL;")
            self._local_conn.execute("PRAGMA synchronous=NORMAL;")
        return self._local_conn

    @contextlib.contextmanager
    def _conn(self):
        """Thread-safe connection context manager."""
        with self._lock:
            conn = self._get_connection()
            try:
                yield conn
            except Exception:
                conn.rollback()
                raise

    def init_db(self):
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
                    logging.warning(f"CleanerDB cache version mismatch ({db_version} != {CURRENT_CACHE_VERSION}). Resetting cache...")
                    cursor.execute("DROP TABLE IF EXISTS file_hashes")
                    cursor.execute("INSERT OR REPLACE INTO sys_meta (key, value) VALUES ('cache_version', ?)", (str(CURRENT_CACHE_VERSION),))

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS file_hashes (
                        path TEXT PRIMARY KEY,
                        size INTEGER,
                        mtime REAL,
                        partial_hash TEXT,
                        full_hash TEXT
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_size ON file_hashes(size)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_path_nocase ON file_hashes(path COLLATE NOCASE)")
                conn.commit()
        except Exception as e:
            logging.error(f"CleanerDB Init Error: {e}", exc_info=True)

    def get_cached_data(self, path, size, mtime):
        """Single file read: returns (partial_hash, full_hash) or None if invalid/missing."""
        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT size, mtime, partial_hash, full_hash FROM file_hashes WHERE path = ?", (path,))
                row = cursor.fetchone()
                if row:
                    cached_size, cached_mtime, p_hash, f_hash = row
                    if cached_size == size and abs(cached_mtime - mtime) < 0.001:
                        return p_hash, f_hash
            return None
        except Exception as e:
            logging.error(f"CleanerDB Read Error: {e}")
            return None

    # Alias for get_cached_data for backward compatibility
    get_cached_hash = get_cached_data

    def upsert_hash(self, path, size, mtime, partial_hash, full_hash=None):
        """Single file write."""
        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO file_hashes (path, size, mtime, partial_hash, full_hash)
                    VALUES (?, ?, ?, ?, ?)
                """, (path, size, mtime, partial_hash, full_hash))
                conn.commit()
        except Exception as e:
            logging.error(f"CleanerDB Write Error: {e}")

    # Alias for upsert_hash for backward compatibility
    set_cached_hash = upsert_hash

    def set_cached_batch(self, items: list[tuple[str, int, float, str, str | None]]):
        """Batch write: items is a list of tuples (path, size, mtime, partial_hash, full_hash)."""
        if not items:
            return
        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.executemany("""
                    INSERT OR REPLACE INTO file_hashes (path, size, mtime, partial_hash, full_hash)
                    VALUES (?, ?, ?, ?, ?)
                """, items)
                conn.commit()
        except Exception as e:
            logging.error(f"CleanerDB Batch Write Error: {e}")

    def get_cached_batch(self, paths: list[str]) -> dict[str, tuple[int, float, str, str | None]]:
        """Batch read: returns {path: (size, mtime, partial_hash, full_hash)}."""
        if not paths:
            return {}
        result = {}
        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                chunk_size = 500
                for i in range(0, len(paths), chunk_size):
                    chunk = paths[i:i + chunk_size]
                    placeholders = ','.join('?' * len(chunk))
                    cursor.execute(f"""
                        SELECT path, size, mtime, partial_hash, full_hash 
                        FROM file_hashes 
                        WHERE path IN ({placeholders})
                    """, chunk)
                    for row in cursor.fetchall():
                        result[row[0]] = (row[1], row[2], row[3], row[4])
        except Exception as e:
            logging.error(f"CleanerDB Batch Read Error: {e}")
        return result

    def check_path_scanned(self, folder_path):
        from utils_io import strip_long_path_prefix
        try:
            clean = strip_long_path_prefix(os.path.normpath(folder_path))
            p_back = clean.replace('/', '\\').rstrip('\\') + '\\%'
            p_fwd = clean.replace('\\', '/').rstrip('/') + '/%'
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 1 FROM file_hashes 
                    WHERE path LIKE ? OR path LIKE ? 
                    LIMIT 1
                """, (p_back, p_fwd))
                return cursor.fetchone() is not None
        except Exception:
            return False

    def clear_cache(self):
        """Clear cache tables and compact database with VACUUM."""
        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM file_hashes;")
                conn.commit()
                cursor.execute("VACUUM;")
                cursor.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                conn.commit()
                logging.info("CleanerDB cache cleared and vacuumed.")
        except Exception as e:
            logging.error(f"CleanerDB Clear Cache Error: {e}")
            self.close()
            for p in [self.db_path, f"{self.db_path}-wal", f"{self.db_path}-shm"]:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            self.init_db()

    def close(self):
        """Explicitly close connection."""
        with self._lock:
            if self._local_conn is not None:
                try:
                    self._local_conn.close()
                except Exception:
                    pass
                self._local_conn = None

    def __del__(self):
        self.close()


class SimilarDB:
    DB_NAME = "similar_cache.db"

    def __init__(self, root_dir=None, hash_size=16, algorithm="phash", video_frames=None):
        self._lock = threading.Lock()
        self._local_conn = None
        self.hash_size = hash_size
        self.algorithm = algorithm.lower()
        self.video_frames = video_frames
        self.table_name = f"file_sigs_{self.algorithm}_{self.hash_size}"
        if self.video_frames is not None:
            self.table_name += f"_vf_{self.video_frames}"
        if root_dir is None:
            from logic_paths import get_app_data_dir
            self.db_dir = get_app_data_dir()
        else:
            self.db_dir = os.path.join(root_dir, ".mediakeeper")
        if not os.path.exists(self.db_dir):
            try:
                os.makedirs(self.db_dir, exist_ok=True)
            except Exception as e:
                logging.error(f"Failed to create db dir: {e}")
        self.db_path = os.path.join(self.db_dir, self.DB_NAME)
        self.init_db()

    def _get_connection(self):
        if self._local_conn is None:
            self._local_conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
            self._local_conn.execute("PRAGMA journal_mode=WAL;")
            self._local_conn.execute("PRAGMA synchronous=NORMAL;")
        return self._local_conn

    @contextlib.contextmanager
    def _conn(self):
        """Thread-safe connection context manager."""
        with self._lock:
            conn = self._get_connection()
            try:
                yield conn
            except Exception:
                conn.rollback()
                raise

    def init_db(self):
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
                    logging.warning(f"SimilarDB cache version mismatch ({db_version} != {CURRENT_CACHE_VERSION}). Resetting cache tables...")
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'file_sigs_%'")
                    tables = [r[0] for r in cursor.fetchall()]
                    for tbl in tables:
                        cursor.execute(f"DROP TABLE IF EXISTS {tbl}")
                    cursor.execute("INSERT OR REPLACE INTO sys_meta (key, value) VALUES ('cache_version', ?)", (str(CURRENT_CACHE_VERSION),))

                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.table_name} (
                        path TEXT PRIMARY KEY,
                        size INTEGER,
                        mtime REAL,
                        signature TEXT
                    )
                """)
                cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_path_nocase ON {self.table_name}(path COLLATE NOCASE)")
                conn.commit()
        except Exception as e:
            logging.error(f"Similar DB Init Error: {e}", exc_info=True)

    def get_cached_signature(self, path, size, mtime):
        """Single file read: returns signature or None."""
        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT size, mtime, signature FROM {self.table_name} WHERE path = ?", (path,))
                row = cursor.fetchone()
                if row:
                    cached_size, cached_mtime, signature = row
                    if cached_size == size and abs(cached_mtime - mtime) < 0.001:
                        return signature
            return None
        except Exception as e:
            logging.error(f"Similar DB Read Error: {e}")
            return None

    # Alias for get_cached_signature for backward compatibility
    get_cached_hash = get_cached_signature

    def upsert_signature(self, path, size, mtime, signature):
        """Single file write."""
        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    INSERT OR REPLACE INTO {self.table_name} (path, size, mtime, signature)
                    VALUES (?, ?, ?, ?)
                """, (path, size, mtime, signature))
                conn.commit()
        except Exception as e:
            logging.error(f"Similar DB Write Error: {e}")

    # Alias for upsert_signature for backward compatibility
    set_cached_hash = upsert_signature

    def set_cached_batch(self, items: list[tuple[str, int, float, str]]):
        """Batch write: items is a list of tuples (path, size, mtime, signature)."""
        if not items:
            return
        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.executemany(f"""
                    INSERT OR REPLACE INTO {self.table_name} (path, size, mtime, signature)
                    VALUES (?, ?, ?, ?)
                """, items)
                conn.commit()
        except Exception as e:
            logging.error(f"SimilarDB Batch Write Error: {e}")

    def get_cached_batch(self, paths: list[str]) -> dict[str, tuple[int, float, str]]:
        """Batch read: returns {path: (size, mtime, signature)}."""
        if not paths:
            return {}
        result = {}
        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                chunk_size = 500
                for i in range(0, len(paths), chunk_size):
                    chunk = paths[i:i + chunk_size]
                    placeholders = ','.join('?' * len(chunk))
                    cursor.execute(f"""
                        SELECT path, size, mtime, signature 
                        FROM {self.table_name} 
                        WHERE path IN ({placeholders})
                    """, chunk)
                    for row in cursor.fetchall():
                        result[row[0]] = (row[1], row[2], row[3])
        except Exception as e:
            logging.error(f"SimilarDB Batch Read Error: {e}")
        return result

    def check_path_scanned(self, folder_path):
        from utils_io import strip_long_path_prefix
        try:
            clean = strip_long_path_prefix(os.path.normpath(folder_path))
            p_back = clean.replace('/', '\\').rstrip('\\') + '\\%'
            p_fwd = clean.replace('\\', '/').rstrip('/') + '/%'
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT 1 FROM {self.table_name} 
                    WHERE path LIKE ? OR path LIKE ? 
                    LIMIT 1
                """, (p_back, p_fwd))
                return cursor.fetchone() is not None
        except Exception:
            return False

    def clear_cache(self):
        """Clear cache table and vacuum the database."""
        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute(f"DELETE FROM {self.table_name};")
                conn.commit()
                cursor.execute("VACUUM;")
                cursor.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                conn.commit()
                logging.info(f"SimilarDB cache table {self.table_name} cleared and vacuumed.")
        except Exception as e:
            logging.error(f"SimilarDB Clear Cache Error: {e}")
            self.close()
            for p in [self.db_path, f"{self.db_path}-wal", f"{self.db_path}-shm"]:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            self.init_db()

    def close(self):
        """Explicitly close connection."""
        with self._lock:
            if self._local_conn is not None:
                try:
                    self._local_conn.close()
                except Exception:
                    pass
                self._local_conn = None

    def __del__(self):
        self.close()
