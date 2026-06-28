
import sqlite3
import os
import logging

class CleanerDB:
    DB_NAME = "cleaner_cache.db"
    def __init__(self, root_dir=None):
        if root_dir is None:
            from logic_paths import get_app_data_dir
            self.db_dir = get_app_data_dir()
        else:
            self.db_dir = os.path.join(root_dir, ".mediakeeper")
        if not os.path.exists(self.db_dir):
            try: os.makedirs(self.db_dir)
            except Exception as e: logging.error(f"Failed to create db dir: {e}")
        self.db_path = os.path.join(self.db_dir, self.DB_NAME)
        self.init_db()

    def init_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS file_hashes (
                    path TEXT PRIMARY KEY,
                    size INTEGER,
                    mtime REAL,
                    partial_hash TEXT,
                    full_hash TEXT
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_size ON file_hashes(size)')
            conn.commit()
            conn.close()
        except Exception as e: logging.error(f"DB Init Error: {e}")

    def get_cached_data(self, path, size, mtime):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT size, mtime, partial_hash, full_hash FROM file_hashes WHERE path = ?', (path,))
            row = cursor.fetchone()
            conn.close()
            if row:
                cached_size, cached_mtime, p_hash, f_hash = row
                if cached_size == size and abs(cached_mtime - mtime) < 0.001:
                    return p_hash, f_hash
            return None
        except Exception as e:
            logging.error(f"DB Read Error: {e}")
            return None

    def upsert_hash(self, path, size, mtime, partial_hash, full_hash=None):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO file_hashes (path, size, mtime, partial_hash, full_hash)
                VALUES (?, ?, ?, ?, ?)
            ''', (path, size, mtime, partial_hash, full_hash))
            conn.commit()
            conn.close()
        except Exception as e: logging.error(f"DB Write Error: {e}")

    def check_path_scanned(self, folder_path):
        try:
            folder = os.path.normpath(folder_path)
            pattern = f"{folder_path}%"
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM file_hashes WHERE path LIKE ? LIMIT 1", (pattern,))
            row = cursor.fetchone()
            conn.close()
            return row is not None
        except: return False

class SimilarDB:
    DB_NAME = "similar_cache.db"
    def __init__(self, root_dir=None):
        if root_dir is None:
            from logic_paths import get_app_data_dir
            self.db_dir = get_app_data_dir()
        else:
            self.db_dir = os.path.join(root_dir, ".mediakeeper")
        if not os.path.exists(self.db_dir):
            try: os.makedirs(self.db_dir)
            except Exception as e: logging.error(f"Failed to create db dir: {e}")
        self.db_path = os.path.join(self.db_dir, self.DB_NAME)
        self.init_db()

    def init_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS file_signatures (
                    path TEXT PRIMARY KEY,
                    size INTEGER,
                    mtime REAL,
                    signature TEXT
                )
            ''')
            conn.commit()
            conn.close()
        except Exception as e: logging.error(f"Similar DB Init Error: {e}")

    def get_cached_signature(self, path, size, mtime):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT size, mtime, signature FROM file_signatures WHERE path = ?', (path,))
            row = cursor.fetchone()
            conn.close()
            if row:
                cached_size, cached_mtime, signature = row
                if cached_size == size and abs(cached_mtime - mtime) < 0.001:
                    return signature
            return None
        except Exception as e:
            logging.error(f"Similar DB Read Error: {e}")
            return None

    def upsert_signature(self, path, size, mtime, signature):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO file_signatures (path, size, mtime, signature)
                VALUES (?, ?, ?, ?)
            ''', (path, size, mtime, signature))
            conn.commit()
            conn.close()
        except Exception as e: logging.error(f"Similar DB Write Error: {e}")

    def check_path_scanned(self, folder_path):
        try:
            folder = os.path.normpath(folder_path)
            pattern = f"{folder_path}%"
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM file_signatures WHERE path LIKE ? LIMIT 1", (pattern,))
            row = cursor.fetchone()
            conn.close()
            return row is not None
        except: return False
