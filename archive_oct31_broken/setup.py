# setup.py
from setuptools import setup

APP = ['launcher.py']

INFO_PLIST = dict(
    CFBundleName='Retail Ad Monitor',
    CFBundleDisplayName='Retail Ad Monitor',
    CFBundleIdentifier='com.GALE.retailadmonitor',
    CFBundleShortVersionString='0.1.0',
    CFBundleVersion='0.0.0',
    NSHighResolutionCapable=True,
    NSPrincipalClass='NSApplication',  # keep; we removed the nib
    # NSMainNibFile intentionally omitted
)

OPTIONS = dict(
    argv_emulation=False,  # IMPORTANT: disable AppleEvent argv emulation
    packages=[],
    includes=[],
    resources=[],
    plist=INFO_PLIST,
)

setup(
    app=APP,
    name='Retail Ad Monitor',
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)