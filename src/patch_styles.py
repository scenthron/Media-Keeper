import os

def patch_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replacements
    content = content.replace("APP_DESIGN.colors.text_secondary", '"#888"')
    content = content.replace("APP_DESIGN.colors.surface", '"#2b2b2b"')
    content = content.replace("APP_DESIGN.colors.border", '"#444"')
    content = content.replace("APP_DESIGN.colors.text_primary", '"#fff"')
    content = content.replace("APP_DESIGN.colors.primary_transparent", '"#3b82f6"')
    content = content.replace("APP_DESIGN.colors.primary", '"#3b82f6"')
    content = content.replace("APP_DESIGN.stylesheets.button_primary", '"background-color: #3b82f6; color: white; border-radius: 4px; padding: 8px;"')
    content = content.replace("APP_DESIGN.stylesheets.progress_bar", '""')

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

patch_file(r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py')
patch_file(r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_crop_dialog.py')
print("Patched successfully.")
