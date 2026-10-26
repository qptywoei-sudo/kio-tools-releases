"""Real filesystem/DPAPI/OAuth callback tests; no real Google account required."""
import sys,tempfile,unittest,json,hashlib,time,urllib.request,urllib.error,urllib.parse,os
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
source=Path(__file__).resolve().parents[1];sys.path[:0]=[str(source/'engine'),str(source/'agent')]
from common import AgentError,atomic_json,read_json
from google_drive import GoogleDrive,protect,SCOPE
from storage_library import StorageLibrary,kind_for,COMPLETED_CACHE_AGE
from PIL import Image

class MemoryKeychain:
 """Test-only OS-vault boundary; never invokes the user's real Keychain."""
 values={}
 def __init__(self,profile):self.key=str(Path(profile).resolve())
 def load(self):return self.values.get(self.key)
 def save(self,data):self.values[self.key]=data
 def delete(self):self.values.pop(self.key,None)

def browser_fixture(urls=None,error=None):
 """Intercept the actual host browser adapter without changing os/sys globals."""
 def opened(url):
  if error is not None:raise error
  if urls is not None:urls.append(url)
  return True
 return patch('google_drive.os.startfile' if os.name=='nt' else 'google_drive.webbrowser.open',side_effect=opened)

class FakeDrive:
 def __init__(self):self.connected=True;self.email='fixture@example.invalid';self.fail=False;self.uploads=[]
 def status(self):return {'connected':self.connected,'email':self.email}
 def upload(self,path,metadata):
  if self.fail:raise AgentError('driveNetwork')
  self.uploads.append((Path(path).read_bytes(),metadata));return {'id':'fixture-'+metadata['assetId']}

class StorageTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.source=self.root/'테스트 원본.png';Image.new('RGB',(80,60),'yellow').save(self.source);self.original=self.source.read_bytes();self.drive=FakeDrive();self.settings={'saveMode':'local','saveFolder':str(self.root/'saved')};self.lib=StorageLibrary(self.root/'state',self.settings,self.drive)
 def tearDown(self):
  self.lib.close()
  if self.lib.worker:self.lib.worker.join(3)
  self.assertEqual(self.source.read_bytes(),self.original);self.tmp.cleanup()
 def wait(self):
  if self.lib.worker:self.lib.worker.join(3)
 def test_local_organization_metadata_no_overwrite(self):
  first,info=self.lib.publish([self.source],'image_export');second,_=self.lib.publish([self.source],'image_export')
  self.assertNotEqual(first,second);self.assertEqual(Path(first[0]).read_bytes(),self.original);self.assertIn('사진',Path(first[0]).parts)
  metadata=read_json(self.root/'saved'/'.kio-library'/'items'/(info[0]['assetId']+'.json'))
  self.assertEqual(metadata['sha256'],hashlib.sha256(self.original).hexdigest());self.assertEqual(metadata['schemaVersion'],1);self.assertFalse(Path(metadata['relativePath']).is_absolute());self.assertEqual(self.drive.uploads,[])
 def test_dual_destinations_share_asset_identity_and_content(self):
  self.settings['saveMode']='both';files,items=self.lib.publish([self.source],'image_export');self.wait()
  self.assertEqual(len(self.drive.uploads),1);self.assertEqual(self.drive.uploads[0][0],Path(files[0]).read_bytes());self.assertEqual(self.drive.uploads[0][1]['assetId'],items[0]['assetId']);self.assertEqual(self.lib.status()['pending'],0)
 def test_drive_only_uses_retry_cache_without_permanent_local_output(self):
  self.settings['saveMode']='drive';files,_=self.lib.publish([self.source],'image_export');self.wait();self.assertFalse((self.root/'saved').exists());self.assertTrue(Path(files[0]).is_file());self.assertEqual(self.lib.status()['recent'][0]['status'],'complete')
 def test_failure_durable_retry_and_account_mismatch(self):
  self.settings['saveMode']='both';self.drive.fail=True;files,_=self.lib.publish([self.source],'image_export');self.wait();self.assertEqual(self.lib.status()['failed'],1);self.assertTrue(Path(files[0]).exists())
  self.drive.fail=False;self.drive.email='another@example.invalid';self.lib.retry();self.wait();self.assertEqual(self.lib.status()['recent'][0]['error'],'driveAccountChanged');self.assertEqual(self.drive.uploads,[])
  self.drive.email='fixture@example.invalid';self.lib.retry();self.wait();self.assertEqual(self.lib.status()['pending'],0);self.assertEqual(len(self.drive.uploads),1)
 def test_kind_mapping(self):
  for name,op,kind in [('x.gif','video_gif','gifs'),('x.mp4','record_stop','videos'),('x.pdf','signature_apply','pdf'),('x.png','signature_apply','signatures'),('x.png','code_generate','codes')]:self.assertEqual(kind_for(name,op),kind)
 def test_completed_drive_cache_retained_seven_days_from_completion(self):
  self.settings['saveMode']='drive';files,items=self.lib.publish([self.source],'image_export');self.wait()
  row=self.lib.queue/(items[0]['assetId']+'.json');item=read_json(row);completed=datetime.fromisoformat(item['completedAt']).timestamp()
  self.lib.cleanup_completed(completed+COMPLETED_CACHE_AGE-1);self.assertTrue(Path(files[0]).is_file())
  self.lib.cleanup_completed(completed+COMPLETED_CACHE_AGE+1);self.assertFalse(Path(files[0]).exists());self.assertFalse(Path(files[0]).parent.exists())
  after=read_json(row);self.assertEqual(after['status'],'complete');self.assertIn('cacheExpiredAt',after);self.assertEqual(after['driveId'],item['driveId'])
 def test_failed_and_pending_cache_never_age_out(self):
  self.settings['saveMode']='drive';self.drive.fail=True;files,items=self.lib.publish([self.source],'image_export');self.wait()
  row=self.lib.queue/(items[0]['assetId']+'.json');item=read_json(row);item['completedAt']='2000-01-01T00:00:00+00:00';atomic_json(row,item)
  self.lib.cleanup_completed(time.time()+COMPLETED_CACHE_AGE*3);self.assertTrue(Path(files[0]).is_file())
  item['status']='pending';atomic_json(row,item);self.lib.cleanup_completed(time.time()+COMPLETED_CACHE_AGE*3);self.assertTrue(Path(files[0]).is_file())
 def test_cache_cleanup_never_deletes_outside_its_asset_directory(self):
  self.settings['saveMode']='drive';_,items=self.lib.publish([self.source],'image_export');self.wait()
  row=self.lib.queue/(items[0]['assetId']+'.json');item=read_json(row);item.update(source=str(self.source),name=self.source.name,completedAt='2000-01-01T00:00:00+00:00');atomic_json(row,item)
  self.lib.cleanup_completed(time.time());self.assertTrue(self.source.is_file());self.assertNotIn('cacheExpiredAt',read_json(row))
 def test_legacy_completed_cache_gets_full_retention_before_cleanup(self):
  self.settings['saveMode']='drive';files,items=self.lib.publish([self.source],'image_export');self.wait()
  row=self.lib.queue/(items[0]['assetId']+'.json');item=read_json(row);item.pop('completedAt');item['createdAt']='2000-01-01T00:00:00+00:00';atomic_json(row,item)
  now=time.time();self.lib.cleanup_completed(now);self.assertTrue(Path(files[0]).is_file());self.assertAlmostEqual(datetime.fromisoformat(read_json(row)['completedAt']).timestamp(),now,places=4)
 def test_queue_rejects_source_outside_private_cache(self):
  self.settings['saveMode']='drive';self.drive.fail=True;_,items=self.lib.publish([self.source],'image_export');self.wait()
  row=self.lib.queue/(items[0]['assetId']+'.json');item=read_json(row);item['source']=str(self.source);atomic_json(row,item)
  self.drive.fail=False;self.lib.retry();self.wait();self.assertEqual(self.drive.uploads,[]);self.assertEqual(read_json(row)['error'],'fileMissing')
 def test_sidecar_failure_does_not_undo_confirmed_cloud_upload(self):
  self.settings['saveMode']='both';self.drive.fail=True;files,items=self.lib.publish([self.source],'image_export');self.wait();self.drive.fail=False
  def write(path,value):
   if Path(path).parent.name=='items':raise OSError('fixture read-only local metadata')
   atomic_json(path,value)
  with patch('storage_library.atomic_json',side_effect=write):self.lib.retry();self.wait()
  self.assertEqual(self.lib.status()['pending'],0);self.assertEqual(self.lib.status()['recent'][0]['status'],'complete');self.assertTrue(Path(files[0]).is_file())

class OAuthTests(unittest.TestCase):
 def setUp(self):
  # Publisher configuration must never turn a fixture test into a real login.
  isolated=patch('google_drive.read_json',side_effect=lambda path,default=None,**kwargs:default if Path(path).name=='google-oauth-client.json' else read_json(path,default,**kwargs))
  isolated.start();self.addCleanup(isolated.stop)
  vault=patch('google_drive.MacKeychain',MemoryKeychain);vault.start();self.addCleanup(vault.stop)
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.drive=GoogleDrive(self.root)
 def tearDown(self):
  self.drive.auth_generation+=1
  if self.drive.session:
   deadline=time.time()+2
   while self.drive.session and time.time()<deadline:time.sleep(.05)
  self.tmp.cleanup()
 def config(self):
  p=self.root/'client.json';atomic_json(p,{'installed':{'client_id':'fixture.apps.googleusercontent.com','client_secret':'fixture-client'}});self.drive.configure(p)
 def test_missing_registration_and_web_clients_rejected(self):
  with self.assertRaisesRegex(AgentError,'driveSetupRequired'):self.drive.connect()
  p=self.root/'web.json';atomic_json(p,{'web':{'client_id':'fixture.apps.googleusercontent.com'}})
  with self.assertRaisesRegex(AgentError,'driveDesktopClientRequired'):self.drive.configure(p)
 def test_dpapi_roundtrip_never_stores_plaintext_tokens(self):
  token=b'private-fixture-refresh-token'
  if os.name=='nt':
   encoded=protect(token);self.assertNotIn(token,encoded);self.assertEqual(protect(encoded,True),token)
  else:
   # DPAPI must remain refused on unsupported hosts. The Mac vault is an
   # explicit memory fixture; this is not a claim of actual OS encryption QA.
   with self.assertRaisesRegex(AgentError,'driveSecureStorageUnavailable'):protect(token)
   self.drive.tokens={'refresh_token':token.decode(),'account':{'permissionId':'fixture-only'}};self.drive.save_tokens()
   self.assertFalse(self.drive.token_path.exists());self.assertEqual(json.loads(self.drive.keychain.load())['refresh_token'],token.decode())
   reloaded=GoogleDrive(self.root);self.assertEqual(reloaded.tokens['refresh_token'],token.decode())
 def test_pkce_loopback_rejects_state_then_persists_encrypted_account(self):
  self.config();urls=[];exchanged=[]
  def exchange(values):exchanged.append(values);return {'access_token':'access-fixture','refresh_token':'refresh-fixture','scope':SCOPE,'expires_in':3600}
  with browser_fixture(urls),patch.object(self.drive,'exchange',side_effect=exchange),patch.object(self.drive,'account_info',return_value={'emailAddress':'fixture@example.invalid','displayName':'Fixture'}):
   status=self.drive.connect();self.assertTrue(status['connecting']);query=urllib.parse.parse_qs(urllib.parse.urlparse(urls[0]).query);redirect=query['redirect_uri'][0]
   self.assertTrue(redirect.startswith('http://127.0.0.1:'));self.assertEqual(query['code_challenge_method'],['S256']);self.assertEqual(query['scope'],[SCOPE])
   with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(redirect+'?code=fake&state=invalid',timeout=3)
   self.assertEqual(error.exception.code,400);self.assertEqual(exchanged,[])
   with urllib.request.urlopen(redirect+'?'+urllib.parse.urlencode({'code':'fixture-code','state':query['state'][0]}),timeout=3) as response:self.assertEqual(response.status,200)
   verifier=exchanged[0]['code_verifier'];import base64
   self.assertEqual(base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode(),query['code_challenge'][0]);self.assertTrue(self.drive.status()['connected'])
   if self.drive.keychain is not None:self.assertFalse(self.drive.token_path.exists())
   else:self.assertNotIn(b'refresh-fixture',self.drive.token_path.read_bytes())
   reloaded=GoogleDrive(self.root);self.assertEqual(reloaded.status()['email'],'fixture@example.invalid')
 def test_refresh_and_endpoint_allowlist(self):
  self.config();self.drive.tokens={'refresh_token':'fixture','expires_at':0}
  with patch.object(self.drive,'exchange',return_value={'access_token':'new','expires_in':3600}) as exchange:self.assertEqual(self.drive.access_token(),'new');self.assertEqual(exchange.call_args.args[0]['grant_type'],'refresh_token')
  with self.assertRaisesRegex(AgentError,'driveInvalidEndpoint'):self.drive.raw('https://example.com/not-google')
 def test_resumable_chunks_and_idempotency(self):
  self.config();self.drive.tokens={'refresh_token':'fixture','access_token':'access','expires_at':time.time()+1000};file=self.root/'video.mp4';file.write_bytes(b'x'*(5*1024*1024));meta={'assetId':'00000000-0000-0000-0000-000000000001','relativePath':'영상/2026/10/video.mp4','name':'video.mp4','mime':'video/mp4','kind':'videos','createdAt':'2026-10-12T00:00:00Z','sha256':'a'*64};calls=[]
  def raw(url,method,data,headers,timeout=45):
   calls.append((len(data),headers['Content-Range']));return (308,{'Range':'bytes=0-4194303'},b'') if len(calls)==1 else (200,{},b'{"id":"uploaded"}')
  with patch.object(self.drive,'list_files',return_value=[]),patch.object(self.drive,'folder',return_value='folder'),patch.object(self.drive,'request',return_value=({}, {'Location':'https://www.googleapis.com/upload/session'})),patch.object(self.drive,'raw',side_effect=raw):
   self.assertEqual(self.drive.upload(file,meta)['id'],'uploaded')
  self.assertEqual(calls,[(4194304,'bytes 0-4194303/5242880'),(1048576,'bytes 4194304-5242879/5242880')])
  with patch.object(self.drive,'list_files',return_value=[{'id':'uploaded'}]),patch.object(self.drive,'raw') as raw:self.assertEqual(self.drive.upload(file,meta)['id'],'uploaded');raw.assert_not_called()
 def upload_fixture(self):
  self.config();self.drive.tokens={'refresh_token':'fixture','access_token':'access','expires_at':time.time()+1000};self.drive.account={'emailAddress':'fixture@example.invalid'}
  file=self.root/'video.mp4';file.write_bytes(b'x'*(5*1024*1024))
  meta={'assetId':'00000000-0000-0000-0000-000000000001','account':'fixture@example.invalid','relativePath':'영상/2026/10/video.mp4','name':'video.mp4','mime':'video/mp4','kind':'videos','createdAt':'2026-10-12T00:00:00Z','sha256':'a'*64}
  return file,meta
 def test_upload_rejects_account_change_before_any_network(self):
  file,meta=self.upload_fixture();meta['account']='another@example.invalid'
  with patch.object(self.drive,'raw') as raw:
   with self.assertRaisesRegex(AgentError,'driveAccountChanged'):self.drive.upload(file,meta)
   raw.assert_not_called()
 def test_upload_stops_if_account_switches_during_file_discovery(self):
  file,meta=self.upload_fixture()
  def changed(*args):self.drive.auth_generation+=1;return []
  with patch.object(self.drive,'list_files',side_effect=changed),patch.object(self.drive,'folder') as folder:
   with self.assertRaisesRegex(AgentError,'driveAccountChanged'):self.drive.upload(file,meta)
   folder.assert_not_called()
 def test_generation_bound_request_never_uses_new_account_token(self):
  self.upload_fixture();generation=self.drive.auth_generation;self.drive.auth_generation+=1
  with patch.object(self.drive,'access_token') as token,patch.object(self.drive,'raw') as raw:
   with self.assertRaisesRegex(AgentError,'driveAccountChanged'):self.drive.request('https://www.googleapis.com/drive/v3/about',generation=generation)
   token.assert_not_called();raw.assert_not_called()
 def test_repeated_unauthorized_response_requires_reconnect(self):
  self.upload_fixture()
  with patch.object(self.drive,'upload_token',return_value='fixture'),patch.object(self.drive,'raw',return_value=(401,{},b'{}')):
   with self.assertRaisesRegex(AgentError,'driveReconnect'):self.drive.request('https://www.googleapis.com/drive/v3/about')
 def test_resumable_recovers_acknowledged_chunk_after_network_error(self):
  file,meta=self.upload_fixture();ranges=[]
  def raw(url,method,data,headers,timeout=45):
   ranges.append(headers['Content-Range'])
   if len(ranges)==1:raise AgentError('driveNetwork')
   if len(ranges)==2:return (308,{'Range':'bytes=0-4194303'},b'')
   return (200,{},b'{"id":"resumed"}')
  with patch.object(self.drive,'list_files',return_value=[]),patch.object(self.drive,'folder',return_value='folder'),patch.object(self.drive,'request',return_value=({}, {'Location':'https://www.googleapis.com/upload/session'})),patch.object(self.drive,'raw',side_effect=raw),patch('google_drive.time.sleep'):
   self.assertEqual(self.drive.upload(file,meta)['id'],'resumed')
  self.assertEqual(ranges,['bytes 0-4194303/5242880','bytes */5242880','bytes 4194304-5242879/5242880'])

if __name__=='__main__':unittest.main(verbosity=2)
