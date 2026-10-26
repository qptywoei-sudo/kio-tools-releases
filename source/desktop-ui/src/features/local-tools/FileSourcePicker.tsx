import {useEffect,useRef,useState} from 'react';
import {ArrowLeft,Check,FileAudio,FileImage,FileVideo,FolderOpen,History,LoaderCircle,X} from 'lucide-react';
import type {AgentFile} from './types';
import type {LocalAgentClient} from '@/services/local-agent';
import {useToolsLocale} from './tool-locale';
import './file-source-picker.css';

export function supportsHistoryFile(file:AgentFile,accept:string){
 const extension=file.name.split('.').at(-1)?.toLowerCase()??'';
 const kind=file.mime?.startsWith('image/')||['png','jpg','jpeg','webp','bmp','gif'].includes(extension)?'image':file.mime?.startsWith('video/')||['mp4','mov','mkv','webm','avi','m4v'].includes(extension)?'video':file.mime?.startsWith('audio/')||['mp3','wav','m4a','aac','ogg','flac'].includes(extension)?'audio':'';
 return Boolean(kind&&accept.split(',').some(value=>value.trim()===kind+'/*'||value.trim()===file.mime||value.trim()==='.'+extension));
}
export function FileSourcePicker({client,accept,multiple=true,historyFiles,onLocal,onHistory,onClose}:{client:LocalAgentClient;accept:string;multiple?:boolean;historyFiles:AgentFile[];onLocal:(files:File[])=>void|Promise<void>;onHistory:(files:AgentFile[])=>void|Promise<void>;onClose:()=>void}){
 const{ui}=useToolsLocale();const dialog=useRef<HTMLDialogElement>(null),input=useRef<HTMLInputElement>(null);
 const[page,setPage]=useState<'choose'|'history'>('choose'),[selected,setSelected]=useState<string[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [saved,setSaved]=useState<AgentFile[]>([]),[cursor,setCursor]=useState(''),[loading,setLoading]=useState(false);
 const alive=useRef(true);
 const seen=new Set<string>(),files=[...historyFiles,...saved].filter(file=>{if(seen.has(file.id)||!supportsHistoryFile(file,accept))return false;seen.add(file.id);return true;});
 async function load(cursor=''){setLoading(true);try{const result=await client.historyFiles(cursor);if(alive.current){setSaved(old=>cursor?[...old,...result.files]:result.files);setCursor(result.nextCursor);}}catch{if(alive.current)setError(ui('이전 내역을 불러오지 못했습니다. 다시 시도해 주세요.'));}finally{if(alive.current)setLoading(false);}}
 useEffect(()=>{alive.current=true;void load();return()=>{alive.current=false;};},[client]);
 useEffect(()=>{dialog.current?.showModal();return()=>dialog.current?.close();},[]);
 async function choose(files:File[]|AgentFile[],local:boolean){if(busy||!files.length)return;setBusy(true);setError('');try{if(local)await onLocal(files as File[]);else await onHistory(files as AgentFile[]);onClose();}catch{setError(ui('파일을 불러오지 못했습니다. 파일을 다시 선택해 주세요.'));}finally{setBusy(false);}}
 return <dialog ref={dialog} className="file-source-picker" aria-labelledby="file-source-title" onCancel={event=>{event.preventDefault();if(!busy)onClose();}}><header><div><h2 id="file-source-title">{ui('파일 가져오기')}</h2><p>{ui('내 컴퓨터 또는 Bogo Tools 이전 내역에서 선택하세요.')}</p></div><button className="ps-icon" autoFocus disabled={busy} title={ui('닫기')} aria-label={ui('닫기')} onClick={onClose}><X size={18}/></button></header>
  <input ref={input} hidden type="file" accept={accept} multiple={multiple} onChange={event=>{const files=[...event.target.files??[]];event.target.value='';void choose(files,true);}}/>
  {page==='choose'?<div className="source-choices"><button disabled={busy} onClick={()=>input.current?.click()}><span><FolderOpen size={27}/></span><strong>{ui('내 컴퓨터에서 가져오기')}</strong><small>{ui('컴퓨터에 저장된 파일 선택')}</small></button><button disabled={busy} onClick={()=>setPage('history')}><span><History size={27}/></span><strong>{ui('Bogo Tools 이전 내역')}</strong><small>{ui('이전에 만든 사진·영상 다시 사용')}</small></button></div>:<><div className="source-history-bar"><button className="ps-button" disabled={busy} onClick={()=>setPage('choose')}><ArrowLeft size={15}/>{ui('뒤로')}</button><span>{ui('사용할 수 있는 파일')} · {files.length}</span></div>{loading&&<p role="status">{ui("불러오는 중…")}</p>}<div className="source-history-list">{!files.length?<p className="source-history-empty">{ui('사용할 수 있는 이전 내역이 없습니다. 먼저 사진이나 영상을 저장해 주세요.')}</p>:files.map(file=>{const chosen=selected.includes(file.id),Icon=file.mime?.startsWith('video/')?FileVideo:file.mime?.startsWith('audio/')?FileAudio:FileImage;return <button type="button" key={file.id} className={chosen?'selected':''} aria-pressed={chosen} disabled={busy} onClick={()=>setSelected(old=>multiple?(old.includes(file.id)?old.filter(id=>id!==file.id):[...old,file.id]):[file.id])}><span className="source-file-icon"><Icon size={25}/></span><span className="source-file-name"><strong>{file.name}</strong><small>{file.mime??file.extension??''}{file.size?' · '+(file.size<1048576?(file.size/1024).toFixed(1)+' KB':(file.size/1048576).toFixed(1)+' MB'):''}</small></span><span className="source-file-check">{chosen&&<Check size={16}/>}</span></button>;})}</div>{cursor&&<button className="ps-button" disabled={loading||busy} onClick={()=>void load(cursor)}>{ui("더 보기")}</button>}<footer><span>{selected.length} {ui('개 선택')}</span><button className="ps-primary" disabled={busy||!selected.length} onClick={()=>void choose(files.filter(file=>selected.includes(file.id)),false)}>{busy?<LoaderCircle size={16} className="ps-spin"/>:<Check size={16}/>} {ui('선택한 파일 가져오기')}</button></footer></>}
  {error&&<p className="ps-alert" role="alert">{error}</p>}
 </dialog>;
}
