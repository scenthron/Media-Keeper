
import os
from PyQt6.QtWidgets import (
    QPushButton, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QSizeGrip, QFrame, QStackedLayout, QLineEdit, QMenu, QGraphicsOpacityEffect
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QPropertyAnimation, QEasingCurve, QTimer, QPointF, QMimeData, QSize, QRegularExpression
from PyQt6.QtGui import QAction, QColor, QDrag, QIcon, QRegularExpressionValidator
import re
from ui_widgets_base import FlowLayout
from config import AppContext

# ==================================================================================
# НАСТРОЙКИ ДИЗАЙНА ПАНЕЛИ АФФИКСОВ (AFFIX PANEL DESIGN)
# ==================================================================================
AFFIX_DESIGN = {
    "panel_bg": "#2b2b2b",       
    "btn_bg": "#404040",         
    "btn_fg": "#ffffff",         
    "btn_hover": "#505050",      
    "btn_pressed": "#303030",    
    "btn_border": "#555555",     
    "btn_radius": 4,             
    "btn_padding_x": 15,         
    "font_family": "Arial",      
    "font_size": 12,             
    "conflict_color": "#dc2626"  
}

class AffixButton(QPushButton):
    """
    Кнопка для панели аффиксов с поддержкой режима удаления.
    """
    delete_requested = pyqtSignal(object) # signal(self)

    def __init__(self, text, btn_type, payload, callback, parent=None):
        super().__init__(text, parent)
        self.btn_type = btn_type
        self.payload = payload
        self.callback = callback
        
        self.is_delete_mode = False
        
        self.clicked.connect(self._on_pushed)
        
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.apply_base_style()

    def _on_pushed(self):
        if self.is_delete_mode:
            self.delete_requested.emit(self)
        else:
            if self.callback:
                self.callback(self.btn_type, self.payload, self)

    def apply_base_style(self):
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {AFFIX_DESIGN['btn_bg']};
                color: {AFFIX_DESIGN['btn_fg']};
                border: 1px solid {AFFIX_DESIGN['btn_border']};
                border-radius: {AFFIX_DESIGN['btn_radius']}px;
                padding: 4px {AFFIX_DESIGN['btn_padding_x']}px;
                font-family: {AFFIX_DESIGN['font_family']};
                font-size: {AFFIX_DESIGN['font_size']}px;
            }}
            QPushButton:hover {{ background-color: {AFFIX_DESIGN['btn_hover']}; }}
            QPushButton:pressed {{ background-color: {AFFIX_DESIGN['btn_pressed']}; }}
        """)

    def set_delete_style(self):
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {AFFIX_DESIGN['conflict_color']};
                color: white;
                border: 1px solid #991b1b;
                border-radius: {AFFIX_DESIGN['btn_radius']}px;
                padding: 4px {AFFIX_DESIGN['btn_padding_x']}px;
                font-family: {AFFIX_DESIGN['font_family']};
                font-size: {AFFIX_DESIGN['font_size']}px;
            }}
            QPushButton:hover {{ background-color: #b91c1c; }}
        """)
    
    def set_conflict_style(self):
        self.set_delete_style() # Same red style for conflict

    def reset_style(self):
        self.apply_base_style()

    def set_mode(self, delete_mode):
        self.is_delete_mode = delete_mode
        if delete_mode:
            self.set_delete_style()
        else:
            self.reset_style()

    def set_allow_drag(self, allow):
        self._allow_drag = allow
        self._drag_start_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and getattr(self, '_allow_drag', False) and not self.is_delete_mode:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self, '_allow_drag', False) and self._drag_start_pos and not self.is_delete_mode:
            if (event.pos() - self._drag_start_pos).manhattanLength() > 5: # Threshold
                drag = QDrag(self)
                mime = QMimeData()
                mime.setText(self.text()) # Just ID
                drag.setMimeData(mime)
                drag.exec(Qt.DropAction.MoveAction)
                self._drag_start_pos = None
        super().mouseMoveEvent(event)


class AffixDropContainer(QWidget):
    """
    Container that accepts drops from AffixButtons to reorder them.
    """
    reorder_requested = pyqtSignal(int, int) # from_idx, to_idx

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        source = event.source()
        if source and isinstance(source, AffixButton):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        source = event.source()
        if not source or not isinstance(source, AffixButton):
            return

        # Find layout
        layout = self.layout()
        if not layout: return

        # Find source index
        from_idx = -1
        for i in range(layout.count()):
            if layout.itemAt(i).widget() == source:
                from_idx = i
                break
        
        if from_idx == -1: return

        # Find target index by position
        pos = event.position().toPoint()
        
        # Simple heuristic: find widget closest to point?
        # Or just find which widget contains the point.
        # FlowLayout might have gaps.
        
        target_idx = -1
        min_dist = 999999
        
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if not w: continue
            
            # Check if point inside rect?
            # Or assume insert BEFORE the item we dropped on
            w_rect = w.geometry()
            center = w_rect.center()
            dist = (pos - center).manhattanLength()
            
            if w_rect.contains(pos):
                # Dropped ONTO a widget.
                # Decide if before or after based on center
                if pos.x() < center.x():
                    target_idx = i
                else:
                    target_idx = i + 1
                break
                
            # Keep track of closest just in case we are in gap
            if dist < min_dist:
                min_dist = dist
                # Approximate
                if pos.x() < center.x():
                    target_idx = i
                else:
                    target_idx = i + 1
        
        if target_idx == -1:
            target_idx = layout.count() - 1 # Append

        # Adjust target index if shifting
        if target_idx > layout.count(): target_idx = layout.count()
        
        if from_idx != target_idx:
            # If moving down, index shifts because item is removed
            # But abstract logic: move item at `from` to `target`.
            # Let caller handle list logic.
            # But note: if target > from, we must account for removal?
            # Usually easiest is: remove at old, insert at new.
            # If target_idx > from_idx, the actual insertion index in list (after removal) is target_idx - 1?
            # Let logic handle that.
            self.reorder_requested.emit(from_idx, target_idx)
            
        event.acceptProposedAction()

class AffixModeSwitch(QWidget):
    """
    Custom toggle switch for Prefix/Postfix mode.
    """
    mode_changed = pyqtSignal(str) # "prefix" or "postfix"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(140, 22) 
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.current_mode = "prefix"
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.frame = QFrame()
        self.frame.setStyleSheet("""
            QFrame {
                background-color: #333;
                border: none;
                border-radius: 11px;
            }
        """)
        frame_layout = QHBoxLayout(self.frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)
        
        self.lbl_pre = QLabel("PRE -")
        self.lbl_pre.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(self.lbl_pre)
        
        self.lbl_post = QLabel("- POST")
        self.lbl_post.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(self.lbl_post)
        
        layout.addWidget(self.frame)
        self.update_visuals()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle()
        super().mousePressEvent(event)

    def toggle(self):
        if self.current_mode == "prefix":
            self.set_mode("postfix")
        else:
            self.set_mode("prefix")
            
    def set_mode(self, mode):
        self.current_mode = mode
        self.update_visuals()
        self.mode_changed.emit(self.current_mode)

    def get_mode(self):
        return self.current_mode

    def update_visuals(self):
        active_style = "color: white; font-weight: bold; background-color: #3b82f6; border-radius: 10px;"
        inactive_style = "color: #888; font-weight: normal; background-color: transparent;"
        
        if self.current_mode == "prefix":
            self.lbl_pre.setStyleSheet(active_style)
            self.lbl_post.setStyleSheet(inactive_style)
        else:
            self.lbl_pre.setStyleSheet(inactive_style)
            self.lbl_post.setStyleSheet(active_style)


class AffixToolWindow(QWidget):
    """
    Floating window for Affix operations with two pages:
    1. Main Page: Separator | Switch | Settings Button | List of Affixes
    2. Settings Page: Back | Delete Mode | Input New + Helper + Add | List of Affixes (Red in Delete Mode)
    """
    closed = pyqtSignal()
    settings_changed = pyqtSignal(dict) # {separator, list_of_affixes, etc}

    def __init__(self, initial_config, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Window | 
            Qt.WindowType.FramelessWindowHint
        )
        self.setWindowTitle(AppContext.tr("title_affix_window"))
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            AffixToolWindow {{
                background-color: {AFFIX_DESIGN['panel_bg']}; 
                border: 1px solid #555;
            }}
            QLineEdit {{
                background-color: #1a1a1a;
                color: white;
                border: 1px solid #555;
                padding: 3px 6px;
                border-radius: 4px;
            }}
            QLineEdit:focus {{ border-color: #3b82f6; }}
            QPushButton#IconBtn {{
                background: transparent;
                border: none;
                border-radius: 4px;
                color: #ccc;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton#IconBtn:hover {{ background-color: #444; color: white; }}
            QPushButton#PinBtn {{
                background: transparent;
                border: none;
                border-radius: 4px;
            }}
            QPushButton#PinBtn:hover {{ background-color: #444; }}
            QPushButton#PinBtn:checked {{ background-color: #3b82f6; }}
        """)
        self.resize(380, 200) 
        
        self.icons_dir = AppContext.find_resource_dir("icons")
        self.setWindowIcon(QIcon(os.path.join(self.icons_dir, "tag-color.svg")))
        # Data
        self.config = initial_config
        self.affix_items = self._parse_affixes(self.config.get("affix_text", ""))
        self.separator = self.config.get("affix_separator", "_")
        self.current_mode = self.config.get("affix_mode", "prefix") # prefix/postfix
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # START: Title Bar (Shared)
        self._init_title_bar()
        self.layout.addWidget(self.title_bar)
        
        # START: Stacked Content
        self.stack = QStackedLayout()
        self.layout.addLayout(self.stack)
        
        # PAGE 1: Main View
        self.page_main = QWidget()
        self.page_main.setObjectName("PageMain")
        self.page_main.setStyleSheet("QWidget#PageMain { background-color: #2b2b2b; border: none; }")
        self._init_main_page()
        self.stack.addWidget(self.page_main)
        
        # PAGE 2: Settings View
        self.page_settings = QWidget()
        self.page_settings.setObjectName("PageSettings")
        self.page_settings.setStyleSheet("QWidget#PageSettings { background-color: #2b2b2b; border: none; }")
        self._init_settings_page()
        self.stack.addWidget(self.page_settings)
        
        # Grip
        self.grip = QSizeGrip(self)
        self.grip.setFixedSize(16, 16)
        self.grip.setStyleSheet("background: transparent;")
        
        # Drag Logic
        self._dragging = False
        self._drag_start_pos = QPoint()

        # Init state
        self.render_affixes()
        self.mode_switch.set_mode(self.current_mode)
        self.inp_separator.setText(self.separator)

    def _parse_affixes(self, text):
        matches = re.findall(r'<([^>]+)>', text)
        return matches # list of strings

    def _serialize_affixes(self):
        return "".join([f"<{x}>" for x in self.affix_items])

    def _init_title_bar(self):
        self.title_bar = QWidget()
        self.title_bar.setFixedHeight(24)
        self.title_bar.setStyleSheet("background-color: #444; border-bottom: 1px solid #555;")
        
        layout = QHBoxLayout(self.title_bar)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(6)
        
        # Иконка панели аффиксов в заголовке
        self.lbl_title_icon = QLabel()
        self.lbl_title_icon.setFixedSize(14, 14)
        self.lbl_title_icon.setPixmap(QIcon(os.path.join(self.icons_dir, "tag-color.svg")).pixmap(14, 14))
        self.lbl_title_icon.setScaledContents(True)
        layout.addWidget(self.lbl_title_icon)
        
        lbl = QLabel(AppContext.tr("title_affix_window"))
        lbl.setStyleSheet("color: #ccc; font-size: 11px; font-weight: bold;")
        layout.addWidget(lbl)
        
        layout.addStretch()
        
        btn_minimize = QPushButton()
        btn_minimize.setIcon(QIcon(os.path.join(self.icons_dir, "minimize.svg")))
        btn_minimize.setIconSize(QSize(12, 12))
        btn_minimize.setFixedSize(30, 24)
        btn_minimize.setStyleSheet("""
            QPushButton { background: transparent; border: none;}
            QPushButton:hover { background-color: #555; }
        """)
        btn_minimize.clicked.connect(self.showMinimized)
        layout.addWidget(btn_minimize)
        
        btn_close = QPushButton()
        btn_close.setIcon(QIcon(os.path.join(self.icons_dir, "cross.svg")))
        btn_close.setIconSize(QSize(12, 12))
        btn_close.setFixedSize(30, 24)
        btn_close.setStyleSheet("""
            QPushButton { background: transparent; border: none;}
            QPushButton:hover { background-color: #ef4444; }
        """)
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close)

    def _init_main_page(self):
        l = QVBoxLayout(self.page_main)
        l.setContentsMargins(0,0,0,0)
        l.setSpacing(5)
        
        # Header Row
        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(5, 5, 5, 5)
        
        # 1. Separator Input
        self.inp_separator = QLineEdit()
        self.inp_separator.setFixedSize(30, 24)
        self.inp_separator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.inp_separator.setMaxLength(1)
        
        # Запрещаем ввод недопустимых символов для Windows имен файлов: \/:*?"<>|
        sep_rx = QRegularExpression(r"^[^\\/:*?\"<>|]*$")
        self.inp_separator.setValidator(QRegularExpressionValidator(sep_rx, self))
        
        self.inp_separator.setToolTip(AppContext.tr("lbl_separator_tooltip")) # "Separator"
        self.inp_separator.textChanged.connect(self._on_separator_changed)
        hl.addWidget(self.inp_separator)

        # Текст "- разделитель" после поля ввода
        self.lbl_sep_text = QLabel(f"- {AppContext.tr('lbl_separator')}")
        self.lbl_sep_text.setStyleSheet("color: #888; font-size: 11px; font-weight: bold;")
        hl.addWidget(self.lbl_sep_text)
        
        hl.addStretch()
        
        # 2. Switch
        self.mode_switch = AffixModeSwitch()
        self.mode_switch.mode_changed.connect(self._on_mode_changed)
        hl.addWidget(self.mode_switch)
        
        hl.addStretch()

        # 3. Always on Top Button
        self.btn_pin = QPushButton()
        self.btn_pin.setIcon(QIcon(os.path.join(self.icons_dir, "layers-top.svg")))
        self.btn_pin.setIconSize(QSize(18, 18))
        self.btn_pin.setObjectName("PinBtn")
        self.btn_pin.setFixedSize(30, 30)
        self.btn_pin.setCheckable(True)
        self.btn_pin.setToolTip(AppContext.tr("tooltip_always_on_top"))
        self.btn_pin.toggled.connect(self.set_always_on_top)
        hl.addWidget(self.btn_pin)
        
        # 4. Settings Button
        btn_settings = QPushButton()
        btn_settings.setIcon(QIcon(os.path.join(self.icons_dir, "gear-color.svg")))
        btn_settings.setIconSize(QSize(18, 18))
        btn_settings.setObjectName("IconBtn")
        btn_settings.setFixedSize(30, 30)
        btn_settings.setToolTip(AppContext.tr("btn_settings_tooltip")) # "Affix Settings"
        btn_settings.clicked.connect(self._goto_settings)
        hl.addWidget(btn_settings)
        
        l.addWidget(header)
        
        # Content Area
        from PyQt6.QtWidgets import QScrollArea, QFrame
        self.scroll_main = QScrollArea()
        self.scroll_main.setWidgetResizable(True)
        self.scroll_main.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_main.setStyleSheet("QScrollArea { border: none; background-color: #2b2b2b; }")
        
        self.content_main = QWidget()
        self.content_main.setStyleSheet("background-color: #2b2b2b; border: none;")
        self.flow_main = FlowLayout(self.content_main, margin=0, spacing=6)
        self.content_main.setContentsMargins(4, 0, 4, 4)
        
        self.scroll_main.setWidget(self.content_main)
        l.addWidget(self.scroll_main)

    def _init_settings_page(self):
        l = QVBoxLayout(self.page_settings)
        l.setContentsMargins(0,0,0,0)
        l.setSpacing(5)
        
        # Header Row
        header = QWidget()
        header.setStyleSheet("background-color: #383838;") # Slightly darker header
        hl = QHBoxLayout(header)
        hl.setContentsMargins(5, 5, 5, 5)
        
        # 1. Back Button
        btn_back = QPushButton("←")
        btn_back.setObjectName("IconBtn")
        btn_back.setFixedSize(30, 30)
        btn_back.clicked.connect(self._exit_settings)
        hl.addWidget(btn_back)
        
        hl.addStretch()
        
        # 2. Delete Toggle
        self.btn_del_mode = QPushButton()
        self.btn_del_mode.setIcon(QIcon(os.path.join(self.icons_dir, "trash-color.svg")))
        self.btn_del_mode.setIconSize(QSize(18, 18))
        self.btn_del_mode.setCheckable(True)
        self.btn_del_mode.setFixedSize(40, 30)
        self.btn_del_mode.setToolTip(AppContext.tr("btn_delete_mode")) # "Delete Mode"
        self.btn_del_mode.setStyleSheet("""
            QPushButton { background: #444; border: 1px solid #555; border-radius: 4px; }
            QPushButton:checked { background-color: #991b1b; border-color: #ef4444; }
            QPushButton:hover { background-color: #505050; }
        """)
        self.btn_del_mode.toggled.connect(self._on_del_mode_toggled)
        hl.addWidget(self.btn_del_mode)
        
        l.addWidget(header)
        
        # Creator Row
        creator = QWidget()
        creator.setObjectName("CreatorArea")
        creator.setStyleSheet("QWidget#CreatorArea { background-color: #2b2b2b; border: none; }")
        cl = QHBoxLayout(creator)
        cl.setContentsMargins(5, 0, 5, 5)
        
        self.inp_new_affix = QLineEdit()
        
        # Запрещаем ввод недопустимых символов для Windows имен файлов: \/:*?"<>|
        affix_rx = QRegularExpression(r"^[^\\/:*?\"<>|]*$")
        self.inp_new_affix.setValidator(QRegularExpressionValidator(affix_rx, self))
        
        self.inp_new_affix.setPlaceholderText(AppContext.tr("placeholder_new_affix")) # "New affix..."
        self.inp_new_affix.returnPressed.connect(self._create_affix)
        cl.addWidget(self.inp_new_affix)
        
        btn_help = QPushButton("?")
        btn_help.setFixedSize(24, 24)
        btn_help.setStyleSheet("background: #555; color: white; border-radius: 12px; font-weight: bold;")
        btn_help.clicked.connect(self._show_tags_menu)
        cl.addWidget(btn_help)
        
        btn_add = QPushButton("+")
        btn_add.setFixedSize(30, 24)
        btn_add.setStyleSheet("background: #15803d; color: white; border-radius: 4px; font-weight: bold;")
        btn_add.clicked.connect(self._create_affix)
        cl.addWidget(btn_add)
        
        l.addWidget(creator)
        
        # Content Area
        from PyQt6.QtWidgets import QScrollArea, QFrame
        self.scroll_settings = QScrollArea()
        self.scroll_settings.setWidgetResizable(True)
        self.scroll_settings.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_settings.setStyleSheet("QScrollArea { border: none; background-color: #2b2b2b; }")

        self.content_settings = AffixDropContainer()
        self.content_settings.setStyleSheet("background-color: #2b2b2b; border: none;")
        self.content_settings.reorder_requested.connect(self._on_reorder)
        self.flow_settings = FlowLayout(self.content_settings, margin=0, spacing=6)
        self.content_settings.setContentsMargins(4, 0, 4, 4)

        self.scroll_settings.setWidget(self.content_settings)
        l.addWidget(self.scroll_settings)

    # --- LOGIC ---
    
    def render_affixes(self):
        # Clear both layouts
        self._clear_layout(self.flow_main)
        self._clear_layout(self.flow_settings)
        
        # Re-populate
        for token in self.affix_items:
            display_text, btn_type = self._parse_token_display(token)
            
            # Button for Main View
            btn_main = AffixButton(display_text, btn_type, token, self._on_affix_click_main)
            self.flow_main.addWidget(btn_main)
            
            # Button for Settings View
            btn_set = AffixButton(display_text, btn_type, token, None)
            btn_set.delete_requested.connect(self._delete_affix)
            btn_set.set_mode(self.btn_del_mode.isChecked()) # Apply current del mode
            btn_set.set_allow_drag(True) # Enable drag
            self.flow_settings.addWidget(btn_set)

    def _parse_token_display(self, token):
        # Helper to format text (R: Name, RND, etc)
        btn_type = "text"
        display_text = token
        
        if "%dell" in token:
            btn_type = "rename"
            m = re.match(r'%dell\[(.*)\]', token)
            content = m.group(1) if m else token.replace("%dell", "")
            display_text = "R: " + content
        elif "%rand" in token or "%randNum" in token:
            parts = []
            r_m = re.findall(r'%rand\[(\d+)\]', token)
            for n in r_m: parts.append(f"RND[{n}]")
            rn_m = re.findall(r'%randNum\[(\d+)\]', token)
            for n in rn_m: parts.append(f"Num[{n}]")
            if parts: display_text = " ".join(parts)
            else: display_text = "RND"
            
        return display_text, btn_type

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    # --- EVENTS ---

    def _on_separator_changed(self, text):
        self.separator = text
        # self._emit_change() # Save on exit settings

    def _on_mode_changed(self, mode):
        self.current_mode = mode
        self._emit_change()
        
    def _on_del_mode_toggled(self, checked):
        # Update style of all buttons in settings view
        for i in range(self.flow_settings.count()):
            w = self.flow_settings.itemAt(i).widget()
            if isinstance(w, AffixButton):
                w.set_mode(checked)

    def set_always_on_top(self, checked):
        flags = self.windowFlags()
        if checked:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def _goto_settings(self):
        self.stack.setCurrentIndex(1)
        self.grip.raise_()

    def _exit_settings(self):
        self.btn_del_mode.setChecked(False) # Turn off delete mode on exit
        self.stack.setCurrentIndex(0)
        self.grip.raise_()
        self._emit_change() # Commit changes on exit

    def _on_reorder(self, from_idx, to_idx):
        if from_idx < 0 or from_idx >= len(self.affix_items): return
        
        item = self.affix_items.pop(from_idx)
        
        # Adjust index if necessary
        # If moving down (higher index), the removal shifts subsequent items up.
        # But 'to_idx' was calculated based on old layout?
        # My AffixDropContainer logic:
        # If target > from, it means we drop after.
        # But python insert: insert before index.
        # If I drop at index 5 (which is item 5), I want to be 5.
        # If from < to: item removed from 2. Index 5 becomes 4. So insert at 4?
        # Let's simplify:
        # self.affix_items.insert(to_idx, item) usually works if careful.
        
        # In DropContainer I handled: if from != target -> emit.
        # Let's trust target_idx relative to OLD list?
        # No, removing changes indices.
        # Let's use simple logic:
        
        if to_idx > from_idx:
            to_idx -= 1
            
        if to_idx < 0: to_idx = 0
        if to_idx > len(self.affix_items): to_idx = len(self.affix_items)
            
        self.affix_items.insert(to_idx, item)
        self.render_affixes()

    def _create_affix(self):
        text = self.inp_new_affix.text().strip()
        if not text: return
        
        # Check duplicates? Allow for now.
        self.affix_items.append(text)
        self.inp_new_affix.clear()
        self.render_affixes()
        # self._emit_change() # Save on exit

    def _delete_affix(self, btn):
        token = btn.payload
        if token in self.affix_items:
            self.affix_items.remove(token)
            self.render_affixes()
            # self._emit_change() # Save on exit

    def _show_tags_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #444; color: white; } QMenu::item:selected { background-color: #3b82f6; }")
        
        tags = [
            ("%date", AppContext.tr("tag_date")),
            ("%time", AppContext.tr("tag_time")),
            ("%rand[4]", AppContext.tr("tag_rand4")),
            ("%randNum[3]", AppContext.tr("tag_randnum3")),
            ("%seq", AppContext.tr("tag_seq")),
            ("%parent", AppContext.tr("tag_parent")),
            ("%name", AppContext.tr("tag_name")),
            ("%dell[%date_%time]", AppContext.tr("tag_dell"))
        ]
        
        for tag, desc in tags:
            action = QAction(f"{tag} - {desc}", self)
            action.triggered.connect(lambda _, t=tag: self._insert_tag(t))
            menu.addAction(action)
        
        sender = self.sender()
        menu.exec(sender.mapToGlobal(QPoint(0, sender.height())))

    def _insert_tag(self, tag):
        self.inp_new_affix.insert(tag)
        self.inp_new_affix.setFocus()

    def _on_affix_click_main(self, btn_type, payload, btn_widget):
        # Notify parent to apply affix
        self.apply_affix_requested.emit(btn_type, payload, btn_widget)

    apply_affix_requested = pyqtSignal(str, str, object) # type, payload, btn_widget

    def get_mode(self):
        return self.current_mode

    def _emit_change(self):
        data = {
            "affix_separator": self.separator,
            "affix_mode": self.current_mode,
            "affix_text": self._serialize_affixes()
        }
        self.settings_changed.emit(data)

    # --- SYSTEM EVENTS ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if event.position().y() <= self.title_bar.height():
                self._dragging = True
                self._drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_start_pos)
            event.accept()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        rect = self.rect()
        self.grip.move(rect.right() - 16, rect.bottom() - 16)
        self.grip.raise_()
        super().resizeEvent(event)

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)
