import os

file_path = 'src/modules/cleaner/ui_ai_tab.py'
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Extract post_filter_widget creation block
start_idx = -1
end_idx = -1
for i, line in enumerate(lines):
    if line.strip() == 'post_filter_layout = QHBoxLayout()':
        start_idx = i
    if line.strip() == 'self.post_filter_widget.hide() # Hidden until scan is done' and start_idx != -1:
        end_idx = i + 1
        break

extracted = lines[start_idx:end_idx]
del lines[start_idx:end_idx]

# Find where to insert
insert_idx = -1
for i, line in enumerate(lines):
    if line.strip() == 'self.action_bar.layout().insertWidget(0, self.post_filter_widget)':
        insert_idx = i
        break

# Insert the extracted block
lines = lines[:insert_idx] + extracted + lines[insert_idx:]

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Applied')
