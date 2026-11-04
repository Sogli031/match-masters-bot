# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import os

block_cipher = None
project_root = os.path.abspath('.')

# All root-level .py files are potential hidden imports
root_py_files = [
    p.stem for p in Path(project_root).glob('*.py')
    if p.stem not in ('memory_gui', 'setup', 'primeni_novi_dizajn', 'sync_to_flash')
    and not p.stem.startswith('test_')
]

# tools subpackage
tools_hidden = ['tools.matchmasters_board_reader']

a = Analysis(
    ['memory_gui.py'],
    pathex=[project_root],
    binaries=[],
    datas=[
        ('models', 'models'),
        ('data', 'data'),
        ('assets', 'assets'),
        ('board_config.json', '.'),
        ('board_config_supersize.json', '.'),
        ('display_calibration.json', '.'),
        ('swipe_profile.json', '.'),
        ('memory_gui_timing.json', '.'),
        ('tools/matchmasters_board_reader.py', 'tools'),
        ('tools/matchmasters_board_dump.js', 'tools'),
        ('tools/build_board_agent.ps1', 'tools'),
    ],
    hiddenimports=root_py_files + tools_hidden + [
        'PyQt5.sip',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'onnxruntime',
        'cv2',
        'numpy',
        'PIL',
        'mss',
        'pyautogui',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'tkinter', 'scipy', 'pandas'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MatchMastersBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MatchMastersBot',
)
