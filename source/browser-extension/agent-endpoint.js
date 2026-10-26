// Only these loopback endpoints may receive an agent request.
export const AGENT_PORTS=Object.freeze([4323,4324,4325,4321]);
export const AGENT_ORIGINS=Object.freeze(AGENT_PORTS.map(port=>`http://127.0.0.1:${port}`));
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?![\s\S])/i;
const tokenValue=value=>typeof value==='string'&&value.length>=32&&value.length<=256&&/^[A-Za-z0-9_-]+(?![\s\S])/.test(value);
export function validAgentHealth(value,deviceId){
 return !!value&&typeof value==='object'&&!Array.isArray(value)&&value.connected===true&&typeof value.version==='string'&&/^4\.\d{1,3}\.\d{1,3}$/.test(value.version)&&
  ['macOS','Windows'].includes(value.os)&&typeof value.deviceId==='string'&&uuid.test(value.deviceId)&&
  (deviceId===undefined||value.deviceId===deviceId)&&typeof value.nativeReady==='boolean'&&
  Array.isArray(value.operations)&&value.operations.length>0&&value.operations.length<=128&&
  value.operations.every(operation=>typeof operation==='string'&&operation.length>0&&operation.length<=128&&/^[a-z][a-z0-9_]*(?![\s\S])/.test(operation))&&
  value.operations.includes('image_process');
}
function validPairing(value){return !!value&&typeof value==='object'&&!Array.isArray(value)&&
 typeof value.deviceId==='string'&&uuid.test(value.deviceId)&&AGENT_ORIGINS.includes(value.origin)&&tokenValue(value.token);}
function validPath(value){return typeof value==='string'&&value.startsWith('/')&&!value.startsWith('//')&&!/[\\\r\n?#]/.test(value)&&!value.split('/').includes('..');}

export function createAgentClient({storage,fetchFn=globalThis.fetch.bind(globalThis),probeTimeoutMs=900,extensionId=globalThis.chrome?.runtime?.id}){
 const extensionOrigin=typeof extensionId==='string'&&/^[a-p]{32}$/.test(extensionId)?'chrome-extension://'+extensionId:undefined;
 function identifiedHeaders(value){const headers=new Headers(value);if(extensionOrigin)headers.set('X-KIO-Extension-Origin',extensionOrigin);return headers;}
 let pairingInFlight,knownDeviceId,knownToken,approvalRevisionNumber=0;
 function trackApproval(value){
  // The worker can retire an old event stream without exposing its credential.
  // Moving the same approval to another allowed port does not rotate revision.
  if(knownDeviceId!==value?.deviceId||knownToken!==value?.token){knownDeviceId=value?.deviceId;knownToken=value?.token;approvalRevisionNumber++;}
  return value;
 }
 async function pairing(){
  const saved=await storage.get(['agentPairing','agentToken']);
  // A legacy token has no device identity. Require native approval again.
  if(saved.agentToken!==undefined)await storage.remove('agentToken');
  if(validPairing(saved.agentPairing))return trackApproval(saved.agentPairing);
  if(saved.agentPairing!==undefined)await storage.remove('agentPairing');
  return trackApproval(undefined);
 }
 async function probe(origin,deviceId,signal){
  if(!AGENT_ORIGINS.includes(origin))return undefined;
  const abort=new AbortController();const cancel=()=>abort.abort();
  if(signal?.aborted)return undefined;signal?.addEventListener('abort',cancel,{once:true});
  const timer=setTimeout(cancel,probeTimeoutMs);
  try{
   const response=await fetchFn(origin+'/health',{method:'GET',headers:identifiedHeaders(),cache:'no-store',redirect:'error',credentials:'omit',signal:abort.signal});
   if(!response.ok)return undefined;const health=await response.json();
   return validAgentHealth(health,deviceId)&&health.nativeReady?{origin,deviceId:health.deviceId,health}:undefined;
  }catch{return undefined;}finally{clearTimeout(timer);signal?.removeEventListener('abort',cancel);}
 }
 async function discover(deviceId,signal){
  const candidates=await Promise.all(AGENT_ORIGINS.map(origin=>probe(origin,deviceId,signal)));
  if(signal?.aborted)throw Error('cancelled');
  const found=candidates.find(Boolean);if(!found)throw Error('agentUnavailable');return found;
 }
 async function resolve(signal){
  const saved=await pairing();if(!saved)throw Error('pairingRequired');
  // Probe without credentials before every authenticated request. A server at
  // the previous port may now be a different application or another device.
  const endpoint=await discover(saved.deviceId,signal);const current=await pairing();
  if(!current||current.deviceId!==saved.deviceId||current.token!==saved.token)throw Error('pairingRequired');
  if(current.origin!==endpoint.origin)await storage.set({agentPairing:{...current,origin:endpoint.origin}});
  return {...endpoint,token:current.token};
 }
 async function request(path,options={}){
  if(!validPath(path))throw Error('invalidRequest');
  const endpoint=await resolve(options.signal);const headers=identifiedHeaders(options.headers);
  headers.set('X-Local-Agent-Token',endpoint.token);
  const response=await fetchFn(endpoint.origin+path,{...options,headers,cache:'no-store',redirect:'error',credentials:'omit'});
  if(response.status===401){const current=await pairing();if(current?.token===endpoint.token&&current.deviceId===endpoint.deviceId)await storage.remove('agentPairing');}
  return response;
 }
 async function connect(clientName){
  const saved=await pairing();
  if(saved){
   // Connecting again must reuse the user's approval. A public /health reply
   // cannot validate a token, so check the existing read-only authenticated API.
   const response=await request('/browser',{method:'GET'});
   if(response.ok)return {connected:true};
   if(response.status!==401)throw Error(response.status===403?'pairingDenied':'agentUnavailable');
   // request() removed only the rejected token. Do not overwrite a newer
   // pairing that another extension context may have saved in the meantime.
   if(await pairing())throw Error('pairingRequired');
  }
  // A revoked approval is renewed only for the same device, and only when
  // pair() is explicitly called by the user's Connect button.
  const endpoint=await discover(saved?.deviceId);const response=await fetchFn(endpoint.origin+'/pair',{method:'POST',headers:identifiedHeaders({'Content-Type':'application/json'}),body:JSON.stringify({clientName}),cache:'no-store',redirect:'error',credentials:'omit'});
  if(!response.ok){const error=await response.json().catch(()=>({}));throw Error(error.errorCode||'pairingDenied');}
  const result=await response.json();if(!tokenValue(result?.token)||result?.device?.deviceId!==endpoint.deviceId)throw Error('pairingDenied');
  if(!await probe(endpoint.origin,endpoint.deviceId))throw Error('agentUnavailable');
  await storage.set({agentPairing:{deviceId:endpoint.deviceId,origin:endpoint.origin,token:result.token}});
  await storage.remove('agentToken');return {connected:true};
 }
 function pair(clientName='ADMIN Web Capture'){
  // Repeated clicks while the first native approval is open share one request.
  if(!pairingInFlight)pairingInFlight=connect(clientName).finally(()=>{pairingInFlight=undefined;});
  return pairingInFlight;
 }
 async function status(){try{if(!await pairing())return {connected:false};const response=await request('/browser',{method:'GET'});return {connected:response.ok};}catch{return {connected:false};}}
 async function clear(){await storage.remove(['agentPairing','agentToken']);}
 async function approvalRevision(){await pairing();return approvalRevisionNumber;}
 return {request,pair,status,clear,approvalRevision,isPaired:async()=>!!await pairing()};
}
