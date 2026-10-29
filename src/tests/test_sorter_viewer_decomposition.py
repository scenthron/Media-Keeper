import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt

app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

import modules.sorter.ui_viewer as old_ui_viewer
from modules.sorter.viewer_items import (
    safe_relpath, format_short_size, elide_text_to_two_lines,
    FileIconManager, SorterGridItemWidget, ThumbnailCard, SorterListItemWidget,
    SorterGridGroupSeparatorWidget, SorterListGroupSeparatorWidget,
    SorterPlaceholderWidget, find_main_app
)
from modules.sorter.viewer_media_player import ZoomableGraphicsView, SingleCanvasView
from modules.sorter.viewer_views import SorterBaseListView, SorterGridView, SorterListView
from modules.sorter.ui_viewer import SorterViewerArea, MediaViewer


class TestSorterViewerDecomposition(unittest.TestCase):
    def test_01_exports_and_compatibility(self):
        """Проверяем реэкспорт всех классов и совпадение псевдонимов."""
        self.assertIs(old_ui_viewer.SorterViewerArea, SorterViewerArea)
        self.assertIs(old_ui_viewer.MediaViewer, SorterViewerArea)
        self.assertIs(MediaViewer, SorterViewerArea)

        self.assertIs(old_ui_viewer.ZoomableGraphicsView, ZoomableGraphicsView)
        self.assertIs(old_ui_viewer.SingleCanvasView, ZoomableGraphicsView)
        self.assertIs(SingleCanvasView, ZoomableGraphicsView)

        self.assertIs(old_ui_viewer.SorterGridItemWidget, SorterGridItemWidget)
        self.assertIs(old_ui_viewer.ThumbnailCard, SorterGridItemWidget)
        self.assertIs(ThumbnailCard, SorterGridItemWidget)

        self.assertIs(old_ui_viewer.SorterListItemWidget, SorterListItemWidget)
        self.assertIs(old_ui_viewer.SorterGridView, SorterGridView)
        self.assertIs(old_ui_viewer.SorterListView, SorterListView)
        self.assertIs(old_ui_viewer.SorterBaseListView, SorterBaseListView)
        self.assertIs(old_ui_viewer.SorterPlaceholderWidget, SorterPlaceholderWidget)
        self.assertIs(old_ui_viewer.FileIconManager, FileIconManager)

    def test_02_utility_functions(self):
        """Проверяем функции форматирования и расчета путей."""
        self.assertEqual(format_short_size(0), "0Kb")
        self.assertEqual(format_short_size(1024), "1Kb")
        self.assertEqual(format_short_size(1024 * 1024), "1Mb")
        self.assertEqual(format_short_size(1024 * 1024 * 1024), "1Gb")

        # safe_relpath
        rel = safe_relpath("C:/Media/Photo/image.jpg", "C:/Media")
        self.assertIn("Photo", rel)

    def test_03_file_icon_manager_singleton(self):
        """Проверяем singleton FileIconManager."""
        mgr1 = FileIconManager.inst()
        mgr2 = FileIconManager.inst()
        self.assertIs(mgr1, mgr2)

    def test_04_items_instantiation(self):
        """Проверяем создание виджетов карточки плитки, строки списка и заглушки."""
        grid_item = SorterGridItemWidget("C:/fake/photo.jpg", 150)
        self.assertIsNotNone(grid_item.lbl_badge)
        self.assertEqual(grid_item.lbl_badge.text(), "JPG")

        list_item = SorterListItemWidget("C:/fake/video.mp4", 64)
        self.assertIsNotNone(list_item.lbl_badge)
        self.assertEqual(list_item.lbl_badge.text(), "MP4")

        placeholder = SorterPlaceholderWidget()
        self.assertIsNotNone(placeholder)

    def test_05_media_player_canvas(self):
        """Проверяем создание холста одиночного просмотра ZoomableGraphicsView."""
        canvas = ZoomableGraphicsView()
        self.assertIsNotNone(canvas.scene)
        self.assertIsNotNone(canvas.pixmap_item)
        self.assertIsNotNone(canvas.video_item)

    def test_06_views_instantiation(self):
        """Проверяем создание сеточного и списочного представлений."""
        from PyQt6.QtWidgets import QListWidget
        grid_view = SorterGridView()
        self.assertEqual(grid_view.viewMode(), QListWidget.ViewMode.IconMode)

        list_view = SorterListView()
        self.assertEqual(list_view.viewMode(), QListWidget.ViewMode.ListMode)

    def test_07_viewer_facade_coordination(self):
        """Проверяем главный координатор SorterViewerArea / MediaViewer."""
        mock_parent = QWidget()
        viewer = SorterViewerArea(mock_parent)

        self.assertIsNotNone(viewer.grid_view)
        self.assertIsNotNone(viewer.list_view)
        self.assertIsNotNone(viewer.single_view)
        self.assertIsNotNone(viewer.empty_placeholder_widget)

        # Проверяем переключение режимов через set_mode
        viewer.set_mode(0)
        self.assertEqual(viewer.current_view_mode, 0)

        viewer.set_mode(1)
        self.assertEqual(viewer.current_view_mode, 1)

        viewer.set_mode(2)
        self.assertEqual(viewer.current_view_mode, 2)

        viewer.set_mode(0)
        self.assertEqual(viewer.get_selected_files(), [])


if __name__ == '__main__':
    unittest.main()
