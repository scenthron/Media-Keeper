import os
import logging
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QSlider, QStyle, QStyleOptionSlider, 
    QLabel, QCheckBox
)
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QRectF, QPointF, QSizeF, QSize, QTimer
from PyQt6.QtGui import QCursor, QIcon
from config import AppContext, VIEWER_DESIGN

class ClickableSlider(QSlider):
    seek_requested = pyqtSignal(int)
    seek_moved = pyqtSignal(int)
    seek_drag_start = pyqtSignal()
    seek_drag_stop = pyqtSignal()
    
    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setObjectName("ClickableSlider")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Styles injected at birth
        self.setStyleSheet(f"""
            #ClickableSlider {{ 
                background: transparent; 
                min-height: 20px; 
                max-height: 20px;
            }}
            #ClickableSlider::groove:horizontal {{
                background: {VIEWER_DESIGN['slider_groove_color']}; 
                height: 4px; 
                border-radius: 2px;
                margin: 0px;
            }}
            #ClickableSlider::handle:horizontal {{
                background: {VIEWER_DESIGN['slider_handle_color']}; 
                width: 14px; 
                height: 14px; 
                margin: -5px 0; 
                border-radius: 7px;
            }}
            #ClickableSlider::sub-page:horizontal {{
                background: {VIEWER_DESIGN['slider_handle_color']}; 
                border-radius: 2px;
            }}
            /* HARDENED STYLES FOR DEBUG & COMPATIBILITY */
            #ClickableSlider::groove:horizontal:disabled {{ background: #222; }}
            #ClickableSlider::handle:horizontal:disabled {{ background: #555; }}
            #ClickableSlider::groove:vertical {{ background: #333; width: 4px; }}
            #ClickableSlider::handle:vertical {{ background: {VIEWER_DESIGN['slider_handle_color']}; height: 14px; margin: 0 -5px; }}
        """)

    def mousePressEvent(self, event):
        self.seek_drag_start.emit()
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            val = self.pixelPosToRangeValue(event.position().x())
            self.setValue(val)
            self.seek_requested.emit(val) 
            self.seek_moved.emit(val)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if event.buttons() & Qt.MouseButton.LeftButton:
            val = self.value()
            self.seek_moved.emit(val)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.seek_drag_stop.emit()

    def pixelPosToRangeValue(self, pos):
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        gr = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderGroove, self)
        sr = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self)

        if self.orientation() == Qt.Orientation.Horizontal:
            sliderLength = sr.width()
            sliderMin = gr.x()
            sliderMax = gr.right() - sliderLength + 1
        else:
            sliderLength = sr.height()
            sliderMin = gr.y()
            sliderMax = gr.bottom() - sliderLength + 1
        
        return QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), int(pos) - sliderMin,
                                              sliderMax - sliderMin, opt.upsideDown)

class MagneticSlider(QSlider):
    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setObjectName("MagneticSlider")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.snap_values = [10, 50, 100, 150, 200, 300, 400, 500, 600] 
        self.snap_threshold = 2
        # Styles injected at birth
        self.setStyleSheet(f"""
            #MagneticSlider {{ 
                background: transparent; 
                min-height: 20px; 
                max-height: 20px;
            }}
            #MagneticSlider::groove:horizontal {{
                background: {VIEWER_DESIGN['slider_groove_color']}; 
                height: 4px; 
                border-radius: 2px;
                margin: 0px;
            }}
            #MagneticSlider::handle:horizontal {{
                background: {VIEWER_DESIGN['slider_handle_color']}; 
                width: 14px; 
                height: 14px; 
                margin: -5px 0; 
                border-radius: 7px;
            }}
            #MagneticSlider::sub-page:horizontal {{
                background: {VIEWER_DESIGN['slider_handle_color']}; 
                border-radius: 2px;
            }}
        """)

    def mouseReleaseEvent(self, event):
        val = self.value()
        nearest = min(self.snap_values, key=lambda x: abs(x - val))
        
        if abs(nearest - val) <= self.snap_threshold:
            self.setValue(nearest)
            self.valueChanged.emit(nearest)
        
        super().mouseReleaseEvent(event)

class PlayerSettingsPopup(QWidget):
    speed_changed = pyqtSignal(float)
    loop_toggled = pyqtSignal(bool)
    apply_all_toggled = pyqtSignal(bool)
    closed = pyqtSignal() 

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("PlayerSettingsPopup")
        self.setStyleSheet("""
            PlayerSettingsPopup { background-color: #222222; border: 1px solid #444; border-radius: 6px; }
            QLabel { color: #ccc; border: none; font-size: 11px; font-weight: bold; margin: 0px; background: transparent; }
            QCheckBox { color: #ccc; border: none; font-size: 11px; spacing: 5px; background: transparent; }
            QCheckBox::indicator { width: 13px; height: 13px; border: 1px solid #555; border-radius: 2px; background: #333; }
            QCheckBox::indicator:checked { background: #3b82f6; border-color: #3b82f6; }
            QCheckBox:disabled { color: #555; }
            QPushButton { background-color: #333; color: white; border: 1px solid #555; border-radius: 3px; font-size: 10px; font-weight: bold;}
            QPushButton:hover { background-color: #444; }
        """)
        self.setFixedSize(160, 90)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)
        
        speed_row = QHBoxLayout()
        speed_row.setSpacing(5)
        
        self.btn_reset_speed = QPushButton("x1")
        self.btn_reset_speed.setFixedSize(20, 16)
        self.btn_reset_speed.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_speed.clicked.connect(self.reset_speed)
        
        self.lbl_speed = QLabel(f"{AppContext.tr('lbl_speed')} 1.0x")
        
        speed_row.addWidget(self.btn_reset_speed)
        speed_row.addWidget(self.lbl_speed)
        speed_row.addStretch()
        layout.addLayout(speed_row)
        
        self.slider_speed = MagneticSlider(Qt.Orientation.Horizontal)
        self.slider_speed.setRange(10, 600) 
        self.slider_speed.setValue(100)
        self.slider_speed.valueChanged.connect(self.on_speed_change)
        self.slider_speed.setFixedHeight(16)
        layout.addWidget(self.slider_speed)
        
        self.chk_apply_all = QCheckBox(AppContext.tr("lbl_all_videos"))
        self.chk_apply_all.toggled.connect(self.apply_all_toggled.emit)
        layout.addWidget(self.chk_apply_all)
        
        self.chk_loop = QCheckBox(AppContext.tr("lbl_loop_media"))
        self.chk_loop.toggled.connect(self.loop_toggled.emit)
        layout.addWidget(self.chk_loop)
    
    def update_ui_text(self):
        current_speed = self.slider_speed.value() / 100.0
        self.lbl_speed.setText(f"{AppContext.tr('lbl_speed')} {current_speed:.1f}x")
        self.chk_apply_all.setText(AppContext.tr("lbl_all_videos"))
        self.chk_loop.setText(AppContext.tr("lbl_loop_media"))
    
    def hideEvent(self, event):
        self.closed.emit()
        super().hideEvent(event)
        
    def reset_speed(self):
        self.slider_speed.setValue(100)
        
    def on_speed_change(self, val):
        speed = val / 100.0
        self.lbl_speed.setText(f"{AppContext.tr('lbl_speed')} {speed:.1f}x")
        self.speed_changed.emit(speed)

    def set_values(self, speed_val, is_loop, is_apply_all):
        self.blockSignals(True)
        self.slider_speed.blockSignals(True)
        self.chk_loop.blockSignals(True)
        self.chk_apply_all.blockSignals(True)
        
        pct = int(speed_val * 100)
        self.slider_speed.setValue(pct)
        self.lbl_speed.setText(f"{AppContext.tr('lbl_speed')} {speed_val:.1f}x")
        
        self.chk_loop.setChecked(is_loop)
        
        self.chk_apply_all.setChecked(is_apply_all)
        
        self.blockSignals(False)
        self.slider_speed.blockSignals(False)
        self.chk_loop.blockSignals(False)
        self.chk_apply_all.blockSignals(False)

    def set_mode(self, is_video):
        self.chk_apply_all.setEnabled(is_video)
        if not is_video:
            self.chk_apply_all.setToolTip(AppContext.tr("tip_video_only"))
        else:
            self.chk_apply_all.setToolTip("")



class VideoPlayerControls(QWidget):
    play_pause_clicked = pyqtSignal()
    seek_requested = pyqtSignal(int)
    seek_moved = pyqtSignal(int)
    seek_drag_start = pyqtSignal()
    seek_drag_stop = pyqtSignal()
    speed_changed = pyqtSignal(float)
    loop_toggled = pyqtSignal(bool)
    apply_all_toggled = pyqtSignal(bool)
    volume_changed = pyqtSignal(int) # New Signal 0-100
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        # FORCE BLACK BACKGROUND for Controls container to avoid gray artifacts
        self.setStyleSheet("VideoPlayerControls { background-color: #000000; border-top: 1px solid #333; }")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(10)
        
        # Загрузка глобальных иконок плеера
        icons_dir_global = AppContext.find_resource_dir("icons")
        self.icon_play = QIcon(os.path.join(icons_dir_global, "media_play.svg"))
        self.icon_pause = QIcon(os.path.join(icons_dir_global, "media_pause.svg"))
        self.icon_speaker = QIcon(os.path.join(icons_dir_global, "speaker.svg"))
        self.icon_speaker_off = QIcon(os.path.join(icons_dir_global, "speaker_off.svg"))

        self.btn_play = QPushButton(self)
        self.btn_play.setFixedSize(30, 24)
        self.btn_play.setIconSize(QSize(14, 14))
        self.btn_play.setIcon(self.icon_play)
        self.btn_play.setStyleSheet("background: transparent; border: none;")
        self.btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_play.clicked.connect(self.play_pause_clicked.emit)
        self.btn_play.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.btn_play)
        
        self.seeker = ClickableSlider(Qt.Orientation.Horizontal)
        self.seeker.setRange(0, 100) # Safe default range to prevent 0-0 errors
        self.seeker.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
        self.is_seeking = False
        
        self.seeker.seek_drag_start.connect(self._on_drag_start)
        self.seeker.seek_drag_stop.connect(self._on_drag_stop)
        self.seeker.seek_moved.connect(self._on_seeker_moved)
        self.seeker.seek_requested.connect(self.seek_requested.emit)
        
        self.seeker.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.seeker)

        # --- VOLUME CONTROL ---
        self.btn_mute = QPushButton(self)
        self.btn_mute.setFixedSize(24, 24)
        self.btn_mute.setIconSize(QSize(14, 14))
        self.btn_mute.setIcon(self.icon_speaker)
        self.btn_mute.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
                padding: 0px;
            }
        """)
        self.btn_mute.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mute.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_mute.clicked.connect(self.toggle_mute)
        layout.addWidget(self.btn_mute)

        self.vol_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setFixedWidth(60)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(10) # Default 10%
        # Explicit background transparent
        self.vol_slider.setStyleSheet("""
            #ClickableSlider { background: transparent; }
            #ClickableSlider::groove:horizontal { background: #333; height: 4px; border-radius: 2px; }
            #ClickableSlider::handle:horizontal { background: #888; width: 10px; height: 10px; margin: -3px 0; border-radius: 5px; }
            #ClickableSlider::sub-page:horizontal { background: #888; border-radius: 2px; }
        """)
        
        self.is_muted = False
        self.saved_volume = 10
        self.vol_slider.valueChanged.connect(self._on_volume_slider_changed)
        self.vol_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.vol_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.vol_slider)
        # -----------------------

        self.btn_settings = QPushButton(self)
        self.btn_settings.setIcon(QIcon(os.path.join(icons_dir_global, "gear-color.svg")))
        self.btn_settings.setIconSize(QSize(14, 14))
        self.btn_settings.setFixedSize(24, 24)
        self.btn_settings.setStyleSheet("""
            QPushButton { 
                background: transparent; 
                border: 1px solid #444; 
                border-radius: 4px; 
                padding: 2px;
            }
            QPushButton:hover { border-color: #666; background-color: #333; }
            QPushButton:checked { background-color: #3b82f6; border-color: #3b82f6; }
        """)
        self.btn_settings.setCheckable(True)
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.setToolTip(AppContext.tr("tooltip_player_settings"))
        self.btn_settings.clicked.connect(self.toggle_settings_popup)
        self.btn_settings.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.btn_settings)

        self.popup = PlayerSettingsPopup(self)
        self.popup.hide()
        self.popup.speed_changed.connect(self.speed_changed.emit)
        self.popup.loop_toggled.connect(self.loop_toggled.emit)
        self.popup.apply_all_toggled.connect(self.apply_all_toggled.emit)
        self.popup.closed.connect(self._on_popup_closed)

        self.app_reference = None

        # Инициализация таймера для дросселирования сигналов перемотки (seek throttling)
        self._seek_timer: QTimer = QTimer(self)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.setInterval(40) # Задержка в 40 мс (дросселирование)
        self._seek_timer.timeout.connect(self._emit_throttled_seek)
        self._pending_seek_val: int = -1

    def update_ui_text(self):
        self.btn_settings.setToolTip(AppContext.tr("tooltip_player_settings"))
        self.popup.update_ui_text()

    def set_app_reference(self, app):
        self.app_reference = app

    def toggle_settings_popup(self):
        if self.btn_settings.isChecked():
            btn_pos = self.btn_settings.mapToGlobal(QPoint(0, 0))
            x = btn_pos.x() - self.btn_settings.width() - self.popup.width() + 10 # Align to left of button
            y = btn_pos.y() - self.popup.height() - 5
            self.popup.move(x, y)
            self.popup.show()
            self.popup.raise_()
        else:
            self.popup.hide()

    def _on_popup_closed(self):
        cursor_pos = QCursor.pos()
        btn_rect = self.btn_settings.frameGeometry()
        
        top_left = self.btn_settings.mapToGlobal(QPoint(0,0))
        btn_global_rect = QRectF(QPointF(top_left), QSizeF(btn_rect.width(), btn_rect.height()))
        
        if not btn_global_rect.contains(QPointF(cursor_pos)):
             self.btn_settings.setChecked(False)

    def set_popup_values(self, speed, loop, apply_all, is_video):
        self.popup.set_values(speed, loop, apply_all)
        self.popup.set_mode(is_video)

    def reset_controls(self):
        if self.popup.isVisible():
            self.popup.hide()
            self.btn_settings.setChecked(False)

    def _on_drag_start(self) -> None:
        self.is_seeking = True
        self.seek_drag_start.emit()
    
    def _on_drag_stop(self) -> None:
        self.is_seeking = False
        if self._seek_timer.isActive():
            self._seek_timer.stop()
            self._emit_throttled_seek()
        self.seek_drag_stop.emit()

    def _on_seeker_moved(self, val: int) -> None:
        self._pending_seek_val = val
        if not self._seek_timer.isActive():
            self._seek_timer.start()

    def _emit_throttled_seek(self) -> None:
        if self._pending_seek_val != -1:
            self.seek_moved.emit(self._pending_seek_val)
            self._pending_seek_val = -1
        
    def set_playing_state(self, is_playing):
        self.btn_play.setIcon(self.icon_pause if is_playing else self.icon_play)

    def update_position(self, position):
        if not self.is_seeking:
            self.seeker.setValue(position)

    def update_duration(self, duration):
        self.seeker.setRange(0, duration)

    def toggle_mute(self):
        if self.is_muted:
            self.is_muted = False
            self.vol_slider.setValue(self.saved_volume)
        else:
            current_val = self.vol_slider.value()
            if current_val > 0:
                self.saved_volume = current_val
            self.is_muted = True
            self.vol_slider.setValue(0)
            
    def _on_volume_slider_changed(self, val):
        if val > 0:
            self.is_muted = False
            self.saved_volume = val
        else:
            self.is_muted = True
            
        self.update_mute_icon(val)
        self.volume_changed.emit(val)

    def update_mute_icon(self, val):
        if val == 0 or self.is_muted:
            self.btn_mute.setIcon(self.icon_speaker_off)
        else:
            self.btn_mute.setIcon(self.icon_speaker)
