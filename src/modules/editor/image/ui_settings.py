
import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, 
                              QCheckBox, QGroupBox, QSlider, QSpinBox, QComboBox, QStyle, 
                              QTabWidget, QFrame)
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
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(10, 0, 0, 0)

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

        # Tab Widget for Mode Switching
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #444;
                border-radius: 6px;
                background: #262626;
                padding: 6px;
            }
            QTabBar::tab {
                background: #2b2b2b;
                color: #888;
                border: 1px solid #444;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 7px 16px;
                font-weight: bold;
                font-size: 12px;
                margin-right: 4px;
            }
            QTabBar::tab:hover:!selected {
                background: #333;
                color: #ddd;
            }
            QTabBar::tab:selected {
                background: #3b82f6;
                color: white;
                border-color: #3b82f6;
            }
        """)

        # ==========================================
        # TAB 1: CONVERSION
        # ==========================================
        self.tab_convert = QWidget()
        tab_convert_layout = QVBoxLayout(self.tab_convert)
        tab_convert_layout.setSpacing(15)
        tab_convert_layout.setContentsMargins(4, 4, 4, 4)

        # Section 1: Output Format
        self.grp_format = self.create_group_box(AppContext.tr("settings_image_format"))
        fmt_layout = QVBoxLayout(self.grp_format)
        self.combo_format = QComboBox()
        self.combo_format.addItems(["JPG", "PNG", "WebP", "BMP", "TIFF", "GIF"])
        self.combo_format.setStyleSheet(APP_DESIGN['nativelike_combo'])
        self.combo_format.setFixedHeight(28)
        self.combo_format.currentIndexChanged.connect(self.on_format_changed)
        fmt_layout.addWidget(self.combo_format)
        tab_convert_layout.addWidget(self.grp_format)

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
        tab_convert_layout.addWidget(self.grp_quality)

        # Section 3: Scale
        self.grp_scale = self.create_group_box(AppContext.tr("chk_scale_video"))
        scale_layout = QVBoxLayout(self.grp_scale)
        
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
        tab_convert_layout.addWidget(self.grp_scale)

        # Section 3.5: Size Limit
        self.grp_limit = self.create_group_box(AppContext.tr("settings_limit_size_group"))
        limit_layout = QVBoxLayout(self.grp_limit)
        limit_layout.setSpacing(10)

        # Row 1: Checkbox and SpinBox
        row_limit_input = QHBoxLayout()
        self.chk_limit_size = QCheckBox(AppContext.tr("chk_max_file_size"))
        self.chk_limit_size.setStyleSheet(cb_style)
        self.chk_limit_size.toggled.connect(self.on_limit_size_toggled)
        row_limit_input.addWidget(self.chk_limit_size)

        self.sb_limit_size = QSpinBox()
        self.sb_limit_size.setRange(1, 500)
        self.sb_limit_size.setValue(10)
        self.sb_limit_size.setSuffix(" MB")
        self.sb_limit_size.setFixedHeight(28)
        self.sb_limit_size.setStyleSheet(sb_style)
        self.sb_limit_size.setEnabled(False)
        self.sb_limit_size.valueChanged.connect(self.settings_changed.emit)
        row_limit_input.addWidget(self.sb_limit_size)
        limit_layout.addLayout(row_limit_input)

        # Row 2: Priority Label and Slider
        self.lbl_compress_priority = QLabel(AppContext.tr("lbl_compress_priority"))
        self.lbl_compress_priority.setStyleSheet("color: #aaa; font-size: 12px; margin-top: 5px;")
        self.lbl_compress_priority.setEnabled(False)
        limit_layout.addWidget(self.lbl_compress_priority)

        row_priority_labels = QHBoxLayout()
        lbl_q = QLabel(AppContext.tr("lbl_priority_quality"))
        lbl_q.setStyleSheet("color: #777; font-size: 11px;")
        lbl_q.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.lbl_priority_quality = lbl_q
        self.lbl_priority_quality.setEnabled(False)

        lbl_r = QLabel(AppContext.tr("lbl_priority_resolution"))
        lbl_r.setStyleSheet("color: #777; font-size: 11px;")
        lbl_r.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.lbl_priority_resolution = lbl_r
        self.lbl_priority_resolution.setEnabled(False)

        row_priority_labels.addWidget(self.lbl_priority_quality)
        row_priority_labels.addWidget(self.lbl_priority_resolution)
        limit_layout.addLayout(row_priority_labels)

        self.slider_compress_priority = QSlider(Qt.Orientation.Horizontal)
        self.slider_compress_priority.setRange(0, 100)
        self.slider_compress_priority.setValue(50)
        self.slider_compress_priority.setEnabled(False)
        self.slider_compress_priority.setStyleSheet("""
            QSlider::groove:horizontal { border: 1px solid #444; height: 4px; background: #333; margin: 6px 0; border-radius: 2px; }
            QSlider::handle:horizontal { background: #3b82f6; border: 1px solid #3b82f6; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
            QSlider::handle:horizontal:disabled { background: #555; border-color: #555; }
        """)
        self.slider_compress_priority.valueChanged.connect(self.settings_changed.emit)
        limit_layout.addWidget(self.slider_compress_priority)
        tab_convert_layout.addWidget(self.grp_limit)

        # Section 4: Naming
        self.grp_naming = self.create_group_box(AppContext.tr("settings_other"))
        nam_layout = QVBoxLayout(self.grp_naming)
        
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
        tab_convert_layout.addWidget(self.grp_naming)
        tab_convert_layout.addStretch()

        # ==========================================
        # TAB 2: REPAIR PREVIEW
        # ==========================================
        self.tab_repair = QWidget()
        tab_repair_layout = QVBoxLayout(self.tab_repair)
        tab_repair_layout.setSpacing(15)
        tab_repair_layout.setContentsMargins(4, 4, 4, 4)

        # Section 1: Save Mode (Dropdown)
        self.grp_repair_mode = self.create_group_box(AppContext.tr("repair_save_mode_title"))
        rep_mode_layout = QVBoxLayout(self.grp_repair_mode)
        self.combo_repair_mode = QComboBox()
        self.combo_repair_mode.addItems([
            AppContext.tr("repair_save_mode_duplicate"),
            AppContext.tr("repair_save_mode_inplace")
        ])
        self.combo_repair_mode.setStyleSheet(APP_DESIGN['nativelike_combo'])
        self.combo_repair_mode.setFixedHeight(28)
        self.combo_repair_mode.currentIndexChanged.connect(self._on_repair_mode_changed)
        rep_mode_layout.addWidget(self.combo_repair_mode)
        tab_repair_layout.addWidget(self.grp_repair_mode)

        # Section 2: Operation Type
        self.grp_op_type = self.create_group_box(AppContext.tr("repair_op_type_title"))
        op_type_layout = QVBoxLayout(self.grp_op_type)
        self.combo_op_type = QComboBox()
        self.combo_op_type.addItems([
            AppContext.tr("repair_op_format"),
            AppContext.tr("repair_op_exif")
        ])
        self.combo_op_type.setStyleSheet(APP_DESIGN['nativelike_combo'])
        self.combo_op_type.setFixedHeight(28)
        self.combo_op_type.currentIndexChanged.connect(self._on_op_type_changed)
        op_type_layout.addWidget(self.combo_op_type)
        tab_repair_layout.addWidget(self.grp_op_type)

        # Section 3A: Scope for Format Repair (Only damaged vs All)
        self.grp_repair_scope = self.create_group_box(AppContext.tr("repair_scope_title"))
        rep_scope_layout = QVBoxLayout(self.grp_repair_scope)
        self.combo_repair_scope = QComboBox()
        self.combo_repair_scope.addItems([
            AppContext.tr("repair_scope_damaged"),
            AppContext.tr("repair_scope_all")
        ])
        self.combo_repair_scope.setStyleSheet(APP_DESIGN['nativelike_combo'])
        self.combo_repair_scope.setFixedHeight(28)
        self.combo_repair_scope.currentIndexChanged.connect(self.settings_changed.emit)
        rep_scope_layout.addWidget(self.combo_repair_scope)
        tab_repair_layout.addWidget(self.grp_repair_scope)

        # Section 3B: Thumbnail Size for EXIF Repair
        self.grp_repair_size = self.create_group_box(AppContext.tr("repair_thumb_size_title"))
        rep_size_layout = QVBoxLayout(self.grp_repair_size)
        self.combo_thumb_size = QComboBox()
        self.combo_thumb_size.addItems([
            AppContext.tr("repair_thumb_160"),
            AppContext.tr("repair_thumb_256"),
            AppContext.tr("repair_thumb_320"),
            AppContext.tr("repair_thumb_512")
        ])
        self.combo_thumb_size.setStyleSheet(APP_DESIGN['nativelike_combo'])
        self.combo_thumb_size.setFixedHeight(28)
        self.combo_thumb_size.currentIndexChanged.connect(self.settings_changed.emit)
        rep_size_layout.addWidget(self.combo_thumb_size)
        self.grp_repair_size.hide()
        tab_repair_layout.addWidget(self.grp_repair_size)

        # Section 4: Info Box (Lossless / Format hint)
        self.info_frame = QFrame()
        self.info_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(59, 130, 246, 0.08);
                border: 1px solid rgba(59, 130, 246, 0.3);
                border-left: 3px solid #3b82f6;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        info_layout = QVBoxLayout(self.info_frame)
        info_layout.setContentsMargins(6, 6, 6, 6)
        self.lbl_repair_info = QLabel(AppContext.tr("repair_format_info"))
        self.lbl_repair_info.setWordWrap(True)
        self.lbl_repair_info.setStyleSheet("color: #93c5fd; font-size: 11px; line-height: 15px; border: none; background: transparent;")
        info_layout.addWidget(self.lbl_repair_info)
        tab_repair_layout.addWidget(self.info_frame)

        tab_repair_layout.addStretch()

        # Add tabs
        self.tab_widget.addTab(self.tab_convert, AppContext.tr("tab_mode_convert"))
        self.tab_widget.addTab(self.tab_repair, AppContext.tr("tab_mode_repair"))
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        main_layout.addWidget(self.tab_widget)

        # Shared Output Folder DropZone at bottom
        self.output_zone = OutputFolderDropZone()
        self.output_zone.folder_dropped.connect(self.set_output_folder)
        self.output_zone.browse_clicked.connect(self.select_output_folder)
        main_layout.addWidget(self.output_zone)

        # Update initial output zone state
        self._update_output_zone_state()

    def _on_op_type_changed(self, idx):
        is_format = (idx == 0)
        self.grp_repair_scope.setVisible(is_format)
        self.grp_repair_size.setVisible(not is_format)
        if is_format:
            self.lbl_repair_info.setText(AppContext.tr("repair_format_info"))
        else:
            self.lbl_repair_info.setText(AppContext.tr("repair_exif_info"))
        self.settings_changed.emit()

    def _on_tab_changed(self, idx):
        self._update_output_zone_state()
        self.settings_changed.emit()

    def _on_repair_mode_changed(self, idx):
        self._update_output_zone_state()
        self.settings_changed.emit()

    def _update_output_zone_state(self):
        current_tab = self.tab_widget.currentIndex()
        if current_tab == 0:
            # Convert tab -> output zone is fully enabled
            self.output_zone.setEnabled(True)
            self.output_zone.setGraphicsEffect(None)
        else:
            # Repair tab -> enabled if duplicate mode (index 0), disabled if in-place (index 1)
            is_inplace = (self.combo_repair_mode.currentIndex() == 1)
            self.output_zone.setEnabled(not is_inplace)

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
            QGroupBox { border: 1px solid #444; border-radius: 6px; margin-top: 14px; font-weight: bold; color: #ddd; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; left: 10px; }
        """)
        return gb

    def on_format_changed(self, idx):
        fmt = self.combo_format.currentText()
        is_lossless_only = fmt in ("PNG", "BMP", "TIFF", "GIF")
        
        if is_lossless_only:
            self.chk_lossless.blockSignals(True)
            self.chk_lossless.setChecked(True)
            self.chk_lossless.setEnabled(False)
            self.chk_lossless.blockSignals(False)
            self.slider_quality.setEnabled(False)
            self.lbl_quality.setEnabled(False)
        else:
            self.chk_lossless.setEnabled(True)
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
            if not self.inp_width.text() or self.inp_width.text() == "0":
                self.inp_width.setText(str(w))
                self.inp_height.setText(str(h))
        
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

    def on_limit_size_toggled(self, checked):
        self.sb_limit_size.setEnabled(checked)
        self.lbl_compress_priority.setEnabled(checked)
        self.lbl_priority_quality.setEnabled(checked)
        self.lbl_priority_resolution.setEnabled(checked)
        self.slider_compress_priority.setEnabled(checked)
        self.settings_changed.emit()

    def get_settings(self):
        idx = self.combo_scale.currentIndex()
        sp = 100
        if idx == 1: sp = 50
        elif idx == 2: sp = 33
        elif idx == 3: sp = 25
        elif idx == 4: sp = self.inp_scale_percent.value()

        # Repair thumb sizes
        thumb_sizes = [(160, 120), (256, 192), (320, 240), (512, 384)]
        t_idx = self.combo_thumb_size.currentIndex()
        thumb_size = thumb_sizes[t_idx] if 0 <= t_idx < len(thumb_sizes) else (160, 120)

        is_format_op = (self.combo_op_type.currentIndex() == 0)

        return {
            'mode': 'convert' if self.tab_widget.currentIndex() == 0 else 'repair',
            'repair_save_mode': 'duplicate' if self.combo_repair_mode.currentIndex() == 0 else 'in_place',
            'repair_op_type': 'format' if is_format_op else 'exif',
            'repair_scope': 'damaged_only' if self.combo_repair_scope.currentIndex() == 0 else 'all',
            'repair_thumb_size': thumb_size,
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
            'output_dir': self.output_dir,
            'limit_size': self.chk_limit_size.isChecked(),
            'max_size_mb': self.sb_limit_size.value(),
            'compress_priority': self.slider_compress_priority.value()
        }

    def update_ui_text(self):
        self.tab_widget.setTabText(0, AppContext.tr("tab_mode_convert"))
        self.tab_widget.setTabText(1, AppContext.tr("tab_mode_repair"))
        
        self.grp_format.setTitle(AppContext.tr("settings_image_format"))
        self.grp_quality.setTitle(AppContext.tr("settings_compression_mode"))
        self.chk_lossless.setText(AppContext.tr("chk_lossless"))
        self.lbl_quality.setText(AppContext.tr("lbl_quality_slider").format(self.slider_quality.value()))
        self.grp_scale.setTitle(AppContext.tr("chk_scale_video"))
        self.grp_naming.setTitle(AppContext.tr("settings_other"))
        self.chk_rename.setText(AppContext.tr("chk_rename"))
        
        if hasattr(self, 'grp_limit'):
            self.grp_limit.setTitle(AppContext.tr("settings_limit_size_group"))
            self.chk_limit_size.setText(AppContext.tr("chk_max_file_size"))
            self.lbl_compress_priority.setText(AppContext.tr("lbl_compress_priority"))
            self.lbl_priority_quality.setText(AppContext.tr("lbl_priority_quality"))
            self.lbl_priority_resolution.setText(AppContext.tr("lbl_priority_resolution"))

        if hasattr(self, 'grp_repair_mode'):
            self.grp_repair_mode.setTitle(AppContext.tr("repair_save_mode_title"))
            cur_mode = self.combo_repair_mode.currentIndex()
            self.combo_repair_mode.blockSignals(True)
            self.combo_repair_mode.clear()
            self.combo_repair_mode.addItems([
                AppContext.tr("repair_save_mode_duplicate"),
                AppContext.tr("repair_save_mode_inplace")
            ])
            self.combo_repair_mode.setCurrentIndex(cur_mode)
            self.combo_repair_mode.blockSignals(False)

        if hasattr(self, 'grp_op_type'):
            self.grp_op_type.setTitle(AppContext.tr("repair_op_type_title"))
            cur_op = self.combo_op_type.currentIndex()
            self.combo_op_type.blockSignals(True)
            self.combo_op_type.clear()
            self.combo_op_type.addItems([
                AppContext.tr("repair_op_format"),
                AppContext.tr("repair_op_exif")
            ])
            self.combo_op_type.setCurrentIndex(cur_op)
            self.combo_op_type.blockSignals(False)

        if hasattr(self, 'grp_repair_scope'):
            self.grp_repair_scope.setTitle(AppContext.tr("repair_scope_title"))
            cur_scope = self.combo_repair_scope.currentIndex()
            self.combo_repair_scope.blockSignals(True)
            self.combo_repair_scope.clear()
            self.combo_repair_scope.addItems([
                AppContext.tr("repair_scope_damaged"),
                AppContext.tr("repair_scope_all")
            ])
            self.combo_repair_scope.setCurrentIndex(cur_scope)
            self.combo_repair_scope.blockSignals(False)

        if hasattr(self, 'grp_repair_size'):
            self.grp_repair_size.setTitle(AppContext.tr("repair_thumb_size_title"))
            cur_size = self.combo_thumb_size.currentIndex()
            self.combo_thumb_size.blockSignals(True)
            self.combo_thumb_size.clear()
            self.combo_thumb_size.addItems([
                AppContext.tr("repair_thumb_160"),
                AppContext.tr("repair_thumb_256"),
                AppContext.tr("repair_thumb_320"),
                AppContext.tr("repair_thumb_512")
            ])
            self.combo_thumb_size.setCurrentIndex(cur_size)
            self.combo_thumb_size.blockSignals(False)

        if hasattr(self, 'lbl_repair_info'):
            is_format = (self.combo_op_type.currentIndex() == 0)
            self.lbl_repair_info.setText(AppContext.tr("repair_format_info") if is_format else AppContext.tr("repair_exif_info"))

