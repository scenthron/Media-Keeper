import os

def fix_ui_filter():
    frag_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(frag_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find where scroll_dirs is added to col_dirs
    target = "        col_dirs.addWidget(scroll_dirs)\n        top_layout.addLayout(col_dirs, 2)"
    
    if target in content:
        new_code = """        col_dirs.addWidget(scroll_dirs)
        
        # Filter Layout
        filter_layout = QHBoxLayout()
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(8)
        
        import os
        from PyQt6.QtCore import QSize
        from PyQt6.QtWidgets import QPushButton
        from .ui_panels import load_svg_icon
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
        
        self.btn_filter = QPushButton("Сканировать типы файлов")
        self.btn_filter.setIcon(load_svg_icon(os.path.join(icons_dir, "loupe-color.svg"), QSize(16, 16)))
        self.btn_filter.setIconSize(QSize(16, 16))
        self.btn_filter.setFixedHeight(36)
        self.btn_filter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_filter.setStyleSheet("QPushButton { background-color: #444; color: #fff; border: 1px solid #666; padding: 0 10px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #555; color: white; border-color: #888; }")
        self.btn_filter.clicked.connect(self.open_filter_dialog)
        
        self.lbl_filter_status = QLabel("Фильтр: Все файлы")
        self.lbl_filter_status.setStyleSheet("color: #aaa; font-size: 11px;")
        self.lbl_filter_status.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        filter_layout.addWidget(self.btn_filter)
        filter_layout.addWidget(self.lbl_filter_status)
        filter_layout.addStretch()
        
        col_dirs.addLayout(filter_layout)
        
        self.fragment_filter_config = {'mode': 'all', 'exts': []}
        
        top_layout.addLayout(col_dirs, 2)"""
        
        content = content.replace(target, new_code)
        
    # Check if open_filter_dialog exists, if not add it
    if "def open_filter_dialog(self):" not in content:
        methods = """    def open_filter_dialog(self):
        dirs = list(self.cleaner.source_folders.keys()) if hasattr(self.cleaner, 'source_folders') else []
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
        self.btn_filter.setText("Сканировать типы файлов")
        
        from .ui_dialogs import MatrixFilterDialog
        dlg = MatrixFilterDialog(stats, self)
        if dlg.exec():
            res = dlg.get_result()
            self.fragment_filter_config = {'mode': res['mode'], 'exts': res['exts']}
            
            if res['mode'] == 'all':
                self.lbl_filter_status.setText("Фильтр: Все файлы")
                self.lbl_filter_status.setStyleSheet("color: #aaa; font-size: 11px;")
            elif res['mode'] == 'include':
                self.lbl_filter_status.setText(f"Фильтр: {', '.join(res['exts'])}")
                self.lbl_filter_status.setStyleSheet("color: #4ade80; font-size: 11px;")
            else:
                self.lbl_filter_status.setText(f"Фильтр (кроме): {', '.join(res['exts'])}")
                self.lbl_filter_status.setStyleSheet("color: #f87171; font-size: 11px;")\n"""
        
        content = content.replace("    def start_scan(self):", methods + "\n    def start_scan(self):")
        
    # Pass filter_config in start_scan
    old_start_call = """            max_features=max_feat
        )"""
        
    new_start_call = """            max_features=max_feat,
            filter_config=getattr(self, 'fragment_filter_config', {'mode': 'all', 'exts': []})
        )"""
        
    if old_start_call in content:
        content = content.replace(old_start_call, new_start_call)

    # In start scan, use cleaner.source_folders
    old_dirs_scan = "dirs = list(self.cleaner.source_folders_fragment.keys()) if hasattr(self.cleaner, 'source_folders_fragment') else []"
    new_dirs_scan = "dirs = list(self.cleaner.source_folders.keys()) if hasattr(self.cleaner, 'source_folders') else []"
    
    if old_dirs_scan in content:
        content = content.replace(old_dirs_scan, new_dirs_scan)

    with open(frag_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed Filter layout")

fix_ui_filter()
