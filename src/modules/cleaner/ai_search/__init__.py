"""
Пакет ai_search: декомпозированные компоненты ИИ-поиска и классификации медиафайлов.
"""
from .ui_ai_tab import AiClassificationTab, AiSearchTab, AiModelDownloaderThread
from .ui_samples_panel import (
    AiSamplesPanel, SearchTextEdit, AiFolderDropContainer, QCheckBoxCustom
)
from .ui_results_view import AiResultsView
from .ui_grid_view import (
    AiResultsGridView, AiCardDelegate, AiResultsListModel,
    AiResultsFilterProxyModel, HoverSettingsDialog, AiGridItem
)
from .logic_ai_actions import AiActionsController

__all__ = [
    "AiClassificationTab",
    "AiSearchTab",
    "AiModelDownloaderThread",
    "AiSamplesPanel",
    "SearchTextEdit",
    "AiFolderDropContainer",
    "QCheckBoxCustom",
    "AiResultsView",
    "AiResultsGridView",
    "AiCardDelegate",
    "AiResultsListModel",
    "AiResultsFilterProxyModel",
    "HoverSettingsDialog",
    "AiGridItem",
    "AiActionsController",
]
