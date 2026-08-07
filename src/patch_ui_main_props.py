import os
import re

def patch_ui_main():
    file_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_main.py'
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # property action_bar
    content = content.replace(
        "if self.current_tab == 3:\n            return self.page_ai.action_bar\n        return self.action_bar_similar if self.current_tab == 1 else self.action_bar_dupes",
        "if self.current_tab == 3:\n            return self.page_ai.action_bar\n        elif self.current_tab == 2:\n            return self.page_fragment.action_bar\n        return self.action_bar_similar if self.current_tab == 1 else self.action_bar_dupes"
    )
    
    # property preview_widget
    content = content.replace(
        "if self.current_tab == 3:\n            return self.page_ai.preview_widget\n        return self.preview_widget_similar if self.current_tab == 1 else self.preview_widget_dupes",
        "if self.current_tab == 3:\n            return self.page_ai.preview_widget\n        elif self.current_tab == 2:\n            return self.page_fragment.preview_widget\n        return self.preview_widget_similar if self.current_tab == 1 else self.preview_widget_dupes"
    )
    
    # property lbl_groups_found
    content = content.replace(
        "elif self.current_tab == 3:\n            return self.page_ai.lbl_stats",
        "elif self.current_tab == 3:\n            return self.page_ai.lbl_stats\n        elif self.current_tab == 2:\n            return self.page_fragment.lbl_stats"
    )
    
    # property lbl_selection_info
    content = content.replace(
        "elif self.current_tab == 3:\n            return self.page_ai.action_bar.lbl_selection_info",
        "elif self.current_tab == 3:\n            return self.page_ai.action_bar.lbl_selection_info\n        elif self.current_tab == 2:\n            return self.page_fragment.action_bar.lbl_selection_info"
    )
    
    # update_toggle_settings_button
    content = content.replace(
        "if self.current_tab == 3:\n            visible = not self.page_ai.top_settings.isHidden()",
        "if self.current_tab == 3:\n            visible = not self.page_ai.top_settings.isHidden()\n        elif self.current_tab == 2:\n            visible = not self.page_fragment.top_settings.isHidden()"
    )
    
    # toggle_settings
    content = content.replace(
        "if self.current_tab == 3:\n            if not self.page_ai.top_settings.isHidden():\n                self.page_ai.top_settings.hide()\n            else:\n                self.page_ai.top_settings.show()",
        "if self.current_tab == 3:\n            if not self.page_ai.top_settings.isHidden():\n                self.page_ai.top_settings.hide()\n            else:\n                self.page_ai.top_settings.show()\n        elif self.current_tab == 2:\n            if not self.page_fragment.top_settings.isHidden():\n                self.page_fragment.top_settings.hide()\n            else:\n                self.page_fragment.top_settings.show()"
    )
    
    # get_active_source_folders
    content = content.replace(
        "if self.current_tab == 3:\n            return list(self.source_folders_ai.keys())\n        return list(self.source_folders_similar.keys()) if self.current_tab == 1 else list(self.source_folders_dupes.keys())",
        "if self.current_tab == 3:\n            return list(self.source_folders_ai.keys())\n        elif self.current_tab == 2:\n            return list(self.source_folders_fragment.keys())\n        return list(self.source_folders_similar.keys()) if self.current_tab == 1 else list(self.source_folders_dupes.keys())"
    )
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

patch_ui_main()
print("ui_main patched.")
