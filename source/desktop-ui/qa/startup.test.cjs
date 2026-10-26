const test=require('node:test'),assert=require('node:assert/strict');
const load=require('./load-source.cjs');
const {finishToolsStartup}=load('features/local-tools/startup.ts');
test('startup keeps its image through the current paint, removes it once usable and sends no private data',()=>{
 const saved=Object.fromEntries(['document','requestAnimationFrame','cancelAnimationFrame','chrome'].map(k=>[k,globalThis[k]]));
 const pending=new Map(),sent=[];let id=0,removed=0;
 try{
  globalThis.document={getElementById(name){assert.equal(name,'kio-tools-startup');return{remove(){removed++;}};}};
  globalThis.requestAnimationFrame=callback=>{pending.set(++id,callback);return id;};globalThis.cancelAnimationFrame=key=>pending.delete(key);
  globalThis.chrome={webview:{postMessage:payload=>sent.push(payload)}};
  const cancel=finishToolsStartup();assert.equal(removed,0);cancel();assert.equal(pending.size,0);
  finishToolsStartup();for(const callback of pending.values())callback();
  assert.equal(removed,1);assert.deepEqual(sent,[{action:'surfaceReady'}]);
 }finally{for(const [key,value] of Object.entries(saved)){if(value===undefined)delete globalThis[key];else globalThis[key]=value;}}
});
test('server rendering does not require browser animation APIs',()=>{
 assert.equal(typeof document,'undefined');assert.doesNotThrow(()=>finishToolsStartup()());
});
