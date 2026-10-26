"""Runs from a private copied Python runtime, after the app closes, with rollback."""
import json,os,sys,time,shutil,subprocess,plistlib,uuid,urllib.request,urllib.parse
from pathlib import Path

def alive(pid):
 if os.name=='nt':
  import ctypes
  k=ctypes.WinDLL('kernel32',use_last_error=True)
  k.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong];k.OpenProcess.restype=ctypes.c_void_p
  k.CloseHandle.argtypes=[ctypes.c_void_p];k.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
  h=k.OpenProcess(0x1000,False,pid)
  if not h:return ctypes.get_last_error()==5
  try:
   code=ctypes.c_ulong()
   # A process object can still be opened after exit while another program
   # retains its handle. Check execution state rather than handle existence.
   return not k.GetExitCodeProcess(h,ctypes.byref(code)) or code.value==259
  finally:k.CloseHandle(h)
 try:os.kill(pid,0);return True
 except ProcessLookupError:return False
 except PermissionError:return True

def close_owned_windows_tools(target):
 """Stop only persistent ADB executables inside this installation, never global names."""
 if os.name!='nt':return []
 import ctypes
 from ctypes import wintypes as w
 class Entry(ctypes.Structure):
  _fields_=[('dwSize',w.DWORD),('cntUsage',w.DWORD),('pid',w.DWORD),('heap',ctypes.c_size_t),('module',w.DWORD),('threads',w.DWORD),('parent',w.DWORD),('priority',w.LONG),('flags',w.DWORD),('exe',w.WCHAR*260)]
 k=ctypes.WinDLL('kernel32',use_last_error=True)
 k.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD];k.CreateToolhelp32Snapshot.restype=w.HANDLE
 k.Process32FirstW.argtypes=[w.HANDLE,ctypes.POINTER(Entry)];k.Process32NextW.argtypes=[w.HANDLE,ctypes.POINTER(Entry)]
 k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
 k.QueryFullProcessImageNameW.argtypes=[w.HANDLE,w.DWORD,w.LPWSTR,ctypes.POINTER(w.DWORD)]
 k.TerminateProcess.argtypes=[w.HANDLE,w.UINT];k.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD];k.CloseHandle.argtypes=[w.HANDLE]
 owned=(Path(target)/'tools/scrcpy/adb.exe').resolve()
 if not owned.is_relative_to(Path(target).resolve()):return []
 expected=os.path.normcase(str(owned));closed=[]
 snapshot=k.CreateToolhelp32Snapshot(2,0)
 if snapshot==ctypes.c_void_p(-1).value:raise OSError(ctypes.get_last_error(),'Process inventory failed')
 try:
  entry=Entry();entry.dwSize=ctypes.sizeof(entry);more=k.Process32FirstW(snapshot,ctypes.byref(entry))
  while more:
   if entry.exe.lower()=='adb.exe':
    handle=k.OpenProcess(0x1000|0x100000|1,False,entry.pid)
    if handle:
     try:
      size=w.DWORD(32768);path=ctypes.create_unicode_buffer(size.value)
      if k.QueryFullProcessImageNameW(handle,0,path,ctypes.byref(size)) and os.path.normcase(str(Path(path.value).resolve()))==expected:
       if k.WaitForSingleObject(handle,0)==258:
        if not k.TerminateProcess(handle,0) or k.WaitForSingleObject(handle,10000)!=0:raise ValueError('updateProgramBusy')
        closed.append(entry.pid)
     finally:k.CloseHandle(handle)
   more=k.Process32NextW(snapshot,ctypes.byref(entry))
 finally:k.CloseHandle(snapshot)
 return closed

def launch_program(target,platform):
 if platform=='Mac':return subprocess.Popen(['/usr/bin/open',str(target)],start_new_session=True)
 return subprocess.Popen([str(Path(target)/'KIOControl.exe')],cwd=target,creationflags=0x00000200|0x00000008)

def restore_program(target,backup,platform):
 target=Path(target);backup=Path(backup)
 if target.parent.resolve()!=backup.parent.resolve() or not backup.name.startswith(target.name+'.previous-') or backup.is_symlink():raise ValueError('updateTargetInvalid')
 failed=target.with_name(target.name+'.failed-'+uuid.uuid4().hex[:12]);target.rename(failed);moved=[]
 try:
  if platform=='Windows':
   managed={'KIOControl.exe','resources','tools','USB드라이버','START-HERE.txt','시작 안내.txt','FFMPEG-NOTICE.md'}
   for item in failed.iterdir():
    if item.name not in managed and not (backup/item.name).exists():shutil.move(str(item),str(backup/item.name));moved.append(item.name)
  backup.rename(target)
 except Exception:
  for name in moved:
   if (backup/name).exists():shutil.move(str(backup/name),str(failed/name))
  if not target.exists():failed.rename(target)
  raise
 return str(failed)

def wait_for_started_app(plan,process,timeout=90):
 """Require the relaunched native PID and expected authenticated local backend."""
 state=Path(plan['receipt']).parent.parent;deadline=time.monotonic()+timeout
 while time.monotonic()<deadline:
  try:
   native=json.loads((state/'bridge/status.json').read_text(encoding='utf-8'))
   session=json.loads((state/'desktop-session.json').read_text(encoding='utf-8'))
   if plan['platform']=='Windows' and native.get('pid')!=process.pid:raise ValueError('notReady')
   origin=session.get('origin','');url=urllib.parse.urlparse(origin)
   if url.scheme!='http' or url.hostname!='127.0.0.1' or not url.port or url.username or url.password or session.get('version')!=plan['version']:raise ValueError('notReady')
   request=urllib.request.Request(origin+'/health',headers={'Origin':origin,'X-Local-Agent-Token':session['token']})
   class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('notReady')
   with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(request,timeout=1) as response:health=json.loads(response.read(65536))
   if health.get('version')==plan['version'] and health.get('nativeReady') is True:return
  except (OSError,ValueError,KeyError):pass
  if plan['platform']=='Windows' and process.poll() is not None:raise ValueError('updateRestartFailed')
  time.sleep(.2)
 raise ValueError('updateRestartFailed')

def replace_program(staged,target,platform):
 staged=Path(staged);target=Path(target);suffix=str(int(time.time()))+'-'+uuid.uuid4().hex[:8];backup=target.with_name(target.name+'.previous-'+suffix)
 incoming=target.with_name(target.name+'.incoming-'+suffix)
 if not target.is_dir() or target.is_symlink() or incoming.exists() or backup.exists():raise ValueError('updateTargetInvalid')
 shutil.copytree(staged,incoming,symlinks=True)
 moved=[]
 try:
  target.rename(backup)
  if platform=='Windows':
   # Preserve portable user documents, credentials and edited configuration.
   managed={'KIOControl.exe','resources','tools','USB드라이버','START-HERE.txt','시작 안내.txt','FFMPEG-NOTICE.md'}
   for item in backup.iterdir():
    if item.name in managed:continue
    dest=incoming/item.name
    if dest.exists():
     if dest.is_dir():shutil.rmtree(dest)
     else:dest.unlink()
    shutil.move(str(item),str(dest));moved.append(item.name)
  incoming.rename(target)
 except Exception:
  for name in moved:
   src=incoming/name
   if src.exists():shutil.move(str(src),str(backup/name))
  if backup.exists() and not target.exists():backup.rename(target)
  raise
 return str(backup)

def main(plan_path):
 # Plans are emitted as UTF-8, independently of the Windows ANSI code page.
 # Decode before waiting or touching the installation; Korean Drive paths must
 # also work under the isolated embedded interpreter's default CP949 locale.
 plan_path=Path(plan_path);plan=json.loads(plan_path.read_text(encoding='utf-8-sig'));result=Path(plan['receipt'])
 def record(phase,**data):
  temporary=result.with_name('.'+result.name+'-'+str(os.getpid()))
  try:
   temporary.write_text(json.dumps({'phase':phase,'version':plan['version'],'helperId':plan_path.parent.name,'pid':os.getpid(),**data},ensure_ascii=False),encoding='utf-8')
   os.replace(temporary,result)
  finally:temporary.unlink(missing_ok=True)
 stage='waitingForExit';installed=False;process=None;backup=None
 try:
  record('waitingForExit')
  deadline=time.monotonic()+120
  while any(alive(pid) for pid in plan['pids']):
   if time.monotonic()>deadline:raise ValueError('updateCloseCancelled')
   time.sleep(.5)
  # Recheck the signed package hash before replacing any installed file.
  from update_security import digest,verified_manifest,extract_verified,platform_release
  payload=verified_manifest(plan['envelope'],plan['publicKey']);release=platform_release(payload,plan['platform']);package=release['package']
  if release['version']!=plan['version'] or digest(plan['archive'])!=package['sha256']:raise ValueError('updateInvalidSignature')
  stage='closingOwnedTools';record(stage,closedOwnedTools=close_owned_windows_tools(plan['target']) if plan['platform']=='Windows' else [])
  stage='extracting';record(stage)
  extracted=extract_verified(plan['archive'],plan_path.parent/'unpacked',package['root'])
  if plan['platform']=='Mac':
   apps=list(extracted.glob('*.app'))
   if len(apps)!=1:raise ValueError('updateTargetInvalid')
   staged=apps[0];info=plistlib.loads((staged/'Contents/Info.plist').read_bytes())
   if info.get('CFBundleIdentifier')!='local.galaxycontrol.portable' or info.get('CFBundleShortVersionString')!=plan['version']:raise ValueError('updateTargetInvalid')
   subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(staged)],check=True,capture_output=True)
  else:
   staged=extracted
   if not(staged/'KIOControl.exe').is_file() or not(staged/'tools/engine/agent/common.py').is_file():raise ValueError('updateTargetInvalid')
  stage='installing';record(stage);backup=replace_program(staged,plan['target'],plan['platform']);installed=True;record('installed',backup=backup)
  stage='restartingApp';record(stage,backup=backup);process=launch_program(plan['target'],plan['platform'])
  wait_for_started_app(plan,process);record('complete',backup=backup,reopened=True)
 except Exception as e:
  code=str(e) if str(e).startswith('update') else ('updateProgramBusy' if getattr(e,'winerror',None) in (5,32,33) else 'updateInstallFailed')
  reopened=False;restored=False
  if installed and backup:
   try:
    if process and process.poll() is None:process.terminate();process.wait(timeout=15)
    if plan['platform']=='Windows':close_owned_windows_tools(plan['target'])
    restore_program(plan['target'],backup,plan['platform']);restored=True;installed=False
   except Exception:pass
  if not installed and (Path(plan['target'])/('Contents/Info.plist' if plan['platform']=='Mac' else 'KIOControl.exe')).is_file():
   try:launch_program(plan['target'],plan['platform']);reopened=True
   except OSError:pass
  record('failed',error=code,failedStage=stage,errorType=type(e).__name__,winError=getattr(e,'winerror',None),reopened=reopened,restored=restored)
if __name__=='__main__':
 # Only the copies shipped by the current app are loaded, never an ambient Python install.
 sys.path.insert(0,str(Path(__file__).parent))
 sys.path.insert(0,str(Path(__file__).parent/'deps'))
 plan_file=Path(sys.argv[1]).resolve()
 # Also repair older callers that inherited the installed program's cwd.
 os.chdir(plan_file.parent)
 main(plan_file)
