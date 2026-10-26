"""Acquire verified official wheels into isolated additive runtime dependencies."""
import urllib.request,json,hashlib,zipfile,io,argparse
from pathlib import Path
base=Path(__file__).resolve().parent.parent/'engine'
def metadata(name,version=''):
 with urllib.request.urlopen('https://pypi.org/pypi/'+name+('/'+version if version else '')+'/json',timeout=60) as r:return json.load(r)
packages={'numpy':'2.5.3','watchdog':'6.0.0','imageio-ffmpeg':'0.6.0','opencv-python-headless':'4.13.0.92','flatbuffers':'','packaging':'','protobuf':'','sympy':'','mpmath':'','coloredlogs':'','humanfriendly':'','python-pptx':'','lxml':'','XlsxWriter':'','PyJWT':'2.15.1','cryptography':'50.0.2','cffi':'2.1.1','pycparser':'3.11'}
parser=argparse.ArgumentParser();parser.add_argument('--packages',nargs='+',choices=list(packages));parser.add_argument('--arch',nargs='+',choices=['arm64','x86_64','win64']);args=parser.parse_args()
if args.packages:packages={name:packages[name] for name in args.packages}
manifest_path=base/'agent-dependencies.json'
manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else []
architectures=args.arch or ('arm64','x86_64','win64')
manifest=[row for row in manifest if not(row.get('name') in packages and row.get('arch') in architectures)]
for arch in architectures:
 target=base/'deps-agent'/arch;target.mkdir(parents=True,exist_ok=True)
 for name,version in packages.items():
  d=metadata(name,version)
  def score(x):
   f=x['filename']
   if not f.endswith('.whl'):return -1
   if not any(s in f for s in ('cp313-cp313','abi3','py3-none','py2.py3-none')):return -1
   if '-any.whl' in f:return 1
   if arch=='win64':return 2 if 'win_amd64' in f else -1
   if 'macosx' not in f:return -1
   if 'universal2' in f:return 3
   if arch=='arm64' and 'arm64' in f:return 4 if '11_0' in f else 2
   if arch=='x86_64' and 'x86_64' in f:return 4 if '10_' in f else 2
   return -1
  choices=sorted((x for x in d['urls'] if score(x)>=0),key=score,reverse=True)
  if not choices:
   print('UNAVAILABLE',arch,name,version,flush=True);continue
  item=choices[0];record={'arch':arch,'name':name,'version':d['info']['version'],'filename':item['filename'],'sha256':item['digests']['sha256'],'url':item['url']}
  receipt=target/(name.replace('-','_')+'.wheel-receipt.json')
  if receipt.exists() and json.loads(receipt.read_text()).get('sha256')==record['sha256']:
   manifest.append(record);continue
  with urllib.request.urlopen(item['url'],timeout=120) as r:content=r.read(150_000_000)
  if hashlib.sha256(content).hexdigest()!=record['sha256']:raise RuntimeError('Checksum mismatch')
  with zipfile.ZipFile(io.BytesIO(content)) as z:
   for info in z.infolist():
    p=target/info.filename
    if not p.resolve().is_relative_to(target.resolve()):raise RuntimeError('Wheel path escape')
   z.extractall(target)
   for info in z.infolist():
    mode=(info.external_attr>>16)&0o777
    if mode and (target/info.filename).is_file():(target/info.filename).chmod(mode)
  receipt.write_text(json.dumps(record));manifest.append(record)
  print('OK',arch,name,d['info']['version'],flush=True)
(base/'agent-dependencies.json').write_text(json.dumps(manifest,indent=2))
