# PrivacyProjectApp
The user study application for the privacy project using the EntitySentiment model.

We use pyinstaller to package the entire project into a stand-alone executable so that users can run the application without needing python or other dependencies. Below are the steps to do this. Note first make sure the project runs in regular python first before doing the steps below (i.e. python3 main.py).

1. pip3 install pyinstaller
2. Place nltk_data folder in project directory res/ (remove any unnecessary files to reduce executable size)
3. Create main.spec file in project directory. The spec files are listed below:
4. pyinstaller main.spec -w
5. Executable will then be in project directory dist/

Note: 
May need to use dev version of pyinstaller if there are issues.\
There was a Mac issue with pyinstaller which can be fixed by following: https://github.com/pyinstaller/pyinstaller/pull/2969/files




#macOS Spec file
~~~~
# -*- mode: python -*-

block_cipher = None


a = Analysis(['main.py'],
             pathex=['/Users/<USER>/PycharmProjects/PrivacyApp'],
             binaries=[],
             datas=[('res','res')],
             hiddenimports=["nltk.chunk.named_entity"],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          exclude_binaries=True,
          name='main',
          debug=False,
          strip=False,
          upx=True,
          console=False )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='main')
app = BUNDLE(coll,
             name='privacy-project.app',
             icon='sbu_logo.png.icns',
             bundle_identifier='com.stony-brook.nlp.privacy-project',
             info_plist={'NSHighResolutionCapable': 'True'},)
~~~~

#Windows Spec file
