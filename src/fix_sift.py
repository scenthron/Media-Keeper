import sys
import os
import cv2

def apply_sift_fix():
    orb_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\logic_orb.py'
    with open(orb_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace ORB with SIFT
    old_init = """    def __init__(self, max_features=50000):
        # Инициализация ORB
        self.orb = cv2.ORB_create(nfeatures=max_features)
        
        # Настройка матчера (для ORB лучше всего подходит NORM_HAMMING)
        # crossCheck=False, так как мы будем использовать knnMatch и Lowe's ratio test
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)"""

    new_init = """    def __init__(self, max_features=0):
        # Инициализация SIFT (работает гораздо точнее для вырезанных фрагментов)
        self.orb = cv2.SIFT_create()
        
        # Настройка матчера (для SIFT используется NORM_L2)
        self.matcher = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)"""

    content = content.replace(old_init, new_init)
    
    with open(orb_path, 'w', encoding='utf-8') as f:
        f.write(content)

    # In ui_fragment_tab.py, we also need to adjust the slider mapping for SIFT
    # SIFT works best with ratio between 0.6 and 0.8
    # If slider is 100% (Strict), ratio = 0.55, min_match = 7
    # If slider is 0% (Loose), ratio = 0.85, min_match = 4
    
    frag_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(frag_path, 'r', encoding='utf-8') as f:
        frag_content = f.read()
        
    old_logic = """            # Slider: 100% (Strict), 0% (Loose)
            ratio_thresh = 0.85 - (self.tolerance / 100.0) * 0.15
            min_match = max(4, int(4 + (15 - 4) * (self.tolerance / 100.0)))"""
            
    new_logic = """            # Slider: 100% (Strict), 0% (Loose)
            ratio_thresh = 0.85 - (self.tolerance / 100.0) * 0.30
            min_match = max(4, int(4 + (7 - 4) * (self.tolerance / 100.0)))"""

    frag_content = frag_content.replace(old_logic, new_logic)
    
    # Also fix ui text from ORB to SIFT
    frag_content = frag_content.replace('Очистить кэш ORB', 'Очистить кэш')
    
    with open(frag_path, 'w', encoding='utf-8') as f:
        f.write(frag_content)
        
    # Clear cache again
    cache_dir = os.path.join(os.getenv('APPDATA'), "MediaKeeper", "cache", "orb")
    if os.path.exists(cache_dir):
        for f in os.listdir(cache_dir):
            try:
                os.remove(os.path.join(cache_dir, f))
            except:
                pass

apply_sift_fix()
print("Switched from ORB to SIFT")
