import os
os.environ['TOKENIZERS_PARALLELISM']='false'
os.environ['TRANSFORMERS_VERBOSITY']='error'
import sys
sys.path.append('src')
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRunnable, QThreadPool

print("Importing in MAIN thread...", flush=True)
from modules.cleaner.logic_clip import CLIPSearcher
c = CLIPSearcher()
print("Importing DONE in MAIN thread.", flush=True)

app = QApplication(sys.argv)

class W(QRunnable):
    def run(self):
        try:
            print("2. Starting encoding in QThread...", flush=True)
            res = c.encode_text('хомяк')
            print("3. Encoded array shape:", res.shape if res is not None else None, flush=True)
        except Exception as e:
            print("EXCEPTION:", e, flush=True)
        finally:
            print("4. Exiting thread", flush=True)
            app.quit()

QThreadPool.globalInstance().start(W())
app.exec()
