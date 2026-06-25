import unittest
import os
import re

class TestExplorerLaunch(unittest.TestCase):
    """
    Тест для жесткой проверки того, что для открытия папок и выделения файлов
    используется ТОЛЬКО нативный метод reveal_in_explorer из utils_common.
    Использование прямого вызова subprocess, explorer.exe или других способов
    внутри рабочих модулей ЗАПРЕЩЕНО.
    """

    def test_strict_native_explorer_usage(self):
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        py_files_checked = 0
        violations = []

        # Запрещенные паттерны: прямой вызов explorer.exe через subprocess.Popen или os.system
        # или использование /select в обход reveal_in_explorer
        forbidden_patterns = [
            (re.compile(r"subprocess\.Popen\(\s*.*explorer"), "Прямой вызов explorer через subprocess.Popen"),
            (re.compile(r"\/select,"), "Использование флага /select в обход reveal_in_explorer"),
            (re.compile(r"explorer\.exe"), "Прямое упоминание explorer.exe (должно использоваться только в utils_common.py)"),
        ]

        for root, _, files in os.walk(root_dir):
            # Пропускаем папку тестов, временные тесты и сам файл утилит, где метод реализован
            dir_name = os.path.split(root)[1]
            if dir_name in ('tests', 'open_file_test'):
                continue
                
            for file in files:
                # utils_common.py - единственный файл, где разрешено использовать explorer.exe и SHOpenFolderAndSelectItems
                if file == 'utils_common.py':
                    continue
                    
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    py_files_checked += 1
                    
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        for idx, line in enumerate(f, 1):
                            # Игнорируем комментарии
                            if line.strip().startswith('#'):
                                continue
                                
                            for pattern, desc in forbidden_patterns:
                                if pattern.search(line):
                                    violations.append(
                                        f"{os.path.relpath(file_path, root_dir)}:line {idx} -> {line.strip()} ({desc})"
                                    )

        # Выводим подробное сообщение об ошибке, если найдены нарушения
        if violations:
            error_msg = (
                "\n[КРИТИЧЕСКАЯ ОШИБКА] Обнаружен запрещенный способ открытия папки/проводника!\n"
                "Для открытия папки с выделением файла необходимо импортировать и использовать:\n"
                "    from utils_common import reveal_in_explorer\n"
                "    reveal_in_explorer(path)\n\n"
                "Нарушения найдены в следующих файлах:\n" + "\n".join(violations)
            )
            self.fail(error_msg)

        print(f"Жесткая проверка пройдена. Успешно проверено файлов: {py_files_checked}. Все вызовы проводника идут через reveal_in_explorer.")

if __name__ == '__main__':
    unittest.main()
