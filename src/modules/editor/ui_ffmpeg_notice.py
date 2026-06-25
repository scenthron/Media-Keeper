"""
Виджет уведомления о необходимости FFmpeg с возможностью загрузки.
"""

import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, QProgressBar, QDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from config import AppContext, APP_DESIGN
from .ffmpeg_downloader import FFmpegDownloaderWorker, check_ffmpeg_available


class FFmpegNoticeWidget(QWidget):
    """
    Виджет уведомления о необходимости FFmpeg.
    Показывает кнопку загрузки, прогресс-бар и статус.
    """
    download_finished = pyqtSignal(bool)  # Успешна ли загрузка
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.downloader_worker = None
        self.init_ui()
        
    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Основной контейнер с рамкой
        container = QFrame()
        container.setStyleSheet(f"""
            QFrame {{
                background-color: #2b2b2b;
                border: none;
                border-radius: 8px;
                padding: 20px;
            }}
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(20, 20, 20, 20)
        container_layout.setSpacing(15)
        
        # Заголовок
        self.title_lbl = QLabel()
        self.title_lbl.setStyleSheet("""
            QLabel {
                color: #fff;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(self.title_lbl)
        
        # Описание
        self.desc_lbl = QLabel()
        self.desc_lbl.setStyleSheet("""
            QLabel {
                color: #aaa;
                font-size: 13px;
            }
        """)
        self.desc_lbl.setWordWrap(True)
        self.desc_lbl.setOpenExternalLinks(True)
        self.desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(self.desc_lbl)
        
        # Прогресс-бар (скрыт по умолчанию)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(25)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #555;
                border-radius: 4px;
                text-align: center;
                color: white;
                background: #1a1a1a;
                font-size: 12px;
            }
            QProgressBar::chunk {
                background-color: #3b82f6;
                border-radius: 3px;
            }
        """)
        self.progress_bar.hide()
        container_layout.addWidget(self.progress_bar)
        
        # Статус загрузки (скрыт по умолчанию)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #3b82f6;
                font-size: 12px;
            }
        """)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.hide()
        container_layout.addWidget(self.status_label)
        
        # Кнопка загрузки/остановки
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.btn_download = QPushButton()
        self.btn_download.setFixedSize(150, 40)
        self.btn_download.setStyleSheet(f"""
            QPushButton {{
                background-color: {APP_DESIGN['accent_color']};
                color: white;
                font-size: 14px;
                font-weight: bold;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: #2563eb;
            }}
        """)
        self.btn_download.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_download.clicked.connect(self.on_download_clicked)
        button_layout.addWidget(self.btn_download)
        
        button_layout.addStretch()
        container_layout.addLayout(button_layout)
        
        layout.addWidget(container)
        layout.addStretch()
        
        self.update_ui_text()
        
    def on_download_clicked(self):
        """Обработчик нажатия на кнопку загрузки/остановки"""
        if self.downloader_worker and self.downloader_worker.isRunning():
            # Остановка загрузки
            self.stop_download()
        else:
            # Начало загрузки
            self.start_download()
    
    def start_download(self):
        """Запуск загрузки FFmpeg"""
        logging.info("Запуск загрузки FFmpeg")
        
        # Создаем воркер
        self.downloader_worker = FFmpegDownloaderWorker()
        self.downloader_worker.progress_updated.connect(self.on_progress_updated)
        self.downloader_worker.status_message.connect(self.on_status_message)
        self.downloader_worker.finished.connect(self.on_download_finished)
        
        # Обновляем UI
        self.btn_download.setText("Стоп")
        self.btn_download.setStyleSheet(f"""
            QPushButton {{
                background-color: #ef4444;
                color: white;
                font-size: 14px;
                font-weight: bold;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: #dc2626;
            }}
        """)
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        self.status_label.show()
        self.status_label.setText("Подготовка...")
        
        # Запускаем воркер
        self.downloader_worker.start()
    
    def stop_download(self):
        """Остановка загрузки FFmpeg"""
        logging.info("Остановка загрузки FFmpeg пользователем")
        
        if self.downloader_worker:
            self.downloader_worker.stop()
            # Ждем завершения потока (но не долго)
            if not self.downloader_worker.wait(1000):
                logging.warning("Воркер не завершился за 1 секунду")
        
        # Возвращаем UI в исходное состояние
        self.reset_ui()
    
    def reset_ui(self):
        """Сброс UI в исходное состояние"""
        self.btn_download.setText("Скачать")
        self.btn_download.setStyleSheet(f"""
            QPushButton {{
                background-color: {APP_DESIGN['accent_color']};
                color: white;
                font-size: 14px;
                font-weight: bold;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: #2563eb;
            }}
        """)
        self.progress_bar.hide()
        self.progress_bar.setValue(0)
        self.status_label.hide()
        self.status_label.setText("")
    
    def on_progress_updated(self, percent):
        """Обновление прогресс-бара"""
        self.progress_bar.setValue(percent)
        self.progress_bar.setFormat(f"{percent}%")
    
    def on_status_message(self, message):
        """Обновление статусного сообщения"""
        self.status_label.setText(message)
        logging.debug(f"Статус загрузки: {message}")
    
    def on_download_finished(self, success, error_message):
        """Обработка завершения загрузки"""
        if success:
            logging.info("FFmpeg успешно загружен и установлен")
            self.status_label.setText("FFmpeg успешно установлен!")
            self.status_label.setStyleSheet("""
                QLabel {
                    color: #10b981;
                    font-size: 12px;
                }
            """)
            # Через небольшую задержку скрываем виджет и эмитируем сигнал
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(1500, lambda: self.download_finished.emit(True))
        else:
            logging.error(f"Ошибка загрузки FFmpeg: {error_message}")
            self.status_label.setText(f"Ошибка: {error_message}")
            self.status_label.setStyleSheet("""
                QLabel {
                    color: #ef4444;
                    font-size: 12px;
                }
            """)
            self.reset_ui()
    
    def check_and_hide_if_available(self):
        """
        Проверяет наличие FFmpeg и скрывает виджет, если он доступен.
        Возвращает True, если FFmpeg доступен.
        """
        is_available, _ = check_ffmpeg_available()
        if is_available:
            self.hide()
        return is_available

    def update_ui_text(self):
        if AppContext.LANG == "RU":
            self.title_lbl.setText("⚙️ Требуются библиотеки обработки медиа FFmpeg")
            self.desc_lbl.setText(
                "FFmpeg — это свободная библиотека с открытым исходным кодом для обработки видео и аудио "
                "(<a href='https://ffmpeg.org' style='color: #3b82f6;'>официальный сайт</a>).<br><br>"
                "Нажмите кнопку <b>«Скачать»</b>, чтобы автоматически загрузить необходимые файлы в локальную папку программы "
                "(общий вес файлов составляет ~200 MB, установка в систему не требуется).<br><br>"
                "Если вы предпочитаете ручную установку, вы можете самостоятельно скачать бинарные файлы "
                "<b>ffmpeg.exe</b> и <b>ffprobe.exe</b> и скопировать их в каталог приложения по пути: <b>.mediakeeper/bin/</b>"
            )
            if not self.downloader_worker or not self.downloader_worker.isRunning():
                self.btn_download.setText("Скачать")
            else:
                self.btn_download.setText("Стоп")
        else:
            self.title_lbl.setText("⚙️ FFmpeg Media Libraries Required")
            self.desc_lbl.setText(
                "FFmpeg is a free, open-source library for video and audio processing "
                "(<a href='https://ffmpeg.org' style='color: #3b82f6;'>official website</a>).<br><br>"
                "Click <b>\"Download\"</b> to automatically fetch the required files to the local application folder "
                "(total file size is ~200 MB, no system installation required).<br><br>"
                "If you prefer manual setup, you can download "
                "<b>ffmpeg.exe</b> and <b>ffprobe.exe</b> yourself and copy them into the application directory under: <b>.mediakeeper/bin/</b>"
            )
            if not self.downloader_worker or not self.downloader_worker.isRunning():
                self.btn_download.setText("Download")
            else:
                self.btn_download.setText("Stop")


class FFmpegDownloadConfirmDialog(QDialog):
    """
    Диалог подтверждения скачивания FFmpeg.
    При согласии скачивает библиотеки прямо внутри диалога.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройка FFmpeg" if AppContext.LANG == "RU" else "FFmpeg Setup")
        self.setFixedSize(540, 280)
        self.setStyleSheet("QDialog { background-color: #2b2b2b; color: white; }")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint)
        self.downloader_worker = None
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)
        
        # Заголовок
        title_text = "⚙️ Требуются библиотеки обработки медиа FFmpeg" if AppContext.LANG == "RU" else "⚙️ FFmpeg Media Libraries Required"
        self.title_lbl = QLabel(title_text)
        self.title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #fff; background: transparent;")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.title_lbl)
        
        # Описание
        if AppContext.LANG == "RU":
            desc_text = (
                "FFmpeg — это свободная библиотека с открытым исходным кодом для обработки видео и аудио "
                "(<a href='https://ffmpeg.org' style='color: #3b82f6;'>официальный сайт</a>).<br><br>"
                "Нажмите кнопку <b>«Скачать»</b>, чтобы автоматически загрузить необходимые файлы в локальную папку программы "
                "(общий вес файлов составляет ~200 MB, установка в систему не требуется).<br><br>"
                "Если вы предпочитаете ручную установку, вы можете самостоятельно скачать бинарные файлы "
                "<b>ffmpeg.exe</b> и <b>ffprobe.exe</b> и скопировать их в каталог приложения по пути: <b>.mediakeeper/bin/</b>"
            )
        else:
            desc_text = (
                "FFmpeg is a free, open-source library for video and audio processing "
                "(<a href='https://ffmpeg.org' style='color: #3b82f6;'>official website</a>).<br><br>"
                "Click <b>\"Download\"</b> to automatically fetch the required files to the local application folder "
                "(total file size is ~200 MB, no system installation required).<br><br>"
                "If you prefer manual setup, you can download "
                "<b>ffmpeg.exe</b> and <b>ffprobe.exe</b> yourself and copy them into the application directory under: <b>.mediakeeper/bin/</b>"
            )
        self.desc_lbl = QLabel(desc_text)
        self.desc_lbl.setStyleSheet("font-size: 12px; color: #cccccc; background: transparent;")
        self.desc_lbl.setWordWrap(True)
        self.desc_lbl.setOpenExternalLinks(True)
        self.desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.desc_lbl)
        
        # Embedded Progress bar & Status
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #555;
                border-radius: 4px;
                text-align: center;
                color: white;
                background: #1a1a1a;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background-color: #3b82f6;
                border-radius: 3px;
            }
        """)
        self.progress_bar.hide()
        self.layout.addWidget(self.progress_bar)
        
        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("font-size: 11px; color: #3b82f6; background: transparent;")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.hide()
        self.layout.addWidget(self.status_lbl)
        
        # Buttons Box
        self.btn_layout = QHBoxLayout()
        self.btn_layout.setSpacing(10)
        
        self.b_download = QPushButton("Скачать" if AppContext.LANG == "RU" else "Download")
        self.b_download.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_download.setStyleSheet("""
            QPushButton { 
                background-color: #3b82f6; color: white; font-weight: bold; 
                padding: 8px 20px; border-radius: 4px; border: none; font-size: 13px;
            } 
            QPushButton:hover { background-color: #2563eb; }
        """)
        self.b_download.clicked.connect(self.start_download_flow)
        
        self.b_later = QPushButton("Позже" if AppContext.LANG == "RU" else "Later")
        self.b_later.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_later.setStyleSheet("""
            QPushButton { 
                background-color: #555; color: white; 
                padding: 8px 15px; border-radius: 4px; border: 1px solid #666; font-size: 13px;
            } 
            QPushButton:hover { background-color: #666; border-color: #777; }
        """)
        self.b_later.clicked.connect(self.reject)
        
        self.b_stop = QPushButton("Стоп" if AppContext.LANG == "RU" else "Stop")
        self.b_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_stop.setStyleSheet("""
            QPushButton { 
                background-color: #ef4444; color: white; font-weight: bold; 
                padding: 8px 20px; border-radius: 4px; border: none; font-size: 13px;
            } 
            QPushButton:hover { background-color: #dc2626; }
        """)
        self.b_stop.clicked.connect(self.reject)
        self.b_stop.hide()
        
        self.btn_layout.addStretch()
        self.btn_layout.addWidget(self.b_download)
        self.btn_layout.addWidget(self.b_later)
        self.btn_layout.addWidget(self.b_stop)
        self.layout.addLayout(self.btn_layout)

    def start_download_flow(self):
        self.title_lbl.setText("⏳ Загрузка библиотек FFmpeg..." if AppContext.LANG == "RU" else "⏳ Downloading FFmpeg Libraries...")
        self.desc_lbl.hide()
        self.b_download.hide()
        self.b_later.hide()
        self.b_stop.show()
        
        self.progress_bar.show()
        self.status_lbl.show()
        self.status_lbl.setText("Подготовка..." if AppContext.LANG == "RU" else "Preparing...")
        
        self.downloader_worker = FFmpegDownloaderWorker()
        self.downloader_worker.progress_updated.connect(self.progress_bar.setValue)
        self.downloader_worker.status_message.connect(self.status_lbl.setText)
        self.downloader_worker.finished.connect(self._on_download_finished)
        self.downloader_worker.start()

    def _on_download_finished(self, success, error_message):
        self.b_stop.hide()
        if success:
            self.status_lbl.setStyleSheet("font-size: 11px; color: #10b981; background: transparent;")
            self.status_lbl.setText("FFmpeg успешно установлен!" if AppContext.LANG == "RU" else "FFmpeg successfully installed!")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(1000, self.accept)
        else:
            self.title_lbl.setText("⚙️ Требуются библиотеки FFmpeg" if AppContext.LANG == "RU" else "⚙️ FFmpeg Media Libraries Required")
            self.status_lbl.setStyleSheet("font-size: 11px; color: #ef4444; background: transparent;")
            self.status_lbl.setText(f"Ошибка: {error_message}" if AppContext.LANG == "RU" else f"Error: {error_message}")
            self.b_later.setText("Закрыть" if AppContext.LANG == "RU" else "Close")
            self.b_later.show()

    def reject(self):
        if self.downloader_worker and self.downloader_worker.isRunning():
            self.downloader_worker.stop()
            self.downloader_worker.wait(1000)
        super().reject()

