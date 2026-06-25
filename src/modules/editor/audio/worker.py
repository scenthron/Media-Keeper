import os
import subprocess
import json
from PyQt6.QtCore import QThread, pyqtSignal
from logic_paths import get_ffmpeg_exe, get_ffprobe_exe

class AudioConverterWorker(QThread):
    file_progress = pyqtSignal(str, int)
    file_finished = pyqtSignal(str, bool, str)
    all_finished = pyqtSignal()
    
    def __init__(self, queue, settings):
        super().__init__()
        self.queue = queue
        self.settings = settings
        self.is_running = True
        self.process = None

    def run(self):
        ffmpeg_exe = get_ffmpeg_exe()
        if not os.path.exists(ffmpeg_exe):
            self.file_finished.emit("Global", False, f"FFmpeg not found at {ffmpeg_exe}")
            self.all_finished.emit()
            return
            
        ffprobe_exe = get_ffprobe_exe()
        
        for file_info in self.queue:
            if not self.is_running: break
            self._all_results = [] # Cleanup for new task
            
            try:
                self.process_file(file_info, ffmpeg_exe, ffprobe_exe)
                self.file_finished.emit(file_info['path'], True, ";".join(self._all_results))
            except Exception as e:
                self.file_finished.emit(file_info['path'], False, str(e))
        
        self.all_finished.emit()

    def process_file(self, info, ffmpeg_exe, ffprobe_exe):
        s = self.settings
        src_path = info['path']
        
        # 1. Get all audio streams detected by ProbeWorker
        a_streams = info.get('a_streams', [])
        if not a_streams:
            # Fallback if probe failed or it's a pure audio file without streams list
            a_streams = [{'index': 0, 'codec': info.get('a_codec', 'mp3'), 'br': info.get('a_br', 0)}]

        total_tracks = len(a_streams)
        
        for track_idx, stream_info in enumerate(a_streams):
            if not self.is_running: break
            
            # Progress reporting: split progress by tracks
            self.current_track_offset = (track_idx / total_tracks) * 100
            self.current_track_weight = (1.0 / total_tracks)
            
            # 2. Extract specific stream info
            src_bitrate = stream_info.get('br', 0) // 1000
            if src_bitrate == 0: src_bitrate = self.get_source_bitrate(src_path, ffprobe_exe)
            
            a_codec = stream_info.get('codec', 'mp3').lower()
            
            # 3. Output Path Logic
            out_dir = s['output_dir'] or os.path.dirname(src_path)
            base_name, _ = os.path.splitext(os.path.basename(src_path))
            
            if s['copy_stream']:
                ext_map = {
                    'aac': '.m4a', 'mp3': '.mp3', 'libmp3lame': '.mp3', 
                    'vorbis': '.ogg', 'opus': '.opus', 'flac': '.flac',
                    'pcm_s16le': '.wav', 'ac3': '.ac3', 'dts': '.dts'
                }
                ext = ext_map.get(a_codec, "." + s['format'].lower())
            else:
                ext = "." + s['format'].lower()
            
            track_suffix = f"_T{track_idx+1}" if total_tracks > 1 else ""
            target_name = base_name
            if s['rename']:
                tmpl = s['name_tmpl']
                target_name = f"{tmpl}{base_name}" if s['rename_prefix'] else f"{base_name}{tmpl}"
            
            out_path = os.path.join(out_dir, f"{target_name}{track_suffix}{ext}")
            
            if os.path.exists(out_path):
                c = 1
                while os.path.exists(out_path):
                    out_path = os.path.join(out_dir, f"{target_name}{track_suffix}_{c}{ext}")
                    c += 1

            # 4. FFmpeg Command
            cmd = [ffmpeg_exe, "-y", "-i", src_path, "-vn", "-map", f"0:a:{track_idx}"]
            
            # Smart Logic: if Copy is ON, we only copy if formats match, otherwise re-encode with max quality
            target_fmt = s['format'].lower()
            
            # Проверяем лимит максимального размера
            max_size = s.get('max_size') # в МБ
            src_size_bytes = info.get('size', 0)
            if src_size_bytes == 0 and os.path.exists(src_path):
                try:
                    src_size_bytes = os.path.getsize(src_path)
                except:
                    pass
            src_size_mb = src_size_bytes / (1024 * 1024)
            
            # Если исходный файл больше лимита — отключаем копирование и принудительно перекодируем
            force_reencode_for_size = False
            if max_size and src_size_mb > max_size:
                force_reencode_for_size = True

            can_copy = s['copy_stream'] and not force_reencode_for_size and (
                (target_fmt == 'mp3' and 'mp3' in a_codec) or
                (target_fmt == 'aac' and 'aac' in a_codec) or
                (target_fmt == 'flac' and 'flac' in a_codec) or
                (target_fmt == 'wav' and 'pcm' in a_codec) or
                (target_fmt == 'ogg' and ('vorbis' in a_codec or 'opus' in a_codec))
            )

            if can_copy:
                cmd += ["-acodec", "copy"]
                if target_fmt == 'aac' or 'aac' in a_codec:
                    cmd += ["-bsf:a", "aac_adtstoasc"]
            else:
                # High-Quality Re-encode
                if target_fmt == 'mp3': cmd += ["-acodec", "libmp3lame"]
                elif target_fmt == 'ogg': cmd += ["-acodec", "libvorbis"]
                elif target_fmt == 'wav': cmd += ["-acodec", "pcm_s16le"]
                elif target_fmt == 'flac': cmd += ["-acodec", "flac"]
                elif target_fmt in ('m4a', 'aac'): cmd += ["-acodec", "aac"]
                elif target_fmt == 'opus': cmd += ["-acodec", "libopus"]

                # Fixed Max Quality (320k) if Copy Stream was requested but impossible
                force_max = s['copy_stream'] and not force_reencode_for_size
                
                if target_fmt not in ('wav', 'flac'):
                    duration = info.get('duration', 0)
                    
                    # Вычисляем ограничение по битрейту на основе max_size
                    max_allowed_br = None
                    if max_size and duration > 0:
                        # 1 MB = 8192 Kilobits. Запас 7% на метаданные контейнера.
                        safety_margin = 0.93
                        max_allowed_br = int((max_size * 8192 * safety_margin) / duration)
                        if max_allowed_br < 8:
                            max_allowed_br = 8
                        elif max_allowed_br > 320:
                            max_allowed_br = 320

                    # Если включено ограничение размера, мы ВСЕГДА используем CBR (-b:a) 
                    # для гарантированного попадания в заданный размер
                    if max_allowed_br is not None:
                        if s['mode'] == 'vbr':
                            # Стандартный битрейт VBR для отката в CBR
                            base_br = 192
                        else:
                            base_br = 320 if force_max else s['bitrate']
                            
                        target_br = min(base_br, max_allowed_br)
                        
                        # Также ограничиваем битрейтом источника, если он ниже расчетного
                        if not force_max and src_bitrate > 0 and target_br > src_bitrate:
                            target_br = src_bitrate
                            
                        cmd += ["-b:a", f"{target_br}k"]
                    else:
                        # Обычная логика
                        if not force_max and s['mode'] == 'vbr':
                            cmd += ["-q:a", str(s['bitrate'])]
                        else:
                            target_br = 320 if force_max else s['bitrate']
                            if not force_max and src_bitrate > 0 and target_br > src_bitrate:
                                target_br = src_bitrate 
                            cmd += ["-b:a", f"{target_br}k"]

                if s['sample_rate'] != "Auto":
                    cmd += ["-ar", s['sample_rate']]
                
                if s['channels'] == 1: cmd += ["-ac", "2"]
                elif s['channels'] == 2: cmd += ["-ac", "1"]

            cmd.append(out_path)

            # 5. Execute
            print(f"[DEBUG] AudioConverter Running: {' '.join(cmd)}")
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                            universal_newlines=True, startupinfo=startupinfo, encoding='utf-8', errors='replace')
        
        duration = info.get('duration', 0)
        full_output_log = []
        for line in self.process.stdout:
            if not self.is_running: break
            line_str = line.strip()
            if not line_str: continue
            
            full_output_log.append(line_str)
            
            if "time=" in line:
                try:
                    time_part = line.split("time=")[1].split(" ")[0]
                    h, m, s_part = time_part.split(":")
                    secs = int(h)*3600 + int(m)*60 + float(s_part)
                    if duration > 0:
                        item_pct = min(1.0, secs / duration)
                        global_pct = int(self.current_track_offset + (item_pct * self.current_track_weight * 100))
                        self.file_progress.emit(src_path, global_pct)
                except: pass

        self.process.wait()
        if self.process.returncode == 0:
            if not hasattr(self, '_all_results'): self._all_results = []
            self._all_results.append(out_path)
        else:
            # Print last bits of log to console and exception
            error_preview = "\n".join(full_output_log[-10:]) 
            print(f"\n[ERROR] AudioConverter Failed!")
            print(f"[ERROR] CMD: {' '.join(cmd)}")
            print(f"[ERROR] LAST LOG LINES:\n{error_preview}")
            raise Exception(f"FFmpeg error: {full_output_log[-1] if full_output_log else 'Unknown'}")

    def get_source_bitrate(self, path, ffprobe_exe):
        try:
            cmd = [ffprobe_exe, "-v", "error", "-show_entries", "format=bit_rate", "-of", "json", path]
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            res = subprocess.check_output(cmd, startupinfo=startupinfo)
            data = json.loads(res)
            br = int(data.get('format', {}).get('bit_rate', 0))
            return br // 1000 # To kbps
        except: return 0

    def stop(self):
        self.is_running = False
        if self.process:
            try: self.process.terminate()
            except: pass
