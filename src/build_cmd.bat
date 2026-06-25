@echo off
chcp 65001 > nul
cls

:: ===========================================================================
::  MEDIA KEEPER — Скрипт сборки EXE (Windows)
::  Запускать из командной строки, находясь ВНУТРИ папки src/
::  Пример: cd /d C:\Users\...\Media_Keeper\src && build_cmd.bat
::
::  ЖЕЛЕЗНОЕ ПРАВИЛО: При добавлении новых ресурсных папок (иконки, языки и т.д.)
::  обязательно добавить их в .spec файл в секцию datas.
::  Текущие ресурсы в сборке:
::    icons\      — SVG иконки интерфейса
::    languages\  — JSON словари переводов + MD мануалы
::    launcher\   — Стартовый экран и иконка приложения
:: ===========================================================================

echo [BUILD] Начало сборки Media Keeper...
echo.

:: --- Проверка наличия PyInstaller ---
where pyinstaller > nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] PyInstaller не найден! Установите его: pip install pyinstaller
    pause
    exit /b 1
)

:: --- Выбор типа сборки ---
echo Выберите тип сборки:
echo   1 - Alpha (для тестирования) — "Media Keeper Alpha by Centhron.exe"
echo   2 - Release (финальная)      — "Media Keeper.exe"
echo.
set /p BUILD_TYPE=Введите 1 или 2: 

if "%BUILD_TYPE%"=="1" (
    echo.
    echo [BUILD] Сборка ALPHA версии...
    pyinstaller --clean "Media Keeper Alpha by Centhron.spec"
) else if "%BUILD_TYPE%"=="2" (
    echo.
    echo [BUILD] Сборка RELEASE версии...
    pyinstaller --clean "Media Keeper.spec"
) else (
    echo [ERROR] Неверный выбор. Запустите скрипт снова.
    pause
    exit /b 1
)

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Сборка завершилась с ошибкой! Проверьте вывод PyInstaller выше.
    pause
    exit /b 1
)

echo.
echo [BUILD] Сборка успешно завершена!
echo [BUILD] Готовый EXE находится в папке: dist\
echo.
pause