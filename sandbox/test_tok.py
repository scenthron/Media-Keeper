import sys
from PyQt6.QtWidgets import QApplication
import os
os.environ['TOKENIZERS_PARALLELISM']='false'
from tokenizers import Tokenizer
sys.path.append('src')
from logic_paths import get_models_dir

app = QApplication(sys.argv)
tokenizer_path = os.path.join(get_models_dir(), 'clip', 'text_multi', 'tokenizer.json')
t = Tokenizer.from_file(tokenizer_path)
enc = t.encode('хомяк')
print("IDS:", enc.ids)
app.quit()
