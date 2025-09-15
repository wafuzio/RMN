# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['keyword_input.py'],
    pathex=['/Users/dan.maguire/Documents/Amazon_Scrape'],
    binaries=[],
    datas=[('icon2.png', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Kroger TOA Scraper',
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
    icon='icon2.png',
)

app = BUNDLE(
    exe,
    name='Kroger TOA Scraper.app',
    icon='icon2.png',
    bundle_identifier='com.wafuzio.kroger-toa-scraper',
    info_plist={
        'NSDocumentsFolderUsageDescription': 'Kroger TOA Scraper needs access to the Documents folder to save scraped data, keywords, and configuration files.',
        'NSDesktopFolderUsageDescription': 'Kroger TOA Scraper may need access to save files to the Desktop.',
        'NSDownloadsFolderUsageDescription': 'Kroger TOA Scraper may need access to save scraped data to the Downloads folder.',
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,
        'LSApplicationCategoryType': 'public.app-category.productivity',
    },
)
