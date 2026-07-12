
import os
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool

class ScanWorkerSignals(QObject):
    result_ready = pyqtSignal(str, int, object)

class ScanWorker(QRunnable):
    def __init__(self, path):
        super().__init__()
        self.path = path
        self.signals = ScanWorkerSignals()

    def run(self):
        total_size = 0
        file_count = 0
        from utils_io import ensure_long_path
        long_folder = ensure_long_path(self.path)
        try:
            try:
                with os.scandir(long_folder) as it:
                    for entry in it:
                        if entry.is_file():
                            file_count += 1
            except:
                pass
                
            for root, dirs, files in os.walk(long_folder):
                if '.mediakeeper' in dirs:
                    dirs.remove('.mediakeeper')
                
                for f in files:
                    try:
                        fp = os.path.join(root, f)
                        total_size += os.path.getsize(fp)
                    except: pass
        except: pass
        self.signals.result_ready.emit(self.path, file_count, total_size)

from utils_io import strip_long_path_prefix

class DirCache(QObject):
    updated = pyqtSignal(str) # path that changed
    
    _instance = None
    
    def __init__(self):
        super().__init__()
        self._cache = {} # path -> {'c': count, 's': size}
        self._active_scans = set() # paths currently being scanned
        
        # Dedicated thread pool for disk scanning to prevent IO thrashing
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(1)

    @staticmethod
    def inst():
        if DirCache._instance is None:
            DirCache._instance = DirCache()
        return DirCache._instance

    def get_data(self, path):
        """
        Returns (count, size). 
        If not cached, returns (0, 0) and triggers background scan.
        """
        if not path: return 0, 0
        path = strip_long_path_prefix(os.path.normpath(path))
        
        # Check cache
        if path in self._cache:
            data = self._cache[path]
            return data['c'], data['s']
        
        # Not cached -> Trigger scan
        self.refresh_path(path)
        return 0, 0

    def refresh_path(self, path):
        if not path: return
        path = strip_long_path_prefix(os.path.normpath(path))
        if path in self._active_scans: return # Already scanning
        
        self._active_scans.add(path)
        worker = ScanWorker(path)
        worker.signals.result_ready.connect(self._on_worker_finished)
        self.thread_pool.start(worker)

    def _on_worker_finished(self, path, count, size):
        path = strip_long_path_prefix(os.path.normpath(path))
        self._active_scans.discard(path)
        self._cache[path] = {'c': count, 's': size}
        self.updated.emit(path)

    def optimistic_update(self, path, delta_count, delta_size):
        """
        Updates cache immediately without disk access. 
        """
        if not path: return
        path = strip_long_path_prefix(os.path.normpath(path))
        if path in self._cache:
            self._cache[path]['c'] += delta_count
            self._cache[path]['s'] += delta_size
            # Prevent negative values
            if self._cache[path]['c'] < 0: self._cache[path]['c'] = 0
            if self._cache[path]['s'] < 0: self._cache[path]['s'] = 0
            self.updated.emit(path)
        else:
            # If not in cache, we better trigger a scan to be safe
            self.refresh_path(path)

    def invalidate(self, path: str) -> None:
        path = os.path.normpath(path)
        self._cache.pop(path, None)

    def invalidate_with_parents(self, path: str) -> None:
        current: str = os.path.normpath(path)
        while True:
            self._cache.pop(current, None)
            parent: str = os.path.dirname(current)
            if parent == current or not parent or parent == os.path.sep:
                break
            current = parent

    def clear(self) -> None:
        self._cache.clear()
