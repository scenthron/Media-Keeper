
import os
import shutil
import time
import sys
import subprocess

# ==================================================================================
# НАСТРОЙКИ СБОРЩИКА (BUILDER CONFIG)
# ==================================================================================

SOURCE_DIR_NAME = 'src'
IGNORE_DIRS = {'docs', 'manuals', '__pycache__', '.git', '.idea', 'assets', 'logs', '.mediakeeper'}

def run_unit_tests(src_path):
    print(f"\n==========================================")
    print(f"   RUNNING AUTO-TESTS (unittest)          ")
    print(f"==========================================")
    
    import unittest
    # Добавляем src в пути, чтобы импорты в тестах работали
    sys.path.insert(0, src_path)
    
    test_dir = os.path.join(src_path, 'tests')
    suite = unittest.defaultTestLoader.discover(start_dir=test_dir)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    if not result.wasSuccessful():
        print(f"\n[CRITICAL ERROR] Auto-tests failed!")
        print(f"Application start aborted to prevent data loss.")
        print(f"==========================================\n")
        return False
        
    print(f"==========================================")
    print(f"   AUTO-TESTS PASSED SUCCESSFULLY (OK)    ")
    print(f"==========================================\n")
    return True

def main():
    root_dir = os.getcwd()
    src_path = os.path.join(root_dir, SOURCE_DIR_NAME)

    print(f"==========================================")
    print(f"   MEDIA KEEPER BUILDER (Recursive)      ")
    print(f"==========================================")

    if not os.path.exists(src_path):
        print(f"[ERROR] Папка '{SOURCE_DIR_NAME}' не найдена!")
        return

    stats = {'init_created': 0}

    # Рекурсивный обход для создания __init__.py
    for current_root, dirs, files in os.walk(src_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        
        # Создаем __init__.py, чтобы папки были пакетами
        if current_root != src_path:
            init_path = os.path.join(current_root, '__init__.py')
            if not os.path.exists(init_path):
                try:
                    with open(init_path, 'w') as f: pass
                    stats['init_created'] += 1
                except: pass

    print(f"\n==========================================")
    print(f"   INITs created: {stats['init_created']}")
    print(f"==========================================")

    # RUN TESTS BEFORE STARTING
    if not run_unit_tests(src_path):
        return

    # AUTO-LAUNCH
    main_script_path = os.path.join(src_path, 'main.py')
    if os.path.exists(main_script_path):
        print(f"\n🚀 Автозапуск: {main_script_path} ...\n")
        try:
            # Используем sys.executable для запуска в том же окружении
            subprocess.run([sys.executable, main_script_path])
        except Exception as e:
            print(f"[CRASH] Не удалось запустить приложение: {e}")
    else:
        print(f"[WARN] Файл {main_script_path} не найден, запуск невозможен.")

if __name__ == "__main__":
    main()
