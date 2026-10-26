import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile,mkdtemp,mkdir,copyFile,writeFile,rm,access} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {CAPTURE_PERMISSIONS,POPUP_WORDS,mountPopup} from './popup.js';

// Labelled browser/DOM mock: exercises the production popup controller, not OS
// permission dialogs. Actual Chrome/Edge permission acceptance is a separate QA.
class Element{
 constructor(text){this.dataset=text?{text}:{};this.handlers=new Map();this.disabled=false;this.value='';this.textContent='';this.children=[];}
 addEventListener(type,handler){const list=this.handlers.get(type)||[];list.push(handler);this.handlers.set(type,list);}
 emit(type){return Promise.all((this.handlers.get(type)||[]).map(handler=>handler({type,target:this})));}
 append(child){this.children.push(child);}
 replaceChildren(...children){this.children=children;}
 click(){return this.emit('click');}
}
// Production uses the browser's standard Option constructor. Supply that DOM
// primitive in this explicitly labelled mock; no permission/controller test is skipped.
const originalOption=globalThis.Option;
globalThis.Option=class Option extends Element{
 constructor(text,value){super();this.textContent=text;this.value=value;this.selected=false;this.defaultSelected=false;}
};
test.after(()=>{if(originalOption===undefined)delete globalThis.Option;else globalThis.Option=originalOption;});
function mockDocument(){
 const elements=new Map(['language','status','connect','capture','disconnect','format','results'].map(id=>[id,new Element(['connect','capture','disconnect'].includes(id)?id:undefined)]));
 elements.get('format').value='PNG';const title=new Element('title');
 return {elements,querySelector:selector=>elements.get(selector.slice(1)),querySelectorAll:()=>[title,...elements.values()].filter(element=>element.dataset.text),createElement:()=>new Element()};
}
function fixture(options={}){
 const document=mockDocument(),state={language:options.language||'ko',granted:options.granted??false,allowRequest:true,connected:options.connected??false,tab:{id:12,windowId:7,url:'https://example.test/report'},...options};
 const calls=[],messages=[];
 const chrome={
  storage:{local:{async get(){return {language:state.language};},async set(value){Object.assign(state,value);}}},
  permissions:{async contains(value){calls.push({type:'contains',value});return state.granted;},async request(value){calls.push({type:'request',value});const allowed=await (state.onPermissionRequest?.()??state.allowRequest);state.granted=allowed;return allowed;}},
  tabs:{query(value){calls.push({type:'query',value});if(state.onQuery)return state.onQuery(value);return Promise.resolve([structuredClone(state.tab)]);}},
  runtime:{async sendMessage(message){messages.push(structuredClone(message));calls.push({type:'message',message:structuredClone(message)});if(state.onMessage)return state.onMessage(message);if(message.type==='status')return state.statusError?{errorCode:state.statusError}:{connected:state.connected};if(message.type==='connect'){state.connected=true;return {connected:true};}if(message.type==='disconnect'){state.connected=false;return {connected:false};}return state.captureError?{errorCode:state.captureError}:{job:{id:'test-job',status:'complete',result:{files:[]}}};}}
 };
 const agent={async request(path,options){calls.push({type:'api',path,options});return state.onRequest?.(path,options)||Response.json({job:{id:'test-job',status:'complete',result:{files:[]}}});}};
 const f={document,state,calls,messages,chrome,agent,ready:undefined,click:id=>document.elements.get(id).emit('click'),status:()=>document.elements.get('status').textContent};
 f.ready=mountPopup({document,chrome,agent,sleep:async()=>{}});return f;
}
const prompts=f=>f.calls.filter(call=>call.type==='request');
const messages=(f,type)=>f.messages.filter(message=>message.type===type);

test('opening the popup only reads permissions and status, never requests approval',async()=>{
 for(const connected of [false,true]){const f=fixture({connected});await f.ready;assert.equal(prompts(f).length,0);assert.equal(messages(f,'connect').length,0);assert.equal(f.status(),POPUP_WORDS.ko[connected?'browserPermissionRequired':'offline']);}
});

test('first Connect requests the persistent capture grant once, later clicks reuse it',async()=>{
 const f=fixture();await f.ready;
 for(let i=0;i<3;i++)await f.click('connect');
 assert.equal(prompts(f).length,1);assert.deepEqual(prompts(f)[0].value,{origins:['<all_urls>']});
 assert.equal(messages(f,'connect').length,3);assert.equal(f.status(),POPUP_WORDS.ko.connected);
 assert.equal(f.calls.filter(call=>call.type==='contains').length,3);
});

test('persisted Chrome permission is reused after popup restart',async()=>{
 const first=fixture();await first.ready;await first.click('connect');
 const reopened=fixture({granted:first.state.granted,connected:true});await reopened.ready;await reopened.click('connect');
 assert.equal(prompts(reopened).length,0);assert.equal(reopened.status(),POPUP_WORDS.ko.connected);
});

test('revoked permission causes no automatic prompt; explicit Connect requests it again',async()=>{
 const f=fixture();await f.ready;await f.click('connect');f.state.granted=false;f.state.captureError='browserPermissionRequired';
 await f.click('capture');assert.equal(prompts(f).length,1);assert.equal(f.status(),POPUP_WORDS.ko.browserPermissionRequired);
 await f.click('connect');assert.equal(prompts(f).length,2);assert.equal(f.status(),POPUP_WORDS.ko.connected);
});

test('denied host access does not start native pairing',async()=>{
 const f=fixture({allowRequest:false});await f.ready;await f.click('connect');
 assert.equal(prompts(f).length,1);assert.equal(messages(f,'connect').length,0);assert.equal(f.status(),POPUP_WORDS.ko.browserPermissionRequired);
 for(const id of ['connect','capture','disconnect','format'])assert.equal(f.document.elements.get(id).disabled,false);
});

test('busy controls and the click guard prevent duplicate permission/native requests',async()=>{
 let release;const permission=new Promise(resolve=>{release=resolve;});const f=fixture({onPermissionRequest:()=>permission});await f.ready;
 const first=f.click('connect');for(const id of ['connect','capture','disconnect','format'])assert.equal(f.document.elements.get(id).disabled,true);
 await f.click('connect');await f.click('capture');await f.click('disconnect');release(true);await first;
 assert.equal(prompts(f).length,1);assert.equal(messages(f,'connect').length,1);assert.equal(messages(f,'capture').length,0);assert.equal(messages(f,'disconnect').length,0);
});

test('capture binds the active page at click before awaiting reconnect readiness',async()=>{
 let release;const ready=new Promise(resolve=>{release=resolve;});const f=fixture({granted:true,onMessage:message=>message.type==='status'?{connected:true}:ready});await f.ready;
 const first=f.click('capture');const query=f.calls.at(-1);assert.equal(query.type,'query');assert.deepEqual(query.value,{active:true,lastFocusedWindow:true});
 await Promise.resolve();f.state.tab={id:99,windowId:9,url:'https://other.test/'};await f.click('capture');
 const capture=messages(f,'capture');assert.equal(capture.length,1);assert.deepEqual(capture[0],{type:'capture',format:'png',target:{id:12,windowId:7,url:'https://example.test/report'}});
 release({job:{id:'test-job',status:'complete',result:{files:[]}}});await first;assert.equal(f.status(),POPUP_WORDS.ko.done);
});

test('unsupported or missing tabs fail before sending any capture command',async()=>{
 for(const tab of [{id:1,windowId:2,url:'chrome://settings/'},{id:1,windowId:2,url:'edge://extensions/'},{id:1,windowId:2,url:'file:///private/file.pdf'},{id:-1,windowId:2,url:'https://example.test/'},{id:1,url:'https://example.test/'},{}]){
  const f=fixture({tab});await f.ready;await f.click('capture');assert.equal(messages(f,'capture').length,0);assert.equal(f.status(),POPUP_WORDS.ko.unsupportedPage);assert.equal(prompts(f).length,0);
 }
});

test('all six languages cover every visible string and actionable capture error',async()=>{
 assert.deepEqual(Object.keys(POPUP_WORDS),['ko','en','vi','ja','zh','zh-TW']);const keys=Object.keys(POPUP_WORDS.ko).sort();
 for(const [language,words]of Object.entries(POPUP_WORDS)){
  assert.deepEqual(Object.keys(words).sort(),keys);for(const value of Object.values(words))assert.ok(typeof value==='string'&&value.trim());
  for(const errorCode of ['unsupportedPage','tabChanged','browserPermissionRequired','browserRequired','agentUnavailable','pairingRequired']){const f=fixture({language,captureError:errorCode});await f.ready;await f.click('capture');assert.equal(f.status(),words[errorCode]);}
 }
});

test('ready-status failures are translated and never trigger permissions automatically',async()=>{
 const f=fixture({language:'en',statusError:'browserPermissionRequired'});await f.ready;
 assert.equal(f.status(),POPUP_WORDS.en.browserPermissionRequired);assert.equal(prompts(f).length,0);
});

test('Connect is not reported as successful until the worker confirms readiness',async()=>{
 const f=fixture({granted:true,onMessage:()=>({connected:false})});await f.ready;await f.click('connect');
 assert.equal(f.status(),POPUP_WORDS.ko.browserRequired);assert.equal(prompts(f).length,0);
});

test('queued capture failure preserves the agent error code instead of hiding the remedy',async()=>{
 const f=fixture({onMessage:message=>message.type==='capture'?{job:{id:'test-job',status:'queued'}}:{connected:false},onRequest:()=>Response.json({job:{id:'test-job',status:'failed',errorCode:'tabChanged'}})});
 await f.ready;await f.click('capture');assert.equal(f.status(),POPUP_WORDS.ko.tabChanged);
 assert.equal(f.calls.find(call=>call.type==='api').path,'/jobs/test-job');
});

test('unrecognized errors are not printed in the popup',async()=>{
 const f=fixture({captureError:'private_path_or_token_should_not_be_visible'});await f.ready;await f.click('capture');
 assert.equal(f.status(),POPUP_WORDS.ko.failed);assert.ok(!f.status().includes('private_path'));
});

test('slow initial status cannot overwrite a completed capture',async()=>{
 let release;const initial=new Promise(resolve=>{release=resolve;});const f=fixture({onMessage:message=>message.type==='status'?initial:{job:{id:'test-job',status:'complete',result:{files:[]}}}});
 await Promise.resolve();await f.click('capture');assert.equal(f.status(),POPUP_WORDS.ko.done);release({connected:false});await f.ready;assert.equal(f.status(),POPUP_WORDS.ko.done);
});

test('disconnect keeps browser host access; only pairing is disconnected',async()=>{
 const f=fixture({granted:true,connected:true});await f.ready;await f.click('disconnect');await f.click('connect');
 assert.equal(prompts(f).length,0);assert.equal(f.state.granted,true);assert.equal(messages(f,'disconnect').length,1);
});

test('manifest declares the matching optional permission and update version without widening required hosts',async()=>{
 const manifest=JSON.parse(await readFile(new URL('./manifest.json',import.meta.url),'utf8'));
 assert.equal(manifest.version,'4.6.23');assert.deepEqual(manifest.optional_host_permissions,CAPTURE_PERMISSIONS.origins);
 assert.ok(manifest.host_permissions.every(origin=>/^http:\/\/127\.0\.0\.1:(4323|4324|4325|4321)\/\*$/.test(origin)));
 assert.deepEqual(manifest.permissions,['activeTab','scripting','storage','alarms']);
 const build=await readFile(new URL('./build_manifest.py',import.meta.url),'utf8');assert.ok(build.includes("'version':'4.6.23'"));assert.ok(build.includes("'optional_host_permissions':['<all_urls>']"));
});

test('regenerating distributed manifest without a private key preserves the public key and extension ID',async()=>{
 const root=await mkdtemp(join(tmpdir(),'galaxy-extension-manifest-test-'));
 try{
  const extension=join(root,'browser-extension'),agent=join(root,'agent');await mkdir(extension);await mkdir(agent);
  await copyFile(new URL('./build_manifest.py',import.meta.url),join(extension,'build_manifest.py'));await copyFile(new URL('./manifest.json',import.meta.url),join(extension,'manifest.json'));await copyFile(new URL('../agent/extension-origin.json',import.meta.url),join(agent,'extension-origin.json'));
  const before=JSON.parse(await readFile(join(extension,'manifest.json'),'utf8')),originBefore=JSON.parse(await readFile(join(agent,'extension-origin.json'),'utf8'));
  const {stdout}=await promisify(execFile)((process.env.PYTHON || (process.platform==='win32'?'python':'python3')),[join(extension,'build_manifest.py')]);
  const after=JSON.parse(await readFile(join(extension,'manifest.json'),'utf8')),originAfter=JSON.parse(await readFile(join(agent,'extension-origin.json'),'utf8'));
  assert.equal(after.key,before.key);assert.deepEqual(after.icons,before.icons);assert.deepEqual(after.action.default_icon,before.action.default_icon);assert.deepEqual(originAfter,originBefore);assert.equal(stdout.trim(),originBefore.extensionId);assert.equal(after.version,'4.6.23');
  await assert.rejects(access(join(extension,'build-private-key.pem')));
 }finally{await rm(root,{recursive:true,force:true});}
});

test('invalid or mismatched public identity fails without generating a replacement key or changing files',async()=>{
 const root=await mkdtemp(join(tmpdir(),'galaxy-extension-manifest-test-'));
 try{
  const extension=join(root,'browser-extension'),agent=join(root,'agent');await mkdir(extension);await mkdir(agent);
  await copyFile(new URL('./build_manifest.py',import.meta.url),join(extension,'build_manifest.py'));
  const manifest=JSON.parse(await readFile(new URL('./manifest.json',import.meta.url),'utf8')),origin=JSON.parse(await readFile(new URL('../agent/extension-origin.json',import.meta.url),'utf8'));
  for(const [nextManifest,nextOrigin]of [[{...manifest,key:'not-valid-base64!!'},origin],[{...manifest,key:'AAAA'},origin],[manifest,{extensionId:'a'.repeat(32),origin:'chrome-extension://'+'a'.repeat(32)}]]){
   const manifestBytes=JSON.stringify(nextManifest),originBytes=JSON.stringify(nextOrigin);await writeFile(join(extension,'manifest.json'),manifestBytes);await writeFile(join(agent,'extension-origin.json'),originBytes);
   await assert.rejects(promisify(execFile)((process.env.PYTHON || (process.platform==='win32'?'python':'python3')),[join(extension,'build_manifest.py')]));
   assert.equal(await readFile(join(extension,'manifest.json'),'utf8'),manifestBytes);assert.equal(await readFile(join(agent,'extension-origin.json'),'utf8'),originBytes);await assert.rejects(access(join(extension,'build-private-key.pem')));
  }
 }finally{await rm(root,{recursive:true,force:true});}
});
