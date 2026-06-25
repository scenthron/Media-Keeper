
import os
import re
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QProgressBar, QLineEdit, QTextEdit, QMessageBox, QGridLayout, QFrame,
    QScrollArea, QWidget, QTabWidget, QTextBrowser, QStyle
)
from PyQt6.QtCore import Qt, QUrl, QSize, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer

from config import AppContext
from utils_common import format_size, markdown_to_html, get_unique_filepath

_ICONS_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons"))

def _svg_to_icon(filename: str, size: int = 20) -> QIcon:
    """Render an SVG file to a QIcon of given pixel size."""
    path = os.path.join(_ICONS_DIR, filename)
    renderer = QSvgRenderer(path)
    if not renderer.isValid():
        return QIcon()
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)

class ProgressDialog(QDialog):
    cancelled = pyqtSignal()

    def __init__(self, message, parent=None, show_cancel=False):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        height = 135 if show_cancel else 100
        self.setFixedSize(380, height)
        self.setStyleSheet("""
            QDialog { background-color: #333333; border: 1px solid #555; border-radius: 8px; }
            QLabel { color: #eeeeee; font-size: 14px; font-weight: bold; }
            QProgressBar { border: 1px solid #444; border-radius: 4px; background-color: #222; text-align: center; color: white; }
            QProgressBar::chunk { background-color: #3b82f6; width: 10px; margin: 0.5px; }
            QPushButton#BtnStop {
                background-color: #ef4444;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 13px;
            }
            QPushButton#BtnStop:hover {
                background-color: #dc2626;
            }
            QPushButton#BtnStop:pressed {
                background-color: #b91c1c;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.label = QLabel(message)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setFixedWidth(350)
        layout.addWidget(self.label)
        
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setFixedHeight(10)
        layout.addWidget(self.bar)

        if show_cancel:
            self.btn_stop = QPushButton(AppContext.tr("btn_stop"))
            self.btn_stop.setObjectName("BtnStop")
            self.btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_stop.clicked.connect(self._on_stop_clicked)
            layout.addWidget(self.btn_stop, 0, Qt.AlignmentFlag.AlignCenter)

    def _on_stop_clicked(self):
        self.cancelled.emit()
        self.reject()

class SmartNameDialog(QDialog):
    def __init__(self, title_key, label_key, parent_dir, current_name="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(AppContext.tr(title_key))
        self.parent_dir = parent_dir
        self.original_name = current_name
        
        # Разделяем базовое имя и расширение, если это файл
        full_path = os.path.join(parent_dir, current_name) if current_name else ""
        if full_path and os.path.isfile(full_path):
            self.base_name, self.ext = os.path.splitext(current_name)
        else:
            self.base_name = current_name
            self.ext = ""
            
        self.setFixedSize(450, 130)
        self.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: white; }
            QLabel { color: white; font-size: 14px; }
            QLineEdit { color: white; background-color: #444; border: 1px solid #555; padding: 4px; border-radius: 4px;}
            QPushButton { color: white; background-color: #555; border: 1px solid #444; padding: 5px; border-radius: 3px;}
            QPushButton:hover { background-color: #666; }
            QLabel#ErrorLabel { color: #fcd34d; font-weight: bold; font-size: 11px; margin-left: 10px; }
            QLabel#ExtLabel { color: #888888; font-size: 13px; font-weight: bold; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(15, 12, 15, 12)
        
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel(AppContext.tr(label_key)))
        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("ErrorLabel")
        self.lbl_error.hide()
        top_row.addWidget(self.lbl_error)
        top_row.addStretch()
        layout.addLayout(top_row)
        
        self.edit_name = QLineEdit(self.base_name)
        layout.addWidget(self.edit_name)
        
        btn_box = QHBoxLayout()
        
        # Format extension for display: show at most 10 chars, truncate with ellipsis if longer
        display_ext = self.ext
        if len(display_ext) > 10:
            display_ext = display_ext[:9] + "..."
            
        self.lbl_ext = QLabel(display_ext)
        self.lbl_ext.setObjectName("ExtLabel")
        if self.ext:
            self.lbl_ext.setToolTip(self.ext)
            
        self.btn_ok = QPushButton(AppContext.tr("btn_rename") if current_name else AppContext.tr("btn_create"))
        self.btn_ok.clicked.connect(self.validate)
        self.btn_cancel = QPushButton(AppContext.tr("btn_cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_box.addWidget(self.lbl_ext)
        btn_box.addStretch()
        btn_box.addWidget(self.btn_ok)
        btn_box.addWidget(self.btn_cancel)
        layout.addLayout(btn_box)
        self.final_name = current_name

    def validate(self):
        new_base = self.edit_name.text().strip()
        if not new_base: return self.show_msg(AppContext.tr("msg_error_name_empty"))
        
        # Добавляем оригинальное расширение обратно
        new_name = new_base + self.ext
        
        if re.search(r'[<>:"/\\|?*]', new_name): return self.show_msg(AppContext.tr("msg_error_chars"))
        
        if self.original_name and new_name == self.original_name:
            self.final_name = new_name
            self.accept()
            return

        target_path = os.path.join(self.parent_dir, new_name)
        if os.path.exists(target_path):
            name_no_ext, ext = os.path.splitext(new_name)
            idx = 1
            while True:
                candidate = f"{name_no_ext}_{idx}{ext}"
                if not os.path.exists(os.path.join(self.parent_dir, candidate)):
                    break
                idx += 1
            
            candidate_base, _ = os.path.splitext(candidate)
            self.edit_name.setText(candidate_base)
            self.show_msg(AppContext.tr("msg_rename_exists"))
            return 
            
        self.final_name = new_name
        self.accept()

    def show_msg(self, text):
        self.lbl_error.setText(text)
        self.lbl_error.show()

class InfoDialog(QDialog):
    # (tr_key, section, icon_or_svg, is_svg)
    _TABS = [
        ("dlg_about_tab_general",  "about",    "info-color.svg",       True),
        ("dlg_about_tab_sorter",   "sorter",   "folder-color.svg",     True),
        ("dlg_about_tab_analyzer", "analyzer", "diagram-pie-color.svg",True),
        ("dlg_about_tab_cleaner",  "cleaner",  "broom-color.svg",      True),
        ("dlg_about_tab_editor",   "editor",   "tools-color.svg",      True),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(AppContext.tr("tooltip_info"))
        self.resize(760, 620)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; color: #cdd6f4; }
            QTabWidget {
                background-color: transparent;
                border: none;
            }
            QTabWidget::pane {
                border: 1px solid #45475a;
                background-color: #181825;
                border-radius: 6px;
                top: -1px;
            }
            QTabBar {
                background-color: transparent;
                border: none;
            }
            QTabBar::tab {
                background-color: #313244;
                color: #a6adc8;
                padding: 8px 18px;
                border: 1px solid #45475a;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-size: 13px;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QTabBar::tab:selected {
                background-color: #89b4fa;
                color: #1e1e2e;
                font-weight: bold;
                border-bottom: 1px solid #181825;
            }
            QTabBar::tab:hover:!selected {
                background-color: #45475a;
                color: #cdd6f4;
            }
            QTextBrowser {
                background-color: #181825;
                color: #cdd6f4;
                border: none;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px;
                padding: 14px;
                selection-background-color: #89b4fa;
                selection-color: #1e1e2e;
            }
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                padding: 6px 16px;
                border-radius: 5px;
                font-size: 13px;
                min-width: 80px;
            }
            QPushButton:hover { background-color: #45475a; }
            QPushButton:pressed { background-color: #89b4fa; color: #1e1e2e; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        self.tabs.tabBar().setFocusPolicy(Qt.FocusPolicy.NoFocus)

        for tr_key, section, icon, is_svg in self._TABS:
            browser = QTextBrowser()
            # Отключаем внутреннюю навигацию — обрабатываем ссылки сами
            browser.setOpenLinks(False)
            browser.setOpenExternalLinks(False)
            browser.anchorClicked.connect(QDesktopServices.openUrl)
            md_text = AppContext.get_manual_section_md(section)
            browser.setHtml(markdown_to_html(md_text))
            if is_svg:
                tab_idx = self.tabs.addTab(browser, f"  {AppContext.tr(tr_key)}")
                self.tabs.setTabIcon(tab_idx, _svg_to_icon(icon, 18))
            else:
                tab_idx = self.tabs.addTab(browser, f"{icon}  {AppContext.tr(tr_key)}")

        self.tabs.setIconSize(QSize(18, 18))

        # Фокусируем текстовый виджет первой вкладки, чтобы избежать выделения табов по умолчанию
        first_widget = self.tabs.widget(0)
        if first_widget:
            first_widget.setFocus()

        self.tabs.currentChanged.connect(lambda idx: self.tabs.widget(idx).setFocus() if self.tabs.widget(idx) else None)

        layout.addWidget(self.tabs)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton("OK")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def retranslate(self):
        self.setWindowTitle(AppContext.tr("tooltip_info"))
        for i, (tr_key, section, icon, is_svg) in enumerate(self._TABS):
            if is_svg:
                self.tabs.setTabText(i, f"  {AppContext.tr(tr_key)}")
                self.tabs.setTabIcon(i, _svg_to_icon(icon, 18))
            else:
                self.tabs.setTabText(i, f"{icon}  {AppContext.tr(tr_key)}")
            browser = self.tabs.widget(i)
            if isinstance(browser, QTextBrowser):
                md_text = AppContext.get_manual_section_md(section)
                browser.setHtml(markdown_to_html(md_text))

class FileConflictDialog(QDialog):
    def __init__(self, filename, dest_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle(AppContext.tr("msg_conflict_title"))
        self.resize(450, 200)
        self.dest_dir = dest_dir
        self.original_extension = os.path.splitext(filename)[1]
        self.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: white; }
            QLabel { color: #dddddd; font-size: 14px; }
            QLineEdit { color: white; background-color: #444; border: 1px solid #555; padding: 6px; border-radius: 4px; font-size: 14px;}
            QPushButton { color: white; background-color: #555; border: 1px solid #444; padding: 6px 12px; border-radius: 4px;}
            QLabel#ErrorLabel { color: #ef4444; font-weight: bold; font-size: 13px; }
        """)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(AppContext.tr("msg_conflict_text").format(filename)))
        layout.addWidget(QLabel(AppContext.tr("msg_enter_new_name")))
        
        # Use smart unique name generator for suggestion
        full_suggested_path = get_unique_filepath(dest_dir, filename)
        suggested_name = os.path.basename(full_suggested_path)
        
        self.input_name = QLineEdit(suggested_name)
        layout.addWidget(self.input_name)
        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("ErrorLabel")
        self.lbl_error.hide()
        layout.addWidget(self.lbl_error)
        btn_box = QHBoxLayout()
        self.btn_ok = QPushButton(AppContext.tr("btn_rename"))
        self.btn_ok.clicked.connect(self.validate)
        self.btn_cancel = QPushButton(AppContext.tr("btn_cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(self.btn_ok)
        btn_box.addWidget(self.btn_cancel)
        layout.addLayout(btn_box)
        self.final_name = suggested_name
    def validate(self):
        name = self.input_name.text().strip()
        if not name: return self.err(AppContext.tr("msg_error_name_empty"))
        if re.search(r'[<>:"/\\|?*]', name): return self.err(AppContext.tr("msg_error_chars"))
        if os.path.exists(os.path.join(self.dest_dir, name)): return self.err(AppContext.tr("msg_error_exists"))
        self.final_name = name
        self.accept()
    def err(self, m):
        self.lbl_error.setText(m)
        self.lbl_error.show()

class FolderStatsDialog(QDialog):
    def __init__(self, folder_path, parent=None):
        super().__init__(parent)
        self.folder_path = folder_path
        self.setWindowTitle(AppContext.tr("dlg_stats_title"))
        self.setFixedSize(500, 250)
        self.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: white; }
            QLabel { color: #cccccc; font-size: 14px; }
            QLabel#Title { color: white; font-size: 16px; font-weight: bold; margin-bottom: 10px; }
            QLabel#Header { color: #3b82f6; font-size: 14px; font-weight: bold; text-decoration: underline;}
            QLabel#Value { color: white; font-weight: bold; }
            QFrame#Sep { border-top: 1px solid #444; }
            QPushButton { background-color: #555; color: white; padding: 6px 15px; border-radius: 4px; border: 1px solid #444; }
            QPushButton:hover { background-color: #666; }
        """)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        
        lbl_title = QLabel(f"{AppContext.tr('lbl_auto_folder')} {os.path.basename(folder_path)}")
        lbl_title.setObjectName("Title")
        self.layout.addWidget(lbl_title)
        
        # Grid for Stats
        grid_widget = QFrame()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setSpacing(15)
        
        # Headers
        grid_layout.addWidget(QLabel(AppContext.tr("stat_param")), 0, 0)
        
        lbl_local = QLabel(AppContext.tr("stat_local"))
        lbl_local.setObjectName("Header")
        grid_layout.addWidget(lbl_local, 0, 1)
        
        lbl_recursive = QLabel(AppContext.tr("stat_recursive"))
        lbl_recursive.setObjectName("Header")
        grid_layout.addWidget(lbl_recursive, 0, 2)
        
        # Separator line
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #555;")
        grid_layout.addWidget(line, 1, 0, 1, 3)
        
        # Data Rows
        self.val_l_files = QLabel("...")
        self.val_r_files = QLabel("...")
        self.val_l_folders = QLabel("...")
        self.val_r_folders = QLabel("...")
        self.val_l_size = QLabel("...")
        self.val_r_size = QLabel("...")
        
        for l in [self.val_l_files, self.val_r_files, self.val_l_folders, self.val_r_folders, self.val_l_size, self.val_r_size]:
            l.setObjectName("Value")

        # Row 2: Files
        grid_layout.addWidget(QLabel(AppContext.tr("stat_files")), 2, 0)
        grid_layout.addWidget(self.val_l_files, 2, 1)
        grid_layout.addWidget(self.val_r_files, 2, 2)
        
        # Row 3: Folders
        grid_layout.addWidget(QLabel(AppContext.tr("stat_folders")), 3, 0)
        grid_layout.addWidget(self.val_l_folders, 3, 1)
        grid_layout.addWidget(self.val_r_folders, 3, 2)
        
        # Row 4: Size
        grid_layout.addWidget(QLabel(AppContext.tr("stat_size")), 4, 0)
        grid_layout.addWidget(self.val_l_size, 4, 1)
        grid_layout.addWidget(self.val_r_size, 4, 2)
        
        self.layout.addWidget(grid_widget)
        self.layout.addStretch()
        
        btn_close = QPushButton(AppContext.tr("btn_close"))
        btn_close.clicked.connect(self.accept)
        h_btn = QHBoxLayout()
        h_btn.addStretch()
        h_btn.addWidget(btn_close)
        self.layout.addLayout(h_btn)
        
        # Start calc
        self.calculate_stats()

    def calculate_stats(self):
        l_files = 0
        l_folders = 0
        l_size = 0
        l_hidden_files = 0
        l_hidden_folders = 0
        
        r_files = 0
        r_folders = 0
        r_size = 0
        r_hidden_files = 0
        r_hidden_folders = 0
        
        def is_hidden(filepath):
            basename = os.path.basename(filepath)
            if basename.startswith('.'):
                return True
            if os.name == 'nt':
                import ctypes
                try:
                    attrs = ctypes.windll.kernel32.GetFileAttributesW(filepath)
                    return attrs != -1 and bool(attrs & 2) # FILE_ATTRIBUTE_HIDDEN = 2
                except:
                    return False
            return False
            
        try:
            # 1. Local Scan (Fast)
            with os.scandir(self.folder_path) as it:
                for entry in it:
                    is_entry_hidden = is_hidden(entry.path)
                    if entry.is_file():
                        l_files += 1
                        l_size += entry.stat().st_size
                        if is_entry_hidden:
                            l_hidden_files += 1
                    elif entry.is_dir():
                        l_folders += 1
                        if is_entry_hidden:
                            l_hidden_folders += 1

            # 2. Recursive Scan (Can be slow, technically should be threaded but ok for now)
            for root, dirs, files in os.walk(self.folder_path):
                # Count files
                for f in files:
                    fp = os.path.join(root, f)
                    r_files += 1
                    try: r_size += os.path.getsize(fp)
                    except: pass
                    if is_hidden(fp):
                        r_hidden_files += 1
                
                # Count folders
                for d in dirs:
                    dp = os.path.join(root, d)
                    r_folders += 1
                    if is_hidden(dp):
                        r_hidden_folders += 1

            # Update UI
            hidden_label = AppContext.tr("stat_hidden")
            self.val_l_files.setText(f"{l_files} ({hidden_label}: {l_hidden_files})")
            self.val_l_folders.setText(f"{l_folders} ({hidden_label}: {l_hidden_folders})")
            self.val_l_size.setText(format_size(l_size))
            
            self.val_r_files.setText(f"{r_files} ({hidden_label}: {r_hidden_files})")
            self.val_r_folders.setText(f"{r_folders} ({hidden_label}: {r_hidden_folders})")
            self.val_r_size.setText(format_size(r_size))

        except Exception as e:
            self.val_l_files.setText("Error")
            print(f"Stats error: {e}")


class FileDeletionConfirmDialog(QDialog):
    def __init__(self, file_paths, parent=None):
        super().__init__(parent)
        self.setWindowTitle(AppContext.tr("dlg_confirm_del_title"))
        self.setStyleSheet("QDialog { background-color: #2b2b2b; color: white; }")
        self.setFixedSize(450, 280)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(15)

        icon_lbl = QLabel("🚨")
        icon_lbl.setStyleSheet("font-size: 42px; background: transparent; border: none; color: #ef4444;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        
        # Calculate total size of all files
        total_size = 0
        for path in file_paths:
            try:
                if os.path.exists(path):
                    total_size += os.path.getsize(path)
            except:
                pass
        size_str = format_size(total_size)
        
        title_text = AppContext.tr("dlg_confirm_del_question").format(len(file_paths), size_str)
        title_lbl = QLabel(title_text)
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #f87171; background: transparent;")
        title_lbl.setWordWrap(True)
        
        warn_msg = AppContext.tr("dlg_confirm_del_warning")
        msg_lbl = QLabel(warn_msg)
        msg_lbl.setStyleSheet("font-size: 11px; color: #cccccc; background: transparent;")
        msg_lbl.setWordWrap(True)
        
        text_layout.addWidget(title_lbl)
        text_layout.addWidget(msg_lbl)
        
        header_layout.addWidget(icon_lbl, 1) # 1/3 width
        header_layout.addLayout(text_layout, 2) # 2/3 width
        main_layout.addLayout(header_layout)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(80)
        scroll.setMaximumHeight(120)
        scroll.setStyleSheet("""
            QScrollArea {
                background-color: #1f2937;
                border-radius: 6px;
                border: 1px solid #374151;
            }
            QScrollBar:vertical {
                width: 6px;
                background: transparent;
            }
            QScrollBar::handle:vertical {
                background: #4b5563;
                border-radius: 3px;
                min-height: 15px;
            }
            QScrollBar::handle:vertical:hover {
                background: #3b82f6;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                border: none;
                background: none;
            }
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {
                border: none;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(10, 8, 10, 8)
        scroll_layout.setSpacing(4)
        
        for path in file_paths:
            fn = os.path.basename(path)
            size_str_file = ""
            try:
                if os.path.exists(path):
                    size_bytes = os.path.getsize(path)
                    size_str_file = f" ({format_size(size_bytes)})"
            except:
                pass
                
            flbl = QLabel(f"{fn}{size_str_file}")
            flbl.setStyleSheet("font-size: 11px; color: #9ca3af; background: transparent; border: none;")
            flbl.setWordWrap(True)
            scroll_layout.addWidget(flbl)
            
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        btns_layout = QHBoxLayout()
        btns_layout.setSpacing(10)
        
        b_del = QPushButton(AppContext.tr("btn_delete_simple"))
        b_del.setCursor(Qt.CursorShape.PointingHandCursor)
        b_del.setStyleSheet("""
            QPushButton { 
                background-color: #dc2626; color: white; font-weight: bold; 
                padding: 8px 20px; border-radius: 4px; border: none; font-size: 13px;
            } 
            QPushButton:hover { background-color: #ef4444; }
        """)
        b_del.clicked.connect(self.accept)
        
        b_cancel = QPushButton(AppContext.tr("btn_cancel"))
        b_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        b_cancel.setStyleSheet("""
            QPushButton { 
                background-color: #555; color: white; 
                padding: 8px 15px; border-radius: 4px; border: 1px solid #666; font-size: 13px;
            } 
            QPushButton:hover { background-color: #666; border-color: #777; }
        """)
        b_cancel.clicked.connect(self.reject)
        
        btns_layout.addStretch()
        btns_layout.addWidget(b_del)
        btns_layout.addWidget(b_cancel)
        main_layout.addLayout(btns_layout)


class BatchRenameErrorsDialog(QDialog):
    def __init__(self, errors: list[str], parent: QWidget = None) -> None:
        if not isinstance(parent, QWidget):
            parent = None
        super().__init__(parent)
        self.setWindowTitle(AppContext.tr("dlg_rename_errors_title"))
        self.setStyleSheet("QDialog { background-color: #2b2b2b; color: white; }")
        self.setFixedSize(450, 280)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(15)

        icon_lbl = QLabel()
        pixmap = self.style().standardPixmap(QStyle.StandardPixmap.SP_MessageBoxWarning)
        scaled_pixmap = pixmap.scaled(42, 42, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        icon_lbl.setPixmap(scaled_pixmap)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        
        title_text = AppContext.tr("dlg_rename_errors_fail")
        title_lbl = QLabel(title_text)
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #f87171; background: transparent;")
        title_lbl.setWordWrap(True)
        
        warn_msg = AppContext.tr("dlg_rename_errors_conflict")
        msg_lbl = QLabel(warn_msg)
        msg_lbl.setStyleSheet("font-size: 11px; color: #cccccc; background: transparent;")
        msg_lbl.setWordWrap(True)
        
        text_layout.addWidget(title_lbl)
        text_layout.addWidget(msg_lbl)
        
        header_layout.addWidget(icon_lbl, 1) # 1/3 width
        header_layout.addLayout(text_layout, 2) # 2/3 width
        main_layout.addLayout(header_layout)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(80)
        scroll.setMaximumHeight(120)
        scroll.setStyleSheet("""
            QScrollArea {
                background-color: #1f2937;
                border-radius: 6px;
                border: 1px solid #374151;
            }
            QScrollBar:vertical {
                width: 6px;
                background: transparent;
            }
            QScrollBar::handle:vertical {
                background: #4b5563;
                border-radius: 3px;
                min-height: 15px;
            }
            QScrollBar::handle:vertical:hover {
                background: #3b82f6;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                border: none;
                background: none;
            }
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {
                border: none;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(10, 8, 10, 8)
        scroll_layout.setSpacing(4)
        
        for err in errors:
            flbl = QLabel(err)
            flbl.setStyleSheet("font-size: 11px; color: #fca5a5; background: transparent; border: none;")
            flbl.setWordWrap(True)
            scroll_layout.addWidget(flbl)
            
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        btns_layout = QHBoxLayout()
        b_ok = QPushButton(AppContext.tr("btn_ok"))
        b_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        b_ok.setStyleSheet("""
            QPushButton { 
                background-color: #555; color: white; 
                padding: 8px 25px; border-radius: 4px; border: 1px solid #666; font-size: 13px;
                min-width: 80px;
            } 
            QPushButton:hover { background-color: #666; border-color: #777; }
        """)
        b_ok.clicked.connect(self.accept)
        
        btns_layout.addStretch()
        btns_layout.addWidget(b_ok)
        main_layout.addLayout(btns_layout)


class MultiFileConflictDialog(QDialog):
    def __init__(self, conflicts, parent=None):
        super().__init__(parent)
        self.setWindowTitle(AppContext.tr("dlg_name_conflict_title"))
        self.setStyleSheet("QDialog { background-color: #2b2b2b; color: white; }")
        self.setFixedSize(450, 280)
        
        self.result_action = "cancel"
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(15)

        icon_lbl = QLabel("⚠️")
        icon_lbl.setStyleSheet("font-size: 42px; background: transparent; border: none; color: #f59e0b;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        
        title_text = AppContext.tr("dlg_name_conflict_files").format(len(conflicts))
        title_lbl = QLabel(title_text)
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #fbbf24; background: transparent;")
        title_lbl.setWordWrap(True)
        
        warn_msg = AppContext.tr("dlg_name_conflict_exists")
        msg_lbl = QLabel(warn_msg)
        msg_lbl.setStyleSheet("font-size: 11px; color: #cccccc; background: transparent;")
        msg_lbl.setWordWrap(True)
        
        text_layout.addWidget(title_lbl)
        text_layout.addWidget(msg_lbl)
        
        header_layout.addWidget(icon_lbl, 1) # 1/3 width
        header_layout.addLayout(text_layout, 2) # 2/3 width
        main_layout.addLayout(header_layout)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(80)
        scroll.setMaximumHeight(120)
        scroll.setStyleSheet("""
            QScrollArea {
                background-color: #1f2937;
                border-radius: 6px;
                border: 1px solid #374151;
            }
            QScrollBar:vertical {
                width: 6px;
                background: transparent;
            }
            QScrollBar::handle:vertical {
                background: #4b5563;
                border-radius: 3px;
                min-height: 15px;
            }
            QScrollBar::handle:vertical:hover {
                background: #3b82f6;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                border: none;
                background: none;
            }
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {
                border: none;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(10, 8, 10, 8)
        scroll_layout.setSpacing(4)
        
        for src, dst in conflicts:
            fn = os.path.basename(src)
            size_str = ""
            try:
                if os.path.exists(src):
                    size_bytes = os.path.getsize(src)
                    size_str = f" ({format_size(size_bytes)})"
            except:
                pass
                
            flbl = QLabel(f"{fn}{size_str}")
            flbl.setStyleSheet("font-size: 11px; color: #9ca3af; background: transparent; border: none;")
            flbl.setWordWrap(True)
            scroll_layout.addWidget(flbl)
            
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        btns_layout = QHBoxLayout()
        btns_layout.setSpacing(8)
        
        b_rename = QPushButton(AppContext.tr("btn_rename_simple"))
        b_rename.setCursor(Qt.CursorShape.PointingHandCursor)
        b_rename.setStyleSheet("""
            QPushButton { 
                background-color: #2563eb; color: white; font-weight: bold; 
                padding: 8px 16px; border-radius: 4px; border: none; font-size: 13px;
            } 
            QPushButton:hover { background-color: #3b82f6; }
        """)
        b_rename.clicked.connect(self._action_rename)
        
        b_skip = QPushButton(AppContext.tr("btn_skip_simple"))
        b_skip.setCursor(Qt.CursorShape.PointingHandCursor)
        b_skip.setStyleSheet("""
            QPushButton { 
                background-color: #4b5563; color: white; 
                padding: 8px 14px; border-radius: 4px; border: 1px solid #6b7280; font-size: 13px;
            } 
            QPushButton:hover { background-color: #6b7280; border-color: #9ca3af; }
        """)
        b_skip.clicked.connect(self._action_skip)
        
        b_cancel = QPushButton(AppContext.tr("btn_cancel"))
        b_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        b_cancel.setStyleSheet("""
            QPushButton { 
                background-color: #374151; color: #d1d5db; 
                padding: 8px 14px; border-radius: 4px; border: 1px solid #4b5563; font-size: 13px;
            } 
            QPushButton:hover { background-color: #4b5563; border-color: #6b7280; }
        """)
        b_cancel.clicked.connect(self.reject)
        
        btns_layout.addStretch()
        btns_layout.addWidget(b_rename)
        btns_layout.addWidget(b_skip)
        btns_layout.addWidget(b_cancel)
        main_layout.addLayout(btns_layout)

    def _action_rename(self):
        self.result_action = "rename"
        self.accept()

    def _action_skip(self):
        self.result_action = "skip"
        self.accept()


class MoveErrorsDialog(QDialog):
    def __init__(self, failed_pairs, parent=None):
        super().__init__(parent)
        self.setWindowTitle(AppContext.tr("dlg_move_errors_title"))
        self.setStyleSheet("QDialog { background-color: #2b2b2b; color: white; }")
        self.setFixedSize(450, 280)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(15)

        icon_lbl = QLabel("🚨")
        icon_lbl.setStyleSheet("font-size: 42px; background: transparent; border: none; color: #ef4444;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        
        title_text = AppContext.tr("dlg_move_errors_fail").format(len(failed_pairs))
        title_lbl = QLabel(title_text)
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #f87171; background: transparent;")
        title_lbl.setWordWrap(True)
        
        warn_msg = AppContext.tr("dlg_move_errors_busy")
        msg_lbl = QLabel(warn_msg)
        msg_lbl.setStyleSheet("font-size: 11px; color: #cccccc; background: transparent;")
        msg_lbl.setWordWrap(True)
        
        text_layout.addWidget(title_lbl)
        text_layout.addWidget(msg_lbl)
        
        header_layout.addWidget(icon_lbl, 1) # 1/3 width
        header_layout.addLayout(text_layout, 2) # 2/3 width
        main_layout.addLayout(header_layout)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(80)
        scroll.setMaximumHeight(120)
        scroll.setStyleSheet("""
            QScrollArea {
                background-color: #1f2937;
                border-radius: 6px;
                border: 1px solid #374151;
            }
            QScrollBar:vertical {
                width: 6px;
                background: transparent;
            }
            QScrollBar::handle:vertical {
                background: #4b5563;
                border-radius: 3px;
                min-height: 15px;
            }
            QScrollBar::handle:vertical:hover {
                background: #3b82f6;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                border: none;
                background: none;
            }
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {
                border: none;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(10, 8, 10, 8)
        scroll_layout.setSpacing(4)
        
        for src, dst, err_reason in failed_pairs:
            fn = os.path.basename(src)
            flbl = QLabel(f"{fn} — {err_reason}")
            flbl.setStyleSheet("font-size: 11px; color: #fca5a5; background: transparent; border: none;")
            flbl.setWordWrap(True)
            scroll_layout.addWidget(flbl)
            
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        btns_layout = QHBoxLayout()
        b_ok = QPushButton(AppContext.tr("btn_ok"))
        b_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        b_ok.setStyleSheet("""
            QPushButton { 
                background-color: #555; color: white; 
                padding: 8px 25px; border-radius: 4px; border: 1px solid #666; font-size: 13px;
                min-width: 80px;
            } 
            QPushButton:hover { background-color: #666; border-color: #777; }
        """)
        b_ok.clicked.connect(self.accept)
        
        btns_layout.addStretch()
        btns_layout.addWidget(b_ok)
        main_layout.addLayout(btns_layout)

