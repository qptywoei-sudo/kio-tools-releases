import {useEffect,useRef,useState,type PointerEvent} from 'react';
import {Brush,Check,Download,Eraser,LoaderCircle,Redo2,Sparkles,Undo2,X} from 'lucide-react';
import type {LocalAgentClient} from '@/services/local-agent';
import {decodeToolImage} from './image-resource';
import {clamp,photoBlob,photoCanvas} from './photo-studio';
import {useToolsLocale} from './tool-locale';
import './subject-selection.css';

type Point={x:number;y:number};
export function SubjectSelectionDialog(props:{source:HTMLCanvasElement;client:LocalAgentClient;onApply:(canvas:HTMLCanvasElement)=>void;onCancel:()=>void}){
 const{ui}=useToolsLocale(),dialog=useRef<HTMLDialogElement>(null);
 useEffect(()=>{dialog.current?.showModal();return()=>dialog.current?.close();},[]);
 return <dialog ref={dialog} className="subject-modal" aria-label={ui('AI 대상 선택')} onCancel={event=>{event.preventDefault();props.onCancel();}}><header><strong>{ui('AI 대상 선택')}</strong></header><SubjectSelection {...props}/></dialog>;
}
export function copyMask(mask:HTMLCanvasElement){const c=photoCanvas(mask.width,mask.height);c.getContext('2d')!.drawImage(mask,0,0);return c;}
export function paintSubjectMask(mask:HTMLCanvasElement,points:Point[],radius:number,keep:boolean){
 if(!points.length)return;const c=mask.getContext('2d')!;c.save();c.globalCompositeOperation=keep?'source-over':'destination-out';c.fillStyle=c.strokeStyle='#fff';c.lineWidth=radius*2;c.lineCap=c.lineJoin='round';c.beginPath();points.forEach((p,i)=>i?c.lineTo(p.x,p.y):c.moveTo(p.x,p.y));c.stroke();for(const p of [points[0],points.at(-1)!]){c.beginPath();c.arc(p.x,p.y,radius,0,Math.PI*2);c.fill();}c.restore();
}
export function applySubjectMask(source:HTMLCanvasElement,mask:HTMLCanvasElement,trim=false,feather=0){
 const output=copyMask(source),ctx=output.getContext('2d')!;ctx.globalCompositeOperation='destination-in';ctx.filter=feather>0?`blur(${feather}px)`:'none';ctx.drawImage(mask,0,0,source.width,source.height);ctx.filter='none';ctx.globalCompositeOperation='source-over';
 if(!trim)return output;
 const pixels=mask.getContext('2d')!.getImageData(0,0,mask.width,mask.height).data;let left=mask.width,top=mask.height,right=-1,bottom=-1;
 for(let y=0;y<mask.height;y++)for(let x=0;x<mask.width;x++)if(pixels[(y*mask.width+x)*4+3]>4){left=Math.min(left,x);right=Math.max(right,x);top=Math.min(top,y);bottom=Math.max(bottom,y);}
 if(right<left)return output;
 const sx=source.width/mask.width,sy=source.height/mask.height,x=Math.floor(left*sx),y=Math.floor(top*sy),w=Math.min(source.width-x,Math.ceil((right+1)*sx)-x),h=Math.min(source.height-y,Math.ceil((bottom+1)*sy)-y),cropped=photoCanvas(w,h);cropped.getContext('2d')!.drawImage(output,x,y,w,h,0,0,w,h);return cropped;
}
export function SubjectSelection({source,client,onApply,onCancel,onSave}:{source:HTMLCanvasElement;client:LocalAgentClient;onApply?:(canvas:HTMLCanvasElement)=>void;onCancel?:()=>void;onSave?:(blob:Blob)=>Promise<void>}){
 const{ui}=useToolsLocale();
 const scale=Math.min(1,2048/Math.max(source.width,source.height));
 const[mask,setMask]=useState(()=>photoCanvas(source.width*scale,source.height*scale)),[undo,setUndo]=useState<HTMLCanvasElement[]>([]),[redo,setRedo]=useState<HTMLCanvasElement[]>([]),[keep,setKeep]=useState(true),[radius,setRadius]=useState(24),[trim,setTrim]=useState(false),[feather,setFeather]=useState(1),[showMask,setShowMask]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[revision,setRevision]=useState(0);
 const canvas=useRef<HTMLCanvasElement>(null),stroke=useRef<{before:HTMLCanvasElement;points:Point[];keep:boolean;radius:number}|null>(null),live=useRef(true),request=useRef(0),jobId=useRef(''),upload=useRef<Promise<string>|null>(null),maskRef=useRef(mask);
 maskRef.current=mask;
 const historyLimit=Math.min(20,Math.max(2,Math.floor(33554432/(mask.width*mask.height))));
 function remember(before:HTMLCanvasElement){setUndo(items=>[...items,before].slice(-historyLimit));setRedo([]);}
 function step(back:boolean){const list=back?undo:redo,item=list.at(-1);if(!item||busy||stroke.current)return;if(back){setRedo(items=>[...items,copyMask(mask)].slice(-historyLimit));setUndo(items=>items.slice(0,-1));}else{setUndo(items=>[...items,copyMask(mask)].slice(-historyLimit));setRedo(items=>items.slice(0,-1));}setMask(item);}
 async function autoSelect(){if(busy)return;const seq=++request.current;setBusy(true);setError('');
  try{
   if(!upload.current)upload.current=photoBlob(source).then(blob=>client.upload(new File([blob],'subject-selection.png',{type:'image/png'}))).then(file=>file.id).catch(e=>{upload.current=null;throw e;});
   const id=await upload.current;if(!live.current||seq!==request.current)return;
   let{job}=await client.jobs('image_background',[id],{segmentation:'ai',previewOnly:true,trim:false,maskOnly:true,format:'png'});jobId.current=job.id;
   if(!live.current||seq!==request.current){void client.cancel(job.id).catch(()=>{});return;}
   const deadline=Date.now()+60000;
   while(!['complete','completed','failed','cancelled'].includes(job.status)){
    if(Date.now()>deadline){void client.cancel(job.id).catch(()=>{});throw Error('timeout');}
    await new Promise(resolve=>setTimeout(resolve,160));if(!live.current||seq!==request.current)return;job=(await client.job(job.id)).job;
   }
   if(!['complete','completed'].includes(job.status))throw Error(job.errorCode??'failed');
   const file=(job.artifacts??job.result?.files??job.result?.artifacts??[])[0];if(!file)throw Error('missing');
   const decoded=await decodeToolImage(await client.artifact(file.id));
   try{if(!live.current||seq!==request.current)return;const next=photoCanvas(mask.width,mask.height),ctx=next.getContext('2d')!;ctx.drawImage(decoded,0,0,next.width,next.height);ctx.globalCompositeOperation='source-in';ctx.fillStyle='#fff';ctx.fillRect(0,0,next.width,next.height);ctx.globalCompositeOperation='source-over';remember(copyMask(maskRef.current));setMask(next);setShowMask(true);}finally{decoded.close();}
  }catch{if(live.current&&seq===request.current)setError(ui('자동 선택하지 못했습니다. 다시 시도하거나 붓으로 영역을 지정해 주세요.'));}
  finally{if(live.current&&seq===request.current){setBusy(false);jobId.current='';}}
 }
 function cancel(){request.current++;if(jobId.current)void client.cancel(jobId.current).catch(()=>{});jobId.current='';setBusy(false);}
 useEffect(()=>{live.current=true;const timer=setTimeout(()=>void autoSelect(),0);return()=>{clearTimeout(timer);live.current=false;request.current++;if(jobId.current)void client.cancel(jobId.current).catch(()=>{});};},[]);
 useEffect(()=>{const target=canvas.current;if(!target)return;target.width=mask.width;target.height=mask.height;const ctx=target.getContext('2d')!;ctx.clearRect(0,0,target.width,target.height);ctx.drawImage(source,0,0,target.width,target.height);if(showMask){const tint=copyMask(mask),tc=tint.getContext('2d')!;tc.globalCompositeOperation='source-in';tc.fillStyle='rgba(38,210,113,.52)';tc.fillRect(0,0,tint.width,tint.height);ctx.drawImage(tint,0,0);}else{ctx.clearRect(0,0,target.width,target.height);ctx.drawImage(source,0,0,target.width,target.height);ctx.globalCompositeOperation='destination-in';ctx.drawImage(mask,0,0);ctx.globalCompositeOperation='source-over';}},[source,mask,showMask,revision]);
 function point(e:PointerEvent<HTMLCanvasElement>){const r=e.currentTarget.getBoundingClientRect();return{x:clamp((e.clientX-r.left)*mask.width/r.width,0,mask.width),y:clamp((e.clientY-r.top)*mask.height/r.height,0,mask.height)};}
 function validSelection(){const data=mask.getContext('2d')!.getImageData(0,0,mask.width,mask.height).data;for(let i=3;i<data.length;i+=4)if(data[i]>4)return true;setError(ui('남길 영역을 먼저 선택해 주세요.'));return false;}
 async function save(){if(!validSelection())return;setBusy(true);setError('');try{await onSave?.(await photoBlob(applySubjectMask(source,mask,trim,feather)));}catch{if(live.current)setError(ui('사진을 저장하지 못했습니다. 다시 시도해 주세요.'));}finally{if(live.current)setBusy(false);}}
 return <section className="subject-selection" aria-label={ui('AI 대상 선택')} tabIndex={-1} onKeyDown={e=>{if(e.key==='Escape'&&onCancel){e.preventDefault();e.stopPropagation();onCancel();return;}if((e.target as HTMLElement).closest('input'))return;if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();e.stopPropagation();step(!e.shiftKey);}}}>
  <div className="ps-toolbar"><button className="ps-primary" disabled={busy} onClick={()=>void autoSelect()}><Sparkles size={16}/>{ui('AI 자동 선택')}</button><div className="ps-segments"><button aria-pressed={keep} className={keep?'is-active':''} disabled={busy} onClick={()=>{setKeep(true);setShowMask(true);}}><Brush size={16}/>{ui('남길 부분')}</button><button aria-pressed={!keep} className={!keep?'is-active':''} disabled={busy} onClick={()=>{setKeep(false);setShowMask(true);}}><Eraser size={16}/>{ui('지울 부분')}</button></div><label className="subject-radius">{ui('붓 크기')}<input type="range" min={2} max={150} value={radius} disabled={busy} onChange={e=>setRadius(Number(e.target.value))}/></label><button className="ps-icon" title={ui('한 단계 되돌리기')} aria-label={ui('한 단계 되돌리기')} disabled={busy||!undo.length} onClick={()=>step(true)}><Undo2 size={18}/></button><button className="ps-icon" title={ui('다시 실행')} aria-label={ui('다시 실행')} disabled={busy||!redo.length} onClick={()=>step(false)}><Redo2 size={18}/></button><button className="ps-icon" title={ui('선택 영역 비우기')} aria-label={ui('선택 영역 비우기')} disabled={busy} onClick={()=>{remember(copyMask(mask));setMask(photoCanvas(mask.width,mask.height));setError('');}}><Eraser size={17}/></button><div className="ps-toolbar-end">{onApply&&<button className="ps-primary" disabled={busy} onClick={()=>{if(validSelection())onApply(applySubjectMask(source,mask,trim,feather));}}><Check size={16}/>{ui('선택 적용')}</button>}{onSave&&<button className="ps-primary" disabled={busy} onClick={()=>void save()}><Download size={16}/>{ui('PNG 저장')}</button>}{onCancel&&<button className="ps-icon" title={ui('취소')} aria-label={ui('취소')} onClick={onCancel}><X size={18}/></button>}</div></div>
  <div className="ps-context"><span>{ui('초록색 영역이 남습니다. 붓으로 더하거나 지우고 Ctrl+Z로 되돌리세요.')}</span><label><input type="checkbox" checked={trim} onChange={e=>setTrim(e.target.checked)}/>{ui('대상 크기로 자르기')}</label><label className="subject-radius">{ui('경계 부드럽게')}<input aria-label={ui('경계 부드럽게')} type="range" min={0} max={4} step={.5} value={feather} disabled={busy} onChange={e=>setFeather(Number(e.target.value))}/></label><button className="ps-button" onClick={()=>setShowMask(v=>!v)}>{showMask?ui('누끼 결과 보기'):ui('선택 영역 보기')}</button></div>
  {error&&<p role="alert" className="ps-alert">{error}</p>}
  <div className="ps-stage subject-stage"><canvas ref={canvas} tabIndex={0} aria-label={ui('붓으로 선택 영역 수정')} onPointerDown={e=>{if(busy||e.button!==0)return;e.currentTarget.focus({preventScroll:true});const p=point(e);stroke.current={before:copyMask(mask),points:[p],keep,radius};paintSubjectMask(mask,[p],radius,keep);e.currentTarget.setPointerCapture(e.pointerId);setRevision(n=>n+1);}} onPointerMove={e=>{const s=stroke.current;if(!s||busy)return;const p=point(e),previous=s.points.at(-1)!;s.points.push(p);paintSubjectMask(mask,[previous,p],s.radius,s.keep);setRevision(n=>n+1);}} onPointerUp={e=>{const s=stroke.current;if(s){remember(s.before);stroke.current=null;setRevision(n=>n+1);}if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);}} onPointerCancel={()=>{if(stroke.current)setMask(stroke.current.before);stroke.current=null;setRevision(n=>n+1);}}/>
  {busy&&<div className="subject-busy" role="status"><LoaderCircle className="ps-spin" size={22}/><span>{ui('AI가 대상을 선택하고 있습니다…')}</span><button className="ps-button" onClick={cancel}>{ui('취소')}</button></div>}</div><p className="subject-note">{ui('PC에서 처리합니다. 사진은 외부 AI 서버로 전송되지 않습니다.')}</p>
 </section>;
}
