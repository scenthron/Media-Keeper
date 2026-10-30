from config import AppContext

from PyQt6.QtWidgets import QGraphicsObject, QGraphicsItem

from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer, pyqtSignal, QSizeF

from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QPixmap, QMovie, QFont, QFontMetrics, QImage

from PyQt6.QtMultimedia import QVideoSink, QVideoFrame



class VideoGraphicsItem(QGraphicsObject):

    """

    Надежный графический элемент видео на базе QVideoSink.

    Исключает внутренние C++ баги масштабирования и обрезки QGraphicsVideoItem при поворотах.

    """

    nativeSizeChanged = pyqtSignal(QSizeF)



    def __init__(self, parent=None):

        super().__init__(parent)

        self._sink = QVideoSink(self)

        self._sink.videoFrameChanged.connect(self._on_frame_changed)

        self._frame_image = QImage()

        self._native_size = QSizeF(0, 0)

        self._size = QSizeF(0, 0)



    def videoSink(self):

        return self._sink



    def _on_frame_changed(self, frame: QVideoFrame):

        if frame.isValid():

            img = frame.toImage()

            if not img.isNull():

                self._frame_image = img

                new_native = QSizeF(img.width(), img.height())

                if self._native_size != new_native:

                    self._native_size = new_native

                    self.nativeSizeChanged.emit(self._native_size)

                self.update()



    def setSize(self, size: QSizeF):

        if self._size != size:

            self.prepareGeometryChange()

            self._size = size

            self.update()



    def size(self) -> QSizeF:

        return self._size if self._size.isValid() and not self._size.isEmpty() else self._native_size



    def nativeSize(self) -> QSizeF:

        return self._native_size



    def boundingRect(self) -> QRectF:

        s = self.size()

        return QRectF(0, 0, s.width(), s.height())



    def paint(self, painter: QPainter, option, widget=None):

        if not self._frame_image.isNull():

            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

            painter.drawImage(self.boundingRect(), self._frame_image)





class OverlayGraphicsItem(QGraphicsObject):

    """

    Интерактивный элемент наложения (Рисунок, Регион или Размытие).

    """

    geometry_changed = pyqtSignal()

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

            self.setToolTip("Потяните для изменения размера (Shift для пропорций)" if AppContext.is_ru() else "Drag to resize (Shift to keep proportions)")

        elif handles['tr'].contains(pos) or handles['bl'].contains(pos):

            cursor = Qt.CursorShape.SizeBDiagCursor

            self.hover_handle = 'tr' if handles['tr'].contains(pos) else 'bl'

            self.setToolTip("Потяните для изменения размера (Shift для пропорций)" if AppContext.is_ru() else "Drag to resize (Shift to keep proportions)")

        elif self._rect.contains(pos):

            cursor = Qt.CursorShape.SizeAllCursor

            self.setToolTip("Перетащите для перемещения" if AppContext.is_ru() else "Drag to move")

        else:

            cursor = Qt.CursorShape.ArrowCursor

            self.setToolTip("")

            

        self.setCursor(cursor)

        super().hoverMoveEvent(event)



    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.isSelected() and self.hover_handle:
                self.is_resizing = True
                s_pos = event.scenePos() if hasattr(event, 'scenePos') else event.pos()
                self.resize_start_scene_pos = QPointF(s_pos)
                self.resize_start_pos = QPointF(event.pos())
                self.resize_start_item_pos = QPointF(self.pos())
                self.resize_start_rect = QRectF(self._rect)
                self.resize_start_size = QSizeF(self._rect.size())
                event.accept()
                return
        try:
            super().mousePressEvent(event)
        except TypeError:
            pass

    def mouseMoveEvent(self, event):
        if self.is_resizing:
            scene_pos_val = None
            if hasattr(event, 'scenePosition'):
                scene_pos_val = event.scenePosition()
            elif hasattr(event, 'scenePos'):
                scene_pos_val = event.scenePos() if callable(event.scenePos) else event.scenePos
            pos_val = event.pos() if callable(getattr(event, 'pos', None)) else getattr(event, 'pos', None)

            if getattr(self, 'resize_start_scene_pos', None) is not None and scene_pos_val is not None:
                diff = QPointF(scene_pos_val) - self.resize_start_scene_pos
            elif getattr(self, 'resize_start_pos', None) is not None and pos_val is not None:
                diff = QPointF(pos_val) - self.resize_start_pos
            else:
                diff = QPointF(0.0, 0.0)

            start_item_pos = getattr(self, 'resize_start_item_pos', self.pos())
            start_x = start_item_pos.x()
            start_y = start_item_pos.y()
            if hasattr(self, 'resize_start_size'):
                start_w = self.resize_start_size.width()
                start_h = self.resize_start_size.height()
            elif hasattr(self, 'resize_start_rect'):
                start_w = self.resize_start_rect.width()
                start_h = self.resize_start_rect.height()
            else:
                start_w = self._rect.width()
                start_h = self._rect.height()

            # Проверяем зажатие Shift или Ctrl для пропорционального изменения размера (как в Photoshop)
            keep_aspect = bool(event.modifiers() & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier))

            if keep_aspect:
                if self._mode == "image" and self._pixmap and not self._pixmap.isNull():
                    aspect = float(self._pixmap.width()) / max(1.0, float(self._pixmap.height()))
                else:
                    aspect = start_w / max(1.0, start_h)

                if self.hover_handle == 'br':
                    cand_w = max(10.0, start_w + diff.x())
                    cand_h = max(10.0, start_h + diff.y())
                    if abs(diff.x() / max(1.0, start_w)) >= abs(diff.y() / max(1.0, start_h)):
                        final_w = cand_w
                        final_h = final_w / aspect
                    else:
                        final_h = cand_h
                        final_w = final_h * aspect
                    new_x = start_x
                    new_y = start_y

                elif self.hover_handle == 'tl':
                    cand_w = max(10.0, start_w - diff.x())
                    cand_h = max(10.0, start_h - diff.y())
                    if abs(diff.x() / max(1.0, start_w)) >= abs(diff.y() / max(1.0, start_h)):
                        final_w = cand_w
                        final_h = final_w / aspect
                    else:
                        final_h = cand_h
                        final_w = final_h * aspect
                    new_x = start_x + (start_w - final_w)
                    new_y = start_y + (start_h - final_h)

                elif self.hover_handle == 'tr':
                    cand_w = max(10.0, start_w + diff.x())
                    cand_h = max(10.0, start_h - diff.y())
                    if abs(diff.x() / max(1.0, start_w)) >= abs(diff.y() / max(1.0, start_h)):
                        final_w = cand_w
                        final_h = final_w / aspect
                    else:
                        final_h = cand_h
                        final_w = final_h * aspect
                    new_x = start_x
                    new_y = start_y + (start_h - final_h)

                elif self.hover_handle == 'bl':
                    cand_w = max(10.0, start_w - diff.x())
                    cand_h = max(10.0, start_h + diff.y())
                    if abs(diff.x() / max(1.0, start_w)) >= abs(diff.y() / max(1.0, start_h)):
                        final_w = cand_w
                        final_h = final_w / aspect
                    else:
                        final_h = cand_h
                        final_w = final_h * aspect
                    new_x = start_x + (start_w - final_w)
                    new_y = start_y

            else:
                if self.hover_handle == 'br':
                    final_w = max(10.0, start_w + diff.x())
                    final_h = max(10.0, start_h + diff.y())
                    new_x = start_x
                    new_y = start_y
                elif self.hover_handle == 'tl':
                    final_w = max(10.0, start_w - diff.x())
                    final_h = max(10.0, start_h - diff.y())
                    new_x = start_x + (start_w - final_w)
                    new_y = start_y + (start_h - final_h)
                elif self.hover_handle == 'tr':
                    final_w = max(10.0, start_w + diff.x())
                    final_h = max(10.0, start_h - diff.y())
                    new_x = start_x
                    new_y = start_y + (start_h - final_h)
                elif self.hover_handle == 'bl':
                    final_w = max(10.0, start_w - diff.x())
                    final_h = max(10.0, start_h + diff.y())
                    new_x = start_x + (start_w - final_w)
                    new_y = start_y

            # Ограничиваем пределами видео-родителя (parentItem)
            if self.parentItem():
                p_rect = self.parentItem().boundingRect()
                new_x = max(p_rect.left(), min(new_x, p_rect.right() - final_w))
                new_y = max(p_rect.top(), min(new_y, p_rect.bottom() - final_h))
                final_w = min(final_w, p_rect.width())
                final_h = min(final_h, p_rect.height())

            self.setPos(new_x, new_y)
            self.set_rect(QRectF(0, 0, final_w, final_h))
            event.accept()
            return

        try:
            super().mouseMoveEvent(event)
        except TypeError:
            pass

    def mouseReleaseEvent(self, event):
        was_resizing = self.is_resizing
        self.is_resizing = False
        try:
            super().mouseReleaseEvent(event)
        except TypeError:
            pass
        self.geometry_changed.emit()





class CropFrameItem(QGraphicsObject):

    """

    Контрастная анимированная рамка кадрирования («марширующие муравьи»)

    со встроенной сеткой «Правило третей» (3x3) и эстетичными зазорами

    перед угловыми L-маркерами и центральными дефисами.

    """

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setZValue(25)

        self._rect = QRectF(0, 0, 0, 0)

        self._dash_offset = 0

        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)



    def boundingRect(self):

        return self._rect.adjusted(-2, -2, 2, 2)



    def setRect(self, rect: QRectF):

        if self._rect != rect:

            self.prepareGeometryChange()

            self._rect = rect

            self.update()



    def advance_dash(self, step=1):

        self._dash_offset = (self._dash_offset + step) % 20

        self.update()



    def paint(self, painter, option, widget=None):

        if self._rect.isEmpty() or not self.isVisible():

            return

            

        r = self._rect

        w = r.width()

        h = r.height()

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        

        # 1. Сетка «Правило третей» (3x3)

        w3 = w / 3.0

        h3 = h / 3.0

        if w3 > 25 and h3 > 25:

            grid_pen = QPen(QColor(255, 255, 255, 55), 1, Qt.PenStyle.DotLine)

            painter.setPen(grid_pen)

            painter.drawLine(QPointF(r.left() + w3, r.top()), QPointF(r.left() + w3, r.bottom()))

            painter.drawLine(QPointF(r.left() + 2 * w3, r.top()), QPointF(r.left() + 2 * w3, r.bottom()))

            painter.drawLine(QPointF(r.left(), r.top() + h3), QPointF(r.right(), r.top() + h3))

            painter.drawLine(QPointF(r.left(), r.top() + 2 * h3), QPointF(r.right(), r.top() + 2 * h3))

            

        # 2. Отрезки бегущей зебры с отступами (зазорами) от уголков и дефисов

        # Отступ от угла: длина уголка 14px + зазор 25px = 39px

        # Отступ от центрального дефиса: полудлина дефиса 12px + зазор 25px = 37px

        corner_gap = 39.0

        edge_gap = 37.0

        

        lines_to_draw = []

        

        # Горизонтальные грани (верхняя и нижняя)

        if w > (corner_gap * 2 + edge_gap * 2 + 10):

            cx = r.center().x()

            lines_to_draw.append((QPointF(r.left() + corner_gap, r.top()), QPointF(cx - edge_gap, r.top())))

            lines_to_draw.append((QPointF(cx + edge_gap, r.top()), QPointF(r.right() - corner_gap, r.top())))

            lines_to_draw.append((QPointF(r.left() + corner_gap, r.bottom()), QPointF(cx - edge_gap, r.bottom())))

            lines_to_draw.append((QPointF(cx + edge_gap, r.bottom()), QPointF(r.right() - corner_gap, r.bottom())))

        elif w > (corner_gap * 2 + 6):

            lines_to_draw.append((QPointF(r.left() + corner_gap, r.top()), QPointF(r.right() - corner_gap, r.top())))

            lines_to_draw.append((QPointF(r.left() + corner_gap, r.bottom()), QPointF(r.right() - corner_gap, r.bottom())))

            

        # Вертикальные грани (левая и правая)

        if h > (corner_gap * 2 + edge_gap * 2 + 10):

            cy = r.center().y()

            lines_to_draw.append((QPointF(r.left(), r.top() + corner_gap), QPointF(r.left(), cy - edge_gap)))

            lines_to_draw.append((QPointF(r.left(), cy + edge_gap), QPointF(r.left(), r.bottom() - corner_gap)))

            lines_to_draw.append((QPointF(r.right(), r.top() + corner_gap), QPointF(r.right(), cy - edge_gap)))

            lines_to_draw.append((QPointF(r.right(), cy + edge_gap), QPointF(r.right(), r.bottom() - corner_gap)))

        elif h > (corner_gap * 2 + 6):

            lines_to_draw.append((QPointF(r.left(), r.top() + corner_gap), QPointF(r.left(), r.bottom() - corner_gap)))

            lines_to_draw.append((QPointF(r.right(), r.top() + corner_gap), QPointF(r.right(), r.bottom() - corner_gap)))

            

        # Отрисовка подложки: черная сплошная линия (2px)

        black_pen = QPen(QColor(0, 0, 0, 240), 2.0, Qt.PenStyle.SolidLine)

        painter.setPen(black_pen)

        painter.setBrush(Qt.BrushStyle.NoBrush)

        for p1, p2 in lines_to_draw:

            painter.drawLine(p1, p2)

            

        # Отрисовка бегущей зебры: белый пунктир (2px)

        white_pen = QPen(QColor(255, 255, 255, 255), 2.0, Qt.PenStyle.CustomDashLine)

        white_pen.setDashPattern([5, 5])

        white_pen.setDashOffset(self._dash_offset)

        painter.setPen(white_pen)

        for p1, p2 in lines_to_draw:

            painter.drawLine(p1, p2)





class CropHandle(QGraphicsObject):

    """

    Контрастные маркеры кадрирования:

    - 4 угла ('tl', 'tr', 'bl', 'br') - стильные L-образные уголки;

    - 4 грани ('t', 'b', 'l', 'r') - центральные контрастные дефисы-манипуляторы.

    

    Управление перемещением осуществляется напрямую через mouseMoveEvent,

    что гарантирует 100% неразрывную синхронизацию положения ручек и рамки.

    """

    from PyQt6.QtCore import pyqtSignal

    handle_moved = pyqtSignal(object, QPointF)

    

    def __init__(self, parent=None, handle_type='tl', corner=None):

        super().__init__(parent)

        self.handle_type = corner if corner else handle_type

        # Не используем ItemIsMovable, чтобы избежать рассинхронизации ручки и рамки

        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)

        

        # Специализированные курсоры

        if self.handle_type in ('tl', 'br'):

            self.setCursor(Qt.CursorShape.SizeFDiagCursor)

        elif self.handle_type in ('tr', 'bl'):

            self.setCursor(Qt.CursorShape.SizeBDiagCursor)

        elif self.handle_type in ('t', 'b'):

            self.setCursor(Qt.CursorShape.SizeVerCursor)

        elif self.handle_type in ('l', 'r'):

            self.setCursor(Qt.CursorShape.SizeHorCursor)

        else:

            self.setCursor(Qt.CursorShape.PointingHandCursor)

            

        self.setZValue(30)

        self._rect = QRectF(-14, -14, 28, 28)

        self.is_dragging = False



    def boundingRect(self):

        return self._rect



    def mousePressEvent(self, event):

        if event.button() == Qt.MouseButton.LeftButton:

            self.is_dragging = True

            event.accept()

            return

        super().mousePressEvent(event)



    def mouseMoveEvent(self, event):

        if self.is_dragging and (event.buttons() & Qt.MouseButton.LeftButton):

            new_pos = self.mapToParent(event.pos())

            if not self.signalsBlocked():

                self.handle_moved.emit(self, new_pos)

            event.accept()

            return

        super().mouseMoveEvent(event)



    def mouseReleaseEvent(self, event):

        if event.button() == Qt.MouseButton.LeftButton:

            self.is_dragging = False

            event.accept()

            return

        super().mouseReleaseEvent(event)



    def paint(self, painter, option, widget):

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        L = 14.0

        edge_L = 12.0

        

        # Черная подложка для абсолютного контраста (толщина 4.5px)

        pen_bg = QPen(QColor(0, 0, 0, 240), 4.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin)

        painter.setPen(pen_bg)

        

        # Углы

        if self.handle_type == 'tl':

            painter.drawLine(QPointF(L, 0), QPointF(0, 0))

            painter.drawLine(QPointF(0, 0), QPointF(0, L))

        elif self.handle_type == 'br':

            painter.drawLine(QPointF(-L, 0), QPointF(0, 0))

            painter.drawLine(QPointF(0, 0), QPointF(0, -L))

        elif self.handle_type == 'tr':

            painter.drawLine(QPointF(-L, 0), QPointF(0, 0))

            painter.drawLine(QPointF(0, 0), QPointF(0, L))

        elif self.handle_type == 'bl':

            painter.drawLine(QPointF(L, 0), QPointF(0, 0))

            painter.drawLine(QPointF(0, 0), QPointF(0, -L))

        # Боковые дефисы

        elif self.handle_type in ('t', 'b'):

            painter.drawLine(QPointF(-edge_L, 0), QPointF(edge_L, 0))

        elif self.handle_type in ('l', 'r'):

            painter.drawLine(QPointF(0, -edge_L), QPointF(0, edge_L))



        # Белый основной контур (толщина 2.5px)

        pen_fg = QPen(QColor(255, 255, 255, 255), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin)

        painter.setPen(pen_fg)

        

        # Углы

        if self.handle_type == 'tl':

            painter.drawLine(QPointF(L, 0), QPointF(0, 0))

            painter.drawLine(QPointF(0, 0), QPointF(0, L))

        elif self.handle_type == 'br':

            painter.drawLine(QPointF(-L, 0), QPointF(0, 0))

            painter.drawLine(QPointF(0, 0), QPointF(0, -L))

        elif self.handle_type == 'tr':

            painter.drawLine(QPointF(-L, 0), QPointF(0, 0))

            painter.drawLine(QPointF(0, 0), QPointF(0, L))

        elif self.handle_type == 'bl':

            painter.drawLine(QPointF(L, 0), QPointF(0, 0))

            painter.drawLine(QPointF(0, 0), QPointF(0, -L))

        # Боковые дефисы

        elif self.handle_type in ('t', 'b'):

            painter.drawLine(QPointF(-edge_L, 0), QPointF(edge_L, 0))

        elif self.handle_type in ('l', 'r'):

            painter.drawLine(QPointF(0, -edge_L), QPointF(0, edge_L))



