"""Real PDF preview exports against disposable local state; native bridge is mocked."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from capture_copy_tests import CaptureCopyTests
import engine

class PreviewCacheTests(unittest.TestCase):
 request=CaptureCopyTests.request
 setUp=CaptureCopyTests.setUp
 tearDown=CaptureCopyTests.tearDown
 job=CaptureCopyTests.job
 def pdf(self):
  path=self.path/'original.pdf'
  with engine.fitz.open() as pdf:
   page=pdf.new_page(width=160,height=120);page.insert_text((12,24),'ORIGINAL');pdf.save(path)
  return self.agent.register(path,self.origin,'native'),path
 def test_preview_does_not_write_save_folder_and_is_owned(self):
  artifact,source=self.pdf();original=source.read_bytes();before={p.name:p.read_bytes() for p in self.results.iterdir()}
  job=self.job('pdf_render',[artifact['id']],{'pages':'1','dpi':72,'previewOnly':True})
  self.assertEqual(job['status'],'complete',job)
  result=job['result']['files'][0];path=self.agent.resolve(result['id'],self.origin)
  self.assertTrue(path.is_relative_to(self.agent.state/'uploads'))
  self.assertEqual(self.agent.files[result['id']]['kind'],'upload')
  self.assertEqual(self.request('GET','/artifacts/'+result['id'],origin=self.other)[0],403)
  self.assertEqual({p.name:p.read_bytes() for p in self.results.iterdir()},before)
  self.assertEqual(source.read_bytes(),original)
  self.assertFalse(list((self.agent.state/'tasks').iterdir()))
 def test_explicit_export_still_saves_to_configured_folder(self):
  artifact,_=self.pdf();job=self.job('pdf_render',[artifact['id']],{'pages':'1','dpi':72,'previewOnly':False})
  self.assertEqual(job['status'],'complete',job)
  result=job['result']['files'][0];self.assertTrue(self.agent.resolve(result['id'],self.origin).is_relative_to(self.results))
  self.assertEqual(self.agent.files[result['id']]['kind'],'artifact')
 def test_invalid_preview_flag_rejected_before_any_job(self):
  artifact,_=self.pdf()
  for operation,flag in [('pdf_render',1),('pdf_render','true'),('image_edit',True),('capture',True)]:
   status,data=self.request('POST','/jobs',{'operation':operation,'inputs':[artifact['id']],'options':{'previewOnly':flag}})
   self.assertEqual(status,400,data);self.assertEqual(data['errorCode'],'invalidRequest')
  self.assertFalse(self.agent.jobs)

if __name__=='__main__':
 unittest.main(defaultTest='PreviewCacheTests',verbosity=2)

