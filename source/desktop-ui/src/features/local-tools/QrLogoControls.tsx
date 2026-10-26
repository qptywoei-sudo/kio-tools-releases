import {useToolsLocale} from './tool-locale';
import {useEffect,useRef,useState} from 'react';
import {ImagePlus,X} from 'lucide-react';
import type {LocalAgentClient} from '@/services/local-agent';
import type {AgentFile} from './types';
import {loadQrLogo,type QrLogoAsset} from './qr-logo-image';
import './qr-logo.css';

export type QrLogoSelection={file:AgentFile;asset:QrLogoAsset;shape:'circle'|'square'};
export async function importQrLogo(client:Pick<LocalAgentClient,'upload'>,input:File):Promise<Omit<QrLogoSelection,'shape'>>{
 const asset=await loadQrLogo(input);
 const bytes=Uint8Array.from(atob(asset.dataUrl.slice(asset.dataUrl.indexOf(',')+1)),character=>character.charCodeAt(0));
 const file=await client.upload(new File([bytes],'qr-logo.png',{type:'image/png'}));
 return {file,asset};
}
// Read local image bytes only; pasted URLs and HTML never trigger downloads.
export function transferredQrLogo(data:Pick<DataTransfer,'items'|'files'>):File|null{
 const files=Array.from(data.items??[]).filter(item=>item.kind==='file').map(item=>item.getAsFile()).filter((file):file is File=>file!==null);
 for(const file of [...files,...Array.from(data.files??[])])if(file.type.startsWith('image/')||/\.(png|jpe?g|svg)$/i.test(file.name))return file;
 return null;
}
export async function selectQrLogo(client:Pick<LocalAgentClient,'choose'|'artifact'|'upload'>):Promise<Omit<QrLogoSelection,'shape'>|null>{
 // Embedded desktop webviews use the existing native chooser. A hidden HTML
 // file input has no open-panel delegate in the Mac host and silently fails.
 const selected=(await client.choose('any',false)).files[0];
 if(!selected)return null;
 if((selected.size??0)>5*1024*1024)throw Error('로고는 5MB 이하의 PNG, JPG, SVG 파일을 선택하세요.');
 const blob=await client.artifact(selected.id);
 return importQrLogo(client,new File([blob],selected.name,{type:blob.type||selected.mime||''}));
}
export function QrLogoControls({client,value,onChange,disabled,onBusyChange}:{client:LocalAgentClient;value:QrLogoSelection|null;onChange:(value:QrLogoSelection|null)=>void;disabled:boolean;onBusyChange:(busy:boolean)=>void}){
 const {ui}=useToolsLocale();

 const revision=useRef(0),pending=useRef(false),dragDepth=useRef(0),[error,setError]=useState(''),[uploading,setUploading]=useState(false),[dragging,setDragging]=useState(false);
 useEffect(()=>()=>{revision.current++;},[]);
 async function importSelection(input?:File){
  if(disabled||pending.current)return;
  pending.current=true;
  const current=++revision.current;setError('');setUploading(true);onBusyChange(true);
  try{
   const selection=input?await importQrLogo(client,input):await selectQrLogo(client);
   if(selection&&current===revision.current)onChange({...selection,shape:value?.shape??'square'});
  }catch(error){if(current===revision.current&&!(error instanceof Error&&error.message==='cancelled'))setError(error instanceof Error?error.message:ui("로고를 불러오지 못했습니다."));}
  finally{pending.current=false;onBusyChange(false);if(current===revision.current)setUploading(false);}
 }
 useEffect(()=>{
  const paste=(event:globalThis.ClipboardEvent)=>{
   if(event.defaultPrevented||!event.clipboardData)return;
   const file=transferredQrLogo(event.clipboardData);if(!file)return;
   event.preventDefault();void importSelection(file);
  };
  window.addEventListener('paste',paste);
  return()=>window.removeEventListener('paste',paste);
 });
 return <section className={'kio-qr-logo'+(dragging?' dragging':'')} aria-label={ui("QR 중앙 로고")} data-file-drop="local"
  onDragEnter={event=>{if(!Array.from(event.dataTransfer.types).includes('Files'))return;event.preventDefault();event.stopPropagation();dragDepth.current++;if(!disabled&&!pending.current)setDragging(true);}}
  onDragOver={event=>{if(!Array.from(event.dataTransfer.types).includes('Files'))return;event.preventDefault();event.stopPropagation();event.dataTransfer.dropEffect=disabled||pending.current?'none':'copy';}}
  onDragLeave={event=>{event.preventDefault();event.stopPropagation();if(--dragDepth.current<=0){dragDepth.current=0;setDragging(false);}}}
  onDrop={event=>{event.preventDefault();event.stopPropagation();dragDepth.current=0;setDragging(false);if(disabled||pending.current)return;const file=transferredQrLogo(event.dataTransfer);if(file)void importSelection(file);else setError(ui("PNG, JPG, SVG 이미지 파일을 여기에 놓아 주세요."));}}>
  <div className="kio-qr-logo-heading"><strong>{ui("중앙 로고")}<small>{ui("선택 사항")}</small></strong>{value?<div className="kio-qr-logo-shapes" role="group" aria-label={ui("로고 모양")}><button type="button" disabled={disabled||uploading} aria-pressed={value.shape==='square'} onClick={()=>onChange({...value,shape:'square'})}>{ui("사각형")}</button><button type="button" disabled={disabled||uploading} aria-pressed={value.shape==='circle'} onClick={()=>onChange({...value,shape:'circle'})}>{ui("원형")}</button></div>:<span>{ui("오류보정 H")}</span>}</div>
  <div className="kio-qr-logo-row">
   <div className={'kio-qr-logo-preview '+(value?.shape??'empty')}>{value?<img src={value.asset.dataUrl} alt={ui("선택한 중앙 로고")}/>:<ImagePlus size={22} aria-hidden="true"/>}</div>
   <div className="kio-qr-logo-file"><button type="button" className="lt-button" disabled={disabled||uploading} onClick={()=>void importSelection()}>{uploading?ui("로고 불러오는 중…"):value?ui("로고 바꾸기"):ui("로고 이미지 선택")}</button><small title={value?.asset.name}>{value?.asset.name??ui("PNG · JPG · SVG · 5MB 이하")}</small><small>{ui("여기에 끌어 놓기 · Ctrl+V / ⌘V로 붙여넣기")}</small></div>
   {value&&<button type="button" className="lt-button lt-icon-button" disabled={disabled||uploading} aria-label={ui("중앙 로고 제거")} title={ui("중앙 로고 제거")} onClick={()=>{setError('');onChange(null);}}><X size={15}/></button>}
  </div>
  <p className="lt-note">{ui("흰색 여백 4px · 중앙 자동 정렬 · 오류보정 H")}<br/>{ui("스캔 검사를 통과하는 가장 큰 크기로 자동 맞춥니다.")}</p>
  {error&&<p className="lt-error" role="alert">{ui(error)}</p>}
 </section>;
}
