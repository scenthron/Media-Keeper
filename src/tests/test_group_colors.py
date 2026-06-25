import unittest
import os
import sys

# Добавляем путь к src, чтобы импортировать модули напрямую
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.cleaner.ui_model import DuplicateVirtualModel

class TestGroupColors(unittest.TestCase):
    def setUp(self) -> None:
        self.model = DuplicateVirtualModel(None)

    def test_default_group_no_selections(self) -> None:
        """Проверяет группу без выделений (должен быть дефолтный серый цвет)."""
        fake_items = [
            {
                'type': 'group',
                'id': 1,
                'hash': 'hash1',
                'size': 1000,
                'file_count': 2,
                'wasted_size': 1000,
                'extension': '.jpg'
            },
            {
                'type': 'file',
                'id': 2,
                'group_id': 1,
                'path': 'C:/folder/file1.jpg',
                'size': 1000,
                'is_marked': 0
            },
            {
                'type': 'file',
                'id': 3,
                'group_id': 1,
                'path': 'C:/folder/file2.jpg',
                'size': 1000,
                'is_marked': 0
            }
        ]
        
        # Загружаем в модель
        self.model.set_items(fake_items, {
            'C:/folder': {'protected': False, 'reference': False, 'color': '#ff0000'}
        })
        
        marked, effective_unmarked, total = self.model.calculate_group_status(1)
        
        self.assertEqual(marked, 0)             # 0 выделенных
        self.assertEqual(effective_unmarked, 2)  # 2 спасенных
        self.assertEqual(total, 2)               # 2 всего файлов

    def test_group_partially_selected_red(self) -> None:
        """Проверяет группу с частичным выделением (красный статус)."""
        fake_items = [
            {
                'type': 'group',
                'id': 1,
                'hash': 'hash1',
                'size': 1000,
                'file_count': 3,
                'wasted_size': 2000,
                'extension': '.jpg'
            },
            {
                'type': 'file',
                'id': 2,
                'group_id': 1,
                'path': 'C:/folder/file1.jpg',
                'size': 1000,
                'is_marked': 1  # 1 выделенный
            },
            {
                'type': 'file',
                'id': 3,
                'group_id': 1,
                'path': 'C:/folder/file2.jpg',
                'size': 1000,
                'is_marked': 0
            },
            {
                'type': 'file',
                'id': 4,
                'group_id': 1,
                'path': 'C:/folder/file3.jpg',
                'size': 1000,
                'is_marked': 0
            }
        ]
        
        self.model.set_items(fake_items, {
            'C:/folder': {'protected': False, 'reference': False, 'color': '#ff0000'}
        })
        
        marked, effective_unmarked, total = self.model.calculate_group_status(1)
        
        self.assertEqual(marked, 1)             # 1 выделенный
        self.assertEqual(effective_unmarked, 2)  # осталось 2 спасенных (>1, значит будет КРАСНЫЙ цвет!)
        self.assertEqual(total, 3)

    def test_group_fully_selected_green(self) -> None:
        """Проверяет группу, где выделено все кроме одного (зеленый статус)."""
        fake_items = [
            {
                'type': 'group',
                'id': 1,
                'hash': 'hash1',
                'size': 1000,
                'file_count': 3,
                'wasted_size': 2000,
                'extension': '.jpg'
            },
            {
                'type': 'file',
                'id': 2,
                'group_id': 1,
                'path': 'C:/folder/file1.jpg',
                'size': 1000,
                'is_marked': 1
            },
            {
                'type': 'file',
                'id': 3,
                'group_id': 1,
                'path': 'C:/folder/file2.jpg',
                'size': 1000,
                'is_marked': 1
            },
            {
                'type': 'file',
                'id': 4,
                'group_id': 1,
                'path': 'C:/folder/file3.jpg',
                'size': 1000,
                'is_marked': 0  # Только 1 невыделенный файл остался!
            }
        ]
        
        self.model.set_items(fake_items, {
            'C:/folder': {'protected': False, 'reference': False, 'color': '#ff0000'}
        })
        
        marked, effective_unmarked, total = self.model.calculate_group_status(1)
        
        self.assertEqual(marked, 2)
        self.assertEqual(effective_unmarked, 1)  # Ровно 1 спасенный (ЗЕЛЕНЫЙ статус!)
        self.assertEqual(total, 3)

    def test_group_with_multiple_protected_files(self) -> None:
        """Проверяет сжатие защищенных файлов до 1 оригинала (IRON RULE в цветах)."""
        fake_items = [
            {
                'type': 'group',
                'id': 1,
                'hash': 'hash1',
                'size': 1000,
                'file_count': 4,
                'wasted_size': 3000,
                'extension': '.jpg'
            },
            # 2 защищенных файла (например, в эталонных папках)
            {
                'type': 'file',
                'id': 2,
                'group_id': 1,
                'path': 'C:/protected_folder/file1.jpg',
                'size': 1000,
                'is_marked': 0
            },
            {
                'type': 'file',
                'id': 3,
                'group_id': 1,
                'path': 'D:/protected_folder/file2.jpg',
                'size': 1000,
                'is_marked': 0
            },
            # 2 незащищенных файла
            {
                'type': 'file',
                'id': 4,
                'group_id': 1,
                'path': 'E:/inbox/file3.jpg',
                'size': 1000,
                'is_marked': 1  # 1 незащищенный выделен
            },
            {
                'type': 'file',
                'id': 5,
                'group_id': 1,
                'path': 'E:/inbox/file4.jpg',
                'size': 1000,
                'is_marked': 1  # 2-й незащищенный выделен
            }
        ]
        
        # Конфигурируем защищенные пути
        self.model.set_items(fake_items, {
            'C:/protected_folder': {'protected': True, 'reference': False, 'color': '#00ff00'},
            'D:/protected_folder': {'protected': True, 'reference': False, 'color': '#0000ff'},
            'E:/inbox': {'protected': False, 'reference': False, 'color': '#ff0000'}
        })
        
        marked, effective_unmarked, total = self.model.calculate_group_status(1)
        
        # Общие расчеты:
        # Всего файлов: 4
        # Выделено: 2 (file3, file4)
        # Невыделено: 2 (file1, file2)
        # Оба невыделенных файла — защищенные! (unmarked_protected = 2)
        # Эффективное число невыделенных: (2 - 2) + 1 = 1
        
        self.assertEqual(marked, 2)
        self.assertEqual(effective_unmarked, 1)  # Защищенные сжались в 1! Должен быть ЗЕЛЕНЫЙ статус!
        self.assertEqual(total, 4)

if __name__ == '__main__':
    unittest.main()
