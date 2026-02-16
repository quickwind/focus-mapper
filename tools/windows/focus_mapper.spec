# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None

# Paths relative to build/windows/ directory (where this spec file is)
# We assume this is run via `pyinstaller build/windows/focus_mapper.spec` FROM PROJECT ROOT?
# NO: PyInstaller sets spec_path as base usually if run directly?
# ACTUALLY: The best practice is to set pathex to project root.

# If we run `pyinstaller build/windows/focus_mapper.spec` from project root:
# The spec file is executed. `SPECPATH` is the dir of the spec file.
# relative paths in Analysis arguments are usually relative to CWD if not processed by PyInstaller specially.
# But `datas` paths are relative to CWD.
# Let's make paths absolute based on spec file location to be safe.

# Check if we are in project root or tools/windows
if os.path.basename(os.getcwd()) == "windows" and os.path.basename(os.path.dirname(os.getcwd())) == "tools":
   project_root = os.path.abspath(os.path.join(os.getcwd(), "../../"))
else:
   # Assume project root
   project_root = os.getcwd()

# Directory containing shim scripts (tools/windows)
shim_dir = os.path.join(project_root, 'tools', 'windows')

# Data files to include (source, destination)
# Source is relative to project root
datas = [
    (os.path.join(project_root, 'src/focus_mapper/specs'), 'focus_mapper/specs'),
    (os.path.join(project_root, 'src/focus_mapper/gui/assets'), 'focus_mapper/gui/assets'),
    # Include iso4217parse data files from venv site-packages
    (os.path.join(project_root, '.venv/Lib/site-packages/iso4217parse/data.json'), 'iso4217parse'),
    (os.path.join(project_root, '.venv/Lib/site-packages/iso4217parse/symbols.json'), 'iso4217parse')
]

# --- focus-mapper CLI ---
a_cli = Analysis(
    [os.path.join(shim_dir, 'cli_runner.py')],
    pathex=[os.path.join(project_root, 'src')],
    binaries=[],
    datas=datas,
    hiddenimports=['pyreadline3', 'pandas', 'duckdb'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz_cli = PYZ(a_cli.pure, a_cli.zipped_data, cipher=block_cipher)

exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    a_cli.binaries,
    a_cli.zipfiles,
    a_cli.datas,
    [],
    name='focus-mapper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# --- focus-mapper-wizard CLI ---
a_wizard = Analysis(
    [os.path.join(shim_dir, 'wizard_runner.py')],
    pathex=[os.path.join(project_root, 'src')],
    binaries=[],
    datas=datas,
    hiddenimports=['pyreadline3', 'pandas', 'duckdb'], # Added pyreadline3 just in case
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz_wizard = PYZ(a_wizard.pure, a_wizard.zipped_data, cipher=block_cipher)

exe_wizard = EXE(
    pyz_wizard,
    a_wizard.scripts,
    a_wizard.binaries,
    a_wizard.zipfiles,
    a_wizard.datas,
    [],
    name='focus-mapper-wizard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# --- focus-mapper-gui ---
a_gui = Analysis(
    [os.path.join(shim_dir, 'gui_runner.py')],
    pathex=[os.path.join(project_root, 'src')],
    binaries=[],
    datas=datas,
    hiddenimports=['pyreadline3', 'pandas', 'duckdb', 'tkinter', 'focus_mapper.gui'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz_gui = PYZ(a_gui.pure, a_gui.zipped_data, cipher=block_cipher)

# Splash screen shown during unpacking (before Python starts)
splash = Splash(
    os.path.join(project_root, 'src/focus_mapper/gui/assets/splash.png'),
    binaries=a_gui.binaries,
    datas=a_gui.datas,
    text_pos=(10, 380),
    text_size=12,
    text_color='white',
    text_default='Initializing...',
    always_on_top=True,
)

exe_gui = EXE(
    pyz_gui,
    a_gui.scripts,
    splash,                # Splash target
    splash.binaries,       # Splash binaries
    a_gui.binaries,
    a_gui.zipfiles,
    a_gui.datas,
    [],
    name='focus-mapper-gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False, # GUI app, no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_root, 'src/focus_mapper/gui/assets/icon.ico'),
)
