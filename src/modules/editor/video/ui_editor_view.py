
from PyQt6.QtWidgets import QGraphicsView, QFrame
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QBrush, QColor, QTransform
from .ui_editor_items import OverlayGraphicsItem

class EditorGraphicsView(QGraphicsView):
    """
    Subclass with Zoom and Pan support like in Sorter Viewer.
    """
    def __init__(self, parent=None, editor_widget=None):
        super().__init__(parent)
        self.editor_widget = editor_widget  # Сохраняем ссылку на VideoEditorWidget
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setBackgroundBrush(QBrush(QColor("#000")))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._initial_fit = True

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Find item under mouse
            item = self.itemAt(event.position().toPoint())
            # If we clicked the video item directly or empty space or the preview overlay, но не по элементам управления кадрированием
            if self.editor_widget:
                # Проверяем, что клик не был по элементам управления
                is_control = False
                
                # Check for Overlay Items (Resize Handles are children usually, but itemAt might pick them)
                if item and isinstance(item, OverlayGraphicsItem):
                    pass # Handled by item
                
                # Crop controls check
                if hasattr(self.editor_widget, 'crop_drag_rect') and item == self.editor_widget.crop_drag_rect:
                    is_control = True
                if hasattr(self.editor_widget, 'handle_tl') and item == self.editor_widget.handle_tl:
                    is_control = True
                if hasattr(self.editor_widget, 'handle_br') and item == self.editor_widget.handle_br:
                    is_control = True

                # Если клик был по видео или пустому месту (но не по элементам управления), запускаем play/pause
                # Также игнорируем клик по OverlayGraphicsItem, чтобы не сбивать выделение
                if not is_control and not isinstance(item, OverlayGraphicsItem):
                    if not item or (hasattr(self.editor_widget, 'video_item') and item == self.editor_widget.video_item) or (hasattr(self.editor_widget, 'preview_item') and item == self.editor_widget.preview_item):
                        is_cropping = getattr(self.editor_widget, 'is_cropping', False)
                        if not is_cropping and hasattr(self.editor_widget, 'toggle_play'):
                            self.editor_widget.toggle_play()
        super().mouseReleaseEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.reset_zoom()
        super().mousePressEvent(event)

    def reset_zoom(self):
        self.resetTransform()
        if self.scene() and self.scene().sceneRect().isValid():
            rect = self.scene().sceneRect()
            self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
            self.centerOn(rect.center())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Only fit automatically if we were already in "fit" mode or it's the first time
        if self._initial_fit:
            self.reset_zoom()
