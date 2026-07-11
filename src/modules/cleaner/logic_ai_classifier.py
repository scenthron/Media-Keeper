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
    """Загружает метаданные групп эталонов и настройки ИИ."""
    settings_path = os.path.join(get_ai_assets_dir(), SETTINGS_FILE)
    default_settings = {
        "groups": {},
        "face_det_threshold": 65.0,
        "face_match_threshold": 1.128,
        "deep_merge_enabled": True,
        "deep_merge_threshold": 75.0
    }
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                default_settings.update(loaded)
                
                # Migration for old percentage value
                if default_settings["face_match_threshold"] > 2.0:
                    default_settings["face_match_threshold"] = 1.128
                
                return default_settings
        except Exception as e:
            logging.error(f"Ошибка чтения ai_settings.json: {e}")
    return default_settings

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
        Проверяет наличие дампа группы и возвращает статус:
        (status_color, file_count)
        """
        settings = load_ai_settings()
        group_info = settings.get("groups", {}).get(group_name, {})
        dump_path = group_info.get("path")
        
        if not dump_path or not os.path.exists(dump_path):
            return "gray", 0
            
        from .logic_ai_dump import load_dump_info
        info = load_dump_info(dump_path)
        
        count = info.get("pos_features_count", 0)
        status = "green" if count > 0 else "gray"
        return status, count

    def load_active_references(self) -> bool:
        """
        Загружает в память центроиды и дескрипторы лиц для всех ВКЛЮЧЕННЫХ групп из их дампов.
        Возвращает True, если есть хотя бы один активный класс для поиска.
        """
        self.general_centroids.clear()
        self.general_embeddings.clear()
        self.face_reference_descriptors.clear()
        
        settings = load_ai_settings()
        active_groups = []
        for name, info in settings.get("groups", {}).items():
            if info.get("enabled", True):
                dump_path = info.get("path")
                if dump_path and os.path.exists(dump_path):
                    active_groups.append((name, dump_path))
                
        if not active_groups:
            return False
            
        from .logic_ai_dump import load_dump_info, load_features
        
        for group_name, dump_path in active_groups:
            info = load_dump_info(dump_path)
            is_face = info.get("type", "face") == "face"
            
            descriptors, neg_descriptors = load_features(dump_path)
            
            if not descriptors:
                continue
                
            if is_face:
                if descriptors:
                    if neg_descriptors:
                        neg_centroid = np.mean(neg_descriptors, axis=0)
                        norm_neg = np.linalg.norm(neg_centroid)
                        if norm_neg > 0:
                            neg_centroid /= norm_neg
                            
                        # adjust positive descriptors
                        adjusted_descriptors = []
                        for desc in descriptors:
                            adj = desc - 0.5 * neg_centroid
                            norm = np.linalg.norm(adj)
                            if norm > 0:
                                adj /= norm
                            adjusted_descriptors.append(adj)
                        descriptors = adjusted_descriptors
                        
                    self.face_reference_descriptors[group_name] = descriptors
            else:
                if descriptors:
                    self.general_embeddings[group_name] = descriptors
                    mean_emb = np.mean(descriptors, axis=0)
                    
                    if neg_descriptors:
                        neg_centroid = np.mean(neg_descriptors, axis=0)
                        mean_emb = mean_emb - 0.5 * neg_centroid
                        
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
                
                settings = load_ai_settings()
                match_thresh = settings.get("face_match_threshold", 1.128)
                
                for face in faces:
                    desc = face["descriptor"]
                    for group_name, ref_descs in self.face_reference_descriptors.items():
                        for ref_desc in ref_descs:
                            dist = np.linalg.norm(desc - ref_desc)
                            # Map actual threshold to 75.0 score internally so the rest of the app 
                            # (which expects scores > user spin_threshold) keeps working.
                            if dist <= match_thresh:
                                score = 100.0 - (dist / match_thresh) * 25.0
                            else:
                                if match_thresh >= 2.0:
                                    score = 0.0
                                else:
                                    score = 75.0 - ((dist - match_thresh) / (2.0 - match_thresh)) * 75.0
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
