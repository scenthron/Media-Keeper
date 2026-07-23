import sys

path = 'src/modules/cleaner/ui_ai_tab.py'
with open(path, 'r', encoding='utf-8') as f:
    code = f.read()

old_code = 'self.lbl_progress.setText("Формирование таблицы..." if AppContext.is_ru() else "Building table...")'
new_code = 'self.progress_bar.setFormat("Формирование таблицы... (100%)" if AppContext.is_ru() else "Building table... (100%)")'

if old_code in code:
    code = code.replace(old_code, new_code)
    open(path, 'w', encoding='utf-8').write(code)
    print('Replaced in ui_ai_tab.py')
else:
    print('Not found in ui_ai_tab.py')
