import os
import json
import logging
import sqlite3
import numpy as np

from logic_paths import get_app_data_dir

SETTINGS_FILE = "ai_settings.json"

def get_ai_assets_dir() -> str:
    """Возвращает путь к папке эталонов Ai_assets."""
    path = os.path.join(get_app_data_dir(), "Ai_assets")
    os.makedirs(path, exist_ok=True)
    return path

def load_ai_settings() -> dict:
    """Загружает метаданные групп эталонов."""
    settings_path = os.path.join(get_ai_assets_dir(), SETTINGS_FILE)
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Ошибка чтения ai_settings.json: {e}")
    return {"groups": {}}

def save_ai_settings(settings: dict):
    """Сохраняет метаданные групп эталонов."""
    settings_path = os.path.join(get_ai_assets_dir(), SETTINGS_FILE)
    try:
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Ошибка записи ai_settings.json: {e}")

class AiClassifier:
    def __init__(self, cache_manager, ai_engine):
        self.cache = cache_manager
        self.ai = ai_engine
        
        # Кэш готовых эталонов в ОЗУ для быстрого сопоставления во время сканирования
        self.general_centroids = {}  # group_name -> mean_embedding
        self.general_embeddings = {}  # group_name -> list(embedding)
        self.face_reference_descriptors = {}  # group_name -> list(descriptor)

    def get_group_status(self, group_name: str) -> tuple:
        """
        Проверяет файлы в папке группы и возвращает кортеж:
        (status_color, file_count)
        Цвета:
        - "gray": нет файлов
        - "orange": файлы есть, но не для всех рассчитан кэш
        - "green": все файлы кэшированы
        """
        group_dir = os.path.join(get_ai_assets_dir(), group_name)
        if not os.path.exists(group_dir):
            return "gray", 0
            
        # Считаем только поддерживаемые изображения
        valid_exts = {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}
        files = []
        try:
            for f in os.listdir(group_dir):
                fp = os.path.join(group_dir, f)
                if os.path.isfile(fp) and os.path.splitext(f)[1].lower() in valid_exts:
                    files.append(fp)
        except Exception as e:
            logging.error(f"Ошибка чтения директории эталона {group_name}: {e}")
            
        file_count = len(files)
        if file_count == 0:
            return "gray", 0
            
        # Проверяем, есть ли кэш для каждого файла
        settings = load_ai_settings()
        group_info = settings.get("groups", {}).get(group_name, {})
        is_face_type = group_info.get("type") == "face"
        
        all_cached = True
        for fp in files:
            try:
                stat = os.stat(fp)
                mtime = stat.st_mtime
                size = stat.st_size
                
                if is_face_type:
                    faces = self.cache.get_file_faces(fp, mtime, size)
                    if faces is None:
                        all_cached = False
                        break
                else:
                    emb = self.cache.get_image_embedding(fp, mtime, size)
                    if emb is None:
                        all_cached = False
                        break
            except Exception:
                all_cached = False
                break
                
        status = "green" if all_cached else "orange"
        return status, file_count

    def train_group(self, group_name: str, progress_callback=None) -> bool:
        """
        Рассчитывает эмбеддинги/лица для всех файлов в группе и сохраняет в SQLite.
        progress_callback: функция (current, total)
        """
        group_dir = os.path.join(get_ai_assets_dir(), group_name)
        if not os.path.exists(group_dir):
            return False
            
        valid_exts = {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}
        files = [
            os.path.join(group_dir, f) for f in os.listdir(group_dir)
            if os.path.isfile(os.path.join(group_dir, f)) and os.path.splitext(f)[1].lower() in valid_exts
        ]
        
        if not files:
            return True
            
        settings = load_ai_settings()
        group_info = settings.get("groups", {}).get(group_name, {})
        is_face_type = group_info.get("type") == "face"
        
        # Убедимся, что сессии ONNX инициализированы
        if not self.ai.initialize_sessions():
            return False
            
        total = len(files)
        for idx, fp in enumerate(files):
            try:
                stat = os.stat(fp)
                mtime = stat.st_mtime
                size = stat.st_size
                
                if is_face_type:
                    # Для лиц
                    faces = self.cache.get_file_faces(fp, mtime, size)
                    if faces is None:
                        faces = self.ai.detect_and_extract_faces(fp)
                        self.cache.save_file_faces(fp, mtime, size, faces)
                else:
                    # Для общих
                    emb = self.cache.get_image_embedding(fp, mtime, size)
                    if emb is None:
                        emb = self.ai.extract_image_embedding(fp)
                        self.cache.save_image_embedding(fp, mtime, size, emb)
            except Exception as e:
                logging.error(f"Ошибка обучения на файле {fp}: {e}")
                
            if progress_callback:
                progress_callback(idx + 1, total)
                
        return True

    def load_active_references(self) -> bool:
        """
        Загружает в память центроиды и дескрипторы лиц для всех ВКЛЮЧЕННЫХ групп.
        Возвращает True, если есть хотя бы один активный класс для поиска.
        """
        self.general_centroids.clear()
        self.general_embeddings.clear()
        self.face_reference_descriptors.clear()
        
        settings = load_ai_settings()
        active_groups = []
        for name, info in settings.get("groups", {}).items():
            if info.get("enabled", True):
                active_groups.append((name, info.get("type") == "face"))
                
        if not active_groups:
            return False
            
        # Собираем данные из SQLite
        valid_exts = {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}
        
        for group_name, is_face in active_groups:
            group_dir = os.path.join(get_ai_assets_dir(), group_name)
            if not os.path.exists(group_dir):
                continue
                
            files = [
                os.path.join(group_dir, f) for f in os.listdir(group_dir)
                if os.path.isfile(os.path.join(group_dir, f)) and os.path.splitext(f)[1].lower() in valid_exts
            ]
            
            if not files:
                continue
                
            if is_face:
                descriptors = []
                for fp in files:
                    try:
                        stat = os.stat(fp)
                        faces = self.cache.get_file_faces(fp, stat.st_mtime, stat.st_size)
                        if faces is None:
                            faces = self.ai.detect_and_extract_faces(fp)
                            if faces:
                                self.cache.save_file_faces(fp, stat.st_mtime, stat.st_size, faces)
                        if faces:
                            for face in faces:
                                descriptors.append(face["descriptor"])
                    except Exception:
                        pass
                if descriptors:
                    self.face_reference_descriptors[group_name] = descriptors
            else:
                embeddings = []
                for fp in files:
                    try:
                        stat = os.stat(fp)
                        emb = self.cache.get_image_embedding(fp, stat.st_mtime, stat.st_size)
                        if emb is None:
                            emb = self.ai.extract_image_embedding(fp)
                            if emb is not None:
                                self.cache.save_image_embedding(fp, stat.st_mtime, stat.st_size, emb)
                        if emb is not None:
                            embeddings.append(emb)
                    except Exception:
                        pass
                if embeddings:
                    self.general_embeddings[group_name] = embeddings
                    
                    # Считаем средний центроид
                    mean_emb = np.mean(embeddings, axis=0)
                    # Нормализуем центроид
                    norm = np.linalg.norm(mean_emb)
                    if norm > 0:
                        mean_emb /= norm
                    self.general_centroids[group_name] = mean_emb
                    
        return len(self.general_embeddings) > 0 or len(self.face_reference_descriptors) > 0

    def match_image(self, filepath: str, mtime: float, size: int, match_mode: str = "centroid", threshold: float = 75.0, use_cache: bool = True) -> tuple:
        """
        Сопоставляет сканируемый файл с активными группами эталонов.
        Возвращает кортеж: (best_group_name, confidence_percent, details)
        или (None, 0, None)
        """
        # 1. Сначала проверяем классификацию лица (если есть активные face-группы)
        if self.face_reference_descriptors:
            faces = None
            if use_cache:
                faces = self.cache.get_file_faces(filepath, mtime, size)
                
            if faces is None:
                faces = self.ai.detect_and_extract_faces(filepath)
                if use_cache:
                    self.cache.save_file_faces(filepath, mtime, size, faces)
                
            if faces:
                best_face_group = None
                best_face_score = 0.0
                
                for face in faces:
                    desc = face["descriptor"]
                    for group_name, ref_descs in self.face_reference_descriptors.items():
                        for ref_desc in ref_descs:
                            dist = np.linalg.norm(desc - ref_desc)
                            # SFace L2 norm threshold for verification is ~1.128
                            # We map dist=1.128 to a score of 75.0 (since user UI defaults to 75% for 'same').
                            # dist=0 -> score=100.0. dist=2.0 -> score=0.0
                            if dist <= 1.128:
                                score = 100.0 - (dist / 1.128) * 25.0
                            else:
                                score = 75.0 - ((dist - 1.128) / (2.0 - 1.128)) * 75.0
                            score = max(0.0, min(100.0, score))
                            
                            if score > best_face_score:
                                best_face_score = score
                                best_face_group = group_name
                                
                if best_face_group and best_face_score > 0.0:
                    return best_face_group, best_face_score, {"type": "face"}
                    
        # 2. Если лица не распознаны, делаем общее сопоставление картинок с учетом выбранного режима
        if self.general_embeddings or self.general_centroids:
            emb = None
            if use_cache:
                emb = self.cache.get_image_embedding(filepath, mtime, size)
                
            if emb is None:
                emb = self.ai.extract_image_embedding(filepath)
                if use_cache:
                    self.cache.save_image_embedding(filepath, mtime, size, emb)
                
            best_group = None
            best_score = 0.0
            
            # Собираем все доступные группы
            all_groups = set(self.general_embeddings.keys()) | set(self.general_centroids.keys())
            
            for group_name in all_groups:
                if match_mode == "centroid" or group_name not in self.general_embeddings:
                    # Режим "Средний образ" или если у нас есть только предрассчитанный центроид (например, в тестах)
                    centroid = self.general_centroids.get(group_name)
                    if centroid is not None:
                        similarity = np.dot(emb, centroid)
                        score = max(0.0, (similarity - 0.3) / 0.7) * 100.0
                        if score > best_score:
                            best_score = score
                            best_group = group_name
                else:
                    embs = self.general_embeddings[group_name]
                    scores = []
                    for ref_emb in embs:
                        similarity = np.dot(emb, ref_emb)
                        score = max(0.0, (similarity - 0.3) / 0.7) * 100.0
                        scores.append(score)
                        
                    if not scores:
                        continue
                        
                    if match_mode == "majority":
                        # Должно быть выше threshold для >= 50% эталонов
                        passed = [s for s in scores if s >= threshold]
                        if len(passed) >= max(1, len(scores) / 2.0):
                            mean_passed = np.mean(passed)
                            if mean_passed > best_score:
                                best_score = mean_passed
                                best_group = group_name
                    else:  # "best_match"
                        max_score = max(scores)
                        if max_score > best_score:
                            best_score = max_score
                            best_group = group_name
                            
            if best_group and best_score > 0.0:
                return best_group, best_score, {"type": "general"}
                
        return None, 0, None
