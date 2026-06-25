import logging
from typing import Any
from PyQt6.QtWidgets import QMessageBox, QMenu
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt, QTimer, QCoreApplication

from config import AppContext
from utils_common import format_size, format_compact_count
from .ui_dialogs import MatrixFilterDialog

class ViewMixin:
    def switch_view_mode(self, mode: int) -> None:
        self.current_view_mode = mode
        
        self.settings_panel.btn_duples.set_mode('active' if mode == 0 else 'available')
        self.settings_panel.btn_zero.set_mode('active' if mode == 1 else 'available')
        self.settings_panel.btn_empty.set_mode('active' if mode == 2 else 'available')
        
        if self.settings_panel.btn_duples.text() == "0": self.settings_panel.btn_duples.set_mode('disabled')
        if self.settings_panel.btn_zero.text() == "0": self.settings_panel.btn_zero.set_mode('disabled')
        if self.settings_panel.btn_empty.text() == "0": self.settings_panel.btn_empty.set_mode('disabled')
        
        tree_nav_visible = (mode != 2)
        self.btn_exp.setVisible(tree_nav_visible)
        self.btn_col.setVisible(tree_nav_visible)

        if mode == 0: # Duples
            self.action_bar.combo_autoselect.show()
            self.action_bar.chk_preserve.show()
            self.action_bar.combo_collision.show()
            self.action_bar.drop_zone.show()
            self.action_bar.btn_delete.show()
            self.action_bar.set_move_button_enabled(False, AppContext.tr("cln_btn_move_icon") + " ")
            self.btn_sort_v.show()
            self.btn_types.show()
            self.lbl_show.setVisible(False)
            self.combo_limit.setVisible(False)
            self.lbl_groups_found.show()
            self.action_bar.btn_select_all.hide()
            
        elif mode == 1: # Zero
            self.action_bar.combo_autoselect.hide()
            self.action_bar.chk_preserve.hide() 
            self.action_bar.combo_collision.hide()
            self.action_bar.drop_zone.show()
            self.action_bar.btn_delete.show()
            self.action_bar.set_move_button_enabled(False, AppContext.tr("cln_act_move"))
            self.btn_sort_v.hide()
            self.btn_types.hide()
            self.lbl_show.setVisible(False)
            self.combo_limit.setVisible(False)
            self.lbl_groups_found.hide()
            self.action_bar.btn_select_all.show()
            
        elif mode == 2: # Empty
            self.action_bar.combo_autoselect.hide()
            self.action_bar.chk_preserve.hide()
            self.action_bar.combo_collision.hide()
            self.action_bar.drop_zone.hide()
            self.action_bar.btn_delete.hide()
            self.action_bar.set_move_button_enabled(False, AppContext.tr("cln_act_delete_folders"))
            self.btn_sort_v.hide()
            self.btn_types.hide()
            self.lbl_show.setVisible(False)
            self.combo_limit.setVisible(False)
            self.lbl_groups_found.hide()
            self.action_bar.btn_select_all.show()
            
        self.refresh_tree_view()

    def refresh_tree_view(self) -> None:
        """
        Запускает фоновое чтение БД и обогащение метаданных (Enrich & Cache) в фоновом потоке,
        сохраняя интерфейс на 100% отзывчивым.
        """
        # Если предыдущий воркер работает, останавливаем его
        if hasattr(self, 'db_load_worker') and self.db_load_worker.isRunning():
            logging.info("[PERF] Остановка предыдущего фонового чтения БД перед перезапуском...")
            self.db_load_worker.stop()
            self.db_load_worker.wait()

        self.preview_widget.show_empty("...") 
        self.lbl_selection_info.setText(AppContext.tr("cln_lbl_selected").format(0, "0 B"))

        self.overlay.start_loading_mode(0)
        self.overlay.lbl_title.setText("Подготовка чтения...")
        self.overlay.btn_stop.show()
        
        try:
            self.overlay.cancel_requested.disconnect()
        except:
            pass
        self.overlay.cancel_requested.connect(self.cancel_db_load)
        
        QCoreApplication.processEvents()

        from .workers import DBLoadWorker
        self.db_load_worker = DBLoadWorker(
            session_db=self.session_db,
            current_view_mode=self.current_view_mode,
            source_folders=self.source_folders,
            view_filter_exts=self.view_filter_exts,
            view_filter_mode=self.view_filter_mode
        )
        self.db_load_worker.progress.connect(self.on_db_load_progress)
        self.db_load_worker.finished.connect(self.on_db_load_finished)
        
        logging.info("[PERF] Запуск фонового потока DBLoadWorker...")
        self.db_load_worker.start()

    def on_db_load_progress(self, current: int, total: int) -> None:
        """Слот прогресса чтения БД из фонового потока."""
        self.overlay.update_total(current, total)
        self.overlay.lbl_title.setText(f"Чтение базы данных: {current}/{total}...")
        # Даем Qt обновить графику, оверлей крутится плавно
        QCoreApplication.processEvents()

    def cancel_db_load(self) -> None:
        """Принудительная остановка фонового чтения БД пользователем."""
        if hasattr(self, 'db_load_worker') and self.db_load_worker.isRunning():
            self.db_load_worker.stop()
            self.db_load_worker.wait()
        self.overlay.hide()
        logging.info("[PERF] Фоновое чтение БД успешно прервано пользователем.")

    def on_db_load_finished(self, flat_items: list[dict[str, Any]], group_files_cache: dict[Any, list[dict[str, Any]]]) -> None:
        """Слот завершения фонового чтения и Enrich из воркера."""
        if not flat_items:
            # Пусто или отменено
            self.overlay.hide()
            self.virtual_model.beginResetModel()
            self.virtual_model._all_items = []
            self.virtual_model._flat_items = []
            self.virtual_model._source_flat_items = []
            self.virtual_model._group_files_cache = {}
            self.virtual_model.endResetModel()
            self.update_view_stats()
            return

        logging.info(f"[PERF] Фоновое чтение завершено. Получено элементов: {len(flat_items)}. Вызов start_incremental_load...")
        
        # Передаем управление в инкрементный загрузчик
        self.start_incremental_load_from_worker(flat_items, group_files_cache)

    def on_type_filter_click(self) -> None:
        stats = self.session_db.get_extension_stats()
        if not stats:
            return
        dlg = MatrixFilterDialog(stats, self)
        if dlg.exec():
            result = dlg.get_result()
            if not result['exts']:
                self.view_filter_exts = None
                self.view_filter_mode = 'include'
            else:
                self.view_filter_exts = list(result['exts'])
                self.view_filter_mode = result['mode']
            self.update_types_button_style()
            self.refresh_tree_view()

    def update_types_button_style(self) -> None:
        base_style = "QPushButton { border: 1px solid #444; border-radius: 3px; padding: 2px 8px; }"
        disabled_style = "QPushButton:disabled { color: #555; background: #222; border-color: #333; }"
        if not self.view_filter_exts:
            self.btn_types.setStyleSheet(base_style + "QPushButton { background: #333; color: white; }" + disabled_style)
        elif self.view_filter_mode == 'include':
            self.btn_types.setStyleSheet(base_style + "QPushButton { background: #bfdbfe; color: #1e3a8a; border-color: #3b82f6; font-weight: bold; }" + disabled_style)
        else:
            self.btn_types.setStyleSheet(base_style + "QPushButton { background: #fecaca; color: #7f1d1d; border-color: #ef4444; font-weight: bold; }" + disabled_style)

    def on_types_context_menu(self, pos: Any) -> None:
        menu = QMenu(self)
        action = QAction(AppContext.tr("cln_btn_clear_filter"), self)
        action.triggered.connect(self.clear_type_filter)
        menu.addAction(action)
        menu.exec(self.btn_types.mapToGlobal(pos))

    def clear_type_filter(self) -> None:
        self.view_filter_exts = None
        self.view_filter_mode = 'include'
        self.update_types_button_style()
        self.refresh_tree_view()

    def cleanup_tree_after_move(self) -> None:
        """
        Refreshes tree viewport with current DB states after processing.
        """
        self.refresh_tree_view()
        self.preview_widget.show_empty("Cleanup Done")
        self.action_bar.drop_zone.refresh_stats()

    def update_view_stats(self) -> None:
        """ Centralized method to sync DB stats with UI scrollbar labels and settings panel """
        # Count items from virtual model
        displayed_groups = sum(1 for item in self.virtual_model._all_items if item['type'] == 'group')
        displayed_files = sum(1 for item in self.virtual_model._all_items if item['type'] == 'file')
        
        if self.current_view_mode == 0:
            display_str = f"{displayed_groups} ({displayed_files})"
            self.lbl_groups_found.setText(AppContext.tr("cln_lbl_groups").format(display_str))
        elif self.current_view_mode == 1:
            display_str = f"{displayed_groups} ({displayed_files})"
            self.lbl_groups_found.setText(AppContext.tr("cln_lbl_groups").format(display_str))
        else:
            displayed_folders = len(self.virtual_model._all_items)
            self.lbl_groups_found.setText(f"Папок: {displayed_folders}")
        
        # Update Left Sidebar Stats
        stats = self.session_db.get_active_stats()
        
        # Enable/disable Type Filter button based on availability of data
        if self.current_view_mode == 0:
            self.btn_types.setEnabled(stats['groups_count'] > 0)
        
        g_count = stats['groups_count']
        dupes_count = stats['dupes_count']
        
        g_compact = format_compact_count(g_count)
        d_compact = format_compact_count(dupes_count)
        
        self.settings_panel.btn_duples.setText(f"{g_compact} ({d_compact})")
        self.settings_panel.btn_duples.setToolTip(AppContext.tr("cln_tip_dupes_count").format(g_count, dupes_count))
        
        self.settings_panel.val_wasted.setText(format_size(stats['wasted']))
        self.update_selection_info()
