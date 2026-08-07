import os
import re

def rewrite_logic():
    frag_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(frag_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Update FragmentScannerThread __init__
    old_init = """    def __init__(self, dirs_to_scan, target_frag_path, crop_rect, tolerance, use_cache):
        super().__init__()
        self.dirs_to_scan = dirs_to_scan
        self.target_frag_path = target_frag_path
        self.crop_rect = crop_rect
        self.tolerance = tolerance # 0-100%
        self.use_cache = use_cache
        self.is_running = True"""

    new_init = """    def __init__(self, dirs_to_scan, target_frag_path, crop_rect, tolerance, use_cache, algorithm="pixel", max_features=10000):
        super().__init__()
        self.dirs_to_scan = dirs_to_scan
        self.target_frag_path = target_frag_path
        self.crop_rect = crop_rect
        self.tolerance = tolerance # 0-100%
        self.use_cache = use_cache
        self.algorithm = algorithm
        self.max_features = max_features
        self.is_running = True"""

    content = content.replace(old_init, new_init)

    # 2. Update FragmentScannerThread.run()
    old_run = """            from utils_io import safe_cv2_imread
            engine = OrbEngine()
            cache = OrbCacheManager()
            
            import cv2
            img = safe_cv2_imread(self.target_frag_path)
            if img is None:
                self.finished_signal.emit(False, "Не удалось загрузить исходное изображение")
                return
                
            x, y, w, h = self.crop_rect
            frag_img = img[y:y+h, x:x+w]
            
            f_kp, f_desc, f_shape, f_scale = engine.extract_features_from_img(frag_img, max_dim=99999)
            
            all_files = []
            for d in self.dirs_to_scan:
                for root, _, files in os.walk(d):
                    for f in files:
                        if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp')):
                            all_files.append(os.path.join(root, f))
                            
            total = len(all_files)
            results = []
            
            # Slider: 100% (Strict), 0% (Loose)
            ratio_thresh = 0.85 - (self.tolerance / 100.0) * 0.30
            min_match = max(4, int(4 + (7 - 4) * (self.tolerance / 100.0)))
            
            for i, filepath in enumerate(all_files):
                if not self.is_running:
                    break
                    
                self.progress_update.emit(i + 1, total, os.path.basename(filepath))
                
                t_kp, t_desc = None, None
                t_scale = 1.0
                
                if self.use_cache:
                    t_kp, t_desc, t_scale = cache.load_cache(filepath)
                    
                if t_desc is None:
                    t_kp, t_desc, t_shape, t_scale = engine.extract_features(filepath, max_dim=99999)
                    if self.use_cache and t_desc is not None:
                        cache.save_cache(filepath, t_kp, t_desc, t_scale)
                        
                success, bbox, count = engine.match(
                    f_kp, f_desc, f_shape, 
                    t_kp, t_desc, t_scale, 
                    ratio_thresh, min_match
                )
                
                if success:
                    results.append((filepath, bbox))"""

    new_run = """            from utils_io import safe_cv2_imread
            engine = OrbEngine(max_features=self.max_features)
            cache = OrbCacheManager()
            
            import cv2
            img = safe_cv2_imread(self.target_frag_path)
            if img is None:
                self.finished_signal.emit(False, "Не удалось загрузить исходное изображение")
                return
                
            x, y, w, h = self.crop_rect
            frag_img = img[y:y+h, x:x+w]
            
            if self.algorithm == "vector":
                f_kp, f_desc, f_shape, f_scale = engine.extract_features_from_img(frag_img, max_dim=99999)
            
            all_files = []
            for d in self.dirs_to_scan:
                for root, _, files in os.walk(d):
                    for f in files:
                        if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp')):
                            all_files.append(os.path.join(root, f))
                            
            total = len(all_files)
            results = []
            
            # SIFT Params
            ratio_thresh = 0.85 - (self.tolerance / 100.0) * 0.30
            min_match = max(4, int(4 + (7 - 4) * (self.tolerance / 100.0)))
            
            for i, filepath in enumerate(all_files):
                if not self.is_running:
                    break
                    
                self.progress_update.emit(i + 1, total, os.path.basename(filepath))
                
                if self.algorithm == "pixel":
                    target_img = safe_cv2_imread(filepath)
                    success, bbox, score = engine.match_template(frag_img, target_img, self.tolerance)
                    if success:
                        results.append((filepath, bbox))
                else:
                    t_kp, t_desc = None, None
                    t_scale = 1.0
                    
                    if self.use_cache:
                        t_kp, t_desc, t_scale = cache.load_cache(filepath)
                        
                    if t_desc is None:
                        t_kp, t_desc, t_shape, t_scale = engine.extract_features(filepath, max_dim=99999)
                        if self.use_cache and t_desc is not None:
                            cache.save_cache(filepath, t_kp, t_desc, t_scale)
                            
                    success, bbox, count = engine.match(
                        f_kp, f_desc, f_shape, 
                        t_kp, t_desc, t_scale, 
                        ratio_thresh, min_match
                    )
                    
                    if success:
                        results.append((filepath, bbox))"""
                        
    content = content.replace(old_run, new_run)

    # 3. Update start_scan
    old_start = """    def start_scan(self):
        if not self.target_frag_path or not self.crop_rect:
            QMessageBox.warning(self, "Ошибка", "Выберите фрагмент для поиска.")
            return
            
        dirs = []
        for i in range(self.sources_list_widget_fragment.topLevelItemCount()):
            item = self.sources_list_widget_fragment.topLevelItem(i)
            dirs.append(item.text(0))
            
        if not dirs:
            QMessageBox.warning(self, "Ошибка", "Добавьте папки для поиска.")
            return
            
        self.btn_start.setEnabled(False)
        self.table_fragment.setRowCount(0)
        self.lbl_stats.setText("Сканирование: подготовка...")
        
        self.active_worker = FragmentScannerThread(
            dirs, 
            self.target_frag_path, 
            self.crop_rect,
            self.slider_tolerance.value(),
            self.chk_use_cache.isChecked()
        )"""

    new_start = """    def start_scan(self):
        if not self.target_frag_path or not self.crop_rect:
            QMessageBox.warning(self, "Ошибка", "Выберите фрагмент для поиска.")
            return
            
        dirs = []
        for i in range(self.sources_list_widget_fragment.topLevelItemCount()):
            item = self.sources_list_widget_fragment.topLevelItem(i)
            dirs.append(item.text(0))
            
        if not dirs:
            QMessageBox.warning(self, "Ошибка", "Добавьте папки для поиска.")
            return
            
        self.btn_start.setEnabled(False)
        self.table_fragment.setRowCount(0)
        
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        self.lbl_stats.setText("Сканирование: подготовка...")
        
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        
        idx = self.settings_tabs.currentIndex()
        alg = "pixel" if idx == 0 else "vector"
        tol = self.slider_pixel.value() if idx == 0 else self.slider_tolerance.value()
        
        try:
            max_feat = int(self.combo_features.currentText())
        except:
            max_feat = 10000
            
        self.active_worker = FragmentScannerThread(
            dirs, 
            self.target_frag_path, 
            self.crop_rect,
            tol,
            self.chk_use_cache.isChecked() if alg == "vector" else False,
            algorithm=alg,
            max_features=max_feat
        )"""

    content = content.replace(old_start, new_start)

    # Add QApplication.processEvents() in _on_progress just in case
    old_prog = """    def _on_progress(self, current, total, msg):
        if not self.progress_bar.isVisible():
            self.progress_bar.show()
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
            self.progress_bar.setFormat(f"{int(current/total*100)}%")
        self.lbl_stats.setText(f"Сканирование: {current}/{total} | {msg}")"""

    new_prog = """    def _on_progress(self, current, total, msg):
        if not self.progress_bar.isVisible():
            self.progress_bar.show()
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
            self.progress_bar.setFormat(f"{int(current/total*100)}%")
        self.lbl_stats.setText(f"Сканирование: {current}/{total} | {msg}")
        # Принудительно отрисовываем прогресс-бар, чтобы он не зависал
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()"""

    content = content.replace(old_prog, new_prog)
    
    with open(frag_path, 'w', encoding='utf-8') as f:
        f.write(content)

rewrite_logic()
print("Updated FragmentScannerThread and start logic")
