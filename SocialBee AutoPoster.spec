# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

datas = [('web', 'web'), ('config.json.example', '.'), ('.env.example', '.')]
binaries = []
hiddenimports = [
    'eel', 'bottle', 'bottle_websocket', 'gevent', 'geventwebsocket',
    'src', 'src.config', 'src.airtable_client', 'src.caption',
    'src.socialbee_poster', 'src.app_window', 'src.zoho_client',
    'src.browser_utils',
    'PIL', 'PIL._imaging',
    'playwright', 'playwright.sync_api',
]

# Collect eel's JS and internal files
tmp_ret = collect_all('eel')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# Bundle Playwright's node driver (node.exe + JS package)
import playwright
pw_driver_dir = os.path.join(os.path.dirname(playwright.__file__), 'driver')
datas += [(pw_driver_dir, os.path.join('playwright', 'driver'))]


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'tkcalendar'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name='SocialBee AutoPoster',
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name='SocialBee AutoPoster',
)
