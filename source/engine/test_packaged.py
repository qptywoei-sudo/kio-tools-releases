import json,subprocess,tempfile,shutil
from pathlib import Path
base=Path.cwd();tools=base/'work/mac/unified/GalaxyControl.app/Contents/Resources/tools';python=tools/'python/arm64/bin/python3';engine=tools/'engine/engine.py';directory=base/'work/engine/fixtures/packaged';directory.mkdir(exist_ok=True)
for language in ['ko','en','vi','ja','zh']:
 job={'op':'code_generate','kind':'qr','text':'GalaxyControl 가나다 local','language':language,'output_dir':str(directory)}
 temp=Path(tempfile.mkdtemp(prefix='GalaxyControl-test-'));f=temp/'job.json';r=temp/'result.json';f.write_text(json.dumps(job))
 result=subprocess.run([str(python),'-I','-B',str(engine),'--job',str(f),'--result',str(r)],capture_output=True)
 answer=json.loads(r.read_text());assert answer['success'],answer;assert answer['data']['text']==job['text'];assert Path(answer['files'][0]).stat().st_size>0
 print(language,answer['message']);shutil.rmtree(temp)
print('Packaged isolated runtime: 5-language results and exact Unicode QR contents passed')
