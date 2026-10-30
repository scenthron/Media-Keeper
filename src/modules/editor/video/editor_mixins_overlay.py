
import os
from PyQt6.QtWidgets import QFileDialog, QColorDialog
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPixmap, QMovie, QColor
from config import AppContext

class EditorOverlayMixin:
    """Logic related to overlay mode, type changes, image loading and transparency."""

    def _reset_overlay_to_two_thirds(self) -> None:
        if not self.video_item:
            return
        rect = self.video_item.boundingRect()
        if not rect.isEmpty():
            w, h = rect.width(), rect.height()
            ow, oh = w * (2.0 / 3.0), h * (2.0 / 3.0)
            self.overlay_item.set_rect(QRectF(0, 0, ow, oh))
            self.overlay_item.setPos(w / 2 - ow / 2, h / 2 - oh / 2)

    def _on_overlay_toggled(self, checked: bool) -> None:
        self.overlay_enabled = checked
        self.combo_overlay_type.setEnabled(checked)
        self.slider_overlay_val.setEnabled(checked)
        self.spin_overlay_val.setEnabled(checked)
        self.widget_overlay_img.setEnabled(checked)
        self.widget_overlay_reg.setEnabled(checked)
        
        if checked:
            self.overlay_item.show()
            # If current size is default 200x200 or no image path, make it 2/3
            is_default = (self.overlay_item.get_rect().width() == 200)
            is_img_mode = (self.combo_overlay_type.currentIndex() == 0)
            has_no_img = not getattr(self, 'overlay_image_path', None)
            
            if is_default or not is_img_mode or has_no_img:
                self._reset_overlay_to_two_thirds()
                
            self._on_overlay_type_changed(self.combo_overlay_type.currentIndex())
        else:
            self.overlay_item.hide()
            
        self._check_start_readiness()
        self._schedule_cc_preview()

    def _on_overlay_type_changed(self, idx: int) -> None:
        types = ["image", "region", "blur"]
        self.overlay_type = types[idx]
        self.widget_overlay_img.setVisible(self.overlay_type == "image")
        self.widget_overlay_reg.setVisible(self.overlay_type == "region")
        self.overlay_item.set_mode(self.overlay_type)
        
        if self.overlay_type == "image":
            self.lbl_overlay_val.setText(AppContext.tr("ovl_opacity"))
            self.slider_overlay_val.setValue(100) 
            # If image is selected, scale it. Otherwise reset to 2/3
            img_path = getattr(self, 'overlay_image_path', None)
            if img_path and os.path.exists(img_path):
                self._on_reset_overlay_size()
            else:
                self._reset_overlay_to_two_thirds()
        elif self.overlay_type == "region":
            self.lbl_overlay_val.setText(AppContext.tr("ovl_opacity"))
            self.slider_overlay_val.setValue(50) 
            self._reset_overlay_to_two_thirds()
        elif self.overlay_type == "blur":
            self.lbl_overlay_val.setText(AppContext.tr("ovl_blur_strength"))
            self.slider_overlay_val.setValue(100) 
            self._reset_overlay_to_two_thirds()
            
        self._on_overlay_val_changed(self.slider_overlay_val.value()) 
        self._check_start_readiness()
        self._schedule_cc_preview()

    def _on_overlay_val_changed(self, val: int) -> None:
        if self.overlay_type == "blur":
            self.overlay_item.set_blur_strength(val)
        else:
            self.overlay_item.set_opacity(val / 100.0)
        self._schedule_cc_preview()

    def _update_overlay_image_ui(self) -> None:
        if not hasattr(self, 'edit_overlay_path'):
            return
        has_img = bool(getattr(self, 'overlay_image_path', None) and os.path.exists(self.overlay_image_path))
        icons_dir = getattr(self, 'icons_dir', AppContext.find_resource_dir("icons"))
        from PyQt6.QtGui import QIcon
        
        if has_img:
            base_name = os.path.basename(self.overlay_image_path)
            self.edit_overlay_path.setText(base_name)
            self.edit_overlay_path.setToolTip(self.overlay_image_path)
            self.edit_overlay_path.setStyleSheet(
                "QLineEdit {"
                "    border: 1px dashed #4ade80;"
                "    border-radius: 4px;"
                "    background-color: rgba(74, 222, 128, 0.08);"
                "    color: #4ade80;"
                "    font-weight: bold;"
                "    padding: 4px 8px;"
                "    font-size: 11px;"
                "}"
            )
            if hasattr(self, 'btn_overlay_file_action'):
                self.btn_overlay_file_action.setIcon(QIcon(os.path.join(icons_dir, "trash-color.svg")))
                self.btn_overlay_file_action.setToolTip(AppContext.tr("tooltip_overlay_img_del"))
            if hasattr(self, 'btn_overlay_img_reset'):
                self.btn_overlay_img_reset.show()
        else:
            self.edit_overlay_path.setText("")
            self.edit_overlay_path.setPlaceholderText(AppContext.tr("ovl_drop_placeholder"))
            self.edit_overlay_path.setToolTip(AppContext.tr("tooltip_overlay_drop_field"))
            if hasattr(self.edit_overlay_path, 'update_style'):
                self.edit_overlay_path.update_style(False)
            if hasattr(self, 'btn_overlay_file_action'):
                self.btn_overlay_file_action.setIcon(QIcon(os.path.join(icons_dir, "folder-color.svg")))
                self.btn_overlay_file_action.setToolTip(AppContext.tr("ovl_btn_select"))
            if hasattr(self, 'btn_overlay_img_reset'):
                self.btn_overlay_img_reset.hide()

    def _on_overlay_file_action_clicked(self) -> None:
        if getattr(self, 'overlay_image_path', None):
            self._clear_overlay_image()
        else:
            self._select_overlay_image()

    def _select_overlay_image(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Выберите изображение" if AppContext.is_ru() else "Select image", "", "Image Files (*.png *.jpg *.jpeg *.gif *.webp *.bmp)")
        if f:
            self._apply_overlay_image_file(f)

    def _apply_overlay_image_file(self, f: str) -> None:
        if not f or not os.path.exists(f):
            return
        self.overlay_image_path = f
        self._update_overlay_image_ui()
        
        pix = QPixmap(f)
        if not pix.isNull() and hasattr(self, 'video_item') and self.video_item.boundingRect().width() > 0:
            v_rect = self.video_item.boundingRect()
            new_w, new_h = pix.width(), pix.height()
            if new_w > v_rect.width() or new_h > v_rect.height():
                scaled = pix.scaled(v_rect.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                new_w, new_h = scaled.width(), scaled.height()
            x = (v_rect.width() - new_w) / 2
            y = (v_rect.height() - new_h) / 2
            self.overlay_item.set_rect(QRectF(0, 0, new_w, new_h))
            self.overlay_item.setPos(x, y)
            self.overlay_item.set_pixmap(pix)
        
        ext = os.path.splitext(f)[1].lower()
        if ext == '.gif':
            from PyQt6.QtCore import QBuffer
            from utils_io import ensure_long_path
            try:
                with open(ensure_long_path(f), 'rb') as file:
                    data = file.read()
                self._overlay_movie_buffer = QBuffer()
                self._overlay_movie_buffer.setData(data)
                self._overlay_movie_buffer.open(QBuffer.OpenModeFlag.ReadOnly)
                fmt = ext.strip('.').encode() if ext else b''
                movie = QMovie(self._overlay_movie_buffer, fmt)
                self.overlay_item.set_movie(movie)
            except Exception:
                self.overlay_item.set_movie(QMovie(f))
        else:
            self.overlay_item.set_pixmap(QPixmap(f))
        
        if hasattr(self, 'chk_overlay_bounce') and self.chk_overlay_bounce.isChecked():
            pos = self.player.position() if hasattr(self, 'player') and self.player else 0
            self._update_bouncing_overlay_pos(pos)
            
        self._schedule_cc_preview()

    def _on_reset_overlay_size(self) -> None:
        if not getattr(self, 'overlay_image_path', None): return
        pix = QPixmap(self.overlay_image_path)
        if pix.isNull(): return
        v_rect = self.video_item.boundingRect()
        new_w, new_h = pix.width(), pix.height()
        if new_w > v_rect.width() or new_h > v_rect.height():
             scaled = pix.scaled(v_rect.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
             new_w, new_h = scaled.width(), scaled.height()
        x = (v_rect.width() - new_w) / 2
        y = (v_rect.height() - new_h) / 2
        self.overlay_item.set_rect(QRectF(0, 0, new_w, new_h))
        self.overlay_item.setPos(x, y)
        self._schedule_cc_preview()

    def _clear_overlay_image(self) -> None:
        self.overlay_image_path = None
        self._update_overlay_image_ui()
        self.overlay_item.set_pixmap(None)
        self.overlay_item.set_movie(None)
        self._reset_overlay_to_two_thirds()
        self._schedule_cc_preview()

    def _pick_overlay_color(self) -> None:
        # Retrieve current color from item to use as default in dialog
        initial_color = self.overlay_item._color
        c = QColorDialog.getColor(initial_color, self, "Выберите цвет региона" if AppContext.is_ru() else "Select region color", QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if c.isValid():
            self.btn_overlay_color.setStyleSheet(f"background: {c.name()}; border: 1px solid #888;")
            self.overlay_item.set_color(c)
            self._schedule_cc_preview()

    def _on_overlay_bounce_toggled(self, checked: bool) -> None:
        """Переключение режима отскакивающего/случайного движения водяного знака."""
        if hasattr(self, 'widget_bounce_settings'):
            self.widget_bounce_settings.setVisible(checked)
        if checked:
            self._saved_static_overlay_pos = self.overlay_item.pos()
            pos = self.player.position() if hasattr(self, 'player') and self.player else 0
            self._update_bouncing_overlay_pos(pos)
        else:
            if hasattr(self, '_saved_static_overlay_pos') and self._saved_static_overlay_pos is not None:
                self.overlay_item.setPos(self._saved_static_overlay_pos)
        self._schedule_cc_preview()

    def _on_bounce_params_changed(self) -> None:
        """Вызывается при изменении скорости или угла движения."""
        if hasattr(self, 'chk_overlay_bounce') and self.chk_overlay_bounce.isChecked():
            pos = self.player.position() if hasattr(self, 'player') and self.player else 0
            self._update_bouncing_overlay_pos(pos)
        self._schedule_cc_preview()

    def _update_bouncing_overlay_pos(self, pos_ms: int) -> None:
        """Обновление позиции логотипа по кинематике угла и скорости отскока."""
        if not getattr(self, 'overlay_enabled', False):
            return
        if getattr(self, 'overlay_type', None) != 'image':
            return
        if not hasattr(self, 'chk_overlay_bounce') or not self.chk_overlay_bounce.isChecked():
            return
        if not hasattr(self, 'video_item') or not self.video_item:
            return
        v_rect = self.video_item.boundingRect()
        if v_rect.isEmpty():
            return

        ovl_rect = self.overlay_item.get_rect()
        w, h = ovl_rect.width(), ovl_rect.height()
        if w <= 0 or h <= 0:
            return

        # Если активно кадрирование (Crop), ограничиваем движение зоной кадрирования
        if getattr(self, 'is_cropping', False) and hasattr(self, 'handle_tl') and hasattr(self, 'handle_br'):
            tl = self.handle_tl.pos()
            br = self.handle_br.pos()
            cx = max(0.0, tl.x())
            cy = max(0.0, tl.y())
            cw = max(1.0, br.x() - tl.x())
            ch = max(1.0, br.y() - tl.y())
        else:
            cx = 0.0
            cy = 0.0
            cw = v_rect.width()
            ch = v_rect.height()

        span_x = max(1.0, cw - w)
        span_y = max(1.0, ch - h)

        # Вычисляем составляющие скорости исходя из множителя скорости и угла наклона
        speed_mult = self.spin_bounce_speed.value() if hasattr(self, 'spin_bounce_speed') else 1.0
        angle_deg = self.spin_bounce_angle.value() if hasattr(self, 'spin_bounce_angle') else 45
        import math
        rad = math.radians(angle_deg)

        base_v = max(span_x, span_y) / 4.0
        v = base_v * speed_mult
        vx = max(1.0, v * math.cos(rad))
        vy = max(1.0, v * math.sin(rad))

        t = pos_ms / 1000.0

        mod_x = (t * vx) % (2.0 * span_x)
        dx = abs(mod_x - span_x)
        x = cx + (span_x - dx)

        mod_y = (t * vy) % (2.0 * span_y)
        dy = abs(mod_y - span_y)
        y = cy + (span_y - dy)

        self.overlay_item.setPos(x, y)
