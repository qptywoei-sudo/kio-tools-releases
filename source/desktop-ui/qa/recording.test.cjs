const test=require('node:test');
const assert=require('node:assert/strict');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const load=require('./load-source.cjs');
const {RecordingCommandGate,recordingActionAllowed,recordingGifOptions}=load('features/local-tools/recording-controls.ts');
const {RecordingControls}=load('features/local-tools/RecordingControls.tsx');
const {localToolsTranslator}=load('features/local-tools/translations.ts');
const actions=['record_start','record_pause','record_resume','record_stop'];
const states=[{recording:false,paused:false},{recording:true,paused:false},{recording:true,paused:true}];

test('recording buttons expose exactly the valid actions in every native state',()=>{
 const expected=[[true,false,false,false],[false,true,false,true],[false,false,true,true]];
 states.forEach((state,index)=>assert.deepEqual(actions.map(action=>recordingActionAllowed(action,state)),expected[index]));
 for(const language of ['ko','en','vi','ja','zh'])states.forEach((state,index)=>{
  const t=localToolsTranslator(language);
  const html=renderToStaticMarkup(React.createElement(RecordingControls,{health:{...state,operations:[...actions,'record_gif']},paired:true,busy:false,client:{},t,latestRecording:null,onRecord:async()=>null,onTask:async()=>{},onError(){},runGif:async()=>{}}));
  actions.forEach((action,position)=>{
   const button=html.match(new RegExp('<button[^>]*>(?:(?!</button>)[\\s\\S])*?'+t('tools.'+action)+'</button>'))?.[0];
   assert.ok(button,action);assert.equal(button.includes('disabled=""'),!expected[index][position]);
  });
  assert.ok(!html.includes('>'+t('tools.run')+'</button>'),'No second Execute action');
  assert.ok(!html.includes('tools.record'),'All recording copy is translated');
 });
});

test('each click sends one native operation and rapid duplicate/shortcut clicks are ignored',async()=>{
 const gate=new RecordingCommandGate(),calls=[],updates=[],busy=[];
 let state=states[0],release;
 const ports={health:async()=>state,onHealth:value=>updates.push(value),onBusy:value=>busy.push(value),execute:async(action,options)=>{
  calls.push({action,options});if(action==='record_start')await new Promise(resolve=>{release=resolve;});
  state=action==='record_stop'?states[0]:action==='record_pause'?states[2]:states[1];
  return {id:'test',status:'complete',result:{data:state}};
 }};
 const first=gate.run('record_start',{mode:'area',fps:30},ports);
 await Promise.resolve();
 assert.equal(await gate.run('record_start',{},ports),null);
 assert.equal(await gate.run('toggle',{},ports),null);
 release();await first;
 for(const action of ['record_pause','record_resume','record_stop'])await gate.run(action,{mode:'ignored'},ports);
 assert.deepEqual(calls.map(x=>x.action),actions.filter(x=>x!=='record_stop').concat('record_stop'));
 assert.deepEqual(calls[0].options,{mode:'area',fps:30});
 assert.ok(calls.slice(1).every(x=>Object.keys(x.options).length===0));
 assert.deepEqual(busy,[true,false,true,false,true,false,true,false]);
 assert.equal(updates.at(-1).recording,false);assert.equal(gate.pending,false);
});

test('failed/cancelled command restores native state and leaves the next valid button usable',async()=>{
 const gate=new RecordingCommandGate();let published,calls=0;
 const ports={health:async()=>states[2],onHealth:value=>{published=value;},onBusy(){},execute:async()=>{calls++;throw Error('cancelled');}};
 await assert.rejects(gate.run('record_resume',{},ports),/cancelled/);
 assert.equal(gate.pending,false);assert.equal(published.paused,true);
 assert.equal(await gate.run('record_start',{},ports),null);assert.equal(calls,1);
 ports.execute=async action=>{assert.equal(action,'record_stop');return {status:'complete'};};
 await gate.run('toggle',{},ports);
});

test('GIF ranges are explicit and non-finite/out-of-bounds inputs are rejected',()=>{
 const values={start:2,duration:3,width:720,fps:12};
 assert.deepEqual(recordingGifOptions(values),{ranges:[{start:2,end:5}],width:720,fps:12});
 for(const invalid of [{start:-1},{duration:0},{duration:121},{fps:31},{fps:2.5},{width:32},{start:Infinity},{duration:NaN}])assert.throws(()=>recordingGifOptions({...values,...invalid}),/invalidRequest/);
});
