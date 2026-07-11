import sqlite3
import os
from utils_common import is_subpath
import logging
from typing import Any

class SessionDB:
    DB_NAME: str = "session_cleaner.db"
    
    def __init__(self, root_dir: str = None) -> None:
        if root_dir is None:
            from logic_paths import get_app_data_dir
            self.db_path: str = os.path.join(get_app_data_dir(), self.DB_NAME)
        else:
            self.db_path: str = os.path.join(root_dir, ".mediakeeper", self.DB_NAME)
        # Физически удаляем старый сессионный файл при каждом запуске программы.
        # Это полностью исключает блокировки (database is locked) от зависших ранее процессов
        # и гарантирует создание чистой базы данных SQLite с нуля.
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
                logging.info("[SessionDB] Старый файл сессионной базы данных успешно удален физически.")
            except Exception as e:
                logging.error(f"[SessionDB] Не удалось физически удалить файл базы на старте: {e}. Возможно, он заблокирован зависшим процессом.")
        self.init_db()

    def init_db(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('CREATE TABLE IF NOT EXISTS groups (id INTEGER PRIMARY KEY AUTOINCREMENT, hash TEXT, size INTEGER, file_count INTEGER, wasted_size INTEGER, extension TEXT)')
            cursor.execute('CREATE TABLE IF NOT EXISTS files (id INTEGER PRIMARY KEY AUTOINCREMENT, group_id INTEGER, path TEXT, is_deleted INTEGER DEFAULT 0, is_marked INTEGER DEFAULT 0, similarity_pct INTEGER DEFAULT 100, file_size INTEGER DEFAULT 0, metadata TEXT DEFAULT \'\', FOREIGN KEY(group_id) REFERENCES groups(id))')
            cursor.execute('CREATE TABLE IF NOT EXISTS zero_files (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT, extension TEXT, is_deleted INTEGER DEFAULT 0, is_marked INTEGER DEFAULT 0)')
            cursor.execute('CREATE TABLE IF NOT EXISTS empty_folders (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT, is_deleted INTEGER DEFAULT 0, is_marked INTEGER DEFAULT 0)')
            
            # Внедряем IRON RULE на уровне базы данных через SQLite триггер (100% гарантия)
            cursor.execute("DROP TRIGGER IF EXISTS enforce_survivor_rule")
            cursor.execute("""
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
            conn.commit()
            self._run_migrations(cursor, conn)
            conn.close()
        except Exception as e: 
            logging.error(f"Session DB Init Error: {e}")

    def _run_migrations(self, cursor: sqlite3.Cursor, conn: sqlite3.Connection) -> None:
        """Safely applies schema migrations for older DB files that predate column additions."""
        migrations: list[tuple[str, str]] = [
            ("files",         "ALTER TABLE files ADD COLUMN is_marked INTEGER DEFAULT 0"),
            ("zero_files",    "ALTER TABLE zero_files ADD COLUMN is_marked INTEGER DEFAULT 0"),
            ("empty_folders", "ALTER TABLE empty_folders ADD COLUMN is_marked INTEGER DEFAULT 0"),
            ("files",         "ALTER TABLE files ADD COLUMN is_deleted INTEGER DEFAULT 0"),
            ("zero_files",    "ALTER TABLE zero_files ADD COLUMN is_deleted INTEGER DEFAULT 0"),
            ("empty_folders", "ALTER TABLE empty_folders ADD COLUMN is_deleted INTEGER DEFAULT 0"),
            ("files",         "ALTER TABLE files ADD COLUMN similarity_pct INTEGER DEFAULT 100"),
            ("files",         "ALTER TABLE files ADD COLUMN file_size INTEGER DEFAULT 0"),
            ("files",         "ALTER TABLE files ADD COLUMN metadata TEXT DEFAULT ''"),
        ]
        for _table, sql in migrations:
            try:
                cursor.execute(sql)
                conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists — skip silently
        
        # Гарантируем наличие триггера и в старых базах
        try:
            cursor.execute("DROP TRIGGER IF EXISTS enforce_survivor_rule")
            cursor.execute("""
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
            conn.commit()
        except Exception as e:
            logging.error(f"Failed to create trigger in migrations: {e}")

    def clear_db(self) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM files")
            cursor.execute("DELETE FROM groups")
            cursor.execute("DELETE FROM zero_files")
            cursor.execute("DELETE FROM empty_folders")
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Session DB Clear Error: {e}")

    def add_groups(self, groups_list: list[dict[str, Any]]) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Шаг 1. Формируем пакетные данные для групп
            groups_data = []
            for grp in groups_list:
                files = grp['files']
                wasted = grp.get('wasted_size', grp['size'] * (len(files) - 1))
                g_size = grp.get('total_size', grp['size'])
                ext = ""
                if files:
                    ext = os.path.splitext(files[0].get('real_path', files[0].get('path', '')))[1].lower()
                groups_data.append((grp['hash'], g_size, len(files), wasted, ext))
            
            # Шаг 2. Пакетно вставляем все группы
            cursor.executemany(
                "INSERT INTO groups (hash, size, file_count, wasted_size, extension) VALUES (?, ?, ?, ?, ?)",
                groups_data
            )
            
            # Шаг 3. Получаем сгенерированные ID для сопоставления по уникальному хэшу
            cursor.execute("SELECT id, hash FROM groups")
            hash_to_id = {row[1]: row[0] for row in cursor.fetchall()}
            
            # Шаг 4. Формируем пакетные данные для файлов (с полем similarity_pct)
            files_data = []
            for grp in groups_list:
                g_id = hash_to_id.get(grp['hash'])
                if g_id is not None:
                    for f in grp['files']:
                        real_path = f.get('real_path', f.get('path', ''))
                        similarity_pct = f.get('similarity_pct', 100)
                        file_size = f.get('size', grp.get('size', 0))
                        metadata = f.get('metadata', '')
                        files_data.append((g_id, real_path, similarity_pct, file_size, metadata))
            
            # Шаг 5. Пакетно вставляем все файлы
            cursor.executemany(
                "INSERT INTO files (group_id, path, similarity_pct, file_size, metadata) VALUES (?, ?, ?, ?, ?)",
                files_data
            )
            
            conn.commit()
            conn.close()
        except Exception as e: 
            logging.error(f"Session DB Insert Error: {e}")

    def add_zero_files(self, files_list: list[str]) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            data = []
            for path in files_list:
                ext = os.path.splitext(path)[1].lower()
                data.append((path, ext))
            cursor.executemany("INSERT INTO zero_files (path, extension) VALUES (?, ?)", data)
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Session DB Zero Files Insert Error: {e}")

    def add_empty_folders(self, folders_list: list[str]) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            data = [(path,) for path in folders_list]
            cursor.executemany("INSERT INTO empty_folders (path) VALUES (?)", data)
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Session DB Empty Folders Insert Error: {e}")

    def fetch_groups(self, offset: int, limit: int = 50, filter_exts: list[str] | None = None, filter_mode: str = 'include') -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            where_clause = ""
            params: list[Any] = []
            if filter_exts:
                placeholders = ','.join(['?'] * len(filter_exts))
                if filter_mode == 'include': 
                    where_clause = f"AND extension IN ({placeholders})"
                else: 
                    where_clause = f"AND extension NOT IN ({placeholders})"
                params.extend(filter_exts)

            query = f"""
                SELECT * FROM groups 
                WHERE id IN (
                    SELECT group_id FROM files 
                    WHERE is_deleted = 0 
                    GROUP BY group_id 
                    HAVING COUNT(*) > 1
                ) {where_clause} 
                ORDER BY wasted_size DESC 
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])
            cursor.execute(query, params)
            groups = cursor.fetchall()
            
            for g in groups:
                cursor.execute("SELECT path, is_deleted, is_marked FROM files WHERE group_id = ? AND is_deleted = 0", (g['id'],))
                active_files = cursor.fetchall()
                if len(active_files) > 1:
                    result.append({
                        'id': g['id'], 
                        'hash': g['hash'], 
                        'size': g['size'], 
                        'files': [{'path': f['path'], 'real_path': f['path'], 'is_marked': f['is_marked']} for f in active_files]
                    })
            conn.close()
        except Exception as e:
            logging.error(f"Error in fetch_groups: {e}")
        return result

    def fetch_all_flat_items(self, filter_exts: list[str] | None = None, filter_mode: str = 'include', progress_callback: Any = None) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            where_clause = ""
            params: list[Any] = []
            if filter_exts:
                placeholders = ','.join(['?'] * len(filter_exts))
                if filter_mode == 'include': 
                    where_clause = f"AND extension IN ({placeholders})"
                else: 
                    where_clause = f"AND extension NOT IN ({placeholders})"
                params.extend(filter_exts)

            query = f"""
                SELECT * FROM groups 
                WHERE id IN (
                    SELECT group_id FROM files 
                    WHERE is_deleted = 0 
                    GROUP BY group_id 
                    HAVING COUNT(*) > 1
                ) {where_clause} 
                ORDER BY wasted_size DESC
            """
            cursor.execute(query, params)
            groups = cursor.fetchall()
            
            if not groups:
                conn.close()
                return []
                
            # Загружаем абсолютно все активные файлы за 1 запрос!
            cursor.execute("SELECT id, group_id, path, is_marked, similarity_pct, file_size, metadata FROM files WHERE is_deleted = 0")
            all_files = cursor.fetchall()
            
            # Быстро группируем файлы по group_id в оперативной памяти Python
            files_by_group: dict[int, list[sqlite3.Row]] = {}
            for f in all_files:
                gid = f['group_id']
                if gid not in files_by_group:
                    files_by_group[gid] = []
                files_by_group[gid].append(f)
            
            total_groups = len(groups)
            for idx, g in enumerate(groups):
                # Обновляем прогресс раз в 2000 групп, так как процесс стал почти мгновенным
                if progress_callback and idx % 2000 == 0:
                    progress_callback(idx, total_groups)

                active_files = files_by_group.get(g['id'], [])
                if len(active_files) > 1:
                    wasted = g['size'] * (len(active_files) - 1)
                    shortest_name = min(
                        (os.path.basename(f['path']) for f in active_files),
                        key=len,
                        default=g['hash']
                    )
                    result.append({
                        'type': 'group',
                        'id': g['id'],
                        'hash': g['hash'],
                        'display_name': shortest_name,
                        'size': g['size'],
                        'file_count': len(active_files),
                        'wasted_size': wasted,
                        'extension': g['extension']
                    })
                    for f in active_files:
                        result.append({
                            'type': 'file',
                            'id': f['id'],
                            'group_id': g['id'],
                            'path': f['path'],
                            'size': f['file_size'] if 'file_size' in f.keys() and f['file_size'] > 0 else g['size'],
                            'metadata': f['metadata'] if 'metadata' in f.keys() else '',
                            'is_marked': f['is_marked'],
                            'similarity_pct': f['similarity_pct'] if 'similarity_pct' in f.keys() else 100
                        })
            if progress_callback:
                progress_callback(total_groups, total_groups)
            conn.close()
        except Exception as e:
            logging.error(f"Error in fetch_all_flat_items: {e}")
        return result

    def fetch_all_flat_zero_items(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id, path, extension, is_marked FROM zero_files WHERE is_deleted = 0")
            files = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            groups: dict[str, list[dict[str, Any]]] = {}
            for f in files:
                ext = f['extension'] or "No Extension"
                if ext not in groups: groups[ext] = []
                groups[ext].append(f)
                
            for ext, ext_files in groups.items():
                result.append({
                    'type': 'group',
                    'id': ext,
                    'extension': ext,
                    'file_count': len(ext_files),
                    'size': 0,
                    'wasted_size': 0
                })
                for f in ext_files:
                    result.append({
                        'type': 'file',
                        'id': f['id'],
                        'group_id': ext,
                        'path': f['path'],
                        'size': 0,
                        'is_marked': f['is_marked']
                    })
        except Exception as e:
            logging.error(f"Error in fetch_all_flat_zero_items: {e}")
        return result

    def fetch_all_flat_empty_folders(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id, path, is_marked FROM empty_folders WHERE is_deleted = 0 ORDER BY path")
            rows = cursor.fetchall()
            conn.close()
            for r in rows:
                result.append({
                    'type': 'empty_folder',
                    'id': r['id'],
                    'path': r['path'],
                    'is_marked': r['is_marked']
                })
        except Exception as e:
            logging.error(f"Error in fetch_all_flat_empty_folders: {e}")
        return result

    def fetch_zero_files(self) -> list[dict[str, Any]]:
        res: list[dict[str, Any]] = []
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT path, extension, is_marked FROM zero_files WHERE is_deleted = 0")
            res = [dict(row) for row in cursor.fetchall()]
            conn.close()
        except Exception as e:
            logging.error(f"Error in fetch_zero_files: {e}")
        return res

    def fetch_empty_folders(self) -> list[dict[str, Any]]:
        res: list[dict[str, Any]] = []
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT path, is_marked FROM empty_folders WHERE is_deleted = 0")
            res = [dict(row) for row in cursor.fetchall()]
            conn.close()
        except Exception as e:
            logging.error(f"Error in fetch_empty_folders: {e}")
        return res

    def get_extension_stats(self) -> dict[str, list[dict[str, Any]]]:
        from .workers import EXT_GROUPS 
        stats: dict[str, int] = {}
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            query = """
                SELECT extension, COUNT(*) 
                FROM groups 
                WHERE id IN (
                    SELECT group_id FROM files 
                    WHERE is_deleted = 0 
                    GROUP BY group_id 
                    HAVING COUNT(*) > 1
                )
                GROUP BY extension
            """
            cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()
            for ext, count in rows:
                if not ext: continue
                stats[ext] = count
        except Exception as e:
            logging.error(f"Error in get_extension_stats: {e}")
            
        grouped_results: dict[str, list[dict[str, Any]]] = {}
        for group_name in EXT_GROUPS.keys(): grouped_results[group_name] = []
        other_list: list[dict[str, Any]] = []
        for ext, count in stats.items():
            found = False
            for group_name, ext_set in EXT_GROUPS.items():
                if ext in ext_set:
                    grouped_results[group_name].append({'ext': ext, 'count': count})
                    found = True
                    break
            if not found: other_list.append({'ext': ext, 'count': count})
        if other_list: grouped_results["Other"] = other_list
        final_results = {k: v for k, v in grouped_results.items() if v}
        for k in final_results: final_results[k].sort(key=lambda x: x['count'], reverse=True)
        return final_results

    # =========================================================================
    # IRON RULE — НЕПРИКОСНОВЕННОЕ ПРАВИЛО БЕЗОПАСНОСТИ
    # В каждой группе дубликатов хотя бы ОДИН файл должен оставаться
    # невыделенным (is_marked = 0). Это предотвращает безвозвратное удаление
    # ВСЕХ копий файла. Данный метод нельзя удалять, обходить или отключать.
    # =========================================================================
    def enforce_group_survivor_rule(self, cursor: sqlite3.Cursor, conn: sqlite3.Connection) -> None:
        """IRON RULE: гарантирует что в каждой группе хотя бы 1 файл is_marked=0."""
        try:
            cursor.execute("""
                SELECT DISTINCT group_id FROM files
                WHERE is_deleted = 0
                GROUP BY group_id
                HAVING COUNT(*) > 0 AND COUNT(*) = SUM(is_marked)
            """)
            fully_marked_groups = [row[0] for row in cursor.fetchall()]
            for gid in fully_marked_groups:
                cursor.execute("""
                    SELECT path FROM files
                    WHERE group_id = ? AND is_deleted = 0
                    ORDER BY path ASC
                    LIMIT 1
                """, (gid,))
                row = cursor.fetchone()
                if row:
                    cursor.execute("UPDATE files SET is_marked = 0 WHERE path = ?", (row[0],))
            if fully_marked_groups:
                conn.commit()
        except Exception as e:
            logging.error(f"[IRON RULE] enforce_group_survivor_rule error: {e}")

    def mark_file_selected(self, path: str, state: int) -> None:
        self.set_files_marked_state_safe([path], state)

    def mark_file_deleted(self, path: str) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE files SET is_deleted = 1 WHERE path = ?", (path,))
            cursor.execute("UPDATE zero_files SET is_deleted = 1 WHERE path = ?", (path,))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Error in mark_file_deleted: {e}")

    def mark_all_empty_folders(self, state: int) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE empty_folders SET is_marked = ? WHERE is_deleted = 0", (state,))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Error marking all empty folders: {e}")

    def mark_all_zero_files(self, state: int) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE zero_files SET is_marked = ? WHERE is_deleted = 0", (state,))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Error marking all zero files: {e}")
    def mark_files_deleted(self, paths: list[str]) -> None:
        """Optimized batch marked file deletion using one transaction."""
        if not paths: return
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.executemany("UPDATE files SET is_deleted = 1 WHERE path = ?", [(p,) for p in paths])
            cursor.executemany("UPDATE zero_files SET is_deleted = 1 WHERE path = ?", [(p,) for p in paths])
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Error in mark_files_deleted: {e}")

    def get_all_marked_paths(self) -> set[str]:
        """Saves CPU and memory by loading all marked files into a set, preventing SQLITE_MAX_VARIABLE_NUMBER limit."""
        marked = set()
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT path FROM files WHERE is_marked = 1 AND is_deleted = 0")
            for row in cursor.fetchall(): marked.add(row[0])
            cursor.execute("SELECT path FROM zero_files WHERE is_marked = 1 AND is_deleted = 0")
            for row in cursor.fetchall(): marked.add(row[0])
            cursor.execute("SELECT path FROM empty_folders WHERE is_marked = 1 AND is_deleted = 0")
            for row in cursor.fetchall(): marked.add(row[0])
            conn.close()
        except Exception as e:
            logging.error(f"Error in get_all_marked_paths: {e}")
        return marked

    def mark_folder_deleted(self, path: str) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("UPDATE empty_folders SET is_deleted = 1 WHERE path = ?", (path,))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Error in mark_folder_deleted: {e}")

    def delete_group(self, group_id: int) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM files WHERE group_id = ?", (group_id,))
            cursor.execute("DELETE FROM groups WHERE id = ?", (group_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Error in delete_group: {e}")

    def get_total_groups_count(self, filter_exts: list[str] | None = None, filter_mode: str = 'include') -> int:
        count = 0
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            where_clause = ""
            params: list[Any] = []
            if filter_exts:
                placeholders = ','.join(['?'] * len(filter_exts))
                if filter_mode == 'include': 
                    where_clause = f"AND extension IN ({placeholders})"
                else: 
                    where_clause = f"AND extension NOT IN ({placeholders})"
                params.extend(filter_exts)

            query = f"""
                SELECT COUNT(*) FROM groups 
                WHERE id IN (
                    SELECT group_id FROM files 
                    WHERE is_deleted = 0 
                    GROUP BY group_id 
                    HAVING COUNT(*) > 1
                ) {where_clause}
            """
            cursor.execute(query, params)
            count = cursor.fetchone()[0]
            conn.close()
        except Exception as e:
            logging.error(f"Error in get_total_groups_count: {e}")
        return count

    def get_active_stats(self) -> dict[str, int]:
        stats = {'groups_count': 0, 'copies_count': 0, 'wasted': 0, 'dupes_count': 0}
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Извлекаем количество групп, общее число файлов и объем потерь за 1 запрос
            query = """
                SELECT 
                    COUNT(*),
                    SUM(f_count),
                    SUM((f_count - 1) * size)
                FROM (
                    SELECT 
                        g.size, 
                        COUNT(f.id) AS f_count
                    FROM groups g
                    JOIN files f ON f.group_id = g.id
                    WHERE f.is_deleted = 0
                    GROUP BY g.id
                    HAVING COUNT(f.id) > 1
                )
            """
            cursor.execute(query)
            row = cursor.fetchone()
            if row and row[0] is not None:
                stats['groups_count'] = row[0]
                stats['dupes_count'] = row[1] or 0
                stats['copies_count'] = (row[1] or 0) - (row[0] or 0)
                stats['wasted'] = row[2] or 0
            conn.close()
        except Exception as e:
            logging.error(f"Error in get_active_stats: {e}")
        return stats

    def get_marked_status_for_paths(self, paths: list[str]) -> dict[str, int]:
        result: dict[str, int] = {}
        if not paths: return result
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            placeholders = ','.join(['?'] * len(paths))
            
            cursor.execute(f"SELECT path, is_marked FROM files WHERE path IN ({placeholders})", paths)
            for path, is_marked in cursor.fetchall():
                result[path] = is_marked
                
            cursor.execute(f"SELECT path, is_marked FROM zero_files WHERE path IN ({placeholders})", paths)
            for path, is_marked in cursor.fetchall():
                result[path] = is_marked
                
            cursor.execute(f"SELECT path, is_marked FROM empty_folders WHERE path IN ({placeholders})", paths)
            for path, is_marked in cursor.fetchall():
                result[path] = is_marked
                
            conn.close()
        except Exception as e:
            logging.error(f"Error in get_marked_status_for_paths: {e}")
        return result

    def set_files_marked_state_safe(self, paths: list[str], state: int) -> None:
        """
        Итеративный накопительный шлюз безопасности.
        Помечает список файлов как `state` (0 или 1).
        Если state == 1, помечает файлы поочередно, останавливаясь, когда unmarked_count == 1.
        """
        if not paths:
            return
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            if state == 0:
                # Снятие выделения всегда безопасно, выполняем массово
                placeholders = ','.join(['?'] * len(paths))
                cursor.execute(f"UPDATE files SET is_marked = 0 WHERE path IN ({placeholders})", paths)
                cursor.execute(f"UPDATE zero_files SET is_marked = 0 WHERE path IN ({placeholders})", paths)
                cursor.execute(f"UPDATE empty_folders SET is_marked = 0 WHERE path IN ({placeholders})", paths)
                conn.commit()
                conn.close()
                return

            # Группируем пути файлов по их group_id в БД
            placeholders = ','.join(['?'] * len(paths))
            cursor.execute(f"SELECT path, group_id FROM files WHERE path IN ({placeholders}) AND is_deleted = 0", paths)
            db_files = cursor.fetchall()
            
            # Собираем файлы по группам
            groups_map: dict[int, list[str]] = {}
            for path, gid in db_files:
                if gid not in groups_map:
                    groups_map[gid] = []
                groups_map[gid].append(path)

            # Обрабатываем каждую группу итеративно
            for gid, group_paths in groups_map.items():
                # Получаем все активные невыделенные файлы в этой группе
                cursor.execute("SELECT path FROM files WHERE group_id = ? AND is_deleted = 0 AND is_marked = 0", (gid,))
                unmarked_paths = [row[0] for row in cursor.fetchall()]

                for path in group_paths:
                    if len(unmarked_paths) > 1:
                        cursor.execute("UPDATE files SET is_marked = 1 WHERE path = ?", (path,))
                        if path in unmarked_paths:
                            unmarked_paths.remove(path)
                    else:
                        # В группе остался ровно один выживший — останавливаем автоматическое выделение для нее
                        break

            # Для zero_files и empty_folders ограничение N-1 не действует, обновляем их напрямую
            cursor.execute(f"UPDATE zero_files SET is_marked = 1 WHERE path IN ({placeholders}) AND is_deleted = 0", paths)
            cursor.execute(f"UPDATE empty_folders SET is_marked = 1 WHERE path IN ({placeholders}) AND is_deleted = 0", paths)
            
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"[SafetyGate] set_files_marked_state_safe error: {e}")

    def set_group_marked_state_safe(self, group_id: int, action: str, first_unprotected_path: str | None = None) -> None:
        """
        Безопасное групповое выделение на уровне СУБД для конкретной группы.
        Действия:
        - 'all': выделить все незащищенные файлы в группе, кроме последнего выжившего.
        - 'all_except_first': выделить все незащищенные, кроме первого по алфавиту и последнего выжившего.
        - 'none': снять все выделения в группе.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            if action == 'none':
                cursor.execute("UPDATE files SET is_marked = 0 WHERE group_id = ?", (group_id,))
                conn.commit()
                conn.close()
                return

            if action in ('all', 'all_except_first'):
                # Получаем текущие активные файлы в БД
                cursor.execute("SELECT path, is_marked FROM files WHERE group_id = ? AND is_deleted = 0", (group_id,))
                db_files = [{'path': r[0], 'is_marked': r[1]} for r in cursor.fetchall()]

                unmarked_paths = [f['path'] for f in db_files if f['is_marked'] == 0]
                if len(unmarked_paths) <= 1:
                    # Группа уже зафиксирована
                    conn.close()
                    return

                # Определяем, какие файлы мы хотим выделить (to_mark)
                to_mark = []
                for f in db_files:
                    # Если action == 'all_except_first' и это первый незащищенный путь, пропускаем его
                    if action == 'all_except_first' and f['path'] == first_unprotected_path:
                        continue
                    to_mark.append(f['path'])

                # Итеративно выделяем
                for path in to_mark:
                    # Проверяем актуальный статус в БД (возможно, он уже выделен)
                    cursor.execute("SELECT is_marked FROM files WHERE path = ?", (path,))
                    row = cursor.fetchone()
                    if row and row[0] == 1:
                        continue

                    if len(unmarked_paths) > 1:
                        cursor.execute("UPDATE files SET is_marked = 1 WHERE path = ?", (path,))
                        if path in unmarked_paths:
                            unmarked_paths.remove(path)
                    else:
                        break

            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"[SafetyGate] set_group_marked_state_safe error: {e}")

    def get_global_selection_stats(self) -> dict[str, int]:
        stats = {'count': 0, 'size': 0}
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Duplicates
            cursor.execute("""
                SELECT COUNT(*), SUM(g.size) 
                FROM files f
                JOIN groups g ON f.group_id = g.id
                WHERE f.is_marked = 1 AND f.is_deleted = 0
            """)
            row = cursor.fetchone()
            if row and row[0]:
                stats['count'] += row[0]
                stats['size'] += row[1] or 0
                
            # Zero files
            cursor.execute("SELECT COUNT(*) FROM zero_files WHERE is_marked = 1 AND is_deleted = 0")
            row = cursor.fetchone()
            if row and row[0]:
                stats['count'] += row[0]
                
            # Empty folders
            cursor.execute("SELECT COUNT(*) FROM empty_folders WHERE is_marked = 1 AND is_deleted = 0")
            row = cursor.fetchone()
            if row and row[0]:
                stats['count'] += row[0]
                
            conn.close()
        except Exception as e:
            logging.error(f"Error in get_global_selection_stats: {e}")
        return stats

    def apply_global_autoselect(self, mode: str, source_folders: dict[str, Any], progress_callback: Any = None) -> None:
        """
        Безопасный высокопроизводительный автовыбор дубликатов на уровне СУБД.
        Зафиксированные группы (unmarked_count == 1) полностью игнорируются.
        Незафиксированные группы рассчитываются в ОЗУ и помечаются пакетно.
        Supports aborting via progress_callback returning False.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Загружаем абсолютно все активные файлы за 1 запрос
            cursor.execute("SELECT id, group_id, path, is_marked FROM files WHERE is_deleted = 0")
            all_files = cursor.fetchall()
            
            if not all_files:
                conn.close()
                return
                
            # Быстро группируем файлы по group_id в оперативной памяти Python
            files_by_group = {}
            for f in all_files:
                gid = f['group_id']
                if gid not in files_by_group:
                    files_by_group[gid] = []
                files_by_group[gid].append({
                    'id': f['id'],
                    'path': f['path'],
                    'is_marked': f['is_marked']
                })
            
            # Фильтруем группы дубликатов (где файлов > 1)
            groups = [gid for gid, f_list in files_by_group.items() if len(f_list) > 1]
            total_groups = len(groups)
            
            def is_path_protected(p: str) -> bool:
                for src_path, data in source_folders.items():
                    if is_subpath(p, src_path):
                        return data.get('protected', False)
                return False

            def is_path_reference(p: str) -> bool:
                for src_path, data in source_folders.items():
                    if is_subpath(p, src_path):
                        return data.get('reference', False)
                return False
                
            groups_to_reset = []
            files_to_mark = []
            
            for idx, gid in enumerate(groups):
                if progress_callback and idx % 2000 == 0:
                    if progress_callback(idx, total_groups) is False:
                        logging.info("[SafetyGate] Global autoselect cancelled by user.")
                        break
                        
                group_files = files_by_group[gid]
                
                # 1. Проверяем текущее количество невыделенных активных файлов в группе
                unmarked_count = sum(1 for f in group_files if f['is_marked'] == 0)
                if unmarked_count == 1:
                    # Группа уже зафиксирована пользователем (ровно 1 выживший), полностью пропускаем её!
                    continue
                    
                # 2. Для незафиксированных групп сбрасываем состояние и рассчитываем автовыбор заново
                groups_to_reset.append(gid)
                for f in group_files:
                    f['is_marked'] = 0
                    
                sorted_files = sorted(group_files, key=lambda f: (not is_path_protected(f['path']), f['path']))
                
                candidates = []
                has_protected = False
                for f in sorted_files:
                    is_prot = is_path_protected(f['path'])
                    if is_prot:
                        has_protected = True
                    else:
                        candidates.append(f)
                        
                to_mark = []
                if mode == 'protected_dupes':
                    if has_protected:
                        to_mark = candidates
                elif mode == 'reference_dupes':
                    has_reference = any(is_path_reference(f['path']) for f in sorted_files)
                    if has_reference:
                        to_mark = candidates
                else:
                    if len(candidates) < 2:
                        continue

                    def get_len(f: dict) -> int:
                        return len(os.path.basename(f['path']))
                        
                    def get_depth(f: dict) -> int:
                        return f['path'].count(os.sep)
                        
                    def get_time_tuple(f: dict) -> tuple[float, float]:
                        try:
                            s = os.stat(f['path'])
                            return (s.st_mtime, s.st_ctime)
                        except:
                            return (0.0, 0.0)

                    survivors = []
                    
                    if mode == 'keep_first':
                        survivors = [candidates[0]]
                    elif mode == 'keep_last':
                        survivors = [candidates[-1]]
                    elif mode in ['keep_shortest', 'keep_longest']:
                        vals = [(f, get_len(f)) for f in candidates]
                        target_val = min(v for f, v in vals) if mode == 'keep_shortest' else max(v for f, v in vals)
                        survivors = [f for f, v in vals if v == target_val]
                    elif mode in ['keep_newest', 'keep_oldest']:
                        items_times = [(f, get_time_tuple(f)) for f in candidates]
                        target_time = max(items_times, key=lambda x: x[1])[1] if mode == 'keep_newest' else min(items_times, key=lambda x: x[1])[1]
                        survivors = [x[0] for x in items_times if x[1] == target_time]
                    elif mode in ['keep_shallow', 'keep_deep']:
                        vals = [(f, get_depth(f)) for f in candidates]
                        target_val = min(v for f, v in vals) if mode == 'keep_shallow' else max(v for f, v in vals)
                        survivors = [f for f, v in vals if v == target_val]

                    if len(survivors) < len(candidates):
                        surv_ids = {s['id'] for s in survivors}
                        to_mark = [f for f in candidates if f['id'] not in surv_ids]

                # 3. Итеративно помечаем to_mark, пока не останется ровно 1 выживший в группе
                active_count = len(group_files)
                unmarked_in_group = active_count
                for f in to_mark:
                    if unmarked_in_group > 1:
                        files_to_mark.append(f['id'])
                        unmarked_in_group -= 1
                    else:
                        break
                        
            if progress_callback:
                progress_callback(total_groups, total_groups)
                
            # 4. Применяем изменения в БД пакетно
            if groups_to_reset:
                cursor.executemany("UPDATE files SET is_marked = 0 WHERE group_id = ?", [(gid,) for gid in groups_to_reset])
            if files_to_mark:
                cursor.executemany("UPDATE files SET is_marked = 1 WHERE id = ?", [(fid,) for fid in files_to_mark])
                
            # IRON RULE: применяем жесткую принудительную валидацию триггера в конце
            self.enforce_group_survivor_rule(cursor, conn)
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Error in apply_global_autoselect: {e}")

    def apply_batch_select_by_condition(self, condition_func: Any, source_folders: dict[str, Any], progress_callback: Any = None) -> None:
        """
        Высокопроизводительное пакетное выделение файлов по условию (папка, эталонный корень).
        Осуществляет расчеты в ОЗУ за миллисекунды, затем обновляет СУБД одной пакетной операцией.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Загружаем абсолютно все активные файлы за 1 запрос
            cursor.execute("SELECT id, group_id, path, is_marked FROM files WHERE is_deleted = 0")
            all_files = cursor.fetchall()
            
            if not all_files:
                conn.close()
                return
                
            # Быстро группируем файлы по group_id в оперативной памяти Python
            files_by_group = {}
            for f in all_files:
                gid = f['group_id']
                if gid not in files_by_group:
                    files_by_group[gid] = []
                files_by_group[gid].append({
                    'id': f['id'],
                    'path': f['path'],
                    'is_marked': f['is_marked']
                })
                
            groups = [gid for gid, f_list in files_by_group.items() if len(f_list) > 1]
            total_groups = len(groups)
            
            def is_path_protected(p: str) -> bool:
                for src_path, data in source_folders.items():
                    if is_subpath(p, src_path):
                        return data.get('protected', False)
                return False

            files_to_mark = []
            
            for idx, gid in enumerate(groups):
                if progress_callback and idx % 2000 == 0:
                    if progress_callback(idx, total_groups) is False:
                        logging.info("[SafetyGate] Batch select by condition cancelled by user.")
                        break
                        
                group_files = files_by_group[gid]
                
                # Проверяем, сколько невыделенных активных файлов сейчас в группе
                unmarked_count = sum(1 for f in group_files if f['is_marked'] == 0)
                if unmarked_count <= 1:
                    # Группа уже зафиксирована
                    continue
                    
                # Ищем файлы, которые соответствуют условию и не защищены
                to_mark = []
                for f in group_files:
                    if f['is_marked'] == 0 and not is_path_protected(f['path']) and condition_func(f['path']):
                        to_mark.append(f)
                        
                # Итеративно выделяем файлы, соблюдая правило N-1
                for f in to_mark:
                    if unmarked_count > 1:
                        files_to_mark.append(f['id'])
                        unmarked_count -= 1
                    else:
                        break
                        
            if progress_callback:
                progress_callback(total_groups, total_groups)
                
            # Обновляем БД пакетно
            if files_to_mark:
                cursor.executemany("UPDATE files SET is_marked = 1 WHERE id = ?", [(fid,) for fid in files_to_mark])
                
            # IRON RULE: валидация триггера
            self.enforce_group_survivor_rule(cursor, conn)
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Error in apply_batch_select_by_condition: {e}")

    def get_global_marked_files(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT f.path, f.group_id, g.hash, g.size
                FROM files f
                JOIN groups g ON f.group_id = g.id
                WHERE f.is_marked = 1 AND f.is_deleted = 0
            """)
            rows = cursor.fetchall()
            
            survivors: dict[int, str] = {}
            for r in rows:
                grp_id = r['group_id']
                if grp_id not in survivors:
                    cursor.execute("SELECT path FROM files WHERE group_id = ? AND is_marked = 0 AND is_deleted = 0 LIMIT 1", (grp_id,))
                    s_row = cursor.fetchone()
                    if s_row:
                        survivors[grp_id] = os.path.basename(s_row[0])
                    else:
                        cursor.execute("SELECT path FROM files WHERE group_id = ? LIMIT 1", (grp_id,))
                        fb = cursor.fetchone()
                        survivors[grp_id] = os.path.basename(fb[0]) if fb else "file"
            
            for r in rows:
                items.append({
                    'src': r['path'],
                    'survivor_base': os.path.splitext(survivors[r['group_id']])[0],
                    'group_index': r['group_id'],
                    'size': r['size']
                })
            conn.close()
        except Exception as e:
            logging.error(f"Error in get_global_marked_files: {e}")
        return items

    def get_global_marked_zero_files(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT path FROM zero_files WHERE is_marked = 1 AND is_deleted = 0")
            rows = cursor.fetchall()
            for r in rows:
                items.append({
                    'src': r['path'],
                    'survivor_base': os.path.splitext(os.path.basename(r['path']))[0],
                    'group_index': 0
                })
            conn.close()
        except Exception as e:
            logging.error(f"Error in get_global_marked_zero_files: {e}")
        return items

    def get_global_marked_empty_folders(self) -> list[str]:
        items: list[str] = []
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT path FROM empty_folders WHERE is_marked = 1 AND is_deleted = 0")
            items = [r[0] for r in cursor.fetchall()]
            conn.close()
        except Exception as e:
            logging.error(f"Error in get_global_marked_empty_folders: {e}")
        return items

class SimilarSessionDB(SessionDB):
    DB_NAME = "session_similar.db"

    def init_db(self) -> None:
        super().init_db()
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            # Убираем правило обязательного выжившего для режима поиска похожих
            cursor.execute("DROP TRIGGER IF EXISTS enforce_survivor_rule")
            conn.commit()
            conn.close()
        except Exception as e:
            import logging
            logging.error(f"SimilarSessionDB Init Error: {e}")
