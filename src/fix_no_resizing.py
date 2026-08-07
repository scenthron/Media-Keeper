import os

def fix_no_resizing():
    frag_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(frag_path, 'r', encoding='utf-8') as f:
        content = f.read()

    old_run = """            import cv2
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

    new_run = """            import cv2
            img = safe_cv2_imread(self.target_frag_path)
            if img is None:
                self.finished_signal.emit(False, [])
                return
                
            if self.crop_rect:
                x, y = int(self.crop_rect.x()), int(self.crop_rect.y())
                w, h = int(self.crop_rect.width()), int(self.crop_rect.height())
                frag_img = img[y:y+h, x:x+w]
            else:
                frag_img = img
                
            f_kp, f_desc, f_shape, f_scale = engine.extract_features_from_img(frag_img, max_dim=99999)"""

    content = content.replace(old_run, new_run)

    old_extract = "t_kp, t_desc, t_shape, t_scale = engine.extract_features(filepath)"
    new_extract = "t_kp, t_desc, t_shape, t_scale = engine.extract_features(filepath, max_dim=99999)"
    content = content.replace(old_extract, new_extract)

    with open(frag_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
    # Clear cache so it doesn't use old 1920px cached features
    cache_dir = os.path.join(os.getenv('APPDATA'), "MediaKeeper", "cache", "orb")
    if os.path.exists(cache_dir):
        for f in os.listdir(cache_dir):
            try:
                os.remove(os.path.join(cache_dir, f))
            except:
                pass

fix_no_resizing()
print("Fixed ui_fragment_tab.py and cleared cache")
