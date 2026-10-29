import os
import sys
import time
import unittest
import tempfile
import threading
import numpy as np
import cv2

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.cleaner.logic_orb import OrbCacheManager, CURRENT_CACHE_VERSION

class TestOrbCache(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.cache_dir = self.tmpdir.name

        # Create dummy image file
        self.dummy_img_path = os.path.join(self.tmpdir.name, "sample.jpg")
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        cv2.imwrite(self.dummy_img_path, img)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _create_manager(self, max_memory=150):
        mgr = OrbCacheManager(max_memory_items=max_memory)
        # Override cache_dir to our temporary test directory
        mgr.close()
        mgr.cache_dir = self.cache_dir
        mgr.db_path = os.path.join(self.cache_dir, mgr.DB_NAME)
        mgr._local_conn = None
        mgr.init_db()
        return mgr

    def test_sqlite_wal_and_version(self):
        mgr = self._create_manager()
        try:
            self.assertTrue(os.path.exists(mgr.db_path))
            with mgr._conn() as conn:
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
            mgr.close()

    def test_save_and_load_features(self):
        mgr = self._create_manager()
        try:
            kps = [
                cv2.KeyPoint(x=10.5, y=20.5, size=8.0, angle=30.0, response=0.9, octave=1, class_id=0),
                cv2.KeyPoint(x=55.0, y=75.0, size=12.0, angle=180.0, response=0.75, octave=2, class_id=1),
            ]
            desc = np.random.randn(2, 128).astype(np.float32)
            scale = 0.5

            mgr.save_cache(self.dummy_img_path, kps, desc, scale)

            # 1. Load from RAM cache
            loaded_kps, loaded_desc, loaded_scale = mgr.load_cache(self.dummy_img_path)
            self.assertEqual(len(loaded_kps), 2)
            self.assertEqual(loaded_kps[0].pt, (10.5, 20.5))
            self.assertTrue(np.allclose(loaded_desc, desc))
            self.assertEqual(loaded_scale, 0.5)

            # 2. Clear RAM cache and reload from SQLite
            mgr.clear_memory()
            loaded_kps2, loaded_desc2, loaded_scale2 = mgr.load_cache(self.dummy_img_path)
            self.assertEqual(len(loaded_kps2), 2)
            self.assertAlmostEqual(loaded_kps2[0].pt[0], 10.5, places=3)
            self.assertAlmostEqual(loaded_kps2[0].pt[1], 20.5, places=3)
            self.assertAlmostEqual(loaded_kps2[1].size, 12.0, places=3)
            self.assertTrue(np.allclose(loaded_desc2, desc))
            self.assertEqual(loaded_scale2, 0.5)
        finally:
            mgr.close()

    def test_invalidation_on_file_modification(self):
        mgr = self._create_manager()
        try:
            kps = [cv2.KeyPoint(x=1.0, y=1.0, size=1.0)]
            desc = np.ones((1, 128), dtype=np.float32)
            mgr.save_cache(self.dummy_img_path, kps, desc, 1.0)
            mgr.clear_memory()

            # Modify file content/size
            with open(self.dummy_img_path, "ab") as f:
                f.write(b"modified_data")

            # Must return None because size/mtime changed
            res_kps, res_desc, res_scale = mgr.load_cache(self.dummy_img_path)
            self.assertIsNone(res_kps)
            self.assertIsNone(res_desc)
            self.assertEqual(res_scale, 1.0)
        finally:
            mgr.close()

    def test_lru_memory_cache_bounded(self):
        # Limit to 3 items
        mgr = self._create_manager(max_memory=3)
        try:
            for i in range(6):
                path = os.path.join(self.tmpdir.name, f"test_{i}.jpg")
                with open(path, "wb") as f:
                    f.write(b"img")
                mgr.save_cache(path, [], np.zeros((1, 128), dtype=np.float32), 1.0)

            # Memory cache must have at most 3 items
            self.assertLessEqual(len(mgr.memory_cache), 3)

            # The most recent ones (3, 4, 5) should be in memory
            clean_last = os.path.normcase(os.path.normpath(os.path.join(self.tmpdir.name, "test_5.jpg")))
            clean_first = os.path.normcase(os.path.normpath(os.path.join(self.tmpdir.name, "test_0.jpg")))
            self.assertIn(clean_last, mgr.memory_cache)
            self.assertNotIn(clean_first, mgr.memory_cache)
        finally:
            mgr.close()

    def test_version_migration_reset(self):
        mgr = self._create_manager()
        try:
            mgr.save_cache(self.dummy_img_path, [], np.zeros((1, 128), dtype=np.float32), 1.0)
            mgr.clear_memory()

            # Set outdated version
            with mgr._conn() as conn:
                conn.execute("UPDATE sys_meta SET value = '0' WHERE key = 'cache_version'")
                conn.commit()

            # Re-init: should wipe features and reset version
            mgr.init_db()
            kps, desc, scale = mgr.load_cache(self.dummy_img_path)
            self.assertIsNone(desc)

            with mgr._conn() as conn:
                row = conn.execute("SELECT value FROM sys_meta WHERE key = 'cache_version'").fetchone()
                self.assertEqual(int(row[0]), CURRENT_CACHE_VERSION)
        finally:
            mgr.close()

    def test_cleanup_legacy_pkl_files(self):
        # Create dummy legacy .pkl files
        for i in range(5):
            pkl_path = os.path.join(self.cache_dir, f"old_cache_{i}.pkl")
            with open(pkl_path, "wb") as f:
                f.write(b"legacy_pickle_data")

        mgr = self._create_manager()
        try:
            # Run cleanup
            mgr._cleanup_legacy_pkl_files()
            # Give thread a brief moment to complete
            time.sleep(0.15)

            remaining_pkls = [f for f in os.listdir(self.cache_dir) if f.endswith(".pkl")]
            self.assertEqual(remaining_pkls, [])
        finally:
            mgr.close()

    def test_clear_disk_cache(self):
        mgr = self._create_manager()
        try:
            mgr.save_cache(self.dummy_img_path, [], np.zeros((1, 128), dtype=np.float32), 1.0)
            self.assertGreater(len(mgr.memory_cache), 0)

            mgr.clear_disk_cache()
            self.assertEqual(len(mgr.memory_cache), 0)

            with mgr._conn() as conn:
                count = conn.execute("SELECT COUNT(*) FROM sift_features").fetchone()[0]
                self.assertEqual(count, 0)
        finally:
            mgr.close()


if __name__ == '__main__':
    unittest.main()
