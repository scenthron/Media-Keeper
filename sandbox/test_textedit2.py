import sys
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout
from ui_ai_tab import SearchTextEdit
app = QApplication(sys.argv)
w = QWidget()
l = QVBoxLayout(w)
te = SearchTextEdit()
l.addWidget(te)
def on_ret():
    with open(test_out.txt, w) as f:
        f.write(SUCCESS)
    QApplication.quit()
te.returnPressed.connect(on_ret)
win = w
win.show()
from PyQt6.QtCore import Qt
import threading, time
def test():
    time.sleep(1)
    from PyQt6.QtGui import QKeyEvent
    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    QApplication.postEvent(te, event)
threading.Thread(target=test).start()
app.exec()
