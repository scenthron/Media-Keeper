import os
import time
import sqlite3
import numpy as np
from enum import Enum
from dataclasses import dataclass, field
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool

# -----------------------------------------------------------------------------
# DTO (Data Transfer Objects)
# -----------------------------------------------------------------------------

class AiTaskType(Enum):
    AUTO_CLUSTER = 1
    FIND_BY_REFERENCES = 2
    TEXT_TO_IMAGE = 3
    GENERATE_TAGS = 4

class AiTarget(Enum):
    FACES = 1
    IMAGES = 2
    BOTH = 3

@dataclass
class Rect:
    x1: float
    y1: float
    x2: float
    y2: float

@dataclass
class AiMatchFile:
    path: str
    score: float
    bboxes: list[Rect] = field(default_factory=list)
    matched_bbox: Rect = None
    matched_reference_id: str = None
    auto_tags: list[str] = field(default_factory=list)

@dataclass
class AiGroup:
    group_name: str
    files: list[AiMatchFile] = field(default_factory=list)
    
@dataclass
class AiSearchRequest:
    target_paths: list[str]
    task_type: AiTaskType
    analysis_target: AiTarget
    threshold: float
    file_filter_config: dict = field(default_factory=dict)
    reference_embeddings: list[list[float]] = field(default_factory=list)
    text_queries: dict[str, list[str]] = field(default_factory=dict)
    use_cache: bool = True
    use_gpu: bool = True

@dataclass
class AiSearchResponse:
    groups: list[AiGroup] = field(default_factory=list)

def _dbscan_numpy(X: np.ndarray, eps: float, min_samples: int = 2) -> np.ndarray:
    """Чистый NumPy DBSCAN алгоритм кластеризации с косинусным расстоянием без внешних зависимостей."""
    n = len(X)
    if n == 0:
        return np.array([], dtype=int)
    
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    norms = np.clip(norms, 1e-9, None)
    X_norm = X / norms
    
    sims = np.dot(X_norm, X_norm.T)
    dists = np.clip(1.0 - sims, 0.0, None)
    
    labels = np.full(n, -1, dtype=int)
    cluster_id = 0
    
    for i in range(n):
        if labels[i] != -1:
            continue
            
        neighbors = np.where(dists[i] <= eps)[0]
        if len(neighbors) < min_samples:
            labels[i] = -1
        else:
            labels[i] = cluster_id
            seeds = list(neighbors)
            while seeds:
                curr = seeds.pop(0)
                if labels[curr] == -1:
                    labels[curr] = cluster_id
                elif labels[curr] != -1:
                    continue
                labels[curr] = cluster_id
                curr_neighbors = np.where(dists[curr] <= eps)[0]
                if len(curr_neighbors) >= min_samples:
                    seeds.extend(curr_neighbors)
            cluster_id += 1
            
    return labels

# -----------------------------------------------------------------------------
# Core Worker
# -----------------------------------------------------------------------------

STAGE_SCANNING = 1
STAGE_ANALYSIS = 2

class AiCoreWorker(QRunnable):
    class Signals(QObject):
        # stage, percent, text, scanned_files, groups_found, wasted_bytes, scanned_bytes, files_found, dummy
        progress = pyqtSignal(int, float, str, int, int, object, object, int, int)
        result_found = pyqtSignal(object) # AiSearchResponse
        finished = pyqtSignal()
        error = pyqtSignal(str)

    def __init__(self, request: AiSearchRequest, engine=None, cache=None, classifier=None):
        super().__init__()
        self.request = request
        self.engine = engine
        self.cache = cache
        self.classifier = classifier
        self.signals = self.Signals()
        self.is_cancelled = False

    def run(self):
        try:
            from .workers import ensure_win_path
            import re
            
            # 1. Gather valid files
            self.signals.progress.emit(STAGE_SCANNING, 0.0, "Поиск медиафайлов...", 0, 0, 0, 0, 0, 0)
            valid_exts = {'.jpg', '.jpeg', '.png', '.bmp'}
            valid_files = []
            scanned_files = 0
            scanned_bytes = 0
            
            for folder in self.request.target_paths:
                if self.is_cancelled: return
                norm_folder = os.path.normpath(folder)
                scan_path = ensure_win_path(norm_folder)
                if not os.path.exists(scan_path): continue
                
                if os.path.isfile(scan_path):
                    ext = os.path.splitext(scan_path)[1].lower()
                    if ext in valid_exts:
                        size = os.path.getsize(scan_path)
                        valid_files.append(scan_path)
                        scanned_files += 1
                        scanned_bytes += size
                else:
                    for root, _, files in os.walk(scan_path):
                        if self.is_cancelled: return
                        for f in files:
                            ext = os.path.splitext(f)[1].lower()
                            if ext in valid_exts:
                                fp = os.path.join(root, f)
                                try:
                                    size = os.path.getsize(fp)
                                    valid_files.append(fp)
                                    scanned_files += 1
                                    scanned_bytes += size
                                except:
                                    pass

            total_files = len(valid_files)
            if total_files == 0:
                self.signals.progress.emit(STAGE_ANALYSIS, 100.0, "Нет файлов для обработки", 0, 0, 0, 0, 0, 0)
                self.signals.result_found.emit(AiSearchResponse(groups=[]))
                self.signals.finished.emit()
                return

            if self.request.task_type == AiTaskType.FIND_BY_REFERENCES and self.classifier:
                import logging
                if not self.classifier.load_active_references():
                    logging.warning("Нет активных эталонов для ИИ-поиска")

            self.signals.progress.emit(STAGE_ANALYSIS, 0.0, f"Анализ {total_files} файлов...", scanned_files, 0, 0, scanned_bytes, 0, 0)

            # 2. Extract Features
            if self.engine is None:
                from .logic_ai import AiEngine
                self.engine = AiEngine()
            
            if not self.engine.initialize_sessions(use_gpu=self.request.use_gpu):
                self.signals.error.emit("Не удалось инициализировать нейросети.")
                return

            # Initialize text embeddings if TEXT_TO_IMAGE
            text_embeddings = {}
            if self.request.task_type == AiTaskType.TEXT_TO_IMAGE:
                for group_name, comps in self.request.text_queries.items():
                    text_embeddings[group_name] = []
                    for comp in comps:
                        emb = self.engine.extract_text_embedding(comp)
                        if emb is not None:
                            text_embeddings[group_name].append(emb)

            # 3. Process each file
            file_features = []
            processed = 0
            
            import logging
            logging.info(f"[AiCoreWorker] Входные параметры: {self.request.task_type}, Цель: {self.request.analysis_target}, "
                         f"Файлов для анализа: {total_files}, Порог: {self.request.threshold}")

            cache_batch = []
            cached_hits = 0
            for fp in valid_files:
                if self.is_cancelled: return
                
                percent = (processed / total_files) * 95.0  # Feature extraction takes up 95% of time
                if processed % 10 == 0:
                    status_text = "Чтение из ИИ-кэша..." if (cached_hits > 0 and cached_hits >= processed - 10) else "Извлечение признаков ИИ..."
                    self.signals.progress.emit(STAGE_ANALYSIS, percent, f"{status_text} {processed}/{total_files}", scanned_files, 0, 0, scanned_bytes, 0, 0)
                
                try:
                    stat = os.stat(fp)
                    size = stat.st_size
                    mtime = stat.st_mtime
                except Exception:
                    processed += 1
                    continue
                
                hit_cache = False
                if self.request.analysis_target in (AiTarget.FACES, AiTarget.BOTH):
                    faces = None
                    if self.request.use_cache and self.cache:
                        faces = self.cache.get_file_faces(fp, mtime, size)
                        if faces is not None: hit_cache = True
                    if faces is None:
                        faces = self.engine.extract_faces(fp)
                        if self.request.use_cache and self.cache and faces is not None:
                            self.cache.save_file_faces(fp, mtime, size, faces)
                    
                    if faces and self.request.analysis_target == AiTarget.FACES:
                        file_features.append((fp, faces))
                        
                if self.request.analysis_target in (AiTarget.IMAGES, AiTarget.BOTH):
                    emb = None
                    if self.request.use_cache and self.cache:
                        emb = self.cache.get_image_embedding(fp, mtime, size)
                        if emb is not None: hit_cache = True
                    if emb is None:
                        emb = self.engine.extract_clip_embedding(fp)
                        if self.request.use_cache and self.cache and emb is not None:
                            cache_batch.append((fp, mtime, size, emb))
                            if len(cache_batch) >= 50:
                                self.cache.save_image_embeddings_batch(cache_batch)
                                cache_batch = []
                            
                    if emb is not None and self.request.analysis_target == AiTarget.IMAGES:
                        file_features.append((fp, emb))
                        
                if hit_cache:
                    cached_hits += 1
                        
                # If BOTH, file_features won't be used by auto-cluster, but FIND_BY_REFERENCES uses the cache directly
                if self.request.analysis_target == AiTarget.BOTH:
                    pass
                
                processed += 1

            if cache_batch and self.request.use_cache and self.cache:
                self.cache.save_image_embeddings_batch(cache_batch)
                cache_batch = []

            # 4. Search and Cluster logic
            self.signals.progress.emit(STAGE_ANALYSIS, 95.0, "Группировка результатов...", scanned_files, 0, 0, scanned_bytes, 0, 0)
            
            groups_dict = {}
            
            if self.request.task_type == AiTaskType.TEXT_TO_IMAGE and self.request.analysis_target == AiTarget.IMAGES:
                # Text Multi-tag Search (Vectorized Matrix Multiplication)
                if file_features and text_embeddings:
                    filepaths = []
                    img_embs = []
                    for item in file_features:
                        if item[1] is not None:
                            arr = np.asarray(item[1], dtype=np.float32).flatten()
                            if arr.size > 0:
                                img_embs.append(arr)
                                filepaths.append(item[0])

                    if img_embs:
                        if len(img_embs) == 0:
                            logging.info("[AiCoreWorker] Не удалось извлечь векторы из изображений.")
                        else:
                            img_mat = np.array(img_embs, dtype=np.float32)  # Shape: (N, 512)

                            for group_name, text_embs in text_embeddings.items():
                                if not text_embs:
                                    continue
                                txt_cleaned = [np.asarray(t, dtype=np.float32).flatten() for t in text_embs if t is not None]
                                txt_cleaned = [t for t in txt_cleaned if t.size > 0]
                                if not txt_cleaned:
                                    continue
                                txt_mat = np.array(txt_cleaned, dtype=np.float32)  # Shape: (M, 512)
                                
                                if img_mat.size == 0 or txt_mat.size == 0 or img_mat.ndim != 2 or txt_mat.ndim != 2:
                                    continue

                                # Fast matrix dot product: (N, 512) x (512, M) -> (N, M)
                                sim_matrix = np.dot(img_mat, txt_mat.T)
                                if sim_matrix.size == 0:
                                    continue
                                
                                # Highest similarity score across queries for each image
                                max_sims = np.max(sim_matrix, axis=1)  # Shape: (N,)
                            
                            # Scale to percentage 0..100
                            mapped_scores = (max_sims - 0.14) / (0.28 - 0.14) * 100.0
                            mapped_scores = np.clip(mapped_scores, 0, 100).astype(int)
                            
                            # Filter indices exceeding similarity threshold
                            match_indices = np.where(mapped_scores >= self.request.threshold)[0]
                            
                            if len(match_indices) > 0:
                                if group_name not in groups_dict:
                                    groups_dict[group_name] = []
                                for idx in match_indices:
                                    match_file = AiMatchFile(
                                        path=filepaths[idx], 
                                        score=int(mapped_scores[idx]), 
                                        matched_reference_id=group_name
                                    )
                                    groups_dict[group_name].append(match_file)

            elif self.request.task_type == AiTaskType.AUTO_CLUSTER and self.request.analysis_target == AiTarget.FACES:
                all_embs = []
                file_face_map = []
                
                for fp, faces in file_features:
                    for face in faces:
                        desc = face.get("descriptor")
                        if desc is not None:
                            arr = np.asarray(desc, dtype=np.float32).flatten()
                            if arr.size > 0:
                                all_embs.append(arr)
                                file_face_map.append((fp, face))
                        
                if all_embs:
                    X = np.array(all_embs, dtype=np.float32)
                    eps = 1.0 - (self.request.threshold / 100.0)
                    labels = _dbscan_numpy(X, eps=eps, min_samples=2)
                    
                    for i, label in enumerate(labels):
                        if label == -1: continue # noise
                        group_name = f"Группа Лиц {label+1}"
                        if group_name not in groups_dict:
                            groups_dict[group_name] = []
                            
                        fp, face = file_face_map[i]
                        # Avoid duplicates in same group
                        if not any(f.path == fp for f in groups_dict[group_name]):
                            rect = Rect(face["bbox"][0], face["bbox"][1], face["bbox"][2], face["bbox"][3])
                            match_file = AiMatchFile(path=fp, score=100.0, matched_bbox=rect)
                            groups_dict[group_name].append(match_file)

            elif self.request.task_type == AiTaskType.AUTO_CLUSTER and self.request.analysis_target == AiTarget.IMAGES:
                # Vibe auto clustering
                all_embs = []
                file_map = []
                
                for fp, emb in file_features:
                    if emb is not None:
                        arr = np.asarray(emb, dtype=np.float32).flatten()
                        if arr.size > 0:
                            all_embs.append(arr)
                            file_map.append(fp)
                    
                if all_embs:
                    X = np.array(all_embs, dtype=np.float32)
                    eps = 1.0 - (self.request.threshold / 100.0)
                    labels = _dbscan_numpy(X, eps=eps, min_samples=2)
                    
                    for i, label in enumerate(labels):
                        if label == -1: continue 
                        group_name = f"Группа Объектов {label+1}"
                        if group_name not in groups_dict:
                            groups_dict[group_name] = []
                            
                        fp = file_map[i]
                        match_file = AiMatchFile(path=fp, score=100.0)
                        groups_dict[group_name].append(match_file)

            elif self.request.task_type == AiTaskType.FIND_BY_REFERENCES and self.classifier is not None:
                # Use classifier logic natively
                for fp in valid_files:
                    if self.is_cancelled: return
                    results_dict = self.classifier.classify_file(fp)
                    for g_name, conf_data in results_dict.items():
                        if isinstance(conf_data, dict):
                            conf = conf_data["score"]
                            bbox_tuple = conf_data.get("bbox")
                        else:
                            conf = conf_data
                            bbox_tuple = None
                            
                        conf_pct = conf * 100.0
                        if conf_pct >= self.request.threshold:
                            if g_name not in groups_dict:
                                groups_dict[g_name] = []
                            rect = Rect(bbox_tuple[0], bbox_tuple[1], bbox_tuple[2], bbox_tuple[3]) if bbox_tuple else None
                            # Default to FACE if bbox, else GENERAL
                            typ = "face" if bbox_tuple else "general"
                            match_file = AiMatchFile(path=fp, score=conf_pct, matched_bbox=rect, matched_reference_id=g_name)
                            # Adding type to match_file indirectly (we don't have type in struct but UI relies on matched_bbox)
                            groups_dict[g_name].append(match_file)

            # 5. Format Output
            response_groups = []
            total_matches = 0
            for g_name, files in groups_dict.items():
                if len(files) > 0:
                    files.sort(key=lambda x: x.score, reverse=True)
                    response_groups.append(AiGroup(group_name=g_name, files=files))
                    total_matches += len(files)
            
            logging.info(f"[AiCoreWorker] Выходные данные: найдено {len(response_groups)} групп, всего {total_matches} файлов-совпадений.")
            
            response = AiSearchResponse(groups=response_groups)
            
            self.signals.progress.emit(STAGE_ANALYSIS, 100.0, "Готово", scanned_files, len(response_groups), 0, scanned_bytes, total_matches, 0)
            self.signals.result_found.emit(response)
            self.signals.finished.emit()

        except Exception as e:
            import traceback
            import logging
            tb_str = traceback.format_exc()
            logging.error(f"AiCoreWorker Unhandled Exception:\n{tb_str}")
            print(f"AiCoreWorker Error:\n{tb_str}")
            self.signals.error.emit(str(e))


# -----------------------------------------------------------------------------
# Ai Service Facade
# -----------------------------------------------------------------------------

class AiServiceFacade(QObject):
    def __init__(self):
        super().__init__()
        self.engine = None
        self.cache = None
        self.active_worker = None
        
    def get_engine(self):
        if self.engine is None:
            from .logic_ai import AiEngine
            self.engine = AiEngine()
        return self.engine

    def search(self, request: AiSearchRequest, 
                 progress_callback=None, 
                 result_callback=None, 
                 error_callback=None,
                 classifier=None):
        
        self.cancel_search()
        
        self.active_worker = AiCoreWorker(request, self.get_engine(), self.cache, classifier)
        
        worker = self.active_worker
        def _cleanup_worker(*args):
            if self.active_worker is worker:
                self.active_worker = None
                
        worker.signals.finished.connect(_cleanup_worker)
        worker.signals.error.connect(_cleanup_worker)
        
        if progress_callback:
            self.active_worker.signals.progress.connect(progress_callback)
        if result_callback:
            self.active_worker.signals.result_found.connect(result_callback)
        if error_callback:
            self.active_worker.signals.error.connect(error_callback)
            
        QThreadPool.globalInstance().start(self.active_worker)
        
    def cancel_search(self):
        if self.active_worker:
            self.active_worker.is_cancelled = True
            self.active_worker = None
