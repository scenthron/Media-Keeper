import sys
import os

os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["ORT_INTRA_OP_NUM_THREADS"] = "1"
os.environ["ORT_INTER_OP_NUM_THREADS"] = "1"

try:
    import cv2
    cv2.setNumThreads(1)
except ImportError:
    pass

# Предотвращаем запуск интерактивного шелла Python при выходе (сброс унаследованных переменных)
os.environ.pop('PYTHONINSPECT', None)
if hasattr(sys, '__interactivehook__'):
    try:
        del sys.__interactivehook__
    except:
        pass

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget, QPushButton, QStyle
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QRect, QParallelAnimationGroup, QPoint, QEvent, QSize, QtMsgType, qInstallMessageHandler
from PyQt6.QtGui import QIcon, QAction
import logging
from logic_logger import setup_logging, shutdown_logging

os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.multimedia.*=false"
os.environ["AV_LOG_LEVEL"] = "quiet"

def qt_message_handler(mode, context, message):
    ignore_phrases = [
        "swscaler", 
        "deprecated pixel format used", 
        "Could not update timestamps for skipped samples",
        "Failed setup for format d3d11",
        "hwaccel initialisation returned error",
        "Invalid SOS parameters for sequential JPEG"
    ]
    if any(phrase in message for phrase in ignore_phrases):
        return
    if mode == QtMsgType.QtInfoMsg:
        logging.info(message)
    elif mode == QtMsgType.QtWarningMsg:
        logging.warning(message)
    elif mode == QtMsgType.QtCriticalMsg:
        logging.error(message)
    elif mode == QtMsgType.QtFatalMsg:
        logging.critical(message)
    else:
        logging.debug(message)

qInstallMessageHandler(qt_message_handler)

def silence_c_stderr():
    import os
    import sys
    import threading
    try:
        if sys.stderr is None or not hasattr(sys.stderr, 'fileno'):
            return
        fd = sys.stderr.fileno()
        if fd < 0:
            return
        r_fd, w_fd = os.pipe()
        original_stderr_fd = os.dup(fd)
        os.dup2(w_fd, fd)
        def stderr_reader():
            with os.fdopen(r_fd, 'r', errors='ignore') as pipe_reader:
                for line in pipe_reader:
                    if any(x in line for x in ("d3d11", "hwaccel", "h264 @", "hevc @", "aac @", "swscaler")):
                        continue
                    try:
                        os.write(original_stderr_fd, line.encode('utf-8', errors='ignore'))
                    except Exception:
                        pass
        t = threading.Thread(target=stderr_reader, daemon=True)
        t.start()
    except Exception:
        pass

silence_c_stderr()

# --- Safe QFileDialog Monkey Patch for Windows native dialog stability ---
from PyQt6.QtWidgets import QFileDialog

def _make_safe_dialog_method(orig_method, options_index):
    def safe_method(*args, **kwargs):
        import sys
        import os
        import logging
        
        logging.warning(f"[SafeDialog] {orig_method.__name__} called with args={args}, kwargs={kwargs}")
        
        args_list = list(args)
        
        # 1. Resolve Top-Level window for parent handle (safer and supports Qt modal window states)
        if len(args_list) > 0 and args_list[0] is not None:
            try:
                parent_widget = args_list[0]
                if hasattr(parent_widget, 'window'):
                    args_list[0] = parent_widget.window()
            except Exception as e:
                logging.debug(f"[SafeDialog] Failed to resolve parent.window(): {e}")
                
        # 2. Extract and adjust directory (argument index 2)
        # If the directory path is empty, default to home directory to prevent Shell API failures
        if len(args_list) > 2:
            if not args_list[2]:
                try:
                    args_list[2] = os.path.expanduser("~")
                except Exception:
                    pass
        elif 'directory' in kwargs:
            if not kwargs['directory']:
                try:
                    kwargs['directory'] = os.path.expanduser("~")
                except Exception:
                    pass
        else:
            # Ensure a valid default directory is always appended if not provided
            while len(args_list) < 3:
                args_list.append("")
            try:
                args_list[2] = os.path.expanduser("~")
            except Exception:
                pass

        # 3. Graceful fallback strategy: try native dialog first, fallback to DontUseNativeDialog on error
        try:
            # Create copies to prevent modifying arguments on fallback attempt
            native_args = list(args_list)
            native_kwargs = dict(kwargs)
            
            logging.warning(f"[SafeDialog] Attempting native {orig_method.__name__} with args={native_args}, kwargs={native_kwargs}")
            res = orig_method(*native_args, **native_kwargs)
            logging.warning(f"[SafeDialog] Native {orig_method.__name__} returned: {res!r}")
            return res
        except Exception as native_err:
            logging.error(f"[SafeDialog] Native dialog failed: {native_err}. Falling back to built-in Qt dialog.", exc_info=True)
            
            fallback_args = list(args_list)
            fallback_kwargs = dict(kwargs)
            
            if sys.platform == 'win32':
                if 'options' in fallback_kwargs:
                    fallback_kwargs['options'] = fallback_kwargs['options'] | QFileDialog.Option.DontUseNativeDialog
                else:
                    if len(fallback_args) > options_index:
                        if fallback_args[options_index] is not None:
                            fallback_args[options_index] = fallback_args[options_index] | QFileDialog.Option.DontUseNativeDialog
                        else:
                            fallback_args[options_index] = QFileDialog.Option.DontUseNativeDialog
                    else:
                        while len(fallback_args) < options_index + 1:
                            fallback_args.append(None)
                        fallback_args[options_index] = QFileDialog.Option.DontUseNativeDialog
            
            logging.warning(f"[SafeDialog] Invoking fallback {orig_method.__name__} with args={fallback_args}, kwargs={fallback_kwargs}")
            try:
                res = orig_method(*fallback_args, **fallback_kwargs)
                logging.warning(f"[SafeDialog] Fallback {orig_method.__name__} returned: {res!r}")
                return res
            except Exception as e:
                err_msg = f"[SafeDialog ERROR] Failed calling fallback {orig_method.__name__}: {e}"
                print(err_msg, file=sys.stderr, flush=True)
                logging.error(err_msg, exc_info=True)
                if orig_method.__name__ in ('getOpenFileName', 'getOpenFileNames', 'getSaveFileName'):
                    if orig_method.__name__ == 'getOpenFileNames':
                        return [], ""
                    return "", ""
                return ""
    return safe_method

QFileDialog.getExistingDirectory = _make_safe_dialog_method(QFileDialog.getExistingDirectory, 3)
QFileDialog.getOpenFileName = _make_safe_dialog_method(QFileDialog.getOpenFileName, 5)
QFileDialog.getOpenFileNames = _make_safe_dialog_method(QFileDialog.getOpenFileNames, 5)
QFileDialog.getSaveFileName = _make_safe_dialog_method(QFileDialog.getSaveFileName, 5)
# --------------------------------------------------------------------------

from config import AppContext, APP_VERSION, APP_DESIGN
from ui_menu import NavigationDrawer
# UPDATED IMPORTS:
from modules.sorter.ui_main import SorterModule
from modules.editor.ui_main import EditorMainWidget
from modules.cleaner.ui_main import CleanerModule
from modules.analyzer.ui_main import AnalyzerWidget
from ui_dialogs_generic import InfoDialog

class MediaKeeperShell(QMainWindow):
    def __init__(self):
        super().__init__()
        logging.info("Инициализация главного окна MediaKeeperShell.")
        self.setWindowTitle(f"{AppContext.tr('app_title')} {APP_VERSION}")
        self.resize(1400, 900)
        self.setMinimumSize(800, 600)
        
        assets_dir = AppContext.find_resource_dir("assets")
        icon_path = os.path.join(assets_dir, "icon.png") if assets_dir else None
        if not icon_path or not os.path.exists(icon_path):
            launcher_dir = AppContext.find_resource_dir("launcher")
            icon_path = os.path.join(launcher_dir, "icon.png") if launcher_dir else None
        
        if icon_path and os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            logging.debug(f"Иконка приложения установлена из {icon_path}")
        else:
            self.setWindowIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DesktopIcon))
            logging.warning(f"Файл иконки не найден (assets и launcher отсутствуют), используется системная иконка.")
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        self.stack = QStackedWidget(self.central_widget)
        
        logging.debug("Создание вкладок модулей.")
        self.sorter_tab = SorterModule()
        self.editor_tab = EditorMainWidget()
        self.cleaner_tab = CleanerModule() 
        self.analyzer_tab = AnalyzerWidget()
        
        self.analyzer_tab.back_requested.connect(lambda: self.switch_tab(0))
        self.editor_tab.ffmpeg_downloaded.connect(self.on_ffmpeg_downloaded)

        self.stack.addWidget(self.sorter_tab)   # 0
        self.stack.addWidget(self.editor_tab)   # 1
        self.stack.addWidget(self.cleaner_tab)   # 2
        self.stack.addWidget(self.analyzer_tab)  # 3
        logging.info("Все вкладки модулей успешно добавлены в QStackedWidget.")
        
        self.drawer = NavigationDrawer(self.central_widget)
        self.drawer.hide()
        self.drawer.tab_changed.connect(self.switch_tab)
        self.drawer.about_requested.connect(self.show_about_dialog)
        self.drawer.global_settings_requested.connect(self.open_global_settings)
        self.drawer.close_requested.connect(self.close_drawer)
        
        icons_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "icons"))
        self.btn_menu = QPushButton(self.central_widget)
        self.btn_menu.setFixedSize(50, 40)
        self.btn_menu.setIcon(QIcon(os.path.join(icons_dir, "text-align-justify.svg")))
        self.btn_menu.setIconSize(QSize(24, 24))
        self.btn_menu.setStyleSheet("""
            QPushButton { 
                background-color: #444444; 
                border: none; 
                border-radius: 0px; 
                padding: 0px;
            }
            QPushButton:hover { background-color: #555; }
        """)
        self.btn_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_menu.clicked.connect(self.toggle_drawer)
        
        self.btn_menu.move(0, 0)
        
        self.drawer_open = False
        self.installEventFilter(self)
        self.update_ui_text()
        logging.debug("Базовая тема оформления применена.")

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            if self.isFullScreen():
                self.btn_menu.hide()
            else:
                if not self.drawer.isVisible():
                    self.btn_menu.show()
        super().changeEvent(event)

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            if self.drawer.isVisible() and self.drawer_open:
                if not self.drawer.geometry().contains(event.pos()) and source != self.btn_menu:
                    self.close_drawer()
        return super().eventFilter(source, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.stack.resize(self.central_widget.size())
        if self.drawer.isVisible():
            self.drawer.resize(self.drawer.width(), self.central_widget.height())

    def toggle_drawer(self):
        if self.drawer.isVisible():
            self.close_drawer()
        else:
            self.open_drawer()

    def open_drawer(self):
        logging.info("Открытие навигационной панели (шторки).")
        self.drawer.raise_() 
        self.btn_menu.hide()
        self.drawer.resize(self.drawer.width(), self.central_widget.height())
        self.drawer.move(-self.drawer.width(), 0)
        self.drawer.show()
        self.anim_group = QParallelAnimationGroup()
        anim_drawer = QPropertyAnimation(self.drawer, b"pos")
        anim_drawer.setDuration(200)
        anim_drawer.setStartValue(self.drawer.pos())
        anim_drawer.setEndValue(QPoint(0, 0))
        self.anim_group.addAnimation(anim_drawer)
        self.anim_group.start()
        self.drawer_open = True

    def close_drawer(self):
        logging.info("Закрытие навигационной панели (шторки).")
        self.anim_group = QParallelAnimationGroup()
        anim_drawer = QPropertyAnimation(self.drawer, b"pos")
        anim_drawer.setDuration(200)
        anim_drawer.setStartValue(self.drawer.pos())
        anim_drawer.setEndValue(QPoint(-self.drawer.width(), 0))
        self.anim_group.addAnimation(anim_drawer)
        self.anim_group.finished.connect(self._on_drawer_closed)
        self.anim_group.start()
        self.drawer_open = False
        
    def _on_drawer_closed(self):
        self.drawer.hide()
        if not self.isFullScreen():
            self.btn_menu.show()

    def switch_tab(self, index):
        logging.info(f"Переключение на вкладку с индексом {index}.")
        current_widget = self.stack.currentWidget()
        if current_widget == self.sorter_tab and index != 0:
             if hasattr(self.sorter_tab, "stop_playback"):
                 logging.debug("Остановка воспроизведения при уходе со вкладки Сортировщика.")
                 self.sorter_tab.stop_playback()
        elif current_widget == self.cleaner_tab and index != 2:
             if hasattr(self.cleaner_tab, "stop_playback"):
                 logging.debug("Остановка воспроизведения при уходе со вкладки Поиска дубликатов.")
                 self.cleaner_tab.stop_playback()
        elif current_widget == self.analyzer_tab and index != 3:
             if hasattr(self.analyzer_tab, "stop_playback"):
                 logging.debug("Остановка воспроизведения при уходе со вкладки Анализатора.")
                 self.analyzer_tab.stop_playback()

        self.stack.setCurrentIndex(index)
        self.drawer.set_active_tab(index)
        
        if index == 0:
            if hasattr(self.sorter_tab, "on_tab_enter"):
                logging.debug("Возобновление работы Сортировщика при возвращении на вкладку.")
                self.sorter_tab.on_tab_enter()
        elif index == 3:
            if hasattr(self.analyzer_tab, "on_tab_enter"):
                logging.debug("Синхронизация данных Анализатора при входе на вкладку.")
                self.analyzer_tab.on_tab_enter()

        self.close_drawer()
        current = self.stack.currentWidget()
        if current: current.setFocus()

    def request_analysis(self, path):
        logging.info(f"Запрос анализа диска для пути: {path}")
        self.switch_tab(3)
        if hasattr(self.analyzer_tab, 'start_analysis'):
            self.analyzer_tab.start_analysis(path, from_sorter=True)
            
    def send_to_video_converter(self, filepaths):
        logging.info(f"Отправка {len(filepaths)} видео файлов на конвертацию.")
        self.switch_tab(1)
        self.editor_tab.open_video_converter(filepaths)

    def send_to_video_editor(self, filepath):
        logging.info(f"Отправка файла {filepath} в видеоредактор.")
        self.switch_tab(1)
        self.editor_tab.open_video_editor(filepath)

    def send_to_audio_converter(self, filepaths):
        logging.info(f"Отправка {len(filepaths)} аудио файлов на конвертацию.")
        self.switch_tab(1)
        self.editor_tab.open_audio_converter(filepaths)

    def send_to_image_converter(self, filepaths):
        logging.info(f"Отправка {len(filepaths)} изображений на конвертацию.")
        self.switch_tab(1)
        self.editor_tab.open_image_converter(filepaths)

    def show_about_dialog(self):
        logging.debug("Открытие диалога 'О программе'.")
        dlg = InfoDialog(self)
        dlg.exec()
        self.close_drawer()

    def open_global_settings(self):
        logging.debug("Открытие глобальных настроек (перенаправлено на настройки Сортировщика).")
        if hasattr(self.sorter_tab, "open_settings_dialog"):
            self.sorter_tab.open_settings_dialog()
            self.close_drawer()

    def update_ui_text(self):
        logging.info("Обновление текстов интерфейса для текущего языка.")
        self.setWindowTitle(f"{AppContext.tr('app_title')} {APP_VERSION}")
        self.drawer.update_ui_text()
        if hasattr(self.sorter_tab, "update_ui_text"): self.sorter_tab.update_ui_text()
        if hasattr(self.editor_tab, "update_ui_text"): self.editor_tab.update_ui_text()
        if hasattr(self.analyzer_tab, "update_ui_text"): self.analyzer_tab.update_ui_text()
        if hasattr(self.cleaner_tab, "update_ui_text"): self.cleaner_tab.update_ui_text()

    def on_ffmpeg_downloaded(self) -> None:
        """Вызывается при успешном скачивании FFmpeg для обновления превью видеофайлов в Сортировщике и активации видео-режима в Cleaner."""
        logging.info("FFmpeg скачан. Обновляем превью для видеофайлов в Сортировщике.")
        if hasattr(self.sorter_tab, 'refresh_video_thumbnails'):
            self.sorter_tab.refresh_video_thumbnails()
            
        if hasattr(self, 'cleaner_tab'):
            cleaner = self.cleaner_tab
            if hasattr(cleaner, 'settings_panel_similar') and hasattr(cleaner.settings_panel_similar, 'update_media_types_availability'):
                cleaner.settings_panel_similar.update_media_types_availability()

    def closeEvent(self, event):
        logging.info("Завершение работы приложения.")
        shutdown_logging() # Flush logs
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()
        super().closeEvent(event)

def global_excepthook(exctype, value, traceback_obj):
    import traceback
    import logging
    import sys
    try:
        tb_lines = traceback.format_exception(exctype, value, traceback_obj)
        tb_text = "".join(tb_lines)
        logging.critical(f"Unhandled Python exception:\n{tb_text}")
        
        # Пытаемся показать диалог пользователю
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance():
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Icon.Critical)
                msg.setWindowTitle("Критическая ошибка")
                msg.setText("Произошла непредвиденная ошибка. Приложение может работать нестабильно.")
                msg.setDetailedText(tb_text)
                msg.exec()
        except Exception:
            pass
        
        # Принудительный сброс логов на диск
        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            handler.flush()
            
        # Также сбрасываем фоновые хэндлеры через остановку слушателя, если он есть
        try:
            from logic_logger import shutdown_logging
            shutdown_logging()
        except Exception:
            pass
    except Exception as e:
        print(f"Error in global_excepthook: {e}", file=sys.stderr)
        
    sys.__excepthook__(exctype, value, traceback_obj)

if __name__ == "__main__":
    setup_logging()
    sys.excepthook = global_excepthook

    def thread_excepthook(args):
        global_excepthook(args.exc_type, args.exc_value, args.exc_traceback)

    import threading
    threading.excepthook = thread_excepthook

    def unraisable_hook(args):
        import logging
        logging.error(f"Unraisable exception: {args.exc_value}", exc_info=args.exc_traceback)

    sys.unraisablehook = unraisable_hook

    logging.info(f"Запуск приложения {APP_VERSION}.")
    app = QApplication(sys.argv)
    
    # Увеличиваем размер стека для фоновых потоков (8 МБ) для предотвращения C++ вылетов (Stack Overflow) ONNXRuntime
    from PyQt6.QtCore import QThreadPool
    QThreadPool.globalInstance().setStackSize(8 * 1024 * 1024)
    
    # Load built-in Qt translations for system dialogs (e.g. QFileDialog)
    try:
        from PyQt6.QtCore import QTranslator
        qt_translator = QTranslator()
        lang_dir = AppContext.find_resource_dir("languages")
        if lang_dir:
            lang_code = AppContext.LANG.lower() if hasattr(AppContext, 'LANG') else "ru"
            qm_path = os.path.join(lang_dir, f"qtbase_{lang_code}.qm")
            if os.path.exists(qm_path):
                if qt_translator.load(qm_path):
                    app.installTranslator(qt_translator)
                    logging.info(f"Loaded built-in Qt translations from: {qm_path}")
            else:
                logging.warning(f"Qt translation file not found: {qm_path}")
    except Exception as e:
        logging.warning(f"Failed to load built-in Qt translations: {e}")
    
    # Windows Taskbar Icon & Title Fix (AppUserModelID)
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Centhron.MediaKeeper.Alpha")
        except Exception as e:
            logging.warning(f"Failed to set AppUserModelID: {e}")
            
    app.setStyle("Fusion")
    
    # Global Stylesheet for the whole application
    app.setStyleSheet(f"""
        QWidget {{ background-color: {APP_DESIGN['bg_color_main']}; color: {APP_DESIGN['text_color']}; font-size: 14px; font-family: 'Segoe UI', Arial, sans-serif; }}
        QToolTip {{ 
            color: #ffffff; 
            background-color: #1e1e1e; 
            border: 1px solid #333333; 
            padding: 5px;
            border-radius: 4px;
        }}
        
        /* Reset theme for QFileDialog to ensure a standard, readable light theme on Windows */
        QFileDialog {{ 
            background-color: #f0f0f0 !important; 
            color: #000000 !important; 
        }}
        QFileDialog QWidget {{ 
            background-color: #f0f0f0 !important; 
            color: #000000 !important; 
        }}
        QFileDialog QTreeView, QFileDialog QListView, QFileDialog QTreeView::item, QFileDialog QListView::item {{ 
            background-color: #ffffff !important; 
            color: #000000 !important; 
        }}
        QFileDialog QHeaderView::section {{ 
            background-color: #e1e1e1 !important; 
            color: #000000 !important; 
            border: 1px solid #ccc !important;
            padding: 4px !important;
        }}
        QFileDialog QLineEdit {{ 
            background-color: #ffffff !important; 
            color: #000000 !important; 
            border: 1px solid #ccc !important; 
            border-radius: 2px !important;
            padding: 3px !important;
        }}
        QFileDialog QComboBox {{ 
            background-color: #ffffff !important; 
            color: #000000 !important; 
            border: 1px solid #ccc !important; 
            border-radius: 2px !important;
            padding: 3px !important;
        }}
        QFileDialog QComboBox::drop-down {{
            border: none !important;
            background: transparent !important;
        }}
        QFileDialog QPushButton {{ 
            background-color: #e1e1e1 !important; 
            color: #000000 !important; 
            border: 1px solid #adadad !important; 
            border-radius: 3px !important;
            padding: 5px 15px !important; 
            min-width: 75px !important;
        }}
        QFileDialog QPushButton:hover {{ 
            background-color: #e5f1fb !important; 
            border: 1px solid #0078d7 !important; 
        }}
        QFileDialog QPushButton:pressed {{ 
            background-color: #cce4f7 !important; 
            border: 1px solid #005499 !important; 
        }}
        QFileDialog QLabel {{
            background-color: transparent !important;
            color: #000000 !important;
        }}
        QFileDialog QToolButton {{
            background-color: #f0f0f0 !important;
            color: #000000 !important;
            border: 1px solid transparent !important;
            border-radius: 2px !important;
            padding: 3px !important;
        }}
        QFileDialog QToolButton:hover {{
            background-color: #e5f1fb !important;
            border: 1px solid #0078d7 !important;
        }}
    """)
    assets_dir = AppContext.find_resource_dir("assets")
    icon_path_global = os.path.join(assets_dir, "icon.png") if assets_dir else None
    if not icon_path_global or not os.path.exists(icon_path_global):
        launcher_dir = AppContext.find_resource_dir("launcher")
        icon_path_global = os.path.join(launcher_dir, "icon.png") if launcher_dir else None
        
    if icon_path_global and os.path.exists(icon_path_global):
        app.setWindowIcon(QIcon(icon_path_global))
    else:
        logging.warning("Глобальная иконка не найдена в assets и launcher, используется системная.")
        app.setWindowIcon(app.style().standardIcon(QStyle.StandardPixmap.SP_DesktopIcon))
        
    from launcher_window import LauncherWindow
    window = LauncherWindow()
    window.show()
    logging.info("Главное окно отображено. Запуск цикла событий приложения.")
    ret = app.exec()
    logging.info("Цикл событий завершен. Принудительный выход из процесса.")
    shutdown_logging() # Flush logs
    os._exit(ret)
