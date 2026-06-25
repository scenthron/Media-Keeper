
import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QFrame, QHBoxLayout
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QPainter, QIcon
from PyQt6.QtSvg import QSvgRenderer
from config import APP_DESIGN, AppContext

class MenuButton(QWidget):
    clicked = pyqtSignal()
    
    def __init__(self, text_key, icon="•", parent=None):
        super().__init__(parent)
        self.text_key = text_key
        self.is_active = False
        
        self.setFixedHeight(54)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Explicitly remove borders/outlines to fix visual noise
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("border: none; outline: none;")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 10, 0)
        layout.setSpacing(10)
        
        self.lbl_icon = QLabel()
        self.lbl_icon.setFixedSize(24, 24)
        self.lbl_icon.setStyleSheet("background: transparent; border: none;")
        
        if icon.endswith(".svg"):
            icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
            svg_path = os.path.join(icons_dir, icon)
            if os.path.exists(svg_path):
                renderer = QSvgRenderer(svg_path)
                if renderer.isValid():
                    pixmap = QPixmap(QSize(24, 24))
                    pixmap.fill(Qt.GlobalColor.transparent)
                    painter = QPainter(pixmap)
                    renderer.render(painter)
                    painter.end()
                    self.lbl_icon.setPixmap(pixmap)
                else:
                    self.lbl_icon.setText("•")
            else:
                self.lbl_icon.setText("•")
        else:
            self.lbl_icon.setText(icon)
            
        layout.addWidget(self.lbl_icon)
        
        self.lbl_text = QLabel(AppContext.tr(text_key))
        self.lbl_text.setStyleSheet("color: #eee; font-size: 15px; font-weight: bold; background: transparent; border: none;")
        layout.addWidget(self.lbl_text)
        
        layout.addStretch()
        self.update_style()

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

    def set_active(self, active):
        self.is_active = active
        self.update_style()
        
    def update_text(self):
        self.lbl_text.setText(AppContext.tr(self.text_key))

    def update_style(self):
        bg = APP_DESIGN['menu_btn_active'] if self.is_active else "transparent"
        fg = "white" if self.is_active else "#ccc"
        
        self.setStyleSheet(f"background-color: {bg}; border-radius: 6px; border: none; outline: none;")
        self.lbl_text.setStyleSheet(f"color: {fg}; font-size: 15px; font-weight: bold; background: transparent; border: none;")
        # Keep icon label style transparent and clean
        self.lbl_icon.setStyleSheet("background: transparent; border: none;")

class NavigationDrawer(QWidget):
    tab_changed = pyqtSignal(int)
    about_requested = pyqtSignal()
    global_settings_requested = pyqtSignal()
    close_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.icons_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons"))
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(260)
        # CHANGED: Added border: none to children prevents inheritance issues
        self.setStyleSheet(f"""
            NavigationDrawer {{ background-color: #333333; border-right: 1px solid #555; }}
            * {{ border: none; }}
        """)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 20, 10, 20)
        self.layout.setSpacing(5)
        
        # Header / Logo Row
        header_row = QHBoxLayout()
        header_row.setSpacing(0)
        
        # 1. Dummy Spacer (Left) - Exactly matches Close Button width (30px)
        # This ensures the text in the middle is mathematically centered relative to the drawer width
        dummy_spacer = QWidget()
        dummy_spacer.setFixedSize(30, 30)
        dummy_spacer.setStyleSheet("background: transparent;")
        header_row.addWidget(dummy_spacer)
        
        # Spacer Left
        header_row.addStretch()
        
        lbl_brand = QLabel("MEDIA KEEPER")
        lbl_brand.setStyleSheet("color: white; font-size: 20px; font-weight: 900; letter-spacing: 1px; background: transparent;")
        header_row.addWidget(lbl_brand)
        
        # Spacer Right
        header_row.addStretch()
        
        # 3. Close Button (Right)
        btn_close = QPushButton()
        btn_close.setIcon(QIcon(os.path.join(self.icons_dir, "cross.svg")))
        btn_close.setIconSize(QSize(10, 10))
        btn_close.setFixedSize(30, 30)
        btn_close.setStyleSheet("""
            QPushButton { background: transparent; border: none; }
            QPushButton:hover { background-color: #555; border-radius: 4px; }
        """)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.close_requested.emit)
        header_row.addWidget(btn_close)
        
        self.layout.addLayout(header_row)
        self.layout.addSpacing(20)
        
        self.buttons = []
        self.tab_map = {}

        # Индексы вкладок в QStackedWidget (main.py):
        # 0=Сортировщик, 1=Редактор, 2=Дубликаты, 3=Анализатор

        # Вкладки — новый порядок по приоритету
        tabs = [
            (0, "tab_sorter",    "folder-color.svg"),      # Сортировщик
            (3, "tab_analyzer",  "diagram-pie-color.svg"),  # Анализатор диска
            (2, "tab_cleaner",   "broom-color.svg"),        # Поиск дубликатов
            (1, "tab_converter", "tools-color.svg"),        # Редактор / Конвертер
        ]

        for stack_idx, key, icon in tabs:
            btn = MenuButton(key, icon)
            btn.clicked.connect(lambda i=stack_idx: self.on_tab_click(i))
            self.layout.addWidget(btn)
            self.buttons.append(btn)
            self.tab_map[stack_idx] = btn

        # Разделитель
        self.add_divider()

        # Настройки
        btn_settings = MenuButton("tab_settings", "gear-color.svg")
        btn_settings.clicked.connect(self.global_settings_requested.emit)
        self.layout.addWidget(btn_settings)
        self.buttons.append(btn_settings)

        # О программе
        btn_about = MenuButton("tab_about", "info-color.svg")
        btn_about.clicked.connect(self.about_requested.emit)
        self.layout.addWidget(btn_about)
        self.buttons.append(btn_about)

        self.layout.addStretch()
        
        # Init state
        self.set_active_tab(0)

    def add_divider(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #555; margin: 5px 0;")
        self.layout.addWidget(line)

    def on_tab_click(self, stack_index):
        self.set_active_tab(stack_index)
        self.tab_changed.emit(stack_index)

    def set_active_tab(self, stack_index):
        target_btn = self.tab_map.get(stack_index)
        for btn in self.buttons:
            # Only highlight actual tabs, not About or Settings
            if btn in self.tab_map.values():
                btn.set_active(btn == target_btn)
            else:
                btn.set_active(False)

    def update_ui_text(self):
        for btn in self.buttons:
            btn.update_text()
