"""One post-update, same-parent bundle rename; no data, auth or identity migration.

The normal backend prepares this only after the ORIGINAL signed updater has
completed. A detached copy waits for every owned process to exit normally.
No force signal, global app lookup, preference reset, overwrite or resigning.
"""
from __future__ import annotations
import ctypes,hashlib,json,os,plistlib,re,shutil,stat,subprocess,sys,time,uuid
from pathlib import Path

BUNDLE_ID='local.galaxycontrol.portable'
SIGNER_SHA1='72287f8a5048cd206db014ead6723c75cd459379'
PUBLIC_KEY='JjeL9t/8GSrh2XZ25gawQyI475nXr/rU0li4CoEnfos='
class MigrationError(Exception):pass

def require(value,code):
 if not value:raise MigrationError(code)

def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()

def atomic_json(path,value):
 path=Path(path);temporary=path.with_name('.'+path.name+'-'+uuid.uuid4().hex)
 fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 try:
  with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
  os.replace(temporary,path)
 finally:temporary.unlink(missing_ok=True)

def plain(path,directory=False,private=False):
 path=Path(path);value=path.lstat()
 require(not stat.S_ISLNK(value.st_mode) and (stat.S_ISDIR(value.st_mode) if directory else stat.S_ISREG(value.st_mode)),'nameMigrationUnsafePath')
 require(value.st_uid==os.getuid()==os.geteuid() and value.st_mode&0o022==0,'nameMigrationOwner')
 if private and directory:require(value.st_mode&0o077==0,'nameMigrationPrivateDirectory')
 return value

def private_json(path):
 path=Path(path);plain(path)
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as f:
  st=os.fstat(f.fileno());require(st.st_uid==os.getuid() and stat.S_ISREG(st.st_mode),'nameMigrationOwner')
  raw=f.read(1024*1024+1)
 require(len(raw)<=1024*1024,'nameMigrationPlanBound')
 value=json.loads(raw.decode('utf-8-sig'));require(isinstance(value,dict),'nameMigrationPlanInvalid');return value

def bundle_layout(app,version):
 app=Path(app)
 require(sys.platform=='darwin' and app.is_absolute() and app==app.resolve() and app.name=='KIO Tools.app','nameMigrationLegacyPath')
 st=plain(app,True);parent=app.parent;parent_st=parent.lstat()
 require(stat.S_ISDIR(parent_st.st_mode) and not stat.S_ISLNK(parent_st.st_mode) and parent_st.st_uid in (0,os.getuid()) and parent_st.st_mode&0o002==0 and os.access(parent,os.W_OK|os.X_OK),'nameMigrationParent')
 require(not os.path.lexists(app.with_name('Bogo Tools.app')),'nameMigrationCollision')
 info=app/'Contents/Info.plist';plain(info);plain(app/'Contents/MacOS/KIOControl')
 value=plistlib.loads(info.read_bytes())
 require(value.get('CFBundleIdentifier')==BUNDLE_ID and value.get('CFBundleName')==value.get('CFBundleDisplayName')=='Bogo Tools' and value.get('CFBundleShortVersionString')==version and value.get('CFBundleExecutable')=='KIOControl','nameMigrationForeignBundle')
 return {'device':st.st_dev,'inode':st.st_ino,'uid':st.st_uid,'parentDevice':parent_st.st_dev,'parentInode':parent_st.st_ino}

def requirement_matches(code,stdout):
 require(code==0 and isinstance(stdout,str) and len(stdout)<=16384,'nameMigrationSignature')
 lines=[x.strip() for x in stdout.splitlines() if x.strip().startswith('designated')]
 require(len(lines)==1,'nameMigrationSignature')
 match=re.fullmatch(r'designated\s*=>\s*identifier\s+"([^"\r\n]+)"\s+and\s+certificate\s+leaf\s*=\s*H"([a-fA-F0-9]{40})"',lines[0])
 require(match is not None and match[1]==BUNDLE_ID and match[2].lower()==SIGNER_SHA1,'nameMigrationSignature')

def verify_signature(app):
 run=subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(app)],capture_output=True,timeout=90)
 require(run.returncode==0,'nameMigrationSignature')
 run=subprocess.run(['/usr/bin/codesign','-d','-r-',str(app)],capture_output=True,text=True,timeout=30)
 requirement_matches(run.returncode,run.stdout)

def fingerprint(app):
 app=Path(app);rows={}
 for path in app.rglob('*'):
  value=path.lstat();relative=path.relative_to(app).as_posix()
  if stat.S_ISREG(value.st_mode):content=digest(path)
  elif stat.S_ISLNK(value.st_mode):content=hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()
  elif stat.S_ISDIR(value.st_mode):continue
  else:raise MigrationError('nameMigrationSpecialFile')
  rows[relative]=[value.st_dev,value.st_ino,value.st_size,value.st_mode,content]
 return rows

def atomic_rename(source,target):
 source,target=Path(source),Path(target)
 require(sys.platform=='darwin' and source.parent==target.parent,'nameMigrationRenameUnsupported')
 # Public Darwin SDK sys/stdio.h: RENAME_EXCL=0x4. No overwrite fallback.
 parent=os.open(source.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:
  libc=ctypes.CDLL(None,use_errno=True);rename=libc.renameatx_np
  rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint];rename.restype=ctypes.c_int
  if rename(parent,os.fsencode(source.name),parent,os.fsencode(target.name),4)!=0:
   code=ctypes.get_errno();raise OSError(code,os.strerror(code))
 finally:os.close(parent)

def alive(pid):
 require(type(pid) is int and pid>1,'nameMigrationPid')
 try:os.kill(pid,0);return True
 except ProcessLookupError:return False
 except PermissionError:return True

def wait_for_pids(pids,timeout=120,alive=alive):
 require(pids and all(type(p) is int and p>1 for p in pids),'nameMigrationPid')
 deadline=time.monotonic()+timeout
 while any(alive(pid) for pid in pids):
  require(time.monotonic()<deadline,'nameMigrationExitCancelled');time.sleep(.1)

def bundle_pids(app):
 """Read executable identity only; never send a signal to another app."""
 require(sys.platform=='darwin','nameMigrationProcessIdentity')
 library=ctypes.CDLL('/usr/lib/libproc.dylib',use_errno=True)
 library.proc_listallpids.argtypes=[ctypes.c_void_p,ctypes.c_int];library.proc_listallpids.restype=ctypes.c_int
 library.proc_pidpath.argtypes=[ctypes.c_int,ctypes.c_void_p,ctypes.c_uint];library.proc_pidpath.restype=ctypes.c_int
 count=library.proc_listallpids(None,0);require(0<count<100000,'nameMigrationProcessIdentity')
 capacity=count+256;buffer=(ctypes.c_int*capacity)();actual=library.proc_listallpids(buffer,ctypes.sizeof(buffer))
 require(0<=actual<capacity,'nameMigrationProcessIdentity')
 expected=os.fsencode(Path(app)/'Contents/MacOS/KIOControl');found=[]
 for pid in buffer[:actual]:
  path=ctypes.create_string_buffer(4096)
  if pid>1 and library.proc_pidpath(pid,path,len(path))>0 and path.value==expected:found.append(pid)
 return found

def transaction_fields(receipt,plan,app,version,path):
 app,path=Path(app),Path(path)
 require(receipt.get('phase')=='complete' and receipt.get('reopened') is True and receipt.get('version')==version,'nameMigrationUpdaterNotComplete')
 require(type(receipt.get('pid')) is int and receipt['pid']>1 and isinstance(receipt.get('helperId'),str) and re.fullmatch(r'install-[a-f0-9]{32}',receipt['helperId']),'nameMigrationUpdaterIdentity')
 require(plan.get('target')==str(app) and plan.get('platform')=='Mac' and plan.get('version')==version and plan.get('receipt')==str(path),'nameMigrationUpdaterTarget')
 backup=Path(receipt.get('backup',''))
 require(backup.parent==app.parent and backup.name.startswith(app.name+'.previous-'),'nameMigrationUpdaterTarget')

def transaction(state,app,version,public_key):
 state=Path(state);updates=state/'updates';plain(state,True,True);plain(updates,True,True)
 path=updates/'last-install.json';receipt=private_json(path)
 helper=updates/str(receipt.get('helperId',''));require(helper.parent==updates,'nameMigrationUpdaterIdentity');plain(helper,True,True)
 plan=private_json(helper/'plan.json');transaction_fields(receipt,plan,app,version,path)
 require(public_key==PUBLIC_KEY and plan.get('publicKey')==public_key,'nameMigrationUpdateKey')
 from update_security import verified_manifest,platform_release
 payload=verified_manifest(plan['envelope'],public_key);release=platform_release(payload,'Mac')
 require(release['version']==version and release['package']['root']=='KIO-Control-Mac','nameMigrationUpdateSignature')
 require(not alive(receipt['pid']),'nameMigrationUpdaterStillRunning')
 return {'helperId':receipt['helperId'],'helperPid':receipt['pid'],'receiptSha256':digest(path),'planSha256':digest(helper/'plan.json')}

def retarget_startup(source,target,path=None):
 path=Path(path) if path is not None else Path.home()/'Library/LaunchAgents/local.galaxycontrol.login.plist'
 if not os.path.lexists(path):return 'absent'
 require(path.is_absolute() and path.parent==path.parent.resolve(),'nameMigrationStartupPath')
 plain(path.parent,True)
 plain(path);value=plistlib.loads(path.read_bytes());args=value.get('ProgramArguments')
 if value.get('Label')!='local.galaxycontrol.login' or not isinstance(args,list) or '-a' not in args:return 'foreign-unchanged'
 index=args.index('-a')+1
 if index>=len(args) or args[index]!=str(source):return 'foreign-unchanged'
 updated=dict(value);updated['ProgramArguments']=list(args);updated['ProgramArguments'][index]=str(target)
 temporary=path.with_name('.'+path.name+'-'+uuid.uuid4().hex);fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,stat.S_IMODE(path.stat().st_mode))
 try:
  with os.fdopen(fd,'wb') as f:f.write(plistlib.dumps(updated));f.flush();os.fsync(f.fileno())
  plain(path);os.replace(temporary,path)
 finally:temporary.unlink(missing_ok=True)
 return 'owned-path-updated'

def default_state():return Path.home()/'Library/Application Support/GalaxyControl/Agent'

def execute(plan_path):
 plan_path=Path(plan_path)
 require(plan_path.is_absolute() and not plan_path.is_symlink() and plan_path.parent==plan_path.parent.resolve(),'nameMigrationPlanPath')
 plain(plan_path.parent,True,True);plan=private_json(plan_path)
 state=Path(plan['state']);require(state==default_state().resolve() and plan_path.parent.parent==state/'updates','nameMigrationState')
 result=state/'updates/bogo-name-migration.json';source=Path(plan['source']);target=source.with_name('Bogo Tools.app');version=plan['version'];moved=False;validated=False
 def record(phase,**data):atomic_json(result,{'phase':phase,'version':version,'helperId':plan_path.parent.name,'pid':os.getpid(),'source':str(source),'target':str(target),'transactionHelperId':plan['transaction']['helperId'],**data})
 try:
  require(plan['target']==str(target),'nameMigrationTarget')
  require(bundle_layout(source,version)==plan['identity'],'nameMigrationBundleChanged');verify_signature(source);validated=True
  authorized=transaction(state,source,version,PUBLIC_KEY);require(authorized==plan['transaction'],'nameMigrationTransactionChanged')
  record('waitingForExit');wait_for_pids(plan['pids'])
  require(bundle_layout(source,version)==plan['identity'],'nameMigrationBundleChanged');verify_signature(source)
  require(transaction(state,source,version,PUBLIC_KEY)==authorized,'nameMigrationTransactionChanged')
  require(not bundle_pids(source),'nameMigrationAppStillRunning')
  before=fingerprint(source);record('renaming')
  atomic_rename(source,target);moved=True
  require(fingerprint(target)==before and target.lstat().st_ino==plan['identity']['inode'],'nameMigrationFilesChanged');verify_signature(target)
  startup=retarget_startup(source,target)
  opened=subprocess.run(['/usr/bin/open',str(target)],capture_output=True,timeout=30)
  require(opened.returncode==0 or bool(bundle_pids(target)),'nameMigrationReopenFailed')
  proof=hashlib.sha256(json.dumps(sorted(before.items()),separators=(',',':')).encode('utf-8')).hexdigest()
  record('complete',source=str(source),target=str(target),fileCount=len(before),fileIdsAndBytesPreserved=True,fileTreeIdentitySha256=proof,directoryIdentity=plan['identity'],startup=startup,reopened=True,transactionHelperId=authorized['helperId'])
 except Exception as error:
  restored=False
  # Failed launch/metadata/permissions restore the old name with the same
  # exclusive primitive, only while no app is using either name. Never kill or
  # move an independently reopened process or overwrite a new collision.
  if moved:
   try:
    require(not bundle_pids(target) and not os.path.lexists(source),'nameMigrationRollbackBusy')
    require(target.lstat().st_ino==plan['identity']['inode'],'nameMigrationBundleChanged')
    atomic_rename(target,source);restored=True;moved=False
    retarget_startup(target,source)
   except Exception:pass
  failure={'error':str(error) if isinstance(error,MigrationError) else 'nameMigrationFailed','renamed':moved,'restored':restored,'source':str(source),'target':str(target),'originalBytesRetained':True}
  record('failed',**failure)
  if validated and not moved:
   try:
    verify_signature(source)
    if not bundle_pids(source):
     opened=subprocess.run(['/usr/bin/open',str(source)],capture_output=True,timeout=30)
     record('failed',**failure,reopenedOld=opened.returncode==0)
   except Exception:pass
  return False
 return True

def prepare_and_quit(agent,updates,engine,version,config):
 """Runs in the REAL new backend only; never during source tests/Windows."""
 if sys.platform!='darwin':return
 engine=Path(engine).resolve();app=engine.parents[3]
 if app.name!='KIO Tools.app':return
 state=Path(agent.state).resolve()
 if state!=default_state().resolve():return
 status=Path(updates)/'bogo-name-migration.json';deadline=time.monotonic()+180
 try:
  while not agent.stopping.wait(.5):
   if time.monotonic()>deadline:return
   try:authorized=transaction(state,app,version,config.get('publicKey'))
   except (OSError,ValueError,KeyError,MigrationError):continue
   previous=private_json(status) if status.is_file() else {}
   if previous.get('version')==version and previous.get('source')==str(app) and previous.get('transactionHelperId')==authorized['helperId']:
    if previous.get('phase') in ('complete','failed'):return
    if type(previous.get('pid')) is int and previous['pid']>1 and alive(previous['pid']):continue
   health=agent.health()
   if health.get('activeJobs',1)>0 or health.get('recording') is True or getattr(agent.ai,'active',False):continue
   native=agent.bridge.status();pid=native.get('pid');require(type(pid) is int and pid>1,'nameMigrationPid')
   identity=bundle_layout(app,version);verify_signature(app)
   folder=Path(updates)/('name-migration-'+uuid.uuid4().hex);folder.mkdir(mode=0o700)
   arch='arm64' if __import__('platform').machine()=='arm64' else 'x86_64'
   shutil.copytree(engine.parent/'python'/arch,folder/'python',symlinks=True)
   for name in ('mac_bundle_migration.py','update_security.py'):shutil.copy2(Path(__file__).with_name(name),folder/name)
   deps=folder/'deps';deps.mkdir(mode=0o700)
   for pattern in ('cryptography','_cffi_backend*','cffi'):
    for path in (engine/'deps-agent'/arch).glob(pattern):
     if path.is_dir():shutil.copytree(path,deps/path.name)
     else:shutil.copy2(path,deps/path.name)
   atomic_json(folder/'plan.json',{'state':str(state),'source':str(app),'target':str(app.with_name('Bogo Tools.app')),'version':version,'identity':identity,'transaction':authorized,'pids':[pid,os.getpid()]})
   child=subprocess.Popen([str(folder/'python/bin/python3'),'-I','-B','-X','utf8',str(folder/'mac_bundle_migration.py'),str(folder/'plan.json')],cwd=folder,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
   ready=time.monotonic()+15
   while time.monotonic()<ready:
    if child.poll() is not None:raise MigrationError('nameMigrationHelperFailed')
    value=private_json(status) if status.is_file() else {}
    if value.get('phase')=='waitingForExit' and value.get('pid')==child.pid and value.get('helperId')==folder.name:
     agent.bridge.call('app.quit',{},10);return
    time.sleep(.1)
   raise MigrationError('nameMigrationHelperNotReady')
 except Exception as error:
  atomic_json(status,{'phase':'failed','version':version,'source':str(app),'target':str(app.with_name('Bogo Tools.app')),'transactionHelperId':authorized.get('helperId') if 'authorized' in locals() else None,'error':str(error) if isinstance(error,MigrationError) else 'nameMigrationFailed','renamed':False,'originalBytesRetained':True})

if __name__=='__main__':
 sys.path[:0]=[str(Path(__file__).parent),str(Path(__file__).parent/'deps')]
 if sys.platform!='darwin':raise SystemExit('Mac only')
 raise SystemExit(0 if execute(Path(sys.argv[1])) else 1)
