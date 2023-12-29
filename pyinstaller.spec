# -*- mode: python ; coding: utf-8 -*-

import re, sys, os
from pathlib import Path

from kivymd import hooks_path as kivymd_hooks_path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

import PyInstaller.config
PyInstaller.config.CONF['distpath'] = "bin"  # Make it same as buildozer output path

pyproject_data = Path("pyproject.toml").read_text()
version = re.search(r'''version = ['"](.*)['"]''', pyproject_data).group(1)
assert version, version

root_dir = os.path.abspath(os.getcwd())
assert os.path.isdir(os.path.join(root_dir, "waauthenticator"))

sys.path.append(root_dir)  # To find WAAUTHENTICATOR package

hiddenimports = collect_submodules("waauthenticator") + collect_submodules("wacomponents") + collect_submodules("plyer")

app_name = "witness_angel_authenticator_%s" % version.replace(".","-")

program_icon = "assets/icon_authenticator_512x512.png"
extra_exe_params= []

is_macos = sys.platform.startswith("darwin")

codesign_identity = os.environ.get("MACOS_CODESIGN_IDENTITY", None)
print(">>> macosx codesign identity is", codesign_identity)

if sys.platform.startswith("win32"):
    program_icon = "assets/icon_authenticator_64x64.ico"
    from kivy_deps import sdl2, glew
    extra_exe_params = [Tree(p) for p in (sdl2.dep_bins + glew.dep_bins)]
elif is_macos:
    program_icon = "assets/icon_authenticator_512x512.icns"

USE_CONSOLE = True  # Change this if needed

main_script = os.path.join(root_dir, 'main.py')


a = Analysis([main_script],
             pathex=['.'],
             binaries=[],
             datas=collect_data_files("waauthenticator") + collect_data_files("wacomponents"),
             hiddenimports=hiddenimports,
             hookspath=[kivymd_hooks_path],
             runtime_hooks=[],
             excludes=['_tkinter', 'Tkinter', "enchant", "twisted", "cv2", "numpy", "pygame"],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=None,
             noarchive=True)

pyz = PYZ(a.pure, a.zipped_data,
             cipher=None)

exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          *extra_exe_params,
          #exclude_binaries=True,
          name=app_name,
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          runtime_tmpdir=None,
          console=USE_CONSOLE,
          icon=program_icon,
          codesign_identity=codesign_identity,
          entitlements_file="assets/entitlements.plist",  # For MacOS only
          # This fails because of non-fat dep libs... target_arch="universal2" if is_macos else None,
)

if is_macos:
    app = BUNDLE(exe,
             name=app_name+".app",
             icon=program_icon,
             bundle_identifier="org.witnessangel.authenticator",
             codesign_identity=codesign_identity,
             entitlements_file="assets/entitlements.plist", # For MacOS only
    )


''' UNUSED - FOR DIRECTORY BUILD ONLY
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               *[Tree(p) for p in (sdl2.dep_bins + glew.dep_bins)],
               strip=False,
               upx=True,
               upx_exclude=[],
               name='witness_angel_authenticator')
'''
