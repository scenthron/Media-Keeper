import os

def fix_crop_again():
    crop_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_crop_dialog.py'
    with open(crop_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Disable AnchorUnderMouse and implement manual zoom
    old_init_anchors = """        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)"""
    new_init_anchors = """        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.view.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)"""
    if old_init_anchors in content:
        content = content.replace(old_init_anchors, new_init_anchors)

    old_zoom = """    def _zoom_event(self, event):
        if event.angleDelta().y() > 0:
            factor = 1.15
        else:
            factor = 0.85
        # The ViewportAnchor.AnchorUnderMouse handles the centering automatically
        self.view.scale(factor, factor)
        event.accept()"""
        
    new_zoom = """    def _zoom_event(self, event):
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
        self.view.translate(delta.x(), delta.y())
        event.accept()"""
    if old_zoom in content:
        content = content.replace(old_zoom, new_zoom)

    # 2. Fix QMouseEvent and Left Click Crop
    old_mouse_press = """    def _view_mouse_press(self, event):
        from PyQt6.QtCore import Qt
        if event.button() == Qt.MouseButton.MiddleButton:
            self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.view._pan_active = True
            # Fake left click to initiate ScrollHandDrag
            fake_event = QMouseEvent(event.type(), event.position(), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, event.modifiers())
            super(QGraphicsView, self.view).mousePressEvent(fake_event)
            return
            
        if self.view.itemAt(event.pos()) == self.overlay:
            scene_pos = self.view.mapToScene(event.pos())
            self.drag_start = scene_pos
            self.drawing = True
            self.crop_rect = QRectF(scene_pos, scene_pos)
            self.overlay.set_crop_rect(self.crop_rect)
        self.view._original_mouse_press(event)"""
        
    new_mouse_press = """    def _view_mouse_press(self, event):
        from PyQt6.QtCore import Qt, QPointF
        if event.button() == Qt.MouseButton.MiddleButton:
            self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.view._pan_active = True
            # Fake left click to initiate ScrollHandDrag
            fake_event = QMouseEvent(event.type(), QPointF(event.pos()), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, event.modifiers())
            super(QGraphicsView, self.view).mousePressEvent(fake_event)
            return
            
        scene_pos = self.view.mapToScene(event.pos())
        self.drag_start = scene_pos
        self.drawing = True
        self.crop_rect = QRectF(scene_pos, scene_pos)
        self.overlay.set_crop_rect(self.crop_rect)
        self.view._original_mouse_press(event)"""
    if old_mouse_press in content:
        content = content.replace(old_mouse_press, new_mouse_press)

    # 3. Fix mouse release
    old_mouse_release = """    def _view_mouse_release(self, event):
        from PyQt6.QtCore import Qt
        if event.button() == Qt.MouseButton.MiddleButton and getattr(self.view, '_pan_active', False):
            fake_event = QMouseEvent(event.type(), event.position(), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, event.modifiers())
            super(QGraphicsView, self.view).mouseReleaseEvent(fake_event)
            self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.view._pan_active = False
            return
        super(QGraphicsView, self.view).mouseReleaseEvent(event)"""
        
    new_mouse_release = """    def _view_mouse_release(self, event):
        from PyQt6.QtCore import Qt, QPointF
        if event.button() == Qt.MouseButton.MiddleButton and getattr(self.view, '_pan_active', False):
            fake_event = QMouseEvent(event.type(), QPointF(event.pos()), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, event.modifiers())
            super(QGraphicsView, self.view).mouseReleaseEvent(fake_event)
            self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.view._pan_active = False
            return
        super(QGraphicsView, self.view).mouseReleaseEvent(event)"""
    if old_mouse_release in content:
        content = content.replace(old_mouse_release, new_mouse_release)

    with open(crop_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed.")

fix_crop_again()
