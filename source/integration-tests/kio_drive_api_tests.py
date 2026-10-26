"""Live loopback HTTP and filesystem tests with a deliberately fake Google service."""
import sys,tempfile,unittest,json,hashlib,time,threading,urllib.request,urllib.error,socket
from pathlib import Path
from unittest.mock import patch
source=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(source/'engine'),str(source/'agent')]
from common import AgentError,atomic_json,read_json
from server import Server
from kio_fixture import VerifiedAgent as Agent
from storage_library import StorageLibrary,safe_download_name,DEFAULT_DRIVE_ROOT
from PIL import Image

class FixtureDrive:
    def __init__(self,fixture):
        self.fixture=Path(fixture);self.lock=threading.RLock();self.auth_generation=0
        self.connected=True;self.email='fixture@example.invalid';self.account='fixture-account';self.root='root-a';self.uploads=[];self.fail=False;self.switch_during_download=False;self.last_limit=None
        self.name='테스트 사진.png';self.nodes=[{'id':'root-a','name':'KIO 컨트롤','mimeType':'application/vnd.google-apps.folder'},{'id':'folder-b','name':'공유할 결과','mimeType':'application/vnd.google-apps.folder'}]
    def fence(self,generation):
        if generation!=self.auth_generation:raise AgentError('driveAccountChanged')
    def status(self):
        return {'configured':True,'connected':self.connected,'connecting':False,'email':self.email,'accountId':self.account,'displayName':'QA Fixture','rootId':self.root,'folderName':next((x['name'] for x in self.nodes if x['id']==self.root),'KIO 컨트롤'),'scopeLimited':True,'scope':'https://www.googleapis.com/auth/drive.file','error':''}
    def check(self):
        if not self.connected:raise AgentError('driveNotConnected')
        if self.fail:raise AgentError('driveNetwork')
    def upload(self,path,metadata):
        self.check();self.uploads.append((Path(path).read_bytes(),metadata.copy()));return {'id':'cloud-'+metadata['assetId'],'webViewLink':'https://drive.google.com/file/d/fixture/view'}
    def browse_folders(self,parent_id=None,page_token=None):
        self.check();return {'files':self.nodes,'nextPageToken':'','scopeLimited':True}
    def create_folder(self,name,parent_id=None):
        self.check()
        if not isinstance(name,str) or not name.strip():raise AgentError('invalidRequest')
        item={'id':'created-'+str(len(self.nodes)),'name':name,'mimeType':'application/vnd.google-apps.folder','parents':[parent_id or self.root]};self.nodes.append(item);return item
    def select_root(self,folder_id=None):
        self.check();self.root=folder_id or 'root-a';return self.status()
    def list_library(self,parent_id=None,page_token=None,query='',kind=None):
        self.check();items=[{'id':'photo-1','name':self.name,'mimeType':'image/png','size':str(self.fixture.stat().st_size),'modifiedTime':'2026-10-12T00:00:00Z','parents':[parent_id or self.root],'capabilities':{'canDownload':True}}]
        if query:items=[item for item in items if query in item['name']]
        return {'files':items,'nextPageToken':'','scopeLimited':True,'parentId':parent_id or self.root}
    def download(self,file_id,destination,max_bytes):
        self.check();self.last_limit=max_bytes
        if file_id!='photo-1':raise AgentError('driveFileMissing',404)
        data=self.fixture.read_bytes();Path(destination).write_bytes(data)
        if self.switch_during_download:self.auth_generation+=1;self.account='different-account'
        return {'path':str(destination),'metadata':{'id':file_id,'name':self.name,'mimeType':'image/png'},'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    def connect(self):return self.status()
    def cancel_connect(self):return self.status()
    def disconnect(self):self.auth_generation+=1;self.connected=False;return self.status()

class DriveApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.fixture=self.root/'fixture.png';Image.new('RGB',(48,32),'#ffe600').save(self.fixture)
        with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
        self.agent=Agent(self.root/'state',source/'desktop-ui'/'dist',port);self.agent.storage.close()
        self.drive=FixtureDrive(self.fixture);self.agent.drive=self.drive;self.agent.settings.update(saveMode='local',saveFolder=str(self.root/'local'),localSaveFolder=str(self.root/'local'))
        self.agent.storage=StorageLibrary(self.agent.state,self.agent.settings,self.drive)
        self.server=Server(self.agent);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.origin=f'http://127.0.0.1:{port}';self.token=self.agent.desktop_session['token']
    def tearDown(self):
        self.agent.storage.close()
        if self.agent.storage.worker:self.agent.storage.worker.join(3)
        self.server.shutdown();self.server.server_close();self.agent.close();self.thread.join(3);self.tmp.cleanup()
    def request(self,path,body=None,token=None,origin=None,method=None):
        headers={'Origin':origin or self.origin,'X-Local-Agent-Token':token or self.token,'Content-Type':'application/json'}
        request=urllib.request.Request(self.origin+path,data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method or ('POST' if body is not None else 'GET'))
        try:
            with urllib.request.urlopen(request,timeout=10) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as response:return response.code,json.load(response)
    def wait(self):
        if self.agent.storage.worker:self.agent.storage.worker.join(3)
    def test_native_credential_access_and_regular_pairings_denied(self):
        status,body=self.request('/storage');self.assertEqual(status,200);self.assertTrue(body['drive']['connected'])
        legacy='x'*48;self.agent.tokens[self.origin]={'digest':hashlib.sha256(legacy.encode()).hexdigest()}
        status,denied=self.request('/storage',token=legacy);self.assertEqual(status,401);self.assertEqual(denied['errorCode'],'unauthorized')
        status,denied=self.request('/drive/folders/list',{},token=legacy);self.assertEqual(status,401);self.assertEqual(denied['errorCode'],'unauthorized')
        extension='chrome-extension://'+'a'*32;self.agent.origins.add(extension);self.agent.tokens[extension]={'digest':hashlib.sha256(legacy.encode()).hexdigest()}
        self.assertEqual(self.request('/drive/files/list',{},token=legacy,origin=extension)[0],403)
    def test_signed_out_cloud_identity_is_denied_even_with_native_desktop_token(self):
        self.agent.account.logout()
        status,body=self.request('/storage')
        self.assertEqual(status,401);self.assertEqual(body['errorCode'],'ACCOUNT_REQUIRED')
        self.assertEqual(self.drive.uploads,[])
    def test_folder_selection_and_library_contracts(self):
        status,body=self.request('/drive/folders/list',{});self.assertEqual(status,200);self.assertEqual(len(body['folders']),2)
        status,created=self.request('/drive/folders/create',{'name':'새 폴더','parentId':'root-a'});self.assertEqual(status,200)
        ident=created['folder']['id'];status,selected=self.request('/drive/folders/select',{'folderId':ident});self.assertEqual(status,200);self.assertEqual(selected['drive']['rootId'],ident)
        status,files=self.request('/drive/files/list',{});self.assertEqual(status,200);self.assertEqual(files['parentId'],ident);self.assertEqual(files['files'][0]['id'],'photo-1')
        self.assertEqual(self.request('/drive/files/list',{'query':'absent'})[1]['files'],[])
    def test_upload_uses_registered_input_only_and_keeps_local_mode(self):
        uploaded=self.agent.register(self.fixture,self.origin,'native');before=self.fixture.read_bytes()
        status,body=self.request('/drive/files/upload',{'inputIds':[uploaded['id']]});self.assertEqual(status,202);self.assertEqual(body['queued'],1);self.wait()
        self.assertEqual(self.fixture.read_bytes(),before);self.assertEqual(self.agent.settings['saveMode'],'local');self.assertEqual(len(self.drive.uploads),1)
        row=self.drive.uploads[0][1];self.assertEqual(row['accountId'],'fixture-account');self.assertEqual(row['driveRootId'],'root-a');self.assertFalse((self.root/'local').exists())
        self.assertEqual(self.request('/drive/files/upload',{'paths':[str(self.fixture)]})[0],400)
        self.assertEqual(self.request('/drive/files/upload',{'inputIds':['00000000-0000-0000-0000-000000000001']})[0],403)
        another=self.agent.register(self.fixture,'another-owner','native');self.assertEqual(self.request('/drive/files/upload',{'inputIds':[another['id']]})[0],403)
    def test_queue_pins_account_and_folder_through_retry(self):
        self.drive.fail=True;_,items=self.agent.storage.publish([self.fixture],'drive_upload',mode_override='drive');self.wait()
        self.drive.fail=False;self.drive.root='folder-b';self.agent.storage.retry();self.wait();self.assertEqual(self.drive.uploads[0][1]['driveRootId'],'root-a')
        self.drive.fail=True;_,items=self.agent.storage.publish([self.fixture],'drive_upload',mode_override='drive');self.wait();self.drive.fail=False;self.drive.account='other-permission-id'
        self.agent.storage.retry();self.wait();row=read_json(self.agent.storage.queue/(items[0]['assetId']+'.json'));self.assertEqual(row['error'],'driveAccountChanged');self.assertEqual(len(self.drive.uploads),1)
    def test_stale_account_from_file_picker_is_rejected_before_queueing(self):
        file=self.agent.register(self.fixture,self.origin,'native');self.drive.account='new-account'
        status,body=self.request('/drive/files/upload',{'inputIds':[file['id']],'expectedAccountId':'fixture-account'})
        self.assertEqual(status,400);self.assertEqual(body['errorCode'],'driveAccountChanged');self.assertEqual(list(self.agent.storage.queue.glob('*.json')),[])
        status,_=self.request('/drive/files/upload',{'inputIds':[file['id']],'expectedAccountId':'new-account'});self.assertEqual(status,202);self.wait();self.assertEqual(len(self.drive.uploads),1)
    def test_unresolved_default_root_is_pinned_without_cloud_request(self):
        self.drive.root='';self.drive.fail=True;_,items=self.agent.storage.publish([self.fixture],'drive_upload',mode_override='drive');self.wait()
        row=read_json(self.agent.storage.queue/(items[0]['assetId']+'.json'));self.assertEqual(row['driveRootId'],DEFAULT_DRIVE_ROOT)
    def test_legacy_email_bound_queue_survives_new_permission_id(self):
        self.drive.fail=True;_,items=self.agent.storage.publish([self.fixture],'drive_upload',mode_override='drive');self.wait()
        path=self.agent.storage.queue/(items[0]['assetId']+'.json');row=read_json(path);row.pop('accountId');row.pop('driveRootId');atomic_json(path,row)
        self.drive.fail=False;self.agent.storage.retry();self.wait();self.assertEqual(read_json(path)['status'],'complete');self.assertEqual(self.drive.uploads[0][1]['driveRootId'],DEFAULT_DRIVE_ROOT)
        self.drive.fail=True;_,items=self.agent.storage.publish([self.fixture],'drive_upload',mode_override='drive');self.wait()
        path=self.agent.storage.queue/(items[0]['assetId']+'.json');row=read_json(path);row.pop('accountId');atomic_json(path,row)
        self.drive.fail=False;self.drive.email='another@example.invalid';self.agent.storage.retry();self.wait();self.assertEqual(read_json(path)['error'],'driveAccountChanged');self.assertEqual(len(self.drive.uploads),1)
    def test_files_queued_during_upload_are_drained_without_extra_retry(self):
        started=threading.Event();release=threading.Event();original=self.drive.upload;calls=[]
        def blocked(path,metadata):
            calls.append(metadata['assetId'])
            if len(calls)==1:started.set();release.wait(3)
            return original(path,metadata)
        with patch.object(self.drive,'upload',side_effect=blocked):
            self.agent.storage.publish([self.fixture],'drive_upload',mode_override='drive');self.assertTrue(started.wait(3))
            self.agent.storage.publish([self.fixture],'drive_upload',mode_override='drive');release.set();self.wait()
        self.assertEqual(len(self.drive.uploads),2);self.assertEqual(self.agent.storage.status()['pending'],0)
    def test_legacy_missing_local_root_does_not_undo_cloud_success(self):
        self.drive.fail=True;self.agent.settings['saveMode']='both';_,items=self.agent.storage.publish([self.fixture],'image_export');self.wait()
        path=self.agent.storage.queue/(items[0]['assetId']+'.json');row=read_json(path);row.pop('localRoot');atomic_json(path,row)
        self.drive.fail=False;self.agent.storage.retry();self.wait();self.assertEqual(read_json(path)['status'],'complete');self.assertEqual(len(self.drive.uploads),1)
    def test_transient_windows_queue_file_lock_does_not_strand_upload(self):
        failed=[]
        def temporary_lock(path,item):
            if item.get('status')=='failed' and not failed:failed.append(True);raise PermissionError('fixture Windows sharing violation')
            atomic_json(path,item)
        self.drive.fail=True
        with patch('storage_library.atomic_json',side_effect=temporary_lock):
            self.agent.storage.publish([self.fixture],'drive_upload',mode_override='drive');self.wait()
        self.assertEqual(failed,[True]);self.assertEqual(self.agent.storage.status()['failed'],1)
        self.drive.fail=False;self.agent.storage.retry();self.wait();self.assertEqual(self.agent.storage.status()['pending'],0)
    def test_persistent_queue_lock_keeps_retry_available_and_clears_worker(self):
        self.drive.fail=True
        def locked_failure(path,item):
            if item.get('status')=='failed':raise PermissionError('fixture persistent file lock')
            atomic_json(path,item)
        with patch('storage_library.atomic_json',side_effect=locked_failure):
            self.agent.storage.publish([self.fixture],'drive_upload',mode_override='drive');self.wait()
        status=self.agent.storage.status();self.assertEqual(status['uploading'],0);self.assertEqual(status['failed'],1);self.assertIsNone(self.agent.storage.worker)
        self.drive.fail=False;self.agent.storage.retry();self.wait();self.assertEqual(self.agent.storage.status()['pending'],0)
    def test_download_organizes_without_reupload_or_overwrite(self):
        self.agent.settings['saveMode']='both'
        status,first=self.request('/drive/files/download',{'fileId':'photo-1'});self.assertEqual(status,200);self.assertTrue(first['downloaded'])
        status,second=self.request('/drive/files/download',{'fileId':'photo-1'});self.assertEqual(status,200)
        first_path=self.agent.resolve(first['file']['id'],self.origin);second_path=self.agent.resolve(second['file']['id'],self.origin)
        self.assertNotEqual(first_path,second_path);self.assertEqual(first_path.read_bytes(),self.fixture.read_bytes());self.assertIn('사진',first_path.parts);self.assertEqual(self.drive.uploads,[]);self.assertEqual(self.drive.last_limit,512*1024*1024)
        self.assertEqual(list((self.agent.state/'uploads').glob('*/*')),[])
    def test_remote_filename_cannot_escape_local_folder(self):
        self.drive.name='../../outside\\CON.png'
        status,body=self.request('/drive/files/download',{'fileId':'photo-1'});self.assertEqual(status,200)
        destination=self.agent.resolve(body['file']['id'],self.origin);self.assertTrue(destination.is_relative_to(self.root/'local'));self.assertNotIn('/',destination.name);self.assertNotIn('\\',destination.name)
        self.assertEqual(safe_download_name('CON.png'),'_CON.png');self.assertEqual(safe_download_name('..'),'download')
    def test_account_change_during_download_never_publishes(self):
        self.drive.switch_during_download=True
        status,body=self.request('/drive/files/download',{'fileId':'photo-1'});self.assertEqual(status,400);self.assertEqual(body['errorCode'],'driveAccountChanged')
        self.assertEqual(list((self.root/'local').rglob('*.png')),[]);self.assertEqual(list((self.agent.state/'uploads').glob('*/*')),[])
    def test_drive_only_cache_is_usable_but_queue_metadata_is_private(self):
        paths,_=self.agent.storage.publish([self.fixture],'image_export',mode_override='drive');self.wait()
        file=self.agent.register(paths[0],self.origin);self.assertEqual(self.agent.resolve(file['id'],self.origin).read_bytes(),self.fixture.read_bytes())
        with self.assertRaisesRegex(AgentError,'forbiddenFile'):self.agent.register(next(self.agent.storage.queue.glob('*.json')),self.origin)
    def test_real_image_export_job_succeeds_in_drive_only_mode(self):
        self.agent.settings['saveMode']='drive';file=self.agent.register(self.fixture,self.origin,'native')
        status,response=self.request('/jobs',{'operation':'image_export','inputs':[file['id']],'options':{}});self.assertEqual(status,202)
        job=response['job'];deadline=time.time()+10
        while job['status'] not in ('complete','completed','failed') and time.time()<deadline:
            time.sleep(.05);status,response=self.request('/jobs/'+job['id']);job=response['job']
        self.assertIn(job['status'],('complete','completed'),job);self.assertEqual(len(job['result']['files']),1)
        result=self.agent.resolve(job['result']['files'][0]['id'],self.origin);self.assertEqual(result.read_bytes(),self.fixture.read_bytes());self.wait();self.assertEqual(len(self.drive.uploads),1)
    def test_endpoint_validation_and_disconnect(self):
        for path,body in [('/drive/folders/list',{'parentId':False}),('/drive/folders/select',{'folderId':'../escape'}),('/drive/connect',{'switchAccount':'true'}),('/drive/files/download',{'fileId':'photo-1','path':'C:/escape'})]:self.assertEqual(self.request(path,body)[0],400)
        self.agent.settings['saveMode']='both';status,body=self.request('/drive/disconnect',{});self.assertEqual(status,200);self.assertFalse(body['connected']);self.assertEqual(self.agent.settings['saveMode'],'local')
        self.assertEqual(self.request('/drive/files/list',{})[1]['errorCode'],'driveNotConnected')

if __name__=='__main__':unittest.main(verbosity=2)
