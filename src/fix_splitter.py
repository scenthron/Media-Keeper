import os

def fix_splitter():
    file_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    content = content.replace(
        "self.right_splitter.setStretchFactor(0, 2)\n        self.right_splitter.setStretchFactor(1, 1)",
        "self.right_splitter.setStretchFactor(0, 7)\n        self.right_splitter.setStretchFactor(1, 3)"
    )

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

fix_splitter()
print("Fixed ui_fragment_tab.py")
