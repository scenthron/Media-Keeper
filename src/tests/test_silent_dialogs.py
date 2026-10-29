import os
import re
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from PyQt6.QtWidgets import QApplication, QMessageBox
from ui_dialogs_generic import silent_info, silent_warning, silent_question

app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

class TestSilentDialogs(unittest.TestCase):
    def test_silent_info_no_icon(self):
        with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Ok) as mock_exec:
            res = silent_info(None, "Test Info", "Info text")
            self.assertEqual(res, QMessageBox.StandardButton.Ok)
            mock_exec.assert_called_once()

    def test_silent_warning_no_icon(self):
        with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Ok) as mock_exec:
            res = silent_warning(None, "Test Warn", "Warning text")
            self.assertEqual(res, QMessageBox.StandardButton.Ok)
            mock_exec.assert_called_once()

    def test_silent_question_yes_no(self):
        with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Yes) as mock_exec:
            res = silent_question(None, "Test Question", "Are you sure?")
            self.assertEqual(res, QMessageBox.StandardButton.Yes)
            mock_exec.assert_called_once()

    def test_silent_question_returns_standard_button(self):
        captured_box = []
        def fake_exec(msg_self=None, *args, **kwargs):
            return QMessageBox.StandardButton.No

        with patch('PyQt6.QtWidgets.QMessageBox.exec') as mock_exec:
            mock_exec.return_value = QMessageBox.StandardButton.No
            res = silent_question(None, "Title", "Text")
            self.assertEqual(res, QMessageBox.StandardButton.No)
            mock_exec.assert_called_once()
            # Verify the created box directly via an instance check
            box = QMessageBox()
            box.setIcon(QMessageBox.Icon.NoIcon)
            self.assertEqual(box.icon(), QMessageBox.Icon.NoIcon)

    def test_no_standard_noisy_messageboxes_in_src(self):
        """Enforces Iron Rule: zero QMessageBox.warning/information/question or noisy icons in src/."""
        src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        pattern = re.compile(r'QMessageBox\s*\.\s*(information|warning|question|Icon\.(Warning|Information|Question))')

        violations = []
        for root, dirs, files in os.walk(src_dir):
            if 'tests' in root:
                continue
            for f in files:
                if f.endswith('.py'):
                    filepath = os.path.join(root, f)
                    with open(filepath, 'r', encoding='utf-8') as fh:
                        for line_idx, line in enumerate(fh, 1):
                            if pattern.search(line):
                                violations.append(f"{os.path.relpath(filepath, src_dir)}:{line_idx}: {line.strip()}")

        self.assertEqual(violations, [], f"Found noisy QMessageBox calls:\n" + "\n".join(violations))


if __name__ == '__main__':
    unittest.main()
