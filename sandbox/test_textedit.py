import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QTextEdit, QPushButton
from PyQt6.QtCore import pyqtSignal, Qt
class SearchTextEdit(QTextEdit):
    returnPressed = pyqtSignal()
    def keyPressEvent(self, event):
        with open(test_out.txt, a) as f:
            f.write(KEY:  + str(event.key()) + \n)
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                with open(test_out.txt, a) as f:
                    f.write(EMITTING\n)
                self.returnPressed.emit()
        else:
            super().keyPressEvent(event)
app = QApplication(sys.argv)
w = QWidget()
l = QVBoxLayout(w)
te = SearchTextEdit()
l.addWidget(te)
b = QPushButton(Search)
l.addWidget(b)
te.returnPressed.connect(lambda: open(test_out.txt, a).write(RECEIVED\n))
import threading, time
def test():
    time.sleep(1)
    from PyQt6.QtGui import QKeyEvent
    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    QApplication.postEvent(te, event)
    time.sleep(1)
    QApplication.quit()
threading.Thread(target=test).start()
app.exec()
