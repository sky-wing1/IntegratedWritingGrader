# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for IntegratedWritingGrader"""

import sys
from pathlib import Path

block_cipher = None

# プロジェクトルート
project_root = Path(SPECPATH)

a = Analysis(
    ['app/main.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        # リソースファイルがあれば追加
    ],
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'fitz',
        'pymupdf',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',  # アイコン生成用なので本番では不要
    ],
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
    name='IntegratedWritingGrader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUIアプリなのでコンソール非表示
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='IntegratedWritingGrader',
)

# macOS用 .app バンドル
app = BUNDLE(
    coll,
    name='IntegratedWritingGrader.app',
    icon='resources/AppIcon.icns',
    bundle_identifier='com.integratedwritinggrader.app',
    info_plist={
        'CFBundleName': 'IntegratedWritingGrader',
        'CFBundleDisplayName': '英作文採点',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,  # ダークモード対応
        'LSMinimumSystemVersion': '10.15',
    },
)
