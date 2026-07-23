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
    """Загружает метаданные групп образцов и настройки ИИ."""
    settings_path = os.path.join(get_ai_assets_dir(), SETTINGS_FILE)
    default_settings = {
        "groups": {},
        "face_match_threshold": 0.50, # Now we use 0.50 (50%) by default for both
        "clip_match_threshold": 0.50,
        "deep_merge_enabled": True,
        "deep_merge_threshold": 75.0
    }
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                default_settings.update(loaded)
                return default_settings
        except Exception as e:
            logging.error(f"Ошибка чтения ai_settings.json: {e}")
    return default_settings

def save_ai_settings(settings: dict):
    """Сохраняет метаданные групп образцов."""
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
        
        # Кэш готовых образцов в ОЗУ для быстрого сопоставления во время сканирования
        self.general_embeddings = {}  # group_name -> list(clip_embedding)
        self.face_reference_descriptors = {}  # group_name -> list(insightface_descriptor)

    def get_group_status(self, group_name: str) -> tuple:
        """
        Проверяет наличие дампа группы и возвращает статус: (status_color, file_count)
        """
        settings = load_ai_settings()
        group_info = settings.get("groups", {}).get(group_name, {})
        dump_path = group_info.get("path")
        
        if not dump_path or not os.path.exists(dump_path):
            return "gray", 0
            
        from .logic_ai_dump import load_dump_info
        info = load_dump_info(dump_path)
        
        count_faces = info.get("pos_faces_count", 0)
        count_features = info.get("pos_features_count", 0)
        
        count = count_faces + count_features
        status = "green" if count > 0 else "gray"
        return status, count

    def load_active_references(self) -> bool:
        """
        Загружает в память дескрипторы для всех ВКЛЮЧЕННЫХ групп из их дампов.
        """
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
            
        from .logic_ai_dump import load_features, extract_images_to_temp, save_dump
        import shutil
        loaded_any = False
        
        for name, dump_path in active_groups:
            needs_upgrade = False
            
            # Check CLIP vectors length
            pos_feat, _ = load_features(dump_path, "features")
            if pos_feat and len(pos_feat) > 0 and pos_feat[0].shape[0] != 512:
                needs_upgrade = True
                
            # Check InsightFace vectors length
            pos_faces, _ = load_features(dump_path, "faces")
            if pos_faces and len(pos_faces) > 0 and pos_faces[0].shape[0] != 512:
                needs_upgrade = True
                
            if needs_upgrade:
                import logging
                logging.info(f"Upgrading legacy AI dump vectors for group: {name}")
                temp_dir, pos_paths, neg_paths = extract_images_to_temp(dump_path)
                
                try:
                    new_pos_features, new_pos_faces = [], []
                    for p in pos_paths:
                        # Extract CLIP
                        emb = self.ai.extract_image_embedding(p)
                        if emb is not None: new_pos_features.append(emb)
                        # Extract Face
                        faces = self.ai.extract_faces(p)
                        if faces is not None:
                            for f in faces: new_pos_faces.append(f.embedding)
                            
                    new_neg_features, new_neg_faces = [], []
                    for p in neg_paths:
                        emb = self.ai.extract_image_embedding(p)
                        if emb is not None: new_neg_features.append(emb)
                        faces = self.ai.extract_faces(p)
                        if faces is not None:
                            for f in faces: new_neg_faces.append(f.embedding)
                            
                    # Re-save dump with new vectors
                    save_dump(
                        dump_path, "mixed", pos_paths, neg_paths,
                        new_pos_features, new_neg_features,
                        new_pos_faces, new_neg_faces, False
                    )
                    
                    # Reload the new features
                    pos_feat, _ = load_features(dump_path, "features")
                    pos_faces, _ = load_features(dump_path, "faces")
                finally:
                    shutil.rmtree(temp_dir, ignore_errors=True)
            
            if pos_feat and len(pos_feat) > 0:
                self.general_embeddings[name] = pos_feat
                loaded_any = True
                
            if pos_faces and len(pos_faces) > 0:
                self.face_reference_descriptors[name] = pos_faces
                loaded_any = True
                
        return loaded_any

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Косинусное сходство между двумя векторами."""
        a_norm = a / np.linalg.norm(a)
        b_norm = b / np.linalg.norm(b)
        return float(np.dot(a_norm, b_norm))

    def classify_file(self, filepath: str) -> dict:
        """
        Сопоставляет файл с активными группами. Возвращает словарь с максимальным % сходства для каждой группы.
        """
        result = {}
        
        # 1. Пробуем получить данные из кэша
        current_mtime = os.path.getmtime(filepath)
        current_size = os.path.getsize(filepath)
        
        # Загружаем CLIP
        file_clip_embedding = self.cache.get_image_embedding(filepath, current_mtime, current_size)
        # Загружаем Лица
        file_faces = self.cache.get_file_faces(filepath, current_mtime, current_size)
        
        # 2. Если чего-то нет в кэше - вычисляем на лету (тяжелая операция, обычно делает Worker заранее)
        if file_clip_embedding is None or file_faces is None:
            # Для надежности - в classify_file мы полагаемся на то, что кэш уже собран Worker-ом
            # Если кэша нет - возвращаем пустой результат (файл пропущен)
            return result
            
        # 3. Сопоставляем CLIP
        for group_name, clip_list in self.general_embeddings.items():
            max_sim = 0.0
            if file_clip_embedding is not None and clip_list:
                for ref_emb in clip_list:
                    sim = self._cosine_similarity(file_clip_embedding, ref_emb)
                    if sim > max_sim: max_sim = sim
            result[group_name] = max_sim
            
        # 4. Сопоставляем Лица
        for group_name, face_refs in self.face_reference_descriptors.items():
            max_face_sim = 0.0
            if file_faces and face_refs:
                for file_face in file_faces:
                    if file_face["descriptor"] is None or file_face["descriptor"].size == 0:
                        continue
                    for ref_desc in face_refs:
                        sim = self._cosine_similarity(file_face["descriptor"], ref_desc)
                        if sim > max_face_sim: max_face_sim = sim
            
            # Если совпадение по лицу выше, чем по CLIP, перезаписываем результат для группы
            if max_face_sim > result.get(group_name, 0.0):
                result[group_name] = max_face_sim
                
        return result
