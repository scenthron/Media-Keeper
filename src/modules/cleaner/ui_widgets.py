
import random
import os
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QFrame, 
    QTreeWidget, QTreeWidgetItem, QSizePolicy, QMenu, QDoubleSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QThread, QUrl, QFileSystemWatcher, QTimer, QSize
from PyQt6.QtGui import QColor, QFontMetrics, QDesktopServices, QAction, QValidator, QIcon, QPixmap, QPainter, QFont
from config import AppContext
from utils_common import get_folder_icon, format_size
from ui_widgets_base import ElidedLabel

def generate_vibrant_color(index=None):
    if index is not None:
        hue = (index * 137.5) % 360
    else:
        hue = random.randint(0, 359)
    return QColor.fromHsl(int(hue), 200, 160).name()

def load_svg_pixmap(file_path: str, size: QSize) -> QPixmap:
    from PyQt6.QtSvg import QSvgRenderer
    renderer = QSvgRenderer(file_path)
    if not renderer.isValid():
        return QPixmap()
    pixmap = QPixmap(size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap

class SourceListItem(QWidget):
    removed = pyqtSignal(str)
    context_menu_requested = pyqtSignal(QPoint, str)
    
    def __init__(self, path: str, color: str, is_error: bool = False, is_system_error: bool = False, is_protected: bool = False, is_reference: bool = False, is_cached: bool = False, is_face_cached: bool = False, parent=None):
        super().__init__(parent)
        self.path = path
        self.setFixedHeight(42) 
        self.is_cached = is_cached
        self.is_protected = is_protected
        self.is_reference = is_reference
        self.is_error = is_error
        self.is_system_error = is_system_error
        self.color = color
        
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10, 2, 10, 2)
        self.layout.setSpacing(10)
        
        self.lbl_indicator = QLabel()
        self.lbl_indicator.setFixedSize(20, 20)
        self.lbl_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.lbl_indicator)
        
        self.icon_lbl = QLabel()
        if path.lower().endswith(".mkdump"):
            self.icon_lbl.setText("🗄️")
            self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.icon_lbl.setFixedSize(20, 20)
            self.icon_lbl.setStyleSheet("border: none; background: transparent; font-size: 16px; color: #a855f7;")
        else:
            icon = get_folder_icon(path)
            self.icon_lbl.setPixmap(icon.pixmap(20, 20))
            self.icon_lbl.setStyleSheet("background: transparent; border: none;")
        self.layout.addWidget(self.icon_lbl)
        
        folder_name = os.path.basename(path) or path
        self.lbl_name = ElidedLabel(folder_name)
        self.lbl_name.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 13px; border: none; background: transparent;")
        self.lbl_name.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.lbl_name.setMaximumWidth(200) # Limit name width to avoid overlap/squeeze
        self.layout.addWidget(self.lbl_name)
        
        self.lbl_path = ElidedLabel(path)
        self.lbl_path.setStyleSheet("color: #888888; font-size: 12px; border: none; background: transparent;")
        self.lbl_path.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.layout.addWidget(self.lbl_path, 1) # Add stretch factor to path to take remaining space
        
        self.lbl_cache = QLabel()
        self.lbl_cache.setFixedSize(14, 14)
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
        from PyQt6.QtGui import QPixmap
        self.lbl_cache.setPixmap(load_svg_pixmap(os.path.join(icons_dir, "floppy-disk-color.svg"), QSize(14, 14)))
        self.lbl_cache.setToolTip(AppContext.tr("cln_tip_cached"))
        self.lbl_cache.setStyleSheet("border: none; background: transparent;")
        self.lbl_cache.setVisible(is_cached)
        self.layout.addWidget(self.lbl_cache)
        
        self.lbl_face_cache = QLabel("🙂") # Yellow smiley for face cache
        self.lbl_face_cache.setFixedSize(18, 18)
        self.lbl_face_cache.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_face_cache.setStyleSheet("border: none; background: transparent; font-size: 16px; color: #fbbf24; font-family: 'Segoe UI Emoji', 'Apple Color Emoji', 'Noto Color Emoji';")
        self.lbl_face_cache.setToolTip("Сохранен кэш лиц" if AppContext.is_ru() else "Face cache exists")
        self.lbl_face_cache.setVisible(is_face_cached)
        self.layout.addWidget(self.lbl_face_cache)
        
        btn_del = QPushButton("×")
        btn_del.setFixedSize(24, 24)
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setStyleSheet("QPushButton { background: transparent; color: #666; border: none; font-weight: 900; font-size: 18px; } QPushButton:hover { color: #ff5555; background-color: rgba(255,0,0,0.2); border-radius: 4px;}")
        btn_del.clicked.connect(lambda: self.removed.emit(self.path))
        self.layout.addWidget(btn_del)
        
        self.update_style()

    def get_ideal_name_width(self):
        fm = QFontMetrics(self.lbl_name.font())
        text = getattr(self.lbl_name, '_full_text', self.lbl_name.text())
        return fm.horizontalAdvance(text) + 10

    def set_name_label_width(self, width):
        self.lbl_name.setFixedWidth(width)

    def set_cached_state(self, cached):
        self.is_cached = cached
        self.lbl_cache.setVisible(cached)

    def set_protected_state(self, protected):
        self.is_protected = protected
        self.update_style()

    def set_reference_state(self, reference):
        self.is_reference = reference
        if reference:
            self.is_protected = True   # Эталон всегда защищён
        else:
            self.is_protected = self.path.lower().endswith('.mkdump')
        self.update_style()

    def set_error_state(self, message):
        self.is_error = True
        self.setToolTip(f"⚠️ {message}")
        self.update_style()

    def set_system_error_state(self):
        self.is_system_error = True
        self.setToolTip(AppContext.tr("msg_sys_dir_protected"))
        self.update_style()

    def clear_error_state(self):
        self.is_error = False
        self.setToolTip(self.path)
        self.update_style()

    def update_style(self):
        common_label_style = "background: transparent; border: none;"
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
        from PyQt6.QtGui import QPixmap
        
        if self.is_system_error:
            # System Error Style (Red, Stop Sign)
            self.lbl_indicator.setPixmap(load_svg_pixmap(os.path.join(icons_dir, "stop-color.svg"), QSize(16, 16)))
            self.lbl_indicator.setStyleSheet(f"{common_label_style}")
            
            self.setStyleSheet(f"SourceListItem {{ background-color: rgba(220, 38, 38, 0.2); border: 1px solid #dc2626; border-radius: 4px; margin-bottom: 2px; }} SourceListItem:hover {{ background-color: rgba(220, 38, 38, 0.3); }}")
            self.lbl_name.setStyleSheet("color: #fca5a5; font-weight: bold; font-size: 13px; border: none; background: transparent;")
            
        elif self.is_reference:
            # Reference Style (Blue, Star) - HIGHER PRIORITY than protected
            self.lbl_indicator.setPixmap(load_svg_pixmap(os.path.join(icons_dir, "star-color.svg"), QSize(16, 16)))
            self.lbl_indicator.setStyleSheet(f"{common_label_style}")
            
            self.setStyleSheet(f"SourceListItem {{ background-color: rgba(59, 130, 246, 0.15); border: 2px solid #3b82f6; border-radius: 4px; margin-bottom: 2px; }} SourceListItem:hover {{ background-color: rgba(59, 130, 246, 0.25); }}")
            self.lbl_name.setStyleSheet("color: #93c5fd; font-weight: bold; font-size: 13px; border: none; background: transparent;")

        elif self.is_protected:
            # Protected Style (Yellow Lock)
            self.lbl_indicator.setPixmap(load_svg_pixmap(os.path.join(icons_dir, "lock-color.svg"), QSize(16, 16)))
            self.lbl_indicator.setStyleSheet(f"{common_label_style}")
            
            self.setStyleSheet(f"SourceListItem {{ background-color: rgba(251, 191, 36, 0.15); border: 1px solid rgba(251, 191, 36, 0.3); border-radius: 4px; margin-bottom: 2px; }} SourceListItem:hover {{ background-color: rgba(251, 191, 36, 0.25); }}")
            self.lbl_name.setStyleSheet("color: #fbbf24; font-weight: bold; font-size: 13px; border: none; background: transparent;")

        else:
            # Standard Style (Color Dot)
            self.lbl_indicator.setPixmap(QPixmap())
            self.lbl_indicator.setText("")
            self.lbl_indicator.setStyleSheet(f"background-color: {self.color}; border-radius: 10px; border: 1px solid #555;")
            
            if self.is_error:
                # Nesting Error (Red tint)
                self.setStyleSheet(f"SourceListItem {{ background-color: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.5); border-radius: 4px; margin-bottom: 2px; }} SourceListItem:hover {{ background-color: rgba(239, 68, 68, 0.25); }}")
                self.lbl_name.setStyleSheet("color: #fca5a5; font-weight: bold; font-size: 13px; border: none; background: transparent;")
            else:
                # Normal
                self.setStyleSheet(f"SourceListItem {{ background-color: transparent; border-bottom: 1px solid #333; }} SourceListItem:hover {{ background-color: #2a2a2a; }}")
                self.lbl_name.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 13px; border: none; background: transparent;")
        
        self.icon_lbl.setStyleSheet("background: transparent; border: none;")

    def _on_context_menu(self, pos):
        self.context_menu_requested.emit(self.mapToGlobal(pos), self.path)

class GroupHeaderWidget(QWidget):
    clicked = pyqtSignal()
    menu_requested = pyqtSignal(QPoint)

    def __init__(self, name_text, count, total_size_str, wasted_str, source_indicators):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Save raw data for re-translation
        self.raw_name = name_text
        self.raw_count = count
        self.raw_total = total_size_str
        self.raw_wasted = wasted_str
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(15)
        
        title_text = AppContext.tr("cln_group_fmt_title").format(name_text)
        self.lbl_title = ElidedLabel(title_text)
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #eee; border: none; background: transparent;")
        self.lbl_title.setFixedWidth(200)
        layout.addWidget(self.lbl_title)
        
        count_text = AppContext.tr("cln_group_fmt_files").format(count)
        self.lbl_count = QLabel(count_text)
        self.lbl_count.setStyleSheet("font-size: 12px; color: #aaa; border: none; background: transparent;")
        self.lbl_count.setFixedWidth(100)
        layout.addWidget(self.lbl_count)
        
        size_text = AppContext.tr("cln_group_fmt_total").format(total_size_str)
        self.lbl_size = QLabel(size_text)
        self.lbl_size.setStyleSheet("font-family: monospace; font-size: 12px; color: #aaa; font-weight: bold; border: none; background: transparent;")
        self.lbl_size.setFixedWidth(140) 
        layout.addWidget(self.lbl_size)
        
        wasted_text = AppContext.tr("cln_group_fmt_wasted").format(wasted_str)
        self.lbl_wasted = QLabel(wasted_text)
        self.lbl_wasted.setStyleSheet("font-family: monospace; font-size: 12px; color: #fb923c; border: none; background: transparent;") 
        self.lbl_wasted.setFixedWidth(140) 
        layout.addWidget(self.lbl_wasted)
        
        layout.addSpacing(20)
        
        
        for indicator in source_indicators:
            icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
            if indicator['type'] == 'lock':
                lock = QLabel()
                lock.setFixedSize(20, 20)
                lock.setPixmap(load_svg_pixmap(os.path.join(icons_dir, "lock-color.svg"), QSize(16, 16)))
                lock.setStyleSheet("border: none; background: transparent;")
                lock.setAlignment(Qt.AlignmentFlag.AlignCenter)
                layout.addWidget(lock)
            elif indicator['type'] == 'star':
                star = QLabel()
                star.setFixedSize(20, 20)
                star.setPixmap(load_svg_pixmap(os.path.join(icons_dir, "star-color.svg"), QSize(16, 16)))
                star.setStyleSheet("border: none; background: transparent;")
                star.setAlignment(Qt.AlignmentFlag.AlignCenter)
                layout.addWidget(star)
            else:
                color = indicator['val']
                dot = QFrame()
                dot.setFixedSize(20, 20) 
                dot.setStyleSheet(f"background-color: {color}; border-radius: 10px; margin-right: 4px; border: 1px solid #555; min-width: 20px; min-height: 20px; max-width: 20px; max-height: 20px;")
                layout.addWidget(dot)
            
        layout.addStretch()

    def update_ui_text(self):
        """Re-apply translations"""
        self.lbl_title.setText(AppContext.tr("cln_group_fmt_title").format(self.raw_name))
        self.lbl_count.setText(AppContext.tr("cln_group_fmt_files").format(self.raw_count))
        self.lbl_size.setText(AppContext.tr("cln_group_fmt_total").format(self.raw_total))
        self.lbl_wasted.setText(AppContext.tr("cln_group_fmt_wasted").format(self.raw_wasted))

    def set_visual_state(self, state):
        if state == "done":
            self.setStyleSheet("background-color: #323B4D; border-radius: 4px;")
            self.setToolTip("Группа обработана")
        elif state == "warning":
            self.setStyleSheet("background-color: #3B1C1C; border-radius: 4px;")
            self.setToolTip("Есть необработанные дубли")
        else:
            self.setStyleSheet("background: transparent;")
            self.setToolTip("")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        elif event.button() == Qt.MouseButton.RightButton:
            self.menu_requested.emit(event.globalPosition().toPoint())

class CleanerTreeWidget(QTreeWidget):
    itemMiddleClicked = pyqtSignal(QTreeWidgetItem)
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            item = self.itemAt(event.pos())
            if item: self.itemMiddleClicked.emit(item)
        super().mousePressEvent(event)

class FolderSizeWorker(QThread):
    finished = pyqtSignal(float, int, int) # size(float to avoid overflow), file_count, folder_count
    def __init__(self, path):
        super().__init__()
        self.path = path
    def run(self):
        total_size, file_count, folder_count = 0, 0, 0
        try:
            for root, dirs, files in os.walk(self.path):
                folder_count += len(dirs)
                for f in files:
                    fp = os.path.join(root, f)
                    try: 
                        total_size += os.path.getsize(fp)
                        file_count += 1
                    except: pass
        except: pass
        self.finished.emit(total_size, file_count, folder_count)

class CompactDropZone(QFrame):
    path_changed = pyqtSignal(str)
    clicked = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFixedHeight(28) 
        self.current_path = ""
        self.default_text = AppContext.tr("cln_ph_dest")
        self.calc_worker = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self.on_directory_changed)
        
        self.debounce_timer = QTimer(self)
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(1000)
        self.debounce_timer.timeout.connect(self.on_debounce_timeout)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 5, 0)
        layout.setSpacing(5)
        
        self.lbl_path = ElidedLabel(self.default_text)
        self.lbl_path.setElideMode(Qt.TextElideMode.ElideRight)
        self.lbl_path.setStyleSheet("color: #888; font-size: 12px; font-weight: bold; border: none; background: transparent;")
        self.lbl_path.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self.lbl_path.setMinimumWidth(0)
        layout.addWidget(self.lbl_path, 0)
        
        self.lbl_stats = QLabel("")
        self.lbl_stats.setStyleSheet("color: #cccccc; font-size: 13px; font-weight: bold; border: none; background: transparent;")
        self.lbl_stats.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        self.lbl_stats.hide()
        layout.addWidget(self.lbl_stats, 0)
        
        # Add a stretch spacer (spring) inside the drop zone to absorb remaining space first
        layout.addStretch(1)
        
        self.btn_clear = QPushButton()
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
        self.btn_clear.setIcon(QIcon(os.path.join(icons_dir, "trash-color.svg")))
        self.btn_clear.setIconSize(QSize(14, 14))
        self.btn_clear.setFixedSize(24, 24)
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.clicked.connect(self.clear_path)
        self.btn_clear.setToolTip("Очистить путь")
        self.btn_clear.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background-color: rgba(239, 68, 68, 0.1); border-radius: 4px; }")
        self.btn_clear.hide()
        layout.addWidget(self.btn_clear)

        self.btn_browse = QPushButton(" +")
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
        self.btn_browse.setIcon(QIcon(os.path.join(icons_dir, "folder-color.svg")))
        self.btn_browse.setIconSize(QSize(16, 16))
        self.btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse.setFixedSize(50, 24)
        self.btn_browse.clicked.connect(self.clicked.emit)
        self.btn_browse.setToolTip("Выбрать папку (Обзор)")
        self.btn_browse.setStyleSheet("QPushButton { background-color: transparent; color: #888; border: 1px solid #555; border-radius: 12px; font-size: 12px; font-weight: bold; margin-left: 5px; } QPushButton:hover { background-color: rgba(234, 179, 8, 0.1); color: white; border-color: #eab308; }")
        layout.addWidget(self.btn_browse)
        self.reset_style()

    def reset_style(self):
        if self.current_path:
            self.setStyleSheet("CompactDropZone { background-color: rgba(59, 130, 246, 0.05); border: 2px solid #3b82f6; border-radius: 6px; } CompactDropZone:hover { background-color: rgba(59, 130, 246, 0.1); }")
        else:
            self.setStyleSheet("CompactDropZone { background-color: rgba(0, 0, 0, 0.2); border: 2px dashed #555; border-radius: 6px; } CompactDropZone:hover { background-color: rgba(255, 255, 255, 0.05); border-color: #3b82f6; }")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet("CompactDropZone { background-color: rgba(59, 130, 246, 0.15); border: 2px dashed #3b82f6; border-radius: 6px; }")
        else: event.ignore()

    def dragLeaveEvent(self, event):
        self.reset_style()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if os.path.isdir(path) or path.lower().endswith('.mkdump'):
                self.set_path(path)
                event.acceptProposedAction()
        self.reset_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.pos())
            if child is not self.btn_clear and child is not self.btn_browse:
                self.clicked.emit()
        super().mousePressEvent(event)

    def _show_context_menu(self, pos):
        if not self.current_path: return
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #2b2b2b; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #3b82f6; }")
        act_open = QAction(AppContext.tr("cln_ctx_show_folder"), self)
        act_open.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.current_path)))
        menu.addAction(act_open)
        menu.exec(self.mapToGlobal(pos))

    def set_path(self, path):
        self.current_path = os.path.normpath(path)
        name = os.path.basename(self.current_path) or self.current_path
        self.lbl_path.setText(f"📂 {name}")
        self.lbl_path.setStyleSheet("color: #3b82f6; font-size: 13px; font-weight: bold; border: none; background: transparent;")
        self.lbl_stats.setText("(...)")
        self.lbl_stats.show()
        self.btn_clear.show()
        self.reset_style()
        self.path_changed.emit(self.current_path)
        if self.calc_worker and self.calc_worker.isRunning(): self.calc_worker.terminate()
        self.calc_worker = FolderSizeWorker(self.current_path)
        self.calc_worker.finished.connect(self.on_size_calculated)
        self.calc_worker.start()
        
        if self.watcher.directories():
            self.watcher.removePaths(self.watcher.directories())
        if os.path.exists(self.current_path):
            self.watcher.addPath(self.current_path)

    def on_size_calculated(self, size, count, folder_count):
        if not self.current_path: return
        sz_str = format_size(size)
        self.lbl_stats.setText(f"({sz_str})")
        tooltip = f"{self.current_path}\nРазмер: {sz_str}\nФайлов: {count}\nПапок: {folder_count}"
        self.lbl_path.setToolTip(tooltip)
        self.lbl_stats.setToolTip(tooltip)

    def clear_path(self):
        self.current_path = ""
        self.lbl_path.setText(self.default_text)
        self.lbl_path.setStyleSheet("color: #888; font-size: 12px; font-weight: bold; border: none; background: transparent;")
        self.lbl_path.setToolTip("")
        self.lbl_stats.hide()
        self.btn_clear.hide()
        self.reset_style()
        self.path_changed.emit("")
        if self.watcher.directories():
            self.watcher.removePaths(self.watcher.directories())
            
    def on_directory_changed(self, path):
        self.debounce_timer.start()
        
    def on_debounce_timeout(self):
        if not os.path.exists(self.current_path):
            self.clear_path()
        else:
            self.refresh_stats()

    def refresh_stats(self):
        if self.current_path:
            self.set_path(self.current_path)

    def get_path(self): return self.current_path

    def update_ui_text(self):
        self.default_text = AppContext.tr("cln_ph_dest")
        if not self.current_path:
            self.lbl_path.setText(self.default_text)

class CleanSpinBox(QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lineEdit().setPlaceholderText("0")
    def textFromValue(self, val):
        if val == 0: return ""
        if val.is_integer(): return str(int(val))
        return f"{val:.2f}".rstrip('0').rstrip('.')
    def valueFromText(self, text):
        if not text.strip(): return 0.0
        return super().valueFromText(text)
    def validate(self, input_text, pos):
        if not input_text: return QValidator.State.Acceptable, input_text, pos
        return super().validate(input_text, pos)

class ModeBadgeButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(24)
        self.setCheckable(True)
        self._mode = "disabled"
        self.update_style()
    def set_mode(self, mode):
        self._mode = mode
        self.setEnabled(mode != 'disabled')
        self.update_style()
    def update_style(self):
        if self._mode == 'disabled':
            self.setStyleSheet("QPushButton { background-color: transparent; color: #555; border: 1px solid #444; border-radius: 4px; padding: 0 10px; font-weight: normal; font-size: 12px; }")
        elif self._mode == 'available':
            self.setStyleSheet("QPushButton { background-color: transparent; color: #3b82f6; border: 1px solid #3b82f6; border-radius: 4px; padding: 0 10px; font-weight: bold; font-size: 12px; } QPushButton:hover { background-color: rgba(59, 130, 246, 0.1); }")
        elif self._mode == 'active':
            self.setStyleSheet("QPushButton { background-color: #15803d; color: white; border: 1px solid #16a34a; border-radius: 4px; padding: 0 10px; font-weight: bold; font-size: 12px; }")


from PyQt6.QtWidgets import QListWidget, QAbstractItemView, QStyledItemDelegate

# -----------------------------------------------------------------------------
# Всплывающее окно быстрого просмотра картинок при наведении мыши (в 2.5 раза больше)
# -----------------------------------------------------------------------------
class ImageHoverToolTip(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet("background-color: #2b2b2b; border: 2px solid #3b82f6; padding: 2px; border-radius: 6px;")
        self.setScaledContents(True)
        self.setFixedSize(650, 650) # В 2.5 раза больше (было 260x260)
        self.hide()
        
    def show_image(self, path: str, pos: QPoint):
        if not path or not os.path.exists(path):
            self.hide()
            return
            
        try:
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                # Масштабируем до 640x640 с сохранением пропорций
                scaled = pixmap.scaled(640, 640, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.setPixmap(scaled)
                self.setFixedSize(scaled.width() + 10, scaled.height() + 10)
                
                # Смещаем правее и ниже курсора
                self.move(pos.x() + 15, pos.y() + 15)
                self.show()
            else:
                self.hide()
        except Exception:
            self.hide()


from PyQt6.QtWidgets import QStyledItemDelegate
from PyQt6.QtGui import QPainter, QColor, QPen

class RefImageDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hovered_index = None

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        
        is_face_mode = index.data(Qt.ItemDataRole.UserRole + 1)
        face_found = index.data(Qt.ItemDataRole.UserRole + 2)
        
        rect = option.rect
        
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        ind_rect = rect.adjusted(4, 4, -rect.width() + 24, -rect.height() + 24)
        painter.setPen(Qt.PenStyle.NoPen)
        if face_found == True:
            painter.setBrush(QColor("#22c55e"))
            painter.drawEllipse(ind_rect)
            painter.setPen(QPen(Qt.GlobalColor.white, 2))
            painter.setFont(QFont("Segoe UI Emoji", 9, QFont.Weight.Bold))
            painter.drawText(ind_rect.adjusted(0, -1, 0, -1), Qt.AlignmentFlag.AlignCenter, "🙂" if is_face_mode else "✓")
        elif face_found == False:
            painter.setBrush(QColor("#ef4444"))
            painter.drawEllipse(ind_rect)
            painter.setPen(QPen(Qt.GlobalColor.white, 2))
            painter.setFont(QFont("Segoe UI Emoji", 9, QFont.Weight.Bold))
            painter.drawText(ind_rect.adjusted(0, -1, 0, -1), Qt.AlignmentFlag.AlignCenter, "🙁" if is_face_mode else "✕")
        else:
            painter.setBrush(QColor("#6b7280"))
            painter.drawEllipse(ind_rect)
            painter.setPen(QPen(Qt.GlobalColor.white, 2))
            # Just draw the grey circle with white border, don't draw the ⚪ emoji which has a white center inside.
        painter.restore()
            
        if self.hovered_index is not None and index == self.hovered_index:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            cross_rect = rect.adjusted(rect.width() - 20, 4, -4, -rect.height() + 20)
            painter.setBrush(QColor(239, 68, 68, 220))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(cross_rect, 4, 4)
            painter.setPen(QPen(Qt.GlobalColor.white, 2))
            painter.drawLine(cross_rect.left() + 4, cross_rect.top() + 4, cross_rect.right() - 4, cross_rect.bottom() - 4)
            painter.drawLine(cross_rect.right() - 4, cross_rect.top() + 4, cross_rect.left() + 4, cross_rect.bottom() - 4)
            painter.restore()



# -----------------------------------------------------------------------------
# Кастомный список для картинок-примеров с поддержкой Drag & Drop и Hover-превью
# -----------------------------------------------------------------------------
class RefImagesListWidget(QListWidget):
    files_dropped = pyqtSignal(list)
    item_hovered = pyqtSignal(str, QPoint)
    hover_left = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(76, 76))
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setGridSize(QSize(86, 86))
        self.setMouseTracking(True)
        self.setStyleSheet("""
            QListWidget {
                background-color: #151515;
                border: 1px solid #444;
                border-radius: 6px;
                outline: none;
            }
            QListWidget::item {
                border: 1px solid transparent;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background-color: #2a2a2a;
                border: 1px solid #555;
            }
            QListWidget::item:selected {
                background-color: #3b82f6;
                border: 1px solid #2563eb;
            }
        """)
        
        self.delegate = RefImageDelegate(self)
        self.setItemDelegate(self.delegate)
        
        self.hover_timer = QTimer(self)
        self.hover_timer.setSingleShot(True)
        self.hover_timer.setInterval(500)
        self.hover_timer.timeout.connect(self._emit_hover)
        self._pending_hover_path = None
        self._pending_hover_pos = None

    def _emit_hover(self):
        if self._pending_hover_path:
            self.item_hovered.emit(self._pending_hover_path, self._pending_hover_pos)
            self._is_tooltip_visible = True
            
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dropEvent(self, event):
        files = []
        for url in event.mimeData().urls():
            fp = url.toLocalFile()
            if os.path.isfile(fp):
                ext = os.path.splitext(fp)[1].lower()
                if ext in {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}:
                    files.append(fp)
        if files:
            self.files_dropped.emit(files)
            event.acceptProposedAction()

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.hover_timer.stop()
            self._pending_hover_path = None
            if hasattr(self, "_is_tooltip_visible") and self._is_tooltip_visible:
                if hasattr(self.parent(), "hover_tooltip") and self.parent().hover_tooltip.isVisible():
                    self.parent().hover_tooltip.hide()
                self._is_tooltip_visible = False
            return

        item = self.itemAt(event.pos())
        index = self.indexAt(event.pos())
        
        if index.isValid():
            if self.delegate.hovered_index != index:
                self.delegate.hovered_index = index
                self.viewport().update()
        else:
            if self.delegate.hovered_index is not None:
                self.delegate.hovered_index = None
                self.viewport().update()

        if item:
            path = item.data(Qt.ItemDataRole.UserRole)
            if hasattr(self, "_is_tooltip_visible") and self._is_tooltip_visible:
                if hasattr(self.parent(), "hover_tooltip") and self.parent().hover_tooltip.isVisible():
                    self.parent().hover_tooltip.hide()
                self._is_tooltip_visible = False
                
            self._pending_hover_path = path
            self._pending_hover_pos = event.globalPosition().toPoint()
            self.hover_timer.start()
        else:
            self.hover_timer.stop()
            self._pending_hover_path = None
            self._is_tooltip_visible = False
            if hasattr(self.parent(), "hover_tooltip") and self.parent().hover_tooltip.isVisible():
                self.parent().hover_tooltip.hide()
            self.hover_left.emit()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if self.delegate.hovered_index is not None:
            self.delegate.hovered_index = None
            self.viewport().update()
        self.hover_timer.stop()
        self._pending_hover_path = None
        self.hover_left.emit()
        self.hover_left.emit()

    def mousePressEvent(self, event):
        item = self.itemAt(event.pos())
        if item:
            rect = self.visualItemRect(item)
            cross_rect = rect.adjusted(rect.width() - 20, 4, -4, -rect.height() + 20)
            if cross_rect.contains(event.pos()):
                path = item.data(Qt.ItemDataRole.UserRole)
                parent_dlg = self.parent()
                while parent_dlg and not hasattr(parent_dlg, 'delete_specific_file'):
                    parent_dlg = parent_dlg.parent()
                if parent_dlg and hasattr(parent_dlg, 'delete_specific_file'):
                    parent_dlg.delete_specific_file(path)
                return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            parent_dlg = self.parent()
            while parent_dlg and not hasattr(parent_dlg, 'delete_selected_files'):
                parent_dlg = parent_dlg.parent()
            if parent_dlg and hasattr(parent_dlg, 'delete_selected_files'):
                parent_dlg.delete_selected_files()
        super().keyPressEvent(event)
