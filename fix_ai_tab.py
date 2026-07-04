import os
import re

file_path = 'src/modules/cleaner/ui_ai_tab.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Rename Умная авто-кластеризация -> Умный поиск по людям (Авто-группировка)
content = content.replace('Умная авто-кластеризация', 'Умный поиск по людям')

# 2. Fix checkboxes
chk_gpu_old = 'self.chk_use_gpu.setStyleSheet("color: white; font-size: 11px;")'
chk_gpu_new = '''self.chk_use_gpu.setStyleSheet("""
            QCheckBox { color: white; font-weight: bold; font-size: 11px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 3px; border: 1px solid #555; background: #111; }
            QCheckBox::indicator:checked { background-color: #3b82f6; border-color: #3b82f6; }
        """)'''
content = content.replace(chk_gpu_old, chk_gpu_new)

chk_auto_old = 'self.chk_auto_cluster.setStyleSheet("color: white; font-size: 11px; margin-top: 5px;")'
chk_auto_new = '''self.chk_auto_cluster.setStyleSheet("""
            QCheckBox { color: white; font-weight: bold; font-size: 11px; margin-top: 5px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 3px; border: 1px solid #555; background: #111; margin-top: 5px; }
            QCheckBox::indicator:checked { background-color: #3b82f6; border-color: #3b82f6; }
        """)'''
content = content.replace(chk_auto_old, chk_auto_new)

# 3. Fix populate_results default slider value
default_val_old = 'default_val = float(max(2, min_size))'
default_val_new = '''default_val = 2.0
            if max_size < 2:
                default_val = float(max_size)'''
content = content.replace(default_val_old, default_val_new)

# 4. Move slider to action_bar
# The widget post_filter_widget was added to bot_layout
old_post_filter = '''        bot_layout.addWidget(self.post_filter_widget)
        self.post_filter_widget.hide()
        
        from .ui_panels import CleanerActionBar
        self.action_bar = CleanerActionBar()'''

new_post_filter = '''        from .ui_panels import CleanerActionBar
        self.action_bar = CleanerActionBar()
        
        # Insert post_filter_widget into action_bar layout (index 0)
        self.action_bar.layout().insertWidget(0, self.post_filter_widget)
        self.post_filter_widget.hide()'''

content = content.replace(old_post_filter, new_post_filter)

# Hide buttons
hide_combo_old = 'self.action_bar.combo_autoselect.hide()'
hide_combo_new = '''self.action_bar.combo_autoselect.hide()
        self.action_bar.btn_select_all.hide()
        self.action_bar.btn_deselect.hide()'''
content = content.replace(hide_combo_old, hide_combo_new)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Changes applied!")
