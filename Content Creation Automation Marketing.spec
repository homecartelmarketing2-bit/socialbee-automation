# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_all, copy_metadata


ROOT = SPECPATH

datas = []
binaries = []
hiddenimports = [
    'eel', 'bottle', 'bottle_websocket', 'gevent', 'geventwebsocket',
    'src', 'src.config', 'src.airtable_client', 'src.caption',
    'src.socialbee_poster', 'src.app_window', 'src.zoho_client',
    'src.browser_utils',
    'PIL', 'PIL._imaging',
    'playwright', 'playwright.sync_api',
]


def add_data_if_exists(name, dest='.'):
    source = os.path.join(ROOT, name)
    if os.path.exists(source):
        datas.append((source, dest))


add_data_if_exists('web', 'web')

# Keep package metadata available for libraries that call importlib.metadata.
datas += copy_metadata('imageio')
datas += copy_metadata('imageio-ffmpeg')

for package_name in ('eel', 'imageio', 'imageio_ffmpeg'):
    package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

# Bundle Playwright's node driver (node.exe + JS package).
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
    name='Content Creation Automation Marketing',
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
    name='Content Creation Automation Marketing',
)
