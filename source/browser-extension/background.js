import {planPositions,supportedPage,pageOperation,captureCss} from './capture-core.js';
import {createAgentClient} from './agent-endpoint.js';

export function checkedCaptureUrl(value){
 if(typeof value!=='string'||!value.trim()||value.length>6000)throw Error('invalidRequest');
 let url;try{url=new URL(value.trim());}catch{throw Error('invalidRequest');}
 if(!['http:','https:'].includes(url.protocol)||url.username||url.password)throw Error('unsupportedPage');
 return url.href;
}
function hostPermission(url){const parsed=new URL(url);return parsed.protocol+'//'+parsed.hostname+'/*';}
// Opening a URL never grants permission. Existing optional host access must
// cover both the requested address and any final redirect destination.
export async function openCaptureUrl(chromeApi,value,sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms)),maxPolls=150){
 const url=checkedCaptureUrl(value);
 if(!await chromeApi.permissions.contains({origins:[hostPermission(url)]}))throw Error('browserPermissionRequired');
 const created=await chromeApi.tabs.create({url,active:true});
 if(!Number.isInteger(created?.id)||!Number.isInteger(created.windowId))throw Error('unsupportedPage');
 for(let attempt=0;attempt<maxPolls;attempt++){
  const tab=await chromeApi.tabs.get(created.id);
  if(tab.status==='complete'){
   const finalUrl=checkedCaptureUrl(tab.url);
   if(!await chromeApi.permissions.contains({origins:[hostPermission(finalUrl)]}))throw Error('browserPermissionRequired');
   return {id:tab.id,windowId:tab.windowId,url:finalUrl};
  }
  await sleep(200);
 }
 throw Error('pageLoadTimeout');
}

// The same controller runs in Chrome/Edge and in the regression fixtures.
export function createBrowserController({chromeApi,agent,fetchFn=globalThis.fetch.bind(globalThis),sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms)),requestId=()=>crypto.randomUUID(),streamTimeoutMs=10000}){
 let running=false,session;const commands=new Map(),targets=new Map();
 const pageUrl=value=>String(value||'').split('#')[0];
 async function api(path,body,method='POST'){
  const response=await agent.request(path,{method,headers:{...(body===undefined?{}:{'Content-Type':'application/json'})},...(body===undefined?{}:{body:JSON.stringify(body)})});
  if(!response.ok){const error=await response.json().catch(()=>({}));throw Error(error.errorCode||'processingFailed');}return response.json();
 }
 async function register(){await api('/browser/register',{browser:/Edg\//.test(globalThis.navigator?.userAgent||'')?'Edge':'Chrome'});}
 async function execute(tabId,operation,args){
  const result=await chromeApi.scripting.executeScript({target:{tabId},func:pageOperation,args:[operation,args||{}]});
  if(!result[0]?.result&&operation!=='restore')throw Error('processingFailed');return result[0]?.result;
 }
 async function selectedTab(){const [tab]=await chromeApi.tabs.query({active:true,lastFocusedWindow:true});if(!tab?.id||!supportedPage(tab.url))throw Error('unsupportedPage');return {id:tab.id,windowId:tab.windowId,url:tab.url};}
 async function verifyTab(tab){
  const [active]=await chromeApi.tabs.query({active:true,windowId:tab.windowId});
  if(active?.id!==tab.id||pageUrl(active.url)!==pageUrl(tab.url)||(active.pendingUrl&&pageUrl(active.pendingUrl)!==pageUrl(tab.url)))throw Error('tabChanged');
 }
 async function capture(command){
  if(running){await api('/browser/result',{id:command.id,errorCode:'busy'}).catch(()=>{});return;}
  running=true;let tabId,cssAttempted=false;
  try{
   const tab=targets.get(command.options?.captureRequestId)||command.options?.captureTarget||(command.options?.url?await openCaptureUrl(chromeApi,command.options.url,sleep):await selectedTab());
   if(!Number.isInteger(tab.id)||!Number.isInteger(tab.windowId)||!supportedPage(tab.url))throw Error('unsupportedPage');
   await verifyTab(tab);tabId=tab.id;
   await execute(tabId,'begin');
   cssAttempted=true;await chromeApi.scripting.insertCSS({target:{tabId},css:captureCss,origin:'USER'});
   const meta=await execute(tabId,'measure');const plan=planPositions(meta.width,meta.height,meta.viewportWidth,meta.viewportHeight);const tiles=[];
   for(let i=0;i<plan.length;i++){
    await verifyTab(tab);
    const position=await execute(tabId,'scroll',{...plan[i],first:i===0});
    const unchanged=state=>state.viewportWidth===meta.viewportWidth&&state.viewportHeight===meta.viewportHeight&&(!meta.captureWidth||state.captureWidth===meta.captureWidth)&&(!meta.captureHeight||state.captureHeight===meta.captureHeight)&&(!state.dpr||state.dpr===meta.dpr)&&state.x===position.x&&state.y===position.y;
    if(!unchanged(position))throw Error('tabChanged');
    // Chrome permits at most two visible captures per second.
    await sleep(550);await verifyTab(tab);
    if(!unchanged(await execute(tabId,'position')))throw Error('tabChanged');
    const data=await chromeApi.tabs.captureVisibleTab(tab.windowId,{format:'png'});await verifyTab(tab);
    if(!unchanged(await execute(tabId,'position')))throw Error('tabChanged');
    const blob=await (await fetchFn(data)).blob();
    const response=await agent.request('/uploads',{method:'POST',headers:{'X-File-Name':encodeURIComponent('tile-'+(i+1)+'.png'),'Content-Type':'image/png'},body:blob});
    if(!response.ok)throw Error('processingFailed');const file=await response.json();tiles.push({id:file.id,...position});
   }
   await api('/browser/result',{id:command.id,tiles,...meta});
  }catch(error){
   const known=['unsupportedPage','tabChanged','busy','fileTooLarge','cancelled','agentUnavailable','pairingRequired','invalidRequest','pageLoadTimeout'];
   await api('/browser/result',{id:command.id,errorCode:known.includes(error.message)?error.message:'browserPermissionRequired'}).catch(()=>{});
  }finally{
   if(tabId){
    if(cssAttempted)await chromeApi.scripting.removeCSS({target:{tabId},css:captureCss,origin:'USER'}).catch(()=>{});
    await execute(tabId,'restore').catch(()=>{});
   }
   targets.delete(command.options?.captureRequestId);running=false;
  }
 }
 function receive(event){
  if(event.type!=='browserCapture'||!event.command||typeof event.command.id!=='string')return;
  const command=event.command;if(commands.has(command.id))return;
  // A reconnect can replay a command also delivered to the old stream.
  commands.set(command.id,'running');void capture(command).finally(()=>{
   commands.set(command.id,'done');
   for(const [id,state]of commands){if(commands.size<=120)break;if(state==='done')commands.delete(id);}
  });
 }
 async function ensureStream(){
  const revision=await agent.approvalRevision();
  if(session&&session.revision!==revision)stop();
  if(!await agent.isPaired()){stop();throw Error('pairingRequired');}
  if(!await chromeApi.permissions.contains({origins:['<all_urls>']})){stop();throw Error('browserPermissionRequired');}
  if(session)return session.ready;
  const current={abort:new AbortController(),revision};session=current;
  current.ready=new Promise((resolve,reject)=>{current.resolve=resolve;current.reject=reject;});
  current.ready.catch(()=>{});
  current.timer=setTimeout(()=>{current.reject(Error('browserRequired'));current.abort.abort();if(session===current)session=undefined;},streamTimeoutMs);
  current.task=(async()=>{
   try{
    await register();
    const response=await agent.request('/events',{signal:current.abort.signal});
    if(!response.ok||!response.body)throw Error('agentUnavailable');
    const reader=response.body.getReader();const decoder=new TextDecoder();let pending='';
    try{
     while(!current.abort.signal.aborted){
      const {value,done}=await reader.read();
      if(done||session!==current||current.abort.signal.aborted)break;
      pending=(pending+decoder.decode(value,{stream:true})).replace(/\r\n/g,'\n');
      if(pending.length>1_000_000)throw Error('invalidRequest');let end;
      while((end=pending.indexOf('\n\n'))>=0){
       const block=pending.slice(0,end);pending=pending.slice(end+2);
       const payload=block.split('\n').filter(line=>line.startsWith('data:')).map(line=>line.slice(5).trim()).join('\n');
       if(!payload)continue;
       if(session!==current||current.abort.signal.aborted)break;
       const event=JSON.parse(payload);
       if(event.type==='ready'){clearTimeout(current.timer);current.resolve({connected:true});}else receive(event);
      }
     }
    }finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
    throw Error('agentUnavailable');
   }catch(error){current.reject(error);}
   finally{clearTimeout(current.timer);if(session===current)session=undefined;}
  })();
  return current.ready;
 }
 function stop(){const current=session;session=undefined;if(current){clearTimeout(current.timer);current.reject(Error('cancelled'));current.abort.abort();}}
 async function connect(){await agent.pair();return ensureStream();}
 async function status(){try{if(!(await agent.status()).connected){stop();return {connected:false};}return await ensureStream();}catch(error){stop();return {connected:false,errorCode:error.message};}}
 async function requestCapture({format='png',target}={}){
  // Bind the tab before asynchronous discovery/subscription work begins.
  const tab=target||await selectedTab();
  if(!Number.isInteger(tab.id)||!Number.isInteger(tab.windowId)||!supportedPage(tab.url))throw Error('unsupportedPage');
  await ensureStream();await verifyTab(tab);
  const id=requestId();targets.set(id,tab);
  while(targets.size>120)targets.delete(targets.keys().next().value);
  // Keep this target in the owner-scoped command too: a worker restart must
  // never silently capture a different tab while replaying an unfinished job.
  try{return await api('/browser/capture',{format,split:false,captureRequestId:id,captureTarget:tab});}
  catch(error){targets.delete(id);throw error;}
 }
 async function heartbeat(){await ensureStream();await api('/browser/heartbeat',{});}
 async function disconnect(){stop();try{await api('/pair',{},'DELETE');}finally{await agent.clear();}return {connected:false};}
 return {connect,status,requestCapture,heartbeat,disconnect,start:()=>ensureStream(),stop};
}

if(typeof chrome!=='undefined'&&chrome.runtime?.id){
 const controller=createBrowserController({chromeApi:chrome,agent:createAgentClient({storage:chrome.storage.local})});
 chrome.runtime.onMessage.addListener((message,sender,reply)=>{
  if(sender.id!==chrome.runtime.id)return false;
  const actions={connect:()=>controller.connect(),capture:()=>controller.requestCapture(message),status:()=>controller.status(),disconnect:()=>controller.disconnect()};
  if(!actions[message.type])return false;
  actions[message.type]().then(reply).catch(error=>reply({errorCode:error.message}));return true;
 });
 chrome.commands.onCommand.addListener(command=>{if(command==='capture-current-page')void controller.requestCapture().catch(()=>{});});
 chrome.alarms.create('agent-reconnect',{periodInMinutes:.5});
 chrome.alarms.onAlarm.addListener(alarm=>{if(alarm.name==='agent-reconnect')void controller.heartbeat().catch(()=>{});});
 chrome.runtime.onStartup.addListener(()=>void controller.start().catch(()=>{}));void controller.start().catch(()=>{});
}
