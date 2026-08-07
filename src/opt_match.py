import os

def optimize_pixel_search():
    orb_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\logic_orb.py'
    with open(orb_path, 'r', encoding='utf-8') as f:
        content = f.read()

    old_match = """    def match_template(self, frag_bgr, target_bgr, tolerance):
        # Пиксельный поиск через cv2.matchTemplate
        try:
            if frag_bgr is None or target_bgr is None:
                return False, None, 0
                
            frag_h, frag_w = frag_bgr.shape[:2]
            target_h, target_w = target_bgr.shape[:2]
            
            if frag_h > target_h or frag_w > target_w:
                return False, None, 0
                
            res = cv2.matchTemplate(target_bgr, frag_bgr, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)"""
            
    new_match = """    def match_template(self, frag_bgr, target_bgr, tolerance):
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
            res = cv2.matchTemplate(target_gray, frag_gray, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)"""
            
    if old_match in content:
        content = content.replace(old_match, new_match)
        with open(orb_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print("Optimized match_template.")
    else:
        print("Could not find match_template to replace.")

optimize_pixel_search()
