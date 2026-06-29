
import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, 
                              QCheckBox, QGroupBox, QSlider, QSpinBox, QComboBox, QStyle)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIntValidator, QColor

from config import AppContext, APP_DESIGN
from ..video.ui_widgets import OutputFolderDropZone

class AudioSettingsWidget(QWidget):
    settings_changed = pyqtSignal()
    output_folder_changed = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.output_dir = ""
        self.source_bitrate = 0 # In kbps
        self._setup_chevron_icons()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(10, 0, 0, 0)

        cb_style = """
            QCheckBox { spacing: 8px; color: #eee; font-size: 13px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 3px; border: 1px solid #666; background: #333; }
            QCheckBox::indicator:unchecked:hover { border-color: #888; background: #444; }
            QCheckBox::indicator:checked { background: #3b82f6; border-color: #3b82f6; image: url(src/assets/check.png); }
        """
        
        # Section 1: Output Format
        grp_format = self.create_group_box(AppContext.tr("settings_audio_format"))
        fmt_layout = QVBoxLayout(grp_format)
        self.combo_format = QComboBox()
        self.combo_format.addItems(["MP3", "WAV", "OGG", "FLAC", "M4A", "AAC", "OPUS"])
        self.combo_format.setStyleSheet(APP_DESIGN['nativelike_combo'])
        self.combo_format.setFixedHeight(28)
        self.combo_format.currentIndexChanged.connect(self.on_format_changed)
        fmt_layout.addWidget(self.combo_format)
        
        self.chk_copy_stream = QCheckBox(AppContext.tr("chk_copy_stream"))
        self.chk_copy_stream.setStyleSheet(cb_style)
        self.chk_copy_stream.toggled.connect(self.on_copy_stream_toggled)
        fmt_layout.addWidget(self.chk_copy_stream)
        layout.addWidget(grp_format)

        # Section 2: Bitrate
        self.grp_bitrate = self.create_group_box(AppContext.tr("settings_bitrate"))
        bit_layout = QVBoxLayout(self.grp_bitrate)
        
        mode_layout = QHBoxLayout()
        self.btn_cbr = QPushButton("CBR")
        self.btn_vbr = QPushButton("VBR")
        for b in [self.btn_cbr, self.btn_vbr]:
            b.setCheckable(True)
            b.setFixedHeight(25)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("""
                QPushButton { background: #333; color: #ccc; border: 1px solid #555; border-radius: 4px; font-weight: bold; }
                QPushButton:checked { background: #3b82f6; color: white; border-color: #3b82f6; }
            """)
        self.btn_cbr.setChecked(True)
        self.btn_cbr.clicked.connect(lambda: self.switch_mode('cbr'))
        self.btn_vbr.clicked.connect(lambda: self.switch_mode('vbr'))
        mode_layout.addWidget(self.btn_cbr)
        mode_layout.addWidget(self.btn_vbr)
        bit_layout.addLayout(mode_layout)

        self.lbl_bitrate_val = QLabel("192 kbps")
        self.lbl_bitrate_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_bitrate_val.setStyleSheet("color: #4ade80; font-weight: bold; font-size: 14px;")
        bit_layout.addWidget(self.lbl_bitrate_val)

        self.slider_bitrate = QSlider(Qt.Orientation.Horizontal)
        self.slider_bitrate.setRange(8, 320)
        self.slider_bitrate.setValue(192)
        self.slider_bitrate.setStyleSheet("""
            QSlider::groove:horizontal { border: 1px solid #444; height: 4px; background: #333; margin: 12px 0; border-radius: 2px; }
            QSlider::handle:horizontal { background: #3b82f6; border: 1px solid #3b82f6; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; }
        """)
        self.slider_bitrate.valueChanged.connect(self.update_bitrate_label)
        bit_layout.addWidget(self.slider_bitrate)
        
        self.lbl_cap_hint = QLabel(AppContext.tr("lbl_bitrate_cap_hint"))
        self.lbl_cap_hint.setStyleSheet("color: #888; font-size: 10px;")
        self.lbl_cap_hint.setWordWrap(True)
        bit_layout.addWidget(self.lbl_cap_hint)
        layout.addWidget(self.grp_bitrate)

        # Section 3: Advanced
        grp_adv = self.create_group_box(AppContext.tr("settings_other"))
        adv_layout = QVBoxLayout(grp_adv)
        
        # Sample Rate
        row_sr = QHBoxLayout()
        row_sr.addWidget(QLabel(AppContext.tr("settings_sample_rate") + ":"))
        self.combo_sr = QComboBox()
        self.combo_sr.addItems(["Auto", "44100", "48000", "22050", "11025"])
        self.combo_sr.setStyleSheet(APP_DESIGN['nativelike_combo'])
        row_sr.addWidget(self.combo_sr)
        adv_layout.addLayout(row_sr)
        
        # Channels
        row_ch = QHBoxLayout()
        row_ch.addWidget(QLabel(AppContext.tr("settings_channels") + ":"))
        self.combo_ch = QComboBox()
        self.combo_ch.addItems(["Auto", "Stereo (2)", "Mono (1)"])
        self.combo_ch.setStyleSheet(APP_DESIGN['nativelike_combo'])
        row_ch.addWidget(self.combo_ch)
        adv_layout.addLayout(row_ch)
        
        # Max Size
        sb_style = f"""
            QSpinBox {{ 
                background-color: #3d3d3d; 
                color: white; 
                border: 1px solid #555; 
                border-radius: 4px; 
                padding: 0 4px; 
            }}
            QSpinBox:disabled {{ background-color: #2a2a2a; color: #777; border-color: #444; }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 18px;
                background: #2a2a2a;
                border: none;
            }}
            QSpinBox::up-button {{ border-top-right-radius: 4px; }}
            QSpinBox::down-button {{ border-bottom-right-radius: 4px; }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: #3a3a3a; }}
            QSpinBox::up-arrow {{ image: url('{self.chevron_paths["up_active"]}'); width: 10px; height: 10px; }}
            QSpinBox::down-arrow {{ image: url('{self.chevron_paths["down_active"]}'); width: 10px; height: 10px; }}
            QSpinBox::up-arrow:disabled {{ image: url('{self.chevron_paths["up_disabled"]}'); }}
            QSpinBox::down-arrow:disabled {{ image: url('{self.chevron_paths["down_disabled"]}'); }}
        """
        row_ms = QHBoxLayout()
        self.chk_max_size = QCheckBox(AppContext.tr("chk_max_file_size"))
        self.chk_max_size.setStyleSheet(cb_style + "QCheckBox:disabled { color: #555; }")
        self.chk_max_size.toggled.connect(self.toggle_max_size)
        row_ms.addWidget(self.chk_max_size)
        
        self.inp_max_size = QSpinBox()
        self.inp_max_size.setRange(1, 20000)
        self.inp_max_size.setValue(10)
        self.inp_max_size.setSuffix(" MB")
        self.inp_max_size.setEnabled(False)
        self.inp_max_size.setFixedHeight(28)
        self.inp_max_size.setStyleSheet(sb_style)
        self.inp_max_size.valueChanged.connect(self.settings_changed.emit)
        row_ms.addWidget(self.inp_max_size)
        adv_layout.addLayout(row_ms)
        
        # Naming
        adv_layout.addSpacing(10)
        self.chk_rename = QCheckBox(AppContext.tr("chk_rename"))
        self.chk_rename.setChecked(True)
        self.chk_rename.setStyleSheet(cb_style)
        adv_layout.addWidget(self.chk_rename)
        
        row_nam = QHBoxLayout()
        self.combo_rename_type = QComboBox()
        self.combo_rename_type.addItems([AppContext.tr("btn_prefix"), AppContext.tr("btn_postfix")])
        self.combo_rename_type.setCurrentIndex(1)
        self.combo_rename_type.setStyleSheet(APP_DESIGN['nativelike_combo'])
        row_nam.addWidget(self.combo_rename_type)
        
        self.inp_name_tmpl = QLineEdit("_compress")
        self.inp_name_tmpl.setStyleSheet(APP_DESIGN['nativelike_input'])
        row_nam.addWidget(self.inp_name_tmpl, 1)
        adv_layout.addLayout(row_nam)
        layout.addWidget(grp_adv)

        layout.addStretch()
        self.output_zone = OutputFolderDropZone()
        self.output_zone.folder_dropped.connect(self.set_output_folder)
        self.output_zone.browse_clicked.connect(self.select_output_folder)
        layout.addWidget(self.output_zone)

    def create_group_box(self, title):
        gb = QGroupBox(title)
        gb.setStyleSheet("""
            QGroupBox { border: 1px solid #444; border-radius: 6px; margin-top: 20px; font-weight: bold; color: #ddd; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; left: 10px; }
        """)
        return gb

    def switch_mode(self, mode):
        self.btn_cbr.setChecked(mode == 'cbr')
        self.btn_vbr.setChecked(mode == 'vbr')
        
        if mode == 'vbr':
            self.slider_bitrate.setRange(0, 9)
            self.slider_bitrate.setValue(4)
            self.slider_bitrate.setInvertedAppearance(True) # Lower is better in FFmpeg VBR
        else:
            self.slider_bitrate.setRange(8, 320)
            self.slider_bitrate.setValue(192)
            self.slider_bitrate.setInvertedAppearance(False)
            
        self.update_bitrate_label()
        self.settings_changed.emit()

    def update_bitrate_label(self):
        val = self.slider_bitrate.value()
        if self.btn_vbr.isChecked():
            # FFmpeg -q:a 0-9. 0 is best.
            quality_map = [
                AppContext.tr("vbr_quality_0"), AppContext.tr("vbr_quality_1"),
                AppContext.tr("vbr_quality_2"), AppContext.tr("vbr_quality_3"),
                AppContext.tr("vbr_quality_4"), AppContext.tr("vbr_quality_5"),
                AppContext.tr("vbr_quality_6"), AppContext.tr("vbr_quality_7"),
                AppContext.tr("vbr_quality_8"), AppContext.tr("vbr_quality_9")
            ]
            self.lbl_bitrate_val.setText(AppContext.tr("lbl_vbr_quality").format(quality_map[val]))
            self.lbl_bitrate_val.setToolTip(AppContext.tr("tooltip_vbr_mode"))
        else:
            self.lbl_bitrate_val.setText(f"{val} kbps")
            self.lbl_bitrate_val.setToolTip(AppContext.tr("tooltip_cbr_mode"))
        self.settings_changed.emit()

    def on_format_changed(self, idx):
        fmt = self.combo_format.currentText()
        is_lossless = fmt in ("WAV", "FLAC")
        self.grp_bitrate.setEnabled(not is_lossless and not self.chk_copy_stream.isChecked())
        self.settings_changed.emit()

    def on_copy_stream_toggled(self, checked):
        self.grp_bitrate.setEnabled(not checked)
        self.settings_changed.emit()

    def select_output_folder(self):
        from PyQt6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, AppContext.tr("msg_select_output_folder"))
        if d: self.set_output_folder(d)

    def set_output_folder(self, path):
        self.output_dir = path
        self.output_zone.set_folder(path)
        self.output_folder_changed.emit(path)

    def set_file_info(self, bitrate_kbps):
        self.source_bitrate = bitrate_kbps

    def toggle_max_size(self, checked):
        self.inp_max_size.setEnabled(checked)
        self.settings_changed.emit()

    def get_settings(self):
        return {
            'format': self.combo_format.currentText().lower(),
            'copy_stream': self.chk_copy_stream.isChecked(),
            'mode': 'vbr' if self.btn_vbr.isChecked() else 'cbr',
            'bitrate': self.slider_bitrate.value(),
            'sample_rate': self.combo_sr.currentText(),
            'channels': self.combo_ch.currentIndex(), # 0: auto, 1: 2, 2: 1
            'max_size': self.inp_max_size.value() if self.chk_max_size.isChecked() else None,
            'rename': self.chk_rename.isChecked(),
            'rename_prefix': self.combo_rename_type.currentIndex() == 0,
            'name_tmpl': self.inp_name_tmpl.text(),
            'output_dir': self.output_dir
        }

    def update_ui_text(self):
        # Update group box titles
        for group in self.findChildren(QGroupBox):
            if group.title() in ["Формат аудио", "Audio Format"]:
                group.setTitle(AppContext.tr("settings_audio_format"))
            elif group.title() in ["Настройка битрейта (кб/с)", "Bitrate Setting (kbps)"]:
                group.setTitle(AppContext.tr("settings_bitrate"))
            elif group.title() in ["Другое", "Other"]:
                group.setTitle(AppContext.tr("settings_other"))

        self.lbl_cap_hint.setText(AppContext.tr("lbl_bitrate_cap_hint"))
        self.chk_copy_stream.setText(AppContext.tr("chk_copy_stream"))
        self.chk_max_size.setText(AppContext.tr("chk_max_file_size"))
        self.chk_rename.setText(AppContext.tr("chk_rename"))
        
        # Update rename combo
        rename_idx = self.combo_rename_type.currentIndex()
        self.combo_rename_type.clear()
        self.combo_rename_type.addItems([AppContext.tr("btn_prefix"), AppContext.tr("btn_postfix")])
        if rename_idx >= 0:
            self.combo_rename_type.setCurrentIndex(rename_idx)
            
        # Update channels combo
        ch_idx = self.combo_ch.currentIndex()
        self.combo_ch.clear()
        self.combo_ch.addItems(["Auto", "Stereo (2)", "Mono (1)"])
        if ch_idx >= 0:
            self.combo_ch.setCurrentIndex(ch_idx)

        self.update_bitrate_label()
        
        if hasattr(self, 'output_zone'):
            self.output_zone.update_ui_text()

    def _setup_chevron_icons(self):
        import tempfile
        temp_dir = tempfile.gettempdir()
        
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
        
        self.chevron_paths = {}
        colors = {
            "active": "#ffffff",
            "disabled": "#777777"
        }
        for state, color in colors.items():
            path_up = os.path.join(temp_dir, f"audio-chevron-up-{state}.svg").replace('\\', '/')
            path_down = os.path.join(temp_dir, f"audio-chevron-down-{state}.svg").replace('\\', '/')
            
            try:
                with open(path_up, "w", encoding="utf-8") as f:
                    f.write(chevron_up_tpl.format(color=color))
                with open(path_down, "w", encoding="utf-8") as f:
                    f.write(chevron_down_tpl.format(color=color))
            except Exception as e:
                import logging
                logging.error(f"Failed to write temporary chevron SVG in audio settings: {e}")
                
            self.chevron_paths[f"up_{state}"] = path_up
            self.chevron_paths[f"down_{state}"] = path_down
