import os
import logging
import traceback
from typing import Any, Callable
from PyQt6.QtCore import Qt, QCoreApplication, QTimer

from .in_memory_selection import InMemorySelection
from utils_common import is_subpath


class CleanerSelectionMixin:
    """Mixin that provides selection handling for the Cleaner UI.

    After a scan the virtual model contains a cache ``_group_files_cache``
    (group_id -> list[dict]) where each dict represents a file item.  When the
    model is first loaded we build an ``InMemorySelection`` instance that holds
    the selection state entirely in RAM.  All subsequent UI actions (smart
    select, batch select, deselect, header actions, etc.) operate on this object
    instead of issuing ``UPDATE`` statements against SQLite.  The UI is refreshed
    by copying the ``is_marked`` flag from the in-memory object back into the
    virtual model items.

    Iron Rules (enforced here and in InMemorySelection):
    1. At least one survivor per group must always remain.
    2. Filters are cumulative — each filter pass further reduces candidates.
    3. The program never autonomously un-marks files selected by the user.
    """

    # ------------------------------------------------------------------
    # Model initialisation
    # ------------------------------------------------------------------
    def start_incremental_load(self, flat_items: list[dict[str, Any]]) -> None:
        import time
        logging.info("[PERF] start_incremental_load: Начало загрузки в модель...")
        t_start = time.perf_counter()

        if hasattr(self, 'incremental_loader_timer'):
            self.incremental_loader_timer.stop()

        self.virtual_model.beginResetModel()
        self.virtual_model.source_folders = self.source_folders
        self.virtual_model._all_items = flat_items
        self.virtual_model._group_files_cache = {}

        # Build InMemorySelection from flat_items
        self._build_in_memory_selection(flat_items)

        # Enrich files with source_folders metadata and build group cache
        logging.info("[PERF] start_incremental_load: Запуск цикла Enrich & Cache...")
        for item in flat_items:
            if item['type'] == 'file':
                path: str = item['path']
                is_protected = False
                is_reference = False
                color = "#555"
                if path.startswith('[Дамп]'):
                    is_protected = True
                else:
                    for src_path, data in self.source_folders.items():
                        if is_subpath(path, src_path):
                            is_reference = data.get('reference', False)
                            is_protected = data.get('protected', False) or is_reference
                            color = data.get('color', '#555')
                            break
                item['is_protected'] = is_protected
                item['is_reference'] = is_reference
                item['color'] = color

                g_id = item['group_id']
                if g_id not in self.virtual_model._group_files_cache:
                    self.virtual_model._group_files_cache[g_id] = []
                self.virtual_model._group_files_cache[g_id].append(item)

        groups_count = sum(1 for item in flat_items if item['type'] == 'group')
        if groups_count < 300:
            self.virtual_model._expanded_groups = {
                item['id'] for item in flat_items if item['type'] == 'group'
            }
        else:
            self.virtual_model._expanded_groups = set()

        self.virtual_model.rebuild_flat_items()
        self.virtual_model._flat_items = list(self.virtual_model._source_flat_items)
        self.virtual_model.endResetModel()

        self.overlay.hide()
        self.update_view_stats()
        self.validate_move_state()

        total_duration = time.perf_counter() - t_start
        logging.info(
            f"[PERF] start_incremental_load завершен ({len(self.virtual_model._flat_items)} элементов). "
            f"Время: {total_duration:.4f} сек"
        )

    def start_incremental_load_from_worker(
        self,
        flat_items: list[dict[str, Any]],
        _group_files_cache_ignored: dict[Any, list[dict[str, Any]]]
    ) -> None:
        """Async model initialisation with data pre-built in a background worker."""
        import time
        logging.info("[PERF] start_incremental_load_from_worker: Начало подготовки модели...")
        t_start = time.perf_counter()

        if hasattr(self, 'incremental_loader_timer'):
            self.incremental_loader_timer.stop()

        # Build group_files_cache HERE in the main thread!
        # If we use the dict passed from the QThread signal, PyQt creates a deep copy
        # of the objects, which breaks shared references with flat_items!
        group_files_cache = {}
        for item in flat_items:
            if item['type'] == 'file':
                g_id = item['group_id']
                if g_id not in group_files_cache:
                    group_files_cache[g_id] = []
                group_files_cache[g_id].append(item)

        self.virtual_model.beginResetModel()
        self.virtual_model.source_folders = self.source_folders
        self.virtual_model._all_items = flat_items
        self.virtual_model._group_files_cache = group_files_cache

        # Build InMemorySelection from the enriched flat_items
        self._build_in_memory_selection(flat_items)

        groups_count = sum(1 for item in flat_items if item['type'] == 'group')
        if groups_count < 300:
            self.virtual_model._expanded_groups = {
                item['id'] for item in flat_items if item['type'] == 'group'
            }
        else:
            self.virtual_model._expanded_groups = set()

        self.virtual_model.rebuild_flat_items()
        self.virtual_model._flat_items = list(self.virtual_model._source_flat_items)
        self.virtual_model.endResetModel()

        self.overlay.hide()
        self.update_view_stats()
        self.validate_move_state()

        total_duration = time.perf_counter() - t_start
        logging.info(
            f"[PERF] start_incremental_load_from_worker завершен ({len(self.virtual_model._flat_items)} элементов). "
            f"Время: {total_duration:.4f} сек"
        )

    def _build_in_memory_selection(self, flat_items: list[dict[str, Any]]) -> None:
        """Build the InMemorySelection object from a flat item list."""
        group_files: dict[int, list[dict]] = {}
        protected_file_ids: set[int] = set()

        for item in flat_items:
            if item['type'] != 'file':
                continue
            gid = item['group_id']
            fid = item['id']
            group_files.setdefault(gid, []).append(item)
            if item.get('is_protected'):
                protected_file_ids.add(fid)

        enforce_rule = getattr(self, 'current_tab', 0) == 0
        self.in_memory_selection = InMemorySelection(group_files, protected_file_ids, enforce_survivor_rule=enforce_rule)
        logging.info(
            f"[InMemory] Создан InMemorySelection: {len(group_files)} групп, "
            f"{sum(len(v) for v in group_files.values())} файлов, "
            f"{len(protected_file_ids)} защищённых"
        )

    # ------------------------------------------------------------------
    # Incremental load helpers (chunk-based for very large datasets)
    # ------------------------------------------------------------------
    def process_next_incremental_chunk(self) -> None:
        if not hasattr(self, 'virtual_model') or not self.virtual_model:
            self.incremental_loader_timer.stop()
            return

        has_more = self.virtual_model.load_next_chunk(2000)
        loaded = len(self.virtual_model._flat_items)
        total = len(self.virtual_model._source_flat_items)

        self.overlay.lbl_title.setText(f"Отрисовка списка: {loaded}/{total}...")
        self.overlay.update_total(loaded, total)

        if not has_more or loaded >= total:
            self.incremental_loader_timer.stop()
            self.overlay.hide()
            self.update_view_stats()
            logging.info(f"[PERF] Фоновая догрузка завершена. Всего: {total} элементов.")

    def cancel_incremental_load(self) -> None:
        if hasattr(self, 'incremental_loader_timer'):
            self.incremental_loader_timer.stop()
        self._load_cancelled = True
        self.overlay.hide()
        self.update_view_stats()

    # ------------------------------------------------------------------
    # Smart-select (dropdown autoselect)
    # ------------------------------------------------------------------
    def on_autoselect_changed(self, index: int) -> None:
        if index == 0:
            return
        mode_map = {
            2: 'keep_first',
            3: 'keep_last',
            5: 'keep_shortest',
            6: 'keep_longest',
            8: 'keep_newest',
            9: 'keep_oldest',
            11: 'keep_shallow',
            12: 'keep_deep',
            14: 'protected_dupes',
            15: 'reference_dupes',
        }
        mode = mode_map.get(index)
        if mode:
            self.select_smart(mode)

        self.action_bar.combo_autoselect.blockSignals(True)
        self.action_bar.combo_autoselect.setCurrentIndex(0)
        self.action_bar.combo_autoselect.blockSignals(False)

    def select_smart(self, mode: str) -> None:
        self.overlay.start_loading_mode(0)
        self.overlay.lbl_title.setText("Выделение файлов...")
        QCoreApplication.processEvents()
        QTimer.singleShot(20, lambda: self._select_smart_impl(mode))

    def _select_smart_impl(self, mode: str) -> None:
        self._load_cancelled = False
        self.overlay.btn_stop.hide()
        try:
            if not hasattr(self, 'in_memory_selection'):
                logging.warning("[Selection] in_memory_selection not initialised, skipping.")
                return
            logging.debug(f"[Selection] apply_smart_filter mode={mode}, groups={len(self.in_memory_selection.get_group_files())}")
            self.in_memory_selection.apply_smart_filter(mode)
            marked_count = self.in_memory_selection.get_marked_count()
            logging.info(f"[Selection] after apply_smart_filter: marked={marked_count}")
            self.refresh_selection_from_memory()
        except Exception as e:
            logging.error(f"[Selection] _select_smart_impl error: {e}\n{traceback.format_exc()}")
        finally:
            self.overlay.hide()

    # ------------------------------------------------------------------
    # Select-all / Deselect-all
    # ------------------------------------------------------------------
    def select_all_items(self) -> None:
        self.overlay.start_loading_mode(0)
        self.overlay.lbl_title.setText("Выделение файлов...")
        QCoreApplication.processEvents()
        QTimer.singleShot(20, self._select_all_items_impl)

    def _select_all_items_impl(self) -> None:
        self._load_cancelled = False
        self.overlay.btn_stop.hide()
        try:
            current_mode = getattr(self, 'current_view_mode', 0)
            if current_mode == 0:
                if not hasattr(self, 'in_memory_selection'): return
                self.in_memory_selection.select_all_except_survivor()
                self.refresh_selection_from_memory()
            elif current_mode == 1:
                self.session_db.mark_all_zero_files(1)
                for item in self.virtual_model._all_items:
                    if item['type'] == 'file':
                        item['is_marked'] = 1
                self.virtual_model.beginResetModel()
                self.virtual_model.endResetModel()
                self.update_selection_info()
            elif current_mode == 2:
                self.session_db.mark_all_empty_folders(1)
                for item in self.virtual_model._all_items:
                    if item['type'] == 'empty_folder':
                        item['is_marked'] = 1
                self.virtual_model.beginResetModel()
                self.virtual_model.endResetModel()
                self.update_selection_info()
        except Exception as e:
            logging.error(f"[Selection] _select_all_items_impl error: {e}")
        finally:
            self.overlay.hide()

    def deselect_all(self) -> None:
        self.overlay.start_loading_mode(0)
        self.overlay.lbl_title.setText("Снятие выделения...")
        QCoreApplication.processEvents()
        QTimer.singleShot(20, self._deselect_all_impl)

    def _deselect_all_impl(self) -> None:
        try:
            current_mode = getattr(self, 'current_view_mode', 0)
            if current_mode == 0:
                if not hasattr(self, 'in_memory_selection'): return
                self.in_memory_selection.clear_all()
                self.refresh_selection_from_memory()
            elif current_mode == 1:
                self.session_db.mark_all_zero_files(0)
                for item in self.virtual_model._all_items:
                    if item['type'] == 'file':
                        item['is_marked'] = 0
                self.virtual_model.beginResetModel()
                self.virtual_model.endResetModel()
                self.update_selection_info()
            elif current_mode == 2:
                self.session_db.mark_all_empty_folders(0)
                for item in self.virtual_model._all_items:
                    if item['type'] == 'empty_folder':
                        item['is_marked'] = 0
                self.virtual_model.beginResetModel()
                self.virtual_model.endResetModel()
                self.update_selection_info()
        except Exception as e:
            logging.error(f"[Selection] _deselect_all_impl error: {e}")
        finally:
            self.overlay.hide()

    # ------------------------------------------------------------------
    # Group header context menu actions
    # ------------------------------------------------------------------
    def _header_group_action(self, item: dict[str, Any], action: str) -> None:
        """Handle group header context menu actions (per-group, not global)."""
        group_id = item['id']
        current_mode = getattr(self, 'current_view_mode', 0)
        current_tab = getattr(self, 'current_tab', 0)

        # In duplicate mode, 'all' means 'all except one survivor' to enforce iron rule
        if current_mode == 0 and current_tab == 0 and action == 'all':
            action = 'all_except_first'

        if not hasattr(self, 'in_memory_selection'):
            return

        try:
            if action == 'all_except_first':
                # Mark all files in this group except the survivor
                self.in_memory_selection.select_group_except_survivor(group_id)
            elif action == 'all':
                # Unrestricted: mark all (only reached in non-duplicate modes)
                files = self.in_memory_selection.get_group_files().get(group_id, [])
                for f in files:
                    self.in_memory_selection.mark_file(f['id'] if isinstance(f, dict) else f, group_id)
            elif action == 'none':
                # Clear marks only for this group
                self.in_memory_selection.deselect_group(group_id)

            self.refresh_selection_from_memory()
        except Exception as e:
            logging.error(f"[Selection] _header_group_action error: {e}")

    # ------------------------------------------------------------------
    # Batch selection by path / source root
    # ------------------------------------------------------------------
    def select_by_same_path(self, reference_path: str) -> None:
        if not reference_path or not os.path.exists(reference_path):
            return
        target_dir = os.path.dirname(reference_path)
        self._batch_select(lambda p: os.path.dirname(p) == target_dir)

    def select_by_source_root(self, reference_path: str) -> None:
        found_root = None
        for src in self.source_folders.keys():
            if is_subpath(reference_path, src):
                found_root = src
                break
        if found_root:
            self._batch_select(lambda p: is_subpath(p, found_root))

    def _batch_select(self, condition_func: Callable[[str], bool]) -> None:
        self.overlay.start_loading_mode(0)
        self.overlay.lbl_title.setText("Выделение файлов...")
        QCoreApplication.processEvents()
        QTimer.singleShot(20, lambda: self._batch_select_impl(condition_func))

    def _batch_select_impl(self, condition_func: Callable[[str], bool]) -> None:
        self._load_cancelled = False
        self.overlay.btn_stop.hide()
        try:
            if not hasattr(self, 'in_memory_selection'):
                return
            logging.debug(f"[Selection] apply_path_filter, groups={len(self.in_memory_selection.get_group_files())}")
            self.in_memory_selection.apply_path_filter(condition_func)
            marked_count = self.in_memory_selection.get_marked_count()
            logging.info(f"[Selection] after apply_path_filter: marked={marked_count}")
            self.refresh_selection_from_memory()
        except Exception as e:
            logging.error(f"[Selection] _batch_select_impl error: {e}\n{traceback.format_exc()}")
        finally:
            self.overlay.hide()

    def deselect_by_source_root(self, reference_path: str) -> None:
        found_root = None
        for src in self.source_folders.keys():
            if is_subpath(reference_path, src):
                found_root = src
                break
        if found_root:
            self._batch_deselect(lambda p: is_subpath(p, found_root))

    def _batch_deselect(self, condition_func: Callable[[str], bool]) -> None:
        self.overlay.start_loading_mode(0)
        self.overlay.lbl_title.setText("Снятие выделения...")
        QCoreApplication.processEvents()
        QTimer.singleShot(20, lambda: self._batch_deselect_impl(condition_func))

    def _batch_deselect_impl(self, condition_func: Callable[[str], bool]) -> None:
        self._load_cancelled = False
        self.overlay.btn_stop.hide()
        try:
            if not hasattr(self, 'in_memory_selection'):
                return
            self.in_memory_selection.remove_path_filter(condition_func)
            self.refresh_selection_from_memory()
        except Exception as e:
            logging.error(f"[Selection] _batch_deselect_impl error: {e}\n{traceback.format_exc()}")
        finally:
            self.overlay.hide()

    # ------------------------------------------------------------------
    # Single-file checkbox toggle (called from ui_main._on_tree_checkbox_clicked)
    # ------------------------------------------------------------------
    def toggle_single_file_mark(self, item: dict[str, Any], new_state: bool) -> None:
        """Toggle a single file's mark state according to iron rules.

        This is the sole authorised entry point for manual checkbox interaction.
        Returns the final state applied (may differ from new_state if rule blocked it).
        """
        if not hasattr(self, 'in_memory_selection'):
            logging.warning("[IRON] toggle_single_file_mark called but in_memory_selection missing!")
            return

        file_id = item['id']
        group_id = item.get('group_id')
        logging.debug(f"[IRON] toggle_single_file_mark: file_id={file_id} group_id={group_id} new_state={new_state}")

        if new_state:
            success = self.in_memory_selection.mark_file(file_id, group_id)
            if not success:
                logging.debug(f"[IRON] Blocked marking file_id={file_id} in group={group_id}")
                return
        else:
            self.in_memory_selection.unmark_file(file_id)

        # Directly update the original item dict in _all_items
        for orig_item in self.virtual_model._all_items:
            if orig_item['type'] == 'file' and orig_item['id'] == file_id:
                orig_item['is_marked'] = 1 if new_state else 0
                break
                
        self.update_selection_info()

        # Use dataChanged for a precise repaint of one row (no full model reset)
        try:
            for row, flat_item in enumerate(self.virtual_model._flat_items):
                if flat_item['type'] == 'file' and flat_item['id'] == file_id:
                    idx = self.virtual_model.index(row)
                    # Empty roles list = all roles changed → guarantees repaint
                    self.virtual_model.dataChanged.emit(idx, idx, [])
                    return
            # Item not found in flat_items (group collapsed?) — full refresh
            self.virtual_model.layoutChanged.emit()
        except Exception as e:
            logging.error(f"[IRON] dataChanged emit error: {e}")
            self.virtual_model.layoutChanged.emit()

    # ------------------------------------------------------------------
    # UI refresh
    # ------------------------------------------------------------------
    def refresh_selection_from_memory(self) -> None:
        if not hasattr(self, 'in_memory_selection'):
            return

        marked_ids = self.in_memory_selection.get_marked()
        logging.debug(f"[IRON] refresh_selection_from_memory: marked_ids={marked_ids}")
        for item in self.virtual_model._all_items:
            if item['type'] == 'file':
                item['is_marked'] = 1 if item['id'] in marked_ids else 0
        self.virtual_model.layoutChanged.emit()
        self.update_selection_info_stats_only()

    def update_selection_info_stats_only(self) -> None:
        if hasattr(self, 'update_ui_text'):
            self.update_ui_text()

    # ------------------------------------------------------------------
    # Live folder status update (no rescan needed)
    # ------------------------------------------------------------------
    def apply_folder_status_change(self, folder_path: str) -> None:
        """
        Применяет новый статус папки (защита/эталон) к уже загруженным файлам в модели без повторного сканирования.

        Алгоритм:
        1. Получаем актуальный статус папки из source_folders.
        2. Проходим по всем файлам в virtual_model — обновляем is_protected/is_reference.
        3. Обновляем _protected_files в InMemorySelection.
        4. Снимаем галки с файлов, которые стали защищёнными.
        5. Перерисовываем UI.

        Правило (железное): если пользователь снимает статус защищённой/эталонной — файлы
        остаются не помеченными. Пользователь должен снова применить фильтр для их выделения.
        """
        if not hasattr(self, 'in_memory_selection') or not hasattr(self, 'virtual_model'):
            return
        if self.current_view_mode != 0:
            return

        folder_data = self.source_folders.get(folder_path)
        if not folder_data:
            return

        new_protected = folder_data.get('protected', False)
        new_reference = folder_data.get('reference', False)
        # Файл защищён, если папка защищена ИЛИ является эталоном
        is_now_protected = new_protected or new_reference

        ids_now_protected: set[int] = set()

        for item in self.virtual_model._all_items:
            if item['type'] != 'file':
                continue
            if not is_subpath(item['path'], folder_path):
                continue

            fid = item['id']
            item['is_protected'] = is_now_protected
            item['is_reference'] = new_reference

            if is_now_protected:
                ids_now_protected.add(fid)

        # — Синхронизируем _protected_files в InMemorySelection:
        #   Добавляем или убиၲем файлы из защищённого множества
        #   и снимаем галки с файлов, которые теперь защищены.
        sel = self.in_memory_selection
        if is_now_protected:
            # Выставляем защиту
            for fid in ids_now_protected:
                sel._protected_files.add(fid)
                # Галка с защищённого снимается автоматически — он не может быть помечен
                sel.unmark_file(fid)
        else:
            # Снимаем защиту со всех файлов этой папки
            for item in self.virtual_model._all_items:
                if item['type'] != 'file':
                    continue
                if not is_subpath(item['path'], folder_path):
                    continue
                sel._protected_files.discard(item['id'])

        # — Обновляем флаг is_marked во всех элементах модели по текущему состоянию InMemorySelection
        marked_ids = sel.get_marked()
        for item in self.virtual_model._all_items:
            if item['type'] == 'file':
                item['is_marked'] = 1 if item['id'] in marked_ids else 0

        # — Сортируем файлы внутри групп на лету: эталонные и защищенные переносим наверх
        def get_file_sort_key(f: dict[str, Any]) -> tuple[int, str]:
            if f.get('is_reference', False):
                weight = 0
            elif f.get('is_protected', False):
                weight = 1
            else:
                weight = 2
            return (weight, f.get('path', ''))

        # Группируем элементы _all_items, сохраняя текущий порядок групп
        groups_dict: dict[Any, dict[str, Any]] = {}
        groups_order: list[Any] = []
        curr_group = None
        for item in self.virtual_model._all_items:
            if item['type'] == 'group':
                curr_group = item
                groups_order.append(item['id'])
                groups_dict[item['id']] = {'group': item, 'files': []}
            elif item['type'] == 'file':
                if curr_group:
                    groups_dict[curr_group['id']]['files'].append(item)

        new_all_items: list[dict[str, Any]] = []
        for gid in groups_order:
            group_data = groups_dict[gid]
            group_data['files'].sort(key=get_file_sort_key)
            new_all_items.append(group_data['group'])
            new_all_items.extend(group_data['files'])

        # Сортируем файлы в кэше модели
        for gid in self.virtual_model._group_files_cache:
            self.virtual_model._group_files_cache[gid].sort(key=get_file_sort_key)

        self.virtual_model.beginResetModel()
        self.virtual_model._all_items = new_all_items
        self.virtual_model.rebuild_flat_items()
        self.virtual_model._flat_items = list(self.virtual_model._source_flat_items)
        self.virtual_model.endResetModel()
        self.update_selection_info()
        logging.info(
            f"[Status] apply_folder_status_change: path={folder_path!r} "
            f"protected={new_protected} reference={new_reference} "
            f"affected_files={len(ids_now_protected) if is_now_protected else '(status removed)'}"
        )
