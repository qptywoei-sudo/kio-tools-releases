"""Organized local/Drive output storage with a durable upload queue."""
from __future__ import annotations
import hashlib,json,mimetypes,os,re,shutil,threading,time,uuid
from datetime import datetime,timezone
from pathlib import Path
from common import AgentError,atomic_json,read_json,private_dir,valid_id
import engine

KINDS={'photos':'사진','videos':'영상','gifs':'GIF','pdf':'PDF','signatures':'서명·도장','codes':'QR·바코드','other':'기타'}
COMPLETED_CACHE_AGE=7*24*3600
DEFAULT_DRIVE_ROOT='__kio_default__'
def safe_download_name(value):
    name=re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]','_',str(value or 'download')).strip(' .')[:180] or 'download'
    if re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',name,re.IGNORECASE):name='_'+name
    return name
def kind_for(path,operation):
    suffix=Path(path).suffix.lower()
    if suffix=='.gif':return 'gifs'
    if suffix=='.pdf':return 'pdf'
    if suffix in ('.mp4','.mov','.avi','.webm','.mkv'):return 'videos'
    if operation=='code_generate':return 'codes'
    if operation=='signature_apply':return 'signatures'
    if suffix in ('.jpg','.jpeg','.png','.webp','.bmp','.tif','.tiff'):return 'photos'
    return 'other'

class StorageLibrary:
    def __init__(self,state,settings,drive):
        self.state=private_dir(Path(state)/'library');self.queue=private_dir(self.state/'uploads');self.cache=private_dir(self.state/'cache')
        self.settings=settings;self.drive=drive;self.lock=threading.RLock();self.worker=None;self.closed=False;self.last_cache_cleanup=-float('inf')
    def read_entry(self,path):
        with self.lock:return read_json(path,{})
    def write_entry(self,path,item):
        # Windows cannot replace a file while another reader lacks delete-share.
        # Serialize our polling readers and tolerate short antivirus/indexer locks.
        with self.lock:
            for attempt in range(6):
                try:atomic_json(path,item);return
                except PermissionError:
                    if attempt==5:raise
                    time.sleep(.02*(attempt+1))
    def cached_source(self,item):
        """A queue entry may reference only its own regular private-cache file."""
        asset=item.get('assetId');value=item.get('source')
        if not valid_id(asset) or not isinstance(value,str):raise AgentError('fileMissing')
        source=Path(value);directory=self.cache/asset
        if source.is_symlink() or directory.is_symlink() or directory.is_junction():raise AgentError('fileMissing')
        if directory.resolve().parent!=self.cache.resolve() or source.resolve().parent!=directory.resolve():raise AgentError('fileMissing')
        if source.name!=item.get('name'):raise AgentError('fileMissing')
        return source
    def cleanup_completed(self,now=None):
        """Retain completed Drive previews seven days; queued/failed bytes never expire."""
        with self.lock:
            if now is None and time.monotonic()-self.last_cache_cleanup<3600:return
            self.last_cache_cleanup=time.monotonic();stamp=time.time() if now is None else now
            for path in self.queue.glob('*.json'):
                item=self.read_entry(path)
                if not isinstance(item,dict) or path.stem!=item.get('assetId') or item.get('status')!='complete' or item.get('cacheExpiredAt'):continue
                try:
                    # Earlier versions did not record completion time. Start their
                    # retention now rather than treating creation as completion.
                    if not item.get('completedAt'):
                        item['completedAt']=datetime.fromtimestamp(stamp,timezone.utc).isoformat();self.write_entry(path,item);continue
                    completed=datetime.fromisoformat(item['completedAt']).timestamp()
                    if stamp-completed<COMPLETED_CACHE_AGE:continue
                    source=self.cached_source(item)
                    if source.exists() and not source.is_file():continue
                    source.unlink(missing_ok=True)
                    try:source.parent.rmdir()
                    except OSError:pass
                    item['cacheExpiredAt']=datetime.fromtimestamp(stamp,timezone.utc).isoformat();self.write_entry(path,item)
                except (AgentError,OSError,ValueError,TypeError):continue
    def drive_status(self,allow_network=False):
        cached=getattr(self.drive,'cached_status',None)
        if not callable(cached):return self.drive.status()
        value=cached()
        return self.drive.status() if allow_network and not value['connected'] else value
    def status(self):
        self.cleanup_completed()
        with self.lock:
            rows=[row for p in self.queue.glob('*.json') if isinstance(row:=self.read_entry(p),dict)]
            worker_running=bool(self.worker and self.worker.is_alive())
        if not worker_running:
            # A crash or persistently locked row must never leave the UI stuck
            # at uploading; the durable row is eligible for an explicit retry.
            for row in rows:
                if row.get('status')=='uploading':row.update(status='failed',error='driveUploadFailed')
        pending=[r for r in rows if r.get('status') in ('pending','failed','uploading')]
        return {'mode':self.settings.get('saveMode','local'),'localFolderName':str(self.settings.get('localSaveFolder') or self.settings.get('saveFolder','')),'layout':'사진 · 영상 · GIF · PDF / 연도 / 월','pending':len(pending),'failed':sum(r.get('status')=='failed' for r in pending),'uploading':sum(r.get('status')=='uploading' for r in pending),'drive':self.drive_status(),'recent':[{k:r.get(k) for k in ('assetId','name','status','error','driveUrl')} for r in sorted(rows,key=lambda r:r.get('createdAt',''),reverse=True)[:8]]}
    def publish(self,paths,operation,mode_override=None,expected_account=None):
        mode=mode_override or self.settings.get('saveMode','local')
        if mode not in ('local','drive','both'):raise AgentError('invalidRequest')
        drive_state=self.drive_status(allow_network=True)
        if mode in ('drive','both') and not drive_state['connected']:raise AgentError('driveNotConnected')
        account_id=drive_state.get('accountId') or drive_state.get('email','')
        if expected_account is not None and expected_account!=account_id:raise AgentError('driveAccountChanged')
        drive_root=drive_state.get('rootId') or DEFAULT_DRIVE_ROOT
        local_root=Path(self.settings.get('localSaveFolder') or self.settings['saveFolder'])
        results=[];summaries=[]
        for value in paths:
            source=Path(value);asset=str(uuid.uuid4());now=datetime.now().astimezone();kind=kind_for(source,operation)
            relative=Path(KINDS[kind])/now.strftime('%Y')/now.strftime('%m')/source.name
            digest=hashlib.sha256()
            with source.open('rb') as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
            meta={'schemaVersion':1,'application':'kio-control','assetId':asset,'name':source.name,'kind':kind,'mime':mimetypes.guess_type(source.name)[0] or 'application/octet-stream','bytes':source.stat().st_size,'sha256':digest.hexdigest(),'createdAt':now.isoformat(),'operation':operation,'relativePath':relative.as_posix()}
            local=None
            if mode in ('local','both'):
                root=local_root;destination=engine.write_atomic(root/relative.parent,source.stem,source.suffix,lambda p:shutil.copyfile(source,p))
                local=destination;meta['name']=destination.name;meta['relativePath']=destination.relative_to(root).as_posix()
                catalog=root/'.kio-library'/'library.json'
                if not catalog.exists():atomic_json(catalog,{'schemaVersion':1,'application':'kio-control','entries':'items/{assetId}.json','pathFormat':'{kind}/{year}/{month}/{filename}','createdAt':now.isoformat()})
                atomic_json(root/'.kio-library'/'items'/(asset+'.json'),meta)
            if mode in ('drive','both'):
                # A private retry cache is required even for Drive-only saves.
                # It is not shown as a second permanent local destination.
                cached=private_dir(self.cache/asset)/meta['name'];shutil.copyfile(source,cached)
                queued={**meta,'source':str(cached),'localPath':str(local) if local else '','localRoot':str(root) if local else '', 'status':'pending','error':'','account':drive_state.get('email',''),'accountId':account_id,'driveRootId':drive_root}
                self.write_entry(self.queue/(asset+'.json'),queued)
                display=local or cached
            else:display=local
            results.append(str(display));summaries.append({'assetId':asset,'local':mode in ('local','both'),'drive':'pending' if mode in ('drive','both') else 'off'})
        if mode in ('drive','both'):self.retry()
        return results,summaries
    def import_download(self,source,metadata,generation):
        """Publish a downloaded binary locally, without invoking the upload pipeline."""
        source=Path(source);name=safe_download_name(metadata.get('name'));asset=str(uuid.uuid4());now=datetime.now().astimezone()
        kind=kind_for(name,'drive_download');root=Path(self.settings.get('localSaveFolder') or self.settings['saveFolder'])
        directory=root/KINDS[kind]/now.strftime('%Y')/now.strftime('%m');directory.mkdir(parents=True,exist_ok=True)
        temporary=directory/('.kio-download-'+asset+'.part');destination=None
        try:
            # The server supplies a private, generation-bound staging file. Stage
            # locally before taking the account lock for atomic publication.
            with source.open('rb') as reader,temporary.open('xb') as writer:
                shutil.copyfileobj(reader,writer,1024*1024);writer.flush();os.fsync(writer.fileno())
            stem=Path(name).stem;suffix=Path(name).suffix
            with self.drive.lock:
                self.drive.fence(generation)
                for index in range(1,100000):
                    candidate=directory/(stem+('' if index==1 else '_'+str(index))+suffix)
                    try:engine.publish_exclusive(temporary,candidate);destination=candidate;break
                    except FileExistsError:continue
                if destination is None:raise AgentError('storageFull',507)
                account=self.drive.status().get('accountId','')
            digest=hashlib.sha256()
            with destination.open('rb') as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
            info={'schemaVersion':1,'application':'kio-control','assetId':asset,'name':destination.name,'kind':kind,'mime':metadata.get('mimeType') or mimetypes.guess_type(name)[0] or 'application/octet-stream','bytes':destination.stat().st_size,'sha256':digest.hexdigest(),'createdAt':now.isoformat(),'operation':'drive_download','relativePath':destination.relative_to(root).as_posix(),'driveId':metadata.get('id',''),'accountId':account}
            catalog=root/'.kio-library'/'library.json'
            if not catalog.exists():atomic_json(catalog,{'schemaVersion':1,'application':'kio-control','entries':'items/{assetId}.json','pathFormat':'{kind}/{year}/{month}/{filename}','createdAt':now.isoformat()})
            atomic_json(root/'.kio-library'/'items'/(asset+'.json'),info)
            return destination
        finally:temporary.unlink(missing_ok=True)
    def retry(self):
        with self.lock:
            if self.worker and self.worker.is_alive():return self.status()
            if not self.drive_status()['connected']:return self.status()
            self.closed=False;self.worker=threading.Thread(target=self.process_queue,daemon=True,name='KIO-Drive-Upload');self.worker.start()
        return self.status()
    def process_queue(self):
        try:self.drain_queue()
        finally:
            with self.lock:
                if self.worker is threading.current_thread():self.worker=None
    def drain_queue(self):
        attempted=set()
        while True:
            with self.lock:
                candidates=[path for path in sorted(self.queue.glob('*.json')) if path.name not in attempted]
                if self.closed or not candidates:
                    # A publisher racing this exit observes no worker and starts
                    # a new one. New rows added while uploading get another pass.
                    self.worker=None;return
            for path in candidates:
                if self.closed:
                    with self.lock:self.worker=None
                    return
                attempted.add(path.name);item=self.read_entry(path)
                if not isinstance(item,dict) or path.stem!=item.get('assetId'):continue
                if item.get('status') not in ('pending','failed','uploading'):continue
                try:
                    # Retry each row at most once per worker run; failed files
                    # remain durable without a tight automatic retry loop.
                    drive_state=self.drive_status(allow_network=True)
                    if item.get('account')!=drive_state.get('email','') or (item.get('accountId') and item['accountId']!=(drive_state.get('accountId') or drive_state.get('email',''))):raise AgentError('driveAccountChanged')
                    item.setdefault('driveRootId',DEFAULT_DRIVE_ROOT)
                    source=self.cached_source(item)
                    if not source.is_file():raise AgentError('fileMissing')
                    item.update(status='uploading',error='');self.write_entry(path,item)
                    result=self.drive.upload(source,item)
                    item.update(status='complete',completedAt=datetime.now(timezone.utc).isoformat(),driveId=result['id'],driveUrl=result.get('webViewLink','https://drive.google.com/file/d/'+result['id']+'/view'),error='')
                    self.write_entry(path,item)
                    if item.get('localPath'):
                        # Old queue rows may have no localRoot. Cloud completion
                        # is still valid; skip their optional sidecar update.
                        if item.get('localRoot'):
                            root=Path(item['localRoot']);info={k:v for k,v in item.items() if k not in ('source','localPath','localRoot','account','status','error')}
                            try:atomic_json(root/'.kio-library'/'items'/(item['assetId']+'.json'),info)
                            except OSError:pass
                        try:
                            self.cached_source(item).unlink(missing_ok=True);source.parent.rmdir()
                        except (AgentError,OSError):pass
                except Exception as error:
                    item.update(status='failed',error=error.code if isinstance(error,AgentError) else 'driveUploadFailed')
                    try:self.write_entry(path,item)
                    except OSError:pass
    def close(self):self.closed=True
