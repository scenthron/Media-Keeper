import os
import re

def fix_layout():
    frag_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(frag_path, 'r', encoding='utf-8') as f:
        content = f.read()

    old_code = """        bottom_right_widget = QWidget()
        br_layout = QVBoxLayout(bottom_right_widget)
        br_layout.setContentsMargins(0, 0, 0, 0)
        br_layout.addWidget(self.action_bar)
        br_layout.addWidget(self.tree_results, 1)
        
        self.right_splitter.addWidget(bottom_right_widget)
        self.right_splitter.addWidget(self.preview_widget)
        self.right_splitter.setStretchFactor(0, 7)
        self.right_splitter.setStretchFactor(1, 3)
        
        bottom_layout.addWidget(self.right_splitter, 1)"""

    new_code = """        bottom_right_widget = QWidget()
        br_layout = QVBoxLayout(bottom_right_widget)
        br_layout.setContentsMargins(0, 0, 0, 0)
        br_layout.addWidget(self.tree_results, 1)
        
        self.right_splitter.addWidget(bottom_right_widget)
        self.right_splitter.addWidget(self.preview_widget)
        self.right_splitter.setStretchFactor(0, 1)
        self.right_splitter.setStretchFactor(1, 1)
        
        bottom_layout.addWidget(self.action_bar)
        bottom_layout.addWidget(self.right_splitter, 1)
        
        from PyQt6.QtCore import QTimer
        def apply_splitter_sizes():
            self.right_splitter.setSizes([600, 400])
        QTimer.singleShot(0, apply_splitter_sizes)"""

    content = content.replace(old_code, new_code)
    
    with open(frag_path, 'w', encoding='utf-8') as f:
        f.write(content)

fix_layout()
print("Fixed layout")
