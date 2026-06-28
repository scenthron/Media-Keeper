import os
import logging
from PIL import Image, ImageSequence
from PyQt6.QtCore import QThread, pyqtSignal

def filter_and_skip_frames(frames, durations, skip_enabled):
    """
    Отбрасывает каждый второй кадр анимации для уменьшения размера файла.
    Суммирует задержки пропущенных кадров, чтобы скорость воспроизведения осталась прежней.
    """
    if not skip_enabled or len(frames) <= 4:
        return frames, durations
        
    new_frames = []
    new_durations = []
    
    i = 0
    while i < len(frames):
        if i == len(frames) - 1:
            new_frames.append(frames[i])
            new_durations.append(durations[i])
            break
        
        new_frames.append(frames[i])
        new_durations.append(durations[i] + durations[i+1])
        i += 2
        
    return new_frames, new_durations

def process_single_frame(frame, s, step_params):
    """
    Масштабирует один кадр с учетом общих настроек и коэффициента текущего шага сжатия.
    """
    scale_mul = step_params['scale_mul']
    orig_w, orig_h = frame.size
    tw, th = orig_w, orig_h
    
    if s['scale_mode'] == 'percent':
        ratio = (s['scale_percent'] / 100.0) * scale_mul
        tw, th = int(orig_w * ratio), int(orig_h * ratio)
    elif s['scale_mode'] == 'proportion':
        limit_w, limit_h = s['target_w'], s['target_h']
        if limit_w > 0 and limit_h > 0:
            if orig_w > limit_w or orig_h > limit_h:
                ratio = min(limit_w / orig_w, limit_h / orig_h) * scale_mul
                tw, th = int(orig_w * ratio), int(orig_h * ratio)
    else:
        # scale_mode == 'off'
        if scale_mul < 1.0:
            tw, th = int(orig_w * scale_mul), int(orig_h * scale_mul)
            
    if tw <= 0: tw = 1
    if th <= 0: th = 1
    
    if tw != orig_w or th != orig_h:
        if frame.mode != 'RGBA':
            frame = frame.convert('RGBA')
        frame = frame.resize((tw, th), Image.Resampling.LANCZOS)
        
    return frame

def save_temp_image(processed_frames, durations, loop, out_format, out_path, s, step_params):
    """
    Сохраняет обработанные кадры в файл с учетом формата вывода и параметров сжатия.
    """
    save_params = {}
    is_animated = len(processed_frames) > 1
    
    # Явно указываем формат для Pillow (чтобы корректно сохранять во временные файлы с расширением .tmp)
    pil_format = out_format.upper().replace('JPG', 'JPEG')
    save_params['format'] = pil_format
    
    if out_format == 'jpg':
        img_to_save = processed_frames[0]
        if img_to_save.mode != 'RGB':
            img_to_save = img_to_save.convert('RGB')
        save_params['quality'] = step_params['quality']
        save_params['optimize'] = True
        img_to_save.save(out_path, **save_params)
        
    elif out_format == 'webp':
        if is_animated:
            webp_frames = []
            for f in processed_frames:
                if f.mode not in ('RGB', 'RGBA'):
                    webp_frames.append(f.convert('RGBA'))
                else:
                    webp_frames.append(f)
            
            save_params['save_all'] = True
            save_params['append_images'] = webp_frames[1:]
            save_params['duration'] = durations
            save_params['loop'] = loop
            if s.get('lossless', False) and step_params['quality'] >= 90:
                save_params['lossless'] = True
            else:
                save_params['quality'] = step_params['quality']
            save_params['optimize'] = True
            webp_frames[0].save(out_path, **save_params)
        else:
            img_to_save = processed_frames[0]
            if img_to_save.mode not in ('RGB', 'RGBA'):
                img_to_save = img_to_save.convert('RGBA')
            if s.get('lossless', False) and step_params['quality'] >= 90:
                save_params['lossless'] = True
            else:
                save_params['quality'] = step_params['quality']
            save_params['optimize'] = True
            img_to_save.save(out_path, **save_params)
            
    elif out_format == 'png':
        img_to_save = processed_frames[0]
        colors = step_params['colors']
        if colors < 256:
            img_to_save = img_to_save.convert('P', palette=Image.Palette.ADAPTIVE, colors=colors)
        else:
            if img_to_save.mode == 'P':
                img_to_save = img_to_save.convert('RGBA' if 'transparency' in img_to_save.info else 'RGB')
        save_params['optimize'] = True
        save_params['compress_level'] = 9
        img_to_save.save(out_path, **save_params)
        
    elif out_format == 'gif':
        if is_animated:
            gif_frames = []
            colors = step_params['colors']
            for f in processed_frames:
                if f.mode != 'P':
                    f_p = f.convert('P', palette=Image.Palette.ADAPTIVE, colors=colors)
                else:
                    f_p = f
                gif_frames.append(f_p)
                
            save_params['save_all'] = True
            save_params['append_images'] = gif_frames[1:]
            save_params['duration'] = durations
            save_params['loop'] = loop
            save_params['optimize'] = True
            gif_frames[0].save(out_path, **save_params)
        else:
            img_to_save = processed_frames[0]
            colors = step_params['colors']
            if img_to_save.mode != 'P':
                img_to_save = img_to_save.convert('P', palette=Image.Palette.ADAPTIVE, colors=colors)
            img_to_save.save(out_path, optimize=True, **save_params)
            
    else:
        img_to_save = processed_frames[0]
        if img_to_save.mode == 'P':
            img_to_save = img_to_save.convert('RGBA' if 'transparency' in img_to_save.info else 'RGB')
        img_to_save.save(out_path, **save_params)

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
            is_animated = getattr(img, "is_animated", False)
            
            src_frames = []
            src_durations = []
            loop = img.info.get('loop', 0)
            
            if is_animated:
                for frame in ImageSequence.Iterator(img):
                    src_frames.append(frame.copy())
                    src_durations.append(frame.info.get('duration', 100))
            else:
                src_frames.append(img.copy())
                src_durations.append(100)

            # Limit size logic
            limit_size = s.get('limit_size', False)
            max_size_mb = s.get('max_size_mb', 10)
            max_bytes = max_size_mb * 1024 * 1024
            
            if not limit_size:
                step_params = {
                    'scale_mul': 1.0,
                    'quality': s['quality'],
                    'colors': 256,
                    'skip_frames': False
                }
                logging.info(
                    f"[ImageWorker] Конвертация: {os.path.basename(src_path)} -> {os.path.basename(out_path)}. "
                    f"Настройки: формат={s['format']}, качество={s['quality']}, переименование={s['rename']}, "
                    f"анимированный={is_animated} ({len(src_frames)} кадров)"
                )
                processed = [process_single_frame(f, s, step_params) for f in src_frames]
                save_temp_image(processed, src_durations, loop, s['format'], out_path, s, step_params)
                self.file_finished.emit(src_path, True, out_path)
                return

            logging.info(f"[ImageWorker] Запущено сжатие под лимит {max_size_mb} MB для {src_path}. Приоритет ползунка: {s.get('compress_priority', 50)} (0=Качество, 100=Разрешение). Анимированный: {is_animated}")
            
            P = s.get('compress_priority', 50)
            steps = []
            if P <= 40:
                qualities = [95, 85, 75, 65, 55, 45, 35, 25, 15]
                for q in qualities:
                    steps.append({'scale_mul': 1.0, 'quality': q, 'colors': 256, 'skip_frames': False})
                scales = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.15]
                for sc in scales:
                    steps.append({'scale_mul': sc, 'quality': 20, 'colors': 32, 'skip_frames': True})
            elif P >= 60:
                scales = [0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.15]
                for sc in scales:
                    steps.append({'scale_mul': sc, 'quality': 85, 'colors': 256, 'skip_frames': False})
                qualities = [70, 55, 40, 25, 15]
                for q in qualities:
                    steps.append({'scale_mul': 0.15, 'quality': q, 'colors': 32, 'skip_frames': True})
            else:
                pairs = [
                    (0.95, 85, 256, False),
                    (0.90, 75, 192, False),
                    (0.80, 65, 128, False),
                    (0.70, 55, 96, False),
                    (0.60, 45, 64, True),
                    (0.50, 35, 48, True),
                    (0.40, 25, 32, True),
                    (0.30, 20, 24, True),
                    (0.20, 15, 16, True),
                    (0.15, 10, 16, True),
                ]
                for sc, q, col, skip in pairs:
                    steps.append({'scale_mul': sc, 'quality': q, 'colors': col, 'skip_frames': skip})

            tmp_path = out_path + ".tmp"
            best_path = None
            best_size = float('inf')
            
            for idx, step in enumerate(steps):
                if not self.is_running:
                    break
                
                cur_frames, cur_durations = filter_and_skip_frames(src_frames, src_durations, step['skip_frames'] and is_animated)
                processed = [process_single_frame(f, s, step) for f in cur_frames]
                
                try:
                    save_temp_image(processed, cur_durations, loop, s['format'], tmp_path, s, step)
                    current_size = os.path.getsize(tmp_path)
                    logging.info(f"[ImageWorker] Итерация {idx+1}/{len(steps)}: scale_mul={step['scale_mul']:.2f}, quality={step['quality']}, colors={step['colors']}, skip_frames={step['skip_frames']} -> Размер: {current_size / (1024*1024):.2f} MB")
                    
                    if current_size < best_size:
                        best_size = current_size
                        if os.path.exists(out_path):
                            os.remove(out_path)
                        os.rename(tmp_path, out_path)
                        best_path = out_path
                        
                    if current_size <= max_bytes:
                        logging.info(f"[ImageWorker] Уложились в лимит на итерации {idx+1}. Итоговый размер: {current_size / (1024*1024):.2f} MB")
                        break
                except Exception as e:
                    logging.error(f"[ImageWorker] Ошибка на итерации {idx+1}: {e}")
                    if os.path.exists(tmp_path):
                        try: os.remove(tmp_path)
                        except: pass
            
            if os.path.exists(tmp_path):
                try: os.remove(tmp_path)
                except: pass
                
            if best_path and os.path.exists(best_path):
                logging.info(f"[ImageWorker] Конвертация завершена. Выбран лучший файл размером {best_size / (1024*1024):.2f} MB")
                self.file_finished.emit(src_path, True, out_path)
            else:
                raise Exception("Не удалось создать сжатый файл")

    def stop(self):
        self.is_running = False
