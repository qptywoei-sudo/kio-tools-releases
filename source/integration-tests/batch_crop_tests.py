"""Actual Pillow batch crop tests in disposable storage; originals are preserved."""
import hashlib,sys,tempfile,unittest
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'engine'))
import engine_extra as extra
from PIL import Image

class BatchCropTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.out=self.root/'output';self.out.mkdir();self.inputs=[];self.hashes={}
  for number,size in enumerate([(200,100),(80,240)]):
   path=self.root/f'source-{number}.png';image=Image.new('RGBA',size)
   image.putdata([(x%256,y%256,40,255) for y in range(size[1]) for x in range(size[0])]);image.save(path)
   self.inputs.append(str(path));self.hashes[path]=hashlib.sha256(path.read_bytes()).hexdigest()
 def tearDown(self):
  for path,digest in self.hashes.items():self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)
  self.temp.cleanup()
 def run_edit(self,**options):return extra.image_edit({'inputs':self.inputs,'baseCount':2,'output_dir':str(self.out),'format':'png','layers':[],**options})
 def test_each_size_is_cropped_proportionally_with_source_pixels(self):
  result=self.run_edit(cropX=25,cropY=20,cropWidth=50,cropHeight=50)
  for path,size,origin in zip(result['files'],[(100,50),(40,120)],[(50,20),(20,48)]):
   with Image.open(path) as image:self.assertEqual(image.size,size);self.assertEqual(image.getpixel((0,0)),(*origin,40,255))
 def test_default_is_full_image_and_crop_precedes_rotation_and_border(self):
  for path,size in zip(self.run_edit()['files'],[(200,100),(80,240)]):
   with Image.open(path) as image:self.assertEqual(image.size,size)
  result=self.run_edit(cropX=25,cropY=20,cropWidth=50,cropHeight=50,rotate=90,border=2,borderColor='#ff0000')
  for path,size in zip(result['files'],[(54,104),(124,44)]):
   with Image.open(path) as image:self.assertEqual(image.size,size);self.assertEqual(image.getpixel((0,0)),(255,0,0,255))
 def test_canvas_pixel_crop_takes_priority(self):
  for path in self.run_edit(crop=[10,20,30,40],cropX=90,cropWidth=90)['files']:
   with Image.open(path) as image:self.assertEqual(image.size,(30,40));self.assertEqual(image.getpixel((0,0)),(10,20,40,255))
 def test_invalid_percentage_crops_fail_before_creating_outputs(self):
  for options in [{'cropX':60,'cropWidth':50},{'cropY':70,'cropHeight':40},{'cropWidth':0},{'cropHeight':0},{'cropX':-1},{'cropWidth':101},{'cropX':float('nan')},{'cropY':float('inf')},{'cropWidth':True}]:
   with self.subTest(options=options),self.assertRaises(ValueError):self.run_edit(**options)
  self.assertEqual(list(self.out.iterdir()),[])
 def test_subpixel_empty_crops_are_rejected(self):
  with self.assertRaises(ValueError):self.run_edit(cropWidth=.01)

if __name__=='__main__':unittest.main(verbosity=2)
