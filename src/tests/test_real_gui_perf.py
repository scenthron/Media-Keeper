import os
import sys
import time
import logging
from typing import Any

# Добавляем родительский каталог в sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QCoreApplication
from main import MediaKeeperShell
from modules.cleaner.db_session import SessionDB

def run_real_gui_perf() -> None:
    # 1. Инициализируем логгер в консоль
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] - %(message)s')
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    

    
    print("\n[GUI LAUNCH] Создание главного окна MediaKeeperShell...")
    window = MediaKeeperShell()
    
    # Получаем доступ к модулю cleaner
    cleaner_module = window.cleaner_tab
    session_db = cleaner_module.session_db
    
    print("\n[PREPARATION] Генерация 10 000 групп дубликатов в БД...")
    groups_list = []
    for i in range(1, 10001):
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
    print("[PREPARATION] База данных успешно подготовлена.")
    
    # Задаем source_folders для корректного Enrich
    cleaner_module.source_folders = {
        "C:\\FakeSource\\folder_0": {"protected": False, "reference": False, "color": "#ff0000"},
        "C:\\FakeSource\\folder_1": {"protected": True, "reference": False, "color": "#00ff00"},
        "C:\\FakeSource\\folder_2": {"protected": False, "reference": True, "color": "#0000ff"},
        "C:\\FakeSource\\folder_3": {"protected": False, "reference": False, "color": "#ffff00"},
        "C:\\FakeSource\\folder_4": {"protected": False, "reference": False, "color": "#ff00ff"},
    }
    
    # Даем Qt обработать начальные события запуска
    QCoreApplication.processEvents()
    
    print("\n[SWITCH TAB] Переключение на вкладку Cleaner (вкладка 2)...")
    t_switch = time.perf_counter()
    window.switch_tab(2)
    
    print("[LOAD] Принудительный вызов refresh_tree_view для загрузки 10 000 групп в модель...")
    t_load_start = time.perf_counter()
    cleaner_module.refresh_tree_view()
    
    # Ожидаем завершения фонового DBLoadWorker
    print("Ожидание завершения фонового потока чтения и подготовки модели...")
    while hasattr(cleaner_module, 'db_load_worker') and cleaner_module.db_load_worker.isRunning():
        QCoreApplication.processEvents()
        time.sleep(0.02)
        
    # Ожидаем завершения фоновой догрузки по таймеру, если она активна
    if hasattr(cleaner_module, 'incremental_loader_timer') and cleaner_module.incremental_loader_timer.isActive():
        print("Ожидание завершения фоновой инкрементной отрисовки...")
        while cleaner_module.incremental_loader_timer.isActive():
            QCoreApplication.processEvents()
            time.sleep(0.02)
            
    load_duration = time.perf_counter() - t_load_start
    print(f"[PERF] Загрузка и рендеринг в GUI выполнены за: {load_duration:.4f} секунд!")
    
    # Даем Qt обработать финальные события отрисовки
    for _ in range(5):
        QCoreApplication.processEvents()
        time.sleep(0.02)
        
    switch_duration = time.perf_counter() - t_switch
    print(f"\n[SUCCESS] Общее время переключения, чтения и отрисовки: {switch_duration:.4f} секунд!")
    
    # Очищаем за собой
    session_db.clear_db()
    try:
        os.remove(session_db.db_path)
    except:
        pass
    
    print("\nТест успешно завершен!")
    app.quit()
    sys.exit(0)

if __name__ == "__main__":
    run_real_gui_perf()
