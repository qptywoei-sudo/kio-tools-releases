"""Real loopback HTTP, fixture inference, renderer and native clipboard boundary."""
import sys,io,time,threading,http.client,uuid,copy,unittest
from pathlib import Path
from unittest.mock import Mock
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'agent'),str(Path(__file__).resolve().parent)]
import ai_smart_scan_tests as smart_fixture
import ai_frame_api_tests as api_fixture
from PIL import Image

class ImageJobTests(unittest.TestCase):
 setUp=smart_fixture.SmartTests.setUp
 tearDown=smart_fixture.SmartTests.tearDown
 def test_image_mode_renders_bytes_caches_and_clears_on_logout(self):
  self.a.infer=Mock(return_value=({'regions':[],'originalLanguage':None},'fixture'))
  body={'scanId':'scan','task':'translate-image'}
  result=self.a.analyze(self.job,body)
  self.assertEqual(result['task'],'translate-image');self.assertEqual(result['imageId'],'job')
  self.assertEqual(Image.open(io.BytesIO(self.a.image(result['imageId']))).size,(80,30))
  self.assertEqual(self.a.analyze(self.job,body),result);self.assertEqual(self.a.infer.call_count,1)
  self.assertFalse(list(Path(self.temp.name).rglob('*.png')))
  self.a.clear()
  from common import AgentError
  with self.assertRaises(AgentError):self.a.image('job')
 def test_original_is_available_before_translation_and_remains_unchanged_after_rendering(self):
  from common import AgentError
  self.assertEqual(self.a.scan('scan')['png'],self.png)
  with self.assertRaisesRegex(AgentError,'aiSessionExpired'):self.a.image('job')
  def infer(*unused):
   self.assertEqual(self.a.scan('scan')['png'],self.png)
   self.assertFalse(self.a.images)
   return {'regions':[],'originalLanguage':None},'fixture'
  self.a.infer=Mock(side_effect=infer)
  result=self.a.analyze(self.job,{'scanId':'scan','task':'translate-image'})
  self.assertEqual(self.a.scan('scan')['png'],self.png)
  self.assertNotEqual(self.a.image(result['imageId']),self.png)
  self.assertFalse(list(Path(self.temp.name).rglob('*.png')))

class ImageApiTests(unittest.TestCase):
 setUp=api_fixture.BoundaryTests.setUp
 tearDown=api_fixture.BoundaryTests.tearDown
 start=api_fixture.BoundaryTests.start
 png=api_fixture.BoundaryTests.png
 binary=api_fixture.BoundaryTests.binary
 def test_image_route_requires_owned_desktop_and_returns_exact_png(self):
  session=self.start();self.agent.require_account();ident=str(uuid.uuid4());png=self.png()
  self.agent.ai.images[ident]={'png':png,'created':time.monotonic(),'generation':self.agent.ai.account.generation}
  def get(token=None):
   conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
   headers={'Origin':f'http://127.0.0.1:{self.port}'}
   if token:headers['X-Local-Agent-Token']=token
   conn.request('GET','/ai/images/'+ident,headers=headers);r=conn.getresponse();data=r.read();result=(r.status,r.getheader('Content-Type'),r.getheader('Cache-Control'),data);conn.close();return result
  self.assertEqual(get()[0],401)
  status,mime,cache,data=get(session['token']);self.assertEqual((status,mime,cache,data),(200,'image/png','no-store',png))
  self.agent.ai.clear();self.assertEqual(get(session['token'])[0],404)
 def test_original_and_translated_routes_return_distinct_exact_bytes_and_share_session_limits(self):
  session=self.start();self.agent.require_account();scan=str(uuid.uuid4());image=str(uuid.uuid4());original=self.png()
  output=io.BytesIO();Image.new('RGB',(12,9),'blue').save(output,format='PNG');translated=output.getvalue()
  a=self.agent.ai;generation=a.account.generation
  def prepare(created=None,owner_generation=None):
   common={'created':time.monotonic() if created is None else created,'generation':generation if owner_generation is None else owner_generation}
   a.scans[scan]={**common,'png':original,'results':{}};a.images[image]={**common,'png':translated}
  def get(path,authenticated=True):
   conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
   headers={'Origin':f'http://127.0.0.1:{self.port}'}
   if authenticated:headers['X-Local-Agent-Token']=session['token']
   conn.request('GET',path,headers=headers);r=conn.getresponse();data=r.read();result=(r.status,r.getheader('Content-Type'),r.getheader('Cache-Control'),data);conn.close();return result
  paths=('/ai/scans/'+scan+'/preview','/ai/images/'+image);copied=[];temporary=[]
  def copy_png(operation,args,timeout):
   self.assertEqual(operation,'clipboard.copy');path=Path(args['path']);temporary.append(path);copied.append(path.read_bytes());return {'copied':True}
  self.agent.bridge.call=copy_png
  prepare()
  for path,png in zip(paths,(original,translated)):
   self.assertEqual(get(path,False)[0],401)
   self.assertEqual(get(path),(200,'image/png','no-store',png))
   self.assertEqual(self.binary('/clipboard/png',get(path)[3],session['token'])[0],200)
   self.assertEqual(copied[-1],png);self.assertFalse(temporary[-1].exists())
  self.assertEqual(copied,[original,translated])
  for invalid in ('expired','other-account','cleared'):
   with self.subTest(invalid=invalid):
    prepare(created=time.monotonic()-901 if invalid=='expired' else None,owner_generation=generation-1 if invalid=='other-account' else None)
    if invalid=='cleared':a.clear()
    for path in paths:self.assertEqual(get(path)[0],404)
