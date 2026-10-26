"""Reusable transparent signature copies in private per-user storage.
Only authenticated agent routes may supply an owner and an owned opaque file ID.
Saving never replaces or removes the source image. No network or OCR is used.
"""
import threading
from pathlib import Path
from PIL import Image,ImageOps
from common import AgentError,private_dir,read_json,atomic_json,valid_id,utc
from index import contained,read_local_file
from engine import write_atomic

class SignatureLibrary:
 def __init__(self,state,resolve,register):
  self.state=Path(state);self.root=private_dir(self.state/'signatures');self.manifest=self.root/'library.json';self.resolve=resolve;self.register=register;self.lock=threading.RLock()
  value=read_json(self.manifest,{},maximum=512_000)
  self.items=value.get('items',{}) if isinstance(value,dict) else {}
  if not isinstance(self.items,dict):self.items={}
 def persist(self):atomic_json(self.manifest,{'version':1,'items':self.items})
 def asset(self,ident,item,owner):
  if not isinstance(owner,str) or not owner:raise AgentError('unauthorized',401)
  if not valid_id(ident) or not isinstance(item,dict):raise AgentError('fileMissing',404)
  filename=item.get('file','')
  if not isinstance(filename,str) or Path(filename).name!=filename or not filename.endswith('.png'):raise AgentError('fileMissing',404)
  path=self.root/filename
  if not contained(path,self.root) or not path.is_file():raise AgentError('fileMissing',404)
  aliases=item.get('aliases',{})
  if not isinstance(aliases,dict):aliases={}
  alias=aliases.get(owner);file=None
  if isinstance(alias,dict) and valid_id(alias.get('id')):
   try:
    resolved=self.resolve(alias['id'],owner)
    if Path(resolved).resolve()==path.resolve():file=alias
   except AgentError:pass
  if file is None:
   file=self.register(path,owner,kind='signature',name=item.get('name','Signature')+'.png');aliases[owner]=file;item['aliases']=aliases;self.persist()
  return {**file,'signatureId':ident,'label':item.get('name','Signature'),'width':item.get('width',0),'height':item.get('height',0),'created':item.get('created','')}
 def list(self,owner):
  if not isinstance(owner,str) or not owner:raise AgentError('unauthorized',401)
  with self.lock:
   result=[]
   for ident,item in list(self.items.items())[:100]:
    try:result.append(self.asset(ident,item,owner))
    except AgentError as error:
     if error.code not in ('fileMissing','invalidRequest'):raise
   return result
 def save(self,ident,name,owner):
  if not isinstance(owner,str) or not owner:raise AgentError('unauthorized',401)
  if not isinstance(name,str) or not name.strip() or len(name)>80 or any(ord(c)<32 or c in '/\\' for c in name):raise AgentError('invalidRequest')
  source=self.resolve(ident,owner);data=read_local_file(source,max_bytes=16*1024*1024+1)
  if data is None or len(data)>16*1024*1024:raise AgentError('fileTooLarge',413)
  import io,uuid
  try:
   with Image.open(io.BytesIO(data)) as image:
    if image.format not in ('PNG','JPEG','WEBP','BMP','TIFF') or getattr(image,'n_frames',1)!=1:raise AgentError('unsupported')
    if image.width*image.height>4_000_000:raise AgentError('fileTooLarge',413)
    image=ImageOps.exif_transpose(image).convert('RGBA');bounds=image.getchannel('A').getbbox()
    if bounds is None:raise AgentError('inputMissing')
    image=image.crop(bounds);width,height=image.size
    with self.lock:
     if len(self.items)>=100:raise AgentError('storageFull',507)
     if not contained(self.root,self.state):raise AgentError('unsafePath')
     signature=str(uuid.uuid4());path=Path(write_atomic(self.root,signature,'.png',lambda destination:image.save(destination,'PNG',optimize=True)))
     item={'name':name.strip(),'file':path.name,'width':width,'height':height,'created':utc(),'aliases':{}}
     self.items[signature]=item;self.persist()
     return self.asset(signature,item,owner)
  except Image.DecompressionBombError as error:raise AgentError('fileTooLarge',413) from error
  except (OSError,ValueError,RuntimeError) as error:raise AgentError('unsupported') from error
