"""Real disposable HTTP/SSE broker tests; native approval is a labelled fixture.
No installed browser, production state, OS permission or user file is touched.
"""
import http.client,io,json,queue,socket,sys,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import review_tests as reviewed
from PIL import Image

class BrowserBrokerTests(unittest.TestCase):
 request=reviewed.ReviewAPITests.request
 def setUp(self):
  reviewed.ReviewAPITests.setUp(self)
  self.admin=self.origin # The owned native UI, not a generic loopback client.
  self.extension='chrome-extension://abcdefghijklmnopabcdefghijklmnop'
  self.other_extension='chrome-extension://ponmlkjihgfedcbaponmlkjihgfedcba'
  self.streams=[]
  for origin in (self.extension,self.other_extension):
   self.agent.origins.add(origin)
   self.tokens[origin]=self.agent.pair(origin,'Only disposable broker fixture')['token']
  self.assertEqual(self.request('POST','/browser/register',{'browser':'Chrome fixture'},origin=self.extension)[0],200)
 def tearDown(self):
  self.agent.stopping.set()
  with self.agent.lock:
   for _,events in self.agent.listeners:
    try:events.put_nowait({'type':'fixtureStop'})
    except queue.Full:pass
  for connection,response,sock,thread in self.streams:
   try:sock.shutdown(socket.SHUT_RDWR)
   except OSError:pass
   thread.join(timeout=1);response.close();connection.close()
  reviewed.ReviewAPITests.tearDown(self)
 def wait(self,predicate,timeout=4):
  deadline=time.monotonic()+timeout
  while time.monotonic()<deadline:
   value=predicate()
   if value:return value
   time.sleep(.01)
  self.fail('Disposable broker fixture did not complete')
 def event(self,events,predicate,timeout=4):
  deadline=time.monotonic()+timeout
  while time.monotonic()<deadline:
   try:event=events.get(timeout=min(.2,max(.01,deadline-time.monotonic())))
   except queue.Empty:continue
   if predicate(event):return event
  self.fail('Expected owner-scoped event was not delivered')
 def stream(self,origin):
  connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=4)
  connection.request('GET','/events',headers={'Origin':origin,'X-Local-Agent-Token':self.tokens[origin]})
  sock=connection.sock;response=connection.getresponse();self.assertEqual(response.status,200);sock.settimeout(None)
  events=queue.Queue();events.observed=[]
  def read():
   data=[]
   try:
    while True:
     line=response.readline()
     if not line:return
     text=line.decode().rstrip('\r\n')
     if not text:
      if data:
       event=json.loads('\n'.join(data));events.observed.append(event);events.put(event);data=[]
     elif text.startswith('data:'):data.append(text[5:].strip())
   except (OSError,ValueError,AttributeError):pass
  thread=threading.Thread(target=read,daemon=True);thread.start()
  self.streams.append((connection,response,sock,thread))
  ready=self.event(events,lambda event:event.get('type')=='ready')
  self.assertNotIn('token',ready)
  return events
 def tile(self,name='tile-1.png'):
  stream=io.BytesIO();Image.new('RGB',(20,20),'red').save(stream,'PNG')
  connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=4)
  connection.request('POST','/uploads',stream.getvalue(),{'Origin':self.extension,'X-Local-Agent-Token':self.tokens[self.extension],'X-File-Name':name,'Content-Type':'image/png'})
  response=connection.getresponse();self.assertEqual(response.status,201);value=json.loads(response.read());connection.close()
  return value['id'],Path(self.agent.files[value['id']]['path'])
 def result(self,ident,tile):
  return {'id':ident,'tiles':[{'id':tile,'x':0,'y':0,'viewportWidth':20,'viewportHeight':20}],'width':20,'height':20,'dpr':1}
 def fake_receiver(self):
  # Simulate a worker that was authenticated but died before consuming its queue.
  item=(self.extension,queue.Queue())
  with self.agent.lock:self.agent.listeners.append(item)
  return item
 def close_stream(self,index):
  connection,response,sock,thread=self.streams[index]
  with self.agent.lock:receiver=next(events for owner,events in self.agent.listeners if owner==self.extension)
  sock.shutdown(socket.SHUT_RDWR)
  # Wake the server's normal SSE write path so TCP closure is noticed promptly.
  thread.join(timeout=1);response.close();connection.close()
  for _ in range(20):
   with self.agent.lock:present=any(events is receiver for _,events in self.agent.listeners)
   if not present:break
   receiver.put_nowait({'type':'fixtureWake'});time.sleep(.01)
 def start(self,owner=None):
  status,value=self.request('POST','/browser/capture',{'format':'png','split':False},origin=owner or self.admin)
  self.assertEqual(status,202,value);ident=value['job']['id']
  self.wait(lambda:ident in self.agent.web_waiters)
  return ident
 def complete(self,ident):
  tile,path=self.tile()
  self.assertEqual(self.request('POST','/browser/result',self.result(ident,tile),origin=self.extension)[0],200)
  job=self.wait(lambda:self.agent.jobs[ident] if self.agent.jobs[ident]['status'] in ('complete','failed','cancelled') else None,timeout=8)
  self.assertEqual(job['status'],'complete',job)
  self.assertNotIn(tile,self.agent.files);self.assertFalse(path.exists())
  return job
 def test_heartbeat_alone_does_not_report_ready_or_queue_a_capture(self):
  self.assertFalse(self.agent.browser_ready())
  self.assertFalse(self.request('GET','/health',origin=self.admin)[1]['browserConnected'])
  self.assertFalse(self.request('GET','/browser',origin=self.admin)[1]['connected'])
  self.assertEqual(self.request('POST','/browser/heartbeat',{},origin=self.extension)[0],200)
  status,value=self.request('POST','/browser/capture',{'format':'png'},origin=self.admin)
  self.assertEqual((status,value),(409,{'errorCode':'browserRequired'}))
  self.assertEqual(self.agent.jobs,{})
 def test_capture_immediately_after_stream_ready_is_delivered(self):
  receiver=self.stream(self.extension)
  self.assertTrue(self.agent.browser_ready())
  self.assertTrue(self.request('GET','/health',origin=self.admin)[1]['browserConnected'])
  ident=self.start(self.extension)
  event=self.event(receiver,lambda event:event.get('type')=='browserCapture')
  self.assertEqual(event['command'],{'id':ident,'options':{'format':'png','split':False}})
  job=self.complete(ident)
  self.assertEqual(self.agent.job_owners[ident],self.extension)
  self.assertEqual(self.request('GET','/artifacts/'+job['result']['files'][0]['id'],origin=self.admin)[0],403)
 def test_disconnected_worker_command_replays_only_to_extension_owner(self):
  admin=self.stream(self.admin);other=self.stream(self.other_extension)
  old=self.fake_receiver();ident=self.start()
  self.assertTrue(any(event.get('type')=='browserCapture' for event in list(old[1].queue)))
  with self.agent.lock:self.agent.listeners.remove(old)
  self.assertFalse(self.agent.browser_ready())
  receiver=self.stream(self.extension)
  replay=self.event(receiver,lambda event:event.get('type')=='browserCapture')
  self.assertEqual(replay['command']['id'],ident)
  self.assertEqual(replay['command']['options'],{'format':'png','split':False})
  job=self.complete(ident)
  self.event(admin,lambda event:event.get('type')=='job' and event['job']['id']==ident and event['job']['status']=='complete')
  self.assertEqual(self.request('GET','/jobs/'+ident,origin=self.extension)[0],404)
  output=job['result']['files'][0]['id']
  status,data=self.request('GET','/artifacts/'+output,origin=self.admin)
  self.assertEqual(status,200);self.assertEqual(Image.open(io.BytesIO(data)).convert('RGB').getpixel((10,10)),(255,0,0))
  for events in (admin,other):
   self.assertFalse(any(event.get('type')=='browserCapture' for event in events.observed))
  self.assertEqual(self.request('GET','/artifacts/'+output,origin=self.extension)[0],403)
 def test_result_consumed_for_stitching_cannot_complete_again_or_replay(self):
  receiver=self.stream(self.extension);started=threading.Event();release=threading.Event()
  output=self.path/'saved.png';Image.new('RGB',(20,20),'blue').save(output)
  original=self.path/'original.txt';original.write_bytes(b'USER ORIGINAL MUST SURVIVE')
  original_id=self.agent.register(original,self.admin,'native')['id']
  def stitch(*args):started.set();release.wait(4);return {'success':True,'files':[str(output)]}
  with patch.object(self.agent,'engine_job',side_effect=stitch):
   ident=self.start();self.event(receiver,lambda event:event.get('type')=='browserCapture')
   tile,path=self.tile()
   try:
    self.assertEqual(self.request('POST','/browser/result',self.result(ident,tile),origin=self.extension)[0],200)
    self.assertTrue(started.wait(3));self.assertTrue(self.agent.web_waiters[ident]['queue'].empty())
    duplicate=self.result(ident,original_id)
    self.assertEqual(self.request('POST','/browser/result',duplicate,origin=self.extension)[0],409)
    newer=self.stream(self.extension)
    marker=self.event(newer,lambda event:True)
    self.assertEqual(marker['type'],'browser');self.assertTrue(marker['connected'])
    self.assertFalse(any(event.get('type')=='browserCapture' for event in newer.observed))
   finally:release.set()
   self.wait(lambda:self.agent.jobs[ident]['status']=='complete')
  self.assertNotIn(tile,self.agent.files);self.assertFalse(path.exists())
  self.assertEqual(original.read_bytes(),b'USER ORIGINAL MUST SURVIVE');self.assertIn(original_id,self.agent.files)
  self.assertTrue(output.exists())
 def test_cancelled_command_does_not_replay_and_tracks_upload_cleanup(self):
  old=self.fake_receiver();ident=self.start();tile,path=self.tile()
  self.agent.cancel(ident)
  with self.agent.lock:self.agent.listeners.remove(old)
  receiver=self.stream(self.extension)
  marker=self.event(receiver,lambda event:True)
  self.assertEqual(marker['type'],'browser');self.assertTrue(marker['connected'])
  self.assertFalse(any(event.get('type')=='browserCapture' for event in receiver.observed))
  self.wait(lambda:ident not in self.agent.web_waiters)
  self.assertNotIn(tile,self.agent.files);self.assertFalse(path.exists())
 def test_revoked_extension_is_not_ready_even_with_existing_stream(self):
  self.stream(self.extension);self.assertTrue(self.agent.browser_ready())
  self.agent.revoke(self.extension);self.assertFalse(self.agent.browser_ready())
  self.assertEqual(self.request('POST','/browser/capture',{'format':'png'},origin=self.admin)[0],409)
 def test_admin_receives_ready_then_last_receiver_disconnect_status(self):
  admin=self.stream(self.admin)
  self.assertFalse(self.request('GET','/browser',origin=self.admin)[1]['connected'])
  self.stream(self.extension)
  self.event(admin,lambda event:event.get('type')=='browser' and event.get('connected') is True)
  self.stream(self.extension)
  self.event(admin,lambda event:event.get('type')=='browser' and event.get('connected') is True)
  self.close_stream(1)
  self.wait(lambda:sum(owner==self.extension for owner,_ in self.agent.listeners)==1)
  still_ready=self.event(admin,lambda event:event.get('type')=='browser')
  self.assertTrue(still_ready['connected'])
  self.close_stream(2)
  self.wait(lambda:sum(owner==self.extension for owner,_ in self.agent.listeners)==0)
  closed=self.event(admin,lambda event:event.get('type')=='browser')
  self.assertFalse(closed['connected'])
  self.assertFalse(self.request('GET','/browser',origin=self.admin)[1]['connected'])
 def test_admin_receives_immediate_revoke_status_without_waiting_for_heartbeat(self):
  admin=self.stream(self.admin);self.stream(self.extension)
  self.event(admin,lambda event:event.get('type')=='browser' and event.get('connected') is True)
  start=time.monotonic()
  self.assertEqual(self.request('DELETE','/pair',origin=self.extension)[0],200)
  revoked=self.event(admin,lambda event:event.get('type')=='browser' and event.get('connected') is False,timeout=2)
  self.assertLess(time.monotonic()-start,2)
  self.assertFalse(revoked['connected']);self.assertFalse(self.agent.browser_ready())
 def test_expired_heartbeat_resume_notifies_admin_with_live_receiver(self):
  admin=self.stream(self.admin);self.stream(self.extension)
  self.event(admin,lambda event:event.get('type')=='browser' and event.get('connected') is True)
  with self.agent.lock:self.agent.browser['lastSeen']=time.time()-46
  self.assertFalse(self.request('GET','/browser',origin=self.admin)[1]['connected'])
  self.assertEqual(self.request('POST','/browser/heartbeat',{},origin=self.extension)[0],200)
  resumed=self.event(admin,lambda event:event.get('type')=='browser' and event.get('connected') is True)
  self.assertTrue(resumed['connected']);self.assertTrue(self.agent.browser_ready())

if __name__=='__main__':unittest.main(verbosity=2)
