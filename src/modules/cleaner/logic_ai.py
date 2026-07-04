import os
import sys
import logging
import requests
import numpy as np
import onnxruntime as ort
from PIL import Image
import cv2

from logic_paths import get_app_data_dir

# Ссылки на стабильные версии моделей
MODEL_URLS = {
    "mobilenetv3_large.onnx": "https://huggingface.co/onnx-community/mobilenetv3_large_100.ra_in1k/resolve/main/onnx/model.onnx",
    "face_detection_yunet.onnx": "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "face_recognition_sface.onnx": "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
}

class AiEngine:
    def __init__(self):
        self.models_dir = os.path.join(get_app_data_dir(), "models")
        os.makedirs(self.models_dir, exist_ok=True)
        
        self.mobilenet_path = os.path.join(self.models_dir, "mobilenetv3_large.onnx")
        self.yunet_path = os.path.join(self.models_dir, "face_detection_yunet.onnx")
        self.sface_path = os.path.join(self.models_dir, "face_recognition_sface.onnx")
        
        self.ort_session = None
        self.face_detector = None
        self.face_recognizer = None
        self._is_initialized = False

    def are_models_present(self) -> bool:
        """Проверяет физическое наличие всех трех файлов моделей."""
        return (os.path.exists(self.mobilenet_path) and 
                os.path.exists(self.yunet_path) and 
                os.path.exists(self.sface_path))

    def download_models(self, progress_callback=None) -> bool:
        """
        Скачивает недостающие файлы моделей с обновлением прогресса.
        progress_callback: функция, принимающая (filename, bytes_downloaded, total_bytes)
        """
        for filename, url in MODEL_URLS.items():
            dest_path = os.path.join(self.models_dir, filename)
            if os.path.exists(dest_path):
                # Проверим, не пустой ли файл
                if os.path.getsize(dest_path) > 10000:
                    continue
            
            logging.info(f"Начало загрузки модели {filename} из {url}")
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                response = requests.get(url, headers=headers, stream=True, timeout=30)
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))
                
                downloaded = 0
                with open(dest_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback:
                                progress_callback(filename, downloaded, total_size)
                logging.info(f"Модель {filename} успешно скачана.")
            except Exception as e:
                logging.error(f"Ошибка загрузки модели {filename}: {e}", exc_info=True)
                if os.path.exists(dest_path):
                    try: os.remove(dest_path)
                    except: pass
                return False
        return True

    def initialize_sessions(self, use_gpu: bool = True) -> bool:
        """Инициализирует сессии ONNX Runtime и OpenCV для моделей."""
        if self._is_initialized and getattr(self, "_last_gpu_flag", None) == use_gpu:
            return True
            
        if not self.are_models_present():
            logging.error("Невозможно инициализировать ИИ: отсутствуют файлы моделей.")
            return False
            
        self._last_gpu_flag = use_gpu
        self.gpu_error_msg = ""
        self.is_gpu_active = False
            
        try:
            # 1. Общая классификация через ONNX Runtime
            # Отключаем лишнее логирование ORT
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.log_severity_level = 3
            
            providers = ['CPUExecutionProvider']
            if use_gpu:
                providers = ['CUDAExecutionProvider', 'DmlExecutionProvider'] + providers
                
            try:
                self.ort_session = ort.InferenceSession(self.mobilenet_path, sess_options=opts, providers=providers)
                active_providers = self.ort_session.get_providers()
                if any(p in active_providers for p in ['CUDAExecutionProvider', 'DmlExecutionProvider']):
                    self.is_gpu_active = True
                elif use_gpu:
                    self.gpu_error_msg = "Видеокарта не поддерживается текущей сборкой onnxruntime или отсутствуют драйверы (CUDA/DirectML)."
            except Exception as e:
                self.gpu_error_msg = f"Ошибка GPU: {str(e)}"
                logging.warning(f"Ошибка при инициализации GPU для ORT: {e}, откат на CPU")
                self.ort_session = ort.InferenceSession(self.mobilenet_path, sess_options=opts, providers=['CPUExecutionProvider'])
            
            # Функция-помощник для обхода бага OpenCV с кириллицей в путях на Windows
            def get_ascii_path(path_str):
                import sys, os
                if sys.platform == 'win32':
                    try:
                        import ctypes
                        buffer_size = 256
                        buffer = ctypes.create_unicode_buffer(buffer_size)
                        dir_name = os.path.dirname(path_str)
                        base_name = os.path.basename(path_str)
                        if ctypes.windll.kernel32.GetShortPathNameW(dir_name, buffer, buffer_size):
                            return os.path.join(buffer.value, base_name)
                    except Exception:
                        pass
                return path_str

            yunet_safe = get_ascii_path(self.yunet_path)
            sface_safe = get_ascii_path(self.sface_path)
            
            # 2. Детектор лиц YuNet (OpenCV)
            try:
                import json
                from logic_paths import get_app_data_dir
                settings_path = os.path.join(get_app_data_dir(), "Ai_assets", "ai_settings.json")
                with open(settings_path, 'r', encoding='utf-8') as f:
                    det_threshold = json.load(f).get("face_det_threshold", 65.0) / 100.0
            except Exception:
                det_threshold = 0.65
                
            self.face_detector = cv2.FaceDetectorYN.create(yunet_safe, "", (320, 320), score_threshold=det_threshold)
            
            # 3. Распознаватель лиц SFace (OpenCV)
            self.face_recognizer = cv2.FaceRecognizerSF.create(sface_safe, "")
            
            self._is_initialized = True
            logging.info("ИИ-модели успешно инициализированы.")
            return True
        except Exception as e:
            logging.error(f"Ошибка инициализации ИИ-сессий: {e}", exc_info=True)
            return False

    def extract_image_embedding(self, image_path: str) -> np.ndarray:
        """
        Извлекает 960-мерный вектор признаков (embedding) изображения с помощью MobileNetV3.
        """
        if not self._is_initialized and not self.initialize_sessions():
            raise RuntimeError("ИИ-движок не инициализирован.")
            
        try:
            # Открываем изображение через PIL для максимальной совместимости путей на Windows
            with Image.open(image_path) as img:
                img = img.convert('RGB')
                img_resized = img.resize((224, 224), Image.Resampling.BILINEAR)
                img_data = np.array(img_resized, dtype=np.float32)
                
            # Нормализация MobileNet (mean/std ImageNet)
            img_data /= 255.0
            mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
            std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
            img_data = (img_data - mean) / std
            
            # Транспонируем в формат NCHW: Batch x Channels x Height x Width
            img_data = np.transpose(img_data, (2, 0, 1))
            img_data = np.expand_dims(img_data, axis=0)
            
            # Имя входного тензора в модели Xenova/mobilenetv3: 'pixel_values' (или 'input' в зависимости от сборки)
            input_name = self.ort_session.get_inputs()[0].name
            ort_inputs = {input_name: img_data}
            
            ort_outs = self.ort_session.run(None, ort_inputs)
            
            # Извлекаем вектор признаков (обычно это последний или предпоследний слой до софтмакса)
            # В модели Xenova выход имеет размерность [1, 960, 1, 1] или [1, 960] после pooling
            embedding = ort_outs[0].flatten()
            
            # Нормализуем вектор (L2 норма), чтобы косинусное сходство сводилось к простому скалярному произведению
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding /= norm
                
            return embedding
        except Exception as e:
            logging.error(f"Ошибка извлечения эмбеддинга для {image_path}: {e}")
            raise e

    def detect_and_extract_faces(self, image_path: str) -> list:
        """
        Ищет лица на картинке, выравнивает их и возвращает список словарей:
        [
           {
              "bbox": [x, y, w, h],
              "descriptor": np.ndarray (128-мерный вектор лица)
           },
           ...
        ]
        """
        if not self._is_initialized and not self.initialize_sessions():
            raise RuntimeError("ИИ-движок не инициализирован.")
            
        results = []
        try:
            # Читаем изображение через PIL, чтобы избежать проблем с юникодом в путях на Windows
            with Image.open(image_path) as img:
                img = img.convert('RGB')
                width, height = img.size
                img_data = np.array(img, dtype=np.uint8)
                
            bgr_img_orig = cv2.cvtColor(img_data, cv2.COLOR_RGB2BGR)
            
            # YuNet лучше всего работает с изображениями среднего размера.
            # Если картинка огромная (например 4K), сеть может не найти лицо.
            # Поэтому мы приводим картинку к оптимальному размеру (max 1200px по большей стороне)
            max_dim = 1200
            scale = 1.0
            
            if width > max_dim or height > max_dim:
                if width > height:
                    scale = max_dim / width
                else:
                    scale = max_dim / height
                    
            if scale != 1.0:
                new_w = int(width * scale)
                new_h = int(height * scale)
                bgr_img = cv2.resize(bgr_img_orig, (new_w, new_h))
            else:
                bgr_img = bgr_img_orig
                new_w, new_h = width, height
                
            # Устанавливаем точный размер в детектор
            self.face_detector.setInputSize((new_w, new_h))
            
            retval, faces = self.face_detector.detect(bgr_img)
            
            if retval and faces is not None and len(faces) > 0:
                for face in faces:
                    # Масштабируем bbox обратно к оригинальному размеру
                    bbox = [int(face[0]/scale), int(face[1]/scale), int(face[2]/scale), int(face[3]/scale)]
                    
                    # Выравниваем и обрезаем лицо (по масштабированному изображению!)
                    aligned_face = self.face_recognizer.alignCrop(bgr_img, face)
                    
                    # Извлекаем 128-мерный вектор лица
                    feat = self.face_recognizer.feature(aligned_face)
                    descriptor = feat.flatten()
                    
                    # Нормализуем дескриптор лица
                    norm = np.linalg.norm(descriptor)
                    if norm > 0:
                        descriptor /= norm
                        
                    results.append({
                        "bbox": bbox,
                        "descriptor": descriptor
                    })
                        
            return results
        except Exception as e:
            logging.error(f"Ошибка обработки лиц для {image_path}: {e}")
            return results
