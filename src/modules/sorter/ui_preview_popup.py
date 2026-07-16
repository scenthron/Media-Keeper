import os
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFrame, QLabel,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QDialog, QMenu, QDoubleSpinBox, QGraphicsOpacityEffect
)
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, pyqtSignal, QSize, QUrl, QPoint, QSizeF, QRect
from PyQt6.QtGui import QPixmap, QMovie, QPainter, QIcon, QCursor, QAction, QDesktopServices, QImageReader, QKeySequence
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from typing import Any
from config import AppContext, VIEWER_DESIGN
from modules.sorter.ui_player import VideoPlayerControls, ClickableSlider, TimeOverlayWidget, SegmentIndicatorWidget
from modules.sorter.logic_player import SmartPreviewManager
from utils_io import ensure_long_path, strip_long_path_prefix
from utils_extensions import VIDEO_EXTS, AUDIO_EXTS, IMAGE_EXTS

class PopupImageViewer(QGraphicsView):
    double_clicked = pyqtSignal()
    middle_clicked = pyqtSignal()

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
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: transparent; border: none;")

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)
        self._current_rotation = 0

    def set_pixmap(self, pixmap):
        self.pixmap_item.setPixmap(pixmap)
        if not pixmap.isNull():
            self.scene.setSceneRect(self.pixmap_item.boundingRect())
        self._current_rotation = 0
        self.reset_view()
        
    def rotate(self, angle):
        self._current_rotation = (self._current_rotation + angle) % 360
        self.reset_view()

    def reset_view(self):
        if not self.pixmap_item.pixmap().isNull():
            self.resetTransform()
            if getattr(self, '_current_rotation', 0) != 0:
                super().rotate(self._current_rotation)
            self.horizontalScrollBar().setValue(0)
            self.verticalScrollBar().setValue(0)
            self.pixmap_item.setPos(0, 0)
            if hasattr(self.pixmap_item, 'setTransform'):
                from PyQt6.QtGui import QTransform
                self.pixmap_item.setTransform(QTransform())
            self.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
            self.centerOn(self.pixmap_item)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reset_view()

    def wheelEvent(self, event):
        factor = 1.15
        if event.angleDelta().y() < 0:
            factor = 1.0 / factor
        self.scale(factor, factor)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.middle_clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class PopupVideoViewer(QGraphicsView):
    double_clicked = pyqtSignal()
    middle_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: transparent; border: none;")

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem
        self.video_item = QGraphicsVideoItem()
        self.scene.addItem(self.video_item)
        self.video_item.nativeSizeChanged.connect(self._on_native_size_changed)
        self._current_rotation = 0
        
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
            btn.setFixedSize(50, 100)
            from PyQt6.QtGui import QCursor
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.hide()
            
        self.btn_seg_prev.clicked.connect(self._on_seg_prev)
        self.btn_seg_next.clicked.connect(self._on_seg_next)
        
        # We must enable mouse tracking to catch hover
        self.setMouseTracking(True)

    def _on_seg_prev(self):
        win = self.window()
        if hasattr(win, 'smart_preview_mgr'):
            win.smart_preview_mgr.skip_prev()
            
    def _on_seg_next(self):
        win = self.window()
        if hasattr(win, 'smart_preview_mgr'):
            win.smart_preview_mgr.skip_next()
            
    def update_segment_indicator(self):
        win = self.window()
        if not hasattr(win, 'smart_preview_mgr'): return
        mgr = win.smart_preview_mgr
        
        if mgr and mgr.num_segments > 0:
            if mgr.active and not mgr.user_paused:
                self.btn_seg_prev.show()
                self.btn_seg_next.show()
            else:
                self.btn_seg_prev.hide()
                self.btn_seg_next.hide()
        else:
            self.btn_seg_prev.hide()
            self.btn_seg_next.hide()
            
        if hasattr(win, 'update_segment_indicator'):
            win.update_segment_indicator()

    def _on_native_size_changed(self, size):
        if size.isValid():
            self.video_item.setSize(size)
            self.scene.setSceneRect(QRectF(QPointF(0, 0), size))
            self.reset_view()

    def rotate(self, angle):
        self._current_rotation = (self._current_rotation + angle) % 360
        self.reset_view()

    def reset_view(self):
        content_rect = self.scene.sceneRect()
        if content_rect.width() > 0 and content_rect.height() > 0:
            self.resetTransform()
            if getattr(self, '_current_rotation', 0) != 0:
                super().rotate(self._current_rotation)
            self.horizontalScrollBar().setValue(0)
            self.verticalScrollBar().setValue(0)
            self.video_item.setPos(0, 0)
            if hasattr(self.video_item, 'setTransform'):
                from PyQt6.QtGui import QTransform
                self.video_item.setTransform(QTransform())
            self.fitInView(self.video_item, Qt.AspectRatioMode.KeepAspectRatio)
            self.centerOn(self.video_item)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reset_view()
        if hasattr(self, 'btn_seg_prev'):
            self.btn_seg_prev.move(10, event.size().height() // 2 - self.btn_seg_prev.height() // 2)
            self.btn_seg_next.move(event.size().width() - self.btn_seg_next.width() - 10, event.size().height() // 2 - self.btn_seg_next.height() // 2)
            self.btn_seg_prev.raise_()
            self.btn_seg_next.raise_()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.middle_clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)
        
    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        
        segment_active = False
        win = self.window()
        if hasattr(win, 'smart_preview_mgr'):
            segment_active = win.smart_preview_mgr.active and win.smart_preview_mgr.num_segments > 0
            
        if segment_active:
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

    def leaveEvent(self, event):
        local_pos = self.mapFromGlobal(QCursor.pos())
        if not self.rect().contains(local_pos):
            if hasattr(self, 'btn_seg_prev'): self.btn_seg_prev.hide()
            if hasattr(self, 'btn_seg_next'): self.btn_seg_next.hide()
        super().leaveEvent(event)


class SizeSettingsPopup(QWidget):
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("SizeSettingsPopup")
        
        self.setFixedSize(190, 78)
        
        icons_dir = AppContext.find_resource_dir("icons")
        
        import tempfile
        temp_dir = tempfile.gettempdir()
        
        path_up = os.path.join(icons_dir, "chevron-up.svg").replace('\\', '/')
        path_down = os.path.join(temp_dir, "chevron-down-white.svg").replace('\\', '/')
        
        try:
            with open(path_up, "r", encoding="utf-8") as f:
                content = f.read()
            down_content = content.replace('m18 15-6-6-6 6', 'm6 9 6 6 6-6')
            with open(path_down, "w", encoding="utf-8") as f:
                f.write(down_content)
        except Exception as e:
            logging.error(f"Failed to create chevron-down-white.svg: {e}")
            path_down = path_up

        self.setStyleSheet(f"""
            #SizeSettingsPopup {{
                background-color: #222222;
                border: 1px solid #444;
                border-radius: 6px;
            }}
            QLabel {{
                color: #ccc;
                font-size: 11px;
                font-weight: bold;
                background: transparent;
            }}
            QPushButton {{
                background-color: #333;
                color: white;
                border: 1px solid #555;
                border-radius: 3px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(59, 130, 246, 0.4);
                border: 1px solid #3b82f6;
                color: white;
            }}
            QPushButton:pressed {{
                background-color: rgba(59, 130, 246, 0.6);
            }}
            QDoubleSpinBox {{
                background-color: #333;
                color: white;
                border: 1px solid #555;
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
                padding-left: 4px;
            }}
            QDoubleSpinBox:focus {{
                border: 1px solid #3b82f6;
            }}
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
                width: 16px;
                background: #2a2a2a;
                border: none;
            }}
            QDoubleSpinBox::up-button {{
                border-top-right-radius: 2px;
            }}
            QDoubleSpinBox::down-button {{
                border-bottom-right-radius: 2px;
            }}
            QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
                background: #444;
            }}
            QDoubleSpinBox::up-arrow {{
                image: url('{path_up}');
                width: 10px;
                height: 10px;
            }}
            QDoubleSpinBox::down-arrow {{
                image: url('{path_down}');
                width: 10px;
                height: 10px;
            }}
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(6)
        
        row_size = QHBoxLayout()
        row_size.setSpacing(6)
        
        self.lbl_title = QLabel("Размер:" if AppContext.LANG == "RU" else "Size:")
        row_size.addWidget(self.lbl_title)
        
        self.btn_zoom_out = QPushButton()
        self.btn_zoom_out.setIcon(QIcon(os.path.join(icons_dir, "minus_menu.svg")))
        self.btn_zoom_out.setIconSize(QSize(14, 14))
        self.btn_zoom_out.setFixedSize(24, 24)
        self.btn_zoom_out.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_zoom_out.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_zoom_out.setToolTip("Уменьшить масштаб окна предпросмотра" if AppContext.LANG == "RU" else "Decrease preview window size")
        row_size.addWidget(self.btn_zoom_out)
        
        self.btn_zoom_in = QPushButton()
        self.btn_zoom_in.setIcon(QIcon(os.path.join(icons_dir, "plus_menu.svg")))
        self.btn_zoom_in.setIconSize(QSize(14, 14))
        self.btn_zoom_in.setFixedSize(24, 24)
        self.btn_zoom_in.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_zoom_in.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_zoom_in.setToolTip("Увеличить размер окна предпросмотра" if AppContext.LANG == "RU" else "Increase preview window size")
        row_size.addWidget(self.btn_zoom_in)
        
        row_size.addSpacing(4)
        
        self.btn_reset = QPushButton()
        self.btn_reset.setIcon(QIcon(os.path.join(icons_dir, "rotate_left.svg")))
        self.btn_reset.setIconSize(QSize(14, 14))
        self.btn_reset.setFixedSize(24, 24)
        self.btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_reset.setToolTip("Сбросить размер окна предпросмотра" if AppContext.LANG == "RU" else "Reset preview window size")
        row_size.addWidget(self.btn_reset)
        
        main_layout.addLayout(row_size)
        
        row_delay = QHBoxLayout()
        row_delay.setSpacing(6)
        
        self.lbl_delay = QLabel("Задержка:" if AppContext.LANG == "RU" else "Delay:")
        row_delay.addWidget(self.lbl_delay)
        
        self.spin_delay = QDoubleSpinBox()
        self.spin_delay.setRange(0.0, 10.0)
        self.spin_delay.setSingleStep(0.1)
        self.spin_delay.setDecimals(1)
        self.spin_delay.setFixedSize(65, 24)
        
        tooltip = (
            "Задержка появления окна быстрого просмотра при наведении курсора на файл (от 0.0 до 10.0 секунд)."
            if AppContext.LANG == "RU"
            else "Delay before showing the quick preview window on item hover (from 0.0 to 10.0 seconds)."
        )
        self.lbl_delay.setToolTip(tooltip)
        self.spin_delay.setToolTip(tooltip)
        
        main_app = parent.main_app if parent else None
        initial_delay = 0.4
        if main_app and hasattr(main_app, 'config'):
            initial_delay = float(main_app.config.get("hover_delay", 0.4))
        self.spin_delay.setValue(initial_delay)
        row_delay.addWidget(self.spin_delay)
        
        main_layout.addLayout(row_delay)
        
        if parent:
            self.btn_zoom_out.clicked.connect(lambda: parent.change_popup_size(-1))
            self.btn_zoom_in.clicked.connect(lambda: parent.change_popup_size(1))
            self.btn_reset.clicked.connect(parent.reset_popup_size)
            self.spin_delay.valueChanged.connect(self._on_delay_changed)
            
    def _on_delay_changed(self, val: float) -> None:
        parent = self.parent()
        main_app = parent.main_app if parent else None
        if main_app and hasattr(main_app, 'config'):
            main_app.config["hover_delay"] = val
            from modules.sorter.logic_config import ConfigManager
            ConfigManager.save(main_app.config)
            if AppContext.LANG == "RU":
                logging.info(f"Параметр задержки ховера {val} с успешно сохранен в settings.ini")
            else:
                logging.info(f"Hover delay setting {val} s successfully saved to settings.ini")

    def hideEvent(self, event):
        self.closed.emit()
        super().hideEvent(event)


class LargePreviewPopup(QDialog):
    def __init__(self, filepath: str, main_app: Any = None, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.filepath: str = ensure_long_path(filepath)
        self.main_app: Any = main_app
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        
        icons_dir_global = AppContext.find_resource_dir("icons")
        self.icon_settings = QIcon(os.path.join(icons_dir_global, "settings.svg"))
        self.icon_unchecked = QIcon(os.path.join(icons_dir_global, "checkbox_unchecked.svg"))
        self.icon_checked = QIcon(os.path.join(icons_dir_global, "checkbox_checked.svg"))
        self.icon_reset_view = QIcon(os.path.join(icons_dir_global, "reset_view.svg"))
        self.icon_rot_l = QIcon(os.path.join(icons_dir_global, "rotate_left.svg"))
        self.icon_rot_r = QIcon(os.path.join(icons_dir_global, "rotate_right.svg"))
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                border: 2px solid #3b82f6;
                border-radius: 8px;
            }
            QLabel {
                color: #dddddd;
            }
        """)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(2, 2, 2, 2)
        self.layout.setSpacing(0)
        
        self.top_overlay = QWidget(self)
        self.top_overlay.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(15, 15, 15, 0.42), stop:0.7 rgba(15, 15, 15, 0.20), stop:1 rgba(15, 15, 15, 0));
        """)
        self.top_overlay.installEventFilter(self)
        top_layout = QHBoxLayout(self.top_overlay)
        top_layout.setContentsMargins(4, 1, 4, 0)
        top_layout.setSpacing(10)
        
        self.btn_reset_view = QPushButton(self.top_overlay)
        self.btn_reset_view.setFixedSize(22, 22)
        self.btn_reset_view.setIconSize(QSize(14, 14))
        self.btn_reset_view.setIcon(self.icon_reset_view)
        self.btn_reset_view.setToolTip("Сбросить вид" if AppContext.LANG == "RU" else "Reset View")
        self.btn_reset_view.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.12);
                color: #dddddd;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 4px;
                font-size: 14px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: rgba(59, 130, 246, 0.4);
                border: 1px solid #3b82f6;
                color: white;
            }
            QPushButton:pressed {
                background-color: rgba(59, 130, 246, 0.6);
            }
        """)
        sp = self.btn_reset_view.sizePolicy()
        sp.setRetainSizeWhenHidden(False)
        self.btn_reset_view.setSizePolicy(sp)
        self.btn_reset_view.hide()
        top_layout.addWidget(self.btn_reset_view, alignment=Qt.AlignmentFlag.AlignTop)
        
        from modules.sorter.ui_player import SegmentIndicatorWidget
        self.segment_indicator = SegmentIndicatorWidget(self.top_overlay, is_small=True)
        sp2 = self.segment_indicator.sizePolicy()
        sp2.setRetainSizeWhenHidden(False)
        self.segment_indicator.setSizePolicy(sp2)
        self.segment_indicator.hide()
        self.segment_indicator.clicked.connect(self._on_segment_indicator_clicked)
        top_layout.addWidget(self.segment_indicator, alignment=Qt.AlignmentFlag.AlignTop)
        
        self.lbl_title = QLabel(os.path.basename(filepath), self.top_overlay)
        self.lbl_title.setStyleSheet("color: white; font-weight: bold; font-size: 12px; background: transparent;")
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_opacity_effect = QGraphicsOpacityEffect(self.lbl_title)
        self.title_opacity_effect.setOpacity(1.0)
        self.lbl_title.setGraphicsEffect(self.title_opacity_effect)
        top_layout.addWidget(self.lbl_title, stretch=1)
        
        self.right_btn_container = QWidget(self)
        self.right_btn_container.setStyleSheet("background: transparent;")
        right_layout = QVBoxLayout(self.right_btn_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        
        icons_dir_global = AppContext.find_resource_dir("icons")
        self.icon_settings = QIcon(os.path.join(icons_dir_global, "settings.svg"))
        self.icon_unchecked = QIcon(os.path.join(icons_dir_global, "checkbox_unchecked.svg"))
        self.icon_checked = QIcon(os.path.join(icons_dir_global, "checkbox_checked.svg"))

        self.btn_settings = QPushButton(self.right_btn_container)
        self.btn_settings.setFixedSize(22, 22)
        self.btn_settings.setIconSize(QSize(14, 14))
        self.btn_settings.setIcon(self.icon_settings)
        self.btn_settings.setCheckable(True)
        self.btn_settings.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.12);
                color: #dddddd;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 4px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: rgba(59, 130, 246, 0.4);
                border: 1px solid #3b82f6;
                color: white;
            }
            QPushButton:checked {
                background-color: #3b82f6;
                color: white;
                border-color: #3b82f6;
            }
            QPushButton:pressed {
                background-color: rgba(59, 130, 246, 0.6);
            }
        """)
        self.btn_settings.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.setToolTip("Настройки размера окна" if AppContext.LANG == "RU" else "Window size settings")
        right_layout.addWidget(self.btn_settings)
        
        self.btn_select_file = QPushButton(self.right_btn_container)
        self.btn_select_file.setFixedSize(22, 22)
        self.btn_select_file.setIconSize(QSize(14, 14))
        self.btn_select_file.setIcon(self.icon_unchecked)
        self.btn_select_file.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.12);
                color: #dddddd;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 4px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: rgba(59, 130, 246, 0.4);
                border: 1px solid #3b82f6;
                color: white;
            }
            QPushButton:pressed {
                background-color: rgba(59, 130, 246, 0.6);
            }
        """)
        self.btn_select_file.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_select_file.setCursor(Qt.CursorShape.PointingHandCursor)
        right_layout.addWidget(self.btn_select_file)
        
        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.content_area, stretch=1)
        
        ext = os.path.splitext(filepath)[1].lower()
        self.media_player = None
        self.audio_output = None
        self.movie = None
        
        speed = 1.0
        loop = False
        apply_all = False
        loop = False
        segment_view = False
        volume_pct = 10
        self._context_menu_active = False
        self._click_start_pos = None
        
        if self.main_app:
            apply_all = AppContext.session_all_videos_active
            if apply_all:
                loop = AppContext.session_loop
                segment_view = AppContext.session_segment_view
            volume_pct = int(getattr(self.main_app, 'global_volume', 1.0) * 100)
        
        # Проверяем, поддерживает ли файл анимацию (например, GIF или анимированный WebP)
        reader = QImageReader(filepath)
        is_animated = reader.supportsAnimation() and reader.imageCount() > 1
        logging.info(f"[LargePreviewPopup] File: {os.path.basename(filepath)}, supportsAnimation: {reader.supportsAnimation()}, imageCount: {reader.imageCount()}, resolved is_animated: {is_animated}")
        
        if is_animated:
            self.lbl_media = QLabel()
            self.lbl_media.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lbl_media.installEventFilter(self)
            
            from PyQt6.QtWidgets import QSizePolicy
            self.lbl_media.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
            
            self.content_layout.addWidget(self.lbl_media)
            
            self.movie = QMovie(filepath)
            self.lbl_media.setMovie(self.movie)
            
            self._gif_size_initialized = False
            self.movie.frameChanged.connect(self._on_gif_frame_changed)
            
            self.movie.start()
            
        elif ext in ['.png', '.jpg', '.jpeg', '.bmp', '.webp', '.gif', '.tiff', '.tif', '.heic', '.avif', '.apng', '.jfif']:
            self.media_viewer = PopupImageViewer()
            self.media_viewer.double_clicked.connect(self.open_file_system)
            self.media_viewer.middle_clicked.connect(self.open_folder_with_file)
            self.content_layout.addWidget(self.media_viewer)
            
            pixmap = QPixmap(filepath)
            self.media_viewer.set_pixmap(pixmap)
            self.btn_reset_view.show()
            self.btn_reset_view.clicked.connect(self.media_viewer.reset_view)
            
            if self.main_app and hasattr(self.main_app, 'viewer') and hasattr(self.main_app.viewer, 'file_rotations'):
                norm_path = os.path.normpath(self.filepath)
                angle = self.main_app.viewer.file_rotations.get(norm_path, 0)
                if angle != 0:
                    self.media_viewer.rotate(angle)
            
            self.bottom_overlay = QWidget(self)
            self.bottom_overlay.setStyleSheet("background: transparent;")
            bottom_layout = QHBoxLayout(self.bottom_overlay)
            bottom_layout.setContentsMargins(0, 0, 0, 0)
            bottom_layout.setSpacing(6)
            
            self.btn_rot_l = QPushButton(self.bottom_overlay)
            self.btn_rot_l.setIconSize(QSize(16, 16))
            self.btn_rot_l.setIcon(self.icon_rot_l)
            
            self.btn_rot_r = QPushButton(self.bottom_overlay)
            self.btn_rot_r.setIconSize(QSize(16, 16))
            self.btn_rot_r.setIcon(self.icon_rot_r)
            
            rot_style = """
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.12);
                    color: #dddddd;
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    border-radius: 4px;
                    font-size: 14px;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: rgba(59, 130, 246, 0.4);
                    border: 1px solid #3b82f6;
                    color: white;
                }
                QPushButton:pressed {
                    background-color: rgba(59, 130, 246, 0.6);
                }
            """
            
            for b in [self.btn_rot_l, self.btn_rot_r]:
                b.setFixedSize(30, 30)
                b.setStyleSheet(rot_style)
                b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                bottom_layout.addWidget(b)
                
            self.btn_rot_l.setToolTip("Повернуть против часовой стрелки" if AppContext.LANG == "RU" else "Rotate counter-clockwise")
            self.btn_rot_r.setToolTip("Повернуть по часовой стрелке" if AppContext.LANG == "RU" else "Rotate clockwise")
            
            self.btn_rot_l.clicked.connect(lambda: self.rotate_popup_view(-90))
            self.btn_rot_r.clicked.connect(lambda: self.rotate_popup_view(90))
            
            bottom_layout.addStretch(1)
            
        elif ext in VIDEO_EXTS:
            self.video_viewer = PopupVideoViewer()
            self.video_viewer.double_clicked.connect(self.open_file_system)
            self.video_viewer.middle_clicked.connect(self.open_folder_with_file)
            self.video_viewer.installEventFilter(self)
            self.content_layout.addWidget(self.video_viewer)
            
            self.media_player = QMediaPlayer()
            self.audio_output = QAudioOutput()
            self.media_player.setAudioOutput(self.audio_output)
            self.media_player.setVideoOutput(self.video_viewer.video_item)
            self.media_player.mediaStatusChanged.connect(self._on_media_status_changed_popup)
            
            self.controls = VideoPlayerControls()
            self._install_key_event_filters(self.controls)
            
            self.media_player.positionChanged.connect(self.controls.update_position)
            self.media_player.positionChanged.connect(self._update_overlay_time)
            self.media_player.durationChanged.connect(self.controls.update_duration)
            self.media_player.durationChanged.connect(self._update_overlay_duration)
            self.media_player.durationChanged.connect(self._on_media_duration_changed)
            self.media_player.playbackStateChanged.connect(self._on_playback_state_changed)
            
            self.controls.seek_requested.connect(self.media_player.setPosition)
            self.controls.seek_moved.connect(self.media_player.setPosition)
            self.controls.seek_drag_start.connect(self._on_scrub_start)
            self.controls.seek_drag_stop.connect(self._on_scrub_stop)
            self.controls.play_pause_clicked.connect(self.toggle_playback)
            self.controls.volume_changed.connect(self.change_volume)
            
            self.controls.speed_changed.connect(self.on_speed_changed)
            self.controls.loop_toggled.connect(self.on_loop_toggled)
            self.controls.apply_all_toggled.connect(self.on_apply_all_toggled)
            
            self.smart_preview_mgr = SmartPreviewManager(self.media_player, lambda: float(AppContext.session_video_speed) if apply_all else 1.0)
            self.smart_preview_mgr.set_active(segment_view)
            
            self.layout.addWidget(self.controls)
            
            self.time_overlay = TimeOverlayWidget(self)
            self.time_overlay.show()
            self.time_overlay.adjustSize()
            self.resizeEvent(None)
            
            if apply_all:
                speed = float(AppContext.session_video_speed)
            else:
                speed = 1.0
                
            self.controls.set_popup_values(speed, loop, apply_all, is_video=True)
            
            self.media_player.stop()
            from utils_io import strip_long_path_prefix
            clean_path = strip_long_path_prefix(filepath)
            self.media_player.setSource(QUrl.fromLocalFile(clean_path))
            self.audio_output.setVolume(volume_pct / 100.0)
            self.controls.vol_slider.setValue(volume_pct)
            self.media_player.setPlaybackRate(speed)
            self.media_player.setLoops(QMediaPlayer.Loops.Infinite if loop else QMediaPlayer.Loops.Once)
            self.media_player.play()
            
        elif ext in ['.mp3', '.wav', '.ogg', '.flac', '.m4a', '.wma']:
            track_name = os.path.splitext(os.path.basename(filepath))[0]
            self.lbl_audio = QLabel()
            self.lbl_audio.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lbl_audio.setWordWrap(True)
            self.lbl_audio.setText(f"🎵\n{track_name}")
            self.lbl_audio.setStyleSheet("""
                color: #3b82f6;
                font-size: 18px;
                font-weight: bold;
                margin: 20px;
                background: transparent;
                line-height: 1.4;
            """)
            self.lbl_audio.installEventFilter(self)
            self.content_layout.addWidget(self.lbl_audio)
            
            self.media_player = QMediaPlayer()
            self.audio_output = QAudioOutput()
            self.media_player.setAudioOutput(self.audio_output)
            
            self.controls = VideoPlayerControls()
            self._install_key_event_filters(self.controls)
            
            self.media_player.positionChanged.connect(self.controls.update_position)
            self.media_player.positionChanged.connect(self._update_overlay_time)
            self.media_player.durationChanged.connect(self.controls.update_duration)
            self.media_player.durationChanged.connect(self._update_overlay_duration)
            self.media_player.playbackStateChanged.connect(self._on_playback_state_changed)
            
            self.controls.seek_requested.connect(self.media_player.setPosition)
            self.controls.seek_moved.connect(self.media_player.setPosition)
            self.controls.play_pause_clicked.connect(self.toggle_playback)
            self.controls.volume_changed.connect(self.change_volume)
            
            self.controls.speed_changed.connect(self.on_speed_changed)
            self.controls.loop_toggled.connect(self.on_loop_toggled)
            self.controls.apply_all_toggled.connect(self.on_apply_all_toggled)
            
            self.layout.addWidget(self.controls)
            
            self.time_overlay = TimeOverlayWidget(self)
            self.time_overlay.show()
            self.time_overlay.adjustSize()
            self.resizeEvent(None)
            
            self.controls.set_popup_values(1.0, loop, False, is_video=False)
            
            self.media_player.stop()
            from utils_io import strip_long_path_prefix
            clean_path = strip_long_path_prefix(filepath)
            self.media_player.setSource(QUrl.fromLocalFile(clean_path))
            self.audio_output.setVolume(volume_pct / 100.0)
            self.controls.vol_slider.setValue(volume_pct)
            self.media_player.setPlaybackRate(1.0)
            self.media_player.setLoops(QMediaPlayer.Loops.Infinite if loop else QMediaPlayer.Loops.Once)
            self.media_player.play()
            
        self.size_settings_popup = SizeSettingsPopup(self)
        self.size_settings_popup.hide()
        self.size_settings_popup.closed.connect(self._on_size_popup_closed)
        
        self.btn_settings.clicked.connect(self.toggle_size_settings_popup)

        if self.main_app and hasattr(self.main_app, 'viewer'):
            self.main_app.viewer.selection_changed.connect(self.update_select_button_state)
            self.update_select_button_state()
        self.btn_select_file.clicked.connect(self.on_select_clicked)

    def update_select_button_state(self) -> None:
        if not self.main_app or not hasattr(self.main_app, 'viewer'):
            return
        
        viewer = self.main_app.viewer
        selected_paths = viewer.get_selected_files()
        count = len(selected_paths)
        target_path = os.path.normpath(self.filepath)
        
        if count <= 1:
            self.btn_select_file.setText("")
            self.btn_select_file.setIcon(self.icon_unchecked)
            self.btn_select_file.setToolTip(
                "Выделить этот файл" if AppContext.LANG == "RU" else "Select this file"
            )
        else:
            if target_path not in selected_paths:
                self.btn_select_file.setText("")
                self.btn_select_file.setIcon(self.icon_checked)
                self.btn_select_file.setToolTip(
                    "Добавить текущий файл к выборке" if AppContext.LANG == "RU" else "Add to selection"
                )
            else:
                self.btn_select_file.setText("")
                self.btn_select_file.setIcon(self.icon_unchecked)
                self.btn_select_file.setToolTip(
                    "Оставить выделенным только этот файл" if AppContext.LANG == "RU" else "Select only this file"
                )

    def on_select_clicked(self) -> None:
        if self.main_app and hasattr(self.main_app, 'viewer'):
            self.main_app.viewer.select_file_from_preview(self.filepath)
            self.update_select_button_state()

    def rotate_popup_view(self, angle: int) -> None:
        if not hasattr(self, 'media_viewer') or not self.media_viewer:
            return
        norm_path = os.path.normpath(self.filepath)
        if self.main_app and hasattr(self.main_app, 'viewer') and hasattr(self.main_app.viewer, 'file_rotations'):
            current_angle = self.main_app.viewer.file_rotations.get(norm_path, 0)
            new_angle = (current_angle + angle) % 360
            self.main_app.viewer.file_rotations[norm_path] = new_angle
            
            self.media_viewer.rotate(angle)
            self.main_app.viewer.update_item_preview(norm_path)
            logging.info(f"ROTATE POPUP: File {norm_path} rotated by {angle} deg. New angle: {new_angle} deg.")

    def change_popup_size(self, direction: int) -> None:
        viewer = self.main_app.viewer if (self.main_app and hasattr(self.main_app, 'viewer')) else None
        current_size = viewer.popup_size if (viewer and hasattr(viewer, 'popup_size')) else self.size()
        
        current_w = current_size.width()
        
        app_geom = None
        if self.main_app:
            app_geom = self.main_app.geometry()
        elif self.parent():
            parent_window = self.parent().window()
            if parent_window:
                app_geom = parent_window.geometry()
                
        new_w = current_w + direction * 20
        
        min_w = 320
        max_w = 1280
        if app_geom:
            max_w = app_geom.width()
            if int(max_w * 520 / 640) > app_geom.height():
                max_w = int(app_geom.height() * 640 / 520)
                
        new_w = max(min_w, min(max_w, new_w))
        new_h = int(new_w * 520 / 640)
        
        if new_w == current_size.width() and new_h == current_size.height():
            return
            
        if viewer and hasattr(viewer, 'popup_size'):
            viewer.popup_size = QSize(new_w, new_h)
            
        geom = self.geometry()
        x = geom.x()
        y = geom.y()
        
        if app_geom:
            if x + new_w > app_geom.right():
                x = app_geom.right() - new_w
            if y + new_h > app_geom.bottom():
                y = app_geom.bottom() - new_h
                
            if x < app_geom.left():
                x = app_geom.left()
            if y < app_geom.top():
                y = app_geom.top()
                
            mouse_pos = QCursor.pos()
            if mouse_pos.x() < x:
                x = max(app_geom.left(), mouse_pos.x() - 10)
            elif mouse_pos.x() > x + new_w:
                x = min(app_geom.right() - new_w, mouse_pos.x() - new_w + 10)
                
            if mouse_pos.y() < y:
                y = max(app_geom.top(), mouse_pos.y() - 10)
            elif mouse_pos.y() > y + new_h:
                y = min(app_geom.bottom() - new_h, mouse_pos.y() - new_h + 10)
                
        self.setFixedSize(new_w, new_h)
        self.move(x, y)
        logging.info(f"POPUP SIZE CHANGED: new size={new_w}x{new_h}, position=({x}, {y})")

    def reset_popup_size(self) -> None:
        viewer = self.main_app.viewer if (self.main_app and hasattr(self.main_app, 'viewer')) else None
        new_w = 640
        new_h = 520
        
        if viewer and hasattr(viewer, 'popup_size'):
            viewer.popup_size = QSize(new_w, new_h)
            
        geom = self.geometry()
        x = geom.x()
        y = geom.y()
        
        app_geom = None
        if self.main_app:
            app_geom = self.main_app.geometry()
        elif self.parent():
            parent_window = self.parent().window()
            if parent_window:
                app_geom = parent_window.geometry()
                
        if app_geom:
            if x + new_w > app_geom.right():
                x = app_geom.right() - new_w
            if y + new_h > app_geom.bottom():
                y = app_geom.bottom() - new_h
            if x < app_geom.left():
                x = app_geom.left()
            if y < app_geom.top():
                y = app_geom.top()
                
            mouse_pos = QCursor.pos()
            if mouse_pos.x() < x:
                x = max(app_geom.left(), mouse_pos.x() - 10)
            elif mouse_pos.x() > x + new_w:
                x = min(app_geom.right() - new_w, mouse_pos.x() - new_w + 10)
            if mouse_pos.y() < y:
                y = max(app_geom.top(), mouse_pos.y() - 10)
            elif mouse_pos.y() > y + new_h:
                y = min(app_geom.bottom() - new_h, mouse_pos.y() - new_h + 10)
                
        self.setFixedSize(new_w, new_h)
        self.move(x, y)
        logging.info(f"POPUP SIZE RESET: size={new_w}x{new_h}, position=({x}, {y})")

    def toggle_size_settings_popup(self) -> None:
        if self.btn_settings.isChecked():
            btn_pos = self.btn_settings.mapToGlobal(QPoint(0, 0))
            x = btn_pos.x() - self.size_settings_popup.width() + self.btn_settings.width()
            y = btn_pos.y() + self.btn_settings.height() + 5
            self.size_settings_popup.move(x, y)
            self.size_settings_popup.show()
            self.size_settings_popup.raise_()
        else:
            self.size_settings_popup.hide()

    def _on_size_popup_closed(self) -> None:
        cursor_pos = QCursor.pos()
        btn_rect = self.btn_settings.frameGeometry()
        
        top_left = self.btn_settings.mapToGlobal(QPoint(0, 0))
        btn_global_rect = QRectF(QPointF(top_left), QSizeF(btn_rect.width(), btn_rect.height()))
        
        if not btn_global_rect.contains(QPointF(cursor_pos)):
            self.btn_settings.setChecked(False)

    def _install_key_event_filters(self, widget) -> None:
        if widget:
            widget.installEventFilter(self)
            for child in widget.findChildren(QWidget):
                child.installEventFilter(self)

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        
        if obj == getattr(self, 'top_overlay', None):
            if event.type() == QEvent.Type.Enter:
                if hasattr(self, 'title_opacity_effect') and self.title_opacity_effect:
                    self.title_opacity_effect.setOpacity(0.0)
                self.top_overlay.setStyleSheet("background: transparent;")
            elif event.type() == QEvent.Type.Leave:
                if hasattr(self, 'title_opacity_effect') and self.title_opacity_effect:
                    self.title_opacity_effect.setOpacity(1.0)
                self.top_overlay.setStyleSheet("""
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(15, 15, 15, 0.42), stop:0.7 rgba(15, 15, 15, 0.20), stop:1 rgba(15, 15, 15, 0));
                """)
        
        is_viewer = False
        if obj == getattr(self, 'video_viewer', None):
            is_viewer = True
        elif obj == getattr(self, 'lbl_media', None):
            is_viewer = True
        elif obj == getattr(self, 'lbl_audio', None):
            is_viewer = True
            
        if is_viewer:
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    self._click_start_pos = event.pos()
                    return True
                elif event.button() == Qt.MouseButton.MiddleButton:
                    self.open_folder_with_file()
                    return True
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.LeftButton:
                    if hasattr(self, '_click_start_pos') and self._click_start_pos:
                        dist = (event.pos() - self._click_start_pos).manhattanLength()
                        if dist < 5:
                            self.toggle_playback()
                    self._click_start_pos = None
                    return True
            elif event.type() == QEvent.Type.MouseButtonDblClick:
                if event.button() == Qt.MouseButton.LeftButton:
                    self.open_file_system()
                    return True
        
        if event.type() == QEvent.Type.KeyPress:
            event.ignore()
            self.keyPressEvent(event)
            if event.isAccepted():
                return True
                
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: Any) -> None:
        if self.main_app and hasattr(self.main_app, '_hotkey_registry'):
            registry = self.main_app._hotkey_registry
            key = event.key()
            modifiers = event.modifiers()
            
            # Пропускаем чисто модификаторные клавиши (Shift, Ctrl и т.д.)
            if key not in (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
                key_val = key.value if hasattr(key, 'value') else int(key)
                
                mod_val = 0
                if modifiers & Qt.KeyboardModifier.ShiftModifier:
                    mod_val |= Qt.KeyboardModifier.ShiftModifier.value
                if modifiers & Qt.KeyboardModifier.ControlModifier:
                    mod_val |= Qt.KeyboardModifier.ControlModifier.value
                if modifiers & Qt.KeyboardModifier.AltModifier:
                    mod_val |= Qt.KeyboardModifier.AltModifier.value
                if modifiers & Qt.KeyboardModifier.MetaModifier:
                    mod_val |= Qt.KeyboardModifier.MetaModifier.value

                key_seq = QKeySequence(key_val | mod_val)
                key_str = key_seq.toString().lower()
                
                # Ищем совпадение в активных шорткатах
                matched = False
                for action_id, sc in registry._shortcuts.items():
                    if sc.isEnabled():
                        sc_seq = sc.key()
                        if sc_seq.toString().lower() == key_str:
                            action = registry._actions.get(action_id)
                            if action:
                                callback = getattr(self.main_app, action.callback_name, None)
                                if callback:
                                    try:
                                        callback()
                                    except Exception as e:
                                        logging.error(f"Error executing hotkey callback {action.callback_name}: {e}", exc_info=True)
                                    event.accept()
                                    matched = True
                                    break
                if matched:
                    return

        if self.main_app and hasattr(self.main_app, 'keyPressEvent'):
            self.main_app.keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        self.show_context_menu(event.globalPos())
        event.accept()

    def show_context_menu(self, global_pos):
        self._context_menu_active = True
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #252525;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                color: #dddddd;
                padding: 6px 20px 6px 12px;
                border-radius: 4px;
                font-size: 12px;
            }
            QMenu::item:selected {
                background-color: #3b82f6;
                color: white;
            }
            QMenu::separator {
                height: 1px;
                background: #444;
                margin: 3px 8px;
            }
        """)
        
        ext = os.path.splitext(self.filepath)[1].lower()
        
        video_exts = VIDEO_EXTS
        audio_exts = AUDIO_EXTS
        image_exts = IMAGE_EXTS
        
        act_open = QAction(AppContext.tr("srt_ctx_open_file"), self)
        act_open.triggered.connect(self.open_file_system)
        menu.addAction(act_open)
        
        act_folder = QAction(AppContext.tr("srt_ctx_open_folder"), self)
        act_folder.triggered.connect(self.open_folder_with_file)
        menu.addAction(act_folder)
        
        if ext in video_exts:
            menu.addSeparator()
            act_vconv = QAction(AppContext.tr("srt_ctx_convert_video"), self)
            act_vconv.triggered.connect(lambda: self.send_to_editor_main("video_conv"))
            menu.addAction(act_vconv)
            
            act_aconv = QAction(AppContext.tr("srt_ctx_convert_audio_to"), self)
            act_aconv.triggered.connect(lambda: self.send_to_editor_main("audio_conv"))
            menu.addAction(act_aconv)
            
            act_vedit = QAction(AppContext.tr("srt_ctx_edit_video"), self)
            act_vedit.triggered.connect(lambda: self.send_to_editor_main("video_edit"))
            menu.addAction(act_vedit)
            
        elif ext in image_exts:
            menu.addSeparator()
            act_iconv = QAction(AppContext.tr("srt_ctx_convert_image"), self)
            act_iconv.triggered.connect(lambda: self.send_to_editor_main("image_conv"))
            menu.addAction(act_iconv)
            
            if ext == '.gif':
                from PyQt6.QtGui import QImageReader
                reader = QImageReader(self.filepath)
                if reader.supportsAnimation() and reader.imageCount() > 1:
                    act_vconv = QAction(AppContext.tr("srt_ctx_convert_video"), self)
                    act_vconv.triggered.connect(lambda: self.send_to_editor_main("video_conv"))
                    menu.addAction(act_vconv)
            
        elif ext in audio_exts:
            menu.addSeparator()
            act_aconv = QAction(AppContext.tr("srt_ctx_convert_audio"), self)
            act_aconv.triggered.connect(lambda: self.send_to_editor_main("audio_conv"))
            menu.addAction(act_aconv)
            
            act_aedit = QAction(AppContext.tr("srt_ctx_edit_audio"), self)
            act_aedit.triggered.connect(lambda: self.send_to_editor_main("audio_edit"))
            menu.addAction(act_aedit)
            
        menu.aboutToHide.connect(self._on_menu_about_to_hide)
        menu.exec(global_pos)

    def _on_menu_about_to_hide(self):
        QTimer.singleShot(100, self._clear_menu_flag)

    def _clear_menu_flag(self):
        self._context_menu_active = False

    def send_to_editor_main(self, mode):
        self.close()
        if self.main_app:
            if hasattr(self.main_app, "on_send_to_editor_requested"):
                self.main_app.on_send_to_editor_requested(mode, [self.filepath])

    def open_file_system(self):
        self.close()
        long_fp = ensure_long_path(self.filepath)
        if long_fp and os.path.exists(long_fp):
            clean_path = strip_long_path_prefix(long_fp)
            QDesktopServices.openUrl(QUrl.fromLocalFile(clean_path))

    def open_folder_with_file(self):
        self.close()
        long_fp = ensure_long_path(self.filepath)
        if long_fp and os.path.exists(long_fp):
            from utils_common import reveal_in_explorer
            reveal_in_explorer(long_fp)

    def _on_scrub_start(self):
        if self.media_player:
            self._was_playing_before_scrub = (self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
            self.media_player.pause()

    def _on_scrub_stop(self):
        if self.media_player and getattr(self, '_was_playing_before_scrub', False):
            self.media_player.play()

    def toggle_playback(self):
        if self.media_player:
            if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.media_player.pause()
            else:
                self.media_player.play()
        elif self.movie:
            if self.movie.state() == QMovie.MovieState.Running:
                self.movie.setPaused(True)
            else:
                self.movie.setPaused(False)

    def _on_media_status_changed_popup(self, status):
        if status in (QMediaPlayer.MediaStatus.BufferedMedia, QMediaPlayer.MediaStatus.LoadedMedia):
            if hasattr(self, 'video_viewer') and self.video_viewer:
                sz = self.video_viewer.video_item.nativeSize()
                if sz.isValid():
                    self.video_viewer._on_native_size_changed(sz)
            if hasattr(self, 'time_overlay'):
                self.time_overlay.show()
                self.resizeEvent(None)
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            if hasattr(self, 'time_overlay'):
                self.time_overlay.hide()

    def _on_playback_state_changed(self, state):
        is_playing = (state == QMediaPlayer.PlaybackState.PlayingState)
        if hasattr(self, 'controls') and self.controls:
            self.controls.set_playing_state(is_playing)
            
        if hasattr(self, 'video_viewer') and self.video_viewer and hasattr(self.video_viewer, 'update_segment_indicator'):
            self.video_viewer.update_segment_indicator()
                
    def change_volume(self, value):
        vol = value / 100.0
        if self.media_player:
            self.audio_output.setVolume(vol)
        if self.main_app:
            self.main_app.global_volume = vol
            if hasattr(self.main_app, 'audio_output'):
                self.main_app.audio_output.setVolume(vol)
            if hasattr(self.main_app, 'video_controls'):
                self.main_app.video_controls.vol_slider.setValue(value)
                
    def on_speed_changed(self, speed):
        ext = os.path.splitext(self.filepath)[1].lower()
        is_video = ext in VIDEO_EXTS
        
        if self.media_player:
            self.media_player.setPlaybackRate(speed)
        if self.main_app:
            from config import AppContext
            if is_video:
                AppContext.session_video_speed = speed
            if hasattr(self.main_app, 'media_player'):
                self.main_app.media_player.setPlaybackRate(speed)
            if hasattr(self.main_app, 'video_controls'):
                self.main_app.video_controls.set_popup_values(
                    speed if is_video else 1.0, 
                    AppContext.session_loop, 
                    AppContext.session_all_videos_active, 
                    is_video
                )

    def on_loop_toggled(self, enabled):
        ext = os.path.splitext(self.filepath)[1].lower()
        is_video = ext in VIDEO_EXTS
        
        if self.media_player:
            self.media_player.setLoops(QMediaPlayer.Loops.Infinite if enabled else QMediaPlayer.Loops.Once)
        if self.main_app:
            from config import AppContext
            self.main_app.session_loop = enabled
            AppContext.session_loop = enabled
            AppContext.save_media_settings()
            if hasattr(self.main_app, 'media_player'):
                self.main_app.media_player.setLoops(QMediaPlayer.Loops.Infinite if enabled else QMediaPlayer.Loops.Once)
            if hasattr(self.main_app, 'video_controls'):
                speed = float(AppContext.session_video_speed) if AppContext.session_all_videos_active else 1.0
                self.main_app.video_controls.set_popup_values(
                    speed if is_video else 1.0, 
                    enabled, 
                    AppContext.session_all_videos_active, 
                    is_video
                )

    def update_segment_indicator(self):
        if not hasattr(self, 'smart_preview_mgr'): return
        mgr = self.smart_preview_mgr
        
        if mgr and mgr.num_segments > 0:
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

    def _on_segment_indicator_clicked(self):
        from config import AppContext
        AppContext.session_segment_view = not AppContext.session_segment_view
        if hasattr(self, 'smart_preview_mgr'):
            self.smart_preview_mgr.set_active(AppContext.session_segment_view)
        
        if hasattr(self.viewer, 'update_segment_indicator'):
            self.viewer.update_segment_indicator()
        self.update_segment_indicator()

    def on_apply_all_toggled(self, enabled):
        ext = os.path.splitext(self.filepath)[1].lower()
        is_video = ext in VIDEO_EXTS
        
        if self.main_app:
            self.main_app.session_all_videos_active = enabled
            from config import AppContext
            AppContext.session_all_videos_active = enabled
            AppContext.save_media_settings()
            if is_video:
                segment_view = AppContext.session_segment_view
                if not enabled:
                    if self.media_player:
                        self.media_player.setPlaybackRate(1.0)
                    self.controls.set_popup_values(1.0, AppContext.session_loop, False, True)
                else:
                    speed = float(AppContext.session_video_speed)
                    if self.media_player:
                        self.media_player.setPlaybackRate(speed)
                    self.controls.set_popup_values(speed, AppContext.session_loop, True, True)
                
                if hasattr(self.main_app, 'video_controls'):
                    self.main_app.video_controls.set_popup_values(
                        float(AppContext.session_video_speed) if enabled else 1.0, 
                        AppContext.session_loop, 
                        enabled,
                        True
                    )
                    
    def on_segment_view_toggled(self, enabled):
        from config import AppContext
        AppContext.session_segment_view = enabled
        AppContext.save_media_settings()
        if hasattr(self, 'smart_preview_mgr'):
            self.smart_preview_mgr.set_active(enabled)
            
        if hasattr(self, 'video_viewer') and hasattr(self.video_viewer, 'update_segment_indicator'):
            self.video_viewer.update_segment_indicator()
            
    def resizeEvent(self, event):
        if event is not None:
            super().resizeEvent(event)
        w = self.width()
        h = self.height()
        if hasattr(self, 'top_overlay') and self.top_overlay:
            self.top_overlay.setGeometry(2, 2, w - 4, 38)
            self.top_overlay.raise_()
        if hasattr(self, 'right_btn_container') and self.right_btn_container:
            self.right_btn_container.setGeometry(w - 28, 6, 22, 48)
            self.right_btn_container.raise_()
        if hasattr(self, 'bottom_overlay') and self.bottom_overlay:
            self.bottom_overlay.setGeometry(6, h - 36, 100, 30)
            self.bottom_overlay.raise_()
            
        if hasattr(self, 'time_overlay') and self.time_overlay and self.time_overlay.isVisible():
            padding = 10
            controls_h = self.controls.height() if hasattr(self, 'controls') and self.controls.isVisible() else 0
            x = w - self.time_overlay.width() - padding
            y = h - controls_h - self.time_overlay.height() - padding
            self.time_overlay.move(x, y)
            self.time_overlay.raise_()
            
        self._update_gif_size()

    def _update_overlay_time(self, pos):
        if hasattr(self, 'media_player') and hasattr(self, 'time_overlay'):
            dur = self.media_player.duration()
            self.time_overlay.set_time(pos, dur)

    def _update_overlay_duration(self, dur):
        if hasattr(self, 'media_player') and hasattr(self, 'time_overlay'):
            pos = self.media_player.position()
            self.time_overlay.set_time(pos, dur)
            self.resizeEvent(None)
            
    def _on_media_duration_changed(self, dur):
        if hasattr(self, 'smart_preview_mgr'):
            self.smart_preview_mgr.start_video(dur)
        if hasattr(self, 'video_viewer') and hasattr(self.video_viewer, 'update_segment_indicator'):
            self.video_viewer.update_segment_indicator()

    def leaveEvent(self, event):
        super().leaveEvent(event)

    def _on_gif_frame_changed(self, frame_number):
        if not getattr(self, '_gif_size_initialized', False):
            self._update_gif_size()
            self._gif_size_initialized = True

    def _update_gif_size(self):
        if not hasattr(self, 'movie') or not self.movie or not hasattr(self, 'lbl_media') or not self.lbl_media:
            return
        orig_size = self.movie.frameRect().size()
        if not orig_size.isValid() or orig_size.isEmpty():
            pix = self.movie.currentPixmap()
            if not pix.isNull():
                orig_size = pix.size()
                
        if orig_size.isValid() and not orig_size.isEmpty():
            avail_w = self.width() - 8
            avail_h = self.height() - 8
            if avail_w > 0 and avail_h > 0:
                scaled_size = orig_size.scaled(avail_w, avail_h, Qt.AspectRatioMode.KeepAspectRatio)
                self.movie.setScaledSize(scaled_size)
        
    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)
        
    def cleanup(self):
        if hasattr(self, 'size_settings_popup') and self.size_settings_popup:
            self.size_settings_popup.hide()
            self.size_settings_popup.deleteLater()
            self.size_settings_popup = None

        if self.media_player:
            try:
                self.media_player.positionChanged.disconnect()
                self.media_player.durationChanged.disconnect()
            except Exception:
                pass
            self.media_player.stop()
            self.media_player.setSource(QUrl())
            
            try:
                import time
                from PyQt6.QtMultimedia import QMediaPlayer
                from PyQt6.QtCore import QCoreApplication
                start_t = time.time()
                while self.media_player.mediaStatus() != QMediaPlayer.MediaStatus.NoMedia and (time.time() - start_t) < 0.3:
                    QCoreApplication.processEvents()
                    time.sleep(0.01)
            except Exception as e:
                logging.error(f"Error waiting for popup media player release: {e}")
                
            self.media_player.deleteLater()
            self.media_player = None
            
        if hasattr(self, 'audio_output') and self.audio_output:
            try:
                self.audio_output.deleteLater()
            except Exception:
                pass
            self.audio_output = None
            
        if self.movie:
            self.movie.stop()
            self.movie.deleteLater()
            self.movie = None
            
        parent_list = self.parent()
        if parent_list and hasattr(parent_list, '_on_large_preview_closed'):
            parent_list._on_large_preview_closed()

        if self.main_app and hasattr(self.main_app, 'viewer'):
            try:
                self.main_app.viewer.selection_changed.disconnect(self.update_select_button_state)
            except Exception:
                pass
            
        import gc
        gc.collect()
