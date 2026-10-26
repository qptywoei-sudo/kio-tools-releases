const test=require('node:test');
const assert=require('node:assert/strict');
const load=require('./load-source.cjs');
const {emptyVideoProject,timelineClips,splitVideoItem,videoExportOptions,projectDuration}=load('features/local-tools/video-editor.ts');
const clip={id:'clip',source:'source-one',kind:'video',start:4,end:10,volume:.6};
test('split a trimmed video at project time preserves all source samples and soundtrack levels',()=>{
 const p={...emptyVideoProject(),clips:[{...clip,id:'first',start:0,end:2},clip]};
 const result=splitVideoItem(p,{kind:'clip',id:'clip'},4,'second');
 assert.deepEqual(result.clips.slice(1).map(c=>[c.start,c.end,c.volume]),[[4,6,.6],[6,10,.6]]);
 assert.deepEqual(timelineClips(result.clips).map(c=>c.at),[0,2,4]);assert.equal(projectDuration(result),8);
 assert.deepEqual(p.clips[1],clip);
});
test('split music retains source trim and positions the second segment without a gap',()=>{
 const p={...emptyVideoProject(),audio:[{id:'song',source:'music',start:6,end:12,at:3,volume:.4}]};
 const result=splitVideoItem(p,{kind:'audio',id:'song'},5,'tail');
 assert.deepEqual(result.audio.map(c=>[c.start,c.end,c.at]),[[6,8,3],[8,12,5]]);assert.equal(projectDuration(result),9);
 assert.equal(splitVideoItem(p,{kind:'audio',id:'song'},3,'tail'),p);
});
test('text and overlay splitting keeps time coverage and independent editable copies',()=>{
 const p={...emptyVideoProject(),texts:[{id:'caption',text:'안녕하세요',start:2,end:7,x:.5,y:.8,fontSize:32,color:'#fff',background:true}]};
 const result=splitVideoItem(p,{kind:'text',id:'caption'},4,'caption2');
 assert.deepEqual(result.texts.map(c=>[c.id,c.start,c.end]),[['caption',2,4],['caption2',4,7]]);
});
test('export maps stable source IDs to current input indices and excludes UI identifiers',()=>{
 const p={...emptyVideoProject(),clips:[clip],audio:[{id:'song',source:'music',start:0,end:3,at:2,volume:1}]};
 const options=videoExportOptions(p,['music','source-one'],1280,720);
 assert.equal(options.clips[0].source,1);assert.equal(options.audio[0].source,0);assert.equal('id'in options.clips[0],false);assert.equal(options.format,'mp4');
 assert.throws(()=>videoExportOptions(p,['source-one'],1280,720),/파일/);
});

test('split limits prevent creating a project the renderer would reject',()=>{
 const p={...emptyVideoProject(),clips:Array.from({length:60},(_,i)=>({...clip,id:String(i)}))};
 assert.equal(splitVideoItem(p,{kind:'clip',id:'0'},2,'extra'),p);
});
test('audio export preserves the full project duration while excluding visual overlays',()=>{
 const p={...emptyVideoProject(),clips:[clip],texts:[{id:'text',text:'tail',start:7,end:9,x:.5,y:.8,fontSize:40,color:'#ffffff',background:true}]};
 const options=videoExportOptions(p,['source-one'],1280,720,'m4a');assert.equal(options.duration,9);assert.equal(options.clips.length,1);assert.deepEqual(options.texts,[]);assert.deepEqual(options.overlays,[]);
});
