import urllib.request,json,tarfile
from pathlib import Path
base=Path('work/engine/downloads')
j=json.load(urllib.request.urlopen('https://pypi.org/pypi/PyMuPDF/1.28.2/json'))
a=next(x for x in j['urls'] if x['packagetype']=='sdist');p=base/a['filename']
if not p.exists():urllib.request.urlretrieve(a['url'],p)
print(p.name,p.stat().st_size)
with tarfile.open(p) as t:
 names=t.getnames();print('\n'.join(n for n in names if 'mupdf' in n.lower() and n.endswith(('.gz','.xz','.zip'))));print('\n'.join(n for n in names if n.endswith(('COPYING','setup.py','pyproject.toml'))))
