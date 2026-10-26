const {test}=require('node:test');
const assert=require('node:assert/strict');
const load=require('./load-source.cjs');
const {clampSignature,resizeSignature}=load('features/local-tools/signature-geometry.ts');
const {formatStampDate,stampDateFormats,paintStamp,stampLayouts}=load('features/local-tools/signature-geometry.ts');
const {previewJob,isPdf}=load('features/local-tools/document-preview.ts');

test('drag clamps imported signatures to the document bounds',()=>{
 assert.deepEqual(clampSignature({x:-.2,y:.95,width:.3,height:.1}),{x:0,y:.9,width:.3,height:.1});
 assert.deepEqual(clampSignature({x:.1,y:.1,width:2,height:2}),{x:0,y:0,width:1,height:1});
});
test('wheel sizing preserves signature aspect ratio and center until the document edge',()=>{
 const source={x:.2,y:.3,width:.2,height:.1},grown=resizeSignature(source,1.5);
 assert.ok(Math.abs(grown.width/grown.height-2)<1e-10);
 assert.ok(Math.abs(grown.x+grown.width/2-(source.x+source.width/2))<1e-10);
 const max=resizeSignature(source,100);assert.ok(max.width<=1&&max.height<=1&&max.x>=0&&max.y>=0);
 const min=resizeSignature(source,.0001);assert.ok(min.width>=.025&&min.height>=.025);assert.equal(min.width/min.height,2);
});
test('preview classifies PDF by MIME or extension and waits for real job completion',async()=>{
 assert.equal(isPdf({id:'a',name:'FILE.PDF'}),true);
 assert.equal(isPdf({id:'a',name:'file',mime:'application/pdf'}),true);
 let checked=0,options;
 const client={jobs:async(op,inputs,value)=>{options=value;return {job:{id:'preview',status:'running'}};},job:async()=>{checked++;return {job:{id:'preview',status:'complete',result:{files:[{id:'png',name:'page.png'}]}}};}};
 const result=await previewJob(client,'pdf_render',['doc'],{pages:'2'});
 assert.equal(checked,1);assert.equal(options.previewOnly,true);assert.equal(result.result.files[0].id,'png');
});
test('failed preview jobs are rejected instead of presenting an empty document',async()=>{
 await assert.rejects(previewJob({jobs:async()=>({job:{id:'bad',status:'failed'}})},'pdf_info',['doc'],{}));
});
test('all ten stamp date formats preserve year month and day without timezone conversion',()=>{
 const outputs=['2026-10-13','2026/10/13','2026.10.13','13/10/2026','13-10-2026','13.10.2026','10/13/2026','10-13-2026','2026년 10월 13일','20261013'];
 assert.deepEqual(stampDateFormats.map(([format])=>formatStampDate('2026-10-13',format)),outputs);
 assert.equal(formatStampDate('2024-02-29','dmy-slash'),'29/02/2024');assert.equal(formatStampDate('','dmy-slash'),'');
 assert.equal(formatStampDate('2026-01-02','korean'),'2026년 1월 2일');
});
test('every stamp shape and layout paints the chosen date and legacy stamps keep their appearance',()=>{
 for(const shape of ['circle','oval','square','rect'])for(const [layout] of stampLayouts)for(const [dateFormat] of stampDateFormats){
  const text=[];const ctx={clearRect(){},beginPath(){},ellipse(){},roundRect(){},stroke(){},measureText(value){return {width:value.length*20}},fillText(value){text.push(value)},moveTo(){},lineTo(){},fillRect(){},save(){},restore(){}};
  const canvas={getContext(){return ctx}};paintStamp(canvas,{shape,layout,name:'KIO',company:'TEST',date:'2026-10-13',color:'#c93131',dateFormat});
  assert.ok(text.includes(formatStampDate('2026-10-13',dateFormat)),shape+'/'+layout+'/'+dateFormat);
 }
 const text=[],ctx=new Proxy({measureText(){return {width:100}},fillText(value){text.push(value)}},{get:(target,key)=>target[key]??(()=>{}),set:(target,key,value)=>{target[key]=value;return true}});
 paintStamp({getContext(){return ctx}},{shape:'circle',name:'KIO',company:'',date:'2026.10.13',color:'#c93131'});assert.ok(text.includes('2026.10.13'));
});
