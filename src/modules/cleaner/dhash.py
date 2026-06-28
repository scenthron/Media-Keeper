import os
import logging
from PIL import Image

def get_image_ahash(image_path: str) -> str | None:
    """
    Вычисляет 64-битный перцептивный хэш (aHash) для изображения.
    Устойчив к изменениям разрешения, сжатия и поворотам на 90, 180, 270 градусов
    благодаря бинарной нормализации (выбор минимального значения из всех поворотов).
    """
    try:
        # Открываем изображение и переводим в оттенки серого с ресайзом до 8x8
        with Image.open(image_path) as img:
            img = img.convert('L').resize((8, 8), Image.Resampling.BILINEAR)
            pixels = list(img.getdata())
            
            # Находим среднюю яркость пикселей
            avg = sum(pixels) / 64.0
            
            # Заполняем матрицу 8x8 булевыми значениями (пиксель >= среднего)
            m0 = []
            for r in range(8):
                row = []
                for c in range(8):
                    row.append(pixels[r * 8 + c] >= avg)
                m0.append(row)
                
            # Функция поворота матрицы на 90 градусов по часовой стрелке
            def rotate(m):
                return [[m[7 - c][r] for c in range(8)] for r in range(8)]
                
            m90 = rotate(m0)
            m180 = rotate(m90)
            m270 = rotate(m180)
            
            # Преобразуем каждую из 4-х матриц в 64-битное целое число
            def to_int(m):
                val = 0
                for r in range(8):
                    for c in range(8):
                        val = (val << 1) | m[r][c]
                return val
                
            v0 = to_int(m0)
            v90 = to_int(m90)
            v180 = to_int(m180)
            v270 = to_int(m270)
            
            # Выбираем минимальное число как нормализованный хэш
            min_val = min(v0, v90, v180, v270)
            return f"{min_val:016x}"
    except Exception as e:
        logging.error(f"Error computing aHash for {image_path}: {e}")
        return None

def hamming_distance(h1: str, h2: str) -> int:
    """
    Вычисляет расстояние Хэмминга между двумя 16-ричными хэшами.
    Возвращает число различающихся битов (от 0 до 64).
    """
    try:
        v1 = int(h1, 16)
        v2 = int(h2, 16)
        return bin(v1 ^ v2).count('1')
    except Exception as e:
        logging.error(f"Error computing Hamming distance: {e}")
        return 64
