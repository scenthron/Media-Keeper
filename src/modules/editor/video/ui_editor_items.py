
from PyQt6.QtWidgets import QGraphicsObject, QGraphicsItem
from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QPixmap, QMovie, QFont, QFontMetrics

class OverlayGraphicsItem(QGraphicsObject):
    """
    Интерактивный элемент наложения (Рисунок, Регион или Размытие).
    """
    def __init__(self, parent_item=None):
        super().__init__(parent_item)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable | 
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges |
                      QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        
        self._rect = QRectF(0, 0, 200, 200)
        self._mode = "region" # region, image, blur
        
        # Default color: Red with ~50% alpha
        self._color = QColor(255, 0, 0, 127)
        
        self._pixmap = None # Для режима image
        self._movie = None  # Для режима gif
        self._source_bg_pixmap = None # Для режима blur (фон)
        self._blur_strength = 0 
        self._opacity = 1.0
        
        # Handles
        self.handle_size = 14
        self.hover_handle = None
        self.is_resizing = False
        self.resize_start_pos = None
        self.resize_start_rect = None

        # Animation for marching ants
        self._dash_offset = 0
        self.anim_timer = QTimer()
        self.anim_timer.timeout.connect(self._animate_dash)
        self.anim_timer.setInterval(100) # 10 FPS animation

        self.setZValue(20) 

    def _animate_dash(self):
        if self.isSelected():
            self._dash_offset -= 1
            if self._dash_offset < -10: self._dash_offset = 0
            self.update()
        else:
            self.anim_timer.stop()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            if value: # Selected
                self.anim_timer.start()
            else:
                self.anim_timer.stop()
                self.update() # Redraw to remove handles
        
        # --- CLAMPING POSITION (MOVING) ---
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.parentItem():
            new_pos = value
            parent_rect = self.parentItem().boundingRect()
            content_rect = self._rect
            
            min_x = parent_rect.left() - content_rect.left()
            max_x = parent_rect.right() - content_rect.right()
            min_y = parent_rect.top() - content_rect.top()
            max_y = parent_rect.bottom() - content_rect.bottom()
            
            x = max(min_x, min(new_pos.x(), max_x))
            y = max(min_y, min(new_pos.y(), max_y))
            
            return QPointF(x, y)

        return super().itemChange(change, value)

    def boundingRect(self):
        hs = self.handle_size
        # Increase top margin (-hs - 30) to include the size text label area.
        # This prevents artifacts/ghosting when moving the item.
        return self._rect.adjusted(-hs, -hs - 30, hs, hs)

    def set_rect(self, rect):
        self._rect = rect
        self.prepareGeometryChange()
        self.update()

    def get_rect(self):
        return self._rect

    def set_mode(self, mode):
        self._mode = mode
        self.update()

    def set_color(self, color):
        self._color = QColor(color)
        self.update()

    def set_opacity(self, val):
        self._opacity = val
        self.update()
        
    def set_blur_strength(self, val):
        self._blur_strength = val
        self.update()

    def set_pixmap(self, pixmap):
        self._pixmap = pixmap
        self.update()
        
    def set_source_pixmap(self, pixmap):
        self._source_bg_pixmap = pixmap
        if self._mode == 'blur':
            self.update()
        
    def set_movie(self, movie):
        self._movie = movie
        if self._movie:
            self._movie.frameChanged.connect(self._on_movie_frame)
            self._movie.start()
            
    def _on_movie_frame(self):
        if self._movie:
            self._pixmap = self._movie.currentPixmap()
            self.update()

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        # 1. DRAW CONTENT
        if self._mode == "region":
            c = QColor(self._color)
            c.setAlphaF(self._opacity)
            painter.setBrush(QBrush(c))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(self._rect)
            
        elif self._mode == "blur":
            if self._source_bg_pixmap and not self._source_bg_pixmap.isNull():
                rect_in_parent = self.mapRectToParent(self._rect).toRect()
                cropped = self._source_bg_pixmap.copy(rect_in_parent)
                
                if self._blur_strength > 0 and not cropped.isNull():
                    scale_factor = max(0.02, 1.0 - (self._blur_strength / 100.0))
                    small = cropped.scaled(
                        int(cropped.width() * scale_factor), 
                        int(cropped.height() * scale_factor), 
                        Qt.AspectRatioMode.IgnoreAspectRatio, 
                        Qt.TransformationMode.SmoothTransformation
                    )
                    blurred = small.scaled(
                        cropped.width(), 
                        cropped.height(), 
                        Qt.AspectRatioMode.IgnoreAspectRatio, 
                        Qt.TransformationMode.SmoothTransformation
                    )
                    painter.drawPixmap(self._rect.toRect(), blurred)
                else:
                    painter.drawPixmap(self._rect.toRect(), cropped)
            else:
                c = QColor(200, 200, 200, 100)
                painter.setBrush(QBrush(c))
                painter.drawRect(self._rect)
                painter.setPen(QColor(255,255,255))
                painter.drawText(self._rect, Qt.AlignmentFlag.AlignCenter, "BLUR PREVIEW")
            
        elif self._mode == "image":
            if self._pixmap and not self._pixmap.isNull():
                painter.setOpacity(self._opacity)
                painter.drawPixmap(self._rect.toRect(), self._pixmap)
                painter.setOpacity(1.0)
            else:
                painter.setPen(QPen(Qt.GlobalColor.white, 1, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(self._rect)
                painter.drawText(self._rect, Qt.AlignmentFlag.AlignCenter, "NO IMAGE")

        # 2. DRAW SELECTION UI
        if self.isSelected():
            pen = QPen(QColor("#ef4444"), 2, Qt.PenStyle.DashLine) 
            pen.setDashOffset(self._dash_offset)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self._rect)
            
            painter.setPen(QPen(QColor("#ffffff"), 1)) 
            painter.setBrush(QBrush(QColor("#3b82f6"))) 
            
            handles = self._get_handle_rects()
            for h_rect in handles.values():
                painter.drawEllipse(h_rect)
            
            # Smart Size Label
            lod = option.levelOfDetailFromTransform(painter.worldTransform())
            if lod <= 0: lod = 1
            
            target_pixel_size = 14
            scaled_font_size = max(1, int(target_pixel_size / lod))
            
            w = int(self._rect.width())
            h = int(self._rect.height())
            size_txt = f"{w}x{h}"
            
            font = QFont("Arial")
            font.setPixelSize(scaled_font_size)
            font.setBold(True)
            painter.setFont(font)
            
            fm = QFontMetrics(font)
            txt_w = fm.horizontalAdvance(size_txt) + (8 / lod)
            txt_h = fm.height() + (4 / lod)
            
            txt_rect = QRectF(self._rect.left(), self._rect.top() - txt_h - (2/lod), txt_w, txt_h)
            
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(0,0,0, 180)))
            painter.drawRoundedRect(txt_rect, 3/lod, 3/lod)
            
            painter.setPen(QColor("#ffffff"))
            painter.drawText(txt_rect, Qt.AlignmentFlag.AlignCenter, size_txt)

        elif self.acceptHoverEvents() and self.isUnderMouse():
             painter.setPen(QPen(QColor("#ffffff"), 1, Qt.PenStyle.DotLine))
             painter.setBrush(Qt.BrushStyle.NoBrush)
             painter.drawRect(self._rect)

    def _get_handle_rects(self):
        r = self._rect
        hs = self.handle_size
        return {
            'tl': QRectF(r.left() - hs/2, r.top() - hs/2, hs, hs),
            'tr': QRectF(r.right() - hs/2, r.top() - hs/2, hs, hs),
            'bl': QRectF(r.left() - hs/2, r.bottom() - hs/2, hs, hs),
            'br': QRectF(r.right() - hs/2, r.bottom() - hs/2, hs, hs)
        }

    def hoverMoveEvent(self, event):
        if not self.isSelected():
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            super().hoverMoveEvent(event)
            return

        pos = event.pos()
        handles = self._get_handle_rects()
        cursor = Qt.CursorShape.SizeAllCursor 
        self.hover_handle = None
        
        if handles['tl'].contains(pos) or handles['br'].contains(pos):
            cursor = Qt.CursorShape.SizeFDiagCursor 
            self.hover_handle = 'tl' if handles['tl'].contains(pos) else 'br'
        elif handles['tr'].contains(pos) or handles['bl'].contains(pos):
            cursor = Qt.CursorShape.SizeBDiagCursor
            self.hover_handle = 'tr' if handles['tr'].contains(pos) else 'bl'
        elif self._rect.contains(pos):
            cursor = Qt.CursorShape.SizeAllCursor
        else:
            cursor = Qt.CursorShape.ArrowCursor
            
        self.setCursor(cursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.isSelected() and self.hover_handle:
                self.is_resizing = True
                self.resize_start_pos = event.pos()
                self.resize_start_rect = self._rect
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_resizing and self.resize_start_rect:
            diff = event.pos() - self.resize_start_pos
            r = self.resize_start_rect
            new_rect = QRectF(r)
            
            if self.hover_handle == 'br':
                new_rect.setBottomRight(r.bottomRight() + diff)
            elif self.hover_handle == 'tl':
                new_rect.setTopLeft(r.topLeft() + diff)
            elif self.hover_handle == 'tr':
                new_rect.setTopRight(r.topRight() + diff)
            elif self.hover_handle == 'bl':
                new_rect.setBottomLeft(r.bottomLeft() + diff)
            
            new_rect = new_rect.normalized()

            if self.parentItem():
                parent_rect = self.parentItem().boundingRect()
                pos_in_parent = self.pos() 
                
                if pos_in_parent.x() + new_rect.left() < parent_rect.left():
                    new_rect.setLeft(parent_rect.left() - pos_in_parent.x())
                if pos_in_parent.y() + new_rect.top() < parent_rect.top():
                    new_rect.setTop(parent_rect.top() - pos_in_parent.y())
                if pos_in_parent.x() + new_rect.right() > parent_rect.right():
                    new_rect.setRight(parent_rect.right() - pos_in_parent.x())
                if pos_in_parent.y() + new_rect.bottom() > parent_rect.bottom():
                    new_rect.setBottom(parent_rect.bottom() - pos_in_parent.y())
            
            self.set_rect(new_rect)
            event.accept()
            return
            
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.is_resizing = False
        super().mouseReleaseEvent(event)


class CropHandle(QGraphicsObject):
    """Small handle for resizing crop rect"""
    from PyQt6.QtCore import pyqtSignal
    handle_moved = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable | 
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rect = QRectF(-10, -10, 20, 20)

    def boundingRect(self):
        return self._rect

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor("#3b82f6")))
        painter.setPen(QPen(Qt.GlobalColor.white, 2))
        painter.drawEllipse(self._rect)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if self.parentItem():
                rect = self.parentItem().boundingRect()
                val = value 
                x = max(0, min(val.x(), rect.width()))
                y = max(0, min(val.y(), rect.height()))
                new_pos = QPointF(x, y)
                self.handle_moved.emit()
                return new_pos
        return super().itemChange(change, value)
