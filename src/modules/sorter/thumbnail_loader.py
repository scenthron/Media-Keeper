import os
import logging
from utils_io import ensure_long_path
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, QThreadPool, QSize, Qt
from PyQt6.QtGui import QImage

class ThumbnailSignals(QObject):
    finished = pyqtSignal(str, QImage)  # Emits (filepath, scaled_image)
    error = pyqtSignal(str, str)        # Emits (filepath, error_message)

class ThumbnailWorker(QRunnable):
    def __init__(self, filepath: str, target_size: QSize):
        super().__init__()
        self.filepath = filepath
        self.target_size = target_size
        self.signals = ThumbnailSignals()

    def run(self):
        try:
            # We must load image as QImage in background thread.
            # QPixmap is GUI-only and will crash if loaded in QRunnable.
            image = QImage()
            loaded = False
            
            long_path = ensure_long_path(self.filepath)
            ext = os.path.splitext(long_path)[1].lower()
            video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.3gp', '.ts', '.m2ts', '.webm', '.mpg', '.mpeg', '.m4v']
            
            if ext in video_extensions:
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
                        proc = subprocess.run(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            startupinfo=startupinfo,
                            timeout=5
                        )
                        if proc.returncode == 0 and proc.stdout:
                            if image.loadFromData(proc.stdout):
                                loaded = True
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
        # Cache for loaded images (QImage)
        self.cache = {}

    def get_thumbnail(self, filepath: str, target_size: QSize):
        norm_path = os.path.normpath(filepath)
        
        # Check cache
        if norm_path in self.cache:
            # Check if cached size matches target size
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
        self.pool.start(worker)

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
        norm_new = os.path.normpath(new_path)
        if norm_old in self.cache:
            self.cache[norm_new] = self.cache.pop(norm_old)
