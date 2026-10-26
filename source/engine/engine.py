"""GalaxyControl local file tools. No network, OCR, AI, or shell commands."""
from __future__ import annotations
import argparse, json, os, re, sys, math, uuid, io, platform
from pathlib import Path
from urllib.parse import urlparse

_here = Path(__file__).resolve().parent
_arch = {'aarch64':'arm64','arm64':'arm64','x86_64':'x86_64','AMD64':'win64'}.get(platform.machine(), 'win64')
_dev = _here / 'deps' / _arch
if _dev.is_dir(): sys.path.insert(0, str(_dev))
from PIL import Image, ImageOps, ImageColor
from lazy_dependencies import DeferredModule,barcode_image_writer as ImageWriter
fitz=DeferredModule('pymupdf')
qrcode=DeferredModule('qrcode')
barcode=DeferredModule('barcode')
zxingcpp=DeferredModule('zxingcpp')
Image.MAX_IMAGE_PIXELS = 80_000_000


def checked_image(path):
    with Image.open(path) as src:
        if src.format not in ('JPEG','PNG','WEBP','BMP','TIFF'):
            raise ValueError('지원하지 않는 사진 형식입니다. JPG, PNG, WebP를 사용하세요.')
        if getattr(src,'n_frames',1) != 1: raise ValueError('움직이는 이미지와 여러 프레임 이미지는 이번 버전에서 제외합니다.')
        if src.width * src.height > Image.MAX_IMAGE_PIXELS: raise ValueError('이미지 크기가 너무 큽니다.')
        src.load()
        return ImageOps.exif_transpose(src).convert('RGBA')


def reserve(directory, stem, suffix):
    directory = Path(directory).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', stem).strip(' .')[:150] or 'result'
    for n in range(1,100000):
        path = directory / (stem + ('' if n == 1 else f'_{n}') + suffix)
        try:
            fd = os.open(path, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
            os.close(fd)
            return path
        except FileExistsError: continue
    raise ValueError('새로운 파일 이름을 만들 수 없습니다.')


def publish_exclusive(source,destination):
    """Atomic publication which never replaces an existing destination."""
    import ctypes,errno
    if os.name=='nt':
        kernel=ctypes.WinDLL('kernel32',use_last_error=True);move=kernel.MoveFileExW;move.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint];move.restype=ctypes.c_int
        if not move(str(source),str(destination),0):
            code=ctypes.get_last_error()
            if code in (80,183):raise FileExistsError(errno.EEXIST,'destination exists',str(destination))
            raise OSError(code,'exclusive publish failed')
    elif sys.platform=='darwin':
        libc=ctypes.CDLL(None,use_errno=True);rename=libc.renamex_np;rename.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_uint];rename.restype=ctypes.c_int
        if rename(os.fsencode(source),os.fsencode(destination),4)!=0:
            code=ctypes.get_errno()
            if code==errno.EEXIST:raise FileExistsError(code,'destination exists',str(destination))
            raise OSError(code,'exclusive publish failed')
    else:
        os.link(source,destination);os.unlink(source)


def write_atomic(directory, stem, suffix, writer):
    directory=Path(directory).expanduser().resolve();directory.mkdir(parents=True,exist_ok=True)
    stem=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',stem).strip(' .')[:150] or 'result'
    tmp=directory/('.'+stem+'-'+uuid.uuid4().hex+'.tmp'+suffix)
    try:
        writer(tmp)
        if not tmp.is_file() or tmp.is_symlink() or tmp.stat().st_size==0:raise ValueError('결과 파일이 비어 있습니다.')
        os.chmod(tmp,0o600)
        for n in range(1,100000):
            path=directory/(stem+('' if n==1 else f'_{n}')+suffix)
            try:
                publish_exclusive(tmp,path)
                return path
            except FileExistsError:continue
        raise ValueError('새로운 파일 이름을 만들 수 없습니다.')
    finally:tmp.unlink(missing_ok=True)


def result(files=(), data=None, message='처리를 완료했습니다.', success=True):
    names=[str(Path(x).resolve()) for x in files]
    return dict(success=success,ok=success,message=message,files=names,outputs=names,data=data or {})


def integer(job,key,default,minimum,maximum):
    value=int(job.get(key,default))
    if not minimum<=value<=maximum: raise ValueError(f'{key} 값이 범위를 벗어났습니다.')
    return value


def image_export(job):
    """Publish a validated client-rendered still image without changing its bytes."""
    import shutil
    inputs=job.get('inputs',job.get('paths',[]))
    if len(inputs)!=1:raise ValueError('사진 한 개를 저장하세요.')
    source=Path(inputs[0])
    with Image.open(source) as image:
        fmt=image.format
        if fmt not in ('PNG','JPEG','WEBP'):raise ValueError('지원하지 않는 이미지입니다.')
        if image.width*image.height>Image.MAX_IMAGE_PIXELS:raise ValueError('이미지가 너무 큽니다.')
        image.verify()
    suffix={'PNG':'.png','JPEG':'.jpg','WEBP':'.webp'}[fmt]
    destination=write_atomic(job['output_dir'],source.stem,suffix,lambda p:shutil.copyfile(source,p))
    return result([destination])


def image_process(job):
    inputs=job.get('inputs',job.get('paths',[]))
    if not inputs:raise ValueError('사진 파일을 선택하세요.')
    fmt=str(job.get('format','jpg')).lower().replace('jpeg','jpg')
    if fmt not in ('jpg','png','webp'):raise ValueError('JPG, PNG, WebP 중에서 선택하세요.')
    quality=integer(job,'quality',85,1,100);width=integer(job,'width',0,0,30000);height=integer(job,'height',0,0,30000)
    percent=integer(job,'scale_percent',100,1,400)
    no_upscale=bool(job.get('no_upscale',True));keep=bool(job.get('keep_ratio',True))
    background=ImageColor.getrgb(job.get('background','#FFFFFF'))
    items=[];files=[]
    for value in inputs:
        item={'input':str(value),'success':False}
        try:
            source=Path(value);before=source.stat().st_size;image=checked_image(source)
            ow,oh=image.size
            if width or height:
                if keep:
                    ratio=min(([width/ow] if width else [])+([height/oh] if height else []))
                    if no_upscale:ratio=min(1.0,ratio)
                    size=(max(1,round(ow*ratio)),max(1,round(oh*ratio)))
                else:
                    size=(width or ow,height or oh)
                    if no_upscale:size=(min(ow,size[0]),min(oh,size[1]))
            else:
                ratio=percent/100
                if no_upscale:ratio=min(1,ratio)
                size=(max(1,round(ow*ratio)),max(1,round(oh*ratio)))
            if size[0]*size[1]>Image.MAX_IMAGE_PIXELS:raise ValueError('결과 이미지 크기가 너무 큽니다.')
            if size!=image.size:image=image.resize(size,Image.Resampling.LANCZOS)
            if fmt=='jpg':
                flat=Image.new('RGB',image.size,background);flat.paste(image,mask=image.getchannel('A'));image=flat
            options={'jpg':{'quality':quality,'optimize':True,'progressive':True},'png':{'optimize':True,'compress_level':9},'webp':{'quality':quality,'method':5}}[fmt]
            def save(p):image.save(p,format={'jpg':'JPEG','png':'PNG','webp':'WEBP'}[fmt],**options)
            path=write_atomic(job['output_dir'],source.stem+'_converted','.'+fmt,save)
            with Image.open(path) as verify:verify.load();assert verify.size==size
            after=path.stat().st_size
            item.update(success=True,output=str(path),input_bytes=before,output_bytes=after,saved_bytes=before-after,reduction_percent=(before-after)*100/before if before else 0,width=size[0],height=size[1])
            files.append(path)
        except Exception as error:item['error']=str(error)
        items.append(item)
    count=sum(x['success'] for x in items)
    return result(files,{'results':items},f'{len(items)}개 중 {count}개 처리 완료. 결과 용량은 실제 파일 기준입니다.',count==len(items))


def open_pdf(path):
    doc=fitz.open(path)
    if not doc.is_pdf:doc.close();raise ValueError('PDF 파일을 선택하세요.')
    if doc.needs_pass:doc.close();raise ValueError('비밀번호가 설정된 PDF는 이번 버전에서 처리하지 않습니다.')
    return doc


def pages(text,count):
    if not str(text).strip():return list(range(count))
    values=[]
    for part in re.split(r'[\s,;]+',str(text).strip()):
        if not part:continue
        match=re.fullmatch(r'(\d+)(?:-(\d+))?',part)
        if not match:raise ValueError('페이지는 1-3,5,8-12 형식으로 입력하세요.')
        first=int(match[1]);last=int(match[2] or first)
        if first<1 or last>count or first>last:raise ValueError(f'페이지 범위를 확인하세요. 이 문서는 {count}쪽입니다.')
        for value in range(first-1,last):
            if value not in values:values.append(value)
    if not values:raise ValueError('한 페이지 이상 선택하세요.')
    return values


def save_pdf(doc,job,stem):
    if doc.page_count==0:raise ValueError('빈 PDF는 저장할 수 없습니다.')
    path=write_atomic(job['output_dir'],stem,'.pdf',lambda p:doc.save(p,garbage=3,deflate=True))
    with fitz.open(path) as verify:
        if verify.page_count!=doc.page_count:raise ValueError('PDF 페이지 수 검증에 실패했습니다.')
    return result([path],{'page_count':doc.page_count})


def pdf_merge(job):
    paths=job.get('paths',job.get('inputs',[]))
    if not paths:raise ValueError('PDF 파일을 선택하세요.')
    with fitz.open() as out:
        for path in paths:
            with open_pdf(path) as doc:out.insert_pdf(doc)
        return save_pdf(out,job,'merged')


def pdf_extract(job):
    with open_pdf(job['path']) as doc,fitz.open() as out:
        selected=pages(job.get('pages',''),doc.page_count)
        for n in selected:out.insert_pdf(doc,from_page=n,to_page=n)
        return save_pdf(out,job,Path(job['path']).stem+'_selected')


def pdf_manage(job):
    with open_pdf(job['path']) as doc,fitz.open() as out:
        order=job.get('page_order',list(range(1,doc.page_count+1)))
        if not order or len(set(order))!=len(order):raise ValueError('페이지 순서에 중복이 있거나 모든 페이지가 삭제되었습니다.')
        rotations=job.get('rotations',{})
        for n in order:
            n=int(n)
            if not 1<=n<=doc.page_count:raise ValueError('페이지 번호를 확인하세요.')
            out.insert_pdf(doc,from_page=n-1,to_page=n-1)
            rotation=int(rotations.get(str(n),0))
            if rotation%90:raise ValueError('회전은 90도 단위로 선택하세요.')
            out[-1].set_rotation((doc[n-1].rotation+rotation)%360)
        return save_pdf(out,job,Path(job['path']).stem+'_pages')


def images_pdf(job):
    paths=job.get('paths',job.get('inputs',[]))
    if not paths:raise ValueError('사진 파일을 선택하세요.')
    margin=float(job.get('margin_mm',10))*72/25.4
    if not 0<=margin<=100*72/25.4:raise ValueError('여백을 확인하세요.')
    with fitz.open() as out:
        for path in paths:
            image=checked_image(path);buff=io.BytesIO();image.save(buff,'PNG')
            if job.get('page_size','a4')=='a4':w,h=fitz.paper_size('a4')
            elif job.get('page_size')=='image':w,h=image.width*72/96+margin*2,image.height*72/96+margin*2
            else:raise ValueError('페이지 크기를 선택하세요.')
            if job.get('orientation','portrait')=='landscape' and w<h:w,h=h,w
            elif job.get('orientation','portrait')=='portrait' and w>h and job.get('page_size')=='a4':w,h=h,w
            if margin*2>=min(w,h):raise ValueError('페이지보다 여백이 큽니다.')
            page=out.new_page(width=w,height=h)
            page.insert_image(fitz.Rect(margin,margin,w-margin,h-margin),stream=buff.getvalue(),keep_proportion=True)
        return save_pdf(out,job,'images')


def pdf_render(job):
    fmt=job.get('format','png')
    if fmt not in ('png','jpg','jpeg'):raise ValueError('PNG 또는 JPG를 선택하세요.')
    dpi=integer(job,'dpi',150,36,600);files=[];info=[]
    with open_pdf(job['path']) as doc:
        selected=pages(job.get('pages',''),doc.page_count)
        for n in selected:
            page=doc[n];estimate=page.rect.width*page.rect.height*(dpi/72)**2
            if estimate>80_000_000:raise ValueError('선택한 해상도가 너무 큽니다.')
            pix=page.get_pixmap(dpi=dpi,alpha=False)
            stem=Path(job['path']).stem+f'_page_{n+1:03d}'
            path=write_atomic(job['output_dir'],stem,'.png' if fmt=='png' else '.jpg',lambda p:pix.save(p))
            with Image.open(path) as check:check.load()
            files.append(path);info.append({'index':n+1,'image':str(path),'width':pix.width,'height':pix.height})
    return result(files,{'pages':info})


def pdf_info(job):
    with open_pdf(job['path']) as doc:
        return result(data={'page_count':doc.page_count,'pages':[{'index':n+1,'width':p.rect.width,'height':p.rect.height,'rotation':p.rotation} for n,p in enumerate(doc)]})


def pdf_annotate(job):
    with open_pdf(job['path']) as doc:
        number=integer(job,'page',1,1,doc.page_count);page=doc[number-1]
        overlay=checked_image(job['overlay_path'])
        # Canvas coordinates describe the displayed (rotated) page. Undo that
        # rotation before inserting so the saved PDF displays at the same position.
        if page.rotation:overlay=overlay.rotate(page.rotation,expand=True)
        buff=io.BytesIO();overlay.save(buff,'PNG')
        rect=page.rect*page.derotation_matrix
        page.insert_image(rect,stream=buff.getvalue(),keep_proportion=False,overlay=True)
        return save_pdf(doc,job,Path(job['path']).stem+'_annotated')


def wifi_escape(value):
    return ''.join('\\'+c if c in '\\;,:"' else c for c in str(value))


def checksum(digits):
    return str((-sum(int(n)*(3 if (len(digits)-i)%2 else 1) for i,n in enumerate(digits)))%10)


def code_generate(job):
    kind=job.get('kind','qr');text=str(job.get('text',''));fmt=kind
    if kind=='qr':
        typ=job.get('qr_type','text')
        if typ=='wifi':
            security=job.get('security','WPA')
            if security not in ('WPA','WEP','nopass'):raise ValueError('Wi-Fi 보안 방식을 선택하세요.')
            ssid=str(job.get('ssid',''))
            if not ssid:raise ValueError('Wi-Fi 이름을 입력하세요.')
            text=f'WIFI:T:{security};S:{wifi_escape(ssid)};'+(f'P:{wifi_escape(job.get("password",""))};' if security!='nopass' else '')+';'
        elif typ=='url':
            parsed=urlparse(text)
            if parsed.scheme not in ('http','https') or not parsed.netloc:raise ValueError('http:// 또는 https:// URL을 입력하세요.')
        if not text:raise ValueError('QR 내용이 비어 있습니다.')
        qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H,box_size=10,border=4)
        qr.add_data(text);qr.make(fit=True);image=qr.make_image(fill_color='black',back_color='white').convert('RGB')
    else:
        sizes={'ean13':(12,13),'ean8':(7,8),'upca':(11,12)}
        if kind in sizes:
            body,full=sizes[kind]
            if not text.isascii() or not text.isdigit() or len(text) not in (body,full):raise ValueError(f'{kind.upper()}는 숫자 {body}자리 또는 검증 숫자를 포함한 {full}자리여야 합니다.')
            check=checksum(text[:body])
            if len(text)==full and text[-1]!=check:raise ValueError('바코드 검증 숫자가 맞지 않습니다.')
            text=text[:body]+check
        elif kind=='code128':
            if not text or any(ord(c)<32 or ord(c)>126 for c in text):raise ValueError('Code 128은 영문·숫자·ASCII 기호를 입력하세요.')
        elif kind=='code39':
            # Code 39 uses uppercase ASCII and reserves * for its start/stop bars.
            # Its optional checksum is off so decoding returns the chosen identifier.
            allowed='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-. $/+%'
            if not text or not text.isascii() or len(text)>128 or any(character not in allowed for character in text.upper()):raise ValueError('Code 39는 영문·숫자와 - . 공백 $ / + %를 128자 이내로 입력하세요.')
            text=text.upper()
        else:raise ValueError('지원하지 않는 바코드 형식입니다.')
        code=barcode.get(kind,text,writer=ImageWriter(),options={'add_checksum':False} if kind=='code39' else None)
        text=code.get_fullcode()
        image=code.render({'module_width':0.35,'module_height':22,'quiet_zone':7,'font_size':11,'dpi':300}).convert('RGB')
    path=write_atomic(job['output_dir'],kind,'.png',lambda p:image.save(p,'PNG'))
    return result([path],{'text':text,'kind':kind},'코드 이미지를 만들었습니다.')


def code_read(job):
    image=checked_image(job['path']).convert('RGB')
    decoded=zxingcpp.read_barcodes(image,try_rotate=True,try_downscale=True,try_invert=True)
    found=[{'format':str(x.format),'text':x.text} for x in decoded if x.valid]
    return result(data={'results':found},message='코드를 읽었습니다.' if found else 'QR 코드를 인식할 수 없습니다.',success=bool(found))


OPERATIONS={f.__name__:f for f in [image_export,image_process,pdf_merge,pdf_extract,pdf_manage,images_pdf,pdf_render,pdf_info,pdf_annotate,code_generate,code_read]}

def run(job):
    try:
        operation=job.get('op')
        if operation not in OPERATIONS:raise ValueError('지원하지 않는 작업입니다.')
        answer=OPERATIONS[operation](job)
    except Exception as error:answer=result(message=str(error),success=False)
    language=job.get('language','en');language='zh-CN' if language=='zh' else language
    if language in ('vi','en','ko','ja','zh-TW','zh-CN'):
        try:
            catalog=json.loads((Path(__file__).resolve().parent.parent/'i18n/locales.json').read_text(encoding='utf-8'))
            def translate(value):
                if value in catalog:return catalog[value].get(language,catalog[value].get('en',value))
                for template,entries in catalog.items():
                    fields=re.findall(r'\{[A-Za-z_]+\}',template)
                    if not fields:continue
                    chunks=re.split(r'\{[A-Za-z_]+\}',template)
                    pattern='^'+'(.+?)'.join(re.escape(x) for x in chunks)+'$'
                    matched=re.match(pattern,value,re.S)
                    if matched:
                        translated=entries.get(language,template)
                        for name,arg in zip(fields,matched.groups()):translated=translated.replace(name,arg)
                        return translated
                return value
            answer['message']=translate(answer['message'])
            for item in answer.get('data',{}).get('results',[]):
                if isinstance(item,dict) and item.get('error'):item['error']=translate(item['error'])
        except (OSError,ValueError,TypeError):pass
    return answer


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--job',type=Path,required=True);parser.add_argument('--result',type=Path)
    args=parser.parse_args()
    try:answer=run(json.loads(args.job.read_text(encoding='utf-8')))
    except Exception as error:answer=result(message=str(error),success=False)
    payload=json.dumps(answer,ensure_ascii=False)
    if args.result:
        tmp=args.result.with_name(args.result.name+'.tmp');tmp.write_text(payload,encoding='utf-8');os.replace(tmp,args.result)
    print(payload)
    return 0 if answer['success'] else 1

if __name__=='__main__':sys.exit(main())
