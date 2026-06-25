import unittest
import sqlite3
import os
import sys

# Добавляем путь к src, чтобы импортировать модули напрямую
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.cleaner.db_session import SessionDB

class TestIronRule(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        # Создаем экземпляр SessionDB во временной директории, чтобы не засорять корень проекта
        self.session_db = SessionDB(tempfile.gettempdir())
        self.session_db.db_path = os.path.join(tempfile.gettempdir(), "test_session_cleaner.db")
        if os.path.exists(self.session_db.db_path):
            try: os.remove(self.session_db.db_path)
            except: pass
            
        # Инициализируем таблицы и триггеры
        self.conn = sqlite3.connect(self.session_db.db_path)
        self.cursor = self.conn.cursor()
        self.cursor.execute('CREATE TABLE groups (id INTEGER PRIMARY KEY AUTOINCREMENT, hash TEXT, size INTEGER, file_count INTEGER, wasted_size INTEGER, extension TEXT)')
        self.cursor.execute('CREATE TABLE files (id INTEGER PRIMARY KEY AUTOINCREMENT, group_id INTEGER, path TEXT, is_deleted INTEGER DEFAULT 0, is_marked INTEGER DEFAULT 0, FOREIGN KEY(group_id) REFERENCES groups(id))')
        self.cursor.execute('CREATE TABLE zero_files (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT, extension TEXT, is_deleted INTEGER DEFAULT 0, is_marked INTEGER DEFAULT 0)')
        self.cursor.execute('CREATE TABLE empty_folders (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT, is_deleted INTEGER DEFAULT 0, is_marked INTEGER DEFAULT 0)')
        
        # Создаем триггер
        self.cursor.execute("DROP TRIGGER IF EXISTS enforce_survivor_rule")
        self.cursor.execute("""
        CREATE TRIGGER enforce_survivor_rule
        AFTER UPDATE OF is_marked ON files
        WHEN (
            SELECT COUNT(*) FROM files
            WHERE group_id = NEW.group_id AND is_deleted = 0
        ) = (
            SELECT SUM(is_marked) FROM files
            WHERE group_id = NEW.group_id AND is_deleted = 0
        )
        BEGIN
            UPDATE files SET is_marked = 0
            WHERE id = (
                SELECT id FROM files
                WHERE group_id = NEW.group_id AND is_deleted = 0
                ORDER BY path ASC
                LIMIT 1
            );
        END;
        """)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()
        if os.path.exists(self.session_db.db_path):
            try: os.remove(self.session_db.db_path)
            except: pass

    def _insert_fake_group(self, group_id: int, size: int, files_list: list[dict]) -> None:
        # Вставляем группу
        self.cursor.execute(
            "INSERT INTO groups (id, hash, size, file_count, wasted_size, extension) VALUES (?, ?, ?, ?, ?, ?)",
            (group_id, f"hash_{group_id}", size, len(files_list), size * (len(files_list) - 1), ".jpg")
        )
        # Вставляем файлы
        for f in files_list:
            self.cursor.execute(
                "INSERT INTO files (group_id, path, is_marked, is_deleted) VALUES (?, ?, ?, ?)",
                (group_id, f['path'], f.get('is_marked', 0), f.get('is_deleted', 0))
            )
        self.conn.commit()

    def test_single_selection_allowed(self) -> None:
        """Проверяет, что выделение одного файла из двух в группе разрешено."""
        files = [
            {'path': 'C:/folder/file1.jpg', 'is_marked': 0},
            {'path': 'C:/folder/file2.jpg', 'is_marked': 0}
        ]
        self._insert_fake_group(1, 1000, files)
        
        # Имитируем ручной клик (выделение первого файла)
        self.cursor.execute("UPDATE files SET is_marked = 1 WHERE path = 'C:/folder/file1.jpg'")
        self.session_db.enforce_group_survivor_rule(self.cursor, self.conn)
        self.conn.commit()
        
        # Проверяем, что первый файл выделился, а второй остался чистым
        self.cursor.execute("SELECT path, is_marked FROM files WHERE group_id = 1")
        rows = dict(self.cursor.fetchall())
        self.assertEqual(rows['C:/folder/file1.jpg'], 1)
        self.assertEqual(rows['C:/folder/file2.jpg'], 0)

    def test_iron_rule_blocks_all_selected(self) -> None:
        """IRON RULE: проверяет, что при попытке выделить все файлы, первый автоматически сбрасывается в 0."""
        files = [
            {'path': 'C:/folder/file1.jpg', 'is_marked': 1},
            {'path': 'C:/folder/file2.jpg', 'is_marked': 0}
        ]
        self._insert_fake_group(1, 1000, files)
        
        # Имитируем ручной клик по последнему невыделенному файлу (выделяем второй)
        self.cursor.execute("UPDATE files SET is_marked = 1 WHERE path = 'C:/folder/file2.jpg'")
        self.session_db.enforce_group_survivor_rule(self.cursor, self.conn)
        self.conn.commit()
        
        # Проверяем, что сработала автозащита и сбросила первый по алфавиту файл
        self.cursor.execute("SELECT path, is_marked FROM files WHERE group_id = 1 ORDER BY path ASC")
        rows = self.cursor.fetchall()
        
        # Первый по алфавиту файл должен был сброситься в 0!
        self.assertEqual(rows[0][0], 'C:/folder/file1.jpg')
        self.assertEqual(rows[0][1], 0)  # Сброшен защитой!
        
        # Второй файл должен остаться выделенным
        self.assertEqual(rows[1][0], 'C:/folder/file2.jpg')
        self.assertEqual(rows[1][1], 1)

    def test_iron_rule_with_deleted_files(self) -> None:
        """Проверяет, что удаленные файлы не учитываются как выжившие."""
        files = [
            {'path': 'C:/folder/file1.jpg', 'is_marked': 1, 'is_deleted': 1}, # Уже удален
            {'path': 'C:/folder/file2.jpg', 'is_marked': 1},
            {'path': 'C:/folder/file3.jpg', 'is_marked': 0}
        ]
        self._insert_fake_group(1, 1000, files)
        
        # Выделяем последний активный файл
        self.cursor.execute("UPDATE files SET is_marked = 1 WHERE path = 'C:/folder/file3.jpg'")
        self.session_db.enforce_group_survivor_rule(self.cursor, self.conn)
        self.conn.commit()
        
        # Из активных файлов (file2 и file3) один должен быть сброшен в 0
        self.cursor.execute("SELECT path, is_marked FROM files WHERE group_id = 1 AND is_deleted = 0 ORDER BY path ASC")
        active_rows = self.cursor.fetchall()
        
        # Первый активный (file2) сброшен в 0
        self.assertEqual(active_rows[0][0], 'C:/folder/file2.jpg')
        self.assertEqual(active_rows[0][1], 0)
        
        # Второй активный (file3) остался 1
        self.assertEqual(active_rows[1][0], 'C:/folder/file3.jpg')
        self.assertEqual(active_rows[1][1], 1)

    def test_sqlite_trigger_enforces_rule_directly(self) -> None:
        """Проверяет, что триггер SQLite перехватывает прямые SQL-запросы UPDATE и сбрасывает первый по алфавиту файл."""
        files = [
            {'path': 'C:/folder/file1.jpg', 'is_marked': 0},
            {'path': 'C:/folder/file2.jpg', 'is_marked': 0},
            {'path': 'C:/folder/file3.jpg', 'is_marked': 0}
        ]
        self._insert_fake_group(1, 1000, files)
        
        # Пытаемся выделить абсолютно все файлы в группе прямым UPDATE-запросом к СУБД (в обход Python-кода)
        self.cursor.execute("UPDATE files SET is_marked = 1 WHERE group_id = 1")
        self.conn.commit()
        
        # Проверяем, что сработал триггер SQLite и сбросил первый по алфавиту файл в 0!
        self.cursor.execute("SELECT path, is_marked FROM files WHERE group_id = 1 ORDER BY path ASC")
        rows = self.cursor.fetchall()
        
        # Первый по алфавиту файл ('C:/folder/file1.jpg') должен быть сброшен в 0
        self.assertEqual(rows[0][0], 'C:/folder/file1.jpg')
        self.assertEqual(rows[0][1], 0)
        
        # Остальные два файла ('C:/folder/file2.jpg' и 'C:/folder/file3.jpg') должны остаться выделенными (1)
        self.assertEqual(rows[1][0], 'C:/folder/file2.jpg')
        self.assertEqual(rows[1][1], 1)
        self.assertEqual(rows[2][0], 'C:/folder/file3.jpg')
        self.assertEqual(rows[2][1], 1)

    def test_iterative_selection_keeps_previous_marks(self) -> None:
        """Проверяет, что итеративный пакетный выбор сохраняет ручные выделения и оставляет 1 выжившего."""
        files = [
            {'path': 'C:/folder/file1.jpg', 'is_marked': 0},
            {'path': 'C:/folder/file2.jpg', 'is_marked': 0},
            {'path': 'C:/folder/file3.jpg', 'is_marked': 0},
            {'path': 'C:/folder/file4.jpg', 'is_marked': 0}
        ]
        self._insert_fake_group(1, 1000, files)
        
        # Шаг 1: Пользователь выделил первый файл вручную
        self.session_db.set_files_marked_state_safe(['C:/folder/file1.jpg'], 1)
        
        # Шаг 2: Применяется пакетное выделение на оставшиеся три файла (F2, F3, F4)
        # Шлюз должен поочередно выделить F2 и F3, но на F4 остановиться, так как останется ровно 1 выживший.
        self.session_db.set_files_marked_state_safe(['C:/folder/file2.jpg', 'C:/folder/file3.jpg', 'C:/folder/file4.jpg'], 1)
        
        # Проверяем результат в БД
        self.cursor.execute("SELECT path, is_marked FROM files WHERE group_id = 1 ORDER BY path ASC")
        rows = self.cursor.fetchall()
        
        # F1 остался выделенным (1), F2 и F3 выделились (1), а F4 остался единственным живым выжившим (0)
        self.assertEqual(rows[0][0], 'C:/folder/file1.jpg')
        self.assertEqual(rows[0][1], 1)
        
        self.assertEqual(rows[1][0], 'C:/folder/file2.jpg')
        self.assertEqual(rows[1][1], 1)
        
        self.assertEqual(rows[2][0], 'C:/folder/file3.jpg')
        self.assertEqual(rows[2][1], 1)
        
        self.assertEqual(rows[3][0], 'C:/folder/file4.jpg')
        self.assertEqual(rows[3][1], 0)

    def test_cumulative_selection_ignores_locked_groups(self) -> None:
        """Проверяет, что зафиксированная группа (с 1 невыделенным файлом) полностью игнорируется автоматическим автовыбором."""
        files = [
            {'path': 'C:/folder/file1.jpg', 'is_marked': 1},
            {'path': 'C:/folder/file2.jpg', 'is_marked': 1},
            {'path': 'C:/folder/file3.jpg', 'is_marked': 0} # 1 выживший, группа зафиксирована!
        ]
        self._insert_fake_group(1, 1000, files)
        
        # Применяем глобальный автовыбор (например, keep_first, который в обычной ситуации выделил бы F2 и F3, а F1 оставил 0)
        self.session_db.apply_global_autoselect('keep_first', {})
        
        # Проверяем, что зафиксированная группа проигнорировала автовыбор
        self.cursor.execute("SELECT path, is_marked FROM files WHERE group_id = 1 ORDER BY path ASC")
        rows = self.cursor.fetchall()
        
        # Выделение осталось прежним! F1=1, F2=1, F3=0
        self.assertEqual(rows[0][0], 'C:/folder/file1.jpg')
        self.assertEqual(rows[0][1], 1)
        
        self.assertEqual(rows[1][0], 'C:/folder/file2.jpg')
        self.assertEqual(rows[1][1], 1)
        
        self.assertEqual(rows[2][0], 'C:/folder/file3.jpg')
        self.assertEqual(rows[2][1], 0)

if __name__ == '__main__':
    unittest.main()
