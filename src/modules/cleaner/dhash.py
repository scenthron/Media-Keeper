import os
import math
import logging
from PIL import Image

# Предрассчитанная таблица косинусов для N=32 (pHash)
_cos_tables = {}

def _get_cos_table(N: int):
    if N not in _cos_tables:
        table = []
        for i in range(N):
            row = []
            for k in range(N):
                row.append(math.cos(math.pi * (i + 0.5) * k / N))
            table.append(row)
        _cos_tables[N] = table
    return _cos_tables[N]

def get_image_dhash(image_path: str, hash_size: int = 8) -> tuple[str | None, str, float]:
    """
    Вычисляет градиентный хэш (Difference Hash / dHash) для изображения.
    Возвращает (hash_hex, resolution_str, std_dev)
    """
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            resolution_str = f"{width}x{height}"
            
            img_gray = img.convert('L')
            
            # Вычисляем стандартное отклонение на 32x32 для надежной оценки монотонности
            img_small = img_gray.resize((32, 32), Image.Resampling.BILINEAR)
            small_pixels = list(img_small.getdata())
            mean_val = sum(small_pixels) / len(small_pixels)
            variance = sum((x - mean_val) ** 2 for x in small_pixels) / len(small_pixels)
            std_dev = math.sqrt(variance)
            
            # Изменение размера для dHash: (hash_size + 1) x hash_size
            img_resized = img_gray.resize((hash_size + 1, hash_size), Image.Resampling.BILINEAR)
            pixels = list(img_resized.getdata())
            
            val = 0
            for r in range(hash_size):
                for c in range(hash_size):
                    left = pixels[r * (hash_size + 1) + c]
                    right = pixels[r * (hash_size + 1) + c + 1]
                    val = (val << 1) | (1 if left > right else 0)
                    
            total_pixels = hash_size * hash_size
            hex_len = total_pixels // 4
            return f"{val:0{hex_len}x}", resolution_str, std_dev
    except Exception as e:
        logging.error(f"Error computing dHash for {image_path}: {e}")
        return None, "", 0.0

def get_image_ahash(image_path: str, hash_size: int = 8) -> tuple[str | None, str, float]:
    """
    Вычисляет средний хэш (Average Hash / aHash) для изображения.
    Возвращает (hash_hex, resolution_str, std_dev)
    """
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            resolution_str = f"{width}x{height}"
            
            img_gray = img.convert('L')
            
            # Вычисляем стандартное отклонение на 32x32 для надежной оценки монотонности
            img_small = img_gray.resize((32, 32), Image.Resampling.BILINEAR)
            small_pixels = list(img_small.getdata())
            mean_val = sum(small_pixels) / len(small_pixels)
            variance = sum((x - mean_val) ** 2 for x in small_pixels) / len(small_pixels)
            std_dev = math.sqrt(variance)
            
            img_resized = img_gray.resize((hash_size, hash_size), Image.Resampling.BILINEAR)
            pixels = list(img_resized.getdata())
            
            mean_val_hash = sum(pixels) / len(pixels)
            
            val = 0
            for p in pixels:
                val = (val << 1) | (1 if p > mean_val_hash else 0)
                
            total_pixels = hash_size * hash_size
            hex_len = total_pixels // 4
            return f"{val:0{hex_len}x}", resolution_str, std_dev
    except Exception as e:
        logging.error(f"Error computing aHash for {image_path}: {e}")
        return None, "", 0.0

def get_image_phash(image_path: str, hash_size: int = 8, N: int = 32) -> tuple[str | None, str, float]:
    """
    Вычисляет частотный хэш (Perceptual Hash / pHash) с помощью DCT на чистом Python.
    Возвращает (hash_hex, resolution_str, std_dev)
    """
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            resolution_str = f"{width}x{height}"
            
            img_gray = img.convert('L')
            
            # Сжимаем до N x N и считаем дисперсию
            img_small = img_gray.resize((N, N), Image.Resampling.BILINEAR)
            pixels_flat = list(img_small.getdata())
            
            mean_val = sum(pixels_flat) / len(pixels_flat)
            variance = sum((x - mean_val) ** 2 for x in pixels_flat) / len(pixels_flat)
            std_dev = math.sqrt(variance)
            
            pixels = [pixels_flat[r * N : (r + 1) * N] for r in range(N)]
            cos_table = _get_cos_table(N)
            
            # Вычисляем DCT-коэффициенты для верхнего левого угла hash_size x hash_size
            dct = []
            for k in range(hash_size):
                dct_row = []
                for l in range(hash_size):
                    sum_val = 0.0
                    for i in range(N):
                        for j in range(N):
                            sum_val += pixels[i][j] * cos_table[i][k] * cos_table[j][l]
                    dct_row.append(sum_val)
                dct.append(dct_row)
                
            # Собираем коэффициенты без компонента DCT[0][0]
            dct_flat = []
            for r in range(hash_size):
                for c in range(hash_size):
                    if r == 0 and c == 0:
                        continue
                    dct_flat.append(dct[r][c])
                    
            avg_dct = sum(dct_flat) / len(dct_flat)
            
            val = 0
            for x in dct_flat:
                val = (val << 1) | (1 if x > avg_dct else 0)
                
            bits = hash_size * hash_size - 1
            hex_len = (bits + 3) // 4
            return f"{val:0{hex_len}x}", resolution_str, std_dev
    except Exception as e:
        logging.error(f"Error computing pHash for {image_path}: {e}")
        return None, "", 0.0

def hamming_distance(h1: str, h2: str) -> int:
    """
    Вычисляет расстояние Хэмминга между двумя 16-ричными хэшами.
    """
    try:
        v1 = int(h1, 16)
        v2 = int(h2, 16)
        return bin(v1 ^ v2).count('1')
    except Exception as e:
        logging.error(f"Error computing Hamming distance: {e}")
        return len(h1) * 4 if h1 else 0
