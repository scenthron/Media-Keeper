import os

def fix_all():
    frag_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(frag_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Fix bbox numpy array truth value error
    content = content.replace(
        'if bbox and hasattr(self.preview_widget, "draw_faces"):',
        'if bbox is not None and hasattr(self.preview_widget, "draw_faces"):'
    )

    # Fix slider logic
    old_logic = """            ratio_thresh = 0.7 + (self.tolerance / 100.0) * 0.15
            min_match = max(4, int(10 * (1 - self.tolerance / 100.0)))"""
            
    new_logic = """            # Slider: 100% (Strict), 0% (Loose)
            ratio_thresh = 0.85 - (self.tolerance / 100.0) * 0.15
            min_match = max(4, int(4 + (15 - 4) * (self.tolerance / 100.0)))"""
            
    content = content.replace(old_logic, new_logic)

    with open(frag_path, 'w', encoding='utf-8') as f:
        f.write(content)

fix_all()
print("Fixed bbox truth value and similarity slider logic.")
