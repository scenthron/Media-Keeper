import os

def fix_log_spam():
    # 1. Remove spam from logic_automation.py
    target1 = r'c:\Users\Centhron\Desktop\Media_Keeper\src\modules\sorter\logic_automation.py'
    if os.path.exists(target1):
        with open(target1, 'r', encoding='utf-8') as f:
            content1 = f.read()
            
        bad_log = 'logging.debug(f"Файл конфигурации автоматизации не найден в {target_path}")'
        if bad_log in content1:
            content1 = content1.replace(bad_log, 'pass')
            with open(target1, 'w', encoding='utf-8') as f:
                f.write(content1)
            print("Fixed log spam in logic_automation.py.")
            
    # 2. Disable rotation in logic_logger.py to avoid WinError 32
    target2 = r'c:\Users\Centhron\Desktop\Media_Keeper\src\logic_logger.py'
    if os.path.exists(target2):
        with open(target2, 'r', encoding='utf-8') as f:
            content2 = f.read()
            
        if "maxBytes=5 * 1024 * 1024" in content2:
            content2 = content2.replace("maxBytes=5 * 1024 * 1024", "maxBytes=0")
            content2 = content2.replace("backupCount=5", "backupCount=0")
            with open(target2, 'w', encoding='utf-8') as f:
                f.write(content2)
            print("Disabled file rotation in logic_logger.py.")

fix_log_spam()
