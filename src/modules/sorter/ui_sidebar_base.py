
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFrame, QLabel, QPushButton, QHBoxLayout
)
from PyQt6.QtCore import Qt, pyqtSignal
from config import AppContext
from ui_widgets_base import DropZoneWidget

SIDEBAR_DESIGN = {
    "section_spacing": 6, 
    "category_margin": 0,
    "btn_height": 24,
    "font_size_main": 14,
    "font_size_sub": 13,
    "nested_bg_alpha": "0.2"
}

class SidebarNodeMixin:
    """
    Mixin containing shared logic for CategoryWidget and LeafNodeWidget.
    Expects 'self.app' and 'self.path' to be available.
    """
    def check_if_blocked(self):
        my_norm = os.path.normpath(self.path)
        
        inbox_conf = self.app.config.get("path_unsort", "")
        trash_conf = self.app.config.get("path_todel", "")
        sess_inbox = getattr(self.app, 'session_inbox_path', None)
        sess_trash = getattr(self.app, 'session_trash_path', None)

        is_virtual = getattr(self.app, 'virtual_folder_name', None) is not None
        
        if is_virtual:
            is_inbox = False
        else:
            is_inbox = (sess_inbox and os.path.normpath(sess_inbox) == my_norm) or \
                       (inbox_conf and os.path.normpath(inbox_conf) == my_norm)
        
        is_trash = (sess_trash and os.path.normpath(sess_trash) == my_norm) or \
                   (trash_conf and os.path.normpath(trash_conf) == my_norm)
        
        target_btn = getattr(self, 'btn_name', getattr(self, 'btn_action', None))
        if not target_btn: return is_inbox, is_trash

        if is_inbox:
            target_btn.setCursor(Qt.CursorShape.ForbiddenCursor)
            target_btn.setStyleSheet("""
                QPushButton { 
                    text-align: left; padding: 6px; 
                    background-color: #3b82f6; 
                    border: none; border-radius: 4px; 
                    color: white; 
                    border-top-right-radius: 0px; 
                    border-bottom-right-radius: 0px;
                    font-weight: bold;
                }
            """)
        elif is_trash:
            target_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            target_btn.setStyleSheet("""
                QPushButton { 
                    text-align: left; padding: 6px; 
                    background-color: #b91c1c; 
                    border: none; border-radius: 4px; 
                    color: white; 
                    border-top-right-radius: 0px; 
                    border-bottom-right-radius: 0px;
                    font-weight: bold;
                }
            """)
        else:
            target_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if self.__class__.__name__ == "CategoryWidget":
                fs = SIDEBAR_DESIGN['font_size_main'] if getattr(self, 'level', 0) == 0 else SIDEBAR_DESIGN['font_size_sub']
                target_btn.setStyleSheet(f"QPushButton {{ font-size: {fs}px; text-align: left; padding-left: 4px; font-weight: bold; border: none; background: transparent; color: white; }}")
            elif self.__class__.__name__ == "LeafNodeWidget":
                target_btn.setStyleSheet("""
                    QPushButton { 
                        text-align: left; 
                        padding: 6px; 
                        background-color: rgba(0, 0, 0, 0.25); 
                        border: none; 
                        border-radius: 4px; 
                        border-top-right-radius: 0px; 
                        border-bottom-right-radius: 0px;
                        color: #eee;
                    }
                    QPushButton:hover { 
                        background-color: rgba(255, 255, 255, 0.1); 
                        color: white; 
                    }
                """)
            
        return is_inbox, is_trash

    def check_if_last_target(self):
        """
        Checks if this folder was the destination of the last move operation.
        Returns True if matched.
        """
        if not hasattr(self.app, 'history') or not self.app.history:
            return False
            
        last_action = self.app.history[-1]
        if isinstance(last_action, list) and last_action:
            pair = last_action[0]
            if isinstance(pair, tuple) and len(pair) == 2:
                last_move_dest_path = pair[0]
            else:
                return False
        elif isinstance(last_action, tuple) and len(last_action) == 2:
            last_move_dest_path = last_action[0]
        else:
            return False
        
        parent_of_dest = os.path.dirname(last_move_dest_path)
        
        return os.path.normpath(parent_of_dest) == os.path.normpath(self.path)

    def apply_rich_tooltip(self, is_inbox, is_trash):
        target_btn = getattr(self, 'btn_name', getattr(self, 'btn_action', None))
        if not target_btn: return

        name = getattr(self, 'name', '???')
        path = getattr(self, 'path', '???')
        
        header_color = "#ffffff"
        status_html = ""
        action_prefix = AppContext.tr("tooltip_move_prefix")
        
        if is_inbox:
             header_color = "#3b82f6"
             status_html = f"<div style='color: #3b82f6; font-weight: bold; font-size: 12px; margin-bottom: 2px;'>{AppContext.tr('lbl_unsort').upper()}</div>"
             action_prefix = AppContext.tr("tooltip_src_locked") 
        elif is_trash:
             header_color = "#b91c1c"
             status_html = f"<div style='color: #b91c1c; font-weight: bold; font-size: 12px; margin-bottom: 2px;'>{AppContext.tr('lbl_todel').upper()}</div>"
             action_prefix = AppContext.tr("tooltip_move_prefix") 

        hint_scroll = AppContext.tr("tooltip_scroll_explorer_hint")
        hint_right = AppContext.tr("tooltip_right_click_menu_hint")
        html = (
            f"<div style='white-space: pre-wrap; margin: 0px; padding: 0px; font-family: sans-serif;'>"
            f"<div style='color: #888888; font-size: 12px; margin-bottom: 4px;'>{action_prefix}</div>"
            f"{status_html}"
            f"<div style='font-size: 14px; font-weight: bold; color: {header_color}; margin: 0px;'>{name}</div>"
            f"<div style='color: #aaaaaa; font-size: 12px; margin-top: 2px; word-wrap: break-word;'>{path}</div>"
            f"<div style='color: #888888; font-size: 12px; margin-top: 8px; border-top: 1px solid #444; padding-top: 6px;'>"
            f"• {hint_scroll}<br>"
            f"• {hint_right}"
            f"</div>"
            f"</div>"
        )
        target_btn.setToolTip(html)

class DragContainer(QWidget):
    external_folders_dropped = pyqtSignal(list)
    internal_reorder = pyqtSignal(str, str, int)

    def __init__(self, parent_path, app, parent=None):
        super().__init__(parent)
        self.parent_path = parent_path
        self.app = app
        self.setAcceptDrops(True)
        self.v_layout = QVBoxLayout(self)
        self.v_layout.setContentsMargins(0, 0, 0, 0)
        self.v_layout.setSpacing(SIDEBAR_DESIGN['section_spacing'])
        self.v_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.layout = self.v_layout 

    def dragEnterEvent(self, event):
        md = event.mimeData()
        if md.hasText() or md.hasUrls():
            event.accept()
        else:
            event.ignore()
            
    def dragMoveEvent(self, event):
        md = event.mimeData()
        if md.hasText() or md.hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        md = event.mimeData()

        if md.hasUrls():
            self.external_folders_dropped.emit(md.urls())
            event.accept()
            return

        if md.hasText():
            source_path = md.text()
            if not source_path or not os.path.exists(source_path):
                event.ignore()
                return
            
            drop_y = event.position().y()
            widgets = []
            for i in range(self.v_layout.count()):
                w = self.v_layout.itemAt(i).widget()
                if w: widgets.append(w)
            
            new_index = len(widgets)
            for i, w in enumerate(widgets):
                if drop_y < w.y() + w.height() / 2:
                    new_index = i
                    break
            
            target = self.parent_path if self.parent_path else ""
            self.internal_reorder.emit(target, source_path, new_index)
            event.accept()
        else:
            event.ignore()
