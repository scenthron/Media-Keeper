# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('icons', 'icons'), ('launcher', 'launcher'), ('languages', 'languages'), ('assets', 'assets')]
binaries = [('bin\\fpcalc.exe', 'bin')]
hiddenimports = ['PyQt6.QtSvg', 'PyQt6.QtSvgWidgets', 'PyQt6.QtMultimedia', 'PyQt6.QtMultimediaWidgets', 'PyQt6.sip', 'PIL', 'numpy', 'cv2', 'onnxruntime', 'requests', 'certifi', 'urllib3', 'idna', 'charset_normalizer', 'tokenizers', 'tokenizers.models', 'tokenizers.decoders', 'tokenizers.normalizers', 'tokenizers.pre_tokenizers', 'tokenizers.processors', 'tokenizers.trainers', 'safetensors', 'safetensors.numpy', 'backports', 'jaraco', 'setuptools', 'pkg_resources', 'utils_io', 'utils_common', 'logic_paths', 'logic_cache', 'logic_logger', 'config', 'modules.cleaner.vhash', 'modules.cleaner.dhash', 'modules.cleaner.ahash_audio', 'modules.cleaner.ui_ai_results_tree', 'modules.cleaner.ui_ai_references_panel', 'modules.cleaner.ui_ai_tags_dialog', 'modules.cleaner.ui_ai_group_dialog', 'modules.cleaner.logic_ai_classifier', 'modules.cleaner.logic_ai_cache', 'modules.cleaner.logic_ai_tags', 'modules.cleaner.logic_ai_dump', 'modules.cleaner.logic_ai', 'modules.cleaner.logic_scrfd', 'modules.cleaner.logic_clip', 'modules.cleaner.ai_facade', 'modules.cleaner.db_cache', 'modules.cleaner.db_session', 'modules.cleaner.workers', 'modules.cleaner.workers_move', 'modules.sorter.logic_files', 'modules.sorter.logic_player', 'modules.sorter.logic_mover', 'modules.analyzer.worker', 'modules.editor.audio.worker', 'modules.editor.video.worker', 'modules.editor.image.worker', 'backports.tarfile', 'pkg_resources']
tmp_ret = collect_all('onnxruntime')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('tokenizers')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'skimage', 'sentencepiece', 'transformers', 'huggingface_hub', 'PyQt6.QtSql', 'PyQt6.QtWebEngine', 'PyQt6.QtWebEngineWidgets', 'PyQt6.QAxContainer', 'PyQt6.QtBluetooth', 'PyQt6.QtDBus', 'PyQt6.QtDesigner', 'PyQt6.QtNfc', 'PyQt6.QtSensors'],
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
