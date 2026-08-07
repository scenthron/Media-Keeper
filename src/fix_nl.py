import os

def fix_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    for i in range(len(lines)):
        if "self.drop_zone.lbl_text.setText(\"Перетащите 1 фото" in lines[i]:
            # Next line has the rest of the string
            if i + 1 < len(lines) and "для поиска фрагмента" in lines[i+1]:
                lines[i] = '        self.drop_zone.lbl_text.setText("Перетащите 1 фото\\nдля поиска фрагмента")\n'
                lines[i+1] = ''
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)

fix_file(r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py')
print("Fixed successfully.")
