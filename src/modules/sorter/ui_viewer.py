import os
import logging
import subprocess
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QListWidget, QListWidgetItem,
    QStyle, QPushButton, QFrame, QAbstractItemView, QLabel,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsTextItem, QGraphicsProxyWidget,
    QFileIconProvider, QApplication, QDialog, QMenu, QDoubleSpinBox
)
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, pyqtSignal, QSize, QUrl, QFileInfo, QPoint, QSizeF, QItemSelectionModel
from PyQt6.QtGui import QColor, QPixmap, QMovie, QWheelEvent, QMouseEvent, QFont, QPainter, QKeyEvent, QIcon, QFontMetrics, QCursor, QAction, QDesktopServices, QTransform, QKeySequence
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

from config import AppContext, VIEWER_DESIGN, APP_DESIGN
from .thumbnail_loader import ThumbnailLoader
from .ui_player import VideoPlayerControls, SegmentIndicatorWidget

from .ui_preview_popup import LargePreviewPopup
from utils_extensions import VIDEO_EXTS, AUDIO_EXTS, IMAGE_EXTS
from utils_io import ensure_long_path, strip_long_path_prefix

def safe_relpath(path: str, start: str) -> str:
    if not start:
        return strip_long_path_prefix(path)
    p = strip_long_path_prefix(path)
    s = strip_long_path_prefix(start)
    try:
        return os.path.relpath(p, s)
    except ValueError:
        return p
class FileIconManager:
    _instance = None

    @classmethod
    def inst(cls):
        if cls._instance is None:
            cls._instance = FileIconManager()
        return cls._instance

    def __init__(self):
        self.provider = QFileIconProvider()
        self.cache = {}
        self.icons_dir = AppContext.find_resource_dir("icons")

    def clear_cache(self):
        self.cache.clear()

    def crop_transparent_borders(self, pixmap):
        """Обрезает прозрачные поля вокруг иконки, чтобы она корректно
        масштабировалась и центрировалась, а не оставалась мелкой в углу."""
        if pixmap.isNull():
            return pixmap
            
        from PyQt6.QtGui import QImage
        image = pixmap.toImage()
        if image.format() != QImage.Format.Format_ARGB32:
            image = image.convertToFormat(QImage.Format.Format_ARGB32)
            
        width = image.width()
        height = image.height()
        
        try:
            ptr = image.bits()
            ptr.setsize(height * width * 4)
            buf = memoryview(ptr)
        except Exception:
            buf = None
            
        if buf is not None:
            min_x, min_y = width, height
            max_x, max_y = -1, -1
            
            # Поиск верхней границы (min_y)
            for y in range(height):
                row_offset = y * width * 4
                has_alpha = False
                for idx in range(row_offset + 3, row_offset + width * 4, 4):
                    if buf[idx] > 0:
                        has_alpha = True
                        break
                if has_alpha:
                    min_y = y
                    break
            else:
                return pixmap # Полностью прозрачная
                
            # Поиск нижней границы (max_y)
            for y in range(height - 1, min_y - 1, -1):
                row_offset = y * width * 4
                has_alpha = False
                for idx in range(row_offset + 3, row_offset + width * 4, 4):
                    if buf[idx] > 0:
                        has_alpha = True
                        break
                if has_alpha:
                    max_y = y
                    break
                    
            # Поиск левой границы (min_x)
            for x in range(width):
                has_alpha = False
                for y in range(min_y, max_y + 1):
                    if buf[(y * width + x) * 4 + 3] > 0:
                        has_alpha = True
                        break
                if has_alpha:
                    min_x = x
                    break
                    
            # Поиск правой границы (max_x)
            for x in range(width - 1, min_x - 1, -1):
                has_alpha = False
                for y in range(min_y, max_y + 1):
                    if buf[(y * width + x) * 4 + 3] > 0:
                        has_alpha = True
                        break
                if has_alpha:
                    max_x = x
                    break
        else:
            # Медленный резервный вариант
            min_x, min_y = width, height
            max_x, max_y = -1, -1
            for y in range(height):
                for x in range(width):
                    if image.pixelColor(x, y).alpha() > 0:
                        if x < min_x: min_x = x
                        if x > max_x: max_x = x
                        if y < min_y: min_y = y
                        if y > max_y: max_y = y
            if max_x < 0:
                return pixmap
                
        from PyQt6.QtCore import QRect
        cropped_rect = QRect(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)
        
        # Добавляем небольшой отступ в 2 пикселя, чтобы избежать обрезки краев
        padding = 2
        pad_x = max(0, cropped_rect.x() - padding)
        pad_y = max(0, cropped_rect.y() - padding)
        pad_w = min(width - pad_x, cropped_rect.width() + padding * 2)
        pad_h = min(height - pad_y, cropped_rect.height() + padding * 2)
        
        final_rect = QRect(pad_x, pad_y, pad_w, pad_h)
        return QPixmap.fromImage(image.copy(final_rect))

    def get_icon_pixmap(self, filepath, size=QSize(128, 128)):
        ext = os.path.splitext(filepath)[1].lower()
        # Для исполняемых файлов кэшируем по полному пути, так как у каждого EXE своя иконка
        is_unique_icon = ext in ['.exe', '.lnk']
        key = (filepath if is_unique_icon else ext, size.width(), size.height())
        
        if key in self.cache:
            return self.cache[key]
            
        try:
            file_info = QFileInfo(filepath)
            icon = self.provider.icon(file_info)
            if not icon.isNull():
                # Получаем наибольший доступный размер иконки и масштабируем вниз
                # чтобы избежать крошечных 16×16 иконок, растянутых до 128×128
                available = icon.availableSizes()
                if available:
                    best = max(available, key=lambda s: s.width() * s.height())
                    source_pixmap = icon.pixmap(best)
                else:
                    # Windows GDI-иконки могут не возвращать availableSizes().
                    # Пробуем получить иконку в крупных размерах, чтобы избежать
                    # растяжения 16x16 пикселей до 128x128.
                    source_pixmap = QPixmap()
                    for try_size in [QSize(256, 256), QSize(128, 128), QSize(64, 64)]:
                        candidate = icon.pixmap(try_size)
                        if not candidate.isNull():
                            if source_pixmap.isNull() or candidate.width() > source_pixmap.width():
                                source_pixmap = candidate
                if not source_pixmap.isNull():
                    # Обрезаем прозрачные поля перед масштабированием
                    source_pixmap = self.crop_transparent_borders(source_pixmap)
                    if source_pixmap.size() != size:
                        pixmap = source_pixmap.scaled(
                            size,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation
                        )
                    else:
                        pixmap = source_pixmap
                    self.cache[key] = pixmap
                    return pixmap
        except Exception as e:
            logging.debug(f"Failed to get system icon for {filepath}: {e}")
            
        # Fallback
        pixmap = self.create_default_fallback_pixmap(ext, size)
        self.cache[key] = pixmap
        return pixmap

    def create_default_fallback_pixmap(self, ext, size):
        icon_path = os.path.join(self.icons_dir, "file.svg")
        if os.path.exists(icon_path):
            pixmap = QIcon(icon_path).pixmap(size)
            if not pixmap.isNull():
                return pixmap
        # Резервный вариант, если вдруг файл file.svg отсутствует
        pixmap = QPixmap(size)
        pixmap.fill(QColor("transparent"))
        return pixmap


def format_short_size(size_bytes):
    if size_bytes is None or size_bytes <= 0:
        return "0Kb"
    units = ["b", "Kb", "Mb", "Gb", "Tb"]
    i = 0
    p = float(size_bytes)
    while p >= 1024 and i < len(units) - 1:
        p /= 1024
        i += 1
    if p >= 100:
        val_str = f"{int(round(p))}"
    else:
        val_str = f"{p:.1f}"
        if val_str.endswith(".0"):
            val_str = val_str[:-2]
    return f"{val_str}{units[i]}"


def elide_text_to_two_lines(text, font, width):
    metrics = QFontMetrics(font)
    if metrics.horizontalAdvance(text) <= width:
        return text
        
    line1 = ""
    idx = 0
    while idx < len(text):
        test_line = line1 + text[idx]
        if metrics.horizontalAdvance(test_line) <= width:
            line1 = test_line
            idx += 1
        else:
            break
            
    rest = text[idx:]
    if metrics.horizontalAdvance(rest) <= width:
        return line1 + "\n" + rest
        
    line2 = ""
    for char in rest:
        test_line = line2 + char
        if metrics.horizontalAdvance(test_line + "...") <= width:
            line2 = test_line
        else:
            break
    return line1 + "\n" + line2 + "..."


def _scale_pixmap_to_canvas(pixmap, canvas_size):
    """Помещает pixmap точно по центру canvas_size через QPainter.
    Гарантирует правильное центрирование в отличие от QLabel.setAlignment,
    который работает только в рамках размера самого лэйбла."""
    canvas = QPixmap(canvas_size)
    canvas.fill(Qt.GlobalColor.transparent)
    if pixmap.isNull() or canvas_size.width() <= 0 or canvas_size.height() <= 0:
        return canvas
    scaled = pixmap.scaled(
        canvas_size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation
    )
    painter = QPainter(canvas)
    x = (canvas_size.width() - scaled.width()) // 2
    y = (canvas_size.height() - scaled.height()) // 2
    painter.drawPixmap(x, y, scaled)
    painter.end()
    return canvas

class SorterGridItemWidget(QWidget):
    """Custom grid tile showing preview content and filename."""
    def __init__(self, filepath, tile_size, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.tile_size = tile_size
        self.placeholder_pixmap = None
        self.preview_image = None
        self._is_selected = False
        
        # Сделай виджет прозрачным для мыши, чтобы события пролетали в QListWidget
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("background: transparent;")
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(3)
        
        # Preview Frame (to draw borders/backgrounds)
        self.preview_frame = QFrame()
        self.preview_frame.setObjectName("PreviewFrame")
        self.preview_frame.setStyleSheet("""
            #PreviewFrame {
                background: #2a2a2a;
                border: 1px solid #444444;
                border-radius: 6px;
            }
        """)
        self.preview_layout = QVBoxLayout(self.preview_frame)
        self.preview_layout.setContentsMargins(2, 2, 2, 2)
        self.preview_layout.setSpacing(0)
        
        self.lbl_preview = QLabel()
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setScaledContents(False)
        self.lbl_preview.setStyleSheet("background: transparent;")
        self.preview_layout.addWidget(self.lbl_preview)
        
        self.layout.addWidget(self.preview_frame)
        
        # Filename Label
        self.lbl_name = QLabel()
        self.lbl_name.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        # Шрифт будет установлен в update_sizes() через setPixelSize (DPI-независимо)
        self.lbl_name.setStyleSheet("background: transparent; color: #ffffff;")
        self.lbl_name.setWordWrap(True)
        self.lbl_name.setFixedHeight(28)
        self.layout.addWidget(self.lbl_name)
        self.layout.addStretch(1)
        
        # Badge for extension inside preview_frame
        self.lbl_badge = QLabel(self.preview_frame)
        ext = os.path.splitext(filepath)[1].upper()
        if ext.startswith('.'):
            ext = ext[1:]
        self.lbl_badge.setText(ext if ext else "FILE")
        self.lbl_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Check if preview is available (media files)
        ext_lower = os.path.splitext(filepath)[1].lower()
        is_previewable = ext_lower in VIDEO_EXTS
        
        if is_previewable:
            # Sleek dark green color for previewable files
            badge_bg = "rgba(22, 101, 52, 0.85)"
            badge_border = "1px solid #16a34a"
        else:
            # Default dark color
            badge_bg = "rgba(0, 0, 0, 0.75)"
            badge_border = "1px solid #555555"
            
        self.lbl_badge.setStyleSheet(f"""
            background-color: {badge_bg};
            color: #ffffff;
            border: {badge_border};
            border-radius: 3px;
            padding: 0px;
        """)
        self.lbl_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        
        # Explicitly set clear bold font for the badge
        badge_font = QFont()
        badge_font.setPointSize(8)
        badge_font.setBold(True)
        self.lbl_badge.setFont(badge_font)
        
        # Badge for file size inside preview_frame
        self.lbl_size_badge = QLabel(self.preview_frame)
        self.lbl_size_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_size_badge.setStyleSheet("""
            background-color: rgba(0, 0, 0, 0.75);
            color: #ffffff;
            border: 1px solid #555555;
            border-radius: 3px;
            padding: 0px 2px;
        """)
        self.lbl_size_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        
        size_font = QFont()
        size_font.setPointSize(8)
        size_font.setBold(True)
        self.lbl_size_badge.setFont(size_font)
        
        file_size = 0
        try:
            file_size = os.path.getsize(ensure_long_path(filepath))
        except Exception:
            pass
        self.lbl_size_badge.setText(format_short_size(file_size))
        
        self.update_sizes()

    def update_sizes(self):
        # NOTE: Дублирование кода удалено. Технический долг: в будущих улучшениях можно вынести генерацию элидированного текста в отдельный вспомогательный метод.
        self.preview_frame.setFixedSize(self.tile_size, self.tile_size)
        self.setFixedSize(self.tile_size, self.tile_size + 42)
        
        # --- Динамический размер метки и шрифта (вариант A) ---
        # Вычисляем высоту метки исходя из общего размера плитки.
        # Примерная формула: оставляем место для превью‑кадра (self.tile_size)
        # и 42 px дополнительного пространства (как сейчас). Внутри этого
        # пространства будем размещать метку с отступами сверху/снизу и
        # межстрочным интервалом. Пользователь может менять коэффициенты.
        TOP_MARGIN: int = 5       # отступ сверху до первой строки
        BOTTOM_MARGIN: int = 13   # отступ снизу после второй строки (увеличен на 3px)
        INTER_LINE: int = 2       # промежуток между двумя строками (уменьшен на 3px)
        # Доступная высота для текста (без учёта отступов):
        AVAILABLE_HEIGHT: int = 42 - TOP_MARGIN - BOTTOM_MARGIN
        # Высота одной строки с учётом line‑height (1.05) и промежутка:
        LINE_HEIGHT: float = 1.05
        SINGLE_LINE_PX: float = (AVAILABLE_HEIGHT - INTER_LINE) / 2.0
        # Размер шрифта в пикселях, ограниченный минимумом 8px:
        font_px: int = max(8, min(24, int(SINGLE_LINE_PX / LINE_HEIGHT)))  # верхний предел 24 px
        # Устанавливаем высоту метки равной сумме всех отступов + две строки:
        label_height: int = TOP_MARGIN + BOTTOM_MARGIN + INTER_LINE + int(2 * SINGLE_LINE_PX)
        self.lbl_name.setFixedHeight(label_height)
        # Применяем шрифт:
        font = self.lbl_name.font()
        font.setPixelSize(font_px)
        self.lbl_name.setFont(font)
        
        # Update elided text (excluding extension) with a safe 20px margin to prevent clipping
        base_name = os.path.basename(self.filepath)
        name_without_ext = os.path.splitext(base_name)[0]
        elided = elide_text_to_two_lines(name_without_ext, font, self.tile_size - 20)
        
        import html
        escaped_lines = [html.escape(line) for line in elided.split('\n')]
        elided_html = f"<div style='line-height: 105%; text-align: center;'>{'<br>'.join(escaped_lines)}</div>"
        self.lbl_name.setText(elided_html)
        
        # Tooltip with full name
        self.lbl_name.setToolTip(base_name)
        
        # Position extension badge dynamically based on text width
        badge_font = self.lbl_badge.font()
        metrics = QFontMetrics(badge_font)
        ext_text = self.lbl_badge.text()
        text_w = metrics.horizontalAdvance(ext_text)
        
        badge_w = max(24, text_w + 8) # minimum 24px
        badge_h = 16 # height 16px to prevent clipping
        
        # Constrain badge width by tile size
        max_badge_w = self.tile_size - 4
        if badge_w > max_badge_w:
            badge_w = max_badge_w
            elided_text = metrics.elidedText(ext_text, Qt.TextElideMode.ElideRight, badge_w - 6)
            self.lbl_badge.setText(elided_text)
            
        self.lbl_badge.setGeometry(
            self.tile_size - badge_w - 2,
            self.tile_size - badge_h - 2,
            badge_w,
            badge_h
        )
        
        # Position size badge in the upper left corner of the preview frame
        size_text = self.lbl_size_badge.text()
        size_metrics = QFontMetrics(self.lbl_size_badge.font())
        size_w_calc = size_metrics.horizontalAdvance(size_text)
        size_w = max(24, size_w_calc + 8)
        size_h = 16
        
        if size_w > max_badge_w:
            size_w = max_badge_w
            
        self.lbl_size_badge.setGeometry(
            2,
            2,
            size_w,
            size_h
        )

    def set_tile_size(self, size):
        self.tile_size = size
        self.update_sizes()

    def set_selected(self, selected: bool):
        if getattr(self, '_is_selected', None) == selected:
            return
        self._is_selected = selected
        if selected:
            self.preview_frame.setStyleSheet("""
                #PreviewFrame {
                    background: #1e3a8a;
                    border: 1px solid #3b82f6;
                    border-radius: 6px;
                }
            """)
            self.lbl_name.setStyleSheet("""
                background: #1e3a8a;
                color: #ffffff;
                border-radius: 6px;
            """)
        else:
            self.preview_frame.setStyleSheet("""
                #PreviewFrame {
                    background: #2a2a2a;
                    border: 1px solid #444444;
                    border-radius: 6px;
                }
            """)
            self.lbl_name.setStyleSheet("""
                background: transparent;
                color: #ffffff;
            """)

    def get_viewer_area(self):
        widget = self.parent()
        while widget is not None:
            if hasattr(widget, 'sync_files_queue'):
                return widget
            widget = widget.parent()
        return None

    def set_preview_image(self, qimage):
        self.preview_image = qimage
        self.placeholder_pixmap = None
        s = self.tile_size - 4
        pixmap = QPixmap.fromImage(qimage)
        
        viewer = self.get_viewer_area()
        if viewer and hasattr(viewer, 'file_rotations'):
            angle = viewer.file_rotations.get(os.path.normpath(self.filepath), 0)
            if angle != 0:
                transform = QTransform().rotate(angle)
                pixmap = pixmap.transformed(transform, Qt.TransformationMode.SmoothTransformation)
                
        canvas = _scale_pixmap_to_canvas(pixmap, QSize(s, s))
        self.lbl_preview.setPixmap(canvas)

    def set_placeholder(self, pixmap):
        self.placeholder_pixmap = pixmap
        self.preview_image = None
        s = self.tile_size - 4
        
        viewer = self.get_viewer_area()
        if viewer and hasattr(viewer, 'file_rotations'):
            angle = viewer.file_rotations.get(os.path.normpath(self.filepath), 0)
            if angle != 0:
                transform = QTransform().rotate(angle)
                pixmap = pixmap.transformed(transform, Qt.TransformationMode.SmoothTransformation)
                
        canvas = _scale_pixmap_to_canvas(pixmap, QSize(s, s))
        self.lbl_preview.setPixmap(canvas)

    def update_rotation(self):
        if getattr(self, 'preview_image', None) is not None:
            self.set_preview_image(self.preview_image)
        elif getattr(self, 'placeholder_pixmap', None) is not None:
            self.set_placeholder(self.placeholder_pixmap)


class SorterListItemWidget(QWidget):
    """Custom list item widget showing preview, metadata and details."""
    def __init__(self, filepath, icon_size, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.icon_size = icon_size
        self.placeholder_pixmap = None
        self.preview_image = None
        
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("background: transparent;")
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(4, 2, 6, 2)
        self.layout.setSpacing(8)
        
        # Preview Frame — квадрат точно в высоту строки
        self.preview_frame = QFrame()
        self.preview_frame.setObjectName("PreviewFrame")
        self.preview_frame.setStyleSheet("""
            #PreviewFrame {
                background: transparent;
                border: none;
            }
        """)
        self.preview_layout = QVBoxLayout(self.preview_frame)
        self.preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_layout.setSpacing(0)
        
        self.lbl_preview = QLabel()
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setScaledContents(False)
        self.lbl_preview.setStyleSheet("background: transparent;")
        self.preview_layout.addWidget(self.lbl_preview)
        
        self.layout.addWidget(self.preview_frame)
        
        # Metadata layout
        self.meta_layout = QHBoxLayout()
        self.meta_layout.setContentsMargins(0, 0, 0, 0)
        self.meta_layout.setSpacing(10)
        
        self.lbl_name = QLabel(os.path.basename(filepath))
        self.lbl_name.setStyleSheet("background: transparent; color: #ffffff; font-weight: bold; font-size: 12px;")
        self.lbl_name.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.meta_layout.addWidget(self.lbl_name, stretch=1)
        
        file_size = 0
        try: file_size = os.path.getsize(ensure_long_path(filepath))
        except: pass
        
        from utils_common import format_size
        self.lbl_size = QLabel(format_size(file_size))
        self.lbl_size.setStyleSheet("background: transparent; color: #888888; font-size: 11px;")
        self.lbl_size.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.meta_layout.addWidget(self.lbl_size)
        
        self.layout.addLayout(self.meta_layout, stretch=1)
        
        # Badge for extension inside preview_frame
        self.lbl_badge = QLabel(self.preview_frame)
        ext = os.path.splitext(filepath)[1].upper()
        if ext.startswith('.'):
            ext = ext[1:]
        self.lbl_badge.setText(ext if ext else "FILE")
        self.lbl_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Check if preview is available (media files)
        ext_lower = os.path.splitext(filepath)[1].lower()
        is_previewable = ext_lower in VIDEO_EXTS
        
        if is_previewable:
            badge_bg = "rgba(22, 101, 52, 0.85)"
            badge_border = "1px solid #16a34a"
            badge_color = "#ffffff"
        else:
            badge_bg = "rgba(0, 0, 0, 0.7)"
            badge_border = "1px solid #444"
            badge_color = "#aaa"
            
        self.lbl_badge.setStyleSheet(f"""
            background-color: {badge_bg};
            color: {badge_color};
            font-size: 8px;
            font-weight: bold;
            border: {badge_border};
            border-radius: 2px;
            padding: 1px 2px;
        """)
        self.lbl_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        
        self.update_sizes()

    def update_sizes(self):
        # Иконка - квадрат в размер icon_size, строка = icon_size + 4px (2 сверху, 2 снизу)
        self.preview_frame.setFixedSize(self.icon_size, self.icon_size)
        self.setFixedHeight(self.icon_size + 4)
        
        # Скрываем значок расширения на мелких иконках списка (меньше 48px), 
        # так как имя файла уже содержит расширение, а наложение бэджа 28x11
        # на мелкую иконку 32x32 визуально портит ее вид и мешает восприятию.
        if self.icon_size < 48:
            self.lbl_badge.hide()
        else:
            self.lbl_badge.show()
            badge_w = 28
            badge_h = 11
            self.lbl_badge.setGeometry(
                self.icon_size - badge_w,
                self.icon_size - badge_h,
                badge_w,
                badge_h
            )

    def set_icon_size(self, size):
        self.icon_size = size
        self.update_sizes()

    def get_viewer_area(self):
        widget = self.parent()
        while widget is not None:
            if hasattr(widget, 'sync_files_queue'):
                return widget
            widget = widget.parent()
        return None

    def set_preview_image(self, qimage):
        self.preview_image = qimage
        self.placeholder_pixmap = None
        pixmap = QPixmap.fromImage(qimage)
        
        viewer = self.get_viewer_area()
        if viewer and hasattr(viewer, 'file_rotations'):
            angle = viewer.file_rotations.get(os.path.normpath(self.filepath), 0)
            if angle != 0:
                transform = QTransform().rotate(angle)
                pixmap = pixmap.transformed(transform, Qt.TransformationMode.SmoothTransformation)
                
        canvas = _scale_pixmap_to_canvas(pixmap, QSize(self.icon_size, self.icon_size))
        self.lbl_preview.setPixmap(canvas)

    def set_placeholder(self, pixmap):
        self.placeholder_pixmap = pixmap
        self.preview_image = None
        
        viewer = self.get_viewer_area()
        if viewer and hasattr(viewer, 'file_rotations'):
            angle = viewer.file_rotations.get(os.path.normpath(self.filepath), 0)
            if angle != 0:
                transform = QTransform().rotate(angle)
                pixmap = pixmap.transformed(transform, Qt.TransformationMode.SmoothTransformation)
                
        canvas = _scale_pixmap_to_canvas(pixmap, QSize(self.icon_size, self.icon_size))
        self.lbl_preview.setPixmap(canvas)

    def update_rotation(self):
        if getattr(self, 'preview_image', None) is not None:
            self.set_preview_image(self.preview_image)
        elif getattr(self, 'placeholder_pixmap', None) is not None:
            self.set_placeholder(self.placeholder_pixmap)

class SorterGridGroupSeparatorWidget(QFrame):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background-color: #262626;
                border: 1px dashed #4b5563;
                border-radius: 6px;
            }
            QLabel {
                color: #3b82f6;
                font-weight: bold;
                font-size: 11px;
                border: none;
                background: transparent;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Разбор title на общую группу и тип (например, "Изображения (png)" -> "Изображения" и "png")
        import re
        match = re.match(r"^(.*?)\s*\((.*?)\)$", title)
        if match:
            main_part = match.group(1).strip()
            sub_part = match.group(2).strip()
        else:
            main_part = title
            sub_part = "ГРУППА" if AppContext.LANG == "RU" else "GROUP"
        
        lbl_title = QLabel(main_part)
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setWordWrap(True)
        layout.addWidget(lbl_title)
        
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #4b5563; max-height: 1px; border: none;")
        layout.addWidget(line)
        
        lbl_sub = QLabel(sub_part)
        lbl_sub.setStyleSheet("color: #6b7280; font-size: 9px; font-weight: normal; border: none;")
        lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_sub)


class SorterListGroupSeparatorWidget(QWidget):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        
        lbl = QLabel(title)
        lbl.setStyleSheet("color: #3b82f6; font-weight: bold; font-size: 11px; background: transparent;")
        layout.addWidget(lbl)
        
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #4b5563; min-height: 1px; border: none;")
        layout.addWidget(line)

# We import ZoomableGraphicsView from a separate file to keep ui_viewer.py clean and modular.
# But wait! ZoomableGraphicsView was defined inside ui_viewer.py previously.
# Let's write the whole ui_viewer.py including ZoomableGraphicsView to make it single-contained or import it.
# To prevent import errors, we will keep ZoomableGraphicsView directly in ui_viewer.py.

# Let's place ZoomableGraphicsView code back inside ui_viewer.py.
# That ensures no missing files or circular imports.

class ZoomableGraphicsView(QGraphicsView):
    canvas_clicked = pyqtSignal()
    fullscreen_toggled = pyqtSignal()
    folder_dropped = pyqtSignal(str, bool)
    browse_requested = pyqtSignal()

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
        self.text_item = QGraphicsTextItem()
        self.text_item.setDefaultTextColor(QColor(VIEWER_DESIGN['audio_text_color']))
        self.text_item.setFont(QFont(VIEWER_DESIGN['audio_font'], VIEWER_DESIGN['audio_font_size']))
        self.scene.addItem(self.text_item)
        self.text_item.hide()
        
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
            
    def _on_seg_prev(self):
        main_app = find_main_app(self)
        if main_app and hasattr(main_app, 'smart_preview_mgr'):
            main_app.smart_preview_mgr.skip_prev()
            
    def _on_seg_next(self):
        main_app = find_main_app(self)
        if main_app and hasattr(main_app, 'smart_preview_mgr'):
            main_app.smart_preview_mgr.skip_next()
            
    def _on_segment_indicator_clicked(self):
        main_app = find_main_app(self)
        if main_app and hasattr(main_app, 'video_controls'):
            cb = main_app.video_controls.chk_segment_view
            cb.setChecked(not cb.isChecked())
            self.update_segment_indicator()
            
    def update_segment_indicator(self):
        if not hasattr(self, 'segment_indicator'):
            return
            
        main_app = find_main_app(self)
        mgr = getattr(main_app, 'smart_preview_mgr', None)
        
        if self.current_is_video and mgr and mgr.num_segments > 0:
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
        path = ""
        is_external = False
        if md.hasUrls():
            urls = md.urls()
            if urls:
                path = urls[0].toLocalFile()
                is_external = True
        if path:
            self.folder_dropped.emit(path, is_external)
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
        
        self.text_item.setTextWidth(1000)
        self.text_item.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        self.text_item.setDefaultTextColor(QColor("#3b82f6"))
        
        # Настройка выравнивания по центру без HTML
        from PyQt6.QtGui import QTextOption
        doc = self.text_item.document()
        option = QTextOption()
        option.setAlignment(Qt.AlignmentFlag.AlignCenter)
        doc.setDefaultTextOption(option)
        
        self.text_item.setPlainText(f"🎵\n{track_name}")
        
        base_w, base_h = 1280.0, 720.0
        text_rect = self.text_item.boundingRect()
        x_text = (base_w - text_rect.width()) / 2
        y_text = (base_h - text_rect.height()) / 2
        
        self.text_item.setPos(x_text, y_text)
        self.text_item.show()
        
        self.scene.setSceneRect(0, 0, base_w, base_h)
        self.reset_view()

    def show_empty_state(self, message):
        self.current_is_video = False
        if self.time_overlay: self.time_overlay.hide()
        self.clear_scene_content()
        self.text_item.setPlainText(message)
        self.text_item.show()
        
        # Проверяем, выбрана ли папка входящих и не пуста ли она
        show_btn = True
        viewer_area = self.parent()  # SorterViewerArea
        if viewer_area and hasattr(viewer_area, 'get_main_app'):
            main_app = viewer_area.get_main_app()
            if main_app and getattr(main_app, 'UNSORT_DIR', None) and getattr(main_app, 'files_queue', None):
                show_btn = False
                
        base_w, base_h = 1280.0, 720.0
        text_rect = self.text_item.boundingRect()
        x_text = (base_w - text_rect.width()) / 2
        y_text = (base_h - text_rect.height()) / 2 - 40
        self.text_item.setPos(x_text, y_text)
        
        if show_btn:
            btn = QPushButton("Выбрать папку" if AppContext.LANG == "RU" else "Browse Folder")
            btn.setStyleSheet("""
                QPushButton { 
                    background-color: #3b82f6; 
                    color: white; 
                    font-size: 16px; 
                    font-weight: bold; 
                    padding: 10px 20px; 
                    border-radius: 6px; 
                }
                QPushButton:hover { background-color: #2563eb; }
            """)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(self.browse_requested.emit)
            proxy = self.scene.addWidget(btn)
            proxy.setPos((base_w - proxy.preferredSize().width()) / 2, y_text + text_rect.height() + 20)
            
        self.scene.setSceneRect(0, 0, base_w, base_h)
        self.reset_view()

    def clear_scene_content(self):
        if self.current_movie:
            self.current_movie.stop()
            self.current_movie.deleteLater()
            self.current_movie = None
        self.pixmap_item.hide()
        self.video_item.hide()
        self.text_item.hide()
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
            
        self.horizontalScrollBar().setValue(0)
        self.verticalScrollBar().setValue(0)
        
        active_item = None
        if self.video_item.isVisible():
            active_item = self.video_item
        elif self.pixmap_item.isVisible() and not self.pixmap_item.pixmap().isNull():
            active_item = self.pixmap_item
        elif self.text_item.isVisible():
            active_item = self.text_item
            
        if active_item and active_item != self.text_item:
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
        if self.video_item.isVisible() or self.text_item.isVisible():
            return
        if not hasattr(self, '_current_rotation'):
            self._current_rotation = 0
        self._current_rotation = (self._current_rotation + angle) % 360
        self.reset_view()

    def set_absolute_rotation(self, angle):
        if self.video_item.isVisible() or self.text_item.isVisible():
            return
        self._current_rotation = angle % 360
        self.reset_view()

    def set_background_color(self, color):
        self.setBackgroundBrush(QColor(color))
        self.setStyleSheet(f"background-color: {color}; border: none;")


class SorterBaseListView(QListWidget):
    """Base class for Grid and List views with shared keyboard and drag & drop logic."""
    folder_dropped = pyqtSignal(str, bool)
    item_double_clicked = pyqtSignal(str) # Emits absolute path to switch to Single view
    send_to_editor_requested = pyqtSignal(str, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        
        # Design TITAN Style
        self.setStyleSheet("""
            QListWidget {
                background-color: #1e1e1e;
                border: none;
                outline: none;
            }
            QListWidget::item {
                background-color: #2b2b2b;
                color: #ddd;
                border: 1px solid #444;
                border-radius: 6px;
                margin: 4px;
                padding: 0px;
            }
            QListWidget::item:hover {
                background-color: #353535;
                border-color: #555;
            }
            QListWidget::item:selected {
                background-color: #1e3a8a;
                border-color: #3b82f6;
                color: white;
            }
        """)
            
        # Hover Player
        self.hover_player = QMediaPlayer()
        self.hover_audio = QAudioOutput()
        self.hover_player.setAudioOutput(self.hover_audio)
        self.hover_audio.setVolume(0.0) # Zero volume for hover
        
        self.hover_video_widget = None
        self.hover_movie = None
        self.current_hover_item = None
        self.current_hover_path = ""
        
        self.entered.connect(self._on_item_hover_entered)
        self.itemDoubleClicked.connect(self._on_double_clicked)
        
        # Контекстное меню ПКМ
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        
        # Debounce timer to prevent rapid hover player rebuilding
        self.hover_timer = QTimer(self)
        self.hover_timer.setSingleShot(True)
        self.hover_timer.setInterval(250)
        self.hover_timer.timeout.connect(self._start_hover_playback)

        # Timer for large preview on hover
        self.large_preview_timer = QTimer(self)
        self.large_preview_timer.setSingleShot(True)
        self.large_preview_timer.setInterval(100) # 0.1 seconds (default)
        self.large_preview_timer.timeout.connect(self._show_large_preview)
        
        # Предохранитель дребезга на 100 мс перед началом отсчета
        self.debounce_timer = QTimer(self)
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(100)
        self.debounce_timer.timeout.connect(self._on_debounce_timeout)

        # Таймер периодического отслеживания положения курсора
        self.popup_track_timer = QTimer(self)
        self.popup_track_timer.setInterval(100)
        self.popup_track_timer.timeout.connect(self._track_popup_mouse)
        
        self.large_preview_popup = None

        # Anchor для Shift-выделения (как в Проводнике Windows)
        self._selection_anchor: int = -1
        self.currentItemChanged.connect(self._on_current_item_changed)

    def check_hover_under_mouse(self):
        """Проверяет элемент под курсором мыши и при необходимости вызывает появление ховера."""
        if not self.isVisible():
            return
        from PyQt6.QtGui import QCursor
        pos = self.viewport().mapFromGlobal(QCursor.pos())
        if self.viewport().rect().contains(pos):
            index = self.indexAt(pos)
            if index.isValid():
                self._on_item_hover_entered(index)
            else:
                if self.current_hover_item is not None:
                    if not self.large_preview_popup:
                        self._stop_hover_playback(force=True)
                        self.debounce_timer.stop()
                        self.large_preview_timer.stop()

    def _on_current_item_changed(self, current, previous):
        if current:
            modifiers = QApplication.keyboardModifiers()
            if not (modifiers & Qt.KeyboardModifier.ShiftModifier):
                row = self.row(current)
                if row >= 0:
                    self._selection_anchor = row

    def _get_action_key(self, action_id: str):
        viewer_area = self.get_viewer_area()
        if not viewer_area:
            return None
        main_app = viewer_area.get_main_app()
        if not main_app or not hasattr(main_app, '_hotkey_registry'):
            return None
        registry = main_app._hotkey_registry
        key_str = registry.get_effective_key(action_id)
        if not key_str:
            return None
        seq = QKeySequence(key_str)
        if seq.isEmpty():
            return None
        return seq[0].key()

    def _get_file_row(self, row: int) -> bool:
        """Возвращает True если элемент row является файлом (не группировщиком/сепаратором)."""
        item = self.item(row)
        return item is not None and item.data(Qt.ItemDataRole.UserRole) is not None

    def _next_file_row(self, start: int, direction: int) -> int:
        """Ищет ближайший файловый row в заданном направлении, пропуская сепараторы."""
        count = self.count()
        row = start
        for _ in range(count):
            row = (row + direction) % count
            if self._get_file_row(row):
                return row
        return start  # фолбек если файлов нет вообще

    def _apply_key_navigation(self, new_row: int, modifiers) -> None:
        """Применяет навигационный переход к new_row с учётом модификаторов Shift/Ctrl."""
        shift = modifiers & Qt.KeyboardModifier.ShiftModifier
        ctrl = modifiers & Qt.KeyboardModifier.ControlModifier

        if not self._get_file_row(new_row):
            return

        if shift:
            # Диапазонное выделение от anchor до new_row (как Shift+Click в Проводнике)
            anchor = self._selection_anchor if self._selection_anchor >= 0 else new_row
            lo, hi = min(anchor, new_row), max(anchor, new_row)
            
            # Если Ctrl не зажат, очищаем предыдущие выделения
            if not ctrl:
                self.clearSelection()
                
            for r in range(lo, hi + 1):
                item = self.item(r)
                if item and item.data(Qt.ItemDataRole.UserRole):
                    item.setSelected(True)
            # Устанавливаем текущий без изменения якоря
            self.setCurrentRow(new_row, QItemSelectionModel.SelectionFlag.Current)
        elif ctrl:
            # Ctrl: добавляем элемент к выделению без сброса остальных
            item = self.item(new_row)
            if item:
                item.setSelected(True)
            self.setCurrentRow(new_row, QItemSelectionModel.SelectionFlag.Current)
        else:
            # Без модификаторов: сбросить выделение, выбрать только новый элемент
            self._selection_anchor = new_row
            self.clearSelection()
            item = self.item(new_row)
            if item:
                item.setSelected(True)
            self.setCurrentRow(new_row, QItemSelectionModel.SelectionFlag.Current)

        self.scrollToItem(self.item(new_row))
        # Синхронизируем тулбар главного приложения
        self._notify_viewer_area(new_row)

    def _notify_viewer_area(self, row: int) -> None:
        """Уведомляет SorterViewerArea о смене активного элемента для синхронизации тулбара."""
        viewer_area = self.get_viewer_area()
        if viewer_area and hasattr(viewer_area, '_sync_main_app_index'):
            viewer_area._sync_main_app_index(row)

    def keyPressEvent(self, event) -> None:
        """Обработка стрелок с поддержкой multi-select (Shift/Ctrl) как в Проводнике Windows."""
        key = event.key()
        modifiers = event.modifiers()
        count = self.count()

        if count == 0:
            super().keyPressEvent(event)
            return

        # Получаем коды клавиш из реестра горячих клавиш
        key_up = self._get_action_key("move_up")
        key_down = self._get_action_key("move_down")
        key_left = self._get_action_key("prev_file")
        key_right = self._get_action_key("next_file")

        # Если клавиши не настроены в реестре, используем дефолтные стрелки
        if not key_up: key_up = Qt.Key.Key_Up
        if not key_down: key_down = Qt.Key.Key_Down
        if not key_left: key_left = Qt.Key.Key_Left
        if not key_right: key_right = Qt.Key.Key_Right

        nav_keys = (key_up, key_down, key_left, key_right)

        if key not in nav_keys:
            super().keyPressEvent(event)
            return

        current_row = self.currentRow()
        if current_row < 0:
            current_row = 0

        # Определяем режим (Grid=IconMode, List=ListMode) по родительскому ViewerArea
        viewer_area = self.get_viewer_area()
        is_grid = (viewer_area is not None and
                   viewer_area.stack.currentIndex() == 1)

        if is_grid:
            cols = viewer_area.get_grid_columns_count() if hasattr(viewer_area, 'get_grid_columns_count') else 1
            cols = max(1, cols)

            if key == key_right:
                new_row = self._next_file_row(current_row, 1)
            elif key == key_left:
                new_row = self._next_file_row(current_row, -1)
            elif key == key_down:
                candidate = current_row + cols
                # Ищем ближайший файловый элемент вниз по строке
                while candidate < count and not self._get_file_row(candidate):
                    candidate += 1
                new_row = candidate if candidate < count else current_row
            elif key == key_up:
                candidate = current_row - cols
                # Ищем ближайший файловый элемент вверх по строке
                while candidate >= 0 and not self._get_file_row(candidate):
                    candidate -= 1
                new_row = candidate if candidate >= 0 else current_row
            else:
                new_row = current_row
        else:
            # List-режим: Left/Right = Up/Down (одномерный список)
            if key in (key_right, key_down):
                new_row = self._next_file_row(current_row, 1)
            elif key in (key_left, key_up):
                new_row = self._next_file_row(current_row, -1)
            else:
                new_row = current_row

        if new_row != current_row:
            self._apply_key_navigation(new_row, modifiers)

        event.accept()

    def _on_large_preview_closed(self):
        self.large_preview_popup = None
        self.current_hover_item = None
        self.current_hover_path = ""

    def mouseMoveEvent(self, event):
        if not self.isVisible():
            return
        super().mouseMoveEvent(event)
        index = self.indexAt(event.pos())
        if index.isValid():
            item = self.itemFromIndex(index)
            if item != self.current_hover_item:
                self._on_item_hover_entered(index)
        else:
            # Мышь ушла на пустое место списка
            if self.current_hover_item is not None:
                if not self.large_preview_popup:
                    self._stop_hover_playback(force=True)
                    self.debounce_timer.stop()
                    self.large_preview_timer.stop()

    def get_video_widget(self):
        try:
            if not hasattr(self, 'hover_video_widget') or self.hover_video_widget is None:
                raise RuntimeError("no widget")
            self.hover_video_widget.parent()
        except (RuntimeError, AttributeError):
            logging.info("Recreating deleted/missing hover_video_widget")
            self.hover_video_widget = QVideoWidget()
            self.hover_video_widget.hide()
            self.hover_player.setVideoOutput(self.hover_video_widget)
        return self.hover_video_widget

    def leaveEvent(self, event):
        # Если зажата левая кнопка (выделение или перетаскивание) — не закрывать
        from PyQt6.QtWidgets import QApplication
        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            super().leaveEvent(event)
            return
            
        # Если попап открыт, то пусть закрытием управляет таймер отслеживания (popup_track_timer)
        if hasattr(self, 'large_preview_popup') and self.large_preview_popup:
            super().leaveEvent(event)
            return
            
        # Иначе останавливаем обычный ховер и таймеры
        self._stop_hover_playback(force=True)
        self.debounce_timer.stop()
        self.large_preview_timer.stop()
        super().leaveEvent(event)

    def hideEvent(self, event):
        self._stop_hover_playback(force=True)
        self.debounce_timer.stop()
        self.large_preview_timer.stop()
        super().hideEvent(event)

    def _on_item_hover_entered(self, index):
        if not self.isVisible():
            return
        viewer_area = self.get_viewer_area()
        if viewer_area and getattr(viewer_area, 'disable_hover_preview', False):
            if self.current_hover_item is not None or self.large_preview_popup is not None:
                self._stop_hover_playback(force=True)
            return
            
        item = self.itemFromIndex(index)
        if item == self.current_hover_item:
            return
        
        # Сразу останавливаем таймеры и закрываем старый попап
        self._stop_hover_playback(force=True)
        self.debounce_timer.stop()
        self.large_preview_timer.stop()
        
        if item:
            p = item.data(Qt.ItemDataRole.UserRole)
            if not p:
                self.current_hover_item = None
                self.current_hover_path = None
                return
                
            self.current_hover_item = item
            self.current_hover_path = ensure_long_path(p)
            
            # Запускаем предохранитель дребезга на 100 мс
            self.debounce_timer.start(100)

    def _on_debounce_timeout(self):
        # 100 мс прошло. Запускаем мини-плеер и таймер задержки большого просмотра
        if self.current_hover_item:
            self.hover_timer.start()
            
            viewer_area = self.get_viewer_area()
            main_app = viewer_area.get_main_app() if viewer_area and hasattr(viewer_area, 'get_main_app') else None
            delay_sec = 0.4
            if main_app and hasattr(main_app, 'config'):
                try:
                    delay_sec = float(main_app.config.get("hover_delay", 0.4))
                except (ValueError, TypeError):
                    delay_sec = 0.4
            
            self.large_preview_timer.setInterval(int(delay_sec * 1000))
            self.large_preview_timer.start()

    def _start_hover_playback(self):
        if not self.current_hover_path or not os.path.exists(self.current_hover_path): return
        
        from utils_extensions import VIDEO_EXTS, AUDIO_EXTS, IMAGE_EXTS
        from utils_io import strip_long_path_prefix
        norm_path = os.path.normpath(strip_long_path_prefix(self.current_hover_path))
        main_app = self.get_main_app()
        if main_app and hasattr(main_app, 'locked_files') and norm_path in main_app.locked_files:
            return
            
        ext = os.path.splitext(self.current_hover_path)[1].lower()
        
        # Check if multiple items are selected. If so, don't play anything.
        if len(self.selectedItems()) > 1:
            return
            
        widget = self.itemWidget(self.current_hover_item)
        if not widget:
            return
            
        # Мини-ховер для видео и gif отключён: используется только окно предпросмотра (LargePreviewPopup)
        pass

    def _update_hover_movie_frame(self):
        if self.hover_movie and self.current_hover_item:
            widget = self.itemWidget(self.current_hover_item)
            if widget and hasattr(widget, 'preview_frame'):
                pixmap = self.hover_movie.currentPixmap()
                target_size = widget.preview_frame.size() - QSize(4, 4)
                scaled = pixmap.scaled(
                    target_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                widget.lbl_preview.setPixmap(scaled)

    def _stop_hover_playback(self, force=False):
        if not force:
            import time
            if hasattr(self, '_popup_open_time') and (time.time() - self._popup_open_time) < 0.15:
                return

        self.hover_timer.stop()
        self.large_preview_timer.stop()
        self.popup_track_timer.stop()
        
        if hasattr(self, 'large_preview_popup') and self.large_preview_popup:
            popup = self.large_preview_popup
            self.large_preview_popup = None
            try:
                popup.cleanup()
                popup.close()
            except Exception:
                pass

        if self.hover_movie:
            self.hover_movie.stop()
            self.hover_movie.deleteLater()
            self.hover_movie = None
            
        self.hover_player.stop()
        self.hover_player.setSource(QUrl())
        
        video_widget = self.get_video_widget()
        video_widget.hide()
        
        self.current_hover_item = None
        self.current_hover_path = ""

    def _track_popup_mouse(self):
        if hasattr(self, 'large_preview_popup') and self.large_preview_popup and not self.large_preview_popup.isHidden():
            from PyQt6.QtCore import QRect
            pos = QCursor.pos()
            popup_geom = self.large_preview_popup.geometry()
            
            # Получаем геометрию текущей плитки в глобальных координатах
            tile_geom = QRect()
            if self.current_hover_item:
                rect = self.visualItemRect(self.current_hover_item)
                tile_global_pos = self.viewport().mapToGlobal(rect.topLeft())
                tile_geom = QRect(tile_global_pos, rect.size())
            
            in_popup = popup_geom.adjusted(-8, -8, 8, 8).contains(pos)
            in_tile = tile_geom.adjusted(-8, -8, 8, 8).contains(pos)
            
            logging.debug(f"[TrackPopup] Pos: {pos}, PopupGeom: {popup_geom}, TileGeom: {tile_geom}, in_popup: {in_popup}, in_tile: {in_tile}")
            
            # Если курсор вне попапа и вне плитки (с буфером безопасности 8px), закрываем попап
            if not in_popup and not in_tile:
                logging.info(f"[TrackPopup] Closing popup because cursor {pos} is outside popup {popup_geom} (in: {in_popup}) and tile {tile_geom} (in: {in_tile})")
                self._stop_hover_playback(force=True)
        else:
            if hasattr(self, 'popup_track_timer'):
                self.popup_track_timer.stop()

    def get_main_app(self):
        """Поднимается по дереву родителей до первого объекта с global_volume.
        Это надёжнее чем фиксированное количество уровней (parent -> grandparent),
        так как глубина вложенности может меняться.
        """
        widget = self.parent()
        while widget is not None:
            if hasattr(widget, 'global_volume'):
                return widget
            widget = widget.parent()
        return None

    def get_viewer_area(self):
        """Поднимается по дереву родителей до первого объекта с методом sync_files_queue."""
        widget = self.parent()
        while widget is not None:
            if hasattr(widget, 'sync_files_queue'):
                return widget
            widget = widget.parent()
        return None

    def _on_popup_destroyed(self):
        self.large_preview_popup = None

    def _show_large_preview(self):
        # Если идет загрузка файлов — не открываем окно быстрого просмотра
        viewer_area = self.get_viewer_area()
        if viewer_area and hasattr(viewer_area, 'loading_overlay') and not viewer_area.loading_overlay.isHidden():
            return
            
        if not self.current_hover_path or not os.path.exists(self.current_hover_path):
            return
            
        from utils_extensions import VIDEO_EXTS, AUDIO_EXTS, IMAGE_EXTS
        from utils_io import strip_long_path_prefix
        norm_path = os.path.normpath(strip_long_path_prefix(self.current_hover_path))
        main_app = self.get_main_app()
        if main_app and hasattr(main_app, 'locked_files') and norm_path in main_app.locked_files:
            return
            
        ext = os.path.splitext(self.current_hover_path)[1].lower()
        is_media = ext in VIDEO_EXTS
        if not is_media:
            return
            
        # Stop mini hover playback
        self.hover_timer.stop()
        self.hover_player.stop()
        if self.hover_movie:
            self.hover_movie.stop()
            
        # Автовыделение элемента, если выделено 0 или 1 файл
        selected_items = self.selectedItems()
        if len(selected_items) <= 1:
            if self.current_hover_item and (not selected_items or selected_items[0] != self.current_hover_item):
                self.clearSelection()
                self.current_hover_item.setSelected(True)
                self.setCurrentItem(self.current_hover_item)
            
        main_app = self.get_main_app()
        self.large_preview_popup = LargePreviewPopup(self.current_hover_path, main_app, self.window())
        self.large_preview_popup.destroyed.connect(self._on_popup_destroyed)
        
        # Размеры попапа, установленные пользователем
        viewer_area = self.get_viewer_area()
        popup_size = viewer_area.popup_size if (viewer_area and hasattr(viewer_area, 'popup_size')) else QSize(640, 520)
        popup_w = popup_size.width()
        popup_h = popup_size.height()
        
        # Позиционирование
        pos = QCursor.pos()
        app_geom = self.window().geometry()
        
        if self.current_hover_item:
            rect = self.visualItemRect(self.current_hover_item)
            tile_global_pos = self.viewport().mapToGlobal(rect.topLeft())
            tile_w = rect.width()
            tile_h = rect.height()
            
            # Область превью: ширина равна ширине плитки, высота исключает текстовый блок 42px
            preview_w = tile_w
            preview_h = tile_h - 42
            
            # Внутренний прямоугольник превью с отступами: 15% справа/слева и 20% сверху/снизу
            dx = int(0.15 * preview_w)
            dy = int(0.20 * preview_h)
            X_inner_left = tile_global_pos.x() + dx
            X_inner_right = tile_global_pos.x() + preview_w - dx
            Y_inner_top = tile_global_pos.y() + dy
            Y_inner_bottom = tile_global_pos.y() + preview_h - dy
            
            # Считаем свободное место справа и слева до краев окна приложения
            space_right = app_geom.right() - X_inner_right
            space_left = X_inner_left - app_geom.left()
            
            # Выбираем направление по горизонтали
            if space_right >= space_left:
                x_start = X_inner_left
                dir_x = 'right'
            else:
                x_start = X_inner_right
                dir_x = 'left'
                
            # Считаем свободное место снизу и сверху до краев окна приложения
            space_bottom = app_geom.bottom() - Y_inner_bottom
            space_top = Y_inner_top - app_geom.top()
            
            # Выбираем направление по вертикали
            if space_bottom >= space_top:
                y_start = Y_inner_bottom
                dir_y = 'bottom'
            else:
                y_start = Y_inner_top
                dir_y = 'top'
                
            # Рассчитываем максимально доступное пространство для попапа в выбранном направлении
            max_w = (app_geom.right() - x_start) if dir_x == 'right' else (x_start - app_geom.left())
            max_h = (app_geom.bottom() - y_start) if dir_y == 'bottom' else (y_start - app_geom.top())
            
            # Пропорциональное масштабирование, чтобы попап поместился до краев экрана
            scale = min(1.0, max_w / popup_w, max_h / popup_h)
            
            # Задаем фактический размер (не меньше минимального)
            actual_w = max(320, int(popup_w * scale))
            actual_h = max(260, int(popup_h * scale))
            
            # Финальные координаты верхнего левого угла
            x = x_start if dir_x == 'right' else (x_start - actual_w)
            y = y_start if dir_y == 'bottom' else (y_start - actual_h)
            
            # Корректируем координаты, чтобы попап гарантированно не вылетал за границы окна приложения (экрана)
            if x + actual_w > app_geom.right():
                x = app_geom.right() - actual_w
            if x < app_geom.left():
                x = app_geom.left()
                
            if y + actual_h > app_geom.bottom():
                y = app_geom.bottom() - actual_h
            if y < app_geom.top():
                y = app_geom.top()
            
            popup_w = actual_w
            popup_h = actual_h
        else:
            # Фолбэк на курсор, если плитки вдруг нет
            x = pos.x() - 50
            y = pos.y() - 20
            
            # Гарантируем, что попап не выходит за горизонтальные границы приложения
            if x + popup_w > app_geom.right():
                x = app_geom.right() - popup_w
            if x < app_geom.left():
                x = app_geom.left()
                
            # Гарантируем, что попап не выходит за вертикальные границы приложения
            if y + popup_h > app_geom.bottom():
                y = app_geom.bottom() - popup_h
            if y < app_geom.top():
                y = app_geom.top()
            
        self.large_preview_popup.setFixedSize(popup_w, popup_h)
        self.large_preview_popup.move(x, y)
        import time
        self._popup_open_time = time.time()
        self.large_preview_popup.show()
        
        # Запускаем отслеживание координат мыши
        self.popup_track_timer.start(100)

    def _on_double_clicked(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self._stop_hover_playback(force=True)
            self.item_double_clicked.emit(path)

    def mousePressEvent(self, event):
        """Обработка клика средней кнопкой мыши — открыть папку с файлом."""
        if event.button() == Qt.MouseButton.MiddleButton:
            index = self.indexAt(event.position().toPoint())
            if index.isValid() and len(self.selectedItems()) <= 1:
                item = self.itemFromIndex(index)
                if item:
                    path = item.data(Qt.ItemDataRole.UserRole)
                    if path:
                        self._open_folder_with_focus(path)
        super().mousePressEvent(event)

    def _on_context_menu(self, pos):
        """Контекстное меню ПКМ — поддерживает одиночное и множественное выделение."""
        selected_items = self.selectedItems()
        item = self.itemAt(pos)
        if item and item not in selected_items:
            self.clearSelection()
            item.setSelected(True)
            selected_items = [item]
            
        if not selected_items:
            return
            
        paths = [i.data(Qt.ItemDataRole.UserRole) for i in selected_items if i.data(Qt.ItemDataRole.UserRole)]
        paths = [p for p in paths if os.path.exists(p)]
        if not paths:
            return

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

        video_exts = VIDEO_EXTS
        audio_exts = AUDIO_EXTS
        image_exts = IMAGE_EXTS

        if len(paths) == 1:
            path = paths[0]
            ext = os.path.splitext(path)[1].lower()
            
            act_open = QAction(AppContext.tr("srt_ctx_open_file"), self)
            act_open.triggered.connect(lambda Checked, p=path: self._open_file(p))
            menu.addAction(act_open)

            act_folder = QAction(AppContext.tr("srt_ctx_open_folder"), self)
            act_folder.triggered.connect(lambda Checked, p=path: self._open_folder_with_focus(p))
            menu.addAction(act_folder)
            
            if ext in video_exts:
                menu.addSeparator()
                act_vconv = QAction(AppContext.tr("srt_ctx_convert_video"), self)
                act_vconv.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("video_conv", p))
                menu.addAction(act_vconv)
                
                act_aconv = QAction(AppContext.tr("srt_ctx_convert_audio_to"), self)
                act_aconv.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("audio_conv", p))
                menu.addAction(act_aconv)
                
                act_vedit = QAction(AppContext.tr("srt_ctx_edit_video"), self)
                act_vedit.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("video_edit", p))
                menu.addAction(act_vedit)
                
            elif ext in audio_exts:
                menu.addSeparator()
                act_aconv = QAction(AppContext.tr("srt_ctx_convert_audio"), self)
                act_aconv.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("audio_conv", p))
                menu.addAction(act_aconv)
                
                act_aedit = QAction(AppContext.tr("srt_ctx_edit_audio"), self)
                act_aedit.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("audio_edit", p))
                menu.addAction(act_aedit)
                
            elif ext in image_exts:
                menu.addSeparator()
                act_iconv = QAction(AppContext.tr("srt_ctx_convert_image"), self)
                act_iconv.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("image_conv", p))
                menu.addAction(act_iconv)
                
                if ext == '.gif':
                    from PyQt6.QtGui import QImageReader
                    reader = QImageReader(path)
                    if reader.supportsAnimation() and reader.imageCount() > 1:
                        act_vconv = QAction(AppContext.tr("srt_ctx_convert_video"), self)
                        act_vconv.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("video_conv", p))
                        menu.addAction(act_vconv)
        else:
            is_all_video = all(os.path.splitext(p)[1].lower() in video_exts for p in paths)
            is_all_audio = all(os.path.splitext(p)[1].lower() in audio_exts for p in paths)
            is_all_image = all(os.path.splitext(p)[1].lower() in image_exts for p in paths)
            
            if is_all_video:
                act_vconv = QAction(AppContext.tr("srt_ctx_convert_video_count").format(len(paths)), self)
                act_vconv.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("video_conv", p))
                menu.addAction(act_vconv)
                
                act_aconv = QAction(AppContext.tr("srt_ctx_convert_audio_to_count").format(len(paths)), self)
                act_aconv.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("audio_conv", p))
                menu.addAction(act_aconv)
                
            elif is_all_audio:
                act_aconv = QAction(AppContext.tr("srt_ctx_convert_audio_count").format(len(paths)), self)
                act_aconv.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("audio_conv", p))
                menu.addAction(act_aconv)
                
            elif is_all_image:
                act_iconv = QAction(AppContext.tr("srt_ctx_convert_image_count").format(len(paths)), self)
                act_iconv.triggered.connect(lambda Checked, p=paths: self.send_to_editor_requested.emit("image_conv", p))
                menu.addAction(act_iconv)

        menu.addSeparator()
        if len(paths) <= 1:
            del_label = AppContext.tr("srt_ctx_delete_files")
        else:
            del_label = AppContext.tr("srt_ctx_delete_files_count").format(len(paths))
        act_delete = QAction(del_label, self)
        act_delete.triggered.connect(lambda checked, p=paths: self.delete_files_requested(p))
        menu.addAction(act_delete)

        if menu.actions():
            menu.exec(self.mapToGlobal(pos))

    def delete_files_requested(self, file_paths):
        main_app = self.get_main_app()
        if main_app and hasattr(main_app, 'delete_files_permanently'):
            main_app.delete_files_permanently(file_paths)

    def _open_file(self, path):
        """Открыть файл в программе по умолчанию ОС."""
        try:
            os.startfile(os.path.normpath(path))
        except Exception as e:
            logging.error(f"Cannot open file '{path}': {e}")

    def _open_folder_with_focus(self, path):
        """Открыть папку в Проводнике с выделением файла."""
        try:
            from utils_common import reveal_in_explorer
            reveal_in_explorer(path)
        except Exception as e:
            logging.error(f"Cannot open folder for '{path}': {e}")
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
        path = ""
        is_external = False
        if md.hasUrls():
            urls = md.urls()
            if urls:
                path = urls[0].toLocalFile()
                is_external = True
        if path:
            self.folder_dropped.emit(path, is_external)
            event.acceptProposedAction()
        else:
            event.ignore()


class SorterGridView(SorterBaseListView):
    """Grid View (IconMode) showing thumbnails with Ctrl+Wheel scaling."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setWordWrap(True)
        self.setSpacing(4)
        
        self.tile_size = 128
        self._update_grid_sizes()
        
        self.zoom_commit_timer = QTimer(self)
        self.zoom_commit_timer.setSingleShot(True)
        self.zoom_commit_timer.timeout.connect(self._commit_zoom)
        self._commit_index = 0
        self._zoom_session_id = 0
        
        # Make items background and border transparent in Grid mode to avoid selection overlays
        self.setStyleSheet("""
            QListWidget {
                background-color: #1e1e1e;
                border: none;
                outline: none;
                padding-bottom: 20px;
            }
            QListWidget::item {
                background-color: transparent;
                border: none;
                border-radius: 0px;
                margin: 4px;
                padding: 0px;
            }
            QListWidget::item:hover {
                background-color: transparent;
                border: none;
            }
            QListWidget::item:selected {
                background-color: transparent;
                border: none;
                color: white;
            }
        """)

    def selectionChanged(self, selected, deselected):
        super().selectionChanged(selected, deselected)
        for index in selected.indexes():
            item = self.item(index.row())
            if item:
                widget = self.itemWidget(item)
                if widget and hasattr(widget, 'set_selected'):
                    widget.set_selected(True)
        for index in deselected.indexes():
            item = self.item(index.row())
            if item:
                widget = self.itemWidget(item)
                if widget and hasattr(widget, 'set_selected'):
                    widget.set_selected(False)

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            viewer_area = self.get_viewer_area()
            old_cols = viewer_area.get_grid_columns_count() if viewer_area and hasattr(viewer_area, 'get_grid_columns_count') else 1
            
            delta = event.angleDelta().y()
            if delta > 0:
                self.tile_size = min(256, self.tile_size + 16)
            else:
                self.tile_size = max(64, self.tile_size - 16)
            self._update_grid_sizes()
            self._zoom_session_id += 1
            
            # Scale only visible item custom widgets for ultra-smooth zoom
            viewport_rect = self.viewport().rect()
            start_index = self.indexAt(viewport_rect.topLeft())
            end_index = self.indexAt(viewport_rect.bottomRight())
            
            start_row = start_index.row() if start_index.isValid() else 0
            end_row = end_index.row() if end_index.isValid() else self.count() - 1
            if end_row < 0:
                end_row = self.count() - 1
            
            _thumb_exts = VIDEO_EXTS
            target_thumb_size = QSize(max(256, self.tile_size), max(256, self.tile_size))
            
            for i in range(max(0, start_row), min(self.count(), end_row + 1)):
                item = self.item(i)
                widget = self.itemWidget(item)
                if widget and hasattr(widget, 'set_tile_size'):
                    widget.set_tile_size(self.tile_size)
                    item.setSizeHint(widget.sizeHint())
                    
                    filepath = widget.filepath
                    norm_path = os.path.normpath(filepath)
                    ext = os.path.splitext(filepath)[1].lower()
                    
                    if norm_path in ThumbnailLoader.inst().cache:
                        widget.set_preview_image(ThumbnailLoader.inst().cache[norm_path])
                    elif ext in _thumb_exts:
                        ThumbnailLoader.inst().get_thumbnail(filepath, target_thumb_size)
                        if widget.placeholder_pixmap:
                            widget.set_placeholder(widget.placeholder_pixmap)
                    elif widget.placeholder_pixmap:
                        widget.set_placeholder(widget.placeholder_pixmap)
            
            self.doItemsLayout()
            self.viewport().update()
            
            self.zoom_commit_timer.start(250)
            
            if viewer_area and hasattr(viewer_area, 'sync_files_queue'):
                main_app = viewer_area.get_main_app()
                group_enabled = main_app.config.get("group_by_sort", False) if main_app and hasattr(main_app, 'config') else False
                if group_enabled and hasattr(viewer_area, 'current_inbox_dir') and viewer_area.current_inbox_dir and viewer_area.loading_files:
                    new_cols = viewer_area.get_grid_columns_count()
                    if old_cols != new_cols:
                        viewer_area._last_cols_count = new_cols
                        viewer_area.loading_target_select_idx = viewer_area.get_current_selected_index()
                        viewer_area.sync_files_queue(viewer_area.current_inbox_dir, viewer_area.loading_files, viewer_area.loading_target_select_idx, silent=True)
            
            event.accept()
        else:
            super().wheelEvent(event)

    def _update_grid_sizes(self):
        self.setGridSize(QSize(self.tile_size + 4, self.tile_size + 42))

    def _commit_zoom(self):
        self._commit_index = 0
        self._commit_batch(self._zoom_session_id)

    def _commit_batch(self, session_id):
        if session_id != self._zoom_session_id:
            return
            
        if self._commit_index >= self.count():
            self.doItemsLayout()
            self.viewport().update()
            return
            
        end = min(self.count(), self._commit_index + 500)
        _thumb_exts = VIDEO_EXTS
        target_thumb_size = QSize(max(256, self.tile_size), max(256, self.tile_size))
        
        for i in range(self._commit_index, end):
            item = self.item(i)
            widget = self.itemWidget(item)
            if widget and hasattr(widget, 'set_tile_size'):
                if widget.tile_size != self.tile_size:
                    widget.set_tile_size(self.tile_size)
                    item.setSizeHint(widget.sizeHint())
                    
                    filepath = widget.filepath
                    norm_path = os.path.normpath(filepath)
                    ext = os.path.splitext(filepath)[1].lower()
                    
                    if norm_path in ThumbnailLoader.inst().cache:
                        widget.set_preview_image(ThumbnailLoader.inst().cache[norm_path])
                    elif ext in _thumb_exts:
                        ThumbnailLoader.inst().get_thumbnail(filepath, target_thumb_size)
                        if widget.placeholder_pixmap:
                            widget.set_placeholder(widget.placeholder_pixmap)
                    elif widget.placeholder_pixmap:
                        widget.set_placeholder(widget.placeholder_pixmap)
                        
        self._commit_index = end
        QTimer.singleShot(0, lambda: self._commit_batch(session_id))


class SorterListView(SorterBaseListView):
    """List View (ListMode) showing thumbnails and details (filename, size)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.ListMode)
        self.setSpacing(1)
        self.icon_size = 44
        
        # Переопределяем stylesheet: компактные строки без лишних отступов
        self.setStyleSheet("""
            QListWidget {
                background-color: #1e1e1e;
                border: none;
                outline: none;
            }
            QListWidget::item {
                background-color: #2b2b2b;
                color: #ddd;
                border: none;
                border-bottom: 1px solid #333;
                border-radius: 0px;
                margin: 0px;
                padding: 0px;
            }
            QListWidget::item:first {
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QListWidget::item:last {
                border-bottom: none;
                border-bottom-left-radius: 4px;
                border-bottom-right-radius: 4px;
            }
            QListWidget::item:hover {
                background-color: #333333;
            }
            QListWidget::item:selected {
                background-color: #1e3a8a;
                border-color: #3b82f6;
                color: white;
            }
        """)

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.icon_size = min(128, self.icon_size + 8)
            else:
                self.icon_size = max(32, self.icon_size - 8)
            
            # Scale all items
            for i in range(self.count()):
                item = self.item(i)
                widget = self.itemWidget(item)
                if widget and hasattr(widget, 'set_icon_size'):
                    widget.set_icon_size(self.icon_size)
                    item.setSizeHint(widget.sizeHint())
                    
                    # Reload cached thumbnail if exists
                    filepath = widget.filepath
                    norm_path = os.path.normpath(filepath)
                    if norm_path in ThumbnailLoader.inst().cache:
                        widget.set_preview_image(ThumbnailLoader.inst().cache[norm_path])
                    elif widget.placeholder_pixmap:
                        widget.set_placeholder(widget.placeholder_pixmap)
                        
            self.doItemsLayout()
            self.viewport().update()
            event.accept()
        else:
            super().wheelEvent(event)


class SorterPlaceholderWidget(QWidget):
    folder_dropped = pyqtSignal(str, bool)
    browse_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)
        
        self.lbl_message = QLabel()
        self.lbl_message.setStyleSheet("color: #888888; font-size: 18px; font-weight: 500;")
        self.lbl_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_message.setWordWrap(True)
        layout.addWidget(self.lbl_message)
        
        self.btn_browse = QPushButton()
        self.btn_browse.setStyleSheet("""
            QPushButton { 
                background-color: #3b82f6; 
                color: white; 
                font-size: 16px; 
                font-weight: bold; 
                padding: 12px 24px; 
                border-radius: 6px; 
                border: none;
            }
            QPushButton:hover { background-color: #2563eb; }
            QPushButton:pressed { background-color: #1d4ed8; }
        """)
        self.btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse.clicked.connect(self.browse_requested.emit)
        layout.addWidget(self.btn_browse, 0, Qt.AlignmentFlag.AlignCenter)

    def set_message(self, message, show_button=True):
        self.lbl_message.setText(message)
        self.btn_browse.setText("Выбрать папку" if AppContext.LANG == "RU" else "Browse Folder")
        if show_button:
            self.btn_browse.show()
        else:
            self.btn_browse.hide()

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
        path = ""
        is_external = False
        if md.hasUrls():
            urls = md.urls()
            if urls:
                path = urls[0].toLocalFile()
                is_external = True
        if path:
            self.folder_dropped.emit(path, is_external)
            event.acceptProposedAction()
        else:
            event.ignore()


def find_main_app(widget):
    """Поднимается по дереву родителей до первого объекта с global_volume."""
    w = widget
    while w is not None:
        if hasattr(w, 'global_volume'):
            return w
        w = w.parent()
    return None

class SorterViewerArea(QWidget):
    """Stacked Widget Area controlling Single, Grid and List modes."""
    canvas_clicked = pyqtSignal()
    fullscreen_toggled = pyqtSignal()
    folder_dropped = pyqtSignal(str, bool)
    browse_requested = pyqtSignal()
    mode_changed = pyqtSignal(int)      # Emits index: 0=Single, 1=Grid, 2=List
    selection_changed = pyqtSignal()    # Emits when selected items in Grid/List change
    send_to_editor_requested = pyqtSignal(str, list)

    def get_main_app(self):
        return find_main_app(self)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.stack = QStackedWidget(self)
        layout.addWidget(self.stack)
        
        # 0. Single Viewer
        self.single_view = ZoomableGraphicsView(self)
        self.single_view.canvas_clicked.connect(self.canvas_clicked.emit)
        self.single_view.fullscreen_toggled.connect(self.fullscreen_toggled.emit)
        self.single_view.folder_dropped.connect(self.folder_dropped.emit)
        self.single_view.browse_requested.connect(self.browse_requested.emit)
        self.stack.addWidget(self.single_view)
        
        # Expose video_item and pixmap_item for play/fit compatibility
        self.video_item = self.single_view.video_item
        self.pixmap_item = self.single_view.pixmap_item
        
        # 1. Grid Viewer
        self.grid_view = SorterGridView(self)
        self.grid_view.folder_dropped.connect(self.folder_dropped.emit)
        self.grid_view.itemSelectionChanged.connect(self.selection_changed.emit)
        self.grid_view.send_to_editor_requested.connect(self.send_to_editor_requested.emit)
        self.stack.addWidget(self.grid_view)
        
        # 2. List Viewer
        self.list_view = SorterListView(self)
        self.list_view.folder_dropped.connect(self.folder_dropped.emit)
        self.list_view.itemSelectionChanged.connect(self.selection_changed.emit)
        self.list_view.send_to_editor_requested.connect(self.send_to_editor_requested.emit)
        self.stack.addWidget(self.list_view)
        
        # 3. Empty Placeholder View
        self.empty_placeholder_widget = SorterPlaceholderWidget(self)
        self.empty_placeholder_widget.folder_dropped.connect(self.folder_dropped.emit)
        self.empty_placeholder_widget.browse_requested.connect(self.browse_requested.emit)
        self.stack.addWidget(self.empty_placeholder_widget)
        
        self.current_view_mode = 0
        self.loading_files = []
        
        # Floating Overlay Containers
        self.overlay_container_right = QWidget(self)
        self.overlay_container_right.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.overlay_container_right.setStyleSheet("background: transparent;")
        
        self.overlay_container_left = QWidget(self)
        self.overlay_container_left.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.overlay_container_left.setStyleSheet("background: transparent;")
        
        btn_style = """
            QPushButton { 
                background-color: rgba(0,0,0,0.5); 
                color: white; 
                font-size: 20px; 
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 4px;
                outline: none;
                padding: 0px;
            }
            QPushButton:hover { 
                background-color: rgba(0,0,0,0.8); 
                border: 1px solid rgba(255, 255, 255, 0.8);
            }
        """
        self.overlay_btn_style = btn_style
        self.user_hover_preview_state = False
        self.disable_hover_preview = True # По умолчанию в режиме одиночного просмотра быстрый просмотр отключен
        
        # Загрузка иконок режимов просмотра
        icons_dir_global = AppContext.find_resource_dir("icons")
        self.icons_dir = icons_dir_global
        self.icon_grid = QIcon(os.path.join(icons_dir_global, "view_grid.svg"))
        self.icon_list = QIcon(os.path.join(icons_dir_global, "view_list.svg"))
        self.icon_single = QIcon(os.path.join(icons_dir_global, "view_single.svg"))

        self.btn_view_mode = QPushButton(self.overlay_container_right)
        self.btn_view_mode.setFixedSize(40, 40)
        self.btn_view_mode.setIconSize(QSize(22, 22))
        self.btn_view_mode.setIcon(self.icon_grid)
        self.btn_view_mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_mode.setStyleSheet(btn_style)
        self.btn_view_mode.clicked.connect(self.toggle_mode)
        self.btn_view_mode.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_view_mode.setToolTip("Режим сетки" if AppContext.LANG == "RU" else "Grid Mode")
        self.btn_view_mode.move(0, 0)
        
        self.btn_fullscreen = QPushButton(self.overlay_container_left)
        self.btn_fullscreen.setFixedSize(40, 40)
        self.btn_fullscreen.setIconSize(QSize(22, 22))
        self.btn_fullscreen.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fullscreen.setStyleSheet(btn_style)
        self.btn_fullscreen.clicked.connect(self.fullscreen_toggled.emit)
        self.btn_fullscreen.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_fullscreen.setToolTip("Во весь экран" if AppContext.LANG == "RU" else "Fullscreen")
        self.btn_fullscreen.move(0, 0)
        
        self.btn_toggle_preview = QPushButton("👁", self.overlay_container_right)
        self.btn_toggle_preview.setFixedSize(40, 40)
        self.btn_toggle_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_preview.setCheckable(True)
        self.btn_toggle_preview.setStyleSheet(btn_style)
        self.btn_toggle_preview.clicked.connect(self.on_toggle_preview_clicked)
        self.btn_toggle_preview.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_toggle_preview.setToolTip("Отключить быстрый просмотр по наведению" if AppContext.LANG == "RU" else "Disable hover preview")
        self.btn_toggle_preview.move(0, 50)
        
        self.btn_quick_target = QPushButton(self.overlay_container_right)
        self.btn_quick_target.setFixedSize(40, 40)
        self.btn_quick_target.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_quick_target.setStyleSheet(btn_style)
        self.btn_quick_target.clicked.connect(self.on_quick_target_clicked)
        self.btn_quick_target.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_quick_target.move(0, 100)
        self.btn_quick_target.hide()
        
        # --- Pagination Buttons ---
        self.btn_page_prev = QPushButton("◀", self.overlay_container_right)
        self.btn_page_prev.setFixedSize(40, 40)
        self.btn_page_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_page_prev.setStyleSheet(btn_style)
        self.btn_page_prev.clicked.connect(lambda: self.change_page(-1))
        self.btn_page_prev.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_page_prev.setToolTip("Предыдущая страница" if AppContext.LANG == "RU" else "Previous Page")
        self.btn_page_prev.move(0, 200)
        
        self.lbl_page_text = QLabel("1/1", self.overlay_container_right)
        self.lbl_page_text.setFixedSize(40, 40)
        self.lbl_page_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_page_text.setStyleSheet("""
            background-color: rgba(30, 30, 30, 0.7);
            color: white;
            font-size: 11px;
            font-weight: bold;
            border-radius: 4px;
        """)
        self.lbl_page_text.setToolTip("Текущая страница" if AppContext.LANG == "RU" else "Current Page")
        self.lbl_page_text.move(0, 250)
        
        self.btn_page_next = QPushButton("▶", self.overlay_container_right)
        self.btn_page_next.setFixedSize(40, 40)
        self.btn_page_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_page_next.setStyleSheet(btn_style)
        self.btn_page_next.clicked.connect(lambda: self.change_page(1))
        self.btn_page_next.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_page_next.setToolTip("Следующая страница" if AppContext.LANG == "RU" else "Next Page")
        self.btn_page_next.move(0, 300)
        
        self.btn_page_refresh = QPushButton("↻", self.overlay_container_right)
        self.btn_page_refresh.setFixedSize(40, 40)
        self.btn_page_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_page_refresh.setStyleSheet(btn_style)
        self.btn_page_refresh.clicked.connect(lambda: self.refresh_pagination())
        self.btn_page_refresh.setToolTip("Обновить списки и переформировать группы" if AppContext.LANG == "RU" else "Refresh lists and regroup")
        self.btn_page_refresh.move(0, 350)
        
        self.current_page_idx = 0
        self.total_pages = 1
        
        self.btn_quick_target_icon = QLabel(self.btn_quick_target)
        self.btn_quick_target_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.btn_quick_target_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_quick_target_icon.setStyleSheet("background: transparent; border: none; padding: 0px;")
        self.btn_quick_target_icon.setPixmap(QIcon(os.path.join(self.icons_dir, "star-color.svg")).pixmap(26, 26))
        self.btn_quick_target_icon.setGeometry(7, 7, 26, 26)
        
        # Connect Thumbnail Loader singleton
        ThumbnailLoader.inst().thumbnail_ready.connect(self._on_thumbnail_ready)
        
        self.current_inbox_dir = ""
        self.placeholders = {}
        self.grid_items_map = {}
        self.list_items_map = {}
        self.file_rotations = {}
        self.popup_size = QSize(640, 520)

        # Batch loading setup
        self.loading_timer = QTimer(self)
        self.loading_timer.timeout.connect(self._load_next_batch)
        self.loading_files = []
        self.loading_dir = ""
        self.loading_current_idx = 0
        self.loading_target_select_idx = 0
        self.batch_size = 30
        self.is_loading_interrupted = False
        
        # Loading Overlay Widget
        self.loading_overlay = QFrame(self)
        self.loading_overlay.setObjectName("LoadingOverlay")
        self.loading_overlay.setStyleSheet("""
            #LoadingOverlay {
                background-color: rgba(15, 15, 15, 0.7);
                border: none;
            }
        """)
        
        # Контейнер для статуса по центру
        self.loading_content = QFrame(self.loading_overlay)
        self.loading_content.setObjectName("LoadingContent")
        self.loading_content.setFixedSize(400, 115)
        self.loading_content.setStyleSheet("""
            #LoadingContent {
                background-color: #2b2b2b;
                border: 2px solid #3b82f6;
                border-radius: 8px;
            }
            QLabel {
                color: #ffffff;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton#BtnStopLoading {
                background-color: #ef4444;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 13px;
            }
            QPushButton#BtnStopLoading:hover {
                background-color: #dc2626;
            }
            QPushButton#BtnStopLoading:pressed {
                background-color: #b91c1c;
            }
        """)
        
        overlay_layout = QVBoxLayout(self.loading_overlay)
        overlay_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        content_layout = QVBoxLayout(self.loading_content)
        content_layout.setContentsMargins(15, 12, 15, 12)
        content_layout.setSpacing(10)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_loading_status = QLabel("Загрузка файлов...", self.loading_content)
        self.lbl_loading_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_loading_status.setFixedWidth(370)
        content_layout.addWidget(self.lbl_loading_status)

        self.btn_stop_loading = QPushButton(AppContext.tr("btn_stop"), self.loading_content)
        self.btn_stop_loading.setObjectName("BtnStopLoading")
        self.btn_stop_loading.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stop_loading.clicked.connect(self.stop_loading_batch)
        content_layout.addWidget(self.btn_stop_loading, 0, Qt.AlignmentFlag.AlignCenter)
        
        overlay_layout.addWidget(self.loading_content)
        self.loading_overlay.hide()
        self.update_fullscreen_tooltip(False)

    def change_page(self, delta: int):
        main_app = self.get_main_app()
        if main_app and hasattr(main_app, 'change_page'):
            main_app.change_page(delta)

    def refresh_pagination(self):
        main_app = self.get_main_app()
        if main_app and hasattr(main_app, 'refresh_pagination'):
            main_app.refresh_pagination()

    def update_pagination_ui(self, current: int, total: int):
        self.current_page_idx = current
        self.total_pages = total
        self.lbl_page_text.setText(f"{current + 1}/{total}")
        
        # Только для режима сетки (1) и списка (2)
        is_single_view = getattr(self, 'current_view_mode', 0) == 0
        show_pagination = not is_single_view
        
        self.btn_page_prev.setVisible(show_pagination)
        self.btn_page_prev.setEnabled(total > 1)
        self.lbl_page_text.setVisible(show_pagination)
        self.btn_page_next.setVisible(show_pagination)
        self.btn_page_next.setEnabled(total > 1)
        
        # Кнопка обновления видна всегда в режимах сетки/списка
        self.btn_page_refresh.setVisible(show_pagination)
        
        self.resizeEvent(None)

    def get_grid_columns_count(self):
        grid_w = self.grid_view.gridSize().width()
        if grid_w <= 0:
            grid_w = 120
        viewport_w = self.grid_view.viewport().width()
        if viewport_w <= 0:
            viewport_w = self.grid_view.width()
        if viewport_w <= 0:
            viewport_w = 800
        return max(1, viewport_w // grid_w)

    def get_current_selected_index(self):
        """Returns the index of the currently selected file in loading_files list."""
        main_app = self.get_main_app()
        if main_app and hasattr(main_app, 'current_index'):
            return main_app.current_index
            
        curr_mode = self.stack.currentIndex()
        view = self.grid_view if curr_mode == 1 else self.list_view
        selected = view.selectedItems()
        if selected:
            p = selected[0].data(Qt.ItemDataRole.UserRole)
            if p and hasattr(self, 'loading_files') and self.loading_files and hasattr(self, 'current_inbox_dir') and self.current_inbox_dir:
                rel = safe_relpath(p, self.current_inbox_dir)
                norm_rel = os.path.normpath(rel)
                for idx, f in enumerate(self.loading_files):
                    if os.path.normpath(f) == norm_rel:
                        return idx
        return self.loading_target_select_idx

    def get_grid_item(self, idx):
        if not self.loading_files or idx >= len(self.loading_files):
            return None
        rel_path = self.loading_files[idx]
        full_path = os.path.join(self.current_inbox_dir, rel_path)
        return self.grid_items_map.get(os.path.normpath(full_path))

    def get_list_item(self, idx):
        if not self.loading_files or idx >= len(self.loading_files):
            return None
        rel_path = self.loading_files[idx]
        full_path = os.path.join(self.current_inbox_dir, rel_path)
        return self.list_items_map.get(os.path.normpath(full_path))

    def _center_loading_overlay(self):
        self.loading_overlay.setGeometry(self.rect())
        self.loading_overlay.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        if not self.loading_overlay.isHidden():
            self._center_loading_overlay()

    def resizeEvent(self, event):
        if event:
            super().resizeEvent(event)
        
        # Position floating controls
        m = 10
        m_right = 20  # Отступ справа скорректирован до 20px, чтобы кнопки были вплотную к скроллбару, но не перекрывали его
        w = 40
        spacing = 10
        
        # Right container (view mode, hover preview, quick target toggles, and 4 pagination buttons)
        # We need to calculate height based on visible buttons. 
        # For now, there are 8 buttons (indices 0 to 350 + 40 height) -> 400px
        container_right_w = w
        container_right_h = 400
        self.overlay_container_right.setGeometry(self.width() - container_right_w - m_right, m, container_right_w, container_right_h)
        self.overlay_container_right.show()
        self.overlay_container_right.raise_()
        
        # Left container (fullscreen toggle)
        # Width: 40px, Height: 40px
        container_left_w = w
        container_left_h = w
        self.overlay_container_left.setGeometry(m, m, container_left_w, container_left_h)
        
        # Only show left container if we are in Single View mode (idx 0)
        if self.current_view_mode == 0:
            self.overlay_container_left.show()
            self.overlay_container_left.raise_()
        else:
            self.overlay_container_left.hide()
        
        if not self.loading_overlay.isHidden():
            self._center_loading_overlay()

        # Если включена группировка и изменилось количество колонок в Grid View, перестраиваем список тихо
        main_app = self.get_main_app()
        group_enabled = main_app.config.get("group_by_sort", False) if main_app and hasattr(main_app, 'config') else False
        if group_enabled and hasattr(self, 'current_inbox_dir') and self.current_inbox_dir and self.loading_files:
            cols = self.get_grid_columns_count()
            if not hasattr(self, '_last_cols_count') or self._last_cols_count != cols:
                self._last_cols_count = cols
                self.loading_target_select_idx = self.get_current_selected_index()
                # Запускаем тихое обновление, чтобы пересчитать пустые заполнители
                self.sync_files_queue(self.current_inbox_dir, self.loading_files, self.loading_target_select_idx, silent=True)



    def toggle_mode(self):
        curr = self.current_view_mode
        if curr == 1:       # Grid (плитка) -> List (список)
            next_mode = 2
        elif curr == 2:     # List (список) -> Single (одиночный)
            next_mode = 0
        else:               # Single (одиночный) -> Grid (плитка)
            next_mode = 1
        self.set_mode(next_mode)

    def apply_hover_preview_state(self):
        """Применяет визуальные стили кнопки быстрого просмотра в зависимости от disable_hover_preview."""
        state = self.disable_hover_preview
        if state:
            self.btn_toggle_preview.setChecked(True)
            self.btn_toggle_preview.setStyleSheet("""
                QPushButton { 
                    background-color: rgba(239, 68, 68, 0.6); 
                    color: white; 
                    font-size: 20px; 
                    border: 1px solid #ef4444;
                    border-radius: 4px;
                    outline: none;
                    padding: 0px;
                }
                QPushButton:hover { 
                    background-color: rgba(220, 38, 38, 0.8); 
                    border: 1px solid white;
                }
            """)
            self.btn_toggle_preview.setToolTip(
                "Включить быстрый просмотр по наведению (F1)"
                if AppContext.LANG == "RU" else
                "Enable hover preview (F1)"
            )
            # Принудительно закрываем попапы у списков
            for view in [self.grid_view, self.list_view]:
                if hasattr(view, 'large_preview_popup') and view.large_preview_popup:
                    popup = view.large_preview_popup
                    view.large_preview_popup = None
                    try:
                        popup.cleanup()
                        popup.close()
                    except Exception:
                        pass
                view._stop_hover_playback(force=True)
        else:
            self.btn_toggle_preview.setChecked(False)
            self.btn_toggle_preview.setStyleSheet(self.overlay_btn_style)
            self.btn_toggle_preview.setToolTip(
                "Отключить быстрый просмотр по наведению (F1)"
                if AppContext.LANG == "RU" else
                "Disable hover preview (F1)"
            )

    def toggle_hover_preview(self) -> None:
        """
        Публичный метод переключения быстрого просмотра по наведению.
        Вызывается как кнопкой 👁, так и горячей клавишей F1.
        """
        # Переключаем предпочтение пользователя
        self.user_hover_preview_state = not self.user_hover_preview_state
        
        # В режиме одиночного просмотра (currentIndex == 0 или 3) быстрый просмотр принудительно выключен
        if self.current_view_mode != 0:
            self.disable_hover_preview = self.user_hover_preview_state
        else:
            self.disable_hover_preview = True
            
        self.apply_hover_preview_state()

    def on_toggle_preview_clicked(self, checked: bool) -> None:
        """Обработчик клика кнопки 👁 — делегирует в toggle_hover_preview()."""
        # Синхронизируем состояние флага, toggle_hover_preview сам сделает flip предпочтения
        self.toggle_hover_preview()

    def set_mode(self, mode_idx):
        self.grid_view._stop_hover_playback(force=True)
        self.list_view._stop_hover_playback(force=True)
        
        # Сохраняем/восстанавливаем состояние быстрого просмотра при смене режимов
        if mode_idx == 0:
            self.disable_hover_preview = True
        else:
            self.disable_hover_preview = getattr(self, 'user_hover_preview_state', False)
        self.apply_hover_preview_state()
        
        self.current_view_mode = mode_idx
        
        # If files queue is empty, keep showing empty placeholder widget
        if not getattr(self, 'loading_files', None) and not self.current_inbox_dir:
            self.stack.setCurrentIndex(3)
        else:
            self.stack.setCurrentIndex(mode_idx)
            
        self.mode_changed.emit(mode_idx)
        
        # Update mode button icon and tooltips
        if mode_idx == 0:
            self.btn_view_mode.setText("")
            self.btn_view_mode.setIcon(self.icon_grid)
            self.btn_view_mode.setToolTip("Режим сетки" if AppContext.LANG == "RU" else "Grid Mode")
            self.btn_toggle_preview.hide()
            self.btn_page_prev.hide()
            self.lbl_page_text.hide()
            self.btn_page_next.hide()
            self.btn_page_refresh.hide()
        elif mode_idx == 1:
            self.btn_view_mode.setText("")
            self.btn_view_mode.setIcon(self.icon_list)
            self.btn_view_mode.setToolTip("Режим списка" if AppContext.LANG == "RU" else "List Mode")
            self.btn_toggle_preview.show()
            self.btn_page_prev.show()
            self.lbl_page_text.show()
            self.btn_page_next.show()
            self.btn_page_refresh.show()
        else:
            self.btn_view_mode.setText("")
            self.btn_view_mode.setIcon(self.icon_single)
            self.btn_view_mode.setToolTip("Одиночный просмотр" if AppContext.LANG == "RU" else "Single View")
            self.btn_toggle_preview.show()
            self.btn_page_prev.show()
            self.lbl_page_text.show()
            self.btn_page_next.show()
            self.btn_page_refresh.show()
            
        self.resizeEvent(None)
        self.update_quick_target_visibility()
        self.update_quick_target_tooltip()
        # Гарантируем что overlays всегда поверх текущего виджета стека
        self.overlay_container_right.raise_()
        if mode_idx == 0:
            self.overlay_container_left.raise_()
        
        # Synchronize active item selection when returning to modes
        if mode_idx in [1, 2]:
            self.grid_view.setFocus()
            self.list_view.setFocus()
            
    # Proxy methods for Single mode compatibility
    def set_image(self, pixmap):
        if self.stack.currentIndex() == 3:
            self.stack.setCurrentIndex(0)
        self.single_view.set_image(pixmap)
        main_app = self.get_main_app()
        if main_app and getattr(main_app, 'current_file_path', None):
            norm_path = os.path.normpath(main_app.current_file_path)
            angle = self.file_rotations.get(norm_path, 0)
            if angle != 0:
                if hasattr(self.single_view, 'set_absolute_rotation'):
                    self.single_view.set_absolute_rotation(angle)
                else:
                    self.single_view.rotate(angle)

    def set_animated(self, filepath):
        if self.stack.currentIndex() == 3:
            self.stack.setCurrentIndex(0)
        self.single_view.set_animated(filepath)
        norm_path = os.path.normpath(filepath)
        angle = self.file_rotations.get(norm_path, 0)
        if angle != 0:
            if hasattr(self.single_view, 'set_absolute_rotation'):
                self.single_view.set_absolute_rotation(angle)
            else:
                self.single_view.rotate(angle)

    def update_item_preview(self, filepath):
        norm_path = os.path.normpath(filepath)
        item_grid = self.grid_items_map.get(norm_path)
        if item_grid:
            widget = self.grid_view.itemWidget(item_grid)
            if widget and hasattr(widget, 'update_rotation'):
                widget.update_rotation()
        item_list = self.list_items_map.get(norm_path)
        if item_list:
            widget = self.list_view.itemWidget(item_list)
            if widget and hasattr(widget, 'update_rotation'):
                widget.update_rotation()

    def set_video_mode(self): 
        if self.stack.currentIndex() == 3:
            self.stack.setCurrentIndex(0)
        self.single_view.set_video_mode()
        
    def set_audio_mode(self, text): 
        if self.stack.currentIndex() == 3:
            self.stack.setCurrentIndex(0)
        self.single_view.set_audio_mode(text)
    
    def show_empty_state(self, message):
        main_app = self.get_main_app()
        show_btn = True
        if main_app and getattr(main_app, 'UNSORT_DIR', None) and getattr(main_app, 'files_queue', None):
            show_btn = False
            
        self.empty_placeholder_widget.set_message(message, show_btn)
        self.stack.setCurrentIndex(3)
        
    def change_rotation(self, angle): self.single_view.change_rotation(angle)
    def set_background_color(self, color): self.single_view.set_background_color(color)
    def set_fullscreen_mode(self, enabled, controls_widget=None):
        self.single_view.set_fullscreen_mode(enabled, controls_widget)
        if enabled:
            self.overlay_container_right.hide()
            self.overlay_container_left.hide()
        else:
            self.overlay_container_right.show()
            if self.current_view_mode == 0:
                self.overlay_container_left.show()
        self.update_fullscreen_tooltip(enabled)

    def update_fullscreen_tooltip(self, is_fullscreen: bool):
        main_app = self.get_main_app()
        if is_fullscreen:
            self.btn_fullscreen.setIcon(QIcon(os.path.join(self.icons_dir, "square-arrow-out-down-left.svg")))
            key_str = "Escape"
            if main_app and hasattr(main_app, '_hotkey_registry'):
                key = main_app._hotkey_registry.get_effective_key("exit_fullscreen")
                if key:
                    key_str = key.replace("Return", "Enter")
            
            tooltip_text = (
                f"Выйти из полноэкранного режима ({key_str})"
                if AppContext.LANG == "RU" else
                f"Exit fullscreen ({key_str})"
            )
        else:
            self.btn_fullscreen.setIcon(QIcon(os.path.join(self.icons_dir, "scan.svg")))
            key_str = "Alt+Enter"
            if main_app and hasattr(main_app, '_hotkey_registry'):
                key = main_app._hotkey_registry.get_effective_key("toggle_fullscreen_solo")
                if key:
                    key_str = key.replace("Return", "Enter")
            
            tooltip_text = (
                f"Во весь экран ({key_str})"
                if AppContext.LANG == "RU" else
                f"Fullscreen ({key_str})"
            )
        self.btn_fullscreen.setToolTip(tooltip_text)

    def update_quick_target_visibility(self):
        """Управляет видимостью кнопки Быстрой цели на холсте."""
        main_app = self.get_main_app()
        has_target = main_app and getattr(main_app, 'quick_target_path', None) is not None
        in_valid_mode = self.current_view_mode in [0, 1, 2, 3]
        if has_target and in_valid_mode:
            self.btn_quick_target.show()
        else:
            self.btn_quick_target.hide()

    def update_quick_target_tooltip(self):
        """Обновляет текст подсказки кнопки Быстрой цели с учетом пути и хоткея."""
        main_app = self.get_main_app()
        target_path = getattr(main_app, 'quick_target_path', None)
        if target_path:
            folder_name = os.path.basename(target_path)
            key_str = self.get_fast_move_key_string()
            
            tooltip_text = (
                f"Быстрое перемещение в «{folder_name}» ({key_str})"
                if AppContext.LANG == "RU" else
                f"Fast move to '{folder_name}' ({key_str})"
            )
            self.btn_quick_target.setToolTip(tooltip_text)

    def get_fast_move_key_string(self):
        """Считывает назначенную горячую клавишу для быстрого перемещения."""
        main_app = self.get_main_app()
        if main_app and hasattr(main_app, '_hotkey_registry'):
            key = main_app._hotkey_registry.get_effective_key("fast_move_to_target")
            if key:
                return key
        return "Space"

    def on_quick_target_clicked(self):
        """Обработчик нажатия на кнопку Быстрой цели на холсте."""
        main_app = self.get_main_app()
        if main_app and hasattr(main_app, 'fast_move_to_target'):
            main_app.fast_move_to_target()
            
    def reset_view(self):
        self.single_view.reset_view()

    def clear_scene_content(self):
        self.single_view.clear_scene_content()
        self.grid_view._stop_hover_playback(force=True)
        self.list_view._stop_hover_playback(force=True)

    # SYNC FILES QUEUE WITH GRID/LIST
    def sync_files_queue(self, unsort_dir, files, current_index, silent=False):
        """Build grid and list widget items from incoming files queue."""
        # Stop loading timer if already running
        self.loading_timer.stop()
        
        # Stop hover playback FIRST to prevent crashes
        self.grid_view._stop_hover_playback(force=True)
        self.list_view._stop_hover_playback(force=True)
        
        self.current_inbox_dir = unsort_dir
        
        # Explicitly delete old item widgets to avoid memory leaks in Qt
        for i in range(self.grid_view.count()):
            item = self.grid_view.item(i)
            if item:
                w = self.grid_view.itemWidget(item)
                if w:
                    self.grid_view.removeItemWidget(item)
                    w.deleteLater()
        for i in range(self.list_view.count()):
            item = self.list_view.item(i)
            if item:
                w = self.list_view.itemWidget(item)
                if w:
                    self.list_view.removeItemWidget(item)
                    w.deleteLater()

        self.grid_view.clear()
        self.list_view.clear()
        
        # Clear thumbnail and icon caches when loading a new folder to free RAM
        if getattr(self, 'current_inbox_dir', None) != unsort_dir:
            ThumbnailLoader.inst().clear_cache()
            FileIconManager.inst().clear_cache()
        
        self.grid_items_map = {}
        self.list_items_map = {}
        self.loading_render_items = []
        self.is_loading_interrupted = False
        
        if not unsort_dir and not files:
            self.loading_overlay.hide()
            self.loading_files = []
            self.show_empty_state("Входящие не выбраны\n\nПеретащите папку для анализа на этот холст\nили выберите её через Проводник" if AppContext.LANG == "RU" else "Inbox folder not selected\n\nDrag a folder here for analysis\nor choose it using the button below")
            return
            
        if not files and unsort_dir:
            # Пустая папка
            pass
            
        self.loading_files = files
        if self.stack.currentIndex() == 3:
            self.stack.setCurrentIndex(self.current_view_mode)
            
        self.loading_dir = unsort_dir
        self.loading_current_idx = 0
        self.loading_target_select_idx = current_index
        
        # Сбор элементов для рендеринга с учетом группировки
        main_app = self.get_main_app()
        group_enabled = main_app.config.get("group_by_sort", False) if main_app and hasattr(main_app, 'config') else False
        
        if group_enabled:
            sort_type = main_app.config.get("sort_type", "name_asc") if main_app and hasattr(main_app, 'config') else "name_asc"
            
            def get_group_title(rel_path):
                full_path = os.path.join(unsort_dir, rel_path)
                size, mtime, ctime = 0, 0.0, 0.0
                try:
                    stat = os.stat(full_path)
                    size = stat.st_size
                    mtime = stat.st_mtime
                    ctime = stat.st_ctime
                except Exception:
                    pass
                    
                is_ru = (AppContext.LANG == "RU")
                ext = os.path.splitext(rel_path)[1].lower()
                
                if sort_type in ["name_asc", "name_desc"]:
                    name = os.path.basename(rel_path)
                    if name:
                        first_char = name[0].upper()
                        if first_char.isdigit():
                            return "0-9"
                        elif not first_char.isalnum():
                            return "#"
                        return first_char
                    return "#"
                    
                elif sort_type == "type_asc":
                    video_exts = VIDEO_EXTS
                    audio_exts = AUDIO_EXTS
                    image_exts = IMAGE_EXTS
                    
                    clean_ext = ext.lstrip('.')
                    if not clean_ext:
                        clean_ext = "no ext"
                        
                    if ext in video_exts:
                        cat_name = "Видео" if is_ru else "Video"
                    elif ext in image_exts:
                        cat_name = "Изображения" if is_ru else "Images"
                    elif ext in audio_exts:
                        cat_name = "Аудио" if is_ru else "Audio"
                    else:
                        cat_name = "Другие файлы" if is_ru else "Other files"
                        
                    return f"{cat_name} ({clean_ext})"
                        
                elif sort_type in ["size_desc", "size_asc"]:
                    if size >= 1024*1024*1024:
                        return "Гиганты (> 1 GB)" if is_ru else "Giants (> 1 GB)"
                    elif size >= 1024*1024*100:
                        return "Крупные (100 MB - 1 GB)" if is_ru else "Large (100 MB - 1 GB)"
                    elif size >= 1024*1024*10:
                        return "Средние (10 MB - 100 MB)" if is_ru else "Medium (10 MB - 100 MB)"
                    else:
                        return "Мелкие (< 10 MB)" if is_ru else "Small (< 10 MB)"
                        
                elif sort_type in ["mtime_desc", "mtime_asc", "ctime_desc", "ctime_asc"]:
                    t = mtime if "mtime" in sort_type else ctime
                    from datetime import datetime
                    try:
                        return datetime.fromtimestamp(t).strftime("%d.%m.%Y")
                    except Exception:
                        return "Неизвестная дата" if is_ru else "Unknown date"
                return "Группа" if is_ru else "Group"

            cols = self.get_grid_columns_count()
            last_group = None
            rendered_count = 0
            
            for idx, rel_path in enumerate(files):
                g_title = get_group_title(rel_path)
                if g_title != last_group:
                    # Заполняем пустые плитки в Grid для переноса строки (нового абзаца)
                    if rendered_count > 0:
                        pos = rendered_count % cols
                        if pos != 0:
                            num_placeholders = cols - pos
                            for _ in range(num_placeholders):
                                self.loading_render_items.append(("grid_placeholder",))
                                rendered_count += 1
                                
                    self.loading_render_items.append(("separator", g_title))
                    # Обратите внимание: separator в grid_view не добавляется,
                    # поэтому rendered_count НЕ увеличиваем, чтобы файлы новой группы
                    # начались точно с первой колонки новой строки.
                    last_group = g_title
                    
                self.loading_render_items.append(("file", rel_path, idx))
                rendered_count += 1
        else:
            for idx, rel_path in enumerate(files):
                self.loading_render_items.append(("file", rel_path, idx))
        
        # Show loading overlay (only if not silent)
        if not silent:
            is_ru = (AppContext.LANG == "RU")
            total = len(files)
            w_val = len(str(total))
            self.lbl_loading_status.setText(f"Загрузка файлов... {0:>{w_val}} / {total}" if is_ru else f"Loading files... {0:>{w_val}} / {total}")
            self._center_loading_overlay()
            self.loading_overlay.show()
            self.loading_overlay.raise_()
            QApplication.processEvents()
        else:
            self.loading_overlay.hide()
        
        # Start batch loading
        self.loading_timer.start(0)

    def stop_loading_batch(self):
        logging.info("Загрузка файлов в интерфейс остановлена пользователем.")
        self.is_loading_interrupted = True
        self.loading_timer.stop()
        self.loading_render_items = []
        self.loading_overlay.hide()
        self.grid_view.doItemsLayout()
        self.list_view.doItemsLayout()

    def _load_next_batch(self):
        if not self.loading_render_items:
            self.loading_timer.stop()
            self.loading_overlay.hide()
            return
            
        total = len(self.loading_render_items)
        start = self.loading_current_idx
        end = min(start + self.batch_size, total)
        
        is_ru = (AppContext.LANG == "RU")
        
        # Disable updates during batch insertion to prevent flickering
        self.grid_view.setUpdatesEnabled(False)
        self.list_view.setUpdatesEnabled(False)
        
        try:
            for idx in range(start, end):
                item_data = self.loading_render_items[idx]
                if item_data[0] == "grid_placeholder":
                    # Пустая невыделяемая плитка для переноса строк в Grid
                    item_grid = QListWidgetItem()
                    item_grid.setFlags(item_grid.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                    widget_grid = QWidget()
                    item_grid.setSizeHint(QSize(self.grid_view.gridSize().width(), self.grid_view.gridSize().height()))
                    self.grid_view.addItem(item_grid)
                    self.grid_view.setItemWidget(item_grid, widget_grid)
                elif item_data[0] == "separator":
                    title = item_data[1]
                    
                    # List Separator
                    item_list = QListWidgetItem()
                    item_list.setFlags(item_list.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                    widget_list = SorterListGroupSeparatorWidget(title)
                    item_list.setSizeHint(QSize(self.list_view.width() - 30, 30))
                    self.list_view.addItem(item_list)
                    self.list_view.setItemWidget(item_list, widget_list)
                elif item_data[0] == "file":
                    rel_path = item_data[1]
                    orig_idx = item_data[2]
                    full_path = os.path.join(self.loading_dir, rel_path)
                    
                    # --- 1. Grid Item ---
                    item_grid = QListWidgetItem()
                    item_grid.setData(Qt.ItemDataRole.UserRole, full_path)
                    
                    widget_grid = SorterGridItemWidget(full_path, self.grid_view.tile_size)
                    ph = self._get_placeholder_pixmap(full_path)
                    widget_grid.set_placeholder(ph)
                    
                    item_grid.setSizeHint(widget_grid.sizeHint())
                    self.grid_view.addItem(item_grid)
                    self.grid_view.setItemWidget(item_grid, widget_grid)
                    
                    self.grid_items_map[os.path.normpath(full_path)] = item_grid
                    
                    # --- 2. List Item ---
                    item_list = QListWidgetItem()
                    item_list.setData(Qt.ItemDataRole.UserRole, full_path)
                    
                    widget_list = SorterListItemWidget(full_path, self.list_view.icon_size)
                    widget_list.set_placeholder(ph)
                    
                    item_list.setSizeHint(widget_list.sizeHint())
                    self.list_view.addItem(item_list)
                    self.list_view.setItemWidget(item_list, widget_list)
                    
                    self.list_items_map[os.path.normpath(full_path)] = item_list
                    
                    # Request async thumbnail generation
                    ext = os.path.splitext(rel_path)[1].lower()
                    if ext in VIDEO_EXTS:
                        ThumbnailLoader.inst().get_thumbnail(full_path, QSize(256, 256))
        finally:
            self.grid_view.setUpdatesEnabled(True)
            self.list_view.setUpdatesEnabled(True)
            
        self.loading_current_idx = end
        
        # Update progress overlay (show loaded files count based on files list)
        loaded_files_count = sum(1 for item in self.loading_render_items[:end] if item[0] == "file")
        total_files_count = len(self.loading_files)
        w_val = len(str(total_files_count))
        self.lbl_loading_status.setText(
            f"Загрузка файлов... {loaded_files_count:>{w_val}} / {total_files_count}" if is_ru else f"Loading files... {loaded_files_count:>{w_val}} / {total_files_count}"
        )
        self.loading_overlay.raise_()
        
        if end >= total:
            self.loading_timer.stop()
            self.loading_overlay.hide()
            self.is_loading_interrupted = False
            
            # Set selection on current index
            if self.loading_target_select_idx < len(self.loading_files):
                grid_item = self.get_grid_item(self.loading_target_select_idx)
                list_item = self.get_list_item(self.loading_target_select_idx)
                if grid_item: grid_item.setSelected(True)
                if list_item: list_item.setSelected(True)
                
            # Ensure all widgets have correct set_selected state initially
            for i in range(self.grid_view.count()):
                item = self.grid_view.item(i)
                if not item: continue
                p = item.data(Qt.ItemDataRole.UserRole)
                if not p: continue
                widget = self.grid_view.itemWidget(item)
                if widget and hasattr(widget, 'set_selected'):
                    widget.set_selected(item.isSelected())
                    
            self.selection_changed.emit()
            
            if self.stack.currentIndex() == 0:
                main_window = self.window()
                if main_window and hasattr(main_window, 'show_current_file'):
                    main_window.show_current_file()
            
            # Schedule hover check after load finishes
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(150, self.grid_view.check_hover_under_mouse)
            QTimer.singleShot(150, self.list_view.check_hover_under_mouse)

    def get_selected_files(self):
        """Returns list of absolute filepaths of selected items."""
        curr_mode = self.current_view_mode
        selected_paths = []
        if curr_mode == 0:
            pass
        elif curr_mode == 1:
            for item in self.grid_view.selectedItems():
                p = item.data(Qt.ItemDataRole.UserRole)
                if p: selected_paths.append(p)
        elif curr_mode == 2:
            for item in self.list_view.selectedItems():
                p = item.data(Qt.ItemDataRole.UserRole)
                if p: selected_paths.append(p)
        return selected_paths

    def _get_placeholder_pixmap(self, filepath):
        return FileIconManager.inst().get_icon_pixmap(filepath, QSize(128, 128))

    def _on_thumbnail_ready(self, filepath, image):
        # Update corresponding item icon in Grid and List views using O(1) map lookups
        norm_path = os.path.normpath(filepath)
        
        # Sync Grid
        item_grid = getattr(self, 'grid_items_map', {}).get(norm_path)
        if item_grid:
            widget = self.grid_view.itemWidget(item_grid)
            if widget and hasattr(widget, 'set_preview_image'):
                widget.set_preview_image(image)
                
        # Sync List
        item_list = getattr(self, 'list_items_map', {}).get(norm_path)
        if item_list:
            widget = self.list_view.itemWidget(item_list)
            if widget and hasattr(widget, 'set_preview_image'):
                widget.set_preview_image(image)

    def refresh_video_thumbnails(self) -> None:
        """Перегенерирует превью для всех видеофайлов в текущем каталоге."""
        logging.info("Начато обновление видео-превью после скачивания FFmpeg.")
        video_extensions = VIDEO_EXTS
        
        # Собираем все видеофайлы из текущего кэша отображения
        paths_to_refresh = []
        for path in self.grid_items_map.keys():
            ext = os.path.splitext(path)[1].lower()
            if ext in video_extensions:
                paths_to_refresh.append(path)
                
        if not paths_to_refresh:
            logging.debug("Видеофайлы для обновления превью не найдены.")
            return
            
        logging.info(f"Найдено {len(paths_to_refresh)} видеофайлов для обновления превью.")
        loader = ThumbnailLoader.inst()
        for path in paths_to_refresh:
            # Сбрасываем кэш и текущие активные запросы, чтобы разрешить генерацию заново
            loader.cache.pop(path, None)
            loader.active_requests.discard(path)
            # Запрашиваем генерацию
            loader.get_thumbnail(path, QSize(256, 256))

    def remove_files_from_view(self, paths):
        """Мгновенно удаляет указанные файлы из сетки и списка без перерисовки всей очереди."""
        self.grid_view._stop_hover_playback(force=True)
        self.list_view._stop_hover_playback(force=True)
        
        self.grid_view.setUpdatesEnabled(False)
        self.list_view.setUpdatesEnabled(False)
        try:
            items_to_remove_grid = set()
            items_to_remove_list = set()
            
            # Извлекаем элементы из мапов за O(1) и собираем множества для удаления
            for path in paths:
                norm_path = os.path.normpath(strip_long_path_prefix(path))
                
                item_grid = self.grid_items_map.pop(norm_path, None)
                if item_grid:
                    items_to_remove_grid.add(id(item_grid))
                    
                item_list = self.list_items_map.pop(norm_path, None)
                if item_list:
                    items_to_remove_list.add(id(item_list))
                    
            # Проходим по списку один раз с конца, удаляя нужные элементы за O(N) вместо O(N*K)
            if items_to_remove_grid:
                for i in range(self.grid_view.count() - 1, -1, -1):
                    item = self.grid_view.item(i)
                    if id(item) in items_to_remove_grid:
                        widget = self.grid_view.itemWidget(item)
                        self.grid_view.removeItemWidget(item)
                        self.grid_view.takeItem(i)
                        if widget:
                            widget.deleteLater()
                            
            if items_to_remove_list:
                for i in range(self.list_view.count() - 1, -1, -1):
                    item = self.list_view.item(i)
                    if id(item) in items_to_remove_list:
                        widget = self.list_view.itemWidget(item)
                        self.list_view.removeItemWidget(item)
                        self.list_view.takeItem(i)
                        if widget:
                            widget.deleteLater()
                            
            # Ускоряем удаление из списка загруженных файлов в памяти
            if hasattr(self, 'loading_files') and self.loading_files and hasattr(self, 'current_inbox_dir') and self.current_inbox_dir:
                norm_paths_set = set(os.path.normpath(strip_long_path_prefix(p)) for p in paths)
                base_dir = strip_long_path_prefix(self.current_inbox_dir)
                
                new_loading_files = []
                for f in self.loading_files:
                    full = os.path.normpath(os.path.join(base_dir, f))
                    if full not in norm_paths_set:
                        new_loading_files.append(f)
                self.loading_files = new_loading_files
        finally:
            self.grid_view.setUpdatesEnabled(True)
            self.list_view.setUpdatesEnabled(True)
            
        self.grid_view.doItemsLayout()
        self.list_view.doItemsLayout()
        
        # Schedule hover check after files are removed
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(150, self.grid_view.check_hover_under_mouse)
        QTimer.singleShot(150, self.list_view.check_hover_under_mouse)

    def insert_files_into_view(self, files_to_insert):
        """
        Точечно вставляет новые файлы в сетку и список.
        files_to_insert: список кортежей (full_path, index_in_queue)
        """
        self.grid_view._stop_hover_playback(force=True)
        self.list_view._stop_hover_playback(force=True)
        
        self.grid_view.setUpdatesEnabled(False)
        self.list_view.setUpdatesEnabled(False)
        try:
            for full_path, idx in files_to_insert:
                norm_path = os.path.normpath(full_path)
                ph = self._get_placeholder_pixmap(full_path)
                
                # --- 1. Вставка в Grid View ---
                item_grid = QListWidgetItem()
                item_grid.setData(Qt.ItemDataRole.UserRole, full_path)
                widget_grid = SorterGridItemWidget(full_path, self.grid_view.tile_size)
                widget_grid.set_placeholder(ph)
                item_grid.setSizeHint(widget_grid.sizeHint())
                
                self.grid_view.insertItem(idx, item_grid)
                self.grid_view.setItemWidget(item_grid, widget_grid)
                self.grid_items_map[norm_path] = item_grid
                
                # --- 2. Вставка в List View ---
                item_list = QListWidgetItem()
                item_list.setData(Qt.ItemDataRole.UserRole, full_path)
                widget_list = SorterListItemWidget(full_path, self.list_view.icon_size)
                widget_list.set_placeholder(ph)
                item_list.setSizeHint(widget_list.sizeHint())
                
                self.list_view.insertItem(idx, item_list)
                self.list_view.setItemWidget(item_list, widget_list)
                self.list_items_map[norm_path] = item_list
                
                # Запуск асинхронной загрузки превью
                ext = os.path.splitext(full_path)[1].lower()
                if ext in VIDEO_EXTS:
                    ThumbnailLoader.inst().get_thumbnail(full_path, QSize(256, 256))
                    
            # Также обновим self.loading_files в памяти
            for full_path, idx in files_to_insert:
                rel = safe_relpath(full_path, self.current_inbox_dir)
                if rel not in self.loading_files:
                    self.loading_files.insert(idx, rel)
        finally:
            self.grid_view.setUpdatesEnabled(True)
            self.list_view.setUpdatesEnabled(True)
            
        self.grid_view.doItemsLayout()
        self.list_view.doItemsLayout()
        
        # Schedule hover check after files are inserted
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(150, self.grid_view.check_hover_under_mouse)
        QTimer.singleShot(150, self.list_view.check_hover_under_mouse)

    def update_file_path_in_view(self, old_path: str, new_path: str) -> None:
        """
        Точечно обновляет путь к файлу в сетке, списке и кэшах без перерисовки всей очереди.
        
        На будущее для множественного тегирования: если потребуется обновлять множество путей,
        этот метод можно легко переписать или вызвать в цикле по списку пар (old_path, new_path).
        """
        norm_old = os.path.normpath(old_path)
        if norm_old.startswith("\\\\?\\"):
            norm_old = norm_old[4:]
        norm_new = os.path.normpath(new_path)
        if norm_new.startswith("\\\\?\\"):
            norm_new = norm_new[4:]
        
        self.grid_view.setUpdatesEnabled(False)
        self.list_view.setUpdatesEnabled(False)
        try:
            # 1. Обновляем Grid View
            item_grid = self.grid_items_map.pop(norm_old, None)
            if item_grid:
                item_grid.setData(Qt.ItemDataRole.UserRole, new_path)
                self.grid_items_map[norm_new] = item_grid
                widget_grid = self.grid_view.itemWidget(item_grid)
                if isinstance(widget_grid, SorterGridItemWidget):
                    widget_grid.filepath = new_path
                    # Обновляем бэдж расширения
                    ext = os.path.splitext(new_path)[1].upper()
                    if ext.startswith('.'): ext = ext[1:]
                    widget_grid.lbl_badge.setText(ext if ext else "FILE")
                    # Обновляем размер
                    file_size = 0
                    try: file_size = os.path.getsize(ensure_long_path(new_path))
                    except Exception: pass
                    widget_grid.lbl_size_badge.setText(format_short_size(file_size))
                    # Обновляем имя и размеры
                    widget_grid.update_sizes()
                    
            # 2. Обновляем List View
            item_list = self.list_items_map.pop(norm_old, None)
            if item_list:
                item_list.setData(Qt.ItemDataRole.UserRole, new_path)
                self.list_items_map[norm_new] = item_list
                widget_list = self.list_view.itemWidget(item_list)
                if isinstance(widget_list, SorterListItemWidget):
                    widget_list.filepath = new_path
                    # Обновляем имя
                    widget_list.lbl_name.setText(os.path.basename(new_path))
                    # Обновляем бэдж расширения
                    ext = os.path.splitext(new_path)[1].upper()
                    if ext.startswith('.'): ext = ext[1:]
                    widget_list.lbl_badge.setText(ext if ext else "FILE")
                    # Обновляем размер
                    file_size = 0
                    try: file_size = os.path.getsize(ensure_long_path(new_path))
                    except Exception: pass
                    from utils_common import format_size
                    widget_list.lbl_size.setText(format_size(file_size))
                    widget_list.update_sizes()
                    
            # 3. Обновляем список загруженных файлов в памяти
            if hasattr(self, 'loading_files') and self.loading_files and hasattr(self, 'current_inbox_dir') and self.current_inbox_dir:
                # Находим относительные пути
                rel_old = safe_relpath(old_path, self.current_inbox_dir)
                rel_new = safe_relpath(new_path, self.current_inbox_dir)
                for idx, f in enumerate(self.loading_files):
                    if os.path.normpath(f) == os.path.normpath(rel_old):
                        self.loading_files[idx] = rel_new
                        break
                        
            # 4. Обновляем кэш миниатюр
            ThumbnailLoader.inst().rename_cache_key(old_path, new_path)
            
        finally:
            self.grid_view.setUpdatesEnabled(True)
            self.list_view.setUpdatesEnabled(True)
            
        self.grid_view.doItemsLayout()
        self.list_view.doItemsLayout()

    def sync_active_index(self, idx):
        """Синхронизирует выделенный элемент в сетке и списке с указанным индексом."""
        self.grid_view.clearSelection()
        self.list_view.clearSelection()
        
        grid_item = self.get_grid_item(idx)
        list_item = self.get_list_item(idx)
        
        if grid_item:
            grid_item.setSelected(True)
            self.grid_view.setCurrentItem(grid_item)
            self.grid_view.scrollToItem(grid_item)
        if list_item:
            list_item.setSelected(True)
            self.list_view.setCurrentItem(list_item)
            self.list_view.scrollToItem(list_item)
            
        # Обновим визуальное состояние кастомных виджетов
        for view in [self.grid_view, self.list_view]:
            for i in range(view.count()):
                item = view.item(i)
                if not item: continue
                widget = view.itemWidget(item)
                if widget and hasattr(widget, 'set_selected'):
                    widget.set_selected(item.isSelected())
        self.selection_changed.emit()

    def _sync_main_app_index(self, row: int) -> None:
        """Синхронизирует текущий индекс главного приложения с выбранной строкой в списке/плитке."""
        curr_mode = self.stack.currentIndex()
        view = None
        if curr_mode == 1:
            view = self.grid_view
        elif curr_mode == 2:
            view = self.list_view
            
        if not view:
            return
            
        item = view.item(row)
        if not item:
            return
            
        filepath = item.data(Qt.ItemDataRole.UserRole)
        if not filepath:
            return
            
        main_app = self.get_main_app()
        if not main_app:
            return
            
        rel_path = safe_relpath(filepath, main_app.UNSORT_DIR)
        rel_path_norm = os.path.normpath(rel_path)
        
        for idx, f in enumerate(main_app.files_queue):
            if os.path.normpath(f) == rel_path_norm:
                if main_app.current_index != idx:
                    main_app.current_index = idx
                    main_app.current_file_path = filepath
                    logging.info(f"[SorterViewerArea] Synced main app current_index to {idx} ({os.path.basename(filepath)}) from row {row}")
                    # Обновляем тулбар только если выделен 1 файл
                    selected_count = len(self.get_selected_files())
                    if selected_count <= 1:
                        main_app.update_file_info_label()
                break

    def navigate_vertical(self, direction: int) -> None:
        """Перемещает фокус вверх (-1) или вниз (1) по списку/плиткам в зависимости от режима."""
        curr_mode = self.stack.currentIndex()
        if curr_mode == 0:
            main_app = self.get_main_app()
            if main_app:
                if direction == -1:
                    main_app.prev_file()
                else:
                    main_app.next_file()
            return
            
        view = None
        if curr_mode == 1:
            view = self.grid_view
        elif curr_mode == 2:
            view = self.list_view
            
        if not view or view.count() == 0:
            return
            
        current_row = view.currentRow()
        if current_row < 0:
            current_row = 0
            
        if curr_mode == 1:
            cols = self.get_grid_columns_count()
            cols = max(1, cols)
            if direction == -1:
                candidate = current_row - cols
                while candidate >= 0 and not view._get_file_row(candidate):
                    candidate -= 1
                new_row = candidate if candidate >= 0 else current_row
            else:
                candidate = current_row + cols
                while candidate < view.count() and not view._get_file_row(candidate):
                    candidate += 1
                new_row = candidate if candidate < view.count() else current_row
        else:
            new_row = view._next_file_row(current_row, direction)
            
        if new_row != current_row:
            view._apply_key_navigation(new_row, Qt.KeyboardModifier.NoModifier)

    def select_file_from_preview(self, filepath: str) -> None:
        """
        Выделяет файл из окна быстрого просмотра в соответствии с логикой:
        - Если выделено 0 или 1 файл: сбросить всё и выделить только этот файл.
        - Если выделено >= 2 файлов:
          - Если этот файл НЕ выделен: добавить его к текущей выборке.
          - Если этот файл УЖЕ выделен: снять выделение со всех остальных и оставить только его.
        """
        target_path = os.path.normpath(filepath)
        selected_paths = self.get_selected_files()
        count = len(selected_paths)
        
        item_grid = getattr(self, 'grid_items_map', {}).get(target_path)
        item_list = getattr(self, 'list_items_map', {}).get(target_path)
        
        if count <= 1:
            # Сценарий 1: сбрасываем всё и выделяем только этот
            self.grid_view.clearSelection()
            self.list_view.clearSelection()
            if item_grid:
                item_grid.setSelected(True)
                self.grid_view.setCurrentItem(item_grid)
                self.grid_view.scrollToItem(item_grid)
            if item_list:
                item_list.setSelected(True)
                self.list_view.setCurrentItem(item_list)
                self.list_view.scrollToItem(item_list)
        else:
            # Сценарий 2: выделено >= 2 файлов
            if target_path not in selected_paths:
                # 2a: добавить к текущему выделению
                if item_grid:
                    item_grid.setSelected(True)
                if item_list:
                    item_list.setSelected(True)
            else:
                # 2b: снять с других, оставить только этот
                self.grid_view.clearSelection()
                self.list_view.clearSelection()
                if item_grid:
                    item_grid.setSelected(True)
                    self.grid_view.setCurrentItem(item_grid)
                    self.grid_view.scrollToItem(item_grid)
                if item_list:
                    item_list.setSelected(True)
                    self.list_view.setCurrentItem(item_list)
                    self.list_view.scrollToItem(item_list)
                    
        # Обновим визуальное состояние кастомных виджетов
        for view in [self.grid_view, self.list_view]:
            for i in range(view.count()):
                item = view.item(i)
                if not item: continue
                widget = view.itemWidget(item)
                if widget and hasattr(widget, 'set_selected'):
                    widget.set_selected(item.isSelected())
        self.selection_changed.emit()
