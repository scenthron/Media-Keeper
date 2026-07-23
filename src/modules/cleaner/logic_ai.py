import os
import logging
import cv2
import numpy as np
import onnxruntime as ort
from logic_paths import get_models_dir
from PyQt6.QtWidgets import QMessageBox

class AiEngine:
    def __init__(self):
        self.models_dir = get_models_dir()
        
        self.arcface_path = os.path.join(self.models_dir, "w600k_r50.onnx")
        self.scrfd_path = os.path.join(self.models_dir, "det_10g.onnx")
        self.clip_dir = os.path.join(self.models_dir, "clip")
        
        self.clip_searcher = None
        self.detector = None
        self.arcface_session = None
        
        self._is_initialized = False
        self._idle_timer = None
        self._init_timer()

    def _init_timer(self):
        try:
            from PyQt6.QtCore import QTimer
            self._idle_timer = QTimer()
            self._idle_timer.setSingleShot(True)
            self._idle_timer.setInterval(10 * 60 * 1000)  # 10 минут
            self._idle_timer.timeout.connect(self.unload_models)
        except Exception as e:
            logging.error(f"Ошибка инициализации таймера простоя ИИ: {e}")

    def _reset_idle_timer(self):
        if self._idle_timer:
            try:
                from PyQt6.QtCore import QMetaObject, Qt, QThread, QCoreApplication
                app = QCoreApplication.instance()
                if app and QThread.currentThread() != app.thread():
                    QMetaObject.invokeMethod(self._idle_timer, "start", Qt.ConnectionType.QueuedConnection)
                else:
                    self._idle_timer.start()
            except Exception as e:
                logging.warning(f"Сбой перезапуска таймера простоя: {e}")

    def unload_models(self):
        """Освобождает модели нейросетей из ОЗУ после 10 минут простоя."""
        if not self._is_initialized:
            return
        logging.info("[AiEngine] Истекло 10 минут простоя. Выгрузка ИИ-моделей из памяти для экономии ОЗУ...")
        self.clip_searcher = None
        self.detector = None
        self.arcface_session = None
        self._is_initialized = False
        import gc
        gc.collect()

    def are_models_present(self) -> bool:
        """Проверяет физическое наличие и корректность всех файлов ИИ-моделей."""
        arcface_ok = os.path.exists(self.arcface_path) and os.path.getsize(self.arcface_path) > 1000
        scrfd_ok = os.path.exists(self.scrfd_path) and os.path.getsize(self.scrfd_path) > 1000
        clip_vis_ok = os.path.exists(os.path.join(self.clip_dir, "vision", "model.onnx")) and os.path.getsize(os.path.join(self.clip_dir, "vision", "model.onnx")) > 1000
        clip_txt_ok = os.path.exists(os.path.join(self.clip_dir, "text_multi", "model.onnx")) and os.path.getsize(os.path.join(self.clip_dir, "text_multi", "model.onnx")) > 1000
        tok_ok = os.path.exists(os.path.join(self.clip_dir, "text_multi", "tokenizer.json")) and os.path.getsize(os.path.join(self.clip_dir, "text_multi", "tokenizer.json")) > 100
        return arcface_ok and scrfd_ok and clip_vis_ok and clip_txt_ok and tok_ok

    def download_models(self, progress_callback=None, stop_checker=None) -> bool:
        """Скачивает реальные ИИ-модели по прямым интернет-ссылкам."""
        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        models_to_download = [
            {
                "name": "SCRFD Face Detector (det_10g.onnx)",
                "dest": self.scrfd_path,
                "urls": [
                    "https://huggingface.co/artemonlysuno/det_10g/resolve/main/det_10g.onnx"
                ]
            },
            {
                "name": "ArcFace Model (w600k_r50.onnx)",
                "dest": self.arcface_path,
                "urls": [
                    "https://huggingface.co/richarrrddd/w600k_r50_v1/resolve/main/w600k_r50.onnx"
                ]
            },
            {
                "name": "CLIP Vision Model (vision/model.onnx)",
                "dest": os.path.join(self.clip_dir, "vision", "model.onnx"),
                "urls": [
                    "https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main/onnx/vision_model.onnx"
                ]
            },
            {
                "name": "CLIP Text Model (text_multi/model.onnx)",
                "dest": os.path.join(self.clip_dir, "text_multi", "model.onnx"),
                "urls": [
                    "https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main/onnx/text_model.onnx"
                ]
            },
            {
                "name": "CLIP Tokenizer (text_multi/tokenizer.json)",
                "dest": os.path.join(self.clip_dir, "text_multi", "tokenizer.json"),
                "urls": [
                    "https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main/tokenizer.json"
                ]
            }
        ]

        try:
            for item in models_to_download:
                if stop_checker and stop_checker():
                    logging.info("Загрузка ИИ-моделей остановлена пользователем.")
                    return False

                dest = item["dest"]
                os.makedirs(os.path.dirname(dest), exist_ok=True)

                # Проверяем, если файл уже существует и не пустой
                if os.path.exists(dest) and os.path.getsize(dest) > 1000:
                    logging.info(f"Файл {item['name']} уже существует, пропуск загрузки.")
                    continue

                download_success = False
                for url in item["urls"]:
                    if stop_checker and stop_checker():
                        logging.info("Загрузка ИИ-моделей остановлена пользователем.")
                        return False

                    logging.info(f"Попытка скачивания {item['name']} с {url}...")
                    try:
                        resp = requests.get(url, stream=True, headers=headers, allow_redirects=True, verify=False, timeout=30)
                        if resp.status_code == 200:
                            total_size = int(resp.headers.get("content-length", 0))
                            downloaded = 0
                            tmp_dest = dest + ".tmp"
                            
                            stopped_early = False
                            with open(tmp_dest, "wb") as f:
                                for chunk in resp.iter_content(chunk_size=65536):
                                    if stop_checker and stop_checker():
                                        logging.info(f"Загрузка файла {item['name']} отменена пользователем.")
                                        stopped_early = True
                                        break
                                    if chunk:
                                        f.write(chunk)
                                        downloaded += len(chunk)
                                        if progress_callback:
                                            progress_callback(item["name"], downloaded, total_size)

                            if stopped_early:
                                if os.path.exists(tmp_dest):
                                    try: os.remove(tmp_dest)
                                    except: pass
                                return False

                            if os.path.exists(tmp_dest) and os.path.getsize(tmp_dest) > 100:
                                if os.path.exists(dest):
                                    os.remove(dest)
                                os.rename(tmp_dest, dest)
                                download_success = True
                                logging.info(f"Успешно скачан файл {item['name']}")
                                break
                        else:
                            logging.warning(f"HTTP статус {resp.status_code} при попытке скачивания {url}")
                    except Exception as err:
                        logging.warning(f"Сбой загрузки с {url}: {err}")
                        if os.path.exists(dest + ".tmp"):
                            try: os.remove(dest + ".tmp")
                            except: pass

                if not download_success and not (os.path.exists(dest) and os.path.getsize(dest) > 1000):
                    logging.error(f"Не удалось скачать модель: {item['name']}")
                    return False

            return True
        except Exception as e:
            logging.error(f"Критическая ошибка загрузки нейросетей: {e}", exc_info=True)
            return False

    def initialize_sessions(self, use_gpu: bool = True) -> bool:
        if self._is_initialized:
            return True
            
        if not self.are_models_present():
            logging.error("Невозможно инициализировать ИИ: отсутствуют файлы моделей.")
            return False
            
        try:
            # 1. Загрузка InsightFace (SCRFD + ArcFace)
            from .logic_scrfd import SCRFD
            self.detector = SCRFD(self.scrfd_path)
            opts = ort.SessionOptions()
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
            opts.intra_op_num_threads = 2
            opts.inter_op_num_threads = 2
            self.arcface_session = ort.InferenceSession(self.arcface_path, sess_options=opts, providers=['CPUExecutionProvider'])
            
            # 2. Загрузка CLIP
            from .logic_clip import CLIPSearcher
            self.clip_searcher = CLIPSearcher()
            if not self.clip_searcher.is_loaded:
                return False
                
            self._is_initialized = True
            self._reset_idle_timer()
            return True
            
        except Exception as e:
            logging.error(f"Ошибка инициализации моделей: {e}")
            return False

    def extract_faces(self, image_path: str) -> list:
        """Находит все лица на фото и возвращает список словарей {"bbox": [...], "descriptor": np.ndarray}"""
        if not self._is_initialized:
            return []
            
        from utils_io import safe_cv2_imread
        img = safe_cv2_imread(image_path)
        if img is None:
            return []
            
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        bboxes, kpss = self.detector.detect(img_rgb, conf_thresh=0.5, input_size=(640, 640))
        
        if bboxes is None or kpss is None or len(bboxes) == 0:
            return []
            
        faces = []
        for i in range(len(bboxes)):
            bbox = bboxes[i, :4]
            kps = kpss[i]
            
            src = np.array([
                [38.2946, 51.6963],
                [73.5318, 51.5014],
                [56.0252, 71.7366],
                [41.5493, 92.3655],
                [70.7299, 92.2041]
            ], dtype=np.float32)
            M, _ = cv2.estimateAffinePartial2D(kps, src)
            if M is None:
                continue
            
            face_img = cv2.warpAffine(img_rgb, M, (112, 112), borderValue=0.0)
            
            blob = cv2.dnn.blobFromImage(face_img, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=False)
            net_out = self.arcface_session.run(None, {self.arcface_session.get_inputs()[0].name: blob})[0]
            emb = net_out[0]
            emb = emb / np.linalg.norm(emb)
            
            faces.append({
                "bbox": bbox.tolist(),
                "descriptor": emb
            })
            
        return faces

    def extract_clip_embedding(self, image_path: str) -> np.ndarray | None:
        """Возвращает CLIP-вектор сцены (512-d)."""
        if not self._is_initialized:
            return None
        self._reset_idle_timer()
        try:
            return self.clip_searcher.encode_image(image_path)
        except Exception as e:
            logging.error(f"CLIP Image encode error for {image_path}: {e}")
            return None
            
    def extract_text_embedding(self, text: str) -> np.ndarray | None:
        """Возвращает CLIP-вектор текста (512-d)."""
        if not self._is_initialized:
            return None
        self._reset_idle_timer()
        return self.clip_searcher.encode_text(text)

def check_models_availability(parent_widget=None):
    """
    Показывает диалог с уведомлением о необходимости скачать новые модели.
    """
    engine = AiEngine()
    if not engine.are_models_present():
        msg = QMessageBox(parent_widget)
        msg.setWindowTitle("Требуются новые нейросети")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(
            "Для работы нового сверхточного ИИ-поиска необходимо скачать новые модели (CLIP и InsightFace).\n"
            "Общий объем загрузки составит около 1 ГБ.\n\n"
            "Внимание: загрузка будет интегрирована в следующих версиях.\n"
            "Сейчас убедитесь, что вы распаковали модели в папку:\n"
            f"{engine.models_dir}"
        )
        msg.exec()
        return False
    return True
