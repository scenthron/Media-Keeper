import os

def fix_preview():
    frag_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(frag_path, 'r', encoding='utf-8') as f:
        content = f.read()

    content = content.replace(
        "self.preview_widget.load_preview(path)",
        "self.preview_widget.load_file(path)"
    )

    with open(frag_path, 'w', encoding='utf-8') as f:
        f.write(content)

fix_preview()
print("Fixed ui_fragment_tab.py")
