import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRunnable, QThreadPool

app = QApplication(sys.argv)

class W(QRunnable):
    def run(self):
        print('A', flush=True)
        import onnxruntime
        print('B', flush=True)
        app.quit()

QThreadPool.globalInstance().start(W())
app.exec()
