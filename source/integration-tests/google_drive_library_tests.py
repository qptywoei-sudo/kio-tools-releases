"""Drive contract tests with explicit HTTP mocks; no real account or OAuth client."""
import io,json,os,sys,tempfile,time,unittest,hashlib,urllib.parse,urllib.request
from pathlib import Path
from unittest.mock import patch
source=Path(__file__).resolve().parents[1];sys.path[:0]=[str(source/'engine'),str(source/'agent')]
from common import AgentError,atomic_json
from google_drive import GoogleDrive,SCOPE,FOLDER,DEFAULT_ROOT
from kio_storage_tests import MemoryKeychain,browser_fixture

class Reply(io.BytesIO):
 def __init__(self,data,headers=None):super().__init__(data);self.status=200;self.headers=headers or {}
class DriveLibraryTests(unittest.TestCase):
 def setUp(self):
  vault=patch('google_drive.MacKeychain',MemoryKeychain);vault.start();self.addCleanup(vault.stop)
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.drive=GoogleDrive(self.root)
  self.drive.tokens={'refresh_token':'fixture-refresh','access_token':'fixture-access','expires_at':time.time()+3600};self.drive.account={'permissionId':'account-A','emailAddress':'a@example.invalid'}
 def tearDown(self):self.drive.cancel_connect();self.temp.cleanup()
 def stored_credentials(self):
  if self.drive.keychain is not None:return self.drive.keychain.load()
  return self.drive.token_path.read_bytes()if self.drive.token_path.exists()else None
 def folder(self,ident='folder-A',name='Selected'):return {'id':ident,'name':name,'mimeType':FOLDER,'capabilities':{'canAddChildren':True}}
 def file(self,body=b'fixture'):return {'id':'file-A','name':'photo.png','mimeType':'image/png','size':str(len(body)),'sha256Checksum':hashlib.sha256(body).hexdigest()}
 def test_custom_output_roots_are_rejected(self):
  with self.assertRaisesRegex(AgentError,'driveFolderFixed'):self.drive.select_root('folder-A')
  self.assertFalse(self.drive.preferences_path.exists())
 def test_legacy_custom_root_cannot_redirect_new_output(self):
  key=hashlib.sha256(self.drive.account_id().encode()).hexdigest()
  self.drive.preferences={'roots':{key:{'id':'legacy','name':'Custom'}}}
  with patch.object(self.drive,'folder',return_value='kio-root') as folder:
   self.assertEqual(self.drive.root_id(),'kio-root')
  self.assertEqual(self.drive.status()['folderName'],'KIO 컨트롤')
  self.assertEqual(folder.call_args.args[:3],('KIO 컨트롤',None,'root'))
 def test_fixed_root_cache_is_used(self):
  self.drive.folder_cache={'root':'current-account-kio'}
  self.assertEqual(self.drive.root_id(),'current-account-kio')
 def test_folder_listing_is_paginated_and_scoped(self):
  with patch.object(self.drive,'request',return_value=({'files':[self.folder()],'nextPageToken':'page-two'},{})) as request:
   result=self.drive.browse_folders('parent-A','page-one');query=urllib.parse.parse_qs(urllib.parse.urlparse(request.call_args.args[0]).query)
  self.assertEqual(result['nextPageToken'],'page-two');self.assertTrue(result['scopeLimited']);self.assertEqual(query['pageToken'],['page-one']);self.assertIn("'parent-A' in parents",query['q'][0])
 def test_library_search_escapes_query_and_uses_selected_root(self):
  with patch.object(self.drive,'root_id',return_value='parent-A'),patch.object(self.drive,'request',return_value=({'files':[]},{})) as request:
   result=self.drive.list_library(query="a'\\b",kind='photos');query=urllib.parse.parse_qs(urllib.parse.urlparse(request.call_args.args[0]).query)['q'][0]
  self.assertIn("name contains 'a\\'\\\\b'",query);self.assertIn("mimeType contains 'image/'",query);self.assertEqual(result['parentId'],'parent-A')
 def test_arbitrary_scope_and_invalid_ids_are_never_network_requests(self):
  with patch.object(self.drive,'request') as request:
   for ident in ['../../x',"a' or trashed=true",'https://example.com','a'*257]:
    with self.assertRaisesRegex(AgentError,'invalidRequest'):self.drive.file_metadata(ident)
   with self.assertRaisesRegex(AgentError,'invalidRequest'):self.drive.list_library(kind='allDrive')
   request.assert_not_called()
 def test_create_folder_checks_parent_permissions(self):
  with patch.object(self.drive,'file_metadata',return_value=self.folder()),patch.object(self.drive,'request',return_value=(self.folder('new-folder'),{})) as request:
   result=self.drive.create_folder('  Photos  ','folder-A')
  self.assertEqual(result['id'],'new-folder');self.assertEqual(request.call_args.args[2]['parents'],['folder-A']);self.assertEqual(request.call_args.args[2]['name'],'Photos')
 def test_existing_named_folder_reused_without_duplicate_creation(self):
  with patch.object(self.drive,'list_files',side_effect=[[],[self.folder('legacy')]]),patch.object(self.drive,'request') as request:
   self.assertEqual(self.drive.folder('Photos','selected-root','selected-root/Photos'),'legacy');request.assert_not_called()
 def test_download_streams_checks_hash_and_publishes_without_overwrite(self):
  body=b'z'*(1024*1024+123);dest=self.root/'download.png'
  with patch.object(self.drive,'file_metadata',return_value=self.file(body)),patch.object(self.drive.opener,'open',return_value=Reply(body,{'Content-Length':str(len(body))})):
   result=self.drive.download('file-A',dest)
  self.assertEqual(result['bytes'],len(body));self.assertEqual(dest.read_bytes(),body);self.assertEqual(list(self.root.glob('*.part')),[])
  with patch.object(self.drive,'file_metadata',return_value=self.file(body)),self.assertRaisesRegex(AgentError,'unsafePath'):self.drive.download('file-A',dest)
 def test_size_limit_and_truncated_or_corrupt_downloads_leave_no_partial_file(self):
  for body,item,limit,error in [(b'fixture',self.file(),3,'fileTooLarge'),(b'fi',self.file(),100,'driveDownloadFailed'),(b'changed',self.file(),100,'driveDownloadFailed'),(b'x'*20,{**self.file(), 'size':'-1','sha256Checksum':''},10,'fileTooLarge')]:
   dest=self.root/'bad.png'
   with patch.object(self.drive,'file_metadata',return_value=item),patch.object(self.drive.opener,'open',return_value=Reply(body)),self.assertRaisesRegex(AgentError,error):self.drive.download('file-A',dest,limit)
   self.assertFalse(dest.exists());self.assertEqual(list(self.root.glob('*.part')),[])
 def test_account_change_during_download_discards_content(self):
  reply=Reply(b'fixture');read=reply.read
  def switched(count):self.drive.auth_generation+=1;return read(count)
  reply.read=switched
  with patch.object(self.drive,'file_metadata',return_value=self.file()),patch.object(self.drive.opener,'open',return_value=reply),self.assertRaisesRegex(AgentError,'driveAccountChanged'):self.drive.download('file-A',self.root/'bad.png')
  self.assertFalse((self.root/'bad.png').exists());self.assertEqual(list(self.root.glob('*.part')),[])
 def test_cloud_native_documents_are_explicitly_unsupported(self):
  with patch.object(self.drive,'file_metadata',return_value={'id':'file-A','mimeType':'application/vnd.google-apps.document'}),self.assertRaisesRegex(AgentError,'driveUnsupportedDocument'):self.drive.download('file-A',self.root/'document.docx')
 def test_refresh_revocation_clears_saved_token_and_reports_disconnected(self):
  self.drive.tokens['expires_at']=0;self.drive.save_tokens()
  with patch.object(self.drive,'exchange',side_effect=AgentError('driveReconnect')),self.assertRaisesRegex(AgentError,'driveReconnect'):self.drive.access_token()
  self.assertFalse(self.drive.status()['connected']);self.assertFalse(self.drive.token_path.exists())
 def test_logout_secure_storage_failure_does_not_claim_disconnected(self):
  with patch.object(self.drive,'raw',return_value=(200,{},b'')),patch.object(self.drive,'delete_tokens',side_effect=AgentError('driveSecureStorageUnavailable')),self.assertRaisesRegex(AgentError,'driveSecureStorageUnavailable'):self.drive.disconnect()
  self.assertTrue(self.drive.status()['connected']);self.assertEqual(self.drive.status()['error'],'driveSecureStorageUnavailable')
 def test_failed_remote_revocation_is_distinct_from_completed_local_disconnect(self):
  self.drive.save_tokens()
  with patch.object(self.drive,'raw',side_effect=AgentError('driveNetwork')):status=self.drive.disconnect()
  self.assertFalse(status['connected']);self.assertFalse(status['revocationConfirmed']);self.assertEqual(status['error'],'driveRevokeFailed');self.assertFalse(self.drive.token_path.exists())
 def test_revocation_http_error_is_reported_but_already_invalid_token_is_done(self):
  for code,body,revoked in [(500,b'',False),(403,b'',False),(400,b'{"error":"invalid_token"}',True),(200,b'',True)]:
   self.drive.tokens={'refresh_token':'fixture'}
   with patch.object(self.drive,'raw',return_value=(code,{},body)):status=self.drive.disconnect()
   self.assertEqual(status['revocationConfirmed'],revoked);self.assertFalse(status['connected'])
 def test_real_google_checksum_is_requested_and_preferred_to_old_kio_properties(self):
  with patch.object(self.drive,'request',return_value=(self.file(),{})) as request:self.drive.file_metadata('file-A')
  fields=urllib.parse.parse_qs(urllib.parse.urlparse(request.call_args.args[0]).query)['fields'][0];self.assertIn('sha256Checksum',fields)
  body=b'current';item={**self.file(body),'properties':{'sha256':'0'*64}}
  with patch.object(self.drive,'file_metadata',return_value=item),patch.object(self.drive.opener,'open',return_value=Reply(body)):self.drive.download('file-A',self.root/'current.png')
  self.assertEqual((self.root/'current.png').read_bytes(),body)
 def test_late_unauthorized_response_does_not_expire_new_account_token(self):
  future=time.time()+9999
  def changed(*args,**kwargs):self.drive.auth_generation+=1;self.drive.tokens={'refresh_token':'other','access_token':'other','expires_at':future};return (401,{},b'{}')
  with patch.object(self.drive,'raw',side_effect=changed),self.assertRaisesRegex(AgentError,'driveAccountChanged'):self.drive.request('https://www.googleapis.com/drive/v3/about')
  self.assertEqual(self.drive.tokens['expires_at'],future)
 def test_account_fence_blocks_upload_before_network(self):
  with patch.object(self.drive,'list_files') as listing,self.assertRaisesRegex(AgentError,'driveAccountChanged'):self.drive.upload('unused',{'accountId':'account-B'})
  listing.assert_not_called()
 def test_default_destination_is_pinned_even_if_selection_changes(self):
  path=self.root/'fixture.png';path.write_bytes(b'x');meta={'assetId':'fixture','driveRootId':DEFAULT_ROOT,'relativePath':'Photos/x.png','name':'x.png','mime':'image/png','kind':'photos','createdAt':'2026-10-12','sha256':'a'*64};folders=[]
  def folder(name,parent,key,generation):folders.append((name,parent,key));return 'original-default' if parent is None else 'child'
  with patch.object(self.drive,'list_files',return_value=[]),patch.object(self.drive,'root_id',side_effect=AssertionError('must not read changed selection')),patch.object(self.drive,'folder',side_effect=folder),patch.object(self.drive,'request',return_value=({}, {'Location':'https://www.googleapis.com/upload/session'})),patch.object(self.drive,'raw',return_value=(200,{},b'{"id":"saved"}')):
   self.assertEqual(self.drive.upload(path,meta)['id'],'saved')
  self.assertEqual(folders[0],('KIO 컨트롤',None,'root'));self.assertEqual(folders[1][1],'original-default')
 def test_cancelled_switch_preserves_existing_account(self):
  atomic_json(self.drive.config_path,{'installed':{'client_id':'fixture.apps.googleusercontent.com'}});urls=[]
  with browser_fixture(urls):self.drive.connect()
  query=urllib.parse.parse_qs(urllib.parse.urlparse(urls[0]).query);url=query['redirect_uri'][0]+'?'+urllib.parse.urlencode({'state':query['state'][0],'error':'access_denied'})
  with urllib.request.urlopen(url,timeout=3) as response:self.assertEqual(response.status,200)
  self.assertEqual(self.drive.account_id(),'account-a');self.assertTrue(self.drive.status()['connected']);self.assertEqual(self.drive.status()['error'],'driveLoginCancelled')
  deadline=time.time()+2
  while self.drive.session and time.time()<deadline:time.sleep(.05)
 def callback(self,urls):
  query=urllib.parse.parse_qs(urllib.parse.urlparse(urls[0]).query)
  url=query['redirect_uri'][0]+'?'+urllib.parse.urlencode({'state':query['state'][0],'code':'fixture-code'})
  with urllib.request.urlopen(url,timeout=3) as response:result=response.read()
  deadline=time.time()+2
  while self.drive.session and time.time()<deadline:time.sleep(.05)
  return result
 def test_failed_persistence_never_claims_login_success_or_loses_prior_account(self):
  atomic_json(self.drive.config_path,{'installed':{'client_id':'fixture.apps.googleusercontent.com'}});self.drive.tokens['account']=self.drive.account;self.drive.save_tokens();saved=self.stored_credentials();urls=[]
  with browser_fixture(urls),patch.object(self.drive,'exchange',return_value={'access_token':'new-access','refresh_token':'new-refresh','scope':SCOPE}),patch.object(self.drive,'account_info',return_value={'permissionId':'new-account'}),patch.object(self.drive,'save_tokens',side_effect=AgentError('driveSecureStorageUnavailable')):
   self.drive.connect(language='ko');body=self.callback(urls)
  self.assertNotIn('연결이 완료'.encode(),body);self.assertIn('연결하지 못'.encode(),body);self.assertEqual(self.drive.account_id(),'account-a');self.assertEqual(saved,self.stored_credentials())
 def test_successful_switch_invalidates_work_started_while_login_browser_was_open(self):
  atomic_json(self.drive.config_path,{'installed':{'client_id':'fixture.apps.googleusercontent.com'}});urls=[]
  with browser_fixture(urls),patch.object(self.drive,'exchange',return_value={'access_token':'new-access','refresh_token':'new-refresh','scope':SCOPE}),patch.object(self.drive,'account_info',return_value={'permissionId':'new-account'}):
   self.drive.connect();during_login=self.drive.auth_generation;self.assertEqual(self.drive.upload_token(during_login),'fixture-access');self.callback(urls)
  self.assertEqual(self.drive.account_id(),'new-account');self.assertGreater(self.drive.auth_generation,during_login)
  with self.assertRaisesRegex(AgentError,'driveAccountChanged'):self.drive.upload_token(during_login)
 def test_explicit_cancel_never_looks_like_successful_connected_transition(self):
  status=self.drive.cancel_connect();self.assertTrue(status['connected']);self.assertFalse(status['connecting']);self.assertEqual(status['error'],'driveLoginCancelled')
 def test_failed_new_account_validation_preserves_old_token_file(self):
  atomic_json(self.drive.config_path,{'installed':{'client_id':'fixture.apps.googleusercontent.com'}});self.drive.tokens['account']=self.drive.account;self.drive.save_tokens();saved=self.stored_credentials();urls=[]
  with browser_fixture(urls),patch.object(self.drive,'exchange',return_value={'access_token':'new-access','refresh_token':'new-refresh','scope':SCOPE}),patch.object(self.drive,'account_info',side_effect=AgentError('driveReconnect')):
   self.drive.connect();self.callback(urls)
  self.assertEqual(saved,self.stored_credentials());self.assertTrue(self.drive.status()['connected'])
 def test_browser_failure_and_timeout_clear_connecting_without_losing_account(self):
  atomic_json(self.drive.config_path,{'installed':{'client_id':'fixture.apps.googleusercontent.com'}})
  with browser_fixture(error=OSError()),self.assertRaisesRegex(AgentError,'driveBrowserFailed'):self.drive.connect()
  deadline=time.time()+2
  while self.drive.session and time.time()<deadline:time.sleep(.05)
  self.assertFalse(self.drive.status()['connecting']);self.assertTrue(self.drive.status()['connected'])
  with browser_fixture(),patch('google_drive.LOGIN_TIMEOUT',.01):
   self.drive.connect();deadline=time.time()+2
   while self.drive.session and time.time()<deadline:time.sleep(.05)
  self.assertEqual(self.drive.status()['error'],'driveLoginTimeout');self.assertFalse(self.drive.status()['connecting'])
 def test_mac_storage_uses_keychain_with_no_token_file(self):
  class Keychain:
   values={}
   def __init__(self,profile):self.key=str(profile)
   def load(self):return self.values.get(self.key)
   def save(self,data):self.values[self.key]=data
   def delete(self):self.values.pop(self.key,None)
  with patch('google_drive.sys.platform','darwin'),patch('google_drive.MacKeychain',Keychain):
   drive=GoogleDrive(self.root/'mac');drive.tokens={'refresh_token':'keychain-only','account':{'permissionId':'mac-account'}};drive.save_tokens()
   self.assertFalse(drive.token_path.exists());reloaded=GoogleDrive(self.root/'mac');self.assertTrue(reloaded.status()['connected']);self.assertEqual(reloaded.account_id(),'mac-account')
   another=GoogleDrive(self.root/'mac-other');self.assertFalse(another.status()['connected'])
   with patch.object(reloaded,'raw',return_value=(200,{},b'')):reloaded.disconnect()
   self.assertFalse(GoogleDrive(self.root/'mac').status()['connected'])
 def test_permission_not_found_and_quota_errors_are_distinct(self):
  self.assertEqual(self.drive.error_code(403,b'{}'),'drivePermissionRequired');self.assertEqual(self.drive.error_code(404),'driveFileMissing')
  self.assertEqual(self.drive.error_code(403,b'{"error":{"errors":[{"reason":"storageQuotaExceeded"}]}}'),'driveQuota')

if __name__=='__main__':unittest.main(verbosity=2)
