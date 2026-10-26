const test=require('node:test'),assert=require('node:assert/strict'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server'),load=require('./load-source.cjs');
const {RecordingCommandGate,selectedRecordingMonitor,resolveRecordingTarget}=load('features/local-tools/recording-controls.ts');
const {RecordingControls}=load('features/local-tools/RecordingControls.tsx');
const {desktopShortcut,bindDesktopKeyboardShortcuts}=load('features/local-tools/desktop-events.ts');
const {localToolsTranslator}=load('features/local-tools/translations.ts');
const monitors=[{id:0,name:'DISPLAY1',width:1920,height:1080,primary:true},{id:1,name:'DISPLAY2',width:2560,height:1440},{id:2,name:'DISPLAY3',width:1080,height:1920}];
const health={os:'Windows',recording:false,monitors,operations:['record_start','record_stop','record_pause','record_resume']};
test('three connected monitors render once each without old size/FPS fields',()=>{
 const html=renderToStaticMarkup(React.createElement(RecordingControls,{health,paired:true,busy:false,t:localToolsTranslator('ko'),preferences:{mode:'full',monitor:2,monitorName:'DISPLAY3'},onRecord:async()=>null,onError(){}}));
 for(let n=1;n<=3;n++)assert.ok(html.includes('모니터 '+n));
 assert.equal((html.match(/class="kio-record-monitor(?: selected)?"/g)||[]).length,3);
 assert.ok(html.includes('kio-record-monitor selected'));assert.ok(!html.includes('type="number"'));assert.ok(!html.includes('상세 설정'));
});
test('selection follows device identity when enumeration changes, missing monitor never falls back silently',()=>{
 const prefs={mode:'full',monitor:2,monitorName:'DISPLAY3'};
 const changed={...health,monitors:[monitors[0],{...monitors[2],id:1}]};
 assert.equal(resolveRecordingTarget(prefs,changed).monitor,1);
 assert.equal(selectedRecordingMonitor({},health).id,0);
 assert.throws(()=>resolveRecordingTarget(prefs,{...health,monitors:[monitors[0]]}),/recordMonitorMissing/);
 assert.equal(resolveRecordingTarget({...prefs,mode:'area'},changed).mode,'area');
});
test('hotkey uses latest monitor status and stopping works even if chosen display was unplugged',async()=>{
 const calls=[],gate=new RecordingCommandGate();let status={...health};
 const ports={health:async()=>status,onHealth(){},onBusy(){},execute:async(action,options)=>{calls.push({action,options});return {status:'complete'};}};
 await gate.run('toggle',{mode:'full',monitor:2,monitorName:'DISPLAY3'},ports);
 assert.equal(calls[0].options.monitor,2);assert.ok(!('monitorName' in calls[0].options));
 status={os:'Windows',recording:true,monitors:[]};await gate.run('toggle',{mode:'full',monitor:2},ports);assert.equal(calls[1].action,'record_stop');
});
test('area recording shortcut decodes and foreground fallback dispatches one command',()=>{
 assert.equal(desktopShortcut({name:'recordArea'}),'recordArea');
 const target=new EventTarget(),events=[];const release=bindDesktopKeyboardShortcuts(target,()=>({recordArea:'Control+Shift+R'}),name=>events.push(name));
 const event=new Event('keydown',{cancelable:true});Object.assign(event,{key:'r',code:'KeyR',ctrlKey:true,shiftKey:true});target.dispatchEvent(event);release();assert.deepEqual(events,['recordArea']);assert.equal(event.defaultPrevented,true);
});
