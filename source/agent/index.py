"""Local-only, user-selected folder index. No OCR, network or whole-file AI upload."""
from __future__ import annotations
import os, io, sqlite3, threading, time, uuid, re, zipfile, xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone, timedelta
from common import AgentError, utc

IGNORED={'.git','node_modules','.Trash','__pycache__','.DS_Store','.venv','venv'}
def contained(path,root):
    p=Path(path); r=Path(root)
    try:
        # Reject symlinks anywhere, including a replaced formerly authorized root.
        for part in [p,*p.parents]:
            if part.is_symlink():return False
        return p.resolve().is_relative_to(r.resolve())
    except OSError:return False

def read_local_file(path,max_bytes=64*1024*1024):
    p=Path(path);fd=None;directory=None
    try:
        before=p.stat()
        if not contained(p,p.parent) or before.st_size>64*1024*1024:return None
        if os.name!='nt':
            directory=os.open(p.anchor,os.O_RDONLY|os.O_DIRECTORY)
            for part in p.parts[1:-1]:
                nextdir=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory);os.close(directory);directory=nextdir
            fd=os.open(p.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
        else:fd=os.open(p,os.O_RDONLY|os.O_BINARY)
        opened=os.fstat(fd)
        if (opened.st_ino,opened.st_mtime_ns,opened.st_size)!=(before.st_ino,before.st_mtime_ns,before.st_size):return None
        with os.fdopen(fd,'rb') as stream:
            fd=None;data=stream.read(max_bytes);after=os.fstat(stream.fileno())
        if len(data)>64*1024*1024 or not contained(p,p.parent) or (after.st_ino,after.st_mtime_ns,after.st_size)!=(opened.st_ino,opened.st_mtime_ns,opened.st_size):return None
        return data
    except OSError:return None
    finally:
        if fd is not None:os.close(fd)
        if directory is not None:os.close(directory)

def extract_text(path):
    p=Path(path);suffix=p.suffix.lower()
    text_extensions={'.txt','.md','.csv','.json','.html','.log','.xml','.yaml','.yml'}
    if suffix not in text_extensions|{'.pdf','.docx','.xlsx','.pptx'}:return ''
    try:
        data=read_local_file(p,200_000 if suffix in text_extensions else 64*1024*1024)
        if data is None:return ''
        if suffix in text_extensions:return data[:200_000].decode('utf-8',errors='replace')[:100_000]
        if suffix=='.pdf':
            import pymupdf
            with pymupdf.open(stream=data,filetype='pdf') as doc:
                if doc.needs_pass:return ''
                out=[];size=0
                for page in doc:
                    text=page.get_text()[:30_000];out.append(text);size+=len(text)
                    if size>100_000 or len(out)>=100:break
                return '\n'.join(out)[:100_000]
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            files=[x for x in z.infolist() if x.filename.endswith('.xml') and x.file_size<2_000_000 and x.filename.startswith(('word/','xl/sharedStrings','xl/worksheets/','ppt/slides/'))][:100]
            out=[]
            for item in files:
                part=z.read(item)
                if b'<!DOCTYPE' in part or b'<!ENTITY' in part:continue
                tree=ET.fromstring(part)
                out.extend(t.text for t in tree.iter() if t.tag.rsplit('}',1)[-1] in {'t','v'} and t.text)
                if sum(map(len,out))>100_000:break
            return ' '.join(out)[:100_000]
    except (OSError,ValueError,RuntimeError,zipfile.BadZipFile,ET.ParseError):pass
    return ''

class LazyFileIndex:
    """Open the legacy index only when its API is used, after private-row cleanup."""
    def __init__(self,state,emit=lambda _:None,background=True,*,private_state=None):
        self._state=state;self._emit=emit;self._background=background;self._private_state=private_state
        self._gate=threading.Lock();self._instance=None;self._closed=False
    def _get(self):
        with self._gate:
            if self._closed:raise RuntimeError('File index is closed')
            if self._instance is None:
                instance=FileIndex(self._state,self._emit,background=self._background)
                try:
                    if self._private_state is not None:
                        # Account profiles must exclude the entire agent state,
                        # including credentials belonging to other identities.
                        instance.private_state=Path(self._private_state).resolve()
                        with instance.lock:
                            for row in list(instance.db.execute('SELECT files.id,roots.path AS base,files.relative FROM files JOIN roots ON files.root=roots.id')):
                                if instance.private_path(Path(row['base'])/row['relative']):instance.db.execute('DELETE FROM files WHERE id=?',(row['id'],))
                            instance.db.commit()
                except BaseException:
                    instance.close();raise
                # Publish only after all original privacy cleanup has finished.
                self._instance=instance
            return self._instance
    def __getattr__(self,name):
        if name.startswith('_'):raise AttributeError(name)
        return getattr(self._get(),name)
    def close(self):
        with self._gate:
            self._closed=True
            if self._instance is not None:
                self._instance.close();self._instance=None

class FileIndex:
    def __init__(self,state,emit=lambda _:None,background=True):
        # Our credentials, diagnostics and temporary outputs are engine state,
        # not user search data, even when the user selects its parent folder.
        self.private_state=Path(state).resolve()
        self.lock=threading.RLock();self.emit=emit;self.stopping=threading.Event();self.dirty=set();self.watchers={};self.cancelled=set()
        self.db=sqlite3.connect(str(Path(state)/'index.sqlite'),check_same_thread=False)
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS roots(id TEXT PRIMARY KEY,path TEXT UNIQUE,name TEXT,status TEXT,done INT DEFAULT 0,total INT DEFAULT 0);
        CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY,root TEXT,relative TEXT,name TEXT,extension TEXT,size INTEGER,created REAL,modified REAL,stamp TEXT,text TEXT,UNIQUE(root,relative));
        CREATE INDEX IF NOT EXISTS files_root ON files(root);''')
        self.db.commit()
        # Legacy private rows must be removed even when directory scanning is disabled.
        for row in list(self.db.execute('SELECT files.id,roots.path AS base,files.relative FROM files JOIN roots ON files.root=roots.id')):
            if self.private_path(Path(row['base'])/row['relative']):self.db.execute('DELETE FROM files WHERE id=?',(row['id'],))
        self.db.commit()
        self.cancelled.update(x['id'] for x in self.db.execute("SELECT id FROM roots WHERE status='cancelled'"))
        self.thread=None
        if background:self.start_background()
    def start_background(self):
        with self.lock:
            if self.thread is not None or self.stopping.is_set():return
            self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start()
    def private_path(self,path):
        try:return Path(path).resolve().is_relative_to(self.private_state)
        except (OSError,ValueError):return True
    def roots(self):
        with self.lock:return [dict(id=x['id'],name=x['name'],path=x['path'],status=x['status'],done=x['done'],total=x['total']) for x in self.db.execute('SELECT * FROM roots')]
    def add(self,path):
        p=Path(path).expanduser()
        if not p.is_dir() or p.is_symlink() or self.private_path(p):raise AgentError('unsafePath')
        p=p.resolve()
        # Selecting a folder explicitly authorizes only that subtree, not parent aliases.
        with self.lock:
            old=self.db.execute('SELECT id FROM roots WHERE path=?',(str(p),)).fetchone()
            ident=old[0] if old else str(uuid.uuid4())
            self.db.execute('INSERT OR IGNORE INTO roots(id,path,name,status) VALUES(?,?,?,?)',(ident,str(p),p.name,'queued'))
            self.db.execute("UPDATE roots SET status='queued' WHERE id=?",(ident,));self.cancelled.discard(ident);self.db.commit();self.dirty.add(ident)
        self.watch(ident,p)
        self.start_background()
        return ident
    def remove(self,ident):
        with self.lock:
            self.db.execute('DELETE FROM files WHERE root=?',(ident,));self.db.execute('DELETE FROM roots WHERE id=?',(ident,));self.db.commit();self.dirty.discard(ident);self.cancelled.discard(ident)
        observer=self.watchers.pop(ident,None)
        if observer:observer.stop()
    def cancel(self,ident):
        with self.lock:
            row=self.db.execute('SELECT done,total FROM roots WHERE id=?',(ident,)).fetchone()
            if not row:raise AgentError('rootMissing',404)
            self.cancelled.add(ident);self.dirty.discard(ident)
            self.db.execute("UPDATE roots SET status='cancelled' WHERE id=?",(ident,));self.db.commit()
            event={'type':'index','rootId':ident,'status':'cancelled','done':row['done'],'total':row['total']}
        self.emit(event)
        return {key:value for key,value in event.items() if key!='type'}
    def active(self,ident):
        with self.lock:return not self.stopping.is_set() and ident not in self.cancelled and self.db.execute('SELECT 1 FROM roots WHERE id=?',(ident,)).fetchone() is not None
    def watch(self,ident,path):
        if ident in self.watchers:return
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
            owner=self
            class Events(FileSystemEventHandler):
                def on_any_event(self,event):
                    if owner.private_path(event.src_path) and (not getattr(event,'dest_path','') or owner.private_path(event.dest_path)):return
                    if event.event_type in ('created','modified','deleted','moved','closed'):
                        with owner.lock:
                            if ident not in owner.cancelled:owner.dirty.add(ident)
            watcher=Observer();watcher.schedule(Events(),str(path),recursive=True);watcher.start();self.watchers[ident]=watcher
        except (ImportError,OSError,RuntimeError):
            # Filesystems such as synced Drive may not deliver native events: reconciliation remains enabled.
            pass
    def reconcile(self,ident):
        with self.lock:
            row=self.db.execute('SELECT * FROM roots WHERE id=?',(ident,)).fetchone()
        if not row or not self.active(ident):return
        with self.lock:
            self.db.execute("UPDATE roots SET status='indexing',done=0,total=0 WHERE id=?",(ident,));self.db.commit()
        self.emit({'type':'index','rootId':ident,'status':'indexing','done':0,'total':0})
        root=Path(row['path']);found=[]
        if root.is_dir() and not root.is_symlink() and not self.private_path(root):
            for base,dirs,names in os.walk(root,followlinks=False):
                dirs[:]=[x for x in dirs if x not in IGNORED and not x.startswith('.') and not (Path(base)/x).is_symlink() and not self.private_path(Path(base)/x)]
                for name in names:
                    if not self.active(ident):return
                    p=Path(base)/name
                    if name.startswith('.') or self.private_path(p) or not contained(p,root):continue
                    try:
                        st=p.stat()
                        if p.is_file():found.append((p,st))
                    except OSError:continue
                    if len(found)>=100_000:break
                if len(found)>=100_000:break
        total=len(found);seen=set()
        for n,(path,st) in enumerate(found):
            if not self.active(ident):return
            relative=str(path.relative_to(root));seen.add(relative);stamp=f'{st.st_ino}:{st.st_mtime_ns}:{st.st_size}'
            with self.lock:old=self.db.execute('SELECT id,stamp FROM files WHERE root=? AND relative=?',(ident,relative)).fetchone()
            if not old or old['stamp']!=stamp:
                text=extract_text(path);fid=old['id'] if old else str(uuid.uuid4())
                try:current=path.stat()
                except OSError:seen.discard(relative);continue
                if not contained(path,root) or (current.st_ino,current.st_mtime_ns,current.st_size)!=(st.st_ino,st.st_mtime_ns,st.st_size):seen.discard(relative);continue
                with self.lock:
                    if not self.active(ident):return
                    self.db.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?,?,?,?,?)',(fid,ident,relative,path.name,path.suffix.lower(),st.st_size,st.st_ctime,st.st_mtime,stamp,text))
            if n%50==0:
                with self.lock:
                    if not self.active(ident):return
                    self.db.execute('UPDATE roots SET status=?,done=?,total=? WHERE id=?',('indexing',n,total,ident));self.db.commit()
                self.emit({'type':'index','rootId':ident,'status':'indexing','done':n,'total':total})
        with self.lock:
            if not self.active(ident):return
            for row in list(self.db.execute('SELECT id,relative FROM files WHERE root=?',(ident,))):
                if row['relative'] not in seen:self.db.execute('DELETE FROM files WHERE id=?',(row['id'],))
            self.db.execute('UPDATE roots SET status=?,done=?,total=? WHERE id=?',('complete',total,total,ident));self.db.commit()
        self.emit({'type':'index','rootId':ident,'status':'complete','done':total,'total':total})
    def loop(self):
        with self.lock:
            roots=list(self.db.execute('SELECT id,path FROM roots'))
            self.dirty.update(x['id'] for x in roots if x['id'] not in self.cancelled)
        for r in roots:self.watch(r['id'],r['path'])
        last=time.monotonic()
        while not self.stopping.wait(1):
            if time.monotonic()-last>60:
                with self.lock:self.dirty.update(x['id'] for x in self.db.execute('SELECT id FROM roots') if x['id'] not in self.cancelled)
                last=time.monotonic()
            with self.lock:items=list(self.dirty);self.dirty.clear()
            for ident in items:
                try:self.reconcile(ident)
                except (OSError,sqlite3.Error):self.emit({'type':'index','rootId':ident,'status':'failed','done':0,'total':0})
    def resolve(self,ident):
        with self.lock:r=self.db.execute('SELECT files.*,roots.path AS base FROM files JOIN roots ON files.root=roots.id WHERE files.id=?',(ident,)).fetchone()
        if not r:raise AgentError('fileMissing',404)
        p=Path(r['base'])/r['relative']
        if self.private_path(p) or not contained(p,r['base']) or not p.is_file():raise AgentError('fileMissing',404)
        return p
    def search(self,query,limit=50,filters=None):
        if not isinstance(query,str) or len(query)>1000:raise AgentError('invalidRequest')
        limit=max(1,min(int(limit),100))
        effective_query=re.sub(r'지난달|last\s+month|tháng\s+trước|先月|上个月','',query,flags=re.IGNORECASE)
        terms=[x.casefold() for x in re.findall(r'[\w\-]+',effective_query) if len(x)>1][:24]
        # Local synonyms improve candidate recall; semantic ranking remains the central ADMIN router.
        synonyms={'엑셀':['xlsx','xls','excel'],'excel':['xlsx','xls'],'문서':['pdf','docx'],'불량':['defect','qc'],'검사':['inspection','qc'],'일본어':['japanese','日本語'],'와이파이':['wifi','wi-fi'],'품질':['quality','qc']}
        terms=list(dict.fromkeys(terms+[s for t in terms for s in synonyms.get(t,[])]))
        now=datetime.now().astimezone();date_start=date_end=None
        if any(x in query.casefold() for x in ('지난달','last month','tháng trước','先月','上个月')):
            date_end=now.replace(day=1,hour=0,minute=0,second=0,microsecond=0);date_start=(date_end-timedelta(days=1)).replace(day=1)
        if filters is None:filters={}
        if not isinstance(filters,dict) or set(filters)-{'extensions','dateFrom','dateTo','path'}:raise AgentError('invalidRequest')
        extensions=filters.get('extensions',[])
        if not isinstance(extensions,list) or len(extensions)>20 or any(not isinstance(x,str) or not re.fullmatch(r'\.?[A-Za-z0-9]{1,16}',x) for x in extensions):raise AgentError('invalidRequest')
        path_filter=filters.get('path','')
        if not isinstance(path_filter,str) or len(path_filter)>1000 or '\0' in path_filter:raise AgentError('invalidRequest')
        constraints=[];constraint_args=[]
        if extensions:
            extensions=list(dict.fromkeys('.'+x.lstrip('.').lower() for x in extensions));constraints.append('files.extension IN ('+','.join('?' for _ in extensions)+')');constraint_args.extend(extensions)
        parsed_dates={}
        for key in ('dateFrom','dateTo'):
            value=filters.get(key,'')
            if not isinstance(value,str):raise AgentError('invalidRequest')
            if value:
                try:
                    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError()
                    parsed_dates[key]=datetime.strptime(value,'%Y-%m-%d')
                except ValueError:raise AgentError('invalidRequest')
        if len(parsed_dates)==2 and parsed_dates['dateFrom']>parsed_dates['dateTo']:raise AgentError('invalidRequest')
        if 'dateFrom' in parsed_dates:constraints.append('files.modified>=?');constraint_args.append(parsed_dates['dateFrom'].timestamp())
        if 'dateTo' in parsed_dates:constraints.append('files.modified<?');constraint_args.append((parsed_dates['dateTo']+timedelta(days=1)).timestamp())
        if path_filter:
            escaped=path_filter.replace('\\','/').replace('%','\\%').replace('_','\\_')
            constraints.append("lower(replace(roots.path || '/' || files.relative, '\\', '/')) LIKE ? ESCAPE '\\'");constraint_args.append('%'+escaped.casefold()+'%')
        clauses=[];args=[]
        for term in terms:
            clauses.append('(lower(files.name) LIKE ? ESCAPE \'\\\' OR lower(files.relative) LIKE ? ESCAPE \'\\\' OR lower(files.text) LIKE ? ESCAPE \'\\\')')
            escaped=term.replace('\\','\\\\').replace('%','\\%').replace('_','\\_');args.extend(['%'+escaped+'%']*3)
        if date_start and not parsed_dates:
            constraints.append('(modified>=? AND modified<?)');constraint_args.extend([date_start.timestamp(),date_end.timestamp()])
        sql='SELECT files.*,roots.name AS rootname,roots.path AS rootpath FROM files JOIN roots ON files.root=roots.id'
        where=(['('+' OR '.join(clauses)+')'] if clauses else [])+constraints
        if where:sql+=' WHERE '+' AND '.join(where);args.extend(constraint_args)
        sql+=' ORDER BY modified DESC LIMIT 3000'
        with self.lock:rows=list(self.db.execute(sql,args))
        scored=[]
        for r in rows:
            if self.private_path(Path(r['rootpath'])/r['relative']) or not contained(Path(r['rootpath'])/r['relative'],r['rootpath']):continue
            name=r['name'].casefold();fold=r['relative'].casefold();text=r['text'].casefold();score=0
            for term in terms:
                score+=12*(term in name)+5*(term in fold)+2*(term in text)
            if date_start and date_start.timestamp()<=r['modified']<date_end.timestamp():score+=8
            if not terms:score=1
            if score>0:
                # Only bounded snippets, no absolute path returned to browser or AI by default.
                hit=next((text.find(t) for t in terms if t in text),0);start=max(0,hit-80)
                scored.append((score,r, r['text'][start:start+280]))
        scored.sort(key=lambda x:(x[0],x[1]['modified']),reverse=True)
        return [dict(id=r['id'],name=r['name'],folder=str(Path(r['rootname'])/Path(r['relative']).parent),extension=r['extension'],size=r['size'],modified=datetime.fromtimestamp(r['modified'],timezone.utc).isoformat(),snippet=snippet,score=score) for score,r,snippet in scored[:limit]]
    def details(self,ident):
        p=self.resolve(ident);s=p.stat()
        return {'id':ident,'path':str(p),'modified':datetime.fromtimestamp(s.st_mtime,timezone.utc).isoformat(),'size':s.st_size}
    def preview(self,ident):
        p=self.resolve(ident);s=p.stat();extension=p.suffix.lower()
        kind={'.pdf':'pdf','.docx':'document','.xlsx':'spreadsheet','.pptx':'presentation'}.get(extension,'image' if extension in {'.png','.jpg','.jpeg','.webp','.gif','.bmp','.tif','.tiff','.heic'} else 'text' if extension in {'.txt','.md','.csv','.json','.html','.log','.xml','.yaml','.yml'} else 'binary')
        text=extract_text(p)
        result={'id':ident,'name':p.name,'path':str(p),'size':s.st_size,'modified':datetime.fromtimestamp(s.st_mtime,timezone.utc).isoformat(),'extension':extension,'kind':kind,'text':text[:20_000],'truncated':len(text)>20_000}
        if extension=='.pdf':
            data=read_local_file(p)
            if data is not None:
                try:
                    import pymupdf
                    with pymupdf.open(stream=data,filetype='pdf') as doc:result['pages']=doc.page_count
                except (ValueError,RuntimeError):pass
        return result
    def close(self):
        self.stopping.set()
        for w in self.watchers.values():w.stop()
        if self.thread is not None:self.thread.join(timeout=5)
        for w in self.watchers.values():w.join(timeout=2)
        with self.lock:self.db.close()
