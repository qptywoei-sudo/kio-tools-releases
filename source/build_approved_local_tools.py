"""Build the independent GalaxyControl program UI only.
No ADMIN checkout, browser secrets, public release config or ADMIN web build.
"""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,time
BASE=Path(__file__).resolve().parent
UI=BASE/'desktop-ui'
output=Path(os.environ.get('GALAXY_TOOLS_UI_OUT_DIR',str(BASE/'shared-tools/dist'))).resolve()
if not (UI/'package-lock.json').is_file():raise SystemExit('Missing independent desktop UI source')
npm=os.environ.get('GALAXY_TOOLS_NPM') or shutil.which('npm')
if not npm:raise SystemExit('Node.js and npm are required')
if not (UI/'node_modules/vite').exists():raise SystemExit('Run npm ci in work/desktop-ui first')
env={k:v for k,v in os.environ.items() if not k.startswith(('VITE_','SUPABASE_','VERCEL_','LOCAL_AGENT_'))}
env['GALAXY_TOOLS_UI_OUT_DIR']=str(output)
log=BASE/'shared-tools/qa/desktop-independent-build.log';log.parent.mkdir(parents=True,exist_ok=True)
with log.open('w') as handle:
 subprocess.run([npm,'run','build'],cwd=UI,env=env,check=True,stdout=handle,stderr=subprocess.STDOUT)
receipt={'built':True,'source':'independent GalaxyControl desktop-ui','version':json.loads((UI/'package.json').read_text())['version'],'desktopOnly':True,'adminWebBuilt':False,'outDir':str(output),'at':time.time(),'log':str(log),'entrySha256':hashlib.sha256((output/'index.html').read_bytes()).hexdigest()}
receipt_path=BASE/'integration-analysis/approved-current-build.json';receipt_path.parent.mkdir(parents=True,exist_ok=True);receipt_path.write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
