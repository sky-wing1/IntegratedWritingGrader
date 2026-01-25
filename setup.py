"""
py2app build script for IntegratedWritingGrader
Usage: python setup.py py2app
"""

import re
from setuptools import setup

# Read version from app/__init__.py
with open('app/__init__.py', 'r', encoding='utf-8') as f:
    VERSION = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', f.read()).group(1)

APP = ['app/main.py']
DATA_FILES = [
    ('app/resources/templates', [
        'app/resources/templates/名簿.tex',
        'app/resources/templates/復テ個別化スタイル.sty',
        'app/resources/templates/添削用紙個別化.tex',
        'app/resources/templates/高２Integrated Writing 添削用紙.tex',
    ]),
]
OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'resources/AppIcon.icns',
    'plist': {
        'CFBundleName': 'IntegratedWritingGrader',
        'CFBundleDisplayName': '英作文採点',
        'CFBundleIdentifier': 'com.integratedwritinggrader.app',
        'CFBundleVersion': VERSION,
        'CFBundleShortVersionString': VERSION,
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,
        'LSMinimumSystemVersion': '10.15',
    },
    'packages': ['PyQt6', 'fitz', 'app'],
    'includes': [
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
    ],
    'excludes': [
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
    ],
}

setup(
    name='IntegratedWritingGrader',
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
