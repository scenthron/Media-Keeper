import os

def fix_all_algos():
    # 1. Update logic_orb.py
    orb_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\logic_orb.py'
    with open(orb_path, 'r', encoding='utf-8') as f:
        orb_content = f.read()

    old_match = """    def match_template(self, frag_bgr, target_bgr, tolerance):
        # Пиксельный поиск через cv2.matchTemplate
        try:
            if frag_bgr is None or target_bgr is None:
                return False, None, 0
                
            frag_h, frag_w = frag_bgr.shape[:2]
            target_h, target_w = target_bgr.shape[:2]
            
            if frag_h > target_h or frag_w > target_w:
                return False, None, 0
                
            # Optimize by converting to grayscale (3x faster)
            import cv2
            if len(frag_bgr.shape) == 3:
                frag_gray = cv2.cvtColor(frag_bgr, cv2.COLOR_BGR2GRAY)
            else:
                frag_gray = frag_bgr
                
            if len(target_bgr.shape) == 3:
                target_gray = cv2.cvtColor(target_bgr, cv2.COLOR_BGR2GRAY)
            else:
                target_gray = target_bgr
                
            # If images are huge, matchTemplate is still slow. 
            # We can use TM_CCOEFF_NORMED which is robust.
            res = cv2.matchTemplate(target_gray, frag_gray, cv2.TM_CCOEFF_NORMED)"""
            
    new_match = """    def match_template(self, frag_bgr, target_bgr, tolerance, optimize_bw=False):
        # Пиксельный поиск через cv2.matchTemplate
        try:
            if frag_bgr is None or target_bgr is None:
                return False, None, 0
                
            frag_h, frag_w = frag_bgr.shape[:2]
            target_h, target_w = target_bgr.shape[:2]
            
            if frag_h > target_h or frag_w > target_w:
                return False, None, 0
                
            import cv2
            if optimize_bw:
                if len(frag_bgr.shape) == 3:
                    frag_img = cv2.cvtColor(frag_bgr, cv2.COLOR_BGR2GRAY)
                else:
                    frag_img = frag_bgr
                if len(target_bgr.shape) == 3:
                    target_img = cv2.cvtColor(target_bgr, cv2.COLOR_BGR2GRAY)
                else:
                    target_img = target_bgr
            else:
                frag_img = frag_bgr
                target_img = target_bgr
                
            res = cv2.matchTemplate(target_img, frag_img, cv2.TM_CCOEFF_NORMED)"""
            
    if old_match in orb_content:
        orb_content = orb_content.replace(old_match, new_match)
        with open(orb_path, 'w', encoding='utf-8') as f:
            f.write(orb_content)

    # 2. Update ui_fragment_tab.py
    frag_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(frag_path, 'r', encoding='utf-8') as f:
        frag_content = f.read()

    # Add Checkbox
    old_pixel_desc = """        desc_pixel = QLabel("Мгновенный поиск. Чувствителен к изменению масштаба." if AppContext.is_ru() else "Instant search. Sensitive to scale changes.")
        desc_pixel.setStyleSheet("color: #888; font-size: 11px;")
        desc_pixel.setWordWrap(True)
        tab_pixel_layout.addWidget(desc_pixel)"""
        
    new_pixel_desc = """        desc_pixel = QLabel("Мгновенный поиск. Чувствителен к изменению масштаба." if AppContext.is_ru() else "Instant search. Sensitive to scale changes.")
        desc_pixel.setStyleSheet("color: #888; font-size: 11px;")
        desc_pixel.setWordWrap(True)
        tab_pixel_layout.addWidget(desc_pixel)
        
        self.chk_pixel_bw = QCheckBox("Черно-белый режим (Ускорение x3)")
        self.chk_pixel_bw.setStyleSheet("QCheckBox { color: #ccc; font-weight: bold; font-size: 11px; margin-top: 5px; } QCheckBox::indicator { width: 14px; height: 14px; border-radius: 3px; border: 1px solid #555; background: #111; } QCheckBox::indicator:checked { background-color: #3b82f6; border-color: #3b82f6; }")
        self.chk_pixel_bw.setChecked(False)
        tab_pixel_layout.addWidget(self.chk_pixel_bw)"""
    if old_pixel_desc in frag_content:
        frag_content = frag_content.replace(old_pixel_desc, new_pixel_desc)

    # Update FragmentScannerThread.__init__
    old_thread_init = """    def __init__(self, dirs_to_scan, target_frag_path, crop_rect, tolerance, use_cache, algorithm="pixel", max_features=10000, filter_config=None):
        super().__init__()
        self.dirs_to_scan = dirs_to_scan
        self.filter_config = filter_config or {'mode': 'all', 'exts': []}
        self.target_frag_path = target_frag_path
        self.crop_rect = crop_rect
        self.tolerance = tolerance # 0-100%
        self.use_cache = use_cache
        self.algorithm = algorithm
        self.max_features = max_features
        self.is_running = True"""
        
    new_thread_init = """    def __init__(self, dirs_to_scan, target_frag_path, crop_rect, tolerance, use_cache, algorithm="pixel", max_features=10000, filter_config=None, optimize_bw=False):
        super().__init__()
        self.dirs_to_scan = dirs_to_scan
        self.filter_config = filter_config or {'mode': 'all', 'exts': []}
        self.target_frag_path = target_frag_path
        self.crop_rect = crop_rect
        self.tolerance = tolerance # 0-100%
        self.use_cache = use_cache
        self.algorithm = algorithm
        self.max_features = max_features
        self.optimize_bw = optimize_bw
        self.is_running = True"""
    if old_thread_init in frag_content:
        frag_content = frag_content.replace(old_thread_init, new_thread_init)

    # Update FragmentScannerThread.run pixel match
    old_match_call = """                        found, bbox, score_raw = engine.match_template(frag_img, t_img, self.tolerance)"""
    new_match_call = """                        found, bbox, score_raw = engine.match_template(frag_img, t_img, self.tolerance, getattr(self, 'optimize_bw', False))"""
    if old_match_call in frag_content:
        frag_content = frag_content.replace(old_match_call, new_match_call)

    # Update start_scan
    old_start = """        self.active_worker = FragmentScannerThread(
            dirs, 
            self.target_image_path, 
            self.crop_rect,
            self.slider_tolerance.value(),
            self.chk_use_cache.isChecked()
        )
        self.active_worker.progress_update.connect(self._on_progress)"""
        
    new_start = """        alg = "pixel" if self.settings_tabs.currentIndex() == 0 else "vector"
        tol = self.slider_pixel.value() if alg == "pixel" else self.slider_tolerance.value()
        
        self.active_worker = FragmentScannerThread(
            dirs, 
            self.target_image_path, 
            self.crop_rect,
            tol,
            self.chk_use_cache.isChecked(),
            algorithm=alg,
            max_features=int(self.combo_features.currentText()) if hasattr(self, 'combo_features') else 10000,
            optimize_bw=getattr(self, 'chk_pixel_bw', None) and self.chk_pixel_bw.isChecked() if alg == "pixel" else False
        )
        self.active_worker.progress_update.connect(self._on_progress)"""
    if old_start in frag_content:
        frag_content = frag_content.replace(old_start, new_start)

    with open(frag_path, 'w', encoding='utf-8') as f:
        f.write(frag_content)

fix_all_algos()
