import os
import subprocess
import logging
from typing import Any
from PyQt6.QtWidgets import QMenu
from PyQt6.QtCore import Qt, QUrl, QPoint, QModelIndex
from PyQt6.QtGui import QDesktopServices, QAction

from config import AppContext
from utils_common import format_size, is_subpath

class CleanerTreeMixin:
    def is_path_protected(self, path: str) -> bool:
        if not hasattr(self, 'source_folders'): return False
        for src_path, data in self.source_folders.items():
            if is_subpath(path, src_path):
                return data['protected']
        return False

    def is_path_reference(self, path: str) -> bool:
        if not hasattr(self, 'source_folders'): return False
        for src_path, data in self.source_folders.items():
            if is_subpath(path, src_path):
                return data.get('reference', False)
        return False

    def get_source_color(self, path: str) -> str:
        if not hasattr(self, 'source_folders'): return "#555"
        for src_path, data in self.source_folders.items():
            if is_subpath(path, src_path):
                return data['color']
        return "#555"

    def toggle_tree(self, expand: bool) -> None:
        if hasattr(self, 'virtual_model'):
            if expand:
                self.virtual_model.expand_all()
            else:
                self.virtual_model.collapse_all()

    def sort_tree_by_selection(self) -> None:
        if getattr(self, 'current_view_mode', 0) != 0 or not hasattr(self, 'virtual_model'): return
        self.tree.setUpdatesEnabled(False)
        
        # 1. Group items in memory
        groups_dict: dict[Any, dict[str, Any]] = {}
        curr_group = None
        for item in self.virtual_model._all_items:
            if item['type'] == 'group':
                curr_group = item
                groups_dict[item['id']] = {'group': item, 'files': []}
            elif item['type'] == 'file':
                if curr_group:
                    groups_dict[curr_group['id']]['files'].append(item)
                    
        # Вспомогательная функция вычисления веса категории готовности группы:
        # Красные (частично отмеченные, эффективных > 1 и отмеченных > 0) -> вес 0
        # Серые (неотмеченные вообще, отмеченных == 0) -> вес 1
        # Зеленые (все дубли отмечены, эффективных <= 1 и отмеченных > 0) -> вес 2
        def get_group_category_weight(gid: Any) -> int:
            marked_files, effective_unmarked, total_files = self.virtual_model.calculate_group_status(gid)
            if marked_files == 0:
                return 1 # Серые
            elif effective_unmarked == 1:
                return 2 # Зеленые
            else:
                return 0 # Красные

        # Функция сортировки файлов внутри группы: эталонные (0) -> защищенные (1) -> обычные (2)
        def get_file_sort_key(f: dict[str, Any]) -> tuple[int, str]:
            if f.get('is_reference', False):
                weight = 0
            elif f.get('is_protected', False):
                weight = 1
            else:
                weight = 2
            return (weight, f.get('path', ''))
                    
        # 2. Сортируем группы: сначала по весу категории, затем по wasted_size по убыванию
        sorted_keys = sorted(
            groups_dict.keys(),
            key=lambda gid: (
                get_group_category_weight(gid),
                -groups_dict[gid]['group'].get('wasted_size', 0)
            )
        )
        
        # 3. Сортируем файлы внутри кэша и групп, затем пересобираем _all_items
        new_all_items: list[dict[str, Any]] = []
        for gid in sorted_keys:
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
        self.virtual_model._flat_items = list(self.virtual_model._source_flat_items) # Принудительно обновляем отображаемый список
        self.virtual_model.endResetModel()
        self.tree.setUpdatesEnabled(True)

    def on_tree_context_menu(self, pos: QPoint) -> None:
        index: QModelIndex = self.tree.indexAt(pos)
        if not index.isValid(): return
        item = index.data(Qt.ItemDataRole.UserRole)
        if not item: return
        
        if item['type'] == 'group': 
            self.on_group_header_context_menu(self.tree.mapToGlobal(pos), index)
            return 
            
        path: str = item.get('path', '')
        is_empty_mode = getattr(self, 'current_view_mode', 0) == 2
        
        menu = QMenu(self.tree)
        menu.setStyleSheet("QMenu { background-color: #2b2b2b; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #3b82f6; } QMenu::separator { height: 1px; background: #666; margin: 4px 8px; }")
        
        if getattr(self, 'current_tab', 0) == 1:
            group_item = {'id': item['group_id']}
            act_sel_all = QAction("Выделить всё в этой группе" if AppContext.LANG == "RU" else "Select all in this group", self)
            act_sel_all.triggered.connect(lambda checked, gi=group_item: self._header_group_action(gi, 'all'))
            menu.addAction(act_sel_all)
            
            act_desel_all = QAction("Снять выделение в этой группе" if AppContext.LANG == "RU" else "Deselect all in this group", self)
            act_desel_all.triggered.connect(lambda checked, gi=group_item: self._header_group_action(gi, 'none'))
            menu.addAction(act_desel_all)
            menu.addSeparator()
        
        is_dump = path.startswith('[Дамп]')
        
        if not is_empty_mode and not is_dump:
            act_open = QAction(AppContext.tr("anl_ctx_file_open"), self)
            act_open.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
            menu.addAction(act_open)
        
        reveal_text = AppContext.tr("cln_ctx_show_folder")
        act_reveal = QAction(reveal_text, self)
        from utils_common import reveal_in_explorer
        act_reveal.triggered.connect(lambda: reveal_in_explorer(path))
        if is_dump:
            act_reveal.setEnabled(False)
        menu.addAction(act_reveal)
        
        
        if not is_empty_mode:
            act_rename = QAction(AppContext.tr("menu_rename"), self)
            act_rename.triggered.connect(lambda: self.rename_file_in_tree(index))
            menu.addAction(act_rename)
            
            menu.addSeparator()
            act_move_to = QAction("Переместить в..." if AppContext.LANG == "RU" else "Move to...", self)
            
            if getattr(self, 'current_view_mode', 0) == 0 and hasattr(self, 'in_memory_selection'):
                has_sel = self.in_memory_selection.get_marked_count() > 0
            else:
                has_sel = self.session_db.get_global_selection_stats()['count'] > 0
                
            act_move_to.setEnabled(has_sel)
            act_move_to.triggered.connect(self.prompt_move_selected)
            menu.addAction(act_move_to)
            
        if getattr(self, 'current_view_mode', 0) == 0:
            menu.addSeparator()
            act_select_path = QAction(AppContext.tr("cln_ctx_select_same_path"), self)
            act_select_path.triggered.connect(lambda: self.select_by_same_path(path))
            menu.addAction(act_select_path)
            if hasattr(self, 'source_folders') and len(self.source_folders) > 1:
                act_select_source = QAction(AppContext.tr("cln_ctx_select_all_from_source"), self)
                act_select_source.triggered.connect(lambda: self.select_by_source_root(path))
                menu.addAction(act_select_source)

            # Context actions for protected and reference files
            is_protected_file = item.get('is_protected', False)
            is_reference_file = item.get('is_reference', False)

            if is_protected_file and not is_reference_file:
                menu.addSeparator()
                if is_dump:
                    act_sel_dump = QAction("Выбрать все копии файлов из этого дампа", self)
                    act_sel_dump.triggered.connect(lambda: getattr(self, 'select_copies_from_dump', lambda p: None)(path))
                    menu.addAction(act_sel_dump)
                act_sel_prot_dupes = QAction(AppContext.tr("cln_ctx_select_protected_dupes"), self)
                act_sel_prot_dupes.triggered.connect(lambda: self.select_smart('protected_dupes'))
                menu.addAction(act_sel_prot_dupes)

            if is_reference_file:
                menu.addSeparator()
                act_sel_ref_dupes = QAction(AppContext.tr("cln_ctx_select_reference_dupes"), self)
                act_sel_ref_dupes.triggered.connect(lambda: self.select_smart('reference_dupes'))
                menu.addAction(act_sel_ref_dupes)
            
            menu.addSeparator()
            act_keep_this = QAction(AppContext.tr("cln_ctx_keep_only_this"), self)
            act_keep_this.triggered.connect(lambda: self.keep_only_this_file(index))
            menu.addAction(act_keep_this)

        menu.addSeparator()
        act_delete = QAction(AppContext.tr("cln_ctx_delete_files"), self)
        
        if getattr(self, 'current_view_mode', 0) == 0 and hasattr(self, 'in_memory_selection'):
            has_sel = self.in_memory_selection.get_marked_count() > 0
        else:
            has_sel = self.session_db.get_global_selection_stats()['count'] > 0
            
        act_delete.setEnabled(has_sel)
        act_delete.triggered.connect(self.delete_selected)
        menu.addAction(act_delete)

        menu.exec(self.tree.mapToGlobal(pos))

    def reveal_file_in_explorer(self, path: str) -> None:
        if path and os.path.exists(path):
            from utils_common import reveal_in_explorer
            reveal_in_explorer(path)
    def on_group_header_context_menu(self, pos: QPoint, index: QModelIndex) -> None:
        item = index.data(Qt.ItemDataRole.UserRole)
        if not item: return
        
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #2b2b2b; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #3b82f6; }")
        
        current_mode = getattr(self, 'current_view_mode', 0)
        current_tab = getattr(self, 'current_tab', 0)
        
        if current_mode == 0:
            if current_tab == 0:
                act_sel_smart = QAction(AppContext.tr("cln_ctx_select_all_except_first"), self)
                act_sel_smart.triggered.connect(lambda: self._header_group_action(item, 'all_except_first'))
                menu.addAction(act_sel_smart)
            else:
                act_sel_all = QAction("Выделить всё в этой группе" if AppContext.LANG == "RU" else "Select all in this group", self)
                act_sel_all.triggered.connect(lambda: self._header_group_action(item, 'all'))
                menu.addAction(act_sel_all)
        else:
            act_sel_all = QAction(AppContext.tr("cln_ctx_select_all"), self)
            act_sel_all.triggered.connect(lambda: self._header_group_action(item, 'all'))
            menu.addAction(act_sel_all)
            
        act_desel = QAction("Снять выделение со всех в группе" if AppContext.LANG == "RU" and current_tab == 1 else AppContext.tr("cln_ctx_deselect_all"), self)
        act_desel.triggered.connect(lambda: self._header_group_action(item, 'none'))
        menu.addAction(act_desel)
        menu.addSeparator()

        act_expand = QAction(AppContext.tr("cln_ctx_expand"), self)
        act_expand.triggered.connect(lambda: self.toggle_tree(True))
        menu.addAction(act_expand)
        act_collapse = QAction(AppContext.tr("cln_ctx_collapse"), self)
        act_collapse.triggered.connect(lambda: self.toggle_tree(False))
        menu.addAction(act_collapse)
        
        menu.exec(pos)

    def keep_only_this_file(self, index: QModelIndex) -> None:
        item = index.data(Qt.ItemDataRole.UserRole)
        if not item or item['type'] != 'file':
            return

        group_id = item['group_id']
        target_path = item['path']
        self.tree.setUpdatesEnabled(False)

        try:
            if hasattr(self, 'in_memory_selection'):
                # RAM path: clear group marks, then mark all except this file
                self.in_memory_selection.deselect_group(group_id)
                files = self.virtual_model._group_files_cache.get(group_id, [])
                for f in files:
                    if f['path'] != target_path and not f.get('is_protected', False):
                        self.in_memory_selection.mark_file(f['id'], group_id)

                # Update _all_items is_marked flags
                marked_ids = self.in_memory_selection.get_marked()
                for f in self.virtual_model._all_items:
                    if f['type'] == 'file':
                        f['is_marked'] = 1 if f['id'] in marked_ids else 0
            else:
                # Fallback: legacy DB path
                self.session_db.set_group_marked_state_safe(group_id, 'none')
                self.session_db.set_group_marked_state_safe(group_id, 'all_except_first', target_path)
                for f in self.virtual_model._all_items:
                    if f['type'] == 'file' and f['group_id'] == group_id:
                        f['is_marked'] = 0 if f['path'] == target_path else (1 if not f.get('is_protected', False) else 0)

            self.virtual_model.layoutChanged.emit()
        except Exception as e:
            logging.error(f"Failed in keep_only_this_file: {e}")
        finally:
            self.tree.setUpdatesEnabled(True)
            self.update_selection_info()

    def update_selection_info(self) -> None:
        self.lbl_selection_info.setStyleSheet("color: #93c5fd; font-size: 11px; font-weight: bold;")

        if hasattr(self, 'in_memory_selection') and getattr(self, 'current_view_mode', 0) == 0:
            marked_files = [
                item for item in self.virtual_model._all_items
                if item['type'] == 'file' and item.get('is_marked', 0)
            ]
            marked_files_count = len(marked_files)
            marked_groups_count = len(set(f['group_id'] for f in marked_files if 'group_id' in f))
            total_size = sum(f.get('size', 0) for f in marked_files)
            size_str = format_size(total_size)
            
            # Выбрано: 3 (14 файлов) • 240.4 MB
            self.lbl_selection_info.setText(f"Выбрано: {marked_groups_count} ({marked_files_count} файлов) • {size_str}")
            self.lbl_selection_info.setToolTip(f"Выделено:\nГрупп: {marked_groups_count}\nФайлов: {marked_files_count}\nРазмер: {size_str}")
            count = marked_files_count
        else:
            stats = self.session_db.get_global_selection_stats()
            count = stats['count']
            total_size = stats['size']
            size_str = format_size(total_size)
            if getattr(self, 'current_view_mode', 0) == 1:
                self.lbl_selection_info.setText(f"Выбрано: {count} файлов • {size_str}")
                self.lbl_selection_info.setToolTip(f"Выбрано файлов: {count}\nРазмер: {size_str}")
            else:
                self.lbl_selection_info.setText(f"Выбрано: {count} папок")
                self.lbl_selection_info.setToolTip(f"Выбрано пустых папок: {count}")

        self.validate_move_state(selected_count_cache=count)
