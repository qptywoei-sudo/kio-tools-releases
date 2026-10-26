"""Synthetic Outlook-style email; no real message or customer data is used."""
import io,sys,unittest
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageChops
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
from ai_image_translate import render,font_path

def mail_fixture():
    image=Image.new('RGB',(1100,790),'#ffffff');draw=ImageDraw.Draw(image)
    font=lambda size:ImageFont.truetype(font_path(),size,index=1)
    draw.rectangle((0,0,1099,53),fill='#0f6cbd')
    draw.text((25,10),'Outlook',font=font(24),fill='white')
    draw.rectangle((0,54,219,789),fill='#f4f5f7')
    draw.text((26,90),'Inbox',font=font(20),fill='#242424')
    draw.text((26,140),'Sent Items',font=font(18),fill='#555555')
    draw.text((26,186),'Drafts',font=font(18),fill='#555555')
    draw.line((220,54,220,789),fill='#d5d9de')
    draw.line((255,222,1060,222),fill='#d5d9de')
    draw.rectangle((260,428,1054,590),fill='#f4f6f8',outline='#c9cfd6')
    draw.line((260,480,1054,480),fill='#c9cfd6')
    draw.line((260,536,1054,536),fill='#c9cfd6')
    draw.line((650,428,650,590),fill='#c9cfd6')
    regions=[]
    def text(original,translated,box,size=20,color='#242424',bg='#ffffff',bold=False):
        x,y,right,bottom=box
        draw.multiline_text((x+2,y+2),original,font=font(size),fill=color,spacing=5,stroke_width=1 if bold else 0)
        regions.append({'x':x*1000/image.width,'y':y*1000/image.height,'width':(right-x)*1000/image.width,'height':(bottom-y)*1000/image.height,'originalText':original,'translatedText':translated,'foreground':color,'background':bg,'align':'left','fontSize':size*1000/image.height,'fontWeight':'bold' if bold else 'normal'})
    text('Delivery schedule update','배송 일정 안내',(260,83,1044,140),30,bold=True)
    text('Alex Morgan <alex@example.com>','Alex Morgan <alex@example.com>',(260,150,1000,185),18)
    text('To: Operations team','받는 사람: 운영팀',(260,187,1030,219),16,color='#666666')
    text('Hello everyone,','안녕하세요,',(260,246,1030,281),20)
    text('Please review the updated delivery schedule below.\nThe order number and quantities remain unchanged.','아래의 변경된 배송 일정을 확인해 주세요.\n주문 번호와 수량은 변경되지 않았습니다.',(260,300,1040,374),20)
    text('Delivery information','배송 안내',(260,383,1040,419),22,bold=True)
    text('Order number','주문 번호',(278,439,630,475),18,bg='#f4f6f8')
    text('A-1024','A-1024',(673,439,1037,475),18,bg='#f4f6f8')
    text('Expected delivery','배송 예정',(278,493,630,530),18,bg='#f4f6f8')
    text('Tomorrow before 3:00 PM','내일 오후 3시 이전',(673,493,1037,530),18,bg='#f4f6f8',color='#0f6cbd')
    text('Quantity','수량',(278,549,630,585),18,bg='#f4f6f8')
    text('24','24',(673,549,1037,585),18,bg='#f4f6f8')
    text('Thank you for your cooperation.','협조해 주셔서 감사합니다.',(260,622,1040,660),20)
    text('Best regards,\nAlex','감사합니다.\nAlex',(260,684,1040,753),18)
    stream=io.BytesIO();image.save(stream,'PNG')
    return stream.getvalue(),{'regions':regions,'originalLanguage':'en'}

class MailImageTests(unittest.TestCase):
    def test_outlook_layout_borders_and_unchanged_identifiers_are_preserved(self):
        png,value=mail_fixture();source=Image.open(io.BytesIO(png)).convert('RGB')
        result=Image.open(io.BytesIO(render(png,value))).convert('RGB')
        self.assertEqual(source.size,result.size)
        for box in ((0,0,1100,54),(0,54,221,790),(255,220,1060,224),(649,428,652,590),(260,479,1055,482)):
            self.assertIsNone(ImageChops.difference(source.crop(box),result.crop(box)).getbbox(),box)
        for r in value['regions']:
            if r['originalText']==r['translatedText']:
                x=round(r['x']*1.1);y=round(r['y']*.79)
                box=(x,y,x+round(r['width']*1.1),y+round(r['height']*.79))
                self.assertIsNone(ImageChops.difference(source.crop(box),result.crop(box)).getbbox())
        # The short Korean subject must not leave any English subject ink behind.
        tail=result.crop((550,83,1044,140))
        self.assertIsNone(ImageChops.difference(tail,Image.new('RGB',tail.size,'white')).getbbox())

if __name__=='__main__':unittest.main()
