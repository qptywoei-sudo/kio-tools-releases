import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {AGENT_PORTS,AGENT_ORIGINS,validAgentHealth,createAgentClient} from './agent-endpoint.js';

const device='12345678-1234-1234-1234-123456789abc';
const otherDevice='87654321-4321-4321-4321-cba987654321';
const token='synthetic_test_token_'.repeat(3);
const health=(id=device,extra={})=>({connected:true,version:'4.2.3',os:'Windows',deviceId:id,nativeReady:true,operations:['image_process','web_capture'],...extra});
function fixture(saved={},servers={}){
 const state=structuredClone(saved),calls=[];const network=new Map(Object.entries(servers));
 const storage={async get(keys){return Object.fromEntries((Array.isArray(keys)?keys:[keys]).map(key=>[key,structuredClone(state[key])]));},async set(values){Object.assign(state,structuredClone(values));},async remove(keys){for(const key of Array.isArray(keys)?keys:[keys])delete state[key];}};
 const instance={state,calls,network,storage,onPair:undefined,onRequest:undefined};
 const fetchFn=async(url,options={})=>{
  const parsed=new URL(url),headers=new Headers(options.headers);calls.push({url,path:parsed.pathname,origin:parsed.origin,method:options.method||'GET',token:headers.get('X-Local-Agent-Token'),redirect:options.redirect});
  assert.ok(AGENT_ORIGINS.includes(parsed.origin),'request escaped bounded loopback endpoints');
  assert.equal(options.redirect,'error','redirects must never carry a pairing token');assert.equal(options.credentials,'omit','browser credentials must never accompany agent discovery or requests');
  if(parsed.pathname==='/health'){assert.equal(headers.get('X-Local-Agent-Token'),null);const value=network.get(parsed.origin);if(!value)throw Error('ECONNREFUSED');if(value instanceof Error)throw value;return Response.json(value);}
  if(parsed.pathname==='/pair'&&(options.method||'GET')==='POST'){assert.equal(headers.get('X-Local-Agent-Token'),null);const device=network.get(parsed.origin);await instance.onPair?.(parsed.origin);return Response.json(instance.pairPayload||{token:instance.pairToken||token,device});}
  return instance.onRequest?.(parsed,options)||Response.json({ok:true});
 };
 instance.agent=createAgentClient({storage,fetchFn,probeTimeoutMs:50});return instance;
}
const paired=(origin=AGENT_ORIGINS[0],id=device)=>({agentPairing:{origin,deviceId:id,token}});
const authorized=f=>f.calls.filter(call=>call.token!==null);

test('fixed endpoints preserve priority and reject malformed/foreign health',()=>{
 assert.deepEqual(AGENT_PORTS,[4323,4324,4325,4321]);assert.ok(validAgentHealth(health()));
 assert.ok(validAgentHealth(health(device,{nativeReady:false})));
 for(const field of ['connected','version','os','deviceId','nativeReady','operations']){const value=health();delete value[field];assert.equal(validAgentHealth(value),false,field);}
 for(const value of [null,[],health(device,{connected:'true'}),health(device,{version:'1.0.0'}),health(device,{os:'Linux'}),health('../not-uuid'),health(device+'\n'),health(device,{nativeReady:1}),health(device,{operations:[]}),health(device,{operations:['creator']}),health(device,{operations:['image_process',1]}),health(device,{operations:['image_process','web_capture\n']})])assert.equal(validAgentHealth(value),false);
 assert.equal(validAgentHealth(health(otherDevice),device),false);
});

test('pair prefers first healthy candidate, skips creator, and stores token bound to device and origin',async()=>{
 const f=fixture({}, {[AGENT_ORIGINS[0]]:{connected:true,version:'4.0.0'},[AGENT_ORIGINS[1]]:health(),[AGENT_ORIGINS[2]]:health(otherDevice)});
 assert.deepEqual(await f.agent.pair(),{connected:true});assert.deepEqual(f.state.agentPairing,{origin:AGENT_ORIGINS[1],deviceId:device,token});
 assert.equal(f.calls.find(call=>call.path==='/pair').origin,AGENT_ORIGINS[1]);assert.deepEqual(authorized(f),[]);
});

test('repeated Connect reuses one native approval and the saved token',async()=>{
 const f=fixture({}, {[AGENT_ORIGINS[0]]:health()});
 for(let i=0;i<4;i++)assert.deepEqual(await f.agent.pair(),{connected:true});
 assert.equal(f.calls.filter(call=>call.path==='/pair').length,1);
 assert.equal(authorized(f).length,3);assert.ok(authorized(f).every(call=>call.path==='/browser'&&call.method==='GET'&&call.token===token));
 assert.deepEqual(f.state.agentPairing,paired().agentPairing);
});

test('extension restart reuses persisted approval without asking the native app again',async()=>{
 const first=fixture({}, {[AGENT_ORIGINS[0]]:health()});await first.agent.pair();
 const restarted=fixture(first.state,{[AGENT_ORIGINS[0]]:health()});
 assert.deepEqual(await restarted.agent.status(),{connected:true});assert.deepEqual(await restarted.agent.pair(),{connected:true});
 assert.equal(restarted.calls.filter(call=>call.path==='/pair').length,0);assert.equal(authorized(restarted).length,2);
});

test('simultaneous Connect clicks share the first native approval',async()=>{
 const f=fixture({}, {[AGENT_ORIGINS[0]]:health()});let release;
 const approved=new Promise(resolve=>{release=resolve;});f.onPair=()=>approved;
 const first=f.agent.pair(),second=f.agent.pair();assert.equal(first,second);
 release();assert.deepEqual(await Promise.all([first,second]),[{connected:true},{connected:true}]);
 assert.equal(f.calls.filter(call=>call.path==='/pair').length,1);
});

test('Connect follows the paired UUID to another port without reapproval or credentials on the previous foreign service',async()=>{
 const f=fixture(paired(AGENT_ORIGINS[3]),{[AGENT_ORIGINS[3]]:health(otherDevice),[AGENT_ORIGINS[1]]:health()});
 assert.deepEqual(await f.agent.pair(),{connected:true});
 assert.equal(f.calls.filter(call=>call.path==='/pair').length,0);assert.equal(authorized(f).length,1);
 assert.equal(authorized(f)[0].origin,AGENT_ORIGINS[1]);assert.deepEqual(f.state.agentPairing,paired(AGENT_ORIGINS[1]).agentPairing);
});

test('revoked token requires exactly one new native approval on explicit Connect, then is reused',async()=>{
 const replacement='replacement_synthetic_token_'.repeat(2);
 const f=fixture(paired(),{[AGENT_ORIGINS[0]]:health(),[AGENT_ORIGINS[1]]:health(otherDevice)});f.pairToken=replacement;
 f.onRequest=(_url,options)=>new Headers(options.headers).get('X-Local-Agent-Token')===token?Response.json({errorCode:'unauthorized'},{status:401}):Response.json({connected:true});
 assert.deepEqual(await f.agent.pair(),{connected:true});assert.deepEqual(await f.agent.pair(),{connected:true});
 assert.equal(f.calls.filter(call=>call.path==='/pair').length,1);assert.equal(f.state.agentPairing.token,replacement);
 assert.equal(f.state.agentPairing.deviceId,device);assert.ok(authorized(f).every(call=>call.origin===AGENT_ORIGINS[0]));
});

test('revoked approval is renewed for its own UUID even when another healthy agent has higher priority',async()=>{
 const f=fixture(paired(AGENT_ORIGINS[1]),{[AGENT_ORIGINS[0]]:health(otherDevice),[AGENT_ORIGINS[1]]:health()});
 f.onRequest=()=>Response.json({errorCode:'unauthorized'},{status:401});
 await f.agent.pair();assert.equal(f.calls.find(call=>call.path==='/pair').origin,AGENT_ORIGINS[1]);
 assert.ok(authorized(f).every(call=>call.origin===AGENT_ORIGINS[1]));assert.equal(f.state.agentPairing.deviceId,device);
});

test('a temporary authenticated API failure preserves approval and never opens another native prompt',async()=>{
 const f=fixture(paired(),{[AGENT_ORIGINS[0]]:health()});f.onRequest=()=>Response.json({errorCode:'busy'},{status:503});
 await assert.rejects(f.agent.pair(),/agentUnavailable/);assert.deepEqual(f.state.agentPairing,paired().agentPairing);
 assert.equal(f.calls.filter(call=>call.path==='/pair').length,0);
});

test('Connect cannot send an old token or request a new approval from another device when the paired device is unavailable',async()=>{
 const f=fixture(paired(),{[AGENT_ORIGINS[0]]:health(otherDevice)});
 await assert.rejects(f.agent.pair(),/agentUnavailable/);assert.deepEqual(authorized(f),[]);
 assert.equal(f.calls.filter(call=>call.path==='/pair').length,0);assert.deepEqual(f.state.agentPairing,paired().agentPairing);
});

test('same-device restart at another port preserves pairing without sending token to previous foreign service',async()=>{
 const f=fixture(paired(AGENT_ORIGINS[3]),{[AGENT_ORIGINS[3]]:health(otherDevice),[AGENT_ORIGINS[1]]:health()});
 await f.agent.request('/browser/register',{method:'POST',credentials:'include',redirect:'follow',headers:{'X-Local-Agent-Token':'forged'}});
 assert.deepEqual(f.state.agentPairing,{origin:AGENT_ORIGINS[1],deviceId:device,token});
 assert.equal(authorized(f).length,1);assert.equal(authorized(f)[0].origin,AGENT_ORIGINS[1]);assert.equal(authorized(f)[0].token,token);
});

test('wrong device UUID receives no old token even when its health is otherwise valid',async()=>{
 const f=fixture(paired(),{[AGENT_ORIGINS[0]]:health(otherDevice),[AGENT_ORIGINS[1]]:health(otherDevice)});
 await assert.rejects(f.agent.request('/browser/register'),/agentUnavailable/);assert.deepEqual(authorized(f),[]);assert.deepEqual(await f.agent.status(),{connected:false});
});

test('unbound legacy token is removed and requires native pairing again',async()=>{
 const f=fixture({agentToken:token,language:'vi'},{[AGENT_ORIGINS[0]]:health()});
 await assert.rejects(f.agent.request('/events'),/pairingRequired/);assert.equal(f.state.agentToken,undefined);assert.equal(f.state.language,'vi');assert.equal(f.calls.length,0);
});

test('invalid saved origin never receives credentials or even a discovery request',async()=>{
 const f=fixture(paired('https://attacker.invalid'),{[AGENT_ORIGINS[0]]:health()});
 await assert.rejects(f.agent.request('/uploads'),/pairingRequired/);assert.equal(f.calls.length,0);assert.equal(f.state.agentPairing,undefined);
});

test('native-not-ready service cannot receive authenticated capture calls',async()=>{
 const f=fixture(paired(),{[AGENT_ORIGINS[0]]:health(device,{nativeReady:false})});
 await assert.rejects(f.agent.request('/browser/capture'),/agentUnavailable/);assert.deepEqual(authorized(f),[]);
});

test('new pairing is discarded if endpoint changes UUID during native approval',async()=>{
 const f=fixture({}, {[AGENT_ORIGINS[0]]:health()});f.onPair=origin=>f.network.set(origin,health(otherDevice));
 await assert.rejects(f.agent.pair(),/agentUnavailable/);assert.equal(f.state.agentPairing,undefined);assert.deepEqual(authorized(f),[]);
});

test('invalid native approval token is rejected without storing it',async()=>{
 for(const invalidToken of [token+'\n',token+'\r\nInjected: value']){const f=fixture({}, {[AGENT_ORIGINS[0]]:health()});f.pairToken=invalidToken;
 await assert.rejects(f.agent.pair(),/pairingDenied/);assert.equal(f.state.agentPairing,undefined);}
});

test('native approval response must include the exact probed device UUID',async()=>{
 for(const pairPayload of [{token},{token,device:{deviceId:otherDevice}},{token,device:{deviceId:device+'\n'}}]){const f=fixture({}, {[AGENT_ORIGINS[0]]:health()});f.pairPayload=pairPayload;await assert.rejects(f.agent.pair(),/pairingDenied/);assert.equal(f.state.agentPairing,undefined);assert.deepEqual(authorized(f),[]);}
});

test('saved pairing with trailing newline UUID or token is invalidated',async()=>{
 for(const update of [{deviceId:device+'\n'},{token:token+'\n'}]){const saved=paired();Object.assign(saved.agentPairing,update);const f=fixture(saved,{[AGENT_ORIGINS[0]]:health()});await assert.rejects(f.agent.request('/events'),/pairingRequired/);assert.equal(f.calls.length,0);}
});

test('endpoint is rechecked before every request so port reuse cannot inherit the old token',async()=>{
 const f=fixture(paired(),{[AGENT_ORIGINS[0]]:health()});await f.agent.request('/browser/heartbeat',{method:'POST'});
 f.network.set(AGENT_ORIGINS[0],health(otherDevice));await assert.rejects(f.agent.request('/uploads'),/agentUnavailable/);
 assert.equal(authorized(f).length,1);
});

test('401 invalidates only its own pairing and asks for a new native approval',async()=>{
 const f=fixture(paired(),{[AGENT_ORIGINS[0]]:health()});f.onRequest=()=>Response.json({errorCode:'pairingRequired'},{status:401});
 assert.equal((await f.agent.request('/browser/heartbeat')).status,401);assert.equal(f.state.agentPairing,undefined);
 await assert.rejects(f.agent.request('/events'),/pairingRequired/);
});

test('late 401 for old token cannot erase a newer pairing',async()=>{
 const f=fixture(paired(),{[AGENT_ORIGINS[0]]:health()});f.onRequest=()=>{f.state.agentPairing={origin:AGENT_ORIGINS[1],deviceId:otherDevice,token:'new_token_'.repeat(5)};return Response.json({errorCode:'pairingRequired'},{status:401});};
 await f.agent.request('/browser/heartbeat');assert.equal(f.state.agentPairing.deviceId,otherDevice);
});

test('public status response contains no token or private pairing fields',async()=>{
 const f=fixture(paired(),{[AGENT_ORIGINS[0]]:health()});assert.deepEqual(await f.agent.status(),{connected:true});assert.equal(authorized(f).length,1);assert.equal(authorized(f)[0].path,'/browser');
 await f.agent.clear();assert.deepEqual(await f.agent.status(),{connected:false});assert.equal(f.state.agentPairing,undefined);
});

test('status detects revocation without automatically asking for native approval',async()=>{
 const f=fixture(paired(),{[AGENT_ORIGINS[0]]:health()});f.onRequest=()=>Response.json({errorCode:'unauthorized'},{status:401});
 assert.deepEqual(await f.agent.status(),{connected:false});assert.equal(f.state.agentPairing,undefined);
 assert.equal(f.calls.filter(call=>call.path==='/pair').length,0);assert.equal(authorized(f).length,1);
});

test('late revoked-token response during Connect never overwrites a newer saved approval',async()=>{
 const replacement={origin:AGENT_ORIGINS[1],deviceId:otherDevice,token:'new_token_'.repeat(5)};
 const f=fixture(paired(),{[AGENT_ORIGINS[0]]:health()});f.onRequest=()=>{f.state.agentPairing=structuredClone(replacement);return Response.json({errorCode:'unauthorized'},{status:401});};
 await assert.rejects(f.agent.pair(),/pairingRequired/);assert.deepEqual(f.state.agentPairing,replacement);
 assert.equal(f.calls.filter(call=>call.path==='/pair').length,0);
});

test('approval revision is numeric, stable across reads and requests, and excludes private pairing data',async()=>{
 const f=fixture(paired(),{[AGENT_ORIGINS[0]]:health()});const revision=await f.agent.approvalRevision();
 assert.ok(Number.isSafeInteger(revision));assert.ok(revision>0);assert.equal(JSON.stringify(revision).includes(token),false);
 await f.agent.status();await f.agent.request('/browser/heartbeat',{method:'POST'});await f.agent.pair();
 assert.equal(await f.agent.approvalRevision(),revision);assert.equal(await f.agent.approvalRevision(),revision);
 assert.deepEqual(await f.agent.status(),{connected:true});assert.deepEqual(await f.agent.pair(),{connected:true});
});

test('moving the same approval to a different allowed port does not rotate its revision',async()=>{
 const f=fixture(paired(),{[AGENT_ORIGINS[0]]:health()});const revision=await f.agent.approvalRevision();
 f.network.delete(AGENT_ORIGINS[0]);f.network.set(AGENT_ORIGINS[2],health());await f.agent.request('/browser');
 assert.equal(f.state.agentPairing.origin,AGENT_ORIGINS[2]);assert.equal(await f.agent.approvalRevision(),revision);
});

test('revocation and a newly approved token both change revision so old streams can be retired',async()=>{
 const f=fixture(paired(),{[AGENT_ORIGINS[0]]:health()});const pairedRevision=await f.agent.approvalRevision();
 f.onRequest=()=>Response.json({errorCode:'unauthorized'},{status:401});await f.agent.status();
 const revokedRevision=await f.agent.approvalRevision();assert.ok(revokedRevision>pairedRevision);
 f.pairToken='newly_approved_synthetic_token_'.repeat(2);f.onRequest=undefined;await f.agent.pair();
 const renewedRevision=await f.agent.approvalRevision();assert.ok(renewedRevision>revokedRevision);
 assert.equal(await f.agent.approvalRevision(),renewedRevision);assert.equal(f.calls.filter(call=>call.path==='/pair').length,1);
});

test('approval revision rereads storage and notices another context rotating or clearing its token',async()=>{
 const f=fixture(paired(),{[AGENT_ORIGINS[0]]:health()});const original=await f.agent.approvalRevision();
 f.state.agentPairing={...f.state.agentPairing,token:'other_context_synthetic_token_'.repeat(2)};
 const rotated=await f.agent.approvalRevision();assert.ok(rotated>original);
 f.state.agentPairing={...f.state.agentPairing,deviceId:otherDevice};const rebound=await f.agent.approvalRevision();assert.ok(rebound>rotated);
 delete f.state.agentPairing;const cleared=await f.agent.approvalRevision();assert.ok(cleared>rebound);assert.equal(await f.agent.approvalRevision(),cleared);
 assert.equal(f.calls.length,0);
});

test('unpaired and explicitly cleared approval revisions remain stable until identity changes',async()=>{
 const f=fixture({}, {[AGENT_ORIGINS[0]]:health()});assert.equal(await f.agent.approvalRevision(),0);assert.equal(await f.agent.approvalRevision(),0);
 await f.agent.pair();const pairedRevision=await f.agent.approvalRevision();assert.ok(pairedRevision>0);
 await f.agent.clear();const clearedRevision=await f.agent.approvalRevision();assert.ok(clearedRevision>pairedRevision);assert.equal(await f.agent.approvalRevision(),clearedRevision);
});

test('invalid paths and an aborted discovery never send authenticated requests',async()=>{
 const f=fixture(paired(),{[AGENT_ORIGINS[0]]:health()});
 for(const path of ['https://attacker.invalid','//attacker.invalid','/../pair','/events\r\n','/events?redirect=http://elsewhere'])await assert.rejects(f.agent.request(path),/invalidRequest/);
 assert.equal(f.calls.length,0);const abort=new AbortController();abort.abort();await assert.rejects(f.agent.request('/events',{signal:abort.signal}),/cancelled/);assert.deepEqual(authorized(f),[]);
});

test('manifest keeps stable extension key and finite loopback permissions',async()=>{
 const manifest=JSON.parse(await readFile(new URL('./manifest.json',import.meta.url),'utf8'));
 assert.deepEqual(manifest.host_permissions,AGENT_ORIGINS.map(origin=>origin+'/*'));assert.equal(manifest.background.type,'module');assert.equal(manifest.default_locale,'en');
 const {createHash}=await import('node:crypto');const id=[...createHash('sha256').update(Buffer.from(manifest.key,'base64')).digest('hex').slice(0,32)].map(c=>String.fromCharCode(97+Number.parseInt(c,16))).join('');
 const existing=JSON.parse(await readFile(new URL('../agent/extension-origin.json',import.meta.url),'utf8'));assert.equal(id,existing.extensionId);
});

test('all supported v4 patch releases are discoverable, incompatible versions are rejected',()=>{for(const version of ['4.0.0','4.2.3','4.2.4','4.12.99'])assert.equal(validAgentHealth(health(device,{version})),true);for(const version of ['3.9.9','5.0.0','4.2.3-beta','4.2.3\n','4.2',4.2])assert.equal(validAgentHealth(health(device,{version})),false);});
