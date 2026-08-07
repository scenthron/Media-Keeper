import re

def fix_imports():
    file_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find PyQt6.QtWidgets import line
    import_match = re.search(r'from PyQt6\.QtWidgets import \((.*?)\)', content, re.DOTALL)
    if import_match:
        imports_str = import_match.group(1)
        if 'QTabWidget' not in imports_str:
            new_imports_str = imports_str + ', QTabWidget'
            content = content[:import_match.start(1)] + new_imports_str + content[import_match.end(1):]
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print("Fixed imports in ui_fragment_tab.py")
        else:
            print("QTabWidget already imported")

fix_imports()
