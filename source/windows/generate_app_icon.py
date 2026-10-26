"""Encode the owner-approved Bogo Tools original; never substitute other artwork."""
from pathlib import Path
import hashlib,json,shutil,re
from PIL import Image


def main():
 root=Path(__file__).resolve().parent
 source=root.parent/'desktop-ui/src/assets/bogo-tools-icon.png'
 provenance=json.loads((root.parent/'bogo-tools-artwork.json').read_text())
 data=source.read_bytes()
 if len(data)!=provenance['bytes'] or hashlib.sha256(data).hexdigest()!=provenance['sha256']:
  raise ValueError('Bogo Tools master does not match the approved artwork identity')
 with Image.open(source) as original:
  if original.format!='PNG' or original.size!=(1024,1024) or original.mode!='RGBA':
   raise ValueError('Bogo Tools requires the exact 1024x1024 RGBA PNG master')
  artwork=original.copy()
 if artwork.getchannel('A').getextrema()!=(0,255):
  raise ValueError('Bogo Tools master must retain its transparent background')
 shutil.copyfile(source,root/'GalaxyControl.png')
 sizes=(16,20,24,32,40,48,64,128,256)
 artwork.save(root/'GalaxyControl.ico',format='ICO',sizes=[(n,n) for n in sizes])
 artwork.save(root.parent/'mac/KIOTools.icns',format='ICNS')
 artwork.resize((240,240),Image.Resampling.LANCZOS).save(root/'BogoToolsStartup.png',format='PNG')
 extension=root.parent/'browser-extension/icons'
 extension.mkdir(exist_ok=True)
 for n in (16,32,48,128):artwork.resize((n,n),Image.Resampling.LANCZOS).save(extension/f'icon-{n}.png')
 icon_hash=hashlib.sha256((root/'GalaxyControl.ico').read_bytes()).hexdigest()
 header=root/'TaskbarBranding.h';text=header.read_bytes().decode()
 text,count=re.subn(r'kio-tools-app-[a-f0-9]{8}\.ico|bogo-tools-app-[a-f0-9]{8}\.ico','bogo-tools-app-'+icon_hash[:8]+'.ico',text)
 if count!=1:raise ValueError('Expected exactly one taskbar artwork reference')
 header.write_bytes(text.encode())
 report={'source':provenance['approvedSource'],'source_sha256':provenance['sha256'],'artwork_redrawn':False,'ico_sizes':list(sizes),'ico_sha256':icon_hash,'taskbar_icon':'bogo-tools-app-'+icon_hash[:8]+'.ico','startup_png_sha256':hashlib.sha256((root/'BogoToolsStartup.png').read_bytes()).hexdigest(),'mac_icns_sha256':hashlib.sha256((root.parent/'mac/KIOTools.icns').read_bytes()).hexdigest(),'mac_binary_built':False}
 (root/'app-icon-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(report))


if __name__=='__main__':main()
