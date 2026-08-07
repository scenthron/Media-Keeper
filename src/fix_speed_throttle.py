import os

def fix_speed_throttle():
    frag_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(frag_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Change 0.05 to 0.2 (5 updates per second)
    old_throttle = "if current_time - last_progress_time > 0.05 or idx == total - 1:"
    new_throttle = "if current_time - last_progress_time > 0.2 or idx == total - 1:"
    
    if old_throttle in content:
        content = content.replace(old_throttle, new_throttle)
        with open(frag_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print("Updated throttle to 0.2s (5 times per second)")
    else:
        print("Could not find the throttle condition to replace.")

fix_speed_throttle()
