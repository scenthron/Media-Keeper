import sys

path = 'src/modules/cleaner/workers.py'
with open(path, 'r', encoding='utf-8') as f:
    code = f.read()

old_code = '''        if getattr(self, "is_cluster", False):
            import numpy as np'''

new_code = '''        if getattr(self, "is_cluster", False):
            try:
                from ui_translations import AppContext
                is_ru = AppContext.is_ru()
            except:
                is_ru = True
            msg = "Формирование групп результатов..." if is_ru else "Forming result groups..."
            self.progress.emit(STAGE_ANALYSIS, 100.0, msg, scanned_files, groups_found, wasted_bytes, scanned_bytes, files_found, 0)
            import numpy as np'''

if old_code in code:
    code = code.replace(old_code, new_code)
    open(path, 'w', encoding='utf-8').write(code)
    print('Replaced in workers.py')
else:
    print('Not found in workers.py')
