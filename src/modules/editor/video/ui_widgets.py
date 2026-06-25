
import os
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import pyqtSignal, Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer
from ui_widgets_base import DropZoneWidget
from config import AppContext

def load_svg_pixmap(file_path: str, size: QSize) -> QPixmap:
    renderer = QSvgRenderer(file_path)
    if not renderer.isValid():
        return QPixmap()
    pixmap = QPixmap(size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap

class OutputFolderDropZone(QFrame):
    """Dashed dropzone for output folder with drag&drop support"""
    folder_dropped = pyqtSignal(str)
    browse_clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.output_path = ""
        # Fixed height to prevent interface jumping when text wraps/unwraps
        self.setFixedHeight(85) 
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2) # Tighter spacing
        
        icons_dir = AppContext.find_resource_dir("icons")
        
        # Row 1: Icon and Text
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.lbl_icon = QLabel()
        self.lbl_icon.setFixedSize(16, 16)
        self.lbl_icon.setPixmap(load_svg_pixmap(os.path.join(icons_dir, "folder-color.svg"), QSize(16, 16)))
        self.lbl_icon.setStyleSheet("border: none; background: transparent;")
        row1.addWidget(self.lbl_icon)
        
        self.lbl_text = QLabel(AppContext.tr("output_folder_title"))
        self.lbl_text.setStyleSheet("color: #eee; font-size: 14px; font-weight: bold; border: none; background: transparent;")
        row1.addWidget(self.lbl_text, 1)

        self.btn_browse = QPushButton("...")
        self.btn_browse.setFixedSize(24, 24)
        self.btn_browse.setStyleSheet("""
            QPushButton { background: #444; border: 1px solid #555; border-radius: 4px; color: #ccc; font-weight: bold; }
            QPushButton:hover { background: #555; color: white; border-color: #eab308; }
        """)
        self.btn_browse.clicked.connect(lambda: self.browse_clicked.emit())

        # Trash button (Clear)
        self.btn_clear = QPushButton()
        self.btn_clear.setIcon(QIcon(os.path.join(icons_dir, "trash-color.svg")))
        self.btn_clear.setIconSize(QSize(12, 12))
        self.btn_clear.setFixedSize(24, 24)
        self.btn_clear.hide()
        self.btn_clear.setStyleSheet("""
            QPushButton { background: #444; border: 1px solid #555; border-radius: 12px; color: #ccc; font-size: 11px; }
            QPushButton:hover { background: #555; color: #ef4444; border-color: #ef4444; }
        """)
        self.btn_clear.clicked.connect(self._clear_folder)
        row1.addWidget(self.btn_browse)
        row1.addWidget(self.btn_clear)
        layout.addLayout(row1)

        # Row 2: Subtext (Hint)
        self.lbl_hint = QLabel(AppContext.tr("output_folder_hint"))
        self.lbl_hint.setStyleSheet("color: #999; font-size: 11px; font-weight: 500; border: none; background: transparent;")
        self.lbl_hint.setWordWrap(True)
        layout.addWidget(self.lbl_hint)
        
        self.update_style(False)

    def update_style(self, active):
        border_color = "#3b82f6" if active else "#555"
        bg_color = "rgba(59, 130, 246, 0.05)" if active else "rgba(255, 255, 255, 0.02)"
        
        self.setStyleSheet(f"""
            OutputFolderDropZone {{
                background-color: {bg_color};
                border: 2px dashed {border_color};
                border-radius: 8px;
            }}
        """)

    def set_folder(self, path):
        self.output_path = path
        if path:
            self.lbl_text.setText(os.path.basename(path) or path)
            self.lbl_text.setStyleSheet("color: #4ade80; font-weight: bold; border: none; background: transparent;")
            self.lbl_hint.setText(path) # Show full path in gray hint
            self.btn_clear.show()
        else:
            self.lbl_text.setText(AppContext.tr("output_folder_title"))
            self.lbl_text.setStyleSheet("color: #eee; font-weight: bold; border: none; background: transparent;")
            self.lbl_hint.setText(AppContext.tr("output_folder_hint"))
            self.btn_clear.hide()

    def _clear_folder(self):
        self.set_folder("")
        self.folder_dropped.emit("")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self.update_style(True)
            event.acceptProposedAction()
    
    def dragLeaveEvent(self, event):
        self.update_style(False)
        
    def dropEvent(self, event):
        self.update_style(False)
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if os.path.isdir(path):
                self.folder_dropped.emit(path)
                event.acceptProposedAction()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.browse_clicked.emit()
        super().mousePressEvent(event)

    def update_ui_text(self):
        """Обновляет тексты интерфейса при смене языка"""
        if self.output_path:
            self.lbl_text.setText(os.path.basename(self.output_path) or self.output_path)
            self.lbl_hint.setText(self.output_path)
        else:
            self.lbl_text.setText(AppContext.tr("output_folder_title"))
            self.lbl_hint.setText(AppContext.tr("output_folder_hint"))

class IntegratedDropZone(DropZoneWidget):
    def __init__(self, text_key="drop_video_here", parent=None):
        if not isinstance(text_key, str):
            parent = text_key
            text_key = "drop_video_here"
            
        super().__init__(parent)
        self.setObjectName("IntegratedDropZone")
        self.text_key = text_key
        self.setFixedHeight(100) 
        
        self.lbl_text.setStyleSheet("color: #777; font-size: 12px; border: none; background: transparent;")
        
        self.btn_add.setFixedSize(80, 30)
        self.btn_add.setText("📄 +")
        self.btn_add.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #888;
                border: 1px solid #555;
                border-radius: 15px;
                font-size: 14px;
                font-weight: bold;
                text-align: center;
            }
            QPushButton:hover {
                background-color: rgba(234, 179, 8, 0.1);
                color: white;
                border-color: #eab308;
            }
        """)

        self.btn_clear.setFixedSize(30, 30)
        self.btn_clear.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #888;
                border: 1px solid #555;
                border-radius: 15px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #444;
                color: #ef4444;
                border-color: #ef4444;
            }
        """)
        
        self.setStyleSheet("""
            #IntegratedDropZone {
                background-color: rgba(255, 255, 255, 0.03);
                border: 2px dashed #555;
                border-radius: 8px;
                margin: 5px;
            }
            #IntegratedDropZone:hover {
                background-color: rgba(255, 255, 255, 0.05);
                border-color: #777;
            }
        """)
        self.update_ui_text()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet("""
                #IntegratedDropZone {
                    background-color: rgba(59, 130, 246, 0.15);
                    border: 2px dashed #3b82f6;
                    border-radius: 8px;
                    margin: 5px;
                }
            """)
        else:
            event.ignore()
            
    def dragLeaveEvent(self, event):
        self.setStyleSheet("""
            #IntegratedDropZone {
                background-color: rgba(255, 255, 255, 0.03);
                border: 2px dashed #555;
                border-radius: 8px;
                margin: 5px;
            }
            #IntegratedDropZone:hover {
                background-color: rgba(255, 255, 255, 0.05);
                border-color: #777;
            }
        """)
        
    def dropEvent(self, event):
        self.setStyleSheet("""
            #IntegratedDropZone {
                background-color: rgba(255, 255, 255, 0.03);
                border: 2px dashed #555;
                border-radius: 8px;
                margin: 5px;
            }
            #IntegratedDropZone:hover {
                background-color: rgba(255, 255, 255, 0.05);
                border-color: #777;
            }
        """)
        super().dropEvent(event)

    def update_ui_text(self):
        """Обновляет тексты интерфейса при смене языка"""
        super().update_ui_text()
        if self.text_key == "drop_video_here":
            self.lbl_text.setText("Перетащите видео файл сюда" if AppContext.LANG == "RU" else "Drop video file here")
        elif self.text_key == "drop_audio_here":
            self.lbl_text.setText("Перетащите видео или аудио файл сюда" if AppContext.LANG == "RU" else "Drop video or audio file here")
        elif self.text_key == "drop_image_here":
            self.lbl_text.setText("Перетащите изображения сюда" if AppContext.LANG == "RU" else "Drop images here")
        else:
            self.lbl_text.setText(AppContext.tr(self.text_key))
