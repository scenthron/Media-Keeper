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
                
                # Migrate relative paths to absolute for runtime use
                assets_dir = get_ai_assets_dir()
                for group_name, info in default_settings.get("groups", {}).items():
                    path = info.get("path")
                    if path and not os.path.isabs(path):
                        info["path"] = os.path.normpath(os.path.join(assets_dir, path))
                        
                return default_settings
        except Exception as e:
            logging.error(f"Ошибка чтения ai_settings.json: {e}")
    return default_settings

def save_ai_settings(settings: dict):
    """Сохраняет метаданные групп образцов, конвертируя локальные пути в относительные."""
    import copy
    settings_to_save = copy.deepcopy(settings)
    assets_dir = os.path.normpath(get_ai_assets_dir()).lower()
    
    for group_name, info in settings_to_save.get("groups", {}).items():
        path = info.get("path")
        if path:
            path_norm = os.path.normpath(path)
            if path_norm.lower().startswith(assets_dir):
                rel_path = os.path.relpath(path_norm, get_ai_assets_dir())
                info["path"] = rel_path
                
    settings_path = os.path.join(get_ai_assets_dir(), SETTINGS_FILE)
    try:
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(settings_to_save, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Ошибка записи ai_settings.json: {e}")

class AiClassifier:
    def __init__(self, cache_manager, ai_engine):
        self.cache = cache_manager
        self.ai = ai_engine
        
        # Кэш готовых образцов в ОЗУ для быстрого сопоставления во время сканирования
        self.general_embeddings = {}  # group_name -> list(clip_embedding)
        self.face_reference_descriptors = {}  # group_name -> list(insightface_descriptor)
        
        self.general_negative_embeddings = {}
        self.face_negative_descriptors = {}
        self.group_types = {}
        self.last_defective_faces = []

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

    def load_active_references(self, fast_search_dump: str = None) -> bool:
        """
        Загружает в память дескрипторы для всех ВКЛЮЧЕННЫХ групп из их дампов.
        """
        self.general_embeddings.clear()
        self.face_reference_descriptors.clear()
        self.general_negative_embeddings.clear()
        self.face_negative_descriptors.clear()
        self.group_types.clear()
        self.last_defective_faces.clear()
        
        active_groups = []
        if fast_search_dump and os.path.exists(fast_search_dump):
            active_groups.append(("FastSearch", fast_search_dump))
        else:
            settings = load_ai_settings()
            for name, info in settings.get("groups", {}).items():
                if info.get("enabled", True):
                    dump_path = info.get("path")
                    if dump_path and os.path.exists(dump_path):
                        active_groups.append((name, dump_path))
                
        if not active_groups:
            return False
            
        from .logic_ai_dump import load_features, extract_images_to_temp, save_dump, load_dump_info
        import shutil
        loaded_any = False
        
        for name, dump_path in active_groups:
            needs_upgrade = False
            
            dump_info = load_dump_info(dump_path)
            g_type = dump_info.get("search_type", dump_info.get("type", "face"))
            pos_count = dump_info.get("pos_images_count", 0)
            self.group_types[name] = g_type
            
            # Check CLIP vectors length
            pos_feat, neg_feat = load_features(dump_path, "features")
            if pos_feat and len(pos_feat) > 0 and pos_feat[0].shape[0] != 768:
                needs_upgrade = True
            elif g_type in ("general", "mixed") and pos_count > 0 and len(pos_feat) == 0:
                needs_upgrade = True
                
            # Check InsightFace vectors length
            pos_faces, neg_faces = load_features(dump_path, "faces")
            if pos_faces and len(pos_faces) > 0 and pos_faces[0].shape[0] != 512:
                needs_upgrade = True
            elif g_type in ("face", "mixed") and pos_count > 0 and len(pos_faces) == 0:
                needs_upgrade = True
                
            if needs_upgrade:
                import logging
                logging.info(f"Upgrading legacy or incomplete AI dump vectors for group: {name}")
                logging.info(f"  ai engine initialized: {self.ai._is_initialized if hasattr(self.ai, '_is_initialized') else 'unknown'}")
                temp_dir, pos_paths, neg_paths = extract_images_to_temp(dump_path)
                logging.info(f"  extracted pos_paths: {len(pos_paths)}, neg_paths: {len(neg_paths)}")
                for pp in pos_paths:
                    logging.info(f"    pos image: {pp} (exists={os.path.exists(pp)})")
                
                try:
                    new_pos_features, new_pos_faces = [], []
                    for p in pos_paths:
                        # Extract CLIP
                        emb = self.ai.extract_clip_embedding(p)
                        logging.info(f"  CLIP for {os.path.basename(p)}: {'OK' if emb is not None else 'FAIL'}")
                        if emb is not None: new_pos_features.append(emb)
                        # Extract Face
                        faces = self.ai.extract_faces(p)
                        logging.info(f"  Faces for {os.path.basename(p)}: {len(faces) if faces is not None else 'None (engine not ready?)'}")
                        if faces is not None and len(faces) > 0:
                            for f in faces: new_pos_faces.append(f["descriptor"])
                        elif g_type in ("face", "mixed"):
                            self.last_defective_faces.append(p)
                            
                    new_neg_features, new_neg_faces = [], []
                    for p in neg_paths:
                        emb = self.ai.extract_clip_embedding(p)
                        if emb is not None: new_neg_features.append(emb)
                        faces = self.ai.extract_faces(p)
                        if faces is not None and len(faces) > 0:
                            for f in faces: new_neg_faces.append(f["descriptor"])
                        elif g_type in ("face", "mixed"):
                            self.last_defective_faces.append(p)
                    
                    logging.info(f"  Upgrade results: pos_features={len(new_pos_features)}, pos_faces={len(new_pos_faces)}, neg_features={len(new_neg_features)}, neg_faces={len(new_neg_faces)}")
                    
                    # Re-save dump with new vectors
                    save_dump(
                        dump_path, g_type, pos_paths, neg_paths,
                        new_pos_features, new_neg_features,
                        new_pos_faces, new_neg_faces,
                        is_hash_only=False
                    )
                    
                    # Reload the new features
                    pos_feat, neg_feat = load_features(dump_path, "features")
                    pos_faces, neg_faces = load_features(dump_path, "faces")
                    logging.info(f"  After reload: pos_feat={len(pos_feat)}, pos_faces={len(pos_faces)}")
                finally:
                    shutil.rmtree(temp_dir, ignore_errors=True)
            
            if pos_feat and len(pos_feat) > 0:
                self.general_embeddings[name] = pos_feat
                if neg_feat: self.general_negative_embeddings[name] = neg_feat
                loaded_any = True
                
            if pos_faces and len(pos_faces) > 0:
                self.face_reference_descriptors[name] = pos_faces
                if neg_faces: self.face_negative_descriptors[name] = neg_faces
                loaded_any = True
                
        return loaded_any

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Косинусное сходство между двумя векторами."""
        a_norm = a / np.linalg.norm(a)
        b_norm = b / np.linalg.norm(b)
        return float(np.dot(a_norm, b_norm))

    def classify_file(self, filepath: str, neg_threshold: float = 50.0) -> dict:
        """
        Сопоставляет файл с активными группами. Возвращает словарь с максимальным % сходства для каждой группы.
        """
        result = {}
        
        # 1. Пробуем получить данные из кэша
        current_mtime = os.path.getmtime(filepath)
        current_size = os.path.getsize(filepath)
        
        has_image_groups = any(t in ("general", "mixed") for t in self.group_types.values())
        has_face_groups = any(t in ("face", "mixed") for t in self.group_types.values())
        
        file_clip_embedding = self.cache.get_image_embedding(filepath, current_mtime, current_size) if has_image_groups else None
        file_faces = self.cache.get_file_faces(filepath, current_mtime, current_size) if has_face_groups else None
        
        if (has_image_groups and file_clip_embedding is None) and (has_face_groups and file_faces is None):
            return result
            
        # Сила антипаттернов зависит от ползунка (0 = 2x, 50 = 1x, 100 = 0x)
        neg_weight = (100.0 - neg_threshold) / 50.0
            
        for group_name, g_type in self.group_types.items():
            if g_type in ("general", "mixed"):
                clip_list = self.general_embeddings.get(group_name, [])
                neg_clip_list = self.general_negative_embeddings.get(group_name, [])
                
                if file_clip_embedding is not None and clip_list:
                    max_sim = 0.0
                    for ref_emb in clip_list:
                        sim = self._cosine_similarity(file_clip_embedding, ref_emb)
                        if sim > max_sim: max_sim = sim
                        
                    # SigLIP image-to-image similarity has a very high baseline
                    mapped_score = (max_sim - 0.40) / (0.85 - 0.40)
                    mapped_score = max(0.0, min(1.0, float(mapped_score)))
                    
                    if neg_clip_list:
                        max_neg = 0.0
                        for ref_neg in neg_clip_list:
                            sim = self._cosine_similarity(file_clip_embedding, ref_neg)
                            if sim > max_neg: max_neg = sim
                        neg_mapped = (max_neg - 0.40) / (0.85 - 0.40)
                        neg_mapped = max(0.0, min(1.0, float(neg_mapped)))
                        mapped_score = max(0.0, mapped_score - (neg_mapped * neg_weight))
                        
                    if mapped_score > 0:
                        result[group_name] = mapped_score

            if g_type in ("face", "mixed"):
                face_refs = self.face_reference_descriptors.get(group_name, [])
                neg_faces = self.face_negative_descriptors.get(group_name, [])
                
                if file_faces and face_refs:
                    max_sim = 0.0
                    matched_bbox = None
                    for file_face in file_faces:
                        if file_face["descriptor"] is None or file_face["descriptor"].size == 0:
                            continue
                        for ref_desc in face_refs:
                            sim = self._cosine_similarity(file_face["descriptor"], ref_desc)
                            if sim > max_sim: 
                                max_sim = sim
                                matched_bbox = file_face.get("bbox")
                            
                    mapped_score = (max_sim - 0.35) / (0.85 - 0.35)
                    mapped_score = max(0.0, min(1.0, float(mapped_score)))
                    
                    if neg_faces:
                        max_neg = 0.0
                        for file_face in file_faces:
                            if file_face["descriptor"] is None or file_face["descriptor"].size == 0:
                                continue
                            for ref_neg in neg_faces:
                                sim = self._cosine_similarity(file_face["descriptor"], ref_neg)
                                if sim > max_neg: max_neg = sim
                                
                        neg_mapped = (max_neg - 0.35) / (0.85 - 0.35)
                        neg_mapped = max(0.0, min(1.0, float(neg_mapped)))
                        mapped_score = max(0.0, mapped_score - (neg_mapped * neg_weight))
                        
                    if mapped_score > 0:
                        result[group_name] = {"score": mapped_score, "bbox": matched_bbox}
                        
        return result
