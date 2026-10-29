"""
viewer_items.py: Виджеты карточек, элементов списков, разделителей групп и плейсхолдера для Sorter.
"""
import os
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QStyle, QApplication,
    QFileIconProvider, QPushButton, QCheckBox
)
from PyQt6.QtCore import Qt, QSize, QRect, QFileInfo, QPoint, pyqtSignal
from PyQt6.QtGui import (
    QColor, QPixmap, QFont, QPainter, QFontMetrics, QIcon
)

from config import AppContext, VIEWER_DESIGN, APP_DESIGN
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

class SorterPlaceholderWidget(QWidget):
    items_dropped = pyqtSignal(list, bool)
    browse_requested = pyqtSignal()
    double_clicked = pyqtSignal()
    middle_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(14)
        
        # 1. Icon
        self.lbl_icon = QLabel()
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        icons_dir = AppContext.find_resource_dir("icons")
        if icons_dir:
            icon_path = os.path.join(icons_dir, "folder-color.svg")
            if os.path.exists(icon_path):
                pix = QIcon(icon_path).pixmap(QSize(64, 64))
                if not pix.isNull():
                    self.lbl_icon.setPixmap(pix)
        layout.addWidget(self.lbl_icon, 0, Qt.AlignmentFlag.AlignCenter)

        # 2. Title
        self.lbl_title = QLabel()
        self.lbl_title.setStyleSheet("color: #e5e7eb; font-size: 20px; font-weight: bold;")
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.lbl_title, 0, Qt.AlignmentFlag.AlignCenter)

        # 3. Description / Hint
        self.lbl_desc = QLabel()
        self.lbl_desc.setStyleSheet("color: #9ca3af; font-size: 15px; font-weight: normal; line-height: 1.4;")
        self.lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.lbl_desc, 0, Qt.AlignmentFlag.AlignCenter)
        
        # Compatibility alias
        self.lbl_message = self.lbl_desc

        # 4. Action Button
        self.btn_browse = QPushButton()
        self.btn_browse.setStyleSheet("""
            QPushButton { 
                background-color: #3b82f6; 
                color: white; 
                font-size: 15px; 
                font-weight: bold; 
                padding: 10px 24px; 
                border-radius: 6px; 
                border: none;
            }
            QPushButton:hover { background-color: #2563eb; }
            QPushButton:pressed { background-color: #1d4ed8; }
        """)
        self.btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse.clicked.connect(self.browse_requested.emit)
        layout.addWidget(self.btn_browse, 0, Qt.AlignmentFlag.AlignCenter)

        self.set_default_message()

    def set_default_message(self):
        is_ru = AppContext.is_ru() if hasattr(AppContext, 'is_ru') else (getattr(AppContext, 'LANG', 'RU') == 'RU')
        title = "Входящие не выбраны" if is_ru else "Inbox not selected"
        desc = (
            "Перетащите папку или группу файлов для анализа на этот холст\nили выберите их через кнопку ниже"
            if is_ru
            else "Drag & drop a folder or a group of files here for analysis\nor choose them using the button below"
        )
        self.set_content(title, desc, show_button=True)

    def set_content(self, title: str, desc: str = "", show_button: bool = True):
        self.lbl_title.setText(title)
        if desc:
            self.lbl_desc.setText(desc)
            self.lbl_desc.show()
        else:
            self.lbl_desc.setText("")
            self.lbl_desc.hide()
            
        is_ru = AppContext.is_ru() if hasattr(AppContext, 'is_ru') else (getattr(AppContext, 'LANG', 'RU') == 'RU')
        self.btn_browse.setText("📁  Выбрать папку" if is_ru else "📁  Browse Folder")
        if show_button:
            self.btn_browse.show()
        else:
            self.btn_browse.hide()

    def set_message(self, message, show_button=True):
        if not message or message in ("Входящие не выбраны", "Входящие сброшены", "Inbox reset", "Inbox not selected"):
            self.set_default_message()
            return
            
        if "\n\n" in message:
            parts = message.split("\n\n", 1)
            self.set_content(parts[0], parts[1], show_button=show_button)
        elif "\n" in message:
            parts = message.split("\n", 1)
            self.set_content(parts[0], parts[1], show_button=show_button)
        else:
            self.set_content(message, "", show_button=show_button)

    def retranslate_ui(self):
        self.set_default_message()

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

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.middle_clicked.emit()
        super().mousePressEvent(event)

def find_main_app(widget):
    """Поднимается по дереву родителей до первого объекта с global_volume."""
    w = widget
    while w is not None:
        if hasattr(w, 'global_volume'):
            return w
        w = w.parent()
    return None



# Псевдоним для совместимости
ThumbnailCard = SorterGridItemWidget
