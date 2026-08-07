import os
import cv2
import numpy as np
import logging
import pickle
from logic_paths import get_app_data_dir
from utils_io import safe_cv2_imread, ensure_long_path

class OrbEngine:
    def match_template(self, frag_bgr, target_bgr, tolerance, optimize_bw=False):
        # Пиксельный поиск через cv2.matchTemplate
        try:
            if frag_bgr is None or target_bgr is None:
                return False, None, 0
                
            frag_h, frag_w = frag_bgr.shape[:2]
            target_h, target_w = target_bgr.shape[:2]
            
            if frag_h > target_h or frag_w > target_w:
                return False, None, 0
                
            import cv2
            if optimize_bw:
                if len(frag_bgr.shape) == 3:
                    frag_img = cv2.cvtColor(frag_bgr, cv2.COLOR_BGR2GRAY)
                else:
                    frag_img = frag_bgr
                if len(target_bgr.shape) == 3:
                    target_img = cv2.cvtColor(target_bgr, cv2.COLOR_BGR2GRAY)
                else:
                    target_img = target_bgr
            else:
                frag_img = frag_bgr
                target_img = target_bgr
                
            res = cv2.matchTemplate(target_img, frag_img, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            
            # tolerance в UI от 0 до 100. 100 = 0.99, 0 = 0.70
            threshold = 0.7 + (tolerance / 100.0) * 0.29
            
            if max_val >= threshold:
                x, y = max_loc
                import numpy as np
                # Возвращаем рамку как полигон
                bbox = np.int32([[[x, y]], [[x, y + frag_h]], [[x + frag_w, y + frag_h]], [[x + frag_w, y]]])
                return True, bbox, int(max_val * 100)
            return False, None, 0
        except Exception as e:
            import logging
            logging.error(f"[TemplateMatch] Error: {e}")
            return False, None, 0

    """Движок для поиска фрагментов на основе ORB Feature Matching."""
    
    def __init__(self, max_features=0):
        # Инициализация SIFT (работает гораздо точнее для вырезанных фрагментов)
        self.orb = cv2.SIFT_create(nfeatures=10000)
        
        # Настройка матчера (для SIFT используется NORM_L2)
        self.matcher = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
        
    def _resize_if_needed(self, img, max_dim=1920):
        """Уменьшает изображение, если оно слишком большое, для скорости."""
        h, w = img.shape[:2]
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            new_w, new_h = int(w * scale), int(h * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            return img, scale
        return img, 1.0

    def extract_features(self, image_path, max_dim=1920):
        """Извлекает ключевые точки и дескрипторы из изображения."""
        img = safe_cv2_imread(image_path)
        if img is None:
            return None, None, None, 1.0
            
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray, scale = self._resize_if_needed(gray, max_dim)
        
        # Извлекаем ключевые точки и дескрипторы
        keypoints, descriptors = self.orb.detectAndCompute(gray, None)
        return keypoints, descriptors, img.shape[:2], scale

    def extract_features_from_img(self, img_bgr, max_dim=1920):
        """Извлекает признаки напрямую из BGR numpy массива (используется для вырезанного фрагмента)."""
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        gray, scale = self._resize_if_needed(gray, max_dim)
        keypoints, descriptors = self.orb.detectAndCompute(gray, None)
        return keypoints, descriptors, img_bgr.shape[:2], scale

    def match(self, frag_kp, frag_desc, frag_shape, target_kp, target_desc, target_scale=1.0, 
              ratio_thresh=0.75, min_match_count=10):
        """
        Ищет фрагмент в целевом изображении.
        Возвращает: (успех (bool), рамка (tuple of points) или None, кол-во хороших совпадений)
        """
        if frag_desc is None or target_desc is None or len(frag_desc) < 2 or len(target_desc) < 2:
            return False, None, 0
            
        try:
            # Ищем 2 лучших совпадения для каждой точки
            matches = self.matcher.knnMatch(frag_desc, target_desc, k=2)
            
            # Применяем Lowe's ratio test
            good_matches = []
            for m_n in matches:
                if len(m_n) != 2:
                    continue
                m, n = m_n
                if m.distance < ratio_thresh * n.distance:
                    good_matches.append(m)
                    
            if len(good_matches) >= min_match_count:
                # Находим координаты ключевых точек
                src_pts = np.float32([frag_kp[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
                dst_pts = np.float32([target_kp[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
                
                # Ищем гомографию (перспективное преобразование)
                M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
                
                if M is not None:
                    h, w = frag_shape[:2]
                    # Точки углов фрагмента
                    pts = np.float32([[0, 0], [0, h - 1], [w - 1, h - 1], [w - 1, 0]]).reshape(-1, 1, 2)
                    
                    # Трансформируем углы фрагмента на целевое изображение
                    dst = cv2.perspectiveTransform(pts, M)
                    
                    # Возвращаем рамку с учетом скейла целевого изображения
                    # target_scale - это во сколько раз мы уменьшили картинку при извлечении.
                    # Чтобы получить координаты на оригинале, делим на target_scale
                    if target_scale != 1.0 and target_scale > 0:
                        dst = dst / target_scale
                        
                    # Преобразуем в целые координаты
                    bounding_box = np.int32(dst)
                    return True, bounding_box, len(good_matches)
                    
            return False, None, len(good_matches)
        except Exception as e:
            logging.error(f"[ORB] Matcher error: {e}")
            return False, None, 0

class OrbCacheManager:
    """Менеджер для сохранения и загрузки дескрипторов ORB на диск."""
    
    def __init__(self):
        self.cache_dir = os.path.join(get_app_data_dir(), "cache", "orb")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.memory_cache = {} # Кэш в оперативке для супер-быстрого поиска
        
    def _get_cache_path(self, filepath):
        """Генерирует путь к файлу кэша на основе имени и размера исходного файла."""
        try:
            stat = os.stat(ensure_long_path(filepath))
            file_id = f"{os.path.basename(filepath)}_{stat.st_size}_{stat.st_mtime}"
            import hashlib
            hash_str = hashlib.md5(file_id.encode('utf-8')).hexdigest()
            return os.path.join(self.cache_dir, f"{hash_str}.pkl")
        except:
            return None

    def _serialize_keypoints(self, keypoints):
        """Конвертирует cv2.KeyPoint в сериализуемый формат (кортежи)."""
        if not keypoints: return []
        return [(kp.pt, kp.size, kp.angle, kp.response, kp.octave, kp.class_id) for kp in keypoints]
        
    def _deserialize_keypoints(self, kp_tuples):
        """Восстанавливает cv2.KeyPoint из кортежей."""
        if not kp_tuples: return []
        return [cv2.KeyPoint(x=pt[0], y=pt[1], size=size, angle=angle, response=response, octave=octave, class_id=class_id) 
                for (pt, size, angle, response, octave, class_id) in kp_tuples]

    def load_cache(self, filepath):
        """Загружает кэш для файла, если он есть."""
        if filepath in self.memory_cache:
            return self.memory_cache[filepath]
            
        cpath = self._get_cache_path(filepath)
        if cpath and os.path.exists(cpath):
            try:
                with open(cpath, 'rb') as f:
                    data = pickle.load(f)
                    kps = self._deserialize_keypoints(data['kp'])
                    desc = data['desc']
                    scale = data['scale']
                    self.memory_cache[filepath] = (kps, desc, scale)
                    return kps, desc, scale
            except Exception as e:
                logging.debug(f"[ORB Cache] Failed to load cache for {filepath}: {e}")
        return None, None, 1.0

    def save_cache(self, filepath, keypoints, descriptors, scale):
        """Сохраняет кэш на диск и в память."""
        if descriptors is None:
            return
            
        self.memory_cache[filepath] = (keypoints, descriptors, scale)
        cpath = self._get_cache_path(filepath)
        if cpath:
            try:
                data = {
                    'kp': self._serialize_keypoints(keypoints),
                    'desc': descriptors,
                    'scale': scale
                }
                with open(cpath, 'wb') as f:
                    pickle.dump(data, f)
            except Exception as e:
                logging.error(f"[ORB Cache] Failed to save cache for {filepath}: {e}")
                
    def clear_memory(self):
        """Очищает оперативную память."""
        self.memory_cache.clear()
        
    def clear_disk_cache(self):
        """Удаляет все файлы кэша ORB с диска."""
        self.clear_memory()
        try:
            for f in os.listdir(self.cache_dir):
                os.remove(os.path.join(self.cache_dir, f))
            logging.info("[ORB Cache] Disk cache cleared.")
        except Exception as e:
            logging.error(f"[ORB Cache] Clear disk cache failed: {e}")
