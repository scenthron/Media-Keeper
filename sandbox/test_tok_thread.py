import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRunnable, QThreadPool
import os
os.environ['TOKENIZERS_PARALLELISM']='false'
sys.path.append('src')
from logic_paths import get_models_dir

app = QApplication(sys.argv)

class W(QRunnable):
    def run(self):
        from tokenizers import Tokenizer
        tokenizer_path = os.path.join(get_models_dir(), 'clip', 'text_multi', 'tokenizer.json')
        t = Tokenizer.from_file(tokenizer_path)
        enc = t.encode('хомяк')
        print("IDS:", enc.ids)
        app.quit()

QThreadPool.globalInstance().start(W())
app.exec()
