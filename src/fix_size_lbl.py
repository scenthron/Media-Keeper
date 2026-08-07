import os

def fix_size_label():
    crop_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_crop_dialog.py'
    with open(crop_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Fix layout
    old_layout_part1 = """        right_layout.addWidget(self.lbl_preview)
        right_layout.addWidget(self.lbl_size)
        
        self.btn_clear = QPushButton("Очистить")"""
        
    new_layout_part1 = """        self.btn_clear = QPushButton("Очистить")"""
    content = content.replace(old_layout_part1, new_layout_part1)
    
    old_layout_part2 = """        right_layout.addWidget(QLabel("Предпросмотр фрагмента:"))
        right_layout.addWidget(self.lbl_preview)
        right_layout.addStretch()
        right_layout.addWidget(self.btn_clear)
        right_layout.addWidget(self.btn_ok)"""
        
    new_layout_part2 = """        right_layout.addWidget(QLabel("Предпросмотр фрагмента:"))
        right_layout.addWidget(self.lbl_preview)
        right_layout.addWidget(self.lbl_size)
        right_layout.addStretch()
        right_layout.addWidget(self.btn_clear)
        right_layout.addWidget(self.btn_ok)"""
    content = content.replace(old_layout_part2, new_layout_part2)

    # 2. Fix update_preview
    old_update = """    def update_preview(self):
        rect = self.overlay.get_crop_rect()
        if not rect.isNull():
            cropped_pixmap = self.pixmap.copy(rect.toRect())
            # Масштабируем превью, чтобы оно влезло в lbl_preview
            scaled = cropped_pixmap.scaled(self.lbl_preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.lbl_preview.setPixmap(scaled)
            self.btn_clear.setEnabled(True)
        else:
            self.lbl_preview.clear()
            self.lbl_preview.setText("Выделите область")
            self.btn_clear.setEnabled(False)"""
            
    new_update = """    def update_preview(self):
        rect = self.overlay.get_crop_rect()
        if not rect.isNull():
            cropped_pixmap = self.pixmap.copy(rect.toRect())
            scaled = cropped_pixmap.scaled(self.lbl_preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.lbl_preview.setPixmap(scaled)
            self.btn_clear.setEnabled(True)
            self.lbl_size.setText(f"Размер: {int(rect.width())} x {int(rect.height())}")
        else:
            self.lbl_preview.clear()
            self.lbl_preview.setText("Выделите область")
            self.btn_clear.setEnabled(False)
            self.lbl_size.setText("Размер: 0 x 0")"""
    content = content.replace(old_update, new_update)

    with open(crop_path, 'w', encoding='utf-8') as f:
        f.write(content)

fix_size_label()
