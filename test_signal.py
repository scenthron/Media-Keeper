from PyQt6.QtCore import QObject, pyqtSignal, QThread
from PyQt6.QtWidgets import QApplication
import numpy as np
import sys

app = QApplication(sys.argv)

class Worker(QThread):
    finished = pyqtSignal(dict)
    def run(self):
        try:
            results = {"Face 1": [{"confidence": np.float32(99.9)}]}
            self.finished.emit(results)
            print("Emitted successfully")
        except Exception as e:
            print("Worker Error:", e)

class Receiver(QObject):
    def on_finished(self, res):
        print("Received:", res)
        app.quit()

w = Worker()
r = Receiver()
w.finished.connect(r.on_finished)
w.start()
app.exec()
