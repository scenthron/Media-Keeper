
import os
import time
import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidgetItem, 
                              QHeaderView, QLabel, QSplitter, QAbstractItemView, QProgressBar, 
                              QFileDialog, QFrame, QScrollArea, QStyle)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon

from config import AppContext, APP_DESIGN
from .ui_settings import AudioSettingsWidget
from .worker import AudioConverterWorker
from ..video.ui_widgets import IntegratedDropZone
from ..video.ui_table import FileDropTable, DeleteRowDelegate
from ..video.helpers import format_file_info
from ..video.worker import ProbeWorker

class AudioConverterWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.files = [] # {path, name, size, duration, bitrate, status, row_idx}
        self.worker_probe = None
        self.worker_convert = None
        self.start_time = None
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background-color: #444; }")

        # LEFT
        self.left_panel = QFrame()
        self.left_panel.setStyleSheet("background-color: #2b2b2b; border-radius: 4px;")
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
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

        self.drop_zone = IntegratedDropZone("drop_audio_here")
        self.drop_zone.clicked.connect(self.add_files_dialog)
        self.drop_zone.files_dropped.connect(self.on_files_dropped)
        self.drop_zone.clear_default_requested.connect(self.clear_list)
        left_layout.addWidget(self.drop_zone)

        # RIGHT
        self.settings_panel = AudioSettingsWidget()
        self.settings_panel.setFixedWidth(380)
        
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

        # BOTTOM
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
        # Allow audio AND video files (to extract sound)
        audio_exts = "*.mp3 *.wav *.ogg *.flac *.m4a *.aac *.opus *.ac3 *.dts *.wma *.m4b *.m4r *.wv *.ape *.aiff *.aif *.au *.mp2 *.mpk *.snd *.oga"
        video_exts = "*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.ts *.m2ts *.3gp *.mpeg *.mpg *.m4v *.f4v *.asf *.vob *.m2v"
        fmt = f"Audio/Video ({audio_exts} {video_exts});;All (*)"
        files, _ = QFileDialog.getOpenFileNames(self, AppContext.tr("msg_select_audio_files"), "", fmt)
        if files: self.on_files_dropped(files)

    def on_files_dropped(self, paths):
        # Allow audio and video for extraction
        valid_exts = {
            '.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac', '.opus', '.ac3', '.dts', '.wma',
            '.m4b', '.m4r', '.wv', '.ape', '.aiff', '.aif', '.au', '.mp2', '.mpk', '.snd', '.oga',
            '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.ts', '.m2ts', '.3gp', 
            '.mpeg', '.mpg', '.m4v', '.f4v', '.asf', '.vob', '.m2v'
        }
        
        new_paths = []
        for p in paths:
            if not os.path.isfile(p): continue
            
            ext = os.path.splitext(p)[1].lower()
            if ext not in valid_exts:
                print(f"[DEBUG] AudioConverter skipping unsupported file: {p}")
                continue
                
            if any(f['path'] == p for f in self.files): continue
            new_paths.append(p)
            
        if not new_paths: return

        self.drop_zone.btn_clear.show()
        start_row = self.table.rowCount()
        for i, path in enumerate(new_paths):
            row = start_row + i
            info = {
                'path': path, 'name': os.path.basename(path), 'size': os.path.getsize(path),
                'duration': 0, 'bitrate': 0, 'status': 'Wait'
            }
            self.files.append(info)
            self.table.insertRow(row)
            
            it_id = QTableWidgetItem(str(row + 1))
            it_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, it_id)
            
            it_src = QTableWidgetItem(format_file_info(info['name'], info['size'], "?", "?"))
            icons_dir = AppContext.find_resource_dir("icons")
            it_src.setIcon(QIcon(os.path.join(icons_dir, "file.svg")))
            it_src.setToolTip(path)
            self.table.setItem(row, 1, it_src)
            self.table.setItem(row, 2, QTableWidgetItem(""))
            self.table.setItem(row, 3, QTableWidgetItem(""))

        # Start analysis for durations/bitrates
        self.worker_probe = ProbeWorker(new_paths)
        self.worker_probe.file_analyzed.connect(self.on_file_analyzed)
        self.worker_probe.start()

    def on_file_analyzed(self, data):
        path = data.get('path')
        row = next((i for i, f in enumerate(self.files) if f['path'] == path), None)
        if row is not None:
            self.files[row].update(data)
            it_src = self.table.item(row, 1)
            if it_src:
                # Format specific for audio: focus on a_codec and a_br
                codec = data.get('a_codec', '?').upper()
                if codec == '?': codec = data.get('codec', '?').upper() # Fallback
                
                br = data.get('a_br', 0)
                if br == 0: br = data.get('bitrate', 0) # Fallback
                
                br_str = f"{br//1000}kbps" if br > 0 else "?"
                
                channels = data.get('channels', 0)
                ch_str = "Stereo" if channels >= 2 else ("Mono" if channels == 1 else "")
                
                info_line = f"{codec}"
                if ch_str: info_line += f", {ch_str}"
                if br_str != "?": info_line += f", {br_str}"
                
                size_mb = data['size'] / (1024 * 1024)
                it_src.setText(f"{os.path.basename(path)} ({size_mb:.1f}MB, {info_line})")

    def delete_file(self, row):
        if 0 <= row < len(self.files):
            del self.files[row]
            self.table.removeRow(row)
            for r in range(self.table.rowCount()):
                self.table.item(r, 0).setText(str(r + 1))
            if not self.files: self.drop_zone.btn_clear.hide()

    def clear_list(self):
        self.table.setRowCount(0)
        self.files = []
        self.progress_global.setValue(0)
        self.lbl_timer.setText("00:00:00")
        self.drop_zone.btn_clear.hide()

    def start_processing(self):
        if self.btn_start.text() == "СТОП":
            if self.worker_convert: self.worker_convert.stop()
            return

        if not self.files: return
        
        self.progress_global.setValue(0)
        self.lbl_timer.setText("00:00:00")
        self.start_time = time.time()
        
        for i in range(len(self.files)):
            self.files[i]['status'] = 'Wait'
            self.table.item(i, 2).setText("")
            self.table.item(i, 3).setText("")
            for c in range(4): self.table.item(i, c).setBackground(QColor(0,0,0,0))

        settings = self.settings_panel.get_settings()
        self.btn_start.setText("СТОП")
        self.btn_start.setStyleSheet("background: #ef4444; color: white; font-weight: bold; border-radius: 4px;")
        
        self.worker_convert = AudioConverterWorker(self.files, settings)
        self.worker_convert.file_progress.connect(self.on_file_progress)
        self.worker_convert.file_finished.connect(self.on_file_finished)
        self.worker_convert.all_finished.connect(self.on_all_finished)
        self.worker_convert.start()

    def on_file_progress(self, path, percent):
        row = next((i for i, f in enumerate(self.files) if f['path'] == path), None)
        if row is not None:
            self.table.item(row, 3).setText(f"{percent}%")
            
            done_count = sum(1 for f in self.files if f['status'] == 'Done')
            total = len(self.files)
            global_prog = int(((done_count + (percent/100.0)) / total) * 100)
            self.progress_global.setValue(global_prog)
            
            elapsed = int(time.time() - self.start_time)
            self.lbl_timer.setText(f"{elapsed//3600:02}:{(elapsed%3600)//60:02}:{elapsed%60:02}")

    def on_file_finished(self, path, success, result):
        row = next((i for i, f in enumerate(self.files) if f['path'] == path), None)
        if row is not None:
            if success:
                self.files[row]['status'] = 'Done'
                self.files[row]['output_path'] = result
                for c in range(4): self.table.item(row, c).setBackground(QColor(34, 197, 94, 30))
                
                # Analyze ALL results and calculate output size
                out_paths = result.split(";")
                total_out_size = 0
                for p in out_paths:
                    if p and os.path.exists(p):
                        try:
                            total_out_size += os.path.getsize(p)
                        except:
                            pass
                
                # Calculate percentage change
                original_size = self.files[row].get('size', 0)
                if original_size == 0 and os.path.exists(path):
                    try:
                        original_size = os.path.getsize(path)
                    except:
                        pass
                
                if original_size > 0 and total_out_size > 0:
                    percent_change = ((total_out_size - original_size) / original_size) * 100
                    sign = "+" if percent_change > 0 else ""
                    percent_str = f"{sign}{percent_change:.1f}%"
                else:
                    percent_str = "100%"
                
                self.table.item(row, 3).setText(percent_str)
                
                if len(out_paths) > 1:
                    it_res = self.table.item(row, 2)
                    it_res.setText(f"Done: {len(out_paths)} tracks")
                
                for p in out_paths:
                    if not p: continue
                    probe = ProbeWorker([p])
                    probe.file_analyzed.connect(lambda data: self.on_result_analyzed(row, data, len(out_paths) > 1))
                    probe.start()
                    if not hasattr(self, '_result_probes'): self._result_probes = []
                    self._result_probes.append(probe)
            else:
                self.table.item(row, 2).setText(f"❌ {result}")

    def on_result_analyzed(self, row, data, is_multi=False):
        it_res = self.table.item(row, 2)
        if it_res:
            name = os.path.basename(data['path'])
            size_mb = data['size'] / (1024 * 1024)
            
            codec = data.get('a_codec', '?').upper()
            if codec == '?': codec = data.get('codec', '?').upper()
            
            br = data.get('a_br', 0)
            if br == 0: br = data.get('bitrate', 0)
            br_str = f"{br//1000}kbps" if br > 0 else "?"
            
            info = f"({size_mb:.1f}MB, {codec}, {br_str})"
            
            if is_multi:
                # Append info for multi-track
                old_text = it_res.text()
                if "Done:" in old_text: old_text = ""
                new_text = (old_text + " | " if old_text else "") + f"T{len(old_text.split('|')) if old_text else 1}: {info}"
                it_res.setText(new_text)
                it_res.setToolTip(it_res.text().replace(" | ", "\n"))
            else:
                it_res.setText(f"{name} {info}")

    def on_all_finished(self):
        self.btn_start.setText(AppContext.tr("btn_start"))
        self.btn_start.setStyleSheet(f"background: {APP_DESIGN['accent_color']}; color: white; font-weight: bold; border-radius: 4px;")
        self.progress_global.setValue(100)

    def update_ui_text(self):
        self.table.setHorizontalHeaderLabels(["#", AppContext.tr("lbl_source_file"), AppContext.tr("lbl_result"), AppContext.tr("lbl_progress")])
        self.drop_zone.lbl_text.setText(AppContext.tr("drop_audio_here"))
        self.btn_start.setText(AppContext.tr("btn_start"))
        if hasattr(self.settings_panel, 'update_ui_text'):
            self.settings_panel.update_ui_text()
