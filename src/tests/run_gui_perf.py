import os
import sys
import time
import sqlite3
import subprocess

# Добавляем родительский каталог в sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.cleaner.db_session import SessionDB

def setup_synthetic_db() -> None:
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    session_db = SessionDB(root_dir)
    session_db.clear_db()
    
    print("Генерация 50 000 групп в реальной сессионной БД...")
    groups_list = []
    for i in range(1, 50001):
        grp_hash = f"hash_value_{i:06d}"
        files = [
            {'real_path': f"C:\\FakeSource\\folder_{i % 5}\\file_{i:06d}_copy_1.mp4"},
            {'real_path': f"C:\\FakeSource\\folder_{i % 5}\\file_{i:06d}_copy_2.mp4"},
            {'real_path': f"C:\\FakeSource\\folder_{i % 5}\\file_{i:06d}_copy_3.mp4"},
        ]
        groups_list.append({
            'hash': grp_hash,
            'size': 1024 * 1024 * 5,  # 5 MB
            'files': files
        })
        
    session_db.add_groups(groups_list)
    print("База данных успешно подготовлена!")

if __name__ == "__main__":
    setup_synthetic_db()
    
    # Запускаем приложение main.py
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    main_py = os.path.join(root_dir, "main.py")
    
    print("Запуск приложения Media Keeper (пожалуйста, переключитесь на вкладку Cleaner)...")
    print("Через 12 секунд приложение будет автоматически закрыто для анализа логов.")
    
    # Запускаем в фоновом режиме
    proc = subprocess.Popen([sys.executable, main_py], cwd=root_dir)
    
    # Ждем 12 секунд
    time.sleep(12)
    
    # Закрываем приложение
    proc.terminate()
    proc.wait()
    print("Приложение успешно закрыто. Теперь можно анализировать media_keeper.log!")
