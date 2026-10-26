import urllib.request,json
for name in ['opencv-python-headless','numpy','watchdog','imageio-ffmpeg']:
 with urllib.request.urlopen('https://pypi.org/pypi/'+name+'/json',timeout=30) as r:d=json.load(r)
 wheels=[x['filename'] for x in d['urls'] if x['filename'].endswith('.whl') and ('cp313' in x['filename'] or 'abi3' in x['filename'] or 'py3-none' in x['filename']) and any(p in x['filename'] for p in ['macosx','win_amd64','any'])]
 print(name,d['info']['version'],wheels)
