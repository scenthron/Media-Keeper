
import os
import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, 
    QScrollArea, QWidget, QProgressBar
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QElapsedTimer, QSize
from PyQt6.QtGui import QColor, QPalette, QIcon
from config import AppContext
from ui_widgets_base import FlowLayout

class MatrixFilterDialog(QDialog):
    def __init__(self, found_extensions, parent=None):
        super().__init__(parent)
        self.setWindowTitle(AppContext.tr("cln_filter_title"))
        self.resize(800, 600)
        self.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: white; }
            QLabel { color: #cccccc; }
            QPushButton { background-color: #444; border: 1px solid #555; color: white; border-radius: 4px; padding: 6px; }
            QPushButton:hover { background-color: #555; }
            QScrollArea { border: none; background: transparent; }
        """)
        self.found_extensions = found_extensions
        self.selected_exts = set()
        self.mode = 'include'
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        header = QFrame()
        header.setStyleSheet("background-color: #333; border: none;")
        header.setFixedHeight(40)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(15, 0, 15, 0)
        lbl_title = QLabel(AppContext.tr("cln_matrix_header"))
        lbl_title.setStyleSheet("font-weight: bold; font-size: 13px; margin-left: 5px; letter-spacing: 0.5px; color: #eee;")
        hl.addWidget(lbl_title)
        self.layout.addWidget(header)
        
        mode_container = QFrame()
        mode_container.setStyleSheet("background-color: #2b2b2b; padding: 10px 15px;")
        ml = QHBoxLayout(mode_container)
        self.btn_include = QPushButton(AppContext.tr("cln_mode_include"))
        self.btn_include.setCheckable(True)
        self.btn_include.clicked.connect(lambda: self.set_mode('include'))
        self.btn_include.setFixedHeight(36) 
        self.btn_exclude = QPushButton(AppContext.tr("cln_mode_exclude"))
        self.btn_exclude.setCheckable(True)
        self.btn_exclude.clicked.connect(lambda: self.set_mode('exclude'))
        self.btn_exclude.setFixedHeight(36)
        ml.addWidget(self.btn_include)
        ml.addWidget(self.btn_exclude)
        self.layout.addWidget(mode_container)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.matrix_widget = QWidget()
        self.matrix_layout = QVBoxLayout(self.matrix_widget)
        self.matrix_layout.setContentsMargins(20, 4, 20, 4)
        self.matrix_layout.setSpacing(4)
        self.chip_buttons = {}
        self.render_matrix()
        scroll.setWidget(self.matrix_widget)
        self.layout.addWidget(scroll)
        
        footer = QFrame()
        footer.setStyleSheet("background-color: #222; border: none;")
        footer.setFixedHeight(48)
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(15, 0, 15, 0)
        self.lbl_stats = QLabel(AppContext.tr("cln_stats_selected").format(0))
        fl.addWidget(self.lbl_stats)
        fl.addStretch()
        btn_cancel = QPushButton(AppContext.tr("btn_cancel"))
        btn_cancel.clicked.connect(self.reject)
        fl.addWidget(btn_cancel)
        btn_apply = QPushButton(AppContext.tr("cln_btn_apply"))
        btn_apply.setStyleSheet("background-color: #15803d; border-color: #16a34a; font-weight: bold;")
        btn_apply.clicked.connect(self.accept)
        fl.addWidget(btn_apply)
        self.layout.addWidget(footer)
        self.set_mode('include')

    def set_mode(self, mode):
        self.mode = mode
        if mode == 'include':
            self.btn_include.setChecked(True)
            self.btn_exclude.setChecked(False)
            self.btn_include.setStyleSheet("background-color: #064e3b; color: #34d399; border: 1px solid #059669; font-weight: bold;")
            self.btn_exclude.setStyleSheet("background-color: #333; color: #888; border: 1px solid #444;")
        else:
            self.btn_include.setChecked(False)
            self.btn_exclude.setChecked(True)
            self.btn_include.setStyleSheet("background-color: #333; color: #888; border: 1px solid #444;")
            self.btn_exclude.setStyleSheet("background-color: #450a0a; color: #fca5a5; border: 1px solid #b91c1c; font-weight: bold;")

    def render_matrix(self):
        tr_key_map = {"Images": "cln_grp_images", "Video": "cln_grp_video", "Audio": "cln_grp_audio", "Documents": "cln_grp_docs", "Archives": "cln_grp_archives", "Code": "cln_grp_code", "Other": "cln_grp_other"}
        for group_name, items in self.found_extensions.items():
            header_frame = QFrame()
            header_layout = QHBoxLayout(header_frame)
            header_layout.setContentsMargins(0, 6, 0, 2)
            display_name = AppContext.tr(tr_key_map.get(group_name, group_name.upper()))
            lbl_g = QLabel(display_name.upper())
            lbl_g.setStyleSheet("color: #888; font-weight: bold; font-size: 11px;")
            header_layout.addWidget(lbl_g)
            
            btn_toggle_group = QPushButton()
            icons_dir = AppContext.find_resource_dir("icons")
            icon_gray = os.path.join(icons_dir, "square-chevron-down-gray.svg").replace("\\", "/")
            icon_white = os.path.join(icons_dir, "square-chevron-down.svg").replace("\\", "/")
            btn_toggle_group.setIconSize(QSize(16, 16))
            btn_toggle_group.setFixedSize(24, 24)
            btn_toggle_group.setToolTip(AppContext.tr("cln_btn_select_group"))
            btn_toggle_group.setStyleSheet(f"""
                QPushButton {{ 
                    background-color: transparent; 
                    border: 1px solid #555; 
                    border-radius: 4px; 
                    qproperty-icon: url("{icon_gray}");
                }}
                QPushButton:hover {{ 
                    background-color: rgba(59, 130, 246, 0.1); 
                    border-color: #3b82f6; 
                    qproperty-icon: url("{icon_white}");
                }}
            """)
            btn_toggle_group.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_toggle_group.clicked.connect(lambda _, i=items: self.toggle_group(i))
            header_layout.addWidget(btn_toggle_group)
            header_frame.setLayout(header_layout)
            self.matrix_layout.addWidget(header_frame)
            
            flow_container = QWidget()
            flow = FlowLayout(flow_container, margin=0, spacing=8)
            for item in items:
                ext = item['ext']
                count = item['count']
                btn = QPushButton(f"{ext} ({count})")
                btn.setCheckable(True)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda _, e=ext: self.toggle_ext(e))
                self.update_chip_style(btn, False)
                self.chip_buttons[ext] = btn
                flow.addWidget(btn)
            self.matrix_layout.addWidget(flow_container)
        self.matrix_layout.addStretch()

    def update_chip_style(self, btn, checked):
        if checked: btn.setStyleSheet("QPushButton { background-color: rgba(59, 130, 246, 0.2); border: 1px solid #3b82f6; color: white; border-radius: 12px; padding: 4px 10px; font-size: 12px; }")
        else: btn.setStyleSheet("QPushButton { background-color: #333; border: 1px solid #444; color: #ccc; border-radius: 12px; padding: 4px 10px; font-size: 12px; } QPushButton:hover { background-color: #444; }")

    def toggle_ext(self, ext):
        if ext in self.selected_exts:
            self.selected_exts.remove(ext)
            self.update_chip_style(self.chip_buttons[ext], False)
            self.chip_buttons[ext].setChecked(False)
        else:
            self.selected_exts.add(ext)
            self.update_chip_style(self.chip_buttons[ext], True)
            self.chip_buttons[ext].setChecked(True)
        self.update_stats()

    def toggle_group(self, items):
        all_selected = True
        for item in items:
            if item['ext'] not in self.selected_exts:
                all_selected = False
                break
        should_select = not all_selected
        for item in items:
            ext = item['ext']
            if should_select:
                if ext not in self.selected_exts:
                    self.selected_exts.add(ext)
                    self.update_chip_style(self.chip_buttons[ext], True)
                    self.chip_buttons[ext].setChecked(True)
            else:
                if ext in self.selected_exts:
                    self.selected_exts.remove(ext)
                    self.update_chip_style(self.chip_buttons[ext], False)
                    self.chip_buttons[ext].setChecked(False)
        self.update_stats()

    def update_stats(self):
        self.lbl_stats.setText(AppContext.tr("cln_stats_selected").format(len(self.selected_exts)))

    def get_result(self):
        return {'mode': self.mode, 'exts': self.selected_exts}

class CleanerOverlay(QWidget):
    cancel_requested = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setMouseTracking(True)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(0, 0, 0, 180))
        self.setPalette(pal)
        
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.container = QFrame()
        self.container.setFixedSize(400, 240)
        self.container.setStyleSheet("QFrame { background-color: #2b2b2b; border: 1px solid #444; border-radius: 8px; } QLabel { color: white; border: none; }")
        
        v_layout = QVBoxLayout(self.container)
        v_layout.setContentsMargins(20, 20, 20, 20)
        v_layout.setSpacing(10)
        
        self.lbl_title = QLabel(AppContext.tr("cln_ovl_moving"))
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #3b82f6;")
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v_layout.addWidget(self.lbl_title)
        
        self.lbl_timer = QLabel("00:00")
        self.lbl_timer.setStyleSheet("color: #888; font-size: 12px; font-family: monospace;")
        self.lbl_timer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v_layout.addWidget(self.lbl_timer)
        
        self.lbl_total = QLabel("Total: 0/0")
        self.lbl_total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v_layout.addWidget(self.lbl_total)
        
        self.bar_total = QProgressBar()
        self.bar_total.setFixedHeight(8)
        self.bar_total.setStyleSheet("QProgressBar { background: #111; border: none; border-radius: 4px; } QProgressBar::chunk { background: #3b82f6; border-radius: 4px; }")
        self.bar_total.setTextVisible(False)
        v_layout.addWidget(self.bar_total)
        
        self.file_info_widget = QWidget()
        self.file_info_widget.setFixedHeight(60)
        self.file_info_widget.setStyleSheet("background: transparent; border: none;")
        f_layout = QVBoxLayout(self.file_info_widget)
        f_layout.setContentsMargins(0,0,0,0)
        f_layout.setSpacing(5)
        
        self.lbl_file = QLabel("Preparing...")
        self.lbl_file.setStyleSheet("color: #aaa; font-size: 11px;")
        self.lbl_file.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_file.setWordWrap(True)
        f_layout.addWidget(self.lbl_file)
        
        self.bar_file = QProgressBar()
        self.bar_file.setFixedHeight(6)
        self.bar_file.setStyleSheet("QProgressBar { background: #111; border: none; border-radius: 3px; } QProgressBar::chunk { background: #10b981; border-radius: 3px; }")
        self.bar_file.setTextVisible(False)
        self.bar_file.hide()
        f_layout.addWidget(self.bar_file)
        v_layout.addWidget(self.file_info_widget)
        
        self.btn_stop = QPushButton(AppContext.tr("cln_btn_stop_loading"))
        self.btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stop.setFixedSize(120, 36)
        self.btn_stop.setStyleSheet("QPushButton { background-color: #dc2626; color: white; font-weight: bold; border: none; border-radius: 4px; } QPushButton:hover { background-color: #ef4444; }")
        self.btn_stop.clicked.connect(self.cancel_requested.emit)
        h_btn = QVBoxLayout()
        h_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_btn.addWidget(self.btn_stop)
        v_layout.addLayout(h_btn)
        
        self.layout.addWidget(self.container)
        self.file_timer = QElapsedTimer()
        self.global_timer = QElapsedTimer()
        self.ui_timer = QTimer(self)
        self.ui_timer.setInterval(1000)
        self.ui_timer.timeout.connect(self._update_timer_label)
        
    def start_process(self, total_items: int, title_key: str = "cln_ovl_moving") -> None:
        self.lbl_title.setText(AppContext.tr(title_key))
        self.lbl_file.show()
        self.bar_total.setRange(0, total_items)
        self.bar_total.setValue(0)
        self.btn_stop.show()
        self.global_timer.start()
        self.ui_timer.start()
        self._update_timer_label()
        self.show()
        
    def start_loading_mode(self, total_items: int) -> None:
        self.lbl_title.setText(AppContext.tr("cln_ovl_loading"))
        self.lbl_file.hide()
        self.bar_file.hide()
        self.bar_total.setRange(0, total_items)
        self.bar_total.setValue(0)
        self.lbl_timer.setText("")
        self.show()
        
    def _update_timer_label(self) -> None:
        ms = self.global_timer.elapsed()
        seconds = (ms // 1000) % 60
        minutes = (ms // (1000 * 60)) % 60
        self.lbl_timer.setText(f"{minutes:02}:{seconds:02}")
        
    def update_total(self, processed: int, total: int) -> None:
        self.bar_total.setValue(processed)
        self.lbl_total.setText(f"Processed: {processed}/{total}")
        
    def start_file(self, filename: str) -> None:
        self.lbl_file.setText(filename)
        self.bar_file.setValue(0)
        self.bar_file.hide()
        self.file_timer.start()
        
    def update_file_progress(self, bytes_moved: int, total_bytes: int) -> None:
        if total_bytes > 0:
            pct = int((bytes_moved / total_bytes) * 100)
            self.bar_file.setValue(pct)
        if self.file_timer.isValid() and self.file_timer.elapsed() > 4000:
            if self.bar_file.isHidden(): self.bar_file.show()
    
    def hide(self) -> None:
        self.ui_timer.stop()
        super().hide()

class CleanerResultDialog(QDialog):
    def __init__(self, moved_count: int, error_count: int, time_str: str | None = None, parent: QWidget | None = None, action_type: str = 'move') -> None:
        super().__init__(parent)
        self.setWindowTitle(AppContext.tr("dlg_result_title"))
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet("QDialog { background-color: #2b2b2b; border: 1px solid #444; border-radius: 8px; } QLabel { color: #cccccc; font-size: 14px; background: transparent; } QPushButton { background-color: #3b82f6; color: white; font-weight: bold; border: none; border-radius: 4px; padding: 6px 20px; min-width: 80px; } QPushButton:hover { background-color: #2563eb; }")
        width = 320 if not time_str else 380
        self.setFixedSize(width, 160 if error_count > 0 else 140)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        icon_layout = QVBoxLayout()
        icon_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        lbl_icon = QLabel()
        if error_count > 0:
            lbl_icon.setText("⚠️")
            lbl_icon.setStyleSheet("font-size: 32px; color: #ef4444;")
        else:
            lbl_icon.setText("✔")
            lbl_icon.setStyleSheet("font-size: 32px; color: #10b981;")
        icon_layout.addWidget(lbl_icon)
        layout.addLayout(icon_layout)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(5)
        if error_count == 0:
            if action_type == 'delete':
                key = "cln_res_delete_success_fmt"
            elif action_type == 'delete_folders':
                key = "cln_res_folder_delete_success_fmt"
            else:
                key = "cln_res_success_fmt"
            msg = AppContext.tr(key).format(moved_count)
        else:
            if action_type == 'delete':
                key = "cln_res_delete_error_fmt"
            elif action_type == 'delete_folders':
                key = "cln_res_folder_delete_error_fmt"
            else:
                key = "cln_res_error_fmt"
            msg = AppContext.tr(key).format(moved_count, error_count)
        lbl_msg = QLabel(msg)
        lbl_msg.setWordWrap(True)
        lbl_msg.setTextFormat(Qt.TextFormat.RichText)
        text_layout.addWidget(lbl_msg)
        if time_str:
            lbl_time = QLabel(AppContext.tr("cln_res_time").format(time_str))
            lbl_time.setStyleSheet("color: #666; font-size: 11px; margin-top: 4px;")
            text_layout.addWidget(lbl_time)
        text_layout.addStretch()
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_ok = QPushButton(AppContext.tr("btn_ok"))
        btn_ok.clicked.connect(self.accept)
        btn_layout.addWidget(btn_ok)
        text_layout.addLayout(btn_layout)
        layout.addLayout(text_layout)

c l a s s   M o v e P r e v i e w D i a l o g ( Q D i a l o g ) :  
         d e f   _ _ i n i t _ _ ( s e l f ,   m a p p i n g :   l i s t [ d i c t ] ,   p a r e n t = N o n e ) :  
                 s u p e r ( ) . _ _ i n i t _ _ ( p a r e n t )  
                 s e l f . s e t W i n d o w T i t l e ( A p p C o n t e x t . t r ( " c l n _ p r e v i e w _ t i t l e " )   i f   h a s a t t r ( A p p C o n t e x t ,   ' t r ' )   e l s e   " >4B25@645=85  ?5@5<5I5=8O" )  
                 s e l f . r e s i z e ( 7 0 0 ,   5 0 0 )  
                 s e l f . s e t S t y l e S h e e t ( " " "  
                         Q D i a l o g   {   b a c k g r o u n d - c o l o r :   # 2 b 2 b 2 b ;   c o l o r :   w h i t e ;   }  
                         Q L a b e l   {   c o l o r :   # c c c c c c ;   f o n t - s i z e :   1 2 p x ;   }  
                         Q P u s h B u t t o n   {   b a c k g r o u n d - c o l o r :   # 4 4 4 ;   b o r d e r :   1 p x   s o l i d   # 5 5 5 ;   c o l o r :   w h i t e ;   b o r d e r - r a d i u s :   4 p x ;   p a d d i n g :   6 p x   1 5 p x ;   f o n t - w e i g h t :   b o l d ;   }  
                         Q P u s h B u t t o n : h o v e r   {   b a c k g r o u n d - c o l o r :   # 5 5 5 ;   }  
                         Q S c r o l l A r e a   {   b o r d e r :   1 p x   s o l i d   # 3 3 3 ;   b a c k g r o u n d :   # 1 e 1 e 1 e ;   b o r d e r - r a d i u s :   4 p x ;   }  
                 " " " )  
                  
                 l a y o u t   =   Q V B o x L a y o u t ( s e l f )  
                 l a y o u t . s e t S p a c i n g ( 1 0 )  
                  
                 l b l _ i n f o   =   Q L a b e l ( " !;54CNI85  D09;K  1C4CB  ?5@5<5I5=K  8  ?5@58<5=>20=K  ?@8  A>2?045=88  8<5=: "   i f   A p p C o n t e x t . L A N G   = =   " R U "   e l s e   " T h e   f o l l o w i n g   f i l e s   w i l l   b e   m o v e d   ( a n d   r e n a m e d   o n   c o n f l i c t ) : " )  
                 l a y o u t . a d d W i d g e t ( l b l _ i n f o )  
                  
                 s c r o l l   =   Q S c r o l l A r e a ( )  
                 s c r o l l . s e t W i d g e t R e s i z a b l e ( T r u e )  
                 c o n t e n t   =   Q W i d g e t ( )  
                 c o n t e n t . s e t S t y l e S h e e t ( " b a c k g r o u n d :   t r a n s p a r e n t ; " )  
                 v b o x   =   Q V B o x L a y o u t ( c o n t e n t )  
                 v b o x . s e t S p a c i n g ( 4 )  
                  
                 f o r   i t e m   i n   m a p p i n g :  
                         s r c   =   i t e m . g e t ( " s r c " ,   " " )  
                         d s t   =   i t e m . g e t ( " d s t " ,   " " )  
                          
                         f r a m e   =   Q F r a m e ( )  
                         f r a m e . s e t S t y l e S h e e t ( " b a c k g r o u n d :   # 2 5 2 5 2 6 ;   b o r d e r - r a d i u s :   4 p x ;   p a d d i n g :   4 p x ; " )  
                         f l   =   Q V B o x L a y o u t ( f r a m e )  
                         f l . s e t C o n t e n t s M a r g i n s ( 5 ,   5 ,   5 ,   5 )  
                          
                         l _ s r c   =   Q L a b e l ( f " 7:   { s r c } "   i f   A p p C o n t e x t . L A N G   = =   " R U "   e l s e   f " F r o m :   { s r c } " )  
                         l _ s r c . s e t S t y l e S h e e t ( " c o l o r :   # 9 9 9 ;   f o n t - s i z e :   1 1 p x ; " )  
                         l _ d s t   =   Q L a b e l ( f "   :   { d s t } "   i f   A p p C o n t e x t . L A N G   = =   " R U "   e l s e   f "     T o :   { d s t } " )  
                         l _ d s t . s e t S t y l e S h e e t ( " c o l o r :   # 4 a d e 8 0 ;   f o n t - w e i g h t :   b o l d ; " )  
                          
                         f l . a d d W i d g e t ( l _ s r c )  
                         f l . a d d W i d g e t ( l _ d s t )  
                         v b o x . a d d W i d g e t ( f r a m e )  
                          
                 v b o x . a d d S t r e t c h ( )  
                 s c r o l l . s e t W i d g e t ( c o n t e n t )  
                 l a y o u t . a d d W i d g e t ( s c r o l l )  
                  
                 b t n _ b o x   =   Q H B o x L a y o u t ( )  
                 b t n _ b o x . a d d S t r e t c h ( )  
                  
                 b t n _ c a n c e l   =   Q P u s h B u t t o n ( " B<5=0"   i f   A p p C o n t e x t . L A N G   = =   " R U "   e l s e   " C a n c e l " )  
                 b t n _ c a n c e l . c l i c k e d . c o n n e c t ( s e l f . r e j e c t )  
                  
                 b t n _ a p p l y   =   Q P u s h B u t t o n ( " @>4>;68BL"   i f   A p p C o n t e x t . L A N G   = =   " R U "   e l s e   " P r o c e e d " )  
                 b t n _ a p p l y . s e t S t y l e S h e e t ( " b a c k g r o u n d - c o l o r :   # 3 b 8 2 f 6 ;   b o r d e r :   n o n e ; " )  
                 b t n _ a p p l y . c l i c k e d . c o n n e c t ( s e l f . a c c e p t )  
                  
                 b t n _ b o x . a d d W i d g e t ( b t n _ c a n c e l )  
                 b t n _ b o x . a d d W i d g e t ( b t n _ a p p l y )  
                  
                 l a y o u t . a d d L a y o u t ( b t n _ b o x )  
 