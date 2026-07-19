from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QSplitter, 
    QTableWidget, QTableWidgetItem, QHeaderView, QGraphicsView, QGraphicsScene,
    QGraphicsTextItem
)
from modules.cleaner.ui_view import ClickableGraphicsView
from PyQt6.QtCore import Qt, QUrl, QRectF, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QImageReader, QMovie, QColor, QFont, QDesktopServices
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem

from config import AppContext, VIEWER_DESIGN
from utils_common import format_size
from modules.sorter.ui_player import VideoPlayerControls, TimeOverlayWidget, SegmentIndicatorWidget
from modules.sorter.logic_player import SmartPreviewManager
import logging
import os
import datetime

VIDEO_EXTS = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v']

class CleanerPreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #000; border: none;")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0,0,0,0)
        self.layout.setSpacing(0)
        
        self.current_media_type = None
        self.current_path = None
        
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setHandleWidth(4)
        self.splitter.setStyleSheet("QSplitter::handle { background-color: #333; border-top: 1px solid #444; border-bottom: 1px solid #444; } QSplitter::handle:hover { background-color: #3b82f6; }")
        
        self.media_container = QWidget()
        self.media_layout = QVBoxLayout(self.media_container)
        self.media_layout.setContentsMargins(0,0,0,0)
        self.media_layout.setSpacing(0)
        
        self.scene = QGraphicsScene()
        self.view = ClickableGraphicsView(self.scene, self.media_container)
        self.scene.setParent(self.view)
        self.media_layout.addWidget(self.view)
        
        self.view.clicked.connect(self.toggle_playback)
        self.view.double_clicked.connect(self.open_current_file)
        self.view.middle_clicked.connect(self.open_containing_folder)
        self.view.right_clicked.connect(self.reset_view)
        self.view.mouse_moved.connect(self._view_mouse_move_event)
        
        self.pixmap_item = self.scene.addPixmap(QPixmap())
        self.pixmap_item.hide()
        
        self.text_item = QGraphicsTextItem()
        self.scene.addItem(self.text_item)
        self.text_item.hide()
        
        self.video_item = QGraphicsVideoItem()
        self.scene.addItem(self.video_item)
        self.video_item.hide()
        
        self.video_controls = VideoPlayerControls()
        self.video_controls.hide()
        self.media_layout.addWidget(self.video_controls)
        
        self.btn_seg_prev = QPushButton("<", self.media_container)
        self.btn_seg_next = QPushButton(">", self.media_container)
        
        btn_style = """
            QPushButton {
                background-color: rgba(0, 0, 0, 0.4);
                color: rgba(255, 255, 255, 0.6);
                border: none;
                border-radius: 8px;
                font-size: 32px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(59, 130, 246, 0.7);
                color: white;
            }
        """
        for btn in (self.btn_seg_prev, self.btn_seg_next):
            btn.setStyleSheet(btn_style)
            btn.setFixedSize(50, 100)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.hide()
            
        self.btn_seg_prev.clicked.connect(self._on_seg_prev)
        self.btn_seg_next.clicked.connect(self._on_seg_next)
        
        self.segment_indicator = SegmentIndicatorWidget(self.media_container, is_small=True)
        self.segment_indicator.hide()
        self.segment_indicator.clicked.connect(self._on_segment_indicator_clicked)
        
        self.media_container.setMouseTracking(True)
        
        self.splitter.addWidget(self.media_container)
        
        self.meta_wrapper = QWidget()
        self.meta_wrapper.hide() 
        mw_layout = QVBoxLayout(self.meta_wrapper)
        mw_layout.setContentsMargins(0,0,0,0)
        mw_layout.setSpacing(0)
        
        self.btn_toggle_info = QPushButton()
        self.btn_toggle_info.setCheckable(True)
        self.btn_toggle_info.setFixedHeight(26)
        self.btn_toggle_info.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_info.setStyleSheet("""
            QPushButton { background-color: #2b2b2b; color: #888; border: none; border-bottom: 2px solid #333; font-size: 10px; font-weight: bold; text-align: left; padding-left: 10px; }
            QPushButton:hover { background-color: #333; color: #bbb; }
            QPushButton:checked { color: #3b82f6; border-bottom-color: #3b82f6; }
        """)
        self.btn_toggle_info.clicked.connect(self.toggle_info_panel)
        mw_layout.addWidget(self.btn_toggle_info)

        self.meta_table = QTableWidget()
        self.meta_table.setColumnCount(2)
        self.meta_table.horizontalHeader().hide()
        self.meta_table.verticalHeader().hide()
        self.meta_table.setShowGrid(False)
        self.meta_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.meta_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.meta_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.meta_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.meta_table.setStyleSheet("QTableWidget { background-color: #111; color: #eee; font-size: 11px; border: none; } QTableWidget::item { padding: 2px 5px; border-bottom: 1px solid #222; }")
        self.meta_table.hide()
        mw_layout.addWidget(self.meta_table)
        self.splitter.addWidget(self.meta_wrapper)
        
        self.layout.addWidget(self.splitter)
        self.splitter.setSizes([800, 26])
        
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_item)
        
        self.player.positionChanged.connect(self.video_controls.update_position)
        self.player.positionChanged.connect(self._update_overlay_time)
        self.player.durationChanged.connect(self.video_controls.update_duration)
        self.player.durationChanged.connect(self._update_overlay_duration)
        self.player.durationChanged.connect(self._on_media_duration_changed)
        self.player.playbackStateChanged.connect(self._on_player_state_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.video_item.nativeSizeChanged.connect(self._fit_video_size_changed)
        
        self.video_controls.seek_requested.connect(self.player.setPosition)
        self.video_controls.seek_moved.connect(self.player.setPosition)
        
        self.video_controls.play_pause_clicked.connect(self.toggle_playback)
        self.video_controls.seek_drag_start.connect(self._on_scrub_start)
        self.video_controls.seek_drag_stop.connect(self._on_scrub_stop)
        self.video_controls.volume_changed.connect(self.change_volume)
        
        self.video_controls.speed_changed.connect(self._on_speed_changed)
        self.video_controls.loop_toggled.connect(self._on_loop_toggled)
        self.video_controls.speed_toggled.connect(self._on_speed_toggled)
        
        self.smart_preview_mgr = None
        self._play_timer = QTimer(self)
        self._play_timer.setSingleShot(True)
        self._play_timer.timeout.connect(self._do_play)
        self.time_overlay = TimeOverlayWidget(self.media_container)
        self.time_overlay.hide()
        
        self.movie = None
        self.show_empty("...")

    def update_ui_text(self):
        base_text = AppContext.tr("cln_meta_header").upper()
        arrow = " ▼" if self.btn_toggle_info.isChecked() else " ▲"
        self.btn_toggle_info.setText(base_text + arrow)
        
        if self.text_item.isVisible() and not self.current_path:
            self.text_item.setPlainText(AppContext.tr("preview_hint"))
        
        if self.current_path:
             self.update_meta(self.current_path)
             
        self.video_controls.update_ui_text()

    def resizeEvent(self, event):
        if event is not None:
            super().resizeEvent(event)
        QTimer.singleShot(10, self.reset_view)
        
        if self.time_overlay.isVisible():
            padding = 10
            controls_h = self.video_controls.height() if self.video_controls.isVisible() else 0
            x = self.media_container.width() - self.time_overlay.width() - padding
            y = self.media_container.height() - controls_h - self.time_overlay.height() - padding
            self.time_overlay.move(x, y)
            
        y_center = (self.media_container.height() - self.btn_seg_prev.height()) // 2
        self.btn_seg_prev.move(20, y_center)
        self.btn_seg_next.move(self.media_container.width() - self.btn_seg_next.width() - 20, y_center)
        self.btn_seg_prev.raise_()
        self.btn_seg_next.raise_()
        self.segment_indicator.move(10, 10)

    def _on_media_duration_changed(self, duration):
        if self.current_media_type == "video" and duration > 1000:
            try:
                self.player.setPosition(100)
            except Exception: pass
        if self.smart_preview_mgr:
            self.smart_preview_mgr.start_video(duration)
            
    def _on_scrub_start(self):
        self._was_playing_before_scrub = (self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
        self.player.pause()
        if self.smart_preview_mgr:
            self.smart_preview_mgr.set_user_paused(True)

    def _on_scrub_stop(self):
        if getattr(self, '_was_playing_before_scrub', False):
            self.player.play()
            if self.smart_preview_mgr:
                self.smart_preview_mgr.set_user_paused(False)

    def _on_speed_changed(self, speed_val):
        AppContext.session_fast_speed_val = float(speed_val)
        active = True
        if self.current_media_type == 'video':
            AppContext.session_video_speed_active = True
        else:
            AppContext.session_audio_speed_active = True
        self.player.setPlaybackRate(speed_val)
        self.video_controls.update_speed_button(AppContext.session_fast_speed_val, active)

    def _on_speed_toggled(self):
        if self.current_media_type == 'video':
            AppContext.session_video_speed_active = not AppContext.session_video_speed_active
            active = AppContext.session_video_speed_active
        else:
            AppContext.session_audio_speed_active = not AppContext.session_audio_speed_active
            active = AppContext.session_audio_speed_active
        speed = AppContext.session_fast_speed_val if active else 1.0
        self.player.setPlaybackRate(speed)
        self.video_controls.update_speed_button(AppContext.session_fast_speed_val, active)

    def _on_loop_toggled(self, is_loop):
        self.player.setLoops(QMediaPlayer.Loops.Infinite if is_loop else QMediaPlayer.Loops.Once)
        AppContext.session_loop = is_loop

    def _on_segment_indicator_clicked(self):
        self.segment_indicator.stop_blinking(transparent=False)
        self.segment_indicator.is_active_mode = True
        self.segment_indicator.setStyleSheet("background-color: #3b82f6; border-radius: 4px;")
        if self.smart_preview_mgr:
            self.smart_preview_mgr.set_user_paused(True)
            
    def _on_seg_prev(self):
        if self.smart_preview_mgr:
            self.smart_preview_mgr.prev_segment()
            
    def _on_seg_next(self):
        if self.smart_preview_mgr:
            self.smart_preview_mgr.next_segment()

    def update_segment_indicator(self):
        mgr = self.smart_preview_mgr
        if self.current_media_type == 'video' and mgr:
            self.segment_indicator.show()
            self.segment_indicator.raise_()
            if mgr.active and not mgr.user_paused:
                if not getattr(self.segment_indicator, 'is_active_mode', False):
                    self.segment_indicator.start_blinking()
            else:
                self.segment_indicator.stop_blinking(transparent=True)
        else:
            self.segment_indicator.stop_blinking(transparent=False)
            self.segment_indicator.hide()
            self.btn_seg_prev.hide()
            self.btn_seg_next.hide()
            
    def _view_mouse_move_event(self, event):
        segment_active = self.smart_preview_mgr and self.smart_preview_mgr.active and self.smart_preview_mgr.num_segments > 0
            
        if segment_active and self.current_media_type == 'video':
            pos = event.pos()
            view_width = self.view.width()
            if pos.x() < view_width * 0.3:
                self.btn_seg_prev.show()
                self.btn_seg_next.hide()
            elif pos.x() > view_width * 0.7:
                self.btn_seg_next.show()
                self.btn_seg_prev.hide()
            else:
                self.btn_seg_prev.hide()
                self.btn_seg_next.hide()
        else:
            self.btn_seg_prev.hide()
            self.btn_seg_next.hide()

    def _update_overlay_time(self, pos):
        dur = self.player.duration()
        self.time_overlay.set_time(pos, dur)

    def _update_overlay_duration(self, dur):
        pos = self.player.position()
        self.time_overlay.set_time(pos, dur)

    def change_volume(self, val):
        self.audio_output.setVolume(val / 100.0)

    def _do_play(self):
        if self.current_media_type in ['video', 'audio'] and hasattr(self, 'player') and self.player:
            self.player.play()

    def _clear_media(self):
        if hasattr(self, '_play_timer'):
            self._play_timer.stop()
        if self.player:
            self.player.stop()
            from PyQt6.QtCore import QUrl
            self.player.setSource(QUrl())
        if self.movie:
            self.movie.stop()
            self.movie = None
        self.smart_preview_mgr = None
        if hasattr(self, 'pixmap_item'): self.pixmap_item.hide()
        if hasattr(self, 'video_item'): self.video_item.hide()
        if hasattr(self, 'text_item'): self.text_item.hide()

    def show_empty(self, msg):
        self.stop_playback(True)
        self.current_media_type = None
        self.current_path = None
        self.view.resetTransform()
        self.video_controls.hide()
        self.time_overlay.hide()
        
        self.text_item.setDefaultTextColor(QColor("#555555"))
        self.text_item.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.text_item.setTextWidth(-1)
        
        if msg == "..." or not msg:
            self.text_item.setPlainText(AppContext.tr("preview_hint"))
        else:
            self.text_item.setPlainText(msg)
            
        self.text_item.show()
        self.reset_view()
        self.meta_table.clear()
        self.meta_table.setRowCount(0)

    def setup_static_image(self, path):
        self._clear_media()
        self.current_media_type = 'image'
        self.video_controls.hide()
        self.time_overlay.hide()
        
        try:
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            img = reader.read()
            if not img.isNull():
                self.pixmap_item.setPixmap(QPixmap.fromImage(img))
                self.pixmap_item.show()
                QTimer.singleShot(10, self.reset_view)
            else:
                self.show_empty(AppContext.tr("msg_error_file"))
        except:
            self.show_empty(AppContext.tr("msg_error_file"))

    def setup_animated(self, path):
        self._clear_media()
        self.current_media_type = 'movie'
        self.video_controls.show()
        self.video_controls.seeker.setEnabled(False)
        self.video_controls.set_playing_state(True)
        self.time_overlay.hide()
        
        self.movie = QMovie(path)
        self.movie.frameChanged.connect(self._on_movie_frame)
        self.movie.start()
        self.pixmap_item.show()
        
    def setup_video(self, path):
        self._clear_media()
        self.time_overlay.show()
        self.time_overlay.set_time(0, 0)
        
        ext = os.path.splitext(path)[1].lower()
        is_audio = ext in ['.mp3', '.wav', '.ogg', '.flac', '.m4a', '.wma', '.aac']
        self.current_media_type = 'audio' if is_audio else 'video'
        
        if is_audio:
            track_name = os.path.splitext(os.path.basename(path))[0]
            html_text = f"<div style='text-align: center; line-height: 1.4; color: #3b82f6;'>🎵<br>{track_name}</div>"
            self.text_item.setHtml(html_text)
            self.text_item.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
            self.text_item.setTextWidth(400)
            self.text_item.show()
            QTimer.singleShot(50, self.reset_view)
        else:
            self.video_item.show()
            
        self.video_controls.show()
        self.video_controls.seeker.setEnabled(True)
        self.video_controls.set_playing_state(False)
        self.audio_output.setVolume(self.video_controls.vol_slider.value() / 100.0)
        
        from utils_io import strip_long_path_prefix
        clean_path = strip_long_path_prefix(path)
        self.player.setSource(QUrl.fromLocalFile(clean_path))
        
        self.resizeEvent(None)
        
        if is_audio:
            AppContext.session_audio_speed_active = False
            is_fast_active = False
            speed = 1.0
            loop = AppContext.session_loop
            segment_view = False
        else:
            is_fast_active = AppContext.session_video_speed_active
            speed = float(AppContext.session_fast_speed_val) if is_fast_active else 1.0
            loop = AppContext.session_loop
            segment_view = AppContext.session_segment_view
            
        self.video_controls.set_playing_state(False)
        self.video_controls.update_speed_button(AppContext.session_fast_speed_val, is_fast_active)
        self.video_controls.update_loop_button(loop)
        
        self.smart_preview_mgr = SmartPreviewManager(self.player, lambda: float(AppContext.session_fast_speed_val) if getattr(AppContext, "session_video_speed_active", False) else 1.0)
        self.smart_preview_mgr.set_active(segment_view)
        
        self.player.setPlaybackRate(speed)
        self.player.setLoops(QMediaPlayer.Loops.Infinite if loop else QMediaPlayer.Loops.Once)
        self._play_timer.start(100)

    def load_file(self, path):
        from utils_io import strip_long_path_prefix
        path = strip_long_path_prefix(path)
        
        if self.current_path == path:
            return
            
        if not hasattr(self, '_heartbeat_timer'):
            self._heartbeat_timer = QTimer(self)
            self._heartbeat_timer.start(100)
            
        self.stop_playback(True)
        if not os.path.exists(path):
            self.show_empty(AppContext.tr("msg_error_file"))
            return
            
        self.current_path = path
        ext = os.path.splitext(path)[1].lower()
        self.update_meta(path)
        
        if ext in ['.jpg', '.jpeg', '.png', '.bmp']: self.setup_static_image(path)
        elif ext in ['.gif', '.webp']: self.setup_animated(path)
        elif ext in VIDEO_EXTS or ext in ['.mp3', '.wav', '.ogg', '.flac', '.m4a', '.wma', '.aac']: 
            self.setup_video(path)
        else:
            self.show_empty("...")

    def toggle_playback(self):
        if self.current_media_type == 'movie' and self.movie:
            if self.movie.state() == QMovie.MovieState.Running: self.movie.setPaused(True)
            else: self.movie.start()
        elif self.current_media_type in ['video', 'audio'] and self.player:
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState: self.player.pause()
            else: self.player.play()

    def _on_media_status_changed(self, status):
        pass

    def _on_player_state_changed(self, state):
        is_playing = (state == QMediaPlayer.PlaybackState.PlayingState)
        if is_playing and hasattr(self, '_heartbeat_timer'):
            self._heartbeat_timer.stop()
        self.video_controls.set_playing_state(is_playing)
        self.update_segment_indicator()

    def _fit_video_size_changed(self, size):
        if self.video_item:
            self.video_item.setSize(size)
        QTimer.singleShot(50, self.reset_view)
            
    def _on_movie_frame(self):
        if not self.movie: return
        pix = self.movie.currentPixmap()
        if not pix.isNull():
             self.pixmap_item.setPixmap(pix)
             if self.movie.frameCount() > 0 and self.movie.currentFrameNumber() == 0:
                 QTimer.singleShot(10, self.reset_view)

    def reset_view(self):
        self.view.resetTransform()
        self.view.horizontalScrollBar().setValue(0)
        self.view.verticalScrollBar().setValue(0)
        
        active_item = None
        if self.video_item.isVisible():
            active_item = self.video_item
        elif self.pixmap_item.isVisible() and not self.pixmap_item.pixmap().isNull(): 
            active_item = self.pixmap_item
        elif self.text_item.isVisible():
            active_item = self.text_item
            
        if not active_item: return

        active_item.setPos(0, 0)
        if hasattr(active_item, 'setTransform'):
            from PyQt6.QtGui import QTransform
            active_item.setTransform(QTransform())

        item_rect = active_item.boundingRect()
        if item_rect.width() <= 0 or item_rect.height() <= 0: return
        
        self.scene.setSceneRect(item_rect)
        viewport_rect = self.view.viewport().rect()
        
        if viewport_rect.width() <= 10 or viewport_rect.height() <= 10:
             QTimer.singleShot(100, self.reset_view)
             return
             
        if active_item == self.video_item:
            self.view.fitInView(active_item, Qt.AspectRatioMode.KeepAspectRatio)
            self.view.centerOn(active_item)
            return

        width_diff = item_rect.width() - viewport_rect.width()
        height_diff = item_rect.height() - viewport_rect.height()
        
        if width_diff > 0 or height_diff > 0:
            self.view.fitInView(active_item, Qt.AspectRatioMode.KeepAspectRatio)
        self.view.centerOn(active_item)

    def update_meta(self, path):
        try:
            stats = os.stat(path)
            mtime = datetime.datetime.fromtimestamp(stats.st_mtime)
            date_str = mtime.strftime("%Y-%m-%d %H:%M:%S")
            try:
                ctime = datetime.datetime.fromtimestamp(stats.st_ctime)
                create_str = ctime.strftime("%Y-%m-%d %H:%M:%S")
            except: create_str = "N/A"
            
            data = [
                (AppContext.tr("cln_meta_name"), os.path.basename(path)),
                (AppContext.tr("cln_meta_folder"), os.path.dirname(path)),
                (AppContext.tr("cln_meta_size"), format_size(stats.st_size)),
                (AppContext.tr("cln_meta_created"), create_str),
                (AppContext.tr("cln_meta_date"), date_str)
            ]
            ext = os.path.splitext(path)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.webp', '.gif']:
                reader = QImageReader(path)
                sz = reader.size()
                if sz.isValid(): data.append((AppContext.tr("cln_meta_res"), f"{sz.width()} x {sz.height()}"))

            self.meta_table.setRowCount(len(data))
            for i, (k, v) in enumerate(data):
                key_item = QTableWidgetItem(k + ":")
                key_item.setForeground(QColor("#888"))
                key_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
                val_item = QTableWidgetItem(v)
                val_item.setForeground(QColor("#fff"))
                val_item.setToolTip(v)
                self.meta_table.setItem(i, 0, key_item)
                self.meta_table.setItem(i, 1, val_item)
            self.meta_table.resizeRowsToContents()
        except: pass

    def toggle_info_panel(self, checked):
        self.meta_table.setVisible(checked)
        base_text = AppContext.tr("cln_meta_header").upper()
        if checked:
            self.btn_toggle_info.setText(base_text + " ▼")
            total = self.splitter.height()
            self.splitter.setSizes([total * 2 // 3, total // 3])
        else:
            self.btn_toggle_info.setText(base_text + " ▲")
            self.splitter.setSizes([self.splitter.height() - 26, 26])

    def stop_playback(self, full_reset=False):
        if self.player: self.player.pause()
        if self.movie: self.movie.stop()
        self.video_controls.set_playing_state(False)
        if full_reset: self._clear_media()

    def open_current_file(self):
        if self.current_path and os.path.exists(self.current_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.current_path))

    def open_containing_folder(self):
        if self.current_path and os.path.exists(self.current_path):
            from utils_common import reveal_in_explorer
            reveal_in_explorer(self.current_path)
