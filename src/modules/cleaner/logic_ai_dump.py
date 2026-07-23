import sqlite3
import os
import shutil
import numpy as np
import tempfile
import logging
from typing import List, Tuple, Dict, Any

def create_tables(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            is_positive INTEGER,
            filename TEXT,
            data BLOB
        )
    """)
    # Для CLIP векторов
    cur.execute("""
        CREATE TABLE IF NOT EXISTS features (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            is_positive INTEGER,
            feature_vector BLOB
        )
    """)
    # Для InsightFace векторов
    cur.execute("""
        CREATE TABLE IF NOT EXISTS faces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            is_positive INTEGER,
            face_vector BLOB
        )
    """)
    conn.commit()

def save_dump(
    path: str,
    search_type: str,
    pos_image_paths: List[str],
    neg_image_paths: List[str],
    pos_features: List[np.ndarray],
    neg_features: List[np.ndarray],
    pos_faces: List[np.ndarray],
    neg_faces: List[np.ndarray],
    is_hash_only: bool = False
):
    """Создает или обновляет файл .mkaidump."""
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception as e:
            logging.error(f"Cannot overwrite dump {path}: {e}")
            
    conn = sqlite3.connect(path)
    try:
        create_tables(conn)
        cur = conn.cursor()
        
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("type", search_type))
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("is_hash_only", "1" if is_hash_only else "0"))
        
        if not is_hash_only:
            for p_path in pos_image_paths:
                if os.path.exists(p_path):
                    with open(p_path, 'rb') as f:
                        data = f.read()
                    filename = os.path.basename(p_path)
                    cur.execute("INSERT INTO images (is_positive, filename, data) VALUES (?, ?, ?)", (1, filename, data))
                    
            for n_path in neg_image_paths:
                if os.path.exists(n_path):
                    with open(n_path, 'rb') as f:
                        data = f.read()
                    filename = os.path.basename(n_path)
                    cur.execute("INSERT INTO images (is_positive, filename, data) VALUES (?, ?, ?)", (0, filename, data))
                    
        def insert_vectors(table_name, is_pos, vectors):
            for feat in vectors:
                if feat is None: continue
                feat_bytes = feat.tobytes()
                shape_str = ','.join(map(str, feat.shape))
                dtype_str = str(feat.dtype)
                header = f"{shape_str}|{dtype_str}|".encode('utf-8')
                full_blob = header + feat_bytes
                cur.execute(f"INSERT INTO {table_name} (is_positive, {'feature_vector' if table_name == 'features' else 'face_vector'}) VALUES (?, ?)", (1 if is_pos else 0, full_blob))

        insert_vectors("features", True, pos_features)
        insert_vectors("features", False, neg_features)
        insert_vectors("faces", True, pos_faces)
        insert_vectors("faces", False, neg_faces)
            
        conn.commit()
    finally:
        conn.close()

def load_dump_info(path: str) -> Dict[str, Any]:
    """Возвращает информацию о дампе."""
    if not os.path.exists(path):
        return {}
        
    try:
        conn = sqlite3.connect(path)
        try:
            cur = conn.cursor()
            
            cur.execute("SELECT key, value FROM settings")
            settings = {row[0]: row[1] for row in cur.fetchall()}
            
            cur.execute("SELECT COUNT(*) FROM images WHERE is_positive=1")
            pos_images_count = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM images WHERE is_positive=0")
            neg_images_count = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM features WHERE is_positive=1")
            pos_features_count = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM features WHERE is_positive=0")
            neg_features_count = cur.fetchone()[0]
            
            try:
                cur.execute("SELECT COUNT(*) FROM faces WHERE is_positive=1")
                pos_faces_count = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM faces WHERE is_positive=0")
                neg_faces_count = cur.fetchone()[0]
            except:
                pos_faces_count = 0
                neg_faces_count = 0
            
            return {
                "type": settings.get("type", "face"),
                "is_hash_only": settings.get("is_hash_only", "0") == "1",
                "pos_images_count": pos_images_count,
                "neg_images_count": neg_images_count,
                "pos_features_count": pos_features_count,
                "neg_features_count": neg_features_count,
                "pos_faces_count": pos_faces_count,
                "neg_faces_count": neg_faces_count
            }
        finally:
            conn.close()
    except Exception as e:
        logging.error(f"Error loading dump info from {path}: {e}")
        return {}

def extract_images_to_temp(path: str) -> Tuple[str, List[str], List[str]]:
    temp_dir = tempfile.mkdtemp(prefix="mkaidump_")
    pos_paths = []
    neg_paths = []
    if not os.path.exists(path): return temp_dir, pos_paths, neg_paths
        
    try:
        conn = sqlite3.connect(path)
        try:
            cur = conn.cursor()
            cur.execute("SELECT is_positive, filename, data FROM images")
            for is_pos, filename, data in cur.fetchall():
                out_path = os.path.join(temp_dir, f"{'pos' if is_pos else 'neg'}_{filename}")
                counter = 1
                base, ext = os.path.splitext(out_path)
                while os.path.exists(out_path):
                    out_path = f"{base}_{counter}{ext}"
                    counter += 1
                with open(out_path, 'wb') as f:
                    f.write(data)
                if is_pos: pos_paths.append(out_path)
                else: neg_paths.append(out_path)
        finally:
            conn.close()
    except Exception as e:
        logging.error(f"Error extracting images from {path}: {e}")
    return temp_dir, pos_paths, neg_paths

def extract_images_to_dir(path: str, dest_dir: str):
    os.makedirs(dest_dir, exist_ok=True)
    if not os.path.exists(path): return
        
    try:
        conn = sqlite3.connect(path)
        try:
            cur = conn.cursor()
            cur.execute("SELECT is_positive, filename, data FROM images")
            for is_pos, filename, data in cur.fetchall():
                sub_dir = os.path.join(dest_dir, "positives" if is_pos else "negatives")
                os.makedirs(sub_dir, exist_ok=True)
                out_path = os.path.join(sub_dir, filename)
                counter = 1
                base, ext = os.path.splitext(out_path)
                while os.path.exists(out_path):
                    out_path = f"{base}_{counter}{ext}"
                    counter += 1
                with open(out_path, 'wb') as f:
                    f.write(data)
        finally:
            conn.close()
    except Exception as e:
        logging.error(f"Error extracting images from {path} to {dest_dir}: {e}")

def load_features(path: str, table_name: str = "features") -> Tuple[List[np.ndarray], List[np.ndarray]]:
    """Загружает векторы из дампа. table_name = 'features' (CLIP) или 'faces' (InsightFace)."""
    pos_features = []
    neg_features = []
    
    if not os.path.exists(path):
        return pos_features, neg_features
        
    try:
        conn = sqlite3.connect(path)
        try:
            cur = conn.cursor()
            column_name = 'feature_vector' if table_name == 'features' else 'face_vector'
            
            # Если это старый дамп и мы просим 'faces', таблица может не существовать
            try:
                cur.execute(f"SELECT is_positive, {column_name} FROM {table_name}")
            except sqlite3.OperationalError:
                return pos_features, neg_features
                
            for is_pos, blob in cur.fetchall():
                try:
                    header_end = blob.find(b'|', blob.find(b'|') + 1)
                    header = blob[:header_end].decode('utf-8')
                    shape_str, dtype_str = header.split('|')
                    shape = tuple(map(int, shape_str.split(',')))
                    
                    feat_bytes = blob[header_end + 1:]
                    arr = np.frombuffer(feat_bytes, dtype=np.dtype(dtype_str)).reshape(shape)
                    
                    if is_pos:
                        pos_features.append(arr)
                    else:
                        neg_features.append(arr)
                except Exception as ex:
                    logging.error(f"Error parsing feature vector in {path}: {ex}")
        finally:
            conn.close()
    except Exception as e:
        logging.error(f"Error loading features from {path}: {e}")
        
    return pos_features, neg_features
