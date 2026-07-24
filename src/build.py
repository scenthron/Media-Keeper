import os
import subprocess
import sys
import shutil
import io

# Force UTF-8 for stdout/stderr regardless of OS locale
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Fallback: wrap with utf-8 writer if reconfigure not available
if sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def log(msg):
    """Safe print that never fails on encoding errors."""
    try:
        sys.stdout.write(msg + "\n")
        sys.stdout.flush()
    except Exception:
        sys.stdout.buffer.write((msg + "\n").encode('utf-8', errors='replace'))
        sys.stdout.buffer.flush()


def build():
    src_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(src_dir)
    os.chdir(root_dir)

    spec_path = os.path.join(root_dir, "Media_Keeper.spec")
    if not os.path.exists(spec_path):
        spec_path = os.path.join(src_dir, "Media_Keeper.spec")

    log("[BUILD] Launching PyInstaller with spec: " + spec_path)

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        log("[BUILD] Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        spec_path,
    ]

    log("[BUILD] Running: " + " ".join(pyinstaller_cmd))
    result = subprocess.run(pyinstaller_cmd, shell=False)

    if result.returncode == 0:
        log("[BUILD] Build completed successfully!")
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
            log("[BUILD] Final executable: " + dest_exe)
    else:
        log("[BUILD] Build FAILED.")
        sys.exit(result.returncode)


if __name__ == "__main__":
    build()
