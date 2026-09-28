import unittest
import os
import sys
import shutil
from PIL import Image
import piexif
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.editor.image.ui_settings import ImageSettingsWidget
from modules.editor.image.worker import repair_single_image

class TestImageRepair(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.test_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../sandbox/test_repair_run'))
        os.makedirs(cls.test_dir, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_settings_tab_and_dropzone_states(self):
        widget = ImageSettingsWidget()
        
        # Mode 1: Convert
        widget.tab_widget.setCurrentIndex(0)
        s = widget.get_settings()
        self.assertEqual(s['mode'], 'convert')
        self.assertTrue(widget.output_zone.isEnabled())
        
        # Mode 2: Repair in-place
        widget.tab_widget.setCurrentIndex(1)
        widget.combo_repair_mode.setCurrentIndex(0)
        s = widget.get_settings()
        self.assertEqual(s['mode'], 'repair')
        self.assertEqual(s['repair_save_mode'], 'in_place')
        self.assertFalse(widget.output_zone.isEnabled())
        
        # Mode 3: Repair duplicate
        widget.combo_repair_mode.setCurrentIndex(1)
        s = widget.get_settings()
        self.assertEqual(s['repair_save_mode'], 'duplicate')
        self.assertTrue(widget.output_zone.isEnabled())

    def test_lossless_repair_in_place(self):
        test_file = os.path.join(self.test_dir, 'img_inplace.jpg')
        Image.new('RGB', (320, 240), (100, 150, 200)).save(test_file, 'JPEG')
        
        target, ok = repair_single_image(test_file, {'repair_save_mode': 'in_place', 'repair_thumb_size': (160, 120)})
        self.assertTrue(ok)
        self.assertEqual(os.path.normpath(target), os.path.normpath(test_file))
        
        exif = piexif.load(target)
        self.assertIsNotNone(exif.get('thumbnail'))

    def test_repair_fake_jpeg_webp(self):
        # Create a real WebP image with .jpg extension
        test_fake_jpg = os.path.join(self.test_dir, 'fake_photo.jpg')
        Image.new('RGB', (300, 200), (50, 150, 250)).save(test_fake_jpg, 'WEBP')
        
        # Verify it is internally WEBP before repair
        with open(test_fake_jpg, 'rb') as f:
            header = f.read(12)
        self.assertTrue(header.startswith(b'RIFF') and header[8:12] == b'WEBP')
        
        # Run in-place repair
        target, ok = repair_single_image(test_fake_jpg, {'repair_save_mode': 'in_place', 'repair_thumb_size': (160, 120)})
        self.assertTrue(ok)
        self.assertEqual(os.path.normpath(target), os.path.normpath(test_fake_jpg))
        
        # Verify it is now a genuine JPEG with EXIF thumbnail
        with open(target, 'rb') as f:
            new_header = f.read(4)
        self.assertTrue(new_header.startswith(b'\xff\xd8'))
        
        exif = piexif.load(target)
        self.assertIsNotNone(exif.get('thumbnail'))

if __name__ == '__main__':
    unittest.main()
