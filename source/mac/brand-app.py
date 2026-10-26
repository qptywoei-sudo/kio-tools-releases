"""Apply Bogo Tools display branding to an already built Mac bundle on its owner Mac.

Run before codesign/notarization. Bundle identity, executable, entitlements,
preferences and Keychain service names deliberately remain compatible.
"""
from pathlib import Path
import argparse,plistlib,shutil

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('bundle',type=Path);args=parser.parse_args()
 bundle=args.bundle.resolve();info=bundle/'Contents/Info.plist'
 if bundle.suffix!='.app' or not info.is_file():parser.error('Pass the built .app bundle')
 data=plistlib.loads(info.read_bytes())
 if data.get('CFBundleIdentifier')!='local.galaxycontrol.portable':parser.error('Unexpected bundle identity')
 data.update(CFBundleDisplayName='Bogo Tools',CFBundleName='Bogo Tools',CFBundleIconFile='KIOTools.icns',LSHasLocalizedDisplayName=True)
 resources=bundle/'Contents/Resources';resources.mkdir(exist_ok=True)
 shutil.copyfile(Path(__file__).with_name('KIOTools.icns'),resources/'KIOTools.icns')
 info.write_bytes(plistlib.dumps(data,sort_keys=False))
 print('Bogo Tools branding applied. Sign/notarize after this step.')
