import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt
from modules.sorter.logic_hotkeys import HotkeyRegistry, HotkeyAction


class MockHostWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.action_called = False
        self.action_mode = None

    def test_callback(self) -> None:
        self.action_called = True


class TestHotkeyRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_registration_and_apply(self) -> None:
        registry = HotkeyRegistry("test_scope")
        action = HotkeyAction(
            action_id="test_action",
            label_ru="Тестовое действие",
            label_en="Test action",
            default_key="Ctrl+T",
            callback_name="test_callback",
            group="test",
        )
        registry.register(action)
        
        host = MockHostWidget()
        registry.apply_all(host)
        
        self.assertIn("test_action", registry._shortcuts)
        shortcut = registry._shortcuts["test_action"]
        self.assertEqual(shortcut.key().toString(), "Ctrl+T")
        
        # Test override loading
        registry.load_overrides({"test_action": "Ctrl+Shift+T"})
        registry.apply_all(host)
        
        shortcut_override = registry._shortcuts["test_action"]
        self.assertEqual(shortcut_override.key().toString(), "Ctrl+Shift+T")
        
        # Test save overrides
        overrides = registry.save_overrides()
        self.assertEqual(overrides, {"test_action": "Ctrl+Shift+T"})

    def test_set_key(self) -> None:
        registry = HotkeyRegistry("test_scope")
        action = HotkeyAction(
            action_id="test_action",
            label_ru="Тестовое действие",
            label_en="Test action",
            default_key="Ctrl+T",
            callback_name="test_callback",
            group="test",
        )
        registry.register(action)
        
        host = MockHostWidget()
        registry.apply_all(host)
        
        success = registry.set_key("test_action", "Ctrl+Y")
        self.assertTrue(success)
        self.assertEqual(registry.get_effective_key("test_action"), "Ctrl+Y")
        
        shortcut = registry._shortcuts["test_action"]
        self.assertEqual(shortcut.key().toString(), "Ctrl+Y")

    def test_mode_filtering(self) -> None:
        registry = HotkeyRegistry("test_scope")
        action = HotkeyAction(
            action_id="mode_action",
            label_ru="Режимное действие",
            label_en="Mode action",
            default_key="M",
            callback_name="test_callback",
            group="test",
            enabled_in_modes={0},  # active only in mode 0 (single)
        )
        registry.register(action)
        
        host = MockHostWidget()
        registry.apply_all(host)
        
        shortcut = registry._shortcuts["mode_action"]
        
        # Update to mode 0 -> enabled
        registry.update_mode(0)
        self.assertTrue(shortcut.isEnabled())
        
        # Update to mode 1 -> disabled
        registry.update_mode(1)
        self.assertFalse(shortcut.isEnabled())


if __name__ == '__main__':
    unittest.main()
