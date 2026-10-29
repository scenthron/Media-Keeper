import os
import sys
import glob
import json
import re
import pytest
from PyQt6.QtWidgets import QApplication

from config import AppContext
from languages.manager import LanguageManager
from modules.shared import ui_theme

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class MockCleaner:
    def __init__(self):
        self.source_folders = {}
        self.current_tab = 3
        self.status_bar = None
    def add_folder(self): pass
    def add_folder_path(self, p): pass
    def add_folder_paths(self, ps): pass
    def clear_folders(self): pass
    def get_active_source_folders(self): return []
    def move_selected(self): pass
    def prompt_move_selected(self): pass
    def delete_selected(self): pass
    def browse_dest(self): pass


def test_dictionary_symmetry():
    """Verify 100% key parity between ru/*.json and en/*.json."""
    lang_dir = AppContext.find_resource_dir("languages")
    assert lang_dir is not None and os.path.exists(lang_dir)
    
    ru_dir = os.path.join(lang_dir, "ru")
    en_dir = os.path.join(lang_dir, "en")
    
    ru_files = sorted(glob.glob(os.path.join(ru_dir, "*.json")))
    for rf in ru_files:
        fname = os.path.basename(rf)
        if fname == "meta.json":
            continue
        ef = os.path.join(en_dir, fname)
        assert os.path.exists(ef), f"Missing English counterpart for {fname}"
        
        with open(rf, "r", encoding="utf-8") as f:
            ru_dict = json.load(f)
        with open(ef, "r", encoding="utf-8") as f:
            en_dict = json.load(f)
            
        ru_keys = set(ru_dict.keys())
        en_keys = set(en_dict.keys())
        
        assert ru_keys == en_keys, f"Key mismatch in {fname}: missing in EN: {ru_keys - en_keys}, missing in RU: {en_keys - ru_keys}"


def test_ui_theme_tokens():
    """Verify theme tokens and style definitions."""
    assert ui_theme.BG_MAIN.startswith("#")
    assert ui_theme.COLOR_PRIMARY.startswith("#")
    assert ui_theme.COLOR_SUCCESS.startswith("#")
    assert ui_theme.COLOR_DANGER.startswith("#")
    
    assert "QSplitter::handle" in ui_theme.STYLE_SPLITTER
    assert "QSlider::groove" in ui_theme.STYLE_SLIDER_BLUE
    assert "QCheckBox" in ui_theme.STYLE_CHECKBOX
    assert "QPushButton" in ui_theme.STYLE_BTN_START
    assert "QMenu" in ui_theme.STYLE_CONTEXT_MENU
    assert "QTabWidget::pane" in ui_theme.STYLE_SETTINGS_TABS
    assert "QTreeWidget" in ui_theme.STYLE_TREE_RESULTS


def test_no_inline_is_ru_ternary():
    """Ensure no ternary `if AppContext.is_ru()` expressions remain in the modernized modules."""
    checked_files = [
        os.path.join("src", "modules", "sorter", "ui_journal.py"),
        os.path.join("src", "modules", "cleaner", "ui_fragment_tab.py"),
    ] + glob.glob(os.path.join("src", "modules", "cleaner", "ai_search", "*.py"))

    for fpath in checked_files:
        with open(fpath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for idx, line in enumerate(lines):
            clean_line = re.sub(r'is_running', '', line)
            clean_line = re.sub(r'#.*', '', clean_line)
            assert "is_ru" not in clean_line, f"Found unresolved is_ru in {fpath}:{idx+1}: {line.strip()}"


def test_retranslate_journal_dialog(qapp):
    """Verify JournalDialog dynamically retranslates all strings upon language switch."""
    from modules.sorter.ui_journal import JournalDialog
    
    # 1. Start in RU
    AppContext.LANG = "RU"
    AppContext.load_languages()
    dlg = JournalDialog()
    assert dlg.windowTitle() == "Журнал перемещений"
    assert dlg.table.horizontalHeaderItem(0).text() == "Дата/Время"
    assert dlg.btn_refresh.text() == "Обновить проверку"
    assert dlg.btn_close.text() == "Закрыть"
    
    # 2. Switch to EN
    AppContext.LANG = "EN"
    AppContext.load_languages()
    dlg.retranslate_ui()
    assert dlg.windowTitle() == "Move Journal"
    assert dlg.table.horizontalHeaderItem(0).text() == "Date/Time"
    assert dlg.btn_refresh.text() == "Refresh Check"
    assert dlg.btn_close.text() == "Close"
    
    # Restore RU
    AppContext.LANG = "RU"
    AppContext.load_languages()
    dlg.close()


def test_retranslate_fragment_tab(qapp):
    """Verify FragmentSearchTab retranslates dynamically."""
    from modules.cleaner.ui_fragment_tab import FragmentSearchTab
    
    cleaner = MockCleaner()
    cleaner.current_tab = 2
    
    AppContext.LANG = "RU"
    AppContext.load_languages()
    tab = FragmentSearchTab(cleaner)
    
    assert tab.btn_crop.text() == "Выбрать фрагмент"
    assert tab.btn_clear_frag.text() == "Очистить"
    assert tab.settings_tabs.tabText(0) == "Пиксельный"
    assert tab.settings_tabs.tabText(1) == "Векторный (SIFT)"
    assert tab.btn_filter.text() == "Сканировать типы файлов"
    
    # Switch to EN
    AppContext.LANG = "EN"
    AppContext.load_languages()
    tab.retranslate_ui()
    
    assert tab.btn_crop.text() == "Select fragment"
    assert tab.btn_clear_frag.text() == "Clear"
    assert tab.settings_tabs.tabText(0) == "Pixel"
    assert tab.settings_tabs.tabText(1) == "Vector (SIFT)"
    assert tab.btn_filter.text() == "Scan file types"
    
    # Restore RU
    AppContext.LANG = "RU"
    AppContext.load_languages()


def test_retranslate_ai_search_tab(qapp):
    """Verify AiSearchTab and its subcomponents retranslate dynamically."""
    from modules.cleaner.ai_search.ui_ai_tab import AiClassificationTab
    
    cleaner = MockCleaner()
    cleaner.current_tab = 3
    
    AppContext.LANG = "RU"
    AppContext.load_languages()
    tab = AiClassificationTab(cleaner)
    
    assert tab.samples_panel.btn_mode_ref.text() == "Поиск по образцам"
    assert tab.samples_panel.btn_mode_text.text() == "Поиск по тексту"
    assert tab.samples_panel.btn_mode_smart.text() == "Умный поиск"
    assert tab.params_tabs.tabText(0) == "Общие настройки"
    assert tab.params_tabs.tabText(1) == "Продвинутые"
    
    # Switch to EN
    AppContext.LANG = "EN"
    AppContext.load_languages()
    tab.retranslate_ui()
    
    assert tab.samples_panel.btn_mode_ref.text() == "Search by Samples"
    assert tab.samples_panel.btn_mode_text.text() == "Search by Text"
    assert tab.samples_panel.btn_mode_smart.text() == "Smart Search"
    assert tab.params_tabs.tabText(0) == "General"
    assert tab.params_tabs.tabText(1) == "Advanced"
    
    # Restore RU
    AppContext.LANG = "RU"
    AppContext.load_languages()
