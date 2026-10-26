const test=require('node:test');
const assert=require('node:assert/strict');
const load=require('./load-source.cjs');
const {clampFloatingToolbar,moveFloatingToolbar}=load('features/local-tools/floating-toolbar.ts');
test('dragging floating options cannot hide any edge outside the editing surface',()=>{
 const surface={width:640,height:480},toolbar={width:172,height:29};
 assert.deepEqual(clampFloatingToolbar({x:-900,y:-900},surface,toolbar),{x:6,y:6});
 assert.deepEqual(clampFloatingToolbar({x:900,y:900},surface,toolbar),{x:462,y:445});
 assert.deepEqual(clampFloatingToolbar({x:140,y:220},surface,toolbar),{x:140,y:220});
});
test('window and toolbar resizing preserves the chosen location until a boundary requires adjustment',()=>{
 const position={x:200,y:160};
 assert.deepEqual(clampFloatingToolbar(position,{width:600,height:400},{width:90,height:29}),position);
 assert.deepEqual(clampFloatingToolbar(position,{width:600,height:400},{width:220,height:29}),position);
 assert.deepEqual(clampFloatingToolbar(position,{width:300,height:170},{width:180,height:29}),{x:114,y:135});
 assert.deepEqual(clampFloatingToolbar(position,{width:80,height:20},{width:172,height:29}),{x:0,y:0});
});
test('drag positions remain finite during initial hidden or not-yet-sized surfaces',()=>{
 assert.deepEqual(clampFloatingToolbar({x:NaN,y:Infinity},{width:0,height:0},{width:0,height:0}),{x:0,y:0});
 assert.deepEqual(clampFloatingToolbar({x:-5,y:400},{width:180,height:30},{width:172,height:29}),{x:4,y:.5});
});
test('keyboard movement offers coarse, precise, and reset actions without taking export shortcuts',()=>{
 assert.deepEqual(moveFloatingToolbar({x:50,y:70},'ArrowRight'),{x:60,y:70});
 assert.deepEqual(moveFloatingToolbar({x:50,y:70},'ArrowUp',true),{x:50,y:69});
 assert.deepEqual(moveFloatingToolbar({x:50,y:70},'Home'),{x:6,y:6});
 assert.equal(moveFloatingToolbar({x:50,y:70},'s'),null);
 assert.equal(moveFloatingToolbar({x:50,y:70},'Escape'),null);
});
