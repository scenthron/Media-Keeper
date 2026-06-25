
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt
from config import APP_DESIGN, AppContext

class PlaceholderWidget(QWidget):
    def __init__(self, title_key, desc_key, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {APP_DESIGN['bg_color_main']};")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        lbl_title = QLabel(AppContext.tr(title_key))
        lbl_title.setStyleSheet(f"color: {APP_DESIGN['text_color']}; font-size: 32px; font-weight: bold;")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        lbl_desc = QLabel(AppContext.tr(desc_key))
        lbl_desc.setStyleSheet("color: #888; font-size: 16px;")
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(lbl_title)
        layout.addWidget(lbl_desc)

class ConverterWidget(PlaceholderWidget):
    def __init__(self, parent=None):
        super().__init__("ph_converter_title", "ph_converter_desc", parent)

# CleanerWidget удален, так как он реализован в ui_cleaner_module.txt

class AnalyzerWidget(PlaceholderWidget):
    # Stub for future or if ui_analyzer fails to load
    def __init__(self, parent=None):
        super().__init__("ph_analyzer_title", "ph_analyzer_desc", parent)
