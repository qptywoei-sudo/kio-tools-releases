const test=require('node:test');
const assert=require('node:assert/strict');
const React=require('react');
// Static render only: never read or write the machine's browser storage.
Object.defineProperty(globalThis,'localStorage',{configurable:true,value:{getItem:()=>null,setItem(){}}});
const escapeHtml=value=>value.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('\"','&quot;').replaceAll("'",'&#x27;');
const {renderToStaticMarkup}=require('react-dom/server');
const load=require('./load-source.cjs');
const {canvasPoint,normalizeCanvasLayer,layerAbsolutePoints,resizeCanvasLayer,pointInsideLayer,canvasLayersForCrop,moveCanvasPage}=load('features/local-tools/canvas-geometry.ts');
const {canvasImageLayer}=load('features/local-tools/canvas-image.ts');
const {safeCanvasPreferences}=load('features/local-tools/canvas-preferences.ts');
const {fileSearchFilters,fileSearchWords}=load('features/local-tools/file-search.ts');
const {toolCategories,toolTasks,taskOptions,batchImageFilters}=load('features/local-tools/catalog.ts');
const {localToolsTranslations,localToolsTranslator}=load('features/local-tools/translations.ts');
const {editorText}=load('features/local-tools/editor-text.ts');
const {validClipRanges}=load('features/local-tools/ClipRanges.tsx');
const {PhoneControl}=load('features/local-tools/PhoneControl.tsx');
const {ToolsApp}=load('features/local-tools/ToolsApp.tsx');
const {CanvasEditor}=load('features/local-tools/CanvasEditor.tsx');
const languages=['ko','en','vi','ja','zh'];

// These are boundary/interaction contracts; they do not duplicate drawing code.
test('canvas pointer positions map a scaled viewport back to original pixels and clamp edges',()=>{
 const rect={left:100,top:50,width:300,height:200};
 assert.deepEqual(canvasPoint(250,150,rect,1200,800),[600,400]);
 assert.deepEqual(canvasPoint(-100,-100,rect,1200,800),[0,0]);
 assert.deepEqual(canvasPoint(9999,9999,rect,1200,800),[1200,800]);
 assert.throws(()=>canvasPoint(0,0,{left:0,top:0,width:0,height:20},100,100),/invalidRequest/);
});

test('freehand strokes retain original pixel positions when normalized and resize proportionally',()=>{
 const source={type:'draw',x:0,y:0,width:0,height:0,lineWidth:10,points:[[100,200],[160,240],[120,260]]};
 const layer=normalizeCanvasLayer(source);
 assert.deepEqual(layerAbsolutePoints(layer),source.points);
 assert.deepEqual(source.points,[[100,200],[160,240],[120,260]]);
 const enlarged=resizeCanvasLayer(layer,layer.width*2,layer.height*3);
 layer.points.forEach(([x,y],index)=>assert.deepEqual(enlarged.points[index],[x*2,y*3]));
 assert.throws(()=>normalizeCanvasLayer({...source,points:[]}),/invalidRequest/);
});

test('selection accounts for layer rotation and crop translates visible annotations without masks',()=>{
 const layer={type:'rect',x:100,y:100,width:100,height:20,rotation:90};
 assert.equal(pointInsideLayer([150,150],layer),true);
 assert.equal(pointInsideLayer([105,110],layer),false);
 const annotations=[{...layer,rotation:0},{type:'mask',x:20,y:20,width:10,height:10}];
 const translated=canvasLayersForCrop(annotations,[50,80,400,300]);
 assert.equal(translated.length,1); assert.equal(translated[0].x,50); assert.equal(translated[0].y,20);
 assert.equal(annotations[0].x,100); assert.equal(annotations.length,2);
});

test('page reordering preserves original page objects and boundary moves are harmless',()=>{
 const pages=[{layers:[{text:'A'}]},{layers:[{text:'B'}]},{layers:[{text:'C'}]}];
 const reordered=moveCanvasPage(pages,1,-1);
 assert.equal(reordered.index,0); assert.equal(reordered.pages[0],pages[1]); assert.equal(reordered.pages[1],pages[0]);
 assert.equal(pages[0].layers[0].text,'A');
 assert.equal(moveCanvasPage(pages,0,-1).pages,pages);
 assert.equal(moveCanvasPage(pages,2,1).pages,pages);
 assert.equal(moveCanvasPage(pages,0.5,1).pages,pages);
});

test('imported photos fit proportionally, keep small natural size, and never start outside a tiny canvas',()=>{
 const landscape=canvasImageLayer(2,4000,2000,1000,800);
 assert.equal(landscape.width,500); assert.equal(landscape.height,250); assert.equal(landscape.inputIndex,2);
 const portrait=canvasImageLayer(0,1000,4000,1000,800);
 assert.equal(portrait.width,100); assert.equal(portrait.height,400);
 const small=canvasImageLayer(0,30,20,1000,800);
 assert.equal(small.width,30); assert.equal(small.height,20);
 const tiny=canvasImageLayer(0,2000,1000,1,1); assert.ok(tiny.x>=0&&tiny.y>=0&&tiny.x+tiny.width<=1&&tiny.y+tiny.height<=1);
 for (const bad of [0,-1,NaN,Infinity]) assert.throws(()=>canvasImageLayer(0,bad,100,1000,800),/invalidRequest/);
 assert.throws(()=>canvasImageLayer(-1,100,100,1000,800),/invalidRequest/);
});

test('persisted editor preferences exclude images, text and unsupported modes and clamp numeric bounds',()=>{
 const prefs=safeCanvasPreferences({mode:'mask',color:'javascript:bad',fill:'#ABCdef',brush:-10,fontSize:5000,text:'private fixture',file:{id:'example'},layers:[{}]});
 assert.deepEqual(Object.keys(prefs).sort(),['brush','color','fill','fontSize','mode']);
 assert.equal(prefs.mode,'draw'); assert.match(prefs.color,/^#[\da-f]{6}$/i); assert.equal(prefs.fill,'#ABCdef');
 assert.equal(prefs.brush,1); assert.equal(prefs.fontSize,1000);
 assert.equal(safeCanvasPreferences({brush:Infinity,fontSize:NaN}).brush,6);
});

test('file search normalizes extensions and passes a literal directory path without executing it',()=>{
 assert.deepEqual(fileSearchFilters('PDF,.docx; pdf\nTXT','2026-01-01','2026-12-31',' /fixture/report $(echo no) '),{extensions:['.pdf','.docx','.txt'],dateFrom:'2026-01-01',dateTo:'2026-12-31',path:'/fixture/report $(echo no)'});
 assert.deepEqual(fileSearchFilters(''),{});
 assert.deepEqual(fileSearchFilters('', '', '', '/fixture'),{path:'/fixture'});
});

test('invalid file search dates, paths and extension filters never reach the indexer',()=>{
 for(const extension of ['../pdf','*.pdf','pdf/doc','x'.repeat(17),Array.from({length:21},(_,n)=>'x'+n).join(',')]) assert.throws(()=>fileSearchFilters(extension),/invalidRequest/);
 for(const date of ['2026-02-30','2026-13-01','2026-1-01']) assert.throws(()=>fileSearchFilters('',date),/invalidRequest/);
 assert.throws(()=>fileSearchFilters('','2026-12-01','2026-01-01'),/invalidRequest/);
 assert.throws(()=>fileSearchFilters('','','','a\0b'),/invalidRequest/);
 assert.throws(()=>fileSearchFilters('','','','x'.repeat(1001)),/invalidRequest/);
 for(const language of languages) for(const text of Object.values(fileSearchWords(language))) assert.ok(text.trim());
});

test('batch photo filters apply only a common percentage crop and reject invalid crop bounds',()=>{
 const options=batchImageFilters({cropX:10,cropY:20,cropWidth:80,cropHeight:50,rotate:90,brightness:1.2,layers:[{text:'ignored'}],crop:[1,2,3,4]},3);
 assert.equal(options.baseCount,3); assert.deepEqual(options.layers,[]); assert.equal(options.crop,undefined);
 assert.equal(options.rotate,90); assert.equal(options.brightness,1.2);
 for (const count of [0,1.5,101,NaN]) assert.throws(()=>batchImageFilters({},count),/invalidRequest/);
 for (const values of [{cropWidth:0},{cropX:60,cropWidth:50},{cropY:80,cropHeight:30},{cropX:true}]) assert.throws(()=>batchImageFilters(values,2),/invalidRequest/);
});

test('tool options reject non-finite image sizes and unsafe QR URL schemes',()=>{
 const image=toolTasks.find(item=>item.operation==='image_process');
 assert.throws(()=>taskOptions(image,{width:NaN}),/invalidRequest/);
 const qr=toolTasks.find(item=>item.operation==='code_generate');
 for(const text of ['javascript:alert(1)','file:///fixture','ftp://example.com']) assert.throws(()=>taskOptions(qr,{qr_type:'url',text}),/invalidRequest/);
 assert.equal(taskOptions(qr,{qr_type:'url',text:'https://example.com/'}).text,'https://example.com/');
 const wifi=taskOptions(qr,{qr_type:'wifi',ssid:'fixture;a:b',password:'fixture,code'});
 assert.match(wifi.text,/S:fixture\\;a\\:b/); assert.equal(wifi.password,undefined);
});

test('video clip boundaries reject reversed or oversized ranges and return fresh validated objects',()=>{
 const input=[{start:0,end:5},{start:10,end:20}]; assert.deepEqual(validClipRanges(input),input); assert.notEqual(validClipRanges(input)[0],input[0]);
 for(const bad of [null,[],[{start:0,end:0}],[{start:-1,end:4}],[{start:10,end:5}],[{start:0,end:121}],[{start:NaN,end:10}]]) assert.throws(()=>validClipRanges(bad),/invalidRequest/);
});

test('all ten categories and each declared tool have usable labels in five languages',()=>{
 assert.equal(toolCategories.length,10); assert.equal(new Set(toolCategories).size,10);
 for(const language of languages){const t=localToolsTranslator(language);
  for(const item of toolCategories) assert.notEqual(t('tools.'+item),'tools.'+item);
  for(const task of toolTasks){assert.notEqual(t('tools.'+task.operation),'tools.'+task.operation); for(const field of task.fields) assert.notEqual(t('tools.'+field.label),'tools.'+field.label);}
 }
 for(const row of localToolsTranslations){const expected=[...row.ko.matchAll(/\{([\w]+)\}/g)].map(match=>match[1]).sort(); for(const language of languages){assert.ok(row[language]?.trim(),row.key+' '+language);assert.deepEqual([...row[language].matchAll(/\{([\w]+)\}/g)].map(match=>match[1]).sort(),expected,row.key+' '+language);}}
});

for(const language of languages){
 test(`standalone ${language} home exposes every tool and simple capture/image/PDF starts`,()=>{
  const t=localToolsTranslator(language),html=renderToStaticMarkup(React.createElement(ToolsApp,{language,t,client:{},standalone:true}));
  assert.equal((html.match(/lt-card lt-card-/g)||[]).length,10);
  for(const item of toolCategories) assert.ok(html.includes(escapeHtml(t('tools.'+item))),item);
  for(const key of ['startCapture','openImage','openPdf']) assert.ok(html.includes(editorText(language,key)),key);
  assert.doesNotMatch(html,/>tools\.[\w.]+</);
 });
 test(`standalone ${language} phone UI explains USB approval and disables control while disconnected`,()=>{
  const t=localToolsTranslator(language),html=renderToStaticMarkup(React.createElement(PhoneControl,{client:{},t,connected:false,onError(){}}));
  for(const key of ['phoneUsbHint','phoneStart','phoneKeyboard','phoneMouse','phoneAudio','phoneClipboard']) assert.ok(html.includes(t('tools.'+key)),key);
  const start=html.match(/<button[^>]*class="lt-button primary"[^>]*>[^]*?<\/button>/)?.[0];
  assert.ok(start?.includes('disabled=""')); assert.ok(start?.includes(escapeHtml(t('tools.phoneStart'))));
  assert.doesNotMatch(html,/>tools\.[\w.]+</);
 });
}

test('capture editor exports are in the labeled top toolbar with keyboard hints and a fit control',()=>{
 const t=localToolsTranslator('en'),html=renderToStaticMarkup(React.createElement(CanvasEditor,{client:{},t,language:'en',captureSession:true,onSave:async()=>{},onCopyImage:async()=>{}}));
 const toolbar=html.indexOf('role="toolbar"'),canvas=html.indexOf('<canvas');
 assert.ok(toolbar>=0&&canvas>toolbar); assert.ok(html.includes('Ctrl/Cmd+C')); assert.ok(html.includes('Ctrl/Cmd+S')); assert.ok(html.includes(editorText('en','fit')));
 for(const key of ['pen','arrow','rectangle','text','crop','image_mosaic','copyImage','canvasSave']) assert.ok(html.includes(t('tools.'+key)),key);
 assert.match(html,/<fieldset[^>]*class="gc-editor-controls"/);
});
