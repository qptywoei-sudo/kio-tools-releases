// Real helper tests with explicitly mocked clipboard receipts. No screen or clipboard access.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const load = require('./load-source.cjs');
const {editorShortcut, createEditorExportController, fitEditorImage} = load('features/local-tools/editor-shortcuts.ts');
const {textCopyHasPriority, isImageCopyShortcut, createImageCopyController, writePngToBrowserClipboard} = load('features/local-tools/capture-copy.ts');
const key = (letter, modifiers = {}) => ({key:letter, ctrlKey:true, metaKey:false, altKey:false,
  shiftKey:false, defaultPrevented:false, ...modifiers});
function deferred() {let resolve, reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}

for (const modifier of ['ctrlKey', 'metaKey']) {
  test(`${modifier}: C/S/Z/Shift-Z/Y select the intended editor action`, () => {
    const keys = {ctrlKey:false, metaKey:false, [modifier]:true};
    for (const [letter, expected] of [['c','copy'],['C','copy'],['s','save'],['S','save'],['z','undo'],['y','redo']]) {
      assert.equal(editorShortcut(key(letter,keys)),expected);
    }
    assert.equal(editorShortcut(key('Z',{...keys,shiftKey:true})),'redo');
  });
}
test('reserved combinations, prior handlers, and plain typing are not intercepted', () => {
  for (const event of [key('c',{ctrlKey:false}), key('s',{altKey:true}), key('c',{shiftKey:true}),
    key('s',{shiftKey:true}),key('y',{shiftKey:true}),key('z',{defaultPrevented:true}),key('x')]) {
    assert.equal(editorShortcut(event),null);
  }
});
for (const firstAction of ['copy', 'save']) {
  test(`${firstAction} and the other export share one lock and close only after its receipt`, async () => {
    const controller=createEditorExportController(), receipt=deferred();
    const runs=[],closed=[];
    const first=controller.perform({run:()=>{runs.push(firstAction);return receipt.promise;},onSuccess:()=>closed.push(firstAction)});
    assert.equal(controller.busy,true);assert.deepEqual(closed,[]);
    assert.equal(await controller.perform({run:async()=>runs.push('second'),onSuccess:()=>closed.push('second')}),false);
    assert.deepEqual(runs,[firstAction]);
    receipt.resolve();assert.equal(await first,true);assert.deepEqual(closed,[firstAction]);assert.equal(controller.busy,false);
    assert.equal(await controller.perform({run:async()=>runs.push('retry'),onSuccess:()=>closed.push('retry')}),true);
    assert.deepEqual(closed,[firstAction,'retry']);
  });
}
test('an export failure keeps the editor open and permits a successful retry', async () => {
  const controller=createEditorExportController();let closed=0;
  await assert.rejects(controller.perform({run:async()=>{throw Error('disk full');},onSuccess:()=>closed++}),/disk full/);
  assert.equal(closed,0);assert.equal(controller.busy,false);
  assert.equal(await controller.perform({run:async()=>{},onSuccess:()=>closed++}),true);assert.equal(closed,1);
});
test('a stale image or dismissed editor is never closed by a late export receipt', async () => {
  const controller=createEditorExportController(), receipt=deferred();let current=true,closed=0;
  const result=controller.perform({run:()=>receipt.promise,isCurrent:()=>current,onSuccess:()=>closed++});
  current=false;receipt.resolve();assert.equal(await result,true);assert.equal(closed,0);assert.equal(controller.busy,false);
});
test('the export gate is released even if a success callback fails', async () => {
  const controller=createEditorExportController();
  await assert.rejects(controller.perform({run:async()=>{},onSuccess:()=>{throw Error('closed host');}}),/closed host/);
  assert.equal(controller.busy,false);assert.equal(await controller.perform({run:async()=>{}}),true);
});
test('fit keeps tall, wide, square, and Retina images completely within the viewport', () => {
  for (const [width,height,availableWidth,availableHeight] of [[1200,9000,900,500],[9000,1200,900,500],
    [6000,6000,320,240],[3840,2160,1000,600]]) {
    const scale=fitEditorImage(width,height,availableWidth,availableHeight);
    assert.ok(scale>0&&scale<=1);assert.ok(width*scale<=availableWidth+1e-9);assert.ok(height*scale<=availableHeight+1e-9);
  }
  assert.equal(fitEditorImage(100,50,900,500),1);
});
test('invalid or not-yet-loaded image dimensions never produce NaN or Infinity scale', () => {
  for (const dimensions of [[0,100,900,500],[100,0,900,500],[100,100,0,500],[Infinity,100,900,500],
    [100,NaN,900,500],[-100,50,900,500]]) assert.equal(fitEditorImage(...dimensions),1);
});
test('native text selection, inherited editable fields and inputs retain copy priority', () => {
  const field={closest:()=>({}),isContentEditable:false};
  assert.equal(textCopyHasPriority(field,{isCollapsed:true}),true);
  assert.equal(textCopyHasPriority({parentElement:field},null),true);
  assert.equal(textCopyHasPriority({isContentEditable:true,closest:()=>null},null),true);
  assert.equal(textCopyHasPriority({closest:()=>null},{isCollapsed:false}),true);
  assert.equal(textCopyHasPriority({closest:()=>null},{isCollapsed:true}),false);
  assert.equal(textCopyHasPriority(null,null),false);
});
test('the image-copy helper accepts ordinary Ctrl/Cmd+C only', () => {
  assert.equal(isImageCopyShortcut(key('c')),true);assert.equal(isImageCopyShortcut(key('C',{ctrlKey:false,metaKey:true})),true);
  for (const event of [key('c',{altKey:true}),key('c',{shiftKey:true}),key('c',{defaultPrevented:true}),key('s')]) {
    assert.equal(isImageCopyShortcut(event),false);
  }
});
test('legacy capture-copy policy respects explicit keep-open and non-capture editors', async () => {
  for (const policy of [{captureSession:true,closeAfterCaptureCopy:false},{captureSession:false}]) {
    let closed=0;
    assert.equal(await createImageCopyController().copy({...policy,copy:async()=>{},onCopySuccess:()=>closed++}),true);
    assert.equal(closed,0);
  }
});
function clipboardFixture() {
  const descriptors={navigator:Object.getOwnPropertyDescriptor(globalThis,'navigator'),ClipboardItem:Object.getOwnPropertyDescriptor(globalThis,'ClipboardItem')};
  const receipt=deferred();let payload,writes=0;
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{clipboard:{write:()=>{writes++;return receipt.promise;}}}});
  Object.defineProperty(globalThis,'ClipboardItem',{configurable:true,value:class{constructor(data){payload=data;}}});
  return {receipt,get payload(){return payload;},get writes(){return writes;},restore(){
    for(const [name,descriptor]of Object.entries(descriptors))if(descriptor)Object.defineProperty(globalThis,name,descriptor);else delete globalThis[name];
  }};
}
test('browser image clipboard starts inside user activation and awaits rendering plus write receipt', async () => {
  const fixture=clipboardFixture(),render=deferred();
  try {
    let done=false;const pending=writePngToBrowserClipboard(render.promise).then(()=>{done=true;});
    assert.equal(fixture.writes,1);assert.deepEqual(Object.keys(fixture.payload),['image/png']);
    const image=new Blob(['mock pixels'],{type:'image/png'});render.resolve(image);
    assert.equal(await fixture.payload['image/png'],image);assert.equal(done,false);
    fixture.receipt.resolve();await pending;assert.equal(done,true);
  }finally{fixture.restore();}
});
test('failed clipboard write and invalid raster never report successful completion', async () => {
  for(const failure of ['permission','empty','jpeg']) {
    const fixture=clipboardFixture();
    try {
      const image=failure==='empty'?new Blob([],{type:'image/png'}):new Blob(['mock'],{type:failure==='jpeg'?'image/jpeg':'image/png'});
      const pending=writePngToBrowserClipboard(Promise.resolve(image));
      if(failure==='permission')fixture.receipt.reject(Error('NotAllowedError'));else fixture.receipt.resolve();
      await assert.rejects(pending,failure==='permission'?/NotAllowedError/:/processingFailed/);
    }finally{fixture.restore();}
  }
});

test('plain Delete and Mac Backspace remove selected objects without taking text shortcuts',()=>{
 const {isEditorDeleteShortcut}=load('features/local-tools/editor-shortcuts.ts');
 for(const letter of ['Delete','Backspace']){
  const event=key(letter,{ctrlKey:false});assert.equal(isEditorDeleteShortcut(event),true);
  for(const modifier of ['ctrlKey','metaKey','altKey','shiftKey','defaultPrevented'])assert.equal(isEditorDeleteShortcut({...event,[modifier]:true}),false);
 }
 assert.equal(isEditorDeleteShortcut(key('a',{ctrlKey:false})),false);
});
