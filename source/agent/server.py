"""ADMIN Local Agent. Loopback-only authenticated typed API over existing GalaxyControl engines."""
from __future__ import annotations
import argparse,hashlib,hmac,json,mimetypes,os,platform,queue,re,secrets,socket,sqlite3,stat,sys,threading,time,uuid,subprocess,shutil,signal
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,unquote,urlencode
from concurrent.futures import ThreadPoolExecutor
_engine_dir=Path(__file__).resolve().parent.parent
if not (_engine_dir/'engine.py').is_file():_engine_dir=_engine_dir/'engine'
sys.path.insert(0,str(_engine_dir))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import engine
_arch={'arm64':'arm64','aarch64':'arm64','x86_64':'x86_64','AMD64':'win64'}.get(platform.machine(),'win64')
_deps=Path(engine.__file__).parent/'deps-agent'/_arch
if not _deps.is_dir():_deps=Path(engine.__file__).resolve().parents[2]/'tools'/'engine'/'deps-agent'/_arch
if _deps.is_dir():sys.path.insert(0,str(_deps))
from common import AgentError,NativeBridge,VERSION,LANGUAGES,atomic_json,read_json,private_dir,valid_id,utc
from signature_library import SignatureLibrary
from index import LazyFileIndex,contained
from rename import Renamer
from process_group import spawn
from phone import PhoneControls,OPERATIONS as PHONE_OPERATIONS
from google_drive import GoogleDrive
from storage_library import StorageLibrary
from ai_translate import AITranslate
from updater import Updater
from kio_cloud_drive import KIOCloudDrive
from kio_account import KIOAccount,CLOUD_ORIGIN
from language import LanguagePreference, normalize as normalize_language, text as language_text
def standalone_origin(origin,port):
    return origin in {f'http://127.0.0.1:{port}',f'http://localhost:{port}'} or re.fullmatch(r'chrome-extension://[a-p]{32}',origin) is not None

MAX_BODY=2*1024*1024;MAX_UPLOAD=256*1024*1024
MAX_REGISTERED_FILES=20000;MAX_REGISTRY_BYTES=16*1024*1024;MAX_UPLOAD_FILES=10000
UPLOAD_CACHE_AGE=7*24*3600
DESKTOP_SESSION_FILE='desktop-session.json'
DESKTOP_SESSION_MAX_BYTES=4096
ENGINE_OPS={'image_export','image_process','image_edit','image_split','image_background','image_retouch','image_mosaic','canvas_export','signature_apply','pdf_merge','pdf_extract','pdf_manage','images_pdf','pdf_render','pdf_info','pdf_annotate','pdf_split','pdf_docx','pdf_pptx','pdf_xlsx','code_generate','code_read','video_gif','video_edit'}
NATIVE_JOBS={'capture','record_start','record_pause','record_resume','record_stop','record_gif','editor_open','phone_open','web_capture'}
FORBIDDEN_KEYS={'path','paths','input','inputs','output_dir','outputDir','fontPath','modelPath','executable','command','shell','cwd','environment'}
def safe_options(value,depth=0):
    if depth>12:raise AgentError('invalidRequest')
    if isinstance(value,dict):
        if len(value)>100 or any(k in FORBIDDEN_KEYS for k in value):raise AgentError('invalidRequest')
        for v in value.values():safe_options(v,depth+1)
    elif isinstance(value,list):
        if len(value)>10000:raise AgentError('invalidRequest')
        for v in value:safe_options(v,depth+1)
    elif isinstance(value,str):
        if len(value)>100000:raise AgentError('invalidRequest')
    elif value is not None and not isinstance(value,(int,float,bool)):raise AgentError('invalidRequest')

def validate_web_options(options,owner,browser_owner):
    if not isinstance(options,dict) or set(options)-{'format','split','url','maxHeight','captureRequestId','captureTarget'}:raise AgentError('invalidRequest')
    if options.get('format','png') not in ('png','jpg','pdf') or type(options.get('split',False)) is not bool:raise AgentError('invalidRequest')
    if 'maxHeight' in options and (type(options['maxHeight']) is not int or not 100<=options['maxHeight']<=30000):raise AgentError('invalidRequest')
    if options.get('url'):
        url=options['url']
        if not isinstance(url,str) or len(url)>6000:raise AgentError('invalidRequest')
        parsed=urlparse(url)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:raise AgentError('invalidRequest')
    if 'captureRequestId' in options or 'captureTarget' in options:
        if not isinstance(owner,str) or not owner.startswith('chrome-extension://') or owner!=browser_owner:raise AgentError('unauthorized',403)
        if not valid_id(options.get('captureRequestId')):raise AgentError('invalidRequest')
        target=options.get('captureTarget')
        if not isinstance(target,dict) or set(target)!={'id','windowId','url'} or any(type(target.get(k)) is not int or target[k]<0 for k in ('id','windowId')):raise AgentError('invalidRequest')
        url=target['url']
        if not isinstance(url,str) or len(url)>6000 or urlparse(url).scheme not in ('http','https') or not urlparse(url).hostname:raise AgentError('invalidRequest')


def private_desktop_session_write(state,value):
    """Native-only credential file. Never follow a replaced file or directory."""
    state=Path(state);path=state/DESKTOP_SESSION_FILE;temporary='.'+DESKTOP_SESSION_FILE+'-'+uuid.uuid4().hex
    data=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    if len(data)>DESKTOP_SESSION_MAX_BYTES:raise AgentError('invalidRequest')
    def checked_target(info):
        if not stat.S_ISREG(info.st_mode) or (os.name!='nt' and info.st_uid!=os.getuid()) or (getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0)):
            raise AgentError('unsafePath')
    directory=None;temp_path=state/temporary
    try:
        if os.name!='nt':
            directory=os.open(state,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            info=os.fstat(directory)
            if info.st_uid!=os.getuid() or not stat.S_ISDIR(info.st_mode):raise AgentError('unsafePath')
            os.fchmod(directory,0o700)
            try:checked_target(os.stat(DESKTOP_SESSION_FILE,dir_fd=directory,follow_symlinks=False))
            except FileNotFoundError:pass
            fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
        else:
            if state.is_symlink() or (getattr(state.lstat(),'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0)):raise AgentError('unsafePath')
            try:checked_target(path.lstat())
            except FileNotFoundError:pass
            fd=os.open(temp_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        if directory is not None:
            try:checked_target(os.stat(DESKTOP_SESSION_FILE,dir_fd=directory,follow_symlinks=False))
            except FileNotFoundError:pass
            os.replace(temporary,DESKTOP_SESSION_FILE,src_dir_fd=directory,dst_dir_fd=directory)
            os.fsync(directory)
        else:
            try:checked_target(path.lstat())
            except FileNotFoundError:pass
            os.replace(temp_path,path)
    finally:
        if directory is not None:
            try:os.unlink(temporary,dir_fd=directory)
            except FileNotFoundError:pass
            os.close(directory)
        else:temp_path.unlink(missing_ok=True)


class Agent:
 def __init__(self,state,ui_dir,port=4323,origins=(),native_pid=0):
    self.state=private_dir(state);self.ui_dir=Path(ui_dir).resolve();self.port=port;self.bridge=NativeBridge(self.state,native_pid)
    defaults=[f'http://127.0.0.1:{port}',f'http://localhost:{port}']
    env=os.environ.get('ADMIN_LOCAL_ALLOWED_ORIGINS','').split(',')
    extension=read_json(Path(__file__).parent/'extension-origin.json',{}).get('origin')
    requested=set(x.rstrip('/') for x in (*defaults,*env,*origins,extension) if x)
    if any(x=='*' or not self.valid_origin(x) for x in requested):raise AgentError('forbiddenOrigin')
    # Standalone tools accept only their own loopback UI and approved browser
    # capture extensions. Legacy ADMIN pairings are kept but cannot authorize.
    self.origins={x for x in requested if standalone_origin(x,port)}
    self.lock=threading.RLock();self.listeners=[];self.jobs={};self.job_owners={};self.browser=None;self.browser_commands=queue.Queue(maxsize=4);self.web_waiters={}
    self.stopping=threading.Event();self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='local-job');self.jobs_limit=threading.BoundedSemaphore(8)
    self.upload_reserved=0;self.upload_reserved_files=0;self.active_inputs={}
    identity=read_json(self.state/'device.json',{})
    if not valid_id(identity.get('deviceId')):
        identity={'deviceId':str(uuid.uuid4()),'deviceName':socket.gethostname(),'os':'Windows' if os.name=='nt' else 'macOS' if sys.platform=='darwin' else platform.system()};atomic_json(self.state/'device.json',identity)
    self.identity=identity
    self.tokens=read_json(self.state/'pairings.json',{})
    self.desktop_session=self.bootstrap_desktop_session()
    self.desktop_origin=self.desktop_session['origin']
    self.desktop_digest=hashlib.sha256(self.desktop_session['token'].encode()).hexdigest()
    self.settings_path=self.state/'settings.json';self.settings_initialized=self.settings_path.exists()
    self.language_preference=LanguagePreference(self.state)
    self.settings=read_json(self.settings_path,{'language':'en','autoStart':False,'saveFolder':str(Path.home()/'Pictures'/'GalaxyControl'),'shortcuts':{'areaCapture':'Control+Shift+F9' if os.name=='nt' else 'Control+Shift+A','fullCapture':'','webCapture':'','recordToggle':''}})
    self.settings['language']=self.language_preference.snapshot()['language']
    # Add defaults without replacing any existing user settings or pairings.
    self.settings.setdefault('closeAfterCaptureCopy',True)
    self.settings.setdefault('openCaptureEditor',True)
    self.settings.setdefault('captureFormat','png')
    self.settings.setdefault('saveMode','local')
    self.account=KIOAccount(self.state)
    self.settings['language']=self.language_state()['language']
    self.account.language_provider=lambda: self.language_state()['language']
    self.drive=KIOCloudDrive(self.state,self.account);self.storage=StorageLibrary(self.state,self.settings,self.drive);self.ai=AITranslate(self.state,self.bridge)
    self.storage.retry()
    private_dir(self.state/'uploads');private_dir(self.state/'tasks')
    self.files=read_json(self.state/'files.json',{},maximum=MAX_REGISTRY_BYTES)
    if not isinstance(self.files,dict):self.files={}
    self.last_upload_cleanup=time.monotonic();self.cleanup_uploads()
    # File-search tools were removed from KIO. Keep legacy records available to
    # explicitly requested file APIs without scanning old roots during startup.
    self.index=LazyFileIndex(self.state,self.emit,background=False);self.signatures=SignatureLibrary(self.state,self.resolve,self.register);self.renamer=Renamer(self.resolve);self.phone=PhoneControls(self)
    self.profile_user_id=None
    self.signals_thread=threading.Thread(target=self.signals,daemon=True);self.signals_thread.start()
    self.updater=Updater(self)
    threading.Thread(target=self.updater.auto_loop,daemon=True).start()
 def language_state(self):
    user=self.account.status().get('user') or {}
    return self.language_preference.snapshot(user.get('locale'))
 def bootstrap_desktop_session(self):
    # Only the owning native host reads this private file and injects it into
    # its own /tools WebView. No HTTP route returns it or auto-approves a site.
    origin=f'http://127.0.0.1:{self.port}'
    path=self.state/DESKTOP_SESSION_FILE
    try:
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or (os.name!='nt' and info.st_uid!=os.getuid()) or (getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0)):raise AgentError('unsafePath')
    except FileNotFoundError:pass
    previous=read_json(path,{},maximum=DESKTOP_SESSION_MAX_BYTES)
    keep=isinstance(previous,dict) and previous.get('origin')==origin and previous.get('deviceId')==self.identity['deviceId'] and previous.get('ownerId')=='desktop' and previous.get('clientName')=='GalaxyControl' and isinstance(previous.get('token'),str) and re.fullmatch(r'[A-Za-z0-9_-]{32,256}',previous['token']) is not None
    session={'token':previous['token'] if keep else secrets.token_urlsafe(48),'deviceId':self.identity['deviceId'],'origin':origin,'ownerId':'desktop','clientName':'GalaxyControl','version':VERSION}
    private_desktop_session_write(self.state,session)
    return session
 @staticmethod
 def valid_origin(value):
    u=urlparse(value)
    return u.scheme in ('http','https','chrome-extension') and bool(u.hostname) and not u.username and not u.password and u.path in ('','/') and not u.query and not u.fragment
 def device(self):return {**self.identity,'architecture':'arm64' if platform.machine().lower() in ('arm64','aarch64') else 'x86_64','version':VERSION,'status':'connected','lastSeen':utc(),'capabilities':self.capabilities(),'operations':self.operations(),'nativeReady':self.bridge.ready()}
 def operations(self):
    ops=set(ENGINE_OPS)
    try:import engine_extra
    except ImportError:ops-=ENGINE_OPS-{'image_process','pdf_merge','pdf_extract','pdf_manage','images_pdf','pdf_render','pdf_info','pdf_annotate','code_generate','code_read'}
    if sys.platform=='darwin':
        major=int(platform.mac_ver()[0].split('.')[0] or 0)
        if major<13:ops.discard('video_gif')
        if major<(14 if platform.machine()=='x86_64' else 13):ops.discard('image_retouch')
    if self.bridge.ready():
        ops|=NATIVE_JOBS
        if self.phone.available():ops|=PHONE_OPERATIONS
        if sys.platform=='darwin' and int(platform.mac_ver()[0].split('.')[0] or 0)<13:ops-= {'record_start','record_pause','record_resume','record_stop','record_gif'}
    return sorted(ops)
 def capabilities(self):
    out=['files','image','pdf','qr','barcode']
    if self.bridge.ready():
        out+=['capture','fullPageCapture','globalShortcuts','phone','clipboard']
        if 'record_start' in self.operations():out.append('record')
    return out
 def browser_install_info(self):
    folder=Path(engine.__file__).parent.parent/'browser-extension';manifest=folder/'manifest.json'
    if folder.is_symlink() or folder.is_junction() or not manifest.is_file() or manifest.is_symlink():raise AgentError('fileMissing',404)
    data=read_json(manifest,{},maximum=65536);name=data.get('name') if isinstance(data,dict) else None
    if not isinstance(name,str) or not name.strip() or len(name)>256 or any(ord(char)<32 for char in name):raise AgentError('fileMissing',404)
    if name.startswith('__MSG_'):
        message=re.fullmatch(r'__MSG_([A-Za-z0-9_]{1,80})__',name)
        if not message:raise AgentError('fileMissing',404)
        language=self.settings.get('language');language={'zh':'zh_CN','zh-CN':'zh_CN','zh-TW':'zh_TW'}.get(language,language)
        name=None;locales=folder/'_locales'
        if locales.is_symlink() or locales.is_junction():raise AgentError('fileMissing',404)
        for locale in (language,data.get('default_locale')):
            if not isinstance(locale,str) or not re.fullmatch(r'[A-Za-z0-9_]{1,32}',locale):continue
            locale_dir=locales/locale;messages=locale_dir/'messages.json'
            if locale_dir.is_symlink() or locale_dir.is_junction() or messages.is_symlink():continue
            translations=read_json(messages,{},maximum=262144)
            entry=translations.get(message[1]) if isinstance(translations,dict) else None
            translated=entry.get('message') if isinstance(entry,dict) else None
            if isinstance(translated,str) and translated.strip() and len(translated)<=256 and not any(ord(char)<32 for char in translated) and not translated.startswith('__MSG_'):
                name=translated;break
        if name is None:raise AgentError('fileMissing',404)
    return {'folderPath':str(folder.resolve()),'extensionName':name}
 def browser_ready(self):
    # A heartbeat only proves the extension exists. Capture commands require a
    # live, authenticated event receiver, including after a worker restart.
    with self.lock:
        return bool(self.browser and time.time()-self.browser['lastSeen']<45 and self.browser['origin'] in self.tokens and any(owner==self.browser['origin'] for owner,_ in self.listeners))
 def emit_browser_state(self,owner):
    with self.lock:
        if not self.browser or self.browser['origin']!=owner:return
        event={'type':'browser','connected':self.browser_ready(),'browser':self.browser.get('browser')}
    # ADMIN refreshes /browser after this event. Never publish while holding
    # the listener mutation lock, and ignore another extension's old stream.
    self.emit(event)
 def health(self):
    native=self.bridge.status() if self.bridge.ready() else {}
    return {**self.device(),'connected':True,'recording':native.get('recording') is True,'paused':native.get('recording') is True and native.get('paused') is True,'monitors':native.get('monitors',[]),'recordingOptions':{'microphone':sys.platform=='darwin' and int(platform.mac_ver()[0].split('.')[0] or 0)>=15,'systemAudio':sys.platform=='darwin' and int(platform.mac_ver()[0].split('.')[0] or 0)>=13,'formats':['mp4'],'fpsMin':5,'fpsMax':60},'activeJobs':sum(j['status'] in ('queued','running') for j in self.jobs.values()),'browserConnected':self.browser_ready()}
 @staticmethod
 def startup_snapshot(snapshot):
    if not isinstance(snapshot,dict):return {}
    value={}
    if isinstance(snapshot.get('autoStart'),bool):value['autoStart']=snapshot['autoStart']
    if snapshot.get('autoStartStatus') in ('enabled','disabled','blocked','repair','error'):value['autoStartStatus']=snapshot['autoStartStatus']
    return value
 def public_settings(self):
    native=self.bridge.status().get('settings',{}) if self.bridge.ready() else {}
    return {k:v for k,v in self.settings.items() if k not in ('saveFolder','localSaveFolder')}|{'saveFolderName':Path(self.settings.get('localSaveFolder') or self.settings['saveFolder']).name}|self.startup_snapshot(native)
 def emit(self,event,owner=None):
    event={**event,'type':event.get('type','update')}
    with self.lock:
        listeners=list(self.listeners)
    for o,q in listeners:
        if owner is None or o==owner:
            try:q.put_nowait(event)
            except queue.Full:pass
 def native_owner(self,fallback):
    return self.desktop_origin
 def authenticate(self,origin,token):
    digest=hashlib.sha256(token.encode()).hexdigest() if token else ''
    with self.lock:r=self.tokens.get(origin)
    extension=re.fullmatch(r'chrome-extension://[a-p]{32}',origin or '') is not None
    standard=extension and isinstance(r,dict) and hmac.compare_digest(str(r.get('digest','')),digest)
    desktop=origin==self.desktop_origin and hmac.compare_digest(self.desktop_digest,digest)
    if not standard and not desktop:raise AgentError('unauthorized',401)
    if origin==CLOUD_ORIGIN:raise AgentError('unauthorized',401)
    return origin
 def require_account(self):
    user=self.account.require()
    # Bind pre-account local artifacts once, and retain the binding thereafter.
    # A different login on this installation cannot read the first user's files.
    with self.lock:
        if self.profile_user_id==user['id']:return user
        path=self.state/'kio-account'/'legacy-owner.json'
        previous=read_json(path,{})
        if not previous.get('userId'):
            atomic_json(path,{'userId':user['id']});previous={'userId':user['id']}
        changed=False
        for row in self.files.values():
            if isinstance(row,dict) and not row.get('accountId'):
                row['accountId']=previous['userId'];changed=True
        if changed:atomic_json(self.state/'files.json',self.files)
        if self.profile_user_id!=user['id']:
            # Preserve the first account's existing ChatGPT/signature settings;
            # later identities get separate profiles on the same OS account.
            if self.profile_user_id is not None or previous['userId']!=user['id']:
                self.ai.clear();self.ai.account.cancel()
                profile=self.state if previous['userId']==user['id'] else private_dir(self.state/'account-profiles'/user['id'])
                self.ai=AITranslate(profile,self.bridge);self.signatures=SignatureLibrary(profile,self.resolve,self.register)
                old_storage=self.storage;old_storage.close()
                if old_storage.worker is not None and old_storage.worker is not threading.current_thread():old_storage.worker.join(timeout=2)
                self.storage=StorageLibrary(profile,self.settings,self.drive)
                self.index.close();self.index=LazyFileIndex(profile,self.emit,background=False,private_state=self.state)
                # Every account's index excludes the entire agent state tree,
                # including other identities' credentials and temporary data.
                # LazyFileIndex runs this broader private cleanup before the
                # first legacy query, without opening the database at login.
            self.profile_user_id=user['id']
            self.ai.account.bind_kio(self.account,user['id'])
            threading.Thread(target=self.storage.retry,daemon=True).start()
    return user
 def dispatch_shortcut(self,body):
    if not isinstance(body,dict) or set(body)-{'action'} or not isinstance(body.get('action'),str) or body.get('action') not in {'areaCapture','fullCapture','webCapture','recordToggle','recordArea','aiTranslate'}:raise AgentError('invalidRequest')
    if not self.account.status()['signedIn']:return {'destination':'login'}
    self.require_account()
    return {'destination':'desktop'}
 def pair(self,origin,name):
    if re.fullmatch(r'chrome-extension://[a-p]{32}',origin or '') is None:raise AgentError('forbiddenOrigin',403)
    self.bridge.approve(origin,name);token=secrets.token_urlsafe(48)
    with self.lock:
        self.tokens[origin]={'digest':hashlib.sha256(token.encode()).hexdigest(),'createdAt':utc(),'clientName':str(name)[:80]};atomic_json(self.state/'pairings.json',self.tokens)
    return {'token':token,'device':self.device()}
 def revoke(self,owner):
    with self.lock:self.tokens.pop(owner,None);atomic_json(self.state/'pairings.json',self.tokens)
    self.emit_browser_state(owner)
    return {'revoked':True}
 def private_control_file(self,path):
    try:parts=Path(path).resolve().relative_to(self.state).parts
    except ValueError:return False
    except OSError:return True
    # Opaque uploaded/generated image files remain usable. Credentials, job
    # instructions, diagnostics and library manifests never become artifacts.
    if len(parts)>=3 and parts[0]=='uploads' and valid_id(parts[1]):return False
    if len(parts)>=4 and parts[0]=='tasks' and valid_id(parts[1]) and parts[2]=='outputs':return False
    if len(parts)==4 and parts[:2]==('library','cache') and valid_id(parts[2]):return False
    if len(parts)==2 and parts[0]=='signatures' and parts[1].endswith('.png'):return False
    if len(parts)==4 and parts[0]=='account-profiles' and valid_id(parts[1]) and parts[2]=='signatures' and parts[3].endswith('.png'):
        user=self.account.status().get('user') or {}
        return parts[1]!=user.get('id')
    if len(parts)==6 and parts[0]=='account-profiles' and valid_id(parts[1]) and parts[2:4]==('library','cache') and valid_id(parts[4]):
        user=self.account.status().get('user') or {}
        return parts[1]!=user.get('id')
    return True
 def register(self,path,owner,kind='artifact',name=None,expected_account=None):
    p=Path(path)
    if self.private_control_file(p) or (kind=='native' and contained(p,self.state)):raise AgentError('forbiddenFile',403)
    if not contained(p,p.parent) or not p.is_file():raise AgentError('fileMissing',404)
    user=self.require_account()
    if expected_account is not None and user['id']!=expected_account:raise AgentError('accountChanged',409)
    ident=str(uuid.uuid4());r={'path':str(p.resolve()),'owner':owner,'kind':kind,'name':name or p.name,'created':time.time(),'accountId':user['id']}
    with self.lock:
        if kind=='upload' and self.tile_upload_name(owner,r['name']) and not any(waiter['owner']==owner for waiter in self.web_waiters.values()):raise AgentError('cancelled',409)
        if len(self.files)>=MAX_REGISTERED_FILES:raise AgentError('storageFull',507)
        candidate={**self.files,ident:r}
        if len(json.dumps(candidate,ensure_ascii=False).encode('utf-8'))>MAX_REGISTRY_BYTES:raise AgentError('storageFull',507)
        atomic_json(self.state/'files.json',candidate);self.files[ident]=r
        if kind=='upload' and self.tile_upload_name(owner,r['name']):
            for waiter in self.web_waiters.values():
                if waiter['owner']==owner:waiter['uploads'].add(ident)
    return self.file_info(ident)
 @staticmethod
 def tile_upload_name(owner,name):return isinstance(owner,str) and owner.startswith('chrome-extension://') and re.fullmatch(r'tile-[0-9]{1,3}\.png',name) is not None
 def remove_uploads(self,ids,owner):
    # Only known private upload copies may be deleted. Native originals, saved
    # artifacts, aliases used by another active job and every symlink are kept.
    root=self.state/'uploads';changed=False
    with self.lock:
        active={p for paths in self.active_inputs.values() for p in paths}
        originals={other.get('path') for other in self.files.values() if isinstance(other,dict) and other.get('kind')!='upload'}
        for ident in set(ids):
            r=self.files.get(ident)
            if not isinstance(r,dict) or r.get('kind')!='upload' or r.get('owner')!=owner:continue
            p=Path(r.get('path',''))
            if not p.is_absolute() or not contained(root,self.state) or not contained(p,root) or len(p.relative_to(root).parts)!=2 or not valid_id(p.parent.name) or str(p) in active:continue
            if str(p) in originals:continue
            directory=None
            try:
                if os.name!='nt':
                    # Open every directory without following a replaced ancestor.
                    directory=os.open(p.anchor,os.O_RDONLY|os.O_DIRECTORY)
                    for part in p.parts[1:-1]:
                        nextdir=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory);os.close(directory);directory=nextdir
                    info=os.stat(p.name,dir_fd=directory,follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid():continue
                    os.unlink(p.name,dir_fd=directory)
                else:
                    if not stat.S_ISREG(p.lstat().st_mode):continue
                    p.unlink()
            except FileNotFoundError:pass
            except OSError:continue
            finally:
                if directory is not None:os.close(directory)
            self.files.pop(ident,None);changed=True
            try:
                if contained(p.parent,root):p.parent.rmdir()
            except OSError:pass
        if changed:atomic_json(self.state/'files.json',self.files)
 def cleanup_uploads(self,now=None):
    cutoff=(time.time() if now is None else now)-UPLOAD_CACHE_AGE
    with self.lock:
        by_owner={}
        for ident,r in self.files.items():
            if isinstance(r,dict) and r.get('kind')=='upload' and isinstance(r.get('owner'),str) and isinstance(r.get('created'),(int,float)) and r['created']<cutoff:
                by_owner.setdefault(r['owner'],[]).append(ident)
        for owner,ids in by_owner.items():self.remove_uploads(ids,owner)
        self.last_upload_cleanup=time.monotonic()
 def file_info(self,ident):
    r=self.files[ident];p=Path(r['path']);return {'id':ident,'name':r['name'],'size':p.stat().st_size,'mime':mimetypes.guess_type(r['name'])[0] or 'application/octet-stream'}
 def artifact_history(self,owner,cursor=''):
    user=self.require_account()
    with self.lock:
        rows=[(ident,row.copy()) for ident,row in self.files.items() if isinstance(row,dict) and row.get('accountId')==user['id'] and row.get('kind') in ('artifact','recording') and (row.get('owner')==owner or {row.get('owner'),owner}<={self.desktop_origin,CLOUD_ORIGIN})]
    rows.sort(key=lambda item:(item[1].get('created',0),item[0]),reverse=True)
    if cursor:
        positions=[i for i,(ident,_) in enumerate(rows) if ident==cursor]
        if not valid_id(cursor) or not positions:raise AgentError('invalidRequest')
        rows=rows[positions[0]+1:]
    files=[];next_cursor='';seen=set()
    for index,(ident,row) in enumerate(rows):
        try:
            path=self.resolve(ident,owner)
            if str(path) in seen:continue
            seen.add(str(path));files.append({**self.file_info(ident),'modified':row.get('created',0)*1000})
        except (AgentError,OSError):continue
        if len(files)==100:
            if index+1<len(rows):next_cursor=ident
            break
    return {'files':files,'nextCursor':next_cursor}
 def resolve(self,ident,owner=None):
    if not valid_id(ident):raise AgentError('invalidRequest')
    with self.lock:r=self.files.get(ident)
    if r:
        user=self.require_account()
        if r.get('accountId')!=user['id']:raise AgentError('unauthorized',403)
        if owner is not None and r['owner']!=owner and not {owner,r['owner']}<={self.desktop_origin,CLOUD_ORIGIN}:raise AgentError('unauthorized',403)
        p=Path(r['path'])
        if self.private_control_file(p):raise AgentError('forbiddenFile',403)
        if not contained(p,p.parent) or not p.is_file():raise AgentError('fileMissing',404)
        # Every input/output came from native chooser, an owned upload or generated artifact.
        return p
    return self.index.resolve(ident)
 def register_inputs(self,paths,owner):
    if not isinstance(paths,list) or len(paths)>1000:raise AgentError('invalidRequest')
    return [self.register(p,owner,'native') for p in paths]
 def latest_recording(self,owner):
    # Keep this owner-scoped metadata out of the public health response. Older
    # releases registered native recordings as generic artifacts.
    with self.lock:
        user=self.require_account()
        candidates=[(ident,row.copy()) for ident,row in self.files.items() if isinstance(row,dict) and row.get('accountId')==user['id'] and (row.get('owner')==owner or {row.get('owner'),owner}<={self.desktop_origin,CLOUD_ORIGIN}) and (row.get('kind')=='recording' or (row.get('kind')=='artifact' and re.fullmatch(r'Recording-\d{8}-\d{6}-[A-Fa-f0-9]{8}\.mp4',row.get('name',''))))]
    for ident,row in sorted(candidates,key=lambda item:item[1].get('created',0),reverse=True):
        try:
            self.resolve(ident,owner)
            file=self.file_info(ident)
            if file['mime'].startswith('video/'):return file
        except (AgentError,OSError,KeyError):continue
    return None
 def clean_data(self,data):
    if isinstance(data,dict):return {k:self.clean_data(v) for k,v in data.items() if k not in {'path','paths','input','output','outputs','output_dir'}}
    if isinstance(data,list):return [self.clean_data(x) for x in data]
    if isinstance(data,str) and (data.startswith('/') or re_windows_path(data)):return Path(data).name
    return data
 def submit(self,body,owner):
    user=self.require_account()
    op=body.get('operation');inputs=body.get('inputs',[]);options=body.get('options',{})
    if op not in self.operations() or op in PHONE_OPERATIONS:raise AgentError('unsupported')
    if not isinstance(inputs,list) or len(inputs)>1000 or not isinstance(options,dict):raise AgentError('invalidRequest')
    safe_options(options)
    if op=='capture':
        if options.get('mode','area') not in ('area','full','window'):raise AgentError('invalidRequest')
        monitor=options.get('monitor',-1)
        if type(monitor) is not int or not -1<=monitor<10000:raise AgentError('invalidRequest')
        if options.get('format','png') not in ('png','jpg'):raise AgentError('invalidRequest')
    for flag,allowed in (('previewOnly',{'pdf_render','pdf_info','image_process','image_background','video_edit'}),):
        if flag in options and (op not in allowed or type(options[flag]) is not bool):raise AgentError('invalidRequest')
    if op=='video_edit':
        from video_editor import validate
        try:validate({**options,'inputs':inputs})
        except (ValueError,TypeError):raise AgentError('invalidRequest') from None
    if op=='web_capture':validate_web_options(options,owner,self.browser.get('origin') if self.browser else None)
    if op=='record_gif' and len(inputs)>1:raise AgentError('invalidRequest')
    ident=str(uuid.uuid4());job={'id':ident,'operation':op,'status':'queued','progress':0,'errorCode':'','result':None,'createdAt':utc(),'accountId':user['id']}
    if op in {'pdf_render','pdf_info','image_process','image_background','video_edit'} and options.get('previewOnly') is True:job['previewOnly']=True
    with self.lock:
        paths=[str(self.resolve(x,owner)) for x in inputs]
        if not self.jobs_limit.acquire(blocking=False):raise AgentError('busy',429)
        self.active_inputs[ident]=set(paths)
        # Keep a bounded recent history without evicting active jobs.
        terminal=[key for key,value in self.jobs.items() if value['status'] not in ('queued','running')]
        for key in terminal[:-120]:self.jobs.pop(key,None);self.job_owners.pop(key,None)
        self.jobs[ident]=job;self.job_owners[ident]=owner
    self.emit({'type':'job','job':job.copy()},owner)
    try:self.pool.submit(self.execute,ident,op,paths,options,owner)
    except RuntimeError:
        with self.lock:self.active_inputs.pop(ident,None);job.update(status='failed',errorCode='busy')
        self.jobs_limit.release();raise AgentError('busy',503)
    return {'job':job.copy()}
 def execute(self,ident,op,paths,options,owner):
    job=self.jobs[ident]
    def progress(value):
        if job['status']=='cancelled' or not self.account.status()['signedIn'] or job.get('accountId')!=self.account.user['id']:raise AgentError('cancelled')
        job['progress']=max(job['progress'],min(99,int(value)));self.emit({'type':'job','job':job.copy()},owner)
    try:
        if job['status']=='cancelled' or not self.account.status()['signedIn'] or job.get('accountId')!=self.account.user['id']:return
        job['status']='running';progress(1)
        native={'capture':'capture.start','record_start':'record.start','record_pause':'record.pause','record_resume':'record.resume','record_stop':'record.stop','editor_open':'editor.open','phone_open':'phone.open'}
        if op in native:
            args=options.copy()
            if op=='editor_open':
                if not paths:raise AgentError('inputMissing')
                args={'path':paths[0]}
            if op=='capture':
                args={'mode':options.get('mode','area'),'monitor':options.get('monitor',-1)}
                result=self.bridge.call(native[op],args,600,cancel=lambda:job['status']=='cancelled')
            else:result=self.bridge.call(native[op],args,90)
            result={'files':result.get('paths',[]),'data':{k:v for k,v in result.items() if k!='paths'}}
        elif op=='record_gif':
            # Conversion is independent of the recorder. Stopping an already
            # finished session fails, and must never discard its saved MP4.
            if not paths:
                recording=self.latest_recording(owner)
                if not recording:raise AgentError('inputMissing')
                paths=[str(self.resolve(recording['id'],owner))]
                with self.lock:self.active_inputs[ident]=set(paths)
            result=self.engine_job('video_gif',paths,options,progress)
        elif op=='web_capture':result=self.web_capture(ident,options,owner,progress)
        else:result=self.engine_job(op,paths,options,progress)
        if job['status']=='cancelled' or not self.account.status()['signedIn'] or job.get('accountId')!=self.account.user['id']:return
        if result.get('success') is False:raise AgentError('processingFailed')
        cache_only=(op=='image_edit' and options.get('clipboardOnly') is True) or (op in {'pdf_render','pdf_info','image_process','image_background','video_edit'} and options.get('previewOnly') is True)
        if not cache_only and result.get('files'):
            generated=list(result['files']);published,storage_info=self.storage.publish(generated,op)
            result={**result,'files':published,'data':{**result.get('data',{}),'storage':storage_info}}
            # Native captures and recordings are generated artifacts, not user inputs.
            # Relocate the fresh file after all requested durable copies are prepared.
            if op in ('capture','record_stop') or all(contained(Path(p),self.state/'uploads') for p in generated):
                for value in generated:
                    source=Path(value)
                    if str(source) not in published:
                        try:source.unlink()
                        except OSError:pass
        files=[self.register(p,owner,'upload' if cache_only else 'recording' if op=='record_stop' else 'artifact',expected_account=job['accountId']) for p in result.get('files',[])]
        job.update(status='complete',progress=100,result={'files':files,'data':self.clean_data(result.get('data',{}))})
    except AgentError as e:
        if job['status']!='cancelled':job.update(status='cancelled' if e.code=='cancelled' else 'failed',errorCode=e.code)
    except Exception:
        if job['status']!='cancelled':job.update(status='failed',errorCode='processingFailed')
        # No paths, file text, pairing token or raw exception leak into web logs.
    finally:
        with self.lock:self.active_inputs.pop(ident,None)
        self.jobs_limit.release();self.emit({'type':'job','job':job.copy()},owner)
 def engine_job(self,op,paths,options,progress):
    clipboard_only=options.get('clipboardOnly') is True
    preview_only=options.get('previewOnly') is True
    if 'previewOnly' in options and (op not in {'pdf_render','pdf_info','image_process','image_background','video_edit'} or type(options['previewOnly']) is not bool):raise AgentError('invalidRequest')
    if 'clipboardOnly' in options and (op!='image_edit' or not isinstance(options['clipboardOnly'],bool)):raise AgentError('invalidRequest')
    task=private_dir(self.state/'tasks'/str(uuid.uuid4()));out=private_dir(task/'outputs')
    job={**{k:v for k,v in options.items() if k not in ('clipboardOnly','previewOnly')},'operation':op,'op':op,'inputs':paths,'paths':paths,'output_dir':str(out),'language':self.settings.get('language','en')}
    if paths:job['path']=paths[0]
    request=task/'job.json';atomic_json(request,job);answer=None;error=None
    command=[sys.executable,'-I','-B',str(Path(__file__).parent/'job_runner.py'),str(request)]
    creation={ 'creationflags':subprocess.CREATE_NO_WINDOW } if os.name=='nt' else {'start_new_session':True}
    process=spawn(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',**creation)
    messages=queue.Queue(maxsize=100)
    def read():
        for line in process.stdout:
            if len(line)>4_000_000:continue
            try:messages.put(json.loads(line),timeout=1)
            except (ValueError,queue.Full):pass
    threading.Thread(target=read,daemon=True).start();deadline=time.monotonic()+(3600 if op=='video_edit' else 600)
    try:
        size_check=time.monotonic()
        while process.poll() is None or not messages.empty():
            if time.monotonic()>deadline:raise AgentError('timeout',504)
            if time.monotonic()-size_check>2:
                if sum(p.stat().st_size for p in out.iterdir() if p.is_file())>2*1024**3:raise AgentError('storageFull',507)
                size_check=time.monotonic()
            progress(10)
            try:m=messages.get(timeout=.2)
            except queue.Empty:continue
            if 'progress'in m:progress(m['progress'])
            if 'result'in m:answer=m['result']
            if 'errorCode'in m:error=m['errorCode']
        # Drain final buffered worker output if the process exited before the reader delivered it.
        for _ in range(10):
            try:m=messages.get(timeout=.05)
            except queue.Empty:break
            if 'result'in m:answer=m['result']
            if 'errorCode'in m:error=m['errorCode']
        if error:raise AgentError(error)
        if not isinstance(answer,dict) or answer.get('success') is False:raise AgentError('processingFailed')
        if len(answer.get('files',[]))>10000:raise AgentError('fileTooLarge')
        if sum(p.stat().st_size for p in out.iterdir() if p.is_file())>2*1024**3:raise AgentError('storageFull',507)
        files=[]
        for value in answer.get('files',[]):
            source=Path(value)
            if not contained(source,out) or not source.is_file():raise AgentError('processingFailed')
            # Temporary clipboard and PDF previews use the owned cache until normal expiry.
            if clipboard_only or preview_only:
                cache=private_dir(self.state/'uploads'/str(uuid.uuid4()))
                destination=cache/source.name
                shutil.copyfile(source,destination)
                destination.chmod(0o600)
            else:
                cache=private_dir(self.state/'uploads'/str(uuid.uuid4()))
                destination=cache/source.name
                shutil.copyfile(source,destination)
            files.append(str(destination))
        return {**answer,'files':files}
    finally:
        if process.poll() is None:process.terminate_tree(timeout=2)
        if process.stdout:process.stdout.close()
        process.close()
        shutil.rmtree(task,ignore_errors=True)
 def cancel(self,ident):
    j=self.jobs.get(ident)
    if not j:raise AgentError('jobMissing',404)
    if j['status'] in ('queued','running'):j.update(status='cancelled',errorCode='cancelled');self.emit({'type':'job','job':j.copy()},self.job_owners.get(ident))
    return {'job':j.copy()}
 def web_capture(self,ident,options,owner,progress):
    with self.lock:
        if not self.browser_ready():raise AgentError('browserRequired')
        browser_owner=self.browser['origin']
        if any(value['owner']==browser_owner for value in self.web_waiters.values()):raise AgentError('busy',429)
        command={'id':ident,'options':options.copy()}
        waiter=queue.Queue(maxsize=1);entry={'owner':browser_owner,'queue':waiter,'uploads':set(),'command':command,'resultReceived':False};self.web_waiters[ident]=entry
    self.emit({'type':'browserCapture','command':command},browser_owner)
    try:
        deadline=time.monotonic()+600
        while time.monotonic()<deadline:
            progress(5)
            try:r=waiter.get(timeout=1);break
            except queue.Empty:continue
        else:raise AgentError('timeout',504)
        if r.get('errorCode'):raise AgentError(r['errorCode'])
        tiles=[]
        with self.lock:
            for item in r.get('tiles',[]):
                path=str(self.resolve(item['id'],browser_owner));tiles.append({**item,'path':path});self.active_inputs.setdefault(ident,set()).add(path)
        import engine_extra
        return self.engine_job('web_stitch',[],{'tiles':tiles,'width':r.get('width'),'height':r.get('height'),'dpr':r.get('dpr',1),'format':options.get('format','png'),'split':options.get('split',False),'maxHeight':options.get('maxHeight',12000)},progress)
    finally:
        with self.lock:
            self.active_inputs.pop(ident,None)
            self.remove_uploads(entry['uploads'],browser_owner)
            self.web_waiters.pop(ident,None)
 def browser_result(self,body,owner):
    r=self.web_waiters.get(body.get('id'))
    if not r or r['owner']!=owner:raise AgentError('jobMissing',404)
    tiles=body.get('tiles',[])
    if not isinstance(tiles,list) or len(tiles)>200:raise AgentError('invalidRequest')
    with self.lock:
        if self.web_waiters.get(body.get('id')) is not r:raise AgentError('jobMissing',404)
        # Keep this marker through stitching: consuming the queue must not make
        # a duplicate completion valid or add another capture's temporary tiles.
        if r.get('resultReceived'):raise AgentError('conflict',409)
        try:r['queue'].put_nowait(body)
        except queue.Full:raise AgentError('conflict',409)
        r['resultReceived']=True
        r['uploads'].update(item['id'] for item in tiles if isinstance(item,dict) and isinstance(item.get('id'),str))
    return {'received':True}
 def apply_settings(self,body):
    if not isinstance(body,dict) or set(body)-{'language','shortcuts','autoStart','closeAfterCaptureCopy','openCaptureEditor','captureFormat','saveMode','recording'}:raise AgentError('invalidRequest')
    if 'language'in body and body['language'] not in LANGUAGES:raise AgentError('invalidRequest')
    if 'autoStart'in body and not isinstance(body['autoStart'],bool):raise AgentError('invalidRequest')
    for key in ('closeAfterCaptureCopy','openCaptureEditor'):
        if key in body and not isinstance(body[key],bool):raise AgentError('invalidRequest')
    if 'captureFormat' in body and body['captureFormat'] not in ('png','jpg'):raise AgentError('invalidRequest')
    if 'shortcuts'in body:
        s=body['shortcuts']
        if not isinstance(s,dict) or set(s)-{'areaCapture','fullCapture','webCapture','recordToggle','recordArea','aiTranslate'} or any(not isinstance(v,str) or len(v)>80 for v in s.values()):raise AgentError('invalidRequest')
        vals=[v for v in s.values() if v]
        if len(set(vals))!=len(vals):raise AgentError('shortcutConflict',409)
    if 'saveMode' in body:
        if body['saveMode'] not in ('local','drive','both'):raise AgentError('invalidRequest')
        if body['saveMode'] in ('drive','both') and not self.drive.status()['connected']:raise AgentError('driveNotConnected')
    if 'recording' in body:
        r=body['recording']
        if not isinstance(r,dict) or set(r)-{'mode','monitor','monitorName'} or r.get('mode') not in ('area','full','window'):raise AgentError('invalidRequest')
        if 'monitor' in r and (type(r['monitor']) is not int or not 0<=r['monitor']<=255):raise AgentError('invalidRequest')
        if 'monitorName' in r and (not isinstance(r['monitorName'],str) or len(r['monitorName'])>256 or '\0' in r['monitorName']):raise AgentError('invalidRequest')
    native_body={k:v for k,v in body.items() if k not in ('saveMode','recording','language')}
    with self.lock:
        native_result=self.bridge.call('settings.apply',native_body) if native_body else None
        if 'shortcuts'in body:self.settings['shortcuts']={**self.settings.get('shortcuts',{}),**body['shortcuts']}
        self.settings.update({k:v for k,v in body.items() if k!='shortcuts'})
        if 'autoStart' in body:self.settings.pop('autoStartStatus',None)
        if isinstance(native_result,dict):self.settings.update(self.startup_snapshot(native_result.get('settings')))
        atomic_json(self.settings_path,self.settings)
    self.emit({'type':'settings','settings':self.public_settings()});return {'settings':self.public_settings()}
 def signals(self):
    while not self.stopping.wait(.5):
        with self.ai.lock:self.ai.prune()
        if time.monotonic()-self.last_upload_cleanup>=3600:
            try:self.cleanup_uploads()
            except (OSError,AgentError):pass
        with self.lock:
            if self.bridge.ready():
                snapshot=self.bridge.status().get('settings',{})
                if isinstance(snapshot,dict):
                    changed={}
                    # Both native menus and WebView write the same device-local file.
                    # A stale native heartbeat must never overwrite a newer selection.
                    locale=self.language_state()
                    if self.settings.get('language')!=locale['language']:changed['language']=locale['language']
                    if locale['source']=='user' and snapshot.get('language')!=locale['language']:
                        try:self.bridge.call('settings.apply',{'language':locale['language']})
                        except AgentError:pass
                    for k in ('shortcuts','autoStart','autoStartStatus','saveFolder','closeAfterCaptureCopy','openCaptureEditor','captureFormat'):
                        if k in snapshot:
                            value=snapshot[k]
                            if k=='language' and value not in LANGUAGES:continue
                            if k=='autoStart' and not isinstance(value,bool):continue
                            if k=='autoStartStatus' and value not in ('enabled','disabled','blocked','repair','error'):continue
                            if k in ('closeAfterCaptureCopy','openCaptureEditor') and not isinstance(value,bool):continue
                            if k=='captureFormat' and value not in ('png','jpg'):continue
                            if k=='shortcuts' and (not isinstance(value,dict) or set(value)-{'areaCapture','fullCapture','webCapture','recordToggle','recordArea','aiTranslate'} or any(not isinstance(v,str) or len(v)>80 for v in value.values())):continue
                            if k=='saveFolder':
                                p=Path(str(value))
                                if not p.is_absolute() or p.is_symlink() or not p.is_dir():continue
                            if self.settings.get(k)!=value:changed[k]=value
                    if changed or not self.settings_initialized:
                        with self.lock:
                            self.settings.update(changed);atomic_json(self.settings_path,self.settings);self.settings_initialized=True
                        if changed:self.emit({'type':'settings','settings':self.public_settings()})
        for p in (self.bridge.root/'signals').glob('*.json'):
            r=read_json(p,{})
            try:
                if valid_id(r.get('id')) and abs(time.time()-float(r.get('createdAt',0)))<30:
                    if r.get('operation')=='web.capture' and self.browser:self.submit({'operation':'web_capture','options':{}},self.native_owner(self.browser['origin']))
                    elif r.get('operation')=='record.toggle':
                        op='record_stop' if self.bridge.status().get('recording') else 'record_start'
                        self.submit({'operation':op,'options':{}},self.native_owner(f'http://127.0.0.1:{self.port}'))
                    elif r.get('operation')=='record.stop' and self.bridge.status().get('recording'):
                        # Native floating controls must finish through a job so
                        # the saved video reaches results and configured storage.
                        self.submit({'operation':'record_stop','options':{}},self.native_owner(f'http://127.0.0.1:{self.port}'))
            except (AgentError,TypeError,ValueError):pass
            finally:p.unlink(missing_ok=True)
 def close(self):
    self.account.close()
    self.ai.clear();self.ai.account.cancel()
    self.storage.close()
    self.stopping.set()
    if self.signals_thread is not threading.current_thread():self.signals_thread.join(timeout=3)
    self.index.close();self.pool.shutdown(wait=False,cancel_futures=True)

def re_windows_path(value):return len(value)>2 and value[1:3] in (':\\',':/')
class Handler(BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1';server_version='ADMINLocalAgent';sys_version=''
 def log_message(self,*args):pass
 @property
 def agent(self):return self.server.agent
 def origin(self):
    origin=self.headers.get('Origin','')
    # Host-authorized Chromium extensions can omit Origin on GET. The explicit
    # identifier is only a routing hint: allowlist, token and native approval
    # checks still apply. Never let it override an actual website Origin.
    extension=self.headers.get('X-KIO-Extension-Origin','')
    if not origin and re.fullmatch(r'chrome-extension://[a-p]{32}',extension):origin=extension
    if not origin:
        ref=urlparse(self.headers.get('Referer',''));candidate=f'{ref.scheme}://{ref.netloc}'
        if candidate in {f'http://127.0.0.1:{self.agent.port}',f'http://localhost:{self.agent.port}'}:origin=candidate
    return origin
 def guard(self,auth=True):
    expected={f'127.0.0.1:{self.agent.port}',f'localhost:{self.agent.port}'}
    if self.headers.get('Host','') not in expected:raise AgentError('forbiddenHost',403)
    if self.client_address[0]!='127.0.0.1':raise AgentError('forbiddenHost',403)
    self.req_origin=self.origin()
    if self.req_origin not in self.agent.origins or not standalone_origin(self.req_origin,self.agent.port):raise AgentError('forbiddenOrigin',403)
    if auth:self.owner=self.agent.authenticate(self.req_origin,self.headers.get('X-Local-Agent-Token',''))
 def cors(self):
    o=getattr(self,'req_origin',None)
    if o in self.agent.origins:
        self.send_header('Access-Control-Allow-Origin',o);self.send_header('Vary','Origin')
        self.send_header('Access-Control-Allow-Headers','Content-Type,X-Local-Agent-Token,X-File-Name,X-KIO-Extension-Origin')
        self.send_header('Access-Control-Allow-Methods','GET,POST,PATCH,DELETE,OPTIONS')
        self.send_header('Access-Control-Allow-Private-Network','true')
 def require_desktop(self):
    # authenticate() returns an origin, not the literal ownerId in the bootstrap
    # JSON. Require the private host credential, not another pairing on localhost.
    token=self.headers.get('X-Local-Agent-Token','')
    digest=hashlib.sha256(token.encode()).hexdigest() if token else ''
    if self.req_origin!=self.agent.desktop_origin or not hmac.compare_digest(self.agent.desktop_digest,digest):raise AgentError('forbiddenOrigin',403)
 def require_control(self):
    self.require_desktop()
 def respond(self,data,status=200):
    content=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.cors();self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(content)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(content)
 def body(self):
    length=self.length(MAX_BODY)
    try:r=json.loads(self.rfile.read(length)) if length else {}
    except (ValueError,UnicodeError):raise AgentError('invalidRequest')
    if not isinstance(r,dict):raise AgentError('invalidRequest')
    return r
 def length(self,maximum):
    if self.headers.get('Transfer-Encoding'):raise AgentError('invalidRequest')
    try:n=int(self.headers.get('Content-Length','0'))
    except ValueError:raise AgentError('invalidRequest')
    if not 0<=n<=maximum:raise AgentError('fileTooLarge',413)
    return n
 def route(self):
    path=urlparse(self.path).path
    if self.command=='GET' and path.startswith('/tools/'):
        if self.headers.get('Host','') not in {f'127.0.0.1:{self.agent.port}',f'localhost:{self.agent.port}'}:raise AgentError('forbiddenHost',403)
        return self.static(path)
    public=(path=='/health' and self.command=='GET') or (path=='/pair' and self.command=='POST')
    self.guard(auth=not(public or self.command=='OPTIONS'))
    if self.command=='OPTIONS':return self.respond({},200)
    a=self.agent;owner=getattr(self,'owner',None)
    account_allowed=path in {'/health','/preferences/language','/account/status','/account/login','/account/cancel','/account/logout','/desktop/dispatch','/pair'} or path.startswith('/updates/')
    if path.startswith('/kio/web/'):raise AgentError('controlWebRemoved',410)
    if not account_allowed:a.require_account()
    if self.command=='GET':
        if path=='/preferences/language':
            self.require_desktop();return self.respond(a.language_state())
        if path=='/account/status':return self.respond(a.account.status())
        if path.startswith('/ai/scans/') and path.endswith('/preview'):
            self.require_control();png=a.ai.scan(path.split('/')[3])['png'];self.send_response(200);self.cors();self.send_header('Content-Type','image/png');self.send_header('Content-Length',str(len(png)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(png);return
        if path.startswith('/ai/images/') and len(path.split('/'))==4:
            self.require_control();png=a.ai.image(path.split('/')[3]);self.send_response(200);self.cors();self.send_header('Content-Type','image/png');self.send_header('Content-Length',str(len(png)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(png);return
        if path=='/ai/status':
            self.require_control();return self.respond(a.ai.status())
        if path=='/ai/performance':
            self.require_control();return self.respond({'samples':a.ai.performance})
        if path.startswith('/ai/jobs/'):
            self.require_control();return self.respond(a.ai.job(path.split('/')[-1]))
        if path=='/health':return self.respond(a.health())
        if path=='/events':return self.events()
        if path=='/updates/status':
            self.require_desktop();return self.respond(a.updater.status())
        if path=='/settings':return self.respond({'settings':a.public_settings()})
        if path=='/storage':
            self.require_control()
            return self.respond(a.storage.status())
        if path=='/roots':return self.respond({'roots':a.index.roots()})
        if path=='/signatures':return self.respond({'signatures':a.signatures.list(owner)})
        if path=='/recordings/latest':return self.respond({'file':a.latest_recording(owner)})
        if path=='/files/history':
            from urllib.parse import parse_qs
            query=parse_qs(urlparse(self.path).query)
            if set(query)-{'cursor'} or any(len(v)!=1 for v in query.values()):raise AgentError('invalidRequest')
            return self.respond(a.artifact_history(owner,query.get('cursor',[''])[0]))
        if path.startswith('/files/') and path.endswith('/preview'):
            ident=path.split('/')[2]
            if not valid_id(ident):raise AgentError('invalidRequest')
            a.resolve(ident,owner)
            return self.respond(a.index.preview(ident))
        if path=='/permissions':return self.respond(a.bridge.call('permissions.get'))
        if path=='/phone':return self.respond(a.phone.status(owner))
        if path=='/browser':return self.respond({'connected':a.browser_ready(),'browser':a.browser.get('browser') if a.browser else None})
        if path=='/browser/install-info':
            self.require_control();return self.respond(a.browser_install_info())
        if path.startswith('/jobs/'):
            j=a.jobs.get(path.split('/')[-1])
            if not j or j.get('accountId')!=a.account.user['id'] or (a.job_owners.get(j['id'])!=owner and not {a.job_owners.get(j['id']),owner}<={a.desktop_origin,CLOUD_ORIGIN}):raise AgentError('jobMissing',404)
            return self.respond({'job':j})
        if path.startswith('/artifacts/'):
            ident=path.split('/')[-1];p=a.resolve(ident,owner);return self.binary(p,a.files.get(ident,{}).get('name',p.name))
        if path.startswith('/files/') and path.endswith('/details'):return self.respond(a.index.details(path.split('/')[2]))
    if self.command=='POST':
        if path=='/uploads':return self.upload(owner)
        if path=='/files/history':
            body=self.body()
            if set(body)-{'cursor'} or not isinstance(body.get('cursor',''),str):raise AgentError('invalidRequest')
            return self.respond(a.artifact_history(owner,body.get('cursor','')))
        if path.startswith('/ai/frame/'):
            self.require_control();length=self.length(16*1024*1024)
            if length<24 or self.headers.get('Content-Type')!='image/png':raise AgentError('invalidRequest')
            data=self.rfile.read(length)
            if len(data)!=length or data[:8]!=b'\x89PNG\r\n\x1a\n':raise AgentError('aiInvalidImage')
            a.ai.accept_frame(path.split('/')[-1],data);return self.respond({'accepted':True})
        if path=='/clipboard/png':
            self.require_control()
            length=self.length(64*1024*1024)
            if length<24 or self.headers.get('Content-Type')!='image/png':raise AgentError('invalidRequest')
            data=self.rfile.read(length)
            if len(data)!=length or data[:8]!=b'\x89PNG\r\n\x1a\n' or data[12:16]!=b'IHDR':raise AgentError('invalidRequest')
            w=int.from_bytes(data[16:20],'big');h=int.from_bytes(data[20:24],'big')
            if not 0<w<=20000 or not 0<h<=20000 or w*h>64000000:raise AgentError('fileTooLarge')
            folder=private_dir(a.state/'clipboard')
            if not contained(folder,a.state):raise AgentError('unsafePath')
            p=folder/(str(uuid.uuid4())+'.png')
            try:
                with p.open('xb') as stream:stream.write(data)
                result=a.bridge.call('clipboard.copy',{'path':str(p)},30)
                if result.get('copied') is not True:raise AgentError('processingFailed')
            finally:p.unlink(missing_ok=True)
            return self.respond({'copied':True})
        body=self.body()
        if path=='/preferences/language':
            self.require_desktop()
            if set(body)!={'language'} or body['language'] not in ('vi','en','ko','ja','zh-TW','zh-CN'):raise AgentError('invalidRequest')
            value=a.language_preference.select(body['language']);a.settings['language']=value['language']
            atomic_json(a.settings_path,a.settings)
            if a.bridge.ready():
                try:a.bridge.call('settings.apply',{'language':value['language']})
                except AgentError:pass # signals() retries; durable selection already succeeded.
            a.emit({'type':'language','language':value['language'],'source':'user'})
            return self.respond(value)
        if path.startswith('/account/'):

            self.require_desktop()
            if path=='/account/login':
                if set(body)-{'provider'}:raise AgentError('invalidRequest')
                return self.respond(a.account.login(body.get('provider','google')))
            if body:raise AgentError('invalidRequest')
            if path=='/account/cancel':return self.respond(a.account.cancel())
            if path=='/account/logout':
                result=a.account.logout();a.ai.clear();a.drive.identity_now()
                with a.lock:
                    for job in a.jobs.values():
                        if job['status'] in ('queued','running'):job.update(status='cancelled',errorCode='cancelled')
                a.emit({'type':'account','account':result});return self.respond(result)
            raise AgentError('notFound',404)
        if path=='/desktop/dispatch':
            self.require_desktop();return self.respond(a.dispatch_shortcut(body))
        if path.startswith('/updates/'):
            self.require_desktop();action=path.removeprefix('/updates/')
            if action=='preferences':return self.respond(a.updater.preferences_update(body))
            if body:raise AgentError('invalidRequest')
            if action in ('check','download'):return self.respond(a.updater.start(action))
            if action=='install':return self.respond(a.updater.install())
            raise AgentError('invalidRequest')
        if path.startswith('/ai/'):
            self.require_control();action=path.removeprefix('/ai/')
            if action=='settings':return self.respond(a.ai.configure(body))
            if action=='connect':
                if set(body)-{'accountId','newAccount'} or ('newAccount' in body and not isinstance(body['newAccount'],bool)):raise AgentError('invalidRequest')
                a.ai.account.connect(body.get('accountId'),new_account=body.get('newAccount',False));return self.respond(a.ai.status())
            if action=='cancel-login':a.ai.account.cancel();return self.respond(a.ai.status())
            if action=='disconnect':a.ai.clear();a.ai.account.disconnect();return self.respond(a.ai.status())
            if action=='select-account':a.ai.clear();a.ai.account.select(body.get('accountId'));return self.respond(a.ai.status())
            if action=='models':a.ai.account.list_models();return self.respond(a.ai.status())
            if action=='welcome':a.ai.account.welcome();return self.respond(a.ai.status())
            if action=='clear':a.ai.clear();return self.respond({'cleared':True})
            if action=='metrics':return self.respond(a.ai.metrics(body))
            if action=='cancel':return self.respond(a.ai.cancel(body.get('id')))
            if action in ('capture','scan','analyze','reply','retranslate'):return self.respond(a.ai.submit(action,body))
            raise AgentError('notFound',404)
        if path=='/clipboard/image':
            if not isinstance(body,dict) or set(body)!={'id'}:raise AgentError('invalidRequest')
            p=a.resolve(body['id'],owner)
            if p.stat().st_size>MAX_UPLOAD:raise AgentError('fileTooLarge')
            with p.open('rb') as stream:signature=stream.read(8)
            if signature!=b'\x89PNG\r\n\x1a\n':raise AgentError('unsupported')
            result=a.bridge.call('clipboard.copy',{'path':str(p)},30)
            if result.get('copied') is not True:raise AgentError('processingFailed')
            return self.respond({'copied':True})
        if path=='/pair':return self.respond(a.pair(self.req_origin,body.get('clientName','ADMIN')))
        if path.startswith('/drive/') or path=='/storage/retry':
            self.require_control()
            def fields(allowed):
                if set(body)-set(allowed):raise AgentError('invalidRequest')
                for key in ('parentId','folderId','fileId'):
                    if key in body and body[key] is not None and (not isinstance(body[key],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}',body[key])):raise AgentError('invalidRequest')
                if 'pageToken' in body and body['pageToken'] is not None and (not isinstance(body['pageToken'],str) or len(body['pageToken'])>4096):raise AgentError('invalidRequest')
            if path=='/drive/connect':
                fields({'switchAccount'})
                if 'switchAccount' in body and not isinstance(body['switchAccount'],bool):raise AgentError('invalidRequest')
                return self.respond(a.drive.connect())
            if path=='/drive/configure':
                fields(set())
                selected=a.bridge.call('files.choose',{'kind':'any','multiple':False})
                paths=selected.get('paths',[])
                if len(paths)!=1:raise AgentError('cancelled')
                return self.respond(a.drive.configure(paths[0]))
            if path=='/drive/cancel':
                fields(set());return self.respond(a.drive.cancel_connect())
            if path=='/drive/disconnect':
                fields(set())
                a.storage.close();result=a.drive.disconnect();a.settings['saveMode']='local';atomic_json(a.settings_path,a.settings)
                a.emit({'type':'settings','settings':a.public_settings()});return self.respond(result)
            if path=='/drive/folders/list':
                fields({'parentId','pageToken'});result=a.drive.browse_folders(body.get('parentId'),body.get('pageToken'))
                return self.respond({**result,'folders':result.get('files',[])})
            if path=='/drive/folders/create':
                fields({'name','parentId'});return self.respond({'folder':a.drive.create_folder(body.get('name'),body.get('parentId'))})
            if path=='/drive/folders/select':
                fields({'folderId'});return self.respond({'drive':a.drive.select_root(body.get('folderId'))})
            if path=='/drive/files/list':
                fields({'parentId','pageToken','query','kind'})
                return self.respond(a.drive.list_library(body.get('parentId'),body.get('pageToken'),body.get('query',''),body.get('kind')))
            if path=='/drive/files/upload':
                fields({'inputIds','expectedAccountId'});ids=body.get('inputIds');expected=body.get('expectedAccountId')
                if 'expectedAccountId' in body and (not isinstance(expected,str) or not expected or len(expected)>256):raise AgentError('invalidRequest')
                if not isinstance(ids,list) or not 1<=len(ids)<=50 or any(not valid_id(ident) for ident in ids) or len(set(ids))!=len(ids):raise AgentError('invalidRequest')
                paths=[];inputs=[]
                for ident in ids:
                    with a.lock:registered=a.files.get(ident)
                    if not isinstance(registered,dict) or registered.get('owner')!=owner:raise AgentError('forbiddenFile',403)
                    source=a.resolve(ident,owner)
                    if source.stat().st_size>2*1024**3:raise AgentError('fileTooLarge',413)
                    paths.append(source);inputs.append(a.file_info(ident))
                _,summaries=a.storage.publish(paths,'drive_upload',mode_override='drive',expected_account=expected)
                return self.respond({'queued':len(inputs),'files':[{**item,'assetId':summary['assetId']} for item,summary in zip(inputs,summaries)],'storage':a.storage.status()},202)
            if path=='/drive/files/download':
                fields({'fileId'})
                if not isinstance(body.get('fileId'),str):raise AgentError('invalidRequest')
                with a.drive.lock:generation=a.drive.auth_generation
                directory=private_dir(a.state/'uploads'/str(uuid.uuid4()));temporary=directory/'drive-download.bin'
                try:
                    result=a.drive.download(body['fileId'],temporary,max_bytes=512*1024*1024)
                    if Path(result.get('path','')).resolve()!=temporary.resolve() or not temporary.is_file() or temporary.is_symlink():raise AgentError('unsafePath')
                    if temporary.stat().st_size>512*1024*1024:raise AgentError('fileTooLarge',413)
                    destination=a.storage.import_download(temporary,result['metadata'],generation)
                    return self.respond({'file':a.register(destination,owner),'metadata':result['metadata'],'downloaded':True})
                finally:
                    temporary.unlink(missing_ok=True)
                    try:directory.rmdir()
                    except OSError:pass
            if path=='/storage/retry':
                fields(set());return self.respond(a.storage.retry())
        if path=='/jobs':return self.respond(a.submit(body,owner),202)
        if path.startswith('/phone/'):
            operation=path[len('/phone/'):];return self.respond(a.phone.action(operation,body,owner))
        if path.startswith('/jobs/') and path.endswith('/cancel'):
            ident=path.split('/')[2]
            if a.job_owners.get(ident)!=owner:raise AgentError('jobMissing',404)
            return self.respond(a.cancel(ident))
        if path=='/files/choose':
            kind=body.get('kind','any')
            if kind not in ('image','pdf','video','any'):raise AgentError('invalidRequest')
            r=a.bridge.call('files.choose',{'kind':kind,'multiple':body.get('multiple') is not False})
            return self.respond({'files':a.register_inputs(r.get('paths',[]),owner)})
        if path in ('/files/open','/files/reveal','/files/edit'):
            p=a.resolve(body.get('id'),owner);op={'/files/open':'file.open','/files/reveal':'file.reveal','/files/edit':'editor.open'}[path]
            return self.respond(a.bridge.call(op,{'path':str(p)}))
        if path=='/signatures':
            if set(body)-{'id','name'} or not valid_id(body.get('id')):raise AgentError('invalidRequest')
            return self.respond({'signature':a.signatures.save(body['id'],body.get('name'),owner)},201)
        if path=='/roots/select':
            r=a.bridge.call('folder.choose',{'purpose':'search'});ident=a.index.add(r['path']);return self.respond({'rootId':ident,'roots':a.index.roots()})
        if path=='/search':
            if set(body)-{'query','limit','filters'}:raise AgentError('invalidRequest')
            return self.respond({'files':a.index.search(body.get('query',''),body.get('limit',50),body.get('filters'))})
        if path.startswith('/roots/') and path.endswith('/cancel'):
            ident=path.split('/')[2]
            if body or not valid_id(ident):raise AgentError('invalidRequest')
            return self.respond(a.index.cancel(ident))
        if path=='/rename/preview':return self.respond(a.renamer.preview(body.get('ids'),body.get('options',{}),owner))
        if path=='/rename/commit':
            with a.lock:
                preview=a.renamer.previews.get(body.get('previewId'))
                if preview and preview['owner']==owner:
                    candidate=a.files.copy()
                    for item in preview['items']:
                        if item['id'] in candidate:candidate[item['id']]={**candidate[item['id']],'path':item['target'],'name':item['after']}
                    if len(json.dumps(candidate,ensure_ascii=False).encode('utf-8'))>MAX_REGISTRY_BYTES:raise AgentError('storageFull',507)
                r=a.renamer.commit(body.get('previewId'),owner)
                for item in r['items']:
                    if item['id'] in a.files:
                        a.files[item['id']]['path']=item['target'];a.files[item['id']]['name']=item['after']
                atomic_json(a.state/'files.json',a.files)
            with a.index.lock:
                for item in r['items']:
                    row=a.index.db.execute('SELECT files.*,roots.path AS base FROM files JOIN roots ON files.root=roots.id WHERE files.id=?',(item['id'],)).fetchone()
                    if row:
                        a.index.db.execute('UPDATE files SET relative=?,name=? WHERE id=?',(str(Path(item['target']).relative_to(row['base'])),item['after'],item['id']))
                a.index.db.commit()
            r['items']=[{k:v for k,v in x.items() if k in ('id','before','after')} for x in r['items']]
            with a.index.lock:a.index.dirty.update(x['id'] for x in a.index.db.execute('SELECT id FROM roots'))
            return self.respond(r)
        if path=='/settings/save-folder':
            r=a.bridge.call('folder.choose',{'purpose':'save'});p=Path(r['path'])
            if p.is_symlink() or not p.is_dir():raise AgentError('unsafePath')
            a.settings['localSaveFolder']=str(p.resolve());atomic_json(a.settings_path,a.settings);a.emit({'type':'settings','settings':a.public_settings()});return self.respond({'settings':a.public_settings()})
        if path=='/permissions/open':
            if body.get('permission') not in ('screenCapture','accessibility','files'):raise AgentError('invalidRequest')
            return self.respond(a.bridge.call('permissions.open',body))
        if path=='/browser/register':
            if not self.req_origin.startswith('chrome-extension://'):raise AgentError('forbiddenOrigin',403)
            with a.lock:a.browser={'origin':owner,'browser':str(body.get('browser','Chrome'))[:40],'lastSeen':time.time()}
            a.emit_browser_state(owner);return self.respond({'connected':True})
        if path=='/browser/install':
            self.require_control()
            if body:raise AgentError('invalidRequest')
            info=a.browser_install_info()
            a.bridge.call('file.reveal',{'path':str(Path(info['folderPath'])/'manifest.json')})
            return self.respond({'prepared':True,**info})
        if path=='/browser/heartbeat':
            with a.lock:
                if not a.browser or a.browser['origin']!=owner:raise AgentError('unauthorized',403)
                previous=a.browser_ready();a.browser['lastSeen']=time.time();changed=previous!=a.browser_ready()
            if changed:a.emit_browser_state(owner)
            return self.respond({'connected':True})
        if path=='/browser/result':return self.respond(a.browser_result(body,owner))
        if path=='/browser/capture':
            validate_web_options(body,owner,a.browser.get('origin') if a.browser else None)
            if not a.browser_ready():raise AgentError('browserRequired',409)
            return self.respond(a.submit({'operation':'web_capture','options':body},owner),202)
        if path=='/native/tools':
            if body.get('tool') not in ('image','pdf','capture','record','codes','phone'):raise AgentError('invalidRequest')
            return self.respond(a.bridge.call('native.tools',body))
    if self.command=='PATCH' and path=='/settings':return self.respond(a.apply_settings(self.body()))
    if self.command=='DELETE':
        if path=='/pair':return self.respond(a.revoke(owner))
        if path.startswith('/roots/'):
            a.index.remove(path.split('/')[-1]);return self.respond({'roots':a.index.roots()})
    raise AgentError('notFound',404)
 def upload(self,owner):
    length=self.length(MAX_UPLOAD)
    if length<1:raise AgentError('inputMissing')
    name=unquote(self.headers.get('X-File-Name','file'))
    name=Path(name.replace('\\','/')).name[:200]
    if not name or name in ('.','..') or '\0'in name:raise AgentError('invalidName')
    directory=None;p=None;created_file=False
    with self.agent.lock:
        if not contained(self.agent.state/'uploads',self.agent.state):raise AgentError('unsafePath')
        if self.agent.tile_upload_name(owner,name) and not any(waiter['owner']==owner for waiter in self.agent.web_waiters.values()):raise AgentError('cancelled',409)
        count=0;size=0
        for x in (self.agent.state/'uploads').glob('*/*'):
            try:
                if not contained(x,self.agent.state/'uploads'):continue
                info=x.lstat()
                if stat.S_ISREG(info.st_mode):count+=1;size+=info.st_size
            except OSError:pass
        if len(self.agent.files)>=MAX_REGISTERED_FILES or count+self.agent.upload_reserved_files+1>MAX_UPLOAD_FILES or size+self.agent.upload_reserved+length>2*1024**3:raise AgentError('storageFull',507)
        self.agent.upload_reserved+=length;self.agent.upload_reserved_files+=1
    try:
        if not contained(self.agent.state/'uploads',self.agent.state):raise AgentError('unsafePath')
        directory=private_dir(self.agent.state/'uploads'/str(uuid.uuid4()));p=directory/name
        if not contained(p,self.agent.state/'uploads'):raise AgentError('unsafePath')
        with p.open('xb') as f:
            created_file=True
            os.chmod(p,0o600);remaining=length
            while remaining:
                part=self.rfile.read(min(1024*1024,remaining))
                if not part:raise AgentError('invalidRequest')
                f.write(part);remaining-=len(part)
        return self.respond(self.agent.register(p,owner,'upload',name),201)
    except BaseException:
        if created_file and p is not None and contained(p,self.agent.state/'uploads'):p.unlink(missing_ok=True)
        if directory is not None:
            try:directory.rmdir()
            except OSError:pass
        raise
    finally:
        with self.agent.lock:self.agent.upload_reserved-=length;self.agent.upload_reserved_files-=1
 def binary(self,p,name):
    length=p.stat().st_size;mime=mimetypes.guess_type(name)[0] or 'application/octet-stream'
    self.send_response(200);self.cors();self.send_header('Content-Type',mime);self.send_header('Content-Length',str(length));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store');self.end_headers()
    with p.open('rb') as f:
        while part:=f.read(1024*1024):self.wfile.write(part)
 def static(self,path):
    relative=unquote(path[len('/tools/'):]) or 'index.html'
    if relative=='language-bootstrap.js':
        value=self.agent.language_state()
        # Native hosts can migrate a previously saved explicit choice. The
        # automatic language is never written as a saved user preference.
        native=self.agent.bridge.status().get('settings',{}) if self.agent.bridge.ready() else {}
        if value['source']!='user' and native.get('languageSource')=='user' and normalize_language(native.get('language')):
            value=self.agent.language_preference.select(normalize_language(native['language']))
        self.agent.settings['language']=value['language']
        value['startup']=[language_text('startup.title',value['language']),language_text('startup.wait',value['language'])]
        script='globalThis.__kioLocale='+json.dumps(value,ensure_ascii=True)+';document.documentElement.lang=__kioLocale.language;document.addEventListener("DOMContentLoaded",()=>{document.querySelectorAll("[data-startup]").forEach(e=>e.textContent=__kioLocale.startup[Number(e.dataset.startup)]);});'
        data=script.encode();self.send_response(200);self.send_header('Content-Type','text/javascript; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return

    if relative=='index.html' and not (self.agent.ui_dir/relative).is_file():relative='local-tools-standalone.html'
    p=self.agent.ui_dir/relative
    if not contained(p,self.agent.ui_dir) or not p.is_file():raise AgentError('notFound',404)
    self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(p.name)[0] or 'application/octet-stream');self.send_header('Content-Length',str(p.stat().st_size));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'");self.end_headers();self.wfile.write(p.read_bytes())
 def events(self):
    account_id=self.agent.require_account()['id']
    q=queue.Queue(maxsize=100);item=(self.owner,q)
    with self.agent.lock:
        if len(self.agent.listeners)>=16:raise AgentError('busy',429)
        self.agent.listeners.append(item)
    try:
        self.send_response(200);self.cors();self.send_header('Content-Type','text/event-stream');self.send_header('Cache-Control','no-store');self.send_header('Connection','close');self.end_headers()
        # Stream the initial snapshot directly. Filling the listener queue before
        # its consumer starts deadlocks when there are many completed jobs.
        initial=[{'type':'ready','device':self.agent.device(),'settings':self.agent.public_settings()}]
        with self.agent.lock:
            history=[j.copy() for j in self.agent.jobs.values() if j.get('accountId')==account_id and (self.agent.job_owners.get(j['id'])==self.owner or {self.agent.job_owners.get(j['id']),self.owner}<={self.agent.desktop_origin,CLOUD_ORIGIN})]
            pending=[{'type':'browserCapture','command':value['command'].copy()} for ident,value in self.agent.web_waiters.items() if value['owner']==self.owner and not value.get('resultReceived') and self.agent.jobs.get(ident,{}).get('status') in ('queued','running')]
        initial.extend({'type':'job','job':j} for j in history[-120:])
        # Commands may have been emitted just as an old worker disconnected.
        # Replaying the same ID is safe; the extension deduplicates that ID.
        initial.extend(pending)
        for event in initial:
            self.wfile.write((f'event: {event["type"]}\ndata: '+json.dumps(event,ensure_ascii=False)+'\n\n').encode())
        self.wfile.flush()
        self.agent.emit_browser_state(self.owner)
        while not self.agent.stopping.is_set():
            # Re-auth on every heartbeat means revoked tokens cannot keep event streams alive.
            self.agent.authenticate(self.req_origin,self.headers.get('X-Local-Agent-Token',''))
            if self.agent.require_account()['id']!=account_id:raise AgentError('unauthorized',401)
            try:event=q.get(timeout=15);content=f'event: {event["type"]}\ndata: '+json.dumps(event,ensure_ascii=False)+'\n\n'
            except queue.Empty:content=': heartbeat\n\n'
            self.agent.authenticate(self.req_origin,self.headers.get('X-Local-Agent-Token',''))
            if self.agent.require_account()['id']!=account_id:raise AgentError('unauthorized',401)
            self.wfile.write(content.encode());self.wfile.flush()
    except (BrokenPipeError,ConnectionResetError,AgentError,OSError):pass
    finally:
        with self.agent.lock:
            if item in self.agent.listeners:self.agent.listeners.remove(item)
        self.agent.emit_browser_state(self.owner)
        self.close_connection=True
 def dispatch(self):
    self.connection.settimeout(30)
    try:self.route()
    except AgentError as e:
        self.close_connection=True;self.respond({'errorCode':e.code},e.status)
    except (BrokenPipeError,ConnectionResetError,TimeoutError):self.close_connection=True
    except Exception:
        self.close_connection=True;self.respond({'errorCode':'processingFailed'},500)
 do_GET=do_POST=do_PATCH=do_DELETE=do_OPTIONS=dispatch

class Server(ThreadingHTTPServer):
 daemon_threads=True;allow_reuse_address=True
 def __init__(self,agent):
    self.agent=agent;self.connections=threading.BoundedSemaphore(32);super().__init__(('127.0.0.1',agent.port),Handler)
 def get_request(self):
    connection,address=super().get_request();connection.settimeout(15);return connection,address
 def process_request(self,request,client_address):
    if not self.connections.acquire(blocking=False):self.shutdown_request(request);return
    try:super().process_request(request,client_address)
    except BaseException:self.connections.release();raise
 def process_request_thread(self,request,client_address):
    try:super().process_request_thread(request,client_address)
    finally:self.connections.release()

def main():
 p=argparse.ArgumentParser();p.add_argument('--state-dir',required=True);p.add_argument('--ui-dir',required=True);p.add_argument('--port',type=int,default=4323);p.add_argument('--allowed-origin',action='append',default=[]);p.add_argument('--native-pid',type=int,default=0);args=p.parse_args()
 if not 1024<=args.port<=65535:p.error('Invalid port')
 agent=Agent(args.state_dir,args.ui_dir,args.port,args.allowed_origin,args.native_pid);server=Server(agent)
 try:server.serve_forever(poll_interval=.5)
 except KeyboardInterrupt:pass
 finally:server.server_close();agent.close()
if __name__=='__main__':main()
