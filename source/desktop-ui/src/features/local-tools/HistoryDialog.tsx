import {useEffect,useRef,type ReactNode} from 'react';
import {FileText,X} from 'lucide-react';

export function HistoryDialog({title,closeLabel,onClose,children}:{title:string;closeLabel:string;onClose:()=>void;children:ReactNode}){
 const ref=useRef<HTMLDialogElement>(null);
 useEffect(()=>{const dialog=ref.current;dialog?.showModal();return()=>dialog?.close();},[]);
 return <dialog ref={ref} className="kio-history-dialog" aria-labelledby="kio-history-title" onCancel={event=>{event.preventDefault();onClose();}} onClick={event=>{if(event.target===event.currentTarget){const bounds=event.currentTarget.getBoundingClientRect();if(event.clientX<bounds.left||event.clientX>bounds.right||event.clientY<bounds.top||event.clientY>bounds.bottom)onClose();}}}>
  <header><FileText size={20}/><h2 id="kio-history-title">{title}</h2><button autoFocus className="lt-button lt-icon-button" aria-label={closeLabel} title={closeLabel} onClick={onClose}><X size={18}/></button></header>
  <div className="kio-history-content">{children}</div>
 </dialog>;
}
