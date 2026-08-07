import os
import re

def fix_all():
    frag_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(frag_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Fix os import in run()
    old_run = """    def run(self):
        try:
            from utils_io import safe_cv2_imread"""
            
    new_run = """    def run(self):
        try:
            import os
            from utils_io import safe_cv2_imread"""
            
    if old_run in content:
        content = content.replace(old_run, new_run)

    # 2. Add filter config to FragmentScannerThread
    old_thread_init = """    def __init__(self, dirs_to_scan, target_frag_path, crop_rect, tolerance, use_cache, algorithm="pixel", max_features=10000):
        super().__init__()
        self.dirs_to_scan = dirs_to_scan"""
        
    new_thread_init = """    def __init__(self, dirs_to_scan, target_frag_path, crop_rect, tolerance, use_cache, algorithm="pixel", max_features=10000, filter_config=None):
        super().__init__()
        self.dirs_to_scan = dirs_to_scan
        self.filter_config = filter_config or {'mode': 'all', 'exts': []}"""
        
    if old_thread_init in content:
        content = content.replace(old_thread_init, new_thread_init)
        
    # Apply filter in FragmentScannerThread.run
    old_ext = "if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp')):"
    new_ext = """ext = os.path.splitext(f)[1].lower()
                        valid_ext = ext in ['.png', '.jpg', '.jpeg', '.bmp', '.webp']
                        if self.filter_config['mode'] == 'include':
                            valid_ext = ext in self.filter_config['exts']
                        elif self.filter_config['mode'] == 'exclude':
                            valid_ext = valid_ext and ext not in self.filter_config['exts']
                        if valid_ext:"""
                        
    if old_ext in content:
        content = content.replace(old_ext, new_ext)

    # 3. Add lbl_filter_status and filter_config to AiFragmentTab
    old_filter_ui = """        self.btn_filter.clicked.connect(self.open_filter_dialog)
        filter_layout.addWidget(self.btn_filter)
        col_dirs_inner.addLayout(filter_layout)"""
        
    new_filter_ui = """        self.btn_filter.clicked.connect(self.open_filter_dialog)
        filter_layout.addWidget(self.btn_filter)
        
        self.lbl_filter_status = QLabel("Все картинки")
        self.lbl_filter_status.setStyleSheet("color: #aaa; font-size: 11px;")
        filter_layout.addWidget(self.lbl_filter_status)
        filter_layout.addStretch()
        
        col_dirs_inner.addLayout(filter_layout)
        
        self.fragment_filter_config = {'mode': 'all', 'exts': []}"""
        
    if old_filter_ui in content:
        content = content.replace(old_filter_ui, new_filter_ui)

    # 4. Implement open_filter_dialog properly
    old_filter_methods = """    def open_filter_dialog(self):
        # TODO: integrate with main cleaner filter dialog or spawn one
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Фильтр", "Фильтр для поиска по фрагменту (В разработке, использует .png, .jpg, .jpeg, .bmp, .webp по умолчанию)")"""
        
    new_filter_methods = """    def open_filter_dialog(self):
        dirs = []
        for i in range(self.sources_list_widget_fragment.topLevelItemCount()):
            dirs.append(self.sources_list_widget_fragment.topLevelItem(i).text(0))
            
        if not dirs:
            return
            
        self.btn_filter.setEnabled(False)
        self.btn_filter.setText("Сканирование...")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, lambda: self._run_extension_scan(dirs))

    def _run_extension_scan(self, folders):
        from .workers import ExtensionScannerWorker
        self.ext_scanner = ExtensionScannerWorker(folders)
        self.ext_scanner.finished.connect(self._on_ext_scan_finished)
        self.ext_scanner.start()

    def _on_ext_scan_finished(self, stats: dict):
        self.btn_filter.setEnabled(True)
        self.btn_filter.setText("Фильтр файлов")
        
        from .ui_dialogs import MatrixFilterDialog
        dlg = MatrixFilterDialog(stats, self)
        if dlg.exec():
            res = dlg.get_result()
            self.fragment_filter_config = {'mode': res['mode'], 'exts': res['exts']}
            
            if res['mode'] == 'all':
                self.lbl_filter_status.setText("Все картинки")
                self.lbl_filter_status.setStyleSheet("color: #aaa; font-size: 11px;")
            elif res['mode'] == 'include':
                self.lbl_filter_status.setText(f"Только: {', '.join(res['exts'])}")
                self.lbl_filter_status.setStyleSheet("color: #4ade80; font-size: 11px;")
            else:
                self.lbl_filter_status.setText(f"Кроме: {', '.join(res['exts'])}")
                self.lbl_filter_status.setStyleSheet("color: #f87171; font-size: 11px;")"""
                
    if old_filter_methods in content:
        content = content.replace(old_filter_methods, new_filter_methods)

    # 5. Pass filter_config in start_scan
    old_start_call = """            max_features=max_feat
        )"""
        
    new_start_call = """            max_features=max_feat,
            filter_config=getattr(self, 'fragment_filter_config', {'mode': 'all', 'exts': []})
        )"""
        
    if old_start_call in content:
        content = content.replace(old_start_call, new_start_call)

    with open(frag_path, 'w', encoding='utf-8') as f:
        f.write(content)

fix_all()
print("Fixed os import and added MatrixFilterDialog logic")
