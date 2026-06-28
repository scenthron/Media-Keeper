
import os
import subprocess
import logging
import json
import re
from PyQt6.QtCore import QThread, pyqtSignal
from logic_paths import get_ffmpeg_exe, get_ffprobe_exe

class ProbeWorker(QThread):
    """
    Analyzes a list of files using ffprobe to get duration, bitrate, etc.
    """
    file_analyzed = pyqtSignal(dict) # Emits dict with metadata
    finished_all = pyqtSignal()

    def __init__(self, file_paths):
        super().__init__()
        self.file_paths = file_paths

    def run(self):
        ffprobe_exe = get_ffprobe_exe()
        print(f"[DEBUG] ProbeWorker started. FFprobe path: {ffprobe_exe}")
        
        if not os.path.exists(ffprobe_exe):
            print(f"[ERROR] FFprobe not found at {ffprobe_exe}")
            pass

        for path in self.file_paths:
            data = self.analyze_file(ffprobe_exe, path)
            self.file_analyzed.emit(data)
        
        self.finished_all.emit()

    def analyze_file(self, ffprobe, path):
        """
        Returns info dict: {path, duration, bitrate, res, codec, width, height, size}
        """
        res = {
            'path': path,
            'duration': 0,
            'bitrate': 0,
            'res': '?',
            'codec': '?',
            'width': 1920,
            'height': 1080,
            'size': os.path.getsize(path) if os.path.exists(path) else 0
        }
        
        if not os.path.exists(ffprobe):
            return res

        cmd = [
            ffprobe,
            "-v", "error",
            "-show_entries", "stream=width,height,codec_name,duration,bit_rate,channels",
            "-show_entries", "format=duration,bit_rate",
            "-of", "json",
            path
        ]
        
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
            proc = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo)
            info = json.loads(proc.stdout)
            
            fmt = info.get('format', {})
            duration = float(fmt.get('duration', 0))
            streams = info.get('streams', [])
            
            # Categorize streams
            v_streams = [s for s in streams if s.get('codec_type') == 'video']
            a_streams = [s for s in streams if s.get('codec_type') == 'audio']
            
            # Map audio stream details for the list
            res['a_streams'] = []
            for i, s in enumerate(a_streams):
                res['a_streams'].append({
                    'index': i,
                    'codec': s.get('codec_name', '?'),
                    'br': int(s.get('bit_rate', 0)) if s.get('bit_rate') else 0,
                    'ch': int(s.get('channels', 0))
                })

            v_stream = v_streams[0] if v_streams else {}
            a_stream = a_streams[0] if a_streams else {}
            
            # Use found streams or fallback
            main_stream = v_stream or a_stream or (streams[0] if streams else {})
            
            res['duration'] = duration
            res['bitrate'] = int(fmt.get('bit_rate', 0)) if fmt.get('bit_rate') else 0
            
            # Legacy fields for backward compat
            res['a_codec'] = a_stream.get('codec_name', '?')
            res['a_br'] = int(a_stream.get('bit_rate', 0)) if a_stream.get('bit_rate') else 0
            res['channels'] = int(a_stream.get('channels', 0))
            
            # Video info
            res['codec'] = v_stream.get('codec_name', '?')
            width = v_stream.get('width')
            height = v_stream.get('height')
            res['width'] = width if width else 1920
            res['height'] = height if height else 1080
            if width and height:
                res['res'] = f"{width}x{height}"
            
            print(f"[DEBUG] Full analysis of {os.path.basename(path)}: {len(a_streams)} audio streams")
            
        except Exception as e:
            print(f"[ERROR] Probe error for {path}: {e}")
            
        return res


class ConversionWorker(QThread):
    progress_updated = pyqtSignal(str, int) # file_path, percent
    file_finished = pyqtSignal(str, bool, str) # file_path, success, output_path_or_error
    all_finished = pyqtSignal()

    def __init__(self, queue, settings):
        """
        queue: list of dicts {path, name, duration...}
        """
        super().__init__()
        self.queue = queue
        self.settings = settings
        self.is_running = True
    
    def calculate_bitrate_for_size(self, target_mb, item_info):
        """Calculate video bitrate to achieve target file size with 7% safety margin"""
        duration = item_info.get('duration', 0)
        if duration <= 0:
            return 1000  # Fallback
        
        # 1 MB = 8192 Kilobits. 
        # We use 0.93 coefficient to account for container overhead (headers, index) and minor codec fluctuations.
        safety_margin = 0.93
        total_bits = target_mb * 8192 * safety_margin
        total_bitrate = total_bits / duration  # bps -> kbps
        
        audio_bitrate = 128 if not self.settings.get('mute') else 0
        video_bitrate = total_bitrate - audio_bitrate
        
        if video_bitrate < 150:
            video_bitrate = 150 # Minimum viable bitrate for x264
            
        return int(video_bitrate)
    
    def get_startupinfo(self):
        """Get startup info for Windows to hide console"""
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return startupinfo

    def run(self):
        ffmpeg_exe = get_ffmpeg_exe()
        print(f"[DEBUG] ConversionWorker started. FFmpeg path: {ffmpeg_exe}")
        
        if not os.path.exists(ffmpeg_exe):
            logging.error(f"[VideoWorker] FFmpeg not found at {ffmpeg_exe}")
            print(f"[ERROR] FFmpeg not found at {ffmpeg_exe}")
            self.file_finished.emit("Global", False, f"FFmpeg.exe not found at {ffmpeg_exe}!")
            self.all_finished.emit()
            return

        self.current_process = None # Track current process for termination

        for item in self.queue:
            if not self.is_running: break
            
            input_path = item['path']
            print(f"[DEBUG] Processing: {input_path}")
            
            # Smart check: if file is smaller than target size, use copy stream
            file_size_mb = item.get('size', 0) / (1024 * 1024)
            target_mb = self.settings.get('target_mb', 10)
            use_copy_stream = self.settings.get('copy_stream', False)
            
            if self.settings.get('mode') == 'size' and file_size_mb < target_mb:
                # Auto-enable copy stream for this file
                use_copy_stream = True
                print(f"[DEBUG] File {file_size_mb:.1f}MB < Target {target_mb}MB - Using copy stream")
            
            if input_path.lower().endswith('.gif'):
                use_copy_stream = False
            
            # 1. Determine Output Path
            output_dir = self.settings.get('output_dir', '')
            if not output_dir:
                output_dir = os.path.dirname(input_path)
            
            name, ext = os.path.splitext(os.path.basename(input_path))
            postfix = self.settings.get('postfix', '')
            target_ext = self.settings.get('extension', ext).lower()
            if not target_ext.startswith('.'): target_ext = '.' + target_ext
            
            output_filename = f"{name}{postfix}{target_ext}"
            output_path = os.path.join(output_dir, output_filename)
            
            # 2. File Collision Protection (Prevent overwriting)
            if os.path.exists(output_path):
                counter = 1
                while os.path.exists(output_path):
                    output_filename = f"{name}{postfix}_{counter}{target_ext}"
                    output_path = os.path.join(output_dir, output_filename)
                    counter += 1
                print(f"[DEBUG] Destination exists. Using indexed name: {output_filename}")
            
            success = self.convert_file(ffmpeg_exe, input_path, output_path, item, use_copy_stream)
            
            if not self.is_running:
                # If stopped during conversion, we might have a corrupt part - but for now just emit finished
                self.file_finished.emit(input_path, False, "Stopped")
                break

            msg = output_path if success else "Error"
            self.file_finished.emit(input_path, success, msg)
            
        self.all_finished.emit()

    def terminate_process(self):
        """Immediately kill the FFmpeg process"""
        self.is_running = False
        if hasattr(self, 'current_process') and self.current_process:
            try:
                print("[DEBUG] Terminating FFmpeg process...")
                self.current_process.terminate()
                # On Windows, terminate() might not be enough for some subprocesses, 
                # but for Popen with startupinfo it usually works.
                # If it doesn't, we can use taskkill.
            except Exception as e:
                print(f"[ERROR] Failed to terminate FFmpeg: {e}")

    def convert_file(self, ffmpeg, inp, out, item_info, use_copy_stream=None):
        # Build Common Input Flags
        input_args = [ffmpeg, "-y", "-i", inp]
        
        # Audio
        audio_args = []
        if self.settings.get('mute', False):
            audio_args.append("-an")
        else:
            if self.settings.get('extension') == 'webm':
                audio_args.extend(["-c:a", "libvorbis"])
            else:
                audio_args.extend(["-c:a", "aac"]) 

        # Video filters (scaling)
        filter_args = []
        scale_mode = self.settings.get('scale_mode', 'off')
        if scale_mode == 'percent' and not use_copy_stream:
            scale_percent = self.settings.get('scale_percent', 100)
            if scale_percent < 100:
                width = item_info.get('width', 1920)
                height = item_info.get('height', 1080)
                new_width = int((width * scale_percent / 100) // 2) * 2
                new_height = int((height * scale_percent / 100) // 2) * 2
                if new_width < 2: new_width = 2
                if new_height < 2: new_height = 2
                filter_args.extend(['-vf', f'scale={new_width}:{new_height}'])
        elif scale_mode == 'proportion' and not use_copy_stream:
            target_w = self.settings.get('target_width')
            target_h = self.settings.get('target_height')
            if target_w and target_h:
                target_w = (target_w // 2) * 2
                target_h = (target_h // 2) * 2
                filter_args.extend(['-vf', f'scale={target_w}:{target_h}'])
        elif not use_copy_stream:
            # Force even dimensions (divisible by 2) to prevent libx264/libvpx-vp9 encoder failure
            filter_args.extend(['-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2'])

        # Encoding Mode
        mode = self.settings.get('mode', 'crf')
        duration = item_info.get('duration', 0)
        is_webm = self.settings.get('extension') == 'webm'
        
        # Логируем параметры кодирования
        scale_mode = self.settings.get('scale_mode', 'off')
        logging.info(
            f"[VideoWorker] Начало конвертации: {os.path.basename(inp)} -> {os.path.basename(out)}. "
            f"Входной размер: {item_info.get('size', 0) / (1024*1024):.2f} MB, длительность: {duration} сек. "
            f"Настройки: режим={mode}, расширение={self.settings.get('extension')}, "
            f"copy_stream={use_copy_stream}, scale_mode={scale_mode}, "
            f"scale_percent={self.settings.get('scale_percent', 100)}, "
            f"target_resolution={self.settings.get('target_width')}x{self.settings.get('target_height')}, "
            f"mute={self.settings.get('mute', False)}, target_mb={self.settings.get('target_mb')}"
        )
        
        if use_copy_stream:
            cmd = input_args + ["-c:v", "copy"] + audio_args + [out]
            logging.info(f"[VideoWorker] Запуск копирования потока: {' '.join(cmd)}")
            return self.run_ffmpeg_with_progress(cmd, duration, 0, 100, inp)
        else:
            # Re-encode
            if is_webm:
                base_v_args = ["-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p"]
            else:
                base_v_args = ["-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p"]
                if self.settings.get('extension') == 'mp4':
                    base_v_args.extend(["-movflags", "+faststart"])
            
            if inp.lower().endswith('.gif'):
                # Force constant frame rate of 25 fps for GIF inputs.
                # This guarantees valid timestamps and duration in containers like MP4/WebM.
                base_v_args.extend(["-r", "25", "-vsync", "cfr"])
            
            if mode == 'crf':
                crf = self.settings.get('crf', 23)
                v_args = ["-crf", str(crf)]
                if is_webm:
                    v_args.extend(["-b:v", "0"])
                cmd = input_args + base_v_args + v_args + filter_args + audio_args + [out]
                return self.run_ffmpeg_with_progress(cmd, duration, 0, 100, inp)
            
            elif mode == 'crf_percent':
                crf = 23
                v_args = ["-crf", str(crf)]
                max_size = self.settings.get('max_size')
                if max_size:
                    target_bitrate = self.calculate_bitrate_for_size(max_size, item_info)
                    v_args.extend(["-b:v", f"{target_bitrate}k"])
                    if not is_webm:
                        v_args.extend(["-maxrate", f"{target_bitrate}k", "-bufsize", f"{target_bitrate * 2}k"])
                else:
                    percent = self.settings.get('percent', 50)
                    original_bitrate = item_info.get('bitrate', 0) // 1000
                    if original_bitrate > 0:
                        maxrate = int(original_bitrate * (percent / 100))
                        v_args.extend(["-b:v", f"{maxrate}k"])
                        if not is_webm:
                            v_args.extend(["-maxrate", f"{maxrate}k", "-bufsize", f"{maxrate * 2}k"])
                    else:
                        v_args.extend(["-b:v", "1000k"])
                
                cmd = input_args + base_v_args + v_args + filter_args + audio_args + [out]
                return self.run_ffmpeg_with_progress(cmd, duration, 0, 100, inp)
            
            elif mode == '2pass' or mode == 'size': # Handle 'size' as 2pass if not copy
                max_size = self.settings.get('max_size') or self.settings.get('target_mb')
                if max_size:
                    target_bitrate = self.calculate_bitrate_for_size(max_size, item_info)
                else:
                    percent = self.settings.get('percent', 50)
                    original_bitrate = item_info.get('bitrate', 0) // 1000
                    target_bitrate = int(original_bitrate * (percent / 100)) if original_bitrate > 0 else 1000
                
                import tempfile
                import uuid
                import glob
                
                # Создаем уникальный префикс для временных логов FFmpeg в системной папке Temp
                temp_log_prefix = os.path.join(tempfile.gettempdir(), f"ffmpeg2pass_{uuid.uuid4().hex}")
                
                # Pass 1: Analysis (30% of total progress)
                # Note: pass 1 needs to output to NUL/null
                pass1_out = "NUL" if os.name == 'nt' else "/dev/null"
                pass1_args = [
                    "-b:v", f"{target_bitrate}k", 
                    "-pass", "1", 
                    "-passlogfile", temp_log_prefix, 
                    "-an", "-f", "null"
                ]
                cmd1 = input_args + base_v_args + pass1_args + filter_args + [pass1_out]
                
                print(f"[DEBUG] Starting Pass 1: {target_bitrate}k")
                pass1_ok = False
                try:
                    pass1_ok = self.run_ffmpeg_with_progress(cmd1, duration, 0, 30, inp)
                finally:
                    if not pass1_ok:
                        # Если первый проход упал, очищаем за собой
                        for f in glob.glob(temp_log_prefix + "*"):
                            try: os.remove(f)
                            except: pass
                
                if not pass1_ok:
                    return False
                
                # Pass 2: Encoding (30% -> 100%)
                pass2_args = [
                    "-b:v", f"{target_bitrate}k", 
                    "-pass", "2", 
                    "-passlogfile", temp_log_prefix
                ]
                cmd2 = input_args + base_v_args + pass2_args + filter_args + audio_args + [out]
                
                print(f"[DEBUG] Starting Pass 2: {target_bitrate}k")
                pass2_ok = False
                try:
                    pass2_ok = self.run_ffmpeg_with_progress(cmd2, duration, 30, 100, inp)
                    return pass2_ok
                finally:
                    # В любом случае (успех или ошибка) стираем временные логи FFmpeg
                    for f in glob.glob(temp_log_prefix + "*"):
                        try: os.remove(f)
                        except: pass
        
        return False

    def run_ffmpeg_with_progress(self, cmd, duration, start_pct, end_pct, file_path):
        """Runs ffmpeg and maps its time progress to the [start_pct, end_pct] range."""
        if not self.is_running:
            return False

        logging.info(f"[VideoWorker] Запуск FFmpeg: {' '.join(cmd)}")
        print(f"[DEBUG] Running FFmpeg: {' '.join(cmd)}")
        startupinfo = self.get_startupinfo()
        
        try:
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
                startupinfo=startupinfo,
                encoding='utf-8',
                errors='replace'
            )
            
            pct_range = end_pct - start_pct
            
            while self.is_running:
                line = self.current_process.stderr.readline()
                if not line and self.current_process.poll() is not None:
                    break
                
                if line:
                    match = re.search(r'time=\s*(\d+):(\d+):(\d+(?:\.\d+)?)', line)
                    if match and duration > 0:
                        h, m, s = match.groups()
                        curr_seconds = int(h)*3600 + int(m)*60 + float(s)
                        
                        # Relative progress within this specific pass
                        pass_pct = (curr_seconds / duration)
                        if pass_pct > 1.0: pass_pct = 1.0
                        
                        # Absolute progress mapped to global range
                        global_pct = int(start_pct + (pass_pct * pct_range))
                        self.progress_updated.emit(file_path, global_pct)
                    
                    elif "Error" in line or "Invalid" in line:
                        logging.warning(f"[VideoWorker] FFmpeg log output error: {line.strip()}")
                        print(f"[FFMPEG LOG] {line.strip()}")

            if not self.is_running:
                if self.current_process.poll() is None:
                    print("[DEBUG] Terminating FFmpeg process (is_running=False)")
                    self.current_process.terminate()
                return False

            success = self.current_process.returncode == 0
            if not success:
                logging.error(f"[VideoWorker] FFmpeg process exited with code {self.current_process.returncode}")
            self.current_process = None
            return success

        except Exception as e:
            logging.error(f"[VideoWorker] run_ffmpeg_with_progress failed: {e}", exc_info=True)
            print(f"[ERROR] run_ffmpeg_with_progress failed: {e}")
            if self.current_process:
                self.current_process.kill()
            self.current_process = None
            return False
