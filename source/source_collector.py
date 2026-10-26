"""Allowlisted native source and parsed standalone UI closure, never whole ADMIN trees."""
from pathlib import Path,PurePosixPath
import hashlib,json,os,re,subprocess,tempfile,zipfile

def checked_file(path,root):
 path=Path(path);root=Path(root).resolve()
 if not path.is_file() or not path.resolve().is_relative_to(root):raise ValueError('Source must be a plain contained file')
 for parent in (path,*path.parents):
  if parent.is_symlink():raise ValueError('Source symlink rejected')
  if parent==root:break
 name=path.name.lower()
 if name.startswith('.env') or name in ('files.json','device.json','settings.json','pairings.json','desktop-session.json','credentials.json','service-account.json','native-agent.log') or path.suffix.lower() in ('.pem','.p12','.pfx'):raise ValueError('Private source file rejected')
 data=path.read_bytes()
 if path.suffix in ('.py','.ts','.tsx','.js','.mjs','.json','.txt','.swift','.c','.cpp','.h'):
  if re.search(rb'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----',data) or re.search(rb'\b(?:sb_secret_[A-Za-z0-9_-]{20,}|sk-proj-[A-Za-z0-9_-]{25,})\b',data):raise ValueError('Private key marker rejected in source')
 return data

def collect_source_entries(work,repo,catalog,desktop_ui=None):
 if desktop_ui is not None:repo=desktop_ui
 work=Path(work).resolve();repo=Path(repo).resolve();entries={};provenance={}
 def add(path,name=None):
  path=Path(path);base=repo if path.is_relative_to(repo) else work;name=name or path.relative_to(base).as_posix()
  if base==repo:name=('desktop-ui/' if desktop_ui is not None else 'admin/')+name
  data=checked_file(path,base)
  if name in entries and entries[name]!=data:raise ValueError('Duplicate differing source member')
  entries[name]=data;provenance[name]={'source':path.relative_to(base).as_posix(),'sourceSHA256':hashlib.sha256(data).hexdigest()}
 for folder,patterns in [('release-tools',('*.py','*.md','*.ps1','release-config.example.json')),('agent',('*.py','protocol.json','api-shapes.json','operation-options.json','extension-origin.json','update-channel.json','ai-model-policy.json')),('engine',('*.py','*.json','requirements.txt')),('mac',('*.swift','*.sh','brand-app.py','KIOTools.icns')),('windows',('*.c','*.cpp','*.h','*.sh','*.nsi','*.rc','GalaxyControl.ico','GalaxyControl.png','BogoToolsStartup.png','KioRunning.gif','generate_app_icon.py','verify_app_icon.py','BrowserCaptureUpdate.py','CoreUpdate.py','translations-agent.json')),('browser-extension',('*.js','manifest.json','*.html','*.css','*.py','*.mjs')),('i18n',('native-bridge.json','messages.json'))]:
  for pattern in patterns:
   for file in sorted((work/folder).glob(pattern)):add(file)
 for folder in ('windows/include','windows/webview2','engine/licenses-agent'):
  for file in sorted((work/folder).glob('*')):
   if file.is_file() and file.suffix.lower() in ('.h','.hpp','.txt','.json'):add(file)
 for file in sorted((work/'browser-extension/_locales').rglob('*.json')):add(file)
 for file in sorted((work/'browser-extension/icons').glob('*.png')):add(file)
 test_names=('browser_extension_tests.mjs','browser_broker_tests.py','browser_owner_tests.py','upload_cache_tests.py','review_tests.py','test_local_system.py','search_index_tests.py','signature_library_tests.py','local_feature_routes_tests.py','source_collector_tests.py','native_cancel_tests.py','desktop_session_tests.py','desktop_ai_free_tests.py','desktop_single_ui_release_tests.py')
 if desktop_ui is not None:
  if (work/'integration-tests/kio_fixture.py').is_file():add(work/'integration-tests/kio_fixture.py')
  # Independent source ships its own current regression suite. The legacy
  # collector fixture requires an ADMIN checkout and remains in legacy mode only.
  test_names=tuple(name for name in test_names if name!='source_collector_tests.py')+('capture_copy_tests.py','capture_target_tests.py','ui_contract_tests.py','ui-contract-fixture.json','generate_ui_contract_fixture.cjs','batch_crop_tests.py','pdf_workspace_tests.mjs','pdf_workspace_engine_tests.py','barcode_catalog_tests.py','pdf_preview_cache_tests.py','recording_tests.py')
 test_names=tuple(sorted(set(test_names)|{p.name for p in (work/'integration-tests').glob('*_tests.py') if desktop_ui is None or p.name!='source_collector_tests.py'}))
 for folder,names in [('integration-tests',test_names),('nsis',('build_installer.py','build_browser_update.py','build_core_update.py'))]:
  for name in names:
   file=work/folder/name
   if file.is_file():add(file)
 if desktop_ui is not None:
  add(work/'integration-tests/desktop_source_isolation_tests.py')
  if (work/'integration-tests/legacy_update_security_v1.py').is_file():add(work/'integration-tests/legacy_update_security_v1.py')
  if (work/'mac/native-capture-tests.py').is_file():add(work/'mac/native-capture-tests.py')
  if (work/'mac/sign-local.py').is_file():add(work/'mac/sign-local.py')
 for font in sorted((work/'engine/fonts').glob('*')):
  if font.is_file() and font.suffix in ('.json','.py'):add(font)
 for model in sorted((work/'engine/models').glob('*')):
  if model.is_file() and (model.suffix in ('.json','.py') or model.name.endswith('-LICENSE') or model.name in ('u2netp.onnx','U2NET-LICENSE.txt','rembg-LICENSE.txt')):add(model)
 for name in (('build_approved_local_tools.py','source_collector.py','local_tools_source_graph.mjs','BRANDING.md','bogo-tools-artwork.json') if desktop_ui is not None else ('package_integrated.py','finalize_local_release.py','build_arch_mac.py','source_collector.py','local_tools_source_graph.mjs')):
  if (work/name).is_file():add(work/name)
 if desktop_ui is not None:
  graph=json.loads(subprocess.run(['node',str(work/'local_tools_source_graph.mjs'),str(repo),'vite.config.ts'],check=True,capture_output=True,text=True).stdout)
  for name in (*graph['files'],'package.json','package-lock.json','tsconfig.json','README.md'):add(repo/name)
  # Preserve the new vector original and inactive approved historical PNG.
  for artwork in ('src/assets/bogo-tools-master.svg','src/assets/kio-tools-icon.png'):add(repo/artwork)
  for file in sorted((repo/'qa').glob('*.cjs')):add(file)
  if (repo/'qa/README.md').is_file():add(repo/'qa/README.md')
  entries['BUILDING.txt']=b"Independent desktop UI: Node 22+; cd desktop-ui; npm ci; npm run typecheck; npm test; npm run build. No ADMIN checkout, credentials, remote server or deployment is required. Output defaults to desktop-ui/dist. Native Mac: sh mac/build-mac.sh on macOS with Xcode. Sign a completed local Mac app bundle after all resource changes with python3 mac/sign-local.py --setup /path/to/GalaxyControl.app; subsequent updates reuse that private local identity. The signing keychain stays outside this archive. Public distribution requires Apple-issued signing and notarization. Native Windows: sh windows/build-windows.sh with Zig 0.16. Python dependencies are listed in engine/requirements.txt and engine/agent-dependencies.json. Third-party corresponding-source archives and licenses remain alongside this archive in the portable payload. ADMIN source, backend, migrations, environment files, user uploads and private agent state are excluded.\n"
  entries['i18n/locales.json']=json.dumps(catalog,ensure_ascii=False,indent=2).encode()
  entries['COPYING']=b'GalaxyControl and additive local agent: GNU Affero General Public License version 3 or later. Dependency licenses and original corresponding sources are included alongside this archive.\n'
  manifest={'schemaVersion':2,'scope':'Independent desktop program corresponding source only','graph':graph,'requiresAdmin':False,'excludedTrees':['ADMIN','desktop-ui/public','desktop-ui/.env','desktop-ui/node_modules','private agent state'],'files':[{'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),**provenance.get(name,{'generated':True})} for name,data in sorted(entries.items())]}
  entries['SOURCE-MANIFEST.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
  return entries,manifest
 graph=json.loads(subprocess.run(['node',str(work/'local_tools_source_graph.mjs'),str(repo)],check=True,capture_output=True,text=True).stdout)
 for name in (*graph['files'],'package.json','package-lock.json','tsconfig.json'):add(repo/name)
 # Keep dependency/lock versions exact; only expose scripts that work in this closure.
 package=json.loads(entries['admin/package.json']);package['scripts']={'build':'tsc -p tsconfig.local-tools.json && vite build --config vite.local-tools.config.ts','typecheck':'tsc -p tsconfig.local-tools.json','dev':'vite --config vite.local-tools.config.ts','preview':'vite preview --config vite.local-tools.config.ts'}
 entries['admin/package.json']=(json.dumps(package,ensure_ascii=False,indent=2)+'\n').encode();provenance['admin/package.json']['generated']='Standalone scripts; original dependency+lock versions preserved'
 config=json.loads(entries['admin/tsconfig.json']);config['include']=['src','vite.local-tools.config.ts','scripts/local-tools-release-plugin.ts'];config['compilerOptions']['lib']=['ES2023','DOM','DOM.Iterable'];entries['admin/tsconfig.local-tools.json']=(json.dumps(config,indent=2)+'\n').encode()
 entries['admin/build-tools.mjs']=b"import {spawnSync} from 'node:child_process';\nfor(const args of [['run','typecheck'],['exec','vite','--','build','--config','vite.local-tools.config.ts']]){const result=spawnSync(process.platform==='win32'?'npm.cmd':'npm',args,{stdio:'inherit',env:{...process.env,LOCAL_TOOLS_OUT_DIR:process.env.LOCAL_TOOLS_OUT_DIR||'dist',ALLOW_PAID_GENERATION:'false'}});if(result.status!==0)process.exit(result.status||1);}\n"
 entries['BUILDING.txt']=b"Standalone UI: Node 22+; cd admin; npm ci; node build-tools.mjs. Output defaults to admin/dist. Native Mac: sh mac/build-mac.sh on macOS with Xcode. Native Windows: sh windows/build-windows.sh with Zig 0.16. Python dependencies are listed in engine/requirements.txt and engine/agent-dependencies.json. Third-party binary corresponding-source archives and licenses remain alongside this archive in the portable payload. ADMIN backend, workflows, migrations, environment files, user uploads and unrelated public files are deliberately excluded. No publishing or deployment command is included.\n"
 entries['i18n/locales.json']=json.dumps(catalog,ensure_ascii=False,indent=2).encode()
 entries['COPYING']=b'GalaxyControl and additive local agent: GNU Affero General Public License version 3 or later. Dependency licenses and original corresponding sources are included alongside this archive.\n'
 manifest={'schemaVersion':1,'scope':'Native plus actual standalone UI corresponding source only','graph':graph,'excludedTrees':['admin/public','admin/supabase','admin/n8n','admin/api','admin/backend','admin/output'],'files':[{'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),**provenance.get(name,{'generated':True})} for name,data in sorted(entries.items())]}
 entries['SOURCE-MANIFEST.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
 return entries,manifest

def write_source_bundle(work,repo,catalog,destination,desktop_ui=None):
 entries,manifest=collect_source_entries(work,repo,catalog,desktop_ui=desktop_ui);destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
 fd,temp=tempfile.mkstemp(prefix='.source-',suffix='.zip',dir=destination.parent);os.close(fd)
 try:
  with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as archive:
   for name,data in sorted(entries.items()):
    parts=PurePosixPath(name).parts
    if not parts or name.startswith('/') or any(part in ('.','..') for part in parts):raise ValueError('Unsafe source member')
    archive.writestr(name,data)
  with zipfile.ZipFile(temp) as archive:
   if archive.testzip() is not None:raise ValueError('Source ZIP CRC failure')
  os.replace(temp,destination)
 finally:Path(temp).unlink(missing_ok=True)
 return manifest
