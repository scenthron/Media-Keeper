import os
import sqlite3
import numpy as np
import logging
import contextlib

from logic_paths import get_app_data_dir

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
        """Создает таблицы базы данных кэша, если они отсутствуют."""
        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                
                # Таблица для эмбеддингов картинок (MobileNetV3)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS image_embeddings (
                        filepath TEXT PRIMARY KEY,
                        mtime REAL,
                        size INTEGER,
                        embedding BLOB
                    )
                """)
                
                # Таблица для дескрипторов лиц (SFace)
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
                logging.info(f"База данных кэша ИИ успешно инициализирована по пути: {self.db_path}")
        except Exception as e:
            logging.error(f"Ошибка инициализации базы данных ИИ-кэша: {e}", exc_info=True)

    def get_image_embedding(self, filepath: str, current_mtime: float, current_size: int) -> np.ndarray | None:
        """
        Возвращает сохраненный вектор изображения из кэша, если дата изменения и размер совпадают.
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
                    # Проверяем актуальность файла по дате изменения и размеру
                    if abs(mtime - current_mtime) < 0.01 and size == current_size:
                        # Десериализуем вектор из байтов
                        return np.frombuffer(emb_blob, dtype=np.float32)
        except Exception as e:
            logging.error(f"Ошибка чтения эмбеддинга из кэша для {filepath}: {e}")
        return None

    def save_image_embedding(self, filepath: str, mtime: float, size: int, embedding: np.ndarray):
        """Сохраняет вектор изображения в кэш."""
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
        Возвращает список лиц, найденных на изображении, из кэша (если файл актуален).
        Возвращает list(dict) или None (если файла нет в кэше).
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
                    
                # Проверим актуальность файла по первому лицу
                first_face = rows[0]
                mtime, size = first_face[1], first_face[2]
                if abs(mtime - current_mtime) > 0.01 or size != current_size:
                    # Файл изменился, кэш неактуален
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
        """Сохраняет список найденных лиц файла в кэш."""
        try:
            with self._conn() as conn:
                cursor = conn.cursor()
                # Сначала удалим старые записи для этого файла
                cursor.execute("DELETE FROM face_embeddings WHERE filepath = ?", (filepath,))
                
                # Если лиц не найдено, мы записываем специальную запись-пустышку (face_index = -1),
                # чтобы при следующем сканировании знать, что файл уже был просканирован и на нем нет лиц.
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
                        bbox_str = ",".join(str(x) for x in face["bbox"])
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
