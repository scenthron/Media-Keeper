import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsItem, QWidget, QLabel
)
from PyQt6.QtCore import Qt, QRectF, pyqtSignal, QPointF
from PyQt6.QtGui import QPixmap, QColor, QBrush, QPen, QPainter, QPainterPath, QMouseEvent

from config import AppContext, APP_DESIGN

class CropOverlayItem(QGraphicsItem):
    """Оверлей для отображения затемненного фона и рамки."""
    def __init__(self, rect, parent=None):
        super().__init__(parent)
        self._rect = rect # Выделенная область (фрагмент)
        self._image_rect = QRectF() # Область всего изображения
        self.setAcceptHoverEvents(True)
        
        # Ручки для изменения размера
        self.handle_size = 10
        self.active_handle = None
        self.is_resizing = False
        self.is_moving = False
        self.last_pos = None

    def boundingRect(self):
        return self._image_rect

    def set_image_rect(self, rect):
        self._image_rect = rect
        self.prepareGeometryChange()

    def set_crop_rect(self, rect):
        self._rect = rect.intersected(self._image_rect)
        self.prepareGeometryChange()

    def get_crop_rect(self):
        return self._rect

    def paint(self, painter, option, widget):
        if self._rect.isNull():
            return
            
        # Заливка вне рамки
        painter.setBrush(QBrush(QColor(0, 0, 0, 150)))
        painter.setPen(Qt.PenStyle.NoPen)
        
        path = QPainterPath()
        path.addRect(self._image_rect)
        path.addRect(self._rect)
        painter.drawPath(path)
        
        # Рисуем саму рамку
        pen = QPen(QColor("#3b82f6"))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self._rect)
        
        # Никаких точек внутри рамки по запросу пользователя.
        
    def _get_handle_at(self, pos):
        # 0: top-left, 1: top, 2: top-right, 3: right, 4: bottom-right, 5: bottom, 6: bottom-left, 7: left
        hs = self.handle_size
        r = self._rect
        handles = [
            QRectF(r.left() - hs, r.top() - hs, hs*2, hs*2), # TL
            QRectF(r.center().x() - hs, r.top() - hs, hs*2, hs*2), # T
            QRectF(r.right() - hs, r.top() - hs, hs*2, hs*2), # TR
            QRectF(r.right() - hs, r.center().y() - hs, hs*2, hs*2), # R
            QRectF(r.right() - hs, r.bottom() - hs, hs*2, hs*2), # BR
            QRectF(r.center().x() - hs, r.bottom() - hs, hs*2, hs*2), # B
            QRectF(r.left() - hs, r.bottom() - hs, hs*2, hs*2), # BL
            QRectF(r.left() - hs, r.center().y() - hs, hs*2, hs*2) # L
        ]
        for i, h in enumerate(handles):
            if h.contains(pos):
                return i
        if r.contains(pos):
            return 8 # Внутри - перемещение
        return None

    def hoverMoveEvent(self, event):
        handle = self._get_handle_at(event.pos())
        if handle in (0, 4): self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif handle in (2, 6): self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif handle in (1, 5): self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif handle in (3, 7): self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif handle == 8: self.setCursor(Qt.CursorShape.SizeAllCursor)
        else: self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._get_handle_at(event.pos())
            if handle is not None:
                self.active_handle = handle
                self.last_pos = event.pos()
                if handle == 8:
                    self.is_moving = True
                else:
                    self.is_resizing = True
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.active_handle is not None:
            delta = event.pos() - self.last_pos
            self.last_pos = event.pos()
            
            r = self._rect
            if self.is_moving:
                r.translate(delta.x(), delta.y())
            elif self.is_resizing:
                if self.active_handle in (0, 1, 2): r.setTop(r.top() + delta.y())
                if self.active_handle in (4, 5, 6): r.setBottom(r.bottom() + delta.y())
                if self.active_handle in (0, 6, 7): r.setLeft(r.left() + delta.x())
                if self.active_handle in (2, 3, 4): r.setRight(r.right() + delta.x())
            
            # Не даем рамке стать слишком маленькой или выйти за пределы изображения
            r = r.normalized()
            if r.width() < 10: r.setWidth(10)
            if r.height() < 10: r.setHeight(10)
            r = r.intersected(self._image_rect)
            
            self._rect = r
            self.prepareGeometryChange()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.active_handle = None
        self.is_moving = False
        self.is_resizing = False
        super().mouseReleaseEvent(event)


class CropDialog(QDialog):
    def __init__(self, image_path, parent=None, previous_crop_rect=None):
        super().__init__(parent)
        self.setWindowTitle("Выбор фрагмента для поиска")
        self.setMinimumSize(1024, 768)
        self.image_path = image_path
        self.crop_rect = None # Результат (QRectF)
        
        self.init_ui()
        self.load_image(previous_crop_rect)
        
    def init_ui(self):
        main_layout = QHBoxLayout(self)
        
        # Левая часть: Холст
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.view.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.view.wheelEvent = self._zoom_event
        self.view._original_mouse_press = self.view.mousePressEvent
        self.view.mousePressEvent = self._view_mouse_press
        self.view._original_mouse_release = self.view.mouseReleaseEvent
        self.view.mouseReleaseEvent = self._view_mouse_release
        self.view._original_mouse_move = self.view.mouseMoveEvent
        self.view.mouseMoveEvent = self._view_mouse_move
        self.view._pan_active = False
        self.drawing = False
        
        # Правая часть: Превью и кнопки
        right_panel = QWidget()
        right_panel.setFixedWidth(250)
        right_layout = QVBoxLayout(right_panel)
        
        self.lbl_preview = QLabel("Превью")
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setMinimumHeight(250)
        self.lbl_preview.setStyleSheet(f"border: 1px solid #444; background: #1a1a1a;")
        
        self.lbl_size = QLabel("Размер: 0 x 0")
        self.lbl_size.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_size.setStyleSheet("color: #aaa; font-size: 11px;")
        
        self.btn_clear = QPushButton("Очистить")
        self.btn_clear.clicked.connect(self.clear_crop)
        
        self.btn_ok = QPushButton("ОК / Выбрать фрагмент")
        self.btn_ok.setStyleSheet("background-color: #3b82f6; color: white; border-radius: 4px; padding: 8px;")
        self.btn_ok.clicked.connect(self.accept)
        
        right_layout.addWidget(QLabel("Предпросмотр фрагмента:"))
        right_layout.addWidget(self.lbl_preview)
        right_layout.addWidget(self.lbl_size)
        right_layout.addStretch()
        right_layout.addWidget(self.btn_clear)
        right_layout.addWidget(self.btn_ok)
        
        main_layout.addWidget(self.view, 1)
        main_layout.addWidget(right_panel)
        
        # Обновление превью по таймеру
        from PyQt6.QtCore import QTimer
        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self.update_preview)
        self.preview_timer.start(50)

    def load_image(self, previous_crop_rect):
        from utils_io import safe_cv2_imread
        import cv2
        from PyQt6.QtGui import QImage
        img = safe_cv2_imread(self.image_path)
        if img is not None:
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            h, w, ch = img_rgb.shape
            qimg = QImage(img_rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
            self.pixmap = QPixmap.fromImage(qimg)
        else:
            self.pixmap = QPixmap(self.image_path)
        
        self.image_item = self.scene.addPixmap(self.pixmap)
        
        rect = self.pixmap.rect()
        self.scene.setSceneRect(QRectF(rect))
        
        self.overlay = CropOverlayItem(QRectF())
        self.overlay.set_image_rect(QRectF(rect))
        self.scene.addItem(self.overlay)
        
        if previous_crop_rect:
            self.overlay.set_crop_rect(previous_crop_rect)
            
        # Подгон масштаба (Fit)
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _zoom_event(self, event):
        if hasattr(event, 'position'):
            pos = event.position().toPoint()
        else:
            pos = event.pos()
            
        old_pos = self.view.mapToScene(pos)
        
        if event.angleDelta().y() > 0:
            factor = 1.15
        else:
            factor = 0.85
            
        self.view.scale(factor, factor)
        
        new_pos = self.view.mapToScene(pos)
        delta = new_pos - old_pos
        self.view.translate(delta.x(), delta.y())
        event.accept()
        
    def _view_mouse_press(self, event):
        from PyQt6.QtCore import Qt, QPointF
        if event.button() == Qt.MouseButton.MiddleButton:
            self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.view._pan_active = True
            fake_event = QMouseEvent(event.type(), QPointF(event.pos()), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, event.modifiers())
            self.view._original_mouse_press(fake_event)
            return
            
        scene_pos = self.view.mapToScene(event.pos())
        self.drag_start = scene_pos
        self.drawing = True
        self.crop_rect = QRectF(scene_pos, scene_pos)
        self.overlay.set_crop_rect(self.crop_rect)
        self.view._original_mouse_press(event)

    def _view_mouse_release(self, event):
        from PyQt6.QtCore import Qt, QPointF
        if event.button() == Qt.MouseButton.MiddleButton and getattr(self.view, '_pan_active', False):
            fake_event = QMouseEvent(event.type(), QPointF(event.pos()), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, event.modifiers())
            self.view._original_mouse_release(fake_event)
            self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.view._pan_active = False
            return
            
        if getattr(self, 'drawing', False):
            self.drawing = False
            
        self.view._original_mouse_release(event)
        
    def _view_mouse_move(self, event):
        if getattr(self, 'drawing', False):
            scene_pos = self.view.mapToScene(event.pos())
            self.crop_rect = QRectF(self.drag_start, scene_pos).normalized()
            self.overlay.set_crop_rect(self.crop_rect)
            
        if getattr(self.view, '_pan_active', False):
            from PyQt6.QtCore import Qt, QPointF
            fake_event = QMouseEvent(event.type(), QPointF(event.pos()), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, event.modifiers())
            self.view._original_mouse_move(fake_event)
            return
            
        self.view._original_mouse_move(event)


    def update_preview(self):
        rect = self.overlay.get_crop_rect()
        if not rect.isNull():
            cropped_pixmap = self.pixmap.copy(rect.toRect())
            scaled = cropped_pixmap.scaled(self.lbl_preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.lbl_preview.setPixmap(scaled)
            self.btn_clear.setEnabled(True)
            self.lbl_size.setText(f"Размер: {int(rect.width())} x {int(rect.height())}")
        else:
            self.lbl_preview.clear()
            self.lbl_preview.setText("Выделите область")
            self.btn_clear.setEnabled(False)
            self.lbl_size.setText("Размер: 0 x 0")

    def clear_crop(self):
        self.overlay.set_crop_rect(QRectF())
        self.update_preview()

    def get_result(self):
        rect = self.overlay.get_crop_rect()
        if rect.isNull():
            return None
        return rect
