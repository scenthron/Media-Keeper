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
        
        self.arcface_path = os.path.join(self.models_dir, "face_detection", "w600k_r50.onnx")
        self.scrfd_path = os.path.join(self.models_dir, "face_detection", "det_10g.onnx")
        self.clip_dir = os.path.join(self.models_dir, "image_vision")
        
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
        dense_ok = os.path.exists(os.path.join(self.clip_dir, "text_multi", "dense.safetensors")) and os.path.getsize(os.path.join(self.clip_dir, "text_multi", "dense.safetensors")) > 100
        tok_ok = os.path.exists(os.path.join(self.clip_dir, "text_multi", "tokenizer.json")) and os.path.getsize(os.path.join(self.clip_dir, "text_multi", "tokenizer.json")) > 100
        
        # Проверка наличия библиотеки DirectML, если она включена в настройках
        dml_ok = True
        try:
            import configparser
            from logic_paths import get_app_data_dir
            cfg_path = os.path.join(get_app_data_dir(), "settings.ini")
            cp = configparser.ConfigParser()
            if os.path.exists(cfg_path):
                cp.read(cfg_path, encoding='utf-8')
            
            use_dml = True
            if "Main" in cp:
                use_dml = cp.getboolean("Main", "use_directml", fallback=True)
                
            if use_dml:
                import sys
                py_ver = f"cp{sys.version_info.major}{sys.version_info.minor}"
                dml_whl = os.path.join(self.models_dir, "onnx_directml", f"onnxruntime_directml_{py_ver}.whl")
                dml_path = os.path.join(self.models_dir, "onnx_directml", "onnxruntime")
                dml_ok = os.path.exists(dml_whl) and os.path.exists(dml_path)
        except Exception:
            pass
            
        return arcface_ok and scrfd_ok and clip_vis_ok and clip_txt_ok and tok_ok and dense_ok and dml_ok

    def check_legacy_models(self) -> list:
        """Проверяет наличие старых (неиспользуемых) моделей и возвращает список путей к ним."""
        legacy_names = {
            "1k3d68.onnx", "2d106det.onnx", "genderage.onnx", "glintr100.onnx", 
            "scrfd_10g_bnkps.onnx", "mobilenetv3_large.onnx", 
            "face_recognition_sface.onnx", "face_detection_yunet.onnx",
            "ai_cache.db", "ai_cache.db-wal", "ai_cache.db-shm"
        }
        found = []
        from logic_paths import get_app_data_dir
        app_dir = get_app_data_dir()
        
        # Рекурсивный обход директории .mediakeeper
        for root, dirs, files in os.walk(app_dir):
            for file in files:
                if file.lower() in legacy_names:
                    found.append(os.path.join(root, file))
                    
        # Отдельная проверка для старой модели CLIP (model.onnx в папке text, а не text_multi)
        old_clip_path = os.path.join(self.clip_dir, "text", "model.onnx")
        if os.path.exists(old_clip_path):
            found.append(old_clip_path)
            
        return found

    def clean_legacy_models(self, legacy_files: list) -> int:
        """Удаляет старые модели и возвращает объем освобожденного места в байтах."""
        freed_bytes = 0
        import shutil
        for path in legacy_files:
            try:
                size = os.path.getsize(path)
                os.remove(path)
                freed_bytes += size
                logging.info(f"Удалена старая ИИ-модель: {path}")
            except Exception as e:
                logging.error(f"Не удалось удалить старую модель {path}: {e}")
        
        # Попытка удалить пустую старую папку
        old_text_dir = os.path.join(self.clip_dir, "text")
        if os.path.exists(old_text_dir):
            try:
                shutil.rmtree(old_text_dir)
            except:
                pass
                
        return freed_bytes

    def download_models(self, progress_callback=None, stop_checker=None) -> bool:
        """Скачивает реальные ИИ-модели по прямым интернет-ссылкам."""
        import requests
        import urllib3
        import sys
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        py_ver = f"cp{sys.version_info.major}{sys.version_info.minor}"
        dml_url = "https://files.pythonhosted.org/packages/09/17/82ba888edc50392660c84f88f3d001a8ad9048a2cff43b03bf4bc0658f7a/onnxruntime_directml-1.15.1-cp311-cp311-win_amd64.whl"
        if py_ver == "cp310":
            dml_url = "https://files.pythonhosted.org/packages/1e/23/2a92ebfe9059b4dfa2c0d2f2327d0e3bbdae02188e1d826f15e6560f9fbb/onnxruntime_directml-1.15.1-cp310-cp310-win_amd64.whl"

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
                "name": "CLIP Text Model Multi (text_multi/model.onnx)",
                "dest": os.path.join(self.clip_dir, "text_multi", "model.onnx"),
                "urls": [
                    "https://huggingface.co/sentence-transformers/clip-ViT-B-32-multilingual-v1/resolve/main/onnx/model.onnx"
                ]
            },
            {
                "name": "CLIP Dense Layer Multi (text_multi/dense.safetensors)",
                "dest": os.path.join(self.clip_dir, "text_multi", "dense.safetensors"),
                "urls": [
                    "https://huggingface.co/sentence-transformers/clip-ViT-B-32-multilingual-v1/resolve/main/2_Dense/model.safetensors"
                ]
            },
            {
                "name": "CLIP Tokenizer Multi (text_multi/tokenizer.json)",
                "dest": os.path.join(self.clip_dir, "text_multi", "tokenizer.json"),
                "urls": [
                    "https://huggingface.co/sentence-transformers/clip-ViT-B-32-multilingual-v1/resolve/main/tokenizer.json"
                ]
            },
            {
                "name": f"DirectML GPU Driver (onnxruntime_directml_{py_ver}.whl)",
                "dest": os.path.join(self.models_dir, "onnx_directml", f"onnxruntime_directml_{py_ver}.whl"),
                "urls": [dml_url]
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
                                
                                # Распаковка архива, если это .whl (для DirectML)
                                if dest.endswith(".whl"):
                                    try:
                                        import zipfile
                                        import shutil
                                        extract_dir = os.path.dirname(dest)
                                        ort_dir = os.path.join(extract_dir, "onnxruntime")
                                        if os.path.exists(ort_dir):
                                            try:
                                                shutil.rmtree(ort_dir)
                                            except Exception:
                                                pass
                                        with zipfile.ZipFile(dest, 'r') as zip_ref:
                                            zip_ref.extractall(extract_dir)
                                        logging.info(f"Архив {item['name']} успешно распакован в {extract_dir}")
                                    except Exception as e:
                                        logging.error(f"Ошибка при распаковке {item['name']}: {e}")
                                        if os.path.exists(ort_dir):
                                            try: shutil.rmtree(ort_dir)
                                            except: pass
                                        return False
                                
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
            self.detector = SCRFD(self.scrfd_path, use_gpu=use_gpu)
            opts = ort.SessionOptions()
            # Возвращаем оптимизации и многопоточность по умолчанию
            providers = ['DmlExecutionProvider', 'CPUExecutionProvider'] if use_gpu else ['CPUExecutionProvider']
            self.arcface_session = ort.InferenceSession(self.arcface_path, sess_options=opts, providers=providers)
            
            # 2. Загрузка CLIP
            from .logic_clip import CLIPSearcher
            self.clip_searcher = CLIPSearcher(use_gpu=use_gpu)
            if not self.clip_searcher.is_loaded:
                return False
                
            self._is_initialized = True
            self._reset_idle_timer()
            return True
            
        except Exception as e:
            logging.error(f"Ошибка инициализации моделей: {e}")
            return False

    def extract_faces(self, image_path: str, img_rgb: np.ndarray = None, conf_thresh: float = 0.70) -> list | None:
        """Находит все лица на фото и возвращает список словарей {"bbox": [...], "descriptor": np.ndarray}. Возвращает None если файл битый."""
        if not self._is_initialized:
            return None
            
        try:
            if img_rgb is None:
                from utils_io import safe_cv2_imread
                img = safe_cv2_imread(image_path)
                if img is None:
                    logging.warning(f"[DEBUG-AI] Не удалось прочитать изображение (битый файл): {image_path}")
                    return None
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                
            logging.debug(f"[DEBUG-AI] Запускаем SCRFD для {image_path} (shape: {img_rgb.shape})")
            # Используем динамический порог уверенности (по умолчанию 0.70)
            bboxes, kpss = self.detector.detect(img_rgb, conf_thresh=conf_thresh, input_size=(640, 640))
            logging.debug(f"[DEBUG-AI] SCRFD успешно завершен для {image_path}, найдено {len(bboxes) if bboxes is not None else 0} лиц.")
        except Exception as e:
            logging.error(f"[DEBUG-AI] Ошибка во время детекции лиц для {image_path}: {e}", exc_info=True)
            return None
        
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
            
            logging.debug(f"[DEBUG-AI] Запускаем ArcFace onnxruntime для {image_path} (face {i})")
            # ArcFace (w600k/buffalo_l) ожидает BGR формат на входе! Поскольку face_img у нас RGB, делаем swapRB=True
            blob = cv2.dnn.blobFromImage(face_img, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
            blob = np.ascontiguousarray(blob, dtype=np.float32)
            net_out = self.arcface_session.run(None, {self.arcface_session.get_inputs()[0].name: blob})[0]
            logging.debug(f"[DEBUG-AI] Успешно получен ArcFace вектор для {image_path} (face {i})")
            
            emb = net_out[0]
            emb = emb / np.linalg.norm(emb)
            
            faces.append({
                "bbox": bbox.tolist(),
                "descriptor": emb
            })
            
        return faces

    def extract_clip_embedding(self, image_path: str, img_rgb: np.ndarray = None) -> np.ndarray | None:
        """Возвращает CLIP-вектор сцены (512-d)."""
        if not self._is_initialized:
            return None
        self._reset_idle_timer()
        try:
            return self.clip_searcher.encode_image(image_path, img_rgb)
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
            "Общий объем загрузки составит около 1.5 ГБ.\n\n"
            "Во время загрузки программа может ненадолго перестать отвечать, пожалуйста, дождитесь завершения.\n"
            "Сейчас убедитесь, что вы распаковали модели в папку:\n"
            f"{engine.models_dir}"
        )
        msg.exec()
        return False
    return True
