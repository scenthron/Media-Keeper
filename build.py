import os
import sys
import subprocess

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    src_build_script = os.path.join(root_dir, "src", "build.py")

    sys.stdout.write("Delegating build to src/build.py...\n")
    sys.stdout.flush()

    if os.path.exists(src_build_script):
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run([sys.executable, src_build_script], env=env)
        sys.exit(result.returncode)
    else:
        sys.stdout.write("[ERROR] Build script not found: " + src_build_script + "\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
