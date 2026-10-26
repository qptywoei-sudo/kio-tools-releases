const test=require('node:test'),assert=require('node:assert/strict'),load=require('./load-source.cjs');
const {LocalAgentClient}=load('services/local-agent.ts');
test('recording choices and every shortcut survive the client settings request',async()=>{
 const client=Object.create(LocalAgentClient.prototype),requests=[];
 client.json=async(path,method,body)=>{requests.push({path,method,body});return {settings:body};};
 const shortcuts={areaCapture:'Control+Shift+A',fullCapture:'Control+Shift+B',webCapture:'Control+Shift+C',recordToggle:'Control+Shift+D',recordArea:'Control+Shift+E',aiTranslate:'Control+Shift+F'};
 for(const mode of ['full','area','window']){
  const recording={mode,monitor:1,monitorName:'DISPLAY2'},result=await client.applySettings({recording,shortcuts});
  assert.deepEqual(result,{recording,shortcuts});assert.equal(requests.at(-1).path,'/settings');assert.equal(requests.at(-1).method,'PATCH');
 }
 const disabled=Object.fromEntries(Object.keys(shortcuts).map(key=>[key,'']));assert.deepEqual((await client.applySettings({shortcuts:disabled})).shortcuts,disabled);
});
