import sys

with open('src/modules/cleaner/ui_ai_tab.py', 'r', encoding='utf-8') as f:
    code = f.read()

old_block = '''                  except Exception as e:
                      import logging
                      logging.error(f"Ошибка получения лиц для предпросмотра: {e}")
                      
                  self.file_selected.emit(path)'''

new_block = '''                  except Exception as e:
                      import logging
                      logging.error(f"Ошибка получения лиц для предпросмотра: {e}")
                      
                  self.file_selected.emit(path)
          else:
              from .ui_translations import AppContext
              msg = "Файл не выбран" if AppContext.is_ru() else "No file selected"
              self.preview_widget.show_empty(msg)'''

code = code.replace(old_block, new_block)

with open('src/modules/cleaner/ui_ai_tab.py', 'w', encoding='utf-8') as f:
    f.write(code)
    
print("Replaced!")
