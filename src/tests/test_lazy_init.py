import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import QCoreApplication, QThreadPool

app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

from main import MediaKeeperShell
from modules.sorter.ui_main import SorterModule


class TestLazyTabInitialization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shell = MediaKeeperShell()

    @classmethod
    def tearDownClass(cls):
        cls.shell.close()
        QThreadPool.globalInstance().waitForDone(3000)
        QCoreApplication.processEvents()

    def test_01_initial_state_tabs_not_loaded(self):
        """Проверяем, что при создании окна тяжелые вкладки не инициализированы."""
        self.assertIsNotNone(self.shell.sorter_tab)
        self.assertIsInstance(self.shell.sorter_tab, SorterModule)
        
        # Проверяем приватные поля
        self.assertIsNone(self.shell._editor_tab)
        self.assertIsNone(self.shell._cleaner_tab)
        self.assertIsNone(self.shell._analyzer_tab)

        # Проверяем виджеты в stack: на индексах 1, 2, 3 должны быть простые заглушки
        self.assertEqual(type(self.shell.stack.widget(1)), QWidget)
        self.assertEqual(type(self.shell.stack.widget(2)), QWidget)
        self.assertEqual(type(self.shell.stack.widget(3)), QWidget)

    def test_02_property_access_loads_cleaner(self):
        """Проверяем, что обращение к shell.cleaner_tab лениво загружает модуль Cleaner."""
        cleaner = self.shell.cleaner_tab
        self.assertIsNotNone(cleaner)
        self.assertIsNotNone(self.shell._cleaner_tab)
        self.assertIs(cleaner, self.shell._cleaner_tab)
        
        # Виджет в stack(2) должен быть заменен на cleaner
        self.assertIs(self.shell.stack.widget(2), cleaner)

        # Повторное обращение возвращает тот же экземпляр
        cleaner2 = self.shell.cleaner_tab
        self.assertIs(cleaner, cleaner2)

    def test_03_property_access_loads_editor(self):
        """Проверяем, что обращение к shell.editor_tab лениво загружает модуль Editor."""
        editor = self.shell.editor_tab
        self.assertIsNotNone(editor)
        self.assertIsNotNone(self.shell._editor_tab)
        self.assertIs(editor, self.shell._editor_tab)
        self.assertIs(self.shell.stack.widget(1), editor)

    def test_04_property_access_loads_analyzer(self):
        """Проверяем, что обращение к shell.analyzer_tab лениво загружает модуль Analyzer."""
        analyzer = self.shell.analyzer_tab
        self.assertIsNotNone(analyzer)
        self.assertIsNotNone(self.shell._analyzer_tab)
        self.assertIs(analyzer, self.shell._analyzer_tab)
        self.assertIs(self.shell.stack.widget(3), analyzer)

    def test_05_switch_tab_loads_and_switches(self):
        """Проверяем переключение вкладок через switch_tab."""
        self.shell.switch_tab(0)
        self.assertEqual(self.shell.stack.currentIndex(), 0)

        self.shell.switch_tab(1)
        self.assertEqual(self.shell.stack.currentIndex(), 1)
        self.assertIs(self.shell.stack.currentWidget(), self.shell.editor_tab)

        self.shell.switch_tab(2)
        self.assertEqual(self.shell.stack.currentIndex(), 2)
        self.assertIs(self.shell.stack.currentWidget(), self.shell.cleaner_tab)

        self.shell.switch_tab(3)
        self.assertEqual(self.shell.stack.currentIndex(), 3)
        self.assertIs(self.shell.stack.currentWidget(), self.shell.analyzer_tab)

        self.shell.switch_tab(0)
        self.assertEqual(self.shell.stack.currentIndex(), 0)

    def test_06_lifecycle_methods_safe_when_loaded(self):
        """Проверяем, что update_ui_text и on_ffmpeg_downloaded работают без ошибок."""
        self.shell.update_ui_text()
        self.shell.on_ffmpeg_downloaded()
        QCoreApplication.processEvents()


if __name__ == '__main__':
    unittest.main()
