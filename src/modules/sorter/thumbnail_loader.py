import os
import logging
from utils_io import ensure_long_path
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, QThreadPool, QSize, Qt
from PyQt6.QtGui import QImage

class ThumbnailSignals(QObject):
    finished = pyqtSignal(str, QImage)  # Emits (filepath, scaled_image)
    error = pyqtSignal(str, str)        # Emits (filepath, error_message)
    process_started = pyqtSignal(str, object) # Emits (filepath, Popen)
    process_finished = pyqtSignal(str) # Emits (filepath)

class ThumbnailWorker(QRunnable):
    def __init__(self, filepath: str, target_size: QSize):
        super().__init__()
        self.filepath = filepath
        self.target_size = target_size
        self.signals = ThumbnailSignals()

    def run(self):
        try:
            image = QImage()
            loaded = False
            
            long_path = ensure_long_path(self.filepath)
            ext = os.path.splitext(long_path)[1].lower()
            from utils_extensions import VIDEO_EXTS
            
            if ext in VIDEO_EXTS:
                from logic_paths import get_ffmpeg_exe
                import subprocess
                ffmpeg = get_ffmpeg_exe()
                if os.path.exists(ffmpeg):
                    cmd = [
                        ffmpeg,
                        "-y",
                        "-ss", "00:00:00",
                        "-i", long_path,
                        "-frames:v", "1",
                        "-f", "image2pipe",
                        "-vcodec", "mjpeg",
                        "-"
                    ]
                    startupinfo = None
                    if os.name == 'nt':
                        startupinfo = subprocess.STARTUPINFO()
                        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    
                    try:
                        proc = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            startupinfo=startupinfo
                        )
                        self.signals.process_started.emit(self.filepath, proc)
                        try:
                            stdout, stderr = proc.communicate(timeout=5)
                            if proc.returncode == 0 and stdout:
                                if image.loadFromData(stdout):
                                    loaded = True
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.communicate()
                            logging.debug(f"FFmpeg extraction timeout for {self.filepath}")
                        finally:
                            self.signals.process_finished.emit(self.filepath)
                    except Exception as ex:
                        logging.debug(f"FFmpeg extraction failed for {self.filepath}: {ex}")
            
            if not loaded:
                if not image.load(long_path):
                    self.signals.error.emit(self.filepath, "Failed to load image")
                    return

            scaled = image.scaled(
                self.target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            self.signals.finished.emit(self.filepath, scaled)
        except Exception as e:
            logging.error(f"Error loading thumbnail for {self.filepath}: {e}", exc_info=True)
            self.signals.error.emit(self.filepath, str(e))

class ThumbnailLoader(QObject):
    thumbnail_ready = pyqtSignal(str, QImage)

    _instance = None

    @classmethod
    def inst(cls):
        if cls._instance is None:
            cls._instance = ThumbnailLoader()
        return cls._instance

    def __init__(self):
        if ThumbnailLoader._instance is not None:
            raise Exception("This class is a singleton!")
        super().__init__()
        self.pool = QThreadPool.globalInstance()
        # Keep track of active requests to prevent duplicate loading
        self.active_requests = set()
        self.active_processes = {} # filepath -> Popen
        # Cache for loaded images (QImage)
        self.cache = {}

    def get_thumbnail(self, filepath: str, target_size: QSize):
        norm_path = os.path.normpath(filepath)
        
        # Check RAM cache
        if norm_path in self.cache:
            cached_img = self.cache[norm_path]
            if cached_img.size().width() >= target_size.width() * 0.8:
                self.thumbnail_ready.emit(norm_path, cached_img)
                return

        if norm_path in self.active_requests:
            return

        self.active_requests.add(norm_path)
        worker = ThumbnailWorker(norm_path, target_size)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.error.connect(self._on_error)
        worker.signals.process_started.connect(self._on_process_started)
        worker.signals.process_finished.connect(self._on_process_finished)
        self.pool.start(worker)

    def _on_process_started(self, filepath: str, proc: object):
        norm_path = os.path.normpath(filepath)
        self.active_processes[norm_path] = proc

    def _on_process_finished(self, filepath: str):
        norm_path = os.path.normpath(filepath)
        if norm_path in self.active_processes:
            del self.active_processes[norm_path]

    def cancel_for_file(self, filepath: str):
        norm_path = os.path.normpath(filepath)
        if norm_path in self.active_processes:
            try:
                proc = self.active_processes[norm_path]
                proc.kill()
                logging.info(f"Killed active ffmpeg process for {filepath}")
            except Exception as e:
                logging.debug(f"Failed to kill ffmpeg for {filepath}: {e}")
            del self.active_processes[norm_path]
        if norm_path in self.active_requests:
            self.active_requests.remove(norm_path)

    def _on_finished(self, filepath: str, image: QImage):
        norm_path = os.path.normpath(filepath)
        if norm_path in self.active_requests:
            self.active_requests.remove(norm_path)
        
        # Limit cache size to 500 items to prevent memory leaks (FIFO eviction)
        if len(self.cache) >= 500:
            try:
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
            except Exception:
                pass
                
        self.cache[norm_path] = image
            
        self.thumbnail_ready.emit(norm_path, image)

    def _on_error(self, filepath: str, error_msg: str):
        norm_path = os.path.normpath(filepath)
        if norm_path in self.active_requests:
            self.active_requests.remove(norm_path)
        logging.debug(f"Failed to generate thumbnail for {filepath}: {error_msg}")

    def clear_cache(self):
        self.cache.clear()
        self.active_requests.clear()

    def rename_cache_key(self, old_path: str, new_path: str) -> None:
        """Переименовывает ключ в кэше миниатюр при переименовании файла, сохраняя миниатюру в RAM."""
        norm_old = os.path.normpath(old_path)
        if norm_old.startswith("\\\\?\\"): norm_old = norm_old[4:]
        norm_new = os.path.normpath(new_path)
        if norm_new.startswith("\\\\?\\"): norm_new = norm_new[4:]
        if norm_old in self.cache:
            self.cache[norm_new] = self.cache.pop(norm_old)
