"""Verify release ZIPs and sign manifests using the original Ed25519 identity.
Encrypted PKCS#8 passwords are prompted securely, never accepted on argv or env.
"""
import argparse,base64,copy,getpass,hashlib,json,os,plistlib,re,stat,struct,sys,zipfile,io
from pathlib import Path,PurePosixPath
sys.path.insert(0,str(Path(__file__).resolve().parent))
# The backup folder contains update_security.py; development source uses agent/.
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
for dep in [Path(sys.executable).parent.parent/'engine/deps-agent/win64',Path(sys.executable).parents[2]/'engine/deps-agent/arm64',Path(__file__).resolve().parents[1]/'engine/deps-agent/arm64']:
 if dep.is_dir():sys.path.insert(0,str(dep))
from update_security import verified_manifest,platform_release,version,digest,zip_name,allowed_url
PUBLIC_KEY='JjeL9t/8GSrh2XZ25gawQyI475nXr/rU0li4CoEnfos='
FEED_ID='1p91Pj2v2RhhnSG0rxOxBJW_oBvGjuGqd'
FEED_URL='https://github.com/qptywoei-sudo/kio-tools-releases/releases/download/tools-update-channel/latest.json'
# Exact unchanged third-party corresponding-source archives from the previous release.
VENDOR_SOURCE_HASHES={'mupdf-1.28.2-source.tar.gz': '44075a84e329db55b9bef5f342a70fd26d69e48ad1d33cb89d9664581c641156', 'pymupdf-1.28.2-source.tar.gz': 'fe2cca0e7579545e626d4261aa6915b56163b79cb2d2411e832f56a57a1cc569', 'nsis-3.13-src.tar.bz2': 'a8ffe024602d46b6d766f9e1ce30c324ad2a24daeacd3efc2642d436a0c157ac', 'FFmpeg-video-source-notices.zip': '01eaec5d0f7aa0180249c08733e276caabe60021e7e80769c4ab222550e25d59', 'ffmpeg-7.1-zlib-1.3.2-rebuild.tar.xz': '87ca54d2fa28fb73bef4128f54214d2d6bb43d84e93b5e1009b0f1bd4d3309aa', 'KIO-FFmpeg-7.1-Mac-source.tar.xz': 'cee3d9c061227d29d0af40633ffd5b889bdf032fdb68b009eeadb6760cc2bd7a'}

def pe_version(data):
 if data[:2]!=b'MZ' or len(data)<256:raise ValueError('Missing Windows executable')
 pe=struct.unpack_from('<I',data,60)[0]
 if data[pe:pe+4]!=b'PE\0\0':raise ValueError('Invalid Windows executable')
 sections=struct.unpack_from('<H',data,pe+6)[0];optional=struct.unpack_from('<H',data,pe+20)[0]
 found=[]
 for i in range(sections):
  pos=pe+24+optional+40*i
  if data[pos:pos+8].rstrip(b'\0')!=b'.rsrc':continue
  size,offset=struct.unpack_from('<II',data,pos+16);resource=data[offset:offset+size]
  for m in re.finditer(re.escape(b'\xbd\x04\xef\xfe\x00\x00\x01\x00'),resource):
   ms,ls=struct.unpack_from('<II',resource,m.start()+8);found.append(f'{ms>>16}.{ms&65535}.{ls>>16}')
 if len(set(found))!=1:raise ValueError('Missing or ambiguous PE version resource')
 return found[0]

def inspect_zip(path,platform,expected):
 version(expected);root='KIO-Control-'+platform
 forbidden={'desktop-session.json','settings.json','device.json','auth.json','credentials.json','tokens.json','account.json'}
 seen=set();links=set();total=0;agent=None;native=None
 with zipfile.ZipFile(path) as z:
  if len(z.infolist())>60000:raise ValueError('Too many ZIP entries')
  for info in z.infolist():
   name=zip_name(info);p=PurePosixPath(name);parts=[x.casefold() for x in p.parts]
   if name.startswith('__MACOSX/'):continue
   if not parts or p.is_absolute() or '..' in parts or '\\' in name or ':' in name or p.parts[0]!=root:raise ValueError('Unsafe ZIP path')
   folded='/'.join(parts)
   if folded in seen:raise ValueError('Duplicate ZIP path')
   seen.add(folded);total+=info.file_size
   if total>5*1024**3:raise ValueError('ZIP exceeds expanded size limit')
   if any(x in {'releasesigning','.git','.kio-key-handoffs','__pycache__'} for x in parts) or p.name.casefold() in forbidden or p.suffix.lower() in {'.p12','.pfx','.kioenc','.log'} or 'signing-private' in folded or 'update-key' in folded:raise ValueError('Private/user data in ZIP: '+name)
   if info.is_dir():continue
   mode=info.external_attr>>16
   if stat.S_ISLNK(mode):
    links.add(folded)
    target=z.read(info).decode()
    if not target or target in ('.','..') or '/' in target or '\\' in target:raise ValueError('Unsafe ZIP symlink')
    continue
   if '/tools/source/' in name:
    nested=z.read(info)
    if p.name=='KIO-Control-source.zip':
     with zipfile.ZipFile(io.BytesIO(nested)) as source:
      if sum(i.file_size for i in source.infolist())>100*1024**2:raise ValueError('Source archive too large')
      for entry in source.infolist():
       child=PurePosixPath(entry.filename)
       if child.name.casefold() in forbidden or 'signing-private' in entry.filename or '..' in child.parts:raise ValueError('Private or unsafe nested source')
       data=source.read(entry)
       if re.search(rb'-----BEGIN (?:ENCRYPTED |RSA |EC |OPENSSH )?PRIVATE KEY-----\r?\n[A-Za-z0-9+/=]{40}',data):raise ValueError('Private key in nested source')
    elif hashlib.sha256(nested).hexdigest()!=VENDOR_SOURCE_HASHES.get(p.name):raise ValueError('Unreviewed third-party source archive')
   elif p.suffix.lower() in {'.zip','.7z','.rar','.tar','.gz','.tgz'} and '/tools/python/' not in folded and '/tools/engine/deps-agent/' not in folded:
    raise ValueError('Nested release archive requires separate inspection: '+name)
   # The unchanged 4.4.1 bundled GnuTLS binary embeds its own key fixture.
   # Permit only these exact vendor bytes, never an arbitrary library path.
   vendor_fixture = name.endswith('/cv2/.dylibs/libgnutls.30.dylib') and hashlib.sha256(z.read(info)).hexdigest() == '2b8f602e5d576a87460d6e64838a58fe05ccbcf285ac48b853786bb678b52ae6'
   # Scan every other file in bounded chunks for PEM private keys.
   with z.open(info) as f:
    tail=b''
    for chunk in iter(lambda:f.read(1024*1024),b''):
     scan=tail+chunk
     if not vendor_fixture and re.search(rb'-----BEGIN (?:ENCRYPTED |RSA |EC |OPENSSH )?PRIVATE KEY-----\r?\n[A-Za-z0-9+/=]{40}',scan):raise ValueError('Private key content in ZIP: '+name)
     tail=scan[-100:]
   if name.endswith('/tools/engine/agent/common.py'):
    source=z.read(info).decode();m=re.search(r'^VERSION\s*=\s*[\'\"]([^\'\"]+)',source,re.M)
    agent=m.group(1) if m else None
   if platform=='Windows' and name==root+'/KIOControl.exe':native=pe_version(z.read(info))
   if platform=='Mac' and name.endswith('.app/Contents/Info.plist'):
    meta=plistlib.loads(z.read(info))
    if meta.get('CFBundleIdentifier')!='local.galaxycontrol.portable':raise ValueError('Unexpected Mac bundle identity')
    native=meta.get('CFBundleShortVersionString')
  if any(any('/'.join(path.split('/')[:i]) in links for i in range(1,len(path.split('/')))) for path in seen):raise ValueError('ZIP entry below symlink')
  if agent!=expected or native!=expected:raise ValueError(f'Actual build version mismatch: native={native}, agent={agent}, requested={expected}')
 return {'size':Path(path).stat().st_size,'sha256':digest(path),'root':root}

def package(path,platform,release_version,url):
 if not allowed_url(url):raise ValueError('Only pinned HTTPS release download URLs are allowed')
 return {'url':url,**inspect_zip(path,platform,release_version)}

def load_signing_key(path):
 from cryptography.hazmat.primitives import serialization
 from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
 data=Path(path).read_bytes();encrypted=data.startswith((b'-----BEGIN '+b'ENCRYPTED PRIVATE KEY-----'))
 password=getpass.getpass('Update signing key password: ').encode() if encrypted else None
 try:key=serialization.load_pem_private_key(data,password=password)
 finally:password=None
 if not isinstance(key,Ed25519PrivateKey):raise ValueError('Ed25519 key required')
 public=base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode()
 if public!=PUBLIC_KEY:raise ValueError('STOP: original signing identity mismatch')
 return key

def sign(payload,key):
 raw=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
 envelope={'payload':payload,'signature':base64.b64encode(key.sign(raw)).decode()}
 verified_manifest(envelope,PUBLIC_KEY)
 return envelope

def publish_platform(previous,platform,new_version,new_package,notes):
 payload=copy.deepcopy(verified_manifest(previous,PUBLIC_KEY))
 if 'platformReleases' not in payload:raise ValueError('Publish the verified two-platform transition first')
 if version(new_version)<=version(platform_release(payload,platform)['version']):raise ValueError('New version must increase')
 payload['platformReleases'][platform]={'version':new_version,'notes':notes,'package':new_package}
 return payload

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--version',required=True);parser.add_argument('--key',required=True);parser.add_argument('--output',required=True);parser.add_argument('--note',action='append',default=[])
 parser.add_argument('--windows');parser.add_argument('--mac');parser.add_argument('--windows-id');parser.add_argument('--mac-id')
 parser.add_argument('--platform',choices=['Windows','Mac']);parser.add_argument('--previous');parser.add_argument('--zip');parser.add_argument('--url')
 args=parser.parse_args();version(args.version)
 if args.platform:
  if not all([args.previous,args.zip,args.url]):parser.error('--platform needs --previous --zip --url')
  payload=publish_platform(json.loads(Path(args.previous).read_text()),args.platform,args.version,package(args.zip,args.platform,args.version,args.url),args.note)
 else:
  if not all([args.windows,args.mac,args.windows_id,args.mac_id]):parser.error('Transition needs both real builds and their Drive IDs')
  packages={p:package(path,p,args.version,'https://drive.google.com/uc?export=download&id='+ident) for p,path,ident in [('Windows',args.windows,args.windows_id),('Mac',args.mac,args.mac_id)]}
  payload={'product':'kio-control','format':1,'version':args.version,'notes':args.note,'packages':packages,'platformReleases':{p:{'version':args.version,'notes':args.note,'package':dict(value)} for p,value in packages.items()}}
 envelope=sign(payload,load_signing_key(args.key));target=Path(args.output);temp=target.with_suffix(target.suffix+'.tmp')
 temp.write_text(json.dumps(envelope,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(temp,target)
 print('ZIP versions, original signing identity and signed manifest verified.')
if __name__=='__main__':main()
