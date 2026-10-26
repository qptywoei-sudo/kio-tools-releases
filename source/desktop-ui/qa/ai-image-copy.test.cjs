const test=require('node:test'),assert=require('node:assert/strict'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server'),load=require('./load-source.cjs');
const {AIImageResult,copyAIImage,saveAIImage}=load('features/local-tools/AIImageResult.tsx');

function fixture(){
 const original=new Blob(['original captured PNG'],{type:'image/png'}),translated=new Blob(['rendered translated PNG'],{type:'image/png'}),calls=[];
 const client={async aiScanPreview(id){calls.push(['original',id]);return original;},async aiTranslatedImage(id){calls.push(['translated',id]);return translated;},async copyImageBlob(png){calls.push(['copy',png]);}};
 return {original,translated,calls,client};
}
test('original image can be copied before translation and uses unchanged capture bytes',async()=>{
 const f=fixture();await copyAIImage(f.client,'scan-1',null,'original');
 assert.deepEqual(f.calls,[['original','scan-1'],['copy',f.original]]);
});
test('translated copy retrieves the completed rendered image rather than original pixels',async()=>{
 const f=fixture();await copyAIImage(f.client,'scan-1','result-1','translated');
 assert.deepEqual(f.calls,[['translated','result-1'],['copy',f.translated]]);
});
test('missing result and expired original cannot fall back to another image',async()=>{
 const f=fixture();await assert.rejects(copyAIImage(f.client,'scan-1',null,'translated'),/aiSessionExpired/);assert.deepEqual(f.calls,[]);
 f.client.aiScanPreview=async()=>{throw Error('aiSessionExpired');};
 await assert.rejects(copyAIImage(f.client,'scan-1','result-1','original'),/aiSessionExpired/);assert.deepEqual(f.calls,[]);
});
test('a result arriving after scan closure or account switch is never copied',async()=>{
 const f=fixture();let current=true;f.client.aiScanPreview=async()=>{current=false;return f.original;};
 await assert.rejects(copyAIImage(f.client,'scan-1',null,'original',()=>current),/aiSessionExpired/);assert.deepEqual(f.calls,[]);
 await assert.rejects(copyAIImage(f.client,'scan-1','result-1','translated',()=>false),/aiSessionExpired/);assert.deepEqual(f.calls,[]);
});
test('replacing the connected client during original fetch discards its late pixels',async()=>{
 const f=fixture(),source={client:f.client,scanId:'scan-1'};let current=source;
 f.client.aiScanPreview=async()=>{current={client:{...f.client},scanId:'scan-1'};return f.original;};
 await assert.rejects(copyAIImage(f.client,source.scanId,null,'original',()=>current.client===source.client&&current.scanId===source.scanId),/aiSessionExpired/);
 assert.deepEqual(f.calls,[]);
});
test('pending translation exposes source and result copy buttons at the top without displaying source',()=>{
 const html=renderToStaticMarkup(React.createElement(AIImageResult,{client:fixture().client,scanId:'scan-1',value:null}));
 const buttons=[...html.matchAll(/<button\b([^>]*)>(.*?)<\/button>/g)].map(match=>({attributes:match[1],content:match[2]}));
 assert.equal(buttons.length,2);assert.ok(buttons[0].content.includes('원문 복사'));assert.ok(!buttons[0].attributes.includes('disabled'));
 assert.ok(buttons[1].content.includes('번역본 복사'));assert.ok(buttons[1].attributes.includes('disabled'));
 assert.ok(!html.includes('<img'));assert.ok(!html.includes('번역 글자 확인'));
});
test('closing or rescanning during upload does not start a stale image-save job',async()=>{
 let current=true;const calls=[],png=fixture().translated;
 const client={async upload(){calls.push('upload');current=false;return {id:'upload-1'};},async jobs(){calls.push('jobs');throw Error('stale job started');}};
 assert.equal(await saveAIImage(client,png,()=>current),undefined);assert.deepEqual(calls,['upload']);
});
test('changing image during immediately completed save does not export its old result',async()=>{
 let epoch=1;const calls=[],png=fixture().translated;
 const client={async upload(){calls.push('upload');return {id:'upload-1'};},async jobs(){calls.push('jobs');epoch++;return {job:{status:'complete',result:null}};}};
 // The intentionally invalid old result would throw if export were attempted.
 assert.equal(await saveAIImage(client,png,()=>epoch===1),undefined);assert.deepEqual(calls,['upload','jobs']);
});
test('a completed poll returning after closure cannot export a stale save',async()=>{
 let current=true;const calls=[],png=fixture().translated;
 const client={async upload(){return {id:'upload-1'};},async jobs(){return {job:{id:'job-1',status:'running'}};},async job(id){calls.push(id);current=false;return {job:{status:'complete',result:null}};}};
 assert.equal(await saveAIImage(client,png,()=>current),undefined);assert.deepEqual(calls,['job-1']);
});
test('saving the current completed image returns the agent-confirmed PNG',async()=>{
 const png=fixture().translated,file={id:'saved-1',mime:'image/png'},calls=[];
 const client={async upload(upload){calls.push(['upload',upload.type,await upload.text()]);return {id:'upload-1'};},async jobs(operation,ids,options){calls.push([operation,ids,options]);return {job:{status:'complete',result:{files:[file]}}};}};
 assert.equal(await saveAIImage(client,png,()=>true),file);
 assert.deepEqual(calls,[['upload','image/png',await png.text()],['image_process',['upload-1'],{format:'png',scale_percent:100,no_upscale:true}]]);
});
