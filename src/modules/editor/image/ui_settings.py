
import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, 
                              QCheckBox, QGroupBox, QSlider, QSpinBox, QComboBox, QStyle)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIntValidator, QColor

from config import AppContext, APP_DESIGN
from ..video.ui_widgets import OutputFolderDropZone

class ImageSettingsWidget(QWidget):
    settings_changed = pyqtSignal()
    output_folder_changed = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.output_dir = ""
        self.orig_width = 1920
        self.orig_height = 1080
        self.file_count = 0
        self._sync_lock = False 
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(10, 0, 0, 0)

        cb_style = """
            QCheckBox { spacing: 8px; color: #eee; font-size: 13px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 3px; border: 1px solid #666; background: #333; }
            QCheckBox::indicator:unchecked:hover { border-color: #888; background: #444; }
            QCheckBox::indicator:checked { background: #3b82f6; border-color: #3b82f6; image: url(src/assets/check.png); }
        """
        
        sb_style = """
            QSpinBox { background-color: #3d3d3d; color: white; border: 1px solid #555; border-radius: 4px; padding: 0 4px; }
            QSpinBox:disabled { background-color: #2a2a2a; color: #777; border-color: #444; }
        """

        # Section 1: Output Format
        grp_format = self.create_group_box(AppContext.tr("settings_image_format"))
        fmt_layout = QVBoxLayout(grp_format)
        self.combo_format = QComboBox()
        self.combo_format.addItems(["JPG", "PNG", "WebP", "BMP", "TIFF"])
        self.combo_format.setStyleSheet(APP_DESIGN['nativelike_combo'])
        self.combo_format.setFixedHeight(28)
        self.combo_format.currentIndexChanged.connect(self.on_format_changed)
        fmt_layout.addWidget(self.combo_format)
        layout.addWidget(grp_format)

        # Section 2: Quality
        self.grp_quality = self.create_group_box(AppContext.tr("settings_compression_mode"))
        qual_layout = QVBoxLayout(self.grp_quality)
        
        self.chk_lossless = QCheckBox(AppContext.tr("chk_lossless"))
        self.chk_lossless.setStyleSheet(cb_style)
        self.chk_lossless.toggled.connect(self.on_lossless_toggled)
        qual_layout.addWidget(self.chk_lossless)
        
        self.lbl_quality = QLabel(AppContext.tr("lbl_quality_slider").format(85))
        self.lbl_quality.setStyleSheet("color: #aaa; font-size: 12px; margin-top: 5px;")
        qual_layout.addWidget(self.lbl_quality)
        
        self.slider_quality = QSlider(Qt.Orientation.Horizontal)
        self.slider_quality.setRange(1, 100)
        self.slider_quality.setValue(85)
        self.slider_quality.setStyleSheet("""
            QSlider::groove:horizontal { border: 1px solid #444; height: 4px; background: #333; margin: 12px 0; border-radius: 2px; }
            QSlider::handle:horizontal { background: #3b82f6; border: 1px solid #3b82f6; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; }
        """)
        self.slider_quality.valueChanged.connect(self.update_quality_label)
        qual_layout.addWidget(self.slider_quality)
        layout.addWidget(self.grp_quality)

        # Section 3: Scale
        grp_scale = self.create_group_box(AppContext.tr("chk_scale_video")) # Reuse key
        scale_layout = QVBoxLayout(grp_scale)
        
        row_scale = QHBoxLayout()
        self.chk_scale = QCheckBox()
        self.chk_scale.setFixedWidth(20)
        self.chk_scale.setStyleSheet(cb_style)
        self.chk_scale.toggled.connect(self.on_scale_toggled)
        row_scale.addWidget(self.chk_scale)
        
        self.combo_scale = QComboBox()
        self.combo_scale.addItems([
            AppContext.tr("scale_proportion"),
            AppContext.tr("scale_half"), 
            AppContext.tr("scale_third"), 
            AppContext.tr("scale_quarter"), 
            AppContext.tr("scale_custom")
        ])
        self.combo_scale.setFixedHeight(28)
        self.combo_scale.setEnabled(False)
        self.combo_scale.setStyleSheet(APP_DESIGN['nativelike_combo'])
        self.combo_scale.currentIndexChanged.connect(self.on_scale_mode_changed)
        row_scale.addWidget(self.combo_scale, 1)
        
        self.inp_scale_percent = QSpinBox()
        self.inp_scale_percent.setRange(1, 400)
        self.inp_scale_percent.setValue(100)
        self.inp_scale_percent.setSuffix("%")
        self.inp_scale_percent.setFixedHeight(28)
        self.inp_scale_percent.setStyleSheet(sb_style)
        self.inp_scale_percent.hide()
        self.inp_scale_percent.valueChanged.connect(self.settings_changed.emit)
        row_scale.addWidget(self.inp_scale_percent)
        scale_layout.addLayout(row_scale)
        
        self.prop_container = QWidget()
        self.prop_container.hide()
        prop_layout = QHBoxLayout(self.prop_container)
        prop_layout.setContentsMargins(25, 0, 0, 0)
        prop_layout.setSpacing(5)
        
        self.inp_width = QLineEdit()
        self.inp_height = QLineEdit()
        v_int = QIntValidator(1, 10000)
        for inp, lbl_key in [(self.inp_width, "lbl_width"), (self.inp_height, "lbl_height")]:
            inp.setValidator(v_int)
            inp.setFixedWidth(60)
            inp.setStyleSheet(APP_DESIGN['nativelike_input'])
            l = QLabel(AppContext.tr(lbl_key))
            l.setStyleSheet("color: #aaa; font-size: 11px;")
            prop_layout.addWidget(l)
            prop_layout.addWidget(inp)
        
        self.inp_width.textEdited.connect(self.sync_height)
        self.inp_height.textEdited.connect(self.sync_width)
        scale_layout.addWidget(self.prop_container)
        layout.addWidget(grp_scale)

        # Section 4: Naming
        grp_naming = self.create_group_box(AppContext.tr("settings_other"))
        nam_layout = QVBoxLayout(grp_naming)
        
        self.chk_rename = QCheckBox(AppContext.tr("chk_rename"))
        self.chk_rename.setChecked(True)
        self.chk_rename.setStyleSheet(cb_style)
        nam_layout.addWidget(self.chk_rename)
        
        row_nam = QHBoxLayout()
        self.combo_rename_type = QComboBox()
        self.combo_rename_type.addItems([AppContext.tr("btn_prefix"), AppContext.tr("btn_postfix")])
        self.combo_rename_type.setCurrentIndex(1)
        self.combo_rename_type.setStyleSheet(APP_DESIGN['nativelike_combo'])
        row_nam.addWidget(self.combo_rename_type)
        
        self.inp_name_tmpl = QLineEdit("_convert")
        self.inp_name_tmpl.setStyleSheet(APP_DESIGN['nativelike_input'])
        row_nam.addWidget(self.inp_name_tmpl, 1)
        nam_layout.addLayout(row_nam)
        layout.addWidget(grp_naming)

        layout.addStretch()
        self.output_zone = OutputFolderDropZone()
        self.output_zone.folder_dropped.connect(self.set_output_folder)
        self.output_zone.browse_clicked.connect(self.select_output_folder)
        layout.addWidget(self.output_zone)

    def select_output_folder(self):
        from PyQt6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, AppContext.tr("msg_select_output_folder"))
        if d: self.set_output_folder(d)

    def set_output_folder(self, path):
        self.output_dir = path
        self.output_zone.set_folder(path)
        self.output_folder_changed.emit(path)

    def create_group_box(self, title):
        gb = QGroupBox(title)
        gb.setStyleSheet("""
            QGroupBox { border: 1px solid #444; border-radius: 6px; margin-top: 20px; font-weight: bold; color: #ddd; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; left: 10px; }
        """)
        return gb

    def on_format_changed(self, idx):
        fmt = self.combo_format.currentText()
        is_lossless_only = fmt in ("PNG", "BMP", "TIFF")
        
        if is_lossless_only:
            self.chk_lossless.blockSignals(True)
            self.chk_lossless.setChecked(True)
            self.chk_lossless.setEnabled(False)
            self.chk_lossless.blockSignals(False)
            self.slider_quality.setEnabled(False)
            self.lbl_quality.setEnabled(False)
        else:
            self.chk_lossless.setEnabled(True)
            # Restore slider state based on checkbox
            self.on_lossless_toggled(self.chk_lossless.isChecked())
            
        self.settings_changed.emit()

    def on_lossless_toggled(self, checked):
        self.slider_quality.setEnabled(not checked)
        self.lbl_quality.setEnabled(not checked)
        self.settings_changed.emit()

    def update_quality_label(self, val):
        self.lbl_quality.setText(AppContext.tr("lbl_quality_slider").format(val))
        self.settings_changed.emit()

    def on_scale_toggled(self, checked):
        self.combo_scale.setEnabled(checked)
        self.on_scale_mode_changed()

    def on_scale_mode_changed(self):
        idx = self.combo_scale.currentIndex()
        is_prop = (idx == 0)
        is_custom = (idx == 4)
        active = self.chk_scale.isChecked()
        
        self.prop_container.setVisible(active and is_prop)
        self.inp_scale_percent.setVisible(active and is_custom)
        
        if active and is_prop:
            self.inp_width.setText(str(self.orig_width))
            self.inp_height.setText(str(self.orig_height))
        self.settings_changed.emit()

    def set_file_info(self, count, w=None, h=None):
        self.file_count = count
        if w and h:
            self.orig_width, self.orig_height = w, h
            # If width/height were empty, populate them
            if not self.inp_width.text() or self.inp_width.text() == "0":
                self.inp_width.setText(str(w))
                self.inp_height.setText(str(h))
        
        # Now Proportion is allowed for any count (Fit-In mode)
        is_prop_allowed = (count >= 1)
        model = self.combo_scale.model()
        idx = model.index(0, 0)
        
        model.setData(idx, Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable, Qt.ItemDataRole.UserRole - 1)
        model.setData(idx, QColor("#ffffff"), Qt.ItemDataRole.ForegroundRole)
        
        self.settings_changed.emit()

    def sync_height(self):
        if self._sync_lock or not self.inp_width.text() or self.orig_width == 0: return
        try:
            self._sync_lock = True
            w = int(self.inp_width.text())
            h = int(w * self.orig_height / self.orig_width)
            self.inp_height.setText(str(h))
        finally: self._sync_lock = False
        self.settings_changed.emit()

    def sync_width(self):
        if self._sync_lock or not self.inp_height.text() or self.orig_height == 0: return
        try:
            self._sync_lock = True
            h = int(self.inp_height.text())
            w = int(h * self.orig_width / self.orig_height)
            self.inp_width.setText(str(w))
        finally: self._sync_lock = False
        self.settings_changed.emit()

    def get_settings(self):
        idx = self.combo_scale.currentIndex()
        sp = 100
        if idx == 1: sp = 50
        elif idx == 2: sp = 33
        elif idx == 3: sp = 25
        elif idx == 4: sp = self.inp_scale_percent.value()

        return {
            'format': self.combo_format.currentText().lower(),
            'lossless': self.chk_lossless.isChecked(),
            'quality': self.slider_quality.value(),
            'scale_mode': 'off' if not self.chk_scale.isChecked() else ('proportion' if idx == 0 else 'percent'),
            'scale_percent': sp,
            'target_w': int(self.inp_width.text() or 0) if idx == 0 else 0,
            'target_h': int(self.inp_height.text() or 0) if idx == 0 else 0,
            'rename': self.chk_rename.isChecked(),
            'rename_prefix': self.combo_rename_type.currentIndex() == 0,
            'name_tmpl': self.inp_name_tmpl.text(),
            'output_dir': self.output_dir
        }

    def update_ui_text(self):
        self.lbl_quality.setText(AppContext.tr("lbl_quality_slider").format(self.slider_quality.value()))
