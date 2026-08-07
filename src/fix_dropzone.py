import os

def fix_ui():
    file_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Fix layout height
    content = content.replace(
        "self.top_settings.setFixedHeight(235)",
        "self.top_settings.setFixedHeight(260)"
    )

    # Fix lbl_icon error
    content = content.replace(
        "self.drop_zone.lbl_icon.show()",
        "self.drop_zone.btn_add.show()"
    )
    content = content.replace(
        "self.drop_zone.lbl_icon.hide()",
        "self.drop_zone.btn_add.hide()"
    )

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

fix_ui()
print("Fixed ui_fragment_tab.py")
