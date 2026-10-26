"""Private state and typed native bridge for ADMIN Local Agent."""
from __future__ import annotations
import json, os, time, uuid, threading, socket, platform
from pathlib import Path

VERSION = '4.6.23'
LANGUAGES = ('vi','en','ko','ja','zh-TW','zh-CN','zh')
class AgentError(Exception):
    def __init__(self, code='invalidRequest', status=400):
        self.code,self.status=code,status
        super().__init__(code)

def atomic_json(path, value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    tmp=path.with_name('.'+path.name+'-'+uuid.uuid4().hex)
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(value,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:tmp.unlink(missing_ok=True)

def read_json(path,default=None,maximum=1_000_000):
    try:
        p=Path(path)
        if p.is_symlink() or p.stat().st_size>maximum:return default
        with p.open('rb') as f:data=f.read(maximum+1)
        if len(data)>maximum:return default
        return json.loads(data.decode('utf-8'))
    except (OSError,ValueError):return default

def valid_id(value):
    try:return isinstance(value,str) and str(uuid.UUID(value))==value
    except ValueError:return False

def utc():
    from datetime import datetime,timezone
    return datetime.now(timezone.utc).isoformat()

def private_dir(path):
    p=Path(path).expanduser()
    if p.is_symlink():raise AgentError('unsafePath')
    p.mkdir(parents=True,exist_ok=True,mode=0o700)
    if os.name!='nt':
        if p.stat().st_uid!=os.getuid():raise AgentError('unsafePath')
        p.chmod(0o700)
    return p.resolve()

NATIVE_OPS={'pair.approve','folder.choose','files.choose','file.open','file.reveal','clipboard.copy','capture.start','capture.cancel','editor.open','record.start','record.pause','record.resume','record.stop','permissions.get','permissions.open','settings.apply','phone.open','phone.status','phone.pair','phone.connect','phone.start','phone.stop','phone.keyboard','native.tools','app.quit'}
class NativeBridge:
    def __init__(self,state,native_pid=0):
        if type(native_pid) is not int or native_pid<0:raise AgentError('invalidRequest')
        root=Path(state)/'bridge'
        self.root=private_dir(root/('native-'+str(native_pid)) if native_pid else root)
        for name in ('requests','responses','signals'):private_dir(self.root/name)
        self.pair_lock=threading.Lock()
    def status(self):
        s=read_json(self.root/'status.json',{})
        if not isinstance(s,dict) or not isinstance(s.get('updatedAt'),(float,int)):return {}
        return s if -2<=time.time()-s['updatedAt']<12 else {}
    def ready(self):return bool(self.status())
    def call(self,operation,args=None,timeout=90,cancel=None):
        if operation not in NATIVE_OPS:raise AgentError('unsupported')
        if not self.ready():raise AgentError('nativeUnavailable',503)
        ident=str(uuid.uuid4());req=self.root/'requests'/f'{ident}.json';res=self.root/'responses'/f'{ident}.json'
        atomic_json(req,{'id':ident,'operation':operation,'args':args or {},'expiresAt':time.time()+timeout})
        if os.name=='nt':
            # Wake the owning native host immediately; the timer remains a fallback.
            # This message only scans authenticated private request files.
            try:
                import ctypes
                status=self.status();hwnd=status.get('requestWindow',0);owner=ctypes.c_ulong()
                user=ctypes.WinDLL('user32',use_last_error=True)
                user.GetWindowThreadProcessId.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
                user.PostMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t]
                if type(hwnd) is int and hwnd>0 and user.GetWindowThreadProcessId(hwnd,ctypes.byref(owner)) and owner.value==status.get('pid'):
                    user.PostMessageW(hwnd,0x8000+121,0,0)
            except (OSError,TypeError,OverflowError):pass
        try:
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                if cancel is not None and cancel():raise AgentError('cancelled')
                if res.exists():
                    r=read_json(res,{},maximum=1_000_000)
                    if r.get('id')!=ident:raise AgentError('nativeUnavailable',503)
                    if not r.get('ok'):raise AgentError(r.get('errorCode') or 'processingFailed')
                    data=r.get('data',{})
                    if not isinstance(data,dict):raise AgentError('processingFailed')
                    if data.get('cancelled'):raise AgentError('cancelled')
                    return data
                if not self.ready():raise AgentError('nativeUnavailable',503)
                time.sleep(.025 if operation=='clipboard.copy' or (args or {}).get('ephemeral') is True else .1)
            raise AgentError('timeout',504)
        except AgentError as error:
            if operation=='capture.start' and error.code in ('cancelled','timeout'):
                # End only this request's native picker/overlay, never a later capture.
                # Remove a still-queued start before cancellation can be handled first.
                req.unlink(missing_ok=True)
                try:self.call('capture.cancel',{'requestId':ident},5)
                except AgentError:pass
            raise
        finally:req.unlink(missing_ok=True);res.unlink(missing_ok=True)
    def approve(self,origin,name):
        if not self.pair_lock.acquire(blocking=False):raise AgentError('pairingBusy',409)
        try:
            r=self.call('pair.approve',{'origin':origin,'clientName':str(name)[:80]},120)
            if r.get('approved') is not True:raise AgentError('pairingDenied',403)
        finally:self.pair_lock.release()
