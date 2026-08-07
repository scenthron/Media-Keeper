import os
import re

def fix_crop_dialog():
    crop_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_crop_dialog.py'
    with open(crop_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Add anchors for zooming at mouse cursor
    if "AnchorUnderMouse" not in content:
        content = content.replace(
            "self.view.setDragMode(QGraphicsView.DragMode.NoDrag)",
            "self.view.setDragMode(QGraphicsView.DragMode.NoDrag)\n        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)\n        self.view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)"
        )
        with open(crop_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print("Fixed zooming in ui_crop_dialog.py")

def fix_fragment_progress():
    frag_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(frag_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # We need to completely replace the layout between "bottom_widget = QWidget()" and "self.main_splitter.addWidget(self.top_settings)"
    # Actually, the structure in the file is currently:
    #         self.main_splitter.addWidget(self.top_settings)
    #         
    #         # BOTTOM: RESULTS & PREVIEW
    #         bottom_widget = QWidget()
    #         bottom_layout = QVBoxLayout(bottom_widget)
    #         bottom_layout.setContentsMargins(0, 0, 0, 0)
    #         ...
    #         self.main_splitter.addWidget(bottom_widget)
    
    # We will just rewrite the bottom section directly.
    import re
    pattern = re.compile(r'# BOTTOM: RESULTS & PREVIEW.*?(?=def check_models_status|def _on_progress|def init_ui|def start_scan)', re.DOTALL)
    
    # Let's just find the section by string manipulation
    start_str = "# BOTTOM: RESULTS & PREVIEW"
    end_str = "self.main_splitter.addWidget(bottom_widget)"
    
    if start_str in content and end_str in content:
        start_idx = content.find(start_str)
        end_idx = content.find(end_str) + len(end_str)
        
        new_bottom = """# BOTTOM: RESULTS & PREVIEW
        bottom_widget = QWidget()
        bot_layout = QVBoxLayout(bottom_widget)
        bot_layout.setContentsMargins(0, 0, 0, 0)
        bot_layout.setSpacing(0)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setStyleSheet(\"\"\"
            QProgressBar { border: none; background-color: #151515; text-align: center; color: white; font-size: 11px; }
            QProgressBar::chunk { background-color: #3b82f6; }
        \"\"\")
        self.progress_bar.hide()
        bot_layout.addWidget(self.progress_bar)
        
        self.lbl_stats = QLabel("")
        self.lbl_stats.setStyleSheet("color: #4ade80; font-weight: bold; font-size: 12px; border: none; padding: 4px 15px; background-color: #1e1e1e;")
        bot_layout.addWidget(self.lbl_stats)
        
        from .ui_panels import CleanerActionBar
        self.action_bar = CleanerActionBar()
        self.action_bar.is_similar_mode = False
        self.action_bar.combo_autoselect.hide()
        self.action_bar.btn_select_all.hide()
        self.action_bar.btn_deselect.hide()
        self.action_bar.chk_preserve.hide()
        self.action_bar.combo_collision.hide()
        
        self.action_bar.lbl_selection_info = QLabel("Выбрано: 0 файлов • 0 B")
        self.action_bar.lbl_selection_info.setStyleSheet("color: #93c5fd; font-size: 11px; font-weight: bold;")
        ab_layout = self.action_bar.layout()
        if ab_layout:
            ab_layout.insertWidget(3, self.action_bar.lbl_selection_info)
            
        bot_layout.addWidget(self.action_bar)
        
        self.right_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.right_splitter.setHandleWidth(2)
        self.right_splitter.setStyleSheet("QSplitter::handle { background-color: #2d2d2d; }")
        
        self.tree_results = QTreeWidget()
        self.tree_results.setColumnCount(4)
        self.tree_results.setHeaderLabels(["Файл", "Сходство (%)", "Размер", "Путь"])
        self.tree_results.setColumnWidth(0, 240)
        self.tree_results.setColumnWidth(1, 100)
        self.tree_results.setColumnWidth(2, 90)
        self.tree_results.setStyleSheet("QTreeWidget { background-color: #1a1a1a; border: none; outline: none; color: #eee; } QTreeWidget::item { padding: 6px; border-bottom: 1px solid #222; } QTreeWidget::item:selected { background-color: #2b2b2b; color: white; }")
        self.tree_results.itemSelectionChanged.connect(self.on_tree_selection_changed)
        
        self.right_splitter.addWidget(self.tree_results)
        
        from .ui_preview import CleanerPreviewWidget
        self.preview_widget = CleanerPreviewWidget()
        self.preview_widget.show_empty("Выберите файл для предпросмотра")
        self.right_splitter.addWidget(self.preview_widget)
        
        self.right_splitter.setSizes([650, 350])
        bot_layout.addWidget(self.right_splitter, 1)
        
        self.main_splitter.addWidget(bottom_widget)"""
        
        content = content[:start_idx] + new_bottom + content[end_idx:]
        
    # Fix progress logic
    # Find _on_progress
    prog_start = "    def _on_progress(self, current, total, text):"
    prog_end = "    def _on_scan_finished(self, success, results):"
    
    if prog_start in content and prog_end in content:
        start_idx = content.find(prog_start)
        end_idx = content.find(prog_end)
        
        new_prog = """    def _on_progress(self, current, total, text):
        if not self.progress_bar.isVisible():
            self.progress_bar.show()
            self.lbl_stats.hide()
            
        if total > 0:
            percent = (current / total) * 100
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
            self.progress_bar.setFormat(f"Сканирование: {current}/{total} файлов ({int(percent)}%) - {text}")
            
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

"""
        content = content[:start_idx] + new_prog + content[end_idx:]
        
    # Fix scan start logic
    if "self.lbl_stats.setText(\"Идет сканирование...\")" in content:
        content = content.replace("self.lbl_stats.setText(\"Идет сканирование...\")", "self.lbl_stats.hide()\n        self.progress_bar.show()\n        self.progress_bar.setFormat(\"Подготовка к сканированию...\")")

    # Fix scan finished logic
    if "self.lbl_stats.setText(f\"Поиск завершен. Найдено файлов: {len(results)}\")" in content:
        content = content.replace("self.lbl_stats.setText(f\"Поиск завершен. Найдено файлов: {len(results)}\")", "self.progress_bar.hide()\n            self.lbl_stats.show()\n            self.lbl_stats.setText(f\"Поиск завершен. Найдено файлов: {len(results)}\")")

    if "self.lbl_stats.setText(\"Поиск остановлен или произошла ошибка.\")" in content:
        content = content.replace("self.lbl_stats.setText(\"Поиск остановлен или произошла ошибка.\")", "self.progress_bar.hide()\n            self.lbl_stats.show()\n            self.lbl_stats.setText(\"Поиск остановлен или произошла ошибка.\")")

    with open(frag_path, 'w', encoding='utf-8') as f:
        f.write(content)
        print("Fixed ui_fragment_tab progress bar and text")

fix_crop_dialog()
fix_fragment_progress()
