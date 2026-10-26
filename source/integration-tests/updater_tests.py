"""Signed release, transport, extraction and rollback tests with isolated fixtures."""
import base64,copy,hashlib,io,json,os,stat,sys,tempfile,threading,unittest,zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
r=Path(__file__).resolve().parents[1];sys.path[:0]=[str(r/'engine'),str(r/'agent'),str(r/'engine/deps-agent'/('arm64' if __import__('platform').machine()=='arm64' else 'x86_64'))]
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from update_security import verified_manifest,extract_verified,allowed_url,version
from update_helper import replace_program
from updater import Updater,DownloadForm,install_layout
from common import VERSION,AgentError
class UpdateTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.key=Ed25519PrivateKey.generate();self.public=base64.b64encode(self.key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode();self.data=b'fixture-release'*100
  self.payload={'format':1,'product':'kio-control','version':'99.0.0','notes':['Test fixture only'],'packages':{p:{'root':'KIO-Control-'+p,'size':len(self.data),'sha256':hashlib.sha256(self.data).hexdigest(),'url':'https://drive.google.com/uc?export=download&id=fixture'} for p in ('Windows','Mac')}}
 def tearDown(self):self.temp.cleanup()
 def sign(self,p=None):
  p=copy.deepcopy(self.payload if p is None else p);raw=json.dumps(p,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode();return {'payload':p,'signature':base64.b64encode(self.key.sign(raw)).decode()}
 def updater(self):
  a=SimpleNamespace(state=self.root,stopping=threading.Event(),jobs={},ai=SimpleNamespace(active=None),health=lambda:{})
  u=Updater(a);u.config={'feedUrl':'https://drive.google.com/uc?export=download&id=fixture','publicKey':self.public};return u
 def test_manifest_tamper_and_different_key_fail_closed(self):
  e=self.sign();self.assertEqual(verified_manifest(e,self.public)['version'],'99.0.0');e['payload']['version']='99.0.1'
  with self.assertRaisesRegex(ValueError,'updateInvalidSignature'):verified_manifest(e,self.public)
  with self.assertRaisesRegex(ValueError,'updateInvalidSignature'):verified_manifest(self.sign(),'invalid')
 def test_signed_manifest_still_rejects_unsafe_or_malformed_metadata(self):
  for field,value in [('url','http://drive.google.com/a'),('url','https://drive.google.com.evil.test/a'),('url','https://user@drive.google.com/a'),('size',True),('sha256','a'*63),('root','../../app')]:
   p=copy.deepcopy(self.payload);p['packages']['Mac'][field]=value
   with self.assertRaises(ValueError):verified_manifest(self.sign(p),self.public)
  self.assertGreater(version('4.10.0'),version('4.9.9'))
 def test_old_version_never_offered_and_transport_failure_never_claims_latest(self):
  u=self.updater();p=copy.deepcopy(self.payload);p['version']='1.0.0'
  with patch('updater.download_response',return_value=io.BytesIO(json.dumps(self.sign(p)).encode())):u._run('check')
  self.assertFalse(u.status()['available']);self.assertEqual(u.status()['phase'],'current')
  with patch('updater.download_response',side_effect=OSError('offline')):u._run('check')
  self.assertEqual(u.status()['phase'],'error');self.assertEqual(u.status()['error'],'updateNetwork')
 def test_download_checks_exact_size_and_digest_before_ready(self):
  u=self.updater()
  with patch('updater.download_response',return_value=io.BytesIO(json.dumps(self.sign()).encode())):u._run('check')
  self.assertTrue(u.status()['available'])
  for data in (self.data[:-1],b'x'*len(self.data),self.data+b'x'):
   with patch('updater.download_response',return_value=io.BytesIO(data)):u._run('download')
   self.assertEqual(u.status()['phase'],'error');self.assertEqual(u.status()['error'],'updateInvalidSignature');self.assertIsNone(u.archive)
  with patch('updater.download_response',return_value=io.BytesIO(self.data)):u._run('download')
  self.assertEqual(u.status()['phase'],'ready');self.assertEqual(u.archive.read_bytes(),self.data)
 def test_preference_persists_and_busy_or_not_ready_install_rejected(self):
  u=self.updater();u.preferences_update({'autoCheck':False});self.assertFalse(Updater(u.agent).status()['autoCheck'])
  with self.assertRaises(AgentError):u.preferences_update({'autoCheck':1})
  with self.assertRaisesRegex(AgentError,'updateNotReady'):u.install()
  u.archive=self.root/'fixture.zip';u.value['phase']='ready';u.agent.ai.active='busy'
  with self.assertRaisesRegex(AgentError,'busy'):u.install()
 def archive(self,entries):
  target=self.root/'test.zip'
  with zipfile.ZipFile(target,'w') as z:
   for name,data,mode in entries:
    i=zipfile.ZipInfo(name);i.external_attr=mode<<16;z.writestr(i,data)
  return target
 def test_extraction_preserves_korean_names_executable_and_safe_python_link(self):
  z=self.archive([('KIO-Control-Mac/KIO 컨트롤.app/bin/python3.13',b'exe',stat.S_IFREG|0o755),('KIO-Control-Mac/KIO 컨트롤.app/bin/python3',b'python3.13',stat.S_IFLNK|0o777)])
  try:root=extract_verified(z,self.root/'out','KIO-Control-Mac')
  except OSError as exc:
   if os.name=='nt' and getattr(exc,'winerror',None)==1314:self.skipTest('Mac symlink extraction requires Windows symlink privilege')
   raise
  p=root/'KIO 컨트롤.app/bin/python3';self.assertEqual(p.read_bytes(),b'exe');self.assertTrue(os.access(p,os.X_OK))
 def test_extraction_rejects_traversal_escaping_links_and_duplicate_paths(self):
  bad=[ [('KIO-Control-Mac/../escape',b'x',0)], [('/KIO-Control-Mac/x',b'x',0)], [('KIO-Control-Mac/x',b'../../outside',stat.S_IFLNK)], [('KIO-Control-Mac/x',b'sibling',stat.S_IFLNK),('KIO-Control-Mac/x/y',b'x',0)], [('KIO-Control-Mac/A',b'x',0),('KIO-Control-Mac/a',b'y',0)] ]
  for n,entries in enumerate(bad):
   with self.assertRaises(ValueError):extract_verified(self.archive(entries),self.root/str(n),'KIO-Control-Mac')
 def test_windows_replacement_preserves_settings_and_user_documents(self):
  old=self.root/'installed';new=self.root/'staged';old.mkdir();new.mkdir()
  for root,value in [(old,'old'),(new,'new')]:
   (root/'KIOControl.exe').write_text(value);(root/'tools').mkdir();(root/'tools/version').write_text(value)
  (old/'KIOControl.ini').write_text('custom shortcuts');(old/'My Photos').mkdir();(old/'My Photos/user.png').write_bytes(b'private')
  backup=Path(replace_program(new,old,'Windows'));self.assertEqual((old/'KIOControl.exe').read_text(),'new');self.assertEqual((old/'KIOControl.ini').read_text(),'custom shortcuts');self.assertEqual((old/'My Photos/user.png').read_bytes(),b'private');self.assertEqual((backup/'KIOControl.exe').read_text(),'old')
 def test_replacement_failure_restores_existing_program(self):
  old=self.root/'installed';new=self.root/'staged';old.mkdir();new.mkdir();(old/'data').write_text('keep');(new/'data').write_text('new');original=Path.rename
  def rename(p,to):
   if '.incoming-' in p.name:raise OSError('fixture failure after backup')
   return original(p,to)
  with patch.object(Path,'rename',rename),self.assertRaises(OSError):replace_program(new,old,'Mac')
  self.assertEqual((old/'data').read_text(),'keep')
 def test_installer_uses_the_shipped_runtime_layout_for_each_platform(self):
  target,runtime,arch=install_layout(Path('/portable/tools/engine'),True);self.assertEqual(target.as_posix(),'/portable');self.assertEqual(runtime.as_posix(),'/portable/tools/python');self.assertEqual(arch,'win64')
  target,runtime,arch=install_layout(Path('/Applications/KIO.app/Contents/Resources/tools/engine'),False,'arm64');self.assertEqual(target.as_posix(),'/Applications/KIO.app');self.assertEqual(runtime.as_posix(),'/Applications/KIO.app/Contents/Resources/tools/python/arm64')
 def test_drive_confirmation_form_only_collects_download_fields(self):
  form=DownloadForm();form.feed('<form id="download-form" action="https://drive.usercontent.google.com/download"><input type="hidden" name="id" value="abc"><input type="hidden" name="confirm" value="t"></form><input type="hidden" name="evil" value="1">')
  self.assertEqual(form.fields,{'id':'abc','confirm':'t'});self.assertTrue(allowed_url(form.action))
if __name__=='__main__':unittest.main()
