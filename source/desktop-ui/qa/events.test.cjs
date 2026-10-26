const test = require('node:test');
const assert = require('node:assert/strict');
const load = require('./load-source.cjs');
const {toolCategories} = load('features/local-tools/catalog.ts');
const {desktopNavigation, desktopShortcut, bindDesktopEvents, bindDesktopKeyboardShortcuts, createDesktopShortcutDispatcher,
  notifyDesktopCapture, notifyDesktopDriveConnected, finishDesktopCaptureSession, completeDesktopCaptureSession, copyDesktopText} = load('features/local-tools/desktop-events.ts');
const detailEvent = (name, detail) => new CustomEvent(name, {detail});
const deferred = () => { let resolve, reject; const promise = new Promise((yes,no) => {resolve=yes; reject=no;}); return {promise,resolve,reject}; };

test('Drive return-to-app message carries no credentials and supports both native hosts', () => {
  for (const platform of ['windows','mac']) {
    const sent=[],native={postMessage:message=>sent.push(message)};
    const target=platform==='windows'?{chrome:{webview:native}}:{webkit:{messageHandlers:{galaxycontrol:native}}};
    assert.equal(notifyDesktopDriveConnected(target),true);
    assert.deepEqual(sent,[{action:'driveConnected'}]);
  }
  assert.equal(notifyDesktopDriveConnected({}),false);
  assert.equal(notifyDesktopDriveConnected({chrome:{webview:{postMessage(){throw Error('closed');}}}}),false);
});

test('native menu messages accept only existing tool names and known shortcuts', () => {
  for (const category of ['home','settings',...toolCategories]) assert.equal(desktopNavigation({category}),category);
  for (const category of ['https://example.com','__proto__','ADMIN','']) assert.equal(desktopNavigation({category}),null);
  for (const detail of [null,undefined,[],true,'capture',{}]) {assert.equal(desktopNavigation(detail),null); assert.equal(desktopShortcut(detail),null);}
  for (const name of ['areaCapture','fullCapture','webCapture','toggleRecording']) assert.equal(desktopShortcut({name}),name);
  assert.equal(desktopShortcut({name:'recordToggle'}),'toggleRecording');
  assert.equal(desktopShortcut({name:'executeJavaScript'}),null);
});

test('native event listeners deliver validated data once and are removed on cleanup', () => {
  const target = new EventTarget(), seen=[];
  const unbind = bindDesktopEvents(target,{navigate:value=>seen.push(value),shortcut:value=>seen.push(value)});
  target.dispatchEvent(detailEvent('galaxycontrol:navigate',{category:'pdf'}));
  target.dispatchEvent(detailEvent('galaxycontrol:navigate',{category:'https://example.com'}));
  target.dispatchEvent(detailEvent('galaxycontrol:shortcut',{name:'recordToggle'}));
  unbind(); unbind();
  target.dispatchEvent(detailEvent('galaxycontrol:shortcut',{name:'areaCapture'}));
  assert.deepEqual(seen,['pdf','toggleRecording']);
});

test('repeated capture shortcuts coalesce during execution and within the debounce interval', async () => {
  let now=1000,busy=false,starts=0; const ignored=[],pending=deferred();
  const dispatcher=createDesktopShortcutDispatcher({now:()=>now,isBusy:()=>busy,run:async()=>{starts++;await pending.promise;},onIgnored:name=>ignored.push(name)});
  busy=true; assert.equal(await dispatcher.dispatch('areaCapture'),false); busy=false;
  const first=dispatcher.dispatch('areaCapture');
  assert.equal(await dispatcher.dispatch('fullCapture'),false); assert.equal(starts,1);
  pending.resolve(); assert.equal(await first,true);
  now=1399; assert.equal(await dispatcher.dispatch('areaCapture'),false);
  now=1400; assert.equal(await dispatcher.dispatch('fullCapture'),true); assert.equal(starts,2);
  assert.deepEqual(ignored,['areaCapture','fullCapture','areaCapture']);
});

test('shortcut failure releases the execution lock so retry can work', async () => {
  let now=0,calls=0;
  const dispatcher=createDesktopShortcutDispatcher({now:()=>now,isBusy:()=>false,run:async()=>{if(++calls===1)throw Error('permissionRequired');}});
  await assert.rejects(dispatcher.dispatch('fullCapture'),/permissionRequired/);
  now=400; assert.equal(await dispatcher.dispatch('fullCapture'),true); assert.equal(calls,2);
});

test('capture lifecycle sends data-only native actions and closes each session once', () => {
  for (const os of ['mac','windows']) {
    const sent=[],native={postMessage:value=>sent.push(value)},target=os==='mac'?{webkit:{messageHandlers:{galaxycontrol:native}}}:{chrome:{webview:native}};
    assert.equal(notifyDesktopCapture('captureStarted',target),true);
    assert.deepEqual(sent,[{action:'captureStarted'}]);
  }
  assert.equal(notifyDesktopCapture('captureClosed',{}),false);
  assert.equal(notifyDesktopCapture('captureClosed',{chrome:{webview:{postMessage(){throw Error('host closed');}}}}),false);
  const session={current:true},seen=[];
  assert.equal(completeDesktopCaptureSession(session,true,()=>seen.push('editor'),action=>{seen.push(action);return true;}),true);
  assert.equal(session.current,true);
  assert.equal(finishDesktopCaptureSession(session,'captureClosed',action=>{seen.push(action);return true;}),true);
  assert.equal(finishDesktopCaptureSession(session,'captureClosed',()=>{throw Error('duplicate close');}),false);
  assert.equal(completeDesktopCaptureSession(session,true,()=>{throw Error('late editor');}),false);
  assert.deepEqual(seen,['editor','captureReady','captureClosed']);
});

test('native text copy waits for its matching clipboard receipt and ignores foreign events', async () => {
  const target=new EventTarget(); let message;
  target.webkit={messageHandlers:{galaxycontrol:{postMessage:value=>message=value}}};
  let settled=false; const copying=copyDesktopText('fixture text',target,1000).then(()=>settled=true);
  assert.equal(message.action,'copyText'); assert.equal(message.text,'fixture text'); assert.match(message.requestId,/^[\da-f-]{36}$/i);
  target.dispatchEvent(detailEvent('galaxycontrol:clipboard-result',{requestId:'another request',copied:true}));
  await Promise.resolve(); assert.equal(settled,false);
  target.dispatchEvent(detailEvent('galaxycontrol:clipboard-result',{requestId:message.requestId,copied:true}));
  await copying; assert.equal(settled,true);
});

for (const copied of [false,undefined,'true',1]) test(`native text copy cannot succeed with copied=${String(copied)}`, async () => {
  const target=new EventTarget(); let message;
  target.chrome={webview:{postMessage:value=>message=value}};
  const copying=copyDesktopText('fixture text',target,1000);
  target.dispatchEvent(detailEvent('galaxycontrol:clipboard-result',{requestId:message.requestId,copied}));
  await assert.rejects(copying,/processingFailed/);
});

test('native text copy rejects invalid input, missing host, and timed out clipboard receipts', async () => {
  let calls=0; const target=new EventTarget(); target.chrome={webview:{postMessage(){calls++;}}};
  await assert.rejects(copyDesktopText('x'.repeat(12001),target),/invalidRequest/);
  await assert.rejects(copyDesktopText(null,target),/invalidRequest/); assert.equal(calls,0);
  await assert.rejects(copyDesktopText('fixture text',new EventTarget()),/nativeUnavailable/);
  await assert.rejects(copyDesktopText('fixture text',target,10),/processingFailed/);
});


const keyEvent = (values={}) => {
  const event=new Event('keydown',{cancelable:true});
  for(const [key,value] of Object.entries({key:'a',code:'KeyA',ctrlKey:false,metaKey:false,altKey:false,shiftKey:false,repeat:false,...values})) Object.defineProperty(event,key,{value});
  return event;
};

test('foreground configured shortcut works in Latin and Korean IME input and unbinds cleanly',()=>{
 const target=new EventTarget(),seen=[];
 const unbind=bindDesktopKeyboardShortcuts(target,()=>({areaCapture:'Control+Shift+A'}),name=>seen.push(name));
 for(const key of ['a','A','ㅁ','Process']){
  const event=keyEvent({key,code:'KeyA',ctrlKey:true,shiftKey:true});target.dispatchEvent(event);assert.equal(event.defaultPrevented,true);
 }
 unbind();unbind();target.dispatchEvent(keyEvent({ctrlKey:true,shiftKey:true}));
 assert.deepEqual(seen,Array(4).fill('areaCapture'));
});

test('foreground shortcut reads current configuration and maps recording alias with shifted digit keys',()=>{
 const target=new EventTarget(),seen=[];let settings={areaCapture:'Control+Shift+A'};
 const unbind=bindDesktopKeyboardShortcuts(target,()=>settings,name=>seen.push(name));
 target.dispatchEvent(keyEvent({ctrlKey:true,shiftKey:true}));settings={fullCapture:'Command+Option+B',recordToggle:'Control+Shift+0'};
 const old=keyEvent({ctrlKey:true,shiftKey:true});target.dispatchEvent(old);assert.equal(old.defaultPrevented,false);
 target.dispatchEvent(keyEvent({key:'b',code:'KeyB',metaKey:true,altKey:true}));
 target.dispatchEvent(keyEvent({key:')',code:'Digit0',ctrlKey:true,shiftKey:true}));
 settings={webCapture:'Option+Shift+9',toggleRecording:'Command+R'};
 target.dispatchEvent(keyEvent({key:'(',code:'Digit9',altKey:true,shiftKey:true}));
 target.dispatchEvent(keyEvent({key:'r',code:'KeyR',metaKey:true}));unbind();
 assert.deepEqual(seen,['areaCapture','fullCapture','toggleRecording','webCapture','toggleRecording']);
});

test('foreground shortcuts require exact modifiers and ignore repeat or previously handled editor keys',()=>{
 const target=new EventTarget(),seen=[];
 const unbind=bindDesktopKeyboardShortcuts(target,()=>({areaCapture:'Control+Shift+A'}),name=>seen.push(name));
 for(const values of [{},{ctrlKey:true},{ctrlKey:true,shiftKey:true,altKey:true},{metaKey:true,shiftKey:true},{ctrlKey:true,shiftKey:true,repeat:true},{ctrlKey:true,shiftKey:true,getModifierState:()=>true}]){
  const event=keyEvent(values);target.dispatchEvent(event);assert.equal(event.defaultPrevented,false);
 }
 const handled=keyEvent({ctrlKey:true,shiftKey:true});handled.preventDefault();target.dispatchEvent(handled);
 unbind();assert.deepEqual(seen,[]);
});

test('unknown, duplicate and unsupported configured combinations never consume keyboard events',()=>{
 for(const combo of ['A','Control+Control+A','Hyper+A','Control++A','Control+F9','Control+KeyA','control+A','Control+a','Control+C','Command+V','']){
  const target=new EventTarget(),seen=[],unbind=bindDesktopKeyboardShortcuts(target,()=>({areaCapture:combo}),name=>seen.push(name));
  const event=keyEvent({key:combo.endsWith('+C')?'c':combo.endsWith('+V')?'v':'a',ctrlKey:combo.split('+').includes('Control'),metaKey:combo.split('+').includes('Command')});target.dispatchEvent(event);
  assert.equal(event.defaultPrevented,false,combo);assert.deepEqual(seen,[],combo);unbind();
 }
 const target=new EventTarget(),seen=[],unbind=bindDesktopKeyboardShortcuts(target,()=>({unknown:'Control+Shift+A'}),name=>seen.push(name));
 const event=keyEvent({ctrlKey:true,shiftKey:true});target.dispatchEvent(event);assert.equal(event.defaultPrevented,false);assert.deepEqual(seen,[]);unbind();
});

test('foreground and Carbon/native shortcut events share one capture execution and debounce gate',async()=>{
 const target=new EventTarget(),pending=deferred();let starts=0,now=1000;
 const dispatcher=createDesktopShortcutDispatcher({now:()=>now,isBusy:()=>false,run:async()=>{starts++;await pending.promise;}});
 const dispatch=name=>{void dispatcher.dispatch(name);};
 const unbindKey=bindDesktopKeyboardShortcuts(target,()=>({areaCapture:'Control+Shift+A'}),dispatch);
 const unbindNative=bindDesktopEvents(target,{navigate(){},shortcut:dispatch});
 target.dispatchEvent(keyEvent({key:'ㅁ',ctrlKey:true,shiftKey:true}));
 target.dispatchEvent(detailEvent('galaxycontrol:shortcut',{name:'areaCapture'}));assert.equal(starts,1);
 pending.resolve();await Promise.resolve();await Promise.resolve();
 now=1100;target.dispatchEvent(keyEvent({ctrlKey:true,shiftKey:true}));assert.equal(starts,1);
 now=1400;target.dispatchEvent(detailEvent('galaxycontrol:shortcut',{name:'areaCapture'}));assert.equal(starts,2);
 unbindKey();unbindNative();await Promise.resolve();
});
