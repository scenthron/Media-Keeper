import os
import re

def fix_all():
    # 1. Fix FragmentScannerThread to actually use pixel search
    frag_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(frag_path, 'r', encoding='utf-8') as f:
        content = f.read()

    old_loop = """                t_kp, t_desc, t_scale = None, None, 1.0
                if self.use_cache:
                    t_kp, t_desc, t_scale = cache.load_cache(filepath)
                    
                if t_desc is None:
                    t_kp, t_desc, t_shape, t_scale = engine.extract_features(filepath, max_dim=99999)
                    if self.use_cache and t_desc is not None:
                        cache.save_cache(filepath, t_kp, t_desc, t_scale)
                
                if t_desc is not None:
                    found, bbox, match_count = engine.match(f_kp, f_desc, f_shape, t_kp, t_desc, t_scale, 
                                                            ratio_thresh=ratio_thresh, min_match_count=min_match)
                    if found:
                        score = min(100, int((match_count / max(1, len(f_kp))) * 100 * 2))
                        results.append((filepath, score, bbox))"""
                        
    new_loop = """                if self.algorithm == "pixel":
                    from utils_io import safe_cv2_imread
                    t_img = safe_cv2_imread(filepath)
                    if t_img is not None:
                        found, bbox, score_raw = engine.match_template(frag_img, t_img, self.tolerance)
                        if found:
                            score = min(100, int(score_raw * 100))
                            results.append((filepath, score, bbox))
                else:
                    t_kp, t_desc, t_scale = None, None, 1.0
                    if self.use_cache:
                        t_kp, t_desc, t_scale = cache.load_cache(filepath)
                        
                    if t_desc is None:
                        t_kp, t_desc, t_shape, t_scale = engine.extract_features(filepath, max_dim=99999)
                        if self.use_cache and t_desc is not None:
                            cache.save_cache(filepath, t_kp, t_desc, t_scale)
                    
                    if t_desc is not None:
                        found, bbox, match_count = engine.match(f_kp, f_desc, f_shape, t_kp, t_desc, t_scale, 
                                                                ratio_thresh=ratio_thresh, min_match_count=min_match)
                        if found:
                            score = min(100, int((match_count / max(1, len(f_kp))) * 100 * 2))
                            results.append((filepath, score, bbox))"""
                            
    if old_loop in content:
        content = content.replace(old_loop, new_loop)
        with open(frag_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print("Fixed FragmentScannerThread logic.")
        
    # 2. Fix ui_crop_dialog.py for size label and middle mouse drag
    crop_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_crop_dialog.py'
    with open(crop_path, 'r', encoding='utf-8') as f:
        crop_content = f.read()

    # Size label UI
    if "self.lbl_size =" not in crop_content:
        old_ui = """        self.lbl_preview.setStyleSheet(f"border: 1px solid #444; background: #1a1a1a;")
        
        self.btn_clear = QPushButton("Очистить")"""
        
        new_ui = """        self.lbl_preview.setStyleSheet(f"border: 1px solid #444; background: #1a1a1a;")
        
        self.lbl_size = QLabel("Размер: 0 x 0")
        self.lbl_size.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_size.setStyleSheet("color: #aaa; font-size: 11px;")
        
        right_layout.addWidget(self.lbl_preview)
        right_layout.addWidget(self.lbl_size)
        
        self.btn_clear = QPushButton("Очистить")"""
        crop_content = crop_content.replace(old_ui, new_ui)

    # Size label update
    if "self.lbl_size.setText" not in crop_content:
        old_update = """            self.lbl_preview.setPixmap(preview_pixmap)
        else:
            self.lbl_preview.clear()"""
            
        new_update = """            self.lbl_preview.setPixmap(preview_pixmap)
            self.lbl_size.setText(f"Размер: {int(w)} x {int(h)}")
        else:
            self.lbl_preview.clear()
            self.lbl_size.setText("Размер: 0 x 0")"""
        crop_content = crop_content.replace(old_update, new_update)

    # Mouse drag events
    if "MiddleButton" not in crop_content:
        old_view_init = """        self.view.mousePressEvent = self._view_mouse_press"""
        
        new_view_init = """        self.view.mousePressEvent = self._view_mouse_press
        self.view.mouseReleaseEvent = self._view_mouse_release
        self.view.mouseMoveEvent = self._view_mouse_move
        self.view._pan_active = False"""
        crop_content = crop_content.replace(old_view_init, new_view_init)

        methods_to_add = """    def _view_mouse_press(self, event):
        from PyQt6.QtCore import Qt
        if event.button() == Qt.MouseButton.MiddleButton:
            self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.view._pan_active = True
            # Fake left click to initiate ScrollHandDrag
            fake_event = QMouseEvent(event.type(), event.pos(), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, event.modifiers())
            super(QGraphicsView, self.view).mousePressEvent(fake_event)
            return
            
        if self.view.itemAt(event.pos()) == self.overlay:
            scene_pos = self.view.mapToScene(event.pos())
            self.drag_start = scene_pos
            self.drawing = True
            self.crop_rect = QRectF(scene_pos, scene_pos)
            self.overlay.set_rect(self.crop_rect)
        self.view._original_mouse_press(event)

    def _view_mouse_release(self, event):
        from PyQt6.QtCore import Qt
        if event.button() == Qt.MouseButton.MiddleButton and getattr(self.view, '_pan_active', False):
            fake_event = QMouseEvent(event.type(), event.pos(), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, event.modifiers())
            super(QGraphicsView, self.view).mouseReleaseEvent(fake_event)
            self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.view._pan_active = False
            return
        super(QGraphicsView, self.view).mouseReleaseEvent(event)
        
    def _view_mouse_move(self, event):
        super(QGraphicsView, self.view).mouseMoveEvent(event)\n"""

        # Replace existing _view_mouse_press
        import re
        pattern = re.compile(r'    def _view_mouse_press\(self, event\):.*?        self\.view\._original_mouse_press\(event\)', re.DOTALL)
        if pattern.search(crop_content):
            crop_content = pattern.sub(methods_to_add, crop_content)
        
        # Add imports for QMouseEvent at the top of ui_crop_dialog.py
        if "from PyQt6.QtGui import QMouseEvent" not in crop_content:
            crop_content = crop_content.replace("from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen", "from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QMouseEvent")

    with open(crop_path, 'w', encoding='utf-8') as f:
        f.write(crop_content)
    print("Fixed Crop Dialog.")

fix_all()
