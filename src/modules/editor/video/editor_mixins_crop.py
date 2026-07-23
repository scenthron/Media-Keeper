
from PyQt6.QtWidgets import QGraphicsRectItem
from PyQt6.QtGui import QColor, QPen, QBrush
from PyQt6.QtCore import Qt, QPointF

class EditorCropMixin:
    """Logic related to crop mode, handles, spinboxes and locked size mode."""

    def toggle_crop_mode(self, checked):
        self.is_cropping = checked
        if hasattr(self, 'widget_crop_controls'):
            self.widget_crop_controls.setVisible(checked)
        for s in [self.spin_crop_x, self.spin_crop_y, self.spin_crop_w, self.spin_crop_h]:
            s.setEnabled(checked and not self.is_crop_locked_size)
        self.btn_crop_lock_size.setEnabled(checked)
            
        if checked:
            self.center_video() 
            rect = self.video_item.boundingRect()
            w, h = rect.width(), rect.height()
            self.spin_crop_x.setRange(0, int(w) - 10)
            self.spin_crop_y.setRange(0, int(h) - 10)
            self.spin_crop_w.setRange(10, int(w))
            self.spin_crop_h.setRange(10, int(h))

            self.handle_tl.setPos(w * 0.1, h * 0.1)
            self.handle_br.setPos(w * 0.9, h * 0.9)

            if not self.is_crop_locked_size:
                self.handle_tl.show()
                self.handle_br.show()
            self._enable_crop_drag_mode()
            self._update_crop_spins_from_handles()
            self._update_dimming()
            
            if not hasattr(self, 'crop_anim_timer'):
                from PyQt6.QtCore import QTimer
                self.crop_anim_timer = QTimer(self)
                self.crop_anim_timer.setInterval(40)
                self.crop_anim_timer.timeout.connect(self._animate_crop_stripes)
                self._crop_stripe_offset = 0
            self.crop_anim_timer.start()
        else:
            self.handle_tl.hide()
            self.handle_br.hide()
            self._disable_crop_drag_mode()
            self._update_dimming()
            if hasattr(self, 'crop_anim_timer'):
                self.crop_anim_timer.stop()
                
        self._update_crop_controls_enabled()
        self._check_start_readiness()

    def _toggle_crop_lock_size(self, checked):
        self.is_crop_locked_size = checked
        if checked:
            if self.is_cropping: self._apply_crop_lock_size()
        else:
            if self.is_cropping: self._disable_crop_lock_size()
        self._update_crop_button_styles()
        self._update_crop_controls_enabled()
        if self.is_cropping: self._update_dimming()

    def _apply_crop_lock_size(self):
        if not self.is_cropping: return
        self.spin_crop_w.setEnabled(False)
        self.spin_crop_h.setEnabled(False)
        self.handle_tl.hide()
        self.handle_br.hide()
        self._enable_crop_drag_mode()
        self._update_crop_controls_enabled()

    def _disable_crop_lock_size(self):
        if not self.is_cropping: return
        self.handle_tl.show()
        self.handle_br.show()
        self._disable_crop_drag_mode()

    def _enable_crop_drag_mode(self):
        if not hasattr(self, 'crop_drag_rect'):
            self.crop_drag_rect = QGraphicsRectItem(self.video_item)
            self.crop_drag_rect.setBrush(QBrush(QColor(255, 255, 255, 1)))  
            self.crop_drag_rect.setPen(QPen(Qt.PenStyle.NoPen))
            self.crop_drag_rect.setZValue(15)  
            self.crop_drag_rect.setCursor(Qt.CursorShape.SizeAllCursor)

        tl = self.handle_tl.pos()
        br = self.handle_br.pos()
        self.crop_drag_rect.setRect(tl.x(), tl.y(), br.x() - tl.x(), br.y() - tl.y())
        self.crop_drag_rect.show()
        self.crop_drag_rect.mousePressEvent = self._crop_drag_mouse_press
        self.crop_drag_rect.mouseMoveEvent = self._crop_drag_mouse_move
        self.crop_drag_rect.mouseReleaseEvent = self._crop_drag_mouse_release

    def _disable_crop_drag_mode(self):
        if hasattr(self, 'crop_drag_rect'):
            self.crop_drag_rect.hide()

    def _crop_drag_mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging_crop_area = True
            self.drag_start_pos = event.scenePos()
            tl = self.handle_tl.pos()
            self.crop_area_start_pos = QPointF(tl.x(), tl.y())
            event.accept()

    def _crop_drag_mouse_move(self, event):
        if self.is_dragging_crop_area:
            delta = event.scenePos() - self.drag_start_pos
            rect = self.video_item.boundingRect()
            current_w = self.handle_br.x() - self.handle_tl.x()
            current_h = self.handle_br.y() - self.handle_tl.y()
            new_x = self.crop_area_start_pos.x() + delta.x()
            new_y = self.crop_area_start_pos.y() + delta.y()
            new_x = max(0, min(new_x, rect.width() - current_w))
            new_y = max(0, min(new_y, rect.height() - current_h))
            self.handle_tl.setPos(new_x, new_y)
            self.handle_br.setPos(new_x + current_w, new_y + current_h)
            self.crop_drag_rect.setRect(new_x, new_y, current_w, current_h)
            self._update_crop_spins_from_handles()
            self._update_dimming()
            event.accept()

    def _crop_drag_mouse_release(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging_crop_area = False
            event.accept()

    def _update_crop_button_styles(self):
        if self.is_crop_locked_size:
            self.btn_crop_lock_size.setStyleSheet(
                "QPushButton { background: #7f1d1d; border: 1px solid #ef4444; border-radius: 6px; }"
                "QPushButton:hover { background: #991b1b; }"
            )
        else:
            self.btn_crop_lock_size.setStyleSheet(
                "QPushButton { background: #2a2a3e; border: 1px solid #3a3a5a; border-radius: 6px; }"
                "QPushButton:hover { background: #3a3a5a; border-color: #4ade80; }"
                "QPushButton:disabled { opacity: 0.4; }"
            )

    def _update_crop_controls_enabled(self):
        is_audio = getattr(self, 'is_audio_only', False)
        enabled = self.is_video_loaded and not is_audio
        
        self.btn_crop.setEnabled(enabled)
        crop_controls_enabled = enabled and self.is_cropping
        self.btn_crop_lock_size.setEnabled(crop_controls_enabled)

        _style_active = (
            "QSpinBox { background: #1e1e2e; color: #a0f0a0; border: 1px solid #3a3a5a;"
            "  border-radius: 6px; font-size: 12px; font-weight: bold; padding: 2px 2px 2px 6px; }"
            "QSpinBox:focus { border-color: #4ade80; }"
            "QSpinBox::up-button, QSpinBox::down-button { width: 18px; background: #2a2a3e; border: none; }"
            "QSpinBox::up-button { border-top-right-radius: 5px; }"
            "QSpinBox::down-button { border-bottom-right-radius: 5px; }"
            "QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: #3a3a5a; }"
            f"QSpinBox::up-arrow {{ image: url('{self.chevron_paths['up_active']}'); width: 10px; height: 10px; }}"
            f"QSpinBox::down-arrow {{ image: url('{self.chevron_paths['down_active']}'); width: 10px; height: 10px; }}"
        )
        _style_locked = (
            "QSpinBox { background: #1e1212; color: #ff6b6b; border: 1px solid #7f1d1d;"
            "  border-radius: 6px; font-size: 12px; font-weight: bold; padding: 2px 2px 2px 6px; }"
            "QSpinBox::up-button, QSpinBox::down-button { width: 18px; background: #2a1a1a; border: none; }"
            "QSpinBox::up-button { border-top-right-radius: 5px; }"
            "QSpinBox::down-button { border-bottom-right-radius: 5px; }"
            f"QSpinBox::up-arrow {{ image: url('{self.chevron_paths['up_locked']}'); width: 10px; height: 10px; }}"
            f"QSpinBox::down-arrow {{ image: url('{self.chevron_paths['down_locked']}'); width: 10px; height: 10px; }}"
        )
        _style_disabled = (
            "QSpinBox { background: #181820; color: #3a4a3a; border: 1px solid #2a2a3a;"
            "  border-radius: 6px; font-size: 12px; font-weight: bold; padding: 2px 2px 2px 6px; }"
            "QSpinBox::up-button, QSpinBox::down-button { width: 18px; background: #1e1e28; border: none; }"
            f"QSpinBox::up-arrow {{ image: url('{self.chevron_paths['up_disabled']}'); width: 10px; height: 10px; }}"
            f"QSpinBox::down-arrow {{ image: url('{self.chevron_paths['down_disabled']}'); width: 10px; height: 10px; }}"
        )

        if crop_controls_enabled:
            self.spin_crop_x.setEnabled(True)
            self.spin_crop_y.setEnabled(True)
            self.spin_crop_w.setEnabled(not self.is_crop_locked_size)
            self.spin_crop_h.setEnabled(not self.is_crop_locked_size)
            self.spin_crop_x.setStyleSheet(_style_active)
            self.spin_crop_y.setStyleSheet(_style_active)
            if self.is_crop_locked_size:
                self.spin_crop_w.setStyleSheet(_style_locked)
                self.spin_crop_h.setStyleSheet(_style_locked)
            else:
                self.spin_crop_w.setStyleSheet(_style_active)
                self.spin_crop_h.setStyleSheet(_style_active)
        else:
            for spin in self.crop_spins:
                spin.setEnabled(False)
                spin.setStyleSheet(_style_disabled)

    def _on_crop_spin_changed(self):
        if not self.is_cropping: return
        self.handle_tl.blockSignals(True)
        self.handle_br.blockSignals(True)
        rect = self.video_item.boundingRect()
        w_max, h_max = rect.width(), rect.height()
        x = max(0, min(self.spin_crop_x.value(), w_max - 10))
        y = max(0, min(self.spin_crop_y.value(), h_max - 10))
        w = max(10, min(self.spin_crop_w.value(), w_max - x))
        h = max(10, min(self.spin_crop_h.value(), h_max - y))
        
        self.spin_crop_x.blockSignals(True)
        self.spin_crop_y.blockSignals(True)
        self.spin_crop_w.blockSignals(True)
        self.spin_crop_h.blockSignals(True)
        self.spin_crop_x.setValue(x)
        self.spin_crop_y.setValue(y)
        self.spin_crop_w.setValue(int(w))
        self.spin_crop_h.setValue(int(h))
        self.spin_crop_x.blockSignals(False)
        self.spin_crop_y.blockSignals(False)
        self.spin_crop_w.blockSignals(False)
        self.spin_crop_h.blockSignals(False)
        
        self.handle_tl.setPos(x, y)
        self.handle_br.setPos(x + w, y + h)
        self.handle_tl.blockSignals(False)
        self.handle_br.blockSignals(False)
        self._update_dimming()
        self._check_start_readiness()

    def _update_crop_spins_from_handles(self):
        self.spin_crop_x.blockSignals(True)
        self.spin_crop_y.blockSignals(True)
        self.spin_crop_w.blockSignals(True)
        self.spin_crop_h.blockSignals(True)
        tl = self.handle_tl.pos()
        br = self.handle_br.pos()
        self.spin_crop_x.setValue(int(tl.x()))
        self.spin_crop_y.setValue(int(tl.y()))
        self.spin_crop_w.setValue(int(br.x() - tl.x()))
        self.spin_crop_h.setValue(int(br.y() - tl.y()))
        self.spin_crop_x.blockSignals(False)
        self.spin_crop_y.blockSignals(False)
        self.spin_crop_w.blockSignals(False)
        self.spin_crop_h.blockSignals(False)

    def _on_crop_moved(self):
        if self.is_crop_locked_size:
            self._update_crop_spins_from_handles()
            self._update_dimming()
            return
        self.handle_tl.blockSignals(True)
        self.handle_br.blockSignals(True)
        desired_tl = self.handle_tl.pos()
        desired_br = self.handle_br.pos()
        rect = self.video_item.boundingRect()
        video_w, video_h = rect.width(), rect.height()
        desired_tl.setX(max(0, min(desired_tl.x(), video_w - 10)))
        desired_tl.setY(max(0, min(desired_tl.y(), video_h - 10)))
        min_br_x = desired_tl.x() + 10
        min_br_y = desired_tl.y() + 10
        desired_br.setX(max(min_br_x, min(desired_br.x(), video_w)))
        desired_br.setY(max(min_br_y, min(desired_br.y(), video_h)))
        self.handle_tl.setPos(desired_tl)
        self.handle_br.setPos(desired_br)
        self.handle_tl.blockSignals(False)
        self.handle_br.blockSignals(False)
        self._update_crop_spins_from_handles()
        self._update_dimming()
        self._check_start_readiness()

    def _get_crop_stripe_brush(self, is_locked):
        from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QBrush
        size = 40
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(0, 0, 0, 160)) # Semi-transparent black background
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        stripe_color = QColor(255, 68, 68, 120) if is_locked else QColor(255, 68, 68, 40)
        pen = QPen(stripe_color, 8)
        painter.setPen(pen)
        
        painter.drawLine(0, size, size, 0)
        painter.drawLine(0, 0, size, -size)
        painter.drawLine(0, size*2, size*2, 0)
        
        painter.end()
        return QBrush(pixmap)

    def _animate_crop_stripes(self):
        if not hasattr(self, '_crop_stripe_offset'):
            self._crop_stripe_offset = 0
        self._crop_stripe_offset += 1
        if self._crop_stripe_offset >= 40:
            self._crop_stripe_offset = 0
            
        from PyQt6.QtGui import QTransform
        transform = QTransform().translate(self._crop_stripe_offset, 0)
        if hasattr(self, '_crop_brush'):
            self._crop_brush.setTransform(transform)
            for d in [self.crop_dim_top, self.crop_dim_bottom, self.crop_dim_left, self.crop_dim_right]:
                d.setBrush(self._crop_brush)

    def _update_dimming(self):
        if not self.is_cropping:
            for d in [self.crop_dim_top, self.crop_dim_bottom, self.crop_dim_left, self.crop_dim_right]:
                d.hide()
            if hasattr(self, 'lbl_crop_size'):
                self.lbl_crop_size.setText("")
            return
            
        tl = self.handle_tl.pos()
        br = self.handle_br.pos()
        v_rect = self.video_item.boundingRect()
        vw, vh = v_rect.width(), v_rect.height()
        self.crop_dim_top.setRect(0, 0, vw, tl.y())
        self.crop_dim_bottom.setRect(0, br.y(), vw, vh - br.y())
        self.crop_dim_left.setRect(0, tl.y(), tl.x(), br.y() - tl.y())
        self.crop_dim_right.setRect(br.x(), tl.y(), vw - br.x(), br.y() - tl.y())
        
        if not hasattr(self, '_crop_brush') or getattr(self, '_last_crop_lock_state', None) != self.is_crop_locked_size:
            self._crop_brush = self._get_crop_stripe_brush(self.is_crop_locked_size)
            self._last_crop_lock_state = self.is_crop_locked_size
            
        for d in [self.crop_dim_top, self.crop_dim_bottom, self.crop_dim_left, self.crop_dim_right]:
            # Apply current offset if it exists
            if hasattr(self, '_crop_stripe_offset'):
                from PyQt6.QtGui import QTransform
                self._crop_brush.setTransform(QTransform().translate(self._crop_stripe_offset, 0))
            d.setBrush(self._crop_brush)
            d.show()
            
        if hasattr(self, 'lbl_crop_size'):
            self.lbl_crop_size.setText(f"{self.spin_crop_w.value()} × {self.spin_crop_h.value()} px")
