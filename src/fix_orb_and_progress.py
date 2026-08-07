import os

def fix_all():
    # 1. Update max_features in logic_orb.py
    orb_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\logic_orb.py'
    with open(orb_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Change max_features from 2000 to 50000 to guarantee finding small fragment features in large images
    content = content.replace(
        "def __init__(self, max_features=2000):",
        "def __init__(self, max_features=50000):"
    )

    with open(orb_path, 'w', encoding='utf-8') as f:
        f.write(content)

    # 2. Add progress bar to ui_fragment_tab.py
    frag_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_fragment_tab.py'
    with open(frag_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find header_widget layout and insert progress bar
    old_header = """        self.lbl_stats = QLabel("Найдено файлов: 0")
        self.lbl_stats.setStyleSheet("color: #aaa; font-size: 12px; font-weight: bold;")
        header_layout.addWidget(self.lbl_stats)
        header_layout.addStretch()
        bottom_layout.addWidget(header_widget)"""

    new_header = """        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setStyleSheet(\"\"\"
            QProgressBar { border: none; background-color: #151515; text-align: center; color: white; font-size: 10px; border-radius: 7px; }
            QProgressBar::chunk { background-color: #3b82f6; border-radius: 7px; }
        \"\"\")
        self.progress_bar.hide()
        
        self.lbl_stats = QLabel("Найдено файлов: 0")
        self.lbl_stats.setStyleSheet("color: #aaa; font-size: 12px; font-weight: bold;")
        
        header_layout.addWidget(self.lbl_stats)
        header_layout.addWidget(self.progress_bar)
        header_layout.addStretch()
        bottom_layout.addWidget(header_widget)"""

    content = content.replace(old_header, new_header)

    # Update on_progress to use progress bar
    old_progress = """    def _on_progress(self, current, total, msg):
        self.lbl_stats.setText(f"Сканирование: {current}/{total} | {msg}")"""

    new_progress = """    def _on_progress(self, current, total, msg):
        if not self.progress_bar.isVisible():
            self.progress_bar.show()
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
            self.progress_bar.setFormat(f"{int(current/total*100)}%")
        self.lbl_stats.setText(f"Сканирование: {current}/{total} | {msg}")"""

    content = content.replace(old_progress, new_progress)

    # Update scan_finished to hide progress bar
    old_finished = """    def _on_scan_finished(self, success, results):
        self.active_worker = None"""

    new_finished = """    def _on_scan_finished(self, success, results):
        self.progress_bar.hide()
        self.active_worker = None"""

    content = content.replace(old_finished, new_finished)

    with open(frag_path, 'w', encoding='utf-8') as f:
        f.write(content)

    # Clear cache again because features changed
    cache_dir = os.path.join(os.getenv('APPDATA'), "MediaKeeper", "cache", "orb")
    if os.path.exists(cache_dir):
        for f in os.listdir(cache_dir):
            try:
                os.remove(os.path.join(cache_dir, f))
            except:
                pass

fix_all()
print("Fixed ORB max features and added progress bar")
