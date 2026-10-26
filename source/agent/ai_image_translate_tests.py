import copy,io,math,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw,ImageFont,ImageChops
from ai_image_translate import validate,render,font_path
from common import AgentError

def region(**changes):
    return dict(dict(x=100,y=200,width=700,height=200,originalText='Delivery tomorrow',translatedText='내일 배송',foreground='#182030',background='#FFFFFF',align='left',fontSize=None,fontWeight='normal'),**changes)

class ImageTranslationTests(unittest.TestCase):
    def setUp(self):
        self.image=Image.new('RGB',(800,400),'#dfe8f1');draw=ImageDraw.Draw(self.image)
        draw.rectangle((80,80,639,159),fill='white')
        draw.text((85,82),'Delivery tomorrow',font=ImageFont.truetype(font_path(),36),fill='#182030')
        stream=io.BytesIO();self.image.save(stream,'PNG');self.png=stream.getvalue()
        self.value={'regions':[region()],'originalLanguage':'en'}
    def test_preserves_resolution_and_every_pixel_outside_text_box(self):
        result=Image.open(io.BytesIO(render(self.png,self.value))).convert('RGB')
        self.assertEqual(result.size,self.image.size)
        self.assertIsNone(ImageChops.difference(result.crop((0,160,800,400)),self.image.crop((0,160,800,400))).getbbox())
        self.assertIsNone(ImageChops.difference(result.crop((0,0,80,400)),self.image.crop((0,0,80,400))).getbbox())
        self.assertIsNotNone(ImageChops.difference(result,self.image).getbbox())
    def test_short_translation_erases_original_ink_in_remaining_box(self):
        value=copy.deepcopy(self.value);value['regions'][0]['translatedText']='새'
        result=Image.open(io.BytesIO(render(self.png,value))).convert('RGB')
        cleared=result.crop((230,80,640,160))
        self.assertIsNone(ImageChops.difference(cleared,Image.new('RGB',cleared.size,'white')).getbbox())
    def test_no_text_keeps_all_pixels_and_alpha(self):
        result=Image.open(io.BytesIO(render(self.png,{'regions':[],'originalLanguage':None})))
        self.assertIsNone(ImageChops.difference(result,self.image.convert('RGBA')).getbbox())
    def test_rejects_bad_geometry_before_rendering(self):
        for key,val in [('x',math.nan),('width',-1),('x',True),('x',900),('foreground','url(test)'),('translatedText',''),('fontSize',math.inf),('fontSize',True),('fontSize',0),('fontWeight','heavy')]:
            value=copy.deepcopy(self.value);value['regions'][0][key]=val
            with self.subTest(key=key,val=val),self.assertRaises(AgentError):validate(value)
    def test_cancel_stops_before_output(self):
        def cancel():raise AgentError('cancelled')
        with self.assertRaises(AgentError):render(self.png,self.value,cancel)
    def test_fit_wraps_long_translation_and_cjk(self):
        for text in ['내일 오후 세 시까지 주문하신 제품을 배송합니다.','Giao hàng vào ngày mai trước ba giờ chiều.','明日の午後三時までにお届けします。']:
            value=copy.deepcopy(self.value);value['regions'][0]['translatedText']=text
            self.assertEqual(Image.open(io.BytesIO(render(self.png,value))).size,(800,400))
    def test_short_translation_keeps_body_text_size_in_a_padded_box(self):
        value=copy.deepcopy(self.value);value['regions'][0]['translatedText']='새'
        result=Image.open(io.BytesIO(render(self.png,value))).convert('RGB')
        ink=ImageChops.difference(result.crop((80,80,640,160)),Image.new('RGB',(560,80),'white')).getbbox()
        self.assertIsNotNone(ink)
        self.assertLessEqual(ink[3]-ink[1],40)
        self.assertLessEqual(ink[2]-ink[0],45)
    def test_already_target_language_and_addresses_keep_exact_pixels(self):
        value=copy.deepcopy(self.value);value['regions'][0]['translatedText']=value['regions'][0]['originalText']
        result=Image.open(io.BytesIO(render(self.png,value))).convert('RGB')
        self.assertIsNone(ImageChops.difference(result,self.image).getbbox())
    def test_horizontal_gradient_is_restored_without_source_ink_or_flat_patch(self):
        import numpy as np
        y,x=np.mgrid[:400,:800]
        pixels=np.stack((220+x*25/800,235+x*15/800,245-x*15/800),axis=2).astype('uint8')
        clean=Image.fromarray(pixels);source=clean.copy()
        ImageDraw.Draw(source).text((85,82),'Delivery tomorrow',font=ImageFont.truetype(font_path(),36),fill='#182030')
        stream=io.BytesIO();source.save(stream,'PNG')
        value=copy.deepcopy(self.value);value['regions'][0].update(translatedText='새',background='#e8eef1')
        result=Image.open(io.BytesIO(render(stream.getvalue(),value))).convert('RGB')
        # A short translation leaves the original sentence's tail available as ground truth.
        error=np.abs(np.asarray(result.crop((230,80,640,160))).astype(int)-np.asarray(clean.crop((230,80,640,160))).astype(int))
        self.assertLessEqual(int(error.max()),2)
    def test_gray_email_cell_and_subpixel_fringe_are_completely_cleared(self):
        source=Image.new('RGB',(800,400),'#f3f5f7');draw=ImageDraw.Draw(source)
        draw.rectangle((79,79,640,160),outline='#a0a6ad',width=1)
        draw.text((86,82),'Delivery tomorrow',font=ImageFont.truetype(font_path(),36),fill='#3c1820')
        draw.text((84,82),'Delivery tomorrow',font=ImageFont.truetype(font_path(),36),fill='#182c50')
        draw.text((85,82),'Delivery tomorrow',font=ImageFont.truetype(font_path(),36),fill='#182030')
        stream=io.BytesIO();source.save(stream,'PNG')
        value=copy.deepcopy(self.value);value['regions'][0].update(translatedText='새',background='#f3f5f7')
        result=Image.open(io.BytesIO(render(stream.getvalue(),value))).convert('RGB')
        cleared=result.crop((230,80,640,160))
        self.assertIsNone(ImageChops.difference(cleared,Image.new('RGB',cleared.size,'#f3f5f7')).getbbox())
        self.assertEqual(result.getpixel((79,100)),source.getpixel((79,100)))
        self.assertEqual(result.getpixel((640,100)),source.getpixel((640,100)))
    def test_translation_preserves_existing_transparency(self):
        source=self.image.convert('RGBA');source.putalpha(160)
        stream=io.BytesIO();source.save(stream,'PNG')
        result=Image.open(io.BytesIO(render(stream.getvalue(),self.value)))
        self.assertIsNone(ImageChops.difference(result.getchannel('A'),source.getchannel('A')).getbbox())

if __name__=='__main__':unittest.main()
