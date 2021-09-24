# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

from kivy_deps import sdl2, glew
from kivymd import hooks_path as kivymd_hooks_path

a = Analysis(['wa_keygen_gui.py'],
             pathex=['.'],
             binaries=[],
             datas=[("wa_keygen_gui.kv", ".")],
             hiddenimports=["kivymd"],
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
          name='witness_angel_keygen',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          runtime_tmpdir=None,
          console=True,
          icon='./favicon_white_on_black.ico')

''' UNUSED
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               *[Tree(p) for p in (sdl2.dep_bins + glew.dep_bins)],
               strip=False,
               upx=True,
               upx_exclude=[],
               name='witness_angel_keygen')
'''
