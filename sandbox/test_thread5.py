import os
os.environ['TOKENIZERS_PARALLELISM']='false'
os.environ['TRANSFORMERS_VERBOSITY']='error'
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRunnable, QThreadPool

app = QApplication(sys.argv)

class W(QRunnable):
    def run(self):
        try:
            print("1. Importing transformers...", flush=True)
            from transformers import AutoTokenizer
            print("2. Done!", flush=True)
        except Exception as e:
            print("EXCEPTION:", e, flush=True)
        finally:
            app.quit()

QThreadPool.globalInstance().start(W())
app.exec()
