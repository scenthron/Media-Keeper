import os
import sqlite3
import numpy as np
import logging
import contextlib

from logic_paths import get_app_data_dir

CURRENT_CACHE_VERSION = 2

class AiCacheManager:
    def __init__(self):
        self.db_path = os.path.join(get_app_data_dir(), "ai_cache.db")
        self._init_db()

    @contextlib.contextmanager
    def _conn(self):
        """Гарантированно закрывает соединение и управляет транзакцией."""
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Создает таблицы базы данных кэша и проверяет версию."""
        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                
                # Создаем таблицу метаданных
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sys_meta (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                """)
                
                # Проверяем версию
                cursor.execute("SELECT value FROM sys_meta WHERE key = 'cache_version'")
                row = cursor.fetchone()
                db_version = int(row[0]) if row else 0
                
                if db_version != CURRENT_CACHE_VERSION:
                    logging.warning(f"Версия кэша устарела ({db_version} != {CURRENT_CACHE_VERSION}). Сброс кэша...")
                    cursor.execute("DROP TABLE IF EXISTS image_embeddings")
                    cursor.execute("DROP TABLE IF EXISTS face_embeddings")
                    cursor.execute("INSERT OR REPLACE INTO sys_meta (key, value) VALUES ('cache_version', ?)", (str(CURRENT_CACHE_VERSION),))
                
                # Таблица для эмбеддингов картинок (CLIP)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS image_embeddings (
                        filepath TEXT PRIMARY KEY,
                        mtime REAL,
                        size INTEGER,
                        embedding BLOB
                    )
                """)
                
                # Таблица для дескрипторов лиц (InsightFace)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS face_embeddings (
                        filepath TEXT,
                        face_index INTEGER,
                        mtime REAL,
                        size INTEGER,
                        bbox TEXT,
                        descriptor BLOB,
                        PRIMARY KEY (filepath, face_index)
                    )
                """)
                
                # Создаем индексы для ускорения поиска
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_face_filepath ON face_embeddings(filepath)")
                conn.commit()
                logging.info(f"База данных кэша ИИ успешно инициализирована по пути: {self.db_path} (Версия: {CURRENT_CACHE_VERSION})")
        except Exception as e:
            logging.error(f"Ошибка инициализации базы данных ИИ-кэша: {e}", exc_info=True)

    def get_image_embedding(self, filepath: str, current_mtime: float, current_size: int) -> np.ndarray | None:
        """
        Возвращает сохраненный вектор изображения (CLIP) из кэша.
        """
        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT mtime, size, embedding FROM image_embeddings WHERE filepath = ?", 
                    (filepath,)
                )
                row = cursor.fetchone()
                
                if row:
                    mtime, size, emb_blob = row
                    if abs(mtime - current_mtime) < 0.01 and size == current_size:
                        return np.frombuffer(emb_blob, dtype=np.float32)
        except Exception as e:
            logging.error(f"Ошибка чтения эмбеддинга из кэша для {filepath}: {e}")
        return None

    def save_image_embedding(self, filepath: str, mtime: float, size: int, embedding: np.ndarray):
        """Сохраняет вектор изображения (CLIP) в кэш."""
        try:
            emb_blob = embedding.astype(np.float32).tobytes()
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO image_embeddings (filepath, mtime, size, embedding)
                    VALUES (?, ?, ?, ?)
                    """,
                    (filepath, mtime, size, emb_blob)
                )
                conn.commit()
        except Exception as e:
            logging.error(f"Ошибка сохранения эмбеддинга в кэш для {filepath}: {e}")

    def get_file_faces(self, filepath: str, current_mtime: float, current_size: int) -> list | None:
        """
        Возвращает список лиц (InsightFace) из кэша.
        """
        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT face_index, mtime, size, bbox, descriptor FROM face_embeddings WHERE filepath = ?",
                    (filepath,)
                )
                rows = cursor.fetchall()
                
                if not rows:
                    return None
                    
                first_face = rows[0]
                mtime, size = first_face[1], first_face[2]
                if abs(mtime - current_mtime) > 0.01 or size != current_size:
                    return None
                    
                faces = []
                for row in rows:
                    face_idx, _, _, bbox_str, desc_blob = row
                    if face_idx == -1:
                        continue
                    
                    bbox = []
                    if bbox_str:
                        bbox = [int(x) for x in bbox_str.split(',')]
                        
                    descriptor = np.frombuffer(desc_blob, dtype=np.float32)
                    faces.append({
                        "bbox": bbox,
                        "descriptor": descriptor
                    })
                return faces
        except Exception as e:
            logging.error(f"Ошибка чтения лиц из кэша для {filepath}: {e}")
        return None

    def save_file_faces(self, filepath: str, mtime: float, size: int, faces: list):
        """Сохраняет список найденных лиц (InsightFace) в кэш."""
        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM face_embeddings WHERE filepath = ?", (filepath,))
                
                if not faces:
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO face_embeddings (filepath, face_index, mtime, size, bbox, descriptor)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (filepath, -1, mtime, size, "", b"")
                    )
                else:
                    for idx, face in enumerate(faces):
                        bbox_str = ",".join(str(int(x)) for x in face["bbox"])
                        desc_blob = face["descriptor"].astype(np.float32).tobytes()
                        cursor.execute(
                            """
                            INSERT OR REPLACE INTO face_embeddings (filepath, face_index, mtime, size, bbox, descriptor)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (filepath, idx, mtime, size, bbox_str, desc_blob)
                        )
                conn.commit()
        except Exception as e:
            logging.error(f"Ошибка сохранения лиц в кэш для {filepath}: {e}")

    def has_cached_files_for_folder(self, folder_path: str) -> tuple[bool, bool]:
        """Проверяет наличие кэшированных файлов для заданной папки. Возвращает (has_general, has_faces)."""
        has_general = False
        has_faces = False
        try:
            prefix = os.path.normpath(folder_path) + os.sep
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM image_embeddings WHERE filepath LIKE ? LIMIT 1", (prefix + "%",))
                if cursor.fetchone():
                    has_general = True
                cursor.execute("SELECT 1 FROM face_embeddings WHERE filepath LIKE ? LIMIT 1", (prefix + "%",))
                if cursor.fetchone():
                    has_faces = True
        except Exception as e:
            logging.error(f"Ошибка проверки кэша для папки {folder_path}: {e}")
        return has_general, has_faces

    def clear_cache(self):
        """Полностью очищает кэш."""
        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM image_embeddings")
                cursor.execute("DELETE FROM face_embeddings")
                conn.commit()
                logging.info("SQLite ИИ-кэш успешно очищен.")
        except Exception as e:
            logging.error(f"Ошибка очистки ИИ-кэша: {e}")
