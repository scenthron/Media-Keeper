


import os
import shutil
import subprocess
import logging
from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPathItem, QGraphicsTextItem, QGraphicsRectItem,
    QWidget, QVBoxLayout, QLabel, QFrame, QMenu, QPushButton, QGraphicsProxyWidget, QHBoxLayout,
    QGraphicsItem
)
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QPoint, QUrl, QSize
from PyQt6.QtGui import (
    QPen, QBrush, QColor, QPainterPath, QFont, QPainter, QDesktopServices, QAction,
    QIcon, QPixmap, QTransform, QTextOption
)
from config import AppContext
from utils_common import format_size, truncate_text

# --- PALETTE & STYLES ---

COLOR_FOLDER_BASE = "#E6B422" # Imperial Gold (Folders)
COLOR_FREE = "#444444"
COLOR_OTHER = "#666666"

# Fixed colors for common types (dark pastel palette).
EXT_COLORS = {
    'png': '#5b8dbf', 'jpg': '#5b8dbf', 'jpeg': '#5b8dbf', 'gif': '#6a9bc5',  # Images: Muted Blue
    'mp4': '#8e7cb8', 'avi': '#7b6ba8', 'mov': '#9685b5', 'mkv': '#7568a6',   # Video: Muted Violet
    'mp3': '#5a9e82', 'wav': '#4d8a70', 'flac': '#68a88c',                     # Audio: Muted Green
    'zip': '#5a9eaa', 'rar': '#4d8e98', '7z': '#68a8b0',                       # Archives: Muted Teal
    'exe': '#b07ab8', 'msi': '#a06aaa',                                        # Executables: Muted Magenta
    'txt': '#8a95a5', 'pdf': '#a0a8b5', 'doc': '#7a8595',                      # Docs: Slate
    'py': '#5b8dbf', 'js': '#7578b5', 'css': '#6080aa', 'html': '#8a7ab5'      # Code: Muted Blue/Indigo
}

def get_color_for_ext(ext):
    key = ext.lower().replace('.', '')
    if key in EXT_COLORS:
        return EXT_COLORS[key]
    
    # Generate dark pastel colors for unknown extensions
    hash_val = sum(ord(c) for c in key)
    hue = (hash_val * 37) % 360
    return QColor.fromHsl(hue, 120, 120).name()

def format_size_short(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    kb = size_bytes / 1024
    if kb < 1024:
        return f"{int(round(kb))} KB"
    mb = kb / 1024
    if mb < 1024:
        return f"{int(round(mb))} MB"
    gb = mb / 1024
    if gb < 1024:
        return f"{int(round(gb))} GB"
    tb = gb / 1024
    return f"{int(round(tb))} TB"

# --- CUSTOM TOOLTIP WIDGET ---
class ChartTooltipWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Use ToolTip window type to float above everything, Frameless for style
        self.setWindowFlags(
            Qt.WindowType.ToolTip | 
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) 
        
        # Style: Black background, slight border
        self.setStyleSheet("""
            ChartTooltipWidget {
                background-color: #111111;
                border: 1px solid #444444;
                border-radius: 4px;
            }
            QLabel { color: #eeeeee; border: none; background: transparent; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        
        # Row 1: Name (Bold)
        self.lbl_name = QLabel()
        self.lbl_name.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffffff;")
        layout.addWidget(self.lbl_name)
        
        # Row 2: Path (Grey)
        self.lbl_path = QLabel()
        self.lbl_path.setStyleSheet("font-size: 11px; color: #999999; font-family: monospace;")
        self.lbl_path.setWordWrap(False) 
        layout.addWidget(self.lbl_path)
        
        # Row 3: Size (White)
        self.lbl_size = QLabel()
        self.lbl_size.setStyleSheet("font-size: 12px; color: #dddddd; font-weight: bold;")
        layout.addWidget(self.lbl_size)
        
        self.adjustSize()

    def update_data(self, name, path, size, type_str, parent_folder_name=None):
        # type_str can be: 'dir', 'dir_group', 'file', 'file_group_ext', 'file_group_misc', 'free_space'
        
        icon = "📄 "
        if type_str == 'dir': icon = "📂 "
        elif type_str == 'dir_group': icon = "📂📂 "
        elif type_str == 'file_group_ext' or type_str == 'file_group_misc': icon = "📄📄 "
        elif type_str == 'free_space': icon = "💿 "
            
        if parent_folder_name:
            self.lbl_name.setText(f"📂 {parent_folder_name}  >  {icon}{name}")
        else:
            self.lbl_name.setText(icon + name)
        
        # Shorten path if too long
        display_path = path
        if len(display_path) > 60:
            display_path = "..." + display_path[-57:]
        self.lbl_path.setText(display_path)
        
        self.lbl_size.setText(format_size(size))
        
        self.adjustSize()

class SunburstSliceItem(QGraphicsPathItem):
    def __init__(self, start_angle, span_angle, inner_r, outer_r, color, data, level, parent_item=None):
        super().__init__(parent_item)
        self.data = data
        self.base_color = QColor(color)
        self.level = level
        self.is_selected = False
        
        # Geometry
        self.path = QPainterPath()
        rect_out = QRectF(-outer_r, -outer_r, outer_r*2, outer_r*2)
        rect_in = QRectF(-inner_r, -inner_r, inner_r*2, inner_r*2)
        
        # Draw Slice (Counter-Clockwise in Qt)
        self.path.arcMoveTo(rect_out, start_angle)
        self.path.arcTo(rect_out, start_angle, span_angle)
        self.path.arcTo(rect_in, start_angle + span_angle, 0) 
        self.path.arcTo(rect_in, start_angle + span_angle, -span_angle) 
        self.path.closeSubpath()
        
        self.setPath(self.path)
        self.setPen(QPen(QColor("#1a1a1a"), 1))
        self.setBrush(QBrush(self.base_color))
        self.setAcceptHoverEvents(True)

    def reset_pen(self):
        self.setPen(QPen(QColor("#1a1a1a"), 1))

    def set_text_color(self, color_name):
        pass # Sunburst does not have internal text items

    def reset_highlight(self):
        self.reset_pen()
        if not self.is_selected:
            self.setBrush(QBrush(self.base_color))
        else:
            self.setBrush(QBrush(self.base_color.lighter(150)))

    def set_selected(self, selected):
        self.is_selected = selected
        if selected:
            self.setPen(QPen(QColor("white"), 3, Qt.PenStyle.SolidLine))
            self.setBrush(QBrush(self.base_color.lighter(150)))
        else:
            self.reset_highlight()

    def hoverEnterEvent(self, event):
        views = self.scene().views()
        if views:
            chart = views[0]
            if hasattr(chart, 'set_hovered_slice'):
                chart.set_hovered_slice(self)
            if hasattr(chart, 'slice_hovered'):
                chart.slice_hovered.emit(self.data)
        super().hoverEnterEvent(event)
    
    def hoverLeaveEvent(self, event):
        views = self.scene().views()
        if views:
            chart = views[0]
            if hasattr(chart, 'clear_hovered_slice'):
                chart.clear_hovered_slice(self)
            if hasattr(chart, 'slice_hovered'):
                chart.slice_hovered.emit(None)
        super().hoverLeaveEvent(event)


class TreeMapSliceItem(QGraphicsRectItem):
    def __init__(self, rect, color, data, level, is_leaf=False, parent_item=None):
        super().__init__(rect, parent_item)
        self.data = data
        self.base_color = QColor(color)
        self.level = level
        self.is_leaf = is_leaf
        self.is_selected = False
        
        # Clip text/children to the boundaries of this tile
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, True)
        
        t = data.get('type')
        if t in ('dir', 'dir_group'):
            self.setPen(QPen(QColor("#111111"), 2, Qt.PenStyle.SolidLine))
        else:
            self.setPen(QPen(QColor("#1a1a1a"), 1, Qt.PenStyle.SolidLine))
        self.setBrush(QBrush(self.base_color))
            
        self.setAcceptHoverEvents(True)

    def set_text_color(self, color_name):
        for child in self.childItems():
            if isinstance(child, QGraphicsTextItem):
                child.setDefaultTextColor(QColor(color_name))

    def reset_highlight(self):
        t = self.data.get('type')
        if t in ('dir', 'dir_group'):
            self.setPen(QPen(QColor("#111111"), 2, Qt.PenStyle.SolidLine))
        else:
            self.setPen(QPen(QColor("#1a1a1a"), 1, Qt.PenStyle.SolidLine))
            
        if not self.is_selected:
            self.setBrush(QBrush(self.base_color))
            text_color = "black" if t in ('dir', 'dir_group') else "white"
            self.set_text_color(text_color)
        else:
            self.setBrush(QBrush(self.base_color.lighter(150)))
            self.set_text_color("black")

    def set_selected(self, selected):
        self.is_selected = selected
        if selected:
            self.setPen(QPen(QColor("white"), 3, Qt.PenStyle.SolidLine))
            self.setBrush(QBrush(self.base_color.lighter(150)))
            self.set_text_color("black")
        else:
            self.reset_highlight()

    def hoverEnterEvent(self, event):
        views = self.scene().views()
        if views:
            chart = views[0]
            if hasattr(chart, 'set_hovered_slice'):
                chart.set_hovered_slice(self)
            if hasattr(chart, 'slice_hovered'):
                chart.slice_hovered.emit(self.data)
        super().hoverEnterEvent(event)
    
    def hoverLeaveEvent(self, event):
        views = self.scene().views()
        if views:
            chart = views[0]
            if hasattr(chart, 'clear_hovered_slice'):
                chart.clear_hovered_slice(self)
            if hasattr(chart, 'slice_hovered'):
                chart.slice_hovered.emit(None)
        super().hoverLeaveEvent(event)


class AnalyzerPieChart(QGraphicsView):
    node_clicked = pyqtSignal(dict) 
    file_clicked = pyqtSignal(dict)
    slice_hovered = pyqtSignal(object) 
    slice_context_menu = pyqtSignal(dict, object)
    folder_dropped = pyqtSignal(str)
    browse_requested = pyqtSignal()
    center_clicked = pyqtSignal()
    
    # New signals for center buttons
    nav_back_clicked = pyqtSignal()
    nav_up_clicked = pyqtSignal()
    stop_scan_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setStyleSheet("background: transparent; border: none;")
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        
        # IMPORTANT: Enable drops on the VIEW itself
        self.setAcceptDrops(True)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setMouseTracking(True) # IMPORTANT for hover/tooltip
        
        # Disable scrollbars to prevent viewport size flickering
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Navigation History
        self.root_data = None 
        self.INNER_RADIUS = 150 # Fixed radius in scene units (scales sync with widget)
        
        self.visible_depth_limit = 5
        self.is_scanning = False
        self.chart_mode = 'treemap'
        self.show_empty_state()
        
        # Initialize Overlay Tooltip
        self.tooltip = ChartTooltipWidget(None)
        self.slice_hovered.connect(self.on_slice_hovered)
        self.selected_item = None
        self.custom_colors_active = False
        self.custom_ext_colors = {}
        self.selected_file_path = ""
        self.hovered_file_path = ""
        self.hovered_ext = ""
        self.hovered_slice_item = None
        
        # Debounce resize timer
        from PyQt6.QtCore import QTimer
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.refresh_chart)

    def on_slice_hovered(self, data):
        if data:
            if self.chart_mode == 'treemap' and data.get('type') == 'file':
                parent_path = os.path.dirname(data['path'])
                parent_name = os.path.basename(parent_path)
                if not parent_name:
                    parent_name = parent_path
                self.tooltip.update_data(data['name'], data['path'], data['size'], data['type'], parent_folder_name=parent_name)
            else:
                self.tooltip.update_data(data['name'], data['path'], data['size'], data['type'])
            
            if self.tooltip.isHidden():
                self.tooltip.show()
        else:
            self.tooltip.hide()

    def get_color_for_ext(self, ext):
        key = ext.lower().replace('.', '')
        if key in self.custom_ext_colors:
            return self.custom_ext_colors[key]
            
        if self.custom_colors_active:
            import random
            hue = random.randint(0, 359)
            sat = random.randint(100, 160)
            val = random.randint(105, 145)
            color = QColor.fromHsl(hue, sat, val).name()
            self.custom_ext_colors[key] = color
            return color
            
        if key in EXT_COLORS:
            return EXT_COLORS[key]
        
        # Dark pastel for unknown extensions
        hash_val = sum(ord(c) for c in key)
        hue = (hash_val * 37) % 360
        return QColor.fromHsl(hue, 120, 120).name()

    def regenerate_extension_colors(self):
        import random
        self.custom_colors_active = True
        self.custom_ext_colors = {}
        for key in EXT_COLORS:
            hue = random.randint(0, 359)
            sat = random.randint(100, 160)
            val = random.randint(105, 145)
            self.custom_ext_colors[key] = QColor.fromHsl(hue, sat, val).name()
        self.refresh_chart()

    def mouseMoveEvent(self, event):
        try:
            super().mouseMoveEvent(event)
            # Move tooltip if visible to follow mouse using GLOBAL coordinates
            if self.tooltip.isVisible():
                global_pos = event.globalPosition().toPoint()
                offset = QPoint(20, 20)
                self.tooltip.move(global_pos + offset)
                
            pos = self.mapToScene(event.pos())
            dist = (pos.x()**2 + pos.y()**2) ** 0.5

            # Check for Center Hover to change cursor
            if self.root_data:
                if dist < self.INNER_RADIUS:
                    # If hovering over buttons, let the buttons handle cursor
                    # Otherwise if in empty center space, indicate clickability
                    item = self.scene.itemAt(pos, self.transform())
                    if isinstance(item, QGraphicsProxyWidget):
                        pass # Handled by widget
                    else:
                        self.setCursor(Qt.CursorShape.PointingHandCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
            else:
                # Empty state hover: check if we are over the clickable outline area (dist < 150)
                # and verify if scanning is not active
                if dist < 150 and not getattr(self, 'is_scanning', False):
                    self.setCursor(Qt.CursorShape.PointingHandCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
        except RuntimeError as re:
            logging.debug(f"Silenced RuntimeError in mouseMoveEvent (deleted C++ object): {re}")
        except Exception as e:
            logging.error(f"Error in AnalyzerPieChart.mouseMoveEvent: {e}")

    def show_empty_state(self, message=None, show_back=False):
        self.scene.clear()
        self.root_data = None
        self.current_view_node = None
        
        self.scene.setSceneRect(-200, -200, 400, 400)
        
        outline = QGraphicsPathItem()
        path = QPainterPath()
        if self.chart_mode == 'treemap':
            path.addRoundedRect(QRectF(-150, -100, 300, 200), 8, 8)
        else:
            path.addEllipse(-150, -150, 300, 300)
        outline.setPath(path)
        pen = QPen(QColor("#555"), 2)
        pen.setStyle(Qt.PenStyle.DashLine)
        outline.setPen(pen)
        self.scene.addItem(outline)
        
        txt_str = message if message else AppContext.tr("anl_drag_text")
        
        # Split text if scanning or special state
        if "Scan" in txt_str or "Сканирование" in txt_str:
            self.is_scanning = True
            # Place Stop Button
            btn_stop = QPushButton(AppContext.tr("anl_btn_stop"))
            btn_stop.setStyleSheet("""
                QPushButton { background-color: #dc2626; color: white; border-radius: 4px; padding: 6px 15px; font-weight: bold; }
                QPushButton:hover { background-color: #ef4444; }
            """)
            btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_stop.clicked.connect(self.stop_scan_clicked.emit)
            
            proxy = self.scene.addWidget(btn_stop)
            proxy.setPos(-proxy.preferredSize().width()/2, 20)
            
            txt = QGraphicsTextItem(txt_str)
            txt.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            txt.setDefaultTextColor(QColor("#ccc"))
            font = QFont("Arial", 12, QFont.Weight.Bold)
            txt.setFont(font)
            br = txt.boundingRect()
            txt.setPos(-br.width()/2, -40)
            self.scene.addItem(txt)
            
        else:
            self.is_scanning = False
            # Standard Empty or Cancelled State
            
            # Main label
            txt = QGraphicsTextItem(txt_str)
            txt.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            txt.setDefaultTextColor(QColor("#777"))
            font = QFont("Arial", 14, QFont.Weight.Bold)
            txt.setFont(font)
            br = txt.boundingRect()
            txt.setPos(-br.width()/2, -br.height()/2 - 12)
            self.scene.addItem(txt)
            
            # Sub label
            sub_text = "или кликните для выбора" if AppContext.LANG.upper() == "RU" else "or click to browse"
            sub_txt = QGraphicsTextItem(sub_text)
            sub_txt.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            sub_txt.setDefaultTextColor(QColor("#555"))
            sub_font = QFont("Arial", 11, QFont.Weight.Normal)
            sub_txt.setFont(sub_font)
            sub_br = sub_txt.boundingRect()
            sub_txt.setPos(-sub_br.width()/2, -sub_br.height()/2 + 12)
            self.scene.addItem(sub_txt)
            
            # Show Back Button if requested (e.g. Cancelled but history exists)
            if show_back:
                btn_back = QPushButton("← Back")
                btn_back.setStyleSheet("""
                    QPushButton { background-color: #444; color: #ddd; border-radius: 4px; padding: 6px 15px; font-weight: bold; border: 1px solid #555; }
                    QPushButton:hover { background-color: #555; color: white; }
                """)
                btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_back.clicked.connect(self.nav_back_clicked.emit)
                
                proxy = self.scene.addWidget(btn_back)
                proxy.setPos(-proxy.preferredSize().width()/2, 40)
        
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def load_tree(self, root_node, depth_limit):
        self.root_data = root_node
        self.current_view_node = root_node
        self.visible_depth_limit = depth_limit
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.refresh_chart()

    def get_subtree_depth(self, node):
        """Calculates maximum depth relative to this node"""
        if not node.get('children'): return 0
        max_child_depth = 0
        for child in node['children']:
            if child['type'] == 'dir':
                d = self.get_subtree_depth(child)
                if d > max_child_depth: max_child_depth = d
            else:
                # Files count as 1 level
                if 1 > max_child_depth: max_child_depth = 1
        return 1 + max_child_depth

    def draw_treemap_view(self):
        try:
            self.scene.clear()
            if not self.current_view_node:
                return

            self.btn_tree_back = None
            self.btn_tree_up = None

            # Динамические размеры на основе размера вьюпорта
            w = max(300, self.viewport().width())
            h = max(200, self.viewport().height())

            self.scene.setSceneRect(0, 0, w, h)

            # Отрисовка темно-оранжево-коричневой подложки сцены
            bg_rect = QRectF(0, 0, w, h)
            bg_item = self.scene.addRect(bg_rect, QPen(QColor("#5c3a21"), 1.5), QBrush(QColor("#2d1a0e")))
            bg_item.setZValue(-100)

            # Обновляем навигационные кнопки в главном окне
            main_window = self.window()
            if main_window and hasattr(main_window, 'btn_nav_back') and hasattr(main_window, 'btn_nav_up'):
                self.set_nav_buttons_state(main_window.btn_nav_back.isEnabled(), main_window.btn_nav_up.isEnabled())

            root_rect = QRectF(0, 0, w, h)
            self.draw_treemap_node(self.current_view_node, root_rect, 0, self.visible_depth_limit)

            self.resetTransform()
        except Exception as e:
            logging.error(f"Analyzer: Error drawing TreeMap view: {e}", exc_info=True)

    def draw_treemap_node(self, node, rect, level, max_draw_level):
        if level >= max_draw_level:
            return
        if rect.width() < 10 or rect.height() < 10:
            return
            
        children = node.get('children', [])
        path = node.get('path', '')
        
        is_root_drive = False
        if level == 0 and os.path.exists(path):
            drive, tail = os.path.splitdrive(path)
            if tail in [os.sep, '', '/']:
                is_root_drive = True
                
        if not children and not is_root_drive:
            return
            
        node_size = node['size']
        if is_root_drive:
            try:
                total, used, free = shutil.disk_usage(path)
                node_size = total
            except:
                pass
                
        if node_size == 0:
            return
            
        min_angle = 0.5
        
        raw_dirs = [c for c in children if c['type'] == 'dir']
        raw_files = [c for c in children if c['type'] == 'file']
        
        dir_items = self.process_dirs(raw_dirs, node_size, 360, min_angle, path)
        file_items = self.process_files_by_ext(raw_files, node_size, 360, min_angle, path)
        
        render_queue = dir_items + file_items
        
        if is_root_drive:
            try:
                total, used, free = shutil.disk_usage(path)
                render_queue.append({
                    'name': AppContext.tr('anl_free_space'),
                    'path': path,
                    'type': 'free_space',
                    'size': free
                })
            except:
                pass
                
        render_queue = [item for item in render_queue if item.get('size', 0) > 0]
        if not render_queue:
            return
            
        render_queue.sort(key=lambda x: x['size'], reverse=True)
        
        self.squarify(render_queue, rect, level, max_draw_level)

    def squarify(self, items, rect, level, max_draw_level):
        if not items:
            return
        total_size = sum(item['size'] for item in items)
        if total_size <= 0:
            return
        rect_area = rect.width() * rect.height()
        if rect_area <= 0:
            return
            
        scale = rect_area / total_size
        norm_items = [(item, item['size'] * scale) for item in items]
        
        self.squarify_run(norm_items, rect, level, max_draw_level)

    def squarify_run(self, items, rect, level, max_draw_level):
        if not items:
            return
            
        w = min(rect.width(), rect.height())
        if w <= 0:
            return
            
        row = []
        row.append(items[0])
        
        i = 1
        while i < len(items):
            next_item = items[i]
            if self.get_worst_ratio(row + [next_item], w) <= self.get_worst_ratio(row, w):
                row.append(next_item)
                i += 1
            else:
                break
                
        remaining_items = items[len(row):]
        next_rect = self.layout_row(row, rect, w, level, max_draw_level)
        
        self.squarify_run(remaining_items, next_rect, level, max_draw_level)

    def get_worst_ratio(self, row, w):
        if not row or w <= 0:
            return float('inf')
        sum_areas = sum(area for _, area in row)
        if sum_areas == 0:
            return float('inf')
        min_area = min(area for _, area in row)
        max_area = max(area for _, area in row)
        val1 = (w * w * max_area) / (sum_areas * sum_areas)
        val2 = (sum_areas * sum_areas) / (w * w * min_area)
        return max(val1, val2)

    def layout_row(self, row, rect, w, level, max_draw_level):
        sum_areas = sum(area for _, area in row)
        if w <= 0 or sum_areas <= 0:
            return rect
            
        thickness = sum_areas / w
        
        if abs(w - rect.height()) < 1e-5:
            current_y = rect.y()
            for item_data, area in row:
                h = area / thickness
                item_rect = QRectF(rect.x(), current_y, thickness, h)
                self.draw_item(item_data, item_rect, level, max_draw_level)
                current_y += h
            next_rect = QRectF(rect.x() + thickness, rect.y(), max(0.0, rect.width() - thickness), rect.height())
        else:
            current_x = rect.x()
            for item_data, area in row:
                w_item = area / thickness
                item_rect = QRectF(current_x, rect.y(), w_item, thickness)
                self.draw_item(item_data, item_rect, level, max_draw_level)
                current_x += w_item
            next_rect = QRectF(rect.x(), rect.y() + thickness, rect.width(), max(0.0, rect.height() - thickness))
            
        return next_rect

    def draw_item(self, item_data, item_rect, level, max_draw_level):
        if item_rect.width() < 2 or item_rect.height() < 2:
            return
            
        color = "#888"
        t = item_data['type']
        
        if t == 'dir':
            color = COLOR_FOLDER_BASE
        elif t == 'dir_group':
            color = COLOR_FOLDER_BASE
        elif t == 'file':
            ext = os.path.splitext(item_data['name'])[1]
            color = self.get_color_for_ext(ext)
        elif t == 'file_group_ext':
            ext = item_data.get('ext', '')
            base = QColor(self.get_color_for_ext(ext))
            color = base.darker(140).name()
        elif t == 'file_group_misc':
            color = COLOR_OTHER
        elif t == 'free_space':
            color = COLOR_FREE
            
        is_leaf = False
        if t == 'dir':
            has_children = bool(item_data.get('children'))
            will_detail = has_children and (level + 1 < max_draw_level)
            margin = 4
            fits = (item_rect.width() > 2 * margin) and (item_rect.height() > 2 * margin)
            if not (will_detail and fits):
                is_leaf = True
        elif t == 'dir_group':
            is_leaf = True
            
        slice_item = TreeMapSliceItem(item_rect, color, item_data, level, is_leaf=is_leaf)
        self.scene.addItem(slice_item)
        
        if t == 'dir' and not is_leaf:
            margin = 4
            inner_rect = QRectF(
                item_rect.x() + margin,
                item_rect.y() + margin,
                item_rect.width() - 2 * margin,
                item_rect.height() - 2 * margin
            )
            self.draw_treemap_node(item_data, inner_rect, level + 1, max_draw_level)
        else:
            side = min(item_rect.width(), item_rect.height())
            if side > 120:
                font_size = 12
            elif side > 80:
                font_size = 10
            elif side > 50:
                font_size = 8
            else:
                font_size = 7

            if item_rect.width() > 50 and item_rect.height() > 30:
                name_str = truncate_text(item_data['name'], int(item_rect.width() / 6))
                size_str = format_size(item_data['size'])
                full_str = f"{name_str}\n{size_str}" if name_str else size_str
                
                text_item = QGraphicsTextItem(full_str, slice_item)
                text_color = "black" if t in ('dir', 'dir_group') else "white"
                text_item.setDefaultTextColor(QColor(text_color))
                font = QFont("Arial", font_size)
                text_item.setFont(font)
                
                text_width = max(1.0, item_rect.width() - 6)
                text_item.setTextWidth(text_width)
                option = QTextOption(Qt.AlignmentFlag.AlignCenter)
                option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
                text_item.document().setDefaultTextOption(option)
                
                br = text_item.boundingRect()
                tx = item_rect.x() + (item_rect.width() - br.width()) / 2
                ty = item_rect.y() + (item_rect.height() - br.height()) / 2
                text_item.setPos(tx, ty)
            elif item_rect.width() > 30 and item_rect.height() > 14:
                size_str = format_size_short(item_data['size'])
                text_item = QGraphicsTextItem(size_str, slice_item)
                text_color = "black" if t in ('dir', 'dir_group') else "white"
                text_item.setDefaultTextColor(QColor(text_color))
                font = QFont("Arial", font_size)
                text_item.setFont(font)
                
                text_width = max(1.0, item_rect.width() - 4)
                text_item.setTextWidth(text_width)
                option = QTextOption(Qt.AlignmentFlag.AlignCenter)
                option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
                text_item.document().setDefaultTextOption(option)
                
                br = text_item.boundingRect()
                tx = item_rect.x() + (item_rect.width() - br.width()) / 2
                ty = item_rect.y() + (item_rect.height() - br.height()) / 2
                text_item.setPos(tx, ty)

    def refresh_chart(self):
        try:
            self.scene.clear()
            if not self.current_view_node:
                self.show_empty_state()
                return

            if self.chart_mode == 'treemap':
                self.draw_treemap_view()
                return

            # 1. Calculate Dynamic Depth and Radii
            actual_depth = self.get_subtree_depth(self.current_view_node)
            effective_depth = min(actual_depth, self.visible_depth_limit)
            if effective_depth < 1: effective_depth = 1

            BASE_RADIUS = 380 # Max radius
            current_inner_radius = self.INNER_RADIUS
            
            available_space = BASE_RADIUS - current_inner_radius
            
            # Dynamic Thickness: Fill available space
            ring_thickness = available_space / effective_depth

            total_size = self.current_view_node['size']
            if total_size == 0: total_size = 1

            # 3. Center Widget (Text + Buttons)
            # We use QWidget container + QGraphicsProxyWidget
            center_widget = QWidget()
            center_widget.setFixedSize(260, 260)
            center_widget.setStyleSheet("background: transparent;")
            cw_layout = QVBoxLayout(center_widget)
            cw_layout.setContentsMargins(0, 79, 0, 45)
            cw_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # Name & Size Labels
            size_str = format_size(total_size)
            full_name = self.current_view_node['name']
            name_str = truncate_text(full_name, 20) 
            
            # Size Label (Displayed ABOVE name, font enlarged to 22px)
            lbl_size = QLabel(size_str)
            lbl_size.setStyleSheet("color: #a0aec0; font-size: 22px; font-weight: bold; font-family: Arial;")
            lbl_size.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # Name Label (Displayed strictly in center, font size 24px)
            lbl_name = QLabel(name_str)
            lbl_name.setStyleSheet("color: white; font-size: 24px; font-weight: bold; font-family: Arial;")
            lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # Navigation Buttons Container
            btn_container = QWidget()
            btn_container.setFixedHeight(60) # Prevent vertical clipping/compressing
            btn_layout = QHBoxLayout(btn_container)
            btn_layout.setContentsMargins(0, 0, 0, 0)
            btn_layout.setSpacing(10)
            btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            btn_style = """
                QPushButton { 
                    background-color: rgba(255,255,255,0.1); 
                    border: 1px solid #555; 
                    border-radius: 30px; 
                    padding: 0px;
                }
                QPushButton:hover { background-color: rgba(255,255,255,0.2); border-color: #888; }
                QPushButton:disabled { background-color: rgba(255, 255, 255, 0.02); border-color: #333; }
            """
            
            # Use thick graphical arrows instead of thin lines
            icons_dir = AppContext.find_resource_dir("icons")
            icon_path = os.path.join(icons_dir, "arrow-right-color.svg")
            
            # Helper to generate QIcon with dimmed disabled state
            def create_dimmed_icon(path, size, rotate_angle=0, flip_h=False, flip_v=False):
                temp_icon = QIcon(path)
                pm = temp_icon.pixmap(size)
                transform = QTransform()
                if rotate_angle != 0:
                    transform.rotate(rotate_angle)
                if flip_h:
                    transform.scale(-1, 1)
                if flip_v:
                    transform.scale(1, -1)
                if rotate_angle != 0 or flip_h or flip_v:
                    pm = pm.transformed(transform, Qt.TransformationMode.SmoothTransformation)
                
                # Create dimmed version for disabled state (opacity 0.2)
                dimmed = QPixmap(pm.size())
                dimmed.setDevicePixelRatio(pm.devicePixelRatio())
                dimmed.fill(Qt.GlobalColor.transparent)
                painter = QPainter(dimmed)
                painter.setOpacity(0.2)
                painter.drawPixmap(0, 0, pm)
                painter.end()
                
                icon = QIcon()
                icon.addPixmap(pm, QIcon.Mode.Normal)
                icon.addPixmap(dimmed, QIcon.Mode.Disabled)
                return icon

            icon_size = QSize(52, 52)
            back_icon = create_dimmed_icon(icon_path, icon_size, 180, flip_h=True)
            up_icon = create_dimmed_icon(icon_path, icon_size, 90)
            
            self.btn_center_back = QPushButton()
            self.btn_center_back.setIcon(back_icon)
            self.btn_center_back.setIconSize(icon_size)
            self.btn_center_back.setFixedSize(60, 60)
            self.btn_center_back.setStyleSheet(btn_style)
            self.btn_center_back.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_center_back.clicked.connect(self.nav_back_clicked.emit)
            self.btn_center_back.setToolTip(AppContext.tr("anl_btn_back"))
            
            self.btn_center_up = QPushButton()
            self.btn_center_up.setIcon(up_icon)
            self.btn_center_up.setIconSize(icon_size)
            self.btn_center_up.setFixedSize(60, 60)
            self.btn_center_up.setStyleSheet(btn_style)
            self.btn_center_up.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_center_up.clicked.connect(self.nav_up_clicked.emit)
            self.btn_center_up.setToolTip(AppContext.tr("anl_btn_up"))
            
            btn_layout.addWidget(self.btn_center_back)
            btn_layout.addWidget(self.btn_center_up)
            
            # Precise layout positioning (Strict 10px spacing from name)
            cw_layout.addWidget(lbl_size)
            cw_layout.addSpacing(10)
            cw_layout.addWidget(lbl_name)
            cw_layout.addSpacing(10)
            cw_layout.addWidget(btn_container)
            
            # Add to scene
            proxy = self.scene.addWidget(center_widget)
            # Center it
            proxy.setPos(-130, -130)

            # 4. Draw Rings with calculated dynamic radius
            self.draw_level(self.current_view_node, 90, 360, 0, current_inner_radius, ring_thickness, effective_depth)
            
            dim = BASE_RADIUS * 2 + 20
            self.scene.setSceneRect(-dim/2, -dim/2, dim, dim)
            self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        except Exception as e:
            logging.error(f"Analyzer: Error refreshing chart: {e}", exc_info=True)

    def set_nav_buttons_state(self, can_go_back, can_go_up):
        # Prevent crash if C++ object deleted but Python object exists
        try:
            if hasattr(self, 'btn_center_back') and self.btn_center_back:
                self.btn_center_back.setEnabled(can_go_back)
            if hasattr(self, 'btn_center_up') and self.btn_center_up:
                self.btn_center_up.setEnabled(can_go_up)
            if hasattr(self, 'btn_tree_back') and self.btn_tree_back:
                self.btn_tree_back.setEnabled(can_go_back)
            if hasattr(self, 'btn_tree_up') and self.btn_tree_up:
                self.btn_tree_up.setEnabled(can_go_up)
        except RuntimeError:
            pass

    def set_hovered_slice(self, item):
        self.hovered_slice_item = item
        self.update_highlights()

    def clear_hovered_slice(self, item=None):
        if item is None or self.hovered_slice_item == item:
            self.hovered_slice_item = None
            self.update_highlights()

    def set_hovered_file_on_chart(self, filepath: str):
        self.hovered_file_path = filepath
        self.update_highlights()

    def highlight_file_on_chart(self, filepath: str):
        self.selected_file_path = filepath
        self.update_highlights()

    def highlight_by_ext(self, ext: str):
        self.hovered_ext = ext
        self.update_highlights()

    def clear_highlight(self):
        self.hovered_ext = ""
        self.hovered_slice_item = None
        self.update_highlights()

    def update_highlights(self):
        has_hovered_ext = bool(self.hovered_ext)
        ext_clean = self.hovered_ext.lower().replace('.', '') if has_hovered_ext else ""
        
        norm_selected = os.path.normcase(os.path.normpath(self.selected_file_path)) if self.selected_file_path else None
        norm_hovered = os.path.normcase(os.path.normpath(self.hovered_file_path)) if self.hovered_file_path else None
        
        # If hovered_slice_item is set, determine if it is a directory
        hovered_dir_path = None
        if self.hovered_slice_item:
            s_data = self.hovered_slice_item.data
            s_type = s_data.get('type')
            s_path = s_data.get('path', '')
            if s_type in ('dir', 'dir_group'):
                hovered_dir_path = os.path.normcase(os.path.normpath(s_path))
        
        for item in self.scene.items():
            if isinstance(item, (TreeMapSliceItem, SunburstSliceItem)):
                item_path = item.data.get('path', '')
                item_type = item.data.get('type')
                norm_item_path = os.path.normcase(os.path.normpath(item_path)) if item_path else None
                
                # Check for active state:
                
                # 1. Hovered extension from right table takes absolute precedence!
                if has_hovered_ext:
                    if item_type == 'file':
                        item_ext = os.path.splitext(item.data.get('name', ''))[1].lower().replace('.', '')
                        if item_ext == ext_clean:
                            item.setPen(QPen(QColor("#1a1a1a"), 1, Qt.PenStyle.SolidLine))
                            item.setBrush(QBrush(item.base_color.lighter(150)))
                            item.set_text_color("black")
                            continue
                    item.reset_highlight()
                    continue
                
                # 2. Hovered folder on chart
                if hovered_dir_path and self.chart_mode == 'treemap':
                    # If it is the folder itself
                    if item_type == 'dir' and norm_item_path == hovered_dir_path:
                        item.setPen(QPen(Qt.GlobalColor.white, 3, Qt.PenStyle.SolidLine))
                        item.setBrush(QBrush(item.base_color))
                        continue
                    # If it is a descendant file inside that folder
                    elif norm_item_path and os.path.normcase(os.path.dirname(norm_item_path)) == hovered_dir_path:
                        item.setPen(QPen(QColor("#1a1a1a"), 1, Qt.PenStyle.SolidLine))
                        item.setBrush(QBrush(item.base_color.lighter(115)))
                        continue
                
                # 3. Selected file / Hovered file / Hovered file slice
                is_selected = (norm_selected and norm_item_path == norm_selected)
                is_hovered = (norm_hovered and norm_item_path == norm_hovered)
                is_slice_hovered = (self.hovered_slice_item == item)
                
                item.is_selected = is_selected
                
                if item_type == 'file' and (is_selected or is_hovered or is_slice_hovered):
                    item.setPen(QPen(Qt.GlobalColor.white, 3, Qt.PenStyle.SolidLine))
                    item.setBrush(QBrush(item.base_color.lighter(150)))
                    item.set_text_color("black")
                else:
                    item.reset_highlight()

    # --- NEW RENDERING LOGIC HELPERS ---

    def process_dirs(self, dirs, total_size, span_angle, min_angle, parent_path):
        """
        Sorts directories and groups small ones into 'Other Folders'.
        """
        render_items = []
        dirs.sort(key=lambda x: x['size'], reverse=True)
        
        other_dirs_size = 0
        other_dirs_count = 0
        
        for d in dirs:
            d_span = (d['size'] / total_size) * span_angle
            if d_span < min_angle:
                other_dirs_size += d['size']
                other_dirs_count += 1
            else:
                render_items.append(d) # Keep as is (Large Dir)
        
        if other_dirs_size > 0:
            render_items.append({
                'name': f"Other Folders ({other_dirs_count})",
                'path': parent_path,
                'type': 'dir_group',
                'size': other_dirs_size,
                'count': other_dirs_count
            })
            
        return render_items

    def process_files_by_ext(self, files, total_size, span_angle, min_angle, parent_path):
        """
        Groups files by extension.
        """
        ext_map = {}
        for f in files:
            ext = os.path.splitext(f['name'])[1].lower()
            if not ext: ext = "no_ext"
            if ext not in ext_map: ext_map[ext] = []
            ext_map[ext].append(f)
            
        sorted_exts = sorted(ext_map.items(), key=lambda item: sum(x['size'] for x in item[1]), reverse=True)
        
        render_items = []
        TOP_EXT_LIMIT = 10
        
        for i, (ext, f_list) in enumerate(sorted_exts):
            if i >= TOP_EXT_LIMIT:
                continue
                
            f_list.sort(key=lambda x: x['size'], reverse=True)
            
            grp_other_size = 0
            grp_other_count = 0
            
            for f in f_list:
                f_span = (f['size'] / total_size) * span_angle
                if f_span < min_angle:
                    grp_other_size += f['size']
                    grp_other_count += 1
                else:
                    render_items.append(f) # Large file
            
            if grp_other_size > 0:
                label_ext = ext if ext != "no_ext" else "Files"
                render_items.append({
                    'name': f"Other {label_ext} ({grp_other_count})",
                    'path': parent_path,
                    'type': 'file_group_ext',
                    'size': grp_other_size,
                    'ext': ext
                })

        misc_files = []
        if len(sorted_exts) > TOP_EXT_LIMIT:
            for i in range(TOP_EXT_LIMIT, len(sorted_exts)):
                misc_files.extend(sorted_exts[i][1])
                
        if misc_files:
            misc_size = sum(f['size'] for f in misc_files)
            render_items.append({
                'name': f"Misc Files ({len(misc_files)})",
                'path': parent_path,
                'type': 'file_group_misc',
                'size': misc_size
            })
            
        return render_items

    def draw_level(self, node, start_angle, span_angle, level, inner_r, ring_thick, max_draw_level):
        if level >= max_draw_level: return
 
        children = node.get('children', [])
        path = node.get('path', '')
        
        is_root_drive = False
        if level == 0 and os.path.exists(path):
            drive, tail = os.path.splitdrive(path)
            if tail in [os.sep, '', '/']: is_root_drive = True

        if not children and not is_root_drive: return

        node_size = node['size']
        if is_root_drive:
            try:
                total, used, free = shutil.disk_usage(path)
                node_size = total
            except: pass
        
        if node_size == 0: return

        current_r_in = inner_r + (level * ring_thick)
        current_r_out = current_r_in + ring_thick
        min_angle = 0.5 
        
        raw_dirs = [c for c in children if c['type'] == 'dir']
        raw_files = [c for c in children if c['type'] == 'file']
        
        dir_items = self.process_dirs(raw_dirs, node_size, span_angle, min_angle, path)
        file_items = self.process_files_by_ext(raw_files, node_size, span_angle, min_angle, path)
        
        render_queue = dir_items + file_items
        
        if is_root_drive:
            try:
                total, used, free = shutil.disk_usage(path)
                render_queue.append({
                    'name': AppContext.tr('anl_free_space'),
                    'path': path,
                    'type': 'free_space',
                    'size': free
                })
            except: pass

        current_angle = start_angle
        
        for item_data in render_queue:
            item_size = item_data['size']
            item_span = (item_size / node_size) * span_angle
            
            if item_span < 0.1: 
                current_angle += item_span
                continue
                
            color = "#888"
            t = item_data['type']
            
            if t == 'dir':
                color = COLOR_FOLDER_BASE
            
            elif t == 'dir_group':
                color = COLOR_FOLDER_BASE
                
            elif t == 'file':
                ext = os.path.splitext(item_data['name'])[1]
                color = self.get_color_for_ext(ext)
                
            elif t == 'file_group_ext':
                ext = item_data.get('ext', '')
                base = QColor(self.get_color_for_ext(ext))
                color = base.darker(150).name()
                
            elif t == 'file_group_misc':
                color = COLOR_OTHER
                
            elif t == 'free_space':
                color = COLOR_FREE
            
            slice_item = SunburstSliceItem(current_angle, item_span, current_r_in, current_r_out, color, item_data, level)
            self.scene.addItem(slice_item)
            
            if t == 'dir' and item_data.get('children'):
                self.draw_level(item_data, current_angle, item_span, level + 1, inner_r, ring_thick, max_draw_level)
                
            current_angle += item_span

    def get_slice_item(self, item):
        while item:
            if isinstance(item, (SunburstSliceItem, TreeMapSliceItem)):
                return item
            item = item.parentItem()
        return None

    def mouseDoubleClickEvent(self, event):
        item = self.get_slice_item(self.scene.itemAt(self.mapToScene(event.pos()), self.transform()))
        if item:
            if item.data['type'] == 'file':
                if event.button() == Qt.MouseButton.LeftButton:
                    self.open_file(item.data['path'])
                    return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        # Handle Middle Click first
        if event.button() == Qt.MouseButton.MiddleButton:
            item = self.get_slice_item(self.scene.itemAt(self.mapToScene(event.pos()), self.transform()))
            if item:
                if item.data['type'] == 'file':
                    self.reveal_file(item.data['path'])
                    return

        # Browse Request (If no data loaded, any Left click on empty chart triggers browse dialog)
        pos = self.mapToScene(event.pos())
        dist = (pos.x()**2 + pos.y()**2) ** 0.5
        if self.root_data is None:
            # If scanning is not active, Left click triggers browse
            if not getattr(self, 'is_scanning', False):
                if event.button() == Qt.MouseButton.LeftButton:
                    self.browse_requested.emit()
            super().mousePressEvent(event) # Pass events to buttons (like Stop button)
            return

        # Handle Left/Right for custom logic, but call super for standard events (buttons etc)
        if self.chart_mode == 'sunburst' and dist < self.INNER_RADIUS and event.button() == Qt.MouseButton.LeftButton:
            # Check if we clicked on a widget (buttons)
            item_at = self.scene.itemAt(pos, self.transform())
            if not isinstance(item_at, QGraphicsProxyWidget):
                self.center_clicked.emit()
                return

        item = self.get_slice_item(self.scene.itemAt(pos, self.transform()))
        
        if item:
            if event.button() == Qt.MouseButton.LeftButton:
                if item.data['type'] == 'dir':
                    self.node_clicked.emit(item.data)
                elif item.data['type'] == 'file':
                    self.file_clicked.emit(item.data)
        
        super().mousePressEvent(event)

    def open_file(self, path):
        if os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def reveal_file(self, path):
        if not os.path.exists(path): return
        from utils_common import reveal_in_explorer
        reveal_in_explorer(path)
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                path = urls[0].toLocalFile()
                if os.path.isdir(path):
                    self.folder_dropped.emit(path)
                    event.accept()
                    return
        event.ignore()
    
    def contextMenuEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        item = self.get_slice_item(self.scene.itemAt(scene_pos, self.transform()))
        if item:
            self.slice_context_menu.emit(item.data, event.globalPos())
            event.accept()
        else:
            super().contextMenuEvent(event)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.scene:
            if self.chart_mode == 'treemap':
                if self.current_view_node:
                    # Временно вписываем старую сцену в новые границы вьюпорта
                    self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.IgnoreAspectRatio)
                    self.resize_timer.start(1000)
                else:
                    self.refresh_chart()
            else:
                self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            
    def update_ui_text(self):
        # Refresh dynamic texts
        if self.root_data is None:
            self.show_empty_state()
        else:
            self.refresh_chart()