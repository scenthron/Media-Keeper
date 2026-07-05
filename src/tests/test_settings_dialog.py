import unittest
import os
import sys
from PyQt6.QtWidgets import QApplication

# Добавляем путь к src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Перед импортом Qt-виджетов инициализируем QApplication
app = QApplication.instance() or QApplication([])

from modules.sorter.ui_dialog_settings import PathSettingsDialog, SorterSettingsDialog

class TestSettingsDialogs(unittest.TestCase):
    def test_path_settings_dialog_get_data(self):
        """Проверяет метод get_new_config_data в PathSettingsDialog."""
        test_config = {
            "max_nesting_depth": 5,
            "scan_subfolders": True,
            "filter_mode": "exclude",
            "filter_extensions": "mp3, wav",
            "affix_mode": "postfix",
            "affix_text": "_test",
            "path_unsort": "C:/unsort",
            "path_sort": "C:/sort",
            "path_todel": "C:/todel"
        }
        
        dlg = PathSettingsDialog(test_config)
        
        # Получаем данные
        data = dlg.get_new_config_data()
        
        self.assertEqual(data["max_nesting_depth"], 5)
        self.assertEqual(data["scan_subfolders"], True)
        self.assertEqual(data["filter_mode"], "exclude")
        self.assertEqual(data["filter_extensions"], "mp3, wav")
        self.assertEqual(data["path_sort"], "C:/sort")
        self.assertEqual(data["path_todel"], "C:/todel")

    def test_sorter_settings_dialog_initialization(self):
        """Проверяет инициализацию SorterSettingsDialog."""
        test_config = {
            "sort_type": "size_desc",
            "scan_subfolders": True,
            "filter_extensions": "png, jpg",
            "filter_mode": "include"
        }
        
        dlg = SorterSettingsDialog(test_config)
        
        # Проверяем заполнение полей
        self.assertEqual(dlg.cb_recursive.isChecked(), True)
        self.assertEqual(dlg.e_filter.text(), "png, jpg")
        self.assertEqual(dlg.cb_filter_mode.currentData(), "include")

if __name__ == '__main__':
    unittest.main()
