"""Actual local image/registry tests in disposable storage; no browser or user files."""
import sys,unittest,tempfile,threading
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root/'engine'),str(root/'agent')]
from PIL import Image,ImageDraw
from common import AgentError,read_json
from server import Agent
from signature_library import SignatureLibrary
from kio_fixture import verified_account

class NoIndex:
 def resolve(self,ident):raise AgentError('fileMissing',404)

class SignatureTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.state=self.root/'state';self.state.mkdir();self.owner='http://127.0.0.1:4323';self.remote='https://approved.example';self.agent=self.registry();self.library=SignatureLibrary(self.state,self.agent.resolve,self.agent.register)
 def tearDown(self):self.temp.cleanup()
 def registry(self):
  # Exercise the production registry methods without starting background services.
  agent=Agent.__new__(Agent);agent.state=self.state;agent.lock=threading.RLock();agent.files=read_json(self.state/'files.json',{});agent.index=NoIndex();agent.web_waiters={};agent.desktop_origin=self.owner;agent.account=verified_account(self.state);agent.profile_user_id=agent.account.require()['id'];return agent
 def source(self,size=(120,80),transparent=True):
  path=self.root/'original.png';image=Image.new('RGBA',size,(255,255,255,0 if transparent else 255));ImageDraw.Draw(image).line([(30,20),(50,60),(90,35)],fill=(10,20,30,255),width=3);image.save(path);return path,self.agent.register(path,self.owner,'native')
 def assert_code(self,code,callback):
  with self.assertRaises(AgentError) as caught:callback()
  self.assertEqual(caught.exception.code,code)
 def test_private_transparent_copy_preserves_source_and_tightly_crops(self):
  path,source=self.source();original=path.read_bytes();asset=self.library.save(source['id'],'  My signature  ',self.owner);saved=self.agent.resolve(asset['id'],self.owner)
  self.assertEqual(path.read_bytes(),original);self.assertNotEqual(saved,path);self.assertTrue(saved.is_relative_to(self.state/'signatures'));self.assertEqual(asset['label'],'My signature');self.assertEqual(asset['mime'],'image/png')
  with Image.open(saved) as image:
   self.assertEqual(image.mode,'RGBA');self.assertEqual(image.size,(asset['width'],asset['height']));self.assertLess(image.width,120);self.assertLess(image.height,80);self.assertEqual(image.getchannel('A').getbbox(),(0,0,image.width,image.height));self.assertEqual(image.getchannel('A').getextrema(),(0,255))
  if sys.platform!='win32':self.assertEqual((self.state/'signatures').stat().st_mode&0o777,0o700)
 def test_owned_aliases_reuse_and_different_origin_cannot_resolve_local_alias(self):
  _,source=self.source();asset=self.library.save(source['id'],'Signature',self.owner);count=len(self.agent.files)
  self.assertEqual(self.library.list(self.owner)[0]['id'],asset['id']);self.assertEqual(len(self.agent.files),count)
  self.assert_code('unauthorized',lambda:self.agent.resolve(asset['id'],self.remote));remote=self.library.list(self.remote)[0]
  self.assertNotEqual(remote['id'],asset['id']);self.assertEqual(remote['signatureId'],asset['signatureId']);self.assertEqual(self.agent.resolve(remote['id'],self.remote),self.agent.resolve(asset['id'],self.owner));self.assertEqual(self.library.list(self.remote)[0]['id'],remote['id'])
 def test_saved_copy_and_owned_alias_survive_restart_and_removed_source(self):
  path,source=self.source();asset=self.library.save(source['id'],'Reusable',self.owner);path.unlink();agent=self.registry();library=SignatureLibrary(self.state,agent.resolve,agent.register)
  restored=library.list(self.owner);self.assertEqual(len(restored),1);self.assertEqual(restored[0]['id'],asset['id']);self.assertTrue(agent.resolve(asset['id'],self.owner).is_file())
 def test_owner_and_name_validation_never_writes_signature(self):
  _,source=self.source()
  self.assert_code('unauthorized',lambda:self.library.list(''));self.assert_code('unauthorized',lambda:self.library.save(source['id'],'x',''));self.assert_code('unauthorized',lambda:self.library.save(source['id'],'x',self.remote))
  for name in ['','../signature','x\\y','a\0b','x'*81]:self.assert_code('invalidRequest',lambda:self.library.save(source['id'],name,self.owner))
  self.assertEqual(self.library.list(self.owner),[])
 def test_empty_alpha_animation_and_oversized_pixels_are_rejected(self):
  for suffix,image,arguments,code in [('.png',Image.new('RGBA',(20,20),(0,0,0,0)),{},'inputMissing'),('.png',Image.new('RGBA',(10,10),(0,0,0,255)),{'save_all':True,'append_images':[Image.new('RGBA',(10,10),(10,10,10,255))]},'unsupported'),('.png',Image.new('RGBA',(2001,2000),(0,0,0,255)),{},'fileTooLarge')]:
   path=self.root/('invalid'+suffix);image.save(path,**arguments);source=self.agent.register(path,self.owner,'native');self.assert_code(code,lambda:self.library.save(source['id'],'Invalid',self.owner))
  self.assertEqual(self.library.list(self.owner),[])
 def test_library_symlink_and_missing_copy_cannot_register_foreign_file(self):
  _,source=self.source();asset=self.library.save(source['id'],'Signature',self.owner);saved=self.agent.resolve(asset['id'],self.owner);outside=self.root/'outside.png';saved.rename(outside);saved.symlink_to(outside)
  self.assertEqual(self.library.list(self.owner),[]);self.assertTrue(outside.exists());saved.unlink();self.assertEqual(self.library.list(self.owner),[])
 def test_oversized_source_is_bounded_and_preserved(self):
  path=self.root/'large.png'
  with path.open('wb') as stream:stream.truncate(16*1024*1024+1)
  source=self.agent.register(path,self.owner,'native');self.assert_code('fileTooLarge',lambda:self.library.save(source['id'],'Too large',self.owner));self.assertEqual(path.stat().st_size,16*1024*1024+1);self.assertEqual(self.library.list(self.owner),[])
 def test_replaced_library_ancestor_is_rejected_without_writing_outside(self):
  _,source=self.source();original=self.state/'signatures';old=self.root/'moved-library';original.rename(old);original.symlink_to(old,target_is_directory=True)
  self.assert_code('unsafePath',lambda:self.library.save(source['id'],'Signature',self.owner));self.assertEqual(list(old.glob('*.png')),[])

if __name__=='__main__':unittest.main(verbosity=2)
