import sys
import unittest
from PyQt6.QtWidgets import QApplication, QGraphicsTextItem
from PyQt6.QtGui import QFont, QTextOption, QColor

class TestTextAlignment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_lazy_layout_bug(self):
        text_item = QGraphicsTextItem()
        track_name = '2_54632125309544.mp3'
        
        doc = text_item.document()
        option = QTextOption()
        option.setAlignment(__import__('PyQt6.QtCore').QtCore.Qt.AlignmentFlag.AlignCenter)
        option.setWrapMode(QTextOption.WrapMode.WrapAnywhere)
        doc.setDefaultTextOption(option)
        
        text_item.setFont(QFont('Segoe UI', 24, QFont.Weight.Bold))
        text_item.setTextWidth(1240)
        
        text_item.setPlainText(f'🎵\n{track_name}')
        doc.adjustSize()  # Force layout recalculation
        
        rect = text_item.boundingRect()
        self.assertLess(rect.width(), 1240)  # Actual text width should be less than the container width
        self.assertGreater(rect.width(), 50)
        self.assertLess(rect.height(), 200, 'Height is absurdly large, lazy layout bug is present!')

if __name__ == '__main__':
    unittest.main()

