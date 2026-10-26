"""Real isolated video jobs; preview cache, explicit export and request guards."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from capture_copy_tests import CaptureCopyTests

class VideoEditorAPITests(unittest.TestCase):
 request=CaptureCopyTests.request
 setUp=CaptureCopyTests.setUp
 tearDown=CaptureCopyTests.tearDown
 job=CaptureCopyTests.job
 png=CaptureCopyTests.png
 def options(self,**extra):return {'width':96,'height':64,'fps':10,'clips':[{'source':0,'kind':'image','start':0,'end':.4}],**extra}
 def test_preview_does_not_publish_to_local_or_drive_and_is_owned(self):
  artifact,path=self.png();before={p.name:p.read_bytes() for p in self.results.iterdir()};self.agent.settings['saveMode']='drive'
  job=self.job('video_edit',[artifact['id']],self.options(previewOnly=True));self.assertEqual(job['status'],'complete',job);self.assertTrue(job['previewOnly'])
  result=job['result']['files'][0];self.assertEqual(result['mime'],'video/mp4');self.assertTrue(self.agent.resolve(result['id'],self.origin).is_relative_to(self.agent.state/'uploads'));self.assertEqual(self.agent.files[result['id']]['kind'],'upload')
  self.assertEqual({p.name:p.read_bytes() for p in self.results.iterdir()},before);self.assertFalse(list((self.agent.state/'tasks').iterdir()));self.assertEqual(self.request('GET','/artifacts/'+result['id'],origin=self.other)[0],403)
 def test_explicit_video_export_uses_configured_storage(self):
  artifact,path=self.png();job=self.job('video_edit',[artifact['id']],self.options(previewOnly=False));self.assertEqual(job['status'],'complete',job)
  result=job['result']['files'][0];self.assertTrue(self.agent.resolve(result['id'],self.origin).is_relative_to(self.results));self.assertEqual(self.agent.files[result['id']]['kind'],'artifact')
 def test_m4a_preview_from_existing_project_includes_requested_duration(self):
  artifact,path=self.png();job=self.job('video_edit',[artifact['id']],self.options(format='m4a',duration=.8,previewOnly=True));self.assertEqual(job['status'],'complete',job)
  result=job['result']['files'][0];self.assertEqual(Path(result['name']).suffix,'.m4a');self.assertTrue(job['result']['data']['audioOnly']);self.assertEqual(job['result']['data']['duration'],.8)
 def test_bad_timeline_or_preview_flag_rejected_without_worker(self):
  artifact,path=self.png()
  for options in [self.options(previewOnly='true'),self.options(clips=[{'source':'0','kind':'image','start':0,'end':1}]),self.options(clips=[{'source':0,'kind':'image','start':0,'end':1801}]),self.options(width=1920,height=1920),self.options(audio=[{'source':0,'start':0,'end':1,'at':0,'path':'secret'}])]:
   status,response=self.request('POST','/jobs',{'operation':'video_edit','inputs':[artifact['id']],'options':options});self.assertEqual(status,400,response)
  self.assertFalse(self.agent.jobs)
if __name__=='__main__':unittest.main(defaultTest='VideoEditorAPITests',verbosity=2)
