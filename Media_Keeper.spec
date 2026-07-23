# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_all

block_cipher = None
spec_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(spec_dir, "src") if os.path.exists(os.path.join(spec_dir, "src", "main.py")) else spec_dir

datas = []
binaries = []
hiddenimports = [
    "PyQt6.QtSvg",
    "PyQt6.QtSvgWidgets",
    "PyQt6.QtMultimedia",
    "PyQt6.QtMultimediaWidgets",
    "PyQt6.sip",
    "requests",
    "certifi",
    "urllib3",
    "idna",
    "charset_normalizer",
    "utils_io",
    "utils_common",
    "logic_paths",
    "logic_cache",
    "logic_logger",
    "config",
]

# Декларативный сбор нативных пакетов по стандарту PyInstaller
native_packages = ["onnxruntime", "tokenizers", "safetensors", "cv2", "PIL", "PyQt6"]
for pkg in native_packages:
    try:
        d, b, h = collect_all(pkg)
        datas.extend(d)
        binaries.extend(b)
        hiddenimports.extend(h)
    except Exception as e:
        print(f"[SPEC WARN] Не удалось выполнить collect_all для {pkg}: {e}")

# Сбор встроенных папок ресурсов
resource_dirs = ["icons", "launcher", "languages", "assets"]
for rdir in resource_dirs:
    rpath = os.path.join(src_dir, rdir)
    if os.path.exists(rpath):
        datas.append((rpath, rdir))

# Сбор исполняемой бинарной утилиты fpcalc
fpcalc = os.path.join(src_dir, "bin", "fpcalc.exe")
if os.path.exists(fpcalc):
    binaries.append((fpcalc, "bin"))

a = Analysis(
    [os.path.join(src_dir, 'main.py')],
    pathex=[src_dir],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "skimage"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

icon_path = os.path.join(src_dir, "launcher", "icon.ico")
exe_icon = icon_path if os.path.exists(icon_path) else None

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Media_Keeper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=exe_icon
)
