import os

def fix_logic_actions_remove():
    file_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\logic_actions.py'
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Fix remove_folder
    old_remove = """if hasattr(self, 'current_tab') and self.current_tab == 2:
            layout = self.page_ai.folder_list_layout_ai
        else:"""
    new_remove = """if hasattr(self, 'current_tab') and self.current_tab == 3:
            layout = self.page_ai.folder_list_layout_ai
        elif hasattr(self, 'current_tab') and self.current_tab == 2:
            layout = self.page_fragment.folder_list_layout_fragment
        else:"""
    content = content.replace(old_remove, new_remove)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

fix_logic_actions_remove()
print("Fixed logic_actions.py remove_folder")
