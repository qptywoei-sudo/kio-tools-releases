from pathlib import Path
import urllib.request,json,re,hashlib,tarfile,zipfile,concurrent.futures
base=Path(__file__).resolve().parent;downloads=base/'downloads';downloads.mkdir(exist_ok=True)
def fetch(url):
 req=urllib.request.Request(url,headers={'User-Agent':'GalaxyControl-build'})
 with urllib.request.urlopen(req,timeout=60) as r:return r.read()
release=json.loads(fetch('https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest'))
assets=release['assets']; candidates=[a for a in assets if re.match(r'cpython-3\.13\.\d+\+.*-aarch64-apple-darwin-install_only\.tar\.gz$',a['name'])]
assert candidates,'No supported Python3.13 runtime'
a=candidates[0];version=re.match(r'cpython-(3\.13\.\d+)',a['name']).group(1)
x=next(z for z in assets if z['name']==a['name'].replace('aarch64','x86_64'))
winurl=f'https://www.python.org/ftp/python/{version}/python-{version}-embed-amd64.zip'
def load(item):
 label,url,name=item;p=downloads/name
 if not p.exists():p.write_bytes(fetch(url))
 return label,p,hashlib.sha256(p.read_bytes()).hexdigest()
items=[('arm64',a['browser_download_url'],a['name']),('x86_64',x['browser_download_url'],x['name']),('win64',winurl,f'python-{version}-embed-amd64.zip'),('jsonheader','https://raw.githubusercontent.com/nlohmann/json/v3.12.0/single_include/nlohmann/json.hpp','json.hpp')]
manifest={'python_version':version,'python_release':release['tag_name'],'sources':[]}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 for label,p,digest in pool.map(load,items):
  if label=='jsonheader':(base.parent/'windows/vendor/json.hpp').write_bytes(p.read_bytes());continue
  dest=base/'runtimes'/label;dest.mkdir(parents=True,exist_ok=True)
  if p.suffix=='.zip':
   with zipfile.ZipFile(p) as z:
    for n in z.namelist():assert not Path(n).is_absolute() and '..' not in Path(n).parts
    z.extractall(dest)
   short=''.join(version.split('.')[:2]);(dest/f'python{short}._pth').write_text(f'python{short}.zip\n.\nLib/site-packages\nimport site\n')
  else:
   with tarfile.open(p) as t:
    for m in t.getmembers():
     assert not Path(m.name).is_absolute() and '..' not in Path(m.name).parts
     if m.issym():assert not Path(m.linkname).is_absolute() and '..' not in Path(m.linkname).parts
    t.extractall(dest)
  manifest['sources'].append({'architecture':label,'archive':p.name,'url':next(i[1] for i in items if i[0]==label),'sha256':digest})
(base/'runtime-manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps({'version':version,'release':release['tag_name'],'architectures':[s['architecture'] for s in manifest['sources']]}))
