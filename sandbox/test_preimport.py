import os
os.environ['TOKENIZERS_PARALLELISM']='false'
os.environ['TRANSFORMERS_VERBOSITY']='error'
import transformers
import sys
sys.path.append('src')
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRunnable, QThreadPool

app = QApplication(sys.argv)

class W(QRunnable):
    def run(self):
        print('A', flush=True)
        from modules.cleaner.logic_clip import CLIPSearcher
        print('B', flush=True)
        c=CLIPSearcher()
        print('C', flush=True)
        res=c.encode_text('хомяк')
        print('D', res.shape, flush=True)
        app.quit()

QThreadPool.globalInstance().start(W())
app.exec()
