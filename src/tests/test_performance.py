import os
import sys
import time
import logging
import sqlite3
from typing import Any

# Добавляем родительский каталог в sys.path для импорта модулей проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication, QTreeView
from modules.cleaner.db_session import SessionDB
from modules.cleaner.ui_model import DuplicateVirtualModel, DuplicateDelegate
from modules.cleaner.ui_main import CleanerListView

def run_performance_test() -> None:
    # Инициализируем QApplication для поддержки Qt компонентов
    app = QApplication(sys.argv)
    
    test_dir = os.path.dirname(os.path.abspath(__file__))
    session_db = SessionDB(os.path.dirname(test_dir))
    session_db.clear_db()
    
    print("=== ЗАПУСК СРАВНИТЕЛЬНОГО ТЕСТА ПРОИЗВОДИТЕЛЬНОСТИ GUI (50 000 ГРУПП) ===")
    
    # 1. Генерируем 50 000 синтетических групп (по 3 файла в каждой = 150 000 файлов)
    print("Генерация синтетических данных...")
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
        
    # 2. Пакетная вставка
    session_db.add_groups(groups_list)
    flat_items = session_db.fetch_all_flat_items()
    
    source_folders = {
        "C:\\FakeSource": {"protected": False, "reference": False, "color": "#3b82f6"}
    }
    
    # --- ТЕСТ QLISTVIEW (НАШ НОВЫЙ ВАРИАНТ) ---
    print("\n[ТЕСТ 1] Инициализация QListView (свернутые группы, 50 000 строк):")
    virtual_model_list = DuplicateVirtualModel()
    list_view = CleanerListView()
    delegate_list = DuplicateDelegate()
    list_view.setModel(virtual_model_list)
    list_view.setItemDelegate(delegate_list)
    list_view.setUniformItemSizes(True)
    list_view.resize(800, 600)
    
    start_time = time.time()
    virtual_model_list.beginResetModel()
    virtual_model_list.source_folders = source_folders
    virtual_model_list._all_items = flat_items
    virtual_model_list._group_files_cache = {}
    
    for item in flat_items:
        if item['type'] == 'file':
            item['is_protected'] = False
            item['is_reference'] = False
            item['color'] = "#3b82f6"
            g_id = item['group_id']
            if g_id not in virtual_model_list._group_files_cache:
                virtual_model_list._group_files_cache[g_id] = []
            virtual_model_list._group_files_cache[g_id].append(item)
            
    virtual_model_list._expanded_groups = set() # Свернуты по умолчанию
    virtual_model_list.rebuild_flat_items()
    
    # Вот этот вызов сигнализирует View о необходимости рендеринга
    virtual_model_list.endResetModel()
    list_view_duration = time.time() - start_time
    print(f"-> QListView (endResetModel) выполнен за: {list_view_duration:.4f} секунд!")
    
    # --- ТЕСТ QTREEVIEW (СТАРЫЙ МЕДЛЕННЫЙ ВАРИАНТ) ---
    print("\n[ТЕСТ 2] Инициализация QTreeView (свернутые группы, 50 000 строк):")
    virtual_model_tree = DuplicateVirtualModel()
    tree_view = QTreeView()
    delegate_tree = DuplicateDelegate()
    tree_view.setModel(virtual_model_tree)
    tree_view.setItemDelegate(delegate_tree)
    tree_view.setUniformRowHeights(True)
    tree_view.setRootIsDecorated(False)
    tree_view.setHeaderHidden(True)
    tree_view.resize(800, 600)
    
    start_time = time.time()
    virtual_model_tree.beginResetModel()
    virtual_model_tree.source_folders = source_folders
    virtual_model_tree._all_items = flat_items
    virtual_model_tree._group_files_cache = {}
    
    for item in flat_items:
        if item['type'] == 'file':
            item['is_protected'] = False
            item['is_reference'] = False
            item['color'] = "#3b82f6"
            g_id = item['group_id']
            if g_id not in virtual_model_tree._group_files_cache:
                virtual_model_tree._group_files_cache[g_id] = []
            virtual_model_tree._group_files_cache[g_id].append(item)
            
    virtual_model_tree._expanded_groups = set() # Сворачиваем
    virtual_model_tree.rebuild_flat_items()
    
    # Запускаем endResetModel для дерева
    virtual_model_tree.endResetModel()
    tree_view_duration = time.time() - start_time
    print(f"-> QTreeView (endResetModel) выполнен за: {tree_view_duration:.4f} секунд!")
    
    # Сравнительный вывод
    ratio = tree_view_duration / list_view_duration if list_view_duration > 0 else 1.0
    print(f"\n=======================================================")
    print(f"Результат сравнения: QListView быстрее QTreeView в {ratio:.1f} раз!")
    print(f"=======================================================")
    
    # Очищаем за собой тестовую базу данных
    session_db.clear_db()
    try:
        os.remove(session_db.db_path)
    except:
        pass

if __name__ == "__main__":
    run_performance_test()
