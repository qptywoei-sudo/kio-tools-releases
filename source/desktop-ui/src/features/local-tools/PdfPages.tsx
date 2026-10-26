import {useEffect,useMemo,useRef,useState} from 'react';
import {ArrowDown,ArrowUp,RotateCw,Trash2,Undo2} from 'lucide-react';
import type {AgentFile,AgentJob,ToolLanguage,ToolTranslate} from './types';
import type {LocalAgentClient} from '@/services/local-agent';
import {movePdfPage,moveSelectedPdfPages,pdfPageBatch,pdfPageOrder,PdfThumbnailLoader,removeSelectedPdfPages,selectedPdfPages} from './pdf-workspace';
import {pdfWorkspaceCopy} from './pdf-workspace-copy';
import './pdf-workspace.css';
export {movePdfPage} from './pdf-workspace';
type PageSnapshot={order:number[];rotations:Record<string,number>;current:number};
export function PdfPages({client,file,t,run,onChange,onAnnotate,onExtract,previewPage,onPreviewPage,language='ko'}:{client:LocalAgentClient;file:AgentFile;t:ToolTranslate;run:(operation:string,inputs:string[],options:Record<string,unknown>)=>Promise<AgentJob>;onChange:(order:number[],rotations:Record<string,number>)=>void;onAnnotate:(file:AgentFile,page:number)=>void;onExtract?:(pages:number[])=>void;previewPage?:number;onPreviewPage?:(page:number,rotation:number)=>void;language?:ToolLanguage}){
 const [order,setOrder]=useState<number[]>([]),[rotations,setRotations]=useState<Record<string,number>>({}),[thumbs,setThumbs]=useState<Record<number,AgentFile>>({}),[loading,setLoading]=useState(true),[loadingThumbs,setLoadingThumbs]=useState(false),[error,setError]=useState(false),[thumbError,setThumbError]=useState(false),[annotating,setAnnotating]=useState(false),[current,setCurrent]=useState(1),[selected,setSelected]=useState<number[]>([]),[batch,setBatch]=useState(0),[total,setTotal]=useState(0),[reload,setReload]=useState(0),[retryThumbs,setRetryThumbs]=useState(0),[history,setHistory]=useState<PageSnapshot[]>([]);
 const callbacks=useRef({run,onChange,onAnnotate,onPreviewPage}),generation=useRef(0),loader=useRef(new PdfThumbnailLoader());
 callbacks.current={run,onChange,onAnnotate,onPreviewPage};
 useEffect(()=>{if(previewPage&&order.includes(previewPage))setCurrent(previewPage);},[previewPage,order]);
 useEffect(()=>{callbacks.current.onPreviewPage?.(current,rotations[String(current)]??0);},[current,rotations]);
 const copy=pdfWorkspaceCopy(language),view=useMemo(()=>pdfPageBatch(order,batch),[order,batch]),busy=loading||annotating;
 const visibleKey=view.pages.join(','),selectedOrder=selectedPdfPages(order,selected);
 useEffect(()=>{
  let active=true;const revision=++generation.current;loader.current.reset();setLoading(true);setError(false);setThumbError(false);setThumbs({});setOrder([]);setRotations({});setSelected([]);setHistory([]);setTotal(0);setBatch(0);setCurrent(1);setAnnotating(false);callbacks.current.onChange([],{});
  void callbacks.current.run('pdf_info',[file.id],{}).then(job=>{
   const pages=pdfPageOrder(Number(job.result?.data?.page_count??job.data?.page_count));
   if(!active||revision!==generation.current)return;
   setOrder(pages);setTotal(pages.length);callbacks.current.onChange(pages,{});
  }).catch(()=>{if(active&&revision===generation.current)setError(true);}).finally(()=>{if(active&&revision===generation.current)setLoading(false);});
  return()=>{active=false;generation.current++;loader.current.reset();};
 },[client,file.id,reload]);
 useEffect(()=>{
  if(!view.pages.length||loading)return;
  let active=true;const revision=generation.current;setThumbs(loader.current.cached(view.pages));setLoadingThumbs(true);setThumbError(false);
  void loader.current.load(view.pages,async pages=>{
   const job=await callbacks.current.run('pdf_render',[file.id],{pages:pages.join(','),dpi:72,format:'png',previewOnly:true});
   return job.result?.files??job.artifacts??[];
  }).then(files=>{if(active&&revision===generation.current)setThumbs(files);}).catch(()=>{if(active&&revision===generation.current)setThumbError(true);}).finally(()=>{if(active&&revision===generation.current)setLoadingThumbs(false);});
  return()=>{active=false;};
 },[client,file.id,visibleKey,loading,retryThumbs]);
 const change=(next:number[],rotation=rotations)=>{
  if(next===order&&rotation===rotations)return;
  setHistory(items=>[...items,{order:[...order],rotations:{...rotations},current}].slice(-30));
  apply(next,rotation);
 };
 function apply(next:number[],rotation:Record<string,number>,page=current){
  const remaining=new Set(next),retained=Object.fromEntries(Object.entries(rotation).filter(([number])=>remaining.has(Number(number))));
  setOrder(next);setRotations(retained);setSelected(items=>items.filter(number=>next.includes(number)));setCurrent(next.includes(page)?page:next[0]??1);setBatch(value=>pdfPageBatch(next,value).index);onChange(next,retained);
 }
 function rotate(pages:number[]){const next={...rotations};for(const number of pages)next[String(number)]=((next[String(number)]??0)+90)%360;change(order,next);}
 async function annotate(){
  if(busy||!order.includes(current))return;
  const revision=generation.current;setAnnotating(true);setError(false);
  try{const job=await run('pdf_render',[file.id],{pages:String(current),dpi:120,format:'png',previewOnly:true}),result=(job.result?.files??job.artifacts??[])[0];if(!result)throw Error('processingFailed');if(revision===generation.current)onAnnotate(result,current);}
  catch{if(revision===generation.current)setError(true);}
  finally{if(revision===generation.current)setAnnotating(false);}
 }
 const pager=view.count>1&&<div className="lt-pdf-pager"><button className="lt-button" disabled={busy||view.index===0} onClick={()=>setBatch(view.index-1)}>{copy.first}</button><label>{copy.group}<input aria-label={copy.group} type="number" min={1} max={view.count} value={view.index+1} onChange={event=>{const number=Number(event.target.value);if(Number.isInteger(number)&&number>=1&&number<=view.count)setBatch(number-1);}}/><span>{copy.of} {view.count}</span></label><button className="lt-button" disabled={busy||view.index>=view.count-1} onClick={()=>setBatch(view.index+1)}>{copy.next}</button></div>;
 return <div className="lt-pdf-workspace" aria-busy={busy}>
  {loading&&<p className="lt-note" role="status">{copy.loading}</p>}
  {error&&<div className="lt-error" role="alert"><span>{order.length?t('tools.error.generic'):copy.loadFailed}</span> <button className="lt-button" disabled={busy} onClick={()=>order.length?void annotate():setReload(value=>value+1)}>{copy.retry}</button></div>}
  {order.length>0&&<>
   <div className="lt-pdf-summary"><strong>{order.length} {copy.of} {total} {copy.pages}</strong><span className="lt-note">{selected.length} {copy.selected}</span></div>
   <p className="lt-note" style={{margin:0}}>{copy.hint}</p>
   <div className="lt-actions lt-pdf-actions">
    <button className="lt-button" disabled={busy} onClick={()=>setSelected(selected.length===order.length?[]:[...order])}>{selected.length===order.length?copy.none:copy.all}</button>
    <button className="lt-button" disabled={busy||!selectedOrder.length||order[0]===selectedOrder[0]} onClick={()=>change(moveSelectedPdfPages(order,selectedOrder,-1))}><ArrowUp size={16}/>{copy.earlier}</button>
    <button className="lt-button" disabled={busy||!selectedOrder.length||order.at(-1)===selectedOrder.at(-1)} onClick={()=>change(moveSelectedPdfPages(order,selectedOrder,1))}><ArrowDown size={16}/>{copy.later}</button>
    <button className="lt-button" disabled={busy||!selected.length} onClick={()=>rotate(selectedOrder)}><RotateCw size={16}/>{copy.rotate}</button>
    <button className="lt-button" disabled={busy||!selected.length||!onExtract} onClick={()=>onExtract?.(selectedOrder)}>{copy.extract}</button>
    <button className="lt-button" disabled={busy||!selected.length||selected.length===order.length} onClick={()=>change(removeSelectedPdfPages(order,selectedOrder))}><Trash2 size={16}/>{copy.remove}</button>
    <button className="lt-button" disabled={busy||!history.length} onClick={()=>{const previous=history.at(-1);if(previous){setHistory(items=>items.slice(0,-1));apply(previous.order,previous.rotations,previous.current);}}}><Undo2 size={16}/>{copy.undo}</button>
    <button className="lt-button" disabled={busy||order.length===total&&order.every((number,index)=>number===index+1)&&Object.values(rotations).every(value=>value===0)} onClick={()=>change(pdfPageOrder(total),{})}>{copy.reset}</button>
   </div>
   {pager}
   {loadingThumbs&&<span className="lt-note" role="status">{copy.loadingThumbs}</span>}
   {thumbError&&<div className="lt-error" role="alert">{copy.thumbFailed} <button className="lt-button" disabled={loadingThumbs} onClick={()=>setRetryThumbs(value=>value+1)}>{copy.retry}</button></div>}
   <div className="lt-pages" role="list" aria-label={t('tools.pdf_info')}>{view.pages.map((number,index)=>{
    const position=view.start+index,active=current===number;
    return <div role="listitem" key={number} className={`lt-page${active?' selected':''}`} aria-current={active?'true':undefined} draggable={!busy} onDragStart={event=>event.dataTransfer.setData('application/x-galaxy-pdf-page',String(number))} onDragOver={event=>{if(!busy)event.preventDefault();}} onDrop={event=>{event.preventDefault();if(busy)return;const source=Number(event.dataTransfer.getData('application/x-galaxy-pdf-page')),from=order.indexOf(source);if(from<0||from===position)return;const next=[...order];next.splice(from,1);next.splice(position,0,source);change(next);}}>
     <div className="lt-pdf-page-select"><input type="checkbox" disabled={busy} checked={selected.includes(number)} aria-label={t('tools.page',{number})} onChange={event=>setSelected(items=>event.target.checked?[...items,number]:items.filter(item=>item!==number))}/><button className={'lt-button'+(active?' active':'')} disabled={busy} onClick={()=>setCurrent(number)}>{t('tools.page',{number})}</button></div>
     <button className="lt-pdf-preview" disabled={busy} aria-label={copy.preview+' · '+t('tools.page',{number})} onClick={()=>setCurrent(number)}>{thumbs[number]?<PdfThumbnail client={client} file={thumbs[number]} rotation={rotations[String(number)]??0} t={t}/>:<span className="lt-pdf-preview-empty">{loadingThumbs?copy.waiting:copy.preview}</span>}</button>
     <small className="lt-pdf-position">{copy.position} {position+1} · {(rotations[String(number)]??0)}°</small>
     <div className="lt-actions lt-pdf-page-buttons"><button className="lt-button" disabled={busy||position===0} title={t('tools.previous')} aria-label={t('tools.previous')} onClick={()=>change(movePdfPage(order,position,-1))}><ArrowUp size={16}/></button><button className="lt-button" disabled={busy||position===order.length-1} title={t('tools.next')} aria-label={t('tools.next')} onClick={()=>change(movePdfPage(order,position,1))}><ArrowDown size={16}/></button><button className="lt-button" disabled={busy} title={t('tools.rotate')} aria-label={t('tools.rotate')} onClick={()=>rotate([number])}><RotateCw size={16}/></button><button className="lt-button" disabled={busy||order.length===1} title={t('tools.remove')} aria-label={t('tools.remove')} onClick={()=>change(removeSelectedPdfPages(order,[number]))}><Trash2 size={16}/></button></div>
    </div>;
   })}</div>
   {pager}
   <button className="lt-button" disabled={busy} onClick={()=>void annotate()}>{t('tools.page',{number:current})} · {copy.annotate}</button>
  </>}
 </div>;
}
export function PdfThumbnail({client,file,rotation=0,t}:{client:Pick<LocalAgentClient,'artifact'>;file:AgentFile;rotation?:number;t:ToolTranslate}){
 const [url,setUrl]=useState(''),[failed,setFailed]=useState(false),[rotationFit,setRotationFit]=useState(1),element=useRef<HTMLImageElement>(null);
 useEffect(()=>{const node=element.current;if(!node)return;const fit=()=>{const width=node.clientWidth,height=node.clientHeight;setRotationFit(rotation%180&&width&&height?Math.min(1,width/height,height/width):1);};fit();const observer=typeof ResizeObserver==='undefined'?undefined:new ResizeObserver(fit);observer?.observe(node);return()=>observer?.disconnect();},[url,rotation]);
 useEffect(()=>{
  let active=true,value='';setUrl('');setFailed(false);
  void client.artifact(file.id).then(blob=>{value=URL.createObjectURL(blob);if(active)setUrl(value);else{URL.revokeObjectURL(value);value='';}}).catch(()=>{if(active)setFailed(true);});
  return()=>{active=false;if(value)URL.revokeObjectURL(value);};
 },[client,file.id]);
 return url?<img ref={element} src={url} alt={t('tools.preview')} style={{transform:`rotate(${rotation}deg) scale(${rotationFit})`}}/>:failed?<span className="lt-pdf-preview-empty">{t('tools.error.generic')}</span>:null;
}
