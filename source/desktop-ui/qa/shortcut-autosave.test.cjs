const test=require('node:test'),assert=require('node:assert/strict'),React=require('react');
const load=require('./load-source.cjs');
const {GeneralSettings}=load('features/local-tools/GeneralSettings.tsx');
function walk(node,out=[]){if(!node||typeof node!=='object')return out;if(node.type?.name==='ShortcutPicker')out.push(node);for(const child of [node.props?.children].flat(Infinity))walk(child,out);return out;}
test('custom AI key is committed immediately without Apply and rejected registrations restore the old binding',async()=>{
 const originals={useState:React.useState,useEffect:React.useEffect,useContext:React.useContext,useMemo:React.useMemo};const drafts=[],calls=[];
 React.useState=v=>[v,value=>drafts.push(value)];React.useEffect=()=>{};React.useContext=()=>'ko';React.useMemo=fn=>fn();
 try{
  const settings={shortcuts:{aiTranslate:'Control+Shift+T',areaCapture:'Control+Shift+A'}};
  const tree=GeneralSettings({settings,onSettings(){throw Error('foreground must not change ahead of native commit');},permissions:{},t:x=>x,disabled:false,onPermission(){},onApply(){throw Error('Apply is unnecessary');},windows:false,onShortcutsChange:async next=>{calls.push(next);return false;}});
  const picker=walk(tree).find(n=>n.props.label==='tools.aiTranslate');assert.ok(picker);
  picker.props.onChange('Control+Shift+S');await new Promise(setImmediate);
  assert.equal(calls.length,1);assert.equal(calls[0].aiTranslate,'Control+Shift+S');assert.equal(calls[0].areaCapture,'Control+Shift+A');assert.deepEqual(drafts.at(-1),settings.shortcuts);
  picker.props.onChange('Control+Shift+A');await new Promise(setImmediate);assert.equal(calls.length,1,'duplicate shortcut must not replace global registrations');
 }finally{Object.assign(React,originals);}
});
