import os

def fix_all():
    # 1. Fix ui_crop_dialog.py
    crop_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_crop_dialog.py'
    with open(crop_path, 'r', encoding='utf-8') as f:
        content = f.read()

    new_load_image = """    def load_image(self, previous_crop_rect):
        from utils_io import safe_cv2_imread
        import cv2
        from PyQt6.QtGui import QImage
        img = safe_cv2_imread(self.image_path)
        if img is not None:
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            h, w, ch = img_rgb.shape
            qimg = QImage(img_rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
            self.pixmap = QPixmap.fromImage(qimg)
        else:
            self.pixmap = QPixmap(self.image_path)
        
        self.image_item = self.scene.addPixmap(self.pixmap)"""

    import re
    content = re.sub(r'    def load_image\(self, previous_crop_rect\):.*?self\.image_item = self\.scene\.addPixmap\(self\.pixmap\)', new_load_image, content, flags=re.DOTALL)
    
    with open(crop_path, 'w', encoding='utf-8') as f:
        f.write(content)

    # 2. Fix ui_fragment_tab.py
    frag_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(frag_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Fix cache layout and styles
    old_cache = """        # CACHE
        cache_layout = QHBoxLayout()
        self.chk_use_cache = QCheckBox("Кэшировать анализ (ORB)" if AppContext.is_ru() else "Cache ORB Analysis")
        self.chk_use_cache.setChecked(True)
        self.chk_use_cache.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_use_cache.setStyleSheet("QCheckBox { color: #eee; font-weight: bold; font-size: 12px; }")
        cache_layout.addWidget(self.chk_use_cache)
        cache_layout.addStretch()
        
        self.lbl_cache_info_fragment = QLabel("0 B")
        self.lbl_cache_info_fragment.setStyleSheet("color: #888; font-size: 11px;")
        cache_layout.addWidget(self.lbl_cache_info_fragment)
        
        from .ui_panels import load_svg_icon
        self.btn_clear_cache_fragment = QPushButton()
        self.btn_clear_cache_fragment.setIcon(load_svg_icon("trash.svg", "#ef4444"))
        self.btn_clear_cache_fragment.setIconSize(QSize(16, 16))
        self.btn_clear_cache_fragment.setToolTip("Очистить кэш ORB")
        self.btn_clear_cache_fragment.setFixedSize(32, 32)
        self.btn_clear_cache_fragment.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_cache_fragment.setStyleSheet("QPushButton { background-color: transparent; border: 1px solid #555; border-radius: 16px; padding: 0px; } QPushButton:hover { background-color: #444; border-color: #ef4444; }")
        self.btn_clear_cache_fragment.clicked.connect(self.clear_orb_cache)
        cache_layout.addWidget(self.btn_clear_cache_fragment)
        params_sub_layout.addLayout(cache_layout)"""

    new_cache = """        # CACHE
        cache_layout = QHBoxLayout()
        self.chk_use_cache = QCheckBox("Использовать кэш" if AppContext.is_ru() else "Use Cache")
        self.chk_use_cache.setChecked(True)
        self.chk_use_cache.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_use_cache.setStyleSheet(\"\"\"
            QCheckBox { color: white; font-weight: bold; font-size: 13px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 3px; border: 1px solid #555; background: #111; }
            QCheckBox::indicator:checked { background-color: #3b82f6; border-color: #3b82f6; }
        \"\"\")
        cache_layout.addWidget(self.chk_use_cache)
        cache_layout.addStretch()
        
        self.lbl_cache_info_fragment = QLabel("0 B")
        self.lbl_cache_info_fragment.setStyleSheet("color: #888; font-size: 12px; margin-right: 5px;")
        cache_layout.addWidget(self.lbl_cache_info_fragment)
        
        from .ui_panels import load_svg_icon
        self.btn_clear_cache_fragment = QPushButton()
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
        self.btn_clear_cache_fragment.setIcon(load_svg_icon(os.path.join(icons_dir, "trash-color.svg"), QSize(16, 16)))
        self.btn_clear_cache_fragment.setIconSize(QSize(16, 16))
        self.btn_clear_cache_fragment.setToolTip("Очистить кэш ORB" if AppContext.is_ru() else "Clear ORB Cache")
        self.btn_clear_cache_fragment.setFixedSize(32, 32)
        self.btn_clear_cache_fragment.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_cache_fragment.setStyleSheet(\"\"\"
            QPushButton { background-color: #2b2b2b; border: 1px solid #444; border-radius: 16px; padding: 0px; }
            QPushButton:hover { background-color: #444; border-color: #666; }
        \"\"\")
        self.btn_clear_cache_fragment.clicked.connect(self.clear_orb_cache)
        cache_layout.addWidget(self.btn_clear_cache_fragment)
        params_sub_layout.addLayout(cache_layout)"""
    
    content = content.replace(old_cache, new_cache)

    # Fix run method logic
    old_run = """            img = safe_cv2_imread(self.target_frag_path)
            if img is None:
                self.finished_signal.emit(False, [])
                return
                
            if self.crop_rect:
                x, y, w, h = int(self.crop_rect.x()), int(self.crop_rect.y()), int(self.crop_rect.width()), int(self.crop_rect.height())
                frag_img = img[y:y+h, x:x+w]
            else:
                frag_img = img
                
            f_kp, f_desc, f_shape, f_scale = engine.extract_features_from_img(frag_img)"""
            
    new_run = """            import cv2
            img = safe_cv2_imread(self.target_frag_path)
            if img is None:
                self.finished_signal.emit(False, [])
                return
                
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, img_scale = engine._resize_if_needed(gray, 1920)
                
            if self.crop_rect:
                x = int(self.crop_rect.x() * img_scale)
                y = int(self.crop_rect.y() * img_scale)
                w = int(self.crop_rect.width() * img_scale)
                h = int(self.crop_rect.height() * img_scale)
                img_resized = cv2.resize(img, (0, 0), fx=img_scale, fy=img_scale)
                frag_img = img_resized[y:y+h, x:x+w]
            else:
                frag_img = cv2.resize(img, (0, 0), fx=img_scale, fy=img_scale)
                
            f_kp, f_desc, f_shape, f_scale = engine.extract_features_from_img(frag_img)"""
            
    content = content.replace(old_run, new_run)

    content = content.replace(
        "min_match = max(4, int(15 * (1 - self.tolerance / 100.0)))",
        "min_match = max(4, int(10 * (1 - self.tolerance / 100.0)))"
    )

    old_update_cache = """    def update_cache_info_fragment(self):
        try:
            cache = OrbCacheManager()
            db_path = cache.db_path
            if os.path.exists(db_path):
                size = os.path.getsize(db_path)
                wal_path = db_path + "-wal"
                shm_path = db_path + "-shm"
                if os.path.exists(wal_path): size += os.path.getsize(wal_path)
                if os.path.exists(shm_path): size += os.path.getsize(shm_path)
                self.lbl_cache_info_fragment.setText(f"{format_size(size)}")
            else:
                self.lbl_cache_info_fragment.setText("0 B")
        except Exception as e:
            self.lbl_cache_info_fragment.setText("0 B")"""
            
    new_update_cache = """    def update_cache_info_fragment(self):
        try:
            cache = OrbCacheManager()
            size = 0
            if os.path.exists(cache.cache_dir):
                for f in os.listdir(cache.cache_dir):
                    fp = os.path.join(cache.cache_dir, f)
                    if os.path.isfile(fp):
                        size += os.path.getsize(fp)
                self.lbl_cache_info_fragment.setText(f"{format_size(size)}")
            else:
                self.lbl_cache_info_fragment.setText("0 B")
        except Exception as e:
            self.lbl_cache_info_fragment.setText("0 B")"""
            
    content = content.replace(old_update_cache, new_update_cache)

    with open(frag_path, 'w', encoding='utf-8') as f:
        f.write(content)

fix_all()
print("Fixed ui_crop_dialog.py and ui_fragment_tab.py")
