import os
import sys
import subprocess

def main():
    # Находим путь к src/build.py относительно текущего файла
    root_dir = os.path.dirname(os.path.abspath(__file__))
    src_build_script = os.path.join(root_dir, "src", "build.py")
    
    if os.path.exists(src_build_script):
        print("Delegating build to src/build.py...")
        # Запускаем дочерний процесс сборщика в src/
        result = subprocess.run([sys.executable, src_build_script])
        sys.exit(result.returncode)
    else:
        print(f"[ERROR] Build script not found in src: {src_build_script}")
        sys.exit(1)

if __name__ == "__main__":
    main()
