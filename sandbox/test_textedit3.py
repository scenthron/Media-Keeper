import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QTextEdit, QPushButton
from PyQt6.QtCore import pyqtSignal, Qt, QTimer
class SearchTextEdit(QTextEdit):
    returnPressed = pyqtSignal()
    def keyPressEvent(self, event):
        print("KeyPress:", event.key())
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                event.accept()
                self.returnPressed.emit()
        else:
            super().keyPressEvent(event)

app = QApplication(sys.argv)
w = QWidget()
l = QVBoxLayout(w)
te = SearchTextEdit()
l.addWidget(te)
b = QPushButton("Search")
l.addWidget(b)
te.returnPressed.connect(lambda: print("RETURN PRESSED SIGNAL EMITTED!"))
b.clicked.connect(lambda: print("BUTTON CLICKED"))
w.show()

def sim():
    from PyQt6.QtGui import QKeyEvent
    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    QApplication.postEvent(te, event)
    QTimer.singleShot(100, app.quit)

QTimer.singleShot(500, sim)
app.exec()
