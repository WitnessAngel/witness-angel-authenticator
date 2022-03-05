# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

import re
from pathlib import Path
from kivy_deps import sdl2, glew
from kivymd import hooks_path as kivymd_hooks_path

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

import PyInstaller.config
PyInstaller.config.CONF['distpath'] = "./bin"  # Make it same as buildozer output path

pyproject_data = Path("./pyproject.toml").read_text()
version = re.search(r'''version = ['"](.*)['"]''', pyproject_data).group(1)
assert version, version

a = Analysis(['main.py'],
             pathex=['.'],
             binaries=[],
             datas=[("wa_authenticator_gui.kv", "."), ("config_defaults.ini", ".")] + collect_data_files("wacomponents"),
             hiddenimports=collect_submodules("wacomponents") + collect_submodules("plyer"),
             hookspath=[kivymd_hooks_path],
             runtime_hooks=[],
             excludes=['_tkinter', 'Tkinter', "cv2", "numpy", "pygame"],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)

pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          *[Tree(p) for p in (sdl2.dep_bins + glew.dep_bins)],
          #[],
          #exclude_binaries=True,
          name='witness_angel_authenticator_%s' % version,
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          runtime_tmpdir=None,
          console=True,
          icon='./windows_icon_authenticator_64x64.ico')

''' UNUSED
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
