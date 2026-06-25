from PyQt6.QtWidgets import QFrame, QSlider, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QCheckBox, QStyle, QStyleOptionSlider
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QPointF, QRect, QSize
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QIcon
from config import AppContext, VIEWER_DESIGN, APP_DESIGN


class WaveformProgressWidget(QFrame):
    markers_changed = pyqtSignal(list, bool)
    seek_requested = pyqtSignal(float)
    scrub_started = pyqtSignal()
    scrub_finished = pyqtSignal()
    marker_selected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background-color: #1a1a1a; border-radius: 6px;")

        self.pixmap = None
        self.markers = []
        self.is_inverted = False
        self.selected_idx = -1
        self.playback_pos = -1.0

        self.is_dragging = False
        self.drag_idx = -1
        self.is_scrubbing = False

        self.green_color = QColor(74, 222, 128, 120)
        self.red_color = QColor(239, 68, 68, 120)
        self.handle_color = QColor(VIEWER_DESIGN['slider_handle_color'])
        self.selected_color = QColor("#ffffff")
        self.playhead_color = self.handle_color

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def set_waveform(self, pixmap):
        self.pixmap = pixmap
        self.update()

    def clear_markers(self):
        self.markers = []
        self.selected_idx = -1
        self.update_states()

    def add_marker(self, pos: float):
        """Add a marker (0.0‑1.0) and keep the list sorted."""
        self.markers.append(pos)
        self.markers.sort()
        self.selected_idx = self.markers.index(pos)
        self.update_states()

    def delete_selected(self):
        if 0 <= self.selected_idx < len(self.markers):
            self.markers.pop(self.selected_idx)
            self.selected_idx = -1
            self.update_states()

    def toggle_inversion(self):
        self.is_inverted = not self.is_inverted
        self.update_states()

    def set_playback_pos(self, pos: float):
        self.playback_pos = pos
        self.update()

    # ---------------------------------------------------------------------
    # Internals
    # ---------------------------------------------------------------------
    def update_states(self):
        self._update_playhead_color()
        self.markers_changed.emit(self.markers, self.is_inverted)
        self.marker_selected.emit(self.selected_idx)
        self.update()

    def _update_playhead_color(self):
        self.playhead_color = QColor("#000000") if self.markers else self.handle_color

    # ---------------------------------------------------------------------
    # Event handling
    # ---------------------------------------------------------------------
    def mousePressEvent(self, event):
        x = event.pos().x()
        y = event.pos().y()
        w = self.width()
        p = max(0.0, min(1.0, x / w))

        margin = 15
        clicked_idx = -1
        for i, m in enumerate(self.markers):
            if abs(x - m * w) < margin:
                clicked_idx = i
                break

        if clicked_idx != -1:
            self.selected_idx = clicked_idx
            if y < 15:
                self.delete_selected()
                return
            self.drag_idx = clicked_idx
            self.is_dragging = True
            self.update_states()
        else:
            if self.selected_idx != -1:
                self.selected_idx = -1
                self.update_states()
            self.is_scrubbing = True
            self.scrub_started.emit()
            self.seek_requested.emit(p)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        x = event.pos().x()
        w = self.width()
        p = max(0.0, min(1.0, x / w))

        if self.is_dragging and 0 <= self.drag_idx < len(self.markers):
            lower = self.markers[self.drag_idx - 1] if self.drag_idx > 0 else 0.0
            upper = self.markers[self.drag_idx + 1] if self.drag_idx < len(self.markers) - 1 else 1.0
            self.markers[self.drag_idx] = max(lower + 0.001, min(upper - 0.001, p))
            self.update_states()
            self.seek_requested.emit(p)
        elif self.is_scrubbing:
            self.seek_requested.emit(p)
        self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.is_scrubbing:
            self.is_scrubbing = False
            self.scrub_finished.emit()
        self.is_dragging = False
        self.drag_idx = -1
        super().mouseReleaseEvent(event)

    # ---------------------------------------------------------------------
    # Visualisation
    # ---------------------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Waveform background
        if self.pixmap:
            painter.drawPixmap(self.rect(), self.pixmap)

        # Highlight segments
        if self.markers:
            if len(self.markers) == 2:
                start, end = self.markers[0], self.markers[1]
                if start > end:
                    start, end = end, start
                x_start = int(start * w)
                x_end = int(end * w)
                red = self.red_color if not self.is_inverted else self.green_color
                green = self.green_color if not self.is_inverted else self.red_color
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(red))
                painter.drawRect(0, 0, x_start, h)
                painter.setBrush(QBrush(green))
                painter.drawRect(x_start, 0, x_end - x_start, h)
                painter.setBrush(QBrush(red))
                painter.drawRect(x_end, 0, w - x_end, h)
            else:
                segments = [0.0] + self.markers + [1.0]
                for i in range(len(segments) - 1):
                    s1, s2 = segments[i], segments[i + 1]
                    x1, x2 = int(s1 * w), int(s2 * w)
                    take = (i % 2 == 0)
                    if self.is_inverted:
                        take = not take
                    color = self.green_color if take else self.red_color
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QBrush(color))
                    painter.drawRect(x1, 0, x2 - x1, h)

        # Playback head
        if self.playback_pos >= 0:
            x = int(self.playback_pos * w)
            painter.setPen(QPen(self.playhead_color, 2))
            painter.drawLine(x, 0, x, h)
            painter.setBrush(QBrush(self.playhead_color))
            painter.drawPolygon([QPointF(x - 5, 0), QPointF(x + 5, 0), QPointF(x, 7)])

        # Markers / handles
        for i, m in enumerate(self.markers):
            x = int(m * w)
            is_sel = (i == self.selected_idx)
            color = self.selected_color if is_sel else self.handle_color
            painter.setPen(QPen(Qt.GlobalColor.white, 1))
            painter.setBrush(QBrush(color))
            painter.drawLine(x, 0, x, h)
            painter.drawRect(x - 8, 0, 16, 15)
            arrow_poly = [QPointF(x - 4, h - 6), QPointF(x + 4, h - 6), QPointF(x, h)]
            painter.drawPolygon(arrow_poly)
            painter.setPen(QPen(QColor(0, 0, 0), 1))
            font = painter.font()
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(QRect(x - 8, -5, 16, 16), Qt.AlignmentFlag.AlignCenter, "×")
        super().paintEvent(event)


class MagneticSlider(QSlider):
    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None, snap_values=None):
        super().__init__(orientation, parent)
        self.snap_values = snap_values if snap_values is not None else [10, 50, 100, 150, 200, 300, 400, 500, 600]
        self.snap_threshold = 10
        self.setStyleSheet(f"""
            QSlider {{
                height: 20px;
            }}
            QSlider::groove:horizontal {{
                background: #333;
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {APP_DESIGN['accent_color']};
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }}
            QSlider::handle:horizontal:hover {{
                background: #60a5fa;
            }}
            QSlider::sub-page:horizontal {{
                background: {APP_DESIGN['accent_color']};
                border-radius: 2px;
            }}
        """)

    def setSnapValues(self, values):
        self.snap_values = values

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            style = self.style()
            sr = style.subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self)
            if not sr.contains(event.position().toPoint()):
                val = style.sliderValueFromPosition(
                    self.minimum(), self.maximum(),
                    int(event.position().x()), self.width()
                )
                self.setValue(val)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        val = self.value()
        if not self.snap_values:
            return
        nearest = min(self.snap_values, key=lambda x: abs(x - val))
        if abs(nearest - val) <= self.snap_threshold:
            self.setValue(nearest)
            self.valueChanged.emit(nearest)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        # Only snap during movement if the user is dragging and there are snap values
        if not self.snap_values:
            return
        val = self.value()
        nearest = min(self.snap_values, key=lambda x: abs(x - val))
        if abs(nearest - val) <= self.snap_threshold:
            self.setValue(nearest)


class PlaybackSettingsPopup(QFrame):
    settings_changed = pyqtSignal(float, bool)  # rate, loop
    closed = pyqtSignal()

    def __init__(self, current_rate, current_loop, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.rate = current_rate
        self.loop = current_loop
        self.setFixedSize(160, 90)
        self.init_ui()

    def init_ui(self):
        self.container = QFrame(self)
        self.container.setGeometry(0, 0, 160, 90)
        self.container.setStyleSheet("""
            QFrame { background: #1e1e1e; border: 1px solid #444; border-radius: 6px; }
            QLabel { color: #ccc; font-size: 11px; font-weight: bold; background: transparent; border: none; }
            QCheckBox { color: #ccc; font-size: 11px; spacing: 5px; background: transparent; border: none; }
            QCheckBox::indicator { width: 13px; height: 13px; border: 1px solid #555; border-radius: 2px; background: #333; }
            QCheckBox::indicator:checked { background: #3b82f6; border-color: #3b82f6; }
            QPushButton { background: #333; color: white; border: 1px solid #555; border-radius: 3px; font-size: 10px; font-weight: bold; }
            QPushButton:hover { background-color: #444; }
        """)
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)
        # Rate row
        rate_row = QHBoxLayout()
        btn_reset = QPushButton(AppContext.tr("btn_speed_reset"))
        btn_reset.setFixedSize(20, 16)
        btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reset.clicked.connect(self._reset_rate)
        rate_row.addWidget(btn_reset)
        self.lbl_rate = QLabel(AppContext.tr("lbl_speed").format(self.rate))
        rate_row.addWidget(self.lbl_rate)
        rate_row.addStretch()
        layout.addLayout(rate_row)
        # Speed slider
        self.slider_speed = MagneticSlider(Qt.Orientation.Horizontal)
        self.slider_speed.setRange(10, 600)
        self.slider_speed.setValue(int(self.rate * 100))
        self.slider_speed.valueChanged.connect(self._on_rate_change)
        self.slider_speed.setFixedHeight(18)
        layout.addWidget(self.slider_speed)
        # Loop checkbox
        self.chk_loop = QCheckBox(AppContext.tr("chk_loop_media"))
        self.chk_loop.setChecked(self.loop)
        self.chk_loop.toggled.connect(self._on_loop_toggle)
        layout.addWidget(self.chk_loop)

    def hideEvent(self, event):
        self.closed.emit()
        super().hideEvent(event)

    def set_values(self, rate, loop):
        self.blockSignals(True)
        self.slider_speed.blockSignals(True)
        self.chk_loop.blockSignals(True)
        self.rate = rate
        self.loop = loop
        self.slider_speed.setValue(int(rate * 100))
        self.lbl_rate.setText(AppContext.tr("lbl_speed").format(self.rate))
        self.chk_loop.setChecked(loop)
        self.blockSignals(False)
        self.slider_speed.blockSignals(False)
        self.chk_loop.blockSignals(False)

    def _reset_rate(self):
        self.slider_speed.setValue(100)

    def _on_rate_change(self, val):
        self.rate = val / 100.0
        self.lbl_rate.setText(AppContext.tr("lbl_speed").format(self.rate))
        self.settings_changed.emit(self.rate, self.loop)

    def _on_loop_toggle(self, checked):
        self.loop = checked
        self.settings_changed.emit(self.rate, self.loop)


class CollapsibleSection(QFrame):
    def __init__(self, title: str, parent=None, icon_path: str | None = None, tooltip: str | None = None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("background: transparent; border: none; margin: 0; padding: 0;")
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Header button
        self.btn_header = QPushButton(self)
        if icon_path:
            self.btn_header.setIcon(QIcon(icon_path))
            self.btn_header.setIconSize(QSize(18, 18))
        if tooltip:
            self.btn_header.setToolTip(tooltip)
        self.btn_header.setText(f"▼  {title.upper()}")
        self.btn_header.setFixedHeight(28)
        self.btn_header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_header.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                border: 1px solid #3b82f6;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
                font-size: 11px;
                font-weight: bold;
                text-align: left;
                padding-left: 8px;
            }
            QPushButton:hover {
                background-color: #2563eb;
                color: white;
                border-color: #2563eb;
            }
        """)
        self.btn_header.clicked.connect(self.toggle_expanded)
        self.main_layout.addWidget(self.btn_header)
        
        # Content container
        self.content_container = QFrame(self)
        self.content_container.setStyleSheet("background-color: #1a1a1a; border: 1px solid #252525; border-top: none; border-bottom-left-radius: 4px; border-bottom-right-radius: 4px;")
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(6, 6, 6, 6)
        self.content_layout.setSpacing(6)
        self.main_layout.addWidget(self.content_container)
        
        self.is_expanded = True
        self.title_text = title

    def set_content_layout(self, layout):
        if self.content_container.layout():
            # Reparent old layout to garbage widget
            QWidget().setLayout(self.content_container.layout())
        self.content_container.setLayout(layout)
        self.content_layout = layout

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)

    def add_layout(self, layout):
        self.content_layout.addLayout(layout)

    def toggle_expanded(self):
        self.set_expanded(not self.is_expanded)

    def set_expanded(self, expanded: bool):
        self.is_expanded = expanded
        if self.is_expanded:
            self.btn_header.setText(f"▼  {self.title_text.upper()}")
            self.content_container.show()
            self.btn_header.setStyleSheet("""
                QPushButton {
                    background-color: #3b82f6;
                    color: white;
                    border: 1px solid #3b82f6;
                    border-bottom: none;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                    border-bottom-left-radius: 0px;
                    border-bottom-right-radius: 0px;
                    font-size: 11px;
                    font-weight: bold;
                    text-align: left;
                    padding-left: 8px;
                }
                QPushButton:hover {
                    background-color: #2563eb;
                    color: white;
                    border-color: #2563eb;
                }
            """)
        else:
            self.btn_header.setText(f"▶  {self.title_text.upper()}")
            self.content_container.hide()
            self.btn_header.setStyleSheet("""
                QPushButton {
                    background-color: #252525;
                    color: #ddd;
                    border: 1px solid #333;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: bold;
                    text-align: left;
                    padding-left: 8px;
                }
                QPushButton:hover {
                    background-color: #3b82f6;
                    color: white;
                    border-color: #3b82f6;
                }
            """)

    def update_text(self, new_title: str, new_tooltip: str | None = None) -> None:
        self.title_text = new_title
        arrow = "▼" if self.is_expanded else "▶"
        self.btn_header.setText(f"{arrow}  {new_title.upper()}")
        if new_tooltip:
            self.btn_header.setToolTip(new_tooltip)

