from pathlib import Path
import sys,json,hashlib,io
sys.path.insert(0,str(Path(__file__).parent));import engine as e
from PIL import Image,ImageDraw
import pymupdf as fitz
root=Path(__file__).parent/'fixtures';root.mkdir(exist_ok=True);out=root/'outputs';out.mkdir(exist_ok=True)
checks=[]
def check(name,condition):
 assert condition,name;checks.append(name)
def run(op,**kwargs):
 r=e.run(dict(op=op,output_dir=str(out),**kwargs));assert r['success'],(op,r);return r
image=Image.new('RGBA',(160,100),(0,0,0,0));ImageDraw.Draw(image).rectangle((0,0,79,99),fill=(255,0,0,255));image.save(root/'source.png')
source=root/'source.png';digest=hashlib.sha256(source.read_bytes()).hexdigest()
for fmt in ['jpg','png','webp']:
 r=run('image_process',inputs=[str(source)],format=fmt,quality=70,width=80,height=0,keep_ratio=True,no_upscale=True)
 p=Path(r['files'][0]);i=Image.open(p);i.load();check(f'PNG to {fmt} actual decode+resize',i.size==(80,50))
 if fmt=='jpg':check('Transparent JPEG background white',all(v>240 for v in i.getpixel((70,20))))
 item=r['data']['results'][0];check('Real output byte metrics '+fmt,item['output_bytes']==p.stat().st_size and item['saved_bytes']==source.stat().st_size-p.stat().st_size)
jpg=Image.new('RGB',(30,20),'blue');jpg.putpixel((0,0),(255,0,0));exif=jpg.getexif();exif[274]=6;jpg.save(root/'exif.jpg',exif=exif,quality=100)
r=run('image_process',inputs=[str(root/'exif.jpg')],format='png');check('EXIF rotation normalized',Image.open(r['files'][0]).size==(20,30))
r=run('image_process',inputs=[str(root/'exif.jpg')],format='webp');check('JPEG to WebP',Image.open(r['files'][0]).format=='WEBP')
r=run('image_process',inputs=[str(source)],format='png',width=600);check('No automatic enlargement',Image.open(r['files'][0]).size==(160,100))
r=run('image_process',inputs=[str(source)],format='jpg',scale_percent=25);check('Percentage resize',Image.open(r['files'][0]).size==(40,25))
check('Original image SHA preserved',hashlib.sha256(source.read_bytes()).hexdigest()==digest)
for docname,n in [('a',3),('b',2)]:
 d=fitz.open()
 for index in range(n):
  p=d.new_page(width=300,height=400);p.insert_text((30,40),f'ORIGINAL {docname} PAGE {index+1}',fontsize=16)
 d.save(root/(docname+'.pdf'));d.close()
a=root/'a.pdf';b=root/'b.pdf'
r=run('pdf_merge',paths=[str(a),str(b)]);d=fitz.open(r['files'][0]);check('PDF merge count+content',d.page_count==5 and 'b PAGE 2' in d[4].get_text());d.close()
r=run('pdf_extract',path=str(a),pages='1,3');d=fitz.open(r['files'][0]);check('PDF split selected pages',d.page_count==2 and 'PAGE 3' in d[1].get_text());d.close()
r=run('pdf_manage',path=str(a),page_order=[3,1],rotations={'3':90});d=fitz.open(r['files'][0]);check('PDF delete+reorder+rotate',d.page_count==2 and d[0].rotation==90 and 'PAGE 3' in d[0].get_text());rotated=Path(r['files'][0]);d.close()
r=run('images_pdf',paths=[str(source),str(root/'exif.jpg')],page_size='a4',orientation='landscape',margin_mm=12);d=fitz.open(r['files'][0]);check('Images to PDF A4 landscape',d.page_count==2 and d[0].rect.width>d[0].rect.height);d.close()
r=run('images_pdf',paths=[str(source)],page_size='image',margin_mm=0);d=fitz.open(r['files'][0]);check('Image-size PDF ratio',abs(d[0].rect.width/d[0].rect.height-1.6)<.001);d.close()
for fmt in ['png','jpg']:
 r=run('pdf_render',path=str(a),pages='3,1',format=fmt,dpi=144)
 check('PDF to '+fmt+' ordered actual files',r['data']['pages'][0]['index']==3 and r['data']['pages'][1]['index']==1 and Image.open(r['files'][0]).size==(600,800))
overlay=Image.new('RGBA',(400,300),(0,0,0,0));ImageDraw.Draw(overlay).rectangle((0,0,50,40),fill=(255,0,0,255));overlay.save(root/'overlay.png')
r=run('pdf_annotate',path=str(rotated),page=1,overlay_path=str(root/'overlay.png'));d=fitz.open(r['files'][0]);pix=d[0].get_pixmap();img=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
check('PDF rotated annotation top-left placement',img.getpixel((10,10))[0]>240 and img.getpixel((10,10))[1]<30)
check('PDF source searchable text preserved under annotation','ORIGINAL a PAGE 3' in d[0].get_text());d.close()
for kind,text in [('qr','안녕하세요 GalaxyControl — local 123'),('code128','Galaxy-Control-123'),('ean13','590123412345'),('ean8','9638507')]:
 r=run('code_generate',kind=kind,text=text,qr_type='text');decoded=run('code_read',path=r['files'][0])['data']['results'];actual=r['data']['text']
 same=any(x['text']==actual for x in decoded)
 check(kind+' encode/decode roundtrip',same)
r=run('code_generate',kind='qr',qr_type='wifi',ssid='Local;테스트',password='a:b\\;c',security='WPA');decoded=run('code_read',path=r['files'][0]);check('WiFi QR escaped exact roundtrip',decoded['data']['results'][0]['text']==r['data']['text'])
check('Invalid barcode checksum rejected',not e.run(dict(op='code_generate',kind='ean13',text='5901234123450',output_dir=str(out)))['success'])
check('Invalid PDF range rejected',not e.run(dict(op='pdf_extract',path=str(a),pages='0-500',output_dir=str(out)))['success'])
check('Unreadable QR reports no guessing',not e.run(dict(op='code_read',path=str(source)))['success'])
r=run('image_process',inputs=[str(source)],format='png');r2=run('image_process',inputs=[str(source)],format='png');check('Existing result never overwritten',r['files'][0]!=r2['files'][0])
report={'passed':len(checks),'checks':checks,'versions':{'Pillow':Image.__version__,'PyMuPDF':fitz.VersionBind}}
(Path(__file__).parent/'test-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
