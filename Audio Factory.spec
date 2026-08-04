# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

# Trỏ vào thư mục obfuscated_dist để nạp code lõi đã xáo trộn PyArmor
obfuscated_dir = os.path.abspath('obfuscated_dist')
if os.path.exists(obfuscated_dir):
    sys.path.insert(0, obfuscated_dir)

datas = [('assets', 'assets')]
binaries = []
hiddenimports = [
    'PySide6', 'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
    'google.generativeai', 'google.ai.generativelanguage', 'google.genai',
    'pydantic', 'pydantic.v1', 'pydantic_core',
    'grpc', 'grpc._cython', 'grpc._cython.cygrp',
    'deep_translator', 'openai',
    'asyncio', 'asyncio.base_events', 'anyio._backends._asyncio',
    'faster_whisper', 'ctranslate2', 'torch', 'nvidia',
    'core.security', 'core.device_identity', 'core.dpapi_storage',
    'core.license_client', 'core.updater', 'ui.license_dialog', 'version',
    'packaging', 'packaging.version',
    'urllib.request', 'urllib.error', 'urllib.parse', 'http.cookiejar',
    'html.parser', 'winreg', 'ctypes', 'ctypes.wintypes'
]

pkgs_to_collect = [
    'PySide6',
    'google.generativeai',
    'google.ai.generativelanguage',
    'deep_translator',
    'faster_whisper',
    'ctranslate2',
    'onnxruntime',
    'torch',
    'nvidia'
]

for pkg in pkgs_to_collect:
    try:
        tmp_ret = collect_all(pkg)
        datas += tmp_ret[0]
        binaries += tmp_ret[1]
        hiddenimports += tmp_ret[2]
    except Exception:
        pass

# KHỬ TRÙNG LẶP DLL CUDA / CTRANSLATE2 / NVIDIA: Mỗi file DLL chỉ được giữ đúng 1 bản duy nhất
seen_binaries = set()
deduped_binaries = []

for src, dst in binaries:
    src_norm = os.path.normcase(os.path.abspath(src))
    if src_norm not in seen_binaries:
        seen_binaries.add(src_norm)
        deduped_binaries.append((src, dst))

# Bổ sung các file DLL CUDA/CTranslate2/NVIDIA từ site-packages nếu chưa có
venv_site_pkgs = os.path.abspath(os.path.join('.venv', 'Lib', 'site-packages'))
if os.path.exists(venv_site_pkgs):
    for root_dir, _, files in os.walk(venv_site_pkgs):
        for f in files:
            if f.lower().endswith('.dll') and any(k in f.lower() for k in ['cublas', 'cudnn', 'curand', 'cusparse', 'nvrtc', 'zlib', 'ctranslate2']):
                full_p = os.path.join(root_dir, f)
                full_p_norm = os.path.normcase(os.path.abspath(full_p))
                if full_p_norm not in seen_binaries:
                    seen_binaries.add(full_p_norm)
                    rel_dir = os.path.dirname(os.path.relpath(full_p, venv_site_pkgs))
                    deduped_binaries.append((full_p, rel_dir))

binaries = deduped_binaries

# Loại bỏ các module thừa không dùng đến của PySide6 / GUI để giải phóng dung lượng
excludes = [
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebEngineQuick',
    'PySide6.Qt3DCore',
    'PySide6.Qt3DRender',
    'PySide6.QtDesigner',
    'PySide6.QtQuick',
    'PySide6.QtQml',
    'PySide6.QtBluetooth',
    'PySide6.QtNfc',
    'PySide6.QtPositioning',
    'PySide6.QtSensors',
    'PySide6.QtPdf',
    'PySide6.QtPdfWidgets',
    'matplotlib',
    'tkinter'
]

# Lọc bỏ data files liên quan đến WebEngine thừa
datas = [d for d in datas if not any(x in d[0].lower() for x in ['webengine', 'qt3d', 'qtquick', 'designer'])]

a = Analysis(
    ['main.py'],
    pathex=['obfuscated_dist'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Audio Factory',
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
    icon=['assets\\logo.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Audio Factory',
)
