import unittest
import os
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPen, QBrush

# Добавляем путь к src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Перед импортом Qt-виджетов инициализируем QApplication
app = QApplication.instance() or QApplication([])

from modules.analyzer.ui_chart import AnalyzerPieChart, TreeMapSliceItem, SunburstSliceItem

class TestAnalyzerInteractive(unittest.TestCase):
    def setUp(self):
        self.chart = AnalyzerPieChart()
        # Загружаем простейшее тестовое дерево файлов
        self.test_tree = {
            'name': 'root',
            'path': 'C:/test_root',
            'type': 'dir',
            'size': 3000,
            'children': [
                {
                    'name': 'file1.mp4',
                    'path': 'C:/test_root/file1.mp4',
                    'type': 'file',
                    'size': 1000
                },
                {
                    'name': 'file2.jpg',
                    'path': 'C:/test_root/file2.jpg',
                    'type': 'file',
                    'size': 2000
                }
            ]
        }
        self.chart.load_tree(self.test_tree, depth_limit=5)

    def test_highlight_by_ext(self):
        """Проверяет метод highlight_by_ext (изменение яркости кисти без изменения пера)."""
        # Сначала подсвечиваем mp4
        self.chart.highlight_by_ext("mp4")
        
        found_mp4 = False
        found_jpg = False
        for item in self.chart.scene.items():
            if isinstance(item, TreeMapSliceItem):
                ext = os.path.splitext(item.data.get('name', ''))[1].lower()
                if 'mp4' in ext:
                    found_mp4 = True
                    # Кисть должна быть ярче на 50% (lighter(150))
                    expected_brush_color = item.base_color.lighter(150)
                    self.assertEqual(item.brush().color().name(), expected_brush_color.name())
                    # Перо (рамка) должно быть стандартным
                    pen = item.pen()
                    self.assertEqual(pen.color().name(), "#1a1a1a")
                elif 'jpg' in ext:
                    found_jpg = True
                    # JPG не должен иметь повышенной яркости
                    self.assertEqual(item.brush().color().name(), item.base_color.name())
        
        self.assertTrue(found_mp4)
        self.assertTrue(found_jpg)

    def test_highlight_file(self):
        """Проверяет highlight_file_on_chart (выбранный - белый сплошной 3px, заливка lighter(150))."""
        # Выделяем file1.mp4
        self.chart.highlight_file_on_chart("C:/test_root/file1.mp4")
        
        found_target = False
        found_other = False
        for item in self.chart.scene.items():
            if isinstance(item, TreeMapSliceItem):
                path = item.data.get('path', '')
                if path == "C:/test_root/file1.mp4":
                    found_target = True
                    self.assertTrue(item.is_selected)
                    pen = item.pen()
                    # Выделенный элемент имеет белую рамку 3px
                    self.assertEqual(pen.color().name(), "#ffffff")
                    self.assertEqual(pen.width(), 3)
                    self.assertEqual(pen.style(), Qt.PenStyle.SolidLine)
                    # Кисть должна быть lighter(150)
                    self.assertEqual(item.brush().color().name(), item.base_color.lighter(150).name())
                elif path == "C:/test_root/file2.jpg":
                    found_other = True
                    # Другой файл не должен быть подсвечен
                    self.assertFalse(item.is_selected)
                    self.assertEqual(item.brush().color().name(), item.base_color.name())
                    
        self.assertTrue(found_target)
        self.assertTrue(found_other)

    def test_clear_highlight(self):
        """Проверяет сброс подсветки всех элементов."""
        # Подсвечиваем
        self.chart.highlight_by_ext("mp4")
        self.chart.clear_highlight()
        
        for item in self.chart.scene.items():
            if isinstance(item, TreeMapSliceItem):
                # Кисть должна вернуться к базовой
                self.assertEqual(item.brush().color().name(), item.base_color.name())

if __name__ == '__main__':
    unittest.main()
