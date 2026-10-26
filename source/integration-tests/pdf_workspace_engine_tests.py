"""Real disposable PDF fixtures for the standalone page workspace. No user files or credentials."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'engine')]
import engine
from PIL import Image

class PdfWorkspaceEngineTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name);self.out=self.path/'out';self.out.mkdir();self.source=self.path/'pages.pdf';self.second=self.path/'second.pdf';self.image=self.path/'image.png'
  with engine.fitz.open() as document:
   for number in range(1,26):
    page=document.new_page(width=200,height=120);page.insert_text((20,40),f'Source page {number}')
   document.save(self.source)
  with engine.fitz.open() as document:
   page=document.new_page(width=100,height=180);page.insert_text((10,40),'Second document');document.save(self.second)
  Image.new('RGBA',(160,80),'blue').save(self.image)
  self.originals={path:hashlib.sha256(path.read_bytes()).hexdigest() for path in (self.source,self.second,self.image)}
 def tearDown(self):
  for path,digest in self.originals.items():self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest,'Source file changed')
  self.temp.cleanup()
 def job(self,**options):return {'path':str(self.source),'output_dir':str(self.out),**options}
 def test_merge_preserves_both_documents_and_page_sequence(self):
  output=engine.pdf_merge(self.job(inputs=[str(self.source),str(self.second)]))['files'][0]
  with engine.open_pdf(output) as document:
   self.assertEqual(document.page_count,26);self.assertIn('Source page 1',document[0].get_text());self.assertIn('Second document',document[25].get_text())
 def test_extract_keeps_current_workspace_selection_order(self):
  output=engine.pdf_extract(self.job(pages='24,13,2'))['files'][0]
  with engine.open_pdf(output) as document:
   self.assertEqual(document.page_count,3)
   for index,number in enumerate([24,13,2]):self.assertIn(f'Source page {number}',document[index].get_text())
 def test_later_thumbnail_batch_has_exact_page_metadata_and_images(self):
  result=engine.pdf_render(self.job(pages='13,24,25',dpi=72,format='png'))
  self.assertEqual([page['index'] for page in result['data']['pages']],[13,24,25]);self.assertEqual(len(result['files']),3)
  for path in result['files']:
   with Image.open(path) as image:self.assertEqual(image.size,(200,120));self.assertEqual(image.format,'PNG')
 def test_page_edits_preserve_text_and_apply_rotation_to_reordered_sources(self):
  output=engine.pdf_manage(self.job(page_order=[25,13,1],rotations={'25':90,'1':270}))['files'][0]
  with engine.open_pdf(output) as document:
   self.assertEqual(document.page_count,3);self.assertEqual([page.rotation for page in document],[90,0,270])
   for index,number in enumerate([25,13,1]):self.assertIn(f'Source page {number}',document[index].get_text())
 def test_images_to_pdf_supports_landscape_a4_and_native_image_size(self):
  output=engine.images_pdf(self.job(inputs=[str(self.image)],page_size='a4',orientation='landscape',margin_mm=10))['files'][0]
  with engine.open_pdf(output) as document:self.assertEqual(document.page_count,1);self.assertGreater(document[0].rect.width,document[0].rect.height);self.assertEqual(len(document[0].get_images()),1)
  output=engine.images_pdf(self.job(inputs=[str(self.image)],page_size='image',margin_mm=0))['files'][0]
  with engine.open_pdf(output) as document:self.assertAlmostEqual(document[0].rect.width,120);self.assertAlmostEqual(document[0].rect.height,60)

if __name__=='__main__':unittest.main(verbosity=2)
