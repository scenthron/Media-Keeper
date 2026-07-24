import os
import subprocess
import sys
import shutil

def build():
    # Определяем директорию скрипта (папка src)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Удаляем старый EXE-файл перед сборкой, чтобы гарантировать актуальность результата
    app_name = "Media_Keeper"
    root_dist = os.path.join(os.path.dirname(script_dir), "dist")
    dest_exe = os.path.join(root_dist, f"{app_name}.exe")
    if os.path.exists(dest_exe):
        try:
            os.remove(dest_exe)
            print(f"[INFO] Removed old executable at {dest_exe}")
        except Exception as e:
            print(f"[WARN] Failed to remove old executable: {e}")
            
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
        "--paths", ".",
        "--name", app_name
    ]

    # Добавляем папки ресурсов динамически, если они существуют
    data_dirs = ["icons", "launcher", "languages", "assets"]
    for d in data_dirs:
        if os.path.exists(d):
            # Используем os.pathsep (; для Windows, : для Unix)
            pyinstaller_cmd.extend(["--add-data", f"{d}{os.pathsep}{d}"])
            
    # Добавляем исполняемые утилиты (только fpcalc)
    fpcalc_path = os.path.join("bin", "fpcalc.exe")
    if os.path.exists(fpcalc_path):
        pyinstaller_cmd.extend(["--add-binary", f"{fpcalc_path}{os.pathsep}bin"])
    else:
        print(f"[WARN] fpcalc.exe not found at {fpcalc_path}, it will not be bundled!")

    # Скрытые импорты PyQt6, необходимые для динамической загрузки модулей в рантайме
    hidden_imports = [
        "PyQt6.QtSvg",
        "PyQt6.QtSvgWidgets",
        "PyQt6.QtMultimedia",
        "PyQt6.QtMultimediaWidgets",
        "PyQt6.sip",
        "PIL",
        "numpy",
        "cv2",
        "onnxruntime",
        "requests",
        "certifi",
        "urllib3",
        "idna",
        "charset_normalizer",
        "tokenizers",
        "tokenizers.models",
        "tokenizers.decoders",
        "tokenizers.normalizers",
        "tokenizers.pre_tokenizers",
        "tokenizers.processors",
        "tokenizers.trainers",
        "safetensors",
        "safetensors.numpy",
        "backports",
        "jaraco",
        "setuptools",
        "pkg_resources",
        "utils_io",
        "utils_common",
        "logic_paths",
        "logic_cache",
        "logic_logger",
        "config",
        "modules.cleaner.vhash",
        "modules.cleaner.dhash",
        "modules.cleaner.ahash_audio",
        "modules.cleaner.ui_ai_results_tree",
        "modules.cleaner.ui_ai_references_panel",
        "modules.cleaner.ui_ai_tags_dialog",
        "modules.cleaner.ui_ai_group_dialog",
        "modules.cleaner.logic_ai_classifier",
        "modules.cleaner.logic_ai_cache",
        "modules.cleaner.logic_ai_tags",
        "modules.cleaner.logic_ai_dump",
        "modules.cleaner.logic_ai",
        "modules.cleaner.logic_scrfd",
        "modules.cleaner.logic_clip",
        "modules.cleaner.ai_facade",
        "modules.cleaner.db_cache",
        "modules.cleaner.db_session",
        "modules.cleaner.workers",
        "modules.cleaner.workers_move",
        "modules.sorter.logic_files",
        "modules.sorter.logic_player",
        "modules.sorter.logic_mover",
        "modules.analyzer.worker",
        "modules.editor.audio.worker",
        "modules.editor.video.worker",
        "modules.editor.image.worker",
        "backports",
        "setuptools"
    ]
    for imp in hidden_imports:
        pyinstaller_cmd.extend(["--hidden-import", imp])

    # Добавляем collect-all для тяжелых C++ библиотек с DLL, чтобы предотвратить их потерю
    collect_all_libs = ["onnxruntime", "tokenizers", "cv2", "PyQt6"]
    for lib in collect_all_libs:
        pyinstaller_cmd.extend(["--collect-all", lib])

    # Исключаем тяжелые библиотеки для уменьшения размера EXE и предотвращения падения PyInstaller
    excludes = [
        "tkinter", "matplotlib", "scipy", "skimage", 
        "sentencepiece", "transformers", "huggingface_hub",
        "PyQt6.QtSql", "PyQt6.QtWebEngine", "PyQt6.QtWebEngineWidgets", "PyQt6.QAxContainer",
        "PyQt6.QtBluetooth", "PyQt6.QtDBus", "PyQt6.QtDesigner", "PyQt6.QtNfc", "PyQt6.QtSensors"
    ]
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
