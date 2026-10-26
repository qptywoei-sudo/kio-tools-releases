"""Additive local tools built on GalaxyControl's validated image/PDF engine.
No image/document upload, OCR, arbitrary command execution, or source-file overwrite.
"""
from __future__ import annotations
import io,json,math,os,platform,re,subprocess,sys,uuid,zipfile,html,time
from pathlib import Path
import engine as base
_deps=Path(__file__).parent/'deps-agent'/base._arch
if not _deps.is_dir():_deps=Path(__file__).resolve().parents[2]/'tools'/'engine'/'deps-agent'/base._arch
if _deps.is_dir():sys.path.insert(0,str(_deps))
from PIL import Image,ImageDraw,ImageFont,ImageFilter,ImageEnhance,ImageOps,ImageColor

def bounded(value,default,lo,hi):
 v=float(default if value is None else value)
 if not math.isfinite(v) or not lo<=v<=hi:raise ValueError('invalidRequest')
 return v

def image_save(image,job,stem):
 fmt=str(job.get('format','png')).lower().replace('jpeg','jpg')
 if fmt not in ('png','jpg','webp'):raise ValueError('unsupported')
 quality=int(bounded(job.get('quality'),90,1,100))
 if fmt=='jpg':
  flat=Image.new('RGB',image.size,job.get('backgroundColor','#ffffff'));flat.paste(image,mask=image.getchannel('A') if image.mode=='RGBA' else None);image=flat
 opts={'quality':quality} if fmt!='png' else {'optimize':True}
 p=base.write_atomic(job['output_dir'],stem,'.'+fmt,lambda p:image.save(p,{'png':'PNG','jpg':'JPEG','webp':'WEBP'}[fmt],**opts));return p

def font(size):
 paths=[Path(__file__).parent/'fonts'/'NotoSansCJK-Regular.ttc',Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf'),Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/'malgun.ttf',Path('/System/Library/Fonts/Supplemental/Arial.ttf')]
 for p in paths:
  if p.is_file():
   try:return ImageFont.truetype(str(p),size)
   except OSError:pass
 return ImageFont.load_default(size=size)

def layers(image,items,inputs):
 if not isinstance(items,list) or len(items)>1000:raise ValueError('invalidRequest')
 for item in items:
  if not isinstance(item,dict):raise ValueError('invalidRequest')
  kind=item.get('type')
  item=dict(item)
  points=item.get('points',[])
  if kind in ('draw','line','arrow') and points and (float(item.get('width',0))<=0 or float(item.get('height',0))<=0):
   xs=[float(p[0]) for p in points];ys=[float(p[1]) for p in points];pad=int(item.get('lineWidth',3))*4+2;left=min(xs)-pad;top=min(ys)-pad
   item.update(x=left,y=top,width=max(1,max(xs)-left+pad),height=max(1,max(ys)-top+pad),points=[[x-left,y-top] for x,y in points])
  if kind=='text':
   if float(item.get('width',0))<=0:item['width']=min(30000,max(100,len(str(item.get('text','')))*float(item.get('fontSize',28))))
   if float(item.get('height',0))<=0:item['height']=float(item.get('fontSize',28))*2
  x=int(bounded(item.get('x'),0,-30000,30000));y=int(bounded(item.get('y'),0,-30000,30000));w=int(bounded(item.get('width'),100,1,30000));h=int(bounded(item.get('height'),50,1,30000));color=ImageColor.getcolor(item.get('color','#2563eb'),'RGBA');fill=None if item.get('fill','none') in ('none','',None) else ImageColor.getcolor(item['fill'],'RGBA');stroke=int(bounded(item.get('lineWidth'),3,1,1000));opacity=bounded(item.get('opacity'),1,0,1)
  if w*h>base.Image.MAX_IMAGE_PIXELS:raise ValueError('fileTooLarge')
  if kind in ('mosaic','blur'):
   box=(max(0,x),max(0,y),min(image.width,x+w),min(image.height,y+h))
   if box[2]>box[0] and box[3]>box[1]:
    region=image.crop(box);strength=int(bounded(item.get('strength'),12,1,100))
    changed=region.filter(ImageFilter.GaussianBlur(strength)) if kind=='blur' else region.resize((max(1,region.width//strength),max(1,region.height//strength)),Image.Resampling.BILINEAR).resize(region.size,Image.Resampling.NEAREST)
    image.paste(changed,box[:2])
   continue
  if kind=='arrow':
   # Local-point bounds cover the line; the arrow head needs additional room.
   pad=max(12,stroke*4)+stroke+2;x-=pad;y-=pad;w+=pad*2;h+=pad*2
   item['points']=[[float(a)+pad,float(b)+pad] for a,b in item.get('points',[[0,(h-pad*2)/2],[w-pad*2,(h-pad*2)/2]])]
   if w*h>base.Image.MAX_IMAGE_PIXELS:raise ValueError('fileTooLarge')
  surface=Image.new('RGBA',(w,h));draw=ImageDraw.Draw(surface)
  if kind=='text':
   text=str(item.get('text',''))[:10000];draw.multiline_text((2,2),text,font=font(int(bounded(item.get('fontSize'),28,6,1000))),fill=color,stroke_width=0)
   if fill:
    text_surface=surface;surface=Image.new('RGBA',(w,h),fill);surface.alpha_composite(text_surface)
  elif kind in ('rect','ellipse'):
   getattr(draw,'rectangle' if kind=='rect' else 'ellipse')((stroke/2,stroke/2,w-stroke/2-1,h-stroke/2-1),fill=fill,outline=color,width=stroke)
  elif kind in ('line','arrow'):
   points=item.get('points',[[0,h/2],[w,h/2]])
   if len(points)<2:raise ValueError('invalidRequest')
   a,b=points[0],points[-1];draw.line([tuple(a),tuple(b)],fill=color,width=stroke)
   if kind=='arrow':
    angle=math.atan2(b[1]-a[1],b[0]-a[0]);r=max(12,stroke*4)
    draw.polygon([tuple(b),(b[0]-r*math.cos(angle-.5),b[1]-r*math.sin(angle-.5)),(b[0]-r*math.cos(angle+.5),b[1]-r*math.sin(angle+.5))],fill=color)
  elif kind=='draw':
   points=item.get('points',[])
   if not isinstance(points,list) or len(points)>10000:raise ValueError('invalidRequest')
   if len(points)>1:draw.line([tuple(p) for p in points],fill=color,width=stroke,joint='curve')
   elif points:
    a,b=points[0];radius=stroke/2;draw.ellipse((a-radius,b-radius,a+radius,b+radius),fill=color)
  elif kind=='image':
   i=int(item.get('inputIndex',0))
   if not 0<=i<len(inputs):raise ValueError('inputMissing')
   surface=base.checked_image(inputs[i]).resize((w,h),Image.Resampling.LANCZOS)
  else:raise ValueError('unsupported')
  if opacity<1:surface.putalpha(surface.getchannel('A').point(lambda x:round(x*opacity)))
  rotation=bounded(item.get('rotation'),0,-3600,3600)
  if rotation:surface=surface.rotate(-rotation,expand=True,resample=Image.Resampling.BICUBIC);x-=(surface.width-w)//2;y-=(surface.height-h)//2
  image.alpha_composite(surface,(x,y))
 return image

def image_edit(job):
 files=[];inputs=job.get('inputs',[])
 if not inputs:raise ValueError('inputMissing')
 crop=job.get('crop')
 percent_crop=None
 # Canvas pixel coordinates take priority. Batch coordinates apply independently to each source size.
 if not crop:
  percent_crop=tuple(bounded(job.get(key),default,0,100) for key,default in [('cropX',0),('cropY',0),('cropWidth',100),('cropHeight',100)])
  x,y,w,h=percent_crop
  if any(isinstance(job.get(key),bool) for key in ('cropX','cropY','cropWidth','cropHeight')) or w<=0 or h<=0 or x+w>100 or y+h>100:raise ValueError('invalidRequest')
 # inputIndex references belong to overlays; baseCount permits applying same edits to many source images.
 count=int(job.get('baseCount',1 if job.get('layers') else len(inputs)))
 for p in inputs[:count]:
  image=base.checked_image(p)
  if crop:
   if len(crop)!=4:raise ValueError('invalidRequest')
   x,y,w,h=[int(bounded(v,0,0,30000)) for v in crop]
   if w<1 or h<1 or x+w>image.width or y+h>image.height:raise ValueError('invalidRequest')
   image=image.crop((x,y,x+w,y+h))
  elif percent_crop!=(0,0,100,100):
   x,y,w,h=percent_crop
   left,top=math.floor(image.width*x/100),math.floor(image.height*y/100)
   right,bottom=math.floor(image.width*(x+w)/100),math.floor(image.height*(y+h)/100)
   if right<=left or bottom<=top:raise ValueError('invalidRequest')
   image=image.crop((left,top,right,bottom))
  rotation=bounded(job.get('rotate'),0,-3600,3600)
  if rotation:image=image.rotate(-rotation,expand=True,resample=Image.Resampling.BICUBIC)
  if job.get('flip')=='horizontal':image=ImageOps.mirror(image)
  if job.get('flip')=='vertical':image=ImageOps.flip(image)
  for key,cls in [('brightness',ImageEnhance.Brightness),('contrast',ImageEnhance.Contrast),('saturation',ImageEnhance.Color)]:image=cls(image).enhance(bounded(job.get(key),1,0,4))
  if job.get('width') or job.get('height'):
   w=int(bounded(job.get('width'),0,0,30000));h=int(bounded(job.get('height'),0,0,30000));ratio=min([v for v in (w/image.width if w else None,h/image.height if h else None) if v is not None]);size=(max(1,round(image.width*ratio)),max(1,round(image.height*ratio)))
   if size[0]*size[1]>base.Image.MAX_IMAGE_PIXELS:raise ValueError('fileTooLarge')
   image=image.resize(size,Image.Resampling.LANCZOS)
  image=layers(image,job.get('layers',[]),inputs)
  border=int(bounded(job.get('border'),0,0,1000))
  if border:image=ImageOps.expand(image,border,job.get('borderColor','#ffffff'))
  files.append(image_save(image,job,Path(p).stem+'_edited'))
 return base.result(files)

def make_zip(files,job,stem):
 return base.write_atomic(job['output_dir'],stem,'.zip',lambda p:zip_files(p,files))
def zip_files(p,files):
 with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:
  for value in files:z.write(value,Path(value).name)

def image_split(job):
 image=base.checked_image(job['path']);count=int(job.get('count',4))
 defaults={2:(2,1),4:(2,2),8:(4,2),16:(4,4)}
 if count not in defaults:raise ValueError('invalidRequest')
 cols,rows=defaults[count];cols=int(job.get('columns',cols));rows=int(job.get('rows',rows))
 if cols*rows!=count:raise ValueError('invalidRequest')
 def cuts(key,n,length):
  v=job.get(key,[i/n for i in range(1,n)])
  if len(v)!=n-1 or v!=sorted(set(v)) or any(not 0<float(x)<1 for x in v):raise ValueError('invalidRequest')
  out=[0]+[round(float(x)*length) for x in v]+[length]
  if any(b<=a for a,b in zip(out,out[1:])):raise ValueError('invalidRequest')
  return out
 xs=cuts('xCuts',cols,image.width);ys=cuts('yCuts',rows,image.height);files=[]
 for r in range(rows):
  for c in range(cols):files.append(image_save(image.crop((xs[c],ys[r],xs[c+1],ys[r+1])),job,f'{Path(job["path"]).stem}_{r+1}_{c+1}'))
 if job.get('zip',True):files.append(make_zip(files,job,'split'))
 return base.result(files,{'columns':cols,'rows':rows})

def stroke_mask(size,job):
 mask=Image.new('L',size);d=ImageDraw.Draw(mask)
 for r in job.get('rectangles',[]):
  x,y,w,h=r;d.rectangle((x,y,x+w,y+h),fill=255)
 for s in job.get('strokes',[]):
  radius=int(bounded(s.get('radius'),10,1,1000));pts=[tuple(p) for p in s.get('points',[])]
  if len(pts)>10000:raise ValueError('invalidRequest')
  if len(pts)>1:d.line(pts,fill=255,width=radius*2,joint='curve')
  for x,y in pts:d.ellipse((x-radius,y-radius,x+radius,y+radius),fill=255)
 return mask

def image_retouch(job):
 import cv2,numpy as np
 files=[]
 for p in job.get('inputs',[]):
  image=base.checked_image(p);mask=stroke_mask(image.size,job)
  if not mask.getbbox():raise ValueError('inputMissing')
  rgb=np.array(image.convert('RGB'));out=cv2.inpaint(rgb,np.array(mask),3,cv2.INPAINT_TELEA)
  result=Image.fromarray(out).convert('RGBA');result.putalpha(image.getchannel('A'));files.append(image_save(result,job,Path(p).stem+'_retouched'))
 return base.result(files)

def guided_cutout(image,job):
 """User foreground/background marks seed a bounded-resolution GrabCut mask.
 Color models follow the marked subject, instead of merely erasing brush pixels.
 The final mask is feathered at the original resolution and preserves source alpha.
 """
 import cv2,numpy as np
 marks=job.get('marks',[])
 if not isinstance(marks,list) or len(marks)>300:raise ValueError('invalidRequest')
 if not any(s.get('kind')=='foreground' and s.get('points') for s in marks):raise ValueError('inputMissing')
 ratio=min(1,1400/max(image.size));w=max(2,round(image.width*ratio));h=max(2,round(image.height*ratio))
 if min(image.size)<4:raise ValueError('invalidRequest')
 rgb=np.array(image.convert('RGB').resize((w,h),Image.Resampling.LANCZOS))
 mask=np.full((h,w),cv2.GC_PR_BGD,dtype=np.uint8)
 foreground=Image.new('L',(w,h));background=Image.new('L',(w,h));total=0
 for mark in marks:
  kind=mark.get('kind');points=mark.get('points',[])
  if kind not in ('foreground','background') or not isinstance(points,list):raise ValueError('invalidRequest')
  total+=len(points)
  if total>30000:raise ValueError('invalidRequest')
  pts=[(round(bounded(p[0],0,0,image.width)*ratio),round(bounded(p[1],0,0,image.height)*ratio)) for p in points]
  radius=max(1,round(bounded(mark.get('radius'),12,1,1000)*ratio));d=ImageDraw.Draw(foreground if kind=='foreground' else background)
  if len(pts)>1:d.line(pts,fill=255,width=radius*2,joint='curve')
  for x,y in pts:d.ellipse((x-radius,y-radius,x+radius,y+radius),fill=255)
 fg=np.array(foreground)>0;bg=np.array(background)>0
 ys,xs=np.where(fg)
 if not len(xs):raise ValueError('inputMissing')
 # A broad probable foreground region allows the cut to grow beyond the brush.
 pad=max(12,round(min(w,h)*.12));left=max(1,int(xs.min())-pad);top=max(1,int(ys.min())-pad);right=min(w-1,int(xs.max())+pad+1);bottom=min(h-1,int(ys.max())+pad+1)
 mask[top:bottom,left:right]=cv2.GC_PR_FGD
 edge=max(1,round(min(w,h)*.006));mask[:edge,:]=cv2.GC_BGD;mask[-edge:,:]=cv2.GC_BGD;mask[:,:edge]=cv2.GC_BGD;mask[:,-edge:]=cv2.GC_BGD
 mask[fg]=cv2.GC_FGD;mask[bg]=cv2.GC_BGD
 if not np.any((mask==cv2.GC_BGD)|(mask==cv2.GC_PR_BGD)):raise ValueError('invalidRequest')
 cv2.setRNGSeed(173)
 cv2.grabCut(rgb,mask,None,np.zeros((1,65),np.float64),np.zeros((1,65),np.float64),5,cv2.GC_INIT_WITH_MASK)
 selected=np.where((mask==cv2.GC_FGD)|(mask==cv2.GC_PR_FGD),255,0).astype('uint8')
 selected[fg & ~bg]=255;selected[bg]=0
 # Background lettering/objects with the same color must not become stray islands.
 # Keep every connected subject the user actually marked, including multiple objects.
 _,components=cv2.connectedComponents(selected,connectivity=8)
 keep=np.unique(components[fg & ~bg]);keep=keep[keep!=0]
 selected=np.where(np.isin(components,keep),255,0).astype('uint8')
 alpha=Image.fromarray(selected).resize(image.size,Image.Resampling.LANCZOS)
 feather=bounded(job.get('feather'),1,0,8)
 if feather:alpha=alpha.filter(ImageFilter.GaussianBlur(feather))
 from PIL import ImageChops
 out=image.copy();out.putalpha(ImageChops.multiply(alpha,image.getchannel('A')))
 if job.get('trim',True):
  box=out.getchannel('A').getbbox()
  if box:out=out.crop(box)
 return out

def image_background(job):
 inputs=job.get('inputs',[])
 if not inputs:raise ValueError('inputMissing')
 image=base.checked_image(inputs[0])
 if job.get('segmentation')=='ai':
  from subject_selection import automatic_cutout,subject_alpha
  if job.get('maskOnly') is True:
   alpha=subject_alpha(image);image=Image.new('RGBA',image.size,'white');image.putalpha(alpha)
  else:image=automatic_cutout(image)
  p=image_save(image,{**job,'format':'png'},Path(inputs[0]).stem+'_ai_subject');return base.result([p])
 if job.get('segmentation')=='guided':
  image=guided_cutout(image,job)
  p=image_save(image,{**job,'format':'png'},Path(inputs[0]).stem+'_cutout');return base.result([p])
 mask=Image.new('L',image.size,255);originalAlpha=image.getchannel('A')
 for s in job.get('strokes',[]):
  sub=stroke_mask(image.size,{'strokes':[s]})
  mask.paste(255 if s.get('restore') else 0,(0,0),sub)
 from PIL import ImageChops
 image.putalpha(ImageChops.multiply(mask,originalAlpha));kind=job.get('background','transparent')
 if kind!='transparent':
  if kind=='image':
   index=int(job.get('backgroundInput',1))
   if not 0<=index<len(inputs):raise ValueError('inputMissing')
   bg=ImageOps.fit(base.checked_image(inputs[index]),image.size,Image.Resampling.LANCZOS)
  elif kind=='solid':bg=Image.new('RGBA',image.size,job.get('color','#ffffff'))
  elif kind=='gradient':
   a=ImageColor.getrgb(job.get('color','#ffffff'));b=ImageColor.getrgb(job.get('color2','#dbeafe'));bg=Image.new('RGBA',image.size);d=ImageDraw.Draw(bg)
   for y in range(image.height):t=y/max(1,image.height-1);d.line((0,y,image.width,y),fill=tuple(round(a[i]*(1-t)+b[i]*t) for i in range(3))+(255,))
  else:raise ValueError('invalidRequest')
  bg.alpha_composite(image);image=bg
 p=image_save(image,{**job,'format':job.get('format','png')},Path(inputs[0]).stem+'_background');return base.result([p])

def image_mosaic(job):
 import numpy as np
 image=base.checked_image(job['path']);regions=list(job.get('regions',[]))
 if job.get('faces'):raise ValueError('unsupported')
 if not regions:raise ValueError('inputMissing')
 for r in regions:
  x=int(bounded(r.get('x'),0,0,image.width));y=int(bounded(r.get('y'),0,0,image.height));w=int(bounded(r.get('width'),1,1,image.width));h=int(bounded(r.get('height'),1,1,image.height));box=(x,y,min(image.width,x+w),min(image.height,y+h))
  if box[2]<=x or box[3]<=y:continue
  part=image.crop(box);strength=int(bounded(r.get('strength'),12,1,100));mode=r.get('mode','pixel')
  if mode=='blur':out=part.filter(ImageFilter.GaussianBlur(strength))
  else:
   reduced=part.resize((max(1,part.width//strength),max(1,part.height//strength)),Image.Resampling.BOX)
   if mode=='random':
    a=np.array(reduced);rng=np.random.default_rng(0);order=rng.permutation(a.shape[0]*a.shape[1]);a=a.reshape(-1,4)[order].reshape(a.shape);reduced=Image.fromarray(a)
   elif mode!='pixel':raise ValueError('invalidRequest')
   out=reduced.resize(part.size,Image.Resampling.NEAREST)
  mask=Image.new('L',part.size,255)
  if r.get('shape')=='ellipse':mask=Image.new('L',part.size);ImageDraw.Draw(mask).ellipse((0,0,part.width-1,part.height-1),fill=255)
  image.paste(out,(x,y),mask)
 return base.result([image_save(image,job,Path(job['path']).stem+'_mosaic')],{'regions':regions})

def signature_image(job):
 inputs=job.get('inputs',[]);index=int(job.get('signatureInput',1));w=int(bounded(job.get('width'),160,1,5000));h=int(bounded(job.get('height'),60,1,5000))
 if 0<=index<len(inputs):return ImageOps.contain(base.checked_image(inputs[index]),(w,h),Image.Resampling.LANCZOS)
 text=str(job.get('text',''))
 if not text:raise ValueError('inputMissing')
 image=Image.new('RGBA',(w,h));d=ImageDraw.Draw(image);f=font(max(10,int(h*.65)));d.text((2,2),text[:100],font=f,fill=job.get('color','#111827'));return image

def signature_apply(job):
 p=Path(job['path']);placements=job.get('placements') or [job]
 if not isinstance(placements,list) or len(placements)>100:raise ValueError('invalidRequest')
 def signatures():
  for placement in placements:
   item={**job,**placement};sig=signature_image(item);opacity=bounded(item.get('opacity'),1,0,1);sig.putalpha(sig.getchannel('A').point(lambda a:round(a*opacity)));rotation=bounded(item.get('rotation'),0,-3600,3600)
   if rotation:sig=sig.rotate(-rotation,expand=True,resample=Image.Resampling.BICUBIC)
   yield item,sig
 if job.get('overlay'):
  index=int(job.get('signatureInput',1));inputs=job.get('inputs',[])
  if not 0<=index<len(inputs):raise ValueError('inputMissing')
  overlay=base.checked_image(inputs[index])
  if p.suffix.lower()=='.pdf':
   with base.open_pdf(p) as doc:
    selected=list(range(doc.page_count)) if job.get('allPages') else base.pages(job.get('pages','1'),doc.page_count)
    for n in selected:
     page=doc[n];oriented=overlay.rotate(page.rotation,expand=True) if page.rotation else overlay;buffer=io.BytesIO();oriented.save(buffer,'PNG')
     page.insert_image(page.rect*page.derotation_matrix,stream=buffer.getvalue(),keep_proportion=False,overlay=True)
    return base.save_pdf(doc,job,p.stem+'_signed')
  if p.suffix.lower()=='.docx':return docx_signature(p,overlay,job)
  image=base.checked_image(p);image.alpha_composite(overlay.resize(image.size,Image.Resampling.LANCZOS));return base.result([image_save(image,job,p.stem+'_signed')])
 if p.suffix.lower()=='.pdf':
  with base.open_pdf(p) as doc:
   selected=list(range(doc.page_count)) if job.get('allPages') else base.pages(job.get('pages','1'),doc.page_count)
   for n in selected:
    page=doc[n];sx=page.rect.width/float(job.get('previewWidth',page.rect.width));sy=page.rect.height/float(job.get('previewHeight',page.rect.height))
    for item,sig in signatures():
     x=bounded(item.get('x'),20,0,30000)*sx;y=bounded(item.get('y'),20,0,30000)*sy;buffer=io.BytesIO();sig.save(buffer,'PNG');rect=base.fitz.Rect(x,y,x+sig.width*sx,y+sig.height*sy)
     if rect.is_empty or not rect.intersects(page.rect):raise ValueError('invalidRequest')
     page.insert_image(rect,stream=buffer.getvalue(),overlay=True)
   return base.save_pdf(doc,job,p.stem+'_signed')
 if p.suffix.lower()=='.docx':
  if len(placements)>1:raise ValueError('unsupported')
  item,sig=next(signatures());return docx_signature(p,sig,item)
 image=base.checked_image(p)
 for item,sig in signatures():image.alpha_composite(sig,(int(bounded(item.get('x'),20,0,30000)),int(bounded(item.get('y'),20,0,30000))))
 return base.result([image_save(image,job,p.stem+'_signed')])

def canvas_export(job):
 w=int(bounded(job.get('width'),1920,1,30000));h=int(bounded(job.get('height'),1080,1,30000));pages=job.get('pages',[{'layers':[]}]);fmt=job.get('format','png');inputs=job.get('inputs',[])
 if w*h>base.Image.MAX_IMAGE_PIXELS or not 1<=len(pages)<=100 or w*h*len(pages)>160_000_000:raise ValueError('fileTooLarge')
 images=[layers(Image.new('RGBA',(w,h),job.get('background','#ffffff')),p.get('layers',[]),inputs) for p in pages]
 if job.get('join'):
  if w*h*len(images)>base.Image.MAX_IMAGE_PIXELS:raise ValueError('fileTooLarge')
  joined=Image.new('RGBA',(w,h*len(images)));[joined.alpha_composite(im,(0,i*h)) for i,im in enumerate(images)];images=[joined]
 if fmt=='pdf':
  with base.fitz.open() as doc:
   for im in images:
    stream=io.BytesIO();im.save(stream,'PNG');page=doc.new_page(width=im.width,height=im.height);page.insert_image(page.rect,stream=stream.getvalue())
   return base.save_pdf(doc,job,'canvas')
 if fmt=='gif':
  p=base.write_atomic(job['output_dir'],'canvas','.gif',lambda p:images[0].convert('RGB').save(p,'GIF',save_all=True,append_images=[x.convert('RGB') for x in images[1:]],duration=int(bounded(job.get('duration'),500,20,10000)),loop=0));return base.result([p])
 return base.result([image_save(im,job,f'canvas_{i+1}') for i,im in enumerate(images)])

def pdf_split(job):
 files=[]
 with base.open_pdf(job['path']) as doc:
  mode=job.get('mode','pages');selected=base.pages(job.get('pages',''),doc.page_count)
  n=int(bounded(job.get('groupSize'),1,1,10000)) if mode=='groups' else len(selected) if mode=='selected' else 1
  for start in range(0,len(selected),n):
   with base.fitz.open() as out:
    for p in selected[start:start+n]:out.insert_pdf(doc,from_page=p,to_page=p)
    files.extend(base.save_pdf(out,job,f'{Path(job["path"]).stem}_{start+1}')['files'])
 if job.get('zip',True):files.append(make_zip(files,job,'pdf_split'))
 return base.result(files)

XML='<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
def write_parts(path,parts):
 with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
  for name,data in parts.items():z.writestr(name,data)
def pdf_docx(job):
 with base.open_pdf(job['path']) as doc:texts=[p.get_text() for p in doc]
 if not any(t.strip() for t in texts):raise ValueError('textPdfRequired')
 body=''.join(''.join('<w:p><w:r><w:t xml:space="preserve">'+html.escape(line)+'</w:t></w:r></w:p>' for line in text.splitlines())+('<w:p><w:r><w:br w:type="page"/></w:r></w:p>' if i<len(texts)-1 else '') for i,text in enumerate(texts))
 parts={'[Content_Types].xml':XML+'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>','_rels/.rels':XML+'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>','word/document.xml':XML+'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+body+'<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:body></w:document>'}
 return base.result([base.write_atomic(job['output_dir'],Path(job['path']).stem+'_text','.docx',lambda p:write_parts(p,parts))],{'mode':'textOnly','pages':len(texts)})

def pdf_xlsx(job):
 tables=[]
 with base.open_pdf(job['path']) as doc:
  for page in doc:
   if not page.get_text().strip():continue
   found=page.find_tables()
   for t in found.tables:tables.append(t.extract())
 if not tables:raise ValueError('tableNotFound')
 ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main';rels='http://schemas.openxmlformats.org/package/2006/relationships'
 parts={'_rels/.rels':XML+f'<Relationships xmlns="{rels}"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'};sheets=[];relationships=[];types=[]
 for i,table in enumerate(tables,1):
  rows=[]
  for rn,row in enumerate(table,1):
   cells=[]
   for cn,value in enumerate(row):
    c='';n=cn+1
    while n:n,r=divmod(n-1,26);c=chr(65+r)+c
    cells.append(f'<c r="{c}{rn}" t="inlineStr"><is><t xml:space="preserve">{html.escape(str(value or ""))}</t></is></c>')
   rows.append(f'<row r="{rn}">'+''.join(cells)+'</row>')
  parts[f'xl/worksheets/sheet{i}.xml']=XML+f'<worksheet xmlns="{ns}"><sheetData>'+''.join(rows)+'</sheetData></worksheet>';sheets.append(f'<sheet name="Table {i}" sheetId="{i}" r:id="rId{i}"/>');relationships.append(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>');types.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
 parts['xl/workbook.xml']=XML+f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(sheets)+'</sheets></workbook>';parts['xl/_rels/workbook.xml.rels']=XML+f'<Relationships xmlns="{rels}">'+''.join(relationships)+'</Relationships>';parts['[Content_Types].xml']=XML+'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+''.join(types)+'</Types>'
 return base.result([base.write_atomic(job['output_dir'],Path(job['path']).stem+'_tables','.xlsx',lambda p:write_parts(p,parts))],{'tables':len(tables)})

def pdf_pptx(job):
 import office_export
 return office_export.pdf_pptx(job)
def docx_signature(path,sig,job):
 import office_export
 return office_export.docx_signature(path,sig,job)

def code_generate(job):
 import qrcode
 kind=job.get('kind','qr');fmt=job.get('format','png')
 if kind!='qr':
  r=base.code_generate({**job,'format':'png'})
  if fmt=='png':return r
  if fmt=='jpg':return base.result([image_save(base.checked_image(r['files'][0]),job,kind)],r['data'])
  if fmt=='svg':
   from barcode.writer import SVGWriter
   text=r['data']['text'];code=base.barcode.get(kind,text,writer=SVGWriter(),options={'add_checksum':False} if kind=='code39' else None);data=code.render();return base.result([base.write_atomic(job['output_dir'],kind,'.svg',lambda p:p.write_bytes(data))],r['data'])
  raise ValueError('unsupported')
 text=str(job.get('text',''))
 typ=job.get('qr_type','text')
 if typ=='wifi':
  security=job.get('security','WPA');ssid=str(job.get('ssid',''))
  if security not in ('WPA','WEP','nopass') or not ssid:raise ValueError('invalidRequest')
  text=f'WIFI:T:{security};S:{base.wifi_escape(ssid)};'+(f'P:{base.wifi_escape(job.get("password",""))};' if security!='nopass' else '')+';'
 elif typ=='url':
  from urllib.parse import urlparse
  u=urlparse(text)
  if u.scheme not in ('http','https') or not u.netloc:raise ValueError('invalidRequest')
 if not text:raise ValueError('inputMissing')
 qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H,border=4);qr.add_data(text);qr.make(fit=True)
 size=int(bounded(job.get('size'),512,64,8192));fg=job.get('foreground','#111827');bg=job.get('background','#ffffff');ImageColor.getrgb(fg);ImageColor.getrgb(bg);style=job.get('style','square');matrix=qr.get_matrix();n=len(matrix)
 from qr_logo import artwork,verify_scan,verify_export,verify_svg,logo_candidates
 has_logo=job.get('logoInput') is not None;applied=None;verified=False
 for percent in (logo_candidates(n,size) if has_logo else [30]):
  image,svg,has_logo=artwork(matrix,size,fg,bg,style,job,logo_percent=percent)
  verified=verify_scan(image,text) and verify_svg(svg,text)
  if verified and fmt=='jpg':
   encoded=io.BytesIO();flat=Image.new('RGB',image.size,job.get('backgroundColor','#ffffff'));flat.paste(image,mask=image.getchannel('A'));flat.save(encoded,'JPEG',quality=int(bounded(job.get('quality'),90,1,100)));encoded.seek(0)
   with Image.open(encoded) as saved:verified=verify_scan(saved,text)
  if verified or not has_logo:
   applied=percent if has_logo else None;break
  image.close()
 # Start at the largest permitted logo and automatically reduce it until both
 # complete export formats decode to exactly the untouched original content.
 if has_logo and not verified:raise ValueError('qrScanFailed')
 if fmt=='svg':
  p=base.write_atomic(job['output_dir'],'qr','.svg',lambda p:p.write_text(svg,encoding='utf-8'))
 else:
  p=image_save(image,job,'qr')
 verified=verify_export(p,text)
 if has_logo and not verified:
  p.unlink(missing_ok=True)
  raise ValueError('qrScanFailed')
 return base.result([p],{'text':text,'kind':kind,'errorCorrection':'H','logoIncluded':has_logo,'scanVerified':verified,'appliedLogoPercent':applied,'logoPaddingPx':4 if has_logo else 0})

def video_gif(job,progress=lambda _:None):
 from ffmpeg_runtime import executable
 paths=job.get('inputs',[])
 if not paths:raise ValueError('inputMissing')
 # Force a single-file container demuxer. Automatic probing also accepts HLS,
 # concat and other playlists, which may read unselected files or fetch URLs.
 source=Path(paths[0])
 with source.open('rb') as stream:head=stream.read(4096)
 suffix=source.suffix.lower();demuxer=None
 if suffix in ('.mp4','.mov','.m4v') and len(head)>=12 and head[4:8] in (b'ftyp',b'moov',b'mdat',b'wide',b'free'):demuxer='mov'
 elif suffix in ('.mkv','.webm') and head.startswith(b'\x1a\x45\xdf\xa3'):demuxer='matroska'
 elif suffix=='.avi' and head[:4]==b'RIFF' and head[8:12]==b'AVI ':demuxer='avi'
 elif suffix in ('.ogg','.ogv') and head.startswith(b'OggS'):demuxer='ogg'
 elif suffix=='.gif' and head[:6] in (b'GIF87a',b'GIF89a'):demuxer='gif'
 elif suffix=='.flv' and head.startswith(b'FLV'):demuxer='flv'
 elif suffix=='.ts' and len(head)>376 and all(head[i]==0x47 for i in (0,188,376)):demuxer='mpegts'
 if not demuxer:raise ValueError('unsupported')
 ffmpeg=executable();ranges=job.get('ranges',[{'start':0,'end':5}]);w=int(bounded(job.get('width'),720,64,1920));fps=int(bounded(job.get('fps'),12,1,30));files=[]
 if not 1<=len(ranges)<=30:raise ValueError('invalidRequest')
 for n,r in enumerate(ranges):
  start=bounded(r.get('start'),0,0,86400);end=bounded(r.get('end'),start+5,start+.02,start+120)
  # Explicit argv only; filename is never interpreted by a shell. Bounded resolution/frame count/time.
  aspect=job.get('aspect','original');filters=[]
  if aspect in ('16:9','9:16','1:1'):
   a,b=map(int,aspect.split(':'));filters.append(f'crop=w=min(iw\\,ih*{a}/{b}):h=min(ih\\,iw*{b}/{a})')
  filters += [f'fps={fps}',f'scale={w}:2160:force_original_aspect_ratio=decrease:flags=lanczos']
  watermark=str(job.get('watermark',''))[:100];mark=None
  if watermark:
   mark=Path(job['output_dir'])/('.watermark-'+str(uuid.uuid4())+'.png');im=Image.new('RGBA',(w,50));ImageDraw.Draw(im).text((10,10),watermark,font=font(22),fill='white',stroke_width=1,stroke_fill='black');im.save(mark,'PNG');im.close()
  filt=('[0:v]'+','.join(filters)+'[v];[v][1:v]overlay=0:0:shortest=1' if mark else ','.join(filters))+',split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a'
  def write(p):
   command=[ffmpeg,'-hide_banner','-loglevel','error','-nostdin','-ss',str(start),'-t',str(end-start),'-protocol_whitelist','file','-f',demuxer]
   if demuxer=='mov':command+=['-enable_drefs','0','-use_absolute_path','0']
   command+=['-i',str(source.resolve())]
   if mark:command+=['-loop','1','-i',str(mark)]
   command+=['-an','-filter_complex',filt,'-t',str(end-start),'-loop','0','-y',str(p)]
   subprocess.run(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=180,check=True)
  try:p=base.write_atomic(job['output_dir'],Path(paths[0]).stem+f'_{n+1}','.gif',write)
  finally:
   if mark:mark.unlink(missing_ok=True)
  files.append(p);progress(10+85*(n+1)/len(ranges))
 if job.get('zip') and len(files)>1:files.append(make_zip(files,job,'gifs'))
 return base.result(files)

def web_stitch(job,progress=lambda _:None):
 tiles=job.get('tiles',[]);dpr=bounded(job.get('dpr'),1,.25,4);w=round(bounded(job.get('width'),0,1,30000)*dpr);h=round(bounded(job.get('height'),0,1,500000)*dpr)
 if not tiles or len(tiles)>200:raise ValueError('inputMissing')
 # Stream every segment: never retain a full long page's pixels in a list.
 maxh=min(int(bounded(job.get('maxHeight'),12000,500,30000)),max(1,32_000_000//w));split=bool(job.get('split')) or w*h>32_000_000;step=maxh if split else h
 fmt=job.get('format','png');files=[];count=0;pdf=base.fitz.open() if fmt=='pdf' else None
 try:
  for sy in range(0,h,step):
   segment=Image.new('RGBA',(w,min(step,h-sy)),'white')
   for t in tiles:
    x=round(bounded(t.get('x'),0,0,30000)*dpr);y=round(bounded(t.get('y'),0,0,500000)*dpr)
    cssw=bounded(t.get('viewportWidth'),job['width'],1,30000);cssh=bounded(t.get('viewportHeight'),1000,1,30000)
    capturew=bounded(t.get('captureWidth'),cssw,cssw,30000);captureh=bounded(t.get('captureHeight'),cssh,cssh,30000)
    clipx=round(bounded(t.get('clipLeft'),0,0,capturew-cssw)*dpr)
    expected=(round(capturew*dpr),round(captureh*dpr))
    if min(expected)<1 or expected[0]*expected[1]>32_000_000:raise ValueError('fileTooLarge')
    if y+round(cssh*dpr)<=sy or y>=sy+segment.height or x>=w:continue
    image=base.checked_image(t['path'])
    if image.size!=expected:
     resized=image.resize(expected,Image.Resampling.LANCZOS);image.close();image=resized
    content=(round(cssw*dpr),round(cssh*dpr))
    if image.size!=content or clipx:
     cropped=image.crop((clipx,0,clipx+content[0],content[1]));image.close();image=cropped
    top=max(sy,y);bottom=min(sy+segment.height,y+image.height,h)
    if bottom>top:segment.alpha_composite(image.crop((0,top-y,min(image.width,w-x),bottom-y)),(x,top-sy))
    image.close()
   count+=1
   if pdf is not None:
    stream=io.BytesIO();segment.save(stream,'PNG');page=pdf.new_page(width=w/dpr,height=segment.height/dpr);page.insert_image(page.rect,stream=stream.getvalue());stream.close()
   else:files.append(image_save(segment,job,'webpage'+(f'_{count}' if split else '')))
   segment.close();del segment;progress(20+60*min(h,sy+step)/h)
  if pdf is not None:return base.save_pdf(pdf,job,'webpage')
  if len(files)>1:files.append(make_zip(files,job,'webpage'))
  return base.result(files,{'width':w,'height':h,'segments':count})
 finally:
  if pdf is not None:pdf.close()

from PIL import ImageSequence
from video_editor import video_edit
OPS={f.__name__:f for f in [image_edit,image_split,image_background,image_retouch,image_mosaic,signature_apply,canvas_export,pdf_split,pdf_docx,pdf_pptx,pdf_xlsx,code_generate,video_gif,video_edit]}
def run(job,progress=lambda _:None):
 op=job.get('op',job.get('operation'))
 if op not in OPS:raise ValueError('unsupported')
 if op in ('video_gif','video_edit'):return OPS[op](job,progress)
 progress(20);result=OPS[op](job);progress(95);return result
