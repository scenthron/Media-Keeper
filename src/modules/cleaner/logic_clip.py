import os
import cv2
import numpy as np
import onnxruntime as ort
from safetensors.numpy import load_file
import logging

try:
    from transformers import AutoTokenizer
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False

logger = logging.getLogger(__name__)

class CLIPSearcher:
    """
    Класс для работы с мультиязычным CLIP (Text + Vision).
    Использует onnxruntime для инференса.
    """
    def __init__(self):
        self.vision_sess = None
        self.text_sess = None
        self.tokenizer = None
        self.dense_weights = None
        
        self.is_loaded = False
        self.load_models()
        
    def load_models(self):
        try:
            if not HAS_TRANSFORMERS:
                logger.error("Для работы CLIP требуется пакет transformers. Установите: pip install transformers tokenizers")
                return
                
            app_data = os.path.join(os.path.expanduser("~"), ".mediakeeper")
            clip_dir = os.path.join(app_data, "models", "clip")
            vision_model_path = os.path.join(clip_dir, "vision", "model.onnx")
            text_model_dir = os.path.join(clip_dir, "text_multi")
            text_model_path = os.path.join(text_model_dir, "model.onnx")
            dense_path = os.path.join(text_model_dir, "dense.safetensors")
            
            if not os.path.exists(vision_model_path):
                logger.error(f"Модель CLIP Vision не найдена: {vision_model_path}")
                return
            if not os.path.exists(text_model_path):
                logger.error(f"Модель CLIP Text не найдена: {text_model_path}")
                return
            if not os.path.exists(dense_path):
                logger.error(f"Веса CLIP Dense не найдены: {dense_path}")
                return
                
            logger.info("Загрузка CLIP Tokenizer...")
            self.tokenizer = AutoTokenizer.from_pretrained(text_model_dir)
            
            logger.info("Загрузка CLIP ONNX сессий...")
            opts = ort.SessionOptions()
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self.vision_sess = ort.InferenceSession(vision_model_path, sess_options=opts, providers=['CPUExecutionProvider'])
            self.text_sess = ort.InferenceSession(text_model_path, sess_options=opts, providers=['CPUExecutionProvider'])
            
            logger.info("Загрузка CLIP Dense слоя...")
            self.dense_weights = load_file(dense_path)['linear.weight']
            
            self.is_loaded = True
            logger.info("CLIP модели успешно загружены!")
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке CLIP: {e}", exc_info=True)
            self.is_loaded = False

    def _mean_pooling(self, model_output, attention_mask):
        input_mask_expanded = np.expand_dims(attention_mask, -1)
        input_mask_expanded = np.broadcast_to(input_mask_expanded, model_output.shape)
        sum_embeddings = np.sum(model_output * input_mask_expanded, axis=1)
        sum_mask = np.clip(np.sum(input_mask_expanded, axis=1), a_min=1e-9, a_max=None)
        return sum_embeddings / sum_mask

    def encode_text(self, text: str) -> np.ndarray:
        """
        Превращает текст в нормализованный вектор размерности 512.
        Возвращает None, если модели не загружены или произошла ошибка.
        """
        if not self.is_loaded:
            return None
            
        try:
            inputs = self.tokenizer([text], padding=True, truncation=True, return_tensors="np")
            input_ids = inputs["input_ids"].astype(np.int64)
            attention_mask = inputs["attention_mask"].astype(np.int64)
            
            text_out = self.text_sess.run(None, {
                "input_ids": input_ids,
                "attention_mask": attention_mask
            })[0]
            
            # Пулинг (mean pooling)
            text_emb_768 = self._mean_pooling(text_out, attention_mask)
            
            # Проекция из 768 в 512
            text_emb_512 = np.dot(text_emb_768, self.dense_weights.T)
            
            # L2 нормализация
            norm = np.linalg.norm(text_emb_512, axis=-1, keepdims=True)
            text_emb_norm = text_emb_512 / np.clip(norm, 1e-9, None)
            
            return text_emb_norm[0] # Возвращаем 1D вектор
            
        except Exception as e:
            logger.error(f"Ошибка при кодировании текста '{text}': {e}", exc_info=True)
            return None

    def encode_image(self, img_path: str) -> np.ndarray:
        """
        Превращает изображение по пути в нормализованный вектор размерности 512.
        Возвращает None, если модели не загружены или файл не читается.
        """
        if not self.is_loaded:
            return None
            
        try:
            # Чтение через utils для поддержки кириллицы можно добавить позже,
            # но пока используем np.fromfile как в logic_scrfd, чтобы избежать проблем с путями
            stream = open(img_path, "rb")
            bytes_array = bytearray(stream.read())
            numpyarray = np.asarray(bytes_array, dtype=np.uint8)
            img = cv2.imdecode(numpyarray, cv2.IMREAD_COLOR)
            stream.close()
            
            if img is None:
                return None
                
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            
            # Препроцессинг CLIP (Resize, CenterCrop 224, Normalize)
            h, w = img.shape[:2]
            scale = max(224.0 / h, 224.0 / w)
            new_h, new_w = int(np.ceil(h * scale)), int(np.ceil(w * scale))
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
            
            start_y = (new_h - 224) // 2
            start_x = (new_w - 224) // 2
            img = img[start_y:start_y+224, start_x:start_x+224]
            
            img = img.astype(np.float32) / 255.0
            
            mean = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
            std = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
            img = (img - mean) / std
            
            img = np.transpose(img, (2, 0, 1))
            img_input = np.expand_dims(img, axis=0).astype(np.float32)
            
            vision_out = self.vision_sess.run(None, {"pixel_values": img_input})[0]
            
            # L2 нормализация
            norm = np.linalg.norm(vision_out, axis=-1, keepdims=True)
            img_emb_norm = vision_out / np.clip(norm, 1e-9, None)
            
            return img_emb_norm[0] # Возвращаем 1D вектор
            
        except Exception as e:
            logger.error(f"Ошибка при кодировании изображения '{img_path}': {e}")
            return None

    @staticmethod
    def compute_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Вычисляет косинусное сходство между двумя нормализованными векторами."""
        if emb1 is None or emb2 is None:
            return 0.0
        return float(np.dot(emb1, emb2))
