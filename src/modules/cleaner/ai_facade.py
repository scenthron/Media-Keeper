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
    tag_scores: dict[str, int] = field(default_factory=dict)

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
    neg_threshold: float = 50.0
    file_filter_config: dict = field(default_factory=dict)
    reference_embeddings: list[list[float]] = field(default_factory=list)
    text_queries: dict[str, list[dict]] = field(default_factory=dict)
    negative_queries: dict[str, list[dict]] = field(default_factory=dict)
    use_cache: bool = True
    fast_search_dump: str = None
    use_gpu: bool = True
    face_conf_thresh: float = 0.70


@dataclass
class AiSearchResponse:
    groups: list[AiGroup] = field(default_factory=list)

def _agglomerative_clustering_numpy(X: np.ndarray, eps: float, min_samples: int = 2, linkage: str = "average") -> np.ndarray:
    """Иерархическая агломеративная кластеризация (Average/Complete Linkage) с косинусным расстоянием без внешних зависимостей."""
    n = len(X)
    if n == 0:
        return np.array([], dtype=int)
    
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    norms = np.clip(norms, 1e-9, None)
    X_norm = X / norms
    
    sims = np.dot(X_norm, X_norm.T)
    dists = np.clip(1.0 - sims, 0.0, None)
    np.fill_diagonal(dists, np.inf)
    
    labels = np.arange(n)
    sizes = np.ones(n, dtype=int)
    
    while True:
        if dists.shape[0] < 2:
            break
            
        min_idx = np.argmin(dists)
        i, j = np.unravel_index(min_idx, dists.shape)
        
        if dists[i, j] > eps:
            break
            
        if linkage == "complete":
            new_dists = np.maximum(dists[i, :], dists[j, :])
        else:
            new_dists = (sizes[i] * dists[i, :] + sizes[j] * dists[j, :]) / (sizes[i] + sizes[j])
        
        dists[i, :] = new_dists
        dists[:, i] = new_dists
        dists[i, i] = np.inf
        
        dists[j, :] = np.inf
        dists[:, j] = np.inf
        
        sizes[i] += sizes[j]
        sizes[j] = 0
        
        labels[labels == labels[j]] = labels[i]
        
    unique_labels, counts = np.unique(labels, return_counts=True)
    
    final_labels = np.full(n, -1, dtype=int)
    cluster_id = 0
    for ul, count in zip(unique_labels, counts):
        if count >= min_samples:
            final_labels[labels == ul] = cluster_id
            cluster_id += 1
            
    return final_labels

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
        defective_faces = pyqtSignal(list)  # список temp-путей картинок, на которых не найдены лица

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
            
            if self.cache and hasattr(self.request, 'face_conf_thresh'):
                self.cache.check_and_clear_faces_if_threshold_changed(self.request.face_conf_thresh)
            
            # 1. Gather valid files
            self.signals.progress.emit(STAGE_SCANNING, 0.0, "Поиск медиафайлов...", 0, 0, 0, 0, 0, 0)
            valid_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.avif'}
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

            # Initialize Engine BEFORE loading active references (which may need extraction)
            if self.engine is None:
                from .logic_ai import AiEngine
                self.engine = AiEngine()
            
            if not self.engine.initialize_sessions(use_gpu=self.request.use_gpu):
                self.signals.error.emit("Не удалось инициализировать нейросети.")
                return

            # CRITICAL: Подменяем AiEngine в классификаторе на уже инициализированный,
            # иначе classifier.ai останется неинициализированным и extract_faces вернёт None
            if self.classifier:
                self.classifier.ai = self.engine

            if self.request.task_type == AiTaskType.FIND_BY_REFERENCES and self.classifier:
                import logging
                load_ok = self.classifier.load_active_references(fast_search_dump=self.request.fast_search_dump)
                
                # Всегда сообщаем UI о дефектных картинках (без лиц), даже при частичном успехе
                if hasattr(self.classifier, 'last_defective_faces') and self.classifier.last_defective_faces:
                    self.signals.defective_faces.emit(list(self.classifier.last_defective_faces))
                
                if not load_ok:
                    logging.warning("Нет активных эталонов для ИИ-поиска")
                    if self.request.fast_search_dump:
                        err_msg = "Внимание: На добавленных образцах не найдены лица для сканирования. Добавьте более качественные фото крупным планом."
                    else:
                        err_msg = "Нет активных эталонов для ИИ-поиска"
                    self.signals.error.emit(err_msg)
                    return

            self.signals.progress.emit(STAGE_ANALYSIS, 0.0, f"Анализ {total_files} файлов...", scanned_files, 0, 0, scanned_bytes, 0, 0)

            # 2. Extract Features

            # Initialize text embeddings if TEXT_TO_IMAGE
            text_embeddings = {}
            if self.request.task_type == AiTaskType.TEXT_TO_IMAGE:
                # Precompute global negatives
                global_negatives = []
                for neg_q in getattr(self.request, 'negative_queries', {}).get("__global__", []):
                    text = neg_q.get("text", "")
                    weight = neg_q.get("weight")
                    emb = self.engine.extract_text_embedding(text)
                    if emb is not None:
                        global_negatives.append({"emb": emb, "weight": weight, "text": text})
                        
                # Encode positive queries and applying specific negatives
                for group_name, comps in self.request.text_queries.items():
                    # Compute specific negatives for this group
                    group_negatives = []
                    for neg_q in getattr(self.request, 'negative_queries', {}).get(group_name, []):
                        text = neg_q.get("text", "")
                        weight = neg_q.get("weight")
                        emb = self.engine.extract_text_embedding(text)
                        if emb is not None:
                            group_negatives.append({"emb": emb, "weight": weight, "text": text})
                            
                    all_negs = global_negatives + group_negatives
                        
                    pos_embs = []
                    for comp in comps:
                        text = comp.get("text", "")
                        weight = comp.get("weight")
                        emb = self.engine.extract_text_embedding(text)
                        if emb is not None:
                            pos_embs.append({"emb": emb, "weight": weight, "text": text})
                    text_embeddings[group_name] = {"pos": pos_embs, "neg": all_negs}

            # 3. Process each file
            file_features = []
            processed = 0
            
            import logging
            logging.info(f"[AiCoreWorker] Входные параметры: {self.request.task_type}, Цель: {self.request.analysis_target}, "
                         f"Файлов для анализа: {total_files}, Порог: {self.request.threshold}")

            cache_batch = []
            faces_cache_batch = []
            cached_hits = 0

            import queue
            import cv2
            import threading
            from utils_io import safe_cv2_imread
            from concurrent.futures import ThreadPoolExecutor

            task_queue = queue.Queue(maxsize=16)

            def producer(fp):
                if self.is_cancelled: return
                try:
                    stat = os.stat(fp)
                    size = stat.st_size
                    mtime = stat.st_mtime
                    
                    # Проверка необходимости декодирования (если кэш уже есть, пиксели не нужны)
                    needs_decode = False
                    if self.request.analysis_target in (AiTarget.FACES, AiTarget.BOTH):
                        if not (self.request.use_cache and self.cache and self.cache.get_file_faces(fp, mtime, size) is not None):
                            needs_decode = True
                    if self.request.analysis_target in (AiTarget.IMAGES, AiTarget.BOTH) and not needs_decode:
                        if not (self.request.use_cache and self.cache and self.cache.get_image_embedding(fp, mtime, size) is not None):
                            needs_decode = True
                            
                    img_rgb = None
                    if needs_decode:
                        img = safe_cv2_imread(fp)
                        if img is not None:
                            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                            
                    task_queue.put((fp, mtime, size, img_rgb))
                except Exception:
                    task_queue.put((fp, 0, 0, None))

            def producer_manager():
                with ThreadPoolExecutor(max_workers=4) as executor:
                    for fp in valid_files:
                        if self.is_cancelled: break
                        executor.submit(producer, fp)
                task_queue.put(None) # EOF marker

            threading.Thread(target=producer_manager, daemon=True).start()

            while True:
                if self.is_cancelled: break
                item = task_queue.get()
                if item is None:
                    break
                    
                fp, mtime, size, img_rgb = item
                
                percent = (processed / total_files) * 95.0
                if processed % 10 == 0:
                    status_text = "Чтение из ИИ-кэша..." if (cached_hits > 0 and cached_hits >= processed - 10) else "Извлечение признаков ИИ..."
                    self.signals.progress.emit(STAGE_ANALYSIS, percent, f"{status_text} {processed}/{total_files}", scanned_files, 0, 0, scanned_bytes, 0, 0)
                
                if mtime == 0 and size == 0:
                    processed += 1
                    continue
                
                hit_cache = False
                
                if self.request.analysis_target in (AiTarget.FACES, AiTarget.BOTH):
                    faces = None
                    if self.request.use_cache and self.cache:
                        faces = self.cache.get_file_faces(fp, mtime, size)
                        if faces is not None: hit_cache = True
                        
                    if faces is None:
                        faces = self.engine.extract_faces(fp, img_rgb, conf_thresh=self.request.face_conf_thresh)
                        if self.request.use_cache and self.cache and faces is not None:
                            faces_cache_batch.append((fp, mtime, size, faces))
                            if len(faces_cache_batch) >= 50:
                                self.cache.save_file_faces_batch(faces_cache_batch)
                                faces_cache_batch = []
                    
                    if faces and self.request.analysis_target == AiTarget.FACES:
                        file_features.append((fp, faces))
                        
                if self.request.analysis_target in (AiTarget.IMAGES, AiTarget.BOTH):
                    emb = None
                    if self.request.use_cache and self.cache:
                        emb = self.cache.get_image_embedding(fp, mtime, size)
                        if emb is not None: hit_cache = True
                        
                    if emb is None:
                        emb = self.engine.extract_clip_embedding(fp, img_rgb)
                        if self.request.use_cache and self.cache and emb is not None:
                            cache_batch.append((fp, mtime, size, emb))
                            if len(cache_batch) >= 50:
                                self.cache.save_image_embeddings_batch(cache_batch)
                                cache_batch = []
                                
                    if emb is not None and self.request.analysis_target == AiTarget.IMAGES:
                        file_features.append((fp, emb))
                        
                if hit_cache:
                    cached_hits += 1
                    
                processed += 1

            if faces_cache_batch and self.request.use_cache and self.cache:
                self.cache.save_file_faces_batch(faces_cache_batch)
                
            if cache_batch and self.request.use_cache and self.cache:
                self.cache.save_image_embeddings_batch(cache_batch)

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
                        img_mat = np.array(img_embs, dtype=np.float32)  # Shape: (N, 512)

                        for group_name, group_data in text_embeddings.items():
                            text_embs = group_data["pos"]
                            neg_embs = group_data["neg"]
                            
                            if not text_embs:
                                continue
                                
                            pos_weights = []
                            pos_vectors = []
                            pos_words = []
                            for p in text_embs:
                                if p["emb"] is not None:
                                    arr = np.asarray(p["emb"], dtype=np.float32).flatten()
                                    if arr.size > 0:
                                        pos_vectors.append(arr)
                                        pos_weights.append(p["weight"])
                                        pos_words.append(p["text"])
                                        
                            if not pos_vectors:
                                continue
                            txt_mat = np.array(pos_vectors, dtype=np.float32)  # Shape: (M, 512)
                            
                            # Fast matrix dot product: (N, 512) x (512, M) -> (N, M)
                            sim_matrix = np.dot(img_mat, txt_mat.T)
                            
                            # Scale positive score to percentage 0..100
                            mapped_scores = (sim_matrix - 0.14) / (0.28 - 0.14) * 100.0
                            mapped_scores = np.clip(mapped_scores, 0, 100).astype(int)
                            
                            # 1. Позитивная "пачка": проверяем пороги для каждого тега индивидуально
                            passes_pos = np.zeros(len(img_mat), dtype=bool)
                            best_score_per_img = np.zeros(len(img_mat), dtype=int)
                            tag_scores_per_img = [{} for _ in range(len(img_mat))]
                            
                            for m in range(len(pos_vectors)):
                                threshold = pos_weights[m] if pos_weights[m] is not None else self.request.threshold
                                passes_this = mapped_scores[:, m] >= threshold
                                passes_pos = passes_pos | passes_this
                                best_score_per_img = np.maximum(best_score_per_img, mapped_scores[:, m])
                                word = pos_words[m]
                                for idx in range(len(img_mat)):
                                    tag_scores_per_img[idx][word] = int(mapped_scores[idx, m])
                                
                            match_indices = np.where(passes_pos)[0]
                            
                            if len(match_indices) > 0 and neg_embs:
                                # 2. Негативный фильтр: проверяем каждый антипаттерн индивидуально
                                valid_mask = np.ones(len(match_indices), dtype=bool)
                                
                                for n_data in neg_embs:
                                    n_vec = np.asarray(n_data["emb"], dtype=np.float32).flatten().reshape(1, -1)
                                    n_weight = n_data["weight"]
                                    n_word = f"-{n_data['text']}"
                                    
                                    n_sims = np.dot(img_mat[match_indices], n_vec.T).flatten()
                                    n_mapped = (n_sims - 0.14) / (0.28 - 0.14) * 100.0
                                    n_mapped = np.clip(n_mapped, 0, 100).astype(int)
                                    
                                    # Если вес задан вручную, он означает прямой порог отсечения
                                    if n_weight is not None:
                                        threshold = n_weight
                                    else:
                                        # Если нет - используем глобальную строгость (она тоже задается как прямой порог)
                                        threshold = self.request.neg_threshold
                                        
                                    valid_mask &= (n_mapped < threshold)
                                    
                                    for i, idx in enumerate(match_indices):
                                        tag_scores_per_img[idx][n_word] = int(n_mapped[i])
                                        
                                match_indices = match_indices[valid_mask]
                            
                            if len(match_indices) > 0:
                                if group_name not in groups_dict:
                                    groups_dict[group_name] = []
                                for idx in match_indices:
                                    match_file = AiMatchFile(
                                        path=filepaths[idx], 
                                        score=int(best_score_per_img[idx]), 
                                        matched_reference_id=group_name,
                                        tag_scores=tag_scores_per_img[idx]
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
                    labels = _agglomerative_clustering_numpy(X, eps=eps, min_samples=2, linkage="average")
                    
                    # Вычисляем центроиды кластеров для определения % сходства
                    cluster_centroids = {}
                    for c_id in set(labels):
                        if c_id == -1: continue
                        cluster_points = X[labels == c_id]
                        centroid = np.mean(cluster_points, axis=0)
                        centroid /= np.clip(np.linalg.norm(centroid), 1e-9, None)
                        cluster_centroids[c_id] = centroid
                    
                    for i, label in enumerate(labels):
                        if label == -1: continue # noise
                        group_name = f"Группа Лиц {label+1}"
                        if group_name not in groups_dict:
                            groups_dict[group_name] = []
                            
                        fp, face = file_face_map[i]
                        # Avoid duplicates in same group
                        if not any(f.path == fp for f in groups_dict[group_name]):
                            rect = Rect(face["bbox"][0], face["bbox"][1], face["bbox"][2], face["bbox"][3])
                            
                            # Реальное сходство вместо жесткого 100.0
                            sim = float(np.dot(X[i] / np.clip(np.linalg.norm(X[i]), 1e-9, None), cluster_centroids[label]))
                            mapped_score = (sim - 0.3) / (0.8 - 0.3) * 100.0
                            score = int(np.clip(mapped_score, 0, 100))
                            
                            match_file = AiMatchFile(path=fp, score=score, matched_bbox=rect)
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
                    labels = _agglomerative_clustering_numpy(X, eps=eps, min_samples=2, linkage="average")
                    
                    cluster_centroids = {}
                    for c_id in set(labels):
                        if c_id == -1: continue
                        cluster_points = X[labels == c_id]
                        centroid = np.mean(cluster_points, axis=0)
                        centroid /= np.clip(np.linalg.norm(centroid), 1e-9, None)
                        cluster_centroids[c_id] = centroid
                    
                    for i, label in enumerate(labels):
                        if label == -1: continue 
                        group_name = f"Группа Объектов {label+1}"
                        if group_name not in groups_dict:
                            groups_dict[group_name] = []
                            
                        fp = file_map[i]
                        
                        sim = float(np.dot(X[i] / np.clip(np.linalg.norm(X[i]), 1e-9, None), cluster_centroids[label]))
                        mapped_score = (sim - 0.6) / (0.95 - 0.6) * 100.0
                        score = int(np.clip(mapped_score, 0, 100))
                        
                        match_file = AiMatchFile(path=fp, score=score)
                        groups_dict[group_name].append(match_file)

            elif self.request.task_type == AiTaskType.FIND_BY_REFERENCES and self.classifier is not None:
                # Use classifier logic natively
                for fp in valid_files:
                    if self.is_cancelled: return
                    results_dict = self.classifier.classify_file(fp, self.request.neg_threshold)
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
            
            # Подсчёт суммарного размера найденных файлов
            total_matched_bytes = 0
            for g in response_groups:
                for mf in g.files:
                    try:
                        total_matched_bytes += os.path.getsize(mf.path)
                    except:
                        pass
            
            response = AiSearchResponse(groups=response_groups)
            
            self.signals.progress.emit(STAGE_ANALYSIS, 100.0, "Готово", scanned_files, len(response_groups), total_matched_bytes, scanned_bytes, total_matches, 0)
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
                 classifier=None,
                 defective_callback=None):
        
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
        if defective_callback:
            self.active_worker.signals.defective_faces.connect(defective_callback)
            
        QThreadPool.globalInstance().start(self.active_worker)
        
    def cancel_search(self):
        if self.active_worker:
            self.active_worker.is_cancelled = True
            self.active_worker = None
