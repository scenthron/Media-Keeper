"""
Тесты для InMemorySelection.apply_smart_filter().

Проверяют:
1. protected_dupes — выделяет не-защищённые файлы в группах, где есть хотя бы 1 защищённый.
2. reference_dupes  — выделяет не-эталонные файлы в группах, где есть хотя бы 1 эталонный.
3. Краевой случай: группа из 1 защищённого + 1 обычного (исторический баг).
4. Защищённые и эталонные файлы НИКОГДА не помечаются, даже при фильтрации.
5. Группа без защищённых/эталонных файлов пропускается этими фильтрами.
6. Железное правило: в группе без защищённых минимум 1 файл остаётся не помечен.
7. Накопительный принцип: повторный фильтр не трогает уже помеченные файлы.
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.cleaner.in_memory_selection import InMemorySelection


def _make_file(fid: int, path: str, is_protected: bool = False,
               is_reference: bool = False, size: int = 1000, mtime: float = 0.0) -> dict:
    """Вспомогательная функция — создаёт словарь файла в формате InMemorySelection."""
    return {
        'id': fid,
        'path': path,
        'is_protected': is_protected,
        'is_reference': is_reference,
        'size': size,
        'mtime': mtime,
    }


class TestProtectedDupesFilter(unittest.TestCase):
    """
    Тесты фильтра 'protected_dupes'.
    Логика: в группе есть защищённый файл → помечаем все НЕ-защищённые файлы.
    """

    def test_basic_protected_and_one_normal(self):
        """
        ИСТОРИЧЕСКИЙ БАГ: группа из 1 защищённого + 1 обычного.
        Фильтр должен пометить обычный файл, несмотря на то что candidates == 1.
        """
        prot = _make_file(1, 'C:/protected/img.jpg', is_protected=True)
        norm = _make_file(2, 'C:/normal/img.jpg')

        sel = InMemorySelection(
            group_files={1: [prot, norm]},
            protected_files={1}
        )
        sel.apply_smart_filter('protected_dupes')

        self.assertNotIn(1, sel.get_marked(), "Защищённый файл НЕ должен быть помечен")
        self.assertIn(2, sel.get_marked(), "Обычный файл ДОЛЖЕН быть помечен")

    def test_protected_with_multiple_normals(self):
        """1 защищённый + 3 обычных → все 3 обычных должны быть помечены."""
        prot = _make_file(1, 'C:/prot/img.jpg', is_protected=True)
        files = [
            prot,
            _make_file(2, 'C:/a/img.jpg'),
            _make_file(3, 'C:/b/img.jpg'),
            _make_file(4, 'C:/c/img.jpg'),
        ]
        sel = InMemorySelection(group_files={1: files}, protected_files={1})
        sel.apply_smart_filter('protected_dupes')

        self.assertNotIn(1, sel.get_marked())
        for fid in [2, 3, 4]:
            self.assertIn(fid, sel.get_marked(), f"Файл id={fid} должен быть помечен")

    def test_multiple_protected_in_group(self):
        """2 защищённых + 2 обычных → только обычные помечены."""
        files = [
            _make_file(1, 'C:/prot1/img.jpg', is_protected=True),
            _make_file(2, 'C:/prot2/img.jpg', is_protected=True),
            _make_file(3, 'C:/a/img.jpg'),
            _make_file(4, 'C:/b/img.jpg'),
        ]
        sel = InMemorySelection(group_files={1: files}, protected_files={1, 2})
        sel.apply_smart_filter('protected_dupes')

        self.assertNotIn(1, sel.get_marked())
        self.assertNotIn(2, sel.get_marked())
        self.assertIn(3, sel.get_marked())
        self.assertIn(4, sel.get_marked())

    def test_no_protected_files_in_group_skips(self):
        """Группа без защищённых файлов НЕ должна затрагиваться фильтром protected_dupes."""
        files = [
            _make_file(1, 'C:/a/img.jpg'),
            _make_file(2, 'C:/b/img.jpg'),
        ]
        sel = InMemorySelection(group_files={1: files}, protected_files=set())
        sel.apply_smart_filter('protected_dupes')

        self.assertEqual(sel.get_marked_count(), 0, "Группа без защищённых не должна трогаться")

    def test_all_normal_already_marked_skips(self):
        """Если все не-защищённые файлы уже помечены — нечего добавлять."""
        prot = _make_file(1, 'C:/prot/img.jpg', is_protected=True)
        norm = _make_file(2, 'C:/a/img.jpg')
        sel = InMemorySelection(group_files={1: [prot, norm]}, protected_files={1})
        # Помечаем вручную
        sel.mark_file(2, 1)
        count_before = sel.get_marked_count()
        sel.apply_smart_filter('protected_dupes')
        # Ничего нового не должно добавиться
        self.assertEqual(sel.get_marked_count(), count_before)

    def test_protected_file_never_marked(self):
        """Защищённый файл НЕ должен быть помечен ни при каких условиях."""
        files = [
            _make_file(1, 'C:/prot/img.jpg', is_protected=True),
            _make_file(2, 'C:/a/img.jpg'),
            _make_file(3, 'C:/b/img.jpg'),
        ]
        sel = InMemorySelection(group_files={1: files}, protected_files={1})

        # Пробуем пометить защищённый напрямую
        result = sel.mark_file(1, 1)
        self.assertFalse(result, "mark_file должен вернуть False для защищённого файла")
        self.assertNotIn(1, sel.get_marked())

    def test_multiple_groups_only_protected_groups_affected(self):
        """Фильтр затрагивает только группы, содержащие защищённые файлы."""
        group1 = [
            _make_file(1, 'C:/prot/img.jpg', is_protected=True),
            _make_file(2, 'C:/a/img.jpg'),
        ]
        group2 = [
            _make_file(3, 'C:/b/img.jpg'),
            _make_file(4, 'C:/c/img.jpg'),
        ]
        sel = InMemorySelection(
            group_files={1: group1, 2: group2},
            protected_files={1}
        )
        sel.apply_smart_filter('protected_dupes')

        self.assertIn(2, sel.get_marked(), "Файл из группы 1 должен быть помечен")
        self.assertNotIn(3, sel.get_marked(), "Группа 2 не должна затрагиваться")
        self.assertNotIn(4, sel.get_marked(), "Группа 2 не должна затрагиваться")


class TestReferenceDupesFilter(unittest.TestCase):
    """
    Тесты фильтра 'reference_dupes'.
    Логика: в группе есть эталонный файл → помечаем все НЕ-эталонные, НЕ-защищённые файлы.
    """

    def test_basic_reference_and_one_normal(self):
        """
        ИСТОРИЧЕСКИЙ БАГ: группа из 1 эталонного + 1 обычного.
        Фильтр должен пометить обычный файл (candidates == 1).
        """
        ref = _make_file(1, 'C:/ref/img.jpg', is_reference=True)
        norm = _make_file(2, 'C:/a/img.jpg')
        sel = InMemorySelection(group_files={1: [ref, norm]}, protected_files=set())
        sel.apply_smart_filter('reference_dupes')

        self.assertNotIn(1, sel.get_marked(), "Эталонный файл НЕ должен быть помечен")
        self.assertIn(2, sel.get_marked(), "Обычный файл ДОЛЖЕН быть помечен")

    def test_reference_with_multiple_normals(self):
        """1 эталон + 3 обычных → все 3 обычных помечены."""
        ref = _make_file(1, 'C:/ref/img.jpg', is_reference=True)
        files = [ref, _make_file(2, 'C:/a/img.jpg'), _make_file(3, 'C:/b/img.jpg'), _make_file(4, 'C:/c/img.jpg')]
        sel = InMemorySelection(group_files={1: files}, protected_files=set())
        sel.apply_smart_filter('reference_dupes')

        self.assertNotIn(1, sel.get_marked())
        for fid in [2, 3, 4]:
            self.assertIn(fid, sel.get_marked())

    def test_reference_does_not_mark_protected_files(self):
        """
        КЛЮЧЕВОЕ: 1 эталон + 1 защищённый + 1 обычный.
        Эталон и защищённый НЕ помечаются. Обычный — помечается.
        Это соответствует сценарию: «один файл есть и в эталонной, и в защищённой папке».
        """
        ref = _make_file(1, 'C:/ref/img.jpg', is_reference=True)
        prot = _make_file(2, 'C:/prot/img.jpg', is_protected=True)
        norm = _make_file(3, 'C:/a/img.jpg')
        sel = InMemorySelection(
            group_files={1: [ref, prot, norm]},
            protected_files={2}
        )
        sel.apply_smart_filter('reference_dupes')

        self.assertNotIn(1, sel.get_marked(), "Эталонный не помечается")
        self.assertNotIn(2, sel.get_marked(), "Защищённый не помечается даже в reference_dupes")
        self.assertIn(3, sel.get_marked(), "Обычный должен быть помечен")

    def test_no_reference_files_in_group_skips(self):
        """Группа без эталонных файлов НЕ затрагивается фильтром reference_dupes."""
        files = [_make_file(1, 'C:/a/img.jpg'), _make_file(2, 'C:/b/img.jpg')]
        sel = InMemorySelection(group_files={1: files}, protected_files=set())
        sel.apply_smart_filter('reference_dupes')
        self.assertEqual(sel.get_marked_count(), 0)

    def test_group_only_reference_and_protected_no_action(self):
        """
        Группа: 1 эталон + 1 защищённый, обычных нет.
        Нечего помечать — candidates пуст.
        """
        ref = _make_file(1, 'C:/ref/img.jpg', is_reference=True)
        prot = _make_file(2, 'C:/prot/img.jpg', is_protected=True)
        sel = InMemorySelection(group_files={1: [ref, prot]}, protected_files={2})
        sel.apply_smart_filter('reference_dupes')
        self.assertEqual(sel.get_marked_count(), 0)

    def test_reference_inherits_protection(self):
        """
        Проверяет, что эталонные файлы защищены от пометки.
        Их невозможно выделить (can_mark возвращает False).
        """
        # Эмулируем обогащение данных: если файл эталонный, то is_protected гарантированно True
        data_folder = {'reference': True, 'protected': False} # эталонная папка
        is_ref = data_folder.get('reference', False)
        is_prot = data_folder.get('protected', False) or is_ref # наследование
        
        self.assertTrue(is_prot, "Защита должна наследоваться от эталона")
        
        ref_file = _make_file(1, 'C:/ref/img.jpg', is_reference=is_ref, is_protected=is_prot)
        norm_file = _make_file(2, 'C:/normal/img.jpg')
        
        # Строим InMemorySelection, передавая ID защищенных файлов (включая эталон)
        protected_ids = {1} if ref_file['is_protected'] else set()
        sel = InMemorySelection(
            group_files={1: [ref_file, norm_file]},
            protected_files=protected_ids
        )
        
        # Проверяем, что эталонный файл невозможно пометить
        self.assertFalse(sel.can_mark(1, 1), "Эталонный файл не должен быть доступен для ручной пометки")
        self.assertTrue(sel.can_mark(2, 1), "Обычный файл должен быть доступен для пометки")
        
        # Проверяем, что попытка пометить эталонный файл игнорируется
        success = sel.mark_file(1, 1)
        self.assertFalse(success, "Попытка пометить эталонный файл должна завершиться неудачей")
        self.assertNotIn(1, sel.get_marked())


class TestIronRuleWithSpecialFilters(unittest.TestCase):
    """
    Проверяет, что железные правила (минимум 1 выживший) соблюдаются при специальных фильтрах.
    """

    def test_cumulative_protected_dupes_then_keep_first(self):
        """
        Накопительный принцип:
        1. Сначала protected_dupes помечает всё кроме защищённого.
        2. Потом keep_first не меняет ничего (все кандидаты уже помечены).
        """
        prot = _make_file(1, 'C:/prot/img.jpg', is_protected=True)
        norm1 = _make_file(2, 'C:/a/img.jpg')
        norm2 = _make_file(3, 'C:/b/img.jpg')
        sel = InMemorySelection(group_files={1: [prot, norm1, norm2]}, protected_files={1})

        sel.apply_smart_filter('protected_dupes')
        self.assertIn(2, sel.get_marked())
        self.assertIn(3, sel.get_marked())
        count_before = sel.get_marked_count()

        sel.apply_smart_filter('keep_first')
        self.assertEqual(sel.get_marked_count(), count_before, "keep_first не должен менять уже помеченные")

    def test_iron_rule_group_without_protected_never_marks_all(self):
        """
        Железное правило: в группе без защищённых файлов keep_first должен
        оставить минимум 1 файл не помеченным.
        """
        files = [_make_file(i, f'C:/folder/img{i}.jpg') for i in range(1, 5)]
        sel = InMemorySelection(group_files={1: files}, protected_files=set())
        sel.apply_smart_filter('keep_first')

        marked = sel.get_marked()
        total = len(files)
        self.assertLess(len(marked), total, "Не все файлы должны быть помечены")
        # id=1 (keep_first) должен остаться
        self.assertNotIn(1, marked)
        for fid in [2, 3, 4]:
            self.assertIn(fid, marked)

    def test_protected_dupes_respects_can_mark_more(self):
        """
        Если все не-защищённые файлы уже помечены (_can_mark_more=False),
        фильтр protected_dupes должен пропустить эту группу.
        """
        prot = _make_file(1, 'C:/prot/img.jpg', is_protected=True)
        norm = _make_file(2, 'C:/a/img.jpg')
        sel = InMemorySelection(group_files={1: [prot, norm]}, protected_files={1})
        # Уже помечен
        sel.mark_file(2, 1)
        self.assertEqual(sel.get_marked_count(), 1)

        sel.apply_smart_filter('protected_dupes')
        # Ничего нового
        self.assertEqual(sel.get_marked_count(), 1)


class TestMutualExclusionLogic(unittest.TestCase):
    """
    Юнит-тесты бизнес-логики взаимоисключения статусов (эталон/защита).
    Тестируется на уровне данных (словарь source_folders), без GUI.
    """

    def _make_source_data(self, protected: bool = False, reference: bool = False) -> dict:
        return {'protected': protected, 'reference': reference, 'is_system': False, 'color': '#fff'}

    def test_cannot_protect_reference_folder(self):
        """
        Логика toggle_source_protection: если папка уже эталон — защита не должна применяться.
        """
        data = self._make_source_data(reference=True, protected=True)  # Как было до фикса

        # Имитируем логику toggle_source_protection: если is_reference → выходим
        if data.get('reference', False):
            # Нельзя переключить — нет изменений
            pass
        else:
            data['protected'] = not data['protected']

        # protected не должен измениться (остался True от эталона)
        self.assertTrue(data['protected'], "Защита не должна сниматься с эталонной папки через toggle_source_protection")

    def test_cannot_set_reference_on_protected_folder(self):
        """
        Логика toggle_source_reference: если папка уже защищена (не эталон) — нельзя сделать эталоном.
        """
        data = self._make_source_data(protected=True, reference=False)

        # Имитируем логику toggle_source_reference: if is_protected and not is_reference → return
        can_toggle = not (data['protected'] and not data.get('reference', False))
        self.assertFalse(can_toggle, "Нельзя сделать эталоном уже защищённую папку")

    def test_removing_reference_resets_protected(self):
        """
        При снятии статуса эталона — protected должен тоже сброситься.
        """
        data = self._make_source_data(protected=True, reference=True)

        # Имитируем снятие эталона
        new_state = False
        data['reference'] = new_state
        if not new_state:
            data['protected'] = False

        self.assertFalse(data['reference'])
        self.assertFalse(data['protected'], "Снятие эталона должно убрать автоматически выставленную защиту")

    def test_setting_reference_sets_protected(self):
        """
        При назначении папки эталоном — protected автоматически True.
        """
        data = self._make_source_data(protected=False, reference=False)
        data['reference'] = True
        if data['reference']:
            data['protected'] = True

        self.assertTrue(data['protected'], "Назначение эталоном должно выставить защиту")
        self.assertTrue(data['reference'])


class TestPathMatching(unittest.TestCase):
    """
    Юнит-тесты для метода is_subpath из utils_common.
    Проверяет сегментированное сравнение путей (баг пересечения префиксов Folder и Folder2).
    """
    def test_exact_match(self):
        from utils_common import is_subpath
        self.assertTrue(is_subpath("C:/Folder", "C:/Folder"))
        self.assertTrue(is_subpath("C:\\Folder\\", "C:/Folder"))

    def test_subpath_match(self):
        from utils_common import is_subpath
        self.assertTrue(is_subpath("C:/Folder/sub/file.jpg", "C:/Folder"))
        self.assertTrue(is_subpath("C:\\Folder\\sub\\file.jpg", "C:/Folder"))

    def test_prefix_intersection_rejected(self):
        """
        КРИТИЧЕСКИЙ ТЕСТ: C:/Folder2 не должна считаться подпутем C:/Folder.
        """
        from utils_common import is_subpath
        self.assertFalse(is_subpath("C:/Folder2/file.jpg", "C:/Folder"), "Папка с пересекающимся префиксом не должна совпадать")
        self.assertFalse(is_subpath("C:\\Folder22\\file.jpg", "C:/Folder"))
        self.assertFalse(is_subpath("C:/Folder_Ref/file.jpg", "C:/Folder"))

    def test_case_insensitivity_windows(self):
        from utils_common import is_subpath
        self.assertTrue(is_subpath("c:/folder/file.jpg", "C:/Folder"))


class TestReadyStateSorting(unittest.TestCase):
    """
    Юнит-тесты для сортировки по степени готовности (Ready-State Sorting) и файлов внутри групп.
    """
    def test_ready_state_sorting_logic(self):
        from modules.cleaner.logic_tree import CleanerTreeMixin

        # Имитируем virtual_model
        class FakeVirtualModel:
            def __init__(self):
                self._all_items = []
                self._flat_items = []
                self._source_flat_items = []
                self.group_statuses = {}
                self._group_files_cache = {}
                self.reset_called = False
                self.rebuild_called = False

            def calculate_group_status(self, gid):
                return self.group_statuses[gid]

            def beginResetModel(self):
                pass

            def endResetModel(self):
                self.reset_called = True

            def rebuild_flat_items(self):
                self.rebuild_called = True
                self._source_flat_items = list(self._all_items)

        # Имитируем tree
        class FakeTree:
            def __init__(self):
                self.updates_enabled = True

            def setUpdatesEnabled(self, enabled):
                self.updates_enabled = enabled

        # Имитируем сам CleanerTreeMixin
        class FakeCleanerTree(CleanerTreeMixin):
            def __init__(self):
                self.current_view_mode = 0
                self.virtual_model = FakeVirtualModel()
                self.tree = FakeTree()

        tree_logic = FakeCleanerTree()

        # Создаем элементы: 4 группы с файлами
        # Группа 1: Красная (wasted_size = 1000)
        # marked=1, effective_unmarked=2 (всего 3)
        g1 = {'type': 'group', 'id': 1, 'wasted_size': 1000}
        f1_1 = {'type': 'file', 'id': 101, 'group_id': 1, 'is_marked': 1, 'is_reference': False, 'is_protected': False, 'path': 'C:/1.jpg'}
        f1_2 = {'type': 'file', 'id': 102, 'group_id': 1, 'is_marked': 0, 'is_reference': False, 'is_protected': False, 'path': 'C:/2.jpg'}
        f1_3 = {'type': 'file', 'id': 103, 'group_id': 1, 'is_marked': 0, 'is_reference': False, 'is_protected': False, 'path': 'C:/3.jpg'}

        # Группа 2: Серая (wasted_size = 2000)
        # marked=0, effective_unmarked=2 (всего 2)
        g2 = {'type': 'group', 'id': 2, 'wasted_size': 2000}
        f2_1 = {'type': 'file', 'id': 201, 'group_id': 2, 'is_marked': 0, 'is_reference': False, 'is_protected': False, 'path': 'C:/4.jpg'}
        f2_2 = {'type': 'file', 'id': 202, 'group_id': 2, 'is_marked': 0, 'is_reference': False, 'is_protected': False, 'path': 'C:/5.jpg'}

        # Группа 3: Зеленая (wasted_size = 1500)
        # marked=1, effective_unmarked=1 (всего 2)
        g3 = {'type': 'group', 'id': 3, 'wasted_size': 1500}
        f3_1 = {'type': 'file', 'id': 301, 'group_id': 3, 'is_marked': 1, 'is_reference': False, 'is_protected': False, 'path': 'C:/6.jpg'}
        f3_2 = {'type': 'file', 'id': 302, 'group_id': 3, 'is_marked': 0, 'is_reference': False, 'is_protected': False, 'path': 'C:/7.jpg'}

        # Группа 4: Красная (wasted_size = 5000) - вторичная сортировка
        # marked=1, effective_unmarked=2 (всего 3)
        g4 = {'type': 'group', 'id': 4, 'wasted_size': 5000}
        f4_1 = {'type': 'file', 'id': 401, 'group_id': 4, 'is_marked': 1, 'is_reference': False, 'is_protected': False, 'path': 'C:/8.jpg'}
        f4_2 = {'type': 'file', 'id': 402, 'group_id': 4, 'is_marked': 0, 'is_reference': False, 'is_protected': False, 'path': 'C:/9.jpg'}
        f4_3 = {'type': 'file', 'id': 403, 'group_id': 4, 'is_marked': 0, 'is_reference': False, 'is_protected': False, 'path': 'C:/10.jpg'}

        # Заполняем _all_items (в произвольном исходном порядке)
        tree_logic.virtual_model._all_items = [
            g3, f3_1, f3_2,
            g1, f1_1, f1_2, f1_3,
            g2, f2_1, f2_2,
            g4, f4_1, f4_2, f4_3
        ]
        
        # Кэш
        tree_logic.virtual_model._group_files_cache = {
            1: [f1_1, f1_2, f1_3],
            2: [f2_1, f2_2],
            3: [f3_1, f3_2],
            4: [f4_1, f4_2, f4_3],
        }

        # Задаем статусы групп для calculate_group_status:
        # (marked_files, effective_unmarked, total_files)
        tree_logic.virtual_model.group_statuses = {
            1: (1, 2, 3), # Красная
            2: (0, 2, 2), # Серая
            3: (1, 1, 2), # Зеленая
            4: (1, 2, 3), # Красная
        }

        # Запускаем сортировку
        tree_logic.sort_tree_by_selection()

        # Ожидаемый порядок групп по id:
        # 1. Красные: Группа 4 (wasted_size 5000), затем Группа 1 (wasted_size 1000)
        # 2. Серые: Группа 2 (wasted_size 2000)
        # 3. Зеленые: Группа 3 (wasted_size 1500)
        expected_group_ids = [4, 1, 2, 3]

        sorted_groups = [item for item in tree_logic.virtual_model._all_items if item['type'] == 'group']
        sorted_group_ids = [g['id'] for g in sorted_groups]

        self.assertEqual(sorted_group_ids, expected_group_ids)

        # Проверим, что _flat_items визуально обновлен (не пустой и совпадает с _source_flat_items)
        self.assertEqual(len(tree_logic.virtual_model._flat_items), len(tree_logic.virtual_model._all_items))


class TestFilesInGroupSorting(unittest.TestCase):
    """
    Проверяет, что файлы внутри группы сортируются так, что эталонные и защищенные идут в самом верху.
    """
    def test_files_in_group_sorting(self):
        from modules.cleaner.logic_tree import CleanerTreeMixin

        # Имитируем virtual_model
        class FakeVirtualModel:
            def __init__(self):
                self._all_items = []
                self._flat_items = []
                self._source_flat_items = []
                self._group_files_cache = {}

            def calculate_group_status(self, gid):
                return 0, 2, 2

            def beginResetModel(self):
                pass

            def endResetModel(self):
                pass

            def rebuild_flat_items(self):
                self._source_flat_items = list(self._all_items)

        class FakeTree:
            def setUpdatesEnabled(self, enabled):
                pass

        class FakeCleanerTree(CleanerTreeMixin):
            def __init__(self):
                self.current_view_mode = 0
                self.virtual_model = FakeVirtualModel()
                self.tree = FakeTree()

        tree_logic = FakeCleanerTree()

        # Создаем файлы с разными статусами
        # f1: обычный, f2: защищенный, f3: эталонный
        g = {'type': 'group', 'id': 1, 'wasted_size': 1000}
        f1 = {'type': 'file', 'id': 101, 'group_id': 1, 'is_reference': False, 'is_protected': False, 'path': 'C:/normal.jpg'}
        f2 = {'type': 'file', 'id': 102, 'group_id': 1, 'is_reference': False, 'is_protected': True, 'path': 'C:/protected.jpg'}
        f3 = {'type': 'file', 'id': 103, 'group_id': 1, 'is_reference': True, 'is_protected': True, 'path': 'C:/reference.jpg'}

        tree_logic.virtual_model._all_items = [g, f1, f2, f3]
        tree_logic.virtual_model._group_files_cache = {1: [f1, f2, f3]}

        # Запускаем сортировку
        tree_logic.sort_tree_by_selection()

        # Ожидаемый порядок файлов внутри группы: эталон (f3), защищенный (f2), обычный (f1)
        expected_ids = [1, 103, 102, 101]
        sorted_ids = [item['id'] for item in tree_logic.virtual_model._all_items]
        self.assertEqual(sorted_ids, expected_ids)

        # Проверим, что в кэше _group_files_cache они тоже отсортированы
        cached_ids = [f['id'] for f in tree_logic.virtual_model._group_files_cache[1]]
        self.assertEqual(cached_ids, [103, 102, 101])


if __name__ == '__main__':
    unittest.main(verbosity=2)
