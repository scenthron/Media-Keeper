import re

def fix_unbound_local():
    frag_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(frag_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Remove the local imports from init_ui
    content = content.replace("from PyQt6.QtWidgets import QPushButton", "")
    content = content.replace("from PyQt6.QtCore import QSize", "")
    
    with open(frag_path, 'w', encoding='utf-8') as f:
        f.write(content)

fix_unbound_local()
