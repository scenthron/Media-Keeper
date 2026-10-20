import unittest
from PyQt6.QtWidgets import QApplication
import sys

from src.modules.editor.video.helpers import format_ms_time
from src.modules.editor.video.ui_editor_widgets import WaveformProgressWidget

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

class TestEditorTimeline(unittest.TestCase):
    def test_format_ms_time(self):
        self.assertEqual(format_ms_time(0), "00:00.000")
        self.assertEqual(format_ms_time(1234), "00:01.234")
        self.assertEqual(format_ms_time(65432), "01:05.432")
        self.assertEqual(format_ms_time(3600000), "01:00:00.000")
        self.assertEqual(format_ms_time(3665432), "01:01:05.432")

    def test_waveform_progress_scale(self):
        widget = WaveformProgressWidget()
        self.assertEqual(widget.waveform_scale, 1.0)
        
        # Zoom in step
        new_scale = widget.zoom_in_waveform()
        self.assertAlmostEqual(new_scale, 1.5)
        self.assertAlmostEqual(widget.waveform_scale, 1.5)

        # Zoom in again
        widget.zoom_in_waveform()
        self.assertAlmostEqual(widget.waveform_scale, 2.0)

        # Reset zoom
        widget.reset_waveform_zoom()
        self.assertAlmostEqual(widget.waveform_scale, 1.0)

        # Zoom out
        widget.zoom_out_waveform()
        self.assertAlmostEqual(widget.waveform_scale, 0.6666666, places=1)

    def test_waveform_duration(self):
        widget = WaveformProgressWidget()
        self.assertEqual(widget.total_duration, 0)

        widget.set_duration(50000)
        self.assertEqual(widget.total_duration, 50000)

        # Provider overrides static duration if positive
        widget.set_duration_provider(lambda: 120000)
        self.assertEqual(widget.total_duration, 120000)

    def test_markers_operations(self):
        widget = WaveformProgressWidget()
        widget.add_marker(0.25)
        widget.add_marker(0.75)
        self.assertEqual(len(widget.markers), 2)
        self.assertEqual(widget.markers, [0.25, 0.75])

        widget.clear_markers()
        self.assertEqual(len(widget.markers), 0)


if __name__ == '__main__':
    unittest.main()
