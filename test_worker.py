import sys
import os
import logging
from PyQt6.QtCore import QCoreApplication
from src.modules.cleaner.workers import AiScanWorker
from src.modules.cleaner.logic_ai_classifier import AiClassifier
from src.modules.cleaner.logic_ai_cache import AiCache

app = QCoreApplication(sys.argv)
logging.basicConfig(level=logging.DEBUG)

class DummyClassifier:
    def __init__(self):
        self.ai = type('DummyAI', (), {'initialize_sessions': lambda *args, **kwargs: True, 'detect_and_extract_faces': lambda fp: [{'descriptor': [0.1, 0.2], 'bbox': (0,0,10,10)}]})()
        self.cache = AiCache()
        self.cache.get_file_faces = lambda fp, mt, sz: None
        self.cache.save_file_faces = lambda fp, mt, sz, faces: None

worker = AiScanWorker(["src/modules/cleaner"], DummyClassifier())
worker.is_cluster = True
worker.use_gpu = False
worker.use_cache = False
worker.threshold = 75.0

def on_finished(res):
    print("FINISHED FIRED. Results:", len(res))
    app.quit()

worker.finished.connect(on_finished)
worker.start()
app.exec()
