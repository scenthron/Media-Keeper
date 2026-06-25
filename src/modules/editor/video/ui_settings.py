
import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, 
                              QCheckBox, QGroupBox, QSlider, QSpinBox, QComboBox, QStyle, QMenu)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIntValidator, QCursor, QColor, QFont

from config import AppContext, APP_DESIGN
from .ui_widgets import OutputFolderDropZone

class VideoSettingsWidget(QWidget):
    settings_changed = pyqtSignal()
    output_folder_changed = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.output_dir = ""
        self.is_proportion_mode = False
        self.orig_width = 1920
        self.orig_height = 1080
        self.file_count = 0
        self._sync_lock = False # To prevent recursion when calculating
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(10, 0, 0, 0)

        # Helper styles
        cb_style = """
            QCheckBox { spacing: 8px; color: #eee; font-size: 13px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 3px; border: 1px solid #666; background: #333; }
            QCheckBox::indicator:unchecked:hover { border-color: #888; background: #444; }
            QCheckBox::indicator:checked { background: #3b82f6; border-color: #3b82f6; image: url(src/assets/check.png); }
            QCheckBox::indicator:checked:hover { background: #2563eb; }
        """
        
        # Style for the view (dropdown list) to show disabled items clearly
        combo_view_style = "QListView::item:disabled { color: #555555; background: #2a2a2a; }"
        
        sb_style = """
            QSpinBox { 
                background-color: #3d3d3d; 
                color: white; 
                border: 1px solid #555; 
                border-radius: 4px; 
                padding: 0 4px; 
            }
            QSpinBox:disabled { background-color: #2a2a2a; color: #777; border-color: #444; }
        """

        # Section 1: Output Format
        grp_format = self.create_group_box(AppContext.tr("settings_output_format"))
        fmt_layout = QVBoxLayout(grp_format)
        self.combo_format = QComboBox()
        self.combo_format.addItems(["MP4 (H.264)", "MKV", "MOV", "AVI", "WebM"])
        self.combo_format.setStyleSheet(APP_DESIGN['nativelike_combo'])
        self.combo_format.setFixedHeight(28)
        fmt_layout.addWidget(self.combo_format)
        layout.addWidget(grp_format)

        # Section 2: Quality / Compression
        grp_quality = self.create_group_box(AppContext.tr("settings_compression_mode"))
        qual_layout = QVBoxLayout(grp_quality)
        
        mode_buttons_layout = QHBoxLayout()
        mode_buttons_layout.setSpacing(8)
        
        self.btn_mode_2pass = QPushButton(AppContext.tr("btn_2pass_mode"))
        self.btn_mode_crf = QPushButton(AppContext.tr("btn_crf_mode"))
        self.btn_mode_crf_percent = QPushButton(AppContext.tr("btn_crf_percent_mode"))
        
        mode_btn_style = """
            QPushButton { background: #333; border: 1px solid #555; color: #ccc; padding: 6px 8px; border-radius: 4px; font-size: 13px; font-weight: bold; }
            QPushButton:checked { background: #3b82f6; color: white; border-color: #3b82f6; font-weight: bold; }
            QPushButton:hover:!checked { background: #444; }
        """
        
        # Style for the info icons in buttons
        info_icon_style = "color: #3b82f6; font-weight: bold; font-size: 14px;"
        
        for btn in [self.btn_mode_2pass, self.btn_mode_crf, self.btn_mode_crf_percent]:
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(mode_btn_style)
        
        self.btn_mode_2pass.setChecked(True)
        self.btn_mode_crf.clicked.connect(lambda: self.switch_compression_mode('crf'))
        self.btn_mode_crf_percent.clicked.connect(lambda: self.switch_compression_mode('crf_percent'))
        self.btn_mode_2pass.clicked.connect(lambda: self.switch_compression_mode('2pass'))
        
        self.btn_mode_crf.setToolTip(AppContext.tr("tooltip_crf_mode"))
        self.btn_mode_crf_percent.setToolTip(AppContext.tr("tooltip_crf_percent_mode"))
        self.btn_mode_2pass.setToolTip(AppContext.tr("tooltip_2pass_mode"))
        
        mode_buttons_layout.addWidget(self.btn_mode_2pass)
        mode_buttons_layout.addWidget(self.btn_mode_crf)
        mode_buttons_layout.addWidget(self.btn_mode_crf_percent)
        qual_layout.addLayout(mode_buttons_layout)
        
        # Sliders
        self.slider_container = QWidget()
        slider_layout = QVBoxLayout(self.slider_container)
        slider_layout.setContentsMargins(0, 10, 0, 0)
        
        desc = AppContext.tr("quality_medium")
        self.lbl_slider_value = QLabel(AppContext.tr("lbl_crf_quality").format(23, desc))
        self.lbl_slider_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_slider_value.setStyleSheet("color: #aaa; font-size: 12px; font-weight: bold;")
        slider_layout.addWidget(self.lbl_slider_value)
        
        slider_style = """
            QSlider { 
                min-height: 30px; 
            }
            QSlider::groove:horizontal { 
                border: 1px solid #444; 
                height: 4px; 
                background: #333; 
                margin: 12px 0; 
                border-radius: 2px; 
            }
            QSlider::handle:horizontal { 
                background: #3b82f6; 
                border: 1px solid #3b82f6; 
                width: 16px; 
                height: 16px; 
                margin: -6px 0; 
                border-radius: 8px; 
            }
            QSlider::handle:horizontal:hover { background: #2563eb; }
        """
        
        self.slider_crf = QSlider(Qt.Orientation.Horizontal)
        self.slider_crf.setRange(0, 51)
        self.slider_crf.setValue(23)
        self.slider_crf.setInvertedAppearance(True)
        
        self.slider_crf_percent = QSlider(Qt.Orientation.Horizontal)
        self.slider_crf_percent.setRange(10, 100)
        self.slider_crf_percent.setValue(50)
        self.slider_crf_percent.hide()
        
        self.slider_2pass = QSlider(Qt.Orientation.Horizontal)
        self.slider_2pass.setRange(10, 100)
        self.slider_2pass.setValue(50)
        self.slider_2pass.hide()
        
        for s in [self.slider_crf, self.slider_crf_percent, self.slider_2pass]:
            s.setStyleSheet(slider_style)
            s.valueChanged.connect(self.update_slider_label)
            s.valueChanged.connect(self.settings_changed.emit)
            
        slider_layout.addWidget(self.slider_crf)
        slider_layout.addWidget(self.slider_crf_percent)
        slider_layout.addWidget(self.slider_2pass)
        qual_layout.addWidget(self.slider_container)
        
        # Max Size
        max_size_layout = QHBoxLayout()
        self.chk_max_size = QCheckBox(AppContext.tr("chk_max_file_size"))
        self.chk_max_size.setStyleSheet(cb_style + "QCheckBox:disabled { color: #555; }")
        self.chk_max_size.setEnabled(False)
        self.chk_max_size.toggled.connect(self.toggle_max_size)
        max_size_layout.addWidget(self.chk_max_size)
        
        self.inp_max_size = QSpinBox()
        self.inp_max_size.setRange(1, 20000)
        self.inp_max_size.setValue(10)
        self.inp_max_size.setSuffix(" MB")
        self.inp_max_size.setEnabled(False)
        self.inp_max_size.setFixedHeight(28)
        self.inp_max_size.setStyleSheet(sb_style)
        self.inp_max_size.valueChanged.connect(self.settings_changed.emit)
        max_size_layout.addWidget(self.inp_max_size)
        qual_layout.addLayout(max_size_layout)
        
        # Scale logic (Updated)
        scale_group_layout = QVBoxLayout()
        scale_group_layout.setSpacing(5)
        
        scale_top_layout = QHBoxLayout()
        self.chk_scale_video = QCheckBox(AppContext.tr("chk_scale_video"))
        self.chk_scale_video.setStyleSheet(cb_style)
        self.chk_scale_video.toggled.connect(self.toggle_scale_video)
        scale_top_layout.addWidget(self.chk_scale_video)
        
        self.combo_scale = QComboBox()
        self.combo_scale.addItems([
            AppContext.tr("scale_proportion"),
            AppContext.tr("scale_half"), 
            AppContext.tr("scale_third"), 
            AppContext.tr("scale_quarter"), 
            AppContext.tr("scale_custom")
        ])
        self.combo_scale.setFixedWidth(120)
        self.combo_scale.setFixedHeight(28)
        self.combo_scale.setEnabled(False)
        self.combo_scale.setStyleSheet(APP_DESIGN['nativelike_combo'])
        self.combo_scale.currentIndexChanged.connect(self.on_scale_combo_changed)
        self.combo_scale.view().setStyleSheet(combo_view_style)
        scale_top_layout.addWidget(self.combo_scale)
        
        self.inp_scale_percent = QSpinBox()
        self.inp_scale_percent.setRange(1, 100)
        self.inp_scale_percent.setValue(100)
        self.inp_scale_percent.setSuffix("%")
        self.inp_scale_percent.setFixedWidth(80)
        self.inp_scale_percent.setFixedHeight(28)
        self.inp_scale_percent.setStyleSheet(sb_style)
        self.inp_scale_percent.hide() # Hidden by default
        self.inp_scale_percent.valueChanged.connect(self.settings_changed.emit)
        scale_top_layout.addWidget(self.inp_scale_percent)
        scale_top_layout.addStretch()
        
        scale_group_layout.addLayout(scale_top_layout)
        
        # Proportion inputs (New)
        self.prop_container = QWidget()
        self.prop_container.hide()
        prop_layout = QHBoxLayout(self.prop_container)
        prop_layout.setContentsMargins(25, 0, 0, 0) # Indent from checkbox
        prop_layout.setSpacing(10)
        
        self.inp_width = QLineEdit()
        self.inp_height = QLineEdit()
        v_int = QIntValidator(1, 8192) # General max
        for inp, lbl_key in [(self.inp_width, "lbl_width"), (self.inp_height, "lbl_height")]:
            inp.setValidator(v_int)
            inp.setFixedWidth(70)
            inp.setFixedHeight(28)
            inp.setStyleSheet(APP_DESIGN['nativelike_input'])
            
            l = QLabel(AppContext.tr(lbl_key))
            l.setStyleSheet("color: #aaa; font-size: 11px;")
            prop_layout.addWidget(l)
            prop_layout.addWidget(inp)
            
        self.inp_width.textEdited.connect(self.sync_height)
        self.inp_height.textEdited.connect(self.sync_width)
        
        prop_layout.addStretch()
        scale_group_layout.addWidget(self.prop_container)
        
        qual_layout.addLayout(scale_group_layout)
        layout.addWidget(grp_quality)

        # Section 3: Other (Rename from Audio)
        self.grp_other = self.create_group_box(AppContext.tr("settings_other"))
        oth_layout = QVBoxLayout(self.grp_other)
        self.chk_mute = QCheckBox(AppContext.tr("chk_mute_audio"))
        self.chk_mute.setStyleSheet(cb_style)
        oth_layout.addWidget(self.chk_mute)

        self.chk_copy_stream = QCheckBox(AppContext.tr("chk_copy_stream"))
        self.chk_copy_stream.setStyleSheet(cb_style)
        oth_layout.addWidget(self.chk_copy_stream)
        
        # Naming
        oth_layout.addSpacing(10)
        lbl_naming = QLabel(AppContext.tr("lbl_file_naming"))
        lbl_naming.setStyleSheet("font-weight: bold; color: #ddd;")
        oth_layout.addWidget(lbl_naming)
        
        naming_type_layout = QHBoxLayout()
        self.btn_prefix = QPushButton(AppContext.tr("btn_prefix"))
        self.btn_postfix = QPushButton(AppContext.tr("btn_postfix"))
        for b in [self.btn_prefix, self.btn_postfix]:
            b.setCheckable(True)
            b.setFixedHeight(25)
            b.setStyleSheet("""
                QPushButton { background: #333; color: #ccc; border: 1px solid #555; padding: 4px 10px; }
                QPushButton:checked { background: #3b82f6; color: white; border-color: #3b82f6; }
            """)
        self.btn_postfix.setChecked(True)
        self.btn_prefix.clicked.connect(lambda: self.toggle_naming_type('prefix'))
        self.btn_postfix.clicked.connect(lambda: self.toggle_naming_type('postfix'))
        naming_type_layout.addWidget(self.btn_prefix)
        naming_type_layout.addWidget(self.btn_postfix)
        oth_layout.addLayout(naming_type_layout)
        
        self.inp_name_template = QLineEdit("_compress")
        self.inp_name_template.setStyleSheet(APP_DESIGN['nativelike_input'])
        oth_layout.addWidget(self.inp_name_template)
        
        self.chk_add_info = QCheckBox(AppContext.tr("chk_add_info"))
        self.chk_add_info.setStyleSheet(cb_style)
        self.chk_add_info.toggled.connect(self.settings_changed.emit)
        oth_layout.addWidget(self.chk_add_info)
        layout.addWidget(self.grp_other)

        layout.addStretch()

        # Output Folder Dropzone (Restored Design)
        self.output_zone = OutputFolderDropZone()
        self.output_zone.folder_dropped.connect(self.set_output_folder)
        self.output_zone.browse_clicked.connect(self.select_output_folder)
        self.output_zone.set_folder("") 
        
        layout.addWidget(self.output_zone)
        
        # Устанавливаем режим Размер (2pass) по умолчанию
        self.switch_compression_mode('2pass')

    def select_output_folder(self):
        from PyQt6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, AppContext.tr("msg_select_output_folder"))
        if d: self.set_output_folder(d)

    def set_output_folder(self, path):
        self.output_dir = path
        self.output_zone.set_folder(path)
        self.output_folder_changed.emit(path)

    def calculate_folder_size(self, folder_path):
        if not folder_path or not os.path.exists(folder_path):
            return 0
        total = 0
        try:
            for dirpath, dirnames, filenames in os.walk(folder_path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    if os.path.exists(filepath):
                        total += os.path.getsize(filepath)
        except:
            pass
        return total
    
    def format_folder_size(self, size_bytes):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"

    def create_group_box(self, title):
        gb = QGroupBox(title)
        gb.setStyleSheet("""
            QGroupBox { border: 1px solid #444; border-radius: 6px; margin-top: 20px; font-weight: bold; color: #ddd; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; left: 10px; }
        """)
        return gb

    def switch_compression_mode(self, mode):
        self.btn_mode_crf.setChecked(mode == 'crf')
        self.btn_mode_crf_percent.setChecked(mode == 'crf_percent')
        self.btn_mode_2pass.setChecked(mode == '2pass')
        self.slider_crf.setVisible(mode == 'crf')
        self.slider_crf_percent.setVisible(mode == 'crf_percent')
        self.slider_2pass.setVisible(mode == '2pass')
        self.chk_max_size.setEnabled(mode != 'crf')
        if mode == 'crf': self.chk_max_size.setChecked(False)
        self.update_slider_label()
        self.settings_changed.emit()

    def update_slider_label(self):
        if self.slider_crf.isVisible():
            v = self.slider_crf.value()
            desc = AppContext.tr("quality_high") if v < 20 else (AppContext.tr("quality_medium") if v < 28 else AppContext.tr("quality_low"))
            self.lbl_slider_value.setText(AppContext.tr("lbl_crf_quality").format(v, desc))
        elif self.slider_crf_percent.isVisible():
            self.lbl_slider_value.setText(AppContext.tr("lbl_compress_to_percent").format(self.slider_crf_percent.value()))
        elif self.slider_2pass.isVisible():
            self.lbl_slider_value.setText(AppContext.tr("lbl_2pass_percent").format(self.slider_2pass.value()))

    def toggle_max_size(self, checked):
        self.inp_max_size.setEnabled(checked)
        self.slider_crf_percent.setEnabled(not checked)
        self.slider_2pass.setEnabled(not checked)
        self.settings_changed.emit()

    def toggle_scale_video(self, checked):
        if not checked:
            self.combo_scale.setEnabled(False)
            self.inp_scale_percent.hide()
            self.prop_container.hide()
        else:
            if self.is_proportion_mode:
                self.prop_container.show()
                self.combo_scale.hide()
                self.inp_scale_percent.hide()
            else:
                self.prop_container.hide()
                self.combo_scale.show()
                self.combo_scale.setEnabled(True)
                self.on_scale_combo_changed()
        self.settings_changed.emit()

    def update_proportion_ui(self):
        """Show/hide inputs based on proportion mode"""
        is_prop = (self.combo_scale.currentIndex() == 0)
        if is_prop and self.chk_scale_video.isChecked():
            self.prop_container.show()
            self.inp_scale_percent.hide()
            # Initialize values
            self.inp_width.setText(str(self.orig_width))
            self.inp_height.setText(str(self.orig_height))
        else:
            self.prop_container.hide()
            self.on_scale_combo_changed()
        self.settings_changed.emit()

    def set_file_info(self, count, width=None, height=None):
        """Called when file list changes to update proportion availability"""
        self.file_count = count
        if width and height:
            self.orig_width = width
            self.orig_height = height
        
        # Enable/Disable "Proportion" item in ComboBox (Index 0)
        is_enabled = (self.file_count == 1)
        
        # Standard way to disable item in QComboBox model
        model = self.combo_scale.model()
        if hasattr(model, 'item'): # QStandardItemModel
            item = model.item(0)
            if item:
                item.setEnabled(is_enabled)
                font = item.font()
                if not is_enabled:
                    font.setStrikeOut(True)
                    item.setFont(font)
                    item.setForeground(QColor("#888888"))
                    item.setToolTip(AppContext.tr("tooltip_proportion_single_only"))
                else:
                    font.setStrikeOut(False)
                    item.setFont(font)
                    item.setToolTip("")
                    item.setData(None, Qt.ItemDataRole.ForegroundRole)
        else:
            # Fallback for other models
            idx = model.index(0, 0)
            flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled if is_enabled else Qt.ItemFlag.NoItemFlags
            model.setData(idx, flags, Qt.ItemDataRole.UserRole - 1) # Depends on view delegate
        
        # If current selection is Proportion and now disabled, switch to 1/2
        if not is_enabled and self.combo_scale.currentIndex() == 0:
            self.combo_scale.setCurrentIndex(1)
            # Notify layout about change if checkbox is active
            if self.chk_scale_video.isChecked():
                self.on_scale_combo_changed()
        
        self.update_proportion_ui()

    def sync_height(self, text):
        if self._sync_lock or not text or not self.orig_width or not self.orig_height: return
        try:
            w = int(text)
            if w > self.orig_width: 
                w = self.orig_width
                self.inp_width.setText(str(w))
            
            self._sync_lock = True
            h = int(w * self.orig_height / self.orig_width)
            self.inp_height.setText(str(h))
            self._sync_lock = False
            self.settings_changed.emit()
        except: pass

    def sync_width(self, text):
        if self._sync_lock or not text or not self.orig_width or not self.orig_height: return
        try:
            h = int(text)
            if h > self.orig_height:
                h = self.orig_height
                self.inp_height.setText(str(h))
            
            self._sync_lock = True
            w = int(h * self.orig_width / self.orig_height)
            self.inp_width.setText(str(w))
            self._sync_lock = False
            self.settings_changed.emit()
        except: pass

    def on_scale_combo_changed(self):
        idx = self.combo_scale.currentIndex()
        is_custom = (idx == 4) # Custom
        is_prop = (idx == 0) # Proportion
        
        show_custom = is_custom and self.chk_scale_video.isChecked()
        show_prop = is_prop and self.chk_scale_video.isChecked()
        
        self.inp_scale_percent.setVisible(show_custom)
        self.prop_container.setVisible(show_prop)
        
        if show_prop:
            self.inp_width.setText(str(self.orig_width))
            self.inp_height.setText(str(self.orig_height))
            
        self.settings_changed.emit()

    def toggle_naming_type(self, ntype):
        self.btn_prefix.setChecked(ntype == 'prefix')
        self.btn_postfix.setChecked(ntype == 'postfix')
        self.settings_changed.emit()

    def get_settings(self):
        if self.btn_mode_crf.isChecked(): mode = 'crf'
        elif self.btn_mode_crf_percent.isChecked(): mode = 'crf_percent'
        else: mode = '2pass'
        
        # Scale percent logic
        idx = self.combo_scale.currentIndex()
        if idx == 1: sp = 50
        elif idx == 2: sp = 33
        elif idx == 3: sp = 25
        elif idx == 4: sp = self.inp_scale_percent.value()
        else: sp = 100 # Proportion or default
        
        # Prepare settings dict
        settings = {
            'mode': mode,
            'crf': self.slider_crf.value(),
            'percent': self.slider_crf_percent.value() if mode == 'crf_percent' else self.slider_2pass.value(),
            'max_size': self.inp_max_size.value() if self.chk_max_size.isChecked() else None,
            'extension': self.combo_format.currentText().split(' ')[0].lower(),
            'postfix': self.inp_name_template.text(),
            'is_prefix': self.btn_prefix.isChecked(),
            'add_info': self.chk_add_info.isChecked(),
            'output_dir': self.output_dir,
            'mute': self.chk_mute.isChecked(),
            'copy_stream': self.chk_copy_stream.isChecked()
        }

        if self.chk_scale_video.isChecked():
            if idx == 0: # Proportion
                # Use custom dimensions + flag
                try:
                    target_w = int(self.inp_width.text())
                    target_h = int(self.inp_height.text())
                except:
                    target_w, target_h = self.orig_width, self.orig_height
                
                settings.update({
                    'scale_mode': 'proportion',
                    'target_width': target_w,
                    'target_height': target_h
                })
            else:
                settings.update({
                    'scale_mode': 'percent',
                    'scale_percent': sp
                })
        else:
            settings.update({
                'scale_mode': 'off',
                'scale_percent': 100
            })
            
        return settings

    def update_ui_text(self):
        """Обновляет тексты интерфейса при смене языка"""
        # Обновляем заголовки групп
        for group in self.findChildren(QGroupBox):
            if group.title() == "Формат Вывода" or group.title() == "Output Format":
                group.setTitle(AppContext.tr("settings_output_format"))
            elif group.title() == "Режим сжатия" or group.title() == "Compression Mode":
                group.setTitle(AppContext.tr("settings_compression_mode"))
                
        # Direct update for "Other" group to be reliable
        if hasattr(self, 'grp_other'):
            self.grp_other.setTitle(AppContext.tr("settings_other"))

        # Обновляем кнопки режимов сжатия
        self.btn_mode_crf.setText(AppContext.tr("btn_crf_mode"))
        self.btn_mode_crf_percent.setText(AppContext.tr("btn_crf_percent_mode"))
        self.btn_mode_2pass.setText(AppContext.tr("btn_2pass_mode"))

        # Обновляем чекбоксы
        self.chk_max_size.setText(AppContext.tr("chk_max_file_size"))
        self.chk_scale_video.setText(AppContext.tr("chk_scale_video"))
        self.chk_mute.setText(AppContext.tr("chk_mute_audio"))
        self.chk_copy_stream.setText(AppContext.tr("chk_copy_stream"))
        self.chk_add_info.setText(AppContext.tr("chk_add_info"))

        # Обновляем кнопки префикс/постфикс
        self.btn_prefix.setText(AppContext.tr("btn_prefix"))
        self.btn_postfix.setText(AppContext.tr("btn_postfix"))

        # Обновляем элементы комбобокса масштаба
        self.combo_scale.clear()
        self.combo_scale.addItems([
            AppContext.tr("scale_proportion"),
            AppContext.tr("scale_half"), 
            AppContext.tr("scale_third"), 
            AppContext.tr("scale_quarter"), 
            AppContext.tr("scale_custom")
        ])
        
        # Re-apply disabled state after clear/add if needed
        self.set_file_info(self.file_count)

        # Обновляем метку именования
        for label in self.findChildren(QLabel):
            if label.text() in ["Именование файлов:", "File Naming:"]:
                label.setText(AppContext.tr("lbl_file_naming"))

        # Обновляем превью именования
        if hasattr(self, 'lbl_naming_preview'):
            current_text = self.lbl_naming_preview.text()
            if current_text.startswith("Итоговое имя:") or current_text.startswith("Final name:"):
                preview_part = current_text.split(": ", 1)[1] if ": " in current_text else "-"
                self.lbl_naming_preview.setText(AppContext.tr("lbl_naming_preview").replace(" -", f" {preview_part}"))

        # Update width/height labels if in proportion container
        for label in self.prop_container.findChildren(QLabel):
            if label.text() in ["Ширина", "Width"]:
                label.setText(AppContext.tr("lbl_width"))
            elif label.text() in ["Высота", "Height"]:
                label.setText(AppContext.tr("lbl_height"))

        self.update_slider_label()
        
        # Обновляем зону выходной папки
        if hasattr(self, 'output_zone'):
            self.output_zone.update_ui_text()
