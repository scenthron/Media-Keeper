
import os
import re
import shutil
import traceback
import sys
import ctypes
import subprocess
import logging
from PyQt6.QtWidgets import QMessageBox, QApplication, QLabel, QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QFrame, QScrollArea, QWidget
from PyQt6.QtCore import QTimer, QUrl, Qt, QFile
from PyQt6.QtGui import QDesktopServices

from config import AppContext
from ui_dialogs_generic import ProgressDialog, SmartNameDialog, FileConflictDialog, FileDeletionConfirmDialog, BatchRenameErrorsDialog, MultiFileConflictDialog, MoveErrorsDialog
from .ui_sidebar_category import CategoryWidget
from .ui_sidebar_leaf import LeafNodeWidget
from .workers import ScanThread, MoveThread
from .logic_automation import AutomationConfig, TemplateEngine
from utils_common import format_size, get_unique_filepath
from logic_cache import DirCache
from utils_io import smart_move_file, ensure_long_path, strip_long_path_prefix
from utils_extensions import VIDEO_EXTS, AUDIO_EXTS, IMAGE_EXTS

def safe_relpath(path: str, start: str) -> str:
    if not start:
        return strip_long_path_prefix(path)
    p = strip_long_path_prefix(path)
    s = strip_long_path_prefix(start)
    try:
        return os.path.relpath(p, s)
    except ValueError:
        return p

class FileOpsMixin:
    def _safe_close_dialog(self, dialog_attr_name):
        if not hasattr(self, dialog_attr_name): return
        dlg = getattr(self, dialog_attr_name)
        if dlg:
            try:
                dlg.setParent(None)
                if dlg.isVisible():
                    dlg.hide()
                    dlg.close()
                dlg.deleteLater()
            except RuntimeError: pass
            except Exception as e: logging.error(f"Error closing dialog: {e}")
            setattr(self, dialog_attr_name, None)

    def refresh_files_list(self, show_progress=True):
        """
        Scans Incoming folder to build the queue.
        show_progress: if True, shows the "Scanning..." dialog.
        """
        logging.info(f"Requesting file list refresh (show_progress={show_progress}).")
        
        if hasattr(self, 'scan_thread') and self.scan_thread and self.scan_thread.isRunning():
            logging.debug("Scan already in progress, skipping.")
            return

        if not self.UNSORT_DIR or not os.path.exists(self.UNSORT_DIR):
            if not getattr(self, 'virtual_folder_name', None):
                logging.warning(f"Scan path invalid: {self.UNSORT_DIR}")
                self.files_queue = []
                self._raw_dir_files = []
                if self.isVisible(): self.show_current_file()
                return
        else:
            # We are scanning a real folder, clear virtual session and thumbnail cache
            was_virtual = getattr(self, 'virtual_folder_name', None) is not None
            self.virtual_folder_name = None
            if hasattr(self, 'lbl_unsort_count'):
                self.lbl_unsort_count.virtual_getter = None
            from logic_paths import get_app_data_dir
            session_path = os.path.join(get_app_data_dir(), "virtual_session.json")
            if os.path.exists(session_path):
                try: os.remove(session_path)
                except: pass
                
            from modules.sorter.thumbnail_loader import ThumbnailLoader
            ThumbnailLoader.inst().clear_disk_cache()
            
            if was_virtual and hasattr(self, 'refresh_sidebar_styling'):
                self.refresh_sidebar_styling()

        if show_progress:
            logging.debug("Show scan dialog.")
            self.scan_dlg = ProgressDialog(AppContext.tr("scan_progress"), self, show_cancel=True)
            self.scan_dlg.setWindowModality(Qt.WindowModality.WindowModal)
            self.scan_dlg.cancelled.connect(self.cancel_scan)
            self.scan_dlg.show()
            QApplication.processEvents()
        
        recursive = self.config.get("scan_subfolders", False)
        
        if getattr(self, 'virtual_folder_name', None):
            # We are in virtual folder mode, but the user clicked refresh.
            # We just re-apply filters on existing _raw_dir_files.
            logging.info("Refreshing virtual folder via apply_local_filters_and_sorting")
            self._safe_close_dialog('scan_dlg')
            self.apply_local_filters_and_sorting(trigger_sync=True)
            return

        logging.info(f"Starting scan thread: {self.UNSORT_DIR}")
        # Передаем пустые расширения в ScanThread, чтобы он сканировал все файлы без дисковой фильтрации
        self.scan_thread = ScanThread(self.UNSORT_DIR, recursive, [], "include")
        self.scan_thread.finished_scan.connect(self.on_scan_finished)
        self.scan_thread.start()

    def load_virtual_files(self, file_paths: list[str], source_name: str):
        """Loads an explicit list of absolute file paths (Virtual Folder)."""
        logging.info(f"Loading virtual folder from {source_name} with {len(file_paths)} files.")
        
        import json
        from logic_paths import get_app_data_dir
        session_path = os.path.join(get_app_data_dir(), "virtual_session.json")
        try:
            with open(session_path, 'w', encoding='utf-8') as f:
                json.dump({"source_name": source_name, "files": file_paths}, f, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Failed to save virtual session: {e}")
            
        # Clean thumbnail cache for new virtual session
        from modules.sorter.thumbnail_loader import ThumbnailLoader
        ThumbnailLoader.inst().clear_disk_cache()
        
        self.UNSORT_DIR = ""  # Empty string trick for absolute rel_paths
        self._raw_dir_files = []
        
        for p in file_paths:
            if not os.path.exists(p):
                continue
            try:
                stat = os.stat(p)
                self._raw_dir_files.append({
                    'rel_path': ensure_long_path(p),
                    'size': stat.st_size,
                    'mtime': stat.st_mtime,
                    'ctime': stat.st_ctime
                })
            except Exception:
                pass
                
        self.virtual_folder_name = source_name
        self.files_queue = []
        self.current_index = 0
        
        # We must trigger UI refresh directly since there's no ScanThread
        self.apply_local_filters_and_sorting(trigger_sync=True)
        if hasattr(self, 'update_ui_for_virtual_folder'):
            self.update_ui_for_virtual_folder()

    def _get_virtual_folder_text(self):
        if not getattr(self, 'virtual_folder_name', None): return None
        count = len(self._raw_dir_files) if hasattr(self, '_raw_dir_files') else 0
        total_size = sum(f.get('size', 0) for f in self._raw_dir_files) if hasattr(self, '_raw_dir_files') else 0
        from utils_common import format_size
        size_str = format_size(total_size)
        return f"{self.virtual_folder_name} ({count} файлов, {size_str})"

    def update_ui_for_virtual_folder(self):
        if not getattr(self, 'virtual_folder_name', None): return
        
        if hasattr(self, 'lbl_unsort_count'):
            self.lbl_unsort_count.virtual_getter = self._get_virtual_folder_text
            self.lbl_unsort_count.update_info()
            
        if hasattr(self, 'refresh_sidebar_styling'):
            self.refresh_sidebar_styling()

    def cancel_scan(self):
        logging.info("Сканирование входящей папки отменено пользователем.")
        if hasattr(self, 'scan_thread') and self.scan_thread:
            self.scan_thread.cancel()
            self._scan_was_cancelled = True
            self.scan_thread.wait()  # Гарантируем завершение потока до закрытия диалога
            self.scan_thread.deleteLater()
            self.scan_thread = None
        self._safe_close_dialog('scan_dlg')

    def on_scan_finished(self, files):
        if getattr(self, '_scan_was_cancelled', False):
            self._scan_was_cancelled = False
            self._safe_close_dialog('scan_dlg')
            if hasattr(self, 'scan_thread') and self.scan_thread:
                self.scan_thread.deleteLater()
            self.scan_thread = None
            return

        if hasattr(self, 'scan_thread') and self.scan_thread and getattr(self.scan_thread, '_is_cancelled', False):
            logging.info("Результаты сканирования проигнорированы, так как оно было отменено.")
            self._safe_close_dialog('scan_dlg')
            if hasattr(self, 'scan_thread') and self.scan_thread:
                self.scan_thread.deleteLater()
            self.scan_thread = None
            return

        # Проверяем, изменился ли состав файлов на самом деле
        current_set = set(f['rel_path'] for f in getattr(self, '_raw_dir_files', [])) if getattr(self, '_raw_dir_files', None) is not None else None
        new_set = set(f['rel_path'] for f in files)
        
        is_ui_dirty = getattr(self.viewer, 'is_loading_interrupted', False)
        
        if not is_ui_dirty and current_set is not None and current_set == new_set:
            logging.debug("Scan finished: No changes in file list, skipping UI refresh. Checking missing thumbnails...")
            self._safe_close_dialog('scan_dlg')
            if hasattr(self, 'scan_thread') and self.scan_thread:
                self.scan_thread.deleteLater()
            self.scan_thread = None
            
            # Запускаем генерацию превью для файлов, у которых их нет в кэше
            from PyQt6.QtCore import QSize
            from modules.sorter.thumbnail_loader import ThumbnailLoader
            loader = ThumbnailLoader.inst()
            for f in files:
                f_path = os.path.join(self.UNSORT_DIR, f['rel_path'])
                norm_p = os.path.normpath(f_path)
                if norm_p not in loader.cache:
                    ext = os.path.splitext(norm_p)[1].lower()
                    if ext in IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS:
                        loader.get_thumbnail(f_path, QSize(256, 256))
            return

        logging.info(f"Scan finished. Found {len(files)} files.")
        self._raw_dir_files = files  # Сохраняем полный список с метаданными в ОЗУ
        self.apply_local_filters_and_sorting(trigger_sync=False)
        
        # Закрываем диалог если он был
        self._safe_close_dialog('scan_dlg')
        
        if self._pending_refresh_file:
            if self._pending_refresh_file in self.files_queue:
                self.current_index = self.files_queue.index(self._pending_refresh_file)
            else:
                if self.current_index >= len(self.files_queue): self.current_index = 0
            self._pending_refresh_file = None
        else:
            if self.current_index >= len(self.files_queue): self.current_index = 0
            
        should_reload_player = True
        if self.files_queue and self.current_file_path:
            new_file_rel = self.files_queue[self.current_index]
            new_file_full = os.path.join(self.UNSORT_DIR, new_file_rel)
            if os.path.normpath(new_file_full) == os.path.normpath(self.current_file_path):
                should_reload_player = False

        self.viewer.sync_files_queue(self.UNSORT_DIR, self.files_queue, self.current_index)

        if self.isVisible():
            if should_reload_player:
                self.show_current_file()
            else:
                if hasattr(self, 'update_file_info_label'):
                    self.update_file_info_label()
            
        self.lbl_unsort_count.update_info()
        self.lbl_todel_count.update_info()
        if hasattr(self, 'scan_thread') and self.scan_thread:
            self.scan_thread.deleteLater()
        self.scan_thread = None

    def apply_local_filters_and_sorting(self, trigger_sync=True):
        if not hasattr(self, '_raw_dir_files') or self._raw_dir_files is None:
            self._raw_dir_files = []
            
        raw_filter = self.config.get("filter_extensions", "")
        filter_mode = self.config.get("filter_mode", "include")
        
        valid_extensions = [e.strip().lower() for e in raw_filter.split(',') if e.strip()]
        normalized_extensions = []
        for ext in valid_extensions:
            if not ext.startswith('.'): ext = '.' + ext
            normalized_extensions.append(ext)
            
        # 1. Фильтрация
        filtered_files = []
        min_mb = self.config.get("filter_min_size", 0.0)
        max_mb = self.config.get("filter_max_size", 0.0)
        min_bytes = int(min_mb * 1024 * 1024) if min_mb > 0 else 0
        max_bytes = int(max_mb * 1024 * 1024) if max_mb > 0 else 0
        
        for f_info in self._raw_dir_files:
            size = f_info.get('size', 0)
            if min_bytes > 0 and size < min_bytes:
                continue
            if max_bytes > 0 and size > max_bytes:
                continue
                
            rel_path = f_info['rel_path']
            ext = os.path.splitext(rel_path)[1].lower()
            
            if normalized_extensions:
                if filter_mode == "include":
                    match = ext in normalized_extensions
                else: # exclude
                    match = ext not in normalized_extensions
            else:
                match = True
                
            if match:
                filtered_files.append(f_info)
                
        # 2. Сортировка
        sort_type = self.config.get("sort_type", "name_asc")
        
        if sort_type in ["name_asc", "name_desc"]:
            import re
            def natural_keys(text):
                return [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', text)]
            reverse = sort_type == "name_desc"
            filtered_files.sort(key=lambda x: natural_keys(os.path.basename(x['rel_path'])), reverse=reverse)
        else:
            def get_sort_key(f_info):
                rel_path = f_info['rel_path']
                name = os.path.basename(rel_path).lower()
                ext = os.path.splitext(rel_path)[1].lower()
                
                if sort_type == "type_asc":
                    if ext in VIDEO_EXTS:
                        cat_order = 0
                    elif ext in IMAGE_EXTS:
                        cat_order = 1
                    elif ext in AUDIO_EXTS:
                        cat_order = 2
                    else:
                        cat_order = 3
                    return (cat_order, ext, name)
                elif sort_type == "size_desc" or sort_type == "size_asc":
                    return f_info.get('size', 0)
                elif sort_type == "mtime_desc" or sort_type == "mtime_asc":
                    return f_info.get('mtime', 0.0)
                elif sort_type == "ctime_desc" or sort_type == "ctime_asc":
                    return f_info.get('ctime', 0.0)
                else:
                    return name
            
            reverse = sort_type in ["size_desc", "mtime_desc", "ctime_desc"]
            filtered_files.sort(key=get_sort_key, reverse=reverse)
            
        self._all_filtered_files_queue = [f['rel_path'] for f in filtered_files]
        
        # --- Pagination Slicing ---
        if not hasattr(self, 'page_index'):
            self.page_index = 0
            
        page_size = self.config.get("pagination_size", 1000)
        total_items = len(self._all_filtered_files_queue)
        
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        if self.page_index >= total_pages:
            self.page_index = total_pages - 1
        if self.page_index < 0:
            self.page_index = 0
            
        start_idx = self.page_index * page_size
        end_idx = min(start_idx + page_size, total_items)
        
        new_queue = self._all_filtered_files_queue[start_idx:end_idx]
        
        # Update Viewer Pagination UI
        if hasattr(self, 'viewer') and self.viewer and hasattr(self.viewer, 'update_pagination_ui'):
            self.viewer.update_pagination_ui(self.page_index, total_pages)
        
        current_file = None
        if self.files_queue and self.current_index < len(self.files_queue):
            current_file = self.files_queue[self.current_index]
            
        self.files_queue = new_queue
        
        if current_file in self.files_queue:
            self.current_index = self.files_queue.index(current_file)
        else:
            self.current_index = 0
            
        if trigger_sync:
            self.viewer.sync_files_queue(self.UNSORT_DIR, self.files_queue, self.current_index)
            if self.isVisible():
                self.show_current_file()

    def change_page(self, delta):
        if not hasattr(self, '_all_filtered_files_queue'): return
        
        page_size = self.config.get("pagination_size", 1000)
        total_items = len(self._all_filtered_files_queue)
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        
        new_page = getattr(self, 'page_index', 0) + delta
        if new_page < 0:
            new_page = total_pages - 1
        elif new_page >= total_pages:
            new_page = 0
            
        if new_page != getattr(self, 'page_index', -1):
            self.page_index = new_page
            # Trigger full re-sync of UI
            self.apply_local_filters_and_sorting(trigger_sync=True)

    def refresh_pagination(self):
        # Clears disk thumbnail cache and triggers full refresh to reset state
        from modules.sorter.thumbnail_loader import ThumbnailLoader
        ThumbnailLoader.inst().clear_disk_cache()
        self.manual_full_refresh(reset_position=False, silent=False)

    def apply_sorting_to_queue(self, sort_type, trigger_sync=True):
        self.config["sort_type"] = sort_type
        self.apply_local_filters_and_sorting(trigger_sync=trigger_sync)

    def open_sorter_settings_dialog(self):
        from .ui_dialog_settings import SorterSettingsDialog
        from .logic_config import ConfigManager
        
        old_recursive = self.config.get("scan_subfolders", False)
        
        dlg = SorterSettingsDialog(self.config, self)
        if dlg.exec():
            # Сохраняем измененные настройки
            ConfigManager.save(self.config)
            
            new_recursive = self.config.get("scan_subfolders", False)
            
            # Если изменился параметр рекурсивного сканирования, требуется полный переобход диска
            if new_recursive != old_recursive:
                self.manual_full_refresh(reset_position=False, silent=True)
            else:
                # Применяем новую сортировку и фильтры локально из ОЗУ
                sort_type = self.config.get("sort_type", "name_asc")
                self.apply_sorting_to_queue(sort_type, trigger_sync=True)

    def manual_full_refresh(self, reset_position=False, silent=False, target_path=None):
        if not silent:
            # Только при РУЧНОМ нажатии кнопки показываем визуальную индикацию
            self.btn_refresh.setText("")
            self.btn_refresh.setStyleSheet("QPushButton { background-color: #0f5132; border-radius: 5px; padding: 0px; }")
            QTimer.singleShot(2000, self.reset_refresh_button)
            
            # При ручном рефреше принудительно очищаем весь кэш статистики директорий
            DirCache.inst().clear()

        self.reload_categories_ui()
        
        if target_path:
             self._pending_refresh_file = target_path
        elif not reset_position and self.files_queue and self.current_index < len(self.files_queue):
            self._pending_refresh_file = self.files_queue[self.current_index]
        else: 
            self._pending_refresh_file = None
            if reset_position:
                self.current_index = 0

        # Вызываем сканирование файлов в Incoming (silent=silent подавит ProgressDialog)
        if hasattr(self, 'viewer') and self.viewer:
            self.viewer.is_loading_interrupted = True
        self.refresh_files_list(show_progress=not silent)

    def reset_refresh_button(self):
        self.btn_refresh.setText("")
        self.btn_refresh.setStyleSheet("QPushButton { background-color: #15803d; border-radius: 5px; padding: 0px; } QPushButton:hover { background-color: #166534; }")

    def _collect_watch_dirs(self, root, current_depth, max_depth, result_list, max_paths=100):
        if current_depth >= max_depth or len(result_list) >= max_paths:
            return
        try:
            with os.scandir(root) as it:
                for entry in it:
                    if len(result_list) >= max_paths:
                        break
                    if entry.name == ".mediakeeper":
                        continue
                    if entry.is_dir():
                        result_list.append(entry.path)
                        self._collect_watch_dirs(entry.path, current_depth + 1, max_depth, result_list, max_paths)
        except:
            pass

    def update_watcher_paths(self):
        if not self.fs_watcher: return
        existing = self.fs_watcher.directories()
        if existing: self.fs_watcher.removePaths(existing)
        
        paths_to_watch = []
        if self.UNSORT_DIR and os.path.exists(self.UNSORT_DIR): 
            paths_to_watch.append(self.UNSORT_DIR)
            
        max_depth = min(self.config.get("category_max_depth", 3), 2)  # Cap depth to 2 to prevent deep freezes
        max_total_paths = 150 # Max paths to watch to prevent addPaths freeze
        
        roots_to_check = []
        if self.SORT_DIR and os.path.exists(self.SORT_DIR):
            roots_to_check.append(self.SORT_DIR)
            
        if hasattr(self, 'temp_roots'):
            for t in self.temp_roots:
                if os.path.exists(t):
                    roots_to_check.append(t)
                
        for r in roots_to_check:
            if len(paths_to_watch) < max_total_paths:
                paths_to_watch.append(r)
                self._collect_watch_dirs(r, 0, max_depth, paths_to_watch, max_paths=max_total_paths)

        # Ensure we don't exceed the OS limit for QFileSystemWatcher
        paths_to_watch = list(set(paths_to_watch))[:max_total_paths]
        
        if paths_to_watch:
            try:
                self.fs_watcher.addPaths(paths_to_watch)
            except Exception as e:
                import logging
                logging.error(f"Error adding paths to watcher: {e}")

    def on_fs_directory_changed(self, path):
        # Если мы сами инициировали действие, игнорируем событие
        if getattr(self, '_ignore_watcher', False):
            logging.debug(f"Watcher: Ignoring event for {path} due to internal operation.")
            return
        if not hasattr(self, '_dirty_watcher_paths'):
            self._dirty_watcher_paths = set()
        self._dirty_watcher_paths.add(os.path.normpath(path))
        self.fs_debounce_timer.start()

    def on_fs_debounce_timeout(self):
        dirty = getattr(self, '_dirty_watcher_paths', set())
        self._dirty_watcher_paths = set()
        if not dirty:
            self.update_watcher_paths()
            return

        unsort_changed = False
        sort_changed = False
        
        norm_unsort = os.path.normpath(self.UNSORT_DIR) if self.UNSORT_DIR else None
        
        for p in dirty:
            norm_p = os.path.normpath(p)
            DirCache.inst().invalidate_with_parents(norm_p)
            if norm_unsort and norm_p == norm_unsort:
                unsort_changed = True
            else:
                sort_changed = True

        if unsort_changed:
            logging.info("Watcher: Incoming directory changed. Quietly refreshing files list.")
            if self.isVisible():
                self.refresh_files_list(show_progress=False)
            else:
                self._incoming_dirty = True
            
        if sort_changed:
            logging.info("Watcher: Sort directory or category changed. Reloading categories UI.")
            if self.isVisible():
                self.reload_categories_ui()
            else:
                self._categories_dirty = True

        self.update_watcher_paths()

    def rename_current_file(self):
        if not self.current_file_path:
            QMessageBox.warning(self, "Info", AppContext.tr("msg_empty"))
            return
            
        long_current = ensure_long_path(self.current_file_path)
        if not os.path.exists(long_current):
            QMessageBox.warning(self, "Info", AppContext.tr("msg_empty"))
            return
            
        # Защита: переименование доступно только когда выбран строго 1 файл
        if self.viewer.stack.currentIndex() != 0:
            if len(self.viewer.get_selected_files()) != 1:
                return

        old_name = os.path.basename(self.current_file_path)
        parent_dir = os.path.dirname(self.current_file_path)
        
        dlg = SmartNameDialog("dlg_rename_title", "dlg_enter_name", parent_dir, old_name, self)
        if dlg.exec():
            new_name = dlg.final_name
            if new_name == old_name: return

            new_path = os.path.join(parent_dir, new_name)
            self._stop_all_media_players()
            from PyQt6.QtCore import QThreadPool
            QThreadPool.globalInstance().waitForDone(1000)
            QApplication.processEvents() 
            try:
                # Блокируем watcher чтобы не вызывал рефреш дважды
                self._ignore_watcher = True
                
                long_new_path = ensure_long_path(new_path)
                os.rename(long_current, long_new_path)
                
                self.history.append([(new_path, self.current_file_path)])
                
                long_unsort = ensure_long_path(self.UNSORT_DIR)
                rel_old = safe_relpath(long_current, long_unsort)
                rel_new = safe_relpath(long_new_path, long_unsort)
                if rel_old in self.files_queue:
                    idx = self.files_queue.index(rel_old)
                    self.files_queue[idx] = rel_new
                    self.current_index = idx
                
                # Обновляем RAM-кэш
                if hasattr(self, '_raw_dir_files') and self._raw_dir_files:
                    for f_info in self._raw_dir_files:
                        if os.path.normpath(f_info['rel_path']) == os.path.normpath(rel_old):
                            f_info['rel_path'] = rel_new
                            try:
                                stat = os.stat(long_new_path)
                                f_info['size'] = stat.st_size
                                f_info['mtime'] = stat.st_mtime
                                f_info['ctime'] = stat.st_ctime
                            except Exception:
                                pass
                            break

                old_path = self.current_file_path
                self.current_file_path = new_path
                self.lbl_filename.setText(new_name)
                
                self.viewer.update_file_path_in_view(old_path, new_path)
                if self.viewer.stack.currentIndex() == 0:
                    self.show_current_file()
                else:
                    self.on_selection_changed()
            except Exception as e:
                logging.error(f"Rename error: {e}", exc_info=True)
                QMessageBox.critical(self, AppContext.tr("err_title"), f"{AppContext.tr('msg_rename_fail')} {e}")
                self.show_current_file() 
            finally:
                # Разблокируем watcher через короткое время
                QTimer.singleShot(500, lambda: setattr(self, '_ignore_watcher', False))
        self.setFocus()

    def _stop_all_media_players(self, is_only_images=False, is_single_file=False):
        """Останавливает все плееры (основной, ховер, попапы) и освобождает хэндлы файлов."""
        # Если перемещаются только изображения, пропускаем долгое ожидание в QThreadPool и плеерах,
        # так как изображения не блокируются QMediaPlayer-ом на диске.
        if is_only_images:
            try:
                self.media_player.stop()
                self.media_player.setSource(QUrl())
            except Exception:
                pass
            try:
                if hasattr(self, 'viewer') and self.viewer:
                    self.viewer.clear_scene_content()
                    if hasattr(self.viewer, 'grid_view') and self.viewer.grid_view:
                        try: self.viewer.grid_view._stop_hover_playback(force=True)
                        except: pass
                    if hasattr(self.viewer, 'list_view') and self.viewer.list_view:
                        try: self.viewer.list_view._stop_hover_playback(force=True)
                        except: pass
            except Exception:
                pass
            QApplication.processEvents()
            return

        try:
            from PyQt6.QtCore import QThreadPool
            # Очищаем очередь, но не ждем завершения активных задач, если перемещается один файл
            QThreadPool.globalInstance().clear()
            if not is_single_file:
                QThreadPool.globalInstance().waitForDone(500)
        except Exception as e:
            logging.error(f"Error clearing QThreadPool: {e}")

        # Сначала закрываем попапы и останавливаем ховер-воспроизведение на уровне вьюшек
        try:
            if hasattr(self, 'viewer') and self.viewer:
                if hasattr(self.viewer, 'grid_view') and self.viewer.grid_view:
                    if hasattr(self.viewer.grid_view, '_stop_hover_playback'):
                        try: self.viewer.grid_view._stop_hover_playback(force=True)
                        except: pass
                if hasattr(self.viewer, 'list_view') and self.viewer.list_view:
                    if hasattr(self.viewer.list_view, '_stop_hover_playback'):
                        try: self.viewer.list_view._stop_hover_playback(force=True)
                        except: pass
                self.viewer.clear_scene_content()
        except Exception as e:
            logging.error(f"Error stopping hover players: {e}")

        players_to_wait = []

        try:
            self.media_player.stop()
            self.media_player.setSource(QUrl())
            players_to_wait.append(self.media_player)
        except Exception as e:
            logging.error(f"Error stopping main player: {e}")
            
        try:
            if hasattr(self, 'viewer') and self.viewer:
                for view_name in ['grid_view', 'list_view']:
                    view = getattr(self.viewer, view_name, None)
                    if view:
                        if hasattr(view, 'hover_player') and view.hover_player:
                            try:
                                view.hover_player.stop()
                                view.hover_player.setSource(QUrl())
                                players_to_wait.append(view.hover_player)
                            except Exception:
                                pass
        except Exception as e:
            logging.error(f"Error gathering active hover players: {e}")
            
        # Ждем, пока оставшиеся плееры перейдут в состояние NoMedia (высвободят файлы)
        if players_to_wait:
            try:
                import time
                from PyQt6.QtMultimedia import QMediaPlayer
                from PyQt6.QtCore import QCoreApplication
                start_t = time.time()
                while (time.time() - start_t) < 0.5:
                    all_no_media = True
                    for p in players_to_wait:
                        try:
                            if p.mediaStatus() != QMediaPlayer.MediaStatus.NoMedia:
                                all_no_media = False
                                break
                        except Exception:
                            pass
                    if all_no_media:
                        break
                    QCoreApplication.processEvents()
                    time.sleep(0.01)
            except Exception as e:
                logging.error(f"Error waiting for players NoMedia status: {e}")
            
        QApplication.processEvents()

    def move_current_file(self, destination_dir, start_time=None):
        import time
        if start_time is None:
            start_time = time.perf_counter()
        logging.info(f"[PROFILER] Начало move_current_file. Прошло времени: {(time.perf_counter() - start_time)*1000:.2f} ms")

        if not destination_dir or not os.path.exists(destination_dir): 
            logging.error(f"Destination not found: {destination_dir}")
            return
            
        if hasattr(self, 'move_thread') and self.move_thread and self.move_thread.isRunning():
            logging.debug("Move already in progress, skipping.")
            return

        # Определяем список файлов для перемещения
        if self.viewer.current_view_mode == 0:
            selected_paths = [self.current_file_path] if self.current_file_path else []
        else:
            selected_paths = self.viewer.get_selected_files()

        # Если в режиме Grid/List выделенных файлов нет, но открыт быстрый просмотр, берем файл из быстрого просмотра
        if not selected_paths and self.viewer.current_view_mode in (1, 2):
            active_view = self.viewer.grid_view if self.viewer.current_view_mode == 1 else self.viewer.list_view
            if hasattr(active_view, 'large_preview_popup') and active_view.large_preview_popup:
                popup = active_view.large_preview_popup
                if hasattr(popup, 'filepath') and popup.filepath:
                    selected_paths = [popup.filepath]

        if not selected_paths:
            return

        # Проверяем, все ли перемещаемые файлы являются изображениями
        is_only_images = True
        image_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.gif', '.tiff', '.tif', '.heic', '.avif', '.apng', '.jfif'}
        for path in selected_paths:
            ext = os.path.splitext(path)[1].lower()
            if ext not in image_extensions:
                is_only_images = False
                break

        is_single_file = (len(selected_paths) == 1)

        self._stop_all_media_players(is_only_images=is_only_images, is_single_file=is_single_file)

        pairs = []
        conflicts = []

        automation_cfg = AutomationConfig.load_config(destination_dir)

        for path in selected_paths:
            if not os.path.exists(path):
                continue
            original_filename = os.path.basename(path)
            name_no_ext, ext = os.path.splitext(original_filename)
            
            if automation_cfg and automation_cfg["enabled"]:
                template = automation_cfg["template"]
                collision = automation_cfg["collision"]
                try:
                    final_dest_path = TemplateEngine.get_unique_target(
                        destination_dir, template, original_filename, ext, collision
                    )
                except Exception as e:
                    logging.error(f"Automation Error: {e}", exc_info=True)
                    final_dest_path = os.path.join(destination_dir, original_filename)
            else:
                final_dest_path = os.path.join(destination_dir, original_filename)
                
            if os.path.exists(final_dest_path) and os.path.normpath(final_dest_path) != os.path.normpath(path):
                conflicts.append((path, final_dest_path))
            else:
                pairs.append((path, final_dest_path))

        # Разрешение конфликтов имен
        if conflicts:
            if len(selected_paths) == 1:
                # Для одного файла просто добавляем инкремент без показа диалога
                src, dst = conflicts[0]
                unique_dst = get_unique_filepath(os.path.dirname(dst), os.path.basename(src))
                if unique_dst:
                    pairs.append((src, unique_dst))
            else:
                # Для группы файлов показываем наш новый красивый диалог в стиле окна удаления
                dlg = MultiFileConflictDialog(conflicts, self)
                if dlg.exec():
                    if dlg.result_action == "rename":
                        for src, dst in conflicts:
                            unique_dst = get_unique_filepath(os.path.dirname(dst), os.path.basename(src))
                            if unique_dst:
                                pairs.append((src, unique_dst))
                    elif dlg.result_action == "skip":
                        pass
                    else:
                        self.show_current_file()
                        self.setFocus()
                        return
                else:
                    self.show_current_file()
                    self.setFocus()
                    return

        if not pairs:
            self.show_current_file()
            self.setFocus()
            return
        
        # Рассчитываем общий размер файлов
        total_size = 0
        for src, dst in pairs:
            try:
                if os.path.exists(src):
                    total_size += os.path.getsize(src)
            except:
                pass

        self.move_dlg = ProgressDialog("Подготовка к перемещению...", self)
        self.move_dlg.setup_for_transfer(len(pairs))

        # Показываем диалог сразу, если файлов > 1 или размер > 50 МБ
        if len(pairs) > 1 or total_size > 52428800:
            self.move_dlg.show()
            self.move_progress_timer = None
        else:
            self.move_progress_timer = QTimer()
            self.move_progress_timer.setSingleShot(True)
            self.move_progress_timer.setInterval(5000)
            self.move_progress_timer.timeout.connect(self.move_dlg.show)
            self.move_progress_timer.start()
        
        # Блокируем watcher перед запуском потока
        self._ignore_watcher = True
        
        # Запоминаем список перемещаемых файлов, чтобы блокировать предпросмотр
        from utils_io import strip_long_path_prefix
        if not hasattr(self, 'locked_files'):
            self.locked_files = set()
        self.locked_files.update(os.path.normpath(strip_long_path_prefix(src)) for src, dst in pairs)
        
        self.move_thread = MoveThread(pairs, start_time=start_time)
        self.move_thread.progress_update.connect(self.on_move_progress)
        self.move_thread.detailed_progress.connect(self.on_move_detailed_progress)
        self.move_thread.finished_move.connect(self.on_move_finished)
        logging.info(f"[PROFILER] Запуск MoveThread. Прошло времени: {(time.perf_counter() - start_time)*1000:.2f} ms")
        self.move_thread.start()

    def on_move_progress(self, current_idx, total, filename):
        if hasattr(self, 'move_dlg') and self.move_dlg:
            self.move_dlg.set_current_file(current_idx, filename)

    def on_move_detailed_progress(self, current_bytes, total_bytes, overall_bytes, overall_total_bytes):
        if hasattr(self, 'move_dlg') and self.move_dlg:
            self.move_dlg.update_bars(current_bytes, total_bytes, overall_bytes, overall_total_bytes)

    def on_move_finished(self, success, error_msg, succeeded_pairs, failed_pairs=None):
        import time
        start_time = getattr(self.move_thread, 'start_time', None)
        if start_time is None:
            start_time = time.perf_counter()
        logging.info(f"[PROFILER] on_move_finished запущен. Прошло времени: {(time.perf_counter() - start_time)*1000:.2f} ms")

        # Очищаем заблокированные файлы
        if hasattr(self, 'locked_files'):
            self.locked_files.clear()

        try:
            if hasattr(self, 'move_progress_timer') and self.move_progress_timer and self.move_progress_timer.isActive():
                self.move_progress_timer.stop()
            
            self._safe_close_dialog('move_dlg')
                
            if succeeded_pairs:
                history_entry = []
                for src, dst in succeeded_pairs:
                    src_dir = os.path.dirname(src)
                    dest_dir = os.path.dirname(dst)
                    file_size = 0
                    try: file_size = os.path.getsize(dst)
                    except: pass

                    # --- OPTIMISTIC UPDATE ---
                    DirCache.inst().optimistic_update(src_dir, -1, -file_size)
                    DirCache.inst().optimistic_update(dest_dir, 1, file_size)

                    history_entry.append((dst, src))

                self.history.append(history_entry)

                # Перестраиваем files_queue
                succeeded_src_rels = [safe_relpath(src, self.UNSORT_DIR) for src, dst in succeeded_pairs]
                succeeded_src_rels_set = set(strip_long_path_prefix(os.path.normpath(r)) for r in succeeded_src_rels)
                
                # Удаляем перемещенные файлы из RAM-кэша
                if hasattr(self, '_raw_dir_files') and self._raw_dir_files:
                    self._raw_dir_files = [
                        f for f in self._raw_dir_files 
                        if strip_long_path_prefix(os.path.normpath(f['rel_path'])) not in succeeded_src_rels_set
                    ]
                
                new_queue = []
                new_current_index = 0
                found_next = False
                
                for idx, rel_path in enumerate(self.files_queue):
                    norm_rel = strip_long_path_prefix(os.path.normpath(rel_path))
                    if norm_rel in succeeded_src_rels_set:
                        continue
                    new_queue.append(rel_path)
                    if not found_next and idx >= self.current_index:
                        new_current_index = len(new_queue) - 1
                        found_next = True
                        
                if not found_next:
                    new_current_index = len(new_queue) - 1 if new_queue else 0
                if new_current_index < 0:
                    new_current_index = 0
                    
                self.files_queue = new_queue
                self.current_index = new_current_index
                
                if not self.files_queue and getattr(self, '_raw_dir_files', []):
                    self.apply_local_filters_and_sorting(trigger_sync=True)
                    return
                    
                logging.info(f"[PROFILER] Шаг 1: optimistic_update и files_queue завершены. Прошло времени: {(time.perf_counter() - start_time)*1000:.2f} ms")
                
                # Refresh Sidebar styling to apply highlighting
                self.refresh_sidebar_styling()
                logging.info(f"[PROFILER] Шаг 2: refresh_sidebar_styling завершен. Прошло времени: {(time.perf_counter() - start_time)*1000:.2f} ms")
                
                # Update top labels for folder count/size
                if hasattr(self, 'lbl_unsort_count'): self.lbl_unsort_count.update_info()
                if hasattr(self, 'lbl_todel_count'): self.lbl_todel_count.update_info()
                
                # Синхронизируем очередь в UI точечно без полной перерисовки
                succeeded_srcs = [src for src, dst in succeeded_pairs]
                self.viewer.remove_files_from_view(succeeded_srcs)
                logging.info(f"[PROFILER] Шаг 3: remove_files_from_view завершен (плитка скрыта). Прошло времени: {(time.perf_counter() - start_time)*1000:.2f} ms")
                
                self.viewer.sync_active_index(self.current_index)
                
                if self.viewer.stack.currentIndex() == 0:
                    self.show_current_file()
                    logging.info(f"[PROFILER] Шаг 4: show_current_file (одиночный) завершен. Прошло времени: {(time.perf_counter() - start_time)*1000:.2f} ms")
                else:
                    self.on_selection_changed()
                    logging.info(f"[PROFILER] Шаг 4: on_selection_changed (плитки) завершен. Прошло времени: {(time.perf_counter() - start_time)*1000:.2f} ms")
            
            if not success:
                if failed_pairs:
                    # Показываем наше новое красивое окно ошибок перемещения в стиле окна удаления
                    dlg = MoveErrorsDialog(failed_pairs, self)
                    dlg.exec()
                else:
                    msg = error_msg if error_msg else AppContext.tr("msg_unknown_error")
                    QMessageBox.critical(self, AppContext.tr("err_title"), f"{AppContext.tr('msg_move_fail')}\n\n{msg}")
                if self.isVisible() and self.viewer.stack.currentIndex() == 0:
                    self.show_current_file()
        except Exception as e:
            logging.error(f"Error handling finished move: {e}", exc_info=True)
            QMessageBox.critical(self, AppContext.tr("err_title"), f"Error post-processing move: {e}")
        finally:
            # Разблокируем watcher с задержкой
            QTimer.singleShot(1000, lambda: setattr(self, '_ignore_watcher', False))
            self.setFocus()

    def delete_file(self):
        path_to_trash = getattr(self, 'session_trash_path', None)
        if not path_to_trash:
             path_to_trash = self.TO_DEL_DIR

        if path_to_trash and os.path.exists(path_to_trash):
            self.move_current_file(path_to_trash)
        else:
             QMessageBox.warning(self, AppContext.tr("err_title"), AppContext.tr("msg_trash_not_set"))

    def delete_files_permanently(self, file_paths):
        if not file_paths:
            return

        try:
            confirm_dlg = FileDeletionConfirmDialog(file_paths, self.viewer if hasattr(self, 'viewer') else self)
            if confirm_dlg.exec() != QDialog.DialogCode.Accepted:
                return

            self._stop_all_media_players()

            deleted_paths = []
            deleted_cache_updates = []
            for path in file_paths:
                long_p = ensure_long_path(path)
                if not os.path.exists(long_p):
                    continue
                try:
                    file_size = 0
                    if os.path.isfile(long_p):
                        file_size = os.path.getsize(long_p)
                        
                    success = QFile.moveToTrash(long_p)
                    # QFile.moveToTrash returns (bool, str) on Windows in PyQt6, or bool on other platforms
                    trash_ok = success[0] if isinstance(success, tuple) else bool(success)
                    if not trash_ok:
                        if os.path.isdir(long_p):
                            shutil.rmtree(long_p)
                        else:
                            os.remove(long_p)
                            
                    deleted_paths.append(path)
                    deleted_cache_updates.append((os.path.dirname(path), file_size))
                    logging.info(f"[Files] Файл удален: {path}")
                except Exception as e:
                    logging.error(f"[Files] Не удалось удалить файл '{path}': {e}", exc_info=True)
                    
            if not deleted_paths:
                return
                
            for parent_dir, file_size in deleted_cache_updates:
                from logic_cache import DirCache
                DirCache.inst().optimistic_update(parent_dir, -1, -file_size)
                
            norm_deleted_set = set(strip_long_path_prefix(os.path.normpath(p)) for p in deleted_paths)
            
            # Удаляем удаленные файлы из RAM-кэша виртуальной папки
            if hasattr(self, '_raw_dir_files') and self._raw_dir_files:
                self._raw_dir_files = [
                    f for f in self._raw_dir_files 
                    if strip_long_path_prefix(os.path.normpath(f['rel_path'])) not in norm_deleted_set
                ]
            
            new_queue = []
            found_next = False
            new_current_index = self.current_index
            
            for idx, rel_path in enumerate(self.files_queue):
                full_path = strip_long_path_prefix(os.path.normpath(os.path.join(self.UNSORT_DIR, rel_path)))
                if full_path in norm_deleted_set:
                    continue
                new_queue.append(rel_path)
                if not found_next and idx >= self.current_index:
                    new_current_index = len(new_queue) - 1
                    found_next = True
                    
            if not found_next:
                new_current_index = len(new_queue) - 1 if new_queue else 0
            if new_current_index < 0:
                new_current_index = 0
                
            self.files_queue = new_queue
            self.current_index = new_current_index
            
            if not self.files_queue and getattr(self, '_raw_dir_files', []):
                self.apply_local_filters_and_sorting(trigger_sync=True)
                return
            
            # Update top labels for folder count/size
            if hasattr(self, 'lbl_unsort_count'): self.lbl_unsort_count.update_info()
            if hasattr(self, 'lbl_todel_count'): self.lbl_todel_count.update_info()
            
            # Обновляем UI
            self.viewer.remove_files_from_view(deleted_paths)
            self.viewer.sync_active_index(self.current_index)
            
            if hasattr(self, 'viewer') and hasattr(self.viewer, 'stack') and self.viewer.stack.currentIndex() == 0:
                self.show_current_file()
            else:
                self.on_selection_changed()
        except Exception as e:
            logging.error(f"Error during permanent deletion: {e}", exc_info=True)
            QMessageBox.critical(self, AppContext.tr("err_title"), f"Error during deletion: {e}")

    def next_file(self):
        if self.files_queue:
            self.current_index = (self.current_index + 1) % len(self.files_queue)
            self.show_current_file()
        self.setFocus()

    def prev_file(self):
        if self.files_queue:
            self.current_index = (self.current_index - 1) % len(self.files_queue)
            self.show_current_file()
        self.setFocus()

    def move_up(self):
        if hasattr(self, 'viewer'):
            self.viewer.navigate_vertical(-1)
        self.setFocus()

    def move_down(self):
        if hasattr(self, 'viewer'):
            self.viewer.navigate_vertical(1)
        self.setFocus()

    def undo_action(self) -> None:
        if not self.history: return
        action = self.history.pop()
        
        if isinstance(action, tuple) and len(action) == 2 and isinstance(action[0], str):
            pairs = [action]
        else:
            pairs = action  # list of (dest_path, orig_path)
            
        if not pairs:
            return
            
        succeeded = []
        try:
            self._stop_all_media_players()
            from PyQt6.QtCore import QThreadPool
            QThreadPool.globalInstance().waitForDone(1000)
            QApplication.processEvents()

            # Блокируем watcher
            self._ignore_watcher = True

            resolved_pairs = []
            total_size = 0
            for current_loc, original_loc in reversed(pairs):
                long_curr = ensure_long_path(current_loc)
                long_orig = ensure_long_path(original_loc)
                if os.path.exists(long_curr):
                    os.makedirs(os.path.dirname(long_orig), exist_ok=True)
                    
                    if os.path.exists(long_orig):
                        base, ext = os.path.splitext(original_loc)
                        counter = 1
                        target_path = original_loc
                        long_target = ensure_long_path(target_path)
                        while os.path.exists(long_target):
                            target_path = f"{base}_undo_{counter}{ext}"
                            long_target = ensure_long_path(target_path)
                            counter += 1
                    else:
                        target_path = original_loc
                        long_target = long_orig
                    
                    file_size = os.path.getsize(long_curr)
                    resolved_pairs.append((long_curr, long_target))
                    total_size += file_size
                    
            if not resolved_pairs:
                self._ignore_watcher = False
                return
                
            self.undo_dlg = ProgressDialog("Отмена перемещения...", self)
            self.undo_dlg.setup_for_transfer(len(resolved_pairs))

            if len(resolved_pairs) > 1 or total_size > 52428800:
                self.undo_dlg.show()
                self.undo_progress_timer = None
            else:
                self.undo_progress_timer = QTimer()
                self.undo_progress_timer.setSingleShot(True)
                self.undo_progress_timer.setInterval(5000)
                self.undo_progress_timer.timeout.connect(self.undo_dlg.show)
                self.undo_progress_timer.start()

            from utils_io import strip_long_path_prefix
            if not hasattr(self, 'locked_files'):
                self.locked_files = set()
            self.locked_files.update(os.path.normpath(strip_long_path_prefix(src)) for src, dst in resolved_pairs)

            import time
            self.undo_thread = MoveThread(resolved_pairs, start_time=time.perf_counter())
            self.undo_thread.progress_update.connect(lambda c, t, f: self.undo_dlg.set_current_file(c, f) if hasattr(self, 'undo_dlg') and self.undo_dlg else None)
            self.undo_thread.detailed_progress.connect(lambda c, t, o, ot: self.undo_dlg.update_bars(c, t, o, ot) if hasattr(self, 'undo_dlg') and self.undo_dlg else None)
            self.undo_thread.finished_move.connect(self.on_undo_finished)
            self.undo_thread.start()

        except Exception as e:
            logging.error(f"Undo setup error: {e}", exc_info=True)
            QMessageBox.critical(self, AppContext.tr("err_title"), AppContext.tr("msg_undo_fail") + f"\n{e}")
            self.history.append(action)
            QTimer.singleShot(1000, lambda: setattr(self, '_ignore_watcher', False))

    def on_undo_finished(self, success, error_msg, succeeded_pairs, failed_pairs=None):
        if hasattr(self, 'locked_files'):
            self.locked_files.clear()
            
        try:
            if hasattr(self, 'undo_progress_timer') and self.undo_progress_timer and self.undo_progress_timer.isActive():
                self.undo_progress_timer.stop()
            self._safe_close_dialog('undo_dlg')
            
            succeeded = []
            for src, dst in succeeded_pairs:
                try:
                    file_size = os.path.getsize(ensure_long_path(dst))
                except:
                    file_size = 0
                succeeded.append((src, dst, file_size))
                
            if succeeded:
                # Обновляем кэш статистики
                for current_loc, target_path, file_size in succeeded:
                    src_dir = os.path.dirname(current_loc)
                    dest_dir = os.path.dirname(target_path)
                    DirCache.inst().optimistic_update(src_dir, -1, -file_size)
                    DirCache.inst().optimistic_update(dest_dir, 1, file_size)

                # Удаляем старые переименованные пути из RAM-кэша и UI
                current_locs_to_remove = []
                for current_loc, target_path, file_size in succeeded:
                    try:
                        long_curr = ensure_long_path(current_loc)
                        long_unsort = ensure_long_path(self.UNSORT_DIR)
                        rel_current = safe_relpath(long_curr, long_unsort)
                        if not rel_current.startswith('..') and not os.path.isabs(rel_current):
                            current_locs_to_remove.append(current_loc)
                    except Exception:
                        pass
                
                if current_locs_to_remove:
                    self.viewer.remove_files_from_view(current_locs_to_remove)
                    if hasattr(self, '_raw_dir_files') and self._raw_dir_files:
                        long_unsort = ensure_long_path(self.UNSORT_DIR)
                        norm_removes = {os.path.normpath(safe_relpath(p, long_unsort)) for p in current_locs_to_remove}
                        self._raw_dir_files = [f for f in self._raw_dir_files if os.path.normpath(f['rel_path']) not in norm_removes]

                if not hasattr(self, '_raw_dir_files') or self._raw_dir_files is None:
                    self._raw_dir_files = []
                
                # Добавляем в RAM-кэш восстановленные файлы
                existing_rels = {os.path.normpath(f['rel_path']) for f in self._raw_dir_files}
                for current_loc, target_path, file_size in succeeded:
                    long_target = ensure_long_path(target_path)
                    long_unsort = ensure_long_path(self.UNSORT_DIR)
                    rel_path = safe_relpath(long_target, long_unsort)
                    norm_rel = os.path.normpath(rel_path)
                    if norm_rel not in existing_rels:
                        try:
                            stat = os.stat(long_target)
                            mtime = stat.st_mtime
                            ctime = stat.st_ctime
                        except Exception:
                            mtime = 0.0
                            ctime = 0.0
                        self._raw_dir_files.append({
                            'rel_path': rel_path,
                            'size': file_size,
                            'mtime': mtime,
                            'ctime': ctime
                        })
                
                # Применяем фильтры и сортировку в памяти без перерисовки UI
                self.apply_local_filters_and_sorting(trigger_sync=False)
                
                # Обновляем структуру дерева в сайдбаре, чтобы счетчики категорий были точными
                self.reload_categories_ui()
                self.refresh_sidebar_styling()
                
                # Синхронизируем UI с учетом группировки
                main_app = self.viewer.get_main_app()
                group_enabled = main_app.config.get("group_by_sort", False) if main_app and hasattr(main_app, 'config') else False
                
                first_target_rel = safe_relpath(succeeded[0][1], self.UNSORT_DIR)
                if first_target_rel in self.files_queue:
                    self.current_index = self.files_queue.index(first_target_rel)
                else:
                    self.current_index = 0
                
                if group_enabled:
                    self.viewer.sync_files_queue(self.UNSORT_DIR, self.files_queue, self.current_index, silent=True)
                    if self.viewer.stack.currentIndex() == 0:
                        self.show_current_file()
                    else:
                        self.on_selection_changed()
                else:
                    files_to_insert = []
                    for current_loc, target_path, file_size in succeeded:
                        rel_path = safe_relpath(target_path, self.UNSORT_DIR)
                        if rel_path in self.files_queue:
                            idx = self.files_queue.index(rel_path)
                            files_to_insert.append((target_path, idx))
                            
                    if files_to_insert:
                        files_to_insert.sort(key=lambda x: x[1])
                        self.viewer.insert_files_into_view(files_to_insert)
                        self.viewer.sync_active_index(self.current_index)
                        if self.viewer.stack.currentIndex() == 0:
                            self.show_current_file()
                        else:
                            self.on_selection_changed()
                
            if not success:
                logging.error(f"Undo thread error: {error_msg}")
                if failed_pairs:
                    from ui_dialogs_generic import MoveErrorsDialog
                    err_dlg = MoveErrorsDialog(failed_pairs, self)
                    err_dlg.exec()
        finally:
            QTimer.singleShot(1000, lambda: setattr(self, '_ignore_watcher', False))
            
        self.setFocus()

    def on_affix_click(self, btn_type: str, payload: str, btn_widget: object = None) -> None:
        if self.viewer.stack.currentIndex() == 0:
            # Одиночный режим просмотра
            if not self.current_file_path or not os.path.exists(self.current_file_path):
                return
            
            from utils_io import strip_long_path_prefix
            norm_path = os.path.normpath(strip_long_path_prefix(self.current_file_path))
            if hasattr(self, 'locked_files') and norm_path in self.locked_files:
                return

            selected = [self.current_file_path]
        else:
            # Режимы Grid/List (множественный выбор)
            selected = self.viewer.get_selected_files()
            if not selected:
                return
            if len(selected) > 40:
                return

        # ЗАЩИТА: Если перемещение/переименование уже идет, игнорируем
        if hasattr(self, 'move_thread') and self.move_thread and self.move_thread.isRunning():
            return

        template = payload
        errors = []
        simulated_counters = self.session_counters.copy()
        target_paths = {}
        new_paths_set = set()
        
        # Виртуальная симуляция (Dry Run)
        for old_path in selected:
            if not os.path.exists(old_path):
                errors.append(f"Файл не существует: {old_path}")
                continue
                
            current_dir = os.path.dirname(old_path)
            old_filename = os.path.basename(old_path)
            name_no_ext, ext = os.path.splitext(old_filename)
            
            current_seq_count = simulated_counters.get(template, 0) + 1
            simulated_counters[template] = current_seq_count
            
            if "%dell" in template:
                final_template = template
            else:
                mode = self.affix_window.get_mode()
                sep = self.config.get("affix_separator", "_")
                if mode == "prefix":
                    final_template = f"{template}{sep}%name"
                else:
                    final_template = f"%name{sep}{template}"
                    
            parent_name = os.path.basename(current_dir)
            clean_template = final_template
            match_dell = re.match(r'^%dell\[(.*)\]$', final_template)
            if match_dell:
                clean_template = match_dell.group(1)
            elif "%dell" in final_template:
                clean_template = final_template.replace("%dell", "")
                
            base_name = TemplateEngine.parse_template(clean_template, old_filename, parent_name, iterator=current_seq_count)
            
            # 1. Проверка на запрещенные символы в имени
            forbidden_chars = [c for c in r'\/:*?"<>|' if c in base_name]
            if forbidden_chars:
                forbidden_str = "".join(forbidden_chars)
                errors.append(f"Файл '{old_filename}': имя '{base_name}' содержит запрещенные символы: {forbidden_str}")
                continue
                
            # Целевой путь
            new_path = os.path.join(current_dir, base_name + ext)
            new_path_norm = os.path.normpath(new_path)
            old_path_norm = os.path.normpath(old_path)
            
            # 2. Проверка на дублирование в пакете
            if new_path_norm in new_paths_set:
                errors.append(f"Файл '{old_filename}': имя '{base_name + ext}' дублируется в пакете переименования")
                continue
                
            # 3. Проверка на существование файла на диске
            if new_path_norm != old_path_norm and os.path.exists(new_path):
                errors.append(f"Файл '{old_filename}': целевой файл уже существует: {os.path.basename(new_path)}")
                continue
                
            target_paths[old_path] = new_path
            new_paths_set.add(new_path_norm)

        # Вывод предупреждений
        if errors:
            if btn_widget and hasattr(self, 'animate_conflict_button'):
                self.animate_conflict_button(btn_widget)
                
            # Показываем красивый диалог со скроллируемым списком всех ошибок
            dlg = BatchRenameErrorsDialog(errors, self)
            dlg.exec()
            return

        any_changes = any(os.path.normpath(op) != os.path.normpath(np) for op, np in target_paths.items())
        if not any_changes:
            return

        # Физическое переименование
        if self.current_file_path and self.current_file_path in target_paths:
            self.media_player.stop()
            self.media_player.setSource(QUrl())
            self.viewer.clear_scene_content()
            QApplication.processEvents()

        self._ignore_watcher = True
        rename_pairs = []
        try:
            for old_path, new_path in target_paths.items():
                if os.path.normpath(old_path) == os.path.normpath(new_path):
                    continue
                os.rename(old_path, new_path)
                rename_pairs.append((new_path, old_path))
                
            # Сохраняем в историю одной операцией
            self.history.append(rename_pairs)
            self.session_counters = simulated_counters
            
            # Обновляем RAM-кэш и UI
            for new_path, old_path in rename_pairs:
                rel_old = safe_relpath(old_path, self.UNSORT_DIR)
                rel_new = safe_relpath(new_path, self.UNSORT_DIR)
                
                # Обновляем files_queue
                if rel_old in self.files_queue:
                    idx = self.files_queue.index(rel_old)
                    self.files_queue[idx] = rel_new
                    
                # Обновляем _raw_dir_files
                if hasattr(self, '_raw_dir_files') and self._raw_dir_files:
                    for f_info in self._raw_dir_files:
                        if os.path.normpath(f_info['rel_path']) == os.path.normpath(rel_old):
                            f_info['rel_path'] = rel_new
                            try:
                                stat = os.stat(new_path)
                                f_info['size'] = stat.st_size
                                f_info['mtime'] = stat.st_mtime
                                f_info['ctime'] = stat.st_ctime
                            except Exception:
                                pass
                            break
                            
                self.viewer.update_file_path_in_view(old_path, new_path)

            if self.current_file_path and self.current_file_path in target_paths:
                self.current_file_path = target_paths[self.current_file_path]
                self.lbl_filename.setText(os.path.basename(self.current_file_path))
                
            if self.viewer.stack.currentIndex() == 0:
                self.show_current_file()
            else:
                self.on_selection_changed()
                
        except Exception as e:
            logging.error(f"Affix batch rename error: {e}", exc_info=True)
            # Откат в случае частичной ошибки на диске
            for np, op in reversed(rename_pairs):
                try:
                    os.rename(np, op)
                except Exception:
                    pass
            QMessageBox.critical(self, AppContext.tr("err_title"), f"{AppContext.tr('msg_rename_affix_err')} {e}")
            if self.viewer.stack.currentIndex() == 0:
                self.show_current_file()
        finally:
            QTimer.singleShot(1000, lambda: setattr(self, '_ignore_watcher', False))

    def create_category(self):
        if not self.SORT_DIR or not os.path.exists(self.SORT_DIR): 
            logging.error("Root sort dir missing.")
            return

        dlg = SmartNameDialog("dlg_new_cat_title", "dlg_enter_name", self.SORT_DIR, "", self)
        if dlg.exec() and dlg.final_name:
            path = os.path.join(self.SORT_DIR, dlg.final_name)
            try:
                self._ignore_watcher = True
                os.makedirs(path, exist_ok=True)
                self.reload_categories_ui()
                self.update_watcher_paths() 
            except Exception as e:
                QMessageBox.critical(self, AppContext.tr("err_title"), f"{AppContext.tr('msg_create_cat_fail')} {e}")
            finally:
                QTimer.singleShot(1000, lambda: setattr(self, '_ignore_watcher', False))
        self.setFocus()

    def reload_categories_ui(self):
        pass

    def update_sort_order(self, parent_path, filename, new_index):
        try:
            norm_parent = os.path.normpath(parent_path)
            items = []
            
            if norm_parent in self.custom_orders: 
                items = self.custom_orders[norm_parent]
            else:
                try: 
                    items = [d for d in os.listdir(parent_path) if os.path.isdir(os.path.join(parent_path, d))]
                    items = sorted(items)
                except: 
                    items = []
            
            if filename in items: items.remove(filename)
            if new_index < 0: new_index = 0
            if new_index > len(items): new_index = len(items)
            items.insert(new_index, filename)
            self.custom_orders[norm_parent] = items
            self.reload_categories_ui()
        except Exception as e:
            logging.error(f"Sort order update error: {e}", exc_info=True)



        # ЗАЩИТА: Если перемещение/переименование уже идет, игнорируем
        if hasattr(self, 'move_thread') and self.move_thread and self.move_thread.isRunning():
            return

        template = payload
        errors = []
        simulated_counters = self.session_counters.copy()
        target_paths = {}
        new_paths_set = set()
        
        # Виртуальная симуляция (Dry Run)
        for old_path in selected:
            if not os.path.exists(old_path):
                errors.append(f"Файл не существует: {old_path}")
                continue
                
            current_dir = os.path.dirname(old_path)
            old_filename = os.path.basename(old_path)
            name_no_ext, ext = os.path.splitext(old_filename)
            
            current_seq_count = simulated_counters.get(template, 0) + 1
            simulated_counters[template] = current_seq_count
            
            if "%dell" in template:
                final_template = template
            else:
                mode = self.affix_window.get_mode()
                sep = self.config.get("affix_separator", "_")
                if mode == "prefix":
                    final_template = f"{template}{sep}%name"
                else:
                    final_template = f"%name{sep}{template}"
                    
            parent_name = os.path.basename(current_dir)
            clean_template = final_template
            match_dell = re.match(r'^%dell\[(.*)\]$', final_template)
            if match_dell:
                clean_template = match_dell.group(1)
            elif "%dell" in final_template:
                clean_template = final_template.replace("%dell", "")
                
            base_name = TemplateEngine.parse_template(clean_template, old_filename, parent_name, iterator=current_seq_count)
            
            # 1. Проверка на запрещенные символы в имени
            forbidden_chars = [c for c in r'\/:*?"<>|' if c in base_name]
            if forbidden_chars:
                forbidden_str = "".join(forbidden_chars)
                errors.append(f"Файл '{old_filename}': имя '{base_name}' содержит запрещенные символы: {forbidden_str}")
                continue
                
            # Целевой путь
            new_path = os.path.join(current_dir, base_name + ext)
            new_path_norm = os.path.normpath(new_path)
            old_path_norm = os.path.normpath(old_path)
            
            # 2. Проверка на дублирование в пакете
            if new_path_norm in new_paths_set:
                errors.append(f"Файл '{old_filename}': имя '{base_name + ext}' дублируется в пакете переименования")
                continue
                
            # 3. Проверка на существование файла на диске
            if new_path_norm != old_path_norm and os.path.exists(new_path):
                errors.append(f"Файл '{old_filename}': целевой файл уже существует: {os.path.basename(new_path)}")
                continue
                
            target_paths[old_path] = new_path
            new_paths_set.add(new_path_norm)

        # Вывод предупреждений
        if errors:
            if btn_widget and hasattr(self, 'animate_conflict_button'):
                self.animate_conflict_button(btn_widget)
                
            # Показываем красивый диалог со скроллируемым списком всех ошибок
            dlg = BatchRenameErrorsDialog(errors, self)
            dlg.exec()
            return

        any_changes = any(os.path.normpath(op) != os.path.normpath(np) for op, np in target_paths.items())
        if not any_changes:
            return

        # Физическое переименование
        if self.current_file_path and self.current_file_path in target_paths:
            self.media_player.stop()
            self.media_player.setSource(QUrl())
            self.viewer.clear_scene_content()
            QApplication.processEvents()

        self._ignore_watcher = True
        rename_pairs = []
        try:
            for old_path, new_path in target_paths.items():
                if os.path.normpath(old_path) == os.path.normpath(new_path):
                    continue
                os.rename(old_path, new_path)
                rename_pairs.append((new_path, old_path))
                
            # Сохраняем в историю одной операцией
            self.history.append(rename_pairs)
            self.session_counters = simulated_counters
            
            # Обновляем RAM-кэш и UI
            for new_path, old_path in rename_pairs:
                rel_old = safe_relpath(old_path, self.UNSORT_DIR)
                rel_new = safe_relpath(new_path, self.UNSORT_DIR)
                
                # Обновляем files_queue
                if rel_old in self.files_queue:
                    idx = self.files_queue.index(rel_old)
                    self.files_queue[idx] = rel_new
                    
                # Обновляем _raw_dir_files
                if hasattr(self, '_raw_dir_files') and self._raw_dir_files:
                    for f_info in self._raw_dir_files:
                        if os.path.normpath(f_info['rel_path']) == os.path.normpath(rel_old):
                            f_info['rel_path'] = rel_new
                            try:
                                stat = os.stat(new_path)
                                f_info['size'] = stat.st_size
                                f_info['mtime'] = stat.st_mtime
                                f_info['ctime'] = stat.st_ctime
                            except Exception:
                                pass
                            break
                            
                self.viewer.update_file_path_in_view(old_path, new_path)

            if self.current_file_path and self.current_file_path in target_paths:
                self.current_file_path = target_paths[self.current_file_path]
                self.lbl_filename.setText(os.path.basename(self.current_file_path))
                
            if self.viewer.stack.currentIndex() == 0:
                self.show_current_file()
            else:
                self.on_selection_changed()
                
        except Exception as e:
            logging.error(f"Affix batch rename error: {e}", exc_info=True)
            # Откат в случае частичной ошибки на диске
            for np, op in reversed(rename_pairs):
                try:
                    os.rename(np, op)
                except Exception:
                    pass
            QMessageBox.critical(self, AppContext.tr("err_title"), f"{AppContext.tr('msg_rename_affix_err')} {e}")
            if self.viewer.stack.currentIndex() == 0:
                self.show_current_file()
        finally:
            QTimer.singleShot(1000, lambda: setattr(self, '_ignore_watcher', False))

    def create_category(self):
        if not self.SORT_DIR or not os.path.exists(self.SORT_DIR): 
            logging.error("Root sort dir missing.")
            return

        dlg = SmartNameDialog("dlg_new_cat_title", "dlg_enter_name", self.SORT_DIR, "", self)
        if dlg.exec() and dlg.final_name:
            path = os.path.join(self.SORT_DIR, dlg.final_name)
            try:
                self._ignore_watcher = True
                os.makedirs(path, exist_ok=True)
                self.reload_categories_ui()
                self.update_watcher_paths() 
            except Exception as e:
                QMessageBox.critical(self, AppContext.tr("err_title"), f"{AppContext.tr('msg_create_cat_fail')} {e}")
            finally:
                QTimer.singleShot(1000, lambda: setattr(self, '_ignore_watcher', False))
        self.setFocus()

    def reload_categories_ui(self):
        pass

    def update_sort_order(self, parent_path, filename, new_index):
        try:
            norm_parent = os.path.normpath(parent_path)
            items = []
            
            if norm_parent in self.custom_orders: 
                items = self.custom_orders[norm_parent]
            else:
                try: items = sorted(os.listdir(parent_path))
                except: items = []
            
            if filename in items: items.remove(filename)
            if new_index < 0: new_index = 0
            if new_index > len(items): new_index = len(items)
            items.insert(new_index, filename)
            self.custom_orders[norm_parent] = items
            self.reload_categories_ui()
        except Exception as e:
            logging.error(f"Sort order update error: {e}", exc_info=True)



    def open_current_file_system(self):
        if self.current_file_path and os.path.exists(self.current_file_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.current_file_path))

    def reveal_current_file_in_explorer(self):
        if self.current_file_path and os.path.exists(self.current_file_path):
            from utils_common import reveal_in_explorer
            reveal_in_explorer(self.current_file_path)
