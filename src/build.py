import os
import subprocess
import sys
import shutil

def build():
    # Переходим в корень проекта
    src_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(src_dir)
    os.chdir(root_dir)
    
    spec_path = os.path.join(root_dir, "Media_Keeper.spec")
    if not os.path.exists(spec_path):
        spec_path = os.path.join(src_dir, "Media_Keeper.spec")

    print(f"[BUILD] Запуск официальной спецификации PyInstaller: {spec_path}")

    # Проверяем PyInstaller
    try:
        import PyInstaller
    except ImportError:
        print("[BUILD] Установка PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # Выполняем сборку по официальному .spec файлу
    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        spec_path
    ]

    print(f"[BUILD] Команда сборки: {' '.join(pyinstaller_cmd)}")
    result = subprocess.run(pyinstaller_cmd, shell=False)

    if result.returncode == 0:
        print("\n[BUILD] Сборка успешно завершена!")
        app_name = "Media_Keeper.exe"
        src_exe = os.path.join(root_dir, "dist", app_name)
        if not os.path.exists(src_exe):
            src_exe = os.path.join(src_dir, "dist", app_name)
            
        if os.path.exists(src_exe):
            root_dist = os.path.join(root_dir, "dist")
            os.makedirs(root_dist, exist_ok=True)
            dest_exe = os.path.join(root_dist, app_name)
            if src_exe != dest_exe:
                shutil.copy2(src_exe, dest_exe)
            print(f"[BUILD] Финальный исполняемый файл готов: {dest_exe}")
    else:
        print("\n[BUILD] Ошибка при сборке приложения.")
        sys.exit(result.returncode)

if __name__ == "__main__":
    build()
