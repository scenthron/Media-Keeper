import os

def fix_logic_actions():
    file_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\logic_actions.py'
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Fix is_cached logic
    content = content.replace(
        "if current_tab == 2 and hasattr(self, 'page_ai'):\n            is_cached, is_face_cached = self.page_ai.classifier.cache.has_cached_files_for_folder(path)",
        "if current_tab == 3 and hasattr(self, 'page_ai'):\n            is_cached, is_face_cached = self.page_ai.classifier.cache.has_cached_files_for_folder(path)"
    )

    # Fix widget insertion logic
    content = content.replace(
        "if hasattr(self, 'current_tab') and self.current_tab == 2:\n            self.page_ai.folder_list_layout_ai.addWidget(item_widget)\n        else:",
        "if hasattr(self, 'current_tab') and self.current_tab == 3:\n            self.page_ai.folder_list_layout_ai.addWidget(item_widget)\n        elif hasattr(self, 'current_tab') and self.current_tab == 2:\n            self.page_fragment.folder_list_layout_fragment.addWidget(item_widget)\n        else:"
    )

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

def fix_ui_fragment_tab():
    file_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Fix top settings height
    content = content.replace(
        "self.top_settings.setMinimumHeight(220)\n        self.top_settings.setMaximumHeight(600)",
        "self.top_settings.setFixedHeight(235)"
    )

    # Swap action bar and tree
    content = content.replace(
        "br_layout.addWidget(self.tree_results, 1)\n        br_layout.addWidget(self.action_bar)",
        "br_layout.addWidget(self.action_bar)\n        br_layout.addWidget(self.tree_results, 1)"
    )

    # Fix right splitter size
    content = content.replace(
        "self.right_splitter.setStyleSheet(\"QSplitter::handle { background-color: #2d2d2d; }\")\n        \n        self.tree_results = QTreeWidget()",
        "self.right_splitter.setStyleSheet(\"QSplitter::handle { background-color: #2d2d2d; }\")\n        self.right_splitter.setSizes([650, 350])\n        \n        self.tree_results = QTreeWidget()"
    )

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

fix_logic_actions()
fix_ui_fragment_tab()
print("Fixed successfully.")
