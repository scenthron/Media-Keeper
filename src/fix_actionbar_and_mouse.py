import os
from config import AppContext

def fix_all():
    # 1. Fix ui_crop_dialog.py mouse events
    crop_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_crop_dialog.py'
    with open(crop_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # We need to save the original mousePressEvent
    if "self.view._original_mouse_press" not in content:
        content = content.replace(
            "self.view.mousePressEvent = self._view_mouse_press",
            "self.view._original_mouse_press = self.view.mousePressEvent\n        self.view.mousePressEvent = self._view_mouse_press"
        )
    
    # And replace the wrong super call
    content = content.replace(
        "super(QGraphicsView, self.view).mousePressEvent(event)",
        "self.view._original_mouse_press(event)"
    )
    
    with open(crop_path, 'w', encoding='utf-8') as f:
        f.write(content)

    # 2. Fix ui_fragment_tab.py lbl_selection_info
    frag_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(frag_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if "self.action_bar.lbl_selection_info = " not in content:
        old_action = "self.action_bar = CleanerActionBar()\n        self.action_bar.is_similar_mode = False"
        new_action = """self.action_bar = CleanerActionBar()
        self.action_bar.lbl_selection_info = QLabel("Выбрано: 0 файлов • 0 B")
        self.action_bar.lbl_selection_info.setStyleSheet("color: #93c5fd; font-size: 11px; font-weight: bold;")
        ab_layout = self.action_bar.layout()
        if ab_layout:
            ab_layout.insertWidget(3, self.action_bar.lbl_selection_info)
        self.action_bar.is_similar_mode = False"""
        content = content.replace(old_action, new_action)

        with open(frag_path, 'w', encoding='utf-8') as f:
            f.write(content)

fix_all()
print("Fixed ui_crop_dialog.py and ui_fragment_tab.py")
