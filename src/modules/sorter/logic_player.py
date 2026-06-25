
import os
import logging
from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtGui import QPixmap
from config import AppContext, VIEWER_DESIGN
from utils_common import format_size
from utils_io import ensure_long_path

class PlayerMixin:
    """
    Mixin handles media playback, file display logic, and player controls interaction.
    Requires: self.viewer, self.media_player, self.video_controls, self.files_queue
    """
    
    def show_current_file(self):
        if not self.files_queue:
            self.current_file_path = None
            self.lbl_filename.setText(AppContext.tr("msg_empty"))
            self.viewer.show_empty_state(AppContext.tr("viewer_empty_msg"))
            self.media_player.stop()
            self.media_player.setSource(QUrl())
            return

        if self.current_index >= len(self.files_queue):
            self.current_index = 0
            
        filename = self.files_queue[self.current_index]
        self.current_file_path = ensure_long_path(os.path.join(self.UNSORT_DIR, filename))
        
        # --- Update Filename Label with Metadata (Mandatory) ---
        size = 0
        try: 
            size = os.path.getsize(self.current_file_path)
        except: 
            pass
        size_str = format_size(size)
        idx_str = f"[{self.current_index + 1}/{len(self.files_queue)}]"
        
        display_text = f"[{size_str}]  {filename}  {idx_str}"
        self.lbl_filename.setText(display_text)
        # --------------------------------------------------------
        
        self.update_window_title()

        # Если активен режим плиток или списка, не инициализируем проигрывание
        if hasattr(self, 'viewer') and self.viewer.stack.currentIndex() != 0:
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
        is_rotatable = ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp']
        if hasattr(self, 'btn_rot_l') and self.btn_rot_l:
            self.btn_rot_l.setVisible(is_rotatable)
        if hasattr(self, 'btn_rot_r') and self.btn_rot_r:
            self.btn_rot_r.setVisible(is_rotatable)
        
        # 1. Images (Static)
        if ext in ['.jpg', '.jpeg', '.png', '.bmp']:
            self.video_controls.hide()
            self.current_media_is_video = False
            self.viewer.set_image(QPixmap(self.current_file_path))
            
        # 2. Animations (GIF, WebP)
        elif ext in ['.gif', '.webp']:
            self.video_controls.hide()
            self.current_media_is_video = False
            self.viewer.set_animated(self.current_file_path)
            
        # 3. Video
        elif ext in ['.mp4', '.avi', '.mkv', '.mov', '.webm', '.wmv', '.flv', '.mpg', '.mpeg', '.m4v']:
            self.video_controls.show()
            self.current_media_is_video = True
            
            # Apply Session Settings
            if self.session_all_videos_active:
                speed = self.session_video_speed
            else:
                speed = 1.0
                
            loop = self.session_loop
            apply_all = self.session_all_videos_active
            
            self.video_controls.set_popup_values(speed, loop, apply_all, True)
            
            self.media_player.setSource(QUrl.fromLocalFile(self.current_file_path))
            self.media_player.setPlaybackRate(speed)
            
            if loop:
                self.media_player.setLoops(QMediaPlayer.Loops.Infinite)
            else:
                self.media_player.setLoops(QMediaPlayer.Loops.Once)
                
            self.viewer.set_video_mode()
            self.media_player.play()
            
        # 4. Audio
        elif ext in ['.mp3', '.wav', '.ogg', '.flac']:
            self.video_controls.show()
            self.current_media_is_video = False # Treat as audio for UI logic
            
            # Audio always resets speed by default logic
            self.video_controls.set_popup_values(1.0, False, False, False)
            
            self.media_player.setSource(QUrl.fromLocalFile(self.current_file_path))
            self.viewer.set_audio_mode(filename)
            self.media_player.play()
            
        else:
            self.video_controls.hide()
            self.current_media_is_video = False
            self.viewer.show_empty_state(AppContext.tr("msg_unsupported") + ext)

    def toggle_playback(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def _on_click_canvas(self):
        # Click on canvas toggles playback if it's video/audio
        if self.current_file_path:
            ext = os.path.splitext(self.current_file_path)[1].lower()
            if ext in ['.mp4', '.avi', '.mkv', '.mov', '.webm', '.mp3', '.wav', '.wmv', '.flv', '.mpg', '.mpeg', '.m4v']:
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
                show_player = ext in [
                    '.mp4', '.avi', '.mkv', '.mov', '.webm', '.wmv', '.flv', '.mpg', '.mpeg', '.m4v', # видео
                    '.mp3', '.wav', '.ogg', '.flac' # аудио
                ]
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

    def _on_scrub_stop(self):
        self.media_player.play()

    def _on_speed_changed(self, speed):
        self.media_player.setPlaybackRate(speed)
        if self.current_media_is_video:
            self.session_video_speed = speed
            AppContext.session_video_speed = speed

    def _set_loop_state(self, enabled):
        self.session_loop = enabled
        AppContext.session_loop = enabled
        AppContext.save_media_settings()
        if enabled:
            self.media_player.setLoops(QMediaPlayer.Loops.Infinite)
        else:
            self.media_player.setLoops(QMediaPlayer.Loops.Once)

    def _on_apply_all_toggled(self, enabled):
        self.session_all_videos_active = enabled
        AppContext.session_all_videos_active = enabled
        AppContext.save_media_settings()

    def _on_playback_state_changed(self, state):
        is_playing = (state == QMediaPlayer.PlaybackState.PlayingState)
        self.video_controls.set_playing_state(is_playing)
