"""Windows publisher using the developer's signed-in Google Drive desktop sync.
No developer credentials are distributed to app users. The fixed feed is written
in place, never deleted/recreated. Share the new ZIP using Drive's normal UI.
"""
import argparse,hashlib,json,os,shutil,sys,time,urllib.parse,urllib.request,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
# Use KIO's shipped runtime and crypto dependencies without global pip installs.
for p in [Path(sys.executable).parent.parent/'engine/deps-agent/win64',Path(sys.executable).parents[2]/'engine/deps-agent/arm64']:
 if p.is_dir():sys.path.insert(0,str(p))
from prepare_update import FEED_ID,FEED_URL,PUBLIC_KEY,inspect_zip,package,load_signing_key,sign,publish_platform
from update_security import verified_manifest,digest,allowed_url
# Same public-download transport as the application, including Drive large-file confirmation.
from public_download import download_response

def read_feed():
 with download_response(FEED_URL) as response:data=response.read(524289)
 if len(data)>524288:raise ValueError('Feed exceeds size limit')
 verified_manifest(json.loads(data),PUBLIC_KEY)
 return data

def verify_download(url,expected):
 h=hashlib.sha256();size=0
 with download_response(url) as response:
  while True:
   chunk=response.read(1024*1024)
   if not chunk:break
   size+=len(chunk)
   if size>expected['size']:raise ValueError('Downloaded ZIP exceeds expected size')
   h.update(chunk)
 if size!=expected['size'] or h.hexdigest()!=expected['sha256']:raise ValueError('Drive upload not complete or ZIP hash mismatch')

def write_in_place(path,data):
 # Opening the existing file preserves its Drive ID. Never rename/replace latest.json.
 with Path(path).open('r+b') as f:
  f.seek(0);f.write(data);f.truncate();f.flush();os.fsync(f.fileno())

def commit_feed(path,old,new,fetch=read_feed,wait_seconds=180):
 path=Path(path)
 if path.read_bytes()!=old or fetch()!=old:raise ValueError('Feed changed or Drive not synchronized; nothing published')
 write_in_place(path,new)
 try:
  deadline=time.monotonic()+wait_seconds
  while time.monotonic()<deadline:
   current=fetch()
   if current==new:return
   if current!=old:raise ValueError('Concurrent publisher detected')
   time.sleep(3)
  raise ValueError('Drive did not publish the new feed before timeout')
 except Exception:
  # Do not overwrite another publisher's local write while restoring our own.
  if path.read_bytes()==new:write_in_place(path,old)
  raise

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--config',required=True);parser.add_argument('--version',required=True);parser.add_argument('--zip',required=True);parser.add_argument('--url');parser.add_argument('--note',action='append',default=[])
 args=parser.parse_args();config=json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
 if config.get('feedId')!=FEED_ID:raise ValueError('Original fixed feed ID must be preserved')
 if config.get('publicKey')!=PUBLIC_KEY:raise ValueError('Original public key must be preserved')
 key=Path(config['encryptedKey']);feed=Path(config['feedPath']);directory=Path(config['windowsFolder'])
 if not key.read_bytes().startswith((b'-----BEGIN '+b'ENCRYPTED PRIVATE KEY-----')):raise ValueError('Encrypted PKCS#8 key required')
 if not feed.is_file() or not directory.is_dir():raise ValueError('Sign in to Google Drive desktop and synchronize release folders first')
 info=inspect_zip(args.zip,'Windows',args.version)
 old=read_feed();previous=json.loads(old)
 if feed.read_bytes()!=old:raise ValueError('Local latest.json differs from the public fixed-ID feed; synchronize first')
 destination=directory/f'KIO-Control-{args.version}-Windows-Portable.zip'
 if destination.exists():
  if digest(destination)!=info['sha256']:raise ValueError('Same-named release has different bytes; choose a new version')
 elif Path(args.zip).resolve()!=destination.resolve():shutil.copyfile(args.zip,destination)
 print('ZIP validated and staged:',destination)
 print('Wait for Drive sync. Share ONLY this ZIP as Anyone with the link / Viewer.')
 url=args.url or input('Paste that ZIP Google Drive share link: ').strip()
 parsed=urllib.parse.urlparse(url)
 if not allowed_url(url):raise ValueError('Google Drive HTTPS link required')
 parts=parsed.path.split('/');ident=(parts[3] if parts[:3]==['','file','d'] and len(parts)>3 else urllib.parse.parse_qs(parsed.query).get('id',[''])[0])
 if not ident or not all(c.isalnum() or c in '_-' for c in ident):raise ValueError('Drive file ID missing')
 url='https://drive.google.com/uc?export=download&id='+ident
 candidate={'url':url,**info};verify_download(url,candidate)
 payload=publish_platform(previous,'Windows',args.version,candidate,args.note)
 envelope=sign(payload,load_signing_key(key));new=(json.dumps(envelope,ensure_ascii=False,indent=2)+'\n').encode()
 backup=Path(os.environ.get('LOCALAPPDATA',tempfile.gettempdir()))/'KIOControl/ReleaseBackups';backup.mkdir(parents=True,exist_ok=True)
 backup_file=backup/('latest-before-'+args.version+'-'+str(int(time.time()))+'.json');backup_file.write_bytes(old)
 commit_feed(feed,old,new)
 print('PUBLISHED: anonymous fixed-ID feed, Ed25519 signature, ZIP hash/size verified.')
 print('Windows version:',args.version,'; Mac release unchanged. Backup:',backup_file)
if __name__=='__main__':
 try:main()
 except (Exception,KeyboardInterrupt) as error:
  print('NOT COMPLETED:',str(error),file=sys.stderr);sys.exit(1)
