"""Bounded, local-only timeline rendering. All media references are input indices.

Untrusted containers never choose their own demuxer or network protocol. Text and
still images become validated PNGs before entering FFmpeg; no filter/script text
or paths are accepted from options. The agent owns cancellation of this process
and all FFmpeg descendants, as well as final storage publication.
"""
from __future__ import annotations
import math,os,re,subprocess,sys,tempfile,time
from pathlib import Path
from PIL import Image,ImageDraw,ImageColor
import engine as base

MAX_DURATION=1800
MAX_FILE=256*1024**2
MAX_OUTPUT=2*1024**3

def number(value,default,low,high):
    if value is None:value=default
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:raise ValueError('invalidRequest')
    return value

def integer(value,default,low,high):
    value=number(value,default,low,high)
    if int(value)!=value:raise ValueError('invalidRequest')
    return int(value)

def rows(job,key,maximum,fields):
    value=job.get(key,[])
    if not isinstance(value,list) or len(value)>maximum:raise ValueError('invalidRequest')
    if any(not isinstance(row,dict) or set(row)-fields for row in value):raise ValueError('invalidRequest')
    return value

def validate(job):
    inputs=job.get('inputs',[])
    if not isinstance(inputs,list) or not 1<=len(inputs)<=180:raise ValueError('inputMissing')
    width=integer(job.get('width'),1280,64,1920);height=integer(job.get('height'),720,64,1920);fps=integer(job.get('fps'),30,1,60)
    if width%2 or height%2 or width*height>1920*1080:raise ValueError('invalidRequest')
    fmt=job.get('format','mp4')
    if fmt not in ('mp4','m4a'):raise ValueError('unsupported')
    clips=rows(job,'clips',60,{'source','kind','start','end','volume'})
    audio=rows(job,'audio',60,{'source','start','end','at','volume'})
    overlays=rows(job,'overlays',30,{'source','start','end','x','y','width'})
    texts=rows(job,'texts',60,{'text','start','end','x','y','fontSize','color','background'})
    if not clips and not (fmt=='m4a' and audio):raise ValueError('inputMissing')
    if fmt=='m4a' and (overlays or texts):raise ValueError('invalidRequest')
    def source(row):return integer(row.get('source'),-1,0,len(inputs)-1)
    def interval(row):
        start=number(row.get('start'),0,0,86400);end=number(row.get('end'),None,start+.02,min(86400,start+MAX_DURATION))
        return start,end
    parsed_clips=[]
    for row in clips:
        if row.get('kind') not in ('video','image'):raise ValueError('invalidRequest')
        start,end=interval(row)
        parsed_clips.append({**row,'source':source(row),'start':start,'end':end,'volume':number(row.get('volume'),1,0,2)})
    duration=sum(row['end']-row['start'] for row in parsed_clips)
    parsed_audio=[]
    for row in audio:
        start,end=interval(row);at=number(row.get('at'),0,0,MAX_DURATION)
        parsed_audio.append({**row,'source':source(row),'start':start,'end':end,'at':at,'volume':number(row.get('volume'),1,0,2)})
    clip_duration=duration
    duration=max([duration]+[row['at']+row['end']-row['start'] for row in parsed_audio])
    parsed_overlays=[];parsed_texts=[]
    for key,values in [('overlays',overlays),('texts',texts)]:
        for row in values:
            start,end=interval(row)
            duration=max(duration,end)
            item={**row,'start':start,'end':end,'x':number(row.get('x'),.5,0,1),'y':number(row.get('y'),.5,0,1)}
            if key=='overlays':
                item.update(source=source(row),width=number(row.get('width'),.25,.01,1));parsed_overlays.append(item)
            else:
                text=row.get('text');color=row.get('color','#ffffff');background=row.get('background',True)
                if not isinstance(text,str) or not text.strip() or len(text)>500 or any(ord(c)<32 and c!='\n' for c in text):raise ValueError('invalidRequest')
                if not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',color) or type(background) is not bool:raise ValueError('invalidRequest')
                item.update(fontSize=integer(row.get('fontSize'),40,6,200),color=color,background=background);parsed_texts.append(item)
    if job.get('duration') is not None:
        requested=number(job['duration'],None,.02,MAX_DURATION)
        if requested+.025<duration:raise ValueError('invalidRequest')
        duration=max(duration,requested)
    if not .02<=duration<=MAX_DURATION:raise ValueError('invalidRequest')
    return {'width':width,'height':height,'fps':fps,'format':fmt,'duration':duration,'clipDuration':clip_duration,'clips':parsed_clips,'audio':parsed_audio,'overlays':parsed_overlays,'texts':parsed_texts}

def demuxer(source):
    source=Path(source)
    if source.is_symlink() or not source.is_file():raise ValueError('inputMissing')
    if source.stat().st_size>MAX_FILE:raise ValueError('fileTooLarge')
    with source.open('rb') as stream:head=stream.read(4096)
    suffix=source.suffix.lower()
    if suffix in ('.mp4','.mov','.m4v','.m4a') and len(head)>=12 and head[4:8] in (b'ftyp',b'moov',b'mdat',b'wide',b'free'):return 'mov'
    if suffix in ('.mkv','.webm') and head.startswith(b'\x1a\x45\xdf\xa3'):return 'matroska'
    if suffix=='.avi' and head[:4]==b'RIFF' and head[8:12]==b'AVI ':return 'avi'
    if suffix in ('.ogg','.ogv','.oga','.opus') and head.startswith(b'OggS'):return 'ogg'
    if suffix=='.wav' and head[:4] in (b'RIFF',b'RF64') and head[8:12]==b'WAVE':return 'wav'
    if suffix=='.mp3' and (head.startswith(b'ID3') or len(head)>1 and head[0]==255 and head[1]&224==224):return 'mp3'
    if suffix=='.flac' and head.startswith(b'fLaC'):return 'flac'
    if suffix=='.aac' and len(head)>1 and head[0]==255 and head[1]&246==240:return 'aac'
    raise ValueError('unsupported')

def input_args(source,kind):
    args=['-protocol_whitelist','file','-f',kind,'-threads','2']
    if kind=='mov':args+=['-enable_drefs','0','-use_absolute_path','0']
    if kind=='image2':args+=['-pattern_type','none']
    return args+['-i',str(Path(source).resolve())]

class Renderer:
    def __init__(self,directory,progress):
        from ffmpeg_runtime import executable
        self.ffmpeg=executable();self.directory=Path(directory);self.progress=progress;self.probes={};self.deadline=time.monotonic()+3500;self.encoder=None
    def encoding(self,settings):
        if self.encoder is None:
            try:
                available=subprocess.check_output([self.ffmpeg,'-hide_banner','-encoders'],stderr=subprocess.DEVNULL,timeout=15,creationflags=0x08000000 if os.name=='nt' else 0).decode('utf-8','replace')
            except (OSError,subprocess.SubprocessError):raise ValueError('unsupported') from None
            names=set(re.findall(r'^\s*V[.A-Z]{5}\s+(\w+)\s',available,re.MULTILINE))
            candidates=['libopenh264','h264_mf'] if os.name=='nt' else ['h264_videotoolbox','libopenh264'] if sys.platform=='darwin' else ['libopenh264','libx264']
            self.encoder=next((name for name in candidates if name in names),None)
            if not self.encoder:raise ValueError('unsupported')
        bitrate=min(8_000_000,max(500_000,settings['width']*settings['height']*settings['fps']//6))
        args=['-c:v',self.encoder,'-b:v',str(bitrate),'-maxrate',str(bitrate),'-bufsize',str(bitrate*2),'-threads','2']
        if self.encoder=='h264_mf':args+=['-hw_encoding','0']
        elif self.encoder=='h264_videotoolbox':args+=['-allow_sw','1']
        elif self.encoder=='libx264':args+=['-preset','veryfast','-crf','20']
        return args
    def run(self,args,probe=False):
        if time.monotonic()>=self.deadline:raise ValueError('timeout')
        command=[self.ffmpeg,'-hide_banner','-nostdin','-loglevel','info' if probe else 'error','-filter_complex_threads','1']+args
        # File-backed diagnostics stay bounded on memory and are never returned.
        with tempfile.TemporaryFile() as errors:
            try:completed=subprocess.run(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=errors,timeout=min(15 if probe else 3500,max(1,self.deadline-time.monotonic())),creationflags=0x08000000 if os.name=='nt' else 0)
            except subprocess.TimeoutExpired:raise ValueError('timeout') from None
            errors.seek(0);diagnostics=errors.read(262144).decode('utf-8','replace')
        if not probe and completed.returncode:raise ValueError('processingFailed')
        if sum(path.stat().st_size for path in self.directory.iterdir() if path.is_file())>4*1024**3:raise ValueError('storageFull')
        return diagnostics
    def probe(self,source):
        source=Path(source)
        if source in self.probes:return self.probes[source]
        kind=demuxer(source);diagnostics=self.run(input_args(source,kind),probe=True)
        duration=re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)',diagnostics)
        if not duration:raise ValueError('unsupported')
        length=int(duration[1])*3600+int(duration[2])*60+float(duration[3])
        video=re.search(r'Stream #[^\r\n]+Video: [^\r\n]+',diagnostics)
        audio=re.search(r'Stream #[^\r\n]+Audio: [^\r\n]+',diagnostics)
        if not math.isfinite(length) or not 0<length<=86400:raise ValueError('unsupported')
        if video:
            dimensions=re.search(r'\b(\d{2,5})x(\d{2,5})\b',video[0])
            if not dimensions or int(dimensions[1])*int(dimensions[2])>33_177_600:raise ValueError('fileTooLarge')
        result={'demuxer':kind,'duration':length,'video':bool(video),'audio':bool(audio)};self.probes[source]=result;return result
    def source(self,inputs,row,stream):
        source=Path(inputs[row['source']]);info=self.probe(source)
        if not info[stream]:raise ValueError('unsupported')
        if row['start']>=info['duration'] or row['end']>info['duration']+.075:raise ValueError('invalidRequest')
        return source,info
    def still(self,source,name,size=None):
        source=Path(source)
        if source.is_symlink() or not source.is_file():raise ValueError('inputMissing')
        if source.stat().st_size>MAX_FILE:raise ValueError('fileTooLarge')
        image=base.checked_image(source)
        if size:image.thumbnail(size,Image.Resampling.LANCZOS)
        path=self.directory/name;image.save(path,'PNG');image.close();return path
    def segment(self,inputs,row,index,settings):
        width,height,fps=settings['width'],settings['height'],settings['fps'];duration=row['end']-row['start']
        audio=False
        if row['kind']=='image':
            image=self.still(inputs[row['source']],f'image-{index}.png',(width,height))
            args=['-loop','1','-framerate',str(fps)]+input_args(image,'image2')
        else:
            source,info=self.source(inputs,row,'video');audio=info['audio']
            args=['-ss',str(row['start']),'-t',str(duration)]+input_args(source,info['demuxer'])
        if not audio:args+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
        visual=f'[0:v:0]setpts=PTS-STARTPTS,scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={fps},format=yuv420p,tpad=stop_mode=clone:stop_duration={duration},trim=duration={duration}[v]'
        sound=f'[{0 if audio else 1}:a:0]asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={row["volume"]},apad,atrim=duration={duration}[a]'
        audio_only=settings['format']=='m4a';path=self.directory/f'clip-{index}.{settings["format"]}'
        filters=sound if audio_only else visual+';'+sound
        maps=[] if audio_only else ['-map','[v]']+self.encoding(settings)
        self.run(args+['-filter_complex',filters]+maps+['-map','[a]','-t',str(duration),'-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-map_metadata','-1','-y',str(path)])
        return path
    def text(self,row,index,settings):
        from engine_extra import font
        width,height=settings['width'],settings['height'];face=font(row['fontSize']);spacing=max(2,row['fontSize']//5)
        measure=ImageDraw.Draw(Image.new('RGBA',(1,1)));bounds=measure.multiline_textbbox((0,0),row['text'],font=face,spacing=spacing,align='center',stroke_width=1)
        w=min(width,max(1,math.ceil(bounds[2]-bounds[0]+16)));h=min(height,max(1,math.ceil(bounds[3]-bounds[1]+12)))
        image=Image.new('RGBA',(w,h),(0,0,0,170) if row['background'] else (0,0,0,0));draw=ImageDraw.Draw(image)
        draw.multiline_text(((w-(bounds[2]-bounds[0]))/2-bounds[0],6-bounds[1]),row['text'],font=face,fill=ImageColor.getcolor(row['color'],'RGBA'),spacing=spacing,align='center',stroke_width=1,stroke_fill=(0,0,0,180))
        path=self.directory/f'text-{index}.png';image.save(path,'PNG');image.close();return path,w,h

def video_edit(job,progress=lambda _:None):
    settings=validate(job);inputs=job['inputs'];output=Path(job['output_dir']);output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.video-',dir=output) as directory:
        renderer=Renderer(directory,progress);width,height,fps=settings['width'],settings['height'],settings['fps'];duration=settings['duration'];audio_only=settings['format']=='m4a'
        clips=[]
        for index,row in enumerate(settings['clips']):
            progress(5+50*index/max(1,len(settings['clips'])));clips.append(renderer.segment(inputs,row,index,settings))
        args=[];filters=[];sound=[];next_input=1
        if clips:
            manifest=Path(directory)/'clips.ffconcat'
            # Only program-generated ASCII basenames enter this concat manifest.
            manifest.write_text('ffconcat version 1.0\n'+''.join(f"file '{path.name}'\nduration {row['end']-row['start']:.9f}\n" for path,row in zip(clips,settings['clips'])),encoding='ascii')
            args=['-protocol_whitelist','file','-f','concat','-safe','1','-i',str(manifest)]
            filters=['[0:a:0]asetpts=PTS-STARTPTS,apad,atrim=duration='+str(duration)+'[a0]'];sound=['[a0]'];visual='v0'
            if not audio_only:filters.insert(0,f'[0:v:0]setpts=PTS-STARTPTS,fps={fps},trim=duration={settings["clipDuration"]},tpad=stop_mode=add:color=black:stop_duration={max(0,duration-settings["clipDuration"])},trim=duration={duration}[v0]')
        else:
            args=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo'];filters=[f'[0:a:0]atrim=duration={duration}[a0]'];sound=['[a0]']
        for index,row in enumerate(settings['audio']):
            source,info=renderer.source(inputs,row,'audio');length=row['end']-row['start']
            args+=['-ss',str(row['start']),'-t',str(length)]+input_args(source,info['demuxer'])
            filters.append(f'[{next_input}:a:0]asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={row["volume"]},atrim=duration={length},adelay={round(row["at"]*48000)}S:all=1[a{index+1}]');sound.append(f'[a{index+1}]');next_input+=1
        filters.append(''.join(sound)+f'amix=inputs={len(sound)}:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95:level=false:latency=true,atrim=duration={duration}[audio]')
        elements=[]
        for index,row in enumerate(settings['overlays']):
            target=max(1,round(width*row['width']));path=renderer.still(inputs[row['source']],f'overlay-{index}.png')
            with Image.open(path) as original:
                h=max(1,round(original.height*target/original.width))
                if target*h>base.Image.MAX_IMAGE_PIXELS:raise ValueError('fileTooLarge')
                # Bound off-canvas tall content too; crop after scaling preserves aspect.
                scaled=original.resize((target,h),Image.Resampling.LANCZOS);cropped=scaled.crop((0,0,target,min(height,h)));cropped.save(path,'PNG');scaled.close();cropped.close()
            elements.append((path,round(row['x']*width),round(row['y']*height),row))
        for index,row in enumerate(settings['texts']):
            path,w,h=renderer.text(row,index,settings);elements.append((path,round(row['x']*width-w/2),round(row['y']*height),row))
        for index,(path,x,y,row) in enumerate(elements):
            args+=['-loop','1','-framerate',str(fps)]+input_args(path,'image2')
            label=f'v{index+1}';filters.append(f'[{visual}][{next_input}:v:0]overlay=x={x}:y={y}:eof_action=repeat:enable=\'gte(t,{row["start"]})*lt(t,{row["end"]})\'[{label}]');visual=label;next_input+=1
        progress(60)
        def write(path):
            command=args+['-filter_complex',';'.join(filters)]
            if not audio_only:command+=['-map',f'[{visual}]']+renderer.encoding(settings)+['-pix_fmt','yuv420p','-r',str(fps)]
            command+=['-map','[audio]','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-t',str(duration),'-movflags','+faststart','-map_metadata','-1','-map_chapters','-1','-fs',str(MAX_OUTPUT),'-y',str(path)]
            renderer.run(command)
            # A capped or prematurely ended encoder must never publish a short export.
            diagnostics=renderer.run(input_args(path,'mov'),probe=True)
            match=re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)',diagnostics)
            actual=int(match[1])*3600+int(match[2])*60+float(match[3]) if match else 0
            if abs(actual-duration)>max(.15,2/fps) or path.stat().st_size>=MAX_OUTPUT:raise ValueError('processingFailed')
        path=base.write_atomic(output,'KIO-audio' if audio_only else 'KIO-video','.'+settings['format'],write)
        progress(95)
        return base.result([path],{'duration':duration,'width':0 if audio_only else width,'height':0 if audio_only else height,'fps':0 if audio_only else fps,'clipCount':len(clips),'audioOnly':audio_only})
