import os
import sys
import unittest
import tempfile
import threading
import sqlite3

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.cleaner.db_cache import CleanerDB, SimilarDB, CURRENT_CACHE_VERSION

class TestDBCache(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root_dir = self.tmpdir.name

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_cleaner_db_wal_and_version(self):
        db = CleanerDB(root_dir=self.root_dir)
        try:
            # Check persistent connection
            conn1 = db._get_connection()
            conn2 = db._get_connection()
            self.assertIs(conn1, conn2)

            # Check WAL mode and synchronous NORMAL
            cur = conn1.cursor()
            cur.execute("PRAGMA journal_mode;")
            self.assertEqual(cur.fetchone()[0].lower(), "wal")

            cur.execute("PRAGMA synchronous;")
            # 1 corresponds to NORMAL
            self.assertIn(cur.fetchone()[0], (1, "1", "NORMAL", "normal"))

            # Check sys_meta cache_version
            cur.execute("SELECT value FROM sys_meta WHERE key = 'cache_version'")
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(int(row[0]), CURRENT_CACHE_VERSION)
        finally:
            db.close()

    def test_cleaner_db_version_migration(self):
        db = CleanerDB(root_dir=self.root_dir)
        try:
            # Insert some dummy hash
            db.upsert_hash("C:/test/file1.jpg", 1000, 123.456, "p_hash_1", "f_hash_1")
            self.assertIsNotNone(db.get_cached_data("C:/test/file1.jpg", 1000, 123.456))

            # Simulate outdated cache version in sys_meta
            with db._conn() as conn:
                conn.execute("UPDATE sys_meta SET value = '0' WHERE key = 'cache_version'")
                conn.commit()

            # Re-init DB: should trigger reset and drop file_hashes
            db.init_db()

            # Verify table was cleared and version bumped back to CURRENT_CACHE_VERSION
            self.assertIsNone(db.get_cached_data("C:/test/file1.jpg", 1000, 123.456))
            with db._conn() as conn:
                row = conn.execute("SELECT value FROM sys_meta WHERE key = 'cache_version'").fetchone()
                self.assertEqual(int(row[0]), CURRENT_CACHE_VERSION)
        finally:
            db.close()

    def test_cleaner_db_batch_and_single_operations(self):
        db = CleanerDB(root_dir=self.root_dir)
        try:
            # Single upsert & get
            db.upsert_hash("C:/photos/a.jpg", 500, 100.0, "pa", "fa")
            res = db.get_cached_data("C:/photos/a.jpg", 500, 100.0)
            self.assertEqual(res, ("pa", "fa"))

            # Aliases test
            self.assertEqual(db.get_cached_hash("C:/photos/a.jpg", 500, 100.0), ("pa", "fa"))

            # Batch write (100 items)
            batch = [(f"C:/photos/item_{i}.jpg", 1000 + i, 200.0 + i, f"p_{i}", f"f_{i}") for i in range(100)]
            db.set_cached_batch(batch)

            # Batch read
            paths_to_query = [f"C:/photos/item_{i}.jpg" for i in range(10)]
            batch_res = db.get_cached_batch(paths_to_query)
            self.assertEqual(len(batch_res), 10)
            for i in range(10):
                path = f"C:/photos/item_{i}.jpg"
                self.assertIn(path, batch_res)
                size, mtime, p_h, f_h = batch_res[path]
                self.assertEqual(size, 1000 + i)
                self.assertAlmostEqual(mtime, 200.0 + i, places=3)
                self.assertEqual(p_h, f"p_{i}")
                self.assertEqual(f_h, f"f_{i}")

            # check_path_scanned
            self.assertTrue(db.check_path_scanned("C:/photos"))
            self.assertFalse(db.check_path_scanned("C:/nonexistent"))

            # Clear cache
            db.clear_cache()
            self.assertIsNone(db.get_cached_data("C:/photos/a.jpg", 500, 100.0))
            self.assertEqual(len(db.get_cached_batch(paths_to_query)), 0)
        finally:
            db.close()

    def test_similar_db_wal_and_version(self):
        db = SimilarDB(root_dir=self.root_dir, hash_size=16, algorithm="phash")
        try:
            conn = db._get_connection()
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode;")
            self.assertEqual(cur.fetchone()[0].lower(), "wal")

            cur.execute("PRAGMA synchronous;")
            self.assertIn(cur.fetchone()[0], (1, "1", "NORMAL", "normal"))

            cur.execute("SELECT value FROM sys_meta WHERE key = 'cache_version'")
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(int(row[0]), CURRENT_CACHE_VERSION)
        finally:
            db.close()

    def test_similar_db_batch_and_single_operations(self):
        db = SimilarDB(root_dir=self.root_dir, hash_size=16, algorithm="phash")
        try:
            # Single write & read
            db.upsert_signature("C:/media/pic.jpg", 2048, 50.0, "sig123")
            self.assertEqual(db.get_cached_signature("C:/media/pic.jpg", 2048, 50.0), "sig123")
            self.assertEqual(db.get_cached_hash("C:/media/pic.jpg", 2048, 50.0), "sig123")

            # Batch write
            batch = [(f"C:/media/pic_{i}.jpg", 2000 + i, 50.0 + i, f"sig_{i}") for i in range(50)]
            db.set_cached_batch(batch)

            # Batch read
            paths_to_query = [f"C:/media/pic_{i}.jpg" for i in range(10)]
            res = db.get_cached_batch(paths_to_query)
            self.assertEqual(len(res), 10)
            self.assertEqual(res["C:/media/pic_0.jpg"][2], "sig_0")

            # check_path_scanned
            self.assertTrue(db.check_path_scanned("C:/media"))
            self.assertFalse(db.check_path_scanned("C:/video"))

            # Clear cache
            db.clear_cache()
            self.assertIsNone(db.get_cached_signature("C:/media/pic.jpg", 2048, 50.0))
        finally:
            db.close()

    def test_thread_safety(self):
        """Verify that concurrent writes and reads from multiple threads do not lock or crash."""
        db = CleanerDB(root_dir=self.root_dir)
        errors = []

        def worker(thread_id):
            try:
                for i in range(50):
                    path = f"C:/thread_{thread_id}/file_{i}.jpg"
                    db.upsert_hash(path, 1000, float(i), f"p_{thread_id}_{i}", f"f_{thread_id}_{i}")
                    data = db.get_cached_data(path, 1000, float(i))
                    if data != (f"p_{thread_id}_{i}", f"f_{thread_id}_{i}"):
                        errors.append(f"Mismatch in thread {thread_id} item {i}: got {data}")
            except Exception as e:
                errors.append(f"Exception in thread {thread_id}: {e}")

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        db.close()
        self.assertEqual(errors, [], f"Thread safety errors encountered: {errors}")


if __name__ == '__main__':
    unittest.main()
