import sys

with open('src/modules/cleaner/ui_ai_tab.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Update populate_results
code = code.replace(
'''                file_item.setData(0, Qt.ItemDataRole.UserRole, {"is_group": False, "path": f["path"], "size": f["size"], "confidence": f.get("confidence", 0.0) / 100.0})''',
'''                file_item.setData(0, Qt.ItemDataRole.UserRole, {"is_group": False, "path": f["path"], "size": f["size"], "confidence": f.get("confidence", 0.0) / 100.0, "matched_bbox": f.get("matched_bbox")})''')

# 2. Update draw_faces call
old_call = '''                    if faces:
                        bboxes = [f.get("bbox") for f in faces if f.get("bbox")]
                        if hasattr(self.preview_widget, "draw_faces"):
                            self.preview_widget.draw_faces(bboxes)'''
                            
new_call = '''                    if faces:
                        bboxes = [f.get("bbox") for f in faces if f.get("bbox")]
                        matched_bbox = user_data.get("matched_bbox") if user_data else None
                        if hasattr(self.preview_widget, "draw_faces"):
                            self.preview_widget.draw_faces(bboxes, matched_bbox=matched_bbox)'''

code = code.replace(old_call, new_call)

with open('src/modules/cleaner/ui_ai_tab.py', 'w', encoding='utf-8') as f:
    f.write(code)

with open('src/modules/cleaner/ui_preview.py', 'r', encoding='utf-8') as f:
    code = f.read()

old_draw = '''    def draw_faces(self, bboxes):
        self.clear_faces()
        if not bboxes: return
        from PyQt6.QtWidgets import QGraphicsRectItem
        from PyQt6.QtGui import QPen, QColor
        from PyQt6.QtCore import Qt
        for bbox in bboxes:
            if len(bbox) == 4:
                x1, y1, x2, y2 = bbox
                rect = QGraphicsRectItem(x1, y1, x2 - x1, y2 - y1)
                pen = QPen(QColor(34, 197, 94)) # Зеленый цвет
                pen.setWidth(3)
                pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
                rect.setPen(pen)
                self.scene.addItem(rect)'''

new_draw = '''    def draw_faces(self, bboxes, matched_bbox=None):
        self.clear_faces()
        if not bboxes: return
        from PyQt6.QtWidgets import QGraphicsRectItem
        from PyQt6.QtGui import QPen, QColor
        from PyQt6.QtCore import Qt
        for bbox in bboxes:
            if len(bbox) == 4:
                x1, y1, x2, y2 = bbox
                rect = QGraphicsRectItem(x1, y1, x2 - x1, y2 - y1)
                
                is_matched = False
                if matched_bbox and len(matched_bbox) == 4:
                    mx1, my1, mx2, my2 = matched_bbox
                    if abs(x1 - mx1) < 5 and abs(y1 - my1) < 5:
                        is_matched = True
                        
                if is_matched or matched_bbox is None:
                    pen = QPen(QColor(34, 197, 94)) # Green
                else:
                    pen = QPen(QColor(239, 68, 68)) # Red
                pen.setWidth(3)
                pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
                rect.setPen(pen)
                self.scene.addItem(rect)'''

code = code.replace(old_draw, new_draw)

with open('src/modules/cleaner/ui_preview.py', 'w', encoding='utf-8') as f:
    f.write(code)
    
print("UI patched!")
