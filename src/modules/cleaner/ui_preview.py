
import os
import datetime
import subprocess
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, QSplitter, 
    QTableWidget, QTableWidgetItem, QHeaderView, QGraphicsView, QGraphicsScene,
    QGraphicsTextItem
)
from PyQt6.QtCore import Qt, QUrl, QRectF, QPointF, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QImageReader, QMovie, QColor, QPainter, QMouseEvent, QFont, QDesktopServices, QWheelEvent, QKeyEvent
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem

from config import AppContext, VIEWER_DESIGN
from utils_common import format_size
from modules.sorter.ui_player import VideoPlayerControls 
from modules.cleaner.ui_view import ClickableGraphicsView

class CleanerPreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #000; border: none;")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0,0,0,0)
        self.layout.setSpacing(0)
        
        # State for Video Settings
        from config import AppContext
        self.session_video_speed = AppContext.session_video_speed
        self.session_loop = AppContext.session_loop
        self.session_apply_all = AppContext.session_all_videos_active
        self.current_media_type = None
        self.current_path = None
        
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setHandleWidth(4)
        self.splitter.setStyleSheet("QSplitter::handle { background-color: #333; border-top: 1px solid #444; border-bottom: 1px solid #444; } QSplitter::handle:hover { background-color: #3b82f6; }")
        
        self.media_container = QWidget()
        self.media_layout = QVBoxLayout(self.media_container)
        self.media_layout.setContentsMargins(0,0,0,0)
        self.media_layout.setSpacing(0)
        
        self.scene = QGraphicsScene(self)
        self.view = ClickableGraphicsView(self.scene)
        
        # Connect Signals
        self.view.clicked.connect(self.toggle_playback)
        self.view.double_clicked.connect(self.open_current_file)
        self.view.middle_clicked.connect(self.open_containing_folder)
        self.view.right_clicked.connect(self.reset_view)
        
        self.video_item = QGraphicsVideoItem()
        self.scene.addItem(self.video_item)
        self.video_item.hide() 
        self.pixmap_item = self.scene.addPixmap(QPixmap())
        self.pixmap_item.hide() 
        self.text_item = QGraphicsTextItem()
        self.text_item.setDefaultTextColor(QColor("#555555"))
        # Using a slightly smaller font for hints
        self.text_item.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.scene.addItem(self.text_item)
        self.text_item.hide()
        
        self.media_layout.addWidget(self.view)
        
        # Controls
        self.video_controls = VideoPlayerControls()
        self.video_controls.hide()
        self.media_layout.addWidget(self.video_controls)
        
        self.splitter.addWidget(self.media_container)
        
        # Meta Table Panel
        self.meta_wrapper = QWidget()
        self.meta_wrapper.hide() 
        mw_layout = QVBoxLayout(self.meta_wrapper)
        mw_layout.setContentsMargins(0,0,0,0)
        mw_layout.setSpacing(0)
        
        # Info Header Button (Toggle)
        self.btn_toggle_info = QPushButton(AppContext.tr("cln_meta_header").upper() + " ▲")
        self.btn_toggle_info.setCheckable(True)
        self.btn_toggle_info.setFixedHeight(26)
        self.btn_toggle_info.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_info.setStyleSheet("""
            QPushButton { 
                background-color: #2b2b2b; color: #888; border: none; 
                border-bottom: 2px solid #333; font-size: 10px; font-weight: bold; 
                text-align: left; padding-left: 10px; 
            }
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
        
        self.meta_table.hide() # Collapsed initially
        mw_layout.addWidget(self.meta_table)
        self.splitter.addWidget(self.meta_wrapper)
        
        self.layout.addWidget(self.splitter)
        self.splitter.setSizes([800, 26]) # Show only header initially
        
        # Player Setup
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_item)
        self.audio_output.setVolume(0.05)
        
        # Connect Controls Signals
        self.video_controls.play_pause_clicked.connect(self.toggle_playback)
        self.video_controls.seek_requested.connect(self.player.setPosition)
        self.video_controls.seek_moved.connect(self.player.setPosition)
        self.video_controls.seek_drag_start.connect(self.player.pause)
        self.video_controls.seek_drag_stop.connect(self.player.play)
        self.video_controls.volume_changed.connect(self.change_volume)
        
        # Settings Signals
        self.video_controls.speed_changed.connect(self._on_speed_changed)
        self.video_controls.loop_toggled.connect(self._on_loop_toggled)
        self.video_controls.apply_all_toggled.connect(self._on_apply_all_toggled)
        
        self.player.positionChanged.connect(self.video_controls.update_position)
        self.player.durationChanged.connect(self.video_controls.update_duration)
        self.player.playbackStateChanged.connect(self._on_player_state_changed)
        self.video_item.nativeSizeChanged.connect(self._fit_video_size_changed)
        
        self.movie = None
        self.show_empty("...")

    def update_ui_text(self):
        self.lbl_meta_header.setText(AppContext.tr("cln_meta_header") + ":")
        
        # If showing text (empty/hint/error), refresh it
        if self.text_item.isVisible():
            if not self.current_path:
                self.text_item.setPlainText(AppContext.tr("preview_hint"))
            else:
                # If error state, we need to know which error.
                # For now, re-loading will fix it if it's generic error
                # But simple way: Check text content against old keys? 
                # Better: just update meta if file exists.
                pass

        if self.current_path:
             self.update_meta(self.current_path)
             
        self.video_controls.update_ui_text()

    def toggle_info_panel(self, checked):
        self.meta_wrapper.setVisible(checked)
        if checked:
            total = self.splitter.height()
            self.splitter.setSizes([total * 2 // 3, total // 3])
        else:
            self.splitter.setSizes([800, 0])

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(10, self.reset_view)

    def show_empty(self, msg):
        self.stop_playback(True)
        self.current_media_type = None
        self.current_path = None
        self.view.resetTransform()
        self.pixmap_item.hide()
        self.video_item.hide()
        self.video_controls.hide()
        
        # Reset text item styling to default hint style
        self.text_item.setDefaultTextColor(QColor("#555555"))
        self.text_item.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.text_item.setTextWidth(-1)
        
        if msg == "..." or not msg:
            # SHOW HINT TEXT
            hint = AppContext.tr("preview_hint")
            self.text_item.setPlainText(hint)
            self.text_item.show()
            self.reset_view()
        else:
            # Show actual message
            self.text_item.setPlainText(msg)
            self.text_item.show()
            self.reset_view()
            
        self.meta_table.clear()
        self.meta_table.setRowCount(0)

    def stop_playback(self, full_reset=False):
        self.player.stop()
        self.player.setSource(QUrl())
        if self.movie:
            self.movie.stop()
            self.movie = None
        self.video_controls.set_playing_state(False)

    def pause_playback(self):
        logging.info(f"CleanerPreviewWidget: Пауза воспроизведения. Файл: {self.current_path}, тип: {self.current_media_type}")
        if self.current_media_type == 'movie' and self.movie:
            self.movie.setPaused(True)
        elif self.current_media_type == 'video':
            self.player.pause()

    def load_file(self, path):
        self.stop_playback()
        if not os.path.exists(path):
            self.show_empty(AppContext.tr("msg_error_file"))
            return
        self.current_path = path
        ext = os.path.splitext(path)[1].lower()
        self.update_meta(path)
        if ext in ['.jpg', '.jpeg', '.png', '.bmp']: self.setup_static_image(path)
        elif ext in ['.gif', '.webp']: self.setup_animated(path)
        elif ext in ['.mp4', '.avi', '.mkv', '.mov', '.webm', '.mp3', '.wav', '.ogg', '.wmv', '.flv', '.flac', '.m4a', '.wma', '.aac', '.mpg', '.mpeg', '.m4v']: self.setup_video(path)
        else:
            self.current_media_type = None
            self.video_item.hide()
            self.pixmap_item.hide()
            self.video_controls.hide()
            self.text_item.setPlainText(AppContext.tr("cln_prev_no_preview"))
            self.text_item.show()
            self.reset_view()

    def setup_static_image(self, path):
        self.current_media_type = 'image'
        self.video_controls.hide()
        self.video_item.hide()
        self.text_item.hide()
        pix = QPixmap(path)
        if pix.isNull():
            self.text_item.setPlainText(AppContext.tr("cln_prev_img_err"))
            self.text_item.show()
            return
        self.pixmap_item.setPixmap(pix)
        self.pixmap_item.show()
        # Delay to ensure fit happens after layout update
        QTimer.singleShot(50, self.reset_view)

    def setup_animated(self, path):
        self.current_media_type = 'movie'
        self.video_item.hide()
        self.video_controls.hide()
        self.text_item.hide()
        self.movie = QMovie(path)
        self.movie.setCacheMode(QMovie.CacheMode.CacheAll)
        self.movie.jumpToFrame(0)
        self.pixmap_item.setPos(0, 0)
        self.movie.frameChanged.connect(self._on_movie_frame)
        self._on_movie_frame() 
        self.movie.start()
        self.pixmap_item.show()
        QTimer.singleShot(50, self.reset_view)

    def _on_movie_frame(self):
        if not self.movie: return
        pix = self.movie.currentPixmap()
        if not pix.isNull():
             self.pixmap_item.setPixmap(pix)
             # Center on first frame load
             if self.movie.frameCount() > 0 and self.movie.currentFrameNumber() == 0:
                 QTimer.singleShot(10, self.reset_view)

    def setup_video(self, path):
        self.current_media_type = 'video'
        self.pixmap_item.hide()
        
        ext = os.path.splitext(path)[1].lower()
        is_audio = ext in ['.mp3', '.wav', '.ogg', '.flac', '.m4a', '.wma', '.aac']
        
        if is_audio:
            self.video_item.hide()
            track_name = os.path.splitext(os.path.basename(path))[0]
            # Styled text for audio files matching Sorter popup
            html_text = f"<div style='text-align: center; line-height: 1.4; color: #3b82f6;'>🎵<br>{track_name}</div>"
            self.text_item.setHtml(html_text)
            self.text_item.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
            self.text_item.setTextWidth(400) # Give width for HTML alignment to work
            self.text_item.show()
            QTimer.singleShot(50, self.reset_view)
        else:
            self.text_item.hide()
            self.video_item.show()
            
        self.video_controls.show()
        self.video_controls.seeker.setEnabled(True)
        self.video_controls.set_playing_state(False)
        
        self.player.setSource(QUrl.fromLocalFile(path))
        
        # Apply Session Settings
        if self.session_apply_all:
            speed = self.session_video_speed
        else:
            speed = 1.0
            
        loop = self.session_loop
        apply_all = self.session_apply_all
        
        # Sync UI controls
        self.video_controls.set_popup_values(speed, loop, apply_all, is_video=not is_audio)
        
        # Apply to Player
        self.player.setPlaybackRate(speed)
        self.player.setLoops(QMediaPlayer.Loops.Infinite if loop else QMediaPlayer.Loops.Once)
        
        self.player.play() 

    def toggle_playback(self):
        if self.current_media_type == 'movie' and self.movie:
            if self.movie.state() == QMovie.MovieState.Running: self.movie.setPaused(True)
            else: self.movie.start()
        elif self.current_media_type == 'video':
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState: self.player.pause()
            else: self.player.play()

    def _on_player_state_changed(self, state):
        is_playing = (state == QMediaPlayer.PlaybackState.PlayingState)
        self.video_controls.set_playing_state(is_playing)

    def _fit_video_size_changed(self, size):
        self.video_item.setSize(size)
        QTimer.singleShot(50, self.reset_view)

    def reset_view(self):
        """
        Resets zoom and pans to center content within the viewport.
        Ensures content occupies available space correctly.
        """
        self.view.resetTransform() # 1:1 Scale
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

        # 1. Update Scene Rect to match Item exactly
        item_rect = active_item.boundingRect()
        if item_rect.width() <= 0 or item_rect.height() <= 0: return
        
        self.scene.setSceneRect(item_rect)
        
        # 2. Fit logic
        viewport_rect = self.view.viewport().rect()
        
        # SAFETY CHECK: If viewport is not ready, retry later
        if viewport_rect.width() <= 10 or viewport_rect.height() <= 10:
             QTimer.singleShot(100, self.reset_view)
             return
        
        # If content is video -> Always Fit
        if active_item == self.video_item:
            self.view.fitInView(item_rect, Qt.AspectRatioMode.KeepAspectRatio)
            self.view.centerOn(item_rect.center())
            return

        # If Image/Text -> Fit only if larger than viewport
        width_diff = item_rect.width() - viewport_rect.width()
        height_diff = item_rect.height() - viewport_rect.height()
        
        if width_diff > 0 or height_diff > 0:
            self.view.fitInView(item_rect, Qt.AspectRatioMode.KeepAspectRatio)
        else:
            self.view.centerOn(item_rect.center())

    def change_volume(self, val):
        self.audio_output.setVolume(val / 100.0)

    # --- Settings Slots ---
    def _on_speed_changed(self, speed):
        self.player.setPlaybackRate(speed)
        if self.current_media_type == 'video':
            self.session_video_speed = speed
            from config import AppContext
            AppContext.session_video_speed = speed

    def _on_loop_toggled(self, enabled):
        self.session_loop = enabled
        self.player.setLoops(QMediaPlayer.Loops.Infinite if enabled else QMediaPlayer.Loops.Once)
        from config import AppContext
        AppContext.session_loop = enabled
        AppContext.save_media_settings()

    def _on_apply_all_toggled(self, enabled):
        self.session_apply_all = enabled
        from config import AppContext
        AppContext.session_all_videos_active = enabled
        AppContext.save_media_settings()

    # --- Mouse Actions ---
    def open_current_file(self):
        if self.current_path and os.path.exists(self.current_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.current_path))

    def open_containing_folder(self):
        if not self.current_path: return
        from utils_common import reveal_in_explorer
        reveal_in_explorer(self.current_path)
    def update_meta(self, path):
        self.meta_table.setRowCount(0)
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
        # Header (btn_toggle_info) is always visible in meta_wrapper 
        # But we toggle the Visibility of meta_table to "expand" the panel
        self.meta_table.setVisible(checked)
        
        base_text = AppContext.tr("cln_meta_header").upper()
        if checked:
            self.btn_toggle_info.setText(base_text + " ▼")
            total = self.splitter.height()
            self.splitter.setSizes([total * 2 // 3, total // 3])
        else:
            self.btn_toggle_info.setText(base_text + " ▲")
            self.splitter.setSizes([self.splitter.height() - 26, 26])

    def update_ui_text(self):
        base_text = AppContext.tr("cln_meta_header").upper()
        arrow = " ▼" if self.btn_toggle_info.isChecked() else " ▲"
        self.btn_toggle_info.setText(base_text + arrow)
        
        # Original update_ui_text logic
        if self.text_item.isVisible():
            if not self.current_path:
                self.text_item.setPlainText(AppContext.tr("preview_hint"))
        
        if self.current_path:
             self.update_meta(self.current_path)
             
        self.video_controls.update_ui_text()
