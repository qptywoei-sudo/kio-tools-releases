"""Disposable registry/cache preservation tests; no real user state or browser."""
import sys,time,uuid,json,threading,http.client,tempfile,queue
from pathlib import Path
from unittest.mock import patch
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import review_tests as reviewed
import server as server_module
from kio_fixture import VerifiedAgent
from common import AgentError,atomic_json,read_json

class UploadCacheTests(unittest.TestCase):
 setUp=reviewed.ReviewAPITests.setUp
 tearDown=reviewed.ReviewAPITests.tearDown
 request=reviewed.ReviewAPITests.request
 def cached(self,name='file.png',owner=None,kind='upload',age=0):
  folder=self.agent.state/'uploads'/str(uuid.uuid4());folder.mkdir();path=folder/name;path.write_bytes(b'Only disposable uploaded copy')
  ident=self.agent.register(path,owner or self.origin,kind)['id'];self.agent.files[ident]['created']-=age
  return ident,path
 def upload(self,name='file.png',owner=None):
  owner=owner or self.origin;connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5);connection.request('POST','/uploads',b'Only disposable upload',{'Origin':owner,'X-Local-Agent-Token':self.tokens[owner],'X-File-Name':name,'Content-Type':'image/png'});response=connection.getresponse();status=response.status;body=json.loads(response.read());connection.close();return status,body
 def wait(self,predicate,timeout=3):
  deadline=time.monotonic()+timeout
  while time.monotonic()<deadline:
   if predicate():return
   time.sleep(.01)
  self.fail('Disposable asynchronous fixture did not complete')
 def capture(self,mode='success'):
  extension='chrome-extension://abcdefghijklmnopabcdefghijklmnop';self.agent.origins.add(extension);self.tokens[extension]=self.agent.pair(extension,'Disposable upload cache fixture')['token'];self.agent.browser={'origin':extension,'lastSeen':time.time(),'browser':'Fixture'}
  self.agent.listeners.append((extension,queue.Queue()))  # Labelled live receiver fixture.
  ident=str(uuid.uuid4());cancel=threading.Event();answer={}
  output=self.path/'saved-result.png';output.write_bytes(b'SAVED ARTIFACT MUST SURVIVE');original=self.path/'selected-original.png';original.write_bytes(b'USER ORIGINAL MUST SURVIVE')
  original_id=self.agent.register(original,self.origin,'native')['id'];artifact_id=self.agent.register(output,self.origin,'artifact')['id']
  def progress(_):
   if cancel.is_set():raise AgentError('cancelled')
  def engine(op,paths,options,progress):
   self.assertTrue(all(Path(tile['path']).is_file() for tile in options['tiles']))
   if mode=='engine-failed':raise AgentError('processingFailed')
   return {'files':[str(output)],'success':True}
  def run():
   try:answer['result']=self.agent.web_capture(ident,{},self.origin,progress)
   except AgentError as error:answer['error']=error.code
  with patch.object(self.agent,'engine_job',side_effect=engine):
   thread=threading.Thread(target=run);thread.start();self.wait(lambda:ident in self.agent.web_waiters)
   status,tile=self.upload('tile-1.png',extension);self.assertEqual(status,201);tile_path=Path(self.agent.files[tile['id']]['path'])
   if mode=='cancelled':cancel.set()
   else:
    body={'id':ident,'errorCode':'tabChanged'} if mode=='browser-failed' else {'id':ident,'tiles':[{'id':tile['id'],'x':0,'y':0,'viewportWidth':1,'viewportHeight':1}],'width':1,'height':1}
    self.assertEqual(self.request('POST','/browser/result',body,origin=extension)[0],200)
   thread.join(timeout=3);self.assertFalse(thread.is_alive())
  self.assertFalse(tile_path.exists());self.assertNotIn(tile['id'],self.agent.files);self.assertNotIn(ident,self.agent.web_waiters)
  self.assertEqual(original.read_bytes(),b'USER ORIGINAL MUST SURVIVE');self.assertEqual(output.read_bytes(),b'SAVED ARTIFACT MUST SURVIVE');self.assertIn(original_id,self.agent.files);self.assertIn(artifact_id,self.agent.files)
  if mode=='success':self.assertIn('result',answer)
  else:self.assertEqual(answer['error'],{'engine-failed':'processingFailed','browser-failed':'tabChanged','cancelled':'cancelled'}[mode])
  if mode=='cancelled':
   before=list((self.agent.state/'uploads').iterdir());self.assertEqual(self.upload('tile-2.png',extension)[0],409);self.assertEqual(list((self.agent.state/'uploads').iterdir()),before)
 def test_web_success_reclaims_only_private_tiles(self):self.capture()
 def test_web_engine_failure_reclaims_tiles(self):self.capture('engine-failed')
 def test_web_extension_error_without_tile_ids_reclaims_tracked_tiles(self):self.capture('browser-failed')
 def test_web_cancel_reclaims_tiles_and_rejects_late_uploads(self):self.capture('cancelled')
 def test_registry_larger_than_one_megabyte_survives_agent_restart(self):
  original=self.path/('x'*180+'.txt');original.write_text('Original preserved across restart')
  records={str(uuid.uuid4()):{'path':str(original),'owner':self.origin,'kind':'native','name':original.name,'created':time.time()} for _ in range(4000)};path=self.agent.state/'files.json';atomic_json(path,records)
  self.assertGreater(path.stat().st_size,1_000_000);self.assertEqual(read_json(path,'default'),'default');self.assertEqual(len(read_json(path,{},maximum=server_module.MAX_REGISTRY_BYTES)),4000)
  old=self.agent;old.close();self.agent=VerifiedAgent(old.state,self.ui,self.port);fixture=reviewed.ApprovalFixture();fixture.root=self.agent.bridge.root;self.agent.bridge=fixture;self.server.agent=self.agent
  self.assertEqual(set(self.agent.files),set(records));self.assertEqual(self.agent.resolve(next(iter(records)),self.origin),original);self.assertEqual(original.read_text(),'Original preserved across restart')
 def test_registry_count_and_byte_limits_preserve_existing_metadata(self):
  ident,path=self.cached();before=(self.agent.state/'files.json').read_bytes()
  with patch.object(server_module,'MAX_REGISTERED_FILES',len(self.agent.files)):
   with self.assertRaises(AgentError) as error:self.agent.register(path,self.origin)
  self.assertEqual(error.exception.code,'storageFull');self.assertEqual((self.agent.state/'files.json').read_bytes(),before);self.assertIn(ident,self.agent.files)
  with patch.object(server_module,'MAX_REGISTRY_BYTES',len(before)+1):
   with self.assertRaises(AgentError):self.agent.register(path,self.origin,name='한글'*100)
  self.assertEqual((self.agent.state/'files.json').read_bytes(),before);self.assertTrue(path.exists());self.assertEqual(server_module.MAX_REGISTERED_FILES,20000);self.assertEqual(server_module.MAX_REGISTRY_BYTES,16*1024*1024)
 def test_upload_file_limit_is_reserved_before_creating_any_cache_directory(self):
  for _ in range(3):self.cached()
  before=list((self.agent.state/'uploads').iterdir())
  with patch.object(server_module,'MAX_UPLOAD_FILES',3):self.assertEqual(self.upload()[0],507)
  self.assertEqual(list((self.agent.state/'uploads').iterdir()),before);self.assertEqual(self.agent.upload_reserved_files,0);self.assertEqual(server_module.MAX_UPLOAD_FILES,10000)
 def test_seven_day_cleanup_preserves_new_uploads_active_inputs_and_original_aliases(self):
  old,old_path=self.cached(age=8*86400);new,new_path=self.cached(age=6*86400);active,active_path=self.cached(age=8*86400);alias,alias_path=self.cached(age=8*86400)
  # A private upload is not a user-selected native file. Opaque result aliases
  # remain legitimate and must prevent cleanup from destroying a saved record.
  with self.assertRaises(AgentError) as error:self.agent.register(alias_path,self.origin,'native')
  self.assertEqual(error.exception.code,'forbiddenFile');self.assertEqual(error.exception.status,403)
  artifact_alias=self.agent.register(alias_path,self.origin,'artifact')['id'];self.assertNotEqual(artifact_alias,alias)
  self.assertEqual(self.agent.files[artifact_alias]['kind'],'artifact');self.assertEqual(self.agent.resolve(artifact_alias,self.origin),alias_path)
  original=self.path/'user-original.txt';original.write_bytes(b'KEEP ORIGINAL');native=self.agent.register(original,self.origin,'native')['id'];self.agent.files[native]['created']-=8*86400
  artifact=self.path/'saved-artifact.txt';artifact.write_bytes(b'KEEP ARTIFACT');artifact_id=self.agent.register(artifact,self.origin,'artifact')['id'];self.agent.files[artifact_id]['created']-=8*86400
  self.agent.active_inputs['even-cancelled-but-worker-still-reading']={str(active_path)};self.agent.cleanup_uploads()
  self.assertFalse(old_path.exists());self.assertNotIn(old,self.agent.files)
  for ident,path in ((new,new_path),(active,active_path),(alias,alias_path),(artifact_alias,alias_path),(native,original),(artifact_id,artifact)):self.assertTrue(path.exists());self.assertIn(ident,self.agent.files)
  self.agent.active_inputs.clear();self.agent.cleanup_uploads();self.assertFalse(active_path.exists());self.assertTrue(alias_path.exists());self.assertEqual(original.read_bytes(),b'KEEP ORIGINAL');self.assertEqual(artifact.read_bytes(),b'KEEP ARTIFACT')
 def test_cleanup_cannot_follow_leaf_or_ancestor_symlinks_or_cross_owner(self):
  target=self.path/'real-user-file.png';target.write_bytes(b'NEVER DELETE ORIGINAL');ident,path=self.cached(age=8*86400);self.agent.remove_uploads([ident],self.other);self.assertTrue(path.exists())
  path.unlink();path.symlink_to(target);self.agent.cleanup_uploads();self.assertTrue(path.is_symlink());self.assertEqual(target.read_bytes(),b'NEVER DELETE ORIGINAL');self.assertIn(ident,self.agent.files)
  parent_id,parent_path=self.cached(age=8*86400);directory=parent_path.parent;directory.rename(self.path/'moved-private-cache');directory.symlink_to(self.path,target_is_directory=True);(self.path/parent_path.name).write_bytes(b'ANOTHER USER ORIGINAL');self.agent.cleanup_uploads();self.assertEqual((self.path/parent_path.name).read_bytes(),b'ANOTHER USER ORIGINAL');self.assertIn(parent_id,self.agent.files)
 def test_hourly_cleanup_hook_reclaims_expired_uploads_without_native_actions(self):
  ident,path=self.cached(age=8*86400);self.agent.last_upload_cleanup=time.monotonic()-3601;self.wait(lambda:ident not in self.agent.files,timeout=2);self.assertFalse(path.exists())
 def test_same_extension_concurrent_capture_cannot_delete_another_active_capture_tiles(self):
  extension='chrome-extension://abcdefghijklmnopabcdefghijklmnop';self.agent.tokens[extension]={'digest':'fixture'};self.agent.browser={'origin':extension,'lastSeen':time.time()};self.agent.listeners.append((extension,queue.Queue()));self.agent.web_waiters['existing']={'owner':extension,'uploads':set(),'queue':None}
  with self.assertRaises(AgentError) as error:self.agent.web_capture(str(uuid.uuid4()),{},self.origin,lambda _:None)
  self.assertEqual(error.exception.code,'busy');self.assertIn('existing',self.agent.web_waiters)
 def test_older_mac_does_not_advertise_unsupported_gif_or_recording(self):
  with patch.object(server_module.sys,'platform','darwin'),patch.object(server_module.platform,'machine',return_value='arm64'),patch.object(server_module.platform,'mac_ver',return_value=('12.7.6',('','',''),'')):
   self.assertNotIn('video_gif',self.agent.operations());self.assertNotIn('record_start',self.agent.operations());self.assertNotIn('record',self.agent.capabilities());self.assertIn('capture',self.agent.capabilities())
  with patch.object(server_module.sys,'platform','darwin'),patch.object(server_module.platform,'machine',return_value='arm64'),patch.object(server_module.platform,'mac_ver',return_value=('14.0',('','',''),'')):
   self.assertIn('video_gif',self.agent.operations());self.assertIn('record_start',self.agent.operations());self.assertIn('record',self.agent.capabilities())

if __name__=='__main__':unittest.main(verbosity=2)
