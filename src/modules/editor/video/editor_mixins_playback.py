
import os
import subprocess
import tempfile
from PyQt6.QtCore import QUrl, QTimer, Qt
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtGui import QPixmap, QTransform
from config import AppContext
from logic_paths import get_ffmpeg_exe

class EditorPlaybackMixin:
    """Logic related to media player events, seeking, scrubbing, and preview generation."""

    def _on_pos_changed(self, pos):
        dur = self.player.duration()
        if dur <= 0: return
        
        norm_pos = pos / dur
        self.waveform_progress.set_playback_pos(norm_pos)
        self.lbl_time.setText(f"{self._to_hms(pos)} / {self._to_hms(dur)}")
        
        # Max label width fix
        total_str = self._to_hms(dur)
        max_str = f"{total_str} / {total_str}"
        metrics = self.lbl_time.fontMetrics()
        width = metrics.horizontalAdvance(max_str) + 15
        self.lbl_time.setFixedWidth(width)
        
        # Real-time synchronization of marker time field with playback cursor
        if hasattr(self, 'edit_marker_time') and not self.edit_marker_time.hasFocus():
            self.edit_marker_time.setText(self._to_hms_full(pos))
        
        if self._is_preview_mode:
            markers = self.waveform_progress.markers
            inverted = self.waveform_progress.is_inverted
            
            segments = [0.0] + markers + [1.0]
            current_seg_idx = -1
            for i in range(len(segments) - 1):
                if segments[i] <= norm_pos <= segments[i+1]:
                    current_seg_idx = i
                    break
            
            if current_seg_idx != -1:
                from .helpers import is_segment_taken
                is_green = is_segment_taken(len(markers), current_seg_idx, inverted)
                
                if not is_green:
                    next_green_idx = -1
                    for i in range(current_seg_idx + 1, len(segments) - 1):
                        from .helpers import is_segment_taken
                        take = is_segment_taken(len(markers), i, inverted)
                        if take:
                            next_green_idx = i
                            break
                    
                    if next_green_idx != -1:
                        target_ms = int(segments[next_green_idx] * dur)
                        self.player.setPosition(target_ms)
                    else:
                        self.player.pause()
                        self._is_preview_mode = False
                        self._set_ui_locked(False)

        if pos >= dur and dur > 0:
            if self.is_looping:
                self.player.setPosition(0)
                self.player.play()
            else:
                self.player.pause()

    def _on_duration_changed(self, dur):
        total_str = self._to_hms(dur)
        self.lbl_time.setText(f"0.000 / {total_str}")
        if self.is_video_loaded:
            self.center_video()

    def _on_state_changed(self, state):
        self.btn_play.setIcon(self.icon_pause if state == QMediaPlayer.PlaybackState.PlayingState else self.icon_play)
        
        is_playing = (state == QMediaPlayer.PlaybackState.PlayingState)
        if hasattr(self, 'cc_controls'):
            for w in self.cc_controls:
                w.setEnabled(not is_playing)

        if is_playing:
            if self.preview_item.isVisible():
                self.preview_item.hide()
            if not self.video_item.isVisible():
                self.video_item.show()
        else:
            if self._is_preview_mode:
                self._is_preview_mode = False
                self._set_ui_locked(False)
            self._schedule_cc_preview()

    def toggle_play(self):
        self._is_fragment_mode = False
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _init_frame_step_controllers(self):
        """Инициализация таймеров и контроллеров покадровой перемотки и замедленного просмотра"""
        self._frame_hold_timer = QTimer(self)
        self._frame_hold_timer.setSingleShot(True)
        self._frame_hold_timer.setInterval(260)
        self._frame_hold_timer.timeout.connect(self._on_frame_hold_timeout)
        
        self._rewind_timer = QTimer(self)
        self._rewind_timer.timeout.connect(self._on_rewind_tick)
        
        self._active_step_direction = 0  # 1: вперед, -1: назад, 0: нет
        self._is_holding_step = False
        self._is_seeking_back = False
        self._original_playback_rate = 1.0

    def _get_selected_slow_speed(self) -> float:
        if hasattr(self, 'combo_slow_speed'):
            data = self.combo_slow_speed.currentData()
            if data is not None:
                try:
                    return float(data)
                except Exception:
                    pass
        return 0.25

    def _on_step_btn_pressed(self, direction: int):
        dur = self.player.duration()
        if dur <= 0: return
        self._active_step_direction = direction
        self._is_holding_step = False
        self._frame_hold_timer.start()

    def _on_step_btn_released(self, direction: int):
        if self._active_step_direction != direction and self._active_step_direction != 0:
            return
        
        self._frame_hold_timer.stop()
        
        if not self._is_holding_step:
            # Одиночный клик: точный шаг на 1 кадр
            self._step_frame(direction)
        else:
            # Завершение замедленного просмотра
            if direction == 1:
                self.player.pause()
                self.player.setPlaybackRate(1.0)
                self._schedule_cc_preview()
            elif direction == -1:
                self._rewind_timer.stop()
                self._is_seeking_back = False
                self._schedule_cc_preview()
                
        self._active_step_direction = 0
        self._is_holding_step = False

    def _on_frame_hold_timeout(self):
        self._is_holding_step = True
        dur = self.player.duration()
        if dur <= 0: return
        
        speed = self._get_selected_slow_speed()
        
        if self._active_step_direction == 1:
            # Воспроизведение вперед с выбранной скоростью
            if self.preview_item.isVisible():
                self.preview_item.hide()
            if not self.video_item.isVisible():
                self.video_item.show()
                
            self.player.setPlaybackRate(speed)
            if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self.player.play()
        elif self._active_step_direction == -1:
            # Замедленная перемотка назад с синхронизированной частотой
            interval_ms = max(40, int(33.3 / speed))
            self._rewind_timer.setInterval(interval_ms)
            self._is_seeking_back = False
            self._on_rewind_tick()
            self._rewind_timer.start()

    def _on_rewind_tick(self):
        if self._is_seeking_back:
            return
        if self.player.duration() <= 0:
            self._rewind_timer.stop()
            return
        if self.player.position() <= 0:
            self._rewind_timer.stop()
            return
            
        self._is_seeking_back = True
        self._step_frame(-1)
        # Таймаут сброса флага на случай задержки декодера
        QTimer.singleShot(140, self._unlock_seeking_back)

    def _unlock_seeking_back(self):
        self._is_seeking_back = False

    def _on_video_frame_arrived(self, frame):
        self._is_seeking_back = False

    def _step_frame(self, count):
        step_ms = 33
        dur = self.player.duration()
        if dur <= 0: return

        if self.preview_item.isVisible():
            self.preview_item.hide()
        if not self.video_item.isVisible():
            self.video_item.show()

        if self.waveform_progress.selected_idx != -1:
            idx = self.waveform_progress.selected_idx
            current_norm = self.waveform_progress.markers[idx]
            current_ms = current_norm * dur
            
            new_ms = current_ms + (count * step_ms)
            new_norm = max(0.001, min(0.999, new_ms / dur))
            
            lower = self.waveform_progress.markers[idx-1] if idx > 0 else 0.0
            upper = self.waveform_progress.markers[idx+1] if idx < len(self.waveform_progress.markers)-1 else 1.0
            new_norm = max(lower + 0.001, min(upper - 0.001, new_norm))
            
            self.waveform_progress.markers[idx] = new_norm
            self.waveform_progress.update_states()
            target_pos = int(new_norm * dur)
            self.player.setPosition(target_pos)
            self._pending_preview_pos = target_pos
            self._schedule_cc_preview()
            return

        target_pos = max(0, min(dur, self.player.position() + count * step_ms))
        self.player.setPosition(target_pos)
        self._pending_preview_pos = target_pos
        self._schedule_cc_preview()

    def _on_scrub_started(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._was_playing_before_scrub = True
            self.player.pause()
        else:
            self._was_playing_before_scrub = False

    def _on_scrub_finished(self):
        if self._was_playing_before_scrub:
            self.player.play()

    def _on_seek_requested(self, norm_pos):
        if self.player.duration() > 0:
            if self.preview_item.isVisible():
                self.preview_item.hide()
            if not self.video_item.isVisible():
                self.video_item.show()
            target_pos = int(norm_pos * self.player.duration())
            self.player.setPosition(target_pos)
            self._pending_preview_pos = target_pos
            self.scrub_preview_timer.stop()
            self.scrub_preview_timer.start()

    def _to_hms(self, ms):
        h = ms // 3600000
        m = (ms % 3600000) // 60000
        s = (ms % 60000) // 1000
        sss = ms % 1000
        if h > 0: return f"{h}:{m:02}:{s:02}.{sss:03}"
        if m > 0: return f"{m}:{s:02}.{sss:03}"
        return f"{s}.{sss:03}"

    def _schedule_cc_preview(self, interval=150):
        self.preview_timer.setInterval(interval)
        self.preview_timer.start()

    def _has_cc_or_blur(self) -> bool:
        has_cc = (abs(getattr(self, 'cc_brightness', 0.0)) > 0.01 or 
                  abs(getattr(self, 'cc_contrast', 1.0) - 1.0) > 0.01 or 
                  abs(getattr(self, 'cc_saturation', 1.0) - 1.0) > 0.01)
        has_blur = False
        if hasattr(self, 'chk_overlay_enable') and self.chk_overlay_enable.isChecked():
            if hasattr(self, 'combo_overlay_type') and self.combo_overlay_type.currentIndex() == 2: # blur
                has_blur = True
        return has_cc or has_blur

    def _update_cc_preview(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            return 
        if not self.current_file: return
        
        if not self._has_cc_or_blur():
            if self.preview_item.isVisible():
                self.preview_item.hide()
            if not self.video_item.isVisible():
                self.video_item.show()
            return

        if hasattr(self, '_pending_preview_pos') and self._pending_preview_pos is not None:
            pos_ms = self._pending_preview_pos
            self._pending_preview_pos = None
        else:
            pos_ms = self.player.position()
        
        if pos_ms == 0 and self.player.duration() > 0:
            QTimer.singleShot(100, lambda: self._update_cc_preview() if self.player.duration() > 0 else None)
            return
        
        ss = pos_ms / 1000.0
        filters = []
        eq_parts = []
        if abs(self.cc_brightness) > 0.01: eq_parts.append(f"brightness={self.cc_brightness:.2f}")
        if abs(self.cc_contrast - 1.0) > 0.01: eq_parts.append(f"contrast={self.cc_contrast:.2f}")
        if abs(self.cc_saturation - 1.0) > 0.01: eq_parts.append(f"saturation={self.cc_saturation:.2f}")
        
        if eq_parts: filters.append(f"eq={''.join(':'.join(eq_parts))}")
        
        try:
            temp_path = os.path.join(tempfile.gettempdir(), "mk_preview.jpg")
            ffmpeg_exe = get_ffmpeg_exe()
            
            # Accurate frame seek using combined seek (fast seek before -i, precise seek after -i)
            if ss > 10.0:
                ss_before = ss - 10.0
                cmd = [ffmpeg_exe, "-y", "-ss", f"{ss_before:.3f}", "-i", self.current_file, "-ss", "10.000"]
            else:
                cmd = [ffmpeg_exe, "-y", "-i", self.current_file, "-ss", f"{ss:.3f}"]
            if filters:
                cmd.extend(["-vf", ",".join(filters)])
            cmd.extend(["-frames:v", "1", "-f", "image2", temp_path])
            
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            
            if os.path.exists(temp_path):
                img = QPixmap(temp_path)
                if not img.isNull():
                    if self.video_item.boundingRect().width() > 0:
                        scaled = img.scaled(self.video_item.boundingRect().size().toSize(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                        self.overlay_item.set_source_pixmap(scaled)
                        
                        has_cc = (abs(getattr(self, 'cc_brightness', 0.0)) > 0.01 or 
                                  abs(getattr(self, 'cc_contrast', 1.0) - 1.0) > 0.01 or 
                                  abs(getattr(self, 'cc_saturation', 1.0) - 1.0) > 0.01)
                        if has_cc:
                            self.preview_item.setPixmap(scaled)
                            self.preview_item.setPos(self.video_item.pos())
                            self.preview_item.show()
                        else:
                            if self.preview_item.isVisible():
                                self.preview_item.hide()
                            if not self.video_item.isVisible():
                                self.video_item.show()
        except Exception as e:
            print(f"Preview error: {e}")
