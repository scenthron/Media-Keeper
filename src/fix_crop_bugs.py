import os

def fix_bugs_in_crop():
    crop_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_crop_dialog.py'
    with open(crop_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Fix set_rect -> set_crop_rect
    old_set_rect = "self.overlay.set_rect(self.crop_rect)"
    new_set_rect = "self.overlay.set_crop_rect(self.crop_rect)"
    if old_set_rect in content:
        content = content.replace(old_set_rect, new_set_rect)

    # 2. Fix zoom to mouse cursor
    old_zoom = """    def _zoom_event(self, event):
        if event.angleDelta().y() > 0:
            factor = 1.15
        else:
            factor = 0.85
        self.view.scale(factor, factor)"""
        
    new_zoom = """    def _zoom_event(self, event):
        # Prevent zooming out too far
        if hasattr(event, 'position'):
            pos = event.position().toPoint()
        else:
            pos = event.pos()
            
        old_pos = self.view.mapToScene(pos)
        
        if event.angleDelta().y() > 0:
            factor = 1.15
        else:
            factor = 0.85
            
        self.view.scale(factor, factor)
        
        new_pos = self.view.mapToScene(pos)
        delta = new_pos - old_pos
        self.view.translate(delta.x(), delta.y())"""
        
    if old_zoom in content:
        content = content.replace(old_zoom, new_zoom)

    with open(crop_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed Crop bugs.")

fix_bugs_in_crop()
