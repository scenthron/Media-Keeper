import os

def fix_speed():
    frag_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(frag_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # We find the loop start
    old_loop_block = """            for idx, filepath in enumerate(all_files):
                if not self.is_running:
                    break
                    
                self.progress_update.emit(idx + 1, total, filepath)"""
                
    new_loop = """            import time
            last_progress_time = time.time()
            
            for idx, filepath in enumerate(all_files):
                if not self.is_running:
                    break
                    
                current_time = time.time()
                if current_time - last_progress_time > 0.05 or idx == total - 1:
                    import os
                    self.progress_update.emit(idx + 1, total, os.path.basename(filepath))
                    last_progress_time = current_time"""
                    
    if old_loop_block in content:
        content = content.replace(old_loop_block, new_loop)
        
    with open(frag_path, 'w', encoding='utf-8') as f:
        f.write(content)

fix_speed()
