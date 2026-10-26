// Isolated mocks only: no installed browser, real tab, network, or browser storage.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createBrowserController,checkedCaptureUrl,openCaptureUrl} from '../browser-extension/background.js';
import {planPositions,supportedPage,pageOperation,captureCss} from '../browser-extension/capture-core.js';
const results=[];
async function test(name,fn){try{await fn();results.push({name,passed:true});console.log('PASS '+name);}catch(error){results.push({name,passed:false,error:error.message});console.error('FAIL '+name+': '+error.message);}}
await test('two-axis overlap plan covers right and bottom edges',()=>{
 assert.deepEqual(planPositions(2500,2300,1000,1000),[{x:0,y:0},{x:1000,y:0},{x:1500,y:0},{x:0,y:1000},{x:1000,y:1000},{x:1500,y:1000},{x:0,y:1300},{x:1000,y:1300},{x:1500,y:1300}]);
 assert.deepEqual(planPositions(800,600,1000,1000),[{x:0,y:0}]);
});
await test('huge page rejected before allocating axis arrays',()=>{
 const push=Array.prototype.push;let calls=0;
 Array.prototype.push=function(...items){if(++calls>250)throw Error('axis allocation exceeded tile budget');return push.apply(this,items);};
 try{assert.throws(()=>planPositions(2147483647,2147483647,1,1),/fileTooLarge/);assert.equal(calls,0);}finally{Array.prototype.push=push;}
 assert.throws(()=>planPositions(Infinity,100,10,10),/invalidRequest/);assert.throws(()=>planPositions(100,100,10,10,0),/invalidRequest/);
});
await test('restricted protocols are excluded',()=>{assert.equal(supportedPage('https://example.com/'),true);for(const url of ['chrome://settings','edge://settings','file:///private/file','data:text/plain,secret','javascript:alert(1)'])assert.equal(supportedPage(url),false);});
await test('URL capture validates addresses without stripping login sessions or adding grants',async()=>{
 assert.equal(checkedCaptureUrl(' https://example.com/report?q=one#two '),'https://example.com/report?q=one#two');
 for(const url of ['file:///secret','javascript:alert(1)','https://user:password@example.com','not a URL'])assert.throws(()=>checkedCaptureUrl(url));
 const calls=[],api={permissions:{contains:async({origins})=>{calls.push({permission:origins});return true;}},tabs:{create:async options=>{calls.push({create:options});return {id:55,windowId:2};},get:async()=>({id:55,windowId:2,status:'complete',url:'https://example.com/report?session=existing'})}};
 const tab=await openCaptureUrl(api,'https://example.com/report',async()=>{});assert.equal(tab.url,'https://example.com/report?session=existing');assert.deepEqual(calls.find(x=>x.create).create,{url:'https://example.com/report',active:true});assert.equal(calls.filter(x=>x.permission).length,2);
});
await test('URL capture never creates a tab for ungranted private host or captures ungranted redirect',async()=>{
 let created=0;const api={permissions:{contains:async({origins})=>!origins[0].includes('127.0.0.1')},tabs:{create:async()=>{created++;return {id:55,windowId:2};},get:async()=>({id:55,windowId:2,status:'complete',url:'http://127.0.0.1/private'})}};
 await assert.rejects(openCaptureUrl(api,'http://127.0.0.1/private',async()=>{}),/browserPermissionRequired/);assert.equal(created,0);
 await assert.rejects(openCaptureUrl(api,'https://example.com/report',async()=>{}),/browserPermissionRequired/);assert.equal(created,1);
});
await test('URL capture waits for loading and bounds an unfinished navigation',async()=>{
 let get=0;const sleeps=[],api={permissions:{contains:async()=>true},tabs:{create:async()=>({id:55,windowId:2}),get:async()=>({id:55,windowId:2,status:++get===3?'complete':'loading',url:'https://example.com/report'})}};
 assert.equal((await openCaptureUrl(api,'https://example.com/report',async ms=>sleeps.push(ms))).id,55);assert.deepEqual(sleeps,[200,200]);
 api.tabs.get=async()=>({id:55,windowId:2,status:'loading'});await assert.rejects(openCaptureUrl(api,'https://example.com/report',async()=>{},2),/pageLoadTimeout/);
});
await test('page fixed/sticky styles and scroll restore after capture',async()=>{
 const names=['window','document','innerWidth','innerHeight','devicePixelRatio','scrollX','scrollY','scrollTo','getComputedStyle','requestAnimationFrame','setTimeout'];const old=Object.fromEntries(names.map(name=>[name,{exists:name in globalThis,value:globalThis[name]}]));
 const fixed={position:'fixed',style:{visibility:'visible'}},sticky={position:'sticky',style:{visibility:''}},normal={position:'static',style:{visibility:'collapse'}};
 Object.assign(globalThis,{window:{},document:{documentElement:{scrollWidth:1500,scrollHeight:2200,style:{scrollBehavior:'smooth'}},body:{scrollWidth:1400,scrollHeight:2100},querySelectorAll:()=>[fixed,sticky,normal]},innerWidth:1000,innerHeight:800,devicePixelRatio:2,scrollX:77,scrollY:155,scrollTo(x,y){if(typeof x==='object'){y=x.top;x=x.left;}globalThis.scrollX=Math.max(0,Math.min(500,x));globalThis.scrollY=Math.max(0,Math.min(1400,y));},getComputedStyle:element=>({position:element.position}),requestAnimationFrame:fn=>queueMicrotask(fn),setTimeout:fn=>{queueMicrotask(fn);return 0;}});
 try{const meta=await pageOperation('begin');assert.equal(meta.dpr,2);assert.equal(meta.height,2200);await assert.rejects(()=>pageOperation('begin'),/busy/);await pageOperation('scroll',{x:500,y:1400,first:false});assert.equal(fixed.style.visibility,'hidden');assert.equal(sticky.style.visibility,'hidden');assert.equal(normal.style.visibility,'collapse');await pageOperation('restore');assert.equal(scrollX,77);assert.equal(scrollY,155);assert.equal(document.documentElement.style.scrollBehavior,'smooth');assert.equal(fixed.style.visibility,'visible');assert.equal(sticky.style.visibility,'');assert.equal(window.__ADMIN_CAPTURE_STATE__,undefined);await pageOperation('begin');await pageOperation('restore');}finally{for(const name of names){if(old[name].exists)globalThis[name]=old[name].value;else delete globalThis[name];}}
});
const tick=()=>new Promise(resolve=>setTimeout(resolve,1));
async function until(predicate){for(let i=0;i<1000;i++){if(predicate())return;await tick();}throw Error('fixture timed out');}
function fixture({autoReady=true,paired=true,permission=true,switchAt='',throwCapture=false,meta={width:100,height:100,viewportWidth:100,viewportHeight:100,dpr:1},timeout=1000}={}){
 const f={operations:[],requests:[],results:[],uploads:[],sleepMs:[],created:[],captures:0,pairCalls:0,streams:[],active:{id:10,windowId:2,url:'https://example.com/a'},paired,permission,throwCapture,next:0,revision:1,css:[],cssPresent:false,position:{x:0,y:0}};
 const emit=(event,stream=f.streams.at(-1))=>stream.controller.enqueue(new TextEncoder().encode('event: '+event.type+'\r\ndata: '+JSON.stringify(event)+'\r\n\r\n'));
 f.emit=emit;
 const chromeApi={
  permissions:{contains:async()=>f.permission},
  tabs:{query:async()=>[{...f.active}],create:async options=>{f.created.push(options);f.active={id:70,windowId:2,url:options.url,status:'complete'};return {...f.active};},get:async id=>({...f.active,id}),captureVisibleTab:async()=>{
   f.captures++;assert.equal(f.cssPresent,true,'scrollbars must be hidden before each visible capture');if(f.throwCapture){f.throwCapture=false;throw Error('fixture capture failure');}
   if(switchAt==='capture')f.active={...f.active,id:11,url:'https://example.com/b'};
   return 'data:image/png;base64,AA==';
  }},
  scripting:{insertCSS:async options=>{assert.equal(options.css,captureCss);assert.equal(options.origin,'USER');f.css.push('insert');f.cssPresent=true;if(f.throwCss)throw Error('fixture CSS failure');},removeCSS:async options=>{assert.equal(options.css,captureCss);assert.equal(options.origin,'USER');f.css.push('remove');f.cssPresent=false;},executeScript:async({target,args})=>{
   const [op,position]=args;f.operations.push({op,tabId:target.tabId,position});
   if(op==='scroll'&&switchAt==='scroll')f.active={...f.active,id:11,url:'https://example.com/b'};
   if(op==='scroll')f.position={x:position.x,y:position.y};
   if(op==='restore')assert.equal(f.cssPresent,false,'remove temporary CSS before restoring the original scroll position');
   return [{result:['begin','measure'].includes(op)?meta:['scroll','position'].includes(op)?{...f.position,viewportWidth:meta.viewportWidth+(op==='position'&&f.resize?5:0),viewportHeight:meta.viewportHeight,dpr:meta.dpr}:undefined}];
  }}
 };
 const agent={
  isPaired:async()=>f.paired,status:async()=>({connected:f.paired}),approvalRevision:async()=>f.revision,
  pair:async()=>{f.pairCalls++;if(!f.paired)f.revision++;f.paired=true;},clear:async()=>{f.paired=false;f.revision++;},
  request:async(path,options={})=>{
   const body=typeof options.body==='string'?JSON.parse(options.body):undefined;
   f.requests.push({path,body});
   if(path==='/events'){
    const entry={};const stream=new ReadableStream({start(controller){entry.controller=controller;},cancel(){entry.cancelled=true;}});
    f.streams.push(entry);
    options.signal?.addEventListener('abort',()=>{entry.aborted=true;try{entry.controller.close();}catch{}},{once:true});
    if(autoReady)emit({type:'ready'},entry);
    return new Response(stream,{headers:{'Content-Type':'text/event-stream'}});
   }
   if(path==='/browser/capture'){
    const id='job-'+(++f.next);emit({type:'browserCapture',command:{id,options:body}});
    return Response.json({job:{id,status:'queued'}});
   }
   if(path==='/uploads'){const id='tile-'+(f.uploads.length+1);f.uploads.push({id,blob:options.body});return Response.json({id});}
   if(path==='/browser/result'){f.results.push(body);return Response.json({received:true});}
   return Response.json({ok:true});
  }
 };
 const build=()=>createBrowserController({chromeApi,agent,sleep:async ms=>{f.sleepMs.push(ms);},fetchFn:async()=>new Response(new Uint8Array([0])),requestId:()=>('request-'+(f.next+1)),streamTimeoutMs:timeout});
 f.controller=build();f.restart=()=>{f.controller.stop();f.controller=build();};f.close=()=>f.controller.stop();return f;
}
await test('cold worker waits for SSE ready before posting capture; completes tiles and restores',async()=>{
 const f=fixture({autoReady:false});try{
  const pending=f.controller.requestCapture();await until(()=>f.streams.length===1);
  assert.equal(f.requests.filter(x=>x.path==='/browser/capture').length,0);
  f.emit({type:'ready'});const submitted=await pending;assert.equal(submitted.job.status,'queued');
  await until(()=>f.operations.at(-1)?.op==='restore');
  assert.equal(f.captures,1);assert.equal(f.results.length,1);assert.equal(f.results[0].tiles.length,1);
  assert.ok(f.sleepMs.every(ms=>ms>=500));assert.equal(f.pairCalls,0);
 }finally{f.close();}
});
await test('owner URL command opens a visible tab and captures only that tab while preserving pairing',async()=>{
 const f=fixture();try{
  await f.controller.start();f.emit({type:'browserCapture',command:{id:'url-job',options:{url:'https://example.com/report',format:'pdf'}}});
  await until(()=>f.operations.at(-1)?.op==='restore');assert.equal(f.created.length,1);assert.equal(f.created[0].active,true);assert.equal(f.active.id,70);assert.ok(f.operations.every(x=>x.tabId===70));assert.equal(f.results[0].tiles.length,1);assert.equal(f.pairCalls,0);
 }finally{f.close();}
});
await test('repeated connect clicks retain one receiver and do not rotate a ready stream',async()=>{
 const f=fixture();try{
  await Promise.all([f.controller.connect(),f.controller.connect()]);await f.controller.connect();
  assert.equal(f.streams.length,1);assert.equal(f.requests.filter(x=>x.path==='/browser/register').length,1);
  assert.deepEqual(await f.controller.status(),{connected:true});
 }finally{f.close();}
});
await test('renewed approval replaces an old ready stream without using its buffered commands',async()=>{
 const f=fixture();try{
  await f.controller.start();f.paired=false;
  await f.controller.connect();assert.equal(f.streams.length,2);assert.equal(f.streams[0].aborted,true);
  await f.controller.requestCapture();await until(()=>f.operations.at(-1)?.op==='restore');assert.equal(f.captures,1);
 }finally{f.close();}
});
await test('failed authenticated status closes an old ready stream',async()=>{
 const f=fixture();try{
  await f.controller.start();f.paired=false;
  assert.deepEqual(await f.controller.status(),{connected:false});await tick();assert.equal(f.streams[0].aborted,true);
  assert.equal(f.pairCalls,0);assert.equal(f.captures,0);
 }finally{f.close();}
});
await test('tab switch during scroll settling aborts before screenshot/upload and restores',async()=>{
 const f=fixture({switchAt:'scroll'});try{
  await f.controller.requestCapture();await until(()=>f.operations.at(-1)?.op==='restore');
  assert.equal(f.captures,0);assert.equal(f.uploads.length,0);assert.equal(f.results[0].errorCode,'tabChanged');
 }finally{f.close();}
});
await test('tab switch during screenshot promise discards screenshot and restores',async()=>{
 const f=fixture({switchAt:'capture'});try{
  await f.controller.requestCapture();await until(()=>f.operations.at(-1)?.op==='restore');
  assert.equal(f.captures,1);assert.equal(f.uploads.length,0);assert.equal(f.results[0].errorCode,'tabChanged');
 }finally{f.close();}
});
await test('failed capture restores original page and permits a successful retry',async()=>{
 const f=fixture({throwCapture:true});try{
  await f.controller.requestCapture();await until(()=>f.operations.filter(x=>x.op==='restore').length===1);
  assert.equal(f.results[0].errorCode,'browserPermissionRequired');
  await f.controller.requestCapture();await until(()=>f.operations.filter(x=>x.op==='restore').length===2);
  assert.equal(f.captures,2);assert.equal(f.results[1].tiles.length,1);
 }finally{f.close();}
});
await test('a tab switch while the stream is opening never submits a different current tab',async()=>{
 const f=fixture({autoReady:false});try{
  const pending=f.controller.requestCapture();const rejected=assert.rejects(pending,/tabChanged/);
  await until(()=>f.streams.length===1);f.active={...f.active,id:12,url:'https://example.com/private'};f.emit({type:'ready'});
  await rejected;assert.equal(f.requests.filter(x=>x.path==='/browser/capture').length,0);assert.equal(f.captures,0);
 }finally{f.close();}
});
await test('replayed command is deduplicated before and after stream reconnect',async()=>{
 const f=fixture();try{
  const r=await f.controller.requestCapture();const options=f.requests.find(x=>x.path==='/browser/capture').body;
  f.emit({type:'browserCapture',command:{id:r.job.id,options}});
  await until(()=>f.operations.at(-1)?.op==='restore');assert.equal(f.captures,1);
  f.streams[0].controller.close();await tick();await tick();await f.controller.start();
  f.emit({type:'browserCapture',command:{id:r.job.id,options}});await tick();await tick();
  assert.equal(f.streams.length,2);assert.equal(f.captures,1);assert.equal(f.results.length,1);assert.equal(f.pairCalls,0);
 }finally{f.close();}
});
await test('worker restart replays the originally requested tab and rejects a newly active tab',async()=>{
 const f=fixture();try{
  await f.controller.start();f.restart();await f.controller.start();
  f.active={...f.active,id:90,url:'https://example.com/other'};
  f.emit({type:'browserCapture',command:{id:'pending-fixture',options:{captureRequestId:'prior-request',captureTarget:{id:10,windowId:2,url:'https://example.com/a'}}}});
  await until(()=>f.results.length===1);assert.equal(f.results[0].errorCode,'tabChanged');assert.equal(f.captures,0);assert.equal(f.operations.length,0);
 }finally{f.close();}
});
await test('missing browser permission fails immediately without capture, pairing or prompting',async()=>{
 const f=fixture({permission:false});try{
  await assert.rejects(f.controller.requestCapture(),/browserPermissionRequired/);
  assert.equal(f.pairCalls,0);assert.equal(f.requests.length,0);assert.equal(f.captures,0);
 }finally{f.close();}
});
await test('unpaired startup does not open native approval automatically',async()=>{
 const f=fixture({paired:false});try{
  await assert.rejects(f.controller.start(),/pairingRequired/);assert.equal(f.pairCalls,0);assert.equal(f.requests.length,0);
 }finally{f.close();}
});
await test('missing ready event fails promptly without queued job and reconnect can recover',async()=>{
 const f=fixture({autoReady:false,timeout:20});try{
  await assert.rejects(f.controller.requestCapture(),/browserRequired/);
  assert.equal(f.requests.filter(x=>x.path==='/browser/capture').length,0);
  const pending=f.controller.start();await until(()=>f.streams.length===2);f.emit({type:'ready'});
  assert.deepEqual(await pending,{connected:true});
 }finally{f.close();}
});
await test('all tiles of a two-axis page include final overlapping edges and requested format',async()=>{
 const f=fixture({meta:{width:150,height:230,viewportWidth:100,viewportHeight:100,dpr:2}});try{
  await f.controller.requestCapture({format:'pdf'});await until(()=>f.operations.at(-1)?.op==='restore');
  assert.equal(f.captures,6);assert.deepEqual(f.results[0].tiles.map(({x,y})=>({x,y})),planPositions(150,230,100,100));
  assert.equal(f.results[0].dpr,2);assert.equal(f.requests.find(x=>x.path==='/browser/capture').body.format,'pdf');
 }finally{f.close();}
});
await test('scrollbar CSS is removed on success, capture failure and insertion failure',async()=>{
 for(const failure of ['none','capture','css']){
  const f=fixture({throwCapture:failure==='capture'});f.throwCss=failure==='css';try{
   await f.controller.requestCapture();await until(()=>f.operations.at(-1)?.op==='restore');
   assert.deepEqual(f.css,['insert','remove']);assert.equal(f.cssPresent,false);
   assert.equal(Boolean(f.results[0].errorCode),failure!=='none');
  }finally{f.close();}
 }
});
await test('viewport resize rejects the capture instead of stitching mismatched browser tiles',async()=>{
 const f=fixture();f.resize=true;try{
  await f.controller.requestCapture();await until(()=>f.operations.at(-1)?.op==='restore');
  assert.equal(f.captures,0);assert.equal(f.results[0].errorCode,'tabChanged');assert.deepEqual(f.css,['insert','remove']);
 }finally{f.close();}
});
await test('stopped buffered stream cannot capture or interfere with a newer session',async()=>{
 const f=fixture();try{
  await f.controller.start();
  f.emit({type:'browserCapture',command:{id:'stale-command',options:{}}});f.controller.stop();
  await f.controller.start();await tick();await tick();
  assert.equal(f.captures,0);assert.equal(f.uploads.length,0);assert.equal(f.results.length,0);
  await f.controller.requestCapture();await until(()=>f.operations.at(-1)?.op==='restore');assert.equal(f.captures,1);
 }finally{f.close();}
});
await test('fragmented CRLF SSE frames resolve readiness and preserve capture commands',async()=>{
 const f=fixture({autoReady:false});try{
  const pending=f.controller.start();await until(()=>f.streams.length===1);
  const c=f.streams[0].controller;
  for(const byte of new TextEncoder().encode('event: ready\r\ndata: {"type":"ready","fixture":"준비됨"}\r\n\r\n'))c.enqueue(new Uint8Array([byte]));
  await pending;await f.controller.requestCapture();await until(()=>f.operations.at(-1)?.op==='restore');assert.equal(f.results[0].tiles.length,1);
 }finally{f.close();}
});
mkdirSync(new URL('../integration-analysis/',import.meta.url),{recursive:true});
writeFileSync(new URL('../integration-analysis/browser-extension-tests.json',import.meta.url),JSON.stringify({total:results.length,passed:results.filter(x=>x.passed).length,fixture:'Isolated Chrome API mocks; not a physical Windows/browser test',results},null,2)+'\n');if(results.some(x=>!x.passed))process.exitCode=1;
