const test=require('node:test');
const assert=require('node:assert/strict');
const load=require('./load-source.cjs');
const {LocalAgentClient}=load('services/local-agent.ts');
const origin='http://127.0.0.1:4323',deviceId='9af34c96-995f-469b-a306-2a025159d936',token='w'.repeat(48);
const page={origin,pathname:'/tools/',hash:'#kioWebToken='+token+'&kioDeviceId='+deviceId};
test('an iframe including a legacy web grant cannot inherit stored native approvals',()=>{
 const before={window:globalThis.window,location:globalThis.location,history:globalThis.history,session:globalThis.__galaxyDesktopSession};let reads=0;
 globalThis.window={parent:{}};globalThis.location={...page,hostname:'127.0.0.1',port:'4323',search:''};globalThis.history={replaceState(){}};globalThis.__galaxyDesktopSession=undefined;
 const storage={getItem:key=>{reads++;return key.includes('.token.')?'s'.repeat(48):deviceId;},setItem(){},removeItem(){}};
 try{const client=new LocalAgentClient(()=>{throw Error('must not request without capability');},'desktop',storage);assert.equal(client.paired,false);assert.equal(reads,0);}
 finally{globalThis.window=before.window;globalThis.location=before.location;globalThis.history=before.history;globalThis.__galaxyDesktopSession=before.session;}
});
