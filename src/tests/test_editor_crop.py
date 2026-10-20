import unittest
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QRectF, QPointF

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from src.modules.editor.video.ui_editor_items import CropHandle, CropFrameItem
from src.modules.editor.video.ui_editor import VideoEditorWidget


class TestEditorCrop(unittest.TestCase):
    def test_crop_handle_cursors(self):
        h_tl = CropHandle(handle_type='tl')
        h_tr = CropHandle(handle_type='tr')
        h_bl = CropHandle(handle_type='bl')
        h_br = CropHandle(handle_type='br')
        h_t = CropHandle(handle_type='t')
        h_b = CropHandle(handle_type='b')
        h_l = CropHandle(handle_type='l')
        h_r = CropHandle(handle_type='r')

        self.assertEqual(h_tl.cursor().shape(), Qt.CursorShape.SizeFDiagCursor)
        self.assertEqual(h_br.cursor().shape(), Qt.CursorShape.SizeFDiagCursor)
        self.assertEqual(h_tr.cursor().shape(), Qt.CursorShape.SizeBDiagCursor)
        self.assertEqual(h_bl.cursor().shape(), Qt.CursorShape.SizeBDiagCursor)

        self.assertEqual(h_t.cursor().shape(), Qt.CursorShape.SizeVerCursor)
        self.assertEqual(h_b.cursor().shape(), Qt.CursorShape.SizeVerCursor)
        self.assertEqual(h_l.cursor().shape(), Qt.CursorShape.SizeHorCursor)
        self.assertEqual(h_r.cursor().shape(), Qt.CursorShape.SizeHorCursor)

    def test_crop_frame_item(self):
        frame = CropFrameItem()
        frame.setRect(QRectF(10, 20, 300, 200))
        self.assertEqual(frame._rect, QRectF(10, 20, 300, 200))
        
        # Advance dash test
        old_dash = frame._dash_offset
        frame.advance_dash(1)
        self.assertEqual(frame._dash_offset, (old_dash + 1) % 20)

    def test_editor_crop_handles_sync(self):
        w = VideoEditorWidget()
        self.assertEqual(len(w.crop_handles), 8)

        # Sync to rect: (50, 60, 200, 100)
        w._sync_crop_handles_to_rect(50, 60, 200, 100)
        self.assertEqual(w.handle_tl.pos(), QPointF(50, 60))
        self.assertEqual(w.handle_tr.pos(), QPointF(250, 60))
        self.assertEqual(w.handle_bl.pos(), QPointF(50, 160))
        self.assertEqual(w.handle_br.pos(), QPointF(250, 160))

        # Midpoints
        self.assertEqual(w.handle_t.pos(), QPointF(150, 60))
        self.assertEqual(w.handle_b.pos(), QPointF(150, 160))
        self.assertEqual(w.handle_l.pos(), QPointF(50, 110))
        self.assertEqual(w.handle_r.pos(), QPointF(250, 110))

    def test_edge_handle_movement(self):
        w = VideoEditorWidget()
        from PyQt6.QtWidgets import QGraphicsRectItem
        rect_item = QGraphicsRectItem(0, 0, 1000, 1000)
        w.video_item = rect_item

        w._sync_crop_handles_to_rect(100, 100, 400, 300)
        self.assertEqual(w.handle_tl.pos(), QPointF(100, 100))
        self.assertEqual(w.handle_br.pos(), QPointF(500, 400))

        # Move top edge handle from Y=100 down to Y=150
        w.handle_t.setPos(300, 150)
        w._on_crop_moved(w.handle_t)

        self.assertEqual(w.handle_tl.x(), 100)
        self.assertEqual(w.handle_tl.y(), 150)
        self.assertEqual(w.handle_br.x(), 500)
        self.assertEqual(w.handle_br.y(), 400)
        self.assertEqual(w.handle_t.pos(), QPointF(300, 150))

        # Move right edge handle from X=500 to X=600
        w.handle_r.setPos(600, 275)
        w._on_crop_moved(w.handle_r)

        self.assertEqual(w.handle_tl.x(), 100)
        self.assertEqual(w.handle_tl.y(), 150)
        self.assertEqual(w.handle_br.x(), 600)
        self.assertEqual(w.handle_br.y(), 400)
        self.assertEqual(w.handle_r.pos(), QPointF(600, 275))


if __name__ == '__main__':
    unittest.main()
