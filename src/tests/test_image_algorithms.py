import unittest
import os
import tempfile
from PIL import Image

from modules.cleaner.dhash import get_image_dhash, get_image_phash, get_image_ahash

class TestImageAlgorithms(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        
        # 1. Создаем монотонное серое изображение (низкая дисперсия)
        self.mono_path = os.path.join(self.temp_dir.name, "mono.jpg")
        mono_img = Image.new("RGB", (100, 100), (128, 128, 128))
        mono_img.save(self.mono_path)
        
        # 2. Создаем контрастное изображение (высокая дисперсия)
        self.contrast_path = os.path.join(self.temp_dir.name, "contrast.jpg")
        contrast_img = Image.new("RGB", (100, 100), (255, 255, 255))
        # Рисуем черную сетку для контраста
        pixels = contrast_img.load()
        for i in range(100):
            for j in range(100):
                if (i // 10) % 2 == (j // 10) % 2:
                    pixels[i, j] = (0, 0, 0)
        contrast_img.save(self.contrast_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_dhash_variance_and_computation(self):
        # Тестируем dHash
        hash_mono, res_mono, dev_mono = get_image_dhash(self.mono_path, hash_size=8)
        hash_contr, res_contr, dev_contr = get_image_dhash(self.contrast_path, hash_size=8)
        
        self.assertIsNotNone(hash_mono)
        self.assertIsNotNone(hash_contr)
        self.assertEqual(res_mono, "100x100")
        
        # Монотонная картинка должна иметь дисперсию близкую к 0
        self.assertLess(dev_mono, 2.0)
        # Контрастная картинка должна иметь высокую дисперсию
        self.assertGreater(dev_contr, 50.0)

    def test_ahash_variance_and_computation(self):
        # Тестируем aHash
        hash_mono, res_mono, dev_mono = get_image_ahash(self.mono_path, hash_size=8)
        hash_contr, res_contr, dev_contr = get_image_ahash(self.contrast_path, hash_size=8)
        
        self.assertIsNotNone(hash_mono)
        self.assertIsNotNone(hash_contr)
        self.assertLess(dev_mono, 2.0)
        self.assertGreater(dev_contr, 50.0)

    def test_phash_variance_and_computation(self):
        # Тестируем pHash
        hash_mono, res_mono, dev_mono = get_image_phash(self.mono_path, hash_size=8)
        hash_contr, res_contr, dev_contr = get_image_phash(self.contrast_path, hash_size=8)
        
        self.assertIsNotNone(hash_mono)
        self.assertIsNotNone(hash_contr)
        self.assertLess(dev_mono, 2.0)
        self.assertGreater(dev_contr, 50.0)
        
        # Проверяем, что хэши для монотонной и контрастной картинок различаются
        self.assertNotEqual(hash_mono, hash_contr)

if __name__ == "__main__":
    unittest.main()
