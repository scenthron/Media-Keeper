import unittest
import os
import sys
import tempfile
import shutil
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRegularExpression
from PyQt6.QtGui import QRegularExpressionValidator

# Добавляем путь к src, чтобы импортировать модули напрямую
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Инициализируем QApplication для всего тестового сеанса,
# предотвращая краш при инициализации виджетов QDialog в pytest
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

from modules.sorter.logic_automation import TemplateEngine

class DummySorter:
    """Заглушка для SorterModule для тестирования on_affix_click."""
    def __init__(self, unsort_dir: str) -> None:
        self.UNSORT_DIR = unsort_dir
        self.files_queue = []
        self._raw_dir_files = []
        self.session_counters = {}
        self.current_file_path = None
        self.lbl_filename = DummyLabel()
        self.viewer = DummyViewer()
        self.affix_window = DummyAffixWindow()
        self.config = {"affix_separator": "_"}
        self.history = []
        self._ignore_watcher = False
        
        # Свойства медиа плеера
        self.media_player = DummyMediaPlayer()

    def show_current_file(self) -> None:
        pass

    def on_selection_changed(self) -> None:
        pass

    # Копируем метод из logic_files.py для тестирования на заглушке
    from modules.sorter.logic_files import FileOpsMixin
    on_affix_click = FileOpsMixin.on_affix_click

class DummyLabel:
    def __init__(self) -> None:
        self.text = ""

    def setText(self, val: str) -> None:
        self.text = val

class DummyViewer:
    def __init__(self) -> None:
        self.selected_files = []
        self.stack = DummyStack()

    def get_selected_files(self) -> list[str]:
        return self.selected_files

    def update_file_path_in_view(self, old_path: str, new_path: str) -> None:
        pass

    def remove_files_from_view(self, paths: list[str]) -> None:
        pass

class DummyStack:
    def __init__(self) -> None:
        self._current_index = 1 # Grid/List mode by default

    def currentIndex(self) -> int:
        return self._current_index

class DummyAffixWindow:
    def __init__(self) -> None:
        self.mode = "prefix"

    def get_mode(self) -> str:
        return self.mode

class DummyMediaPlayer:
    def stop(self) -> None:
        pass

    def setSource(self, src: object) -> None:
        pass

class TestBatchRename(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp()
        self.sorter = DummySorter(self.test_dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir)

    def test_validator_regex(self) -> None:
        """Проверяет, что регулярное выражение корректно запрещает недопустимые символы Windows."""
        regex = QRegularExpression(r"^[^\\/:*?\"<>|]*$")
        validator = QRegularExpressionValidator(regex)
        
        # Валидные символы
        self.assertEqual(validator.validate("test_tag", 0)[0], QRegularExpressionValidator.State.Acceptable)
        self.assertEqual(validator.validate("Work-Project", 0)[0], QRegularExpressionValidator.State.Acceptable)
        self.assertEqual(validator.validate("123", 0)[0], QRegularExpressionValidator.State.Acceptable)
        self.assertEqual(validator.validate("", 0)[0], QRegularExpressionValidator.State.Acceptable)
        
        # Инвалидные символы
        self.assertEqual(validator.validate("test/tag", 0)[0], QRegularExpressionValidator.State.Invalid)
        self.assertEqual(validator.validate("tag\\tag", 0)[0], QRegularExpressionValidator.State.Invalid)
        self.assertEqual(validator.validate("tag:tag", 0)[0], QRegularExpressionValidator.State.Invalid)
        self.assertEqual(validator.validate("tag*tag", 0)[0], QRegularExpressionValidator.State.Invalid)
        self.assertEqual(validator.validate("tag?tag", 0)[0], QRegularExpressionValidator.State.Invalid)
        self.assertEqual(validator.validate("tag\"tag", 0)[0], QRegularExpressionValidator.State.Invalid)
        self.assertEqual(validator.validate("tag<tag", 0)[0], QRegularExpressionValidator.State.Invalid)
        self.assertEqual(validator.validate("tag>tag", 0)[0], QRegularExpressionValidator.State.Invalid)
        self.assertEqual(validator.validate("tag|tag", 0)[0], QRegularExpressionValidator.State.Invalid)

    def test_batch_rename_success(self) -> None:
        """Проверяет успешное пакетное переименование нескольких файлов без конфликтов."""
        # Создаем файлы
        f1 = os.path.join(self.test_dir, "file1.txt")
        f2 = os.path.join(self.test_dir, "file2.txt")
        with open(f1, "w") as f: f.write("1")
        with open(f2, "w") as f: f.write("2")
        
        self.sorter.viewer.selected_files = [f1, f2]
        self.sorter.files_queue = ["file1.txt", "file2.txt"]
        self.sorter._raw_dir_files = [
            {"rel_path": "file1.txt"},
            {"rel_path": "file2.txt"}
        ]
        
        # Применяем аффикс
        self.sorter.on_affix_click("text", "tag")
        
        # Проверяем переименование на диске
        expected_f1 = os.path.join(self.test_dir, "tag_file1.txt")
        expected_f2 = os.path.join(self.test_dir, "tag_file2.txt")
        self.assertTrue(os.path.exists(expected_f1))
        self.assertTrue(os.path.exists(expected_f2))
        self.assertFalse(os.path.exists(f1))
        self.assertFalse(os.path.exists(f2))
        
        # Проверяем обновление RAM-кэша
        self.assertIn("tag_file1.txt", self.sorter.files_queue)
        self.assertIn("tag_file2.txt", self.sorter.files_queue)
        self.assertEqual(self.sorter._raw_dir_files[0]["rel_path"], "tag_file1.txt")
        self.assertEqual(self.sorter._raw_dir_files[1]["rel_path"], "tag_file2.txt")

    def test_batch_rename_conflict_with_existing_file(self) -> None:
        """Проверяет отмену операции при конфликте с уже существующим на диске файлом."""
        # Создаем файлы
        f1 = os.path.join(self.test_dir, "file1.txt")
        f2 = os.path.join(self.test_dir, "tag_file1.txt") # Конфликтный файл!
        with open(f1, "w") as f: f.write("1")
        with open(f2, "w") as f: f.write("2")
        
        self.sorter.viewer.selected_files = [f1]
        self.sorter.files_queue = ["file1.txt", "tag_file1.txt"]
        
        # Переопределяем BatchRenameErrorsDialog для перехвата ошибок
        import ui_dialogs_generic
        dialog_errors = []
        original_init = ui_dialogs_generic.BatchRenameErrorsDialog.__init__
        def mock_init(dialog_self, errors, parent=None):
            dialog_errors.extend(errors)
            original_init(dialog_self, errors, parent)
            
        original_exec = ui_dialogs_generic.BatchRenameErrorsDialog.exec
        ui_dialogs_generic.BatchRenameErrorsDialog.__init__ = mock_init
        ui_dialogs_generic.BatchRenameErrorsDialog.exec = lambda dialog_self: 0
        
        try:
            self.sorter.on_affix_click("text", "tag")
            
            # Проверяем, что исходный файл не переименован
            self.assertTrue(os.path.exists(f1))
            self.assertTrue(os.path.exists(f2))
            
            # Проверяем, что предупреждение сработало и содержало описание ошибки
            self.assertTrue(len(dialog_errors) > 0)
            self.assertTrue(any("целевой файл уже существует" in err for err in dialog_errors))
        finally:
            ui_dialogs_generic.BatchRenameErrorsDialog.__init__ = original_init
            ui_dialogs_generic.BatchRenameErrorsDialog.exec = original_exec

    def test_batch_rename_duplicate_conflict_in_batch(self) -> None:
        """Проверяет отмену операции при дублировании имен файлов внутри пакета переименования."""
        # Создаем файлы
        f1 = os.path.join(self.test_dir, "file1.txt")
        f2 = os.path.join(self.test_dir, "file2.txt")
        with open(f1, "w") as f: f.write("1")
        with open(f2, "w") as f: f.write("2")
        
        self.sorter.viewer.selected_files = [f1, f2]
        self.sorter.files_queue = ["file1.txt", "file2.txt"]
        
        # Переопределяем BatchRenameErrorsDialog для перехвата ошибок
        import ui_dialogs_generic
        dialog_errors = []
        original_init = ui_dialogs_generic.BatchRenameErrorsDialog.__init__
        def mock_init(dialog_self, errors, parent=None):
            dialog_errors.extend(errors)
            original_init(dialog_self, errors, parent)
            
        original_exec = ui_dialogs_generic.BatchRenameErrorsDialog.exec
        ui_dialogs_generic.BatchRenameErrorsDialog.__init__ = mock_init
        ui_dialogs_generic.BatchRenameErrorsDialog.exec = lambda dialog_self: 0
        
        try:
            self.sorter.on_affix_click("rename", "%dell[static_name]")
            
            # Проверяем, что файлы не изменились
            self.assertTrue(os.path.exists(f1))
            self.assertTrue(os.path.exists(f2))
            
            # Проверяем предупреждение
            self.assertTrue(len(dialog_errors) > 0)
            self.assertTrue(any("дублируется в пакете переименования" in err for err in dialog_errors))
        finally:
            ui_dialogs_generic.BatchRenameErrorsDialog.__init__ = original_init
            ui_dialogs_generic.BatchRenameErrorsDialog.exec = original_exec

if __name__ == '__main__':
    unittest.main()
