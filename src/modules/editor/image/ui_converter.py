
import os
import time
import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidgetItem, 
                              QHeaderView, QLabel, QSplitter, QAbstractItemView, QProgressBar, 
                              QFileDialog, QFrame, QScrollArea, QStyle)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QPixmap, QIcon
from PIL import Image

from config import AppContext, APP_DESIGN
from .ui_settings import ImageSettingsWidget
from .worker import ImageConverterWorker
from ..video.ui_widgets import IntegratedDropZone
from ..video.ui_table import FileDropTable, DeleteRowDelegate
from ..video.helpers import format_file_info

class ImageConverterWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.files = [] # List of dicts: {path, name, size, width, height, status, row_idx}
        self.output_dir = ""
        self.worker = None
        self.start_time = None
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background-color: #444; }")

        # LEFT PANEL
        self.left_panel = QFrame()
        self.left_panel.setStyleSheet("background-color: #2b2b2b; border-radius: 4px;")
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.table = FileDropTable()
        self.table.files_dropped.connect(self.on_files_dropped)
        self.table.delete_request_signal.connect(self.delete_file)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["#", AppContext.tr("lbl_source_file"), AppContext.tr("lbl_result"), AppContext.tr("lbl_progress")])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(3, 80)
        self.table.verticalHeader().hide()
        self.table.setItemDelegateForColumn(0, DeleteRowDelegate(self.table))
        self.table.setStyleSheet("QTableWidget { background: transparent; color: #eee; border: none; } QHeaderView::section { background: #222; color: #aaa; border: none; font-weight: bold; }")
        
        left_layout.addWidget(self.table)

        self.drop_zone = IntegratedDropZone("drop_image_here")
        self.drop_zone.clicked.connect(self.add_files_dialog)
        self.drop_zone.files_dropped.connect(self.on_files_dropped)
        self.drop_zone.clear_default_requested.connect(self.clear_list)
        left_layout.addWidget(self.drop_zone)

        # RIGHT PANEL
        self.settings_panel = ImageSettingsWidget()
        self.settings_panel.setFixedWidth(380)
        self.settings_panel.output_folder_changed.connect(self.set_output_folder)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.settings_panel)
        scroll.setFixedWidth(400)

        splitter.addWidget(self.left_panel)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        main_layout.addWidget(splitter)

        # BOTTOM BAR
        bottom = QHBoxLayout()
        self.progress_global = QProgressBar()
        self.progress_global.setFixedHeight(25)
        self.progress_global.setStyleSheet("QProgressBar { border: 1px solid #444; border-radius: 4px; text-align: center; color: white; background: #222; } QProgressBar::chunk { background-color: #3b82f6; border-radius: 3px; }")
        bottom.addWidget(self.progress_global)

        self.lbl_timer = QLabel("00:00:00")
        self.lbl_timer.setStyleSheet("color: #aaa; font-size: 12px; margin: 0 10px;")
        bottom.addWidget(self.lbl_timer)

        self.btn_start = QPushButton(AppContext.tr("btn_start"))
        self.btn_start.setFixedSize(120, 35)
        self.btn_start.setStyleSheet(f"QPushButton {{ background: {APP_DESIGN['accent_color']}; color: white; font-weight: bold; border-radius: 4px; }} QPushButton:hover {{ background: #2563eb; }}")
        self.btn_start.clicked.connect(self.start_processing)
        bottom.addWidget(self.btn_start)
        main_layout.addLayout(bottom)

    def add_files_dialog(self):
        img_exts = "*.jpg *.jpeg *.png *.webp *.bmp *.tiff *.heic *.gif *.ico *.svg *.jfif *.pjpeg *.pjp *.avif *.apng *.dng *.raw *.cr2 *.nef *.arw *.sr2"
        fmt = f"Images ({img_exts});;All (*)"
        files, _ = QFileDialog.getOpenFileNames(self, AppContext.tr("msg_select_image_files"), "", fmt)
        if files: self.on_files_dropped(files)

    def on_files_dropped(self, paths):
        # Allow only image extensions
        image_exts = {
            '.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.heic', '.gif', '.ico', '.svg', 
            '.jfif', '.pjpeg', '.pjp', '.avif', '.apng', '.dng', '.raw', '.cr2', '.nef', '.arw', '.sr2'
        }
        
        new_paths = []
        for p in paths:
            if not os.path.isfile(p): continue
            
            ext = os.path.splitext(p)[1].lower()
            if ext not in image_exts:
                print(f"[DEBUG] ImageConverter skipping non-image file: {p}")
                continue
                
            if any(f['path'] == p for f in self.files): continue
            new_paths.append(p)
            
        if not new_paths: return

        self.drop_zone.btn_clear.show()
        start_row = self.table.rowCount()
        for i, path in enumerate(new_paths):
            row = start_row + i
            try:
                with Image.open(path) as img:
                    w, h = img.size
                    res = f"{w}x{h}"
            except:
                w, h, res = 0, 0, "?"

            info = {
                'path': path, 'name': os.path.basename(path), 'size': os.path.getsize(path),
                'width': w, 'height': h, 'res': res, 'status': 'Wait'
            }
            self.files.append(info)
            self.table.insertRow(row)
            
            it_id = QTableWidgetItem(str(row + 1))
            it_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, it_id)
            
            it_src = QTableWidgetItem(format_file_info(info['name'], info['size'], "", info['res']))
            icons_dir = AppContext.find_resource_dir("icons")
            it_src.setIcon(QIcon(os.path.join(icons_dir, "file.svg")))
            it_src.setToolTip(path)
            self.table.setItem(row, 1, it_src)
            self.table.setItem(row, 2, QTableWidgetItem(""))
            self.table.setItem(row, 3, QTableWidgetItem(""))

        if len(self.files) == 1:
            f = self.files[0]
            self.settings_panel.set_file_info(1, f['width'], f['height'])
        else:
            self.settings_panel.set_file_info(len(self.files))

    def delete_file(self, row):
        if 0 <= row < len(self.files):
            del self.files[row]
            self.table.removeRow(row)
            for r in range(self.table.rowCount()):
                self.table.item(r, 0).setText(str(r + 1))
            if not self.files: self.drop_zone.btn_clear.hide()
            self.settings_panel.set_file_info(len(self.files))

    def clear_list(self):
        self.table.setRowCount(0)
        self.files = []
        self.progress_global.setValue(0)
        self.lbl_timer.setText("00:00:00")
        self.drop_zone.btn_clear.hide()

    def set_output_folder(self, path):
        self.output_dir = path

    def start_processing(self):
        if self.btn_start.text() == "СТОП":
            if self.worker: self.worker.stop()
            return

        if not self.files: return
        
        # Reset UI immediately
        self.progress_global.setValue(0)
        self.lbl_timer.setText("00:00:00")
        
        for i in range(len(self.files)):
            self.files[i]['status'] = 'Wait'
            self.files[i]['out_path'] = None # Clear previous results
            if self.table.item(i, 2): self.table.item(i, 2).setText("")
            if self.table.item(i, 3): self.table.item(i, 3).setText("")
            for c in range(4): 
                item = self.table.item(i, c)
                if item: item.setBackground(QColor(0,0,0,0))
        self.btn_start.setText("СТОП")
        self.btn_start.setStyleSheet("background: #ef4444; color: white; font-weight: bold; border-radius: 4px;")
        self.start_time = time.time()
        
        settings = self.settings_panel.get_settings()
        
        self.worker = ImageConverterWorker(self.files, settings)
        self.worker.file_finished.connect(self.on_file_finished)
        self.worker.all_finished.connect(self.on_all_finished)
        self.worker.start()

    def on_file_finished(self, path, success, result):
        row = next((i for i, f in enumerate(self.files) if f['path'] == path), None)
        if row is not None:
            if success:
                self.files[row]['status'] = 'Done'
                self.files[row]['output_path'] = result
                new_size = os.path.getsize(result)
                old_size = self.files[row]['size']
                diff = ((new_size - old_size) / old_size) * 100 if old_size > 0 else 0
                
                self.table.item(row, 2).setText(os.path.basename(result))
                self.table.item(row, 3).setText(f"{diff:+.1f}%")
                for c in range(4): self.table.item(row, c).setBackground(QColor(34, 197, 94, 30))
            else:
                self.table.item(row, 2).setText(f"❌ {result}")
            
            done = sum(1 for f in self.files if f['status'] == 'Done')
            self.progress_global.setValue(int((done / len(self.files)) * 100))
            
            elapsed = int(time.time() - self.start_time)
            self.lbl_timer.setText(f"{elapsed//3600:02}:{(elapsed%3600)//60:02}:{elapsed%60:02}")

    def on_all_finished(self):
        self.btn_start.setText(AppContext.tr("btn_start"))
        self.btn_start.setStyleSheet(f"background: {APP_DESIGN['accent_color']}; color: white; font-weight: bold; border-radius: 4px;")
        self.progress_global.setValue(100)

    def update_ui_text(self):
        self.table.setHorizontalHeaderLabels(["#", AppContext.tr("lbl_source_file"), AppContext.tr("lbl_result"), AppContext.tr("lbl_progress")])
        self.drop_zone.lbl_text.setText(AppContext.tr("drop_image_here"))
        self.btn_start.setText(AppContext.tr("btn_start"))
        if hasattr(self.settings_panel, 'update_ui_text'):
            self.settings_panel.update_ui_text()
