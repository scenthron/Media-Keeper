# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[('bin\\fpcalc.exe', 'bin')],
    datas=[('icons', 'icons'), ('launcher', 'launcher'), ('languages', 'languages'), ('assets', 'assets')],
    hiddenimports=['PyQt6.QtSvg', 'PyQt6.QtSvgWidgets', 'PyQt6.QtMultimedia', 'PyQt6.QtMultimediaWidgets', 'PyQt6.sip', 'PIL', 'numpy', 'cv2', 'onnxruntime', 'requests', 'certifi', 'urllib3', 'idna', 'charset_normalizer', 'tokenizers', 'safetensors', 'safetensors.numpy', 'backports', 'backports.tarfile', 'jaraco', 'jaraco.text', 'jaraco.functools', 'jaraco.context', 'pkg_resources', 'setuptools', 'modules.cleaner.vhash', 'modules.cleaner.ahash_audio', 'modules.cleaner.ui_ai_results_tree', 'modules.cleaner.ui_ai_references_panel', 'modules.cleaner.logic_ai_classifier', 'modules.cleaner.logic_ai_cache', 'modules.cleaner.logic_ai', 'modules.cleaner.ai_facade'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'skimage'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
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
    icon=['launcher\\icon.ico'],
)
