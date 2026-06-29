import os
import subprocess
import sys
import shutil

def build():
    print("Starting Media Keeper build from src folder...")

    # Определяем директорию скрипта (папка src)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Переходим в директорию src, чтобы все пути определялись относительно неё
    os.chdir(script_dir)
    print(f"Working directory changed to: {os.getcwd()}")

    # Убеждаемся, что pyinstaller установлен
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # Получаем версию из config.py с помощью регулярных выражений
    app_version = "v1.0"
    config_path = "config.py"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
                import re
                match = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', content)
                if match:
                    app_version = match.group(1)
        except Exception as e:
            print(f"Warning: Failed to read version from config.py: {e}")

    app_name = "Media_Keeper"

    # Базовая команда
    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", app_name
    ]

    # Добавляем папки ресурсов динамически, если они существуют
    data_dirs = ["icons", "launcher", "languages"]
    for d in data_dirs:
        if os.path.exists(d):
            # Используем os.pathsep (; для Windows, : для Unix)
            pyinstaller_cmd.extend(["--add-data", f"{d}{os.pathsep}{d}"])
            
    # Добавляем исполняемые утилиты (только fpcalc)
    binaries = ["fpcalc.exe"]
    for b in binaries:
        if os.path.exists(b):
            pyinstaller_cmd.extend(["--add-binary", f"{b}{os.pathsep}."])

    # Скрытые импорты PyQt6, необходимые для динамической загрузки модулей в рантайме
    hidden_imports = [
        "PyQt6.QtSvg",
        "PyQt6.QtSvgWidgets",
        "PyQt6.QtMultimedia",
        "PyQt6.QtMultimediaWidgets",
        "PyQt6.sip",
        "PIL",
        "modules.cleaner.vhash",
        "modules.cleaner.ahash_audio"
    ]
    for imp in hidden_imports:
        pyinstaller_cmd.extend(["--hidden-import", imp])

    # Исключаем тяжелые библиотеки для уменьшения размера EXE
    excludes = ["tkinter", "matplotlib", "numpy", "scipy"]
    for exc in excludes:
        pyinstaller_cmd.extend(["--exclude-module", exc])

    # Добавляем иконку приложения, если она есть
    icon_path = os.path.join("launcher", "icon.ico")
    if os.path.exists(icon_path):
        pyinstaller_cmd.extend(["--icon", icon_path])

    # Точка входа в приложение
    pyinstaller_cmd.append("main.py")

    print(f"Running command: {' '.join(pyinstaller_cmd)}")
    
    # Запуск сборки
    result = subprocess.run(pyinstaller_cmd, shell=False)
    
    if result.returncode == 0:
        print("\nBuild completed successfully!")
        exe_name = f"{app_name}.exe"
        src_exe = os.path.join("dist", exe_name)
        
        if os.path.exists(src_exe):
            root_dist = os.path.join(os.path.dirname(script_dir), "dist")
            os.makedirs(root_dist, exist_ok=True)
            dest_exe = os.path.join(root_dist, exe_name)
            
            try:
                shutil.copy2(src_exe, dest_exe)
                print(f"Executable successfully copied to root folder: {dest_exe}")
            except Exception as e:
                print(f"Warning: Failed to copy executable to root dist folder: {e}")
    else:
        print("\nAn error occurred during build.")
        sys.exit(result.returncode)

if __name__ == "__main__":
    build()
