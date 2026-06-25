
import os
import subprocess
import re
import json
import logging
from PyQt6.QtCore import QThread, pyqtSignal
from logic_paths import get_ffmpeg_exe, get_ffprobe_exe
from config import AppContext

class VideoEditorWorker(QThread):
    progress_updated = pyqtSignal(int) # Percent
    finished = pyqtSignal(bool, str) # Success, Message
    
    def __init__(self, settings):
        """
        settings: {
            'input': str,
            'output': str,
            'markers': list,    # list of floats (0.0-1.0)
            'is_inverted': bool,
            'rotation': float (0/90/180/270),
            'flip_h': bool,
            'flip_v': bool,
            'cc': { 'brightness': float, 'contrast': float, 'saturation': float },
            'overlay': { 'type': 'image'|'region'|'blur', 'x','y','w','h', 'opacity', 'color', 'path', 'blur_val' },
            'crop': {x, y, w, h} or None (normalized/scene coords),
            'video_size': (w, h),
            'orig_bitrate': int
        }
        """
        super().__init__()
        self.s = settings
        self.is_running = True
        self.process = None

    def run(self) -> None:
        ffmpeg = get_ffmpeg_exe()
        ffprobe = get_ffprobe_exe()
        
        if not os.path.exists(ffmpeg):
            self.finished.emit(False, AppContext.tr("ffmpeg_not_found"))
            return
            
        # 1. Probe & Analyze
        is_audio = self.s.get('is_audio', False)
        info = self._get_video_info(ffprobe, self.s['input'], is_audio)
        orig_w = info.get('width', 1920)
        orig_h = info.get('height', 1080)
        total_dur_sec = info.get('duration', 0)
        bitrate = self.s.get('orig_bitrate') or info.get('bitrate', 5000000)
        
        # Check if the source file actually has an audio stream
        has_audio = False
        if not is_audio:
            has_audio = self._has_audio_stream(ffprobe, self.s['input'])
        
        # 2. Extract Segments (Green Zones)
        markers = sorted(self.s.get('markers', []))
        is_inverted = self.s.get('is_inverted', False)
        all_points = [0.0] + markers + [1.0]
        segments = []
        for i in range(len(all_points)-1):
            take = (i % 2 == 0)
            if is_inverted: take = not take
            if take:
                s1, s2 = all_points[i], all_points[i+1]
                if s2 - s1 > 0.001: # ignore tiny slivers
                    segments.append((s1 * total_dur_sec, s2 * total_dur_sec))

        if not segments:
            self.finished.emit(False, AppContext.tr("editor_err_no_segments"))
            return

        has_image_input = False
        if self.s.get('overlay') and self.s['overlay']['path']:
            path = self.s['overlay']['path']
            if os.path.exists(path):
                has_image_input = True

        has_effects = (
            self.s.get('rotation', 0) != 0 or
            self.s.get('flip_h') or
            self.s.get('flip_v') or
            self.s.get('crop') or
            self.s['cc']['brightness'] != 0 or
            self.s['cc']['contrast'] != 1 or
            self.s['cc']['saturation'] != 1 or
            self.s.get('overlay')
        )

        split_video = self.s.get('split_video', False)

        if split_video:
            total_segs = len(segments)
            base_out, ext = os.path.splitext(self.s['output'])
            success_all = True
            saved_paths = []
            
            for idx, (start_s, end_s) in enumerate(segments):
                if not self.is_running:
                    break
                
                seg_out = f"{base_out}_{idx+1}{ext}"
                seg_dur = end_s - start_s
                
                # Check for collisions
                if os.path.exists(seg_out):
                    c = 1
                    while os.path.exists(seg_out):
                        seg_out = f"{base_out}_{idx+1}_{c}{ext}"
                        c += 1
                
                cmd = [ffmpeg, "-y"]
                if not has_effects:
                    cmd.extend(["-ss", f"{start_s:.3f}", "-i", self.s['input'], "-t", f"{seg_dur:.3f}"])
                    if is_audio:
                        cmd.extend(["-c:a", "copy", seg_out])
                    elif self.s.get('remove_audio') or not has_audio:
                        cmd.extend(["-c:v", "copy", "-an", seg_out])
                    else:
                        cmd.extend(["-c", "copy", seg_out])
                else:
                    cmd.extend(["-i", self.s['input']])
                    if has_image_input:
                        if self.s['overlay']['path'].lower().endswith('.gif'):
                            cmd.extend(["-ignore_loop", "0"])
                        cmd.extend(["-i", self.s['overlay']['path']])
                    
                    filter_complex = []
                    if not is_audio:
                        filter_complex.append(f"[0:v]trim=start={start_s:.3f}:end={end_s:.3f},setpts=PTS-STARTPTS[v0]")
                        current_v_label = "[v0]"
                    if not self.s.get('remove_audio') and has_audio:
                        filter_complex.append(f"[0:a]atrim=start={start_s:.3f}:end={end_s:.3f},asetpts=PTS-STARTPTS[a0]")
                        filter_complex.append("[a0]anull[a_out]")
                    
                    # Transforms (Rotate/Flip)
                    transforms = []
                    rot = self.s.get('rotation', 0) % 360
                    if rot == 90: transforms.append("transpose=1")
                    elif rot == 180: transforms.append("transpose=1,transpose=1")
                    elif rot == 270: transforms.append("transpose=2")
                    if self.s.get('flip_h'): transforms.append("hflip")
                    if self.s.get('flip_v'): transforms.append("vflip")
                    if transforms:
                        t_str = ",".join(transforms)
                        filter_complex.append(f"{current_v_label}{t_str}[v_trans]")
                        current_v_label = "[v_trans]"
                        
                    # Overlay
                    ovl = self.s.get('overlay')
                    if ovl:
                        x = int(ovl['x'] * orig_w)
                        y = int(ovl['y'] * orig_h)
                        w = int(ovl['w'] * orig_w)
                        h = int(ovl['h'] * orig_h)
                        w = max(1, w)
                        h = max(1, h)
                        
                        if ovl['type'] == 'region':
                            color = ovl.get('color', '#ff0000').replace('#', '0x')
                            opacity = ovl.get('opacity', 1.0)
                            col_str = f"{color}@{opacity}"
                            filter_complex.append(f"{current_v_label}drawbox=x={x}:y={y}:w={w}:h={h}:color={col_str}:t=fill[v_ovl]")
                            current_v_label = "[v_ovl]"
                        elif ovl['type'] == 'blur':
                            sigma = (ovl.get('blur_val', 100) / 100.0) * 50
                            filter_complex.append(f"{current_v_label}split=2[v_base][v_tocrop]")
                            filter_complex.append(f"[v_tocrop]crop={w}:{h}:{x}:{y},gblur=sigma={sigma}[v_blurred]")
                            filter_complex.append(f"[v_base][v_blurred]overlay={x}:{y}[v_ovl]")
                            current_v_label = "[v_ovl]"
                        elif ovl['type'] == 'image' and has_image_input:
                            filter_complex.append(f"[1:v]scale={w}:{h}[img_scaled]")
                            opacity = ovl.get('opacity', 1.0)
                            filter_complex.append(f"[img_scaled]format=rgba,colorchannelmixer=aa={opacity}[img_ready]")
                            filter_complex.append(f"{current_v_label}[img_ready]overlay={x}:{y}[v_ovl]")
                            current_v_label = "[v_ovl]"
                            
                    # Color Correction
                    cc = self.s['cc']
                    if cc['brightness'] != 0 or cc['contrast'] != 1 or cc['saturation'] != 1:
                        eq_str = f"eq=brightness={cc['brightness']}:contrast={cc['contrast']}:saturation={cc['saturation']}"
                        filter_complex.append(f"{current_v_label}{eq_str}[v_cc]")
                        current_v_label = "[v_cc]"
                        
                    # Final Crop
                    if self.s.get('crop'):
                        c = self.s['crop']
                        sw, sh = self.s['video_size']
                        current_w, current_h = orig_w, orig_h
                        rot = self.s.get('rotation', 0) % 360
                        if rot == 90 or rot == 270:
                            current_w, current_h = orig_h, orig_w
                        rx = int(c['x'] * current_w / sw)
                        ry = int(c['y'] * current_h / sh)
                        rw = (int(c['w'] * current_w / sw) // 2) * 2
                        rh = (int(c['h'] * current_h / sh) // 2) * 2
                        filter_complex.append(f"{current_v_label}crop={rw}:{rh}:{rx}:{ry}[v_final]")
                        current_v_label = "[v_final]"
                        
                    cmd.extend(["-filter_complex", ";".join(filter_complex)])
                    if not is_audio:
                        cmd.extend(["-map", current_v_label])
                    if not self.s.get('remove_audio') and has_audio:
                        cmd.extend(["-map", "[a_out]"])
                        
                    if not is_audio:
                        codec_val = self.s.get('video_codec', 'libx264')
                        preset_val = self.s.get('video_preset', 'medium')
                        quality_val = self.s.get('video_quality', 17)
                        cmd.extend(["-c:v", codec_val, "-preset", preset_val, "-crf", str(quality_val)])
                    
                    cmd.extend(["-t", f"{seg_dur:.3f}"])
                    if not self.s.get('remove_audio') and has_audio:
                        cmd.extend(["-c:a", "aac", "-b:a", "192k"])
                    cmd.append(seg_out)
                    
                start_pct = (idx / total_segs) * 100
                step_pct = 100.0 / total_segs
                
                logging.info(f"SMART ENCODE (Split Segment {idx+1}/{total_segs}): {' '.join(cmd)}")
                ok = self._run_ffmpeg_cmd(cmd, seg_dur, start_pct, step_pct)
                if not ok:
                    success_all = False
                    if os.path.exists(seg_out):
                        try: os.remove(seg_out)
                        except: pass
                    break
                else:
                    saved_paths.append(os.path.basename(seg_out))
            
            if not self.is_running:
                self.finished.emit(False, AppContext.tr("editor_msg_aborted"))
            elif success_all:
                self.finished.emit(True, AppContext.tr("editor_msg_files_saved").format(', '.join(saved_paths)))
            else:
                self.finished.emit(False, AppContext.tr("editor_err_ffmpeg"))
            return

        # --- LOGIC FOR SINGLE FILE EXPORT (JOINED SEGMENTS) ---
        target_duration_sec = sum(end - start for start, end in segments)
        is_complex = has_effects or len(segments) > 1

        cmd = [ffmpeg, "-y"]
        cmd.extend(["-i", self.s['input']])
        if has_image_input:
            if self.s['overlay']['path'].lower().endswith('.gif'):
                cmd.extend(["-ignore_loop", "0"])
            cmd.extend(["-i", self.s['overlay']['path']])

        if not is_complex:
            # Simple TRIM - use copy mode
            start_s, end_s = segments[0]
            cmd = [ffmpeg, "-y", "-ss", f"{start_s:.3f}", "-i", self.s['input'], "-t", f"{(end_s - start_s):.3f}"]
            if is_audio:
                cmd.extend(["-c:a", "copy", self.s['output']])
            elif self.s.get('remove_audio') or not has_audio:
                cmd.extend(["-c:v", "copy", "-an", self.s['output']])
            else:
                cmd.extend(["-c", "copy", self.s['output']])
        else:
            filter_complex = []
            for idx, (ss, ee) in enumerate(segments):
                if not is_audio:
                    filter_complex.append(f"[0:v]trim=start={ss:.3f}:end={ee:.3f},setpts=PTS-STARTPTS[v{idx}]")
                if not self.s.get('remove_audio') and has_audio:
                    filter_complex.append(f"[0:a]atrim=start={ss:.3f}:end={ee:.3f},asetpts=PTS-STARTPTS[a{idx}]")
            
            if len(segments) > 1:
                if not is_audio:
                    v_inputs = "".join([f"[v{i}]" for i in range(len(segments))])
                    filter_complex.append(f"{v_inputs}concat=n={len(segments)}:v=1:a=0[v_joined]")
                    current_v_label = "[v_joined]"
                if not self.s.get('remove_audio') and has_audio:
                    a_inputs = "".join([f"[a{i}]" for i in range(len(segments))])
                    filter_complex.append(f"{a_inputs}concat=n={len(segments)}:v=0:a=1[a_out]")
            else:
                if not is_audio:
                    current_v_label = "[v0]"
                if not self.s.get('remove_audio') and has_audio:
                    filter_complex.append(f"[a0]anull[a_out]")

            # Transforms (Rotate/Flip)
            transforms = []
            rot = self.s.get('rotation', 0) % 360
            if rot == 90: transforms.append("transpose=1")
            elif rot == 180: transforms.append("transpose=1,transpose=1")
            elif rot == 270: transforms.append("transpose=2")
            if self.s.get('flip_h'): transforms.append("hflip")
            if self.s.get('flip_v'): transforms.append("vflip")
            if transforms:
                t_str = ",".join(transforms)
                filter_complex.append(f"{current_v_label}{t_str}[v_trans]")
                current_v_label = "[v_trans]"

            # Overlay
            ovl = self.s.get('overlay')
            if ovl:
                x = int(ovl['x'] * orig_w)
                y = int(ovl['y'] * orig_h)
                w = int(ovl['w'] * orig_w)
                h = int(ovl['h'] * orig_h)
                w = max(1, w)
                h = max(1, h)
                
                if ovl['type'] == 'region':
                    color = ovl.get('color', '#ff0000').replace('#', '0x')
                    opacity = ovl.get('opacity', 1.0)
                    col_str = f"{color}@{opacity}"
                    filter_complex.append(f"{current_v_label}drawbox=x={x}:y={y}:w={w}:h={h}:color={col_str}:t=fill[v_ovl]")
                    current_v_label = "[v_ovl]"
                elif ovl['type'] == 'blur':
                    sigma = (ovl.get('blur_val', 100) / 100.0) * 50
                    filter_complex.append(f"{current_v_label}split=2[v_base][v_tocrop]")
                    filter_complex.append(f"[v_tocrop]crop={w}:{h}:{x}:{y},gblur=sigma={sigma}[v_blurred]")
                    filter_complex.append(f"[v_base][v_blurred]overlay={x}:{y}[v_ovl]")
                    current_v_label = "[v_ovl]"
                elif ovl['type'] == 'image' and has_image_input:
                    filter_complex.append(f"[1:v]scale={w}:{h}[img_scaled]")
                    opacity = ovl.get('opacity', 1.0)
                    filter_complex.append(f"[img_scaled]format=rgba,colorchannelmixer=aa={opacity}[img_ready]")
                    filter_complex.append(f"{current_v_label}[img_ready]overlay={x}:{y}[v_ovl]")
                    current_v_label = "[v_ovl]"

            # Color Correction
            cc = self.s['cc']
            if cc['brightness'] != 0 or cc['contrast'] != 1 or cc['saturation'] != 1:
                eq_str = f"eq=brightness={cc['brightness']}:contrast={cc['contrast']}:saturation={cc['saturation']}"
                filter_complex.append(f"{current_v_label}{eq_str}[v_cc]")
                current_v_label = "[v_cc]"

            # Final Crop
            if self.s.get('crop'):
                c = self.s['crop']
                sw, sh = self.s['video_size']
                current_w, current_h = orig_w, orig_h
                rot = self.s.get('rotation', 0) % 360
                if rot == 90 or rot == 270:
                    current_w, current_h = orig_h, orig_w
                rx = int(c['x'] * current_w / sw)
                ry = int(c['y'] * current_h / sh)
                rw = (int(c['w'] * current_w / sw) // 2) * 2
                rh = (int(c['h'] * current_h / sh) // 2) * 2
                filter_complex.append(f"{current_v_label}crop={rw}:{rh}:{rx}:{ry}[v_final]")
                current_v_label = "[v_final]"

            cmd.extend(["-filter_complex", ";".join(filter_complex)])
            if not is_audio:
                cmd.extend(["-map", current_v_label])
            if not self.s.get('remove_audio') and has_audio:
                cmd.extend(["-map", "[a_out]"])

            if not is_audio:
                codec_val = self.s.get('video_codec', 'libx264')
                preset_val = self.s.get('video_preset', 'medium')
                quality_val = self.s.get('video_quality', 17)
                cmd.extend(["-c:v", codec_val, "-preset", preset_val, "-crf", str(quality_val)])
            
            cmd.extend(["-t", f"{target_duration_sec:.3f}"])
            if not self.s.get('remove_audio') and has_audio:
                cmd.extend(["-c:a", "aac", "-b:a", "192k"])
            cmd.append(self.s['output'])

        logging.info(f"SMART ENCODE (Joined Mode): {' '.join(cmd)}")
        ok = self._run_ffmpeg_cmd(cmd, target_duration_sec, 0, 100)
        
        if not self.is_running:
            self.finished.emit(False, AppContext.tr("editor_msg_aborted"))
        elif ok:
            self.finished.emit(True, AppContext.tr("editor_msg_file_saved").format(os.path.basename(self.s['output'])))
        else:
            if os.path.exists(self.s['output']):
                try: os.remove(self.s['output'])
                except: pass
            self.finished.emit(False, AppContext.tr("editor_err_ffmpeg"))

    def _run_ffmpeg_cmd(self, cmd: list[str], duration: float, start_pct: float, step_pct: float) -> bool:
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
                startupinfo=startupinfo,
                encoding='utf-8',
                errors='replace'
            )
        except Exception as e:
            logging.error(f"Failed to start FFmpeg process: {e}")
            return False

        stderr_lines: list[str] = []
        while self.is_running:
            line = self.process.stderr.readline()
            if not line and self.process.poll() is not None:
                break
            
            if line:
                stderr_lines.append(line.strip())
                if len(stderr_lines) > 30:
                    stderr_lines.pop(0)
                match = re.search(r'time=\s*(\d+):(\d+):(\d+(?:\.\d+)?)', line)
                if match and duration > 0:
                    h, m, s = match.groups()
                    curr_sec = int(h)*3600 + int(m)*60 + float(s)
                    percent = int((curr_sec / duration) * 100)
                    if percent > 100: percent = 100
                    global_percent = int(start_pct + (percent / 100.0) * step_pct)
                    if global_percent > 100: global_percent = 100
                    self.progress_updated.emit(global_percent)

        if not self.is_running:
            if self.process.poll() is None:
                self.process.terminate()
            self.process.wait()
            return False
            
        ret = (self.process.returncode == 0)
        if not ret:
            logging.error("FFmpeg error output:\n" + "\n".join(stderr_lines))
        return ret


    def stop(self) -> None:
        self.is_running = False

    def _has_audio_stream(self, ffprobe: str, path: str) -> bool:
        cmd = [
            ffprobe, "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=index",
            "-of", "json", path
        ]
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            proc = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo)
            data = json.loads(proc.stdout)
            return len(data.get('streams', [])) > 0
        except Exception as e:
            logging.error(f"Error checking audio stream: {e}")
            return False

    def _get_video_info(self, ffprobe: str, path: str, is_audio: bool = False) -> dict:
        stream_spec = "a:0" if is_audio else "v:0"
        cmd = [
            ffprobe, "-v", "error", "-select_streams", stream_spec,
            "-show_entries", "stream=width,height,bit_rate,duration",
            "-show_entries", "format=bit_rate,duration",
            "-of", "json", path
        ]
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            proc = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo)
            data = json.loads(proc.stdout)
            
            fmt = data.get('format', {})
            streams = data.get('streams', [])
            stream = streams[0] if streams else {}
            
            def safe_int(val, default):
                try: 
                    if isinstance(val, str):
                        val = val.split('.')[0] # handle float strings
                    return int(val)
                except: return default

            return {
                'width': safe_int(stream.get('width'), 1920),
                'height': safe_int(stream.get('height'), 1080),
                'bitrate': safe_int(fmt.get('bit_rate') or stream.get('bit_rate'), 5000000),
                'duration': float(fmt.get('duration') or stream.get('duration') or 0)
            }
        except Exception as e:
            logging.error(f"Error getting video info: {e}")
            return {}

    def _ms_to_ffmpeg(self, ms: float) -> str:
        sec = ms / 1000.0
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = sec % 60
        return f"{h:02}:{m:02}:{s:06.3f}"
