import os

def fix_ui_fragment_tab():
    frag_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(frag_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Replace the entire bottom_layout construction to match ui_ai_tab.py precisely
    bottom_start = "        # BOTTOM: RESULTS & PREVIEW"
    bottom_end = "        self.main_splitter.addWidget(self.bottom_container)"
    
    if bottom_start in content and bottom_end in content:
        start_idx = content.find(bottom_start)
        end_idx = content.find(bottom_end) + len(bottom_end)
        
        # For the progress bar to show up correctly, we add it to bot_layout like AI tab does.
        # Then lbl_stats, then CleanerActionBar, then right_splitter
        new_bottom = """        # BOTTOM: RESULTS & PREVIEW
        self.bottom_container = QWidget()
        bot_layout = QVBoxLayout(self.bottom_container)
        bot_layout.setContentsMargins(0, 0, 0, 0)
        bot_layout.setSpacing(0)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setStyleSheet(\"\"\"
            QProgressBar { border: none; background-color: #151515; text-align: center; color: white; font-size: 11px; }
            QProgressBar::chunk { background-color: #3b82f6; }
        \"\"\")
        self.progress_bar.hide()
        bot_layout.addWidget(self.progress_bar)
        
        self.lbl_stats = QLabel("")
        self.lbl_stats.setStyleSheet("color: #4ade80; font-weight: bold; font-size: 12px; border: none; padding: 4px 15px; background-color: #1e1e1e;")
        bot_layout.addWidget(self.lbl_stats)
        
        from .ui_panels import CleanerActionBar
        self.action_bar = CleanerActionBar()
        self.action_bar.is_similar_mode = False
        self.action_bar.combo_autoselect.hide()
        self.action_bar.btn_select_all.hide()
        self.action_bar.btn_deselect.hide()
        self.action_bar.chk_preserve.hide()
        self.action_bar.combo_collision.hide()
        
        self.action_bar.lbl_selection_info = QLabel("Выбрано: 0 файлов • 0 B")
        self.action_bar.lbl_selection_info.setStyleSheet("color: #93c5fd; font-size: 11px; font-weight: bold;")
        ab_layout = self.action_bar.layout()
        if ab_layout:
            ab_layout.insertWidget(3, self.action_bar.lbl_selection_info)
            
        bot_layout.addWidget(self.action_bar)
        
        # SPLITTER FOR TREE AND PREVIEW
        self.right_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.right_splitter.setHandleWidth(2)
        self.right_splitter.setStyleSheet("QSplitter::handle { background-color: #2d2d2d; }")
        
        self.tree_results = QTreeWidget()
        self.tree_results.setColumnCount(4)
        self.tree_results.setHeaderLabels(["Файл", "Сходство (%)", "Размер", "Путь"])
        self.tree_results.setColumnWidth(0, 240)
        self.tree_results.setColumnWidth(1, 100)
        self.tree_results.setColumnWidth(2, 90)
        self.tree_results.setStyleSheet(\"\"\"
            QTreeWidget { background-color: #1a1a1a; border: none; outline: none; color: #eee; } 
            QTreeWidget::item { padding: 6px; border-bottom: 1px solid #222; } 
            QTreeWidget::item:selected { background-color: #2b2b2b; color: white; } 
        \"\"\")
        self.tree_results.itemSelectionChanged.connect(self.on_tree_selection_changed)
        
        self.right_splitter.addWidget(self.tree_results)
        
        from .ui_preview import CleanerPreviewWidget
        self.preview_widget = CleanerPreviewWidget()
        self.preview_widget.show_empty("Выберите файл для предпросмотра")
        self.right_splitter.addWidget(self.preview_widget)
        
        self.right_splitter.setSizes([650, 350])
        bot_layout.addWidget(self.right_splitter, 1)
        
        self.main_splitter.addWidget(self.bottom_container)"""
        
        content = content[:start_idx] + new_bottom + content[end_idx:]

    # 2. Add DropZoneWidget and Filter button to "Папки для поиска"
    # Search for col_dirs logic
    dirs_start = "        self.sources_list_widget_fragment.setStyleSheet(\"QTreeWidget { background: transparent; border: none; } QTreeWidget::item { padding: 4px; }\")"
    
    if dirs_start in content:
        new_dirs = """        self.sources_list_widget_fragment.setStyleSheet("QTreeWidget { background: transparent; border: none; } QTreeWidget::item { padding: 4px; }")
        
        # Drop Zone (Like AI Search)
        self.drop_zone_fragment = DropZoneWidget()
        self.drop_zone_fragment.clicked.connect(self.add_fragment_folder)
        self.drop_zone_fragment.folder_dropped.connect(self.add_fragment_folder_path)
        if hasattr(self.drop_zone_fragment, 'files_dropped'):
            self.drop_zone_fragment.files_dropped.connect(self.add_fragment_folder_paths)
        self.drop_zone_fragment.clear_default_requested.connect(self.clear_fragment_folders)
        self.drop_zone_fragment.btn_clear.show()
        self.drop_zone_fragment.setStyleSheet(self.drop_zone_fragment.styleSheet() + "margin: 0px; padding: 2px;")
        
        scroll_dirs.setWidget(self.sources_list_widget_fragment)
        
        col_dirs_inner = QVBoxLayout()
        col_dirs_inner.setContentsMargins(0,0,0,0)
        col_dirs_inner.addWidget(self.drop_zone_fragment)
        col_dirs_inner.addWidget(scroll_dirs)
        
        # Filter Button
        filter_layout = QHBoxLayout()
        from .ui_panels import load_svg_icon
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
        self.btn_filter = QPushButton("Фильтр файлов")
        self.btn_filter.setIcon(load_svg_icon(os.path.join(icons_dir, "loupe-color.svg"), QSize(16, 16)))
        self.btn_filter.setIconSize(QSize(16, 16))
        self.btn_filter.setFixedHeight(36)
        self.btn_filter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_filter.setStyleSheet("QPushButton { background-color: #444; color: #fff; border: 1px solid #666; padding: 0 10px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #555; color: white; border-color: #888; }")
        self.btn_filter.clicked.connect(self.open_filter_dialog)
        filter_layout.addWidget(self.btn_filter)
        col_dirs_inner.addLayout(filter_layout)
        
        # replace col_dirs with our inner layout container
        col_dirs_container = QWidget()
        col_dirs_container.setLayout(col_dirs_inner)
        col_dirs.addWidget(col_dirs_container)
"""
        
        # Replace only the line + the old addWidget
        content = content.replace(dirs_start + "\n        scroll_dirs.setWidget(self.sources_list_widget_fragment)\n        col_dirs.addWidget(scroll_dirs)", new_dirs)

    # Add methods for DropZone logic
    methods = """    def add_fragment_folder(self):
        from PyQt6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "Выберите папку для поиска", "")
        if d: self.add_fragment_folder_path(d)
        
    def add_fragment_folder_path(self, path):
        import os
        from PyQt6.QtWidgets import QTreeWidgetItem
        if not os.path.exists(path): return
        for i in range(self.sources_list_widget_fragment.topLevelItemCount()):
            if self.sources_list_widget_fragment.topLevelItem(i).text(0) == path: return
        item = QTreeWidgetItem([path])
        self.sources_list_widget_fragment.addTopLevelItem(item)
        
    def add_fragment_folder_paths(self, paths):
        for p in paths:
            self.add_fragment_folder_path(p)
            
    def clear_fragment_folders(self):
        self.sources_list_widget_fragment.clear()
        
    def open_filter_dialog(self):
        # TODO: integrate with main cleaner filter dialog or spawn one
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Фильтр", "Фильтр для поиска по фрагменту (В разработке, использует .png, .jpg, .jpeg, .bmp, .webp по умолчанию)")
"""
    
    if "def add_fragment_folder(" not in content:
        content = content.replace("    def start_scan(self):", methods + "\n    def start_scan(self):")
        
    with open(frag_path, 'w', encoding='utf-8') as f:
        f.write(content)

fix_ui_fragment_tab()
print("Fixed ui_fragment_tab layout")
