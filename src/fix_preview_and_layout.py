import os

def fix_all():
    # 1. Fix ui_preview.py to handle polygon draw
    preview_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_preview.py'
    with open(preview_path, 'r', encoding='utf-8') as f:
        content = f.read()

    new_clear_faces = """    def clear_faces(self):
        # Удаляем все прямоугольники и полигоны
        for item in self.scene.items():
            from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsPolygonItem
            if isinstance(item, (QGraphicsRectItem, QGraphicsPolygonItem)):
                self.scene.removeItem(item)"""

    import re
    content = re.sub(r'    def clear_faces\(self\):.*?self\.scene\.removeItem\(item\)', new_clear_faces, content, flags=re.DOTALL)

    new_draw_polygon = """
    def draw_polygon(self, pts):
        if not self.scene or not self.pixmap_item: return
        self.clear_faces()
        if pts is None or len(pts) == 0: return
        
        from PyQt6.QtWidgets import QGraphicsPolygonItem
        from PyQt6.QtGui import QPen, QColor, QPolygonF
        from PyQt6.QtCore import Qt, QPointF
        
        poly = QPolygonF()
        try:
            for pt in pts:
                x, y = pt[0][0], pt[0][1]
                poly.append(QPointF(float(x), float(y)))
        except:
            return
            
        poly_item = QGraphicsPolygonItem(poly)
        pen = QPen(QColor(59, 130, 246, 255))
        pen.setWidth(4)
        poly_item.setPen(pen)
        poly_item.setZValue(10)
        self.scene.addItem(poly_item)
"""
    if "def draw_polygon" not in content:
        content += new_draw_polygon

    with open(preview_path, 'w', encoding='utf-8') as f:
        f.write(content)


    # 2. Fix ui_fragment_tab.py
    frag_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(frag_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace draw_faces with draw_polygon
    content = content.replace(
        'if bbox is not None and hasattr(self.preview_widget, "draw_faces"):',
        'if bbox is not None and hasattr(self.preview_widget, "draw_polygon"):'
    )
    content = content.replace(
        'self.preview_widget.draw_faces([bbox], matched_bbox=bbox)',
        'self.preview_widget.draw_polygon(bbox)'
    )

    # Fix action bar layout
    old_layout = """        bottom_right_widget = QWidget()
        bottom_right_layout = QVBoxLayout(bottom_right_widget)
        bottom_right_layout.setContentsMargins(0, 0, 0, 0)
        bottom_right_layout.addWidget(self.action_bar)
        bottom_right_layout.addWidget(self.tree_results)

        self.right_splitter.addWidget(bottom_right_widget)
        self.right_splitter.addWidget(self.preview_widget)
        self.right_splitter.setStretchFactor(0, 7)
        self.right_splitter.setStretchFactor(1, 3)
        
        bottom_layout.addWidget(self.right_splitter, 1)"""

    new_layout = """        bottom_right_widget = QWidget()
        bottom_right_layout = QVBoxLayout(bottom_right_widget)
        bottom_right_layout.setContentsMargins(0, 0, 0, 0)
        bottom_right_layout.addWidget(self.tree_results)

        self.right_splitter.addWidget(bottom_right_widget)
        self.right_splitter.addWidget(self.preview_widget)
        self.right_splitter.setStretchFactor(0, 1)
        self.right_splitter.setStretchFactor(1, 1)
        
        # Action bar to the main layout to span full width
        bottom_layout.addWidget(self.action_bar)
        bottom_layout.addWidget(self.right_splitter, 1)
        
        from PyQt6.QtCore import QTimer
        def apply_splitter_sizes():
            self.right_splitter.setSizes([600, 400])
        QTimer.singleShot(0, apply_splitter_sizes)"""

    content = content.replace(old_layout, new_layout)

    with open(frag_path, 'w', encoding='utf-8') as f:
        f.write(content)

fix_all()
print("Fixed ui_preview.py and ui_fragment_tab.py")
