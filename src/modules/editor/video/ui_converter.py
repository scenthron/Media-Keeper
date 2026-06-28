
import os
import time
import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidgetItem, 
                              QHeaderView, QLabel, QLineEdit, QCheckBox, QGroupBox, QSlider, QSplitter, 
                              QAbstractItemView, QMessageBox, QProgressBar, QFileDialog,
                              QFrame, QSpinBox, QScrollArea, QComboBox, QStyle, QStackedWidget)
from PyQt6.QtCore import Qt, QSize, QEvent
from PyQt6.QtGui import QColor, QIcon

from config import AppContext, APP_DESIGN
from .worker import ProbeWorker, ConversionWorker
from .helpers import format_file_info
from .ui_widgets import OutputFolderDropZone, IntegratedDropZone
from .ui_table import FileDropTable, DeleteRowDelegate
from .ui_settings import VideoSettingsWidget
from ..ui_ffmpeg_notice import FFmpegNoticeWidget
from ..ffmpeg_downloader import check_ffmpeg_available

class VideoConverterWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.files = [] # List of dicts
        self.output_dir = "" # Empty = same as source or specific default
        self.worker_probe = None
        self.worker_convert = None
        self.conversion_start_time = None  # Track conversion start
        self.ffmpeg_notice = None
        self.content_widget = None
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Stack для переключения между контентом и уведомлением
        self.stack = QStackedWidget(self)
        main_layout.addWidget(self.stack)
        
        # 1. Виджет уведомления о FFmpeg
        self.ffmpeg_notice = FFmpegNoticeWidget()
        self.ffmpeg_notice.download_finished.connect(self.on_ffmpeg_downloaded)
        self.stack.addWidget(self.ffmpeg_notice)
        
        # 2. Основной контент
        self.content_widget = QWidget()
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(10)

        # 1. Main Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background-color: #444; }")

        # --- LEFT PANEL ---
        self.left_panel = QFrame()
        self.left_panel.setStyleSheet("background-color: #2b2b2b; border-radius: 4px;")
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0) 

        # Table (NOW FIRST)
        self.table = FileDropTable()
        self.table.files_dropped.connect(self.on_files_dropped)
        self.table.delete_request_signal.connect(self.delete_file) # Connect delete
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["#", AppContext.tr("lbl_source_file"), AppContext.tr("lbl_result"), AppContext.tr("lbl_progress")])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch) # Source
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch) # Result
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)   # #
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)   # %
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(3, 80)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)  # Disable editing
        self.table.verticalHeader().hide() # Hide '1', '2' and corner button
        self.table.setStyleSheet("QTableWidget { background: transparent; color: #eee; border: none; } QHeaderView::section { background: #222; color: #aaa; border: none; font-weight: bold; }")
        
        # Set Delegate
        self.table.setItemDelegateForColumn(0, DeleteRowDelegate(self.table))
        
        left_layout.addWidget(self.table)
        
        # Drop Zone (Footer Style)
        self.drop_zone = IntegratedDropZone("drop_video_here")
        self.drop_zone.clicked.connect(self.add_files_dialog)
        self.drop_zone.clear_default_requested.connect(self.clear_list) # Connect trash button
        self.drop_zone.files_dropped.connect(self.on_files_dropped) 
        left_layout.addWidget(self.drop_zone)

        # --- RIGHT PANEL (Settings) ---
        self.settings_panel = VideoSettingsWidget()
        self.settings_panel.setFixedWidth(380) # Set fixed width for the widget itself to match audio/image converters
        self.settings_panel.settings_changed.connect(self.update_naming_format)
        self.settings_panel.output_folder_changed.connect(self.set_output_folder)
        
        # Wrapping in ScrollArea
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidget(self.settings_panel)
        self.scroll_area.setFixedWidth(400) # Match audio/image scroll area width

        splitter.addWidget(self.left_panel)
        splitter.addWidget(self.scroll_area)
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        content_layout.addWidget(splitter)
        
        # Bottom Bar: Progress | Timer | START
        bottom_bar = QHBoxLayout()
        
        self.progress_bar_global = QProgressBar()
        self.progress_bar_global.setFixedHeight(25)
        self.progress_bar_global.setStyleSheet("""
            QProgressBar { border: 1px solid #444; border-radius: 4px; text-align: center; color: white; background: #222; }
            QProgressBar::chunk { background-color: #3b82f6; border-radius: 3px; }
        """)
        bottom_bar.addWidget(self.progress_bar_global)
        
        # Timer label
        self.lbl_timer = QLabel("00:00:00")
        self.lbl_timer.setStyleSheet("color: #aaa; font-size: 12px; margin: 0 10px;")
        bottom_bar.addWidget(self.lbl_timer)
        
        # START button
        self.btn_start = QPushButton(AppContext.tr("btn_start"))
        self.btn_start.setFixedSize(120, 35)
        self.btn_start.setStyleSheet(f"QPushButton {{ background: {APP_DESIGN['accent_color']}; color: white; font-weight: bold; border-radius: 4px; }} QPushButton:hover {{ background: #2563eb; }}")
        self.btn_start.clicked.connect(self.start_conversion)
        bottom_bar.addWidget(self.btn_start)
        
        content_layout.addLayout(bottom_bar)
        
        # Добавляем content_widget в stack
        self.stack.addWidget(self.content_widget)
        
        # Проверяем FFmpeg при инициализации
        self.check_ffmpeg_and_switch()

    def add_files_dialog(self):
        video_exts = "*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.ts *.m2ts *.3gp *.mpeg *.mpg *.m4v *.f4v *.asf *.vob *.m2v *.vro *.divx *.xvid *.ogv *.gif"
        fmt = f"Video Files ({video_exts});;All Files (*)"
        files, _ = QFileDialog.getOpenFileNames(self, AppContext.tr("msg_select_video_files"), "", fmt)
        if files:
            self.on_files_dropped(files)

    def set_output_folder(self, path):
        self.output_dir = path # Keep sync with settings panel

    def clear_list(self):
        self.table.setRowCount(0)
        self.files = []
        self.progress_bar_global.setValue(0)
        self.lbl_timer.setText("00:00:00")
        self.conversion_start_time = None
        self.drop_zone.btn_clear.hide()
    
    def update_naming_format(self):
        """Auto-generate naming based on settings from VideoSettingsWidget"""
        settings = self.settings_panel.get_settings()
        is_prefix = settings['is_prefix']
        add_info = settings['add_info']
        base = "compress"
        
        suffix = ""
        if add_info:
            # Determine current mode
            if settings['mode'] == 'crf':
                crf = settings['crf']
                suffix = f"_(CRF{crf})"
            elif settings['mode'] == 'crf_percent':
                if settings['max_size']:
                    size = settings['max_size']
                    suffix = f"_(max{size}MB)"
                else:
                    percent = settings['percent']
                    suffix = f"_(CRF%{percent})"
            elif settings['mode'] == '2pass':
                if settings['max_size']:
                    size = settings['max_size']
                    suffix = f"_(2pass_max{size}MB)"
                else:
                    percent = settings['percent']
                    suffix = f"_(2pass_{percent}%)"
            
            # Add scale info if enabled
            if settings.get('scale_mode') == 'proportion':
                w = settings.get('target_width', 0)
                h = settings.get('target_height', 0)
                suffix += f"_{w}x{h}"
            else:
                scale_percent = settings.get('scale_percent', 100)
                if scale_percent < 100:
                    suffix += f"_Orig{scale_percent}%"
            
            base = f"compress{suffix}"
        
        if is_prefix:
            self.settings_panel.inp_name_template.setText(f"{base}_")
        else:
            self.settings_panel.inp_name_template.setText(f"_{base}")
    
    def on_files_dropped(self, paths):
        # Filter existing and folders, and VALID VIDEO EXTENSIONS
        video_exts = {
            '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.ts', '.m2ts', '.3gp', 
            '.mpeg', '.mpg', '.m4v', '.f4v', '.asf', '.vob', '.m2v', '.vro', '.divx', '.xvid', '.ogv',
            '.gif'
        }
        
        new_paths = []
        for p in paths:
            if not os.path.exists(p): continue
            if os.path.isdir(p): continue # Skip folders
            
            ext = os.path.splitext(p)[1].lower()
            if ext not in video_exts:
                print(f"[DEBUG] Skipping non-video file: {p}")
                continue
                
            if any(f['path'] == p for f in self.files): continue
            new_paths.append(p)
            
        if not new_paths: return

        # Show clear button
        self.drop_zone.btn_clear.show()

        # Add stubs to table
        start_row = self.table.rowCount()
        for i, path in enumerate(new_paths):
            row = start_row + i
            info = {
                'path': path,
                'name': os.path.basename(path),
                'size': os.path.getsize(path),
                'duration': 0,
                'bitrate': 0,
                'res': '?',
                'codec': '?',
                'width': 0, # Placeholder
                'height': 0, # Placeholder
                'status': 'Wait',
                'row_idx': row # Track row to update later
            }
            self.files.append(info)
            self.table.insertRow(row)
            
            # 0. ID
            item_id = QTableWidgetItem(str(row + 1))
            item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, item_id)
            
            # 1. Source File (name + size placeholder)
            # Use explicit format function here too
            source_text = format_file_info(info['name'], info['size'], '?', '?')
            item_source = QTableWidgetItem(source_text)
            item_source.setToolTip(path)  # Full path in tooltip
            self.table.setItem(row, 1, item_source)
            
            # 2. Result (empty initially)
            item_result = QTableWidgetItem("")
            self.table.setItem(row, 2, item_result)
            
            # 3. % optimization (empty initially)
            item_percent = QTableWidgetItem("")
            item_percent.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, item_percent)
        
        # Immediate update for Proportion mode availability
        self.settings_panel.set_file_info(len(self.files))

        # Start Probe Worker
        self.worker_probe = ProbeWorker(new_paths)
        self.worker_probe.file_analyzed.connect(self.on_file_analyzed)
        self.worker_probe.start()
    
    def on_file_analyzed(self, data):
        """Called when file analysis finishes"""
        # Extract path and info from data dict
        path = data.get('path', '')
        
        row = self.get_row_by_path(path)
        if row is not None and row < len(self.files):
            # Update file info
            self.files[row].update(data)
            
            # Update "Исходный файл" column with formatted info
            formatted_info = format_file_info(
                os.path.basename(path),
                data.get('size', 0),
                data.get('codec', '?'),
                data.get('res', '?')
            )
            source_item = self.table.item(row, 1)
            if source_item:
                source_item.setText(formatted_info)
                
                # Add file icon
                icons_dir = AppContext.find_resource_dir("icons")
                icon = QIcon(os.path.join(icons_dir, "file.svg"))
                source_item.setIcon(icon)
                
                # Add detailed tooltip
                tooltip = self.generate_file_tooltip(path, data)
                source_item.setToolTip(tooltip)
            
            # Update settings panel about file info for proportion mode
            if len(self.files) == 1:
                self.settings_panel.set_file_info(1, data.get('width'), data.get('height'))
            else:
                self.settings_panel.set_file_info(len(self.files))
    
    def generate_file_tooltip(self, file_path, info):
        """Generate detailed tooltip for file"""
        filename = os.path.basename(file_path)
        size_mb = info.get('size', 0) / (1024 * 1024)
        codec = info.get('codec', '?')
        res = info.get('res', '?')
        duration = info.get('duration', 0)
        
        # Format duration
        if duration > 0:
            mins = int(duration // 60)
            secs = int(duration % 60)
            duration_str = f"{mins:02d}:{secs:02d}"
        else:
            duration_str = "?"
        
        # Build tooltip
        tooltip = f"📄 {filename}\n"
        tooltip += f"📁 {file_path}\n"
        tooltip += f"━━━━━━━━━━━━━━━━━━━━━\n"
        tooltip += f"📐 Разрешение: {res}\n"
        tooltip += f"🎬 Кодек: {codec}\n"
        tooltip += f"💾 Размер: {size_mb:.1f} MB\n"
        tooltip += f"⏱ Длительность: {duration_str}"
        
        return tooltip

    def get_row_by_path(self, path):
        for i, f in enumerate(self.files):
            if f['path'] == path:
                return i
        return None

    def get_file_info_by_row(self, row):
        """Safe access to files list"""
        if 0 <= row < len(self.files):
            return self.files[row]
        return None

    def start_conversion(self):
        if self.btn_start.text() == AppContext.tr("btn_stop"):
            self.stop_conversion()
            return

        if not self.files:
            return
        
        # Reset all files to Wait status and clear visual effects
        for idx, file_info in enumerate(self.files):
            file_info['status'] = 'Wait'
            file_info['progress'] = None
            if 'output_path' in file_info:
                del file_info['output_path']
            
            # Clear Result and % columns
            self.table.item(idx, 2).setText("")
            self.table.item(idx, 3).setText("")
            
            # Remove row highlighting
            for col in range(self.table.columnCount()):
                item = self.table.item(idx, col)
                if item:
                    item.setBackground(QColor(0, 0, 0, 0))  # Transparent
            
            # Trigger repaint of # column
            self.table.viewport().update(self.table.visualRect(self.table.model().index(idx, 0)))
        
        # Build settings from settings panel
        settings = self.settings_panel.get_settings()
        settings['output_dir'] = self.output_dir # Ensure output_dir is passed
        
        self.btn_start.setText("СТОП")
        self.btn_start.setStyleSheet("QPushButton { background-color: #ef4444; color: white; font-weight: bold; border-radius: 4px; } QPushButton:hover { background-color: #dc2626; }")
        
        self.progress_bar_global.setValue(0)
        self.conversion_start_time = time.time()  # Save start time
        
        # Prepare queue (only Wait items)
        queue = [f for f in self.files] 
        
        self.worker_convert = ConversionWorker(queue, settings)
        self.worker_convert.progress_updated.connect(self.on_convert_progress)
        self.worker_convert.file_finished.connect(self.on_convert_file_finished)
        self.worker_convert.all_finished.connect(self.on_convert_finished)
        self.worker_convert.start()

    def stop_conversion(self):
        if self.worker_convert and self.worker_convert.isRunning():
            self.worker_convert.terminate_process()
            self.btn_start.setEnabled(False)
            self.btn_start.setText(AppContext.tr("msg_stop_conversion"))

    def on_convert_progress(self, path, percent):
        row = self.get_row_by_path(path)
        if row is not None:
            # Update file status
            if row < len(self.files):
                self.files[row]['status'] = 'Converting'
                self.files[row]['progress'] = percent
            
            # Update % column
            self.table.item(row, 3).setText(f"{percent}%")
            # Trigger repaint of # column
            self.table.viewport().update(self.table.visualRect(self.table.model().index(row, 0)))
            
            # Update global progress bar
            total_files = len(self.files)
            completed_files = sum(1 for f in self.files if f.get('status') == 'Done')
            current_progress = percent / 100.0
            overall_progress = int(((completed_files + current_progress) / total_files) * 100)
            self.progress_bar_global.setValue(overall_progress)
            
            # Update timer label with elapsed time
            if self.conversion_start_time:
                elapsed = int(time.time() - self.conversion_start_time)
                hours = elapsed // 3600
                minutes = (elapsed % 3600) // 60
                seconds = elapsed % 60
                time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                self.lbl_timer.setText(time_str)

    def on_convert_file_finished(self, path, success, msg):
        if path == "Global" and not success:
            QMessageBox.critical(self, AppContext.tr("msg_error_conversion"), f"{AppContext.tr('msg_critical_error')}\n{msg}")
            return

        row = self.get_row_by_path(path)
        if row is not None:
            if success:
                self.files[row]['status'] = 'Done'
                self.files[row]['output_path'] = msg  # Save output path from worker
                
                # Try to get output file info
                output_path = msg
                if output_path and os.path.exists(output_path):
                    output_size = os.path.getsize(output_path)
                    
                    # Calculate percentage change
                    original_size = self.files[row].get('size', 0)
                    if original_size > 0:
                        percent_change = ((output_size - original_size) / original_size) * 100
                        sign = "+" if percent_change > 0 else ""
                        percent_str = f"{sign}{percent_change:.1f}%"
                    else:
                        percent_str = "?"
                    
                    # Get output resolution (may differ if scaled)
                    settings = self.settings_panel.get_settings()
                    scale_mode = settings.get('scale_mode', 'off')
                    
                    orig_width = self.files[row].get('width', 1920)
                    orig_height = self.files[row].get('height', 1080)
                    new_width = orig_width
                    new_height = orig_height
                    output_res = self.files[row].get('res', '?') # Default to original
                    
                    if scale_mode == 'percent':
                        scale_percent = settings.get('scale_percent', 100)
                        if scale_percent < 100:
                            new_width = (int(orig_width * (scale_percent / 100.0)) // 2) * 2
                            new_height = (int(orig_height * (scale_percent / 100.0)) // 2) * 2
                            output_res = f"{new_width}x{new_height}"
                    elif scale_mode == 'proportion':
                        new_width = (settings.get('target_width', orig_width) // 2) * 2
                        new_height = (settings.get('target_height', orig_height) // 2) * 2
                        output_res = f"{new_width}x{new_height}"
                    
                    # Formatted result
                    result_text = format_file_info(
                        os.path.basename(output_path),
                        output_size,
                        self.files[row].get('codec', '?'),
                        output_res
                    )
                    result_item = self.table.item(row, 2)
                    result_item.setText(result_text)
                    
                    # Add file icon
                    icons_dir = AppContext.find_resource_dir("icons")
                    icon = QIcon(os.path.join(icons_dir, "file.svg"))
                    result_item.setIcon(icon)
                    
                    # Add detailed tooltip
                    result_info = {
                        'size': output_size,
                        'codec': self.files[row].get('codec', '?'),
                        'res': output_res,
                        'duration': self.files[row].get('duration', 0),
                        'width': new_width,
                        'height': new_height
                    }
                    tooltip = self.generate_file_tooltip(output_path, result_info)
                    result_item.setToolTip(tooltip)
                    
                    # Update % column
                    self.table.item(row, 3).setText(percent_str)
                    
                    # Add subtle green row highlight
                    for col in range(self.table.columnCount()):
                        item = self.table.item(row, col)
                        if item:
                            item.setBackground(QColor(34, 197, 94, 30))  # Very subtle green
                else:
                    self.table.item(row, 2).setText(f"✅ {AppContext.tr('msg_done')}")
                
                # Trigger repaint of # column
                self.table.viewport().update(self.table.visualRect(self.table.model().index(row, 0)))
            else:
                self.files[row]['status'] = 'Error'
                self.table.item(row, 2).setText(f"❌ {AppContext.tr('msg_error')}")
                self.table.item(row, 2).setToolTip(msg)
                logging.error(f"[VideoConverter] Ошибка конвертации файла {path}: {msg}")
                print(f"File Error: {msg}")
        else:
            print(f"Unknown file finished: {path} - {msg}")

    def on_convert_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_start.setText(AppContext.tr("btn_start"))
        self.btn_start.setStyleSheet(f"QPushButton {{ background: {APP_DESIGN['accent_color']}; color: white; font-weight: bold; border-radius: 4px; }} QPushButton:hover {{ background: #2563eb; }}")
        self.progress_bar_global.setValue(100)
        
        # Final time display
        if self.conversion_start_time:
            elapsed = int(time.time() - self.conversion_start_time)
            hours = elapsed // 3600
            minutes = (elapsed % 3600) // 60
            seconds = elapsed % 60
            time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            self.lbl_timer.setText(time_str)
            self.conversion_start_time = None
    
    def showEvent(self, event):
        """Проверка FFmpeg при показе виджета"""
        super().showEvent(event)
        self.check_ffmpeg_and_switch()
    
    def check_ffmpeg_and_switch(self):
        """Проверяет наличие FFmpeg и переключает виджеты"""
        is_available, _ = check_ffmpeg_available()
        if is_available:
            self.stack.setCurrentWidget(self.content_widget)
            logging.debug("FFmpeg доступен, показываем контент конвертера")
        else:
            self.stack.setCurrentWidget(self.ffmpeg_notice)
            logging.info("FFmpeg не найден, показываем уведомление")
    
    def on_ffmpeg_downloaded(self, success):
        """Обработчик завершения загрузки FFmpeg"""
        if success:
            logging.info("FFmpeg загружен, переключаемся на контент")
            # Небольшая задержка для завершения установки
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(500, self.check_ffmpeg_and_switch)
        
        print("Conversion finished")

    def delete_file(self, row):
        if 0 <= row < len(self.files):
            # Remove from logic
            del self.files[row]
            # Remove from UI
            self.table.removeRow(row)
            # Re-index remaining
            for r in range(self.table.rowCount()):
                item_id = QTableWidgetItem(str(r + 1))
                item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(r, 0, item_id)

            # If empty, hide clear button
            if not self.files:
                self.drop_zone.btn_clear.hide()
            
            # Update settings panel
            if len(self.files) == 1:
                f = self.files[0]
                self.settings_panel.set_file_info(1, f.get('width'), f.get('height'))
            else:
                self.settings_panel.set_file_info(len(self.files))

    def update_ui_text(self):
        """Обновляет тексты интерфейса при смене языка"""
        # Обновляем заголовки таблицы
        self.table.setHorizontalHeaderLabels(["#", AppContext.tr("lbl_source_file"), AppContext.tr("lbl_result"), AppContext.tr("lbl_progress")])

        # Обновляем кнопку СТАРТ
        if self.btn_start.text() in ["СТАРТ", "START"]:
            self.btn_start.setText(AppContext.tr("btn_start"))
        elif self.btn_start.text() in ["СТОП", "STOP"]:
            self.btn_start.setText(AppContext.tr("btn_stop"))

        # Обновляем компоненты настроек
        if hasattr(self.settings_panel, 'update_ui_text'):
            self.settings_panel.update_ui_text()

        # Обновляем drop zone
        if hasattr(self.drop_zone, 'update_ui_text'):
            self.drop_zone.update_ui_text()
