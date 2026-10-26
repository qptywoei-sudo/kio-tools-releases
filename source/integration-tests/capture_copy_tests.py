"""Disposable capture-copy API regression tests.
The image_edit subprocess is real local engine code against tiny temporary PNGs.
Native approval, OS clipboard publication and native settings are labelled mocks;
these tests do not establish Windows/macOS clipboard or capture runtime quality.
No existing user folder, approved asset, installed app or remote service is touched.
"""
import io,json,sys,time,http.client,unittest
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import review_tests as reviewed
import server as server_module
from kio_fixture import VerifiedAgent
from common import AgentError
from PIL import Image

class NativeMock(reviewed.ApprovalFixture):
 def __init__(self):self.calls=[];self.copy_result={'copied':True};self.copy_error=None
 def call(self,operation,args=None,timeout=90):
  self.calls.append((operation,dict(args or {}),timeout))
  if operation=='settings.apply':return {'applied':True}
  if operation=='clipboard.copy':
   if self.copy_error:raise self.copy_error
   return self.copy_result
  raise AgentError('nativeUnavailable')

class CaptureCopyTests(unittest.TestCase):
 request=reviewed.ReviewAPITests.request
 def setUp(self):
  reviewed.ReviewAPITests.setUp(self)
  self.native=NativeMock();self.native.root=self.agent.bridge.root;self.agent.bridge=self.native
  self.results=Path(self.agent.settings['saveFolder']);self.results.mkdir()
  self.keep=self.results/'existing-approved.txt';self.keep.write_bytes(b'KEEP existing disposable output')
 def tearDown(self):reviewed.ReviewAPITests.tearDown(self)
 def png(self,name='source.png',owner=None):
  path=self.path/name;Image.new('RGBA',(32,32),'white').save(path)
  artifact=self.agent.register(path,owner or self.origin,'native')
  return artifact,path
 def copies(self):return [call for call in self.native.calls if call[0]=='clipboard.copy']
 def job(self,operation,inputs,options):
  status,answer=self.request('POST','/jobs',{'operation':operation,'inputs':inputs,'options':options});self.assertEqual(status,202,answer)
  ident=answer['job']['id'];deadline=time.monotonic()+15
  while time.monotonic()<deadline:
   status,data=self.request('GET','/jobs/'+ident);self.assertEqual(status,200,data)
   if data['job']['status'] not in ('queued','running'):return data['job']
   time.sleep(.03)
  self.fail('Disposable engine job did not finish')
 def restart(self):
  old=self.agent;old.close();self.agent=VerifiedAgent(old.state,self.ui,self.port)
  self.native=NativeMock();self.native.root=self.agent.bridge.root;self.agent.bridge=self.native;self.server.agent=self.agent
 def test_defaults_are_actual_boolean_on_and_png(self):
  status,data=self.request('GET','/settings');self.assertEqual(status,200)
  settings=data['settings'];self.assertIs(settings['closeAfterCaptureCopy'],True);self.assertIs(settings['openCaptureEditor'],True);self.assertEqual(settings['captureFormat'],'png');self.assertNotIn('saveFolder',settings)
 def test_off_preferences_persist_across_restart_with_existing_files_and_pairings(self):
  pairings=(self.agent.state/'pairings.json').read_bytes()
  status,data=self.request('PATCH','/settings',{'closeAfterCaptureCopy':False,'openCaptureEditor':False,'captureFormat':'jpg'});self.assertEqual(status,200,data)
  saved=json.loads(self.agent.settings_path.read_text());self.assertIs(saved['closeAfterCaptureCopy'],False);self.assertIs(saved['openCaptureEditor'],False);self.assertEqual(saved['captureFormat'],'jpg')
  self.restart();status,data=self.request('GET','/settings');self.assertEqual(status,200);self.assertIs(data['settings']['closeAfterCaptureCopy'],False);self.assertIs(data['settings']['openCaptureEditor'],False);self.assertEqual(data['settings']['captureFormat'],'jpg')
  self.assertEqual((self.agent.state/'pairings.json').read_bytes(),pairings);self.assertEqual(self.keep.read_bytes(),b'KEEP existing disposable output')
 def test_settings_reject_nonboolean_flags_and_invalid_format_before_native_mock(self):
  for key in ('closeAfterCaptureCopy','openCaptureEditor'):
   for value in (0,1,'true','false',None,[],{}):
    with self.subTest(key=key,value=value):self.assertEqual(self.request('PATCH','/settings',{key:value})[0],400)
  for value in ('jpeg','webp',True,1,None,[],{}):
   with self.subTest(format=value):self.assertEqual(self.request('PATCH','/settings',{'captureFormat':value})[0],400)
  self.assertEqual(self.native.calls,[]);self.assertIs(self.agent.settings['closeAfterCaptureCopy'],True);self.assertIs(self.agent.settings['openCaptureEditor'],True)
 def test_owned_png_routes_only_registry_path_to_native_mock(self):
  artifact,path=self.png();before=path.read_bytes();status,data=self.request('POST','/clipboard/image',{'id':artifact['id']})
  self.assertEqual(status,200,data);self.assertIs(data['copied'],True);self.assertEqual(self.copies(),[('clipboard.copy',{'path':str(path.resolve())},30)]);self.assertEqual(path.read_bytes(),before)
 def test_other_owner_cannot_copy_registered_png(self):
  artifact,path=self.png();before=path.read_bytes();status,data=self.request('POST','/clipboard/image',{'id':artifact['id']},origin=self.other)
  self.assertEqual(status,403,data);self.assertEqual(self.copies(),[]);self.assertEqual(path.read_bytes(),before)
 def test_copy_rejects_arbitrary_path_and_invalid_body_schema(self):
  artifact,path=self.png()
  bodies=[{'path':str(path)}, {'id':artifact['id'],'path':str(path)}, {'id':''},{'id':42},{'id':True},{'id':[]},{'id':{}},[],True,'source.png']
  for body in bodies:
   with self.subTest(body=body):self.assertEqual(self.request('POST','/clipboard/image',body)[0],400)
  self.assertEqual(self.copies(),[])
 def test_replaced_registered_ancestor_cannot_copy_unowned_path(self):
  parent=self.path/'authorized';parent.mkdir();file=parent/'source.png';Image.new('RGB',(4,4),'red').save(file);artifact=self.agent.register(file,self.origin,'native')
  parent.rename(self.path/'moved');outside=self.path/'outside';outside.mkdir();Image.new('RGB',(4,4),'blue').save(outside/'source.png');symlink_or_skip(parent,outside,target_is_directory=True)
  status,data=self.request('POST','/clipboard/image',{'id':artifact['id']});self.assertEqual(status,404,data);self.assertEqual(self.copies(),[])
 def test_non_png_signature_is_rejected_before_native_mock(self):
  path=self.path/'pretend.png';path.write_bytes(b'not a PNG despite the file extension');artifact=self.agent.register(path,self.origin,'native')
  status,data=self.request('POST','/clipboard/image',{'id':artifact['id']});self.assertEqual(status,400,data);self.assertEqual(data['errorCode'],'unsupported');self.assertEqual(self.copies(),[])
 def test_truthy_native_flags_do_not_report_clipboard_success(self):
  artifact,path=self.png();before=path.read_bytes()
  for value in (False,1,'true',None,[],{}):
   self.native.copy_result={'copied':value}
   with self.subTest(native_mock_copied=value):
    status,data=self.request('POST','/clipboard/image',{'id':artifact['id']});self.assertEqual(status,400,data);self.assertEqual(data['errorCode'],'processingFailed');self.assertNotIn('copied',data)
  self.assertEqual(path.read_bytes(),before)
 def test_native_failure_does_not_become_success(self):
  artifact,_=self.png();self.native.copy_error=AgentError('clipboardFailed')
  status,data=self.request('POST','/clipboard/image',{'id':artifact['id']});self.assertEqual(status,400,data);self.assertEqual(data['errorCode'],'clipboardFailed');self.assertNotIn('copied',data)
 def test_copy_requires_authentication_before_registry_and_native_mock(self):
  artifact,_=self.png();connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
  try:
   connection.request('POST','/clipboard/image',json.dumps({'id':artifact['id']}),{'Origin':self.origin,'Content-Type':'application/json'})
   response=connection.getresponse();body=json.loads(response.read());self.assertEqual(response.status,401,body)
  finally:connection.close()
  self.assertEqual(self.copies(),[])
 def test_real_render_for_clipboard_stays_private_and_remains_owned_copyable(self):
  artifact,source=self.png();original=source.read_bytes();existing={p.name:p.read_bytes() for p in self.results.iterdir()}
  result=self.job('image_edit',[artifact['id']],{'format':'png','clipboardOnly':True,'layers':[{'type':'rect','x':4,'y':4,'width':12,'height':12,'fill':'#ff0000'}]})
  self.assertEqual(result['status'],'complete',result);files=result['result']['files'];self.assertEqual(len(files),1);ident=files[0]['id']
  path=self.agent.resolve(ident,self.origin);self.assertTrue(path.is_file());self.assertTrue(path.is_relative_to(self.agent.state/'uploads'));self.assertEqual(self.agent.files[ident]['kind'],'upload')
  with Image.open(path) as image:self.assertEqual(image.convert('RGBA').getpixel((8,8)),(255,0,0,255))
  self.assertNotEqual(path.read_bytes(),original);self.assertEqual(source.read_bytes(),original);self.assertEqual({p.name:p.read_bytes() for p in self.results.iterdir()},existing)
  self.assertEqual(self.request('GET','/artifacts/'+ident,origin=self.other)[0],403)
  status,data=self.request('POST','/clipboard/image',{'id':ident});self.assertEqual(status,200,data);self.assertIs(data['copied'],True)
  self.assertFalse(list((self.agent.state/'tasks').iterdir()),'Private job requests and worker temp output must be reclaimed')
 def test_normal_render_keeps_user_output_behavior(self):
  artifact,source=self.png();original=source.read_bytes();result=self.job('image_edit',[artifact['id']],{'format':'png','layers':[]})
  self.assertEqual(result['status'],'complete',result);ident=result['result']['files'][0]['id'];path=self.agent.resolve(ident,self.origin)
  self.assertEqual(path.parent,self.results/'사진'/datetime.now().strftime('%Y')/datetime.now().strftime('%m'));self.assertEqual(self.agent.files[ident]['kind'],'artifact');self.assertEqual(source.read_bytes(),original);self.assertTrue(self.keep.exists())
 def test_clipboard_only_requires_real_boolean_and_image_edit_operation(self):
  artifact,_=self.png()
  for operation,value in [('image_edit',1),('image_edit','true'),('image_process',True)]:
   with self.subTest(operation=operation,value=value):
    result=self.job(operation,[artifact['id']],{'format':'png','clipboardOnly':value});self.assertEqual(result['status'],'failed',result);self.assertEqual(result['errorCode'],'invalidRequest')
  self.assertEqual(sorted(p.name for p in self.results.iterdir()),['existing-approved.txt']);self.assertFalse(list((self.agent.state/'tasks').iterdir()))



def symlink_or_skip(path,target,**kwargs):
 try:path.symlink_to(target,**kwargs)
 except OSError as error:
  if getattr(error,'winerror',None)==1314:raise unittest.SkipTest('Windows symlink privilege unavailable; fixture not executed')
  raise

if __name__=='__main__':unittest.main(verbosity=2)
