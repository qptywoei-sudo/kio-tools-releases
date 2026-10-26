"""Approved artwork, derived OS icons and immutable legacy identity regressions."""
from pathlib import Path
import hashlib,json,sys,unittest
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent'))
import language
MASTER_SHA='e3196a03cf3d259b5e3662c39206b36339b22986ac910b0e772fb84f7759957b'
LEGACY_ICON_SHA='0b6a7ed393f4f4e01b91ab09d7e8c99bce965ab68342b9f7ef86475a03923318'
PROTECTED={
 'desktop-ui/src/services/local-agent.ts':'21be9c390cb9f1dc8a5fe9c859228bbc8bc66203d5fed04b1b64ed87a4d88e72',
 'agent/update-channel.json':'26e2075dd63bde180c0bd66b0c39921056b9fe624ebbaa8189872afa22a4db61',
 'agent/update_security.py':'e7a30b70457762e6f9eaf373d0e8695f438f9e025a4ac98ecaa5ef117389d52a',
 'agent/update_helper.py':'7fb5d40ae052980dd479c97974126f683c488dfa99852ae1d64da3e7a621b5fc',
 'agent/updater.py':'089ec6adba64391fc4a23a651182781dc3f58c8197cb2f4d8dc55b655aa7c128',
 'agent/secure_tokens.py':'4dd8f6efcf4d1fbc2892abd3cd41b6b42748f161a80b01bdf7493f4029574db9',
 'agent/google_drive.py':'94444cc902d42dfb3b55b49b0177b7fc39974c2f0565802d5154ee1b278bf841',
 'agent/kio_account.py':'0f6086cb938e0b3a551d14e446aee6f721fddc747bc8efb1a40f7d562b3f43ab',
 'mac/sign-local.py':'c3268840d6f78c30c471e73fd9c74822e5cd78521f202fcc2fbd16e3f5cc0560',
 'COPYING':'62587d38d3aed8de92dbb52179c49595f70b20a925f836514cbc9c2d90dac728',
}

# Exact authorized additions for the post-update bundle-name transaction.
# Removing only these hooks must recover the ORIGINAL protected updater bytes;
# its signature, URL, download, install, rollback and credential logic stay pinned.
MIGRATION_HOOKS=(
 b"  # The normal Mac backend observes the ORIGINAL update transaction. The\n  # detached name helper never moves an actively running app or user data.\n  from mac_bundle_migration import prepare_and_quit\n  threading.Thread(target=prepare_and_quit,args=(self.agent,self.root,Path(__file__).resolve().parent.parent,VERSION,self.config),daemon=True).start()\n",
 b"   name=read_json(self.root/'bogo-name-migration.json',{})\n   own=install_layout(Path(__file__).resolve().parent.parent,os.name=='nt')[0]\n   if name.get('version')==VERSION and name.get('phase')=='failed' and str(own) in (name.get('source'),name.get('target')):\n    r['nameMigration']={k:name[k] for k in ('phase','error','renamed','originalBytesRetained') if k in name}\n    r.update(phase='error',error='updateInstallFailed')\n",
)
def original_updater_bytes(raw):
 for hook in MIGRATION_HOOKS:
  if raw.count(hook)!=1:raise ValueError('Unexpected name-migration hook shape')
  raw=raw.replace(hook,b'',1)
 return raw

class BogoBrandingTests(unittest.TestCase):
 def master(self):return Image.open(ROOT/'desktop-ui/src/assets/bogo-tools-icon.png')
 def test_approved_original_identity_and_transparency(self):
  path=ROOT/'desktop-ui/src/assets/bogo-tools-icon.png';pin=json.loads((ROOT/'bogo-tools-artwork.json').read_text())
  self.assertEqual(path.stat().st_size,28248);self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),MASTER_SHA)
  self.assertEqual(pin['sha256'],MASTER_SHA);self.assertEqual(pin['id'],'tools')
  with self.master() as image:
   self.assertEqual((image.format,image.size,image.mode),('PNG',(1024,1024),'RGBA'))
   self.assertEqual(image.getchannel('A').getextrema(),(0,255));self.assertEqual(image.getpixel((0,0))[3],0)
   self.assertEqual(image.getpixel((128,512)),(252,117,1,255))
  svg=ROOT/pin['sourceSvg'];self.assertEqual(hashlib.sha256(svg.read_bytes()).hexdigest(),pin['sourceSvgSha256'])
 def test_old_approved_png_is_preserved_separately(self):
  legacy=ROOT/'desktop-ui/src/assets/kio-tools-icon.png'
  self.assertTrue(legacy.is_file())
  self.assertEqual(hashlib.sha256(legacy.read_bytes()).hexdigest(),LEGACY_ICON_SHA)
  self.assertNotEqual(MASTER_SHA,LEGACY_ICON_SHA)
 def test_windows_derivatives_are_from_the_original(self):
  self.assertEqual((ROOT/'windows/GalaxyControl.png').read_bytes(),(ROOT/'desktop-ui/src/assets/bogo-tools-icon.png').read_bytes())
  with Image.open(ROOT/'windows/GalaxyControl.ico') as icon:
   self.assertEqual(icon.ico.sizes(),{(n,n) for n in (16,20,24,32,40,48,64,128,256)})
   for size in icon.ico.sizes():
    frame=icon.ico.getimage(size).convert('RGBA');self.assertEqual(frame.size,size);self.assertEqual(frame.getpixel((0,0))[3],0)
  with self.master() as original,Image.open(ROOT/'windows/BogoToolsStartup.png') as startup:
   self.assertEqual(startup.size,(240,240));self.assertEqual(startup.convert('RGBA').tobytes(),original.resize((240,240),Image.Resampling.LANCZOS).tobytes())
 def test_mac_icns_retains_original_largest_representation(self):
  with self.master() as original,Image.open(ROOT/'mac/KIOTools.icns') as icon:
   icon.size=(1024,1024);icon.load();self.assertEqual(icon.convert('RGBA').tobytes(),original.tobytes())
 def test_auth_data_update_and_license_policy_is_unchanged(self):
  for name,expected in PROTECTED.items():
   raw=(ROOT/name).read_bytes()
   if name=='agent/updater.py':raw=original_updater_bytes(raw)
   self.assertEqual(hashlib.sha256(raw).hexdigest(),expected,name)
 def test_original_updater_pin_rejects_changes_outside_exact_migration_hooks(self):
  raw=(ROOT/'agent/updater.py').read_bytes();original=original_updater_bytes(raw)
  self.assertEqual(hashlib.sha256(original).hexdigest(),PROTECTED['agent/updater.py'])
  mutated=raw.replace(b"raise AgentError('updateNotAvailable')",b"raise AgentError('tampered')",1)
  self.assertNotEqual(hashlib.sha256(original_updater_bytes(mutated)).hexdigest(),PROTECTED['agent/updater.py'])
  with self.assertRaises(ValueError):original_updater_bytes(raw.replace(MIGRATION_HOOKS[0],b'',1))
 def test_callback_and_startup_copy_use_current_brand_in_every_language(self):
  for code in ('ko','en','vi','ja','zh-CN','zh-TW'):
   page=language.callback_page('startup.title',code).decode()
   self.assertIn('Bogo Tools',page);self.assertNotIn('KIO',page);self.assertNotIn('GalaxyControl',page)
   self.assertIn('Bogo Tools',language.text('startup.title',code))

if __name__=='__main__':unittest.main(verbosity=2)
