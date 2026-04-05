# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = [('assets', 'assets'), ('config', 'config'), ('utils', 'utils'), ('C:/Users/evargas/AppData/Local/ms-playwright/chromium-1208', 'ms-playwright/chromium-1208')]
binaries = []
hiddenimports = ['qasync', 'openpyxl', 'openpyxl.cell._writer', 'openpyxl.drawing.spreadsheet_drawing', 'openpyxl.styles.builtins', 'PySide6.QtSvg', 'PySide6.QtSvgWidgets', 'PySide6.QtNetwork', 'winreg', 'ctypes.wintypes']
hiddenimports += collect_submodules('qasync')
tmp_ret = collect_all('playwright')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['rthook_playwright.py'],
    excludes=['PyQt6', 'PyQt5'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ALERTRAN',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\alertran.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ALERTRAN',
)
