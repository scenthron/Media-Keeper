import os

def fix_all_bugs():
    # 1. Fix CropDialog dragging
    crop_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_crop_dialog.py'
    with open(crop_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    content = content.replace(
        "self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)",
        "self.view.setDragMode(QGraphicsView.DragMode.NoDrag)"
    )
    with open(crop_path, 'w', encoding='utf-8') as f:
        f.write(content)

    # 2. Fix source_folders property in ui_main.py
    ui_main_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_main.py'
    with open(ui_main_path, 'r', encoding='utf-8') as f:
        content = f.read()

    old_getter = """    @property
    def source_folders(self) -> dict:
        if self.current_tab == 3:
            return self.source_folders_ai
        return self.source_folders_similar if self.current_tab == 1 else self.source_folders_dupes

    @source_folders.setter
    def source_folders(self, val: dict) -> None:
        if self.current_tab == 3:
            self.source_folders_ai = val
        elif self.current_tab == 1:
            self.source_folders_similar = val
        else:
            self.source_folders_dupes = val"""
            
    new_getter = """    @property
    def source_folders(self) -> dict:
        if self.current_tab == 3:
            return self.source_folders_ai
        elif self.current_tab == 2:
            return self.source_folders_fragment
        return self.source_folders_similar if self.current_tab == 1 else self.source_folders_dupes

    @source_folders.setter
    def source_folders(self, val: dict) -> None:
        if self.current_tab == 3:
            self.source_folders_ai = val
        elif self.current_tab == 2:
            self.source_folders_fragment = val
        elif self.current_tab == 1:
            self.source_folders_similar = val
        else:
            self.source_folders_dupes = val"""

    content = content.replace(old_getter, new_getter)
    with open(ui_main_path, 'w', encoding='utf-8') as f:
        f.write(content)

fix_all_bugs()
print("Fixed bugs.")
