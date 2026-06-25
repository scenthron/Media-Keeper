import os
import sys
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QApplication
from PyQt6.QtGui import QPainter, QColor, QPixmap, QFont, QIcon
from PyQt6.QtCore import Qt, QRect, pyqtSignal, QTimer

from config import AppContext, APP_VERSION
from main import MediaKeeperShell
from languages.manager import LanguageManager

class LauncherWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Media Keeper {APP_VERSION}")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.drag_position = None
        
        self.base_path = AppContext._get_base_path()
        icon_path = os.path.join(self.base_path, "launcher", "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.image_en_path = os.path.join(self.base_path, "launcher", "launcher-en.png")
        self.image_ru_path = os.path.join(self.base_path, "launcher", "launcher-ru.png")
        
        self.overlay_files = {
            "editor": "Cel_conv.png",
            "cleaner": "Cel_dub.png",
            "analyzer": "Cel_mapdisk.png",
            "sorter": "Cel_sorter.png",
            "exit": "Open_gates.png",
            "lang": "Select_lang.png"
        }
        self.overlays = {}
        
        self.scale_factor = 1.5
        self.load_background()
            
        self.hovered_zone = None
        self.setMouseTracking(True)
        
        # Original Coordinates: x, y, width (x2 - x1), height (y2 - y1)
        # Scaled dynamically
        self.zones = {
            "lang":     {"rect": QRect(int(66 / self.scale_factor), int(26 / self.scale_factor), int(74 / self.scale_factor), int(49 / self.scale_factor))},
            "exit":     {"rect": QRect(int(1240 / self.scale_factor), int(15 / self.scale_factor), int(85 / self.scale_factor), int(101 / self.scale_factor))},
            "sorter":   {"rect": QRect(int(72 / self.scale_factor), int(190 / self.scale_factor), int(581 / self.scale_factor), int(243 / self.scale_factor))},
            "editor":   {"rect": QRect(int(72 / self.scale_factor), int(505 / self.scale_factor), int(581 / self.scale_factor), int(229 / self.scale_factor))},
            "analyzer": {"rect": QRect(int(727 / self.scale_factor), int(190 / self.scale_factor), int(581 / self.scale_factor), int(243 / self.scale_factor))},
            "cleaner":  {"rect": QRect(int(727 / self.scale_factor), int(505 / self.scale_factor), int(581 / self.scale_factor), int(229 / self.scale_factor))}
        }

    def load_background(self):
        path = self.image_ru_path if AppContext.LANG == "RU" else self.image_en_path
        self.bg_pixmap = QPixmap(path) if os.path.exists(path) else None
        if self.bg_pixmap and not self.bg_pixmap.isNull():
            scaled_width = int(self.bg_pixmap.width() / self.scale_factor)
            scaled_height = int(self.bg_pixmap.height() / self.scale_factor)
            self.bg_pixmap = self.bg_pixmap.scaled(scaled_width, scaled_height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.setFixedSize(self.bg_pixmap.size())
        else:
            self.setFixedSize(int(1400 / self.scale_factor), int(800 / self.scale_factor)) # Fallback size
            
        self.load_overlays()

    def load_overlays(self):
        self.overlays = {}
        for key, filename in self.overlay_files.items():
            path = os.path.join(self.base_path, "launcher", filename)
            pixmap = QPixmap(path) if os.path.exists(path) else None
            if pixmap and not pixmap.isNull():
                if self.bg_pixmap and not self.bg_pixmap.isNull():
                    scaled_size = self.bg_pixmap.size()
                    pixmap = pixmap.scaled(scaled_size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                else:
                    scaled_width = int(pixmap.width() / self.scale_factor)
                    scaled_height = int(pixmap.height() / self.scale_factor)
                    pixmap = pixmap.scaled(scaled_width, scaled_height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.overlays[key] = pixmap
            else:
                self.overlays[key] = None

    def mouseMoveEvent(self, event):
        pos = event.pos()
        found_zone = None
        for key, data in self.zones.items():
            if data["rect"].contains(pos):
                found_zone = key
                break
                
        if self.hovered_zone != found_zone:
            self.hovered_zone = found_zone
            self.update() # Trigger repaint for the hover effect
            
        if self.drag_position is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.hovered_zone:
                self.handle_zone_click(self.hovered_zone)
            else:
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = None
            event.accept()

    def handle_zone_click(self, zone):
        if zone == "exit":
            os._exit(0)
        elif zone == "lang":
            self.toggle_language()
            return
            
        # Проверяем наличие FFmpeg перед переходом в любой рабочий инструмент
        from modules.editor.ffmpeg_downloader import check_ffmpeg_available
        is_available, _ = check_ffmpeg_available()
        
        if not is_available and not getattr(AppContext, "ffmpeg_warning_dismissed", False):
            from modules.editor.ui_ffmpeg_notice import FFmpegDownloadConfirmDialog
            dlg = FFmpegDownloadConfirmDialog(self)
            if dlg.exec() != 1:
                AppContext.ffmpeg_warning_dismissed = True
                
        if zone == "cleaner":
            self.launch_cleaner()
        elif zone == "sorter":
            self.launch_sorter()
        elif zone == "editor":
            self.launch_editor()
        elif zone == "analyzer":
            self.launch_analyzer()

    def toggle_language(self):
        # Switch language
        new_lang = "RU" if AppContext.LANG == "EN" else "EN"
        AppContext.LANG = new_lang
        
        # Save to settings
        import configparser
        from logic_paths import get_app_data_dir
        settings_path = os.path.join(get_app_data_dir(), "settings.ini")
        config = configparser.ConfigParser()
        if os.path.exists(settings_path):
            config.read(settings_path)
        if not config.has_section("General"):
            config.add_section("General")
        config.set("General", "Language", new_lang)
        with open(settings_path, "w") as f:
            config.write(f)
            
        LanguageManager.load_language(new_lang)
        self.load_background()
        self.update()

    def launch_cleaner(self):
        self.hide()
        self.cleaner_window = MediaKeeperShell()
        self.cleaner_window.switch_tab(2)
        self.cleaner_window.show()

    def launch_sorter(self):
        self.hide()
        self.cleaner_window = MediaKeeperShell()
        self.cleaner_window.switch_tab(0)
        self.cleaner_window.show()

    def launch_editor(self):
        self.hide()
        self.cleaner_window = MediaKeeperShell()
        self.cleaner_window.switch_tab(1)
        self.cleaner_window.show()

    def launch_analyzer(self):
        self.hide()
        self.cleaner_window = MediaKeeperShell()
        self.cleaner_window.switch_tab(3)
        self.cleaner_window.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw background
        if self.bg_pixmap and not self.bg_pixmap.isNull():
            painter.drawPixmap(0, 0, self.bg_pixmap)
        else:
            painter.fillRect(self.rect(), QColor(30, 30, 30))
                
        # Draw hovered overlay if any
        if self.hovered_zone and self.hovered_zone in self.overlays:
            overlay_pixmap = self.overlays[self.hovered_zone]
            if overlay_pixmap and not overlay_pixmap.isNull():
                painter.drawPixmap(0, 0, overlay_pixmap)
