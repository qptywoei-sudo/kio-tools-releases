"""Real disposable HTTP boundary; native clipboard and inference are fixtures."""
import sys,time,threading,json,http.client,io,unittest,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import desktop_session_tests as fixture
from common import AgentError
from PIL import Image
class BoundaryTests(unittest.TestCase):
 setUp=fixture.DesktopSessionTests.setUp
 tearDown=fixture.DesktopSessionTests.tearDown
 start=fixture.DesktopSessionTests.start
 request=fixture.DesktopSessionTests.request
 def binary(self,path,data,token=None,content='image/png'):
  c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5);headers={'Origin':f'http://127.0.0.1:{self.port}','Content-Type':content}
  if token:headers['X-Local-Agent-Token']=token
  c.request('POST',path,data,headers);r=c.getresponse();answer=(r.status,json.loads(r.read()));c.close();return answer
 def png(self):
  b=io.BytesIO();Image.new('RGB',(12,9),'yellow').save(b,format='PNG');return b.getvalue()
 def test_frame_requires_desktop_and_is_accepted_once_in_memory(self):
  s=self.start();self.agent.require_account();ident=str(uuid.uuid4());job={'id':ident,'kind':'capture','status':'running','stage':'capture','created':time.monotonic(),'cancel':threading.Event(),'generation':self.agent.ai.account.generation};self.agent.ai.jobs[ident]=job
  p=self.png();self.assertEqual(self.binary('/ai/frame/'+ident,p)[0],401)
  self.assertEqual(self.binary('/ai/frame/'+ident,p,s['token'])[0],200);self.assertEqual(job['png'],p)
  self.assertEqual(self.binary('/ai/frame/'+ident,p,s['token'])[0],409);self.assertFalse(list(self.state.rglob('*.png')))
 def test_frame_for_previous_account_generation_is_rejected(self):
  s=self.start();self.agent.require_account();ident=str(uuid.uuid4())
  job={'id':ident,'kind':'capture','status':'running','stage':'capture','created':time.monotonic(),'cancel':threading.Event(),'generation':self.agent.ai.account.generation-1};self.agent.ai.jobs[ident]=job
  status,body=self.binary('/ai/frame/'+ident,self.png(),s['token'])
  self.assertEqual(status,400);self.assertEqual(body['errorCode'],'aiAccountChanged');self.assertNotIn('png',job)
 def test_frame_rejects_bad_content_and_unknown_job(self):
  s=self.start();path='/ai/frame/'+str(uuid.uuid4())
  for data,content in [(b'not PNG'*4,'image/png'),(b'','text/plain')]:self.assertEqual(self.binary(path,data,s['token'],content)[0],400)
  self.assertEqual(self.binary(path,self.png(),s['token'])[0],409)
 def test_clipboard_temp_is_deleted_on_success_and_native_failure(self):
  s=self.start();seen=[]
  def copy(op,args,timeout):
   p=Path(args['path']);seen.append(p);self.assertEqual(p.read_bytes(),self.png());return {'copied':True}
  self.agent.bridge.call=copy;self.assertEqual(self.binary('/clipboard/png',self.png(),s['token'])[0],200);self.assertFalse(seen[-1].exists())
  def fail(op,args,timeout):seen.append(Path(args['path']));raise AgentError('clipboardFailed')
  self.agent.bridge.call=fail;self.assertEqual(self.binary('/clipboard/png',self.png(),s['token'])[0],400);self.assertFalse(seen[-1].exists())
 def test_clipboard_rejects_unauthed_and_oversized_dimensions(self):
  s=self.start();self.assertEqual(self.binary('/clipboard/png',self.png())[0],401)
  p=bytearray(self.png());p[16:20]=(20001).to_bytes(4,'big');self.assertEqual(self.binary('/clipboard/png',bytes(p),s['token'])[0],400)
 def test_metrics_rejects_content_fields_nonfinite_values_and_unauthed_reads(self):
  s=self.start();a=self.agent.ai;a.jobs['test']={'id':'test','kind':'capture','status':'running','created':time.monotonic(),'timings':{}}
  self.assertEqual(self.request('GET','/ai/performance')[0],401)
  for body in [{'id':'test','text':'private'},{'id':'test','popupShownAt':float('nan')},{'id':'test','popupShownAt':float('inf')}]:self.assertEqual(self.request('POST','/ai/metrics',body,token=s['token'])[0],400)
  self.assertEqual(self.request('POST','/ai/metrics',{'id':'test','popupShownAt':time.time()*1000},token=s['token'])[0],200)
  a.jobs.clear()
 def test_extension_identifier_does_not_bypass_origin_or_authentication(self):
  self.start();extension='chrome-extension://'+'a'*32;self.agent.origins.add(extension)
  def get(path,origin=None,identifier=extension):
   c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5);h={'X-KIO-Extension-Origin':identifier}
   if origin is not None:h['Origin']=origin
   c.request('GET',path,headers=h);r=c.getresponse();r.read();status=r.status;c.close();return status
  self.assertEqual(get('/health'),200)
  self.assertEqual(get('/settings'),401)
  self.assertEqual(get('/health','https://untrusted.example'),403)
  self.assertEqual(get('/health',identifier='chrome-extension://'+'b'*32),403)
  self.assertEqual(get('/health',identifier='http://127.0.0.1:'+str(self.port)),403)
if __name__=='__main__':unittest.main()
