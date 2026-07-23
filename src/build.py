import os
import subprocess
import sys
import shutil

# Гарантируем UTF-8 вывод логов для любых серверных консолей (Windows Actions CP1252)
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

def build():
    src_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(src_dir)
    os.chdir(root_dir)
    
    spec_path = os.path.join(root_dir, "Media_Keeper.spec")
    if not os.path.exists(spec_path):
        spec_path = os.path.join(src_dir, "Media_Keeper.spec")

    print(f"[BUILD] Launching PyInstaller build with spec: {spec_path}")

    try:
        import PyInstaller
    except ImportError:
        print("[BUILD] Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        spec_path
    ]

    print(f"[BUILD] Running command: {' '.join(pyinstaller_cmd)}")
    result = subprocess.run(pyinstaller_cmd, shell=False)

    if result.returncode == 0:
        print("\n[BUILD] Build completed successfully!")
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
            print(f"[BUILD] Final executable ready: {dest_exe}")
    else:
        print("\n[BUILD] Build failed with errors.")
        sys.exit(result.returncode)

if __name__ == "__main__":
    build()
