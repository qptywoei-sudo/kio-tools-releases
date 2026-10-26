"""Per-user Google Drive OAuth for the installed Windows application.

System browser + PKCE + a short-lived loopback listener. Refresh tokens use
Windows DPAPI or native macOS Keychain and are never sent to the UI.
"""
from __future__ import annotations
from language import normalize, callback_page
import base64,ctypes,hashlib,hmac,json,mimetypes,os,re,secrets,sys,threading,time,urllib.parse,urllib.request,urllib.error,webbrowser
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
from common import AgentError,atomic_json,read_json,private_dir
from secure_tokens import MacKeychain

SCOPE='https://www.googleapis.com/auth/drive.file'
API='https://www.googleapis.com/drive/v3/'
TOKEN='https://oauth2.googleapis.com/token'
FOLDER='application/vnd.google-apps.folder'
FILE_FIELDS='id,name,mimeType,size,modifiedTime,createdTime,parents,webViewLink,properties,sha256Checksum,capabilities(canDownload,canAddChildren),trashed'
MAX_DOWNLOAD=512*1024*1024
LOGIN_TIMEOUT=300
DEFAULT_ROOT='__kio_default__'
def drive_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}',value):raise AgentError('invalidRequest')
    return value
def query_text(value):return str(value).replace('\\','\\\\').replace("'","\\'")

class Blob(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]

def protect(data:bytes,decrypt=False)->bytes:
    if os.name!='nt':raise AgentError('driveSecureStorageUnavailable')
    buffer=ctypes.create_string_buffer(data);source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));out=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    method=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    method.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)];method.restype=wintypes.BOOL
    if not method(ctypes.byref(source),None,None,None,None,1,ctypes.byref(out)):raise AgentError('driveSecureStorageUnavailable')
    try:return ctypes.string_at(out.data,out.size)
    finally:kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree(out.data)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

class GoogleDrive:
    def __init__(self,state):
        self.state=private_dir(Path(state)/'google-drive');self.lock=threading.RLock();self.upload_lock=threading.RLock()
        self.token_path=self.state/'account.dpapi';self.config_path=self.state/'oauth-client.json';self.session=None;self.error='';self.account={};self.auth_generation=0
        self.folder_cache={};self.tokens={};self.opener=urllib.request.build_opener(NoRedirect());self.keychain=None
        self.preferences_path=self.state/'preferences.json';self.preferences=read_json(self.preferences_path,{})
        if not isinstance(self.preferences,dict):self.preferences={}
        try:
            if sys.platform=='darwin':self.keychain=MacKeychain(self.state);saved=self.keychain.load()
            elif self.token_path.exists():
                if self.token_path.is_symlink() or self.token_path.stat().st_size>65536:raise ValueError()
                saved=protect(self.token_path.read_bytes(),True)
            else:saved=None
            if saved:
                tokens=json.loads(saved)
                if not isinstance(tokens,dict) or not isinstance(tokens.get('account',{}),dict):raise ValueError()
                if tokens.get('clientId') and tokens['clientId']!=self.config().get('client_id'):raise ValueError()
                self.tokens=tokens;self.account=self.tokens.get('account',{})
        except Exception:self.error='driveReconnect'
    def config(self):
        data=read_json(self.config_path,None) or read_json(Path(__file__).with_name('google-oauth-client.json'),{})
        client=data.get('installed',{}) if isinstance(data,dict) else {}
        return client if isinstance(client,dict) and str(client.get('client_id','')).endswith('.apps.googleusercontent.com') else {}
    def configure(self,path):
        data=read_json(path,{},maximum=65536);client=data.get('installed',{}) if isinstance(data,dict) else {}
        if not isinstance(client,dict) or not str(client.get('client_id','')).endswith('.apps.googleusercontent.com'):raise AgentError('driveDesktopClientRequired')
        with self.lock:
            if self.tokens or self.session is not None:raise AgentError('driveDisconnectFirst')
            atomic_json(self.config_path,{'installed':{k:client[k] for k in ('client_id','client_secret','project_id') if k in client}})
            self.error=''
        return self.status()
    def account_id(self):return str(self.account.get('permissionId') or self.account.get('emailAddress','')).lower()
    def selected_root(self):
        # Output locations are owned by KIO. Retain old preferences on disk only
        # for migration/recovery; they cannot redirect new output.
        return {'name':'KIO 컨트롤','id':self.folder_cache.get('root','')}
    def status(self):
        with self.lock:
            root=self.selected_root()
            return {'configured':bool(self.config()),'connected':bool(self.tokens.get('refresh_token')),'connecting':self.session is not None,'email':self.account.get('emailAddress',''),'displayName':self.account.get('displayName',''),'accountId':self.account_id(),'folderName':root.get('name','KIO 컨트롤'),'rootId':root.get('id',self.folder_cache.get('root','')),'scopeLimited':True,'scope':SCOPE,'error':self.error}
    def save_tokens(self):
        self.tokens['clientId']=self.config().get('client_id','');data=json.dumps(self.tokens,ensure_ascii=False).encode('utf-8')
        if sys.platform=='darwin':
            if self.keychain is None:self.keychain=MacKeychain(self.state)
            self.keychain.save(data);return
        encrypted=protect(data);temporary=self.token_path.with_name('account-'+secrets.token_hex(8)+'.tmp')
        try:
            fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'wb') as stream:stream.write(encrypted);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,self.token_path)
        finally:temporary.unlink(missing_ok=True)
    def delete_tokens(self):
        if self.keychain is not None:self.keychain.delete()
        self.token_path.unlink(missing_ok=True)
    def fence(self,generation):
        if generation is not None and generation!=self.auth_generation:raise AgentError('driveAccountChanged')
    def raw(self,url,method='GET',data=None,headers=None,timeout=45):
        parsed=urllib.parse.urlparse(url)
        if parsed.scheme!='https' or parsed.hostname not in ('www.googleapis.com','oauth2.googleapis.com') or parsed.port not in (None,443) or parsed.username or parsed.password or parsed.fragment:raise AgentError('driveInvalidEndpoint')
        request=urllib.request.Request(url,data=data,method=method,headers=headers or {})
        try:
            with self.opener.open(request,timeout=timeout) as response:return response.status,dict(response.headers),response.read(8*1024*1024)
        except urllib.error.HTTPError as error:return error.code,dict(error.headers),error.read(65536)
        except (OSError,urllib.error.URLError,TimeoutError):raise AgentError('driveNetwork')
    def exchange(self,values):
        code,_,body=self.raw(TOKEN,'POST',urllib.parse.urlencode(values).encode(),{'Content-Type':'application/x-www-form-urlencoded'})
        try:result=json.loads(body)
        except ValueError:raise AgentError('driveNetwork')
        if code!=200 or not result.get('access_token'):raise AgentError('driveReconnect' if result.get('error')=='invalid_grant' else 'driveLoginFailed')
        return result
    def account_info(self,access_token):
        code,_,body=self.raw(API+'about?fields=user','GET',None,{'Authorization':'Bearer '+access_token})
        if code!=200:raise AgentError(self.error_code(code,body))
        try:user=json.loads(body).get('user',{})
        except ValueError:raise AgentError('driveLoginFailed')
        if not isinstance(user,dict) or not (user.get('permissionId') or user.get('emailAddress')):raise AgentError('driveLoginFailed')
        return user
    def access_token(self):
        with self.lock:
            if not self.tokens.get('refresh_token'):raise AgentError('driveNotConnected')
            if time.time()<self.tokens.get('expires_at',0)-60:return self.tokens['access_token']
            client=self.config();values={'client_id':client.get('client_id',''),'refresh_token':self.tokens['refresh_token'],'grant_type':'refresh_token'}
            if client.get('client_secret'):values['client_secret']=client['client_secret']
            try:token=self.exchange(values)
            except AgentError as e:
                self.error=e.code
                if e.code=='driveReconnect':self.tokens={};self.auth_generation+=1;self.delete_tokens()
                raise
            self.tokens.update(access_token=token['access_token'],expires_at=time.time()+int(token.get('expires_in',3600)))
            self.save_tokens();return self.tokens['access_token']
    def upload_token(self,generation):
        with self.lock:
            if generation is not None and generation!=self.auth_generation:raise AgentError('driveAccountChanged')
            return self.access_token()
    def request(self,url,method='GET',body=None,headers=None,generation=None):
        with self.lock:generation=self.auth_generation if generation is None else generation;self.fence(generation)
        data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None
        for attempt in range(2):
            code,head,raw=self.raw(url,method,data,{'Authorization':'Bearer '+self.upload_token(generation),'Content-Type':'application/json; charset=UTF-8',**(headers or {})})
            if generation is not None and generation!=self.auth_generation:raise AgentError('driveAccountChanged')
            if code==401 and attempt==0:
                with self.lock:self.fence(generation);self.tokens['expires_at']=0
                continue
            if code not in (200,201,204):raise AgentError(self.error_code(code,raw))
            return (json.loads(raw) if raw else {}),head
        raise AgentError('driveReconnect')
    @staticmethod
    def error_code(code,body=b''):
        try:reason=json.loads(body).get('error',{}).get('errors',[{}])[0].get('reason','')
        except (ValueError,TypeError,AttributeError,IndexError):reason=''
        if code==401:return 'driveReconnect'
        if code==404:return 'driveFileMissing'
        if code==403:return 'driveQuota' if reason in ('storageQuotaExceeded','userRateLimitExceeded','rateLimitExceeded','dailyLimitExceeded') else 'drivePermissionRequired'
        return 'driveQuota' if code==429 else 'driveNetwork'
    def connect(self, language='en'):
        language=normalize(language) or 'en'
        client=self.config()
        if not client:raise AgentError('driveSetupRequired')
        with self.lock:
            if self.session is not None:return self.status()
            verifier=secrets.token_urlsafe(64);state=secrets.token_urlsafe(32);self.auth_generation+=1;generation=self.auth_generation;owner=self
            prior_tokens=dict(self.tokens);prior_account=dict(self.account);prior_folders=dict(self.folder_cache)
            class Callback(BaseHTTPRequestHandler):
                def setup(self):
                    super().setup();self.connection.settimeout(5)
                def log_message(self,*args):pass
                def do_GET(self):
                    parsed=urllib.parse.urlparse(self.path);query=urllib.parse.parse_qs(parsed.query)
                    valid=parsed.path=='/oauth/callback' and hmac.compare_digest(query.get('state',[''])[0],state) and self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}'
                    if not valid:self.send_error(400);return
                    try:
                        if query.get('error'):raise AgentError('driveLoginCancelled')
                        code=query.get('code',[''])[0]
                        if not code or len(code)>4096:raise AgentError('driveLoginFailed')
                        values={'client_id':client['client_id'],'code':code,'code_verifier':verifier,'redirect_uri':redirect,'grant_type':'authorization_code'}
                        if client.get('client_secret'):values['client_secret']=client['client_secret']
                        token=owner.exchange(values)
                        if SCOPE not in str(token.get('scope','')).split():raise AgentError('drivePermissionRequired')
                        if not token.get('refresh_token'):raise AgentError('driveLoginFailed')
                        account=owner.account_info(token['access_token'])
                        with owner.lock:
                            if generation!=owner.auth_generation:raise AgentError('driveLoginCancelled')
                            owner.tokens={**token,'expires_at':time.time()+int(token.get('expires_in',3600))};owner.folder_cache={}
                            owner.account=account;owner.tokens['account']=owner.account;owner.save_tokens();owner.error=''
                            # Requests started while the browser was open used the
                            # prior account. They must not retry with this new token.
                            owner.auth_generation+=1
                        message='driveAuth.success'
                    except Exception as error:
                        with owner.lock:
                            if generation==owner.auth_generation:
                                owner.tokens=prior_tokens;owner.account=prior_account;owner.folder_cache=prior_folders
                                owner.error=error.code if isinstance(error,AgentError) else 'driveLoginFailed'
                        message='driveAuth.failure'
                    finally:self.server.completed=True
                    data=callback_page(message,language)
                    self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'");self.end_headers();self.wfile.write(data)
            server=HTTPServer(('127.0.0.1',0),Callback);server.timeout=.5;server.completed=False
            redirect=f'http://127.0.0.1:{server.server_port}/oauth/callback';self.session=server;self.error=''
            challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
            url='https://accounts.google.com/o/oauth2/v2/auth?'+urllib.parse.urlencode({'hl':language,'client_id':client['client_id'],'redirect_uri':redirect,'response_type':'code','scope':SCOPE,'state':state,'code_challenge':challenge,'code_challenge_method':'S256','access_type':'offline','prompt':'consent select_account'})
        def wait():
            deadline=time.monotonic()+LOGIN_TIMEOUT
            try:
                while not server.completed and time.monotonic()<deadline and generation==owner.auth_generation:server.handle_request()
                with owner.lock:
                    if not server.completed and generation==owner.auth_generation:owner.error='driveLoginTimeout'
            finally:
                server.server_close()
                with owner.lock:
                    if owner.session is server:owner.session=None
        threading.Thread(target=wait,daemon=True,name='KIO-Drive-Login').start()
        try:
            if os.name=='nt':os.startfile(url)
            elif not webbrowser.open(url):raise OSError()
        except OSError:
            with self.lock:
                if generation==self.auth_generation:self.auth_generation+=1;self.error='driveBrowserFailed';self.session=None
            raise AgentError('driveBrowserFailed')
        return self.status()
    def disconnect(self):
        with self.lock:
            self.auth_generation+=1;generation=self.auth_generation;token=self.tokens.get('refresh_token');self.session=None
            try:self.delete_tokens()
            except AgentError as error:self.error=error.code;raise
            self.tokens={};self.account={};self.folder_cache={};self.error=''
        revoked=not bool(token)
        if token:
            try:
                code,_,body=self.raw('https://oauth2.googleapis.com/revoke','POST',urllib.parse.urlencode({'token':token}).encode(),{'Content-Type':'application/x-www-form-urlencoded'},timeout=15)
                revoked=code==200 or (code==400 and b'invalid_token' in body)
            except AgentError:revoked=False
        with self.lock:
            if generation==self.auth_generation and not revoked:self.error='driveRevokeFailed'
        return {**self.status(),'revocationConfirmed':revoked}
    def cancel_connect(self):
        with self.lock:self.auth_generation+=1;self.session=None;self.error='driveLoginCancelled'
        return self.status()
    def list_files(self,query,generation=None):
        return self.request(API+'files?'+urllib.parse.urlencode({'q':query,'fields':'files(id,name,webViewLink,properties)','pageSize':100}),generation=generation)[0].get('files',[])
    def file_metadata(self,file_id,generation=None):
        with self.lock:generation=self.auth_generation if generation is None else generation;self.fence(generation)
        item,_=self.request(API+'files/'+drive_id(file_id)+'?'+urllib.parse.urlencode({'fields':FILE_FIELDS,'supportsAllDrives':'true'}),generation=generation)
        if item.get('trashed'):raise AgentError('driveFileMissing')
        return item
    def _folder_metadata(self,folder_id,generation):
        item=self.file_metadata(folder_id,generation)
        if item.get('mimeType')!=FOLDER:raise AgentError('driveFolderRequired')
        if item.get('capabilities',{}).get('canAddChildren') is False:raise AgentError('driveFolderReadOnly')
        return item
    def root_id(self,generation=None):
        with self.lock:
            generation=self.auth_generation if generation is None else generation;self.fence(generation)
            selected=self.selected_root().get('id')
        return drive_id(selected) if selected else self.folder('KIO 컨트롤',None,'root',generation)
    def select_root(self,folder_id=None):
        if folder_id is not None:raise AgentError('driveFolderFixed')
        with self.lock:generation=self.auth_generation
        if folder_id is None:folder_id=self.folder('KIO 컨트롤',None,'root',generation)
        item=self._folder_metadata(folder_id,generation)
        with self.lock:
            self.fence(generation);key=hashlib.sha256(self.account_id().encode()).hexdigest()
            prior=self.preferences.get('roots',{});roots=dict(prior) if isinstance(prior,dict) else {}
            roots[key]={'id':item['id'],'name':item.get('name','KIO 컨트롤')};preferences={**self.preferences,'roots':roots}
            atomic_json(self.preferences_path,preferences);self.preferences=preferences;self.folder_cache={}
        return self.status()
    def _list_page(self,query,page_token,generation):
        if page_token is not None and (not isinstance(page_token,str) or len(page_token)>4096):raise AgentError('invalidRequest')
        args={'q':query,'fields':'nextPageToken,files('+FILE_FIELDS+')','pageSize':100,'orderBy':'folder,name_natural','supportsAllDrives':'true','includeItemsFromAllDrives':'true'}
        if page_token:args['pageToken']=page_token
        result,_=self.request(API+'files?'+urllib.parse.urlencode(args),generation=generation)
        return {'files':result.get('files',[]),'nextPageToken':result.get('nextPageToken',''),'scopeLimited':True}
    def browse_folders(self,parent_id=None,page_token=None):
        with self.lock:generation=self.auth_generation
        query="trashed = false and mimeType = '"+FOLDER+"'"
        if parent_id:query+=" and '"+drive_id(parent_id)+"' in parents"
        return self._list_page(query,page_token,generation)
    def create_folder(self,name,parent_id=None):
        if not isinstance(name,str) or not name.strip() or len(name)>200 or any(ord(c)<32 for c in name):raise AgentError('invalidRequest')
        with self.lock:generation=self.auth_generation
        parent=drive_id(parent_id) if parent_id else self.root_id(generation)
        self._folder_metadata(parent,generation)
        body={'name':name.strip(),'mimeType':FOLDER,'parents':[parent],'properties':{'application':'kio-control','schemaVersion':'1'}}
        return self.request(API+'files?'+urllib.parse.urlencode({'fields':FILE_FIELDS,'supportsAllDrives':'true'}),'POST',body,generation=generation)[0]
    def list_library(self,parent_id=None,page_token=None,query='',kind=None):
        if not isinstance(query,str) or len(query)>200:raise AgentError('invalidRequest')
        kinds={'images':"mimeType contains 'image/' and mimeType != 'image/gif'",'photos':"mimeType contains 'image/' and mimeType != 'image/gif'",'videos':"mimeType contains 'video/'",'gifs':"mimeType = 'image/gif'",'pdf':"mimeType = 'application/pdf'",'folders':"mimeType = '"+FOLDER+"'"}
        if kind is not None and kind not in kinds:raise AgentError('invalidRequest')
        with self.lock:generation=self.auth_generation
        parent=drive_id(parent_id) if parent_id else self.root_id(generation)
        filters="trashed = false and '"+parent+"' in parents"
        if query.strip():filters+=" and name contains '"+query_text(query.strip())+"'"
        if kind:filters+=' and ('+kinds[kind]+')'
        return {**self._list_page(filters,page_token,generation),'parentId':parent}
    def download(self,file_id,destination,max_bytes=MAX_DOWNLOAD):
        """Stream an app-authorized binary into a server-selected temporary path."""
        if not isinstance(max_bytes,int) or isinstance(max_bytes,bool) or not 0<max_bytes<=2*1024*1024*1024:raise AgentError('invalidRequest')
        with self.lock:generation=self.auth_generation
        item=self.file_metadata(file_id,generation);mime=item.get('mimeType','')
        if mime.startswith('application/vnd.google-apps.'):raise AgentError('driveUnsupportedDocument')
        if item.get('capabilities',{}).get('canDownload') is False:raise AgentError('drivePermissionRequired')
        try:expected=int(item.get('size',-1))
        except (TypeError,ValueError):raise AgentError('driveDownloadFailed')
        if expected>max_bytes:raise AgentError('fileTooLarge')
        destination=Path(destination)
        if destination.exists() or destination.is_symlink() or not destination.parent.is_dir():raise AgentError('unsafePath')
        temporary=destination.with_name('.kio-download-'+secrets.token_hex(12)+'.part');url=API+'files/'+drive_id(file_id)+'?alt=media&supportsAllDrives=true'
        total=0;digest=hashlib.sha256()
        try:
            for attempt in range(2):
                request=urllib.request.Request(url,headers={'Authorization':'Bearer '+self.upload_token(generation)})
                try:response=self.opener.open(request,timeout=90)
                except urllib.error.HTTPError as error:
                    if error.code==401 and attempt==0:
                        with self.lock:self.fence(generation);self.tokens['expires_at']=0
                        continue
                    raise AgentError(self.error_code(error.code,error.read(65536)))
                with response:
                    self.fence(generation)
                    if response.status!=200:raise AgentError('driveDownloadFailed')
                    length=response.headers.get('Content-Length')
                    if length and (not length.isdigit() or int(length)>max_bytes):raise AgentError('fileTooLarge')
                    fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                    with os.fdopen(fd,'wb') as stream:
                        while True:
                            self.fence(generation);chunk=response.read(min(1024*1024,max_bytes-total+1))
                            if not chunk:break
                            total+=len(chunk)
                            if total>max_bytes:raise AgentError('fileTooLarge')
                            digest.update(chunk);stream.write(chunk)
                        stream.flush();os.fsync(stream.fileno())
                    self.fence(generation)
                    if expected>=0 and total!=expected:raise AgentError('driveDownloadFailed')
                    checksum=item.get('sha256Checksum') or item.get('properties',{}).get('sha256')
                    if checksum and not hmac.compare_digest(digest.hexdigest(),str(checksum).lower()):raise AgentError('driveDownloadFailed')
                    # Hard link gives atomic, no-overwrite publication on NTFS/APFS.
                    with self.lock:self.fence(generation);os.link(temporary,destination)
                    return {'path':str(destination),'metadata':item,'bytes':total,'sha256':digest.hexdigest()}
            raise AgentError('driveReconnect')
        except (urllib.error.URLError,TimeoutError,OSError) as error:
            if isinstance(error,FileExistsError):raise AgentError('unsafePath')
            raise AgentError('driveNetwork')
        finally:temporary.unlink(missing_ok=True)
    def folder(self,name,parent,key,generation=None):
        with self.upload_lock:
            with self.lock:
                if generation is not None and generation!=self.auth_generation:raise AgentError('driveAccountChanged')
                if key in self.folder_cache:return self.folder_cache[key]
            safe=query_text(key)
            query="trashed = false and mimeType = 'application/vnd.google-apps.folder' and appProperties has { key='kioFolder' and value='"+safe+"' }"
            if parent:query+=" and '"+parent+"' in parents"
            found=self.list_files(query,generation)
            if not found and parent:
                # Reuse earlier KIO folders and user-created names in this exact parent.
                found=self.list_files("trashed = false and mimeType = '"+FOLDER+"' and '"+drive_id(parent)+"' in parents and name = '"+query_text(name)+"'",generation)
            if found:ident=found[0]['id']
            else:
                data={'name':name,'mimeType':'application/vnd.google-apps.folder','appProperties':{'kioFolder':key},'properties':{'application':'kio-control','schemaVersion':'1'}}
                if parent:data['parents']=[parent]
                ident=self.request(API+'files?fields=id','POST',data,generation=generation)[0]['id']
            with self.lock:
                if generation is not None and generation!=self.auth_generation:raise AgentError('driveAccountChanged')
                self.folder_cache[key]=ident
            return ident
    def upload(self,path,metadata):
        """Idempotent upload, resumed by querying the server after transient errors."""
        with self.upload_lock:
            with self.lock:
                generation=self.auth_generation
                if 'account' in metadata and metadata['account']!=self.account.get('emailAddress',''):raise AgentError('driveAccountChanged')
                if metadata.get('accountId') and metadata['accountId']!=self.account_id():raise AgentError('driveAccountChanged')
            path=Path(path);asset=metadata['assetId'];existing=self.list_files("trashed = false and properties has { key='assetId' and value='"+query_text(asset)+"' }",generation)
            if generation!=self.auth_generation:raise AgentError('driveAccountChanged')
            if existing:return existing[0]
            pinned=metadata.get('driveRootId')
            root=self.folder('KIO 컨트롤',None,'root',generation) if pinned==DEFAULT_ROOT else drive_id(pinned) if pinned else self.root_id(generation);parent=root
            for i,name in enumerate(metadata['relativePath'].split('/')[:-1]):parent=self.folder(name,parent,root+'/'+ '/'.join(metadata['relativePath'].split('/')[:i+1]),generation)
            props={key:str(metadata[key]) for key in ('assetId','kind','createdAt','sha256')};props.update(application='kio-control',schemaVersion='1')
            size=path.stat().st_size;mime=metadata['mime'];data={'name':metadata['name'],'parents':[parent],'mimeType':mime,'properties':props}
            _,headers=self.request('https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&fields=id,name,webViewLink,properties','POST',data,{'X-Upload-Content-Type':mime,'X-Upload-Content-Length':str(size)},generation=generation)
            location=next((v for k,v in headers.items() if k.lower()=='location'),'')
            parsed=urllib.parse.urlparse(location)
            if parsed.scheme!='https' or parsed.hostname!='www.googleapis.com':raise AgentError('driveInvalidEndpoint')
            offset=0;failures=0
            def received_offset(headers):
                received=next((v for k,v in headers.items() if k.lower()=='range'),'')
                if not received:return 0
                match=re.fullmatch(r'bytes=0-(\d+)',received)
                if not match or int(match[1])>=size:raise AgentError('driveUploadFailed')
                return int(match[1])+1
            with path.open('rb') as stream:
                while offset<size:
                    if generation!=self.auth_generation:raise AgentError('driveAccountChanged')
                    stream.seek(offset);chunk=stream.read(4*1024*1024)
                    try:
                        status,headers,body=self.raw(location,'PUT',chunk,{'Authorization':'Bearer '+self.upload_token(generation),'Content-Type':mime,'Content-Range':f'bytes {offset}-{offset+len(chunk)-1}/{size}'},timeout=90)
                        if generation!=self.auth_generation:raise AgentError('driveAccountChanged')
                        if status in (200,201):return json.loads(body)
                        if status==308:
                            next_offset=received_offset(headers)
                            if next_offset<=offset:failures+=1
                            else:failures=0
                            offset=next_offset
                            if failures>=3:raise AgentError('driveNetwork')
                            continue
                        if status==401:
                            with self.lock:self.fence(generation);self.tokens['expires_at']=0
                        if status not in (401,429,500,502,503,504):raise AgentError('driveQuota' if status==403 else 'driveUploadFailed')
                    except AgentError as e:
                        if e.code not in ('driveNetwork',):raise
                    failures+=1
                    if failures>3:raise AgentError('driveNetwork')
                    time.sleep(min(2**failures,8))
                    status,headers,body=self.raw(location,'PUT',b'',{'Authorization':'Bearer '+self.upload_token(generation),'Content-Range':f'bytes */{size}'})
                    if generation!=self.auth_generation:raise AgentError('driveAccountChanged')
                    if status in (200,201):return json.loads(body)
                    if status==308:
                        offset=received_offset(headers)
                    elif status not in (429,500,502,503,504):raise AgentError('driveUploadFailed')
            raise AgentError('driveUploadFailed')
