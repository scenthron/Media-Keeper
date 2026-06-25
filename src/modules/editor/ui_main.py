
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QStackedWidget, QLabel, QFrame, QHBoxLayout, QPushButton, QButtonGroup
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from config import AppContext, APP_DESIGN

# Lazy imports to avoid circular deps if needed, 
# but here we can import directly as strictly hierarchical.
from .video.ui_converter import VideoConverterWidget
from .video.ui_editor import VideoEditorWidget
from .audio.ui_converter import AudioConverterWidget
from .image.ui_converter import ImageConverterWidget
from .ui_ffmpeg_notice import FFmpegNoticeWidget

class EditorMainWidget(QWidget):
    ffmpeg_downloaded = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        # Apply global theme background to prevent "white lines" if transparent widgets are used
        self.setStyleSheet(f"background-color: {APP_DESIGN['bg_color_main']}; color: {APP_DESIGN['text_color']};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Custom Toolbar
        self.top_toolbar = QFrame()
        self.top_toolbar.setFixedHeight(40)
        self.top_toolbar.setStyleSheet("background-color: #2b2b2b; border-bottom: 1px solid #444;")
        
        tb_layout = QHBoxLayout(self.top_toolbar)
        tb_layout.setContentsMargins(10, 0, 10, 0)
        tb_layout.setSpacing(10)
        tb_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        
        # Hamburger Menu Button
        self.btn_menu = QPushButton("≡")
        self.btn_menu.setFixedSize(40, 40)
        self.btn_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_menu.setStyleSheet("QPushButton { background: transparent; color: #ccc; font-size: 24px; border: none; font-weight: bold; } QPushButton:hover { color: white; background-color: rgba(255,255,255,0.1); border-radius: 4px; }")
        tb_layout.addWidget(self.btn_menu)
        
        # Tab Buttons Group
        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)
        
        # Helper to create styled tab buttons
        def create_tab_btn(text, index):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(30)
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #888;
                    border: none;
                    font-weight: bold;
                    padding: 0 15px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.05);
                    color: #ddd;
                }
                QPushButton:checked {
                    background-color: #3b82f6;
                    color: white;
                }
            """)
            btn.clicked.connect(lambda checked, idx=index: self._update_tab_buttons(idx))
            self.tab_group.addButton(btn, index)
            tb_layout.addWidget(btn)
            return btn

        self.btn_video = create_tab_btn(f"🎬 {AppContext.tr('tab_video_converter')}", 0)
        self.btn_editor = create_tab_btn(f"✂️ {AppContext.tr('tab_video_editor')}", 1)
        
        tb_layout.addSpacing(20) 
        self.btn_audio = create_tab_btn(f"🎵 {AppContext.tr('tab_audio_converter')}", 2)
        
        tb_layout.addSpacing(20)
        self.btn_image = create_tab_btn(f"🖼️ {AppContext.tr('tab_image_converter')}", 3)
        
        tb_layout.addStretch()
        
        layout.addWidget(self.top_toolbar)

        # Tabs Content
        self.tabs = QStackedWidget()
        layout.addWidget(self.tabs)

        # 1. Video Converter Tab
        self.tab_video = VideoConverterWidget()
        self.tabs.addWidget(self.tab_video)
        
        # 2. Video Editor Tab
        self.tab_editor = VideoEditorWidget()
        self.tabs.addWidget(self.tab_editor)
        
        # 3. Audio Converter Tab (New)
        self.tab_audio = AudioConverterWidget()
        self.tabs.addWidget(self.tab_audio)
        
        # 4. Image Converter Tab
        self.tab_image = ImageConverterWidget()
        self.tabs.addWidget(self.tab_image)
        
        # 5. FFmpeg Notice Tab (Fallback)
        self.notice_widget = FFmpegNoticeWidget(self)
        self.tabs.addWidget(self.notice_widget)
        self.notice_widget.download_finished.connect(self.on_ffmpeg_downloaded)
        self.notice_widget.download_finished.connect(lambda success: success and self.ffmpeg_downloaded.emit())
        if hasattr(self.tab_video, 'ffmpeg_notice') and self.tab_video.ffmpeg_notice:
            self.tab_video.ffmpeg_notice.download_finished.connect(lambda success: success and self.ffmpeg_downloaded.emit())
        if hasattr(self.tab_editor, 'ffmpeg_notice') and self.tab_editor.ffmpeg_notice:
            self.tab_editor.ffmpeg_notice.download_finished.connect(lambda success: success and self.ffmpeg_downloaded.emit())
        
        self.tabs.setStyleSheet("QTabWidget::pane { border: 0; background: #1e1e1e; }")

        # Sync Tabs -> Buttons
        self._update_tab_buttons(0)

    def _update_tab_buttons(self, index):
        from .ffmpeg_downloader import check_ffmpeg_available
        is_available, _ = check_ffmpeg_available()
        
        btns = [self.btn_video, self.btn_editor, self.btn_audio, self.btn_image]
        for i, b in enumerate(btns):
            b.setChecked(i == index)
            
        if not is_available and index in (0, 1, 2):
            self.last_target_index = index
            self.tabs.setCurrentIndex(4)
        else:
            self.tabs.setCurrentIndex(index)

    def open_video_converter(self, filepaths):
        from .ffmpeg_downloader import check_ffmpeg_available
        is_available, _ = check_ffmpeg_available()
        if not is_available:
            self.pending_files = ("video_converter", filepaths)
            self._update_tab_buttons(0)
            return
            
        self._update_tab_buttons(0)
        if hasattr(self.tab_video, 'on_files_dropped'):
            self.tab_video.on_files_dropped(filepaths)

    def open_video_editor(self, filepath):
        from .ffmpeg_downloader import check_ffmpeg_available
        is_available, _ = check_ffmpeg_available()
        if not is_available:
            self.pending_files = ("video_editor", filepath)
            self._update_tab_buttons(1)
            return
            
        self._update_tab_buttons(1)
        if hasattr(self.tab_editor, 'load_video'):
            self.tab_editor.load_video(filepath)

    def open_audio_converter(self, filepaths):
        from .ffmpeg_downloader import check_ffmpeg_available
        is_available, _ = check_ffmpeg_available()
        if not is_available:
            self.pending_files = ("audio_converter", filepaths)
            self._update_tab_buttons(2)
            return
            
        self._update_tab_buttons(2)
        if hasattr(self.tab_audio, 'on_files_dropped'):
            self.tab_audio.on_files_dropped(filepaths)

    def open_image_converter(self, filepaths):
        from .ffmpeg_downloader import check_ffmpeg_available
        is_available, _ = check_ffmpeg_available()
        if not is_available:
            self.pending_files = ("image_converter", filepaths)
            self._update_tab_buttons(3)
            return
            
        self._update_tab_buttons(3)
        if hasattr(self.tab_image, 'on_files_dropped'):
            self.tab_image.on_files_dropped(filepaths)

    def on_ffmpeg_downloaded(self, success):
        if success:
            index = getattr(self, "last_target_index", 0)
            self._update_tab_buttons(index)
            
            # Открываем отложенные файлы, если они есть
            pending = getattr(self, "pending_files", None)
            if pending:
                action, data = pending
                self.pending_files = None
                if action == "video_converter":
                    self.open_video_converter(data)
                elif action == "video_editor":
                    self.open_video_editor(data)
                elif action == "audio_converter":
                    self.open_audio_converter(data)
                elif action == "image_converter":
                    self.open_image_converter(data)

    def update_ui_text(self):
        """Обновляет тексты интерфейса при смене языка"""
        # Обновляем кнопки табов
        self.btn_video.setText(f"🎬 {AppContext.tr('tab_video_converter')}")
        self.btn_editor.setText(f"✂️ {AppContext.tr('tab_video_editor')}")
        self.btn_audio.setText(f"🎵 {AppContext.tr('tab_audio_converter')}")
        self.btn_image.setText(f"🖼️ {AppContext.tr('tab_image_converter')}")

        # Обновляем дочерние компоненты
        for tab in [self.tab_video, self.tab_editor, self.tab_audio, self.tab_image, self.notice_widget]:
            if hasattr(tab, 'update_ui_text'):
                tab.update_ui_text()
