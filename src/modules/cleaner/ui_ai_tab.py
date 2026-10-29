"""
Модуль-фасад ui_ai_tab (обратная совместимость).
Реэкспортирует классы декомпозированного пакета ai_search.
"""
from .ai_search.ui_ai_tab import (
    AiClassificationTab,
    AiSearchTab,
    AiModelDownloaderThread,
)
from .ai_search.ui_samples_panel import (
    AiSamplesPanel,
    SearchTextEdit,
    AiFolderDropContainer,
    QCheckBoxCustom,
)
from .ai_search.ui_results_view import AiResultsView
from .ai_search.logic_ai_actions import AiActionsController
from .ui_widgets import ImageHoverToolTip, RefImagesListWidget

__all__ = [
    "AiClassificationTab",
    "AiSearchTab",
    "AiModelDownloaderThread",
    "AiSamplesPanel",
    "SearchTextEdit",
    "AiFolderDropContainer",
    "QCheckBoxCustom",
    "ImageHoverToolTip",
    "RefImagesListWidget",
    "AiResultsView",
    "AiActionsController",
]
