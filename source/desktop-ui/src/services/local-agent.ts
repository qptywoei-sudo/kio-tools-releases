import {type KIOAccountStatus} from '@/features/local-tools/kio-account';
import type {StorageStatus,DriveStatus,DriveFolder,DriveFoldersResponse,DriveFilesResponse,DriveUploadResponse,DriveDownloadResponse} from '@/features/local-tools/drive-library';
import type {UpdateStatus} from '@/features/local-tools/update-types';
import type {AIStatus,AIJob} from '@/features/local-tools/ai-types';
import type {SignatureAsset} from '@/features/local-tools/SignatureLibrary';
import type {FileSearchFilters,FileSearchPreview} from '@/features/local-tools/file-search';
import type {AgentEvent,AgentFile,AgentHealth,AgentJob,AgentRoot,AgentSettings,PhoneOptions,PhoneState,RenamePreview,ReleaseManifest} from '@/features/local-tools/types';

export const localAgentPorts=[4323,4324,4325,4321] as const;
const deviceIdPattern=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?![\s\S])/i;
export function validAgentHealth(value:unknown):value is AgentHealth{
 if(!value||typeof value!=='object'||Array.isArray(value))return false;
 const health=value as AgentHealth;
 return health.connected===true&&typeof health.version==='string'&&/^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?(?![\s\S])/.test(health.version)&&typeof health.deviceId==='string'&&deviceIdPattern.test(health.deviceId)&&['macOS','Windows','Linux'].includes(health.os??'')&&typeof health.nativeReady==='boolean'&&Array.isArray(health.operations)&&health.operations.length>0&&health.operations.length<=100&&health.operations.every(operation=>typeof operation==='string'&&/^[a-zA-Z0-9_-]{1,80}(?![\s\S])/.test(operation));
}
const opaqueId=/^[a-zA-Z0-9_-]{1,160}$/;
const tokenPattern=/^[A-Za-z0-9_-]{32,256}(?![\s\S])/;
const allowedAgentOrigins=localAgentPorts.map(port=>'http://127.0.0.1:'+port);
type DesktopSession={token:string;deviceId:string;origin:string;ownerId:'desktop';clientName:'GalaxyControl'};
export function validDesktopSession(value:unknown,page:{origin:string;pathname:string}|undefined,scope:string):value is DesktopSession{
 if(scope!=='desktop'||!page||!/^\/tools(?:\/|$)/.test(page.pathname)||!allowedAgentOrigins.includes(page.origin)||!value||typeof value!=='object'||Array.isArray(value))return false;
 const session=value as Record<string,unknown>;
 return session.origin===page.origin&&session.ownerId==='desktop'&&session.clientName==='GalaxyControl'&&typeof session.token==='string'&&tokenPattern.test(session.token)&&typeof session.deviceId==='string'&&deviceIdPattern.test(session.deviceId);
}
function browserStorage(kind:'localStorage'|'sessionStorage'='localStorage'){try{return globalThis[kind];}catch{return undefined;}}
function permissionFailure(error:unknown){return !!error&&typeof error==='object'&&'name'in error&&['NotAllowedError','SecurityError'].includes(String(error.name));}
function delay(ms:number,signal:AbortSignal){return new Promise<void>(resolve=>{if(signal.aborted){resolve();return;}const abort=()=>{clearTimeout(timer);resolve();},timer=setTimeout(()=>{signal.removeEventListener('abort',abort);resolve();},ms);signal.addEventListener('abort',abort,{once:true});});}
export type LocalAgentConnectionStatus='checking'|'connected'|'unpaired'|'offline'|'permissionRequired';
export type LocalAgentConnectionState={status:LocalAgentConnectionStatus;health:AgentHealth|null;paired:boolean;browserConnected:boolean;errorCode?:string};
export function checkedAgentId(value:string){if(!opaqueId.test(value))throw Error('INVALID_ID');return value;}
export function supportedOperation(health:AgentHealth|null,operation:string){return (!Array.isArray(health?.capabilities)&&health?.capabilities?.[operation]===true)||(Array.isArray(health?.operations)?health.operations.includes(operation):health?.operations?.[operation]===true);}
export function normalizeReleaseManifest(input:unknown):ReleaseManifest{
 if(!input||typeof input!=='object')return {};
 const value=input as Record<string,unknown>;
 const url=(item:unknown)=>{if(typeof item!=='string'||item.length>2048)return undefined;try{const u=new URL(item);return u.protocol==='https:'&&!u.username&&!u.password?u.href:undefined;}catch{return undefined;}};
 const release:ReleaseManifest={macDownloadUrl:url(value.macDownloadUrl),windowsDownloadUrl:url(value.windowsDownloadUrl),latestVersion:typeof value.latestVersion==='string'&&/^[a-zA-Z0-9.+_-]{1,80}$/.test(value.latestVersion)?value.latestVersion:undefined};
 for(const key of ['macUpdateUrl','windowsUpdateUrl','browserDownloadUrl','macArmDownloadUrl','macIntelDownloadUrl'] as const){const safe=url(value[key]);if(safe)release[key]=safe;}
 for(const key of ['macBytes','windowsBytes','macArmBytes','macIntelBytes'] as const){const bytes=value[key];if(typeof bytes==='number'&&Number.isSafeInteger(bytes)&&bytes>0&&bytes<5*1024**3)release[key]=bytes;}
 for(const key of ['macSha256','windowsSha256','macArmSha256','macIntelSha256'] as const){const sha=value[key];if(typeof sha==='string'&&/^[a-fA-F0-9]{64}(?![\s\S])/.test(sha))release[key]=sha.toLowerCase();}
 return release;
}
export function downloadForPlatform(release:ReleaseManifest,platform:string){return /mac|darwin/i.test(platform)?release.macDownloadUrl:/win/i.test(platform)?release.windowsDownloadUrl:undefined;}
// SSE is consumed with fetch: credentials remain in headers, never query strings.
export async function consumeAgentEvents(stream:ReadableStream<Uint8Array>,onEvent:(event:AgentEvent)=>void,signal?:AbortSignal){
 const reader=stream.getReader(),decoder=new TextDecoder();let pending='';
 const abort=()=>void reader.cancel();signal?.addEventListener('abort',abort,{once:true});
 try{while(!signal?.aborted){const {done,value}=await reader.read();if(done)break;pending+=decoder.decode(value,{stream:true});pending=pending.replace(/\r\n/g,'\n');if(pending.length>1024*1024)throw Error('EVENT_LIMIT');let boundary;
 while((boundary=pending.indexOf('\n\n'))!==-1){const block=pending.slice(0,boundary);pending=pending.slice(boundary+2);const data=block.split('\n').filter(line=>line.startsWith('data:')).map(line=>line.slice(5).trimStart()).join('\n');if(!data)continue;const event=JSON.parse(data) as AgentEvent;if(!event||typeof event.type!=='string')throw Error('EVENT_INVALID');onEvent(event);}}
 }finally{signal?.removeEventListener('abort',abort);reader.releaseLock();}
}
export class LocalAgentClient{
 readonly webContext=typeof window!=='undefined'&&window.parent!==window;
 private token='';
 private storageKey:string;
 private deviceKey:string;
 private pairedDevice='';
 private base='';
 private healthRequest:Promise<AgentHealth>|undefined;
 private authorizationRevision=0;
 private persistedPairing=true;
 private desktopHostSession=false;
 private pairingRequest:Promise<{token:string;device?:AgentHealth}>|undefined;
 private subscriptionEpoch=0;
 private subscriptionAbort:AbortController|undefined;
 private eventAttemptAbort:AbortController|undefined;
 constructor(private fetcher:typeof fetch=(...args)=>globalThis.fetch(...args),scope='desktop',private storage:Storage|undefined=browserStorage()){
  const suffix=encodeURIComponent((typeof location==='undefined'?'test':location.origin)+'.'+scope);this.storageKey='admin.localAgent.token.v1.'+suffix;this.deviceKey='admin.localAgent.device.v1.'+suffix;
  if(this.webContext){this.persistedPairing=false;return;}
  const desktopSession=(globalThis as typeof globalThis&{__galaxyDesktopSession?:unknown}).__galaxyDesktopSession;
  if(validDesktopSession(desktopSession,typeof location==='undefined'?undefined:location,scope)){
   // Only the native host can inject its private credential before this trusted
   // page loads. Keep it in memory, separate from persisted ADMIN approvals.
   this.desktopHostSession=true;this.persistedPairing=false;this.base=desktopSession.origin;this.setPairing(desktopSession.token,desktopSession.deviceId);
  }else this.syncStoredPairing();
 }
 private setPairing(token:string,device:string){if(this.token===token&&this.pairedDevice===device)return;this.token=token;this.pairedDevice=device;this.authorizationRevision++;this.healthRequest=undefined;this.eventAttemptAbort?.abort();}
 private syncStoredPairing(){
  if(!this.storage||!this.persistedPairing)return;
  try{const token=this.storage.getItem(this.storageKey),device=this.storage.getItem(this.deviceKey);this.setPairing(token&&tokenPattern.test(token)&&device&&deviceIdPattern.test(device)?token:'',token&&tokenPattern.test(token)&&device&&deviceIdPattern.test(device)?device:'');}
  catch{/* A temporarily unavailable browser store must not erase session approval. */}
 }
 get paired(){this.syncStoredPairing();return Boolean(this.token);}
 clearPairing(){if(!this.token&&!this.pairedDevice){this.authorizationRevision++;this.healthRequest=undefined;this.eventAttemptAbort?.abort();}else this.setPairing('','');if(this.desktopHostSession)return;this.persistedPairing=true;try{this.storage?.removeItem(this.storageKey);this.storage?.removeItem(this.deviceKey);}catch{this.persistedPairing=false;}}
 async revokePairing(){this.syncStoredPairing();const token=this.token,device=this.pairedDevice;try{await this.json('/pair','DELETE');}finally{this.syncStoredPairing();if(this.token===token&&this.pairedDevice===device)this.clearPairing();}}
 private async request(path:string,init:RequestInit={},auth=true){
  if(!path.startsWith('/')||path.startsWith('//')||/[\\\r\n?#]/.test(path)||path.split('/').includes('..'))throw Error('INVALID_ENDPOINT');
  this.syncStoredPairing();if(auth&&!this.token)throw Error('PAIRING_REQUIRED');const revision=this.authorizationRevision;
  // A different local ADMIN service may own the previous port after a restart.
  // Discover and validate without credentials before sending a pairing token.
  const health=await this.health();this.syncStoredPairing();if(auth&&!this.token)throw Error('PAIRING_REQUIRED');if(revision!==this.authorizationRevision)throw Error('AGENT_STATE_CHANGED');if(init.signal?.aborted)throw Error('CANCELLED');
  if(auth&&health.deviceId!==this.pairedDevice)throw Error('AGENT_DEVICE_UNAVAILABLE');
  const token=this.token,device=this.pairedDevice,base=this.base,headers=new Headers(init.headers);headers.delete('Authorization');if(auth)headers.set('X-Local-Agent-Token',token);else headers.delete('X-Local-Agent-Token');
  const response=await this.fetcher(base+path,{...init,headers,credentials:'omit',redirect:'error',cache:'no-store',signal:init.signal??AbortSignal.timeout(['/pair','/files/choose','/roots/select','/settings/save-folder','/permissions/open','/browser/install','/phone/pair','/phone/connect','/phone/start','/phone/keyboard-settings'].includes(path)?120000:30000)});
  this.syncStoredPairing();
  if(!response.ok){if(response.status===401&&this.token===token&&this.pairedDevice===device)this.clearPairing();let code='AGENT_UNAVAILABLE';try{const body=await response.json();if(typeof body.errorCode==='string'&&/^[A-Za-z_][A-Za-z0-9_]{0,79}$/.test(body.errorCode))code=body.errorCode;else if(typeof body.error==='string'&&/^[A-Za-z_][A-Za-z0-9_]{0,79}$/.test(body.error))code=body.error;}catch{/* Preserve bounded generic error. */}throw Error(code);}
  if(auth&&(revision!==this.authorizationRevision||token!==this.token||device!==this.pairedDevice)){void response.body?.cancel().catch(()=>{});throw Error('AGENT_STATE_CHANGED');}
  return response;
 }
 private async json<T>(path:string,method='GET',body?:unknown,auth=true):Promise<T>{return (await this.request(path,{method,headers:body===undefined?{}:{'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})},auth)).json();}
 health():Promise<AgentHealth>{this.syncStoredPairing();if(this.healthRequest)return this.healthRequest;const request=this.discover();this.healthRequest=request;void request.finally(()=>{if(this.healthRequest===request)this.healthRequest=undefined;}).catch(()=>{});return request;}
 private async probe(base:string,timeout:number,signal:AbortSignal):Promise<{base:string;health:AgentHealth}>{
  if(!allowedAgentOrigins.includes(base))throw Error('AGENT_UNAVAILABLE');
  const response=await this.fetcher(base+'/health',{method:'GET',credentials:'omit',redirect:'error',cache:'no-store',signal:AbortSignal.any([signal,AbortSignal.timeout(timeout)])});
  if(!response.ok)throw Error('AGENT_UNAVAILABLE');const health:unknown=await response.json();if(!validAgentHealth(health))throw Error('AGENT_UNAVAILABLE');return {base,health};
 }
 private async discover():Promise<AgentHealth>{
  const standalone=typeof location!=='undefined'&&['127.0.0.1','localhost'].includes(location.hostname)?Number(location.port):0;
  const preferred=this.base?Number(new URL(this.base).port):standalone;
  const ports=[...(localAgentPorts.includes(preferred as typeof localAgentPorts[number])?[preferred]:[]),...localAgentPorts.filter(port=>port!==preferred)];
  const device=this.pairedDevice,revision=this.authorizationRevision,abort=new AbortController();let other=false,permission=false;
  // The first browser request may wait for Chrome's local network permission.
  const timeout=this.base?1500:30000;
  // Probe the finite candidates concurrently so a hanging unrelated service
  // cannot hide a working agent at a later port. Discovery sends no credential.
  try{
   const check=async(port:number)=>{try{const candidate=await this.probe('http://127.0.0.1:'+port,timeout,abort.signal);if(device&&candidate.health.deviceId!==device){other=true;throw Error('AGENT_DEVICE_UNAVAILABLE');}return candidate;}catch(error){permission||=permissionFailure(error);throw error;}};
   let found:{base:string;health:AgentHealth}|undefined;
   if(this.base){try{found=await check(preferred);}catch{/* The last endpoint may have stopped or moved. */}}
   found??=await Promise.any(ports.filter(port=>!this.base||port!==preferred).map(check));
   this.syncStoredPairing();if(revision!==this.authorizationRevision)throw Error('AGENT_STATE_CHANGED');this.base=found.base;return found.health;
  }catch(error){this.syncStoredPairing();if(revision!==this.authorizationRevision||error instanceof Error&&error.message==='AGENT_STATE_CHANGED')throw Error('AGENT_STATE_CHANGED',{cause:error});this.base='';throw Error(permission?'LOCAL_NETWORK_PERMISSION_REQUIRED':device&&other?'AGENT_DEVICE_UNAVAILABLE':'AGENT_UNAVAILABLE',{cause:error});}
  finally{abort.abort();}
 }
 pair(){if(!this.pairingRequest){const request=this.performPair();this.pairingRequest=request;void request.finally(()=>{if(this.pairingRequest===request)this.pairingRequest=undefined;}).catch(()=>{});}return this.pairingRequest;}
 private async performPair(){
  if(this.paired){try{const health=await this.health();await this.browser();return {token:this.token,device:health};}catch(error){if(this.paired)throw error;}}
  if(this.desktopHostSession)throw Error('PAIRING_REQUIRED');
  const health=await this.health(),base=this.base,revision=this.authorizationRevision;if(!health.nativeReady)throw Error('nativeUnavailable');
  const response=await this.fetcher(base+'/pair',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({clientName:'ADMIN'}),credentials:'omit',redirect:'error',cache:'no-store',signal:AbortSignal.timeout(120000)});
  if(!response.ok){const error=await response.json().catch(()=>({}));throw Error(typeof error.errorCode==='string'&&/^[A-Za-z_][A-Za-z0-9_]{0,79}$/.test(error.errorCode)?error.errorCode:'PAIRING_INVALID');}
  const value:{token:string;device?:AgentHealth}=await response.json();this.syncStoredPairing();if(revision!==this.authorizationRevision)throw Error('AGENT_STATE_CHANGED');
  if(typeof value.token!=='string'||!tokenPattern.test(value.token)||value.device?.deviceId!==health.deviceId)throw Error('PAIRING_INVALID');
  const confirmed=await this.probe(base,1500,new AbortController().signal);this.syncStoredPairing();if(revision!==this.authorizationRevision||confirmed.health.deviceId!==health.deviceId)throw Error('PAIRING_INVALID');
  this.setPairing(value.token,health.deviceId!);try{this.storage?.setItem(this.storageKey,this.token);this.storage?.setItem(this.deviceKey,this.pairedDevice);this.persistedPairing=Boolean(this.storage);}catch{this.persistedPairing=false;}return value;
 }
 accountStatus(){return this.json<KIOAccountStatus>('/account/status');}
 accountLogin(){return this.json<KIOAccountStatus>('/account/login','POST',{});}
 accountCancel(){return this.json<KIOAccountStatus>('/account/cancel','POST',{});}
 accountLogout(){return this.json<KIOAccountStatus>('/account/logout','POST',{});}
 async upload(file:File){if(file.size>256*1024*1024)throw Error('FILE_LIMIT');return (await this.request('/uploads',{method:'POST',headers:{'Content-Type':file.type||'application/octet-stream','X-File-Name':encodeURIComponent(file.name)},body:file,signal:AbortSignal.timeout(120000)})).json() as Promise<AgentFile>;}
 choose(kind:string,multiple=true){return this.json<{files:AgentFile[]}>('/files/choose','POST',{kind,multiple});}
 latestRecording(){return this.json<{file:AgentFile|null}>('/recordings/latest');}
 async selectLanguage(language:import('@/i18n/language').Language){return this.json<import('@/i18n/language').LanguagePreference>('/preferences/language','POST',{language});}
 languagePreference(){return this.json<import('@/i18n/language').LanguagePreference>('/preferences/language');}
 historyFiles(cursor=''){return this.json<{files:AgentFile[];nextCursor:string}>('/files/history','POST',{cursor:cursor?checkedAgentId(cursor):''});}
 jobs(operation:string,inputs:string[],options:Record<string,unknown>={}){return this.json<{job:AgentJob}>('/jobs','POST',{operation,inputs:inputs.map(checkedAgentId),options});}
 cancel(id:string){return this.json('/jobs/'+checkedAgentId(id)+'/cancel','POST',{});}
 job(id:string){return this.json<{job:AgentJob}>('/jobs/'+checkedAgentId(id));}
 async artifact(id:string){return (await this.request('/artifacts/'+checkedAgentId(id),{signal:AbortSignal.timeout(120000)})).blob();}
 fileAction(action:'open'|'reveal',id:string){return this.json('/files/'+action,'POST',{id:checkedAgentId(id)});}
 signatures(){return this.json<{signatures:SignatureAsset[]}>('/signatures');}
 saveSignature(id:string,name:string){return this.json<{signature:SignatureAsset}>('/signatures','POST',{id:checkedAgentId(id),name});}
 roots(){return this.json<{roots:AgentRoot[]}>('/roots');}
 selectRoot(){return this.json('/roots/select','POST',{});}
 removeRoot(id:string){return this.json('/roots/'+checkedAgentId(id),'DELETE');}
 async search(query:string,filtersOrLimit:FileSearchFilters|number=40,signal?:AbortSignal){const filters=typeof filtersOrLimit==='number'?undefined:filtersOrLimit,limit=typeof filtersOrLimit==='number'?filtersOrLimit:40;return (await this.request('/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:query.trim().slice(0,1000),limit:Math.max(1,Math.min(80,limit)),...(filters?{filters}:{})}),signal})).json() as Promise<{files:AgentFile[]}>;}
 cancelIndex(id:string){return this.json('/roots/'+checkedAgentId(id)+'/cancel','POST',{});}
 previewFile(id:string){return this.json<FileSearchPreview>('/files/'+checkedAgentId(id)+'/preview');}
 renamePreview(ids:string[],options:Record<string,unknown>){return this.json<RenamePreview>('/rename/preview','POST',{ids:ids.map(checkedAgentId),options});}
 renameCommit(previewId:string){return this.json('/rename/commit','POST',{previewId:checkedAgentId(previewId)});}
 async settings(){const value=await this.json<{settings:AgentSettings}>('/settings');return value.settings;}
 async applySettings(settings:AgentSettings){const safe:AgentSettings={};if(settings.saveMode!==undefined)safe.saveMode=settings.saveMode;if(settings.language!==undefined)safe.language=settings.language;if(settings.shortcuts!==undefined)safe.shortcuts=settings.shortcuts;if(settings.autoStart!==undefined)safe.autoStart=settings.autoStart;if(settings.closeAfterCaptureCopy!==undefined)safe.closeAfterCaptureCopy=settings.closeAfterCaptureCopy;if(settings.openCaptureEditor!==undefined)safe.openCaptureEditor=settings.openCaptureEditor;if(settings.captureFormat!==undefined)safe.captureFormat=settings.captureFormat;if(settings.recording!==undefined)safe.recording=settings.recording;const value=await this.json<{settings:AgentSettings}>('/settings','PATCH',safe);return value.settings;}
 async copyImage(id:string){const result=await this.json<{copied:boolean}>('/clipboard/image','POST',{id:checkedAgentId(id)});if(result.copied!==true)throw Error('processingFailed');}
 async updateStatus(){return this.json<UpdateStatus>('/updates/status');}
 async updateAction(action:'check'|'download'|'install'){return this.json<UpdateStatus>('/updates/'+action,'POST',{});}
 async updatePreferences(autoCheck:boolean){return this.json<UpdateStatus>('/updates/preferences','POST',{autoCheck});}
 async aiStatus(){return this.json<AIStatus>('/ai/status');}
 async aiAccount(action:'connect'|'cancel-login'|'disconnect'|'select-account'|'models'|'settings'|'welcome',body:Record<string,unknown>={}){return this.json<AIStatus>('/ai/'+action,'POST',body);}
 async aiStart(kind:'capture'|'scan'|'analyze'|'reply'|'retranslate',body:Record<string,unknown>={}){return this.json<AIJob>('/ai/'+kind,'POST',body);}
 async aiScanPreview(id:string){return (await this.request('/ai/scans/'+checkedAgentId(id)+'/preview')).blob();}
 async aiTranslatedImage(id:string){return (await this.request('/ai/images/'+checkedAgentId(id))).blob();}
 async aiJob(id:string){return this.json<AIJob>('/ai/jobs/'+checkedAgentId(id));}
 async aiCancel(id:string){return this.json('/ai/cancel','POST',{id:checkedAgentId(id)});}
 async aiMetrics(id:string,timings:Record<string,number>){return this.json('/ai/metrics','POST',{id:checkedAgentId(id),...timings});}
 async aiClear(){return this.json('/ai/clear','POST',{});}
 async copyImageBlob(png:Blob){if(png.type!=='image/png'||!png.size||png.size>64*1024*1024)throw Error('fileTooLarge');const response=await this.request('/clipboard/png',{method:'POST',headers:{'Content-Type':'image/png'},body:png,signal:AbortSignal.timeout(30000)});const result=await response.json();if(result.copied!==true)throw Error('processingFailed');}
 saveFolder(){return this.json('/settings/save-folder','POST',{});}
 storageStatus(){return this.json<StorageStatus>('/storage');}
 driveConnect(switchAccount=false){return this.json<DriveStatus>('/drive/connect','POST',{switchAccount});}
 driveCancel(){return this.json<DriveStatus>('/drive/cancel','POST',{});}
 driveDisconnect(){return this.json('/drive/disconnect','POST',{});}
 storageRetry(){return this.json('/storage/retry','POST',{});}
 driveFolders(options:{parentId?:string;pageToken?:string}={}){return this.json<DriveFoldersResponse>('/drive/folders/list','POST',options);}
 driveCreateFolder(name:string,parentId?:string){return this.json<{folder:DriveFolder}>('/drive/folders/create','POST',{name,parentId});}
 driveSelectFolder(folderId?:string){return this.json<{drive:DriveStatus}>('/drive/folders/select','POST',{folderId});}
 driveFiles(options:{parentId?:string;pageToken?:string;query?:string;kind?:string}={}){return this.json<DriveFilesResponse>('/drive/files/list','POST',options);}
 async driveUpload(inputIds:string[],expectedAccountId?:string){return (await this.request('/drive/files/upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({inputIds:inputIds.map(checkedAgentId),expectedAccountId}),signal:AbortSignal.timeout(120000)})).json() as Promise<DriveUploadResponse>;}
 async driveDownload(fileId:string){return (await this.request('/drive/files/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fileId:checkedAgentId(fileId)}),signal:AbortSignal.timeout(600000)})).json() as Promise<DriveDownloadResponse>;}

 permissions(){return this.json<Record<string,string>>('/permissions');}
 openPermission(permission:string){return this.json('/permissions/open','POST',{permission});}
 browserInstallInfo(){return this.json<{folderPath:string;extensionName:string}>('/browser/install-info');}
 installBrowser(){return this.json<{prepared:true;folderPath:string;extensionName:string}>('/browser/install','POST',{});}
 browser(){return this.json<{connected?:boolean;capabilities?:Record<string,boolean>}>('/browser');}
 captureBrowser(format:string,split:boolean,url=''){return this.json<{job?:AgentJob}>('/browser/capture','POST',{format,split,...(url.trim()?{url:url.trim()}:{})});}
 phone(){return this.json<PhoneState>('/phone');}
 pairPhone(address:string,code:string){return this.json<PhoneState>('/phone/pair','POST',{address,code});}
 connectPhone(address:string){return this.json<PhoneState>('/phone/connect','POST',{address});}
 startPhone(input:string|({deviceId:string}&Partial<PhoneOptions>),options:Partial<PhoneOptions>={}){const deviceId=typeof input==='string'?input:input.deviceId,source=typeof input==='string'?options:input;return this.json<PhoneState>('/phone/start','POST',{deviceId,...Object.fromEntries(['keyboard','mouse','audio','clipboard'].filter(key=>source[key as keyof PhoneOptions]!==undefined).map(key=>[key,source[key as keyof PhoneOptions]]))});}
 stopPhone(){return this.json<PhoneState>('/phone/stop','POST',{});}
 phoneKeyboardSettings(deviceId:string){return this.json<PhoneState>('/phone/keyboard-settings','POST',{deviceId});}
 async connection(signal?:AbortSignal):Promise<LocalAgentConnectionState>{
  let health:AgentHealth|null=null;
  try{
   health=await this.health();if(signal?.aborted)throw Error('CANCELLED');
   if(!health.nativeReady)return {status:'offline',health,paired:this.paired,browserConnected:false,errorCode:'nativeUnavailable'};
   if(!this.paired)return {status:'unpaired',health,paired:false,browserConnected:false,errorCode:'PAIRING_REQUIRED'};
   const revision=this.authorizationRevision,browser:{connected?:boolean}=await (await this.request('/browser',{signal})).json();this.syncStoredPairing();if(revision!==this.authorizationRevision||health.deviceId!==this.pairedDevice)throw Error('AGENT_STATE_CHANGED');
   return {status:'connected',health,paired:true,browserConnected:browser.connected===true};
  }catch(error){
   const code=error instanceof Error?error.message:'AGENT_UNAVAILABLE',paired=this.paired;
   if(health&&!paired)return {status:'unpaired',health,paired:false,browserConnected:false,errorCode:'PAIRING_REQUIRED'};
   return {status:code==='LOCAL_NETWORK_PERMISSION_REQUIRED'||permissionFailure(error)?'permissionRequired':'offline',health:null,paired,browserConnected:false,errorCode:permissionFailure(error)?'LOCAL_NETWORK_PERMISSION_REQUIRED':['LOCAL_NETWORK_PERMISSION_REQUIRED','AGENT_DEVICE_UNAVAILABLE','AGENT_STATE_CHANGED','CANCELLED'].includes(code)?code:'AGENT_UNAVAILABLE'};
  }
 }
 // Health checks never request approval. Saved authorization survives a stopped
 // app and is validated again when the same UUID comes back, even at a new port.
 watchConnection(onState:(state:LocalAgentConnectionState)=>void,signal:AbortSignal):()=>void{
  let stopped=signal.aborted,generation=0,running=false,pending=false,failures=0,timer:ReturnType<typeof setTimeout>|undefined;
  const windowEvents=typeof window==='undefined'?undefined:window,documentEvents=typeof document==='undefined'?undefined:document;
  const visible=()=>documentEvents?.visibilityState!=='hidden';
  const emit=(state:LocalAgentConnectionState)=>{if(!stopped&&!signal.aborted)onState(state);};
  const cancelTimer=()=>{if(timer!==undefined)clearTimeout(timer);timer=undefined;};
  const schedule=(ms:number)=>{cancelTimer();if(!stopped&&visible())timer=setTimeout(()=>{timer=undefined;void check();},ms);};
  const check=async()=>{
   if(stopped||signal.aborted||!visible())return;
   if(running){pending=true;return;}running=true;const epoch=++generation;
   try{const state=await this.connection(signal);if(!stopped&&epoch===generation){emit(state);failures=state.status==='connected'||state.status==='unpaired'?0:failures+1;schedule(state.status==='connected'||state.status==='unpaired'?10000:Math.min(10000,500*2**Math.min(failures,5)));}}
   finally{running=false;if(pending&&!stopped){pending=false;void check();}}
  };
  const refresh=()=>{if(stopped)return;generation++;cancelTimer();if(!visible())return;if(running)pending=true;else void check();};
  const storageChanged=(event:StorageEvent)=>{if(event.key===null||event.key===this.storageKey||event.key===this.deviceKey)refresh();};
  const stop=()=>{if(stopped)return;stopped=true;generation++;cancelTimer();windowEvents?.removeEventListener('focus',refresh);windowEvents?.removeEventListener('online',refresh);windowEvents?.removeEventListener('storage',storageChanged);documentEvents?.removeEventListener('visibilitychange',refresh);signal.removeEventListener('abort',stop);};
  if(!stopped){windowEvents?.addEventListener('focus',refresh);windowEvents?.addEventListener('online',refresh);windowEvents?.addEventListener('storage',storageChanged);documentEvents?.addEventListener('visibilitychange',refresh);signal.addEventListener('abort',stop,{once:true});emit({status:'checking',health:null,paired:this.paired,browserConnected:false});void check();}
  return stop;
 }
 async subscribe(onEvent:(event:AgentEvent)=>void,signal:AbortSignal,onConnection:(connected:boolean)=>void=()=>{}){
  const epoch=++this.subscriptionEpoch;this.subscriptionAbort?.abort();const controller=new AbortController();this.subscriptionAbort=controller;const subscriptionSignal=AbortSignal.any([signal,controller.signal]);let wait=500;
  const current=()=>epoch===this.subscriptionEpoch&&!subscriptionSignal.aborted;
  if(current())onConnection(false);
  try{while(current()&&this.paired){const revision=this.authorizationRevision,attempt=new AbortController();this.eventAttemptAbort=attempt;const attemptSignal=AbortSignal.any([subscriptionSignal,attempt.signal]);
   try{const response=await this.request('/events',{signal:attemptSignal});if(!response.body)throw Error('EVENT_STREAM_MISSING');if(!current()||revision!==this.authorizationRevision){void response.body.cancel().catch(()=>{});continue;}onConnection(true);await consumeAgentEvents(response.body,event=>{this.syncStoredPairing();if(current()&&revision===this.authorizationRevision)onEvent(event);},attemptSignal);wait=500;}
   catch(error){if(!current())return;if(!this.paired)throw error;}
   finally{if(this.eventAttemptAbort===attempt)this.eventAttemptAbort=undefined;if(current())onConnection(false);}
   if(current())await delay(wait,subscriptionSignal);wait=Math.min(10000,wait*2);
  }}finally{if(this.subscriptionAbort===controller)this.subscriptionAbort=undefined;}
 }
}
export function clearStoredAgentPairings(storage:Storage|undefined=browserStorage()){const clear=(value:Storage|undefined)=>{if(!value)return;try{for(const key of Object.keys(value))if(key.startsWith('admin.localAgent.token.v1.')||key.startsWith('admin.localAgent.device.v1.'))value.removeItem(key);}catch{/* Storage unavailable. */}};clear(storage);clear(browserStorage('sessionStorage'));}
