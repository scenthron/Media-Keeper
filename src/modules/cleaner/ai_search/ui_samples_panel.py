import os
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QScrollArea, QTabWidget, QStackedWidget, QComboBox, QTextEdit,
    QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

from config import AppContext
from ui_widgets_base import FlowLayout
from ui_dialogs_generic import silent_warning
from ..logic_ai_tags import AiTextTagsManager, parse_multi_tags, MultiTagHighlighter
from ..ui_ai_tags_dialog import AiTagManagerDialog
from ..logic_ai_classifier import load_ai_settings, save_ai_settings, get_ai_assets_dir
from ..ui_ai_references_panel import RefDropContainer, AiGroupChipWidget
from ..ui_ai_group_dialog import AiGroupSettingsDialog
from ..ui_ai_fast_search import AiFastSearchWidget


class SearchTextEdit(QTextEdit):
    returnPressed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setFixedHeight(72)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.textChanged.connect(self._check_length)
        
    def _check_length(self):
        max_len = 500
        if len(self.toPlainText()) > max_len:
            cursor = self.textCursor()
            pos = cursor.position()
            text = self.toPlainText()[:max_len]
            self.blockSignals(True)
            self.setPlainText(text)
            cursor.setPosition(min(pos, max_len))
            self.setTextCursor(cursor)
            self.blockSignals(False)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                event.accept()
                QTimer.singleShot(0, self.returnPressed.emit)
        elif event.text() == '(':
            super().keyPressEvent(event)
            self.insertPlainText(')')
            cursor = self.textCursor()
            cursor.movePosition(cursor.MoveOperation.Left)
            self.setTextCursor(cursor)
        elif event.text() == '[':
            super().keyPressEvent(event)
            self.insertPlainText(']')
            cursor = self.textCursor()
            cursor.movePosition(cursor.MoveOperation.Left)
            self.setTextCursor(cursor)
        else:
            super().keyPressEvent(event)


class AiFolderDropContainer(QWidget):
    folder_dropped = pyqtSignal(str)
    files_dropped = pyqtSignal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dropEvent(self, event: QDropEvent):
        paths = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.exists(path):
                if os.path.isdir(path):
                    self.folder_dropped.emit(path)
                else:
                    paths.append(path)
        if paths:
            self.files_dropped.emit(paths)


class QCheckBoxCustom(QPushButton):
    toggled = pyqtSignal(bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(16, 16)
        self.clicked.connect(self._on_clicked)
        self.update_style()
        
    def _on_clicked(self):
        self.toggled.emit(self.isChecked())
        self.update_style()
        
    def setChecked(self, checked):
        super().setChecked(checked)
        self.update_style()
        
    def update_style(self):
        if self.isChecked():
            self.setStyleSheet("background-color: #3b82f6; border: 1px solid #2563eb; border-radius: 3px; color: white; font-size: 10px; font-weight: bold;")
            self.setText("✓")
        else:
            self.setStyleSheet("background-color: #333; border: 1px solid #555; border-radius: 3px;")
            self.setText("")


class AiSamplesPanel(QWidget):
    """
    Панель управления образцами, мультитегами и автоматической группировкой.
    Включает переключение режимов поиска, быстрый поиск и менеджер образцов.
    """
    mode_changed = pyqtSignal(int)
    search_state_changed = pyqtSignal()
    text_search_requested = pyqtSignal(str)

    def __init__(self, classifier, parent=None):
        super().__init__(parent)
        self.classifier = classifier
        self.chips_map = {}
        self.tags_manager = AiTextTagsManager()
        self.active_tag_buttons = {}

        self._init_ui()
        self.reload_groups()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        mode_header = QHBoxLayout()
        self.btn_mode_ref = QPushButton("Поиск по образцам" if AppContext.is_ru() else "Search by Samples")
        self.btn_mode_text = QPushButton("Поиск по тексту" if AppContext.is_ru() else "Search by Text")
        self.btn_mode_smart = QPushButton("Умный поиск" if AppContext.is_ru() else "Smart Search")

        mode_style = """
            QPushButton {
                background-color: #2b2b2b;
                color: #888;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:checked {
                background-color: #3b82f6;
                color: white;
                border-color: #2563eb;
            }
        """
        for btn in (self.btn_mode_ref, self.btn_mode_text, self.btn_mode_smart):
            btn.setCheckable(True)
            btn.setStyleSheet(mode_style)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_mode_ref.setChecked(True)
        mode_header.addWidget(self.btn_mode_ref)
        mode_header.addWidget(self.btn_mode_text)
        mode_header.addWidget(self.btn_mode_smart)
        layout.addLayout(mode_header)

        self.mode_stack = QStackedWidget()
        layout.addWidget(self.mode_stack)

        # Страница 0: Образцы (Вкладки: Быстрый поиск и Менеджер)
        self.page_ref = QTabWidget()
        self.page_ref.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #444; border-radius: 4px; background: #1e1e1e; }
            QTabBar::tab { background: #2b2b2b; color: #aaa; padding: 6px 12px; border: 1px solid #444; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:selected { background: #3b82f6; color: white; border-color: #2563eb; }
        """)

        # Вкладка 0: Быстрый поиск
        self.fast_search_widget = AiFastSearchWidget()
        self.fast_search_widget.paths_changed.connect(lambda: self.search_state_changed.emit())
        self.page_ref.addTab(self.fast_search_widget, "Быстрый поиск" if AppContext.is_ru() else "Fast Search")

        # Вкладка 1: Менеджер образцов
        self.ref_manager_widget = QWidget()
        page_ref_layout = QVBoxLayout(self.ref_manager_widget)
        page_ref_layout.setContentsMargins(0, 4, 0, 0)
        page_ref_layout.setSpacing(4)

        ref_header = QHBoxLayout()
        page_ref_layout.addLayout(ref_header)
        ref_title = QLabel("Группы Образцов" if AppContext.is_ru() else "Reference Groups")
        ref_title.setStyleSheet("font-weight: bold; color: #888; font-size: 11px; font-family: 'Segoe UI';")
        ref_header.addWidget(ref_title)
        ref_header.addStretch()

        self.btn_create_ref = QPushButton("[+] Создать" if AppContext.is_ru() else "[+] Create")
        self.btn_create_ref.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_create_ref.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6; 
                color: white; 
                border: none; 
                padding: 2px 8px; 
                border-radius: 3px; 
                font-weight: bold; 
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
        """)
        self.btn_create_ref.clicked.connect(self.create_group)
        ref_header.addWidget(self.btn_create_ref)

        self.scroll_ref = QScrollArea()
        self.scroll_ref.setWidgetResizable(True)
        self.scroll_ref.setStyleSheet("QScrollArea { border: 1px solid #333; background-color: #111; border-radius: 4px; }")

        self.ref_container = RefDropContainer()
        self.ref_container.dump_dropped.connect(self.add_external_dump)
        self.ref_container.setStyleSheet("background-color: #111;")
        self.group_list_layout_ai = QVBoxLayout(self.ref_container)
        self.group_list_layout_ai.setContentsMargins(5, 5, 5, 5)
        self.group_list_layout_ai.setSpacing(4)
        self.group_list_layout_ai.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_ref.setWidget(self.ref_container)
        page_ref_layout.addWidget(self.scroll_ref)

        self.page_ref.addTab(self.ref_manager_widget, "Менеджер образцов" if AppContext.is_ru() else "Reference Manager")
        self.page_ref.currentChanged.connect(lambda: self.search_state_changed.emit())
        self.mode_stack.addWidget(self.page_ref)

        # Страница 1: Поиск по тексту
        self.page_text = QWidget()
        page_text_layout = QVBoxLayout(self.page_text)
        page_text_layout.setContentsMargins(0, 5, 0, 0)
        page_text_layout.setSpacing(8)
        page_text_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        lbl_text_search = QLabel("Введите текстовый запрос для поиска:" if AppContext.is_ru() else "Enter text query for search:")
        lbl_text_search.setStyleSheet("color: #ccc; font-size: 12px;")
        page_text_layout.addWidget(lbl_text_search)

        self.line_text_search = SearchTextEdit()
        self.line_text_search.setPlaceholderText(
            "Например: дом(30), дождь, -люди, -собака(80), [Домашние животные: кошка(70)]" if AppContext.is_ru()
            else "E.g.: house(30), rain, -people, -dog(80), [Pets: cat(70)]"
        )
        self.line_text_search.setStyleSheet("""
            QTextEdit {
                background-color: #222;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px;
                color: white;
                font-family: 'Consolas', 'Courier New';
                font-size: 13px;
            }
            QTextEdit:focus { border-color: #3b82f6; }
        """)
        self.text_highlighter = MultiTagHighlighter(self.line_text_search.document())
        page_text_layout.addWidget(self.line_text_search)

        tags_action_layout = QHBoxLayout()
        is_ru = AppContext.is_ru()
        self.btn_manage_tags = QPushButton("⚙️ " + ("Теги" if is_ru else "Tags"))
        self.btn_manage_tags.setToolTip("Управление текстовыми тегами" if is_ru else "Manage text tags")
        self.btn_manage_tags.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_manage_tags.setStyleSheet("""
            QPushButton { background-color: #333; border: 1px solid #555; border-radius: 4px; padding: 4px 8px; color: #ccc; }
            QPushButton:hover { background-color: #444; color: white; }
        """)
        self.btn_manage_tags.clicked.connect(self.open_tag_manager)

        self.btn_info_tags = QPushButton("ℹ️")
        self.btn_info_tags.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_info_tags.setStyleSheet("QPushButton { background: transparent; border: none; font-size: 16px; }")
        self.btn_info_tags.clicked.connect(self.show_tags_info)

        self.btn_text_search = QPushButton("Найти" if AppContext.is_ru() else "Find")
        self.btn_text_search.setFixedHeight(32)
        self.btn_text_search.setFixedWidth(100)
        self.btn_text_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_text_search.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #2563eb; }
        """)

        tags_action_layout.addWidget(self.btn_manage_tags)
        tags_action_layout.addWidget(self.btn_info_tags)
        tags_action_layout.addStretch()
        tags_action_layout.addWidget(self.btn_text_search)
        page_text_layout.addLayout(tags_action_layout)

        self.tags_scroll = QScrollArea()
        self.tags_scroll.setWidgetResizable(True)
        self.tags_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.tags_container = QWidget()
        self.tags_container.setStyleSheet("background: transparent;")
        self.tags_flow = FlowLayout(self.tags_container, margin=0, spacing=6)
        self.tags_scroll.setWidget(self.tags_container)
        page_text_layout.addWidget(self.tags_scroll)

        self.mode_stack.addWidget(self.page_text)

        # Страница 2: Умный поиск (Автокластеризация)
        self.page_smart = QWidget()
        page_smart_layout = QVBoxLayout(self.page_smart)
        page_smart_layout.setContentsMargins(0, 5, 0, 0)
        page_smart_layout.setSpacing(8)
        page_smart_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        lbl_smart_title = QLabel("Автоматическая группировка" if AppContext.is_ru() else "Automatic Grouping")
        lbl_smart_title.setStyleSheet("color: #ccc; font-weight: bold; font-size: 12px;")
        page_smart_layout.addWidget(lbl_smart_title)

        lbl_smart_desc = QLabel(
            "Умный поиск позволяет находить похожие объекты и лица в указанных каталогах без использования заранее подготовленных Образцов. ИИ автоматически сгруппирует похожие файлы."
            if AppContext.is_ru() else
            "Smart search automatically groups similar objects and faces without using prepared references."
        )
        lbl_smart_desc.setWordWrap(True)
        lbl_smart_desc.setStyleSheet("color: #888; font-size: 11px;")
        page_smart_layout.addWidget(lbl_smart_desc)

        smart_type_layout = QHBoxLayout()
        lbl_smart_type = QLabel("Тип поиска:" if AppContext.is_ru() else "Search Type:")
        lbl_smart_type.setStyleSheet("color: #ccc; font-size: 12px;")
        smart_type_layout.addWidget(lbl_smart_type)

        self.combo_auto_type = QComboBox()
        self.combo_auto_type.addItem("По людям" if AppContext.is_ru() else "By People", "face")
        self.combo_auto_type.addItem("По изображениям" if AppContext.is_ru() else "By Images", "general")
        self.combo_auto_type.setStyleSheet("QComboBox { background-color: #2b2b2b; color: white; border: 1px solid #444; border-radius: 4px; padding: 2px 5px; font-size: 11px; height: 22px; }")
        self.combo_auto_type.setFixedWidth(130)
        smart_type_layout.addWidget(self.combo_auto_type)
        smart_type_layout.addStretch()

        page_smart_layout.addLayout(smart_type_layout)
        self.mode_stack.addWidget(self.page_smart)

        self.refresh_tag_chips()

        self.btn_mode_ref.clicked.connect(lambda: self._switch_mode(0))
        self.btn_mode_text.clicked.connect(lambda: self._switch_mode(1))
        self.btn_mode_smart.clicked.connect(lambda: self._switch_mode(2))

        self.line_text_search.returnPressed.connect(self._trigger_text_search)
        self.btn_text_search.clicked.connect(self._trigger_text_search)

    def _switch_mode(self, index: int):
        self.mode_stack.setCurrentIndex(index)
        self.btn_mode_ref.setChecked(index == 0)
        self.btn_mode_text.setChecked(index == 1)
        self.btn_mode_smart.setChecked(index == 2)
        self.mode_changed.emit(index)
        self.search_state_changed.emit()

    def _trigger_text_search(self):
        query = self.get_active_text_query()
        if not query:
            silent_warning(
                self,
                "Внимание" if AppContext.is_ru() else "Warning",
                "Введите текстовый запрос или выберите тег." if AppContext.is_ru() else "Please enter a query or select a tag."
            )
            return
        self.text_search_requested.emit(query)

    def get_active_text_query(self) -> str:
        query = self.line_text_search.toPlainText().strip()
        active_tags = []
        for name, btn in self.active_tag_buttons.items():
            if btn.isChecked():
                body = self.tags_manager.get_tags().get(name)
                if body:
                    active_tags.append(f"[{name}: {body}]")
        return ", ".join(filter(None, [query] + active_tags))

    def has_enabled_groups(self) -> bool:
        mode = self.mode_stack.currentIndex()
        if mode == 0:
            if self.page_ref.currentIndex() == 0:
                return len(self.fast_search_widget.get_pos_paths()) > 0
            return any(widget.chk.isChecked() for widget in self.chips_map.values())
        return False

    def reload_groups(self):
        self.chips_map.clear()
        while self.group_list_layout_ai.count():
            item = self.group_list_layout_ai.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        settings = load_ai_settings()
        groups = settings.get("groups", {})
        assets_dir = get_ai_assets_dir()

        to_delete = []
        for name, info in groups.items():
            path = info.get("path")
            if path:
                basename = os.path.basename(path)
                local_path = os.path.join(assets_dir, basename)
                if os.path.exists(local_path):
                    path = local_path
                    info["path"] = path
            if not path or not os.path.exists(path):
                to_delete.append(name)

        if to_delete:
            for name in to_delete:
                del groups[name]
            settings["groups"] = groups
            save_ai_settings(settings)

        # Авто-добавление из папки Ai_assets
        added_new = False
        if os.path.exists(assets_dir):
            for f in os.listdir(assets_dir):
                if f.lower().endswith(".mkaidump"):
                    path = os.path.join(assets_dir, f)
                    path_norm = os.path.normpath(path).lower()
                    found = any(os.path.normpath(info.get("path", "")).lower() == path_norm for info in groups.values())
                    if not found:
                        name = f.replace(".hash.mkaidump", "").replace(".mkaidump", "")
                        orig_name = name
                        c = 1
                        while name in groups:
                            name = f"{orig_name}_{c}"
                            c += 1
                        groups[name] = {"enabled": True, "path": path}
                        added_new = True

        if added_new:
            settings["groups"] = groups
            save_ai_settings(settings)

        sorted_groups = sorted(groups.items(), key=lambda item: (not item[1].get("enabled", True), item[0].lower()))

        for name, info in sorted_groups:
            status, count = self.classifier.get_group_status(name)
            is_face = info.get("type") == "face"
            is_enabled = info.get("enabled", True)

            is_hash = info.get("is_hash_only", False)
            if not is_hash and info.get("path") and os.path.exists(info["path"]):
                from ..logic_ai_dump import load_dump_info
                dump_info = load_dump_info(info["path"])
                is_hash = dump_info.get("is_hash_only", False)
                is_face = dump_info.get("type", "face") == "face"

            display_name = f"[Hash] {name}" if is_hash else name
            norm_assets = os.path.normpath(assets_dir).lower()
            path_norm = os.path.normpath(info.get("path", "")).lower() if info.get("path") else ""
            is_external = not (path_norm and path_norm.startswith(norm_assets))

            widget = AiGroupChipWidget(display_name, is_enabled, is_face, status, count, is_external=is_external, parent=self)
            widget.state_changed.connect(self.on_group_state_changed)
            widget.settings_clicked.connect(lambda n=name: self.open_edit_group_dialog(n))
            widget.remove_clicked.connect(self.remove_group_from_list)
            self.group_list_layout_ai.addWidget(widget)
            self.chips_map[name] = widget

        self.search_state_changed.emit()

    def remove_group_from_list(self, group_name: str):
        settings = load_ai_settings()
        if "groups" in settings and group_name in settings["groups"]:
            del settings["groups"][group_name]
            save_ai_settings(settings)
        self.reload_groups()

    def on_group_state_changed(self, group_name: str, is_enabled: bool):
        settings = load_ai_settings()
        if group_name in settings.get("groups", {}):
            settings["groups"][group_name]["enabled"] = is_enabled
            save_ai_settings(settings)

        if group_name in self.chips_map:
            self.chips_map[group_name].set_error_highlight(False)

        self.search_state_changed.emit()

    def open_edit_group_dialog(self, group_name: str):
        dlg = AiGroupSettingsDialog(self.classifier, group_name, self)
        dlg.exec()
        self.reload_groups()

    def add_external_dump(self, path: str):
        settings = load_ai_settings()
        groups = settings.get("groups", {})

        name = os.path.basename(path).replace(".hash.mkaidump", "").replace(".mkaidump", "")
        original_name = name
        counter = 1
        while name in groups:
            name = f"{original_name}_{counter}"
            counter += 1

        groups[name] = {"enabled": True, "path": path}
        settings["groups"] = groups
        save_ai_settings(settings)
        self.reload_groups()

    def create_group(self):
        dlg = AiGroupSettingsDialog(self.classifier, None, self)
        dlg.exec()
        self.reload_groups()

    def open_tag_manager(self):
        dlg = AiTagManagerDialog(self.tags_manager, self)
        dlg.tags_changed.connect(self.refresh_tag_chips)
        dlg.exec()

    def show_tags_info(self):
        from PyQt6.QtWidgets import QMessageBox
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.NoIcon)
        msg.setWindowTitle("Справка по текстовым тегам" if AppContext.is_ru() else "Text Tags Help")

        ru_text = (
            "<b>Сложные поисковые запросы (Мультитеги):</b><br>"
            "Вы можете вводить сложные запросы прямо в строку поиска, используя квадратные скобки и двоеточие.<br>"
            "Синтаксис: <b>[Заголовок: запрос 1, запрос 2, ...]</b><br>"
            "<i>Пример:</i> запрос <b>[Домашние животные: кошка, собака, попугай]</b> создаст одну колонку результатов "
            "с именем «Домашние животные», в которой будут собраны все 3 вида животных.<br><br>"
            "<b>Индивидуальные пороги параметров (число):</b><br>"
            "Вы можете точно настраивать порог срабатывания для каждого конкретного слова, приписав порог в круглых скобках (без пробела).<br>"
            "<i>Пример позитивного:</i> <b>девушка(80)</b> — картинка пройдет, если сходство с девушкой ≥ 80%. (Чем выше число, тем строже отсев).<br>"
            "<i>Пример негативного (толерантность):</i> <b>-парень(50)</b> — картинка будет отброшена, если сходство с парнем ≥ 50%. (Чем <b>ниже</b> число, тем строже отсев мусора).<br><br>"
            "<b>Система сохраненных тегов:</b><br>"
            "Теги — это удобные закладки для ваших частых запросов.<br>"
            "Заголовок тега формирует название группы результатов, в которую будет выводиться поиск:<br>"
            "• По <i>одиночному тегу</i> (например, «Собака») — группа будет называться так же.<br>"
            "• По <i>мультитегу</i> — заголовок тега станет именем группы для множественного запроса.<br><br>"
            "Вы можете комбинировать обычный текст в строке поиска с выбранными тегами. Каждый отдельный тег или запрос "
            "создает свою независимую колонку результатов."
        )

        en_text = (
            "<b>Complex Search Queries (Multi-tags):</b><br>"
            "You can enter complex queries directly into the search bar using square brackets and a colon.<br>"
            "Syntax: <b>[Header: query 1, query 2, ...]</b><br>"
            "<i>Example:</i> query <b>[Pets: cat, dog, parrot]</b> creates a single result group "
            "named 'Pets' containing all 3 types of animals.<br><br>"
            "<b>Individual Parameter Thresholds (number):</b><br>"
            "You can fine-tune the match threshold for any specific word by appending a number in round brackets (no space).<br>"
            "<i>Positive example:</i> <b>girl(80)</b> — passes if similarity is ≥ 80%. (Higher = stricter filtering).<br>"
            "<i>Negative example (tolerance):</i> <b>-boy(50)</b> — drops the image if similarity is ≥ 50%. (Lower = stricter filtering).<br><br>"
            "<b>Saved Tags System:</b><br>"
            "Tags are convenient bookmarks for your frequent queries.<br>"
            "The tag header sets the name of the result group for the search:<br>"
            "• For a <i>single tag</i> (e.g., 'Dog') — the group will have the same name.<br>"
            "• For a <i>multi-tag</i> — the tag header becomes the group name for multiple queries.<br><br>"
            "You can combine plain text in the search bar with selected tags. Each individual tag or query "
            "creates its own independent result column."
        )

        msg.setText(ru_text if AppContext.is_ru() else en_text)
        msg.exec()

    def refresh_tag_chips(self):
        while self.tags_flow.count():
            item = self.tags_flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.active_tag_buttons.clear()
        tags = self.tags_manager.get_tags()
        for name, body in tags.items():
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

            is_multi = "," in body
            base_color = "#d97706" if is_multi else "#166534"
            hover_color = "#f59e0b" if is_multi else "#15803d"

            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: #888;
                    border: 1px solid #444;
                    border-radius: 12px;
                    padding: 4px 10px;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    border-color: {hover_color};
                    color: #eee;
                }}
                QPushButton:checked {{
                    background-color: {base_color};
                    color: white;
                    border: 1px solid {hover_color};
                }}
            """)

            self.active_tag_buttons[name] = btn
            self.tags_flow.addWidget(btn)
