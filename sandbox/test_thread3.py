import os
os.environ['TOKENIZERS_PARALLELISM']='false'
os.environ['TRANSFORMERS_VERBOSITY']='error'
import sys
sys.path.append('src')
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRunnable, QThreadPool

app = QApplication(sys.argv)

class W(QRunnable):
    def run(self):
        try:
            print("1. Initializing in thread...")
            from modules.cleaner.logic_clip import CLIPSearcher
            c = CLIPSearcher()
            print("2. Starting encoding in QThread...")
            res = c.encode_text('хомяк')
            print("3. Encoded array shape:", res.shape if res is not None else None)
        except Exception as e:
            print("EXCEPTION:", e)
        finally:
            app.quit()

QThreadPool.globalInstance().start(W())
app.exec()
