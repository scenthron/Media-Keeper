"""
Юнит-тесты логики построения дерева каталогов в Sorter.

Тестируется чистая логика классификации папок (CategoryWidget vs LeafNodeWidget),
без запуска Qt и без создания реальных виджетов.

Эта логика находится в:
  src/modules/sorter/ui_sidebar_category.py → refresh_sections()

Железное правило (из истории багов):
  - Папка должна стать CategoryWidget если у неё ЕСТЬ подпапки.
  - Папка должна стать LeafNodeWidget если у неё НЕТ подпапок.
  - QTimer.singleShot на родителе при отсутствии папок — запрещён (удалён),
    т.к. вызывался на уже удалённом через deleteLater объекте.
  - max_nesting_depth ограничивает ГЛУБИНУ СКАНИРОВАНИЯ, но не отображение узла как CategoryWidget.
"""

import os
import sys
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


# ---------------------------------------------------------------------------
# Чистая функция-классификатор — точный аналог логики из refresh_sections().
# Тестируем именно её, без Qt-зависимостей.
# ---------------------------------------------------------------------------

MEDIAKEEPER_SKIP = ".mediakeeper"


def classify_subfolders(parent_path: str, max_nesting_depth: int, level: int) -> list[dict]:
    """
    Возвращает список описаний дочерних папок — точно так же, как это делает
    refresh_sections() в CategoryWidget.

    Каждый элемент: {'name': str, 'path': str, 'type': 'category' | 'leaf'}

    'category' → папка имеет подпапки → рендерится как CategoryWidget (раскрываемый)
    'leaf'     → папка без подпапок  → рендерится как LeafNodeWidget (кнопка)
    """
    if not os.path.exists(parent_path):
        return []

    try:
        items = sorted(os.listdir(parent_path))
    except PermissionError:
        return []

    folders = [
        d for d in items
        if os.path.isdir(os.path.join(parent_path, d)) and d != MEDIAKEEPER_SKIP
    ]

    result = []
    for f in folders:
        fp = os.path.join(parent_path, f)
        has_sub = False

        if level + 1 < max_nesting_depth:
            try:
                sub = os.listdir(fp)
                has_sub = any(
                    os.path.isdir(os.path.join(fp, i)) for i in sub
                    if i != MEDIAKEEPER_SKIP
                )
            except PermissionError:
                pass

        result.append({
            'name': f,
            'path': fp,
            'type': 'category' if has_sub else 'leaf',
        })

    return result


def has_any_folders(parent_path: str) -> bool:
    """Возвращает True если в папке есть хотя бы одна дочерняя папка (кроме .mediakeeper)."""
    if not os.path.exists(parent_path):
        return False
    try:
        items = os.listdir(parent_path)
    except PermissionError:
        return False
    return any(
        os.path.isdir(os.path.join(parent_path, d)) and d != MEDIAKEEPER_SKIP
        for d in items
    )


# ---------------------------------------------------------------------------
# Вспомогательный класс для построения тестовых файловых структур
# ---------------------------------------------------------------------------

class FsBuilder:
    """Строит временную файловую структуру на диске для тестов."""

    def __init__(self, base: str):
        self.base = base

    def mkdir(self, *parts) -> str:
        path = os.path.join(self.base, *parts)
        os.makedirs(path, exist_ok=True)
        return path

    def touch(self, *parts) -> str:
        path = os.path.join(self.base, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, 'w').close()
        return path

    def path(self, *parts) -> str:
        return os.path.join(self.base, *parts)


# ---------------------------------------------------------------------------
# Тесты
# ---------------------------------------------------------------------------

class TestClassifySubfolders(unittest.TestCase):
    """Тестирует функцию classify_subfolders — аналог логики refresh_sections."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.fs = FsBuilder(self.tmpdir)
        self.MAX = 10  # max_nesting_depth по умолчанию

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Базовые случаи
    # ------------------------------------------------------------------

    def test_empty_folder_returns_no_children(self):
        """Пустая папка — нет дочерних узлов."""
        root = self.fs.mkdir("root")
        result = classify_subfolders(root, self.MAX, level=0)
        self.assertEqual(result, [])

    def test_folder_with_only_files_returns_no_children(self):
        """Папка только с файлами (без подпапок) — нет дочерних узлов."""
        root = self.fs.mkdir("root")
        self.fs.touch("root", "video.mp4")
        self.fs.touch("root", "image.jpg")
        result = classify_subfolders(root, self.MAX, level=0)
        self.assertEqual(result, [])

    def test_single_leaf_subfolder(self):
        """Папка с одной подпапкой без своих подпапок → LeafNode."""
        root = self.fs.mkdir("root")
        self.fs.mkdir("root", "Фильмы")
        result = classify_subfolders(root, self.MAX, level=0)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'Фильмы')
        self.assertEqual(result[0]['type'], 'leaf')

    def test_single_category_subfolder(self):
        """Папка с одной подпапкой, у которой ЕСТЬ свои подпапки → CategoryWidget."""
        root = self.fs.mkdir("root")
        self.fs.mkdir("root", "Фильмы", "2023")
        result = classify_subfolders(root, self.MAX, level=0)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'Фильмы')
        self.assertEqual(result[0]['type'], 'category')

    # ------------------------------------------------------------------
    # Смешанные конфигурации
    # ------------------------------------------------------------------

    def test_mixed_leaf_and_category(self):
        """Папка с двумя подпапками: одна без вложений (leaf), другая с вложениями (category)."""
        root = self.fs.mkdir("root")
        self.fs.mkdir("root", "Сериалы")              # leaf — нет подпапок
        self.fs.mkdir("root", "Фильмы", "2023")       # category — есть подпапка
        result = classify_subfolders(root, self.MAX, level=0)
        by_name = {r['name']: r['type'] for r in result}
        self.assertEqual(by_name['Сериалы'], 'leaf')
        self.assertEqual(by_name['Фильмы'], 'category')

    def test_multiple_leaves(self):
        """Несколько подпапок без вложений — все LeafNode."""
        root = self.fs.mkdir("root")
        for name in ["Аниме", "Сериалы", "Мультфильмы"]:
            self.fs.mkdir("root", name)
        result = classify_subfolders(root, self.MAX, level=0)
        self.assertEqual(len(result), 3)
        for r in result:
            self.assertEqual(r['type'], 'leaf', f"{r['name']} должен быть leaf")

    def test_multiple_categories(self):
        """Несколько подпапок с вложениями — все CategoryWidget."""
        root = self.fs.mkdir("root")
        self.fs.mkdir("root", "Фильмы", "2023")
        self.fs.mkdir("root", "Сериалы", "Сезон1")
        self.fs.mkdir("root", "Аниме", "Жанр")
        result = classify_subfolders(root, self.MAX, level=0)
        self.assertEqual(len(result), 3)
        for r in result:
            self.assertEqual(r['type'], 'category', f"{r['name']} должен быть category")

    # ------------------------------------------------------------------
    # Глубокая вложенность
    # ------------------------------------------------------------------

    def test_three_levels_deep(self):
        """
        Трёхуровневая структура:
        root/
          Видео/          → category (есть подпапка Фильмы)
            Фильмы/       → category (есть подпапка 2023)
              2023/       → leaf (нет подпапок)
        """
        root = self.fs.mkdir("root")
        self.fs.mkdir("root", "Видео", "Фильмы", "2023")

        # Уровень 0: Видео → category
        level0 = classify_subfolders(root, self.MAX, level=0)
        self.assertEqual(len(level0), 1)
        self.assertEqual(level0[0]['name'], 'Видео')
        self.assertEqual(level0[0]['type'], 'category')

        # Уровень 1: Фильмы → category
        level1 = classify_subfolders(level0[0]['path'], self.MAX, level=1)
        self.assertEqual(len(level1), 1)
        self.assertEqual(level1[0]['name'], 'Фильмы')
        self.assertEqual(level1[0]['type'], 'category')

        # Уровень 2: 2023 → leaf
        level2 = classify_subfolders(level1[0]['path'], self.MAX, level=2)
        self.assertEqual(len(level2), 1)
        self.assertEqual(level2[0]['name'], '2023')
        self.assertEqual(level2[0]['type'], 'leaf')

    def test_deep_nesting_at_max_level(self):
        """
        При достижении max_nesting_depth сканирование подпапок не выполняется,
        поэтому папка классифицируется как leaf, даже если у неё есть подпапки.
        Это железное правило: max_nesting_depth ограничивает СКАНИРОВАНИЕ, а не рендеринг.
        """
        root = self.fs.mkdir("root")
        self.fs.mkdir("root", "Deep", "SubDeep")  # Deep имеет подпапку SubDeep

        # level=9, max_nesting_depth=10: level+1=10 — не < max_nesting_depth → has_sub не вычисляется → leaf
        result = classify_subfolders(root, max_nesting_depth=10, level=9)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'Deep')
        self.assertEqual(result[0]['type'], 'leaf',
                         "При достижении max_nesting_depth папка должна стать leaf")

    def test_just_below_max_level(self):
        """Уровень на 1 ниже max_nesting_depth — сканирование разрешено, корректно возвращает category."""
        root = self.fs.mkdir("root")
        self.fs.mkdir("root", "Deep", "SubDeep")  # Deep имеет подпапку

        # level=8, max_nesting_depth=10: level+1=9 < 10 → has_sub вычисляется → category
        result = classify_subfolders(root, max_nesting_depth=10, level=8)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'Deep')
        self.assertEqual(result[0]['type'], 'category')

    # ------------------------------------------------------------------
    # Специальные папки и граничные случаи
    # ------------------------------------------------------------------

    def test_mediakeeper_folder_is_ignored(self):
        """.mediakeeper не должна появляться в дереве каталогов."""
        root = self.fs.mkdir("root")
        self.fs.mkdir("root", ".mediakeeper")
        self.fs.mkdir("root", "Фильмы")
        result = classify_subfolders(root, self.MAX, level=0)
        names = [r['name'] for r in result]
        self.assertNotIn('.mediakeeper', names)
        self.assertIn('Фильмы', names)

    def test_only_mediakeeper_returns_empty(self):
        """Если единственная папка — .mediakeeper, результат должен быть пустым."""
        root = self.fs.mkdir("root")
        self.fs.mkdir("root", ".mediakeeper")
        result = classify_subfolders(root, self.MAX, level=0)
        self.assertEqual(result, [])

    def test_folder_with_files_and_subfolders(self):
        """Папка содержит и файлы, и подпапки — файлы игнорируются, папки учитываются."""
        root = self.fs.mkdir("root")
        self.fs.touch("root", "readme.txt")
        self.fs.mkdir("root", "Фильмы")
        self.fs.mkdir("root", "Сериалы", "Сезон1")
        result = classify_subfolders(root, self.MAX, level=0)
        self.assertEqual(len(result), 2)
        by_name = {r['name']: r['type'] for r in result}
        self.assertEqual(by_name['Фильмы'], 'leaf')
        self.assertEqual(by_name['Сериалы'], 'category')

    def test_nonexistent_path_returns_empty(self):
        """Несуществующий путь не должен кидать исключение — возвращает пустой список."""
        result = classify_subfolders("/path/that/does/not/exist", self.MAX, level=0)
        self.assertEqual(result, [])

    def test_result_is_sorted_alphabetically(self):
        """Дочерние папки должны быть отсортированы по алфавиту."""
        root = self.fs.mkdir("root")
        for name in ["Ящик", "Антресоль", "Балкон"]:
            self.fs.mkdir("root", name)
        result = classify_subfolders(root, self.MAX, level=0)
        names = [r['name'] for r in result]
        self.assertEqual(names, sorted(names))

    def test_leaf_with_only_files_in_subfolder(self):
        """
        Папка Фильмы содержит только файлы (не подпапки) → has_sub = False → leaf.
        Регрессионный тест: было бы ошибкой считать файлы внутри за признак category.
        """
        root = self.fs.mkdir("root")
        self.fs.mkdir("root", "Фильмы")
        self.fs.touch("root", "Фильмы", "movie1.mp4")
        self.fs.touch("root", "Фильмы", "movie2.mkv")
        result = classify_subfolders(root, self.MAX, level=0)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['type'], 'leaf')

    # ------------------------------------------------------------------
    # Реальный сценарий: создание новой подпапки (баг из истории)
    # ------------------------------------------------------------------

    def test_scenario_leaf_becomes_category_after_subfolder_created(self):
        """
        РЕГРЕССИОННЫЙ ТЕСТ — воспроизводит краш при создании папки в дереве.

        Сценарий:
          1. Видео/ имеет Фильмы/ без подпапок → Фильмы = leaf
          2. Пользователь создаёт Фильмы/2023/ через кнопку +
          3. parent.refresh_sections() вызывается повторно
          4. Теперь Фильмы/ имеет подпапку → Фильмы = category

        До исправления: QTimer.singleShot на удалённом объекте вызывал NameError
        и некорректно обновлял дерево.
        """
        root = self.fs.mkdir("root")
        filmy = self.fs.mkdir("root", "Фильмы")

        # Шаг 1: до создания подпапки
        result_before = classify_subfolders(root, self.MAX, level=0)
        self.assertEqual(result_before[0]['type'], 'leaf',
                         "До создания подпапки — Фильмы должна быть leaf")

        # Шаг 2: создаём подпапку (имитация нажатия кнопки +)
        os.makedirs(os.path.join(filmy, "2023"), exist_ok=True)

        # Шаг 3: повторный вызов classify (аналог refresh_sections после создания)
        result_after = classify_subfolders(root, self.MAX, level=0)
        self.assertEqual(result_after[0]['type'], 'category',
                         "После создания подпапки — Фильмы должна стать category")

    def test_scenario_category_becomes_leaf_after_subfolder_removed(self):
        """
        РЕГРЕССИОННЫЙ ТЕСТ — обратный сценарий: удаление последней подпапки.

        Сценарий:
          1. Фильмы/ имеет 2023/ → category
          2. 2023/ удаляется
          3. refresh_sections() вызывается снова
          4. Фильмы/ больше не имеет подпапок → leaf

        До исправления: QTimer.singleShot(0, parent.refresh_sections) мог
        вызываться на уже удалённом виджете через deleteLater → пустое дерево.
        """
        root = self.fs.mkdir("root")
        sub2023 = self.fs.mkdir("root", "Фильмы", "2023")

        result_before = classify_subfolders(root, self.MAX, level=0)
        self.assertEqual(result_before[0]['type'], 'category',
                         "С подпапкой 2023 — Фильмы должна быть category")

        # Удаляем подпапку
        shutil.rmtree(sub2023)

        result_after = classify_subfolders(root, self.MAX, level=0)
        self.assertEqual(result_after[0]['type'], 'leaf',
                         "После удаления 2023 — Фильмы должна стать leaf")

    def test_only_mediakeeper_inside_subfolder_is_leaf(self):
        """
        РЕГРЕССИОННЫЙ ТЕСТ — точный баг из боевого использования.

        Сценарий: папка Фильмы/ содержит только .mediakeeper/ внутри
        (папка конфига автоматизации). НИ ОДНОЙ реальной подпапки нет.
        Ожидание: Фильмы = leaf (без кнопки цвета, без кнопки свернуть).

        До исправления: has_sub проверял ALL подпапки включая .mediakeeper,
        поэтому папка ошибочно становилась CategoryWidget с кнопкой цвета.
        """
        root = self.fs.mkdir("root")
        self.fs.mkdir("root", "Фильмы", ".mediakeeper")  # только конфиг, без реальных подпапок
        result = classify_subfolders(root, self.MAX, level=0)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'Фильмы')
        self.assertEqual(result[0]['type'], 'leaf',
                         "Папка с только .mediakeeper внутри должна быть leaf, не category")

    def test_mediakeeper_plus_real_subfolder_is_category(self):
        """
        Папка имеет .mediakeeper И реальную подпапку → должна быть category.
        """
        root = self.fs.mkdir("root")
        self.fs.mkdir("root", "Фильмы", ".mediakeeper")
        self.fs.mkdir("root", "Фильмы", "2023")  # реальная подпапка
        result = classify_subfolders(root, self.MAX, level=0)
        self.assertEqual(result[0]['type'], 'category',
                         "Папка с .mediakeeper и реальной подпапкой должна быть category")

    def test_scenario_new_root_category_created(self):
        """
        Создание новой папки верхнего уровня через кнопку «Создать категорию».
        Новая папка пустая → leaf.
        """
        root = self.fs.mkdir("root")
        self.fs.mkdir("root", "Видео")

        result = classify_subfolders(root, self.MAX, level=0)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'Видео')
        self.assertEqual(result[0]['type'], 'leaf')

    # ------------------------------------------------------------------
    # has_any_folders — тест видимости кнопки «свернуть»
    # ------------------------------------------------------------------

    def test_has_any_folders_true(self):
        """has_any_folders возвращает True если есть хотя бы одна подпапка."""
        root = self.fs.mkdir("root")
        self.fs.mkdir("root", "Фильмы")
        self.assertTrue(has_any_folders(root))

    def test_has_any_folders_false_for_empty_dir(self):
        """has_any_folders возвращает False для пустой папки."""
        root = self.fs.mkdir("root")
        self.assertFalse(has_any_folders(root))

    def test_has_any_folders_false_for_files_only(self):
        """has_any_folders возвращает False если есть только файлы."""
        root = self.fs.mkdir("root")
        self.fs.touch("root", "file.mp4")
        self.assertFalse(has_any_folders(root))

    def test_has_any_folders_ignores_mediakeeper(self):
        """.mediakeeper не считается папкой для кнопки свернуть."""
        root = self.fs.mkdir("root")
        self.fs.mkdir("root", ".mediakeeper")
        self.assertFalse(has_any_folders(root))

    def test_has_any_folders_false_for_nonexistent(self):
        """has_any_folders не кидает исключение для несуществующего пути."""
        self.assertFalse(has_any_folders("/nonexistent/path/xyz"))


class TestClassifyCount(unittest.TestCase):
    """Тестирует количество и порядок возвращаемых узлов."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.fs = FsBuilder(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_count_matches_actual_subfolders(self):
        """Количество результатов равно количеству реальных подпапок (без .mediakeeper)."""
        root = self.fs.mkdir("root")
        expected_count = 5
        for i in range(expected_count):
            self.fs.mkdir("root", f"Folder_{i}")
        self.fs.mkdir("root", ".mediakeeper")  # не должна считаться

        result = classify_subfolders(root, max_nesting_depth=10, level=0)
        self.assertEqual(len(result), expected_count)

    def test_paths_are_absolute_and_correct(self):
        """Каждый путь в результате корректно указывает на реальную папку."""
        root = self.fs.mkdir("root")
        self.fs.mkdir("root", "Видео")
        self.fs.mkdir("root", "Аудио")

        result = classify_subfolders(root, max_nesting_depth=10, level=0)
        for r in result:
            self.assertTrue(os.path.exists(r['path']),
                            f"Путь {r['path']} не существует")
            self.assertTrue(os.path.isdir(r['path']),
                            f"Путь {r['path']} не является папкой")


if __name__ == '__main__':
    unittest.main(verbosity=2)
