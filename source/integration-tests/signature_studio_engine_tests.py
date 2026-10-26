"""Verify the exact full-page overlay export used by SignatureStudio with real files."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import engine
import engine_extra
from PIL import Image,ImageDraw

class SignatureStudioEngineTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.out=self.root/'out';self.out.mkdir()
  self.source=self.root/'document.pdf'
  with engine.fitz.open() as doc:
   for rotation in (0,90,180,270):
    page=doc.new_page(width=200,height=300);page.insert_text((20,50),'ORIGINAL TEXT');page.set_rotation(rotation)
   doc.save(self.source)
  self.digest=hashlib.sha256(self.source.read_bytes()).hexdigest()
 def tearDown(self):
  self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(),self.digest);self.temp.cleanup()
 def overlay(self,w,h):
  path=self.root/f'mark-{w}-{h}.png';image=Image.new('RGBA',(w,h),(0,0,0,0));ImageDraw.Draw(image).rectangle((10,10,39,29),fill=(220,20,20,255));image.save(path);return path
 def apply(self,path,overlay,**options):
  return Path(engine_extra.signature_apply(dict(path=str(path),inputs=[str(path),str(overlay)],signatureInput=1,overlay=True,format='png',output_dir=str(self.out),**options))['files'][0])
 def test_selected_pdf_page_and_all_rotations_match_preview_coordinates(self):
  for page_number in range(1,5):
   with engine.open_pdf(self.source) as doc:w,h=map(int,(doc[page_number-1].rect.width,doc[page_number-1].rect.height))
   output=self.apply(self.source,self.overlay(w,h),pages=str(page_number))
   with engine.open_pdf(output) as doc:
    self.assertEqual(doc.page_count,4)
    for index,page in enumerate(doc):
     self.assertIn('ORIGINAL TEXT',page.get_text());pix=page.get_pixmap();image=Image.frombytes('RGB',(pix.width,pix.height),pix.samples);r,g,b=image.getpixel((20,20))
     if index==page_number-1:self.assertGreater(r,180);self.assertLess(g,40)
     else:self.assertGreater(g,240)
 def test_all_pages_preserves_searchable_text_and_adds_marks(self):
  output=self.apply(self.source,self.overlay(200,300),allPages=True)
  with engine.open_pdf(output) as doc:
   self.assertTrue(all(len(page.get_images())>=1 and 'ORIGINAL TEXT' in page.get_text() for page in doc))
 def test_image_output_preserves_size_and_composites_only_nontransparent_pixels(self):
  source=self.root/'photo.png';Image.new('RGBA',(400,600),(30,120,200,255)).save(source);before=source.read_bytes()
  output=self.apply(source,self.overlay(200,300),pages='1');self.assertEqual(source.read_bytes(),before)
  with Image.open(output) as image:self.assertEqual(image.size,(400,600));self.assertEqual(image.getpixel((300,400))[:3],(30,120,200));self.assertLess(image.getpixel((40,40))[1],40)

if __name__=='__main__':unittest.main(verbosity=2)
