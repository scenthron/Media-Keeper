import os
import logging
from typing import Any
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QMenu, QDialog
from PyQt6.QtGui import QAction, QDesktopServices
from PyQt6.QtCore import QUrl, Qt, QModelIndex, QPoint, QCoreApplication

from config import AppContext
from .ui_widgets import SourceListItem, generate_vibrant_color
from .ui_dialogs import CleanerResultDialog
from .workers_move import SessionMoveWorker, SessionDeleteWorker
from ui_dialogs_generic import SmartNameDialog, FileDeletionConfirmDialog

class ActionMixin:
    def add_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, AppContext.tr("dlg_select_folder"), "")
        if path:
            self.add_folder_path(path)

    def add_folder_path(self, path: str) -> None:
        path = os.path.normpath(path)
        if path in self.source_folders: return
        
        # --- SYSTEM PROTECTION BLOCK ---
        sys_drive = os.getenv("SystemDrive", "C:") + os.sep
        win_dir = os.environ.get("SystemRoot", "C:\\Windows")
        prog_files = os.environ.get("ProgramFiles", "C:\\Program Files")
        prog_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
        
        forbidden = [win_dir, prog_files, prog_x86]
        norm_input = path.lower()
        is_system = False
        
        for f in forbidden:
            if f and norm_input.startswith(os.path.normpath(f).lower()):
                is_system = True
                break
        
        if not is_system and norm_input == os.path.normpath(sys_drive).lower():
             is_system = True
        # -------------------------------
        
        idx = len(self.source_folders)
        color = generate_vibrant_color(idx)
        is_cached = self.db_helper.check_path_scanned(path)
        
        self.source_folders[path] = {'color': color, 'protected': False, 'is_system': is_system, 'reference': False}
        
        item_widget = SourceListItem(path, color, is_cached=is_cached)
        if is_system:
            item_widget.set_system_error_state()
            
        item_widget.removed.connect(self.remove_folder)
        item_widget.context_menu_requested.connect(self.show_source_menu)
        
        self.settings_panel.folder_list_layout.addWidget(item_widget)
        self.settings_panel.refresh_list_alignment()
        self.revalidate_sources()

    def remove_folder(self, path: str) -> None:
        if path in self.source_folders:
            del self.source_folders[path]
        layout = self.settings_panel.folder_list_layout
        for i in range(layout.count()):
            item = layout.itemAt(i)
            widget = item.widget()
            if widget and isinstance(widget, SourceListItem) and widget.path == path:
                widget.deleteLater()
                break
        self.revalidate_sources()

    def clear_folders(self) -> None:
        self.source_folders.clear()
        layout = self.settings_panel.folder_list_layout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.revalidate_sources()

    def revalidate_sources(self) -> None:
        has_error = False
        paths = list(self.source_folders.keys())
        layout = self.settings_panel.folder_list_layout
        
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if not getattr(w, 'is_system_error', False):
                    w.clear_error_state()

        for i, p1 in enumerate(paths):
            for j, p2 in enumerate(paths):
                if i == j: continue
                try:
                    if os.path.commonpath([p1, p2]) == os.path.normpath(p2):
                        has_error = True
                        for k in range(layout.count()):
                            w = layout.itemAt(k).widget()
                            if w and w.path == p1:
                                if not getattr(w, 'is_system_error', False):
                                    w.set_error_state(AppContext.tr("cln_err_nested").format(p2))
                except ValueError: pass

        has_system_error = any(data.get('is_system', False) for data in self.source_folders.values())
        is_ok = bool(self.source_folders) and not has_error and not has_system_error
        self.settings_panel.set_scan_enabled(is_ok)
        self.settings_panel.btn_filter.setEnabled(is_ok)
        if hasattr(self, 'reset_scan_button'):
            self.reset_scan_button()

    def show_source_menu(self, pos: QPoint, path: str) -> None:
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        menu.setStyleSheet("QMenu { background-color: #2b2b2b; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #3b82f6; } QMenu::item:disabled { color: #666; } QMenu::separator { height: 1px; background: #666; margin: 4px 8px; }")

        is_prot = self.source_folders[path]['protected']
        is_ref = self.source_folders[path].get('reference', False)
        is_system = self.source_folders[path].get('is_system', False)

        if getattr(self, 'current_tab', 0) == 1:
            act_sel_cat = QAction("Выбрать все файлы в категории" if AppContext.LANG == "RU" else "Select all files in category", self)
            act_sel_cat.triggered.connect(lambda: self.select_by_source_root(path))
            act_sel_cat.setEnabled(not is_prot and not is_system)
            menu.addAction(act_sel_cat)
            
            act_desel_cat = QAction("Снять выделение в категории" if AppContext.LANG == "RU" else "Deselect files in category", self)
            act_desel_cat.triggered.connect(lambda: self.deselect_by_source_root(path))
            menu.addAction(act_desel_cat)
            
            menu.addSeparator()

        # 1. Открыть в проводнике
        act_open = QAction(AppContext.tr("menu_open_explorer"), self)
        act_open.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
        menu.addAction(act_open)

        menu.addSeparator()

        # 2. Защитить группу
        act_prot = QAction(AppContext.tr("cln_ctx_unprotect") if is_prot else AppContext.tr("cln_ctx_protect"), self)
        act_prot.triggered.connect(lambda: self.toggle_source_protection(path))
        act_prot.setEnabled(not is_ref and not is_system)
        
        if AppContext.LANG == "RU":
            prot_tip = "<b>Защитить группу</b><br>Файлы из этой папки никогда не будут автоматически отмечаться галочками для удаления во всех группах дубликатов. Это гарантирует защиту важных оригиналов от случайной очистки."
        else:
            prot_tip = "<b>Protect Group</b><br>Files from this folder will never be automatically selected for deletion in duplicate groups. This guarantees that important originals remain safe."
        act_prot.setToolTip(prot_tip)
        menu.addAction(act_prot)

        # 3. Поиск по эталону
        if getattr(self, 'current_tab', 0) == 0:
            act_ref = QAction(AppContext.tr("cln_ctx_unset_reference") if is_ref else AppContext.tr("cln_ctx_set_reference"), self)
            act_ref.triggered.connect(lambda: self.toggle_source_reference(path))
            act_ref.setEnabled(not (is_prot and not is_ref) and not is_system)
            
            if AppContext.LANG == "RU":
                ref_tip = "<b>Поиск по эталону</b><br>Назначает папку образцовой (эталоном). Все её файлы защищаются от удаления, позволяя вам безопасно очищать дубликаты в других папках при помощи фильтров авто-выбора."
            else:
                ref_tip = "<b>Search by Reference</b><br>Designates this folder as reference/sample. All files here are protected, allowing you to safely clean duplicate copies in other folders using auto-selection filters."
            act_ref.setToolTip(ref_tip)
            menu.addAction(act_ref)

        menu.addSeparator()

        # 4. Удалить из списка
        act_rem = QAction(AppContext.tr("cln_ctx_remove_from_list"), self)
        act_rem.triggered.connect(lambda: self.remove_folder(path))
        menu.addAction(act_rem)

        menu.exec(pos)

    def toggle_source_protection(self, path: str) -> None:
        if path not in self.source_folders: return
        # Защита и эталон взаимоисключающие: нельзя защитить папку-эталон
        if self.source_folders[path].get('reference', False): return
        new_state = not self.source_folders[path]['protected']
        self.source_folders[path]['protected'] = new_state
        layout = self.settings_panel.folder_list_layout
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if w and w.path == path:
                w.set_protected_state(new_state)
                break
        # Применяем новый статус к уже загруженным файлам в таблице
        if hasattr(self, 'apply_folder_status_change'):
            self.apply_folder_status_change(path)

    def toggle_source_reference(self, path: str) -> None:
        if path not in self.source_folders: return
        # Защита и эталон взаимоисключающие: нельзя сделать эталоном защищённую папку
        if not self.source_folders[path].get('reference', False) and self.source_folders[path].get('protected', False):
            return
        was_reference = self.source_folders[path].get('reference', False)

        # Снимаем предыдущий эталон (только один эталон в сессии)
        layout = self.settings_panel.folder_list_layout
        prev_ref_path: str | None = None
        for p, data in self.source_folders.items():
            if data.get('reference') and p != path:
                prev_ref_path = p
                data['reference'] = False
                data['protected'] = False  # Эталон снят — убираем автоматически выставленную защиту
                for i in range(layout.count()):
                    w = layout.itemAt(i).widget()
                    if w and w.path == p:
                        w.set_reference_state(False)
                        break

        new_state = not was_reference
        self.source_folders[path]['reference'] = new_state
        # При включении эталона: protection автоматически выставляется в True
        # При снятии эталона: protection сбрасывается в False
        if new_state:
            self.source_folders[path]['protected'] = True
        else:
            self.source_folders[path]['protected'] = False

        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if w and w.path == path:
                w.set_reference_state(new_state)
                break

        self.revalidate_sources()

        # При изменении статуса эталона результаты дубликатов становятся недействительными.
        # Вместо изменения in-memory модели мы запрашиваем новое сканирование и подсвечиваем кнопку.
        if hasattr(self, 'virtual_model') and len(self.virtual_model._all_items) > 0:
            self.settings_panel.scan_stale = True
            self.settings_panel.validate_size_inputs()
            self.update_ui_text()

    def browse_dest(self) -> None:
        path = QFileDialog.getExistingDirectory(self, AppContext.tr("cln_ph_dest"), "")
        if path:
            self.action_bar.drop_zone.set_path(path)

    def validate_move_state(self, selected_count_cache: int | None = None) -> None:
        if isinstance(selected_count_cache, str): selected_count_cache = None

        if selected_count_cache is not None:
            has_selection = (selected_count_cache > 0)
        elif hasattr(self, 'in_memory_selection') and self.current_view_mode == 0:
            has_selection = self.in_memory_selection.get_marked_count() > 0
        else:
            has_selection = self.session_db.get_global_selection_stats()['count'] > 0

        self.action_bar.set_delete_button_enabled(has_selection)
        self.action_bar.set_deselect_button_enabled(has_selection)

        if self.current_view_mode == 2:
            self.action_bar.set_move_button_enabled(has_selection, AppContext.tr("cln_act_delete_folders"))
            return

        dest_path = self.action_bar.drop_zone.get_path().strip()
        has_path = bool(dest_path and os.path.exists(dest_path))

        self.action_bar.set_move_button_enabled(has_path and has_selection)
        self.action_bar.btn_move_to.setEnabled(has_selection)

    def prompt_move_selected(self) -> None:
        if self.current_view_mode == 2: return
        title = "Переместить в..." if AppContext.LANG == "RU" else "Move to..."
        start = getattr(self, 'last_moved_dir', getattr(AppContext, 'last_moved_dir', ""))
        if not start:
            start = self.action_bar.drop_zone.get_path() if self.action_bar.drop_zone.get_path() else ""
        if not start:
            start = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            
        d = QFileDialog.getExistingDirectory(self, title, start)
        if d:
            AppContext.last_moved_dir = d
            self.last_moved_dir = d
            # НЕ перезаписываем путь быстрого перемещения в интерфейсе
            self.move_selected(dest_folder=d)

    def move_single_file_to_dir_from_context(self, path: str, group_index: int = -1) -> None:
        if self.current_view_mode == 2: return
        title = "Переместить в..." if AppContext.LANG == "RU" else "Move to..."
        start = getattr(self, 'last_moved_dir', getattr(AppContext, 'last_moved_dir', ""))
        if not start:
            start = self.action_bar.drop_zone.get_path() if self.action_bar.drop_zone.get_path() else ""
        if not start:
            start = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            
        d = QFileDialog.getExistingDirectory(self, title, start)
        if d:
            AppContext.last_moved_dir = d
            self.last_moved_dir = d
            # НЕ перезаписываем путь быстрого перемещения в интерфейсе
            
            items_to_process = [{'src': path, 'group_index': group_index}]
            self.preview_widget.show_empty("Moving...")
            QCoreApplication.processEvents()

            self.overlay.start_process(1)
            rename_idx = self.action_bar.combo_collision.currentIndex()
            preserve_struct = self.action_bar.chk_preserve.isChecked()
            self.move_timer.start()

            self.mover = SessionMoveWorker(items_to_process, d, rename_idx, preserve_struct)
            self.mover.progress_total.connect(self.overlay.update_total)
            self.mover.file_started.connect(self.overlay.start_file)
            self.mover.file_progress.connect(self.overlay.update_file_progress)
            self.mover.finished.connect(self.on_move_finished)
            
            try:
                self.overlay.cancel_requested.disconnect()
            except Exception:
                pass
            self.overlay.cancel_requested.connect(self.on_overlay_cancel)
            
            self.mover.start()

    def move_selected(self, dest_folder: str = None) -> None:
        if self.current_view_mode == 2:
            self.delete_empty_folders()
            return

        dest_root = dest_folder if dest_folder else self.action_bar.drop_zone.get_path()
        if not dest_root or not os.path.exists(dest_root):
            QMessageBox.warning(self, AppContext.tr("err_title"), AppContext.tr("msg_trash_not_set"))
            return

        self.preview_widget.show_empty("Moving...")
        QCoreApplication.processEvents()

        items_to_process: list[dict[str, Any]] = []

        if hasattr(self, 'current_tab') and self.current_tab() == 2:
            files = self.page_ai.get_selected_files_paths()
            for idx, p in enumerate(files):
                items_to_process.append({
                    'src': p,
                    'group_index': -1
                })
        elif self.current_view_mode == 0:
            # Get marked items directly from RAM (no DB query needed)
            if hasattr(self, 'in_memory_selection'):
                raw_items = self.in_memory_selection.get_marked_items()
                # Build the format expected by SessionMoveWorker
                for idx, f in enumerate(raw_items):
                    items_to_process.append({
                        'src': f['path'],
                        'group_index': f.get('group_id', -1),
                    })
            else:
                items_to_process = self.session_db.get_global_marked_files()
        elif self.current_view_mode == 1:
            items_to_process = self.session_db.get_global_marked_zero_files()

        if not items_to_process:
            return

        self.overlay.start_process(len(items_to_process))
        rename_idx = self.action_bar.combo_collision.currentIndex()
        preserve_struct = self.action_bar.chk_preserve.isChecked()
        self.move_timer.start()

        self.mover = SessionMoveWorker(items_to_process, dest_root, rename_idx, preserve_struct)
        self.mover.progress_total.connect(self.overlay.update_total)
        self.mover.file_started.connect(self.overlay.start_file)
        self.mover.file_progress.connect(self.overlay.update_file_progress)
        self.mover.finished.connect(self.on_move_finished)
        
        try:
            self.overlay.cancel_requested.disconnect()
        except Exception:
            pass
        self.overlay.cancel_requested.connect(self.on_overlay_cancel)
        
        self.mover.start()

    def delete_selected(self) -> None:
        if self.current_view_mode == 2:
            self.delete_empty_folders()
            return

        file_paths: list[str] = []

        if hasattr(self, 'current_tab') and self.current_tab() == 2:
            file_paths = self.page_ai.get_selected_files_paths()
        elif self.current_view_mode == 0:
            if hasattr(self, 'in_memory_selection'):
                raw_items = self.in_memory_selection.get_marked_items()
                file_paths = [f['path'] for f in raw_items]
            else:
                raw_items = self.session_db.get_global_marked_files()
                file_paths = [f['src'] for f in raw_items]
        elif self.current_view_mode == 1:
            raw_items = self.session_db.get_global_marked_zero_files()
            file_paths = [f['src'] for f in raw_items]

        if not file_paths:
            return

        confirm_dlg = FileDeletionConfirmDialog(file_paths, self)
        if confirm_dlg.exec() != QDialog.DialogCode.Accepted:
            return

        self.preview_widget.show_empty("Deleting...")
        QCoreApplication.processEvents()

        self.overlay.start_process(len(file_paths), "cln_ovl_deleting")
        self.move_timer.start()

        self.deleter = SessionDeleteWorker(file_paths, is_folders=False, use_trash=True)
        self.deleter.progress_total.connect(self.overlay.update_total)
        self.deleter.file_started.connect(self.overlay.start_file)
        self.deleter.finished.connect(self.on_delete_finished)

        try:
            self.overlay.cancel_requested.disconnect()
        except Exception:
            pass
        self.overlay.cancel_requested.connect(self.on_overlay_cancel)

        self.deleter.start()

    def on_delete_finished(self, deleted_paths: list[str], errors: list[tuple[str, str]]) -> None:
        if deleted_paths:
            from logic_cache import DirCache
            for path in deleted_paths:
                DirCache.inst().invalidate_with_parents(os.path.dirname(path))

        if not deleted_paths:
            self.overlay.hide()
            if errors:
                QMessageBox.critical(self, AppContext.tr("err_title"), f"Не удалось удалить файлы:\n{errors[0][1]}")
            return

        self.overlay.start_loading_mode(0)
        self.overlay.lbl_title.setText("Обновление списка...")
        QCoreApplication.processEvents()

        try:
            deleted_set = set(deleted_paths)

            if hasattr(self, 'page_ai') and self.current_tab() == 2:
                self.page_ai.remove_processed_files(deleted_paths)
            elif self.current_view_mode == 0 and hasattr(self, 'in_memory_selection'):
                self.session_db.mark_files_deleted(deleted_paths)
                moved_ids: set[int] = set()
                for files in self.virtual_model._group_files_cache.values():
                    for f in files:
                        if f['path'] in deleted_set:
                            moved_ids.add(f['id'])
                self.in_memory_selection.remove_marked_from_groups(moved_ids)

                self.virtual_model._all_items = [
                    item for item in self.virtual_model._all_items
                    if not (item['type'] == 'file' and item['path'] in deleted_set)
                ]

                groups_to_remove: set = set()
                for gid, files in list(self.virtual_model._group_files_cache.items()):
                    remaining = [f for f in files if f['path'] not in deleted_set]
                    if len(remaining) <= 1:
                        groups_to_remove.add(gid)
                    else:
                        self.virtual_model._group_files_cache[gid] = remaining

                if groups_to_remove:
                    self.virtual_model._all_items = [
                        item for item in self.virtual_model._all_items
                        if not (
                            (item['type'] == 'group' and item['id'] in groups_to_remove) or
                            (item['type'] == 'file' and item.get('group_id') in groups_to_remove)
                        )
                    ]
                    for gid in groups_to_remove:
                        self.virtual_model._group_files_cache.pop(gid, None)

                self.virtual_model.beginResetModel()
                self.virtual_model.rebuild_flat_items()
                self.virtual_model._flat_items = list(self.virtual_model._source_flat_items)
                self.virtual_model.endResetModel()
            else:
                self.session_db.mark_files_deleted(deleted_paths)
                self.cleanup_tree_after_move()
        finally:
            self.overlay.hide()

        self.update_selection_info()
        self.update_view_stats()
        self.update_cache_info()

        elapsed_ms = self.move_timer.elapsed()
        time_str = None
        if elapsed_ms > 1000:
            seconds = (elapsed_ms // 1000) % 60
            minutes = (elapsed_ms // (1000 * 60)) % 60
            time_str = f"{minutes:02}:{seconds:02}"

        dlg = CleanerResultDialog(len(deleted_paths), len(errors), time_str, self, action_type='delete')
        dlg.exec()

    def on_move_finished(self, moved: list[str], errors: list[Any], affected_groups: Any = None) -> None:
        self.overlay.start_loading_mode(0)
        self.overlay.lbl_title.setText("Обновление списка...")
        QCoreApplication.processEvents()

        try:
            moved_set = set(moved)

            if hasattr(self, 'page_ai') and self.current_tab() == 2:
                self.page_ai.remove_processed_files(moved)
            elif self.current_view_mode == 0 and hasattr(self, 'in_memory_selection'):
                self.session_db.mark_files_deleted(moved)
                # Remove moved files from in-memory state
                # Map paths to file_ids using group_files_cache
                moved_ids: set[int] = set()
                for files in self.virtual_model._group_files_cache.values():
                    for f in files:
                        if f['path'] in moved_set:
                            moved_ids.add(f['id'])
                self.in_memory_selection.remove_marked_from_groups(moved_ids)

                # Remove moved items from virtual model
                self.virtual_model._all_items = [
                    item for item in self.virtual_model._all_items
                    if not (item['type'] == 'file' and item['path'] in moved_set)
                ]
                # Remove groups that now have 0 or 1 file remaining
                groups_to_remove: set = set()
                for gid, files in list(self.virtual_model._group_files_cache.items()):
                    remaining = [f for f in files if f['path'] not in moved_set]
                    if len(remaining) <= 1:
                        groups_to_remove.add(gid)
                    else:
                        self.virtual_model._group_files_cache[gid] = remaining

                if groups_to_remove:
                    self.virtual_model._all_items = [
                        item for item in self.virtual_model._all_items
                        if not (
                            (item['type'] == 'group' and item['id'] in groups_to_remove) or
                            (item['type'] == 'file' and item.get('group_id') in groups_to_remove)
                        )
                    ]
                    for gid in groups_to_remove:
                        self.virtual_model._group_files_cache.pop(gid, None)

                # Rebuild flat view
                self.virtual_model.beginResetModel()
                self.virtual_model.rebuild_flat_items()
                self.virtual_model._flat_items = list(self.virtual_model._source_flat_items)
                self.virtual_model.endResetModel()
            else:
                # For zero files or fallback: use DB-based cleanup
                self.session_db.mark_files_deleted(moved)
                self.cleanup_tree_after_move()
        finally:
            self.overlay.hide()

        if moved:
            from logic_cache import DirCache
            for path in moved:
                DirCache.inst().invalidate_with_parents(os.path.dirname(path))
            dest_root = self.action_bar.drop_zone.get_path()
            if dest_root:
                DirCache.inst().invalidate_with_parents(dest_root)
                self.action_bar.drop_zone.refresh_stats()

        elapsed_ms = self.move_timer.elapsed()
        time_str = None
        if elapsed_ms > 1000:
            seconds = (elapsed_ms // 1000) % 60
            minutes = (elapsed_ms // (1000 * 60)) % 60
            time_str = f"{minutes:02}:{seconds:02}"

        dlg = CleanerResultDialog(len(moved), len(errors) if isinstance(errors, list) else errors, time_str, self)
        dlg.exec()

    def delete_empty_folders(self) -> None:
        paths = self.session_db.get_global_marked_empty_folders()
        if not paths: return
        
        res = QMessageBox.question(self, AppContext.tr("msg_del_confirm_title"), f"Удалить {len(paths)} пустых папок?\nЭто действие нельзя отменить через Откат.", 
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if res == QMessageBox.StandardButton.Yes:
            self.preview_widget.show_empty("Deleting folders...")
            QCoreApplication.processEvents()

            self.overlay.start_process(len(paths), "cln_ovl_deleting_folders")
            self.move_timer.start()

            self.deleter = SessionDeleteWorker(paths, is_folders=True, use_trash=False)
            self.deleter.progress_total.connect(self.overlay.update_total)
            self.deleter.file_started.connect(self.overlay.start_file)
            self.deleter.finished.connect(self.on_delete_folders_finished)

            try:
                self.overlay.cancel_requested.disconnect()
            except Exception:
                pass
            self.overlay.cancel_requested.connect(self.on_overlay_cancel)

            self.deleter.start()

    def on_delete_folders_finished(self, deleted_paths: list[str], errors: list[tuple[str, str]]) -> None:
        try:
            for p in deleted_paths:
                self.session_db.mark_folder_deleted(p)
        finally:
            self.overlay.hide()

        self.cleanup_tree_after_move()

        elapsed_ms = self.move_timer.elapsed()
        time_str = None
        if elapsed_ms > 1000:
            seconds = (elapsed_ms // 1000) % 60
            minutes = (elapsed_ms // (1000 * 60)) % 60
            time_str = f"{minutes:02}:{seconds:02}"

        dlg = CleanerResultDialog(len(deleted_paths), len(errors), time_str, self, action_type='delete_folders')
        dlg.exec()


    def rename_file_in_tree(self, index: QModelIndex) -> None:
        item = index.data(Qt.ItemDataRole.UserRole)
        if not item or item['type'] != 'file': return
        
        old_path = item['path']
        if not os.path.exists(old_path):
            QMessageBox.warning(self, "Error", "File not found!")
            return
            
        parent_dir = os.path.dirname(old_path)
        old_name = os.path.basename(old_path)
        dlg = SmartNameDialog("dlg_rename_title", "dlg_enter_name", parent_dir, old_name, self)
        if dlg.exec():
            new_name = dlg.final_name
            if new_name == old_name: return
            new_path = os.path.join(parent_dir, new_name)
            try:
                self.preview_widget.show_empty("Renaming...")
                QCoreApplication.processEvents() # Flush event loop to fully close and release preview media in OS
                os.rename(old_path, new_path)
                try:
                    import sqlite3
                    with sqlite3.connect(self.session_db.db_path) as db:
                        db.execute("UPDATE files SET path = ? WHERE path = ?", (new_path, old_path))
                        db.execute("UPDATE zero_files SET path = ? WHERE path = ?", (new_path, old_path))
                except Exception as e:
                    logging.error(f"Failed to update session DB on rename: {e}")
                
                self.refresh_tree_view()
                self.preview_widget.load_file(new_path)
            except Exception as e:
                QMessageBox.critical(self, AppContext.tr("err_title"), f"{AppContext.tr('msg_rename_fail')} {e}")

    def on_overlay_cancel(self) -> None:
        if self.mover and self.mover.isRunning():
            self.mover.stop()
            self.overlay.lbl_title.setText(AppContext.tr("cln_ovl_cancelling"))
        elif hasattr(self, 'deleter') and self.deleter and self.deleter.isRunning():
            self.deleter.stop()
            self.overlay.lbl_title.setText(AppContext.tr("cln_ovl_cancelling"))
        elif self.loading_timer.isActive():
            self.stop_loading()
        elif self.selection_timer.isActive():
            self.pending_selection_changes = []
            self.selection_timer.stop()
            self.overlay.hide()
            self.btn_stop_load.hide()
