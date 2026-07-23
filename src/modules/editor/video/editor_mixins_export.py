
import os
import logging
from PyQt6.QtWidgets import QFileDialog
from config import AppContext
from .worker_editor import VideoEditorWorker

class EditorExportMixin:
    """Logic related to export execution, progress, timers and settings aggregation."""

    def _check_start_readiness(self):
        is_ready = False
        if self.is_video_loaded:
            # Detect type
            is_audio = getattr(self, 'is_audio_only', False)
            
            # Markers - Always priority
            if len(self.waveform_progress.markers) > 0: is_ready = True
            
            if not is_audio:
                # Transformations
                if (self.current_rotation % 360) != 0: is_ready = True
                if self.is_flip_h or self.is_flip_v: is_ready = True
                if self.is_cropping: is_ready = True
                # Color Correction
                if abs(self.cc_brightness) > 0.01: is_ready = True
                if abs(self.cc_contrast - 1.0) > 0.01: is_ready = True
                if abs(self.cc_saturation - 1.0) > 0.01: is_ready = True
                # Overlay
                if self.overlay_enabled: is_ready = True
            
            # Even if no changes, allow export if rename is active or folder is set
            if self.chk_rename.isChecked() and self.inp_naming.text(): is_ready = True

        self.btn_start_exec.setEnabled(is_ready)

    def _set_export_dir(self, path):
        self.output_dir = path
        self.export_zone.set_folder(path)

    def _browse_export_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения")
        if d: self._set_export_dir(d)

    def start_execution(self):
        if self.worker and self.worker.isRunning():
            self.stop_execution()
            return
            
        settings = self._gather_editor_settings()
        if not settings: return
        
        logging.info(f"Запуск процесса экспорта. Настройки: {settings}")
        
        self.player.pause()
        self.btn_start_exec.setText(AppContext.tr("btn_stop"))
        self.btn_start_exec.setStyleSheet("background-color: #ef4444; color: white; font-weight: bold;")
        self.progress_bar.setValue(0)
        self.progress_bar.setEnabled(True)
        
        self.start_time = 0 
        self.exec_timer.start()
        
        self.worker = VideoEditorWorker(settings)
        self.worker.progress_updated.connect(self._on_exec_progress)
        self.worker.finished.connect(self._on_exec_finished)
        self.worker.start()

    def stop_execution(self):
        if self.worker:
            self.worker.stop()
            self.btn_start_exec.setText(AppContext.tr("msg_stop_conversion"))
            self.btn_start_exec.setEnabled(False)

    def _on_exec_progress(self, p):
        self.progress_bar.setValue(p)

    def _on_exec_finished(self, success, msg):
        self.exec_timer.stop()
        self.btn_start_exec.setText(AppContext.tr("btn_start_processing"))
        self.btn_start_exec.setEnabled(True)
        self._check_start_readiness() 
        self.progress_bar.setEnabled(False)
        self.progress_bar.setValue(0)
        
        if success:
            logging.info(f"Экспорт успешно завершен: {msg}")
            self.progress_bar.setValue(100)
        else:
            logging.error(f"Экспорт завершен с ошибкой: {msg}")
            from PyQt6.QtWidgets import QMessageBox
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.NoIcon)
            msg_box.setWindowTitle("Ошибка экспорта")
            msg_box.setText(f"Произошла ошибка при экспорте:\n{msg}")
            msg_box.exec()

    def _update_exec_timer(self):
        """Updates the timer label during export execution."""
        # Update every second (timer interval is 1000)
        self.start_time += 1
        m = self.start_time // 60
        s = self.start_time % 60
        self.lbl_exec_timer.setText(f"{m:02}:{s:02}")

    def _gather_editor_settings(self):
        if not self.current_file: return None
        
        out_dir = self.output_dir or os.path.dirname(self.current_file)
        name, ext = os.path.splitext(os.path.basename(self.current_file))
        
        mode_text = self.inp_naming.text()
        if self.chk_rename.isChecked(): 
            if self.combo_naming.currentIndex() == 0: # Prefix
                target_name = f"{mode_text}{name}{ext}"
            else: # Postfix
                target_name = f"{name}{mode_text}{ext}"
        else:
            target_name = f"{name}{ext}"
            
        out_path = os.path.join(out_dir, target_name)
        if os.path.exists(out_path):
            c = 1
            while os.path.exists(out_path):
                new_n = f"{os.path.splitext(target_name)[0]}_{c}{ext}"
                out_path = os.path.join(out_dir, new_n)
                c += 1

        overlay_data = None
        if self.overlay_enabled:
            rect_in_video = self.overlay_item.mapRectToParent(self.overlay_item.get_rect())
            v_rect = self.video_item.boundingRect()
            if v_rect.width() > 0:
                overlay_data = {
                    'type': self.overlay_type,
                    'x': rect_in_video.x() / v_rect.width(),
                    'y': rect_in_video.y() / v_rect.height(),
                    'w': rect_in_video.width() / v_rect.width(),
                    'h': rect_in_video.height() / v_rect.height(),
                    'opacity': self.overlay_item._opacity,
                    'color': self.overlay_item._color.name() if self.overlay_type == 'region' else None,
                    'path': self.overlay_image_path if self.overlay_type == 'image' else None,
                    'blur_val': self.slider_overlay_val.value() if self.overlay_type == 'blur' else 0
                }

        return {
            'input': self.current_file,
            'output': out_path,
            'markers': sorted(self.waveform_progress.markers),
            'is_inverted': self.waveform_progress.is_inverted,
            'rotation': self.current_rotation,
            'flip_h': self.is_flip_h,
            'flip_v': self.is_flip_v,
            'cc': {
                'brightness': self.slider_bright.value() / 100.0,
                'contrast': self.slider_contrast.value() / 100.0,
                'saturation': self.slider_sat.value() / 100.0,
                'gamma': 1.0, 
            },
            'overlay': overlay_data,
            'remove_audio': self.btn_remove_audio.isChecked(),
            'split_video': self.btn_split_video.isChecked(),
            'crop': self._get_normalized_crop() if self.is_cropping else None,
            'video_size': (self.video_item.boundingRect().width(), self.video_item.boundingRect().height()),
            'orig_bitrate': self.orig_bitrate,
            'is_audio': getattr(self, 'is_audio_only', False),
            'video_codec': self.combo_video_codec.currentData(),
            'video_quality': self.combo_video_quality.currentData(),
            'video_preset': self.combo_video_preset.currentText()
        }

    def _get_normalized_crop(self):
        tl = self.handle_tl.pos()
        br = self.handle_br.pos()
        return {
            'x': tl.x(), 'y': tl.y(),
            'w': br.x() - tl.x(), 'h': br.y() - tl.y()
        }
