"""Desktop-only signed GitHub release checker/downloader; signed packages, explicit restart."""
import json,os,sys,time,threading,shutil,subprocess,urllib.request,urllib.error,urllib.parse,http.cookiejar,re,uuid
from pathlib import Path
from html.parser import HTMLParser
from common import AgentError,VERSION,read_json,atomic_json,private_dir
from update_security import version,verified_manifest,digest,allowed_url,platform_release

class SafeRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  if not allowed_url(newurl):raise ValueError('updateNetwork')
  return super().redirect_request(req,fp,code,msg,headers,newurl)
class DownloadForm(HTMLParser):
 def __init__(self):super().__init__();self.action='';self.fields={};self.active=False
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag=='form' and attrs.get('id')=='download-form':self.action=attrs.get('action','');self.active=True
  if self.active and tag=='input' and attrs.get('type')=='hidden' and attrs.get('name'):self.fields[attrs['name']]=attrs.get('value','')
 def handle_endtag(self,tag):
  if tag=='form':self.active=False

def download_response(url):
 if not allowed_url(url):raise ValueError('updateInvalidManifest')
 opener=urllib.request.build_opener(SafeRedirect(),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
 response=opener.open(urllib.request.Request(url,headers={'User-Agent':'KIO-Control-Updater/'+VERSION}),timeout=30)
 # Drive's own large-file confirmation is parsed only for a signed, pinned download URL.
 if 'text/html' in response.headers.get('Content-Type',''):
  page=response.read(1024*1024);response.close();form=DownloadForm();form.feed(page.decode(errors='replace'))
  if not form.action or not allowed_url(form.action) or urllib.parse.urlparse(form.action).hostname!='drive.usercontent.google.com':raise ValueError('updateDriveAccess')
  response=opener.open(form.action+'?'+urllib.parse.urlencode(form.fields),timeout=30)
  if 'text/html' in response.headers.get('Content-Type',''):response.close();raise ValueError('updateDriveAccess')
 return response

def install_layout(engine,windows=False,machine=None):
 engine=Path(engine);arch='win64' if windows else ('arm64' if (machine or __import__('platform').machine())=='arm64' else 'x86_64')
 return engine.parents[1] if windows else engine.parents[3], engine.parent/'python' if windows else engine.parent/'python'/arch, arch

def wait_helper_ready(process,receipt,helper_id,release_version,timeout=10):
 # Do not close the application until its independent installer has actually
 # started. A stale receipt from a different installer cannot authorize exit.
 deadline=time.monotonic()+timeout
 while time.monotonic()<deadline:
  if process.poll() is not None:raise ValueError('updateInstallFailed')
  value=read_json(receipt,{})
  if value.get('helperId')==helper_id and value.get('version')==release_version and value.get('pid')==process.pid:
   if value.get('phase')=='waitingForExit':return
   if value.get('phase')=='failed':raise ValueError('updateInstallFailed')
  time.sleep(.05)
 raise ValueError('updateInstallFailed')

class Updater:
 def __init__(self,agent):
  self.agent=agent;self.lock=threading.RLock();self.root=private_dir(agent.state/'updates');self.config=read_json(Path(__file__).with_name('update-channel.json'),{});self.preferences=read_json(self.root/'preferences.json',{'autoCheck':True});self.envelope=None;self.package=None;self.archive=None
  self.value={'currentVersion':VERSION,'latestVersion':None,'available':False,'phase':'idle','received':0,'total':0,'error':'','checkedAt':None,'notes':[],'autoCheck':self.preferences.get('autoCheck',True),'configured':bool(self.config.get('feedUrl'))}
  self.receipt=self.root/'last-install.json'
 def status(self):
  with self.lock:
   r=dict(self.value);receipt=read_json(self.receipt,{})
   if receipt.get('phase')=='failed' and self.value['phase']=='restarting':r.update(phase='error',error=receipt.get('error','updateInstallFailed'))
   try:newer_failure=receipt.get('phase')=='failed' and version(receipt.get('version','0.0.0'))>version(VERSION)
   except (ValueError,TypeError):newer_failure=False
   if newer_failure:r['lastFailure']={k:receipt[k] for k in ('version','error','failedStage','reopened') if k in receipt}
   return r
 def auto_loop(self):
  if self.agent.stopping.wait(15):return
  while not self.agent.stopping.is_set():
   if self.preferences.get('autoCheck',True) and self.value['phase'] not in ('ready','preparing','restarting'):
    try:self.start('check')
    except AgentError:pass
   self.agent.stopping.wait(24*3600)
 def preferences_update(self,body):
  if set(body)!={'autoCheck'} or type(body['autoCheck']) is not bool:raise AgentError('invalidRequest')
  with self.lock:self.preferences=body;self.value['autoCheck']=body['autoCheck'];atomic_json(self.root/'preferences.json',body)
  return self.status()
 def start(self,action):
  with self.lock:
   if self.value['phase'] in ('checking','downloading','preparing','restarting'):raise AgentError('busy')
   if action not in ('check','download'):raise AgentError('invalidRequest')
   if action=='download' and not(self.value['available'] and self.package):raise AgentError('updateNotAvailable')
   self.value.update(phase='checking' if action=='check' else 'downloading',error='',received=0)
   threading.Thread(target=self._run,args=(action,),daemon=True).start()
  return self.status()
 def _run(self,action):
  try:
   if action=='check':
    if not self.config.get('feedUrl'):raise ValueError('updateNotConfigured')
    with download_response(self.config['feedUrl']) as r:data=r.read(512*1024+1)
    if len(data)>512*1024:raise ValueError('updateInvalidManifest')
    envelope=json.loads(data);payload=verified_manifest(envelope,self.config['publicKey']);platform='Windows' if os.name=='nt' else 'Mac';release=platform_release(payload,platform)
    available=version(release['version'])>version(VERSION);cached_ready=None
    if available:
     # A verified failed-install download can be reused after app recovery.
     for cached in sorted(self.root.glob('download-*/release.zip'),key=lambda p:p.stat().st_mtime,reverse=True)[:10]:
      try:matches=cached.stat().st_size==release['package']['size'] and digest(cached)==release['package']['sha256']
      except OSError:matches=False
      if matches:cached_ready=cached;break
    with self.lock:
     self.envelope=envelope;self.package=release['package'];self.archive=cached_ready;self.value.update(phase='ready' if cached_ready else ('available' if available else 'current'),latestVersion=release['version'],available=available,checkedAt=int(time.time()),notes=release['notes'],total=self.package['size'])
   else:
    package=dict(self.package);folder=private_dir(self.root/('download-'+uuid.uuid4().hex));target=folder/'release.zip'
    if shutil.disk_usage(self.root).free<package['size']*4+500_000_000:raise ValueError('updateDiskSpace')
    with download_response(package['url']) as r,target.open('xb') as out:
     received=0
     while True:
      block=r.read(1024*1024)
      if not block:break
      received+=len(block)
      if received>package['size']:raise ValueError('updateInvalidSignature')
      out.write(block)
      with self.lock:self.value['received']=received
    if target.stat().st_size!=package['size'] or digest(target)!=package['sha256']:raise ValueError('updateInvalidSignature')
    with self.lock:self.archive=target;self.value['phase']='ready'
  except Exception as e:
   error=str(e) if str(e).startswith('update') else 'updateNetwork'
   with self.lock:self.value.update(phase='error',error=error)
 def install(self):
  with self.lock:
   if self.value['phase']!='ready' or not self.archive:raise AgentError('updateNotReady')
   if self.agent.health().get('recording') or any(j['status'] in ('queued','running') for j in self.agent.jobs.values()) or self.agent.ai.active:raise AgentError('busy')
   native=read_json(self.agent.state/'bridge/status.json',{});pid=native.get('pid')
   if type(pid) is not int or pid<=1:raise AgentError('nativeUnavailable')
   root=Path(__file__).resolve().parent
   engine=root.parent;target,runtime,arch=install_layout(engine,os.name=='nt')
   if os.name!='nt' and target.suffix!='.app':raise AgentError('updateTargetInvalid')
   helper=private_dir(self.root/('install-'+uuid.uuid4().hex))
   if not runtime.is_dir() or not os.access(target.parent,os.W_OK):raise AgentError('updateTargetInvalid')
   self.receipt.unlink(missing_ok=True)
   self.value['phase']='preparing'
  try:
   shutil.copytree(runtime,helper/'python',symlinks=True)
   shutil.copy2(root/'update_helper.py',helper/'update_helper.py');shutil.copy2(root/'update_security.py',helper/'update_security.py')
   deps=private_dir(helper/'deps')
   for pattern in ('cryptography','_cffi_backend*','cffi'):
    for p in (engine/'deps-agent'/arch).glob(pattern):
     if p.is_dir():shutil.copytree(p,deps/p.name)
     else:shutil.copy2(p,deps/p.name)
   plan={'archive':str(self.archive),'target':str(target),'platform':'Windows' if os.name=='nt' else 'Mac','version':self.value['latestVersion'],'pids':[pid,os.getpid()],'receipt':str(self.receipt),'publicKey':self.config['publicKey'],'envelope':self.envelope}
   atomic_json(helper/'plan.json',plan)
   python=helper/'python'/('python.exe' if os.name=='nt' else 'bin/python3')
   flags={'creationflags':0x00000008|0x00000200|0x01000000} if os.name=='nt' else {'start_new_session':True}
   # Windows keeps a process working directory open. The installer must run
   # outside the program directory that it is about to rename and replace.
   process=subprocess.Popen([str(python),'-I','-B','-X','utf8',str(helper/'update_helper.py'),str(helper/'plan.json')],cwd=helper,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**flags)
   try:wait_helper_ready(process,self.receipt,helper.name,plan['version'])
   except Exception:
    if process.poll() is None:
     process.terminate()
     try:process.wait(timeout=5)
     except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
    atomic_json(self.receipt,{'phase':'failed','version':plan['version'],'helperId':helper.name,'error':'updateInstallFailed'})
    raise
   with self.lock:self.value['phase']='restarting'
   threading.Thread(target=self._quit,daemon=True).start();return self.status()
  except Exception:
   with self.lock:self.value.update(phase='error',error='updateInstallFailed')
   raise AgentError('updateInstallFailed') from None
 def _quit(self):
  time.sleep(1)
  try:self.agent.bridge.call('app.quit',{},10)
  except Exception:
   with self.lock:self.value.update(phase='error',error='updateCloseCancelled')
