import os
os.environ['TOKENIZERS_PARALLELISM']='false'
os.environ['TRANSFORMERS_VERBOSITY']='error'
import sys
sys.path.append('src')
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRunnable, QThreadPool
from modules.cleaner.logic_clip import CLIPSearcher

app = QApplication(sys.argv)
c = CLIPSearcher()

class W(QRunnable):
    def run(self):
        print("Starting encoding in QThread...")
        res = c.encode_text('хомяк')
        print("Encoded array shape:", res.shape if res is not None else None)
        app.quit()

QThreadPool.globalInstance().start(W())
app.exec()
