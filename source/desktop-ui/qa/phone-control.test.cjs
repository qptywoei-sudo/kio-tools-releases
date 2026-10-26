const test=require('node:test'),assert=require('node:assert/strict'),React=require('react');
const load=require('./load-source.cjs');
const {PhoneControl}=load('features/local-tools/PhoneControl.tsx');
const {localToolsTranslator}=load('features/local-tools/translations.ts');
const authorized={id:'phone-authorized-usb',label:'SM_F946N',transport:'usb',status:'device'};
const options={keyboard:'uhid',mouse:'uhid',audio:'output',clipboard:true};
const ready={available:true,devices:[authorized],running:false,activeDeviceId:null,options};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function children(node){return [node?.props?.children].flat(Infinity);}
function text(node){if(node===null||node===undefined||typeof node==='boolean')return '';if(typeof node==='string'||typeof node==='number')return String(node);return children(node).map(text).join('');}
function find(node,predicate){if(!node||typeof node!=='object')return null;if(predicate(node))return node;for(const child of children(node)){const found=find(child,predicate);if(found)return found;}return null;}
function mount({state=ready,connected=true,confirmed=false,busy=false,storageThrows=false,language='ko',platform='Win32',failure}={}){
 const originals={useState:React.useState,useRef:React.useRef,useEffect:React.useEffect,useCallback:React.useCallback,useContext:React.useContext,useMemo:React.useMemo};
 const storageDescriptor=Object.getOwnPropertyDescriptor(globalThis,'localStorage'),navigatorDescriptor=Object.getOwnPropertyDescriptor(globalThis,'navigator');
 const states=[],calls=[],writes=[],errors=[],t=localToolsTranslator(language);let index=0;
 const storage={getItem(){if(storageThrows)throw Error('storage blocked');return confirmed?'confirmed':null;},setItem(...args){if(storageThrows)throw Error('storage blocked');writes.push(args);}};
 Object.defineProperty(globalThis,'localStorage',{configurable:true,value:storage});
 Object.defineProperty(globalThis,'navigator',{configurable:true,value:{platform}});
 React.useContext=()=>language;React.useMemo=fn=>fn();React.useRef=value=>({current:value});React.useEffect=()=>{};React.useCallback=fn=>fn;
 React.useState=value=>{const current=index++;states[current]=current===0?state:current===1?state?.devices[0]?.id??'':current===2?busy:typeof value==='function'?value():value;return[states[current],next=>{states[current]=typeof next==='function'?next(states[current]):next;}];};
 const client={startPhone:async(...args)=>{calls.push(['start',...args]);if(failure)throw failure;},phone:async()=>{calls.push(['refresh']);return state;}};
 let tree;
 try{tree=PhoneControl({client,t,connected,onError:error=>errors.push(error),language});}
 finally{Object.assign(React,originals);if(storageDescriptor)Object.defineProperty(globalThis,'localStorage',storageDescriptor);else delete globalThis.localStorage;if(navigatorDescriptor)Object.defineProperty(globalThis,'navigator',navigatorDescriptor);else delete globalThis.navigator;}
 const start=find(tree,node=>node.type==='button'&&text(node)===t('tools.phoneStart'));
 function click(){const descriptor=Object.getOwnPropertyDescriptor(globalThis,'localStorage');Object.defineProperty(globalThis,'localStorage',{configurable:true,value:storage});try{return start.props.onClick();}finally{if(descriptor)Object.defineProperty(globalThis,'localStorage',descriptor);else delete globalThis.localStorage;}}
 return {tree,start,click,calls,writes,errors,states,t};
}

test('a freshly connected authorized USB phone can open without a separate setup confirmation',async()=>{
 const view=mount();
 assert.equal(view.start.props.disabled,false);
 assert.equal(view.states[8],false);
 assert.equal(view.calls.length,0);
 // Preserve the nearby escape-key instruction even before the first screen opens.
 const actions=find(view.tree,node=>node.props?.className==='lt-actions'&&find(node,child=>child===view.start));
 assert.ok(actions);
 const nodes=children(view.tree).flatMap(node=>node?.type===React.Fragment?children(node):[node]);
 const afterStart=nodes.slice(nodes.indexOf(actions)+1);
 assert.equal(afterStart[0].props.role,'note');
 assert.ok(text(afterStart[0]).includes('왼쪽 Alt'));
 assert.ok(text(afterStart[0]).includes('한 번 누르면 PC 마우스로 돌아옵니다'));
 view.click();await tick();
 assert.deepEqual(view.calls,[['start',authorized.id,options],['refresh']]);
 assert.equal(view.states[8],true);
 assert.deepEqual(view.writes,[['kio-phone-controls-v1','confirmed']]);
 assert.equal(view.states[2],false);
 assert.equal(view.errors.length,0);
});

test('storage restrictions and an existing confirmation both permit authorized first-use opening',async()=>{
 for(const settings of [{storageThrows:true},{confirmed:true}]){
  const view=mount(settings);assert.equal(view.start.props.disabled,false);view.click();await tick();
  assert.deepEqual(view.calls,[['start',authorized.id,options],['refresh']]);assert.equal(view.errors.length,0);
 }
});

test('connection requirements still prevent starting and explain what needs attention',async()=>{
 const cases=[
  [{connected:false},'tools.offline'],
  [{state:null},'tools.checking'],
  [{state:{...ready,available:false}},'tools.phoneToolsUnavailable'],
  [{state:{...ready,devices:[]}},'tools.error.phoneDeviceMissing'],
  [{state:{...ready,devices:[{...authorized,status:'offline'}]}},'tools.error.phoneDeviceMissing'],
  [{state:{...ready,devices:[{...authorized,status:'unauthorized'}]}},'tools.phoneAuthorizeHint'],
 ];
 for(const[settings,key]of cases){const view=mount(settings);assert.equal(view.start.props.disabled,true,key);assert.ok(text(view.tree).includes(view.t(key)),key);view.click();await tick();assert.equal(view.calls.length,0,key);}
 for(const settings of [{busy:true},{state:{...ready,running:true,activeDeviceId:authorized.id}}]){const view=mount(settings);assert.equal(view.start.props.disabled,true);view.click();await tick();assert.equal(view.calls.length,0);}
});

test('a failed screen launch reports the error and leaves the start action ready to retry',async()=>{
 const failure=Error('phoneStartFailed'),view=mount({failure});view.click();await tick();
 assert.deepEqual(view.calls,[['start',authorized.id,options]]);assert.deepEqual(view.errors,[failure]);assert.equal(view.states[2],false);
});

test('the recovery message and adjacent return key are available in every supported language',()=>{
 for(const language of ['ko','en','vi','ja','zh','zh-TW']){
  const view=mount({language,state:{...ready,available:false}});
  assert.notEqual(view.t('tools.phoneToolsUnavailable'),'tools.phoneToolsUnavailable');
  assert.ok(text(view.tree).includes(view.t('tools.phoneToolsUnavailable')));
  assert.ok(find(view.tree,node=>node.props?.role==='note'&&find(node,child=>child.type==='kbd')));
 }
 const mac=mount({platform:'MacIntel'});assert.ok(text(mac.tree).includes('⌘ Command'));
});
