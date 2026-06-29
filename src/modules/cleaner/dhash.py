import os
import logging
from PIL import Image

def get_image_ahash(image_path: str, hash_size: int = 16) -> tuple[str | None, str]:
    """
    Вычисляет перцептивный хэш (dHash) для изображения с настраиваемым разрешением.
    Использует dHash (Difference Hash), который лучше отлавливает границы и структуру,
    что исключает ложные срабатывания на картинках с одинаковым градиентом яркости.
    """
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            resolution_str = f"{width}x{height}"
            
            # Для dHash размер должен быть (hash_size + 1) x hash_size
            img = img.convert('L').resize((hash_size + 1, hash_size), Image.Resampling.BILINEAR)
            pixels = list(img.getdata())
            
            # Формируем базовую матрицу разниц
            m0 = []
            for r in range(hash_size):
                row = []
                for c in range(hash_size):
                    # Сравниваем текущий пиксель с правым соседом
                    left = pixels[r * (hash_size + 1) + c]
                    right = pixels[r * (hash_size + 1) + c + 1]
                    row.append(left > right)
                m0.append(row)
                
            # Преобразуем базовую матрицу разниц m0 в целое число (классический dHash без ложной инвариантности к поворотам)
            val = 0
            for r in range(hash_size):
                for c in range(hash_size):
                    val = (val << 1) | m0[r][c]

            total_pixels = hash_size * hash_size
            hex_len = total_pixels // 4
            return f"{val:0{hex_len}x}", resolution_str
    except Exception as e:
        logging.error(f"Error computing aHash for {image_path}: {e}")
        return None, ""

def hamming_distance(h1: str, h2: str) -> int:
    """
    Вычисляет расстояние Хэмминга между двумя 16-ричными хэшами произвольной длины.
    Возвращает число различающихся битов.
    """
    try:
        v1 = int(h1, 16)
        v2 = int(h2, 16)
        return bin(v1 ^ v2).count('1')
    except Exception as e:
        logging.error(f"Error computing Hamming distance: {e}")
        return len(h1) * 4 if h1 else 0

