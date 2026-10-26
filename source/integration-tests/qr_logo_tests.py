"""Real Pillow / qrcode / ZXing regression checks; no mock decoder or phone claim."""
from pathlib import Path
import base64, hashlib, io, sys, tempfile, unittest, xml.etree.ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
import engine_extra, qrcode, qr_logo, zxingcpp
from PIL import Image, ImageDraw
import pymupdf


class QrLogoTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  self.logo=self.root/'logo.png';image=Image.new('RGBA',(240,120),'#ff0033');ImageDraw.Draw(image).ellipse((90,30,150,90),fill='#123456');image.save(self.logo)
  self.text='https://kio-library.vercel.app/?source=원본&path=%2Fkeep%20this#unchanged'
 def tearDown(self):self.temp.cleanup()
 def generate(self,**options):
  return engine_extra.code_generate({'kind':'qr','text':self.text,'output_dir':str(self.root/'out'),'format':'png','inputs':[str(self.logo)],'logoInput':0,**options})
 def decode(self,path):
  self.assertTrue(qr_logo.verify_export(path,self.text))
 def test_png_jpeg_and_svg_both_shapes_scan_with_exact_original_url(self):
  for shape in ('square','circle'):
   for fmt in ('png','jpg','svg'):
    with self.subTest(shape=shape,format=fmt):
     result=self.generate(format=fmt,logo_shape=shape)
     self.assertTrue(result['data']['scanVerified']);self.assertTrue(result['data']['logoIncluded']);self.assertEqual(result['data']['text'],self.text)
     self.decode(result['files'][0])
 def test_svg_embeds_logo_and_renders_its_actual_pixels(self):
  path=self.generate(format='svg')['files'][0];root=ET.fromstring(Path(path).read_bytes());embedded=root.find('{http://www.w3.org/2000/svg}image');self.assertIsNotNone(embedded)
  payload=embedded.attrib['href'];self.assertTrue(payload.startswith('data:image/png;base64,'));Image.open(io.BytesIO(base64.b64decode(payload.split(',')[1]))).verify()
  with pymupdf.open(path) as doc:
   pix=doc[0].get_pixmap(alpha=False);image=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
   red=image.getpixel((pix.width//2-25,pix.height//2));self.assertGreater(red[0],230);self.assertLess(red[1],20)
 def test_logo_free_legacy_qr_is_still_readable_with_h_level(self):
  result=self.generate(logoInput=None);self.decode(result['files'][0]);self.assertFalse(result['data']['logoIncluded'])
  qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H,border=4);qr.add_data(self.text);qr.make(fit=True)
  with Image.open(result['files'][0]) as image:
   decoded=zxingcpp.read_barcode(image.convert('RGB'));self.assertEqual(decoded.ec_level,'H')
 def test_color_styles_and_logo_resize_keep_content(self):
  for size in (256,768):
   for style in ('square','rounded','circle'):
    with self.subTest(size=size,style=style):
     result=self.generate(size=size,style=style,foreground='#182949',background='#fff8e8',logo_size=14,logo_padding=1);self.decode(result['files'][0])
 def test_original_logo_never_changes(self):
  before=hashlib.sha256(self.logo.read_bytes()).hexdigest();self.generate();self.assertEqual(before,hashlib.sha256(self.logo.read_bytes()).hexdigest())
 def test_white_padding_and_exact_center(self):
  result=self.generate(size=500,logo_size=20,logo_padding=2)
  with Image.open(result['files'][0]) as image:
   self.assertEqual(image.getpixel((250,250)),(18,52,86,255))
  exported=self.generate(format='svg');element=ET.fromstring(Path(exported['files'][0]).read_bytes()).find('{http://www.w3.org/2000/svg}image')
  badge=Image.open(io.BytesIO(base64.b64decode(element.attrib['href'].split(',')[1])))
  self.assertEqual(badge.getpixel((3,badge.height//2)),(255,255,255,255));self.assertEqual(badge.getpixel((4,badge.height//2)),(255,0,51,255))
 def test_circle_badge_has_transparent_corners(self):
  qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H,border=4);qr.add_data(self.text);qr.make(fit=True)
  square,_,_=qr_logo.artwork(qr.get_matrix(),500,'#111827','#ffffff','square',{'inputs':[str(self.logo)],'logoInput':0})
  circle,_,_=qr_logo.artwork(qr.get_matrix(),500,'#111827','#ffffff','square',{'inputs':[str(self.logo)],'logoInput':0,'logo_shape':'circle'})
  self.assertNotEqual(square.tobytes(),circle.tobytes())
 def test_invalid_logo_request_never_publishes_file(self):
  for options in ({'logoInput':-1},{'logoInput':True},{'logoInput':5},{'logo_shape':'triangle'}):
   with self.subTest(options=options),self.assertRaises((ValueError,TypeError)):
    self.generate(**options)
  self.assertFalse(list((self.root/'out').glob('*')))
 def test_client_sizing_options_cannot_override_automatic_logo_and_fixed_padding(self):
  result=self.generate(logo_size=10000,logo_padding=10000);self.decode(result['files'][0])
  self.assertTrue(10<=result['data']['appliedLogoPercent']<=30);self.assertEqual(result['data']['logoPaddingPx'],4)
 def test_real_scan_failure_automatically_reduces_logo_to_a_passing_size(self):
  text='https://example.com/4'+'x'*32
  result=self.generate(text=text,size=96,style='circle')
  self.assertTrue(qr_logo.verify_export(result['files'][0],text))
  self.assertGreaterEqual(result['data']['appliedLogoPercent'],10);self.assertLess(result['data']['appliedLogoPercent'],30)
 def test_small_qr_badge_never_touches_finders_or_timing(self):
  result=self.generate(text='x',size=128)
  self.assertLessEqual(result['data']['appliedLogoPercent'],15);self.assertTrue(qr_logo.verify_export(result['files'][0],'x'))
 def test_card_knockout_omits_every_touched_module_in_svg_and_png(self):
  qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H,border=4);qr.add_data(self.text);qr.make(fit=True);matrix=qr.get_matrix();n=len(matrix)
  for shape in ('circle','square'):
   for style in ('square','circle','rounded'):
    with self.subTest(shape=shape,style=style):
     image,svg,_=qr_logo.artwork(matrix,512,'#111827','#fff8e8',style,{'inputs':[str(self.logo)],'logoInput':0,'logo_shape':shape})
     geometry=qr_logo.logo_geometry(n,512,30);root=ET.fromstring(svg);drawn=[]
     for node in list(root)[1:]:
      if node.tag.endswith('image'):continue
      x=float(node.attrib.get('x',float(node.attrib.get('cx',.5))-.5));y=float(node.attrib.get('y',float(node.attrib.get('cy',.5))-.5));drawn.append((int(x),int(y)))
     expected={(x,y) for y,row in enumerate(matrix) for x,on in enumerate(row) if on and not qr_logo.module_under_badge(geometry,x,y,shape)}
     self.assertEqual(set(drawn),expected)
     touched=[(x,y) for y,row in enumerate(matrix) for x,on in enumerate(row) if on and qr_logo.module_under_badge(geometry,x,y,shape)]
     self.assertTrue(touched)
     for x,y in touched:
      box=(round(x*geometry['unit']),round(y*geometry['unit']),round((x+1)*geometry['unit']),round((y+1)*geometry['unit']))
      self.assertNotIn((17,24,39,255),image.crop(box).getdata())
 def test_badge_intersection_uses_circle_geometry_and_half_pixel_guard(self):
  geometry={'unit':10,'left':20,'outer':20}
  self.assertTrue(qr_logo.module_under_badge(geometry,1,2,'square'))
  self.assertFalse(qr_logo.module_under_badge(geometry,1,1,'circle'))
  self.assertTrue(qr_logo.module_under_badge(geometry,1,2,'circle'))
  self.assertFalse(qr_logo.module_under_badge(geometry,0,0,'square'))
 def test_candidates_protect_ideal_and_rounded_finder_timing_corridor(self):
  for n in (29,33,37,45,65):
   for size in (96,128,257,512):
    for percent in qr_logo.logo_candidates(n,size):
     geometry=qr_logo.logo_geometry(n,size,percent);unit=geometry['unit']
     self.assertGreater(geometry['left'],max(12*unit,round(12*unit))+.5)
     self.assertLess(geometry['left']+geometry['outer'],min((n-12)*unit,round((n-12)*unit))-.5)
 def test_failed_scan_is_explicit_and_not_exported(self):
  with self.assertRaisesRegex(ValueError,'qrScanFailed'):self.generate(foreground='#ffffff',background='#ffffff')
  self.assertFalse(list((self.root/'out').glob('*')))


if __name__=='__main__':unittest.main()
