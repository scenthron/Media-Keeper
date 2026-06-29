
import os
import sys

def get_base_path():
    """
    Determines the absolute base path for resources (like assets, languages).
    Handles Dev environment vs Frozen (PyInstaller) environment.
    """
    if getattr(sys, 'frozen', False):
        # Running as compiled EXE
        # sys._MEIPASS is the temp folder where PyInstaller extracts data
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        # Running from source
        # We assume this file is in src/
        base_path = os.path.dirname(os.path.abspath(__file__))

    return base_path

def find_resource_dir(dir_name):
    """
    Tries to find a specific resource directory (e.g., 'languages') 
    checking multiple probable locations relative to base path.
    """
    base = get_base_path()
    # print(f"[DEBUG] Base path for resources: {base}")
    
    # Priority search paths
    candidates = [
        os.path.join(base, dir_name),           # Same level (Dev or flattened build)
        os.path.join(base, "src", dir_name),    # Inside src (Common structure)
        os.path.join(base, "..", dir_name),     # One level up
    ]
    
    # Special check for PyInstaller _MEIPASS root
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            candidates.append(os.path.join(sys._MEIPASS, dir_name))
            candidates.append(os.path.join(sys._MEIPASS, "src", dir_name))

    for path in candidates:
        if os.path.exists(path) and os.path.isdir(path):
            return path
    
    print(f"[ERROR] Resource directory '{dir_name}' NOT found. Checked: {candidates}")
    return None

def get_icons_dir():
    """
    Returns path to the icons directory, compatible with both dev mode and PyInstaller EXE.
    IRON RULE: Use this instead of os.path.normpath(os.path.join(__file__, "..", "..", "icons")).
    All modules must use AppContext.find_resource_dir("icons") or this function.
    """
    return find_resource_dir("icons")

def get_app_data_dir():
    """
    Returns the main user data directory: .mediakeeper
    
    LOCATION LOGIC:
    1. Dev Mode: Parent of 'src' (Project Root, where run.py is).
    2. Frozen Mode: Folder containing the .exe.
    """
    if getattr(sys, 'frozen', False):
        # EXE mode: Folder with executable
        base_dir = os.path.dirname(sys.executable)
    else:
        # Dev mode:
        # User wants default to be INSIDE the program directory (where main.py is).
        # logic_paths.py is in src/, main.py is in src/. 
        # So we use this file's directory as the base.
        src_dir = os.path.dirname(os.path.abspath(__file__)) # .../Project/src
        base_dir = src_dir # .../Project/src

    path = os.path.join(base_dir, ".mediakeeper")
    
    # Ensure directory exists
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        print(f"[WARN] Failed to create app data dir at {path}: {e}")
        
    return path

def get_ffmpeg_bin_dir():
    """Returns path to the LOCAL user data bin directory (for downloading/writing)"""
    bin_dir = os.path.join(get_app_data_dir(), "bin")
    os.makedirs(bin_dir, exist_ok=True)
    return bin_dir

def get_project_bin_dir():
    """Returns path to the bundled bin directory inside the source code (src/bin)"""
    if getattr(sys, 'frozen', False):
        # Сначала проверяем внутри распакованного EXE (sys._MEIPASS для PyInstaller --onefile)
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            cand = os.path.join(meipass, "bin")
            if os.path.exists(cand):
                return cand
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "bin")

def _find_binary_path(filename):
    """
    Search for binary in priority order:
    1. Bundled in source code (src/bin/)
    2. Local Project Root/.mediakeeper/bin (Downloaded by app)
    3. Global PATH search
    """
    # 1. Bundled inside source code
    bundled_path = os.path.join(get_project_bin_dir(), filename)
    if os.path.exists(bundled_path):
        return bundled_path

    # 2. Local AppData bin
    local_bin = get_ffmpeg_bin_dir()
    local_path = os.path.join(local_bin, filename)
    
    if os.path.exists(local_path):
        return local_path
        
    # 2. Global PATH search
    import shutil
    global_path = shutil.which(filename.replace(".exe", "") if os.name != 'nt' else filename)
    if global_path:
        return global_path
        
    # Default to local path if not found anywhere (so UI shows missing local path)
    return local_path

def get_ffmpeg_exe():
    return _find_binary_path("ffmpeg.exe")

def get_ffprobe_exe():
    return _find_binary_path("ffprobe.exe")

def get_fpcalc_exe():
    return _find_binary_path("fpcalc.exe")
