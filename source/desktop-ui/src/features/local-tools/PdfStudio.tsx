import {useToolsLocale} from './tool-locale';
import {useEffect,useState} from 'react';
import {ChevronLeft,ChevronRight,FileImage,FileText,Maximize2,Plus,Trash2,ArrowUp,ArrowDown} from 'lucide-react';
import type {LocalAgentClient} from '@/services/local-agent';
import type {AgentFile,ToolLanguage,ToolTranslate} from './types';
import {PdfPages,PdfThumbnail} from './PdfPages';
import {isPdf,useDocumentPreview,type DocumentRunner} from './document-preview';
import './document-studio.css';
import {EmptyFileWorkspace} from './FileWorkspace';

export function PdfStudio({files,client,operation,t,language,run,onChange,onExtract,onAnnotate,onChoose,onRemove,onMove,busy=false}:{busy?:boolean;onChoose:()=>void;onRemove:(id:string)=>void;onMove:(index:number,direction:number)=>void;files:AgentFile[];client:LocalAgentClient;operation:string;t:ToolTranslate;language?:ToolLanguage;run:DocumentRunner;onChange:(order:number[],rotations:Record<string,number>)=>void;onExtract?:(pages:number[])=>void;onAnnotate:(file:AgentFile,page:number)=>void}){
 const {ui}=useToolsLocale();

 const [active,setActive]=useState(''),[page,setPage]=useState(1),[pageRotation,setPageRotation]=useState(0),[zoom,setZoom]=useState(false);
 const file=files.find(item=>item.id===active)??files[0];
 useEffect(()=>{setPage(1);setPageRotation(0);},[file?.id,operation]);
 // Parent run callbacks are intentionally excluded: job state updates must not restart previews.
 const preview=useDocumentPreview(client,file,page);
 if(!file)return <EmptyFileWorkspace title={operation==='images_pdf'?ui("PDF로 만들 사진을 여기에 놓으세요"):ui("PDF를 여기에 놓으세요")} detail={operation==='pdf_merge'?ui("PDF 여러 개"):operation==='images_pdf'?ui("사진 여러 장"):ui("PDF 한 개")} onChoose={onChoose} disabled={busy}/>;
 const manage=['pdf_manage','pdf_extract','pdf_annotate'].includes(operation)&&isPdf(file);
 return <section className={'kio-document-studio'+(manage?' has-page-tools':'')}>
  <div className="kio-document-heading"><div><FileText size={19}/><strong>{ui("문서 미리보기")}</strong><span>{files.length}{ui("개 파일")}{isPdf(file)?ui(" · {v0}페이지",{v0:preview.pages}):''}</span></div><div><button className="lt-button" disabled={busy} onClick={onChoose}><Plus size={15}/>{['pdf_merge','images_pdf'].includes(operation)?ui("파일 추가"):ui("파일 바꾸기")}</button><button className="lt-button" disabled={busy} aria-label={ui("현재 파일 제거")} onClick={()=>onRemove(file.id)}><Trash2 size={15}/></button><button className="lt-button" onClick={()=>setZoom(value=>!value)} title={ui("미리보기 크기 전환")}><Maximize2 size={16}/>{zoom?ui("맞춤 보기"):ui("크게 보기")}</button></div></div>
  <div className={'kio-document-layout'+(files.length===1?' single':'')}>
   {files.length>1&&<div className="kio-document-files" aria-label={ui("선택한 문서")}>{files.map((item,index)=><div className="kio-document-file-item" key={item.id}><button className={'kio-document-file'+(item.id===file.id?' active':'')} onClick={()=>{setActive(item.id);setPage(1);}}><span className="kio-document-file-number">{index+1}</span>{isPdf(item)?<FileText size={25}/>:<PdfThumbnail client={client} file={item} t={t}/>}<span>{item.name}</span></button><div className="kio-document-file-order"><button className="lt-button" aria-label={ui("{v0} 위로",{v0:item.name})} disabled={busy||index===0} onClick={()=>onMove(index,-1)}><ArrowUp size={13}/></button><button className="lt-button" aria-label={ui("{v0} 아래로",{v0:item.name})} disabled={busy||index===files.length-1} onClick={()=>onMove(index,1)}><ArrowDown size={13}/></button><button className="lt-button" aria-label={ui("{v0} 제거",{v0:item.name})} disabled={busy} onClick={()=>onRemove(item.id)}><Trash2 size={13}/></button></div></div>)}</div>}
   <div className="kio-document-main">
    <div className="kio-document-pagebar"><span title={file.name}>{file.name}</span>{isPdf(file)&&<div><button className="lt-button" disabled={page<=1||preview.loading} aria-label={ui("이전 페이지")} onClick={()=>setPage(value=>value-1)}><ChevronLeft size={16}/></button><label><input aria-label={ui("미리볼 페이지")} type="number" min={1} max={preview.pages} value={page} onChange={event=>{const value=Number(event.target.value);if(Number.isInteger(value)&&value>=1&&value<=preview.pages)setPage(value);}}/> / {preview.pages}</label><button className="lt-button" disabled={page>=preview.pages||preview.loading} aria-label={ui("다음 페이지")} onClick={()=>setPage(value=>value+1)}><ChevronRight size={16}/></button></div>}</div>
    <div className={'kio-document-preview'+(zoom?' expanded':'')} aria-busy={preview.loading}>{preview.loading?<div className="kio-document-placeholder"><FileText size={36}/><span>{ui("문서를 불러오고 있습니다…")}</span></div>:preview.error?<div className="kio-document-placeholder" role="alert"><span>{preview.error}</span><button className="lt-button" onClick={preview.retry}>{ui("다시 시도")}</button></div>:preview.url?<img src={preview.url} alt={ui("{v0} {v1}페이지 미리보기",{v0:file.name,v1:page})} style={{transform:`rotate(${pageRotation}deg)`}}/>:<FileImage size={40}/>}</div>
   </div>
  </div>
  {manage&&<details className="kio-pdf-page-tools" open><summary>{ui("페이지 선택 · 순서 · 회전 · 삭제")}</summary><PdfPages key={file.id+operation} client={client} file={file} t={t} language={language} run={run} onChange={onChange} onExtract={onExtract} onAnnotate={onAnnotate} previewPage={page} onPreviewPage={(number,rotation)=>{setPage(number);setPageRotation(rotation);}}/></details>}
 </section>;
}

