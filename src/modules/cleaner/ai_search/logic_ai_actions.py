import os
import logging
from PyQt6.QtCore import Qt
from config import AppContext


class AiActionsController:
    """
    Контроллер действий над результатами ИИ-поиска:
    передача групп в Сортировщик, обновление состояния панели действий, сканирование расширений.
    """

    @staticmethod
    def send_group_to_sorter(group_item, parent_widget) -> bool:
        if not group_item:
            return False
        data = group_item.data(0, Qt.ItemDataRole.UserRole)
        if not data or not data.get("is_group", False):
            return False

        files = []
        for i in range(group_item.childCount()):
            child = group_item.child(i)
            c_data = child.data(0, Qt.ItemDataRole.UserRole)
            if c_data:
                path = c_data.get("path")
                if path and os.path.exists(path):
                    files.append(path)

        if not files:
            return False

        virtual_name = "ИИ Поиск"
        main_win = parent_widget.window() if hasattr(parent_widget, "window") else parent_widget
        if hasattr(main_win, "sorter_tab") and hasattr(main_win, "switch_tab"):
            main_win.sorter_tab.load_virtual_files(files, virtual_name)
            main_win.switch_tab(0)
            return True
        return False

    @staticmethod
    def calculate_selection_stats(selected_paths: list[str]) -> tuple[int, int]:
        count = len(selected_paths)
        size = sum(os.path.getsize(p) for p in selected_paths if os.path.exists(p))
        return count, size

    @staticmethod
    def update_action_bar_state(action_bar, count: int, has_destination: bool) -> None:
        has_selection = (count > 0)
        action_bar.set_delete_button_enabled(has_selection)
        action_bar.set_move_button_enabled(has_selection and has_destination, move_to_enabled=has_selection)

    @staticmethod
    def run_extension_scan_ai(cleaner, parent_widget, on_filter_applied_cb):
        folders = list(cleaner.source_folders.keys()) if hasattr(cleaner, "source_folders") else []
        if not folders:
            return None

        from ..workers import ExtensionScannerWorker
        from ..ui_dialogs import MatrixFilterDialog

        scanner = ExtensionScannerWorker(folders)

        def _on_finished(stats: dict):
            dlg = MatrixFilterDialog(stats, parent_widget)
            if dlg.exec():
                res = dlg.get_result()
                filter_config = {"mode": res["mode"], "exts": res["exts"]}
                count = len(res["exts"])
                if count == 0:
                    status_text = AppContext.tr("cln_filter_all") if AppContext.is_ru() else "All images"
                else:
                    key = "Вкл" if res["mode"] == "include" else "Искл"
                    status_text = f"Фильтр: {key} {count} типов" if AppContext.is_ru() else f"Filter: {key} {count} types"
                if on_filter_applied_cb:
                    on_filter_applied_cb(filter_config, status_text)

        scanner.finished.connect(_on_finished)
        scanner.start()
        return scanner
