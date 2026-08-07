import os

def fix_view_events():
    crop_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_crop_dialog.py'
    with open(crop_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Add _original_mouse_move and _original_mouse_release
    old_init = """        self.view.wheelEvent = self._zoom_event
        self.view._original_mouse_press = self.view.mousePressEvent
        self.view.mousePressEvent = self._view_mouse_press
        self.view.mouseReleaseEvent = self._view_mouse_release
        self.view.mouseMoveEvent = self._view_mouse_move
        self.view._pan_active = False"""
        
    new_init = """        self.view.wheelEvent = self._zoom_event
        self.view._original_mouse_press = self.view.mousePressEvent
        self.view.mousePressEvent = self._view_mouse_press
        self.view._original_mouse_release = self.view.mouseReleaseEvent
        self.view.mouseReleaseEvent = self._view_mouse_release
        self.view._original_mouse_move = self.view.mouseMoveEvent
        self.view.mouseMoveEvent = self._view_mouse_move
        self.view._pan_active = False
        self.drawing = False"""
    if old_init in content:
        content = content.replace(old_init, new_init)

    # 2. Fix mousePressEvent
    old_press = """    def _view_mouse_press(self, event):
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

    new_press = """    def _view_mouse_press(self, event):
        from PyQt6.QtCore import Qt, QPointF
        if event.button() == Qt.MouseButton.MiddleButton:
            self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.view._pan_active = True
            fake_event = QMouseEvent(event.type(), QPointF(event.pos()), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, event.modifiers())
            self.view._original_mouse_press(fake_event)
            return
            
        scene_pos = self.view.mapToScene(event.pos())
        self.drag_start = scene_pos
        self.drawing = True
        self.crop_rect = QRectF(scene_pos, scene_pos)
        self.overlay.set_crop_rect(self.crop_rect)
        self.view._original_mouse_press(event)"""
    if old_press in content:
        content = content.replace(old_press, new_press)

    # 3. Fix mouseReleaseEvent
    old_release = """    def _view_mouse_release(self, event):
        from PyQt6.QtCore import Qt, QPointF
        if event.button() == Qt.MouseButton.MiddleButton and getattr(self.view, '_pan_active', False):
            fake_event = QMouseEvent(event.type(), QPointF(event.pos()), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, event.modifiers())
            super(QGraphicsView, self.view).mouseReleaseEvent(fake_event)
            self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.view._pan_active = False
            return
        super(QGraphicsView, self.view).mouseReleaseEvent(event)"""

    new_release = """    def _view_mouse_release(self, event):
        from PyQt6.QtCore import Qt, QPointF
        if event.button() == Qt.MouseButton.MiddleButton and getattr(self.view, '_pan_active', False):
            fake_event = QMouseEvent(event.type(), QPointF(event.pos()), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, event.modifiers())
            self.view._original_mouse_release(fake_event)
            self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.view._pan_active = False
            return
            
        if getattr(self, 'drawing', False):
            self.drawing = False
            
        self.view._original_mouse_release(event)"""
    if old_release in content:
        content = content.replace(old_release, new_release)

    # 4. Fix mouseMoveEvent
    old_move = """    def _view_mouse_move(self, event):
        super(QGraphicsView, self.view).mouseMoveEvent(event)"""

    new_move = """    def _view_mouse_move(self, event):
        if getattr(self, 'drawing', False):
            scene_pos = self.view.mapToScene(event.pos())
            self.crop_rect = QRectF(self.drag_start, scene_pos).normalized()
            self.overlay.set_crop_rect(self.crop_rect)
            
        if getattr(self.view, '_pan_active', False):
            from PyQt6.QtCore import Qt, QPointF
            fake_event = QMouseEvent(event.type(), QPointF(event.pos()), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, event.modifiers())
            self.view._original_mouse_move(fake_event)
            return
            
        self.view._original_mouse_move(event)"""
    if old_move in content:
        content = content.replace(old_move, new_move)

    with open(crop_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed drawing and panning.")

fix_view_events()
