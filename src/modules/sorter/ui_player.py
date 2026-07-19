import os
import logging
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QSlider, QStyle, QStyleOptionSlider, 
    QLabel, QCheckBox
)
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QRectF, QPointF, QSizeF, QSize, QTimer, QTimeLine
from PyQt6.QtGui import QCursor, QIcon, QPainter, QPixmap, QColor, QPen, QBrush, QFont, QPainterPath, QMouseEvent
from config import AppContext, VIEWER_DESIGN

class SegmentIndicatorWidget(QPushButton):
    def __init__(self, parent=None, is_small=False):
        super().__init__("", parent)
        self.is_small = is_small
        
        tooltip_ru = (
            "<div style='font-size: 14px; color: white; padding: 2px;'>"
            "<b>Сегментный режим просмотра</b><br><br>"
            "Видео делится на равные части, из каждой<br>"
            "показывается фрагмент по 1.5 секунды.<br><br>"
            "<span style='color: #4ade80;'>• Кликните</span> для включения/выключения<br>"
            "<span style='color: #60a5fa;'>• Используйте &lt; &gt;</span> для быстрой навигации"
            "</div>"
        )
        tooltip_en = (
            "<div style='font-size: 14px; color: white; padding: 2px;'>"
            "<b>Segmented View Mode</b><br><br>"
            "Video is divided into equal parts, and<br>"
            "the player shows 1.5s of each part.<br><br>"
            "<span style='color: #4ade80;'>• Click</span> to toggle on/off<br>"
            "<span style='color: #60a5fa;'>• Use &lt; &gt;</span> for quick navigation"
            "</div>"
        )
        self.setToolTip(tooltip_ru if AppContext.LANG == "RU" else tooltip_en)
        
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if self.is_small:
            self.setFixedSize(22, 22)
        else:
            self.setFixedSize(40, 40)
        
        # Base style just to ensure transparent background so we can paint it
        self.setStyleSheet("QPushButton { background: transparent; border: none; outline: none; }")
        
        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self.opacity_effect)
        
        from PyQt6.QtCore import QTimeLine, QEasingCurve
        self.anim = QTimeLine(1500, self)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.anim.valueChanged.connect(self._on_anim_value_changed)
        self.anim.finished.connect(self._on_anim_finished)
        
        self.icon_opacity = 1.0
        self.is_active_mode = False
        
    def _on_anim_value_changed(self, value):
        # value goes from 0.0 to 1.0 (forward) or 1.0 to 0.0 (backward)
        # We want opacity to go from 1.0 to 0.01 and back.
        # When value=0.0 -> opacity=1.0
        # When value=1.0 -> opacity=0.01
        self.icon_opacity = 1.0 - (0.99 * value)
        self.update()
        
    def _on_anim_finished(self):
        if not self.is_active_mode:
            return
        self.anim.toggleDirection()
        self.anim.start()
        
    def start_blinking(self):
        self.is_active_mode = True
        self.show()
        self.opacity_effect.setOpacity(1.0)
        self.anim.setDirection(QTimeLine.Direction.Forward)
        self.anim.start()
        
    def stop_blinking(self, transparent=False):
        self.is_active_mode = False
        self.anim.stop()
        self.icon_opacity = 1.0
        self.update()
        if transparent:
            self.show()
            self.opacity_effect.setOpacity(0.4)
        else:
            self.hide()
            
    def paintEvent(self, event):
        from PyQt6.QtGui import QCursor, QIcon, QPainter, QPixmap, QColor, QPen, QBrush, QFont, QPainterPath, QMouseEvent
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        is_hover = self.underMouse()
        
        if self.is_small:
            if is_hover:
                painter.setBrush(QColor(59, 130, 246, int(255 * 0.4)))
                painter.setPen(QPen(QColor("#3b82f6"), 1))
            else:
                painter.setBrush(QColor(255, 255, 255, int(255 * 0.12)))
                painter.setPen(QPen(QColor(255, 255, 255, int(255 * 0.2)), 1))
                
            painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 4, 4)
            
            painter.setOpacity(self.icon_opacity)
            painter.setPen(QColor(255, 255, 255))
            font = self.font()
            font.setPixelSize(12)
            painter.setFont(font)
            # Offset slightly to center emoji visually
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "🎞️")
            return
            
        # Draw background
        bg_alpha = 204 if is_hover else 127 # 0.8 * 255 = 204, 0.5 * 255 = 127
        painter.setBrush(QColor(0, 0, 0, bg_alpha))
        
        # Draw border
        border_alpha = 204 if is_hover else 76 # 0.8 * 255 = 204, 0.3 * 255 = 76
        painter.setPen(QPen(QColor(255, 255, 255, border_alpha), 1))
        
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 4, 4)
        
        # Draw Icon (text)
        painter.setOpacity(self.icon_opacity)
        painter.setPen(QColor(255, 255, 255))
        
        font = self.font()
        font.setPixelSize(20)
        painter.setFont(font)
        
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "🎞️")

class TimeOverlayWidget(QLabel):

    def _create_colored_icon(self, path, color_str):
        icon = QIcon(path)
        pixmap = icon.pixmap(14, 14)
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor(color_str))
        painter.end()
        return QIcon(pixmap)
        
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 0.6);
                color: white;
                border-radius: 4px;
                padding: 4px 8px;
                font-weight: bold;
                font-size: 10px;
                font-family: 'Segoe UI', sans-serif;
            }
        """)
        self.setText("00:00 / 00:00")
        self.hide()

    def set_time(self, position: int, duration: int):
        pos_sec = position // 1000
        dur_sec = duration // 1000
        
        pos_str = f"{pos_sec // 60:02d}:{pos_sec % 60:02d}"
        if duration > 0:
            dur_str = f"{dur_sec // 60:02d}:{dur_sec % 60:02d}"
        else:
            dur_str = "00:00"
            
        new_text = f"{pos_str} / {dur_str}"
        if self.text() != new_text:
            self.setText(new_text)
            self.adjustSize()


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
        if event.button() == Qt.MouseButton.LeftButton:
            self.seek_drag_start.emit()
            val = self.pixelPosToRangeValue(event.position().x())
            self.setValue(val)
            super().mousePressEvent(event)
            self.seek_requested.emit(val) 
            self.seek_moved.emit(val)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if event.buttons() & Qt.MouseButton.LeftButton:
            val = self.value()
            self.seek_moved.emit(val)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.seek_drag_stop.emit()

    def wheelEvent(self, event):
        # Игнорируем системный множитель (wheelScrollLines), 1 щелчок = ровно 1 шаг
        delta = event.angleDelta().y()
        if delta > 0:
            val = min(self.maximum(), self.value() + self.singleStep())
        elif delta < 0:
            val = max(self.minimum(), self.value() - self.singleStep())
        else:
            return
            
        self.setValue(val)
        self.seek_requested.emit(val)
        self.seek_moved.emit(val)
        event.accept()

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
    custom_released = pyqtSignal()
    
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
        self.custom_released.emit()

class SpeedSettingsPopup(QWidget):
    speed_changed = pyqtSignal(float)
    closed = pyqtSignal()


    def _create_colored_icon(self, path, color_str):
        icon = QIcon(path)
        pixmap = icon.pixmap(14, 14)
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor(color_str))
        painter.end()
        return QIcon(pixmap)
        
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("SpeedSettingsPopup")
        self.setStyleSheet("""
            SpeedSettingsPopup { background-color: #222222; border: 1px solid #444; border-radius: 6px; }
            QLabel { color: #ccc; border: none; font-size: 11px; font-weight: bold; margin: 0px; background: transparent; }
            QPushButton { background-color: #333; color: white; border: 1px solid #555; border-radius: 3px; font-size: 10px; font-weight: bold; }
            QPushButton:hover { background-color: #444; }
            QPushButton#btnOk { background-color: #3b82f6; border-color: #2563eb; }
            QPushButton#btnOk:hover { background-color: #2563eb; }
        """)
        self.setFixedSize(160, 60)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(5)
        
        top_row = QHBoxLayout()
        top_row.setSpacing(5)
        
        self.lbl_speed = QLabel("Скорость: 2.0x")
        self.btn_reset = QPushButton("x2")
        self.btn_reset.setFixedSize(24, 18)
        self.btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset.clicked.connect(self.reset_speed)
        
        top_row.addWidget(self.lbl_speed)
        top_row.addStretch()
        top_row.addWidget(self.btn_reset)
        layout.addLayout(top_row)
        
        self.slider_speed = MagneticSlider(Qt.Orientation.Horizontal)
        self.slider_speed.setRange(1, 60)
        self.slider_speed.setValue(20)
        self.slider_speed.valueChanged.connect(self.on_slider_change)
        self.slider_speed.custom_released.connect(self.hide)
        self.slider_speed.setFixedHeight(16)
        layout.addWidget(self.slider_speed)
        
        self.current_speed_val = 2.0
        self.last_val = 20
        
    def hideEvent(self, event):
        self.closed.emit()
        super().hideEvent(event)
        
    def reset_speed(self):
        self.slider_speed.setValue(20)
        self.hide()
        
    def on_slider_change(self, val):
        if val == 10:
            val = 11 if self.last_val <= 10 else 9
            self.slider_speed.blockSignals(True)
            self.slider_speed.setValue(val)
            self.slider_speed.blockSignals(False)
                
        self.last_val = val
        self.current_speed_val = val / 10.0
        self.lbl_speed.setText(f"Скорость: {self.current_speed_val:.1f}x")
        self.speed_changed.emit(self.current_speed_val)

    def set_value(self, val):
        self.slider_speed.blockSignals(True)
        v = int(val * 10)
        if v == 10: v = 11
        self.slider_speed.setValue(v)
        self.last_val = v
        self.current_speed_val = val
        self.lbl_speed.setText(f"Скорость: {self.current_speed_val:.1f}x")
        self.slider_speed.blockSignals(False)


class SpeedButton(QPushButton):
    rightClicked = pyqtSignal()
    

    def _create_colored_icon(self, path, color_str):
        icon = QIcon(path)
        pixmap = icon.pixmap(14, 14)
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor(color_str))
        painter.end()
        return QIcon(pixmap)
        
    def __init__(self, parent=None):
        super().__init__(parent)
    
    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            self.rightClicked.emit()
            e.accept()
        else:
            super().mouseReleaseEvent(e)


class VideoPlayerControls(QWidget):
    def contextMenuEvent(self, event):
        event.accept()

    play_pause_clicked = pyqtSignal()
    seek_requested = pyqtSignal(int)
    seek_moved = pyqtSignal(int)
    seek_drag_start = pyqtSignal()
    seek_drag_stop = pyqtSignal()
    speed_toggled = pyqtSignal()
    speed_changed = pyqtSignal(float)
    loop_toggled = pyqtSignal(bool)
    volume_changed = pyqtSignal(int)
    

    def _create_colored_icon(self, path, color_str):
        icon = QIcon(path)
        pixmap = icon.pixmap(14, 14)
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor(color_str))
        painter.end()
        return QIcon(pixmap)
        
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setStyleSheet("VideoPlayerControls { background-color: #000000; border-top: 1px solid #333; }")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(10)
        
        icons_dir_global = AppContext.find_resource_dir("icons")
        self.icon_play = QIcon(os.path.join(icons_dir_global, "media_play.svg"))
        self.icon_pause = QIcon(os.path.join(icons_dir_global, "media_pause.svg"))
        self.icon_speaker = QIcon(os.path.join(icons_dir_global, "speaker.svg"))
        self.icon_speaker_off = QIcon(os.path.join(icons_dir_global, "speaker_off.svg"))
        self.icon_loop = self._create_colored_icon(os.path.join(icons_dir_global, "repeat.svg"), "#ffffff")

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
        self.seeker.setRange(0, 100)
        self.seeker.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.is_seeking = False
        
        self.seeker.seek_drag_start.connect(self._on_drag_start)
        self.seeker.seek_drag_stop.connect(self._on_drag_stop)
        self.seeker.seek_moved.connect(self._on_seeker_moved)
        self.seeker.seek_requested.connect(self.seek_requested.emit)
        self.seeker.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.seeker)

        # SPEED BUTTON
        self.btn_speed = SpeedButton(self)
        self.btn_speed.setFixedSize(36, 24)
        self.btn_speed.setCheckable(True)
        self.btn_speed.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_speed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_speed.setStyleSheet("""
            QPushButton { 
                background: transparent; 
                color: #ccc;
                border: 1px solid #444; 
                border-radius: 4px; 
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover { border-color: #666; background-color: #333; }
            QPushButton:checked { background-color: #3b82f6; border-color: #3b82f6; color: white; }
        """)
        self.btn_speed.clicked.connect(self.speed_toggled.emit)
        self.btn_speed.rightClicked.connect(self.toggle_speed_popup)
        layout.addWidget(self.btn_speed)
        
        # LOOP BUTTON
        self.btn_loop = QPushButton(self)
        self.btn_loop.setFixedSize(28, 24)
        self.btn_loop.setCheckable(True)
        self.btn_loop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_loop.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
        self.btn_loop.setIcon(self.icon_loop)
        self.btn_loop.setIconSize(QSize(14, 14))
        self.btn_loop.setStyleSheet("""
            QPushButton { 
                background: transparent; 
                border: 1px solid #444; 
                border-radius: 4px; 
            }
            QPushButton:hover { border-color: #666; background-color: #333; }
            QPushButton:checked { background-color: #3b82f6; border-color: #3b82f6; }
        """)
        self.btn_loop.clicked.connect(self._on_loop_clicked)
        layout.addWidget(self.btn_loop)

        # VOLUME CONTROL
        self.btn_mute = QPushButton(self)
        self.btn_mute.setFixedSize(24, 24)
        self.btn_mute.setIconSize(QSize(14, 14))
        self.btn_mute.setIcon(self.icon_speaker)
        self.btn_mute.setStyleSheet("QPushButton { border: none; background: transparent; padding: 0px; }")
        self.btn_mute.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mute.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_mute.clicked.connect(self.toggle_mute)
        layout.addWidget(self.btn_mute)

        self.vol_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setFixedWidth(60)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(10)
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

        self.popup = SpeedSettingsPopup(self)
        self.popup.hide()
        self.popup.speed_changed.connect(self.speed_changed.emit)
        self.popup.closed.connect(self._on_popup_closed)

        self.app_reference = None
        self._seek_timer = QTimer(self)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.setInterval(40)
        self._seek_timer.timeout.connect(self._emit_throttled_seek)
        self._pending_seek_val = -1
        
        self.update_ui_text()

    def update_ui_text(self):
        self.btn_speed.setToolTip(AppContext.tr("Быстрый просмотр (ЛКМ - вкл/выкл, ПКМ - настройка скорости)"))
        self.btn_loop.setToolTip(AppContext.tr("Повтор медиа"))

    def set_app_reference(self, app):
        self.app_reference = app

    def toggle_speed_popup(self):
        if self.popup.isHidden():
            btn_pos = self.btn_speed.mapToGlobal(QPoint(0, 0))
            x = btn_pos.x() - (self.popup.width() // 2) + (self.btn_speed.width() // 2)
            y = btn_pos.y() - self.popup.height() - 5
            self.popup.move(x, y)
            self.popup.show()
            self.popup.raise_()
        else:
            self.popup.hide()

    def _on_popup_closed(self):
        pass

    def update_speed_button(self, speed_val, is_active):
        self.btn_speed.blockSignals(True)
        self.btn_speed.setChecked(is_active)
        if is_active:
            if float(speed_val).is_integer():
                self.btn_speed.setText(f"x{int(speed_val)}")
            else:
                self.btn_speed.setText(f"x{speed_val:.1f}")
        else:
            self.btn_speed.setText("x1")
        self.btn_speed.blockSignals(False)
        self.popup.set_value(speed_val)
        
    def _on_loop_clicked(self):
        self.loop_toggled.emit(self.btn_loop.isChecked())
        
    def update_loop_button(self, is_loop):
        self.btn_loop.blockSignals(True)
        self.btn_loop.setChecked(is_loop)
        self.btn_loop.blockSignals(False)

    def reset_controls(self):
        if self.popup.isVisible():
            self.popup.hide()

    def _on_drag_start(self):
        self.is_seeking = True
        self.seek_drag_start.emit()
    
    def _on_drag_stop(self):
        self.is_seeking = False
        if self._seek_timer.isActive():
            self._seek_timer.stop()
            self._emit_throttled_seek()
        self.seek_drag_stop.emit()

    def _on_seeker_moved(self, val):
        self._pending_seek_val = val
        if not self._seek_timer.isActive():
            self._seek_timer.start()

    def _emit_throttled_seek(self):
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
