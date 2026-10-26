"""Signed, bounded release manifests and traversal-safe ZIP extraction."""
import base64,hashlib,json,re,stat,zipfile,os
from pathlib import Path,PurePosixPath
from urllib.parse import urlparse

def version(text):
 if not isinstance(text,str) or not re.fullmatch(r'\d{1,5}\.\d{1,5}\.\d{1,5}',text):raise ValueError('updateInvalidManifest')
 return tuple(map(int,text.split('.')))
def allowed_url(url):
 u=urlparse(url)
 return u.scheme=='https' and u.hostname in ('drive.google.com','drive.usercontent.google.com') and u.port in (None,443) and not u.username and not u.password and not u.fragment

def verified_manifest(envelope,public_key):
 from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
 if not isinstance(envelope,dict) or set(envelope)!={'payload','signature'}:raise ValueError('updateInvalidSignature')
 payload=envelope['payload'];raw=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
 try:Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key,validate=True)).verify(base64.b64decode(envelope['signature'],validate=True),raw)
 except Exception:raise ValueError('updateInvalidSignature') from None
 if not isinstance(payload,dict):raise ValueError('updateInvalidManifest')
 if payload.get('product')!='kio-control' or payload.get('format')!=1:raise ValueError('updateInvalidManifest')
 version(payload.get('version'));packages=payload.get('packages')
 if not isinstance(packages,dict) or set(packages)!={'Windows','Mac'}:raise ValueError('updateInvalidManifest')
 if not isinstance(payload.get('notes'),list) or len(payload['notes'])>20 or any(not isinstance(x,str) or len(x)>1000 for x in payload['notes']):raise ValueError('updateInvalidManifest')
 for platform,p in packages.items():
  if not isinstance(p,dict) or set(p)!={'url','size','sha256','root'} or not allowed_url(p['url']) or type(p['size']) is not int or not 1000<=p['size']<=2*1024**3 or not isinstance(p['sha256'],str) or not re.fullmatch('[a-f0-9]{64}',p['sha256']) or p['root']!='KIO-Control-'+platform:raise ValueError('updateInvalidManifest')
 releases=payload.get('platformReleases')
 if releases is not None:
  if not isinstance(releases,dict) or set(releases)!={'Windows','Mac'}:raise ValueError('updateInvalidManifest')
  for platform,r in releases.items():
   if not isinstance(r,dict) or set(r)!={'version','notes','package'}:raise ValueError('updateInvalidManifest')
   if version(r['version'])<version(payload['version']):raise ValueError('updateInvalidManifest')
   if not isinstance(r['notes'],list) or len(r['notes'])>20 or any(not isinstance(x,str) or len(x)>1000 for x in r['notes']):raise ValueError('updateInvalidManifest')
   p=r['package']
   if not isinstance(p,dict) or set(p)!={'url','size','sha256','root'} or not allowed_url(p['url']) or type(p['size']) is not int or not 1000<=p['size']<=2*1024**3 or not isinstance(p['sha256'],str) or not isinstance(p['sha256'],str) or not re.fullmatch('[a-f0-9]{64}',p['sha256']) or p['root']!='KIO-Control-'+platform:raise ValueError('updateInvalidManifest')
 return payload

def platform_release(payload,platform):
 """Call only after verified_manifest. Legacy clients ignore the signed extension."""
 if platform not in ('Windows','Mac'):raise ValueError('updateInvalidManifest')
 return payload['platformReleases'][platform] if 'platformReleases' in payload else {'version':payload['version'],'notes':payload['notes'],'package':payload['packages'][platform]}

def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def zip_name(info):
 name=info.filename
 if not info.flag_bits&0x800:
  try:name=name.encode('cp437').decode('utf-8')
  except (UnicodeError,UnicodeEncodeError):pass
 return name

def extract_verified(archive,dest,root):
 dest=Path(dest);dest.mkdir(parents=True,exist_ok=False);entries=[];seen=set();links=set();total=0
 with zipfile.ZipFile(archive) as z:
  if len(z.infolist())>60000:raise ValueError('updateUnsafeArchive')
  for info in z.infolist():
   name=zip_name(info)
   if name.startswith('__MACOSX/'):continue
   p=PurePosixPath(name)
   if p.is_absolute() or '\\' in name or ':' in name or '..' in p.parts or not p.parts or p.parts[0]!=root:raise ValueError('updateUnsafeArchive')
   key='/'.join(p.parts).casefold()
   if key in seen:raise ValueError('updateUnsafeArchive')
   seen.add(key);mode=info.external_attr>>16
   if stat.S_ISLNK(mode):
    link=z.read(info).decode()
    if not link or '/' in link or '\\' in link or link in ('.','..'):raise ValueError('updateUnsafeArchive')
    links.add(p);entries.append((info,p,mode,link))
   else:
    if not(info.is_dir() or stat.S_ISREG(mode) or stat.S_IFMT(mode)==0):raise ValueError('updateUnsafeArchive')
    total+=info.file_size
    if total>5*1024**3:raise ValueError('updateUnsafeArchive')
    entries.append((info,p,mode,None))
  for _,p,_,_ in entries:
   if any(parent in links for parent in p.parents):raise ValueError('updateUnsafeArchive')
  for info,p,mode,link in entries:
   if link is not None:continue
   target=dest.joinpath(*p.parts)
   if info.is_dir():target.mkdir(parents=True,exist_ok=True);continue
   target.parent.mkdir(parents=True,exist_ok=True)
   with z.open(info) as source,target.open('xb') as out:
    while True:
     block=source.read(1024*1024)
     if not block:break
     out.write(block)
   os.chmod(target,(mode&0o777) or 0o644)
  for info,p,mode,link in entries:
   if link is not None:
    target=dest.joinpath(*p.parts);target.parent.mkdir(parents=True,exist_ok=True);target.symlink_to(link)
 return dest/root
