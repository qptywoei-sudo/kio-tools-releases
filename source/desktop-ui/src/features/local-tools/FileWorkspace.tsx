import {useToolsLocale} from './tool-locale';
import {useEffect,useRef,useState,type DragEvent,type ReactNode} from 'react';
import {Upload} from 'lucide-react';
import './file-workspace.css';

/** The editor itself is the external file target. Internal clip/photo drags pass through. */
export function FileWorkspace({children,onFiles,disabled=false,enabled=true,label}:{children:ReactNode;onFiles:(files:File[])=>void;disabled?:boolean;enabled?:boolean;label?:string}){
 const {ui}=useToolsLocale();

 const [over,setOver]=useState(false),depth=useRef(0);
 const reset=()=>{depth.current=0;setOver(false);};
 useEffect(()=>{if(disabled||!enabled){depth.current=0;setOver(false);}},[disabled,enabled]);
 const external=(event:DragEvent)=>enabled&&Array.from(event.dataTransfer.types).includes('Files')&&!(event.target instanceof Element&&event.target.closest('[data-file-drop="local"]'));
 const blocked=(event:DragEvent)=>disabled||Boolean(event.currentTarget.querySelector('[aria-busy="true"]'));
 return <div className={'kio-file-workspace'+(over?' is-file-over':'')} role={enabled?'region':undefined} aria-label={enabled?(label??ui("작업 파일 끌어놓기")):undefined}
  onDragEnterCapture={event=>{if(!external(event))return;event.preventDefault();depth.current++;if(!blocked(event))setOver(true);}}
  onDragOverCapture={event=>{if(!external(event))return;event.preventDefault();event.dataTransfer.dropEffect=blocked(event)?'none':'copy';}}
  onDragLeaveCapture={event=>{if(!external(event))return;depth.current=Math.max(0,depth.current-1);if(!depth.current)setOver(false);}}
  onDragEnd={reset}
  onDropCapture={event=>{if(!external(event))return;event.preventDefault();event.stopPropagation();reset();if(!blocked(event)){const files=Array.from(event.dataTransfer.files);if(files.length)onFiles(files);}}}>
  {children}{over&&<div className="kio-file-drop-feedback" aria-hidden="true"><span><Upload size={22}/>{ui("여기에 놓아 불러오기")}</span></div>}
 </div>;
}

export function EmptyFileWorkspace({title,detail,onChoose,disabled=false}:{title:string;detail:string;onChoose:()=>void;disabled?:boolean}){
 const {ui}=useToolsLocale();

 return <button type="button" className="kio-file-empty" disabled={disabled} onClick={onChoose}><span><Upload size={32}/></span><strong>{title}</strong><small>{detail} {ui("· 클릭해서 선택")}</small></button>;
}
