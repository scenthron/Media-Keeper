import os

file_path = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_main.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    'from .ui_ai_tab import AiClassificationTab',
    'from .ui_ai_tab import AiClassificationTab\nfrom .ui_fragment_tab import AiFragmentTab'
)

content = content.replace(
    'self.tab_bar.addTab("Поиск похожих" if is_ru else "Find Similar")',
    'self.tab_bar.addTab("Поиск похожих" if is_ru else "Find Similar")\n        self.tab_bar.addTab("Поиск по фрагменту" if is_ru else "Fragment Search")'
)

content = content.replace(
    'self.page_ai = AiClassificationTab(self)\n        self.stacked_widget.addWidget(self.page_ai)',
    'self.page_fragment = AiFragmentTab(self)\n        self.stacked_widget.addWidget(self.page_fragment)\n        \n        self.page_ai = AiClassificationTab(self)\n        self.stacked_widget.addWidget(self.page_ai)'
)

content = content.replace(
    'if self.current_tab == 2:',
    'if self.current_tab == 3:'
)

content = content.replace(
    'self.source_folders_ai: dict[str, dict[str, Any]] = {}',
    'self.source_folders_ai: dict[str, dict[str, Any]] = {}\n        self.source_folders_fragment: dict[str, dict[str, Any]] = {}'
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Patched successfully.")
