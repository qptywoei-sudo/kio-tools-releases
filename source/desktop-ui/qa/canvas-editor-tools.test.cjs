const test=require('node:test');
const assert=require('node:assert/strict');
const load=require('./load-source.cjs');
const {changeEditorCrop,cropHandlePoints,editorTextSize}=load('features/local-tools/canvas-editor-tools.ts');

test('moving crop preserves its dimensions and cannot leave the image',()=>{
 assert.deepEqual(changeEditorCrop([100,80,300,200],-500,1000,800,600),[0,400,300,200]);
 assert.deepEqual(changeEditorCrop([100,80,300,200],50,-20,800,600),[150,60,300,200]);
});
test('all crop handles adjust their own edges and support dragging across the opposite corner',()=>{
 assert.deepEqual(cropHandlePoints([100,80,300,200]).se,[400,280]);
 assert.deepEqual(changeEditorCrop([100,80,300,200],1000,-500,800,600,'ne'),[100,0,700,280]);
 assert.deepEqual(changeEditorCrop([100,80,300,200],-350,-250,800,600,'se'),[50,30,50,50]);
 assert.deepEqual(changeEditorCrop([100,80,300,200],50,50,800,600,'s'),[100,80,300,250]);
 assert.deepEqual(changeEditorCrop([100,80,300,200],50,50,800,600,'w'),[150,80,250,200]);
});
test('inline multiline text bounds use the same font metrics as its exported annotation',()=>{
 const measures={ABC:42,'가나다':84};
 assert.deepEqual(editorTextSize('ABC\n가나다',28,line=>measures[line]),{width:92,height:78});
 assert.deepEqual(editorTextSize('',28,()=>0),{width:40,height:43});
});
