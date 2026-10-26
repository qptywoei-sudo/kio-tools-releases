"""Official SIWC public-client flow. No API keys, web cookies or proxy servers.

Reference: developers.openai.com/siwc/token-sharing-open-source/sign-in
Credentials are scoped to this OS user's agent profile and protected by Windows DPAPI or the macOS Keychain.
"""
from __future__ import annotations
import sys
from secure_tokens import MacKeychain
import base64,hashlib,hmac,json,os,secrets,threading,time,urllib.error,urllib.parse,urllib.request,uuid,webbrowser
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
from common import AgentError,atomic_json,private_dir,read_json
from ai_catalog import model_catalog
from language import LanguagePreference, callback_page
from google_drive import NoRedirect,protect

AUTH='https://auth.openai.com'
RESOURCE='https://api.openai.com/v1'
TOKEN=AUTH+'/api/accounts/oauth/token'
PLAN_SCOPE='chatgpt.tokens.use.direct'
SCOPES='openid profile email offline_access resource.invoke '+PLAN_SCOPE

def failure(code='',status=0):
    if code=='3p_delegated_access_policy_denied':return 'aiOrganizationPolicy'
    if code=='subscription_sharing_user_not_eligible':return 'aiUnsupportedAccount'
    if code in ('subscription_sharing_usage_limit_exceeded','subscription_sharing_usage_unavailable') or status==429:return 'aiQuota'
    if code in ('invalid_grant','invalid_token') or status==401:return 'aiReauthenticate'
    if code in ('access_denied','consent_required','insufficient_scope','chatpass_v2_scope_not_authorized','chatpass_v2_invalid_authorization_context'):return 'aiPermission'
    if status==403:return 'aiUnsupportedAccount'
    if code in ('unsupported_image','unsupported_image_input','model_not_found'):return 'aiModelUnavailable'
    return 'aiRequestFailed'

class ChatGPTAccount:
    def __init__(self,state):
        self.state=private_dir(Path(state)/'chatgpt');self.lock=threading.RLock();self.pending=None;self.error='';self.generation=0
        self.opener=urllib.request.build_opener(NoRedirect());self.discovery_cache=None;self.jwks_cache=None
        self.keychain=None
        self.kio=None;self.kio_user='';self.shared_status=None;self.shared_checked=0
        self.path=self.state/'accounts.dpapi';self.data={'accounts':{},'active':''};self.models=[]
        host=read_json(self.state/'host.json',{})
        try:uuid.UUID(host.get('id','').removeprefix('urn:uuid:'))
        except (ValueError,AttributeError):host={'id':'urn:uuid:'+str(uuid.uuid4())};atomic_json(self.state/'host.json',host)
        self.host=host['id']
        try:
            saved=None
            if sys.platform=='darwin':
                self.keychain=MacKeychain(self.state,service='com.kio.control.chatgpt')
                saved=self.keychain.load()
            elif self.path.exists():
                if self.path.is_symlink() or self.path.stat().st_size>1024*1024:raise ValueError()
                saved=protect(self.path.read_bytes(),True)
            if saved:
                value=json.loads(saved)
                if not isinstance(value,dict) or not isinstance(value.get('accounts'),dict):raise ValueError()
                self.data=value
        except Exception:self.error='aiReauthenticate'
    def persist(self):
        # No plaintext token fallback, including unsupported operating systems.
        encoded=json.dumps(self.data,ensure_ascii=False).encode()
        if sys.platform=='darwin':
            if self.keychain is None:self.keychain=MacKeychain(self.state,service='com.kio.control.chatgpt')
            try:self.keychain.save(encoded)
            except AgentError as exc:raise AgentError('aiSecureStorageUnavailable') from exc
            return
        encrypted=protect(encoded)
        temp=self.path.with_name('accounts-'+secrets.token_hex(12)+'.tmp')
        try:
            with temp.open('xb') as stream:stream.write(encrypted);stream.flush();os.fsync(stream.fileno())
            os.replace(temp,self.path)
        finally:temp.unlink(missing_ok=True)
    def current(self):return self.data['accounts'].get(self.data.get('active',''),{})
    def bind_kio(self,account,owner):
        if self.kio_user!=owner:
            self.generation+=1;self.shared_status=None;self.shared_checked=0;self.models=[]
        self.kio=account;self.kio_user=owner
    def cloud_link(self,operation,body=None,method='POST'):
        try:
            result=self.kio.cloud('/control/chatgpt/'+operation,body,method=method,expected_user=self.kio_user)
            if not isinstance(result,dict) or not isinstance(result.get('chatgpt'),dict):raise AgentError('aiNetwork')
            return result['chatgpt']
        except AgentError as error:
            if error.code.startswith('ai'):raise
            raise AgentError('aiNetwork') from None
    def publish_cloud(self,revision):
        record=dict(self.current())
        self.cloud_link('connect',{'grant':record,'revision':revision})
        # Cloud owns refresh rotation from now on. Retain only local registration hints.
        for key in ('access_token','refresh_token','id_token','expires_at','scopes'):self.current().pop(key,None)
        self.current()['shared']=True;self.persist();self.shared_checked=0
    def shared_state(self,force=False):
        if not self.kio:return None
        if not force and self.shared_status is not None and time.monotonic()-self.shared_checked<10:return self.shared_status
        value=self.cloud_link('status',method='GET')
        if value.get('revision')==-1 and self.current().get('refresh_token'):
            try:
                self._local_access();self.publish_cloud(-1);value=self.cloud_link('status',method='GET')
            except AgentError as error:
                # An unusable legacy grant must not block the OAuth action that
                # repairs it. Keep its issued registration and identity hints.
                if error.code not in ('aiPermission','aiReauthenticate'):raise
                self.error=error.code;self.models=[]
        old=self.shared_status
        if old and (old.get('connected'),old.get('accountId'))!=(value.get('connected'),value.get('accountId')):
            self.generation+=1;self.models=[]
        self.shared_status=value;self.shared_checked=time.monotonic()
        if not value.get('connected') and value.get('revision',-1)>=0:
            for key in ('access_token','refresh_token','id_token','expires_at','scopes'):self.current().pop(key,None)
        return value
    def status(self):
        if self.kio:
            try:
                value=self.shared_state();connected=value.get('connected') is True
                return {'connected':connected,'planApproved':connected and self.error!='aiPermission','connecting':self.pending is not None,'email':value.get('email',''),'activeAccount':value.get('accountId',''),'accounts':([{'id':value.get('accountId',''),'email':value.get('email',''),'label':value.get('email','ChatGPT'),'connected':True}] if connected else []),'error':self.error,'models':self.models,'usageUrl':'https://chatgpt.com/settings/usage','deployment':'local-personal','welcomeNeeded':False,'persistent':value.get('persistent',False),'connectionSource':'kio-account'}
            except AgentError as error:
                return {'connected':False,'planApproved':False,'connecting':self.pending is not None,'email':'','activeAccount':'','accounts':[],'error':error.code,'models':[],'usageUrl':'https://chatgpt.com/settings/usage','deployment':'local-personal','welcomeNeeded':False}
        with self.lock:
            account=self.current();logged=bool(account.get('access_token'));granted=PLAN_SCOPE in account.get('scopes',[])
            return {'connected':logged,'planApproved':logged and granted,'connecting':self.pending is not None,'email':account.get('email',''),'activeAccount':self.data.get('active',''),'accounts':[{'id':key,'email':row.get('email',''),'label':row.get('email','ChatGPT')+' · '+key[-6:],'connected':bool(row.get('access_token'))} for key,row in self.data['accounts'].items()], 'error':self.error,'models':self.models,'usageUrl':'https://chatgpt.com/settings/usage','deployment':'local-personal','welcomeNeeded':logged and granted and not account.get('welcomeSeen',False)}
    def raw(self,url,method='GET',data=None,headers=None,timeout=25):
        u=urllib.parse.urlparse(url)
        if u.scheme!='https' or u.hostname not in ('auth.openai.com','api.openai.com') or u.port not in (None,443) or u.username or u.password or u.fragment:raise AgentError('aiInvalidEndpoint')
        try:return self.opener.open(urllib.request.Request(url,data,headers or {},method=method),timeout=timeout)
        except urllib.error.HTTPError as exc:
            error={}
            try:
                body=json.loads(exc.read(65536));error=body.get('error',{});code=error.get('code','') if isinstance(error,dict) else error
            except Exception:code=''
            if isinstance(error,dict) and 'reasoning' in str(error.get('param','')):raise AgentError('aiReasoningUnavailable') from None
            raise AgentError(failure(code,exc.code)) from None
        except (OSError,TimeoutError,urllib.error.URLError):raise AgentError('aiNetwork') from None
    def json(self,url,method='GET',data=None,headers=None):
        with self.raw(url,method,data,headers) as response:
            value=response.read(4*1024*1024+1)
        if len(value)>4*1024*1024:raise AgentError('aiInvalidResponse')
        try:return json.loads(value) if value else {}
        except (ValueError,UnicodeError):raise AgentError('aiInvalidResponse') from None
    def discovery(self):
        if not self.discovery_cache:
            value=self.json(AUTH+'/.well-known/openid-configuration')
            if value.get('issuer')!=AUTH:raise AgentError('aiInvalidIdentity')
            self.discovery_cache=value
        return self.discovery_cache
    def validate(self,id_token,client_id,nonce=None,subject=None):
        import jwt
        try:
            header=jwt.get_unverified_header(id_token)
            if header.get('alg') not in ('RS256','ES256') or not isinstance(header.get('kid'),str):raise ValueError()
            def key():
                return next((k for k in (self.jwks_cache or {}).get('keys',[]) if k.get('kid')==header['kid'] and k.get('use','sig')=='sig'),None)
            item=key()
            if item is None:self.jwks_cache=self.json(self.discovery()['jwks_uri']);item=key()
            if item is None:raise ValueError()
            public=jwt.PyJWK.from_dict(item,algorithm=header['alg']).key
            claims=jwt.decode(id_token,public,algorithms=[header['alg']],audience=client_id,issuer=AUTH,leeway=30,options={'require':['exp','iat','iss','aud','sub']})
            if not isinstance(claims['sub'],str) or not claims['sub']:raise ValueError()
            if nonce is not None and not hmac.compare_digest(str(claims.get('nonce','')),nonce):raise ValueError()
            if subject is not None and claims['sub']!=subject:raise ValueError()
            return claims
        except AgentError:raise
        except Exception:raise AgentError('aiInvalidIdentity') from None
    def token_request(self,fields):
        return self.json(TOKEN,'POST',urllib.parse.urlencode(fields).encode(),{'Content-Type':'application/x-www-form-urlencoded'})
    def credentials(self,result,previous=None,inherit_scopes=False):
        old=previous or {}
        if not isinstance(result.get('access_token'),str) or result.get('token_type','').lower()!='bearer':raise AgentError('aiInvalidResponse')
        # A new authorization must prove its own grant; only refresh may omit
        # scope to retain the existing permission set.
        scopes=result.get('scope',' '.join(old.get('scopes',[])) if inherit_scopes else '')
        expiry=result.get('expires_in',3600)
        if not isinstance(scopes,str) or not isinstance(expiry,(int,float)) or not 0<expiry<=86400:raise AgentError('aiInvalidResponse')
        return {**old,'access_token':result['access_token'],'refresh_token':result.get('refresh_token',old.get('refresh_token','')),'id_token':result.get('id_token',old.get('id_token','')),'scopes':scopes.split(),'expires_at':time.time()+expiry}
    def connect(self,account_id=None,new_account=False):
        if not isinstance(new_account,bool) or (new_account and account_id):raise AgentError('invalidRequest')
        shared=self.shared_state(force=True) if self.kio else None
        revision=shared.get('revision',-1) if shared else None
        with self.lock:
            if self.pending:raise AgentError('busy')
            # Ordinary reconnects must keep the selected registration. Creating a
            # new dynamic client is an explicit account-add action only.
            selected=None if new_account else account_id or (shared or {}).get('accountId') or self.data.get('active')
            prior=self.data['accounts'].get(selected) if selected else None
            if selected and not prior and self.kio:
                matches=[row for row in self.data['accounts'].values() if row.get('subject')==selected]
                if len(matches)==1:prior=matches[0]
                elif shared and shared.get('accountId')==selected:
                    saved=self.cloud_link('access')
                    prior={'client_id':saved['client_id'],'subject':selected,'email':saved.get('email',''),'scopes':saved.get('scopes',[])}
            if account_id and not prior:raise AgentError('invalidRequest')
            request_consent=bool(prior) and (self.error=='aiPermission' or (PLAN_SCOPE not in prior.get('scopes',[]) and not (shared or {}).get('connected')))
            preference_root=self.state.parent
            if preference_root.parent.name=='account-profiles':preference_root=preference_root.parent.parent
            language=LanguagePreference(preference_root).snapshot()['language']
            state=secrets.token_urlsafe(32);nonce=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(64)
            pending={'cloudRevision':revision,'state':state,'nonce':nonce,'verifier':verifier,'previous':dict(prior) if prior else None,'done':threading.Event(),'cancel':threading.Event()};account=self
            class Callback(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_GET(self):
                    parsed=urllib.parse.urlparse(self.path);query=urllib.parse.parse_qs(parsed.query)
                    valid=parsed.path=='/auth/callback' and self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}' and len(query.get('state',[]))==1 and hmac.compare_digest(query['state'][0],state)
                    if not valid:self.send_response(400);self.end_headers();return
                    if pending['done'].is_set() or pending['cancel'].is_set():self.send_response(410);self.end_headers();return
                    pending['query']=query;pending['done'].set()
                    page=callback_page('aiAuth.received',language)
                    self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer');self.end_headers();self.wfile.write(page)
            server=HTTPServer(('127.0.0.1',0),Callback);server.timeout=.25;pending['server']=server
            redirect=f'http://127.0.0.1:{server.server_port}/auth/callback';pending['redirect']=redirect
            fields={'client_id':prior['client_id'] if prior else 'dynamic_agent_client','ext_agent_host_id':self.host,'response_type':'code','redirect_uri':redirect,'scope':SCOPES,'resource':RESOURCE,'state':state,'nonce':nonce,'code_challenge_method':'S256','code_challenge':base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')}
            if prior:
                if prior.get('id_token'):fields['id_token_hint']=prior['id_token']
                if prior.get('email'):fields['login_hint']=prior['email']
            else:fields['agent_name_hint']='Bogo Tools'
            if request_consent:fields['prompt']='consent'
            self.pending=pending;self.error=''
            threading.Thread(target=self._callback,args=(pending,),daemon=True).start()
            if not webbrowser.open(AUTH+'/api/accounts/authorize?'+urllib.parse.urlencode(fields)):
                pending['cancel'].set();self.error='aiBrowserFailed'
        return self.status()
    def _callback(self,pending):
        try:
            until=time.monotonic()+300
            while not pending['done'].is_set() and not pending['cancel'].is_set() and time.monotonic()<until:pending['server'].handle_request()
            if pending['cancel'].is_set():raise AgentError('aiLoginCancelled')
            if not pending['done'].is_set():raise AgentError('aiLoginTimeout')
            q=pending['query'];prior=pending['previous']
            if q.get('error'):
                code=q['error'][0];mapped=failure(code)
                raise AgentError(mapped if mapped!='aiRequestFailed' else 'aiLoginFailed')
            client=q.get('client_id',[prior['client_id'] if prior else ''])[0]
            if not client or client=='dynamic_agent_client' or len(q.get('client_id',[]))>1 or len(client)>500 or (prior and client!=prior['client_id']):raise AgentError('aiInvalidIdentity')
            if len(q.get('code',[]))!=1:raise AgentError('aiLoginFailed')
            result=self.token_request({'grant_type':'authorization_code','client_id':client,'code':q['code'][0],'code_verifier':pending['verifier'],'redirect_uri':pending['redirect'],'resource':RESOURCE})
            claims=self.validate(result.get('id_token',''),client,pending['nonce'],prior.get('subject') if prior else None)
            record=self.credentials(result,prior);record.update(client_id=client,subject=claims['sub'],email=claims.get('email',''),issuer=AUTH)
            plan_granted=PLAN_SCOPE in record['scopes']
            key=hashlib.sha256((AUTH+'|'+client+'|'+claims['sub']).encode()).hexdigest()
            with self.lock:
                if self.pending is not pending or pending['cancel'].is_set():raise AgentError('aiLoginCancelled')
                old=self.data;self.data={'accounts':{**old['accounts'],key:record},'active':key}
                try:self.persist()
                except Exception:self.data=old;raise AgentError('aiSecureStorage') from None
                if self.kio:self.publish_cloud(pending['cloudRevision'])
                self.generation+=1;self.models=[];self.error='' if plan_granted else 'aiPermission'
        except AgentError as exc:
            with self.lock:self.error=exc.code
        except Exception:
            with self.lock:self.error='aiLoginFailed'
        finally:
            pending['server'].server_close();pending['verifier']='';pending['query']={}
            with self.lock:
                if self.pending is pending:self.pending=None
    def cancel(self):
        with self.lock:
            if self.pending:self.pending['cancel'].set()
        return self.status()
    def select(self,key):
        if self.kio:return self.connect(key)
        with self.lock:
            if self.pending:raise AgentError('busy')
            if key not in self.data['accounts']:raise AgentError('invalidRequest')
            self.data['active']=key;self.persist();self.generation+=1;self.models=[];self.error=''
        return self.status()
    def welcome(self):
        with self.lock:
            if self.current():self.current()['welcomeSeen']=True;self.persist()
        return self.status()
    def access(self):
        if self.kio:
            self.shared_state(force=True)
            value=self.cloud_link('access')
            if not value.get('connected') or not value.get('access_token'):raise AgentError('aiNotConnected')
            if PLAN_SCOPE not in value.get('scopes',[]):
                self.error='aiPermission';self.models=[]
                raise AgentError('aiPermission')
            return value['access_token'],self.generation
        return self._local_access()
    def _local_access(self):
        with self.lock:
            account=self.current()
            if not account.get('access_token'):raise AgentError('aiNotConnected')
            if PLAN_SCOPE not in account.get('scopes',[]):raise AgentError('aiPermission')
            if account.get('expires_at',0)<=time.time()+45:
                if not account.get('refresh_token'):raise AgentError('aiReauthenticate')
                try:
                    result=self.token_request({'grant_type':'refresh_token','client_id':account['client_id'],'refresh_token':account['refresh_token'],'resource':RESOURCE})
                    if result.get('id_token'):self.validate(result['id_token'],account['client_id'],subject=account['subject'])
                    replacement=self.credentials(result,account,inherit_scopes=True);self.data['accounts'][self.data['active']]=replacement;self.persist();account=replacement
                except AgentError as exc:self.error=exc.code;raise
            if PLAN_SCOPE not in account['scopes']:raise AgentError('aiPermission')
            return account['access_token'],self.generation
    def list_models(self):
        try:
            token,generation=self.access();response=self.json(RESOURCE+'/models',headers={'Authorization':'Bearer '+token})
            if not isinstance(response.get('models'),list):raise AgentError('aiInvalidResponse')
            result=model_catalog(response['models'])
        except AgentError as exc:
            with self.lock:self.error=exc.code;self.models=[]
            raise
        with self.lock:
            if self.generation!=generation:raise AgentError('aiAccountChanged')
            verified={m['id']:m for m in self.models if m.get('verified')}
            self.models=[{**row,**({'verified':True,'vision':True,'latencyMs':verified[row['id']].get('latencyMs')} if row['id'] in verified else {})} for row in result]
            self.error=''
        return self.status()
    def disconnect(self):
        self.cancel()
        if self.kio:
            self.cloud_link('disconnect',{'confirmed':True});self.shared_status=None;self.shared_checked=0
            with self.lock:
                self.generation+=1;self.models=[];self.error=''
                for row in self.data['accounts'].values():
                    for key in ('access_token','refresh_token','id_token','scopes','expires_at'):row.pop(key,None)
                self.persist()
            return self.status()
        with self.lock:
            account=self.current();self.generation+=1;self.models=[];self.error=''
            if account.get('refresh_token'):
                try:
                    endpoint=self.discovery().get('revocation_endpoint')
                    if not endpoint:raise AgentError('aiRevokeUnconfirmed')
                    with self.raw(endpoint,'POST',urllib.parse.urlencode({'token':account['refresh_token'],'token_type_hint':'refresh_token','client_id':account['client_id']}).encode(),{'Content-Type':'application/x-www-form-urlencoded'}) as response:response.read(1024)
                except Exception:self.error='aiRevokeUnconfirmed'
            for key in ('access_token','refresh_token','id_token','scopes','expires_at'):account.pop(key,None)
            self.persist()
        return self.status()
