import sys

path = 'src/modules/cleaner/ui_ai_tab.py'
with open(path, 'r', encoding='utf-8') as f:
    code = f.read()

target = '                  self.file_selected.emit(path)'

if target in code:
    parts = code.split(target)
    new_code = parts[0] + target + '''
          else:
              from .ui_translations import AppContext
              msg = "Файл не выбран" if AppContext.is_ru() else "No file selected"
              self.preview_widget.show_empty(msg)''' + parts[1]
              
    open(path, 'w', encoding='utf-8').write(new_code)
    print('Patched successfully!')
else:
    print('Target not found!')
