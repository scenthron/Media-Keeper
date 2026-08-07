import os

def fix_fstring(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # The problem is f"color: {"#888"};
    # We replace it with "color: #888;
    content = content.replace('f"color: {"#888"}"', '"color: #888"')
    content = content.replace('f"color: {"#888"};', '"color: #888;')
    content = content.replace('f"color: {"#fff"};', '"color: #fff;')
    content = content.replace('f"""\n            QTreeWidget {\n                background-color: {"#2b2b2b"};\n                border: 1px solid {"#444"};', '"""\n            QTreeWidget {\n                background-color: #2b2b2b;\n                border: 1px solid #444;')
    
    # Let's just blindly remove the `f` prefix and the braces for the colors
    content = content.replace('{"#888"}', '#888')
    content = content.replace('{"#2b2b2b"}', '#2b2b2b')
    content = content.replace('{"#444"}', '#444')
    content = content.replace('{"#fff"}', '#fff')
    content = content.replace('{"#3b82f6"}', '#3b82f6')
    content = content.replace('f"color: #', '"color: #')
    content = content.replace('f"""', '"""')
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

fix_fstring(r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py')
fix_fstring(r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_crop_dialog.py')
print("Fixed successfully.")
