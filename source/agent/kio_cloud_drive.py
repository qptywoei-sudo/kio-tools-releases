"""KIO-owned Drive storage through the same verified account as the web app.

Google grants stay in KIO cloud; native credentials stay in OS secure storage.
Only the pinned private control subtree can be read or written by this adapter.
"""
from __future__ import annotations
import base64, hashlib, threading, time
from pathlib import Path
from common import AgentError, atomic_json, read_json, private_dir, valid_id

FOLDER='application/vnd.google-apps.folder'
PATH='ADMIN/KIO/자료함/키오컨트롤'
DEFAULT_ROOT='__kio_default__'

class KIOCloudDrive:
    def __init__(self,state,account):
        self.account=account;self.lock=threading.RLock();self.upload_lock=threading.RLock()
        self.state=private_dir(Path(state)/'kio-drive');self.tickets=private_dir(self.state/'tickets')
        self.auth_generation=0;self.identity='';self.checked=0;self.connected=False;self.root='';self.error=''
        self.disabled=False;self.cached=None;self.refresh_gate=threading.Lock()
    def identity_now(self):
        status=self.account.status();user=status.get('user') or {};ident=user.get('id','')
        if ident!=self.identity:
            self.auth_generation+=1;self.identity=ident;self.checked=0;self.connected=False;self.root='';self.disabled=False
        return status,user
    def fence(self,generation):
        self.identity_now()
        if generation!=self.auth_generation:raise AgentError('driveAccountChanged')
    def status(self):
        with self.lock:
            status,user=self.identity_now()
            if status.get('signedIn') and not self.disabled and time.monotonic()-self.checked>=30:
                self.checked=time.monotonic()
                try:
                    generation=self.auth_generation
                    value=self.account.cloud('/control/drive/status',method='GET',expected_user=user['id']).get('drive',{})
                    self.fence(generation)
                    self.connected=value.get('connected') is True;self.root=value.get('rootId') or value.get('folderId') or '';self.error=''
                    # Reuse the verified KIO Drive grant, creating only its fixed
                    # output subtree when it has never been used on this account.
                    if self.connected and not self.root:
                        value=self.account.cloud('/control/drive/connect',expected_user=user['id']).get('drive',{})
                        self.fence(generation)
                        self.root=value.get('rootId') or value.get('folderId') or ''
                        if not self.root:raise AgentError('driveInvalidResponse')
                except AgentError as error:self.connected=False;self.error=error.code
            result={'configured':True,'connected':bool(status.get('signedIn') and self.connected and not self.disabled),'connecting':status.get('connecting',False),
                    'email':user.get('email',''),'displayName':user.get('name',''),'accountId':user.get('id',''),
                    'rootId':self.root,'folderName':'키오컨트롤','path':PATH,'scopeLimited':True,'scope':'kio-control-private-subtree','connectionSource':'kio-account','error':self.error}
            self.cached=result;return dict(result)
    def cached_status(self):
        status=self.account.status();user=status.get('user') or {};ident=user.get('id','')
        value=self.cached
        if not value or value.get('accountId')!=ident:
            value={'configured':True,'connected':False,'connecting':False,'accountId':ident,'email':user.get('email',''),
                   'rootId':'','folderName':'키오컨트롤','path':PATH,'scopeLimited':True,'error':''}
        else:value=dict(value)
        value['connecting']=status.get('connecting',False)
        value['checking']=bool(status.get('signedIn') and (self.cached is None or self.cached.get('accountId')!=ident))
        if not status.get('signedIn') or self.disabled:value['connected']=False
        if status.get('signedIn') and not self.disabled and (self.cached is None or self.cached.get('accountId')!=ident or time.monotonic()-self.checked>=30) and self.refresh_gate.acquire(False):
            def refresh():
                try:self.status()
                finally:self.refresh_gate.release()
            threading.Thread(target=refresh,daemon=True).start()
        return value

    def connect(self):
        with self.lock:
            user=self.account.require();self.disabled=False;self.checked=0
            if self.status()['connected']:
                value=self.account.cloud('/control/drive/connect',expected_user=user['id']).get('drive',{})
                self.root=value.get('rootId') or value.get('folderId') or '';return self.status()
            self.account.login('google',expected_user=user['id'],connect_drive=True);return self.status()
    def cancel_connect(self):self.account.cancel();return self.status()
    def disconnect(self):
        with self.lock:
            user=self.account.require()
            self.account.cloud('/control/drive/disconnect',{'confirmed':True},expected_user=user['id'])
            self.disabled=False;self.connected=False;self.root="";self.checked=0;self.auth_generation+=1;self.cached=None
            return self.status()
    def select_root(self,folder_id=None):
        state=self.status()
        if folder_id not in (None,'',state['rootId']):raise AgentError('drivePermissionRequired',403)
        return state
    def browse_folders(self,parent_id=None,page_token=None):
        result=self.list_library(parent_id,page_token)
        return {**result,'files':[item for item in result['files'] if item['mimeType']==FOLDER]}
    def create_folder(self,name,parent_id=None):raise AgentError('drivePermissionRequired',403)
    def list_library(self,parent_id=None,page_token=None,query='',kind=None):
        self.account.require();state=self.status()
        if not state['connected']:raise AgentError('driveNotConnected')
        body={key:value for key,value in [('parentId',parent_id),('pageToken',page_token),('query',query),('kind',kind)] if value}
        generation=self.auth_generation
        result=self.account.cloud('/control/drive/list',body,expected_user=state['accountId'])
        self.fence(generation)
        files=[{**row,'mimeType':row.get('mimeType') or row.get('mime','application/octet-stream'),'webViewLink':row.get('webViewLink') or row.get('webUrl','')} for row in result.get('files',[])]
        return {'files':files,'nextPageToken':result.get('nextPageToken',''),'scopeLimited':True,'parentId':parent_id or self.root}
    def upload(self,path,metadata):
        with self.upload_lock:
            for attempt in range(2):
                try:return self._upload_attempt(path,metadata)
                except AgentError as error:
                    if error.code not in ('accountCloudUnavailable','driveUploadFailed') or attempt:raise
                    asset=metadata.get('assetId')
                    if valid_id(asset):(self.tickets/(asset+'.json')).unlink(missing_ok=True)
            raise AgentError('driveUploadFailed')
    def _upload_attempt(self,path,metadata):
        with self.upload_lock:
            state=self.status();generation=self.auth_generation
            if not state['connected']:raise AgentError('driveNotConnected')
            if metadata.get('accountId')!=state['accountId']:raise AgentError('driveAccountChanged')
            root=metadata.get('driveRootId')
            if root not in (None,'',DEFAULT_ROOT,self.root):raise AgentError('driveAccountChanged')
            asset=metadata.get('assetId')
            if not valid_id(asset):raise AgentError('invalidRequest')
            source=Path(path);size=source.stat().st_size
            if size!=metadata.get('bytes') or not source.is_file():raise AgentError('fileMissing')
            ticket_path=self.tickets/(asset+'.json');saved=read_json(ticket_path,{})
            if saved.get('userId')!=state['accountId'] or saved.get('sha256')!=metadata['sha256'] or saved.get('expires',0)<=time.time()*1000:saved={}
            if not saved:
                self.fence(generation)
                start=self.account.cloud('/control/drive/upload/start',{'name':metadata['name'],'mime':metadata['mime'],'size':size,'sha256':metadata['sha256'],'assetId':asset,'relativePath':metadata['relativePath']},expected_user=state['accountId'])
                self.fence(generation)
                if start.get('complete'):
                    file=start.get('file',{});return {'id':file['id'],'webViewLink':file.get('webUrl','')}
                saved={**start,'userId':state['accountId'],'sha256':metadata['sha256'],'offset':0};atomic_json(ticket_path,saved)
            chunk_bytes=saved.get('chunkBytes',2097152)
            if isinstance(chunk_bytes,bool) or not isinstance(chunk_bytes,int) or not 262144<=chunk_bytes<=2097152:raise AgentError('driveInvalidResponse')
            offset=saved.get('offset',0)
            with source.open('rb') as stream:
                while offset<size:
                    self.fence(generation);stream.seek(offset);data=stream.read(min(chunk_bytes,size-offset))
                    response=self.account.cloud('/control/drive/upload/chunk',{'ticket':saved['ticket'],'offset':offset,'data':base64.b64encode(data).decode()},expected_user=state['accountId'])
                    self.fence(generation);next_offset=response.get('nextOffset')
                    if isinstance(next_offset,bool) or not isinstance(next_offset,int) or next_offset<=offset or next_offset>size:raise AgentError('driveInvalidResponse')
                    offset=next_offset;saved['offset']=offset;atomic_json(ticket_path,saved)
                    if response.get('complete'):
                        file=response.get('file',{})
                        if offset!=size or not isinstance(file.get('id'),str):raise AgentError('driveInvalidResponse')
                        ticket_path.unlink(missing_ok=True);return {'id':file['id'],'webViewLink':file.get('webUrl','')}
            # A final response lost after Google commit is recovered by start's
            # asset ID check, without creating a second output file.
            ticket_path.unlink(missing_ok=True);raise AgentError('driveUploadFailed')
    def download(self,file_id,destination,max_bytes):
        with self.lock:
            _,user=self.identity_now();generation=self.auth_generation
            result=self.account.binary_download(file_id,Path(destination).absolute(),max_bytes,expected_user=user.get('id'))
            self.fence(generation)
            path=Path(destination);digest=hashlib.sha256()
            with path.open('rb') as stream:
                for data in iter(lambda:stream.read(1024*1024),b''):digest.update(data)
            return {'path':str(path),'bytes':result['size'],'sha256':digest.hexdigest(),'metadata':{'id':file_id,'name':result.get('name','download'),'mimeType':result['mime']}}
