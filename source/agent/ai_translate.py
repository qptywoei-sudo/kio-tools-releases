"""Memory-only screen sessions using the official plan-sharing Responses endpoint."""
from __future__ import annotations
import base64,io,json,re,threading,time,uuid,os,math,sys
from pathlib import Path
from common import AgentError,atomic_json,read_json
from chatgpt_account import ChatGPTAccount,RESOURCE,failure
from ai_catalog import effort_id
from ai_prompts import TRANSLATE,REPLY,RETRANSLATE
from ai_image_translate import SCHEMA as IMAGE_SCHEMA, PROMPT as IMAGE_PROMPT, validate as validate_image, render as render_image
from ai_smart_scan import SCHEMAS,COMMON,PROMPTS,validate as validate_smart,validate_reply_language
POLICY=read_json(Path(__file__).with_name('ai-model-policy.json'),{'model':'gpt-6-luna','reasoning':'low'})
IMAGE_POLICY=POLICY.get('imageTranslation',{'model':'gpt-6.1-sol','reasoning':'medium'})

def string_schema(nullable=False):return {'type':['string','null'] if nullable else 'string'}
MESSAGE={'type':'object','additionalProperties':False,'properties':{'speaker':string_schema(),'speakerTranslated':string_schema(),'isMine':{'type':['boolean','null']},'originalText':string_schema(),'translatedText':string_schema(),'language':string_schema(True),'confidence':{'type':'number'},'isTruncated':{'type':'boolean'}}}
MESSAGE['required']=list(MESSAGE['properties'])
TRANSLATION={'type':'object','additionalProperties':False,'properties':{'contentType':{'type':'string','enum':['document','conversation','mixed']},'originalLanguage':string_schema(True),'detectedReplyLanguage':string_schema(True),'replyTarget':{'type':['integer','null']},'messages':{'type':'array','items':MESSAGE}}}
TRANSLATION['required']=list(TRANSLATION['properties'])
REPLY_SCHEMA={'type':'object','additionalProperties':False,'properties':{'replyText':string_schema(),'translatedText':string_schema() },'required':['replyText','translatedText']}

def validate_result(value,reply=False):
    schema=REPLY_SCHEMA if reply else TRANSLATION
    if not isinstance(value,dict) or set(value)!=set(schema['required']):raise AgentError('aiInvalidResponse')
    if reply:
        if any(not isinstance(value[k],str) or len(value[k])>30000 for k in schema['required']):raise AgentError('aiInvalidResponse')
        return value
    if value['contentType'] not in ('document','conversation','mixed') or not isinstance(value['messages'],list) or len(value['messages'])>300:raise AgentError('aiInvalidResponse')
    for k in ('originalLanguage','detectedReplyLanguage'):
        if value[k] is not None and (not isinstance(value[k],str) or len(value[k])>80):raise AgentError('aiInvalidResponse')
    for row in value['messages']:
        if isinstance(row,dict):row.setdefault('speakerTranslated','')
        if not isinstance(row,dict) or set(row)!=set(MESSAGE['required']):raise AgentError('aiInvalidResponse')
        if any(not isinstance(row[k],str) or len(row[k])>30000 for k in ('speaker','speakerTranslated','originalText','translatedText')):raise AgentError('aiInvalidResponse')
        if row['isMine'] is not None and type(row['isMine']) is not bool:raise AgentError('aiInvalidResponse')
        if type(row['isTruncated']) is not bool or type(row['confidence']) not in (float,int) or not 0<=row['confidence']<=1:raise AgentError('aiInvalidResponse')
        if row['language'] is not None and (not isinstance(row['language'],str) or len(row['language'])>80):raise AgentError('aiInvalidResponse')
    # Older or imperfect model output can repeat a speaker as a standalone row.
    # Merge only an exact name-only row immediately preceding that same speaker;
    # retain every actual sentence and remap the reply index.
    rows=value['messages'];old_target=value['replyTarget'];mapping={};merged=[]
    for index,row in enumerate(rows):
        name=row['speaker'].strip()
        if name and not row['isTruncated'] and row['originalText'].strip()==name and index+1<len(rows) and rows[index+1]['speaker'].strip()==name and rows[index+1]['originalText'].strip()!=name:
            following=rows[index+1]
            if not following['speakerTranslated']:following['speakerTranslated']=row['speakerTranslated'] or row['translatedText']
            mapping[index]=len(merged);continue
        mapping[index]=len(merged);merged.append(row)
    if old_target is not None and (type(old_target) is not int or old_target not in mapping):raise AgentError('aiInvalidResponse')
    value['messages']=merged;value['replyTarget']=mapping[old_target] if old_target is not None else None
    target=value['replyTarget']
    if target is not None and (type(target) is not int or target<0 or target>=len(value['messages'])):raise AgentError('aiInvalidResponse')
    if target is not None:
        row=value['messages'][target]
        if row['isMine'] is True or not row['language'] or row['confidence']<.6:target=None
    value['replyTarget']=target
    value['detectedReplyLanguage']=value['messages'][target]['language'] if target is not None else None
    return value

class AITranslate:
    def __init__(self,state,bridge):
        self.account=ChatGPTAccount(state);self.bridge=bridge;self.lock=threading.RLock();self.jobs={};self.sessions={};self.scans={};self.images={};self.active=None
        self.performance_path=self.account.state/'performance.json';self.performance=[]
        self.path=self.account.state/'settings.json';self.settings={'language':'ko','customLanguage':'','model':'auto','reasoning':'recommended','consent':False,**read_json(self.path,{})}
    def status(self):
        with self.lock:self.prune()
        return {**self.account.status(),'settings':self.settings.copy(),'recommendation':POLICY.copy(),'imageRecommendation':IMAGE_POLICY.copy()}
    def configure(self,body):
        if set(body)-{'language','customLanguage','model','reasoning','consent'}:raise AgentError('invalidRequest')
        if 'reasoning' in body:
            effort=body['reasoning']
            if effort not in ('recommended','model-default'):
                if not effort_id(effort):raise AgentError('invalidRequest')
                choice=body.get('model',self.settings['model'])
                ident=POLICY['model'] if choice=='auto' else choice
                model=next((m for m in self.account.models if m['id']==ident),None)
                if self.account.models:
                    if model is None or effort not in model.get('reasoningLevels',[]) or effort in model.get('reasoningUnavailable',{}):raise AgentError('aiReasoningUnavailable')
                elif effort not in ('none','minimal','low','medium','high','xhigh','max','ultra'):raise AgentError('invalidRequest')
        for key in ('language','customLanguage','model'):
            if key in body and (not isinstance(body[key],str) or len(body[key])>120):raise AgentError('invalidRequest')
        if 'language' in body and body['language'] not in ('vi','en','ko','ja','zh-TW','zh-CN','zh','other'):raise AgentError('invalidRequest')
        if 'consent' in body and type(body['consent']) is not bool:raise AgentError('invalidRequest')
        with self.lock:self.settings={**self.settings,**body};atomic_json(self.path,self.settings)
        return self.status()
    def _cancel(self,job):
        job['cancel'].set();job['status']='cancelled';job['result']=None
        response=job.get('response')
        if response:threading.Thread(target=response.close,daemon=True).start()
    def clear(self):
        with self.lock:
            for job in self.jobs.values():self._cancel(job)
            self.jobs.clear();self.sessions.clear();self.scans.clear();self.images.clear()
    def cancel(self,ident):
        with self.lock:
            job=self.jobs.get(ident)
            if job:self._cancel(job)
        return {'cancelled':True}
    def public_job(self,job):return {key:job[key] for key in ('id','status','stage','error','result','received')}
    def accept_frame(self,ident,png):
        with self.lock:
            job=self.jobs.get(ident)
            if not job or job['kind'] not in ('capture','scan') or job['status']!='running' or job['stage']!='capture' or job.get('png'):raise AgentError('aiSessionExpired',409)
            self.check(job);job['png']=png;job['stage']='uploading'
    def scan(self,ident):
        with self.lock:
            if not isinstance(ident,str):raise AgentError('invalidRequest')
            self.prune();scan=self.scans.get(ident)
            if not scan:raise AgentError('aiSessionExpired',404)
            return scan
    def image(self,ident):
        with self.lock:
            self.prune();image=self.images.get(ident)
            if not image or image['generation']!=self.account.generation:raise AgentError('aiSessionExpired',404)
            return image['png']
    def record_performance(self,job):
        t=job.get('timings',{});pairs={'capturePrepareMs':('startedAt','overlayShownAt'),'selectionToRequestMs':('selectedAt','requestStartedAt'),'firstResponseMs':('requestStartedAt','firstResponseAt'),'gptTotalMs':('requestStartedAt','completedAt'),'popupCompleteMs':('selectedAt','popupCompletedAt'),'replyCompleteMs':('startedAt','popupCompletedAt'),'popupShowMs':('selectedAt','popupShownAt')}
        row={'id':job['id'],'kind':job.get('kind','benchmark'),'model':job.get('model',''),'reasoning':job.get('reasoning',''),'status':job.get('status',''),'timestamp':round(time.time()),**{k:round(t[b]-t[a],2) for k,(a,b) in pairs.items() if a in t and b in t and 0<=t[b]-t[a]<600000}}
        if row['kind'] not in ('reply','retranslate'):row.pop('replyCompleteMs',None)
        if job.get('task'):row['task']=job['task']
        if job.get('cacheHit'):row['cacheHit']=True
        if row['kind']=='analyze' and 'popupCompletedAt' in t:row['featureTotalMs']=round(max(0,t['popupCompletedAt']-t['startedAt']),2)
        self.performance=[r for r in self.performance if r['id']!=row['id']][-99:]+[row]
        atomic_json(self.performance_path,self.performance)
    def metrics(self,body):
        if set(body)-{'id','popupShownAt','popupCompletedAt'}:raise AgentError('invalidRequest')
        with self.lock:
            job=self.jobs.get(body.get('id'))
            if not job:return {'recorded':False}
            for name in ('popupShownAt','popupCompletedAt'):
                value=body.get(name)
                if value is not None:
                    if type(value) not in (int,float) or not math.isfinite(value) or abs(value-time.time()*1000)>600000:raise AgentError('invalidRequest')
                    job.setdefault('timings',{})[name]=value
            try:self.record_performance(job)
            except OSError:return {'recorded':False}
        return {'recorded':True}
    def job(self,ident):
        with self.lock:
            self.prune();job=self.jobs.get(ident)
            if not job:raise AgentError('aiSessionExpired',404)
            return self.public_job(job)
    def prune(self):
        cutoff=time.monotonic()-900
        self.sessions={k:v for k,v in self.sessions.items() if v['created']>cutoff and v['generation']==self.account.generation}
        self.scans={k:v for k,v in self.scans.items() if v['created']>cutoff and v['generation']==self.account.generation}
        self.jobs={k:v for k,v in self.jobs.items() if v['created']>cutoff}
        self.images={k:v for k,v in self.images.items() if v['created']>cutoff and v['generation']==self.account.generation}
    def submit(self,kind,body):
        if kind not in ('capture','scan','analyze','reply','retranslate'):raise AgentError('invalidRequest')
        if kind in ('capture','scan') and os.name!='nt' and sys.platform!='darwin':raise AgentError('nativeUnavailable')
        local=kind=='scan'
        if not local and not self.settings.get('consent'):raise AgentError('aiConsentRequired')
        if not local and self.settings['language']=='other' and not self.settings.get('customLanguage','').strip():raise AgentError('aiLanguageRequired')
        if not local:self.account.access()
        body=dict(body);started=body.pop('startedAt',time.time()*1000)
        if type(started) not in (float,int) or not math.isfinite(started) or abs(started-time.time()*1000)>600000:raise AgentError('invalidRequest')
        with self.lock:
            self.prune()
            if self.active:raise AgentError('busy')
            ident=str(uuid.uuid4());job={'id':ident,'kind':kind,'status':'running','stage':'capture' if kind in ('capture','scan') else 'connecting','error':'','result':None,'received':0,'created':time.monotonic(),'cancel':threading.Event(),'generation':self.account.generation,'settings':self.settings.copy(),'timings':{'startedAt':started}}
            self.jobs={k:v for k,v in list(self.jobs.items())[-7:]};self.jobs[ident]=job;self.active=ident
            threading.Thread(target=self._work,args=(job,dict(body)),daemon=True).start()
            return self.public_job(job)
    def check(self,job):
        if job['cancel'].is_set():raise AgentError('cancelled')
        if self.account.generation!=job['generation']:raise AgentError('aiAccountChanged')
    def infer(self,job,instructions,content,schema,image=False):
        self.check(job)
        if not self.account.models:self.account.list_models()
        models=[m for m in self.account.models if not image or m['vision'] is not False]
        if not models:raise AgentError('aiModelUnavailable')
        image_translation=schema is IMAGE_SCHEMA
        policy=IMAGE_POLICY if image_translation else POLICY
        choice='auto' if image_translation else job['settings']['model']
        if choice=='auto':
            model=next((m for m in models if m['id']==policy['model']),None)
            if model is None:raise AgentError('aiImageModelUnavailable' if image_translation else 'aiRecommendedUnavailable')
        else:
            model=next((m for m in models if m['id']==choice),None)
            if model is None:raise AgentError('aiModelUnavailable')
        token,generation=self.account.access();self.check(job)
        payload={'model':model['id'],'instructions':instructions,'input':[{'role':'user','content':content}],'store':False,'stream':True,'text':{'format':{'type':'json_schema','name':'kio_translation','strict':True,'schema':schema}}}
        effort='recommended' if image_translation else job['settings'].get('reasoning','recommended')
        if effort=='recommended':effort=policy['reasoning'] if model['id']==policy['model'] else model.get('defaultReasoning')
        if effort=='model-default':effort=model.get('defaultReasoning')
        if effort:
            if effort in model.get('reasoningUnavailable',{}):raise AgentError('aiReasoningUnavailable')
            if model.get('reasoningLevels') and effort not in model['reasoningLevels'] and not job.get('_benchmarkReasoningProbe'):raise AgentError('aiReasoningUnavailable')
            payload['reasoning']={'effort':effort}
        job['model']=model['id'];job['reasoning']=effort or 'default';job.setdefault('timings',{})['requestStartedAt']=time.time()*1000
        started=time.monotonic();completed=None;text='';event=[];job['stage']='translating' if image else 'reply'
        with self.account.raw(RESOURCE+'/responses','POST',json.dumps(payload).encode(),{'Authorization':'Bearer '+token,'Content-Type':'application/json','Accept':'text/event-stream'},timeout=45) as response:
            job['response']=response
            while True:
                self.check(job)
                line=response.readline(1024*1024+1)
                if not line:break
                job['timings'].setdefault('firstResponseAt',time.time()*1000)
                if len(line)>1024*1024 or time.monotonic()-started>180:raise AgentError('aiInvalidResponse')
                line=line.decode('utf-8').rstrip('\r\n')
                if line.startswith('data:'):event.append(line[5:].lstrip())
                elif line=='':
                    data='\n'.join(event);event=[]
                    if not data or data=='[DONE]':continue
                    try:entry=json.loads(data)
                    except ValueError:raise AgentError('aiInvalidResponse') from None
                    kind=entry.get('type')
                    if kind=='response.output_text.delta':text+=entry.get('delta','');job['received']=len(text)
                    elif kind in ('response.failed','error'):
                        err=entry.get('response',{}).get('error') or entry.get('error') or entry
                        raise AgentError(failure(err.get('code','')))
                    elif kind=='response.incomplete':raise AgentError('aiIncomplete')
                    elif kind=='response.completed':
                        completed=entry.get('response',{})
                        if completed.get('status')!='completed':raise AgentError('aiIncomplete')
                        break
                    if len(text)>1024*1024:raise AgentError('aiInvalidResponse')
        job.pop('response',None);self.check(job)
        if completed is None:raise AgentError('aiIncomplete')
        final=''.join(c.get('text','') for o in completed.get('output',[]) if o.get('type')=='message' for c in o.get('content',[]) if c.get('type')=='output_text')
        try:value=json.loads(final or text)
        except ValueError:raise AgentError('aiInvalidResponse') from None
        value=validate_image(value) if schema is IMAGE_SCHEMA else validate_result(value,schema is REPLY_SCHEMA) if schema in (TRANSLATION,REPLY_SCHEMA) else validate_smart(value,schema)
        job['timings']['completedAt']=time.time()*1000
        if image:
            with self.account.lock:
                self.check(job);model.update(verified=True,vision=True,latencyMs=round((time.monotonic()-started)*1000))
        return value,model['id']
    def image_content(self,png):
        from PIL import Image
        if not isinstance(png,bytes) or len(png)>16*1024*1024 or not png.startswith(b'\x89PNG\r\n\x1a\n'):raise AgentError('aiInvalidImage')
        try:
            with Image.open(io.BytesIO(png)) as image:
                if image.width*image.height>64000000:raise ValueError()
                image.verify()
        except Exception:raise AgentError('aiInvalidImage') from None
        # Only large captures get a lossless rewrite; never shrink text or change pixels.
        if len(png)>2*1024*1024:
            started=time.monotonic()
            with Image.open(io.BytesIO(png)) as source:
                if source.mode=='RGBA' and source.getchannel('A').getextrema()==(255,255):source=source.convert('RGB')
                compact=io.BytesIO();source.save(compact,'PNG',compress_level=3)
                if compact.tell()<len(png):png=compact.getvalue()
        return {'type':'input_image','image_url':'data:image/png;base64,'+base64.b64encode(png).decode(),'detail':'high'}
    def translate_png(self,job,png,instruction='',previous=None,image_content=None):
        settings=job['settings'];language=settings['customLanguage'] if settings['language']=='other' else settings['language']
        context={'baseLanguage':language,'followUp':instruction,'previousResult':previous}
        value,model=self.infer(job,TRANSLATE,[{'type':'input_text','text':json.dumps(context,ensure_ascii=False)},image_content or self.image_content(png)],TRANSLATION,True)
        return {**value,'sessionId':job['id'],'baseLanguage':language,'model':model}
    def analyze(self,job,body):
        if set(body)-{'scanId','task','instruction','force'}:raise AgentError('invalidRequest')
        task=body.get('task');instruction=body.get('instruction','');force=body.get('force',False)
        if task not in (*PROMPTS,'translate-image') or not isinstance(instruction,str) or len(instruction)>5000 or type(force) is not bool:raise AgentError('invalidRequest')
        scan=self.scan(body.get('scanId'));self.check(job);job['task']=task
        settings_key=json.dumps({k:job['settings'].get(k) for k in ('language','customLanguage','model','reasoning')},sort_keys=True)
        if scan.get('settingsKey')!=settings_key:scan['results'].clear();scan['settingsKey']=settings_key
        previous=scan['results'].get(task)
        if previous and not instruction and not force and (task!='translate-image' or previous.get('imageId') in self.images):job['cacheHit']=True;return previous
        if 'imageContent' not in scan:scan['imageContent']=self.image_content(scan['png'])
        if task=='translate-image':
            s=job['settings'];language=s['customLanguage'] if s['language']=='other' else s['language']
            from PIL import Image
            with Image.open(io.BytesIO(scan['png'])) as image:width,height=image.size
            context={'baseLanguage':language,'instruction':instruction,'imageSize':{'width':width,'height':height}}
            value,model=self.infer(job,IMAGE_PROMPT,[{'type':'input_text','text':json.dumps(context,ensure_ascii=False)},scan['imageContent']],IMAGE_SCHEMA,True)
            job['stage']='rendering'
            png=render_image(scan['png'],value,lambda:self.check(job))
            with self.lock:
                self.check(job);self.images={k:v for k,v in list(self.images.items())[-3:]}
                self.images[job['id']]={'png':png,'created':time.monotonic(),'generation':job['generation']}
            value={**value,'task':task,'imageId':job['id'],'model':model,'baseLanguage':language}
        elif task=='translate':
            value=self.translate_png(job,scan['png'],instruction,previous,scan['imageContent'])
            with self.lock:self.check(job);self.sessions[job['id']]={'data':value,'created':time.monotonic(),'generation':job['generation']}
        else:
            s=job['settings'];language=s['customLanguage'] if s['language']=='other' else s['language']
            context={'baseLanguage':language,'instruction':instruction,'previousResult':previous}
            translated=scan['results'].get('translate') if task=='write' else None
            if translated:context['scanContext']=translated
            content=[{'type':'input_text','text':json.dumps(context,ensure_ascii=False)}]
            if not translated:content.append(scan['imageContent'])
            value,model=self.infer(job,COMMON+PROMPTS[task],content,SCHEMAS[task],not bool(translated))
            if task=='write' and (value['needsTarget'] or not value['language']):value.update(text='',meaning='',needsTarget=True)
            if task=='write':validate_reply_language(value)
            value.update(task=task,model=model,baseLanguage=language)
        with self.lock:self.check(job);scan['results'][task]=value
        return value
    def _work(self,job,body):
        try:
            if job['kind'] in ('capture','scan'):
                if body:raise AgentError('invalidRequest')
                result=self.bridge.call('capture.start',{'mode':'area','monitor':0,'format':'png','ephemeral':True,'aiJobId':job['id']},180,cancel=lambda:job['cancel'].is_set())
                self.check(job);job['stage']='uploading'
                for name in ('overlayShownAt','selectedAt'):
                    if type(result.get(name)) in (float,int):job['timings'][name]=result[name]
                png=job.pop('png',b'')
                if job['kind']=='scan':
                    from PIL import Image
                    with Image.open(io.BytesIO(png)) as image:
                        width,height=image.size
                        if width*height>64000000:raise AgentError('aiInvalidImage')
                        image.verify()
                    value={'scanId':job['id'],'width':width,'height':height}
                    with self.lock:
                        self.check(job);self.scans.clear();self.sessions.clear();self.images.clear();self.scans[job['id']]={'png':png,'created':time.monotonic(),'generation':job['generation'],'results':{}}
                else:
                    value=self.translate_png(job,png)
                    with self.lock:
                        self.check(job);self.sessions[job['id']]={'data':value,'created':time.monotonic(),'generation':job['generation']}
                png=b''
            elif job['kind']=='analyze':value=self.analyze(job,body)
            else:
                if set(body)-{'sessionId','target','intent','replyText'}:raise AgentError('invalidRequest')
                session=self.sessions.get(body.get('sessionId'))
                if not session or session['generation']!=job['generation']:raise AgentError('aiSessionExpired')
                data=session['data'];target=body.get('target',data['replyTarget'])
                if type(target) is not int or not 0<=target<len(data['messages']):raise AgentError('aiReplyTargetRequired')
                row=data['messages'][target]
                if row['isMine'] is True or not row['language'] or row['confidence']<.6:raise AgentError('aiReplyTargetRequired')
                intent=body.get('intent','');edited=body.get('replyText','')
                if not isinstance(intent,str) or len(intent)>5000 or not isinstance(edited,str) or len(edited)>30000:raise AgentError('invalidRequest')
                if job['kind']=='retranslate' and not edited.strip():raise AgentError('invalidRequest')
                task={'baseLanguage':data['baseLanguage'],'replyLanguage':row['language'],'target':target,'messages':data['messages'],'intent':intent}
                if job['kind']=='retranslate':task={'baseLanguage':data['baseLanguage'],'editedReply':edited}
                value,model=self.infer(job,RETRANSLATE if job['kind']=='retranslate' else REPLY,[{'type':'input_text','text':json.dumps(task,ensure_ascii=False)}],REPLY_SCHEMA)
                if job['kind']=='retranslate' and value['replyText']!=edited:raise AgentError('aiInvalidResponse')
                value.update(sessionId=data['sessionId'],replyLanguage=row['language'],baseLanguage=data['baseLanguage'],model=model)
            with self.lock:self.check(job);job.update(status='complete',stage='complete',result=value)
        except AgentError as exc:
            job.update(status='cancelled' if job['cancel'].is_set() or exc.code=='cancelled' else 'failed',error=exc.code,result=None)
        except Exception:job.update(status='cancelled' if job['cancel'].is_set() else 'failed',error='aiRequestFailed',result=None)
        finally:
            job.pop('response',None);job.pop('png',None)
            with self.lock:
                if self.active==job['id']:self.active=None
                try:self.record_performance(job)
                except OSError:pass
