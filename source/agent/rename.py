"""Preview-led local rename with collision/staleness checks and rollback."""
import os,re,uuid,time,threading
from pathlib import Path
from datetime import datetime
from common import AgentError
from engine import publish_exclusive
class Renamer:
 def __init__(self,resolve):self.resolve=resolve;self.previews={};self.lock=threading.Lock()
 def preview(self,ids,options,owner):
  if not isinstance(ids,list) or not 1<=len(ids)<=1000 or len(set(ids))!=len(ids):raise AgentError('invalidRequest')
  if not isinstance(options,dict):raise AgentError('invalidRequest')
  start=int(options.get('start',1));digits=int(options.get('digits',3))
  if not 0<=start<=999999999 or not 1<=digits<=12:raise AgentError('invalidRequest')
  items=[];targets=set();conflicts=[]
  for n,ident in enumerate(ids):
   p=self.resolve(ident,owner);st=p.stat();common=str(options.get('name',''))[:120]
   stem=common or p.stem
   find=str(options.get('replaceFrom',''))
   if find:stem=stem.replace(find,str(options.get('replaceTo','')))
   if options.get('keepOriginal'):stem=p.stem
   stem=str(options.get('prefix',''))+stem+str(options.get('suffix',''))
   if options.get('date'):stem+='_'+datetime.fromtimestamp(st.st_mtime).strftime('%Y%m%d')
   if options.get('number',True):stem+='_'+str(start+n).zfill(digits)
   if not stem.strip() or any(x in stem for x in '<>:"/\\|?*\0') or stem.endswith((' ','.')):raise AgentError('invalidName')
   name=stem+p.suffix
   if len(name)>240:raise AgentError('invalidName')
   q=p.with_name(name);key=os.path.normcase(str(q))
   if key in targets or (q.exists() and q!=p):conflicts.append({'id':ident,'name':name})
   targets.add(key);items.append({'id':ident,'before':p.name,'after':name,'path':str(p),'target':str(q),'stamp':[st.st_size,st.st_mtime_ns,st.st_ino]})
  preview=str(uuid.uuid4());self.previews[preview]={'owner':owner,'expires':time.time()+300,'items':items,'conflicts':conflicts}
  return {'previewId':preview,'items':[{k:v for k,v in x.items() if k in ('id','before','after')} for x in items],'conflicts':conflicts}
 def commit(self,ident,owner):
  with self.lock:
   v=self.previews.pop(ident,None)
   if not v or v['owner']!=owner or v['expires']<time.time():raise AgentError('previewExpired',409)
   if v['conflicts']:raise AgentError('conflict',409)
   for x in v['items']:
    p=self.resolve(x['id'],owner);st=p.stat();q=Path(x['target'])
    if str(p)!=x['path'] or [st.st_size,st.st_mtime_ns,st.st_ino]!=x['stamp'] or (q.exists() and q!=p):raise AgentError('conflict',409)
   changed=[]
   try:
    for x in v['items']:
     p=Path(x['path']);q=Path(x['target'])
     if p!=q:
      # Create destination without overwrite. A concurrent filesystem change cannot be overwritten by rename.
      publish_exclusive(p,q);changed.append((p,q))
    return {'renamed':len(changed),'items':v['items']}
   except OSError:
    for p,q in reversed(changed):
     try:
      if not p.exists():publish_exclusive(q,p)
     except OSError:pass
    raise AgentError('renameFailed',409)
