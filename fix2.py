import os

file_path = 'src/modules/cleaner/ui_ai_tab.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. We need to remove the old post_filter_widget from tree_layout
old_tree_layout = '''        self.post_filter_widget = QWidget()
        self.post_filter_widget.setLayout(post_filter_layout)
        self.post_filter_widget.hide() # Hidden until scan is done
        
        tree_layout.addWidget(self.post_filter_widget)
        tree_layout.addWidget(self.tree_results)'''

new_tree_layout = '''        self.post_filter_widget = QWidget()
        self.post_filter_widget.setLayout(post_filter_layout)
        self.post_filter_widget.hide() # Hidden until scan is done
        
        tree_layout.addWidget(self.tree_results)'''
content = content.replace(old_tree_layout, new_tree_layout)

# 2. Add it to action_bar
old_action = '''        self.action_bar = CleanerActionBar()
        self.action_bar.is_similar_mode = False
        self.action_bar.combo_autoselect.hide()
        self.action_bar.btn_select_all.hide()
        self.action_bar.btn_deselect.hide()'''

new_action = '''        self.action_bar = CleanerActionBar()
        self.action_bar.is_similar_mode = False
        self.action_bar.combo_autoselect.hide()
        self.action_bar.btn_select_all.hide()
        self.action_bar.btn_deselect.hide()
        self.action_bar.layout().insertWidget(0, self.post_filter_widget)'''
content = content.replace(old_action, new_action)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Applied')
