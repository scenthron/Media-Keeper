
import os
from PIL import Image
from PyQt6.QtCore import QThread, pyqtSignal

class ImageConverterWorker(QThread):
    file_progress = pyqtSignal(str, int) # path, percent
    file_finished = pyqtSignal(str, bool, str) # path, success, result_path_or_error
    all_finished = pyqtSignal()
    
    def __init__(self, queue, settings):
        super().__init__()
        self.queue = queue
        self.settings = settings
        self.is_running = True

    def run(self):
        for file_info in self.queue:
            if not self.is_running: break
            
            path = file_info['path']
            try:
                self.process_file(file_info)
            except Exception as e:
                self.file_finished.emit(path, False, str(e))
        
        self.all_finished.emit()

    def process_file(self, info):
        src_path = info['path']
        s = self.settings
        
        # 1. Output Path Logic
        out_dir = s['output_dir'] or os.path.dirname(src_path)
        base_name, _ = os.path.splitext(os.path.basename(src_path))
        ext = "." + s['format'].replace("jpg", "jpeg")
        
        target_name = base_name
        if s['rename']:
            tmpl = s['name_tmpl']
            target_name = f"{tmpl}{base_name}" if s['rename_prefix'] else f"{base_name}{tmpl}"
        
        out_path = os.path.join(out_dir, target_name + ext)
        
        # Collision check
        if os.path.exists(out_path):
            count = 1
            while os.path.exists(out_path):
                out_path = os.path.join(out_dir, f"{target_name}_{count}{ext}")
                count += 1

        # 2. Processing
        with Image.open(src_path) as img:
            # Handle GIF (take first frame)
            if getattr(img, "is_animated", False):
                img.seek(0)
            
            # Convert to RGB for JPEG compatibility
            if s['format'] == 'jpg' and img.mode in ('RGBA', 'P', 'LA'):
                img = img.convert('RGB')
            elif img.mode == 'P':
                img = img.convert('RGBA' if 'transparency' in img.info else 'RGB')

            # 3. Resize (Fit-In logic for Proportion)
            if s['scale_mode'] != 'off':
                orig_w, orig_h = img.size
                if s['scale_mode'] == 'percent':
                    ratio = s['scale_percent'] / 100.0
                    tw, th = int(orig_w * ratio), int(orig_h * ratio)
                    if tw > 0 and th > 0:
                        img = img.resize((tw, th), Image.Resampling.LANCZOS)
                else: # Proportion (Fit-In algorithm)
                    limit_w, limit_h = s['target_w'], s['target_h']
                    if limit_w > 0 and limit_h > 0:
                        # Only resize if original exceeds limits
                        if orig_w > limit_w or orig_h > limit_h:
                            ratio = min(limit_w / orig_w, limit_h / orig_h)
                            tw, th = int(orig_w * ratio), int(orig_h * ratio)
                            img = img.resize((tw, th), Image.Resampling.LANCZOS)

            # 4. Save
            save_params = {}
            if s['format'] == 'jpg':
                save_params['quality'] = s['quality']
                save_params['optimize'] = True
            elif s['format'] == 'webp':
                if s['lossless']: save_params['lossless'] = True
                else: save_params['quality'] = s['quality']
                save_params['optimize'] = True
            elif s['format'] == 'png':
                # Force Lossless for PNG as per user request (protecting quality)
                save_params['optimize'] = True
                save_params['compress_level'] = 9 # Maximum file size reduction without loss
            else:
                pass # BMP, TIFF...

            img.save(out_path, **save_params)
            self.file_finished.emit(src_path, True, out_path)

    def stop(self):
        self.is_running = False
