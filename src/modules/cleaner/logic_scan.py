import os
from typing import Any
from config import AppContext
from utils_common import format_size, format_compact_count
from .workers import DuplicateFinderWorker, ExtensionScannerWorker, STAGE_ANALYSIS, STAGE_SCANNING, SimilarScanWorker
from .ui_dialogs import MatrixFilterDialog

class ScanMixin:
    def toggle_scan(self) -> None:
        if self.finder and self.finder.isRunning():
            self.was_stopped_manually = True
            self.finder.stop()
            if hasattr(self, 'btn_abort') and self.btn_abort:
                self.btn_abort.setText(AppContext.tr("cln_btn_stopping"))
                self.btn_abort.setEnabled(False)
            if hasattr(self, 'btn_stop_scan') and self.btn_stop_scan:
                self.btn_stop_scan.setEnabled(False)
        else:
            self.start_scan()

    def create_dump(self):
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        from .workers import CreateDumpWorker
        
        folders = list(self.source_folders.keys())
        if not folders: return
        
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить дамп", "", "Media Keeper Dump (*.mkdump)")
        if not path: return
        
        self.overlay.start_loading_mode(0)
        self.overlay.lbl_title.setText("Создание дампа...")
        self.overlay.btn_stop.hide()
        
        self.dump_worker = CreateDumpWorker(folders, path, use_cache=True)
        # We can reuse on_progress
        self.dump_worker.progress.connect(self.on_progress)
        self.dump_worker.finished.connect(self._on_dump_finished)
        self.dump_worker.start()

    def _on_dump_finished(self, success: bool, error: str):
        self.overlay.hide()
        from PyQt6.QtWidgets import QMessageBox
        if success:
            QMessageBox.information(self, "Готово", "Дамп успешно создан!")
        else:
            QMessageBox.warning(self, "Ошибка", f"Не удалось создать дамп: {error}")

    def reset_scan(self) -> None:
        if self.finder and self.finder.isRunning():
            self.was_reset_manually = True
            self.finder.stop()
            if hasattr(self, 'btn_stop_scan') and self.btn_stop_scan:
                self.btn_stop_scan.setText(AppContext.tr("cln_btn_stopping"))
                self.btn_stop_scan.setEnabled(False)
            if hasattr(self, 'btn_abort') and self.btn_abort:
                self.btn_abort.setEnabled(False)

    def start_scan(self) -> None:
        if not self.source_folders: return
        self.settings_panel.scan_stale = False
        self.settings_panel.validate_size_inputs()
        self.virtual_model.set_items([], {})
        self.session_db.clear_db() 
        self.preview_widget.show_empty("...") 
        
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        self.last_valid_percent = 0.0 
        self.was_stopped_manually = False
        self.was_reset_manually = False
        
        # Динамически перестраиваем кнопки на время сканирования в ui_main
        if hasattr(self, 'setup_scan_buttons'):
            self.setup_scan_buttons()
        
        self.settings_panel.val_scanned.setText("0")
        self.settings_panel.val_wasted.setText("0 B")
        self.settings_panel.val_time.setText("00:00.000")
        
        self.settings_panel.lbl_percent.setText("0%")
        self.settings_panel.lbl_percent.setStyleSheet("color: #cccccc; font-size: 13px; font-weight: bold; margin-right: 5px;")
        self.settings_panel.lbl_percent.setToolTip("")
        self.settings_panel.lbl_percent.show()
        
        self.settings_panel.btn_duples.setText("0")
        self.settings_panel.btn_duples.set_mode('disabled')
        self.settings_panel.btn_zero.setText("0")
        self.settings_panel.btn_zero.set_mode('disabled')
        self.settings_panel.btn_empty.setText("0")
        self.settings_panel.btn_empty.set_mode('disabled')
        
        self.last_scanned_count = 0 
        
        self.scan_timer.start()
        self.ui_timer.start()
        
        folders = list(self.source_folders.keys())
        use_cache = self.settings_panel.chk_cache.isChecked()
        size_limits = self.settings_panel.get_size_limits()
        
        # Find reference folder
        reference_path = None
        for path, data in self.source_folders.items():
            if data.get('reference'):
                reference_path = path
                break
        
        if self.current_tab == 1:
            media_type = self.settings_panel.combo_media_type.currentIndex()
            threshold = self.settings_panel.spin_similarity.value()
            res_idx = self.settings_panel.combo_resolution.currentIndex()
            hash_size = 3 if res_idx == 0 else (8 if res_idx == 1 else (16 if res_idx == 2 else (32 if res_idx == 3 else 64)))
            
            # Чтение алгоритма и фильтра монотонности
            alg_idx = self.settings_panel.combo_algorithm.currentIndex()
            algorithm = "phash" if alg_idx == 0 else ("dhash" if alg_idx == 1 else "ahash")
            monotone_filter = self.settings_panel.chk_monotone.isChecked()
            
            self.finder = SimilarScanWorker(
                self.source_folders, use_cache, self.filter_config, 
                size_limits=size_limits, media_type=media_type, 
                threshold=threshold, hash_size=hash_size,
                algorithm=algorithm, monotone_filter=monotone_filter
            )
        else:
            safe_scan = self.settings_panel.chk_safe_scan.isChecked()
            self.finder = DuplicateFinderWorker(folders, use_cache, self.filter_config, size_limits=size_limits, safe_scan=safe_scan)
            
        if reference_path:
            self.finder.reference_path = reference_path
            
        self.finder.progress.connect(self.on_progress)
        self.finder.finished.connect(self.on_scan_finished)
        self.finder.start()

    def on_progress(self, stage: int, percent: float, msg: str, scanned: int, matches: int, wasted_bytes: int, scanned_bytes: int, zero_count: int, empty_count: int) -> None:
        self.settings_panel.set_current_path(msg)
        if percent >= 0: 
            self.progress_bar.setValue(int(percent))
            self.last_valid_percent = float(percent)
            self.settings_panel.lbl_percent.setText(f"{percent:.2f}%")
            
        size_fmt = format_size(scanned_bytes)
        self.settings_panel.val_scanned.setText(f"{scanned} ({size_fmt})")
        
        if stage == STAGE_ANALYSIS:
            self.settings_panel.val_wasted.setText(format_size(wasted_bytes))
            
        # matches — это количество лишних копий. 
        # В среднем количество групп равно числу копий, а общее число файлов в них — числу копий * 2.
        g_compact = format_compact_count(matches)
        d_compact = format_compact_count(matches * 2)
        self.settings_panel.btn_duples.setText(f"{g_compact} ({d_compact})")
        if matches > 0: self.settings_panel.btn_duples.set_mode('available')
        
        self.settings_panel.btn_zero.setText(str(zero_count))
        if zero_count > 0: self.settings_panel.btn_zero.set_mode('available')
        
        self.settings_panel.btn_empty.setText(str(empty_count))
        if empty_count > 0: self.settings_panel.btn_empty.set_mode('available')
        
        self.last_scanned_count = scanned

    def on_scan_finished(self, results: dict[str, Any]) -> None:
        self.ui_timer.stop()
        self.update_timer_label()
        self.settings_panel.set_current_path("") # Сбрасываем динамический путь
        
        # Сбрасываем фильтры по типам для новых результатов
        self.view_filter_exts = None
        self.view_filter_mode = 'include'
        if hasattr(self, 'virtual_model_dupes') and self.virtual_model_dupes:
            self.virtual_model_dupes.set_filter(None, 'include')
        if hasattr(self, 'virtual_model_similar') and self.virtual_model_similar:
            self.virtual_model_similar.set_filter(None, 'include')
            
        from config import AppContext
        if hasattr(self, 'btn_types_dupes') and self.btn_types_dupes:
            self.btn_types_dupes.setText(AppContext.tr("cln_btn_types"))
        if hasattr(self, 'btn_types_similar') and self.btn_types_similar:
            self.btn_types_similar.setText(AppContext.tr("cln_btn_types"))

        # Восстанавливаем кнопки в UI
        if hasattr(self, 'restore_scan_buttons'):
            self.restore_scan_buttons()

        if getattr(self, 'was_reset_manually', False):
            self.settings_panel.lbl_percent.setText("")
            self.settings_panel.lbl_percent.hide()
            self.progress_bar.hide()
            self.session_db.clear_db()
            self.virtual_model.set_items([], {})
            self.update_view_stats()
            return

        if self.was_stopped_manually:
            final_text = f"{self.last_valid_percent:.2f}%"
            style = "color: #ef4444; font-size: 13px; font-weight: bold; margin-right: 5px;" 
            tooltip = AppContext.tr("cln_tip_scan_stopped")
        else:
            final_text = "100.00%"
            style = "color: #10b981; font-size: 13px; font-weight: bold; margin-right: 5px;" 
            tooltip = AppContext.tr("cln_tip_scan_finished")

        self.settings_panel.lbl_percent.setText(final_text)
        self.settings_panel.lbl_percent.setStyleSheet(style)
        self.settings_panel.lbl_percent.setToolTip(tooltip)
        self.settings_panel.lbl_percent.show()
        
        self.progress_bar.hide()
        self.update_cache_info()
        
        groups = results['groups']
        zero_files = results['zero_files']
        empty_folders = results['empty_folders']
        
        # Общее количество файлов дубликатов во всех группах
        total_files = sum(len(g['files']) for g in groups)
        
        g_compact = format_compact_count(len(groups))
        d_compact = format_compact_count(total_files)
        
        self.settings_panel.btn_duples.setText(f"{g_compact} ({d_compact})")
        self.settings_panel.btn_duples.setToolTip(AppContext.tr("cln_tip_dupes_count").format(len(groups), total_files))
        
        # Показываем оверлей "Сохранение результатов..." на время записи в БД
        self.overlay.start_loading_mode(0)
        self.overlay.lbl_title.setText("Сохранение результатов...")
        self.overlay.btn_stop.hide()
        from PyQt6.QtCore import QCoreApplication
        QCoreApplication.processEvents()
        
        self.session_db.add_groups(groups)
        self.session_db.add_zero_files(zero_files)
        self.session_db.add_empty_folders(empty_folders)
        
        # Switch to appropriate view
        total_matches = total_files - len(groups)
        if total_matches > 0:
            self.switch_view_mode(0) # VIEW_MODE_DUPLES
        elif len(zero_files) > 0:
            self.switch_view_mode(1) # VIEW_MODE_ZERO
        elif len(empty_folders) > 0:
            self.switch_view_mode(2) # VIEW_MODE_EMPTY
        else:
            self.switch_view_mode(0)
        
        if self.settings_panel.chk_cache.isChecked():
            from .ui_widgets import SourceListItem
            count = self.settings_panel.folder_list_layout.count()
            for i in range(count):
                item = self.settings_panel.folder_list_layout.itemAt(i)
                if item and isinstance(item.widget(), SourceListItem):
                    item.widget().set_cached_state(True)

    def open_filter_dialog(self) -> None:
        self.settings_panel.btn_filter.setEnabled(False)
        self.settings_panel.btn_filter.setText("Scanning...")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, self._run_extension_scan)

    def _run_extension_scan(self) -> None:
        folders = list(self.source_folders.keys())
        if not folders:
            self.settings_panel.btn_filter.setEnabled(True)
            self.settings_panel.btn_filter.setText(AppContext.tr("cln_btn_scan_types"))
            return

        self.scanner = ExtensionScannerWorker(folders)
        self.scanner.finished.connect(self._on_ext_scan_finished)
        self.scanner.start()

    def _on_ext_scan_finished(self, stats: dict[str, Any]) -> None:
        self.settings_panel.btn_filter.setEnabled(True)
        self.settings_panel.btn_filter.setText(AppContext.tr("cln_btn_scan_types"))
        
        dlg = MatrixFilterDialog(stats, self)
        if dlg.exec():
            res = dlg.get_result()
            self.filter_config = {'mode': res['mode'], 'exts': res['exts']}
            
            count = len(res['exts'])
            if count > 0:
                # chk_safe_scan есть только у CleanerSettingsPanel
                if hasattr(self.settings_panel, 'chk_safe_scan'):
                    self.settings_panel.chk_safe_scan.setChecked(False)
                
            if count == 0:
                self.settings_panel.lbl_filter_status.setText(AppContext.tr("cln_filter_all"))
            else:
                key = "cln_filter_status_inc" if res['mode'] == 'include' else "cln_filter_status_exc"
                self.settings_panel.lbl_filter_status.setText(AppContext.tr(key).format(count))

    def on_settings_changed_for_rescan(self) -> None:
        if self.last_scanned_count > 0 and not (self.finder and self.finder.isRunning()):
            if hasattr(self, 'settings_panel') and hasattr(self.settings_panel, 'btn_scan'):
                self.settings_panel.btn_scan.setText(" Пересчитать")

    def reset_scan_button(self) -> None:
        if hasattr(self, 'settings_panel') and hasattr(self.settings_panel, 'btn_scan'):
            self.settings_panel.btn_scan.setText(" " + AppContext.tr("cln_btn_start"))
