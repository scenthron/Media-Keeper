import os

def fix_crop_dialog():
    crop_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_crop_dialog.py'
    with open(crop_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Fix TypeError in QMouseEvent
    old_mouse_press = "fake_event = QMouseEvent(event.type(), event.pos(), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, event.modifiers())"
    new_mouse_press = "fake_event = QMouseEvent(event.type(), event.position(), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, event.modifiers())"
    content = content.replace(old_mouse_press, new_mouse_press)

    # 2. Fix zoom event
    old_zoom_event = """    def _zoom_event(self, event):
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

    new_zoom_event = """    def _zoom_event(self, event):
        if event.angleDelta().y() > 0:
            factor = 1.15
        else:
            factor = 0.85
        # The ViewportAnchor.AnchorUnderMouse handles the centering automatically
        self.view.scale(factor, factor)
        event.accept()"""

    if old_zoom_event in content:
        content = content.replace(old_zoom_event, new_zoom_event)

    with open(crop_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed TypeError and zoom bug in Crop Dialog.")

fix_crop_dialog()
