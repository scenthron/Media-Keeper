import os

def fix_tree_ui():
    frag_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(frag_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Update stylesheet
    old_style = """        self.tree_results.setStyleSheet("QTreeWidget { background-color: #1a1a1a; border: none; outline: none; color: #eee; } QTreeWidget::item { padding: 6px; border-bottom: 1px solid #222; } QTreeWidget::item:selected { background-color: #2b2b2b; color: white; }")
        self.tree_results.itemSelectionChanged.connect(self.on_tree_selection_changed)"""
        
    new_style = """        self.tree_results.setStyleSheet('''
            QTreeWidget { background-color: #1a1a1a; border: none; outline: none; color: #eee; } 
            QTreeWidget::item { padding: 6px; border-bottom: 1px solid #222; } 
            QTreeWidget::item:selected { background-color: #2b2b2b; color: white; }
            QTreeWidget::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #666;
                border-radius: 3px;
                background-color: #2b2b2b;
            }
            QTreeWidget::indicator:hover { border-color: #3b82f6; }
            QTreeWidget::indicator:checked {
                background-color: #3b82f6;
                border: 1px solid #2563eb;
            }
            QTreeWidget::indicator:unchecked { background-color: #2b2b2b; }
        ''')
        self.tree_results.itemSelectionChanged.connect(self.on_tree_selection_changed)
        self.tree_results.itemChanged.connect(self.on_tree_item_changed)
        self.tree_results.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_results.customContextMenuRequested.connect(self.show_context_menu)"""
        
    if old_style in content:
        content = content.replace(old_style, new_style)

    # 2. Add methods
    methods = """    def on_tree_item_changed(self, item, column):
        self.update_action_bar_info()
        
    def show_context_menu(self, pos):
        item = self.tree_results.itemAt(pos)
        
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #2b2b2b; color: #eee; border: 1px solid #444; } QMenu::item { padding: 6px 20px; } QMenu::item:selected { background-color: #3b82f6; color: white; }")
        
        action_select_all = QAction("Выделить всё", self)
        action_select_all.triggered.connect(lambda: self.select_all_results(True))
        menu.addAction(action_select_all)
        
        action_deselect_all = QAction("Снять выделение со всех", self)
        action_deselect_all.triggered.connect(lambda: self.select_all_results(False))
        menu.addAction(action_deselect_all)
        
        menu.addSeparator()
        
        action_send_sorter = QAction("Отправить выделенные в сортировщик", self)
        action_send_sorter.triggered.connect(lambda: self.action_bar.btn_move.clicked.emit())
        menu.addAction(action_send_sorter)
        
        if item:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and "path" in data:
                path = data["path"]
                menu.addSeparator()
                
                action_open_dir = QAction("Открыть папку с файлом", self)
                action_open_dir.triggered.connect(lambda p=path: self.reveal_in_explorer(p))
                menu.addAction(action_open_dir)
                
                action_open_file = QAction("Открыть файл", self)
                action_open_file.triggered.connect(lambda p=path: self.open_file_default(p))
                menu.addAction(action_open_file)
                
        menu.exec(self.tree_results.viewport().mapToGlobal(pos))
        
    def reveal_in_explorer(self, path):
        import os
        from utils_common import reveal_in_explorer
        if os.path.exists(path):
            reveal_in_explorer(path)
            
    def open_file_default(self, path):
        import os
        if os.path.exists(path):
            os.startfile(path)

    def on_tree_selection_changed(self):"""
    
    old_selection = """    def on_tree_selection_changed(self):"""
    if old_selection in content and "def show_context_menu" not in content:
        content = content.replace(old_selection, methods)

    with open(frag_path, 'w', encoding='utf-8') as f:
        f.write(content)

fix_tree_ui()
