
from PyQt6.QtWidgets import QGraphicsView, QFrame
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QMouseEvent, QWheelEvent, QColor

class ClickableGraphicsView(QGraphicsView):
    clicked = pyqtSignal()
    double_clicked = pyqtSignal()
    middle_clicked = pyqtSignal()
    right_clicked = pyqtSignal()
    mouse_moved = pyqtSignal(object)

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self._click_start_pos = None
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        # Optimization
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        # Scrollbars off
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setBackgroundBrush(QColor("#000000"))

    def wheelEvent(self, event: QWheelEvent):
        # Zoom logic
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # If Ctrl is held, standard behavior (optional, usually scaling)
            super().wheelEvent(event)
        else:
            # Standard wheel zoom
            factor = 1.15
            if event.angleDelta().y() < 0:
                factor = 1.0 / factor
            self.scale(factor, factor)
            event.accept()

    def mousePressEvent(self, event: QMouseEvent):
        self._click_start_pos = event.pos()
        if event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit()
            # Do not propagate right click to prevent context menu if implemented later on view
            event.accept()
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.middle_clicked.emit()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self._click_start_pos:
            dist = (event.pos() - self._click_start_pos).manhattanLength()
            if dist < 5: 
                self.clicked.emit()
        self._click_start_pos = None

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)


from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtCore import pyqtSignal

class ClickableVideoWidget(QVideoWidget):
    clicked = pyqtSignal()
    double_clicked = pyqtSignal()
    middle_clicked = pyqtSignal()
    right_clicked = pyqtSignal()
    mouse_moved = pyqtSignal(object)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setStyleSheet("background-color: transparent; border: none;")
        
    def mousePressEvent(self, event):
        from PyQt6.QtCore import Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.middle_clicked.emit()
        elif event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit()
        super().mousePressEvent(event)
        
    def mouseMoveEvent(self, event):
        self.mouse_moved.emit(event)
        super().mouseMoveEvent(event)
        
    def mouseDoubleClickEvent(self, event):
        from PyQt6.QtCore import Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)
