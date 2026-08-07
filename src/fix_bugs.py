import os
import re

def fix_all():
    frag_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(frag_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Fix QMouseEvent import in ui_crop_dialog.py
    crop_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_crop_dialog.py'
    with open(crop_path, 'r', encoding='utf-8') as f:
        crop_content = f.read()
    if "from PyQt6.QtGui import QMouseEvent" not in crop_content:
        crop_content = crop_content.replace("from PyQt6.QtGui import QPixmap, QColor, QBrush, QPen, QPainter, QPainterPath", "from PyQt6.QtGui import QPixmap, QColor, QBrush, QPen, QPainter, QPainterPath, QMouseEvent")
        with open(crop_path, 'w', encoding='utf-8') as f:
            f.write(crop_content)

    # 2. Fix layout stretch in ui_fragment_tab.py
    if "top_layout.addLayout(col_dirs, 2)" in content:
        content = content.replace("top_layout.addLayout(col_ref, 1)", "top_layout.addLayout(col_ref, 3)")
        content = content.replace("top_layout.addLayout(col_dirs, 2)", "top_layout.addLayout(col_dirs, 4)")
        content = content.replace("top_layout.addLayout(col_params, 1)", "top_layout.addLayout(col_params, 3)")

    # 3. Add hover enter/leave to SingleFileDropZone for the delete button
    old_dropzone = """class SingleFileDropZone(DropZoneWidget):
    file_dropped = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        # Force square shape with fixed minimum size for aesthetics
        self.setFixedSize(180, 180)"""
        
    new_dropzone = """class SingleFileDropZone(DropZoneWidget):
    file_dropped = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFixedSize(180, 180)
        self.btn_del_img = None
        
    def enterEvent(self, event):
        if self.btn_del_img and not self.btn_del_img.isHidden() and getattr(self, 'has_image', False):
            self.btn_del_img.show()
        elif self.btn_del_img and getattr(self, 'has_image', False):
            self.btn_del_img.show()
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        if self.btn_del_img:
            self.btn_del_img.hide()
        super().leaveEvent(event)"""
    if old_dropzone in content:
        content = content.replace(old_dropzone, new_dropzone)

    # 4. Fix update_dropzone_preview for symmetrical image, click to crop, and delete button
    old_preview = """    def update_dropzone_preview(self):
        if not self.target_image_path:
            self.drop_zone.lbl_text.setText("Перетащите 1 фото\\nдля поиска фрагмента")
            self.drop_zone.btn_add.show()
            self.drop_zone.setStyleSheet(self.drop_zone.styleSheet().replace("border-color: #3b82f6;", ""))
            if hasattr(self.drop_zone, 'img_label'):
                self.drop_zone.img_label.hide()
            return
            
        pixmap = QPixmap(self.target_image_path)
        if self.crop_rect and not self.crop_rect.isNull():
            pixmap = pixmap.copy(self.crop_rect.toRect())
            
        scaled = pixmap.scaled(self.drop_zone.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.drop_zone.lbl_text.setText("")
        self.drop_zone.btn_add.hide()
        
        if not hasattr(self.drop_zone, 'img_label'):
            self.drop_zone.img_label = QLabel(self.drop_zone)
            self.drop_zone.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.drop_zone.layout().addWidget(self.drop_zone.img_label)
            
        self.drop_zone.img_label.setPixmap(scaled)
        self.drop_zone.img_label.show()
        self.drop_zone.setStyleSheet(self.drop_zone.styleSheet() + "border-color: #3b82f6;")"""
        
    new_preview = """    def update_dropzone_preview(self):
        if not self.target_image_path:
            self.drop_zone.has_image = False
            self.drop_zone.lbl_text.setText("Перетащите 1 фото\\nдля поиска фрагмента")
            self.drop_zone.lbl_text.show()
            self.drop_zone.btn_add.show()
            self.drop_zone.setStyleSheet(self.drop_zone.styleSheet().replace("border-color: #3b82f6;", ""))
            if hasattr(self.drop_zone, 'img_label'):
                self.drop_zone.img_label.hide()
            if hasattr(self.drop_zone, 'btn_del_img') and self.drop_zone.btn_del_img:
                self.drop_zone.btn_del_img.hide()
            # Restore icon if exists
            for i in range(self.drop_zone.layout().count()):
                w = self.drop_zone.layout().itemAt(i).widget()
                if isinstance(w, QLabel) and w != self.drop_zone.lbl_text and w != getattr(self.drop_zone, 'img_label', None):
                    w.show()
            return
            
        self.drop_zone.has_image = True
        pixmap = QPixmap(self.target_image_path)
        if self.crop_rect and not self.crop_rect.isNull():
            pixmap = pixmap.copy(self.crop_rect.toRect())
            
        # Symmetrical margins (3px)
        target_size = self.drop_zone.size()
        target_size.setWidth(target_size.width() - 6)
        target_size.height()
        scaled = pixmap.scaled(target_size.width(), target_size.height() - 6, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.drop_zone.lbl_text.hide()
        self.drop_zone.btn_add.hide()
        
        # Hide the icon label (which is the first widget)
        for i in range(self.drop_zone.layout().count()):
            w = self.drop_zone.layout().itemAt(i).widget()
            if isinstance(w, QLabel) and w != self.drop_zone.lbl_text and w != getattr(self.drop_zone, 'img_label', None):
                w.hide()
        
        if not hasattr(self.drop_zone, 'img_label'):
            self.drop_zone.img_label = QLabel(self.drop_zone)
            self.drop_zone.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.drop_zone.img_label.setCursor(Qt.CursorShape.PointingHandCursor)
            self.drop_zone.img_label.mousePressEvent = lambda e: self.open_crop_dialog()
            # Absolute positioning to avoid layout stretches
            self.drop_zone.img_label.setGeometry(3, 3, self.drop_zone.width()-6, self.drop_zone.height()-6)
            
        if not self.drop_zone.btn_del_img:
            self.drop_zone.btn_del_img = QPushButton("✕", self.drop_zone)
            self.drop_zone.btn_del_img.setFixedSize(24, 24)
            self.drop_zone.btn_del_img.setCursor(Qt.CursorShape.PointingHandCursor)
            self.drop_zone.btn_del_img.setStyleSheet("QPushButton { background-color: rgba(239, 68, 68, 0.85); color: white; border-radius: 12px; font-weight: bold; font-size: 14px; padding-bottom: 2px;} QPushButton:hover { background-color: #dc2626; }")
            self.drop_zone.btn_del_img.move(self.drop_zone.width() - 30, 6)
            self.drop_zone.btn_del_img.clicked.connect(self.clear_fragment)
            self.drop_zone.btn_del_img.hide()
            
        self.drop_zone.img_label.setPixmap(scaled)
        self.drop_zone.img_label.show()
        if self.drop_zone.underMouse():
            self.drop_zone.btn_del_img.show()
        if "border-color: #3b82f6;" not in self.drop_zone.styleSheet():
            self.drop_zone.setStyleSheet(self.drop_zone.styleSheet() + "border-color: #3b82f6;")"""
            
    if old_preview in content:
        content = content.replace(old_preview, new_preview)

    with open(frag_path, 'w', encoding='utf-8') as f:
        f.write(content)

fix_all()
