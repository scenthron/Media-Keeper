import os
import cv2
import numpy as np
import onnxruntime as ort
from safetensors.numpy import load_file
import logging

try:
    import os
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    HAS_TRANSFORMERS = True # We keep the flag True to avoid breaking other logic, but use tokenizers directly
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
                
            from logic_paths import get_models_dir
            clip_dir = os.path.join(get_models_dir(), "clip")
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
            logger.info("Загрузка CLIP Tokenizer...")
            from tokenizers import Tokenizer
            tokenizer_path = os.path.join(text_model_dir, "tokenizer.json")
            if os.path.exists(tokenizer_path):
                self.tokenizer = Tokenizer.from_file(tokenizer_path)
            else:
                logger.error(f"Файл токенизатора не найден: {tokenizer_path}")
                return
            
            logger.info("Загрузка CLIP ONNX сессий...")
            opts = ort.SessionOptions()
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self.vision_sess = ort.InferenceSession(vision_model_path, sess_options=opts, providers=['CPUExecutionProvider'])
            self.text_sess = ort.InferenceSession(text_model_path, sess_options=opts, providers=['CPUExecutionProvider'])

            if os.path.exists(dense_path):
                logger.info("Загрузка CLIP Dense слоя...")
                self.dense_weights = load_file(dense_path)['linear.weight']
            else:
                self.dense_weights = None
            
            # Загрузка словаря
            self.ru_en_dict = {}
            from logic_paths import get_base_path
            dict_path = os.path.join(get_base_path(), "assets", "dict", "ru_en_dict.json")
            if os.path.exists(dict_path):
                import json
                try:
                    with open(dict_path, "r", encoding="utf-8") as f:
                        self.ru_en_dict = json.load(f)
                    logger.info(f"Загружен словарь ru-en: {len(self.ru_en_dict)} слов")
                except Exception as de:
                    logger.warning(f"Ошибка загрузки словаря: {de}")
            
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
    def _translate_ru_to_en(self, text: str) -> str:
        """Переводит русский текст на английский 100% офлайн по 50,000-словарному файлу ru_en_dict.json с нормализацией окончаний."""
        import re
        if hasattr(self, 'ru_en_dict') and self.ru_en_dict:
            def replace_word(match):
                w = match.group(0).lower()
                # 1. Прямое совпадение
                if w in self.ru_en_dict:
                    return self.ru_en_dict[w]
                # 2. Нормализация падежей/множественного числа
                for suffix in ['ами', 'ям', 'ях', 'ам', 'ов', 'ев', 'ей', 'ы', 'и', 'а', 'е', 'у', 'ом', 'ой', 'ем']:
                    if w.endswith(suffix):
                        stem = w[:-len(suffix)]
                        if stem in self.ru_en_dict:
                            return self.ru_en_dict[stem]
                        if (stem + 'а') in self.ru_en_dict:
                            return self.ru_en_dict[stem + 'а']
                        if (stem + 'о') in self.ru_en_dict:
                            return self.ru_en_dict[stem + 'о']
                return match.group(0)

            return re.sub(r'[а-яА-ЯёЁ]+', replace_word, text)

        return text

    def encode_text(self, text: str) -> np.ndarray:
        """
        Превращает текст в нормализованный вектор размерности 512.
        Возвращает None, если модели не загружены или произошла ошибка.
        """
        if not self.is_loaded:
            return None
            
        # Автоматический перевод кириллицы на английский для CLIP
        import re
        if re.search(r'[а-яА-ЯёЁ]', text):
            translated_text = self._translate_ru_to_en(text)
            if translated_text:
                logger.info(f"Запрос '{text}' переведен для CLIP: '{translated_text}'")
                text = translated_text
            
        try:
            # Tokenize using tokenizers library directly
            self.tokenizer.enable_truncation(max_length=77)
            self.tokenizer.enable_padding(length=77)
            encoded = self.tokenizer.encode(text)
            
            input_ids = np.array([encoded.ids], dtype=np.int64)
            attention_mask = np.array([encoded.attention_mask], dtype=np.int64)
            
            # Динамически формируем входы ONNX модели на основе её метаданных
            inputs = {}
            for input_meta in self.text_sess.get_inputs():
                if input_meta.name == "input_ids":
                    inputs["input_ids"] = input_ids
                elif input_meta.name == "attention_mask":
                    inputs["attention_mask"] = attention_mask
                elif input_meta.name == "position_ids":
                    inputs["position_ids"] = np.arange(len(encoded.ids), dtype=np.int64)[None, :]

            text_out = self.text_sess.run(None, inputs)[0]
            
            # Пулинг или прямое извлечение 512D вектора
            if text_out.ndim == 3:
                text_emb = self._mean_pooling(text_out, attention_mask)
            else:
                text_emb = text_out
                
            if self.dense_weights is not None and text_emb.shape[-1] == self.dense_weights.shape[1]:
                text_emb_512 = np.dot(text_emb, self.dense_weights.T)
            else:
                text_emb_512 = text_emb
            
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
