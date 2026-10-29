import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

import modules.cleaner.ui_ai_tab as old_tab
import modules.cleaner.ai_search as new_ai_search
from modules.cleaner.ai_search.ui_samples_panel import (
    SearchTextEdit, AiFolderDropContainer, QCheckBoxCustom, AiSamplesPanel
)
from modules.cleaner.ai_search.ui_results_view import AiResultsView
from modules.cleaner.ai_search.logic_ai_actions import AiActionsController
from modules.cleaner.ai_search.ui_ai_tab import AiClassificationTab, AiSearchTab


class TestAiTabDecomposition(unittest.TestCase):
    def test_01_exports_and_compatibility(self):
        """Проверяем реэкспорт всех классов через старый модуль ui_ai_tab."""
        self.assertIs(old_tab.AiClassificationTab, AiClassificationTab)
        self.assertIs(old_tab.AiSearchTab, AiSearchTab)
        self.assertIs(old_tab.AiSearchTab, AiClassificationTab)
        self.assertIs(old_tab.SearchTextEdit, SearchTextEdit)
        self.assertIs(old_tab.AiFolderDropContainer, AiFolderDropContainer)
        self.assertIs(old_tab.QCheckBoxCustom, QCheckBoxCustom)
        self.assertIs(old_tab.AiSamplesPanel, AiSamplesPanel)
        self.assertIs(old_tab.AiResultsView, AiResultsView)
        self.assertIs(old_tab.AiActionsController, AiActionsController)
        self.assertTrue(hasattr(old_tab, "ImageHoverToolTip"))
        self.assertTrue(hasattr(old_tab, "RefImagesListWidget"))

    def test_02_search_text_edit(self):
        """Проверяем виджет SearchTextEdit: авто-закрытие скобок и лимит длины."""
        edit = SearchTextEdit()
        self.assertEqual(edit.height(), 72)
        
        # Лимит длины 500 символов
        edit.setPlainText("a" * 600)
        self.assertEqual(len(edit.toPlainText()), 500)

    def test_03_checkbox_custom(self):
        """Проверяем кастомный чекбокс QCheckBoxCustom."""
        chk = QCheckBoxCustom()
        self.assertFalse(chk.isChecked())
        chk.setChecked(True)
        self.assertTrue(chk.isChecked())
        self.assertEqual(chk.text(), "✓")
        chk.setChecked(False)
        self.assertFalse(chk.isChecked())
        self.assertEqual(chk.text(), "")

    def test_04_results_view_populate_and_selection(self):
        """Проверяем AiResultsView: построение дерева, выбор и пост-фильтр."""
        view = AiResultsView()
        
        results_data = {
            "Cats": [
                {"path": "C:/fake/cat1.jpg", "confidence": 95.0, "size": 1024, "type": "general"},
                {"path": "C:/fake/cat2.jpg", "confidence": 60.0, "size": 2048, "type": "general"}
            ],
            "Dogs": [
                {"path": "C:/fake/dog1.jpg", "confidence": 85.0, "size": 4096, "type": "general"}
            ]
        }
        
        view.populate_results(results_data, is_cluster=False, scan_threshold=50.0)
        self.assertEqual(view.tree_results.topLevelItemCount(), 2)

        # Проверяем выделение всех
        view.select_all_results(True)
        selected = view.get_selected_files_paths()
        self.assertEqual(len(selected), 3)
        self.assertIn("C:/fake/cat1.jpg", selected)
        self.assertIn("C:/fake/dog1.jpg", selected)

        # Проверяем снятие выделения
        view.select_all_results(False)
        self.assertEqual(len(view.get_selected_files_paths()), 0)

        # Проверяем пост-фильтр (порог 80% должен скрыть cat2 с confidence 60%)
        view.on_post_filter_changed(80.0)
        root = view.tree_results.invisibleRootItem()
        cats_group = root.child(0)
        self.assertFalse(cats_group.child(0).isHidden())  # 95% >= 80%
        self.assertTrue(cats_group.child(1).isHidden())   # 60% < 80%

        # Проверяем удаление обработанных файлов
        view.remove_processed_files(["C:/fake/dog1.jpg"])
        self.assertEqual(view.tree_results.topLevelItemCount(), 1)  # Группа Dogs стала пустой и удалилась

    def test_05_actions_controller(self):
        """Проверяем вспомогательные операции AiActionsController."""
        stats = AiActionsController.calculate_selection_stats([])
        self.assertEqual(stats, (0, 0))

        mock_action_bar = MagicMock()
        AiActionsController.update_action_bar_state(mock_action_bar, count=5, has_destination=True)
        mock_action_bar.set_delete_button_enabled.assert_called_with(True)
        mock_action_bar.set_move_button_enabled.assert_called_with(True, move_to_enabled=True)

        AiActionsController.update_action_bar_state(mock_action_bar, count=0, has_destination=False)
        mock_action_bar.set_delete_button_enabled.assert_called_with(False)
        mock_action_bar.set_move_button_enabled.assert_called_with(False, move_to_enabled=False)

    def test_06_ai_classification_tab_properties(self):
        """Проверяем координатор AiClassificationTab и прокси-свойства для CleanerModule."""
        mock_cleaner = MagicMock()
        mock_cleaner.get_active_source_folders.return_value = ["C:/source"]
        mock_cleaner.source_folders = {"C:/source": {}}

        tab = AiClassificationTab(mock_cleaner)
        
        # Проверяем доступность прокси-свойств
        self.assertIsNotNone(tab.tree_results)
        self.assertIsNotNone(tab.preview_widget)
        self.assertIsNotNone(tab.lbl_selection_info)
        self.assertIsNotNone(tab.top_settings)
        self.assertIsNotNone(tab.page_ref)
        self.assertIsNotNone(tab.fast_search_widget)
        self.assertIsNotNone(tab.chips_map)
        self.assertIsNotNone(tab.action_bar)

        # Проверяем методы обратной совместимости
        self.assertEqual(tab.get_selected_files_paths(), [])
        tab.select_all_results(True)
        tab.select_all_results(False)


if __name__ == '__main__':
    unittest.main()
