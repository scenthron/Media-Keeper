import os
import sys
import subprocess

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    src_build_script = os.path.join(root_dir, "src", "build.py")
    
    if os.path.exists(src_build_script):
        print("Delegating build to src/build.py...")
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        result = subprocess.run([sys.executable, src_build_script], env=env)
        sys.exit(result.returncode)
    else:
        print(f"[ERROR] Build script not found: {src_build_script}")
        sys.exit(1)

if __name__ == "__main__":
    main()
