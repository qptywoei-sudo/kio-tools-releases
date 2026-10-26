import {toolCategories,type Category} from './catalog';

export type DesktopNavigation=Category|'home';
export type DesktopShortcut='areaCapture'|'fullCapture'|'webCapture'|'toggleRecording'|'aiTranslate'|'recordArea';
export type DesktopCaptureLifecycle='surfaceReady'|'desktopReady'|'captureStarted'|'captureReady'|'captureClosed'|'captureCancelled'|'shortcutError';
const navigationNames=new Set<string>(['home','settings',...toolCategories]);
const shortcutNames=new Set<string>(['areaCapture','fullCapture','webCapture','toggleRecording','recordToggle','recordArea','aiTranslate']);

// Native menus send data-only messages. Unknown commands never execute code,
// navigate to a URL, or mutate an unrelated ADMIN screen.
export function desktopNavigation(detail:unknown):DesktopNavigation|null{
 if(!detail||typeof detail!=='object'||Array.isArray(detail))return null;
 const category=(detail as Record<string,unknown>).category;
 return typeof category==='string'&&navigationNames.has(category)?category as DesktopNavigation:null;
}
export function desktopShortcut(detail:unknown):DesktopShortcut|null{
 if(!detail||typeof detail!=='object'||Array.isArray(detail))return null;
 const name=(detail as Record<string,unknown>).name;
 if(typeof name!=='string'||!shortcutNames.has(name))return null;
 return name==='recordToggle'?'toggleRecording':name as DesktopShortcut;
}
export function bindDesktopEvents(target:EventTarget,handlers:{navigate:(category:DesktopNavigation)=>void;shortcut:(name:DesktopShortcut,startedAt?:number)=>void}){
 const navigate=(event:Event)=>{const category=desktopNavigation((event as CustomEvent<unknown>).detail);if(category)handlers.navigate(category);};
 const shortcut=(event:Event)=>{const name=desktopShortcut((event as CustomEvent<unknown>).detail);if(name){const value=(event as CustomEvent<{startedAt?:number}>).detail?.startedAt;handlers.shortcut(name,typeof value==='number'&&Math.abs(value-Date.now())<600000?value:Date.now());}};
 target.addEventListener('galaxycontrol:navigate',navigate);target.addEventListener('galaxycontrol:shortcut',shortcut);
 return ()=>{target.removeEventListener('galaxycontrol:navigate',navigate);target.removeEventListener('galaxycontrol:shortcut',shortcut);};
}
type ConfiguredDesktopKey={key:string;command:boolean;control:boolean;option:boolean;shift:boolean};
function configuredDesktopKey(value:unknown):ConfiguredDesktopKey|null{
 if(typeof value!=='string')return null;
 const parts=value.split('+'),key=parts.at(-1)??'',names=new Set(['Command','Win','Control','Option','Alt','Shift']),modifiers=parts.slice(0,-1);
 if(parts.length<2||parts.length>5||!/^(?:[A-Z0-9]|F(?:[1-9]|1[0-9]|2[0-4])|PrintScreen|Space)$/.test(key)||modifiers.some(name=>!names.has(name))||new Set(modifiers).size!==modifiers.length)return null;
 // Match native validation: ordinary copy/paste bindings stay available to the editor.
 if(['C','V'].includes(key)&&modifiers.length===1&&['Command','Control'].includes(modifiers[0]))return null;
 return {key,command:modifiers.includes('Command')||modifiers.includes('Win'),control:modifiers.includes('Control'),option:modifiers.includes('Option')||modifiers.includes('Alt'),shift:modifiers.includes('Shift')};
}
/** Foreground fallback shares the caller's dispatcher with Carbon/native menu events. */
export function bindDesktopKeyboardShortcuts(target:EventTarget,getShortcuts:()=>Record<string,string|undefined>,dispatch:(name:DesktopShortcut)=>void){
 const keydown=(event:Event)=>{
  const keyEvent=event as KeyboardEvent;
  if(keyEvent.defaultPrevented||keyEvent.repeat||keyEvent.getModifierState?.('AltGraph'))return;
  // IMEs can report a composed character or Process; code retains the physical A-Z/0-9 key.
  const physical=/^(?:Key([A-Z])|Digit([0-9]))$/.exec(keyEvent.code??'');
  const key=typeof keyEvent.key==='string'&&/^[a-z0-9]$/i.test(keyEvent.key)?keyEvent.key.toUpperCase():physical?.[1]??physical?.[2]??(/^(?:F(?:[1-9]|1[0-9]|2[0-4])|PrintScreen)$/.test(keyEvent.key)?keyEvent.key:keyEvent.code==='Space'?'Space':undefined);
  if(!key)return;
  const shortcuts=getShortcuts();
  for(const name of ['areaCapture','fullCapture','webCapture','recordToggle','toggleRecording','recordArea','aiTranslate']){
   const binding=configuredDesktopKey(shortcuts[name]);
   if(!binding||binding.key!==key||binding.command!==Boolean(keyEvent.metaKey)||binding.control!==Boolean(keyEvent.ctrlKey)||binding.option!==Boolean(keyEvent.altKey)||binding.shift!==Boolean(keyEvent.shiftKey))continue;
   keyEvent.preventDefault();dispatch(name==='recordToggle'?'toggleRecording':name as DesktopShortcut);return;
  }
 };
 target.addEventListener('keydown',keydown);
 return ()=>target.removeEventListener('keydown',keydown);
}
export function createDesktopShortcutDispatcher({run,isBusy,onIgnored,now=()=>Date.now(),debounceMs=400}:{run:(name:DesktopShortcut)=>Promise<void>;isBusy:()=>boolean;onIgnored?:(name:DesktopShortcut)=>void;now?:()=>number;debounceMs?:number}){
 let running=false,lastStart=-Infinity;
 return {async dispatch(name:DesktopShortcut){const time=now();if(running||isBusy()||time-lastStart<debounceMs){onIgnored?.(name);return false;}running=true;lastStart=time;try{await run(name);return true;}finally{running=false;}}};
}
type NativeMessage={action:DesktopCaptureLifecycle|'driveConnected'}|{action:'copyText';text:string;requestId:string}|{action:'aiPin';enabled:boolean}|{action:'captureFit';width:number;height:number;chromeHeight:number};
type MessageTarget={webkit?:{messageHandlers?:{galaxycontrol?:{postMessage:(message:NativeMessage)=>void}}};chrome?:{webview?:{postMessage:(message:NativeMessage)=>void}}};
function nativePost(payload:NativeMessage,target:MessageTarget){
 if(target.webkit?.messageHandlers?.galaxycontrol){target.webkit.messageHandlers.galaxycontrol.postMessage(payload);return true;}
 if(target.chrome?.webview){target.chrome.webview.postMessage(payload);return true;}return false;
}
export function notifyDesktopCapture(action:DesktopCaptureLifecycle,target:MessageTarget=globalThis as MessageTarget){
 const payload={action};
 try{return nativePost(payload,target);}catch{/* A closed native host must not invalidate a copied image. */}
 return false;
}
/** Return to the app only after a user-started browser authorization succeeds. */
export function notifyDesktopDriveConnected(target:MessageTarget=globalThis as MessageTarget){
 try{return nativePost({action:'driveConnected'},target);}catch{return false;}
}
/** Fit the native capture window once its image and compact toolbar have loaded. */
export function notifyDesktopCaptureSize(width:number,height:number,chromeHeight=112,target:MessageTarget=globalThis as MessageTarget){
 if(![width,height].every(value=>Number.isInteger(value)&&value>0&&value<=64000)||width*height>64000000||!Number.isFinite(chromeHeight)||chromeHeight<0||chromeHeight>600)return false;
 try{return nativePost({action:'captureFit',width,height,chromeHeight:Math.ceil(chromeHeight)},target);}catch{return false;}
}
export function finishDesktopCaptureSession(session:{current:boolean},action:'captureClosed'|'captureCancelled',publish:(action:DesktopCaptureLifecycle)=>boolean=notifyDesktopCapture){
 if(!session.current)return false;session.current=false;publish(action);return true;
}
export function completeDesktopCaptureSession(session:{current:boolean},openEditor:boolean,open:()=>void,publish:(action:DesktopCaptureLifecycle)=>boolean=notifyDesktopCapture){
 if(!session.current)return false;
 if(openEditor){open();publish('captureReady');}
 else finishDesktopCaptureSession(session,'captureClosed',publish);
 return true;
}
export function copyDesktopText(text:string,target:EventTarget&MessageTarget=window,timeoutMs=5000):Promise<void>{
 if(typeof text!=='string'||text.length>12000)return Promise.reject(Error('invalidRequest'));
 return new Promise<void>((resolve,reject)=>{
  const requestId=crypto.randomUUID(),timer=setTimeout(()=>finish(Error('processingFailed')),timeoutMs);
  const result=(event:Event)=>{const detail=(event as CustomEvent<unknown>).detail;if(!detail||typeof detail!=='object'||Array.isArray(detail))return;const response=detail as Record<string,unknown>;if(response.requestId!==requestId)return;finish(response.copied===true?undefined:Error('processingFailed'));};
  function finish(error?:Error){clearTimeout(timer);target.removeEventListener('galaxycontrol:clipboard-result',result);if(error)reject(error);else resolve();}
  target.addEventListener('galaxycontrol:clipboard-result',result);
  try{if(!nativePost({action:'copyText',text,requestId},target))finish(Error('nativeUnavailable'));}catch{finish(Error('processingFailed'));}
 });
}

export function notifyDesktopAIPin(enabled:boolean,target:MessageTarget=globalThis as MessageTarget){try{return nativePost({action:"aiPin",enabled},target);}catch{return false;}}
