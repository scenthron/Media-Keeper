
import os
import logging
from PyQt6.QtCore import QUrl, Qt, QTimer
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtGui import QPixmap, QImageReader
from config import AppContext, VIEWER_DESIGN
from utils_common import format_size
from utils_io import ensure_long_path
from utils_extensions import VIDEO_EXTS, AUDIO_EXTS, IMAGE_EXTS, get_filtered_exts

class SmartPreviewManager:
    """Manages the logic for segmented video playback (Smart Preview)."""
    def __init__(self, media_player, get_speed_func):
        self.media_player = media_player
        self.get_speed_func = get_speed_func # func returning current playback rate
        
        self.active = False
        self.user_paused = False
        
        self.total_duration_ms = 0
        self.num_segments = 0
        self.segment_play_time_ms = 0
        
        self.current_segment_idx = 0
        
        self.timer = QTimer()
        self.timer.timeout.connect(self._check_segment)
        self.timer.setInterval(200) # Check every 200ms
        
        # We also need to know when user manually seeks to pause it
        self.last_known_pos = 0

    def calculate_segments(self, duration_ms):
        dur_sec = duration_ms / 1000.0
        if dur_sec < 15:
            return 0, 0
        elif dur_sec <= 60:
            return 6, 1500
        else:
            return 5, 1500

    def start_video(self, duration_ms):
        self.total_duration_ms = duration_ms
        self.num_segments, self.segment_play_time_ms = self.calculate_segments(duration_ms)
        self.current_segment_idx = 0
        self.user_paused = False
        
        if self.active and self.num_segments > 0:
            self._jump_to_segment(0)
            self.timer.start()
        else:
            self.timer.stop()
            
    def stop(self):
        self.timer.stop()
        
    def set_active(self, active):
        self.active = active
        if active:
            self.user_paused = False
            if self.total_duration_ms > 0 and self.num_segments > 0:
                self._jump_to_segment(self.current_segment_idx)
                self.timer.start()
        else:
            self.timer.stop()
            
    def set_user_paused(self, paused):
        self.user_paused = paused
        if paused:
            self.timer.stop()
        else:
            if self.active and self.num_segments > 0:
                self.timer.start()

    def _jump_to_segment(self, idx):
        if self.num_segments <= 0: return
        self.current_segment_idx = max(0, min(idx, self.num_segments - 1))
        
        # calculate start time for this segment
        # length of each chunk
        chunk_len = self.total_duration_ms / self.num_segments
        target_pos = int(self.current_segment_idx * chunk_len)
        
        # small offset so we don't start at exact 0 frame if it's black
        if target_pos == 0 and self.total_duration_ms > 1000:
            target_pos = 500
            
        try:
            self.media_player.setPosition(target_pos)
            self.last_known_pos = target_pos
            self.segment_start_real_time = self.media_player.position()
        except RuntimeError:
            pass

    def _check_segment(self):
        if not self.active or self.user_paused or self.num_segments == 0:
            return
            
        try:
            # If user seeked manually, pause mode
            current_pos = self.media_player.position()
        except RuntimeError:
            self.timer.stop()
            return
            
        try:
            speed = float(self.get_speed_func())
        except ValueError:
            speed = 1.0
        if speed <= 0: speed = 1.0
        
        # Check how much we played in this segment (scaled by speed)
        chunk_len = self.total_duration_ms / self.num_segments
        segment_start_pos = int(self.current_segment_idx * chunk_len)
        
        time_played_ms = (current_pos - segment_start_pos)
        
        # if user seeked manually far away, disable segment view
        if abs(current_pos - self.last_known_pos) > 2000:
            self.set_user_paused(True)
            return
            
        self.last_known_pos = current_pos
        
        # time_played scaled by speed to check actual watch time
        real_time_watched_ms = time_played_ms / speed
        
        if real_time_watched_ms >= self.segment_play_time_ms:
            # jump to next
            next_idx = self.current_segment_idx + 1
            if next_idx >= self.num_segments:
                # Loop back or stop
                next_idx = 0
            self._jump_to_segment(next_idx)

    def skip_next(self):
        if self.num_segments > 0:
            next_idx = (self.current_segment_idx + 1) % self.num_segments
            self._jump_to_segment(next_idx)
            self.set_user_paused(False)

    def skip_prev(self):
        if self.num_segments > 0:
            prev_idx = (self.current_segment_idx - 1) % self.num_segments
            self._jump_to_segment(prev_idx)
            self.set_user_paused(False)


class PlayerMixin:
    """
    Mixin handles media playback, file display logic, and player controls interaction.
    Requires: self.viewer, self.media_player, self.video_controls, self.files_queue
    """
    
    def show_current_file(self):
        if not self.files_queue:
            self.current_file_path = None
            self.lbl_filename.setText(AppContext.tr("msg_empty") if hasattr(AppContext, 'tr') else "Папка пуста")
            self.viewer.show_empty_state(AppContext.tr("viewer_empty_msg") if hasattr(AppContext, 'tr') else "Нет файлов для отображения")
            self.media_player.stop()
            self.media_player.setSource(QUrl())
            return

        if self.current_index >= len(self.files_queue):
            self.current_index = 0
            
        filename = self.files_queue[self.current_index]
        self.current_file_path = ensure_long_path(os.path.join(self.UNSORT_DIR, filename))
        
        # Проверяем, не перемещается ли файл в данный момент
        from utils_io import strip_long_path_prefix
        norm_path = os.path.normpath(strip_long_path_prefix(self.current_file_path))
        if hasattr(self, 'locked_files') and norm_path in self.locked_files:
            self.lbl_filename.setText(f"{filename} (Перемещение...)")
            self.viewer.show_empty_state("Файл перемещается, предпросмотр недоступен...")
            self.media_player.stop()
            self.media_player.setSource(QUrl())
            if hasattr(self, 'video_controls'):
                self.video_controls.hide()
            return
            
        # --- Update Filename Label with Metadata (Mandatory) ---
        size = 0
        try: 
            size = os.path.getsize(self.current_file_path)
        except: 
            pass
        size_str = format_size(size)
        idx_str = f"[{self.current_index + 1}/{len(self.files_queue)}]"
        
        from utils_io import strip_long_path_prefix
        display_name = os.path.basename(strip_long_path_prefix(filename))
        
        display_text = f"[{size_str}]  {display_name}  {idx_str}"
        self.lbl_filename.setText(display_text)
        # --------------------------------------------------------
        
        self.update_window_title()

        # Если активен режим плиток или списка, не инициализируем проигрывание
        if hasattr(self, 'viewer') and self.viewer.current_view_mode != 0:
            self.media_player.stop()
            self.media_player.setSource(QUrl())
            if hasattr(self, 'video_controls'):
                self.video_controls.hide()
            logging.info(f"[PlayerMixin] Synced active index in Grid/List mode: {self.current_index}")
            self.viewer.sync_active_index(self.current_index)
            return
        
        # Reset Player State
        self.media_player.stop()
        self.video_controls.reset_controls()
        
        # Determine Type
        ext = os.path.splitext(filename)[1].lower()
        
        # Управляем видимостью кнопок вращения в соло-режиме
        is_rotatable = ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tiff', '.tif', '.heic', '.avif', '.apng', '.jfif']
        if hasattr(self, 'btn_rot_l') and self.btn_rot_l:
            self.btn_rot_l.setVisible(is_rotatable)
        if hasattr(self, 'btn_rot_r') and self.btn_rot_r:
            self.btn_rot_r.setVisible(is_rotatable)
        
        # Check if the GIF/WebP is animated
        is_gif_or_webp = ext in ['.gif', '.webp']
        is_animated = False
        if is_gif_or_webp:
            reader = QImageReader(self.current_file_path)
            is_animated = reader.supportsAnimation() and reader.imageCount() > 1
            logging.info(f"[PlayerMixin] File: {filename}, supportsAnimation: {reader.supportsAnimation()}, imageCount: {reader.imageCount()}, resolved is_animated: {is_animated}")
        
        # 1. Images (Static)
        if ext in IMAGE_EXTS or (is_gif_or_webp and not is_animated):
            self.video_controls.hide()
            self.current_media_is_video = False
            self.viewer.set_image(QPixmap(self.current_file_path))
            
        # 2. Animations (GIF, WebP)
        elif is_gif_or_webp and is_animated:
            self.video_controls.hide()
            self.current_media_is_video = False
            self.viewer.set_animated(self.current_file_path)
            
        # 3. Video
        elif ext in get_filtered_exts(VIDEO_EXTS, "logic_player_video"):
            self.video_controls.show()
            self.current_media_is_video = True
            
            from config import AppContext
            apply_all = AppContext.session_all_videos_active
            
            if apply_all:
                speed = float(AppContext.session_video_speed)
                loop = AppContext.session_loop
                segment_view = AppContext.session_segment_view
            else:
                speed = 1.0
                loop = False
                segment_view = False
            
            self.video_controls.set_popup_values(speed, loop, apply_all, segment_view, True)
            if hasattr(self, 'smart_preview_mgr'):
                self.smart_preview_mgr.set_active(segment_view)
            
            self.media_player.stop()
            from utils_io import strip_long_path_prefix
            clean_path = strip_long_path_prefix(self.current_file_path)
            self.media_player.setSource(QUrl.fromLocalFile(clean_path))
            self.media_player.setPlaybackRate(speed)
            
            if loop:
                self.media_player.setLoops(QMediaPlayer.Loops.Infinite)
            else:
                self.media_player.setLoops(QMediaPlayer.Loops.Once)
                
            self.viewer.set_video_mode()
            is_loading = hasattr(self, 'viewer') and hasattr(self.viewer, 'loading_overlay') and not self.viewer.loading_overlay.isHidden()
            if not is_loading:
                self.media_player.play()
            
        # 4. Audio
        elif ext in get_filtered_exts(AUDIO_EXTS, "logic_player_audio"):
            self.video_controls.show()
            self.current_media_is_video = False # Treat as audio for UI logic
            
            
            # Audio always resets speed by default logic
            self.video_controls.set_popup_values(1.0, False, False, False, False)
            
            self.media_player.stop()
            from utils_io import strip_long_path_prefix
            clean_path = strip_long_path_prefix(self.current_file_path)
            self.media_player.setSource(QUrl.fromLocalFile(clean_path))
            self.viewer.set_audio_mode(filename)
            is_loading = hasattr(self, 'viewer') and hasattr(self.viewer, 'loading_overlay') and not self.viewer.loading_overlay.isHidden()
            if not is_loading:
                self.media_player.play()
            
        else:
            self.video_controls.hide()
            self.current_media_is_video = False
            self.viewer.show_empty_state(AppContext.tr("msg_unsupported") + ext)

    def toggle_playback(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            if hasattr(self, 'smart_preview_mgr'):
                self.smart_preview_mgr.set_user_paused(True)
        else:
            self.media_player.play()

    def _on_click_canvas(self):
        # Click on canvas toggles playback if it's video/audio
        if self.current_file_path:
            ext = os.path.splitext(self.current_file_path)[1].lower()
            if ext in get_filtered_exts(VIDEO_EXTS, "logic_player_video") | get_filtered_exts(AUDIO_EXTS, "logic_player_audio"):
                self.toggle_playback()
            else:
                self.setFocus()

    def toggle_app_fullscreen(self):
        if self.window().isFullScreen():
            self.window().showNormal()
            self.viewer.set_fullscreen_mode(False)
            # Restore sidebar and toolbar
            self.sidebar.show()
            self.toolbar.show()
            self.bottom_controls_container.show()
            self.left_layout.insertWidget(2, self.video_controls)
            # Показываем контролы плеера только если текущий файл является видео или аудио
            show_player = False
            if hasattr(self, 'current_file_path') and self.current_file_path:
                ext = os.path.splitext(self.current_file_path)[1].lower()
                show_player = ext in get_filtered_exts(VIDEO_EXTS, "logic_player_video") | get_filtered_exts(AUDIO_EXTS, "logic_player_audio")
            if show_player:
                self.video_controls.show()
            else:
                self.video_controls.hide()
            
            self.layout().setContentsMargins(0,0,0,0)
        else:
            self.window().showFullScreen()
            self.sidebar.hide()
            self.toolbar.hide()
            self.bottom_controls_container.hide()
            
            # Pass controls to viewer overlay if video
            controls_to_pass = None
            if self.video_controls.isVisible():
                controls_to_pass = self.video_controls
                
            self.viewer.set_fullscreen_mode(True, controls_to_pass)

    def _fit_video(self, status):
        if status == QMediaPlayer.MediaStatus.BufferedMedia or status == QMediaPlayer.MediaStatus.LoadedMedia:
            if hasattr(self, 'viewer') and hasattr(self.viewer, 'single_view') and self.viewer.single_view.video_item.nativeSize().isValid():
                sz = self.viewer.single_view.video_item.nativeSize()
                self.viewer.single_view._fit_video_size_changed(sz)
            else:
                self.viewer.reset_view()

    def _fit_video_size_changed(self, size):
        if hasattr(self, 'viewer') and hasattr(self.viewer, 'single_view') and hasattr(self.viewer.single_view, '_fit_video_size_changed'):
            self.viewer.single_view._fit_video_size_changed(size)
        else:
            self.viewer.video_item.setSize(size)
            self.viewer.reset_view()

    def _on_scrub_start(self):
        self.media_player.pause()
        if hasattr(self, 'smart_preview_mgr'):
            self.smart_preview_mgr.set_user_paused(True)

    def _on_scrub_stop(self):
        self.media_player.play()

    def _on_speed_changed(self, speed):
        self.media_player.setPlaybackRate(speed)
        if self.current_media_is_video:
            from config import AppContext
            AppContext.session_video_speed = float(speed)

    def _set_loop_state(self, enabled):
        from config import AppContext
        AppContext.session_loop = enabled
        AppContext.save_media_settings()
        if enabled:
            self.media_player.setLoops(QMediaPlayer.Loops.Infinite)
        else:
            self.media_player.setLoops(QMediaPlayer.Loops.Once)

    def _on_apply_all_toggled(self, enabled):
        from config import AppContext
        AppContext.session_all_videos_active = enabled
        AppContext.save_media_settings()

    def _on_segment_view_toggled(self, enabled):
        from config import AppContext
        AppContext.session_segment_view = enabled
        AppContext.save_media_settings()
        if hasattr(self, 'smart_preview_mgr'):
            self.smart_preview_mgr.set_active(enabled)

    def _log_media_error(self, error, errorString):
        logging.error(f"[MediaPlayer] Error: {error}, Description: {errorString}")

    def _log_media_status(self, status):
        from PyQt6.QtMultimedia import QMediaPlayer
        status_name = {
            QMediaPlayer.MediaStatus.NoMedia: "NoMedia",
            QMediaPlayer.MediaStatus.LoadingMedia: "LoadingMedia",
            QMediaPlayer.MediaStatus.LoadedMedia: "LoadedMedia",
            QMediaPlayer.MediaStatus.StalledMedia: "StalledMedia",
            QMediaPlayer.MediaStatus.BufferingMedia: "BufferingMedia",
            QMediaPlayer.MediaStatus.BufferedMedia: "BufferedMedia",
            QMediaPlayer.MediaStatus.EndOfMedia: "EndOfMedia",
            QMediaPlayer.MediaStatus.InvalidMedia: "InvalidMedia",
        }.get(status, f"Unknown ({status})")
        logging.info(f"[MediaPlayer] Status changed: {status_name}")

    def _on_playback_state_changed(self, state):
        from PyQt6.QtMultimedia import QMediaPlayer
        state_name = {
            QMediaPlayer.PlaybackState.StoppedState: "Stopped",
            QMediaPlayer.PlaybackState.PlayingState: "Playing",
            QMediaPlayer.PlaybackState.PausedState: "Paused",
        }.get(state, f"Unknown ({state})")
        logging.info(f"[MediaPlayer] Playback state changed: {state_name}")
        
        is_playing = (state == QMediaPlayer.PlaybackState.PlayingState)
        self.video_controls.set_playing_state(is_playing)
