"""Disposable native-recorder fixture plus real HTTP, FFmpeg and animated GIF output.
No screen, microphone, installed app, user recording or OS permission is used.
"""
import sys,time,json,unittest,subprocess,hashlib,http.client,uuid
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import review_tests as reviewed
from common import AgentError
from PIL import Image
import imageio_ffmpeg

class RecordingTests(unittest.TestCase):
 request=reviewed.ReviewAPITests.request
 def setUp(self):
  reviewed.ReviewAPITests.setUp(self)
  self.source=self.path/'Recording-20261011-210000-A1B2C3D4.mp4'
  subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-filter_complex','testsrc=size=96x64:rate=8','-t','1.5','-c:v','mpeg4','-pix_fmt','yuv420p',str(self.source)],check=True,timeout=15)
  self.digest=hashlib.sha256(self.source.read_bytes()).hexdigest();self.calls=[];self.recording=False;self.paused=False
  self.agent.bridge.status=lambda:{'updatedAt':time.time(),'recording':self.recording,'paused':self.paused,'settings':{}}
  def native(operation,args=None,timeout=90):
   self.calls.append(operation)
   if operation=='record.start' and not self.recording:self.recording=True
   elif operation=='record.pause' and self.recording and not self.paused:self.paused=True
   elif operation=='record.resume' and self.recording and self.paused:self.paused=False
   elif operation=='record.stop' and self.recording:self.recording=False;self.paused=False
   else:raise AgentError('conflict')
   return {'recording':self.recording,'paused':self.paused,**({'paths':[str(self.source)]} if operation=='record.stop' else {})}
  self.agent.bridge.call=native
 def tearDown(self):reviewed.ReviewAPITests.tearDown(self)
 def job(self,operation,inputs=None,options=None,origin=None):
  status,response=self.request('POST','/jobs',{'operation':operation,'inputs':inputs or [],'options':options or {}},origin)
  self.assertEqual(status,202,response);ident=response['job']['id'];deadline=time.monotonic()+20
  while time.monotonic()<deadline:
   status,response=self.request('GET','/jobs/'+ident,origin=origin);self.assertEqual(status,200,response)
   if response['job']['status'] in ('complete','failed','cancelled'):return response['job']
   time.sleep(.025)
  self.fail('Fixture job did not complete')
 def check_gif(self,job):
  self.assertEqual(job['status'],'complete',job)
  file=job['result']['files'][0];self.assertEqual(file['mime'],'image/gif')
  with Image.open(self.agent.resolve(file['id'],self.origin)) as gif:
   self.assertGreater(gif.n_frames,1);self.assertEqual(gif.info['loop'],0)
   first=gif.convert('RGB').tobytes();gif.seek(gif.n_frames-1);self.assertNotEqual(first,gif.convert('RGB').tobytes())
  self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(),self.digest)
 def test_direct_recording_lifecycle_then_gif_does_not_stop_twice(self):
  for operation in ('record_start','record_pause','record_resume','record_stop'):
   job=self.job(operation);self.assertEqual(job['status'],'complete',job)
  recording=job['result']['files'][0]
  self.assertEqual(self.agent.files[recording['id']]['kind'],'recording')
  self.source=self.agent.resolve(recording['id'],self.origin)
  status,latest=self.request('GET','/recordings/latest');self.assertEqual(status,200);self.assertEqual(latest['file'],recording)
  self.check_gif(self.job('record_gif',options={'ranges':[{'start':0,'end':1.5}],'width':96,'fps':8}))
  self.assertEqual(self.calls,['record.start','record.pause','record.resume','record.stop'])
 def test_selected_video_converts_without_native_recorder(self):
  file=self.agent.register(self.source,self.origin,'native')
  self.check_gif(self.job('record_gif',[file['id']],{'ranges':[{'start':.25,'end':1.25}],'width':96,'fps':8}))
  self.assertEqual(self.calls,[])
 def test_native_stop_signal_publishes_recording_and_never_restarts(self):
  self.recording=True
  directory=self.agent.bridge.root/'signals';directory.mkdir(exist_ok=True)
  def signal():
   ident=str(uuid.uuid4());(directory/(ident+'.json')).write_text(json.dumps({'id':ident,'operation':'record.stop','createdAt':time.time()}))
  signal();deadline=time.monotonic()+10
  while time.monotonic()<deadline:
   finished=[job for job in self.agent.jobs.values() if job['operation']=='record_stop' and job['status'] in ('complete','failed')]
   if finished:break
   time.sleep(.05)
  self.assertTrue(finished,'Native stop must create an output job')
  self.assertEqual(finished[0]['status'],'complete',finished[0])
  self.assertTrue(finished[0]['result']['files'])
  signal();time.sleep(.7)
  self.assertEqual(self.calls,['record.stop'])
 def test_legacy_recording_is_found_after_registry_reload_and_is_owner_scoped(self):
  file=self.agent.register(self.source,self.origin)
  self.agent.files=json.loads((self.agent.state/'files.json').read_text())
  self.assertEqual(self.request('GET','/recordings/latest')[1]['file'],file)
  self.assertIsNone(self.request('GET','/recordings/latest',origin=self.other)[1]['file'])
  self.assertEqual(self.request('POST','/jobs',{'operation':'record_gif','inputs':[file['id']]},self.other)[0],403)
  health=self.request('GET','/health')[1];self.assertNotIn(file['name'],json.dumps(health));self.assertNotIn(file['id'],json.dumps(health))
  self.source.unlink();self.assertIsNone(self.request('GET','/recordings/latest')[1]['file'])
 def test_missing_recording_is_clear_error_without_native_stop(self):
  job=self.job('record_gif');self.assertEqual(job['errorCode'],'inputMissing');self.assertEqual(self.calls,[])
 def test_failed_conversion_preserves_saved_recording_for_retry(self):
  file=self.agent.register(self.source,self.origin,'recording')
  with patch.object(self.agent,'engine_job',side_effect=AgentError('processingFailed')):
   self.assertEqual(self.job('record_gif')['status'],'failed')
  self.assertEqual(self.request('GET','/recordings/latest')[1]['file'],file)
  self.check_gif(self.job('record_gif',options={'width':96,'fps':8}))
  self.assertEqual(self.calls,[])
 def test_latest_recording_requires_auth_and_rejects_multiple_inputs(self):
  file=self.agent.register(self.source,self.origin,'recording')
  connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
  connection.request('GET','/recordings/latest',headers={'Origin':self.origin});response=connection.getresponse();self.assertEqual(response.status,401);response.read();connection.close()
  self.assertEqual(self.request('POST','/jobs',{'operation':'record_gif','inputs':[file['id'],file['id']]})[0],400)

if __name__=='__main__':unittest.main(verbosity=2)
