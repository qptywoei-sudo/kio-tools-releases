"""Disposable real HTTP tests against shared UI options and local tool workers.
UI TypeScript fixture comes from ui-contract-fixture.json; no production approval
or existing user file is accessed. Run with bundled Python -I -B.
"""
import sys,json,time,unittest,io,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import review_tests as reviewed
from PIL import Image,ImageDraw
import engine

UI=json.loads(Path(__file__).with_name('ui-contract-fixture.json').read_text())

class UIContracts(unittest.TestCase):
 setUp=reviewed.ReviewAPITests.setUp
 tearDown=reviewed.ReviewAPITests.tearDown
 request=reviewed.ReviewAPITests.request
 def register(self,path):return self.agent.register(path,self.origin,'fixture')['id']
 def job(self,op,ids=(),options=None):
  status,response=self.request('POST','/jobs',{'operation':op,'inputs':list(ids),'options':options or {}});self.assertEqual(status,202,response);ident=response['job']['id'];deadline=time.monotonic()+45
  while time.monotonic()<deadline:
   status,response=self.request('GET','/jobs/'+ident);self.assertEqual(status,200);job=response['job']
   if job['status'] in ('complete','failed','cancelled'):break
   time.sleep(.04)
  self.assertEqual(job['status'],'complete',job);return job['result']
 def artifact(self,result):
  file=result['files'][0];status,data=self.request('GET','/artifacts/'+file['id']);self.assertEqual(status,200);return file,data
 def canvas(self,layer):
  options={**UI['taskOptions']['canvas_export'],'width':140,'height':100,'pages':[{'layers':[layer]}],'format':'png'}
  return Image.open(io.BytesIO(self.artifact(self.job('canvas_export',options=options))[1])).convert('RGBA')
 def test_draw_and_line_keep_original_pixel_coordinates(self):
  for name,points in [('draw',[(20,20),(60,40),(90,70)]),('line',[(20,50),(60,50),(99,50)])]:
   image=self.canvas(UI[name])
   for point in points:
    pixel=image.getpixel(point);self.assertGreater(pixel[0],180);self.assertLess(pixel[1],50)
 def test_horizontal_arrow_head_survives_positive_local_bbox(self):
  image=self.canvas(UI['arrow']);colored=[(x,y) for y in range(image.height) for x in range(image.width) if image.getpixel((x,y))[0]>180 and image.getpixel((x,y))[1]<50]
  self.assertTrue(colored);height=max(y for _,y in colored)-min(y for _,y in colored)+1
  self.assertGreater(height,UI['arrow']['lineWidth']+2,'Arrow head is clipped to the6-pixel UI bounding box')
 def test_single_point_draw_survives_export(self):
  image=self.canvas(UI['dot']);self.assertLess(image.getpixel((20,20))[1],50,'Single brush mark vanished in saved image')
 def test_qr_read_uses_results_array_expected_by_ui(self):
  text='ADMIN 계약 확인 https://example.com/test'
  generated=self.job('code_generate',options={**UI['taskOptions']['code_generate'],'text':text,'kind':'qr','format':'png'});qr=generated['files'][0]
  read=self.job('code_read',[qr['id']]);self.assertTrue(any(row.get('text')==text and isinstance(row.get('format'),str) for row in read['data']['results']));self.assertEqual(read['files'],[])
 def test_pdf_order_rotation_and_original_preservation(self):
  path=self.path/'three.pdf'
  with engine.fitz.open() as doc:
   for n in range(1,4):page=doc.new_page(width=200,height=120);page.insert_text((20,40),'PAGE '+str(n))
   doc[1].set_rotation(90);doc.save(path)
  before=path.read_bytes();result=self.job('pdf_manage',[self.register(path)],{'page_order':[3,1],'rotations':{'3':90,'1':180}});_,data=self.artifact(result)
  with engine.fitz.open(stream=data,filetype='pdf') as doc:
   self.assertEqual(doc.page_count,2);self.assertIn('PAGE 3',doc[0].get_text());self.assertIn('PAGE 1',doc[1].get_text());self.assertEqual([page.rotation for page in doc],[90,180])
  self.assertEqual(path.read_bytes(),before)
 def overlay_files(self,rotated=False):
  pdf=self.path/'base.pdf'
  with engine.fitz.open() as doc:
   page=doc.new_page(width=200,height=120)
   if rotated:page.set_rotation(90)
   doc.save(pdf)
  size=(120,200) if rotated else (200,120);image=Image.new('RGBA',size);ImageDraw.Draw(image).rectangle((10,10,30,30),fill='red');overlay=self.path/'overlay.png';image.save(overlay)
  return pdf,overlay,size
 def test_pdf_annotation_rotated_overlay_matches_preview(self):
  pdf,overlay,size=self.overlay_files(True);before=pdf.read_bytes();result=self.job('pdf_annotate',[self.register(pdf),self.register(overlay)],{'page':1,'previewWidth':size[0],'previewHeight':size[1]});_,data=self.artifact(result)
  with engine.fitz.open(stream=data,filetype='pdf') as doc:
   pix=doc[0].get_pixmap();image=Image.frombytes('RGB',(pix.width,pix.height),pix.samples);self.assertEqual(image.getpixel((20,20)),(255,0,0));self.assertEqual(image.getpixel((60,100)),(255,255,255))
  self.assertEqual(pdf.read_bytes(),before)
 def test_pdf_signature_rotated_overlay_matches_preview(self):
  pdf,overlay,size=self.overlay_files(True);before=pdf.read_bytes();result=self.job('signature_apply',[self.register(pdf),self.register(overlay)],{'signatureInput':1,'overlay':True,'pages':'1','previewWidth':size[0],'previewHeight':size[1]});_,data=self.artifact(result)
  with engine.fitz.open(stream=data,filetype='pdf') as doc:
   pix=doc[0].get_pixmap();image=Image.frombytes('RGB',(pix.width,pix.height),pix.samples);self.assertEqual(image.getpixel((20,20)),(255,0,0),'Signature moved from displayed preview position')
  self.assertEqual(pdf.read_bytes(),before)
 def test_png_signature_transparency_preserves_background(self):
  base=self.path/'base.png';overlay=self.path/'sig.png';Image.new('RGBA',(40,30),'blue').save(base);image=Image.new('RGBA',(40,30));ImageDraw.Draw(image).rectangle((10,10,20,20),fill='red');image.save(overlay);before=base.read_bytes()
  result=self.job('signature_apply',[self.register(base),self.register(overlay)],{'overlay':True,'signatureInput':1});_,data=self.artifact(result)
  image=Image.open(io.BytesIO(data)).convert('RGB');self.assertEqual(image.getpixel((15,15)),(255,0,0));self.assertEqual(image.getpixel((0,0)),(0,0,255));self.assertEqual(base.read_bytes(),before)
 def test_background_erase_restore_and_original_alpha(self):
  path=self.path/'subject.png';image=Image.new('RGBA',(32,32),(20,160,30,255));image.putpixel((5,5),(20,160,30,0));image.save(path);before=path.read_bytes()
  result=self.job('image_background',[self.register(path)],{'background':'transparent','format':'png','strokes':[{'restore':False,'radius':3,'points':[[8,8]]},{'restore':True,'radius':3,'points':[[24,24]]},{'restore':True,'radius':3,'points':[[5,5]]}]});_,data=self.artifact(result);image=Image.open(io.BytesIO(data)).convert('RGBA')
  self.assertEqual(image.getpixel((8,8))[3],0);self.assertEqual(image.getpixel((24,24))[3],255);self.assertEqual(image.getpixel((5,5))[3],0);self.assertEqual(path.read_bytes(),before)

if __name__=='__main__':unittest.main(verbosity=2)
