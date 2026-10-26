import unittest,time
from PIL import Image,ImageDraw
from subject_selection import subject_alpha,automatic_cutout

class AutomaticSubjectTests(unittest.TestCase):
 def subject(self):
  image=Image.new('RGBA',(400,300),'white');ImageDraw.Draw(image).ellipse((100,35,300,265),fill=(220,30,45,255));return image
 def test_neural_mask_selects_subject_and_rejects_background(self):
  started=time.perf_counter();mask=subject_alpha(self.subject())
  self.assertEqual(mask.size,(400,300));self.assertGreater(mask.getpixel((200,150)),230);self.assertLess(mask.getpixel((12,12)),15);self.assertLess(mask.getpixel((380,150)),15)
  print('U2NETP first selection seconds:',round(time.perf_counter()-started,3))
 def test_keeps_dimensions_rgb_and_original_transparency(self):
  image=self.subject();image.putalpha(128);out=automatic_cutout(image)
  self.assertEqual(out.size,image.size);self.assertEqual(out.getpixel((200,150))[:3],image.getpixel((200,150))[:3]);self.assertLessEqual(out.getpixel((200,150))[3],128);self.assertLess(out.getpixel((10,10))[3],10)
 def test_uniform_image_has_no_invented_subject(self):
  with self.assertRaisesRegex(ValueError,'subjectNotFound'):subject_alpha(Image.new('RGBA',(100,100),'red'))
 def test_tiny_image_rejected_before_inference(self):
  with self.assertRaisesRegex(ValueError,'invalidRequest'):subject_alpha(Image.new('RGBA',(2,2),'red'))
if __name__=='__main__':unittest.main()
