const test=require('node:test');
const assert=require('node:assert/strict');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const load=require('./load-source.cjs');
const {QrLogoControls,selectQrLogo,importQrLogo,transferredQrLogo}=load('features/local-tools/QrLogoControls.tsx');
const logoImage=load('features/local-tools/qr-logo-image.ts');
const {taskOptions,toolTasks}=load('features/local-tools/catalog.ts');
const props={client:{},value:null,onChange(){},disabled:false,onBusyChange(){}};

test('QR logo is optional and upload advertises the supported safe formats',()=>{
 const html=renderToStaticMarkup(React.createElement(QrLogoControls,props));
 assert.match(html,/PNG · JPG · SVG/);assert.match(html,/오류보정 H/);assert.doesNotMatch(html,/type="range"/);assert.doesNotMatch(html,/type="file"/);
 assert.match(html,/data-file-drop="local"/);assert.match(html,/Ctrl\+V/);
});
test('desktop logo selection uses one native file and uploads only the safely normalized image',async()=>{
 const original=logoImage.loadQrLogo,calls=[];
 const asset={name:'회사.svg',dataUrl:'data:image/png;base64,aGVsbG8=',width:100,height:100};
 const client={
  async choose(kind,multiple){calls.push(['choose',kind,multiple]);return {files:[{id:'original',name:'회사.svg',size:21,mime:'image/svg+xml'}]};},
  async artifact(id){calls.push(['artifact',id]);return new Blob(['<svg/>'],{type:'image/svg+xml'});},
  async upload(file){calls.push(['upload',file.name,file.type,await file.text()]);return {id:'safe-png',name:file.name};}
 };
 logoImage.loadQrLogo=async file=>{calls.push(['normalize',file.name,file.type,await file.text()]);return asset;};
 try{
  assert.deepEqual(await selectQrLogo(client),{file:{id:'safe-png',name:'qr-logo.png'},asset});
  assert.deepEqual(calls,[['choose','any',false],['artifact','original'],['normalize','회사.svg','image/svg+xml','<svg/>'],['upload','qr-logo.png','image/png','hello']]);
 }finally{logoImage.loadQrLogo=original;}
});
test('cancelled native logo chooser leaves the existing logo untouched',async()=>{
 assert.equal(await selectQrLogo({async choose(){return {files:[]};},async artifact(){assert.fail('cancel must not read');},async upload(){assert.fail('cancel must not upload');}}),null);
});
test('native logo selection rejects oversized and unsafe input before upload',async()=>{
 const original=logoImage.loadQrLogo;
 try{
  await assert.rejects(selectQrLogo({async choose(){return {files:[{id:'large',name:'large.png',size:5*1024*1024+1}]};},async artifact(){assert.fail('oversized logo must not be read');},async upload(){assert.fail('oversized logo must not upload');}}),/5MB/);
  logoImage.loadQrLogo=async()=>{throw Error('unsafe-svg');};
  await assert.rejects(selectQrLogo({async choose(){return {files:[{id:'unsafe',name:'unsafe.svg'}]};},async artifact(){return new Blob(['<svg><script/></svg>'],{type:'image/svg+xml'});},async upload(){assert.fail('unsafe logo must not upload');}}),/unsafe-svg/);
 }finally{logoImage.loadQrLogo=original;}
});
test('selected logo exposes shape with automatic sizing and fixed padding without replacing payload fields',()=>{
 const value={file:{id:'file-id'},asset:{name:'회사.svg',dataUrl:'data:image/png;base64,aGVsbG8=',width:100,height:100},shape:'circle',size:20,padding:2};
 const html=renderToStaticMarkup(React.createElement(QrLogoControls,{...props,value}));
 assert.match(html,/원형/);assert.match(html,/사각형/);assert.match(html,/흰색 여백 4px/);assert.match(html,/가장 큰 크기로 자동/);assert.doesNotMatch(html,/type="range"/);assert.match(html,/중앙 로고 제거/);assert.match(html,/data:image\/png;base64/);
 const original='https://example.com/a?x=%2F&name=원본#part';
 const options=taskOptions(toolTasks.find(item=>item.operation==='code_generate'),{kind:'qr',qr_type:'url',text:original});
 assert.equal(options.text,original);
});
test('disabled logo editor keeps uploads and all configuration controls unavailable',()=>{
 const value={file:{id:'file-id'},asset:{name:'logo.png',dataUrl:'data:image/png;base64,aGVsbG8=',width:100,height:100},shape:'square',size:18,padding:1};
 const html=renderToStaticMarkup(React.createElement(QrLogoControls,{...props,value,disabled:true}));
 const controls=html.match(/<(?:button|select|input)[^>]*>/g).filter(tag=>!tag.includes('type="file"'));
 assert(controls.length>=3);assert(controls.every(tag=>tag.includes('disabled=""')));
});

test('clipboard image items and dragged files resolve to the same local logo',()=>{
 const image=new File(['png'],'pasted.png',{type:'image/png'});
 const text={kind:'string',type:'text/html',getAsFile(){assert.fail('HTML must not be read as a file');}};
 assert.equal(transferredQrLogo({items:[text,{kind:'file',getAsFile:()=>image}],files:[]}),image);
 const svg=new File(['<svg/>'],'company.SVG');
 assert.equal(transferredQrLogo({items:[],files:[svg]}),svg);
 assert.equal(transferredQrLogo({items:[{kind:'file',getAsFile:()=>null}],files:[image]}),image);
});
test('pasting a URL, text or non-image attachment leaves the logo unchanged',()=>{
 assert.equal(transferredQrLogo({items:[{kind:'string',type:'text/plain'}],files:[]}),null);
 assert.equal(transferredQrLogo({items:[],files:[new File(['pdf'],'document.pdf',{type:'application/pdf'})]}),null);
});
test('paste and drop use the same sanitizer and PNG upload as the native picker',async()=>{
 const original=logoImage.loadQrLogo,calls=[];
 const input=new File(['raw'],'dropped.svg',{type:'image/svg+xml'});
 const asset={name:'dropped.svg',dataUrl:'data:image/png;base64,c2FmZQ==',width:20,height:30};
 logoImage.loadQrLogo=async file=>{assert.equal(file,input);return asset;};
 try{
  const result=await importQrLogo({async upload(file){calls.push([file.name,file.type,await file.text()]);return {id:'logo'};}},input);
  assert.equal(result.asset,asset);assert.equal(result.file.id,'logo');
  assert.deepEqual(calls,[['qr-logo.png','image/png','safe']]);
 }finally{logoImage.loadQrLogo=original;}
});
test('a rejected pasted logo never reaches the upload endpoint',async()=>{
 const original=logoImage.loadQrLogo;
 logoImage.loadQrLogo=async()=>{throw Error('unsafe-svg');};
 try{await assert.rejects(importQrLogo({async upload(){assert.fail('unsafe input uploaded');}},new File(['unsafe'],'bad.svg')),/unsafe-svg/);}
 finally{logoImage.loadQrLogo=original;}
});
