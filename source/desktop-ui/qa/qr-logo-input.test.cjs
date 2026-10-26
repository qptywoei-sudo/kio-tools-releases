const test=require('node:test'),assert=require('node:assert/strict'),React=require('react');
const load=require('./load-source.cjs');
const {QrLogoControls}=load('features/local-tools/QrLogoControls.tsx');
const image=load('features/local-tools/qr-logo-image.ts');

function mount(props){
 const saved={useRef:React.useRef,useState:React.useState,useEffect:React.useEffect,useContext:React.useContext,useMemo:React.useMemo,window:global.window};
 const cleanups=[],listeners={};
 React.useContext=()=>'ko';React.useMemo=fn=>fn();React.useRef=value=>({current:value});React.useState=value=>[value,()=>{}];
 React.useEffect=effect=>{const cleanup=effect();if(cleanup)cleanups.push(cleanup);};
 global.window={addEventListener:(name,fn)=>listeners[name]=fn,removeEventListener:(name,fn)=>{if(listeners[name]===fn)delete listeners[name];}};
 let tree;
 try{tree=QrLogoControls(props);}finally{React.useRef=saved.useRef;React.useState=saved.useState;React.useEffect=saved.useEffect;React.useContext=saved.useContext;React.useMemo=saved.useMemo;}
 return {tree,listeners,close(){for(const cleanup of cleanups)cleanup();global.window=saved.window;}};
}
function event(file){return {defaultPrevented:false,clipboardData:{items:[],files:[file]},dataTransfer:{items:[],files:[file]},preventDefault(){this.defaultPrevented=true;},stopPropagation(){this.stopped=true;}};}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
test('real QR handlers consume a paste once and block simultaneous drop uploads',async()=>{
 const previous=image.loadQrLogo,changes=[],busy=[];let finish,uploads=0;
 image.loadQrLogo=()=>new Promise(resolve=>finish=resolve);
 const mounted=mount({client:{upload:async()=>{uploads++;return {id:'safe'};}},value:null,disabled:false,onChange:value=>changes.push(value),onBusyChange:value=>busy.push(value)});
 try{
  const file=new File(['png'],'clipboard.png',{type:'image/png'}),paste=event(file),drop=event(file);
  mounted.listeners.paste(paste);mounted.tree.props.onDrop(drop);
  assert(paste.defaultPrevented);assert(drop.defaultPrevented&&drop.stopped);
  finish({name:file.name,dataUrl:'data:image/png;base64,aQ==',width:1,height:1});await tick();
  assert.equal(uploads,1);assert.equal(changes.length,1);assert.equal(changes[0].shape,'square');assert.deepEqual(busy,[true,false]);
 }finally{mounted.close();image.loadQrLogo=previous;}
});
test('drop keeps the selected circle shape and upload errors preserve the previous logo',async()=>{
 const previous=image.loadQrLogo,changes=[],busy=[];
 image.loadQrLogo=async file=>({name:file.name,dataUrl:'data:image/png;base64,aQ==',width:1,height:1});
 const mounted=mount({client:{upload:async()=>({id:'safe'})},value:{shape:'circle',file:{id:'previous'},asset:{name:'previous.png',dataUrl:'data:image/png;base64,aQ==',width:1,height:1}},disabled:false,onChange:value=>changes.push(value),onBusyChange:value=>busy.push(value)});
 try{
  mounted.tree.props.onDrop(event(new File(['png'],'dropped.png',{type:'image/png'})));await tick();assert.equal(changes[0].shape,'circle');
  image.loadQrLogo=async()=>{throw Error('invalid-image');};
  mounted.listeners.paste(event(new File(['bad'],'bad.png',{type:'image/png'})));await tick();
  assert.equal(changes.length,1);assert.deepEqual(busy,[true,false,true,false]);
 }finally{mounted.close();image.loadQrLogo=previous;}
});
test('leaving the QR editor cancels stale completion and removes its paste listener',async()=>{
 const previous=image.loadQrLogo,changes=[];let finish;
 image.loadQrLogo=()=>new Promise(resolve=>finish=resolve);
 const mounted=mount({client:{upload:async()=>({id:'safe'})},value:null,disabled:false,onChange:value=>changes.push(value),onBusyChange(){}});
 try{
  mounted.listeners.paste(event(new File(['png'],'clipboard.png',{type:'image/png'})));mounted.close();assert.equal(mounted.listeners.paste,undefined);
  finish({name:'clipboard.png',dataUrl:'data:image/png;base64,aQ==',width:1,height:1});await tick();assert.equal(changes.length,0);
 }finally{image.loadQrLogo=previous;}
});
