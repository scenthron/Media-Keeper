import os
import cv2
import numpy as np
import onnxruntime as ort
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool

class AILabWorker(QRunnable):
    class Signals(QObject):
        progress = pyqtSignal(int, int) # current, total
        result_found = pyqtSignal(str, float) # filepath, similarity
        finished = pyqtSignal()
        error = pyqtSignal(str)

    def __init__(self, folder_path, search_mode, ref_image_path=None, neg_image_path=None, text_query=None, cache=None):
        super().__init__()
        self.folder_path = folder_path
        self.search_mode = search_mode # 'face' or 'text'
        self.ref_image_path = ref_image_path
        self.neg_image_path = neg_image_path
        self.text_query = text_query
        self.cache = cache if cache is not None else {'face': {}, 'text': {}} # { mode: { filepath: feature_vector } }
        
        self.signals = self.Signals()
        self.is_cancelled = False

        from logic_paths import get_models_dir
        
        # Paths to models
        self.arcface_path = os.path.join(os.path.expanduser('~/.mediakeeper/models'), 'w600k_r50.onnx')
        self.scrfd_path = os.path.join(os.path.expanduser('~/.mediakeeper/models'), 'det_10g.onnx')

    def run(self):
        try:
            if self.search_mode == 'face':
                if not os.path.exists(self.arcface_path) or not os.path.exists(self.scrfd_path):
                    self.signals.error.emit("Модели InsightFace (w600k_r50.onnx или det_10g.onnx) не найдены!")
                    return
                from .logic_scrfd import SCRFD
                detector = SCRFD(self.scrfd_path)
                arcface_session = ort.InferenceSession(self.arcface_path, providers=['CPUExecutionProvider'])
                
                ref_feature = self._get_face_feature(self.ref_image_path, detector, arcface_session)
                if ref_feature is None:
                    self.signals.error.emit("Не удалось найти лицо на эталонном фото!")
                    return
                    
                neg_feature = None
                if self.neg_image_path and os.path.exists(self.neg_image_path):
                    neg_feature = self._get_face_feature(self.neg_image_path, detector, arcface_session)

            elif self.search_mode == 'text':
                from .logic_clip import CLIPSearcher
                self.clip_searcher = CLIPSearcher()
                if not self.clip_searcher.is_loaded:
                    self.signals.error.emit("Не удалось загрузить модели CLIP!")
                    return
                
                ref_feature = self.clip_searcher.encode_text(self.text_query)
                if ref_feature is None:
                    self.signals.error.emit("Ошибка обработки текста CLIP!")
                    return

            # Gather files
            valid_exts = {'.jpg', '.jpeg', '.png', '.bmp'}
            files_to_scan = []
            for root, _, files in os.walk(self.folder_path):
                for f in files:
                    if os.path.splitext(f)[1].lower() in valid_exts:
                        files_to_scan.append(os.path.join(root, f))

            total = len(files_to_scan)
            for i, file_path in enumerate(files_to_scan):
                if self.is_cancelled:
                    self.signals.error.emit("Сканирование остановлено пользователем.")
                    return
                
                self.signals.progress.emit(i + 1, total)

                try:
                    feature = None
                    if file_path in self.cache[self.search_mode]:
                        feature = self.cache[self.search_mode][file_path]
                    else:
                        if self.search_mode == 'face':
                            feature = self._get_face_feature(file_path, detector, arcface_session)
                        elif self.search_mode == 'text':
                            feature = self.clip_searcher.encode_image(file_path)
                            
                        # Save to cache even if None (to avoid rescanning broken images)
                        self.cache[self.search_mode][file_path] = feature

                    if feature is not None:
                        if self.search_mode == 'face':
                            score_raw = np.dot(ref_feature, feature) / (np.linalg.norm(ref_feature) * np.linalg.norm(feature))
                            mapped_score = (score_raw - 0.35) / (0.85 - 0.35) * 100
                            mapped_score = max(0, min(100, int(mapped_score)))
                            
                            if self.search_mode == 'face' and neg_feature is not None:
                                neg_score_raw = np.dot(neg_feature, feature) / (np.linalg.norm(neg_feature) * np.linalg.norm(feature))
                                neg_mapped = (neg_score_raw - 0.35) / (0.85 - 0.35) * 100
                                neg_mapped = max(0, min(100, int(neg_mapped)))
                                mapped_score = mapped_score - (neg_mapped * 0.5)
                                mapped_score = max(0, mapped_score)
                                
                        elif self.search_mode == 'text':
                            score_raw = np.dot(ref_feature, feature) # text_emb and img_emb are already L2 normalized
                            # CLIP raw scores usually range from 0.15 (unrelated) to 0.35 (perfect match)
                            # Map 0.20 to 0%, 0.32 to 100%
                            mapped_score = (score_raw - 0.20) / (0.32 - 0.20) * 100
                            mapped_score = max(0, min(100, int(mapped_score)))

                        if mapped_score > 0:
                            self.signals.result_found.emit(file_path, float(mapped_score))
                except Exception as e:
                    continue # Skip broken images

            self.signals.finished.emit()

        except Exception as e:
            self.signals.error.emit(str(e))

    def _get_face_feature(self, img_path, detector, arcface_session):
        paths = img_path if isinstance(img_path, list) else [img_path]
        features = []
        
        for path in paths:
            # Safe read with numpy for cyrillic paths
            stream = open(path, "rb")
            bytes_array = bytearray(stream.read())
            numpyarray = np.asarray(bytes_array, dtype=np.uint8)
            img = cv2.imdecode(numpyarray, cv2.IMREAD_COLOR)
            stream.close()
            
            if img is None: continue
            
            bboxes, kpss = detector.detect(img, input_size=(320, 320))
            if bboxes.shape[0] > 0:
                largest_idx = np.argmax((bboxes[:, 2] - bboxes[:, 0]) * (bboxes[:, 3] - bboxes[:, 1]))
                kps = kpss[largest_idx]
                
                arcface_dst = np.array([
                    [38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
                    [41.5493, 92.3655], [70.7299, 92.2041]
                ], dtype=np.float32)
                tform = cv2.estimateAffinePartial2D(kps, arcface_dst, method=cv2.LMEDS)[0]
                if tform is None: continue
                aligned_face = cv2.warpAffine(img, tform, (112, 112))
                
                input_name = arcface_session.get_inputs()[0].name
                blob = cv2.dnn.blobFromImage(aligned_face, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
                feature = arcface_session.run(None, {input_name: blob})[0][0]
                feature = feature / np.linalg.norm(feature)
                features.append(feature)
                
        if not features:
            return None
            
        avg_feature = np.mean(features, axis=0)
        avg_feature = avg_feature / np.linalg.norm(avg_feature)
        return avg_feature
