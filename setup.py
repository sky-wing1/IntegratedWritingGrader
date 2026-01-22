"""
py2app build script for IntegratedWritingGrader
Usage: python setup.py py2app
"""

from setuptools import setup

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
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
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
