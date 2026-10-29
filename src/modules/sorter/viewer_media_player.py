"""
viewer_media_player.py: Холст одиночного просмотра (ZoomableGraphicsView / SingleCanvasView)
с поддержкой масштабирования, панорамирования, медиаплеера и оверлеев.
"""
import os
import logging
from PyQt6.QtWidgets import (
    QWidget, QFrame, QPushButton, QLabel,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsTextItem, QGraphicsProxyWidget
)
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, pyqtSignal, QSize, QUrl, QPoint
from PyQt6.QtGui import (
    QColor, QPixmap, QMovie, QWheelEvent, QMouseEvent, QPainter, QKeyEvent,
    QCursor, QTransform, QFont
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget, QGraphicsVideoItem

from config import AppContext, VIEWER_DESIGN
from utils_io import ensure_long_path
from .ui_player import VideoPlayerControls, SegmentIndicatorWidget
from .viewer_items import find_main_app, FileIconManager

class ZoomableGraphicsView(QGraphicsView):
    canvas_clicked = pyqtSignal()
    fullscreen_toggled = pyqtSignal()
    items_dropped = pyqtSignal(list, bool)
    browse_requested = pyqtSignal()
    controls_visibility_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        default_color = VIEWER_DESIGN['default_bg']
        self.setBackgroundBrush(QColor(default_color))
        self.setStyleSheet(f"background-color: {default_color}; border: none;")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)

        from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem
        self.video_item = QGraphicsVideoItem()
        self.scene.addItem(self.video_item)
        self.video_item.hide()
        self.video_item.nativeSizeChanged.connect(self._on_video_native_size_changed)

        self.btn_seg_prev = QPushButton("<", self)
        self.btn_seg_next = QPushButton(">", self)
        
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
            btn.setFixedSize(50, 200)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.hide()
            
        self.btn_seg_prev.clicked.connect(self._on_seg_prev)
        self.btn_seg_next.clicked.connect(self._on_seg_next)
        
        self.segment_indicator = SegmentIndicatorWidget(self)
        self.segment_indicator.clicked.connect(self._on_segment_indicator_clicked)
        self.segment_indicator.hide()
        
        # Overlay states
        self.hover_buttons_active = False
        self.lbl_center_text = QLabel(self)
        self.lbl_center_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_center_text.setWordWrap(True)
        self.lbl_center_text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.lbl_center_text.hide()
        
        self.current_movie = None
        self.double_click_callback = None
        self.middle_click_callback = None
        self._click_start_pos = None
        
        self.is_fullscreen_mode = False
        self.floating_controls = None
        self.time_overlay = None
        self.current_is_video = False
        
        self.hide_timer = QTimer(self)
        self.hide_timer.setInterval(3000)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self._hide_overlays)
            
    def get_smart_preview_mgr(self):
        parent = self.parent()
        while parent:
            if type(parent).__name__ == "PreviewPopup":
                if hasattr(parent, 'smart_preview_mgr'):
                    return parent.smart_preview_mgr
            parent = parent.parent()
        main_app = find_main_app(self)
        if main_app and hasattr(main_app, 'smart_preview_mgr'):
            return main_app.smart_preview_mgr
        return None

    def _on_seg_prev(self):
        mgr = self.get_smart_preview_mgr()
        if mgr:
            mgr.skip_prev()
            
    def _on_seg_next(self):
        mgr = self.get_smart_preview_mgr()
        if mgr:
            mgr.skip_next()
            
    def _on_segment_indicator_clicked(self):
        AppContext.session_segment_view = not AppContext.session_segment_view
        
        mgr = self.get_smart_preview_mgr()
        if mgr:
            mgr.set_active(AppContext.session_segment_view)
            
        self.update_segment_indicator()
            
    def update_segment_indicator(self):
        if not hasattr(self, 'segment_indicator'):
            return
            
        mgr = self.get_smart_preview_mgr()
        
        if self.current_is_video and mgr:
            self.segment_indicator.show()
            self.segment_indicator.raise_()
            
            if mgr.active and not mgr.user_paused:
                if not getattr(self.segment_indicator, 'is_active_mode', False):
                    self.segment_indicator.start_blinking()
            else:
                self.segment_indicator.stop_blinking(transparent=True)
                self.btn_seg_prev.hide()
                self.btn_seg_next.hide()
        else:
            self.segment_indicator.stop_blinking(transparent=False)
            self.btn_seg_prev.hide()
            self.btn_seg_next.hide()

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            event.ignore()
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        md = event.mimeData()
        paths = []
        is_external = False
        if md.hasUrls():
            urls = md.urls()
            if urls:
                paths = [u.toLocalFile() for u in urls]
                is_external = True
        if paths:
            self.items_dropped.emit(paths, is_external)
            event.acceptProposedAction()
        else:
            event.ignore()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reset_view()
        self.update_overlay_positions()

    def update_overlay_positions(self):
        if self.floating_controls and self.is_fullscreen_mode:
            w = self.width() - 40 
            h = self.floating_controls.height()
            x = 20
            y = self.height() - h - 20
            self.floating_controls.setGeometry(x, y, w, h)
        if self.time_overlay and self.time_overlay.isVisible():
            padding = 10
            controls_h = self.floating_controls.height() if (self.floating_controls and self.is_fullscreen_mode) else 0
            
            x = self.width() - self.time_overlay.width() - padding
            y = self.height() - controls_h - self.time_overlay.height() - padding
            
            self.time_overlay.move(x, y)
            self.time_overlay.raise_()
            
        if hasattr(self, 'lbl_center_text') and self.lbl_center_text.isVisible():
            max_w = self.width() - 40
            if max_w > 0:
                self.lbl_center_text.setMaximumWidth(max_w)
                self.lbl_center_text.adjustSize()
                x_text = (self.width() - self.lbl_center_text.width()) // 2
                y_text = (self.height() - self.lbl_center_text.height()) // 2
                self.lbl_center_text.move(x_text, y_text)
                
        if hasattr(self, 'btn_seg_prev'):
            y_center = (self.height() - self.btn_seg_prev.height()) // 2
            self.btn_seg_prev.move(80, y_center)
            self.btn_seg_next.move(self.width() - self.btn_seg_next.width() - 80, y_center)
        if hasattr(self, 'segment_indicator'):
            self.segment_indicator.move(10, 60)

    def set_fullscreen_mode(self, enabled, controls_widget=None):
        self.is_fullscreen_mode = enabled
        if enabled:
            self.setMouseTracking(True)
            self.floating_controls = controls_widget
            if self.floating_controls:
                self.floating_controls.setParent(self)
                self.floating_controls.show()
                self.floating_controls.setStyleSheet("background-color: rgba(17,17,17,0.8); border-radius: 10px;")
            self.update_overlay_positions()
            self._reset_hide_timer()
        else:
            self.setMouseTracking(False)
            self.hide_timer.stop()
            self._hide_cursor()
            if self.floating_controls:
                self.floating_controls.setParent(None)
                self.floating_controls.setStyleSheet(f"background-color: {VIEWER_DESIGN['player_bg']};")
                self.floating_controls = None

    def _reset_hide_timer(self):
        if not self.is_fullscreen_mode: return
        if self.floating_controls: self.floating_controls.show()
        if self.time_overlay and getattr(self, 'current_is_video', False): self.time_overlay.show()
        self.controls_visibility_changed.emit(True)
        
        main_app = find_main_app(self)
        if hasattr(main_app, 'media_player') and main_app.media_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            if hasattr(self, 'play_icon_lbl') and getattr(self, 'current_is_video', False):
                self.play_icon_lbl.show()
                
        if hasattr(self, 'update_segment_indicator'):
            self.update_segment_indicator()

        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        self.hide_timer.start()

    def _hide_overlays(self):
        if not self.is_fullscreen_mode: return
        if self.floating_controls and self.floating_controls.underMouse():
            self.hide_timer.start()
            return
        if self.floating_controls: self.floating_controls.hide()
        if self.time_overlay: self.time_overlay.hide()
        self.controls_visibility_changed.emit(False)
        
        if hasattr(self, 'play_icon_lbl'): self.play_icon_lbl.hide()
        if hasattr(self, 'segment_indicator'): self.segment_indicator.hide()
        if hasattr(self, 'btn_seg_prev'): self.btn_seg_prev.hide()
        if hasattr(self, 'btn_seg_next'): self.btn_seg_next.hide()
        
        self.setCursor(Qt.CursorShape.BlankCursor)
        self.viewport().setCursor(Qt.CursorShape.BlankCursor)

    def _hide_cursor(self):
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor)

    def mouseMoveEvent(self, event):
        if self.is_fullscreen_mode:
            self._reset_hide_timer()
            
        main_app = find_main_app(self)
        mgr = getattr(main_app, 'smart_preview_mgr', None)
        
        if mgr:
            segment_active = mgr.active and mgr.num_segments > 0
            
        if segment_active and self.current_is_video:
            pos = event.pos()
            if pos.x() < self.width() * 0.3:
                self.btn_seg_prev.show()
                self.btn_seg_prev.raise_()
                self.btn_seg_next.hide()
            elif pos.x() > self.width() * 0.7:
                self.btn_seg_next.show()
                self.btn_seg_next.raise_()
                self.btn_seg_prev.hide()
            else:
                self.btn_seg_prev.hide()
                self.btn_seg_next.hide()
        else:
            self.btn_seg_prev.hide()
            self.btn_seg_next.hide()
            
        super().mouseMoveEvent(event)

    def enterEvent(self, event):
        super().enterEvent(event)

    def leaveEvent(self, event):
        local_pos = self.mapFromGlobal(QCursor.pos())
        if not self.rect().contains(local_pos):
            if hasattr(self, 'btn_seg_prev'): self.btn_seg_prev.hide()
            if hasattr(self, 'btn_seg_next'): self.btn_seg_next.hide()
        super().leaveEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            super().wheelEvent(event)
        else:
            factor = VIEWER_DESIGN["zoom_factor"]
            if event.angleDelta().y() < 0:
                factor = 1.0 / factor
            self.scale(factor, factor)

    def mousePressEvent(self, event: QMouseEvent):
        self._click_start_pos = event.pos()
        if event.button() == Qt.MouseButton.RightButton:
            self.reset_view()
        elif event.button() == Qt.MouseButton.MiddleButton:
            if self.middle_click_callback: self.middle_click_callback()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self._click_start_pos:
            dist = (event.pos() - self._click_start_pos).manhattanLength()
            if dist < 5:
                self.canvas_clicked.emit()
        self._click_start_pos = None

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.double_click_callback: self.double_click_callback()
        super().mouseDoubleClickEvent(event)

    def set_image(self, pixmap):
        self.current_is_video = False
        if self.time_overlay: self.time_overlay.hide()
        self.clear_scene_content()
        self.pixmap_item.setPixmap(pixmap)
        self.pixmap_item.show()
        if not pixmap.isNull():
            self.scene.setSceneRect(self.pixmap_item.boundingRect())
        self._current_rotation = 0
        self.reset_view()

    def set_animated(self, filepath):
        self.current_is_video = False
        if self.time_overlay: self.time_overlay.hide()
        self.clear_scene_content()
        
        from PyQt6.QtCore import QBuffer
        from utils_io import ensure_long_path
        try:
            with open(ensure_long_path(filepath), 'rb') as f:
                data = f.read()
            self._movie_buffer = QBuffer()
            self._movie_buffer.setData(data)
            self._movie_buffer.open(QBuffer.OpenModeFlag.ReadOnly)
            ext = os.path.splitext(filepath)[1].lower().strip('.')
            fmt = ext.encode() if ext else b''
            self.current_movie = QMovie(self._movie_buffer, fmt)
        except Exception:
            self.current_movie = QMovie(filepath)
            
        self.current_movie.frameChanged.connect(lambda: self.pixmap_item.setPixmap(self.current_movie.currentPixmap()))
        self.current_movie.jumpToNextFrame()
        self.current_movie.start()
        self.pixmap_item.show()
        self._fit_movie()

    def _fit_movie(self):
        if self.current_movie and self.current_movie.isValid():
            rect = QRectF(self.current_movie.frameRect())
            if rect.width() > 0 and rect.height() > 0:
                self.scene.setSceneRect(rect)
                self.reset_view()

    def _on_video_native_size_changed(self, size):
        if not size.isValid():
            return
        self.video_item.setSize(size)
        if getattr(self, 'current_is_video', False):
            from PyQt6.QtCore import QRectF, QPointF
            self.scene.setSceneRect(QRectF(QPointF(0, 0), size))
            self.reset_view()

    def set_video_mode(self):
        self.current_is_video = True
        if self.time_overlay: 
            self.time_overlay.show()
            self.time_overlay.set_time(0, 0)
        self.clear_scene_content()
        self.video_item.show()
        if self.video_item.nativeSize().isValid():
            sz = self.video_item.nativeSize()
            self.video_item.setSize(sz)
            self.scene.setSceneRect(QRectF(QPointF(0,0), sz))
            self.reset_view()

    def set_audio_mode(self, text):
        self.current_is_video = False
        if self.time_overlay: self.time_overlay.hide()
        self.clear_scene_content()
        
        track_name = os.path.basename(text)
        
        self.lbl_center_text.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        self.lbl_center_text.setStyleSheet("color: #3b82f6;")
        self.lbl_center_text.setText(f"🎵\n{track_name}")
        self.lbl_center_text.show()
        
        self.update_overlay_positions()
        
        self.scene.setSceneRect(0, 0, 100, 100) # dummy rect since we use overlay
        self.reset_view()

    def show_empty_state(self, message):
        viewer_area = self.parent()
        if viewer_area and hasattr(viewer_area, 'show_empty_state'):
            viewer_area.show_empty_state(message)
            return

        self.current_is_video = False
        if self.time_overlay:
            self.time_overlay.hide()
        self.clear_scene_content()
        
        self.lbl_center_text.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self.lbl_center_text.setStyleSheet("color: #9ca3af;")
        self.lbl_center_text.setText(message)
        self.lbl_center_text.show()
        
        self.update_overlay_positions()
        self.scene.setSceneRect(0, 0, 100, 100)
        self.reset_view()

    def clear_scene_content(self):
        if self.current_movie:
            self.current_movie.stop()
            self.current_movie.deleteLater()
            self.current_movie = None
        self.pixmap_item.hide()
        self.video_item.hide()
        self.lbl_center_text.hide()
        self.pixmap_item.setPixmap(QPixmap())
        for item in self.scene.items():
            if isinstance(item, QGraphicsProxyWidget):
                w = item.widget()
                self.scene.removeItem(item)
                if w:
                    w.deleteLater()
                item.deleteLater()

    def _fit_video_size_changed(self, size):
        self.video_item.setSize(size)
        self.scene.setSceneRect(QRectF(QPointF(0,0), size))
        self.reset_view()

    def reset_view(self):
        self.resetTransform()
        if getattr(self, '_current_rotation', 0) != 0:
            super().rotate(self._current_rotation)
        if self.video_item.isVisible() or self.lbl_center_text.isVisible():
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        else:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            
        self.horizontalScrollBar().setValue(0)
        self.verticalScrollBar().setValue(0)
        
        active_item = None
        if self.video_item.isVisible():
            active_item = self.video_item
        elif self.pixmap_item.isVisible() and not self.pixmap_item.pixmap().isNull():
            active_item = self.pixmap_item
        elif self.lbl_center_text.isVisible():
            active_item = None # text is now a floating widget, doesn't need scene centering
            
        if active_item:
            active_item.setPos(0, 0)
            if hasattr(active_item, 'setTransform'):
                from PyQt6.QtGui import QTransform
                active_item.setTransform(QTransform())
            
        content_rect = self.scene.sceneRect()
        view_rect = self.viewport().rect()
        if content_rect.width() > 0 and content_rect.height() > 0:
            width_diff = content_rect.width() - view_rect.width()
            height_diff = content_rect.height() - view_rect.height()
            
            is_rotated = getattr(self, '_current_rotation', 0) % 180 != 0
            
            if active_item == self.video_item:
                self.fitInView(active_item, Qt.AspectRatioMode.KeepAspectRatio)
                self.centerOn(active_item)
            elif active_item == self.pixmap_item:
                if width_diff > 0 or height_diff > 0 or is_rotated:
                    self.fitInView(active_item, Qt.AspectRatioMode.KeepAspectRatio)
                    self.centerOn(active_item)
                else:
                    self.centerOn(active_item)
            else:
                self.fitInView(content_rect, Qt.AspectRatioMode.KeepAspectRatio)
                self.centerOn(content_rect.center())

    def change_rotation(self, angle):
        if self.video_item.isVisible() or self.lbl_center_text.isVisible():
            return
        if not hasattr(self, '_current_rotation'):
            self._current_rotation = 0
        self._current_rotation = (self._current_rotation + angle) % 360
        self.reset_view()

    def set_absolute_rotation(self, angle):
        if self.video_item.isVisible() or self.lbl_center_text.isVisible():
            return
        self._current_rotation = angle % 360
        self.reset_view()

    def set_background_color(self, color):
        self.setBackgroundBrush(QColor(color))
        self.setStyleSheet(f"background-color: {color}; border: none;")




# Псевдоним для совместимости
SingleCanvasView = ZoomableGraphicsView
