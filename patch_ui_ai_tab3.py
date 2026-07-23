import sys

path = 'src/modules/cleaner/ui_ai_tab.py'
with open(path, 'r', encoding='utf-8') as f:
    code = f.read()

old_code = '''    def on_scan_finished(self, results):
        self.progress_bar.hide()
        self.btn_start_scan.setText(" Начать ИИ Поиск" if AppContext.is_ru() else " Start AI Search")
        self.btn_start_scan.setStyleSheet("""
            QPushButton { background-color: #15803d; color: white; font-weight: 900; font-size: 14px; border: 1px solid #16a34a; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
            QPushButton:hover { background-color: #16a34a; }
            QPushButton:disabled { background-color: #222; color: #555; font-weight: 900; font-size: 14px; border: 1px solid #333; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
        """)
        
        if self.active_worker:
            self.active_worker.deleteLater()
        self.active_worker = None
        self.scan_finished.emit()
        self.update_cache_info_ai()
        if hasattr(self, 'cleaner'):
            self.update_folders_label(self.cleaner.get_active_source_folders())
        
        self.populate_results(results)'''

new_code = '''    def on_scan_finished(self, results):
        from PyQt6.QtWidgets import QApplication
        self.lbl_progress.setText("Формирование таблицы..." if AppContext.is_ru() else "Building table...")
        QApplication.processEvents()
        
        self.populate_results(results)
        
        self.progress_bar.hide()
        self.btn_start_scan.setText(" Начать ИИ Поиск" if AppContext.is_ru() else " Start AI Search")
        self.btn_start_scan.setStyleSheet("""
            QPushButton { background-color: #15803d; color: white; font-weight: 900; font-size: 14px; border: 1px solid #16a34a; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
            QPushButton:hover { background-color: #16a34a; }
            QPushButton:disabled { background-color: #222; color: #555; font-weight: 900; font-size: 14px; border: 1px solid #333; border-radius: 6px; font-family: 'Segoe UI', 'Segoe UI Emoji'; padding: 4px; }
        """)
        
        if self.active_worker:
            self.active_worker.deleteLater()
        self.active_worker = None
        self.scan_finished.emit()
        self.update_cache_info_ai()
        if hasattr(self, 'cleaner'):
            self.update_folders_label(self.cleaner.get_active_source_folders())'''

if old_code in code:
    code = code.replace(old_code, new_code)
    open(path, 'w', encoding='utf-8').write(code)
    print("Replaced!")
else:
    print("Not found!")
