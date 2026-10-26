"""Real disposable HTTP/SSE/native-signal ownership and heartbeat sync fixtures.
No real browser, native approval, OS settings, installed app or user file touched.
"""
import sys,unittest,time,queue,threading,json,http.client,socket,uuid,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import review_tests as reviewed
from common import atomic_json
from PIL import Image

class BrowserOwnerTests(unittest.TestCase):
 request=reviewed.ReviewAPITests.request
 def setUp(self):
  reviewed.ReviewAPITests.setUp(self);self.streams=[];self.admin=self.origin;self.extension='chrome-extension://abcdefghijklmnopabcdefghijklmnop'
  self.agent.origins.add(self.extension)
  self.tokens[self.extension]=self.agent.pair(self.extension,'Only approved mock browser extension')['token']
  self.assertEqual(self.request('POST','/browser/register',{'browser':'Chrome fixture'},origin=self.extension)[0],200)
 def tearDown(self):
  for connection,response,sock,thread in self.streams:
   try:sock.shutdown(socket.SHUT_RDWR)
   except OSError:pass
   thread.join(timeout=1);response.close();connection.close()
  reviewed.ReviewAPITests.tearDown(self)
 def stream(self,origin):
  connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=4);connection.request('GET','/events',headers={'Origin':origin,'X-Local-Agent-Token':self.tokens[origin]});sock=connection.sock;response=connection.getresponse();self.assertEqual(response.status,200);events=queue.Queue()
  def read():
   data=[]
   try:
    while True:
     line=response.readline()
     if not line:return
     text=line.decode().rstrip('\r\n')
     if not text:
      if data:events.put(json.loads('\n'.join(data)));data=[]
     elif text.startswith('data:'):data.append(text[5:].strip())
   except (OSError,ValueError,AttributeError):pass
  thread=threading.Thread(target=read,daemon=True);thread.start();self.streams.append((connection,response,sock,thread));self.event(events,lambda event:event.get('type')=='ready');return events
 def event(self,events,predicate,timeout=5):
  deadline=time.monotonic()+timeout
  while time.monotonic()<deadline:
   try:event=events.get(timeout=min(.2,max(.01,deadline-time.monotonic())))
   except queue.Empty:continue
   if predicate(event):return event
  self.fail('Expected SSE fixture event was not delivered')
 def upload_tile(self):
  stream=io.BytesIO();Image.new('RGB',(20,20),'red').save(stream,'PNG');body=stream.getvalue();connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
  connection.request('POST','/uploads',body,{'Origin':self.extension,'X-Local-Agent-Token':self.tokens[self.extension],'X-File-Name':'fixture-tile.png','Content-Type':'image/png'});response=connection.getresponse();self.assertEqual(response.status,201);value=json.loads(response.read());connection.close();return value['id']
 def finish_capture(self,command):
  tile=self.upload_tile();status,value=self.request('POST','/browser/result',{'id':command['id'],'tiles':[{'id':tile,'x':0,'y':0,'viewportWidth':20,'viewportHeight':20}],'width':20,'height':20,'dpr':1},origin=self.extension);self.assertEqual(status,200,value);return tile
 def test_global_signal_result_reaches_program_only_and_tiles_stay_extension_owned(self):
  admin=self.stream(self.admin);extension=self.stream(self.extension);signal=str(uuid.uuid4());atomic_json(self.agent.bridge.root/'signals'/f'{signal}.json',{'id':signal,'operation':'web.capture','createdAt':time.time()})
  command=self.event(extension,lambda event:event.get('type')=='browserCapture')['command'];tile=self.finish_capture(command)
  complete=self.event(admin,lambda event:event.get('type')=='job' and event['job']['id']==command['id'] and event['job']['status']=='complete',timeout=8)['job'];self.assertEqual(self.agent.job_owners[command['id']],self.admin)
  self.assertEqual(self.request('GET','/jobs/'+command['id'],origin=self.extension)[0],404)
  self.assertNotIn(tile,self.agent.files);self.assertEqual(self.request('GET','/artifacts/'+tile,origin=self.admin)[0],404)
  output=complete['result']['files'][0]['id'];status,data=self.request('GET','/artifacts/'+output,origin=self.admin);self.assertEqual(status,200);self.assertEqual(Image.open(io.BytesIO(data)).convert('RGB').getpixel((10,10)),(255,0,0));self.assertEqual(self.request('GET','/artifacts/'+output,origin=self.extension)[0],403)
 def test_direct_extension_capture_keeps_request_owner(self):
  admin=self.stream(self.admin);extension=self.stream(self.extension);status,value=self.request('POST','/browser/capture',{'format':'png'},origin=self.extension);self.assertEqual(status,202);ident=value['job']['id']
  command=self.event(extension,lambda event:event.get('type')=='browserCapture')['command'];self.finish_capture(command);self.event(extension,lambda event:event.get('type')=='job' and event['job']['id']==ident and event['job']['status']=='complete',timeout=8)
  self.assertEqual(self.agent.job_owners[ident],self.extension);self.assertEqual(self.request('GET','/jobs/'+ident,origin=self.admin)[0],404)
  seen=[]
  while not admin.empty():seen.append(admin.get_nowait())
  self.assertFalse(any(event.get('job',{}).get('id')==ident for event in seen),'Direct extension result leaked into ADMIN owner stream')
 def test_native_owner_priority_excludes_unpaired_and_extension(self):
  dummy=queue.Queue();fallback=self.extension;self.assertEqual(self.agent.native_owner(fallback),self.agent.desktop_origin)
  unpaired='http://127.0.0.1:5173';self.agent.origins.add(unpaired)
  with self.agent.lock:self.agent.listeners.extend([(unpaired,dummy),(self.extension,dummy)])
  self.assertEqual(self.agent.native_owner(fallback),self.agent.desktop_origin)
  with self.agent.lock:self.agent.listeners.append((self.other,dummy))
  self.assertEqual(self.agent.native_owner(fallback),self.agent.desktop_origin)
  with self.agent.lock:self.agent.listeners.append((self.admin,dummy))
  self.assertEqual(self.agent.native_owner(fallback),self.admin)
  # The live owned program UI receives global shortcuts before any other loopback client.
  with self.agent.lock:self.agent.listeners.append((self.origin,dummy))
  self.assertEqual(self.agent.native_owner(fallback),self.origin)
  self.agent.revoke(self.other);self.assertEqual(self.agent.native_owner(fallback),self.origin)
  with self.agent.lock:self.agent.listeners=[entry for entry in self.agent.listeners if entry[0]!=self.origin]
  self.assertEqual(self.agent.native_owner(fallback),self.agent.desktop_origin)
  with self.agent.lock:self.agent.listeners.clear()
 def test_native_heartbeat_changes_sync_continuously_and_invalid_values_do_not_persist(self):
  events=self.stream(self.admin);folder1=self.path/'chosen1';folder2=self.path/'chosen2';folder1.mkdir();folder2.mkdir();snapshot={'language':'vi','autoStart':True,'saveFolder':str(folder1),'shortcuts':{'areaCapture':'Control+Shift+A','fullCapture':'','webCapture':'','recordToggle':''}}
  # Native menus and WebView now share the device-local language preference.
  # Simulate that real write, rather than trusting a stale heartbeat language.
  self.agent.language_preference.select('vi')
  self.agent.bridge.call=lambda operation,body:{'applied':True,'settings':dict(snapshot)}
  self.agent.bridge.status=lambda:{'updatedAt':time.time(),'settings':dict(snapshot)}
  changed=self.event(events,lambda event:event.get('type')=='settings' and event['settings'].get('language')=='vi');self.assertTrue(changed['settings']['autoStart']);self.assertNotIn('saveFolder',changed['settings']);self.assertEqual(changed['settings']['saveFolderName'],'chosen1')
  self.agent.language_preference.select('ja')
  snapshot.update(language='ja',autoStart=False,saveFolder=str(folder2),shortcuts={'areaCapture':'Control+Shift+A','fullCapture':'Control+Shift+F8','webCapture':'','recordToggle':''})
  changed=self.event(events,lambda event:event.get('type')=='settings' and event['settings'].get('language')=='ja');self.assertFalse(changed['settings']['autoStart']);self.assertEqual(changed['settings']['shortcuts']['fullCapture'],'Control+Shift+F8');self.assertEqual(self.agent.settings['saveFolder'],str(folder2))
  before=json.loads(self.agent.settings_path.read_text());pairings=json.loads((self.agent.state/'pairings.json').read_text());snapshot.update(language='invalid-language',autoStart=1,shortcuts={'areaCapture':True},saveFolder=str(self.path/'missing'))
  time.sleep(1.1);self.assertEqual(json.loads(self.agent.settings_path.read_text()),before);self.assertEqual(json.loads((self.agent.state/'pairings.json').read_text()),pairings)

if __name__=='__main__':unittest.main(verbosity=2)
