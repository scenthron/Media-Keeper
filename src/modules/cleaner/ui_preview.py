
import os
from utils_extensions import VIDEO_EXTS, AUDIO_EXTS, IMAGE_EXTS, get_filtered_exts
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
from modules.sorter.ui_player import VideoPlayerControls, TimeOverlayWidget, SegmentIndicatorWidget
from modules.cleaner.ui_view import ClickableGraphicsView
from modules.sorter.logic_player import SmartPreviewManager

class CleanerPreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #000; border: none;")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0,0,0,0)
        self.layout.setSpacing(0)
        
        # State for Video Settings
        # Use AppContext directly instead of local variables
        self.current_media_type = None
        self.current_path = None
        
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setHandleWidth(4)
        self.splitter.setStyleSheet("QSplitter::handle { background-color: #333; border-top: 1px solid #444; border-bottom: 1px solid #444; } QSplitter::handle:hover { background-color: #3b82f6; }")
        
        self.media_container = QWidget()
        self.media_layout = QVBoxLayout(self.media_container)
        self.media_layout.setContentsMargins(0,0,0,0)
        self.media_layout.setSpacing(0)
        
        self.view = None
        self.scene = None
        self.video_item = None
        self.pixmap_item = None
        self.text_item = None
        
        # Controls
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
        
        
        # Override mouse move for hover
        
        
        
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
        
        self.player = None
        self.audio_output = None
        
        # Connect Controls Signals
        self.video_controls.play_pause_clicked.connect(self.toggle_playback)
        
        
        self.video_controls.seek_drag_start.connect(self._on_scrub_start)
        self.video_controls.seek_drag_stop.connect(self._on_scrub_stop)
        self.video_controls.volume_changed.connect(self.change_volume)
        
        # Settings Signals
        self.video_controls.speed_changed.connect(self._on_speed_changed)
        self.video_controls.loop_toggled.connect(self._on_loop_toggled)
        self.video_controls.speed_toggled.connect(self._on_speed_toggled)
        
        self.smart_preview_mgr = None
        
        # Time Overlay
        self.time_overlay = TimeOverlayWidget(self.media_container)
        self.time_overlay.hide()

        
        
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
        if event is not None:
            super().resizeEvent(event)
        QTimer.singleShot(10, self.reset_view)
        
        # Position the overlay in bottom right corner of media_container
        if hasattr(self, 'time_overlay') and self.time_overlay.isVisible():
            padding = 10
            controls_h = self.video_controls.height() if self.video_controls.isVisible() else 0
            x = self.media_container.width() - self.time_overlay.width() - padding
            y = self.media_container.height() - controls_h - self.time_overlay.height() - padding
            self.time_overlay.move(x, y)
            
        if hasattr(self, 'btn_seg_prev') and self.btn_seg_prev:
            y_center = (self.media_container.height() - self.btn_seg_prev.height()) // 2
            self.btn_seg_prev.move(20, y_center)
            self.btn_seg_next.move(self.media_container.width() - self.btn_seg_next.width() - 20, y_center)
            self.btn_seg_prev.raise_()
            self.btn_seg_next.raise_()
        if hasattr(self, 'segment_indicator'):
            self.segment_indicator.move(10, 10)

    def _on_media_duration_changed(self, dur):
        if hasattr(self, 'smart_preview_mgr'):
            self.smart_preview_mgr.start_video(dur)
            
    def _on_scrub_start(self):
        from PyQt6.QtMultimedia import QMediaPlayer
        self._was_playing_before_scrub = (self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
        self.player.pause()
        if hasattr(self, 'smart_preview_mgr'):
            self.smart_preview_mgr.set_user_paused(True)

    def _on_scrub_stop(self):
        if getattr(self, '_was_playing_before_scrub', False):
            self.player.play()
            if hasattr(self, 'smart_preview_mgr'):
                self.smart_preview_mgr.set_user_paused(False)
            
    def _on_seg_prev(self):
        if hasattr(self, 'smart_preview_mgr'):
            self.smart_preview_mgr.skip_prev()
            
    def _on_seg_next(self):
        if hasattr(self, 'smart_preview_mgr'):
            self.smart_preview_mgr.skip_next()
            
    def _on_segment_indicator_clicked(self):
        AppContext.session_segment_view = not AppContext.session_segment_view
        if hasattr(self, 'smart_preview_mgr'):
            self.smart_preview_mgr.set_active(AppContext.session_segment_view)
        self.update_segment_indicator()
            
    def update_segment_indicator(self):
        if not hasattr(self, 'smart_preview_mgr') or not hasattr(self, 'segment_indicator'):
            return
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
        QGraphicsView.mouseMoveEvent(self.view, event)
        segment_active = False
        if hasattr(self, 'smart_preview_mgr'):
            segment_active = self.smart_preview_mgr.active and self.smart_preview_mgr.num_segments > 0
            
        if segment_active and self.current_media_type == 'video':
            pos = event.pos()
            if pos.x() < self.view.width() * 0.3:
                self.btn_seg_prev.show()
                self.btn_seg_next.hide()
            elif pos.x() > self.view.width() * 0.7:
                self.btn_seg_next.show()
                self.btn_seg_prev.hide()
            else:
                self.btn_seg_prev.hide()
                self.btn_seg_next.hide()
        else:
            self.btn_seg_prev.hide()
            self.btn_seg_next.hide()

    def _view_leave_event(self, event):
        QGraphicsView.leaveEvent(self.view, event)
        if hasattr(self, 'btn_seg_prev'): self.btn_seg_prev.hide()
        if hasattr(self, 'btn_seg_next'): self.btn_seg_next.hide()

    def _update_overlay_time(self, pos):
        dur = self.player.duration()
        self.time_overlay.set_time(pos, dur)

    def _update_overlay_duration(self, dur):
        pos = self.player.position()
        self.time_overlay.set_time(pos, dur)
        # Position may need to be updated since size changed
        self.resizeEvent(None)
        
        # Update meta table with duration if not present
        dur_sec = dur // 1000
        if dur_sec > 0:
            dur_str = f"{dur_sec // 60:02d}:{dur_sec % 60:02d}"
            # Check if duration row exists
            found = False
            for row in range(self.meta_table.rowCount()):
                if self.meta_table.item(row, 0) and self.meta_table.item(row, 0).text() == "Продолжительность:":
                    self.meta_table.item(row, 1).setText(dur_str)
                    found = True
                    break
            if not found:
                row = self.meta_table.rowCount()
                self.meta_table.insertRow(row)
                key_item = QTableWidgetItem("Продолжительность:")
                key_item.setForeground(QColor("#888"))
                key_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
                val_item = QTableWidgetItem(dur_str)
                val_item.setForeground(QColor("#fff"))
                self.meta_table.setItem(row, 0, key_item)
                self.meta_table.setItem(row, 1, val_item)

    def show_empty(self, msg):
        self.stop_playback(True)
        self._create_view()
        self.current_media_type = None
        self.current_path = None
        self.view.resetTransform()
        self.pixmap_item.hide()
        self.video_item.hide()
        self.video_controls.hide()
        self.time_overlay.hide()
        
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

    def _clear_media(self):
        if hasattr(self, 'player') and self.player:
            try:
                self.player.stop()
                self.player.positionChanged.disconnect()
                self.player.durationChanged.disconnect()
                self.player.playbackStateChanged.disconnect()
                self.player.mediaStatusChanged.disconnect()
                self.video_controls.seek_requested.disconnect()
                self.video_controls.seek_moved.disconnect()
            except Exception: pass
            self.player.deleteLater()
            self.player = None
            
        if hasattr(self, 'audio_output') and self.audio_output:
            self.audio_output.deleteLater()
            self.audio_output = None
            
        if hasattr(self, 'movie') and self.movie:
            self.movie.stop()
            self.movie = None
            
        if hasattr(self, 'view') and self.view:
            self.media_layout.removeWidget(self.view)
            self.view.deleteLater()
            self.view = None
            self.scene = None
            self.video_item = None
            self.pixmap_item = None
            self.text_item = None
            
        self.smart_preview_mgr = None

    def _create_view(self):
        self.scene = QGraphicsScene(self)
        self.view = ClickableGraphicsView(self.scene)
        self.view.clicked.connect(self.toggle_playback)
        self.view.double_clicked.connect(self.open_current_file)
        self.view.middle_clicked.connect(self.open_containing_folder)
        self.view.right_clicked.connect(self.reset_view)
        
        
        
        
        from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem
        self.video_item = QGraphicsVideoItem()
        self.scene.addItem(self.video_item)
        self.video_item.nativeSizeChanged.connect(self._fit_video_size_changed)
        self.video_item.hide()
        
        from PyQt6.QtGui import QPixmap, QColor, QFont
        self.pixmap_item = self.scene.addPixmap(QPixmap())
        self.pixmap_item.hide()
        
        self.text_item = QGraphicsTextItem()
        self.text_item.setDefaultTextColor(QColor("#555555"))
        self.text_item.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.scene.addItem(self.text_item)
        self.text_item.hide()
        
        self.media_layout.insertWidget(0, self.view)

    def stop_playback(self, full_reset=False):
        if hasattr(self, 'player') and self.player: self.player.pause()
        if hasattr(self, 'movie') and self.movie: self.movie.stop()
        self.video_controls.set_playing_state(False)
        if full_reset: self._clear_media()

    def toggle_playback(self):
        if self.current_media_type == 'movie' and self.movie:
            if self.movie.state() == QMovie.MovieState.Running: self.movie.setPaused(True)
            else: self.movie.start()
        elif self.current_media_type == 'video':
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState: self.player.pause()
            else: self.player.play()

    def _on_media_status_changed(self, status):
        if status in (QMediaPlayer.MediaStatus.BufferedMedia, QMediaPlayer.MediaStatus.LoadedMedia):
            if self.video_item.isVisible() and self.video_item.nativeSize().isValid():
                sz = self.video_item.nativeSize()
                self._fit_video_size_changed(sz)

    def _on_player_state_changed(self, state):
        is_playing = (state == QMediaPlayer.PlaybackState.PlayingState)
        self.video_controls.set_playing_state(is_playing)
        if hasattr(self, 'update_segment_indicator'):
            self.update_segment_indicator()

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

        # Reset item position and transform to prevent offset bugs
        active_item.setPos(0, 0)
        if hasattr(active_item, 'setTransform'):
            from PyQt6.QtGui import QTransform
            active_item.setTransform(QTransform())

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
            self.view.fitInView(active_item, Qt.AspectRatioMode.KeepAspectRatio)
            self.view.centerOn(active_item)
            return

        # If Image/Text -> Fit only if larger than viewport
        width_diff = item_rect.width() - viewport_rect.width()
        height_diff = item_rect.height() - viewport_rect.height()
        
        if width_diff > 0 or height_diff > 0:
            self.view.fitInView(active_item, Qt.AspectRatioMode.KeepAspectRatio)
            self.view.centerOn(active_item)
        else:
            self.view.centerOn(active_item)

    def change_volume(self, val):
        self.audio_output.setVolume(val / 100.0)

    # --- Settings Slots ---
    def _on_speed_toggled(self):
        if self.current_media_type == 'video':
            AppContext.session_video_speed_active = not getattr(AppContext, "session_video_speed_active", False)
            active = AppContext.session_video_speed_active
        else:
            AppContext.session_audio_speed_active = not getattr(AppContext, "session_audio_speed_active", False)
            active = AppContext.session_audio_speed_active
            
        speed = AppContext.session_fast_speed_val if active else 1.0
        self.player.setPlaybackRate(speed)
        self.video_controls.update_speed_button(AppContext.session_fast_speed_val, active)

    def _on_speed_changed(self, speed_val):
        AppContext.session_fast_speed_val = float(speed_val)
        if self.current_media_type == 'video':
            AppContext.session_video_speed_active = True
        else:
            AppContext.session_audio_speed_active = True
            
        self.player.setPlaybackRate(speed_val)
        self.video_controls.update_speed_button(AppContext.session_fast_speed_val, True)

    def _on_loop_toggled(self, is_loop):
        self.player.setLoops(QMediaPlayer.Loops.Infinite if is_loop else QMediaPlayer.Loops.Once)
        AppContext.session_loop = is_loop


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
