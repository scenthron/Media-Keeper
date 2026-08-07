import os
import cv2

def update_logic_orb():
    orb_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\logic_orb.py'
    with open(orb_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Add match_template to OrbEngine
    new_method = """    def match_template(self, frag_bgr, target_bgr, tolerance):
        # Пиксельный поиск через cv2.matchTemplate
        try:
            if frag_bgr is None or target_bgr is None:
                return False, None, 0
                
            frag_h, frag_w = frag_bgr.shape[:2]
            target_h, target_w = target_bgr.shape[:2]
            
            if frag_h > target_h or frag_w > target_w:
                return False, None, 0
                
            res = cv2.matchTemplate(target_bgr, frag_bgr, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            
            # tolerance в UI от 0 до 100. 100 = 0.99, 0 = 0.70
            threshold = 0.7 + (tolerance / 100.0) * 0.29
            
            if max_val >= threshold:
                x, y = max_loc
                import numpy as np
                # Возвращаем рамку как полигон
                bbox = np.int32([[[x, y]], [[x, y + frag_h]], [[x + frag_w, y + frag_h]], [[x + frag_w, y]]])
                return True, bbox, int(max_val * 100)
            return False, None, 0
        except Exception as e:
            import logging
            logging.error(f"[TemplateMatch] Error: {e}")
            return False, None, 0"""

    if "def match_template" not in content:
        content = content.replace("class OrbEngine:", "class OrbEngine:\n" + new_method + "\n")
        
    with open(orb_path, 'w', encoding='utf-8') as f:
        f.write(content)

update_logic_orb()
print("Updated logic_orb.py")
