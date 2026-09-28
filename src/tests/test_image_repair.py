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
        
        # Mode 2: Repair duplicate (default op is index 0: lossless_ext)
        widget.tab_widget.setCurrentIndex(1)
        widget.combo_repair_mode.setCurrentIndex(0)
        widget.combo_op_type.setCurrentIndex(0)
        s = widget.get_settings()
        self.assertEqual(s['mode'], 'repair')
        self.assertEqual(s['repair_save_mode'], 'duplicate')
        self.assertEqual(s['repair_op_type'], 'lossless_ext')
        self.assertEqual(s['repair_scope'], 'damaged_only')
        self.assertTrue(widget.output_zone.isEnabled())
        
        # Format mode (index 1)
        widget.combo_op_type.setCurrentIndex(1)
        s = widget.get_settings()
        self.assertEqual(s['repair_op_type'], 'format')

        # EXIF mode (index 2)
        widget.combo_op_type.setCurrentIndex(2)
        s = widget.get_settings()
        self.assertEqual(s['repair_op_type'], 'exif')
        
        # Mode 3: Repair in-place (index 1)
        widget.combo_repair_mode.setCurrentIndex(1)
        s = widget.get_settings()
        self.assertEqual(s['repair_save_mode'], 'in_place')
        self.assertFalse(widget.output_zone.isEnabled())

    def test_format_file_info_human_readable(self):
        from modules.editor.video.helpers import format_file_info
        # Under 1MB: 205 KB
        info1 = format_file_info("photo.jpg", 205 * 1024, "", "1188x1232")
        self.assertEqual(info1, "photo.jpg (205KB, 1188x1232)")
        
        # 1.5MB with video codec
        info2 = format_file_info("video.mp4", int(1.5 * 1024 * 1024), "H.264", "1920x1080")
        self.assertEqual(info2, "video.mp4 (1.5MB, H.264, 1920x1080)")

    def test_lossless_exif_repair(self):
        test_file = os.path.join(self.test_dir, 'img_inplace.jpg')
        Image.new('RGB', (320, 240), (100, 150, 200)).save(test_file, 'JPEG')
        
        target, ok = repair_single_image(test_file, {'repair_op_type': 'exif', 'repair_save_mode': 'in_place', 'repair_thumb_size': (160, 120)})
        self.assertTrue(ok)
        self.assertEqual(os.path.normpath(target), os.path.normpath(test_file))
        
        exif = piexif.load(target)
        self.assertIsNotNone(exif.get('thumbnail'))

    def test_format_repair_skips_healthy_files(self):
        # Healthy JPG should be skipped in damaged_only mode
        healthy_jpg = os.path.join(self.test_dir, 'healthy.jpg')
        Image.new('RGB', (300, 200), (10, 20, 30)).save(healthy_jpg, 'JPEG')
        
        res, ok = repair_single_image(healthy_jpg, {'repair_op_type': 'format', 'repair_scope': 'damaged_only'})
        self.assertTrue(ok)
        self.assertEqual(res, "SKIPPED_OK")

    def test_repair_fake_jpeg_webp(self):
        # Create a real WebP image with .jpg extension
        test_fake_jpg = os.path.join(self.test_dir, 'fake_photo.jpg')
        Image.new('RGB', (300, 200), (50, 150, 250)).save(test_fake_jpg, 'WEBP')
        
        # Verify it is internally WEBP before repair
        with open(test_fake_jpg, 'rb') as f:
            header = f.read(12)
        self.assertTrue(header.startswith(b'RIFF') and header[8:12] == b'WEBP')
        
        # Run in-place repair
        target, ok = repair_single_image(test_fake_jpg, {'repair_op_type': 'format', 'repair_save_mode': 'in_place', 'repair_scope': 'damaged_only'})
        self.assertTrue(ok)
        self.assertEqual(os.path.normpath(target), os.path.normpath(test_fake_jpg))
        
        # Verify it is now a genuine JPEG
        with open(target, 'rb') as f:
            new_header = f.read(4)
        self.assertTrue(new_header.startswith(b'\xff\xd8'))

    def test_lossless_extension_repair(self):
        # 1. Create a WebP image with fake .jpg extension
        test_fake = os.path.join(self.test_dir, 'lossless_fake.jpg')
        Image.new('RGB', (100, 100), (10, 20, 30)).save(test_fake, 'WEBP')
        
        # Test in-place rename: should rename lossless_fake.jpg -> lossless_fake.webp
        target, ok = repair_single_image(test_fake, {'repair_op_type': 'lossless_ext', 'repair_save_mode': 'in_place', 'repair_scope': 'damaged_only'})
        self.assertTrue(ok)
        self.assertTrue(target.endswith('.webp'))
        self.assertTrue(os.path.exists(target))
        self.assertFalse(os.path.exists(test_fake))
        
        # 2. Test duplicate copy with collision handling
        test_fake2 = os.path.join(self.test_dir, 'lossless_fake.jpg')
        Image.new('RGB', (100, 100), (10, 20, 30)).save(test_fake2, 'WEBP')
        # lossless_fake.webp already exists! So duplicate should create lossless_fake_1.webp
        target2, ok2 = repair_single_image(test_fake2, {'repair_op_type': 'lossless_ext', 'repair_save_mode': 'duplicate', 'repair_scope': 'damaged_only'})
        self.assertTrue(ok2)
        self.assertTrue(target2.endswith('lossless_fake_1.webp'))
        self.assertTrue(os.path.exists(target2))
        self.assertTrue(os.path.exists(test_fake2)) # original kept

    def test_batch_custom_extension_change(self):
        from modules.editor.image.ui_converter import ImageConverterWidget
        widget = ImageConverterWidget()
        
        # Create 2 test files
        f1 = os.path.join(self.test_dir, 'batch_test_1.webp')
        f2 = os.path.join(self.test_dir, 'batch_test_2.png')
        Image.new('RGB', (50, 50), (1, 2, 3)).save(f1, 'WEBP')
        Image.new('RGB', (50, 50), (4, 5, 6)).save(f2, 'PNG')
        
        widget.on_files_dropped([f1, f2])
        self.assertEqual(len(widget.files), 2)
        
        # Set repair mode in_place
        widget.settings_panel.combo_repair_mode.setCurrentIndex(1)
        
        # Apply custom extension 'jpg'
        widget.on_apply_custom_ext_clicked('jpg')
        
        self.assertTrue(widget.files[0]['path'].endswith('.jpg'))
        self.assertTrue(widget.files[1]['path'].endswith('.jpg'))
        self.assertTrue(os.path.exists(widget.files[0]['path']))
        self.assertTrue(os.path.exists(widget.files[1]['path']))

    def test_unblock_file_attributes(self):
        from src.utils_io import check_file_system_block, unblock_file_system_attributes
        
        test_file = os.path.join(self.test_dir, 'unblock_test.jpg')
        with open(test_file, 'w') as f: f.write('dummy')
        
        # Write Zone.Identifier ADS
        zone_stream = test_file + ':Zone.Identifier'
        try:
            with open(zone_stream, 'w') as f: f.write('[ZoneTransfer]\nZoneId=3\n')
            has_zone = os.path.exists(zone_stream)
        except Exception:
            has_zone = False

        if has_zone:
            self.assertTrue(check_file_system_block(test_file))
            unblocked = unblock_file_system_attributes(test_file)
            self.assertTrue(unblocked)
            self.assertFalse(check_file_system_block(test_file))

if __name__ == '__main__':
    unittest.main()


