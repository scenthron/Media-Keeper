import os
import re

def rewrite_ui():
    frag_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(frag_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract the block to replace
    # We replace from `lbl_params_title = QLabel("Настройки поиска:"` up to `self.main_splitter.addWidget(self.top_settings)`
    start_str = 'lbl_params_title = QLabel("Настройки поиска:" if AppContext.is_ru() else "Search Settings:")'
    end_str = 'self.main_splitter.addWidget(self.top_settings)'
    
    if start_str not in content or end_str not in content:
        print("Could not find replacement bounds")
        return
        
    start_idx = content.find(start_str)
    end_idx = content.find(end_str)
    
    old_block = content[start_idx:end_idx]

    new_block = """lbl_params_title = QLabel("Настройки поиска:" if AppContext.is_ru() else "Search Settings:")
        lbl_params_title.setStyleSheet("color: #aaa; font-weight: bold; font-size: 11px;")
        col_params.addWidget(lbl_params_title)
        
        self.settings_tabs = QTabWidget()
        self.settings_tabs.setStyleSheet(\"\"\"
            QTabWidget::pane { border: 1px solid #444; border-radius: 6px; background-color: #2b2b2b; }
            QTabBar::tab { background-color: #1e1e1e; color: #888; padding: 6px 12px; border: 1px solid #444; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; }
            QTabBar::tab:selected { background-color: #2b2b2b; color: white; font-weight: bold; }
        \"\"\")
        
        slider_style = "QSlider::groove:horizontal { height: 4px; background: #555; border-radius: 2px; } QSlider::handle:horizontal { background: #3b82f6; width: 14px; height: 14px; margin-top: -5px; margin-bottom: -5px; border-radius: 7px; }"
        
        # ==========================================
        # TAB 1: PIXEL MATCHING
        # ==========================================
        tab_pixel = QWidget()
        tab_pixel_layout = QVBoxLayout(tab_pixel)
        
        lbl_sim_pixel = QLabel("Схожесть (Пиксели):" if AppContext.is_ru() else "Similarity (Pixels):")
        lbl_sim_pixel.setStyleSheet("color: #eee; font-weight: bold; font-size: 12px; margin-top: 5px;")
        tab_pixel_layout.addWidget(lbl_sim_pixel)
        
        sim_layout_pixel = QHBoxLayout()
        self.slider_pixel = QSlider(Qt.Orientation.Horizontal)
        self.slider_pixel.setRange(0, 100)
        self.slider_pixel.setValue(80)
        self.slider_pixel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider_pixel.setStyleSheet(slider_style)
        
        self.lbl_pixel_val = QLabel("80%")
        self.lbl_pixel_val.setFixedWidth(40)
        self.lbl_pixel_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_pixel_val.setStyleSheet("color: #3b82f6; font-weight: bold;")
        self.slider_pixel.valueChanged.connect(lambda v: self.lbl_pixel_val.setText(f"{v}%"))
        
        sim_layout_pixel.addWidget(self.slider_pixel)
        sim_layout_pixel.addWidget(self.lbl_pixel_val)
        tab_pixel_layout.addLayout(sim_layout_pixel)
        
        desc_pixel = QLabel("Мгновенный поиск. Чувствителен к изменению масштаба." if AppContext.is_ru() else "Instant search. Sensitive to scale changes.")
        desc_pixel.setStyleSheet("color: #888; font-size: 11px;")
        desc_pixel.setWordWrap(True)
        tab_pixel_layout.addWidget(desc_pixel)
        
        tab_pixel_layout.addStretch()
        self.settings_tabs.addTab(tab_pixel, "Пиксельный" if AppContext.is_ru() else "Pixel")
        
        # ==========================================
        # TAB 2: SIFT MATCHING
        # ==========================================
        tab_sift = QWidget()
        tab_sift_layout = QVBoxLayout(tab_sift)
        
        cache_layout = QHBoxLayout()
        self.chk_use_cache = QCheckBox("Использовать кэш" if AppContext.is_ru() else "Use Cache")
        self.chk_use_cache.setChecked(True)
        self.chk_use_cache.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_use_cache.setStyleSheet(\"\"\"
            QCheckBox { color: white; font-weight: bold; font-size: 13px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 3px; border: 1px solid #555; background: #111; }
            QCheckBox::indicator:checked { background-color: #3b82f6; border-color: #3b82f6; }
        \"\"\")
        cache_layout.addWidget(self.chk_use_cache)
        cache_layout.addStretch()
        
        self.lbl_cache_info_fragment = QLabel("0 B")
        self.lbl_cache_info_fragment.setStyleSheet("color: #888; font-size: 12px; margin-right: 5px;")
        cache_layout.addWidget(self.lbl_cache_info_fragment)
        
        from .ui_panels import load_svg_icon
        self.btn_clear_cache_fragment = QPushButton()
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
        self.btn_clear_cache_fragment.setIcon(load_svg_icon(os.path.join(icons_dir, "trash-color.svg"), QSize(16, 16)))
        self.btn_clear_cache_fragment.setIconSize(QSize(16, 16))
        self.btn_clear_cache_fragment.setToolTip("Очистить кэш" if AppContext.is_ru() else "Clear Cache")
        self.btn_clear_cache_fragment.setFixedSize(32, 32)
        self.btn_clear_cache_fragment.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_cache_fragment.setStyleSheet(\"\"\"
            QPushButton { background-color: #2b2b2b; border: 1px solid #444; border-radius: 16px; padding: 0px; }
            QPushButton:hover { background-color: #444; border-color: #666; }
        \"\"\")
        self.btn_clear_cache_fragment.clicked.connect(self.clear_orb_cache)
        cache_layout.addWidget(self.btn_clear_cache_fragment)
        tab_sift_layout.addLayout(cache_layout)
        
        # SIFT Similarity
        lbl_sim = QLabel("Схожесть (Векторы):" if AppContext.is_ru() else "Similarity (Vectors):")
        lbl_sim.setStyleSheet("color: #eee; font-weight: bold; font-size: 12px; margin-top: 5px;")
        tab_sift_layout.addWidget(lbl_sim)
        
        sim_layout = QHBoxLayout()
        self.slider_tolerance = QSlider(Qt.Orientation.Horizontal)
        self.slider_tolerance.setRange(0, 100)
        self.slider_tolerance.setValue(50)
        self.slider_tolerance.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider_tolerance.setStyleSheet(slider_style)
        
        self.lbl_tolerance_val = QLabel("50%")
        self.lbl_tolerance_val.setFixedWidth(40)
        self.lbl_tolerance_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_tolerance_val.setStyleSheet("color: #3b82f6; font-weight: bold;")
        self.slider_tolerance.valueChanged.connect(lambda v: self.lbl_tolerance_val.setText(f"{v}%"))
        
        sim_layout.addWidget(self.slider_tolerance)
        sim_layout.addWidget(self.lbl_tolerance_val)
        tab_sift_layout.addLayout(sim_layout)
        
        # SIFT Features limit
        from PyQt6.QtWidgets import QComboBox
        features_layout = QHBoxLayout()
        lbl_features = QLabel("Точек сканирования:" if AppContext.is_ru() else "Features limit:")
        lbl_features.setStyleSheet("color: #ccc; font-size: 11px;")
        features_layout.addWidget(lbl_features)
        
        self.combo_features = QComboBox()
        self.combo_features.addItems(["1000", "5000", "10000", "50000"])
        self.combo_features.setCurrentText("10000")
        self.combo_features.setStyleSheet("QComboBox { background-color: #222; color: #eee; border: 1px solid #444; border-radius: 4px; padding: 2px 5px; font-size: 11px; }")
        features_layout.addWidget(self.combo_features)
        features_layout.addStretch()
        tab_sift_layout.addLayout(features_layout)
        
        desc_sift = QLabel("Игнорирует масштаб и фильтры. Медленно." if AppContext.is_ru() else "Scale/filter invariant. Slow.")
        desc_sift.setStyleSheet("color: #888; font-size: 11px;")
        desc_sift.setWordWrap(True)
        tab_sift_layout.addWidget(desc_sift)
        
        self.settings_tabs.addTab(tab_sift, "Векторный (SIFT)" if AppContext.is_ru() else "Vector (SIFT)")
        
        col_params.addWidget(self.settings_tabs)
        
        self.btn_start = QPushButton(" Начать поиск" if AppContext.is_ru() else " Start Scan")
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icons")
        self.btn_start.setIcon(QIcon(os.path.join(icons_dir, "play.svg")))
        self.btn_start.setFixedHeight(36)
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.setStyleSheet("QPushButton { background-color: #15803d; color: white; font-weight: 900; font-size: 14px; border: 1px solid #16a34a; border-radius: 6px; } QPushButton:hover { background-color: #16a34a; }")
        self.btn_start.clicked.connect(self.start_scan)
        
        col_params.addWidget(self.btn_start)
        
        top_layout.addLayout(col_params, 1)
        """

    content = content[:start_idx] + new_block + content[end_idx:]
    
    with open(frag_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
rewrite_ui()
print("Updated UI layout to QTabWidget")
