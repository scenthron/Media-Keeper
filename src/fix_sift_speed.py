import os
import re

def fix_sift_speed():
    orb_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\logic_orb.py'
    with open(orb_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find self.orb = cv2.SIFT_create() and replace with self.orb = cv2.SIFT_create(nfeatures=10000)
    content = content.replace(
        "self.orb = cv2.SIFT_create()",
        "self.orb = cv2.SIFT_create(nfeatures=10000)"
    )

    with open(orb_path, 'w', encoding='utf-8') as f:
        f.write(content)

    # Clear cache since we changed nfeatures
    cache_dir = os.path.join(os.getenv('APPDATA'), "MediaKeeper", "cache", "orb")
    if os.path.exists(cache_dir):
        for f in os.listdir(cache_dir):
            try:
                os.remove(os.path.join(cache_dir, f))
            except:
                pass

fix_sift_speed()
print("Applied speed optimization for SIFT")
