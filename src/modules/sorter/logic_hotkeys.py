"""
Система горячих клавиш Media Keeper — HotkeyRegistry.

Архитектура:
  - HotkeyAction  — дескриптор одного действия (id, клавиша, контекст, ...)
  - HotkeyRegistry — реестр действий одного модуля/раздела приложения
  - SorterHotkeysMixin — инициализирует реестр для модуля Sorter

Принцип изоляции по разделам:
  Каждый модуль создаёт СВОЙ экземпляр HotkeyRegistry(scope_id="...").
  По умолчанию используется контекст WidgetWithChildrenShortcut — хоткей
  срабатывает только когда фокус находится внутри виджета данного модуля.
  Это позволяет назначить одну и ту же клавишу разным функциям в разных
  разделах программы без конфликтов.

  Исключение: глобальные действия (напр. выход из полноэкранного режима)
  используют ApplicationShortcut и срабатывают из любого раздела.

Персистентность:
  Пользовательские переопределения клавиш хранятся в settings.ini в секции
  [Hotkeys_<scope_id>], например [Hotkeys_sorter].
  Секция пишется только при наличии переопределений — обратная совместимость
  гарантирована: пустая или отсутствующая секция = дефолтные клавиши.

Расширение (будущее):
  Для добавления нового хоткея достаточно одного вызова registry.register().
  UI настройки (таблица в диалоге настроек) планируется отдельно — реестр
  уже предоставляет все нужные данные через get_all_actions() и set_key().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable
import os
import logging

from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtCore import Qt


# ---------------------------------------------------------------------------
# HotkeyAction — дескриптор одного действия
# ---------------------------------------------------------------------------

@dataclass
class HotkeyAction:
    """
    Описание одного горячего клавиши.

    action_id       — уникальный идентификатор внутри scope (напр. "next_file")
    label_ru        — человекочитаемое название (для будущего UI настройки)
    label_en        — то же, на английском
    default_key     — строка QKeySequence по умолчанию, напр. "Right", "F1"
    callback_name   — имя метода на хост-виджете (host), который будет вызван
    group           — логическая группа: "navigation"|"playback"|"view"|"file"
    context         — область действия шортката (Qt.ShortcutContext)
    enabled_in_modes— набор индексов режимов (0=single, 1=grid, 2=list),
                      в которых хоткей активен. None = активен во всех режимах.
    """
    action_id: str
    label_ru: str
    label_en: str
    default_key: str
    callback_name: str
    group: str
    context: Qt.ShortcutContext = Qt.ShortcutContext.WidgetWithChildrenShortcut
    enabled_in_modes: set[int] | None = None


# ---------------------------------------------------------------------------
# HotkeyRegistry — реестр горячих клавиш одного модуля
# ---------------------------------------------------------------------------

class HotkeyRegistry:
    """
    Реестр горячих клавиш для одного раздела/модуля приложения.

    Использование:
        registry = HotkeyRegistry("sorter")
        registry.register(HotkeyAction("next_file", ..., default_key="Right", ...))
        registry.load_overrides(config.get("hotkeys_sorter", {}))
        registry.apply_all(host_widget)

        # При смене режима просмотра:
        registry.update_mode(mode_idx)

        # Для будущего UI настройки:
        registry.set_key("next_file", "Shift+Right")
        overrides = registry.save_overrides()  # → сохранить в config
    """

    def __init__(self, scope_id: str) -> None:
        self.scope_id = scope_id
        self._actions: dict[str, HotkeyAction] = {}
        self._shortcuts: dict[str, QShortcut] = {}
        self._user_overrides: dict[str, str] = {}  # action_id → key_str
        self._host: QWidget | None = None
        self._current_mode: int | None = None

    # ------------------------------------------------------------------
    # Регистрация
    # ------------------------------------------------------------------

    def register(self, action: HotkeyAction) -> None:
        """Добавляет описание действия в реестр. Не создаёт QShortcut."""
        if action.action_id in self._actions:
            logging.warning(
                f"[HotkeyRegistry:{self.scope_id}] "
                f"Перезапись уже зарегистрированного действия '{action.action_id}'"
            )
        self._actions[action.action_id] = action

    # ------------------------------------------------------------------
    # Применение к виджету
    # ------------------------------------------------------------------

    def apply_all(self, host: QWidget) -> None:
        """
        Создаёт (или пересоздаёт) все QShortcut на хост-виджете.
        Вызывается один раз при инициализации, или при сбросе клавиш.
        """
        self._host = host

        # Удаляем старые шорткаты, если были
        for sc in self._shortcuts.values():
            sc.setEnabled(False)
            sc.deleteLater()
        self._shortcuts.clear()

        for action_id, action in self._actions.items():
            self._create_shortcut(action_id, action, host)

        # Применяем текущий режим, если он уже известен
        if self._current_mode is not None:
            self.update_mode(self._current_mode)

        logging.debug(
            f"[HotkeyRegistry:{self.scope_id}] "
            f"Применено {len(self._shortcuts)} шорткатов"
        )

    def _create_shortcut(
        self, action_id: str, action: HotkeyAction, host: QWidget
    ) -> None:
        """Внутренний метод: создаёт один QShortcut для действия."""
        key_str = self._user_overrides.get(action_id, action.default_key)
        if not key_str:
            return

        callback = getattr(host, action.callback_name, None)
        if callback is None:
            logging.warning(
                f"[HotkeyRegistry:{self.scope_id}] "
                f"Метод '{action.callback_name}' не найден на хосте "
                f"для действия '{action_id}'"
            )
            return

        try:
            sc = QShortcut(QKeySequence(key_str), host)
            sc.activated.connect(callback)
            sc.setContext(action.context)
            self._shortcuts[action_id] = sc
        except Exception as e:
            logging.error(
                f"[HotkeyRegistry:{self.scope_id}] "
                f"Не удалось создать шоркат для '{action_id}' ({key_str}): {e}"
            )

    # ------------------------------------------------------------------
    # Управление режимами (single/grid/list)
    # ------------------------------------------------------------------

    def update_mode(self, mode_idx: int) -> None:
        """
        Включает/выключает хоткеи в зависимости от активного режима.
        mode_idx: 0=single, 1=grid, 2=list
        """
        self._current_mode = mode_idx
        for action_id, sc in self._shortcuts.items():
            action = self._actions[action_id]
            if action.enabled_in_modes is None:
                sc.setEnabled(True)
            else:
                sc.setEnabled(mode_idx in action.enabled_in_modes)

    # ------------------------------------------------------------------
    # Активация / деактивация всего реестра (для переключения модулей)
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Включает все шоркаты реестра (при переходе в данный модуль)."""
        for action_id, sc in self._shortcuts.items():
            action = self._actions[action_id]
            if action.enabled_in_modes is None or self._current_mode in (action.enabled_in_modes or set()):
                sc.setEnabled(True)

    def deactivate(self) -> None:
        """Выключает все шоркаты реестра (при уходе из данного модуля)."""
        for sc in self._shortcuts.values():
            sc.setEnabled(False)

    # ------------------------------------------------------------------
    # Пользовательские переопределения
    # ------------------------------------------------------------------

    def load_overrides(self, overrides: dict[str, str]) -> None:
        """
        Загружает пользовательские переопределения клавиш.
        overrides: {action_id: key_str}, напр. {"next_file": "Shift+Right"}
        """
        self._user_overrides = {k: v for k, v in overrides.items() if k in self._actions}
        logging.debug(
            f"[HotkeyRegistry:{self.scope_id}] "
            f"Загружено {len(self._user_overrides)} пользовательских переопределений"
        )

    def save_overrides(self) -> dict[str, str]:
        """
        Возвращает только те клавиши, которые отличаются от defaults.
        Это то, что нужно сохранить в settings.ini.
        """
        result = {}
        for action_id, key_str in self._user_overrides.items():
            action = self._actions.get(action_id)
            if action and key_str != action.default_key:
                result[action_id] = key_str
        return result

    def set_key(self, action_id: str, key_str: str) -> bool:
        """
        Изменяет клавишу для действия и пересоздаёт шоркат.
        Предназначен для будущего UI настройки.
        Возвращает True при успехе.
        """
        if action_id not in self._actions:
            logging.warning(
                f"[HotkeyRegistry:{self.scope_id}] "
                f"set_key: действие '{action_id}' не найдено"
            )
            return False

        if key_str is not None:
            self._user_overrides[action_id] = key_str
        elif action_id in self._user_overrides:
            del self._user_overrides[action_id]

        if self._host is not None:
            # Удаляем старый шоркат
            old_sc = self._shortcuts.pop(action_id, None)
            if old_sc:
                old_sc.setEnabled(False)
                old_sc.deleteLater()
            # Создаём новый
            self._create_shortcut(action_id, self._actions[action_id], self._host)
            # Синхронизируем с текущим режимом
            if self._current_mode is not None:
                self.update_mode(self._current_mode)

        return True

    def get_effective_key(self, action_id: str) -> str:
        """Возвращает текущую клавишу (переопределённую или default)."""
        action = self._actions.get(action_id)
        if not action:
            return ""
        return self._user_overrides.get(action_id, action.default_key)

    def get_all_actions(self) -> list[HotkeyAction]:
        """Возвращает все зарегистрированные действия (для UI настройки)."""
        return list(self._actions.values())

    def reset_to_defaults(self) -> None:
        """Сбрасывает все переопределения и пересоздаёт шоркаты."""
        self._user_overrides.clear()
        if self._host is not None:
            self.apply_all(self._host)


# ---------------------------------------------------------------------------
# SorterHotkeysMixin — инициализация реестра для модуля Sorter
# ---------------------------------------------------------------------------

_W = Qt.ShortcutContext.WidgetWithChildrenShortcut
_A = Qt.ShortcutContext.ApplicationShortcut

_SORTER_ACTIONS: list[HotkeyAction] = [
    # ── Навигация ─────────────────────────────────────────────────────
    HotkeyAction(
        action_id="next_file",
        label_ru="Следующий файл",
        label_en="Next file",
        default_key="Right",
        callback_name="next_file",
        group="navigation",
        context=_W,
        enabled_in_modes={0},
    ),
    HotkeyAction(
        action_id="prev_file",
        label_ru="Предыдущий файл",
        label_en="Previous file",
        default_key="Left",
        callback_name="prev_file",
        group="navigation",
        context=_W,
        enabled_in_modes={0},
    ),
    HotkeyAction(
        action_id="move_up",
        label_ru="Вверх по списку / плиткам",
        label_en="Up in list / grid",
        default_key="Up",
        callback_name="move_up",
        group="navigation",
        context=_W,
        enabled_in_modes={0},
    ),
    HotkeyAction(
        action_id="move_down",
        label_ru="Вниз по списку / плиткам",
        label_en="Down in list / grid",
        default_key="Down",
        callback_name="move_down",
        group="navigation",
        context=_W,
        enabled_in_modes={0},
    ),

    # ── Файлы ─────────────────────────────────────────────────────────
    HotkeyAction(
        action_id="delete_file",
        label_ru="Удалить / переместить в корзину",
        label_en="Delete / move to trash",
        default_key="Delete",
        callback_name="delete_file",
        group="file",
        context=_W,
    ),
    HotkeyAction(
        action_id="undo_action",
        label_ru="Отменить последнее действие",
        label_en="Undo last action",
        default_key="Ctrl+Z",
        callback_name="undo_action",
        group="file",
        context=_W,
    ),
    HotkeyAction(
        action_id="rename_file",
        label_ru="Переименовать файл",
        label_en="Rename file",
        default_key="F2",
        callback_name="rename_current_file",
        group="file",
        context=_W,
    ),

    # ── Воспроизведение ───────────────────────────────────────────────
    HotkeyAction(
        action_id="toggle_playback",
        label_ru="Воспроизведение / пауза",
        label_en="Play / pause",
        default_key="Space",
        callback_name="toggle_playback",
        group="playback",
        context=_W,
        enabled_in_modes={0},
    ),

    # ── Вид ───────────────────────────────────────────────────────────
    HotkeyAction(
        action_id="toggle_hover_preview",
        label_ru="Быстрый просмотр по наведению",
        label_en="Toggle hover preview",
        default_key="F1",
        callback_name="toggle_hover_preview",
        group="view",
        context=_W,
    ),
    HotkeyAction(
        action_id="exit_fullscreen",
        label_ru="Выйти из полноэкранного режима",
        label_en="Exit fullscreen",
        default_key="Escape",
        callback_name="exit_fullscreen_if_active",
        group="view",
        context=_A,
    ),
    HotkeyAction(
        action_id="toggle_fullscreen_solo",
        label_ru="Полноэкранный режим (Solo просмотр)",
        label_en="Fullscreen mode (Solo view)",
        default_key="Alt+Return",
        callback_name="toggle_app_fullscreen",
        group="view",
        context=_A,
        enabled_in_modes={0},
    ),
    HotkeyAction(
        action_id="fast_move_to_target",
        label_ru="Быстрое перемещение в выбранную папку",
        label_en="Fast move to selected folder",
        default_key="Space",
        callback_name="fast_move_to_target",
        group="file",
        context=_W,
        enabled_in_modes={1, 2},
    ),
]


class SorterHotkeysMixin:
    """
    Mixin для SorterModule. Инициализирует HotkeyRegistry с набором
    действий Sorter'а и подключает их к методам модуля.
    """

    def init_hotkeys(self) -> None:
        registry = HotkeyRegistry("sorter")

        for action in _SORTER_ACTIONS:
            registry.register(action)

        # Загружаем пользовательские переопределения из конфига
        overrides = self.config.get("hotkeys_sorter", {})
        registry.load_overrides(overrides)

        # Применяем к себе (self — это SorterModule(QWidget))
        registry.apply_all(self)
        self._hotkey_registry = registry
        if hasattr(self, 'update_ui_text'):
            self.update_ui_text()

    def update_hotkeys_context(self, mode_idx: int) -> None:
        """Вызывается при смене режима просмотра (single/grid/list)."""
        if hasattr(self, '_hotkey_registry'):
            self._hotkey_registry.update_mode(mode_idx)

    # ------------------------------------------------------------------
    # Действия, которые живут здесь как методы (не делегируются в viewer)
    # ------------------------------------------------------------------

    def exit_fullscreen_if_active(self) -> None:
        if self.window().isFullScreen():
            self.toggle_app_fullscreen()

    def toggle_app_fullscreen(self) -> None:
        win = self.window()

        if win.isFullScreen():
            win.showNormal()
            self.viewer.set_fullscreen_mode(False)
            self.sidebar.show()
            self.toolbar.show()
            self.bottom_controls_container.show()

            if self.bottom_controls_container:
                idx = self.left_layout.indexOf(self.bottom_controls_container)
                self.left_layout.insertWidget(idx, self.video_controls)
            else:
                self.left_layout.addWidget(self.video_controls)

            # Показываем контролы плеера только если текущий файл является видео или аудио
            show_player = False
            if hasattr(self, 'current_file_path') and self.current_file_path:
                ext = os.path.splitext(self.current_file_path)[1].lower()
                show_player = ext in [
                    '.mp4', '.avi', '.mkv', '.mov', '.webm', '.wmv', '.flv', '.mpg', '.mpeg', '.m4v', # видео
                    '.mp3', '.wav', '.ogg', '.flac' # аудио
                ]
            if show_player:
                self.video_controls.show()
            else:
                self.video_controls.hide()
            
            self.layout().setContentsMargins(0, 0, 0, 0)
        else:
            win.showFullScreen()
            self.sidebar.hide()
            self.toolbar.hide()
            self.bottom_controls_container.hide()

            controls_to_pass = None
            if self.video_controls.isVisible():
                controls_to_pass = self.video_controls

            self.viewer.set_fullscreen_mode(True, controls_to_pass)

    def toggle_hover_preview(self) -> None:
        """Переключает режим быстрого просмотра по наведению и синхронизирует кнопку."""
        if hasattr(self, 'viewer'):
            self.viewer.toggle_hover_preview()

    def fast_move_to_target(self) -> None:
        """Перемещает выделенные файлы в папку быстрой цели (Fast Move)."""
        if not getattr(self, 'quick_target_path', None) or not os.path.exists(self.quick_target_path):
            logging.warning("Fast move triggered, but quick_target_path is not set or invalid.")
            return

        logging.info(f"Fast move triggered for target folder: {self.quick_target_path}")
        self.move_current_file(self.quick_target_path)
