const test=require('node:test'),assert=require('node:assert/strict'),React=require('react');
const load=require('./load-source.cjs');
const {StartupSetting}=load('features/local-tools/StartupSetting.tsx');
const {uiText}=load('features/local-tools/tool-locale.tsx');
const {LocalAgentClient}=load('services/local-agent.ts');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function nodes(tree){return !tree||typeof tree!=='object'?[]:[tree,...React.Children.toArray(tree.props?.children).flatMap(nodes)];}
function mount(props){
 const saved={useRef:React.useRef,useState:React.useState,useContext:React.useContext,useMemo:React.useMemo},changes=[];
 React.useContext=()=>'ko';React.useMemo=fn=>fn();React.useRef=value=>({current:value});React.useState=value=>[value,next=>changes.push(next)];
 try{return {tree:StartupSetting({t:()=> 'Start at login',disabled:false,...props}),changes};}
 finally{Object.assign(React,saved);}
}
test('startup changes save immediately without an Apply action and suppress duplicate requests',async()=>{
 const calls=[];let finish;
 const {tree}=mount({settings:{autoStart:false,autoStartStatus:'disabled'},onChange:enabled=>{calls.push(enabled);return new Promise(resolve=>finish=resolve);}});
 const control=nodes(tree).find(node=>node.type==='input');
 control.props.onChange({target:{checked:true}});control.props.onChange({target:{checked:false}});
 assert.deepEqual(calls,[true]);finish(true);await tick();
 control.props.onChange({target:{checked:false}});assert.deepEqual(calls,[true,false]);finish(true);await tick();
});
test('Windows-disabled startup keeps the saved switch on and offers an explicit repair',async()=>{
 const calls=[];const {tree}=mount({settings:{autoStart:true,autoStartStatus:'blocked'},onChange:async enabled=>{calls.push(enabled);return true;}});
 const all=nodes(tree),control=all.find(node=>node.type==='input'),repair=all.find(node=>node.type==='button');
 assert.equal(control.props.checked,true);assert(repair);repair.props.onClick();await tick();assert.deepEqual(calls,[true]);
});
test('failed startup persistence reports failure and preserves the last confirmed switch',async()=>{
 const {tree,changes}=mount({settings:{autoStart:false},onChange:async()=>false});
 const control=nodes(tree).find(node=>node.type==='input');control.props.onChange({target:{checked:true}});await tick();
 assert.equal(control.props.checked,false);assert(changes.includes(true));
});
test('startup is not overwritten before settings finish loading or while disabled',async()=>{
 for(const props of [{settings:{}},{settings:{autoStart:false},disabled:true}]){
  let requests=0;const {tree}=mount({...props,onChange:async()=>{requests++;return true;}});
  const control=nodes(tree).find(node=>node.type==='input');assert(control.props.disabled);
  control.props.onChange({target:{checked:true}});await tick();assert.equal(requests,0);
 }
});
test('startup-only transport preserves native status and sends no unrelated settings',async()=>{
 const client=Object.create(LocalAgentClient.prototype),requests=[];
 client.json=async(path,method,body)=>{requests.push({path,method,body});return {settings:{autoStart:body.autoStart,autoStartStatus:body.autoStart?'enabled':'disabled'}};};
 for(const enabled of [true,false]){
  const saved=await client.applySettings({autoStart:enabled});assert.equal(saved.autoStart,enabled);
  assert.deepEqual(requests.at(-1),{path:'/settings',method:'PATCH',body:{autoStart:enabled}});
 }
});
test('startup notices and repair actions have all six language copies',()=>{
 for(const text of ['자동 실행 설정을 저장했습니다.','스위치를 변경하면 바로 저장됩니다.','자동 실행 복구','자동 실행 설정을 저장하지 못했습니다. 다시 시도해 주세요.']){
  for(const language of ['vi','en','ko','ja','zh-TW','zh']){
   const translated=uiText(language,text);assert(translated.trim());if(language!=='ko')assert.notEqual(translated,text);
  }
 }
});
