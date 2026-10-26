"""Guided-cutout image tests, independent of a UI or network service."""
import unittest
from PIL import Image, ImageDraw
from engine_extra import guided_cutout

class GuidedCutoutTests(unittest.TestCase):
 def subject(self):
  image=Image.new('RGBA',(240,180),'white')
  ImageDraw.Draw(image).ellipse((60,25,185,155),fill=(220,30,45,255))
  return image

 def marks(self):
  return [{'kind':'foreground','radius':7,'points':[[105,60],[115,90],[120,115]]},
          {'kind':'background','radius':8,'points':[[22,30],[25,90],[30,145]]}]

 def test_segment_follows_subject_instead_of_only_brush(self):
  result=guided_cutout(self.subject(),{'marks':self.marks(),'feather':0,'trim':False})
  self.assertEqual(result.size,(240,180))
  self.assertGreater(result.getpixel((165,90))[3],240)
  self.assertEqual(result.getpixel((12,12))[3],0)
  self.assertEqual(result.getpixel((215,100))[3],0)

 def test_trims_to_subject_and_preserves_original_transparency(self):
  source=self.subject();source.putpixel((120,90),(220,30,45,0))
  full=guided_cutout(source,{'marks':self.marks(),'feather':0,'trim':False})
  self.assertEqual(full.getpixel((120,90))[3],0)
  cropped=guided_cutout(self.subject(),{'marks':self.marks(),'feather':0,'trim':True})
  self.assertLess(cropped.width,160);self.assertLess(cropped.height,160)
  self.assertGreater(cropped.width,100);self.assertGreater(cropped.height,100)

 def test_background_mark_removes_selected_part(self):
  marks=self.marks()+[{'kind':'background','radius':8,'points':[[165,90]]}]
  result=guided_cutout(self.subject(),{'marks':marks,'feather':0,'trim':False})
  self.assertEqual(result.getpixel((165,90))[3],0)
  self.assertGreater(result.getpixel((115,90))[3],240)

 def test_requires_foreground_and_rejects_invalid_points(self):
  with self.assertRaises(ValueError):guided_cutout(self.subject(),{'marks':[]})
  with self.assertRaises(ValueError):guided_cutout(self.subject(),{'marks':[{'kind':'foreground','points':[[-10,30]]}]})

 def test_similar_color_disconnected_background_is_not_kept(self):
  source=self.subject();ImageDraw.Draw(source).rectangle((6,6,28,18),fill=(220,30,45,255))
  result=guided_cutout(source,{'marks':self.marks(),'feather':0,'trim':False})
  self.assertEqual(result.getpixel((15,12))[3],0)
  self.assertEqual(result.getpixel((115,90))[3],255)

if __name__=='__main__':unittest.main()
