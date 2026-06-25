import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.editor.audio.ui_settings import AudioSettingsWidget

class TestAudioConverterSettings(unittest.TestCase):
    def test_max_size_settings_logic(self):
        # QApplication is needed for widget testing
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        widget = AudioSettingsWidget()
        # By default chk_max_size is unchecked, max_size in settings should be None
        settings = widget.get_settings()
        self.assertIsNone(settings.get('max_size'))

        # Check max_size with enabled checkbox
        widget.chk_max_size.setChecked(True)
        widget.inp_max_size.setValue(15)
        settings = widget.get_settings()
        self.assertEqual(settings.get('max_size'), 15)

        # Disable checkbox back and verify it returns None
        widget.chk_max_size.setChecked(False)
        settings = widget.get_settings()
        self.assertIsNone(settings.get('max_size'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
