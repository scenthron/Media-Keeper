
import os
import subprocess
import tempfile
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QSlider, QGraphicsView, QGraphicsScene, QGraphicsRectItem, QSpinBox, 
    QDoubleSpinBox, QCheckBox, QLineEdit, QFileDialog, QComboBox, QProgressBar,
    QGraphicsPixmapItem, QStackedWidget, QColorDialog, QScrollArea, QGridLayout,
    QListWidget, QListWidgetItem, QMessageBox
)
from PyQt6.QtCore import Qt, QUrl, QRectF, QPointF, pyqtSignal, QTimer, QSize, QSizeF, QPoint
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QPixmap, QTransform, QMovie, QIcon
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem

from config import AppContext, APP_DESIGN
from logic_paths import get_ffmpeg_exe, get_ffprobe_exe
from .ui_widgets import OutputFolderDropZone, IntegratedDropZone
from ..ui_ffmpeg_notice import FFmpegNoticeWidget
from ..ffmpeg_downloader import check_ffmpeg_available

# Sub-components
from .ui_editor_items import OverlayGraphicsItem, CropHandle
from .ui_editor_widgets import WaveformProgressWidget, MagneticSlider, PlaybackSettingsPopup, CollapsibleSection
from .ui_editor_view import EditorGraphicsView

# Mixins
from .editor_mixins_playback import EditorPlaybackMixin
from .editor_mixins_crop import EditorCropMixin
from .editor_mixins_overlay import EditorOverlayMixin
from .editor_mixins_export import EditorExportMixin

class VideoEditorWidget(QWidget, EditorPlaybackMixin, EditorCropMixin, EditorOverlayMixin, EditorExportMixin):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file = ""
        self.is_video_loaded = False
        self._is_fragment_mode = False
        self.current_rotation = 0
        self.is_flip_h = False
        self.is_flip_v = False
        self.is_cropping = False
        self.is_looping = False
        self._is_preview_mode = False
        self._was_playing_before_scrub = False
        self.playback_rate = 1.0
        self.output_dir = ""
        self.is_audio_only = False

        self.is_crop_locked_size = False    
        self.is_dragging_crop_area = False  
        self.drag_start_pos = QPointF()     
        self.crop_area_start_pos = QPointF() 
        
        self.orig_bitrate = 5000000
        self.cc_brightness = 0.0
        self.cc_contrast = 1.0
        self.cc_saturation = 1.0

        self.overlay_enabled = False
        self.overlay_type = "region" 
        self.overlay_item = None
        self.overlay_image_path = None
        
        self.worker = None
        self.exec_timer = QTimer(self)
        self.exec_timer.setInterval(1000)
        # Ensure the method from mixin is available. Mixin order matters.
        self.exec_timer.timeout.connect(self._update_exec_timer)
        self.start_time = 0
        
        self.ffmpeg_notice = None
        self.content_widget = None
        self._pending_preview_pos = None  

        # Загрузка глобальных иконок плеера
        self.icons_dir = AppContext.find_resource_dir("icons")
        self.icon_play = QIcon(os.path.join(self.icons_dir, "media_play.svg"))
        self.icon_pause = QIcon(os.path.join(self.icons_dir, "media_pause.svg"))
        self.icon_speaker = QIcon(os.path.join(self.icons_dir, "speaker.svg"))
        self.icon_speaker_off = QIcon(os.path.join(self.icons_dir, "speaker_off.svg"))
        self.icon_rotate_left = QIcon(os.path.join(self.icons_dir, "rotate_left.svg"))
        self.icon_rotate_right = QIcon(os.path.join(self.icons_dir, "rotate_right.svg"))
        self.icon_flip_h = QIcon(os.path.join(self.icons_dir, "arrow-dual-horiz.svg"))
        self.icon_lock = QIcon(os.path.join(self.icons_dir, "lock-color.svg"))
        self.icon_skip_forward = QIcon(os.path.join(self.icons_dir, "skip-forward.svg"))
        
        # Иконки для покадровой промотки
        self.icon_prev_frame = QIcon(os.path.join(self.icons_dir, "chevron-first.svg"))
        _pm_next = QIcon(os.path.join(self.icons_dir, "chevron-first.svg")).pixmap(20, 20)
        _img_next = _pm_next.toImage().transformed(QTransform().scale(-1, 1))
        self.icon_next_frame = QIcon(QPixmap.fromImage(_img_next))

        self.init_player()
        
        self.playback_popup = PlaybackSettingsPopup(self.playback_rate, self.is_looping, self)
        self.playback_popup.hide()
        self.playback_popup.settings_changed.connect(self._apply_playback_settings)
        self.playback_popup.closed.connect(self._on_popup_closed)
        
        self._setup_chevron_icons()
        self.init_ui()
        
        self.scrub_timer = QTimer(self)
        self.scrub_timer.setInterval(50)
        self.scrub_timer.setSingleShot(True)
        
        self.preview_timer = QTimer(self)
        self.preview_timer.setInterval(150) 
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self._update_cc_preview)
        
        self.scrub_preview_timer = QTimer(self)
        self.scrub_preview_timer.setInterval(100) 
        self.scrub_preview_timer.setSingleShot(True)
        self.scrub_preview_timer.timeout.connect(self._update_cc_preview)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.is_video_loaded:
            QTimer.singleShot(50, self.center_video)
        else:
            # Force update DropZone position on resize
            if hasattr(self, 'proxy_hint') and self.proxy_hint: 
                 self._center_drop_zone()

    def _center_drop_zone(self):
        """Centers the drop zone widget in the viewport view"""
        if self.view and self.proxy_hint and not self.is_video_loaded:
             # Calculate exact center based on viewport rect mapped to scene
             viewport_rect = self.view.viewport().rect()
             scene_rect_in_view = self.view.mapToScene(viewport_rect).boundingRect()
             
             center_x = scene_rect_in_view.center().x()
             center_y = scene_rect_in_view.center().y()
             
             scale = self.proxy_hint.scale()
             width = self.drop_zone.width() * scale
             height = self.drop_zone.height() * scale
             
             self.proxy_hint.setPos(center_x - width / 2, center_y - height / 2)

    def init_player(self):
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.1)
        
        self.player.positionChanged.connect(self._on_pos_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_state_changed)

    def init_ui(self):
        self.setStyleSheet(f"background-color: {APP_DESIGN['bg_color_main']}; color: {APP_DESIGN['text_color']};")
        self.setMinimumSize(1000, 700)  
        self.setAcceptDrops(True)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        self.stack = QStackedWidget(self)
        main_layout.addWidget(self.stack)
        
        self.ffmpeg_notice = FFmpegNoticeWidget()
        self.ffmpeg_notice.download_finished.connect(self.on_ffmpeg_downloaded)
        self.stack.addWidget(self.ffmpeg_notice)
        
        self.content_widget = QWidget()
        self.content_widget.setAcceptDrops(True)
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # WORKSPACE LAYOUT (Viewer & Playback controls on Left, Inspector on Right)
        workspace_layout = QHBoxLayout()
        workspace_layout.setContentsMargins(10, 10, 10, 10)
        workspace_layout.setSpacing(10)

        # LEFT AREA (Player viewport + timeline + playback controls)
        player_area = QWidget()
        player_area_layout = QVBoxLayout(player_area)
        player_area_layout.setContentsMargins(0, 0, 0, 0)
        player_area_layout.setSpacing(8)

        self.scene = QGraphicsScene(self)
        self.view = EditorGraphicsView(self.scene, editor_widget=self)
        self.view.setAcceptDrops(False)
        self.view.viewport().setAcceptDrops(False)
        
        self.video_item = QGraphicsVideoItem()
        self.scene.addItem(self.video_item)
        self.player.setVideoOutput(self.video_item)
        
        self.preview_item = QGraphicsPixmapItem(self.video_item)
        self.preview_item.setZValue(5) 
        self.preview_item.hide()
        
        self.overlay_item = OverlayGraphicsItem(self.video_item)
        self.overlay_item.hide()
        
        v = self.video_item
        self.crop_dim_top = QGraphicsRectItem(v)
        self.crop_dim_bottom = QGraphicsRectItem(v)
        self.crop_dim_left = QGraphicsRectItem(v)
        self.crop_dim_right = QGraphicsRectItem(v)
        for d in [self.crop_dim_top, self.crop_dim_bottom, self.crop_dim_left, self.crop_dim_right]:
            d.setBrush(QBrush(QColor(0, 0, 0, 150)))
            d.setPen(QPen(Qt.PenStyle.NoPen))
            d.setZValue(10)
            d.hide()
            
        self.handle_tl = CropHandle(v)
        self.handle_br = CropHandle(v)
        self.handle_tl.setZValue(11)
        self.handle_br.setZValue(11)
        self.handle_tl.hide()
        self.handle_br.hide()
        self.handle_tl.handle_moved.connect(self._on_crop_moved)
        self.handle_br.handle_moved.connect(self._on_crop_moved)
        
        self.video_item.nativeSizeChanged.connect(self.center_video)
        
        self.drop_zone = IntegratedDropZone("drop_audio_here")
        self.drop_zone.resize(400, 100) 
        self.proxy_hint = self.scene.addWidget(self.drop_zone)
        self.proxy_hint.setScale(0.5)
        
        player_area_layout.addWidget(self.view, 1)

        # Timeline and control panel directly below the viewport
        player_controls_panel = QFrame()
        player_controls_panel.setStyleSheet("background-color: #2b2b2b; border-radius: 6px;")
        player_controls_vbox = QVBoxLayout(player_controls_panel)
        player_controls_vbox.setContentsMargins(10, 8, 10, 10)
        player_controls_vbox.setSpacing(6)

        self.waveform_progress = WaveformProgressWidget()
        self.waveform_progress.markers_changed.connect(self._on_markers_changed)
        self.waveform_progress.marker_selected.connect(self._on_marker_selected)
        self.waveform_progress.seek_requested.connect(self._on_seek_requested)
        self.waveform_progress.scrub_started.connect(self._on_scrub_started)
        self.waveform_progress.scrub_finished.connect(self._on_scrub_finished)
        player_controls_vbox.addWidget(self.waveform_progress)

        row1 = QHBoxLayout()
        row1.setSpacing(5)

        self.btn_play = QPushButton()
        self.btn_play.setIcon(self.icon_play)
        self.btn_play.setIconSize(QSize(18, 18))
        self.btn_play.setToolTip(AppContext.tr("tooltip_play_pause"))
        
        self.btn_prev_frame = QPushButton()
        self.btn_prev_frame.setIcon(self.icon_prev_frame)
        self.btn_prev_frame.setIconSize(QSize(18, 18))
        self.btn_prev_frame.setToolTip(AppContext.tr("tooltip_prev_frame"))
        
        self.btn_next_frame = QPushButton()
        self.btn_next_frame.setIcon(self.icon_next_frame)
        self.btn_next_frame.setIconSize(QSize(18, 18))
        self.btn_next_frame.setToolTip(AppContext.tr("tooltip_next_frame"))
        
        for b in [self.btn_play, self.btn_prev_frame, self.btn_next_frame]:
            b.setFixedSize(36, 36)
            b.setStyleSheet(self._btn_style())
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            row1.addWidget(b)
        self.btn_play.clicked.connect(self.toggle_play)
 
        self.btn_play_frag = QPushButton()
        self.btn_play_frag.setIcon(self.icon_skip_forward)
        self.btn_play_frag.setIconSize(QSize(14, 14))
        self.btn_play_frag.setText(" " + AppContext.tr("btn_preview_fragment"))
        self.btn_play_frag.setFixedWidth(160)
        self.btn_play_frag.setFixedHeight(36)
        self.btn_play_frag.setStyleSheet(self._btn_style())
        self.btn_play_frag.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_play_frag.setToolTip(AppContext.tr("tooltip_play_frag"))
        self.btn_play_frag.clicked.connect(self.play_preview)
        row1.insertWidget(1, self.btn_play_frag)
        
        self.btn_prev_frame.clicked.connect(lambda: self._step_frame(-1))
        self.btn_next_frame.clicked.connect(lambda: self._step_frame(1))

        row1.addStretch()
        self.lbl_time = QLabel("00:00:00.000 / 00:00:00.000")
        self.lbl_time.setStyleSheet("color: #ccc; font-family: 'Consolas'; font-size: 13px;")
        row1.addWidget(self.lbl_time)
        row1.addStretch()

        self.is_muted = False
        self.saved_volume = 10
        
        self.btn_reset_editor = QPushButton()
        self.btn_reset_editor.setIcon(QIcon(os.path.join(self.icons_dir, "trash-color.svg")))
        self.btn_reset_editor.setIconSize(QSize(14, 14))
        self.btn_reset_editor.setFixedSize(24, 24)
        self.btn_reset_editor.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_editor.setStyleSheet("""
            QPushButton { 
                border: none; 
                background: transparent; 
                padding: 0px; 
            } 
            QPushButton:hover { 
                background-color: #991b1b; 
                border-radius: 4px; 
            }
        """)
        self.btn_reset_editor.setToolTip(AppContext.tr("tooltip_reset_editor"))
        self.btn_reset_editor.clicked.connect(self.reset_editor_to_default)
        row1.addWidget(self.btn_reset_editor)

        row1.addSpacing(15)

        self.btn_mute = QPushButton()
        self.btn_mute.setIcon(self.icon_speaker)
        self.btn_mute.setIconSize(QSize(14, 14))
        self.btn_mute.setFixedSize(24, 24)
        self.btn_mute.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mute.setStyleSheet("QPushButton { border: none; background: transparent; padding: 0px; }")
        self.btn_mute.setToolTip(AppContext.tr("tooltip_mute"))
        self.btn_mute.clicked.connect(self._on_mute_clicked)
        row1.addWidget(self.btn_mute)
        
        self.slider_vol = MagneticSlider(Qt.Orientation.Horizontal)
        self.slider_vol.setRange(0, 100)
        self.slider_vol.setValue(10)
        self.slider_vol.setFixedWidth(60)
        self.slider_vol.setStyleSheet("QSlider { background: transparent; } QSlider::groove:horizontal { background: #333; height: 4px; border-radius: 2px; } QSlider::handle:horizontal { background: #888; width: 10px; height: 10px; margin: -3px 0; border-radius: 5px; } QSlider::sub-page:horizontal { background: #888; border-radius: 2px; }")
        self.slider_vol.valueChanged.connect(self._on_volume_changed)
        row1.addWidget(self.slider_vol)
        
        self.btn_settings = QPushButton()
        self.btn_settings.setIcon(QIcon(os.path.join(self.icons_dir, "gear-color.svg")))
        self.btn_settings.setIconSize(QSize(14, 14))
        self.btn_settings.setFixedSize(24, 24)
        self.btn_settings.setCheckable(True)
        self.btn_settings.setStyleSheet("QPushButton { background: transparent; border: 1px solid #444; border-radius: 4px; padding: 2px; } QPushButton:hover { border-color: #666; background-color: #333; } QPushButton:checked { background-color: #3b82f6; border-color: #3b82f6; }")
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.setToolTip(AppContext.tr("tooltip_settings"))
        self.btn_settings.clicked.connect(self._toggle_settings_popup)
        row1.addWidget(self.btn_settings)

        player_controls_vbox.addLayout(row1)
        player_area_layout.addWidget(player_controls_panel)
        workspace_layout.addWidget(player_area, 1)

        # RIGHT AREA (Inspector panel with collapsible groups)
        self.inspector_panel = QFrame()
        self.inspector_panel.setFixedWidth(300)
        self.inspector_panel.setStyleSheet("background-color: #1a1a1a; border-left: 1px solid #333; border-radius: 6px;")
        inspector_layout = QVBoxLayout(self.inspector_panel)
        inspector_layout.setContentsMargins(5, 5, 5, 5)
        inspector_layout.setSpacing(10)

        # Scroll area for vertical content overflow
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_area.setStyleSheet("QScrollArea { background-color: #1a1a1a; }")
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: #1a1a1a;")
        scroll_content_layout = QVBoxLayout(scroll_content)
        scroll_content_layout.setContentsMargins(0, 0, 5, 0)
        scroll_content_layout.setSpacing(10)
        scroll_content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # SECTION 1: Transform & Crop
        sec_transform = CollapsibleSection(AppContext.tr("section_transform"), self, icon_path=os.path.join(self.icons_dir, "video-editor-transform.svg"), tooltip=AppContext.tr("tooltip_sec_transform"))
        lay_trans = sec_transform.content_layout
        lay_trans.setSpacing(8)

        self.lbl_rot_title = QLabel(AppContext.tr("lbl_rotate_flip"))
        self.lbl_rot_title.setStyleSheet("border: none; background: transparent; color: #aaa; font-size: 11px; font-weight: bold;")
        lay_trans.addWidget(self.lbl_rot_title)

        row_rot = QHBoxLayout()
        row_rot.setSpacing(5)

        _icon_btn_size = QSize(20, 20)
        _btn_w, _btn_h = 54, 36

        self.btn_rot_ccw = QPushButton()
        self.btn_rot_ccw.setIcon(self.icon_rotate_left)
        self.btn_rot_ccw.setIconSize(_icon_btn_size)
        self.btn_rot_ccw.setToolTip(AppContext.tr("btn_rotate_ccw"))

        self.btn_rot_cw = QPushButton()
        self.btn_rot_cw.setIcon(self.icon_rotate_right)
        self.btn_rot_cw.setIconSize(_icon_btn_size)
        self.btn_rot_cw.setToolTip(AppContext.tr("btn_rotate_cw"))

        self.btn_flip_h = QPushButton()
        self.btn_flip_h.setIcon(self.icon_flip_h)
        self.btn_flip_h.setIconSize(_icon_btn_size)
        self.btn_flip_h.setToolTip(AppContext.tr("btn_flip_h"))

        self.btn_flip_v = QPushButton()
        # Иконка та же, но нарисованная с поворотом через QTransform
        _pm_flip_v = QIcon(os.path.join(self.icons_dir, "arrow-dual-horiz.svg")).pixmap(20, 20)
        _img_flip_v = _pm_flip_v.toImage()
        _img_flip_v = _img_flip_v.transformed(QTransform().rotate(90))
        self.btn_flip_v.setIcon(QIcon(QPixmap.fromImage(_img_flip_v)))
        self.btn_flip_v.setIconSize(_icon_btn_size)
        self.btn_flip_v.setToolTip(AppContext.tr("btn_flip_v"))

        for b in [self.btn_rot_ccw, self.btn_rot_cw, self.btn_flip_h, self.btn_flip_v]:
            b.setFixedSize(_btn_w, _btn_h)
            b.setStyleSheet(self._btn_style())
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            row_rot.addWidget(b)
        row_rot.addStretch()
        self.btn_rot_ccw.clicked.connect(lambda: self._rotate(-90))
        self.btn_rot_cw.clicked.connect(lambda: self._rotate(90))
        self.btn_flip_h.clicked.connect(lambda: self._flip('h'))
        self.btn_flip_v.clicked.connect(lambda: self._flip('v'))
        lay_trans.addLayout(row_rot)

        self.btn_remove_audio = QPushButton()
        self.btn_remove_audio.setIcon(self.icon_speaker_off_white)
        self.btn_remove_audio.setIconSize(QSize(16, 16))
        self.btn_remove_audio.setText(" " + AppContext.tr("chk_mute_audio"))
        self.btn_remove_audio.setCheckable(True)
        self.btn_remove_audio.setFixedHeight(30)
        self.btn_remove_audio.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove_audio.setStyleSheet("QPushButton { background: #333; border: 1px solid #444; border-radius: 4px; color: #aaa; font-size: 12px; font-weight: bold; } QPushButton:hover { background: #444; color: white; border-color: #666; } QPushButton:checked { background-color: #ef4444; color: black; border-color: #ef4444; }")
        self.btn_remove_audio.setToolTip(AppContext.tr("tooltip_remove_audio"))
        self.btn_remove_audio.toggled.connect(
            lambda checked: self.btn_remove_audio.setIcon(
                self.icon_speaker_off_black if checked else self.icon_speaker_off_white
            )
        )
        lay_trans.addWidget(self.btn_remove_audio)

        lay_trans.addSpacing(5)
        self.btn_crop = QPushButton(AppContext.tr("btn_crop"))
        self.btn_crop.setCheckable(True)
        self.btn_crop.setFixedHeight(32)
        self.btn_crop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_crop.setStyleSheet(self._btn_style() + "font-size: 12px;")
        self.btn_crop.setToolTip(AppContext.tr("tooltip_crop"))
        self.btn_crop.clicked.connect(self.toggle_crop_mode)
        lay_trans.addWidget(self.btn_crop)

        # --- Контейнер для полей кропа и замка (скрыт по умолчанию) ---
        self.widget_crop_controls = QWidget()
        lay_crop_ctrls = QVBoxLayout(self.widget_crop_controls)
        lay_crop_ctrls.setContentsMargins(0, 0, 0, 0)
        lay_crop_ctrls.setSpacing(6)

        # --- Координатная сетка кропа ---
        grid_crop = QGridLayout()
        grid_crop.setSpacing(6)
        grid_crop.setColumnStretch(0, 1)
        grid_crop.setColumnStretch(1, 1)

        _coord_spin_style = (
            "QSpinBox {"
            "  background: #1e1e2e;"
            "  color: #a0f0a0;"
            "  border: 1px solid #3a3a5a;"
            "  border-radius: 6px;"
            "  font-size: 12px;"
            "  font-weight: bold;"
            "  padding: 2px 2px 2px 6px;"
            "}"
            "QSpinBox:disabled { color: #4a5a4a; border-color: #2a2a3a; }"
            "QSpinBox:focus { border-color: #4ade80; }"
            "QSpinBox::up-button, QSpinBox::down-button {"
            "  width: 18px;"
            "  background: #2a2a3e;"
            "  border: none;"
            "}"
            "QSpinBox::up-button { border-top-right-radius: 5px; }"
            "QSpinBox::down-button { border-bottom-right-radius: 5px; }"
            "QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: #3a3a5a; }"
            f"QSpinBox::up-arrow {{ image: url('{self.chevron_paths['up_active']}'); width: 10px; height: 10px; }}"
            f"QSpinBox::down-arrow {{ image: url('{self.chevron_paths['down_active']}'); width: 10px; height: 10px; }}"
            f"QSpinBox::up-arrow:disabled {{ image: url('{self.chevron_paths['up_disabled']}'); }}"
            f"QSpinBox::down-arrow:disabled {{ image: url('{self.chevron_paths['down_disabled']}'); }}"
        )

        self.spin_crop_x = self._create_coord_spin("X")
        self.spin_crop_y = self._create_coord_spin("Y")
        self.spin_crop_w = self._create_coord_spin("W")
        self.spin_crop_h = self._create_coord_spin("H")
        self.crop_spins = [self.spin_crop_x, self.spin_crop_y, self.spin_crop_w, self.spin_crop_h]
        for idx, s in enumerate(self.crop_spins):
            s.setFixedHeight(34)
            s.setStyleSheet(_coord_spin_style)
            grid_crop.addWidget(s, idx // 2, idx % 2)
            s.valueChanged.connect(self._on_crop_spin_changed)
            s.setEnabled(False)
        lay_crop_ctrls.addLayout(grid_crop)

        # --- Строка: замок + размер выделения ---
        row_crop_lock = QHBoxLayout()
        row_crop_lock.setSpacing(6)

        self.btn_crop_lock_size = QPushButton()
        self.btn_crop_lock_size.setCheckable(True)
        self.btn_crop_lock_size.setIcon(self.icon_lock)
        self.btn_crop_lock_size.setIconSize(QSize(16, 16))
        self.btn_crop_lock_size.setToolTip(AppContext.tr("tooltip_crop_lock"))
        self.btn_crop_lock_size.setFixedSize(32, 32)
        self.btn_crop_lock_size.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_crop_lock_size.setStyleSheet(
            "QPushButton { background: #2a2a3e; border: 1px solid #3a3a5a; border-radius: 6px; }"
            "QPushButton:hover { background: #3a3a5a; border-color: #4ade80; }"
            "QPushButton:checked { background: #7f1d1d; border-color: #ef4444; }"
            "QPushButton:disabled { opacity: 0.4; }"
        )
        self.btn_crop_lock_size.setEnabled(False)
        self.btn_crop_lock_size.clicked.connect(self._toggle_crop_lock_size)
        row_crop_lock.addWidget(self.btn_crop_lock_size)

        self.lbl_crop_size = QLabel("")
        self.lbl_crop_size.setStyleSheet(
            "color: #4ade80; font-size: 11px; font-weight: bold; font-family: 'Consolas';"
        )
        row_crop_lock.addWidget(self.lbl_crop_size)
        row_crop_lock.addStretch()
        lay_crop_ctrls.addLayout(row_crop_lock)

        lay_trans.addWidget(self.widget_crop_controls)
        self.widget_crop_controls.hide()

        scroll_content_layout.addWidget(sec_transform)

        # SECTION 2: Color Correction
        sec_color = CollapsibleSection(AppContext.tr("section_color"), self, icon_path=os.path.join(self.icons_dir, "video-editor-color.svg"), tooltip=AppContext.tr("tooltip_sec_color"))
        lay_color = sec_color.content_layout
        lay_color.setSpacing(8)

        row_cc_warn = QHBoxLayout()
        row_cc_warn.setSpacing(5)
        lbl_warn = QLabel("⚠️")
        lbl_warn.setToolTip(AppContext.tr("color_correction_warning"))
        lbl_warn.setStyleSheet("color: #f59e0b; font-size: 16px; border: none; background: transparent;") 
        lbl_warn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_warn_text = QLabel(AppContext.tr("lbl_rendering_required"))
        self.lbl_warn_text.setStyleSheet("color: #eee; font-size: 12px; font-weight: bold; border: none; background: transparent;")
        row_cc_warn.addWidget(lbl_warn)
        row_cc_warn.addWidget(self.lbl_warn_text)
        row_cc_warn.addStretch()
        lay_color.addLayout(row_cc_warn)

        self.cc_controls = [] 
        self.cc_dragging = False

        def create_cc_slider(label, min_val, max_val, default):
            vbox = QVBoxLayout()
            vbox.setSpacing(4)
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 12px; color: #eee; font-weight: bold;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
            hbox = QHBoxLayout()
            hbox.setSpacing(6)
            spin = QDoubleSpinBox()
            spin.setRange(min_val, max_val)
            spin.setValue(default)
            spin.setSingleStep(0.05)
            spin.setDecimals(2)
            spin.setFixedHeight(34)
            spin.setMinimumWidth(75)
            
            _cc_spin_style = (
                "QDoubleSpinBox {"
                "  background: #1e1e2e;"
                "  color: #a0f0a0;"
                "  border: 1px solid #3a3a5a;"
                "  border-radius: 6px;"
                "  font-size: 12px;"
                "  font-weight: bold;"
                "  padding: 2px 2px 2px 6px;"
                "}"
                "QDoubleSpinBox:disabled { color: #4a5a4a; border-color: #2a2a3a; }"
                "QDoubleSpinBox:focus { border-color: #4ade80; }"
                "QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {"
                "  width: 18px;"
                "  background: #2a2a3e;"
                "  border: none;"
                "}"
                "QDoubleSpinBox::up-button { border-top-right-radius: 5px; }"
                "QDoubleSpinBox::down-button { border-bottom-right-radius: 5px; }"
                "QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover { background: #3a3a5a; }"
                f"QDoubleSpinBox::up-arrow {{ image: url('{self.chevron_paths['up_active']}'); width: 10px; height: 10px; }}"
                f"QDoubleSpinBox::down-arrow {{ image: url('{self.chevron_paths['down_active']}'); width: 10px; height: 10px; }}"
                f"QDoubleSpinBox::up-arrow:disabled {{ image: url('{self.chevron_paths['up_disabled']}'); }}"
                f"QDoubleSpinBox::down-arrow:disabled {{ image: url('{self.chevron_paths['down_disabled']}'); }}"
            )
            spin.setStyleSheet(_cc_spin_style)
            spin.setToolTip(AppContext.tr("tooltip_cc_spin").format(label))

            s_min = int(min_val * 100)
            s_max = int(max_val * 100)
            s_def = int(default * 100)
            slider = MagneticSlider(Qt.Orientation.Horizontal, snap_values=[s_def])
            slider.setRange(s_min, s_max)
            slider.setValue(s_def)
            slider.setFixedWidth(110)
            slider.setTickPosition(QSlider.TickPosition.TicksBelow)
            slider.setStyleSheet(f"QSlider::groove:horizontal {{ height: 4px; background: #444; margin: 4px 0; }} QSlider::handle:horizontal {{ width: 10px; height: 10px; background: {APP_DESIGN['accent_color']}; margin: -3px 0; border-radius: 5px; }} QSlider::groove:horizontal:disabled {{ background: #2a2a2a; }} QSlider::handle:horizontal:disabled {{ background: #555; }}")
            slider.setToolTip(AppContext.tr("tooltip_cc_slider").format(label))

            btn_reset = QPushButton("0")
            btn_reset.setToolTip(AppContext.tr("tooltip_cc_reset").format(label))
            btn_reset.setFixedSize(26, 26)
            btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_reset.setStyleSheet(self._btn_style() + "font-size: 11px; padding: 0;")
            slider._is_updating = False
            def on_slider(val):
                if slider._is_updating: return
                slider._is_updating = True
                spin.setValue(val / 100.0)
                slider._is_updating = False
            def on_spin(val):
                if slider._is_updating: return
                slider._is_updating = True
                slider.setValue(int(val * 100))
                slider.valueChanged.emit(int(val * 100))
                slider._is_updating = False
                self._schedule_cc_preview()
            def on_reset():
                if slider._is_updating: return
                slider._is_updating = True
                spin.setValue(default)
                slider.setValue(s_def)
                slider.valueChanged.emit(s_def)
                slider._is_updating = False
                self._schedule_cc_preview()
            slider.valueChanged.connect(on_slider)
            spin.valueChanged.connect(on_spin)
            btn_reset.clicked.connect(on_reset)
            hbox.addWidget(spin)
            hbox.addWidget(slider)
            hbox.addWidget(btn_reset)
            vbox.addWidget(lbl)
            vbox.addLayout(hbox)
            self.cc_controls.extend([spin, slider, btn_reset])
            return vbox, slider, spin, btn_reset

        self.lay_bright, self.slider_bright, self.spin_bright, self.btn_reset_bright = create_cc_slider(AppContext.tr("slider_brightness"), -1.0, 1.0, 0.0)
        self.lay_contrast, self.slider_contrast, self.spin_contrast, self.btn_reset_contrast = create_cc_slider(AppContext.tr("slider_contrast"), 0.0, 2.0, 1.0)
        self.lay_sat, self.slider_sat, self.spin_sat, self.btn_reset_sat = create_cc_slider(AppContext.tr("slider_saturation"), 0.0, 3.0, 1.0)
        
        self.slider_bright.valueChanged.connect(self._on_cc_changed)
        self.slider_contrast.valueChanged.connect(self._on_cc_changed)
        self.slider_sat.valueChanged.connect(self._on_cc_changed)
        self.slider_bright.valueChanged.connect(self._schedule_cc_preview)
        self.slider_contrast.valueChanged.connect(self._schedule_cc_preview)
        self.slider_sat.valueChanged.connect(self._schedule_cc_preview)
        
        lay_color.addLayout(self.lay_bright)
        lay_color.addLayout(self.lay_contrast)
        lay_color.addLayout(self.lay_sat)

        scroll_content_layout.addWidget(sec_color)

        # SECTION 3: Overlay / Watermark
        sec_overlay = CollapsibleSection(AppContext.tr("section_overlay"), self, icon_path=os.path.join(self.icons_dir, "video-editor-overlay.svg"), tooltip=AppContext.tr("tooltip_sec_overlay"))
        lay_overlay = sec_overlay.content_layout
        lay_overlay.setSpacing(8)

        self.chk_overlay_enable = QCheckBox(AppContext.tr("ovl_enable"))
        self.chk_overlay_enable.setStyleSheet(f"QCheckBox {{ border: none; background: transparent; color: #eee; font-size: 12px; font-weight: bold; }} QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid #555; background: #333; border-radius: 3px; }} QCheckBox::indicator:checked {{ background-color: {APP_DESIGN['accent_color']}; border-color: {APP_DESIGN['accent_color']}; }} QCheckBox:disabled {{ color: #555; }}")
        self.chk_overlay_enable.toggled.connect(self._on_overlay_toggled)
        self.chk_overlay_enable.setEnabled(False)
        self.chk_overlay_enable.setToolTip(AppContext.tr("tooltip_overlay_enable"))
        lay_overlay.addWidget(self.chk_overlay_enable)

        row_opacity = QHBoxLayout()
        row_opacity.setSpacing(5)
        self.lbl_overlay_val = QLabel(AppContext.tr("ovl_opacity"))
        self.lbl_overlay_val.setStyleSheet("font-size: 12px; color: #eee; font-weight: bold; border: none; background: transparent;")
        row_opacity.addWidget(self.lbl_overlay_val)

        self.slider_overlay_val = MagneticSlider(Qt.Orientation.Horizontal, snap_values=[])
        self.slider_overlay_val.setRange(0, 100)
        self.slider_overlay_val.setValue(100)
        self.slider_overlay_val.setFixedWidth(100)
        self.slider_overlay_val.setStyleSheet("QSlider { border: none; background: transparent; height: 20px; } QSlider::groove:horizontal { border: none; height: 4px; background: #444; border-radius: 2px; } QSlider::handle:horizontal { border: none; width: 10px; height: 10px; background: #3b82f6; margin: -3px 0; border-radius: 5px; } QSlider::sub-page:horizontal { border: none; background: #3b82f6; border-radius: 2px; } QSlider::add-page:horizontal { border: none; background: #444; border-radius: 2px; }")
        self.slider_overlay_val.setEnabled(False)
        self.slider_overlay_val.setToolTip("Регулировка прозрачности или силы размытия наложения")
        row_opacity.addWidget(self.slider_overlay_val)

        self.spin_overlay_val = QSpinBox()
        self.spin_overlay_val.setRange(0, 100)
        self.spin_overlay_val.setValue(100)
        self.spin_overlay_val.setFixedHeight(34)
        self.spin_overlay_val.setMinimumWidth(75)
        _overlay_spin_style = (
            "QSpinBox {"
            "  background: #1e1e2e;"
            "  color: #a0f0a0;"
            "  border: 1px solid #3a3a5a;"
            "  border-radius: 6px;"
            "  font-size: 12px;"
            "  font-weight: bold;"
            "  padding: 2px 2px 2px 6px;"
            "}"
            "QSpinBox:disabled { color: #4a5a4a; border-color: #2a2a3a; background: #1a1a1a; }"
            "QSpinBox:focus { border-color: #4ade80; }"
            "QSpinBox::up-button, QSpinBox::down-button {"
            "  width: 18px;"
            "  background: #2a2a3e;"
            "  border: none;"
            "}"
            "QSpinBox::up-button { border-top-right-radius: 5px; }"
            "QSpinBox::down-button { border-bottom-right-radius: 5px; }"
            "QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: #3a3a5a; }"
            f"QSpinBox::up-arrow {{ image: url('{self.chevron_paths['up_active']}'); width: 10px; height: 10px; }}"
            f"QSpinBox::down-arrow {{ image: url('{self.chevron_paths['down_active']}'); width: 10px; height: 10px; }}"
            f"QSpinBox::up-arrow:disabled {{ image: url('{self.chevron_paths['up_disabled']}'); }}"
            f"QSpinBox::down-arrow:disabled {{ image: url('{self.chevron_paths['down_disabled']}'); }}"
        )
        self.spin_overlay_val.setStyleSheet(_overlay_spin_style)
        self.spin_overlay_val.setEnabled(False)
        self.spin_overlay_val.setToolTip("Точное значение интенсивности или прозрачности наложения в процентах")
        row_opacity.addWidget(self.spin_overlay_val)
        lay_overlay.addLayout(row_opacity)

        self.slider_overlay_val.valueChanged.connect(self.spin_overlay_val.setValue)
        self.spin_overlay_val.valueChanged.connect(self.slider_overlay_val.setValue)
        self.slider_overlay_val.valueChanged.connect(self._on_overlay_val_changed)

        self.combo_overlay_type = QComboBox()
        self.combo_overlay_type.addItems([AppContext.tr("ovl_type_img"), AppContext.tr("ovl_type_region"), AppContext.tr("ovl_type_blur")])
        self.combo_overlay_type.setStyleSheet(APP_DESIGN['nativelike_combo'])
        self.combo_overlay_type.setFixedHeight(30)
        self.combo_overlay_type.currentIndexChanged.connect(self._on_overlay_type_changed)
        self.combo_overlay_type.setEnabled(False)
        self.combo_overlay_type.setToolTip("Выберите тип наложения: Рисунок (картинка), Цветокоррекция (плашка цвета) или Размытие")
        lay_overlay.addWidget(self.combo_overlay_type)

        # Replacement container instead of QStackedWidget for image overlay
        self.widget_overlay_img = QWidget()
        self.widget_overlay_img.setStyleSheet("background: transparent; border: none; margin: 0; padding: 0;")
        pg_img_l = QHBoxLayout(self.widget_overlay_img)
        pg_img_l.setContentsMargins(0, 0, 0, 0)
        pg_img_l.setSpacing(5)
        self.btn_overlay_select_img = QPushButton(AppContext.tr("ovl_btn_select"))
        self.btn_overlay_select_img.clicked.connect(self._select_overlay_image)
        self.btn_overlay_select_img.setStyleSheet("QPushButton { background: #333; border: 1px solid #444; color: white; border-radius: 4px; padding: 4px; font-size: 11px; } QPushButton:hover { background: #444; }")
        self.btn_overlay_select_img.setToolTip("Выбрать графический файл (PNG/JPG/GIF) для наложения на видео")
        self.lbl_overlay_img_name = QLabel("")
        self.lbl_overlay_img_name.setStyleSheet("color: #aaa; font-size: 10px;")
        self.btn_overlay_img_del = QPushButton("×")
        self.btn_overlay_img_del.setFixedSize(20, 20)
        self.btn_overlay_img_del.clicked.connect(self._clear_overlay_image)
        self.btn_overlay_img_del.setStyleSheet("QPushButton { background: #dc2626; color: white; border-radius: 3px; font-weight: bold; } QPushButton:hover { background: #b91c1c; }")
        self.btn_overlay_img_del.setToolTip("Удалить выбранное изображение")
        self.btn_overlay_img_del.hide()
        self.btn_overlay_img_reset = QPushButton("↺")
        self.btn_overlay_img_reset.setFixedSize(20, 20)
        self.btn_overlay_img_reset.clicked.connect(self._on_reset_overlay_size)
        self.btn_overlay_img_reset.setStyleSheet("QPushButton { background: #333; color: white; border-radius: 3px; } QPushButton:hover { background: #444; }")
        self.btn_overlay_img_reset.setToolTip("Сбросить размер")
        self.btn_overlay_img_reset.hide()
        pg_img_l.addWidget(self.btn_overlay_select_img)
        pg_img_l.addWidget(self.lbl_overlay_img_name)
        pg_img_l.addWidget(self.btn_overlay_img_del)
        pg_img_l.addWidget(self.btn_overlay_img_reset)
        lay_overlay.addWidget(self.widget_overlay_img)

        # Replacement container instead of QStackedWidget for region overlay
        self.widget_overlay_reg = QWidget()
        self.widget_overlay_reg.setStyleSheet("background: transparent; border: none; margin: 0; padding: 0;")
        pg_reg_l = QHBoxLayout(self.widget_overlay_reg)
        pg_reg_l.setContentsMargins(0, 0, 0, 0)
        pg_reg_l.setSpacing(5)
        self.btn_overlay_color = QPushButton()
        self.btn_overlay_color.setFixedSize(40, 20)
        self.btn_overlay_color.setStyleSheet("background: #ff0000; border: 1px solid #888; border-radius: 3px;")
        self.btn_overlay_color.clicked.connect(self._pick_overlay_color)
        self.btn_overlay_color.setToolTip("Выбрать цвет заливки для плашки")
        lbl_color = QLabel(AppContext.tr("ovl_lbl_color"))
        lbl_color.setStyleSheet("font-size: 11px; color: #ccc; border: none; background: transparent;")
        pg_reg_l.addWidget(lbl_color)
        pg_reg_l.addWidget(self.btn_overlay_color)
        pg_reg_l.addStretch()
        lay_overlay.addWidget(self.widget_overlay_reg)

        self.widget_overlay_img.hide()
        self.widget_overlay_reg.hide()

        scroll_content_layout.addWidget(sec_overlay)

        # SECTION 4: Markers & Segments
        sec_markers = CollapsibleSection(AppContext.tr("section_markers"), self, icon_path=os.path.join(self.icons_dir, "video-editor-marker.svg"), tooltip=AppContext.tr("tooltip_sec_markers"))
        lay_markers = sec_markers.content_layout
        lay_markers.setSpacing(4)
        lay_markers.setContentsMargins(6, 6, 6, 6)

        row_marker_add = QHBoxLayout()
        row_marker_add.setSpacing(4)
        row_marker_add.setContentsMargins(0, 0, 0, 0)
        self.edit_marker_time = QLineEdit(AppContext.tr("marker_time_format"))
        self.edit_marker_time.setInputMask("99:99:99.999")
        self.edit_marker_time.setFixedHeight(28)
        self.edit_marker_time.setStyleSheet(APP_DESIGN['nativelike_input'] + "font-family: monospace; font-size: 11px; color: #ffffff;")
        self.edit_marker_time.editingFinished.connect(self._on_marker_edit_finished)
        self.edit_marker_time.setToolTip(AppContext.tr("tooltip_marker_time"))
        row_marker_add.addWidget(self.edit_marker_time, 1)

        self.btn_add_marker = QPushButton()
        self.btn_add_marker.setIcon(QIcon(os.path.join(self.icons_dir, "scissors.svg")))
        self.btn_add_marker.setIconSize(QSize(14, 14))
        self.btn_add_marker.setText(" " + AppContext.tr("btn_add_marker_text"))
        self.btn_add_marker.setFixedHeight(28)
        self.btn_add_marker.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_marker.setStyleSheet("QPushButton { background: #2563eb; color: white; border: 1px solid #1d4ed8; border-radius: 4px; font-weight: bold; font-size: 11px; padding: 0 10px; } QPushButton:hover { background: #3b82f6; } QPushButton:pressed { background: #1d4ed8; }")
        self.btn_add_marker.clicked.connect(self._add_marker_at_pos)
        self.btn_add_marker.setToolTip(AppContext.tr("tooltip_add_marker_btn"))
        row_marker_add.addWidget(self.btn_add_marker)

        self.btn_delete_marker = QPushButton()
        self.btn_delete_marker.setIcon(QIcon(os.path.join(self.icons_dir, "cross.svg")))
        self.btn_delete_marker.setIconSize(QSize(10, 10))
        self.btn_delete_marker.setFixedSize(28, 28)
        self.btn_delete_marker.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete_marker.setStyleSheet(
            "QPushButton { background: #333; border: 1px solid #444; border-radius: 4px; }"
            "QPushButton:hover { background: #991b1b; border-color: #ef4444; }"
            "QPushButton:pressed { background: #7f1d1d; }"
            "QPushButton:disabled { opacity: 0.4; background: #222; border-color: #333; }"
        )
        self.btn_delete_marker.setToolTip(AppContext.tr("tooltip_delete_marker"))
        self.btn_delete_marker.setEnabled(False)
        self.btn_delete_marker.clicked.connect(self._delete_selected_marker)
        row_marker_add.addWidget(self.btn_delete_marker)

        lay_markers.addLayout(row_marker_add)

        # --- Список добавленных маркеров (высота под 5 элементов) ---
        self.list_markers = QListWidget()
        self.list_markers.setFixedHeight(110)
        self.list_markers.setStyleSheet("QListWidget { background: #1e1e2e; color: #a0f0a0; border: 1px solid #3a3a5a; border-radius: 6px; font-family: monospace; font-size: 11px; } QListWidget::item { padding: 2px; } QListWidget::item:selected { background: #3b82f6; color: white; }")
        self.list_markers.itemClicked.connect(self._on_list_marker_clicked)
        self.list_markers.setToolTip(AppContext.tr("tooltip_list_markers"))
        lay_markers.addWidget(self.list_markers)

        self.lbl_marker_info = QLabel(AppContext.tr("lbl_markers_title"))
        self.lbl_marker_info.setStyleSheet("color: #eee; font-size: 12px; font-weight: bold; border: none; background: transparent; margin: 0; padding: 0; margin-top: 2px;")
        lay_markers.addWidget(self.lbl_marker_info)

        row_marker_action = QHBoxLayout()
        row_marker_action.setSpacing(4)
        row_marker_action.setContentsMargins(0, 0, 0, 0)
        self.btn_invert = QPushButton(" " + AppContext.tr("btn_invert_markers_text"))
        self.btn_invert.setFixedHeight(28)
        self.btn_invert.setStyleSheet(self._btn_style() + "font-size: 11px;")
        self.btn_invert.clicked.connect(self.waveform_progress.toggle_inversion)
        self.btn_invert.setToolTip(AppContext.tr("tooltip_invert_markers"))
        row_marker_action.addWidget(self.btn_invert, 1)

        self.btn_clear_markers = QPushButton()
        self.btn_clear_markers.setIcon(QIcon(os.path.join(self.icons_dir, "trash-color.svg")))
        self.btn_clear_markers.setIconSize(QSize(14, 14))
        self.btn_clear_markers.setText(" " + AppContext.tr("btn_clear_markers_text"))
        self.btn_clear_markers.setFixedHeight(28)
        self.btn_clear_markers.setStyleSheet(
            "QPushButton { background: #333; border: 1px solid #555; color: #ccc; border-radius: 4px; font-weight: bold; font-size: 11px; }"
            "QPushButton:hover { background: #991b1b; color: white; border-color: #ef4444; }"
            "QPushButton:pressed { background: #7f1d1d; }"
        )
        self.btn_clear_markers.clicked.connect(self.waveform_progress.clear_markers)
        self.btn_clear_markers.setToolTip(AppContext.tr("tooltip_clear_markers"))
        row_marker_action.addWidget(self.btn_clear_markers, 1)
        lay_markers.addLayout(row_marker_action)

        self.btn_split_video = QPushButton()
        self.btn_split_video.setIcon(QIcon(os.path.join(self.icons_dir, "cubes-color-next.svg")))
        self.btn_split_video.setIconSize(QSize(14, 14))
        self.btn_split_video.setText(" " + AppContext.tr("btn_split_video"))
        self.btn_split_video.setCheckable(True)
        self.btn_split_video.setFixedHeight(30)
        self.btn_split_video.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_split_video.setStyleSheet("QPushButton { background: #333; border: 1px solid #444; border-radius: 4px; color: #aaa; font-size: 11px; font-weight: bold; } QPushButton:hover { background: #444; color: white; border-color: #666; } QPushButton:checked { background-color: #3b82f6; color: white; border-color: #3b82f6; }")
        self.btn_split_video.setToolTip(AppContext.tr("tooltip_split_video"))
        lay_markers.addWidget(self.btn_split_video)

        self.lbl_frag_info = QLabel("")
        self.lbl_frag_info.setStyleSheet("font-family: monospace; font-size: 11px; color: #4ade80; font-weight: bold; margin-top: 2px;")
        lay_markers.addWidget(self.lbl_frag_info)

        scroll_content_layout.addWidget(sec_markers)

        # SECTION 5: Encoding settings
        sec_encoding = CollapsibleSection(AppContext.tr("section_encoding"), self, icon_path=os.path.join(self.icons_dir, "gear-color.svg"), tooltip=AppContext.tr("tooltip_sec_encoding"))
        lay_encode = sec_encoding.content_layout
        lay_encode.setSpacing(8)

        self.lbl_codec = QLabel(AppContext.tr("lbl_video_codec"))
        self.lbl_codec.setStyleSheet("border: none; background: transparent; font-size: 11px; color: #ccc; font-weight: bold;")
        self.lbl_codec.setToolTip(AppContext.tr("tooltip_video_codec"))
        lay_encode.addWidget(self.lbl_codec)
        
        self.combo_video_codec = QComboBox()
        self.combo_video_codec.addItem("H.264 (AVC)", "libx264")
        self.combo_video_codec.addItem("H.265 (HEVC)", "libx265")
        self.combo_video_codec.setStyleSheet(APP_DESIGN['nativelike_combo'])
        self.combo_video_codec.setFixedHeight(26)
        self.combo_video_codec.setToolTip(AppContext.tr("tooltip_video_codec_desc"))
        lay_encode.addWidget(self.combo_video_codec)

        self.lbl_quality = QLabel(AppContext.tr("lbl_video_quality"))
        self.lbl_quality.setStyleSheet("border: none; background: transparent; font-size: 11px; color: #ccc; font-weight: bold;")
        self.lbl_quality.setToolTip(AppContext.tr("tooltip_video_quality"))
        lay_encode.addWidget(self.lbl_quality)
        
        self.combo_video_quality = QComboBox()
        self.combo_video_quality.addItem(AppContext.tr("combo_quality_high"), 17)
        self.combo_video_quality.addItem(AppContext.tr("combo_quality_medium"), 23)
        self.combo_video_quality.addItem(AppContext.tr("combo_quality_low"), 28)
        self.combo_video_quality.setCurrentIndex(0)
        self.combo_video_quality.setStyleSheet(APP_DESIGN['nativelike_combo'])
        self.combo_video_quality.setFixedHeight(26)
        self.combo_video_quality.setToolTip(AppContext.tr("tooltip_video_quality_desc"))
        lay_encode.addWidget(self.combo_video_quality)

        self.lbl_preset = QLabel(AppContext.tr("lbl_preset_speed"))
        self.lbl_preset.setStyleSheet("border: none; background: transparent; font-size: 11px; color: #ccc; font-weight: bold;")
        self.lbl_preset.setToolTip(AppContext.tr("tooltip_preset_speed"))
        lay_encode.addWidget(self.lbl_preset)
        
        self.combo_video_preset = QComboBox()
        self.combo_video_preset.addItems(["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"])
        self.combo_video_preset.setCurrentText("medium")
        self.combo_video_preset.setStyleSheet(APP_DESIGN['nativelike_combo'])
        self.combo_video_preset.setFixedHeight(26)
        self.combo_video_preset.setToolTip(AppContext.tr("tooltip_preset_desc"))
        lay_encode.addWidget(self.combo_video_preset)

        scroll_content_layout.addWidget(sec_encoding)
        scroll_content_layout.addStretch(1)

        # Expand only the transform block by default for clean UX
        self.sec_transform = sec_transform
        self.sec_color = sec_color
        self.sec_overlay = sec_overlay
        self.sec_markers = sec_markers
        self.sec_encoding = sec_encoding

        self.sec_transform.set_expanded(True)
        self.sec_color.set_expanded(False)
        self.sec_overlay.set_expanded(False)
        self.sec_markers.set_expanded(False)
        self.sec_encoding.set_expanded(False)

        scroll_area.setWidget(scroll_content)
        inspector_layout.addWidget(scroll_area)
        workspace_layout.addWidget(self.inspector_panel)
        content_layout.addLayout(workspace_layout, 1)

        # FOOTER EXPORT PANEL (Export options + progress + Process processing button)
        self.footer_panel = QFrame()
        self.footer_panel.setStyleSheet("QFrame { background-color: #2b2b2b; border-top: 1px solid #333; }")
        footer_layout = QHBoxLayout(self.footer_panel)
        footer_layout.setContentsMargins(15, 10, 15, 10)
        footer_layout.setSpacing(15)

        # Left Column: Naming settings
        rename_layout = QVBoxLayout()
        rename_layout.setSpacing(4)
        row_rename = QHBoxLayout()
        row_rename.setSpacing(8)
        self.chk_rename = QCheckBox(AppContext.tr("chk_rename"))
        self.chk_rename.setChecked(True)
        self.chk_rename.setStyleSheet(f"QCheckBox {{ background-color: transparent; color: #eee; spacing: 5px; font-size: 12px; font-weight: bold; }} QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid #555; border-radius: 3px; background: #333; }} QCheckBox::indicator:checked {{ background-color: {APP_DESIGN['accent_color']}; border-color: {APP_DESIGN['accent_color']}; }}")
        row_rename.addWidget(self.chk_rename)
        
        self.combo_naming = QComboBox()
        self.combo_naming.addItems([AppContext.tr("combo_naming_prefix"), AppContext.tr("combo_naming_postfix")])
        self.combo_naming.setCurrentIndex(1)
        self.combo_naming.setFixedWidth(100)
        self.combo_naming.setStyleSheet(APP_DESIGN['nativelike_combo'])
        row_rename.addWidget(self.combo_naming)
        
        self.inp_naming = QLineEdit(AppContext.tr("inp_naming_template"))
        self.inp_naming.setFixedWidth(130)
        self.inp_naming.setStyleSheet(APP_DESIGN['nativelike_input'])
        row_rename.addWidget(self.inp_naming)
        rename_layout.addLayout(row_rename)
        
        self.lbl_naming_preview = QLabel(AppContext.tr("lbl_naming_preview"))
        self.lbl_naming_preview.setStyleSheet("QLabel { color: #ccc; font-size: 11px; font-weight: bold; margin-left: 2px; border: none; background-color: transparent; }")
        rename_layout.addWidget(self.lbl_naming_preview)
        footer_layout.addLayout(rename_layout)

        # Center Column: Export destination DropZone
        self.export_zone = OutputFolderDropZone()
        self.export_zone.setFixedWidth(300)
        self.export_zone.folder_dropped.connect(self._set_export_dir)
        self.export_zone.browse_clicked.connect(self._browse_export_dir)
        footer_layout.addWidget(self.export_zone)

        # Right Column: Progress bar & Processing execution controls
        exec_layout = QVBoxLayout()
        exec_layout.setSpacing(4)
        row_progress = QHBoxLayout()
        row_progress.setSpacing(10)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(20) 
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("QProgressBar { border: 1px solid #444; border-radius: 4px; text-align: center; color: white; background: #222; font-size: 10px; } QProgressBar::chunk { background-color: #3b82f6; border-radius: 3px; }")
        row_progress.addWidget(self.progress_bar, 1)
        
        self.lbl_exec_timer = QLabel("0.0s")
        self.lbl_exec_timer.setStyleSheet("color: #eee; font-size: 12px; font-family: monospace; font-weight: bold; border: none; background: transparent;")
        row_progress.addWidget(self.lbl_exec_timer)
        exec_layout.addLayout(row_progress)
        
        self.btn_start_exec = QPushButton(AppContext.tr("btn_start_processing"))
        self.btn_start_exec.setFixedHeight(28)
        self.btn_start_exec.setEnabled(False)
        self.btn_start_exec.setStyleSheet("QPushButton { background-color: #444; color: #888; font-weight: bold; font-size: 12px; border-radius: 4px; } QPushButton:enabled { background-color: #22c55e; color: white; } QPushButton:hover:enabled { background-color: #16a34a; }")
        self.btn_start_exec.clicked.connect(self.start_execution)
        exec_layout.addWidget(self.btn_start_exec)
        footer_layout.addLayout(exec_layout)

        content_layout.addWidget(self.footer_panel)
        self.stack.addWidget(self.content_widget)
        
        self.drop_zone.clicked.connect(self._browse_input_file)
        self.drop_zone.files_dropped.connect(self._on_drop_zone_files)
        
        self.color_correction_widgets = [
            self.slider_bright, self.slider_contrast, self.slider_sat,
            self.lay_bright, self.lay_contrast, self.lay_sat
        ] + self.cc_controls

        self.chk_rename.toggled.connect(self._update_naming_preview)
        self.combo_naming.currentIndexChanged.connect(self._update_naming_preview)
        self.inp_naming.textChanged.connect(self._update_naming_preview)

        self._update_crop_controls_enabled()
        self.check_ffmpeg_and_switch()

    def start_execution(self):
        super().start_execution()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if os.path.isfile(path):
                self.load_video(path)
                event.acceptProposedAction()

    def _on_drop_zone_files(self, paths):
        if paths: self.load_video(paths[0])
    
    def showEvent(self, event):
        super().showEvent(event)
        self.check_ffmpeg_and_switch()
        if not self.is_video_loaded and self.proxy_hint:
             QTimer.singleShot(10, self._center_drop_zone)

    def check_ffmpeg_and_switch(self):
        is_available, _ = check_ffmpeg_available()
        if is_available:
            self.stack.setCurrentWidget(self.content_widget)
        else:
            self.stack.setCurrentWidget(self.ffmpeg_notice)
    
    def on_ffmpeg_downloaded(self, success):
        if success:
            QTimer.singleShot(500, self.check_ffmpeg_and_switch)

    def load_video(self, path):
        self.reset_settings() 
        self.current_file = path
        
        # Audio Detection
        ext = os.path.splitext(path)[1].lower()
        is_audio = ext in {'.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a', '.opus', '.wma'}
        self.is_audio_only = is_audio
        
        logging.info(f"Загрузка {'аудио' if is_audio else 'видео'}: {path}")
        self.player.setSource(QUrl.fromLocalFile(path))
        self._generate_waveform(path)
        self.orig_bitrate = 5000000 
        ffprobe_exe = get_ffprobe_exe()
        if ffprobe_exe:
            try:
                cmd = [ffprobe_exe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=bit_rate", "-of", "default=noprint_wrappers=1:nokey=1", path]
                result = subprocess.check_output(cmd, creationflags=subprocess.CREATE_NO_WINDOW).decode().strip()
                if result and result.isdigit():
                    self.orig_bitrate = int(result)
            except Exception as e:
                print(f"[Editor] FFprobe error: {e}")
            
        self.is_video_loaded = True
        self.proxy_hint.hide() 
        self.view._initial_fit = True
        
        def _init_video_display():
            if self.player.duration() > 0:
                self.player.setPosition(0)
                self.player.play()
                QTimer.singleShot(10, lambda: self.player.pause())
        
        if self.player.duration() > 0:
            _init_video_display()
        else:
            def _on_duration_ready():
                _init_video_display()
                try: self.player.durationChanged.disconnect(_on_duration_ready)
                except: pass
            self.player.durationChanged.connect(_on_duration_ready)
        
        self.chk_overlay_enable.setEnabled(not is_audio)
        self._update_media_type_ui(is_audio)
        self._check_start_readiness()
        self._update_crop_controls_enabled()
        self.update()
        self._update_naming_preview()

    def _update_media_type_ui(self, is_audio):
        """Disables/Enables UI components based on media type"""
        # 1. Video Canvas
        if is_audio:
            self.video_item.hide()
            self.preview_item.hide()
            self.overlay_item.hide()
        else:
            self.video_item.show()
            # preview_item and overlay_item handled by their own logic
            
        # 2. Color Correction
        for w in self.color_correction_widgets:
            if hasattr(w, 'setEnabled'):
                w.setEnabled(not is_audio)
        
        # 3. Crop Controls
        self.btn_crop.setEnabled(not is_audio)
        if is_audio:
            self.btn_crop.setChecked(False)
            if hasattr(self, 'widget_crop_controls'):
                self.widget_crop_controls.hide()
            self._on_crop_moved() # Hide handles
            
        # 4. Overlay Controls
        self.chk_overlay_enable.setEnabled(not is_audio)
        if is_audio:
            self.chk_overlay_enable.setChecked(False)
            self.combo_overlay_type.setEnabled(False)
            self.widget_overlay_img.setEnabled(False)
            self.widget_overlay_reg.setEnabled(False)
        
        # 5. Transformations
        for b in [self.btn_rot_ccw, self.btn_rot_cw, self.btn_flip_h, self.btn_flip_v]:
            b.setEnabled(not is_audio)

    def reset_settings(self):
        if hasattr(self, 'playback_popup') and self.playback_popup.isVisible():
            self.playback_popup.hide()
            self.btn_settings.setChecked(False)
        self.current_rotation = 0
        self._is_fragment_mode = False
        self.is_flip_h = False
        self.is_flip_v = False
        self.is_cropping = False
        self.btn_crop.setChecked(False)
        if hasattr(self, 'widget_crop_controls'):
            self.widget_crop_controls.hide()
        self.btn_play.setText("")
        self.btn_play.setIcon(self.icon_play)
        self.is_crop_locked_size = False
        self.btn_crop_lock_size.blockSignals(True)
        self.btn_crop_lock_size.setChecked(False)
        self.btn_crop_lock_size.blockSignals(False)
        self._update_crop_button_styles()
        self._update_crop_controls_enabled()
        self._disable_crop_drag_mode()
        if self.is_crop_locked_size: self._disable_crop_lock_size()
        self.waveform_progress.clear_markers()
        self.waveform_progress.set_playback_pos(-1)
        self.lbl_frag_info.hide()
        self.handle_tl.hide()
        self.handle_br.hide()
        for s in [self.spin_crop_x, self.spin_crop_y, self.spin_crop_w, self.spin_crop_h]:
            s.setEnabled(False)
            s.setValue(0)
        self._update_dimming()
        self.edit_marker_time.setText("00:00:00.000")
        if hasattr(self, 'slider_bright'):
            for s, d in [(self.slider_bright, 0), (self.slider_contrast, 100), (self.slider_sat, 100)]:
                s.blockSignals(True)
                s.setValue(d)
                s.blockSignals(False)
        self.cc_brightness = 0.0
        self.cc_contrast = 1.0
        self.cc_saturation = 1.0
        self.chk_overlay_enable.setChecked(False)
        self.chk_overlay_enable.setEnabled(False) 
        self.slider_overlay_val.setValue(100)
        self.overlay_enabled = False
        self.overlay_type = "region"
        self.overlay_item.set_rect(QRectF(0, 0, 200, 200))
        self._clear_overlay_image()
        self._apply_view_transform()

    def reset_editor_to_default(self) -> None:
        self.player.stop()
        self.player.setSource(QUrl())
        self.is_video_loaded = False
        self.current_file = ""
        self.orig_bitrate = 5000000
        self.is_audio_only = False
        
        self.reset_settings()
        
        self.scene.setSceneRect(QRectF())
        self.view.resetTransform()
        
        if self.proxy_hint:
            self.proxy_hint.show()
            self._center_drop_zone()
            
        self.video_item.hide()
        self.preview_item.hide()
        self.overlay_item.hide()
        
        self.waveform_progress.clear_markers()
        self.waveform_progress.set_waveform(None)
        self.list_markers.clear()
        
        self.chk_overlay_enable.setChecked(False)
        self.chk_overlay_enable.setEnabled(False)
        self.btn_crop.setEnabled(False)
        for b in [self.btn_rot_ccw, self.btn_rot_cw, self.btn_flip_h, self.btn_flip_v]:
            b.setEnabled(False)
            
        self._check_start_readiness()
        self._update_naming_preview()

    def _generate_waveform(self, path):
        ffmpeg = get_ffmpeg_exe()
        if not os.path.exists(ffmpeg): return
        temp_img = os.path.join(tempfile.gettempdir(), "mk_waveform.png")
        cmd = [ffmpeg, "-y", "-i", path, "-filter_complex", "aformat=channel_layouts=mono,showwavespic=s=1200x80:colors=#666666", "-frames:v", "1", temp_img]
        try:
            subprocess.run(cmd, startupinfo=self._get_startupinfo(), capture_output=True)
            if os.path.exists(temp_img):
                pix = QPixmap(temp_img)
                self.waveform_progress.set_waveform(pix)
        except: pass

    def _get_startupinfo(self):
        if os.name == 'nt':
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            return si
        return None

    def _browse_input_file(self):
        filter_str = AppContext.tr("editor_filter_media")
        f, _ = QFileDialog.getOpenFileName(self, AppContext.tr("msg_select_video_file"), "", filter_str)
        if f: self.load_video(f)

    def _setup_chevron_icons(self):
        chevron_up_tpl = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
            'fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="m18 15-6-6-6 6"/></svg>'
        )
        chevron_down_tpl = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
            'fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="m6 9 6 6 6-6"/></svg>'
        )

        import tempfile
        temp_dir = tempfile.gettempdir()

        colors = {
            "active": "#4ade80",
            "locked": "#ef4444",
            "disabled": "#4a5a4a"
        }

        self.chevron_paths = {}
        for state, color in colors.items():
            path_up = os.path.join(temp_dir, f"chevron-up-{state}.svg").replace('\\', '/')
            path_down = os.path.join(temp_dir, f"chevron-down-{state}.svg").replace('\\', '/')
            
            try:
                with open(path_up, "w", encoding="utf-8") as f:
                    f.write(chevron_up_tpl.format(color=color))
                with open(path_down, "w", encoding="utf-8") as f:
                    f.write(chevron_down_tpl.format(color=color))
            except Exception as e:
                logging.error(f"Failed to write temporary chevron SVG: {e}")
                
            self.chevron_paths[f"up_{state}"] = path_up
            self.chevron_paths[f"down_{state}"] = path_down

        # Генерируем speaker_off_white и speaker_off_black
        speaker_off_path = os.path.join(self.icons_dir, "speaker_off.svg")
        try:
            with open(speaker_off_path, "r", encoding="utf-8") as f:
                svg_content = f.read()
            
            white_svg = svg_content.replace('stroke="#ef4444"', 'stroke="#ffffff"')
            black_svg = svg_content.replace('stroke="#ef4444"', 'stroke="#000000"')
            
            self.path_speaker_off_white = os.path.join(temp_dir, "speaker_off_white.svg").replace('\\', '/')
            self.path_speaker_off_black = os.path.join(temp_dir, "speaker_off_black.svg").replace('\\', '/')
            
            with open(self.path_speaker_off_white, "w", encoding="utf-8") as f:
                f.write(white_svg)
            with open(self.path_speaker_off_black, "w", encoding="utf-8") as f:
                f.write(black_svg)
                
            self.icon_speaker_off_white = QIcon(self.path_speaker_off_white)
            self.icon_speaker_off_black = QIcon(self.path_speaker_off_black)
        except Exception as e:
            logging.error(f"Failed to generate custom speaker_off icons: {e}")
            self.icon_speaker_off_white = QIcon(speaker_off_path)
            self.icon_speaker_off_black = QIcon(speaker_off_path)

    def _btn_style(self):
        return """QPushButton { background: #333; border: 1px solid #555; color: #ccc; border-radius: 4px; font-weight: bold; } QPushButton:hover { background: #444; color: white; border-color: #666; } QPushButton:pressed { background: #222; } QPushButton:checked { background: #3b82f6; color: white; border-color: #3b82f6; } QPushButton:disabled { color: #555; border-color: #444; }"""

    def _create_coord_spin(self, prefix):
        s = QSpinBox()
        s.setRange(0, 9999)
        s.setPrefix(f"{prefix}: ")
        s.setAlignment(Qt.AlignmentFlag.AlignLeft)
        # Ширина подбирается динамически по сетке, фиксированная только высота
        s.setMinimumWidth(80)
        return s

    def _on_volume_changed(self, val):
        if val > 0:
            self.is_muted = False
            self.saved_volume = val
        else:
            self.is_muted = True
            
        self._update_mute_icon(val)
        if not self.is_muted:
            self.audio_output.setVolume(val / 100.0)
        else:
            self.audio_output.setVolume(0.0)

    def _on_cc_changed(self):
        self.cc_brightness = self.slider_bright.value() / 100.0
        self.cc_contrast = self.slider_contrast.value() / 100.0
        self.cc_saturation = self.slider_sat.value() / 100.0
        self._check_start_readiness()

    def _on_mute_clicked(self):
        if self.is_muted:
            self.is_muted = False
            self.slider_vol.setValue(self.saved_volume)
        else:
            current_val = self.slider_vol.value()
            if current_val > 0:
                self.saved_volume = current_val
            self.is_muted = True
            self.slider_vol.setValue(0)

    def _update_mute_icon(self, val):
        if val == 0 or self.is_muted:
            self.btn_mute.setIcon(self.icon_speaker_off)
        else:
            self.btn_mute.setIcon(self.icon_speaker)

    def _toggle_settings_popup(self):
        if self.btn_settings.isChecked():
            self.playback_popup.set_values(self.playback_rate, self.is_looping)
            pos = self.btn_settings.mapToGlobal(QPoint(0, 0))
            x = pos.x() - self.playback_popup.width() + self.btn_settings.width()
            y = pos.y() - self.playback_popup.height() - 5
            self.playback_popup.move(x, y)
            self.playback_popup.show()
            self.playback_popup.raise_()
        else:
            self.playback_popup.hide()

    def _on_popup_closed(self):
        from PyQt6.QtGui import QCursor
        from PyQt6.QtCore import QRectF, QPointF, QSizeF
        cursor_pos = QCursor.pos()
        btn_rect = self.btn_settings.frameGeometry()
        top_left = self.btn_settings.mapToGlobal(QPoint(0, 0))
        btn_global_rect = QRectF(QPointF(top_left), QSizeF(btn_rect.width(), btn_rect.height()))
        if not btn_global_rect.contains(QPointF(cursor_pos)):
            self.btn_settings.setChecked(False)

    def _apply_playback_settings(self, rate, loop):
        self.playback_rate = rate
        self.is_looping = loop
        self.player.setPlaybackRate(rate)

    def center_video(self, size=None):
        if not self.video_item or not self.is_video_loaded: return
        if not isinstance(size, QSizeF): size = self.video_item.nativeSize()
        if not size.isValid(): return
        self.video_item.setSize(size)
        self.video_item.setPos(0, 0)
        self.video_item.setTransform(QTransform()) 
        rect = self.video_item.boundingRect()
        if not rect.isEmpty():
            self.scene.setSceneRect(rect)
            self.view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
            self.view.centerOn(rect.center())
            if self.overlay_item.get_rect().width() == 200: 
                w, h = rect.width(), rect.height()
                ow, oh = w * (2.0 / 3.0), h * (2.0 / 3.0)
                self.overlay_item.set_rect(QRectF(0, 0, ow, oh))
                self.overlay_item.setPos(w/2 - ow/2, h/2 - oh/2)
        self._apply_view_transform()

    def _add_marker_at_pos(self):
        txt = self.edit_marker_time.text()
        ms = self._parse_hms(txt)
        dur = self.player.duration()
        if dur > 0:
            norm = max(0.001, min(0.999, ms / dur))
            self.waveform_progress.add_marker(norm)

    def _on_markers_changed(self, markers, is_inverted):
        count = len(markers) + 1
        selected_count = 0
        total_duration_ms = 0
        dur = self.player.duration()
        if dur <= 0:
            self.lbl_frag_info.setText(AppContext.tr("fragment_info_format").format(0, 0, "0.000"))
            self.lbl_frag_info.show()
            self._check_start_readiness()
            return
        segments = [0.0] + markers + [1.0]
        for i in range(len(segments) - 1):
            take = (i % 2 == 0)
            if is_inverted: take = not take
            if take:
                selected_count += 1
                s_start = segments[i]
                s_end = segments[i+1]
                total_duration_ms += (s_end - s_start) * dur
        dur_str = self._to_hms(int(total_duration_ms))
        self.lbl_frag_info.setText(AppContext.tr("fragment_info_format").format(count, selected_count, f"<span style='color: #4ade80;'>{dur_str}</span>"))
        self.lbl_frag_info.show()
        self._check_start_readiness()

        # Обновление списка маркеров в интерфейсе
        if hasattr(self, 'list_markers'):
            self.list_markers.blockSignals(True)
            self.list_markers.clear()
            for idx, m in enumerate(markers):
                ms = int(m * dur)
                hms = self._to_hms_full(ms)
                item = QListWidgetItem(AppContext.tr("marker_item_text").format(idx+1, hms))
                item.setData(Qt.ItemDataRole.UserRole, m)
                self.list_markers.addItem(item)
            self.list_markers.blockSignals(False)

    def _on_list_marker_clicked(self, item):
        pos = item.data(Qt.ItemDataRole.UserRole)
        dur = self.player.duration()
        if pos is not None and dur > 0:
            ms = int(pos * dur)
            self.player.setPosition(ms)
            # Находим этот маркер на таймлайне и выделяем его
            for idx, m in enumerate(self.waveform_progress.markers):
                if abs(m - pos) < 0.0001:
                    self.waveform_progress.selected_idx = idx
                    self.waveform_progress.update_states()
                    self.edit_marker_time.setText(self._to_hms_full(ms))
                    break
            self._schedule_cc_preview()

    def _on_marker_selected(self, idx):
        if idx >= 0 and idx < len(self.waveform_progress.markers):
            norm = self.waveform_progress.markers[idx]
            ms = int(norm * self.player.duration())
            self.edit_marker_time.setText(self._to_hms_full(ms))
            self.player.setPosition(ms)
            # Выделяем соответствующий пункт в списке маркеров
            if hasattr(self, 'list_markers'):
                self.list_markers.blockSignals(True)
                self.list_markers.setCurrentRow(idx)
                self.list_markers.blockSignals(False)
            if hasattr(self, 'btn_delete_marker'):
                self.btn_delete_marker.setEnabled(True)
            self._schedule_cc_preview()
        else:
            self.edit_marker_time.setText("00:00:00.000")
            if hasattr(self, 'list_markers'):
                self.list_markers.blockSignals(True)
                self.list_markers.setCurrentRow(-1)
                self.list_markers.blockSignals(False)
            if hasattr(self, 'btn_delete_marker'):
                self.btn_delete_marker.setEnabled(False)

    def _on_marker_edit_finished(self):
        txt = self.edit_marker_time.text()
        ms = self._parse_hms(txt)
        dur = self.player.duration()
        if dur > 0 and self.waveform_progress.selected_idx != -1:
            norm = max(0.001, min(0.999, ms / dur))
            idx = self.waveform_progress.selected_idx
            lower = self.waveform_progress.markers[idx-1] if idx > 0 else 0.0
            upper = self.waveform_progress.markers[idx+1] if idx < len(self.waveform_progress.markers)-1 else 1.0
            norm = max(lower + 0.001, min(upper - 0.001, norm))
            self.waveform_progress.markers[idx] = norm
            self.waveform_progress.markers.sort()
            self.waveform_progress.update_states()

    def _parse_hms(self, txt):
        try:
            parts = txt.replace(",", ".").split(":")
            if len(parts) == 3:
                h = int(parts[0])
                m = int(parts[1])
                s_parts = parts[2].split(".")
                s = int(s_parts[0])
                ms = int(s_parts[1]) if len(s_parts) > 1 else 0
                return (h * 3600 + m * 60 + s) * 1000 + ms
            elif len(parts) == 1: 
                p = parts[0].split(".")
                s = int(p[0])
                ms = int(p[1]) if len(p) > 1 else 0
                return s * 1000 + ms
        except: pass
        return 0

    def _update_naming_preview(self):
        if not self.current_file or not self.is_video_loaded: return
        base = os.path.basename(self.current_file)
        name, ext = os.path.splitext(base)
        if self.chk_rename.isChecked():
            val = self.inp_naming.text()
            if self.combo_naming.currentIndex() == 0: name = val + name
            else: name = name + val
        self.lbl_naming_preview.setText(AppContext.tr("lbl_naming_preview").replace(" -", f" {name}{ext}"))

    def _set_ui_locked(self, locked):
        self.btn_add_marker.setEnabled(not locked)
        self.btn_invert.setEnabled(not locked)
        self.btn_clear_markers.setEnabled(not locked)
        self.edit_marker_time.setEnabled(not locked)
        self.waveform_progress.setEnabled(not locked)
        if hasattr(self, 'btn_delete_marker'):
            self.btn_delete_marker.setEnabled(not locked and self.waveform_progress.selected_idx != -1)
        
        # Respect audio mode when unlocking
        is_audio = getattr(self, 'is_audio_only', False)
        self.btn_crop.setEnabled(not locked and not is_audio)
        
        for s in [self.spin_crop_x, self.spin_crop_y, self.spin_crop_w, self.spin_crop_h]:
            s.setEnabled(not locked and self.is_cropping)

    def play_preview(self):
        dur = self.player.duration()
        if dur <= 0: return
        markers = self.waveform_progress.markers
        inverted = self.waveform_progress.is_inverted
        segments = [0.0] + markers + [1.0]
        first_green_start = -1.0
        for i in range(len(segments) - 1):
            take = (i % 2 == 0)
            if inverted: take = not take
            if take:
                first_green_start = segments[i]
                break
        if first_green_start != -1.0:
            self._is_preview_mode = True
            self.preview_item.hide()
            self._set_ui_locked(True)
            self.player.setPosition(int(first_green_start * dur))
            self.player.play()

    def _to_hms_full(self, ms):
        h = ms // 3600000
        m = (ms % 3600000) // 60000
        s = (ms % 60000) // 1000
        sss = ms % 1000
        return f"{h:02}:{m:02}:{s:02}.{sss:03}"

    def _rotate(self, angle):
        self.current_rotation = (self.current_rotation + angle) % 360
        self._apply_view_transform()
        self._check_start_readiness()

    def _flip(self, axis):
        if axis == 'h': self.is_flip_h = not self.is_flip_h
        else: self.is_flip_v = not self.is_flip_v
        self._apply_view_transform()
        self._check_start_readiness()

    def _apply_view_transform(self):
        rect = self.video_item.boundingRect()
        self.video_item.setTransformOriginPoint(rect.center())
        self.video_item.setRotation(self.current_rotation)
        scale_x = -1 if self.is_flip_h else 1
        scale_y = -1 if self.is_flip_v else 1
        t = QTransform()
        t.scale(scale_x, scale_y)
        self.video_item.setTransform(t)
        scene_rect = self.video_item.sceneBoundingRect()
        if not scene_rect.isEmpty():
            self.scene.setSceneRect(scene_rect)
            self.view.fitInView(scene_rect, Qt.AspectRatioMode.KeepAspectRatio)
        self.view.centerOn(scene_rect.center())

    def _delete_selected_marker(self):
        row = self.list_markers.currentRow()
        if row >= 0 and row < len(self.waveform_progress.markers):
            self.waveform_progress.markers.pop(row)
            self.waveform_progress.selected_idx = -1
            self.waveform_progress.update_states()

    def update_ui_text(self):
        self.btn_play.setText("")
        self.btn_play.setToolTip(AppContext.tr("tooltip_play_pause"))
        self.btn_prev_frame.setText("")
        self.btn_prev_frame.setToolTip(AppContext.tr("tooltip_prev_frame"))
        self.btn_next_frame.setText("")
        self.btn_next_frame.setToolTip(AppContext.tr("tooltip_next_frame"))
        self.btn_play_frag.setText(AppContext.tr("btn_preview_fragment"))
        self.btn_play_frag.setToolTip(AppContext.tr("tooltip_play_frag"))
        self.btn_play_frag.setIcon(QIcon(os.path.join(self.icons_dir, "skip-forward.svg")))
        self.btn_play_frag.setIconSize(QSize(14, 14))
        self.btn_rot_ccw.setToolTip(AppContext.tr("btn_rotate_ccw"))
        self.btn_rot_cw.setToolTip(AppContext.tr("btn_rotate_cw"))
        self.btn_flip_h.setToolTip(AppContext.tr("btn_flip_h"))
        self.btn_flip_v.setToolTip(AppContext.tr("btn_flip_v"))
        self.btn_remove_audio.setText(" " + AppContext.tr("chk_mute_audio"))
        self.btn_remove_audio.setToolTip(AppContext.tr("tooltip_remove_audio"))
        self.btn_mute.setText("")
        self.btn_mute.setToolTip(AppContext.tr("tooltip_mute"))
        if hasattr(self, 'btn_reset_editor'):
            self.btn_reset_editor.setToolTip(AppContext.tr("tooltip_reset_editor"))
        self.btn_settings.setText("")
        self.btn_settings.setToolTip(AppContext.tr("tooltip_settings"))
        
        # Section 4 Markers buttons & tooltips
        self.btn_add_marker.setText(" " + AppContext.tr("btn_add_marker_text"))
        self.btn_add_marker.setToolTip(AppContext.tr("tooltip_add_marker_btn"))
        self.btn_invert.setText(" " + AppContext.tr("btn_invert_markers_text"))
        self.btn_invert.setToolTip(AppContext.tr("tooltip_invert_markers"))
        self.btn_clear_markers.setText(" " + AppContext.tr("btn_clear_markers_text"))
        self.btn_clear_markers.setToolTip(AppContext.tr("tooltip_clear_markers"))
        self.btn_split_video.setText(" " + AppContext.tr("btn_split_video"))
        self.btn_split_video.setToolTip(AppContext.tr("tooltip_split_video"))
        
        self.lbl_marker_info.setText(AppContext.tr("lbl_markers_title"))
        self.lbl_naming_preview.setText(AppContext.tr("lbl_naming_preview"))
        self.chk_overlay_enable.setText(AppContext.tr("ovl_enable"))
        self.chk_overlay_enable.setToolTip(AppContext.tr("tooltip_overlay_enable"))
        self.chk_rename.setText(AppContext.tr("chk_rename"))
        self.chk_rename.setToolTip(AppContext.tr("tooltip_rename"))
        self.btn_crop.setText(AppContext.tr("btn_crop"))
        self.btn_crop.setToolTip(AppContext.tr("tooltip_crop"))
        self.btn_crop_lock_size.setToolTip(AppContext.tr("tooltip_crop_lock"))
        self.btn_start_exec.setText(AppContext.tr("btn_start_processing"))
        self.btn_start_exec.setToolTip(AppContext.tr("tooltip_start_exec"))
        
        curr_naming_idx = self.combo_naming.currentIndex()
        if curr_naming_idx < 0:
            curr_naming_idx = 1  # Постфикс по умолчанию
        self.combo_naming.blockSignals(True)
        self.combo_naming.clear()
        self.combo_naming.addItems([AppContext.tr("combo_naming_prefix"), AppContext.tr("combo_naming_postfix")])
        self.combo_naming.setCurrentIndex(curr_naming_idx)
        self.combo_naming.blockSignals(False)

        curr_overlay_idx = self.combo_overlay_type.currentIndex()
        if curr_overlay_idx < 0:
            curr_overlay_idx = 0
        self.combo_overlay_type.blockSignals(True)
        self.combo_overlay_type.clear()
        self.combo_overlay_type.addItems([AppContext.tr("ovl_type_img"), AppContext.tr("ovl_type_region"), AppContext.tr("ovl_type_blur")])
        self.combo_overlay_type.setCurrentIndex(curr_overlay_idx)
        self.combo_overlay_type.blockSignals(False)
        self.lbl_overlay_val.setText(AppContext.tr("ovl_opacity"))
        self.slider_overlay_val.setToolTip(AppContext.tr("tooltip_overlay_val_slider"))
        self.spin_overlay_val.setToolTip(AppContext.tr("tooltip_overlay_val_spin"))
        self.btn_overlay_select_img.setText(AppContext.tr("ovl_btn_select"))
        self.btn_overlay_select_img.setToolTip(AppContext.tr("tooltip_overlay_select_img"))
        self.btn_overlay_img_del.setToolTip(AppContext.tr("tooltip_overlay_img_del"))
        self.btn_overlay_img_reset.setToolTip(AppContext.tr("tooltip_overlay_img_reset"))
        self.btn_overlay_color.setToolTip(AppContext.tr("tooltip_overlay_color"))
        
        self.combo_overlay_type.setToolTip(AppContext.tr("tooltip_overlay_type"))
        self.edit_marker_time.setToolTip(AppContext.tr("tooltip_marker_time"))
        
        # Section 5 Encoding controls
        self.lbl_codec.setText(AppContext.tr("lbl_video_codec"))
        self.lbl_codec.setToolTip(AppContext.tr("tooltip_video_codec"))
        self.combo_video_codec.setToolTip(AppContext.tr("tooltip_video_codec_desc"))
        
        self.lbl_quality.setText(AppContext.tr("lbl_video_quality"))
        self.lbl_quality.setToolTip(AppContext.tr("tooltip_video_quality"))
        
        quality_idx = self.combo_video_quality.currentIndex()
        self.combo_video_quality.clear()
        self.combo_video_quality.addItem(AppContext.tr("combo_quality_high"), 17)
        self.combo_video_quality.addItem(AppContext.tr("combo_quality_medium"), 23)
        self.combo_video_quality.addItem(AppContext.tr("combo_quality_low"), 28)
        if quality_idx >= 0 and quality_idx < self.combo_video_quality.count():
            self.combo_video_quality.setCurrentIndex(quality_idx)
        self.combo_video_quality.setToolTip(AppContext.tr("tooltip_video_quality_desc"))
        
        self.lbl_preset.setText(AppContext.tr("lbl_preset_speed"))
        self.lbl_preset.setToolTip(AppContext.tr("tooltip_preset_speed"))
        self.combo_video_preset.setToolTip(AppContext.tr("tooltip_preset_desc"))
        
        # Section header titles & tooltips
        if hasattr(self, 'sec_transform'):
            self.sec_transform.update_text(AppContext.tr("section_transform"), AppContext.tr("tooltip_sec_transform"))
        if hasattr(self, 'sec_color'):
            self.sec_color.update_text(AppContext.tr("section_color"), AppContext.tr("tooltip_sec_color"))
        if hasattr(self, 'sec_overlay'):
            self.sec_overlay.update_text(AppContext.tr("section_overlay"), AppContext.tr("tooltip_sec_overlay"))
        if hasattr(self, 'sec_markers'):
            self.sec_markers.update_text(AppContext.tr("section_markers"), AppContext.tr("tooltip_sec_markers"))
        if hasattr(self, 'sec_encoding'):
            self.sec_encoding.update_text(AppContext.tr("section_encoding"), AppContext.tr("tooltip_sec_encoding"))
            
        # Section inner titles
        if hasattr(self, 'lbl_rot_title'):
            self.lbl_rot_title.setText(AppContext.tr("lbl_rotate_flip"))
        if hasattr(self, 'lbl_warn_text'):
            self.lbl_warn_text.setText(AppContext.tr("lbl_rendering_required"))
            
        if self.overlay_enabled: 
            self._on_overlay_type_changed(self.combo_overlay_type.currentIndex())
            
        for label in self.findChildren(QLabel):
            if label.text() in ["Яркость", "Brightness"]: label.setText(AppContext.tr("slider_brightness"))
            elif label.text() in ["Контраст", "Contrast"]: label.setText(AppContext.tr("slider_contrast"))
            elif label.text() in ["Насыщ.", "Saturation"]: label.setText(AppContext.tr("slider_saturation"))
            
        # Update Color Correction tooltips dynamically
        if hasattr(self, 'spin_bright'):
            self.spin_bright.setToolTip(AppContext.tr("tooltip_cc_spin").format(AppContext.tr("slider_brightness")))
            self.slider_bright.setToolTip(AppContext.tr("tooltip_cc_slider").format(AppContext.tr("slider_brightness")))
            self.btn_reset_bright.setToolTip(AppContext.tr("tooltip_cc_reset").format(AppContext.tr("slider_brightness")))
            
        if hasattr(self, 'spin_contrast'):
            self.spin_contrast.setToolTip(AppContext.tr("tooltip_cc_spin").format(AppContext.tr("slider_contrast")))
            self.slider_contrast.setToolTip(AppContext.tr("tooltip_cc_slider").format(AppContext.tr("slider_contrast")))
            self.btn_reset_contrast.setToolTip(AppContext.tr("tooltip_cc_reset").format(AppContext.tr("slider_contrast")))
            
        if hasattr(self, 'spin_sat'):
            self.spin_sat.setToolTip(AppContext.tr("tooltip_cc_spin").format(AppContext.tr("slider_saturation")))
            self.slider_sat.setToolTip(AppContext.tr("tooltip_cc_slider").format(AppContext.tr("slider_saturation")))
            self.btn_reset_sat.setToolTip(AppContext.tr("tooltip_cc_reset").format(AppContext.tr("slider_saturation")))
            
        if hasattr(self, 'lbl_rate'):
            current_speed = getattr(self, 'rate', 1.0)
            self.lbl_rate.setText(AppContext.tr("lbl_speed").format(current_speed))
        if hasattr(self, 'chk_loop'): 
            self.chk_loop.setText(AppContext.tr("chk_loop_media"))
        if hasattr(self, 'drop_zone') and hasattr(self.drop_zone, 'update_ui_text'): 
            self.drop_zone.update_ui_text()
        if hasattr(self, 'export_zone') and hasattr(self.export_zone, 'update_ui_text'): 
            self.export_zone.update_ui_text()
            
        self._update_naming_preview()
