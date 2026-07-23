import sys
import os
os.environ['TOKENIZERS_PARALLELISM']='false'
os.environ['TRANSFORMERS_VERBOSITY']='error'
import transformers

from PyQt6.QtWidgets import QApplication
sys.path.append('src')
from modules.cleaner.logic_clip import CLIPSearcher

app = QApplication(sys.argv)
c = CLIPSearcher()
res = c.encode_text('хомяк')
print("SHAPE:", res.shape if res is not None else None)
app.quit()
