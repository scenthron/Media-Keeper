from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QSplitter, 
    QTableWidget, QTableWidgetItem, QHeaderView, QGraphicsView, QGraphicsScene,
    QGraphicsTextItem
)
from modules.cleaner.ui_view import ClickableGraphicsView
from PyQt6.QtCore import Qt, QUrl, QRectF, pyqtSignal, QTimer, QEvent
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
        
        self.lbl_center_text = QLabel(self.view)
        self.lbl_center_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_center_text.setWordWrap(True)
        self.lbl_center_text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.lbl_center_text.hide()
        
        self.center_layout = QVBoxLayout(self.view)
        self.center_layout.setContentsMargins(20, 20, 20, 20)
        self.center_layout.addWidget(self.lbl_center_text, alignment=Qt.AlignmentFlag.AlignCenter)
        
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
        self.media_container.installEventFilter(self)
        
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
        self._video_output_set = False
        
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
        
        if self.lbl_center_text.isVisible() and not self.current_path:
            self.lbl_center_text.setText(AppContext.tr("preview_hint"))
        
        if self.current_path:
             self.update_meta(self.current_path)
             
        self.video_controls.update_ui_text()

    def resizeEvent(self, event):
        if event is not None:
            super().resizeEvent(event)
            
        def _delayed_resize():
            self.reset_view()
            self._position_ai_scores()
            self.update_overlay_positions()
            
            y_center = (self.media_container.height() - self.btn_seg_prev.height()) // 2
            self.btn_seg_prev.move(20, y_center)
            self.btn_seg_next.move(self.media_container.width() - self.btn_seg_next.width() - 20, y_center)
            
        QTimer.singleShot(10, _delayed_resize)
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

    def update_overlay_positions(self):
        if not hasattr(self, 'view'): return
        
        if hasattr(self, 'lbl_center_text') and self.lbl_center_text.isVisible():
            pass # Now handled by QVBoxLayout automatically
                
        if self.time_overlay and self.time_overlay.isVisible():
            padding = 10
            controls_h = self.video_controls.height() if self.video_controls.isVisible() else 0
            x = self.media_container.width() - self.time_overlay.width() - padding
            y = self.media_container.height() - controls_h - self.time_overlay.height() - padding
            self.time_overlay.move(x, y)

    def change_volume(self, val):
        self.audio_output.setVolume(val / 100.0)

    def _do_play(self):
        if self.current_media_type in ['video', 'audio'] and hasattr(self, 'player') and self.player:
            if self.isVisible():
                self.player.play()

    def _clear_media(self):
        if hasattr(self, '_play_timer'):
            self._play_timer.stop()
        if self.player:
            self.player.stop()
            from PyQt6.QtCore import QUrl
            self.player.setSource(QUrl())
            self.player.setVideoOutput(None)
            self._video_output_set = False
        if self.movie:
            self.movie.stop()
            self.movie = None
        self.smart_preview_mgr = None
        if hasattr(self, 'pixmap_item'): self.pixmap_item.hide()
        if hasattr(self, 'video_item'): self.video_item.hide()
        if hasattr(self, 'lbl_center_text'): self.lbl_center_text.hide()

    def show_empty(self, msg):
        self.stop_playback(True)
        self.clear_faces()
        self.current_media_type = None
        self.current_path = None
        self.view.resetTransform()
        self.video_controls.hide()
        self.time_overlay.hide()
        
        self.lbl_center_text.setStyleSheet("color: #555555;")
        self.lbl_center_text.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        
        if self.current_path:
            msg = AppContext.tr("preview_hint") + f"\n\n({self.current_path})"
            self.lbl_center_text.setText(msg)
        else:
            self.lbl_center_text.setText(AppContext.tr("preview_hint"))
            
        self.lbl_center_text.show()
        self.update_overlay_positions()
        self.reset_view()
        self.meta_table.clear()
        self.meta_table.setRowCount(0)
        self.set_ai_info(None)

    def set_ai_info(self, tag_scores: dict, group_name: str = None):
        if not hasattr(self, 'lbl_ai_scores'):
            self.lbl_ai_scores = QLabel(self.media_container)
            self.lbl_ai_scores.setWordWrap(True)
            self.lbl_ai_scores.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lbl_ai_scores.setStyleSheet("background-color: rgba(0, 0, 0, 180); color: white; border-radius: 8px; padding: 6px 12px; font-weight: bold; font-size: 13px;")
            self.lbl_ai_scores.hide()
            
        if not tag_scores:
            self.lbl_ai_scores.setText("")
            self.lbl_ai_scores.hide()
            self._has_ai_scores = False
            return
            
        try:
            # Sort scores descending
            sorted_items = sorted(tag_scores.items(), key=lambda x: x[1], reverse=True)
            parts = []
            for k, v in sorted_items:
                # Colorize positive and negative scores differently
                color = "#ef4444" if k.startswith("-") else "#22c55e"
                # Заменяем обычные пробелы на неразрывные, чтобы блок не разрывался
                k_safe = k.replace(" ", "&nbsp;")
                parts.append(f"<span style='white-space: nowrap;'><span style='color: #ccc;'>{k_safe}:</span>&nbsp;<span style='color: {color};'>{v}%</span></span>")
            
            text = " | ".join(parts)
            
            # Добавляем название группы, если это именованный мультитег
            if group_name and group_name != "Текст" and not group_name.startswith("Группа "):
                text = f"<div style='text-align: center;'><b style='color: #f59e0b;'>{group_name}</b><br>({text})</div>"
            else:
                text = f"<div style='text-align: center;'>{text}</div>"
                
            self.lbl_ai_scores.setText(text)
            self.lbl_ai_scores.show()
            self._position_ai_scores()
            self._has_ai_scores = True
        except Exception as e:
            import logging
            logging.error(f"Error rendering AI scores: {e}")
            self.lbl_ai_scores.hide()
            self._has_ai_scores = False

    def _position_ai_scores(self):
        if hasattr(self, 'lbl_ai_scores') and self.lbl_ai_scores.text():
            max_w = self.media_container.width() - 40
            self.lbl_ai_scores.setMaximumWidth(max_w)
            self.lbl_ai_scores.adjustSize()
            x = (self.media_container.width() - self.lbl_ai_scores.width()) // 2
            self.lbl_ai_scores.move(x, 15)

    def eventFilter(self, obj, event):
        if obj == self.media_container:
            if event.type() == QEvent.Type.Enter:
                if getattr(self, '_has_ai_scores', False) and hasattr(self, 'lbl_ai_scores'):
                    self.lbl_ai_scores.show()
            elif event.type() == QEvent.Type.Leave:
                if hasattr(self, 'lbl_ai_scores'):
                    self.lbl_ai_scores.hide()
        return super().eventFilter(obj, event)

    def setup_static_image(self, path):
        self._clear_media()
        self.current_media_type = 'image'
        self.video_controls.hide()
        self.time_overlay.hide()
        
        try:
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            img = reader.read()
            
            # Fallback for AVIF or other unsupported formats
            if img.isNull() and os.path.splitext(path)[1].lower() == '.avif':
                try:
                    from PIL import Image
                    import pillow_avif
                    from PyQt6.QtGui import QImage
                    with Image.open(path) as pil_img:
                        if pil_img.mode != 'RGB':
                            pil_img = pil_img.convert('RGB')
                        data = pil_img.tobytes("raw", "RGB")
                        img = QImage(data, pil_img.width, pil_img.height, pil_img.width * 3, QImage.Format.Format_RGB888).copy()
                except Exception as pil_e:
                    logging.debug(f"Pillow preview fallback failed for {path}: {pil_e}")

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
        
        from PyQt6.QtCore import QByteArray, QBuffer
        from utils_io import ensure_long_path
        from PyQt6.QtCore import QBuffer
        try:
            with open(ensure_long_path(path), 'rb') as f:
                data = f.read()
            self._movie_buffer = QBuffer()
            self._movie_buffer.setData(data)
            self._movie_buffer.open(QBuffer.OpenModeFlag.ReadOnly)
            ext = os.path.splitext(path)[1].lower().strip('.')
            fmt = ext.encode() if ext else b''
            self.movie = QMovie(self._movie_buffer, fmt)
        except Exception:
            self.movie = QMovie(path)
            
        self.movie.frameChanged.connect(self._on_movie_frame)
        self.movie.start()
        self.pixmap_item.show()
        
    def setup_video(self, path):
        self._clear_media()
        self.time_overlay.show()
        self.time_overlay.set_time(0, 0)
        
        ext = os.path.splitext(path)[1].lower()
        is_audio = ext in ['.mp3', '.wav', '.ogg', '.oga', '.flac', '.m4a', '.wma', '.aac', '.opus']
        self.current_media_type = 'audio' if is_audio else 'video'
        
        if is_audio:
            track_name = os.path.splitext(os.path.basename(path))[0]
            
            self.lbl_center_text.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
            self.lbl_center_text.setStyleSheet("color: #3b82f6;")
            self.lbl_center_text.setText(f"🎵\n{track_name}")
            self.lbl_center_text.show()
            
            self.update_overlay_positions()
            
            QTimer.singleShot(50, self.reset_view)
        else:
            if not getattr(self, "_video_output_set", False):
                self.player.setVideoOutput(self.video_item)
                self._video_output_set = True
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
            is_fast_active = getattr(AppContext, "session_audio_speed_active", False)
            speed = float(AppContext.session_fast_speed_val) if is_fast_active else 1.0
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

    def clear_faces(self):
        # Удаляем все прямоугольники и полигоны
        for item in self.scene.items():
            from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsPolygonItem
            if isinstance(item, (QGraphicsRectItem, QGraphicsPolygonItem)):
                self.scene.removeItem(item)

    def draw_faces(self, bboxes, matched_bbox=None):
        import logging
        logging.info(f"[UI_PREVIEW] draw_faces called with bboxes={bboxes}, matched_bbox={matched_bbox}")
        self.clear_faces()
        if not bboxes: 
            logging.info("[UI_PREVIEW] No bboxes to draw")
            return
        from PyQt6.QtWidgets import QGraphicsRectItem
        from PyQt6.QtGui import QPen, QColor
        from PyQt6.QtCore import Qt

        valid_bboxes = [b for b in bboxes if len(b) == 4]
        if not valid_bboxes: return

        # Находим индекс целевого лица (лучшее совпадение с matched_bbox)
        target_idx = -1
        if matched_bbox and len(matched_bbox) == 4:
            try:
                mx1, my1, mx2, my2 = float(matched_bbox[0]), float(matched_bbox[1]), float(matched_bbox[2]), float(matched_bbox[3])
                mcx, mcy = (mx1 + mx2) / 2.0, (my1 + my2) / 2.0
                
                best_dist = float('inf')
                for idx, bbox in enumerate(valid_bboxes):
                    x1, y1, x2, y2 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
                    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
                    dist = (cx - mcx)**2 + (cy - mcy)**2
                    if dist < best_dist:
                        best_dist = dist
                        target_idx = idx
            except (ValueError, TypeError):
                pass

        for idx, bbox in enumerate(valid_bboxes):
            try:
                x1, y1, x2, y2 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
            except (ValueError, TypeError) as e:
                import logging
                logging.error(f"[UI_PREVIEW] Error converting bbox to float: {e}")
                continue
                
            logging.info(f"[UI_PREVIEW] Drawing rect at {x1}, {y1}, width={x2-x1}, height={y2-y1}")
            rect = QGraphicsRectItem(x1, y1, x2 - x1, y2 - y1)
            
            if target_idx != -1:
                is_target = (idx == target_idx)
            else:
                is_target = (idx == 0) # Первое лицо зеленое, остальные красные
                
            if is_target:
                pen = QPen(QColor(34, 197, 94)) # Green (#22c55e) for target person
            else:
                pen = QPen(QColor(239, 68, 68)) # Red (#ef4444) for other faces
                
            # Устанавливаем косметическое перо, чтобы ширина рамки была 
            # одинаковой (в пикселях экрана) независимо от разрешения картинки (масштаба сцены)
            pen.setWidth(3)
            pen.setCosmetic(True) 
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            rect.setPen(pen)
            rect.setZValue(10)
            self.scene.addItem(rect)

    def load_file(self, path):
        self.clear_faces()
        from utils_io import strip_long_path_prefix, safe_path_exists
        path = strip_long_path_prefix(path)
        
        if self.current_path == path:
            return
            
        if not hasattr(self, '_heartbeat_timer'):
            self._heartbeat_timer = QTimer(self)
            self._heartbeat_timer.start(100)
            
        self.stop_playback(True)
        if not safe_path_exists(path):
            self.show_empty(AppContext.tr("msg_error_file"))
            return
            
        self.current_path = path
        ext = os.path.splitext(path)[1].lower()
        self.update_meta(path)
        
        if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.avif']: self.setup_static_image(path)
        elif ext in ['.gif', '.webp', '.avif']: self.setup_animated(path)
        elif ext in VIDEO_EXTS or ext in ['.mp3', '.wav', '.ogg', '.oga', '.flac', '.m4a', '.wma', '.aac', '.opus']: 
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
        elif self.lbl_center_text.isVisible():
            active_item = None
            
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
            if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.avif', '.webp', '.avif', '.gif']:
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

    def draw_polygon(self, pts):
        if not self.scene or not self.pixmap_item: return
        self.clear_faces()
        if pts is None or len(pts) == 0: return
        
        from PyQt6.QtWidgets import QGraphicsPolygonItem
        from PyQt6.QtGui import QPen, QColor, QPolygonF
        from PyQt6.QtCore import Qt, QPointF
        
        poly = QPolygonF()
        try:
            for pt in pts:
                x, y = pt[0][0], pt[0][1]
                poly.append(QPointF(float(x), float(y)))
        except:
            return
            
        poly_item = QGraphicsPolygonItem(poly)
        pen = QPen(QColor(34, 197, 94, 255)) # Modern green color
        pen.setWidth(3)
        pen.setCosmetic(True) # Ensures consistent thickness regardless of image resolution/zoom
        poly_item.setPen(pen)
        poly_item.setZValue(10)
        self.scene.addItem(poly_item)
