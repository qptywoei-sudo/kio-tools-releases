import {useEffect,useRef,useState} from 'react';
import {Check,CheckCircle2,Copy,ExternalLink,FolderOpen,Globe,LoaderCircle,Puzzle,RefreshCw,X} from 'lucide-react';
import type {LocalAgentClient} from '@/services/local-agent';
import type {ToolLanguage,ToolTranslate} from './types';
import {extensionGuideText} from './extension-guide-text';
import './extension-setup.css';

type BrowserChoice='chrome'|'edge';
export function ExtensionSetup({t,language,client,connected,onClose}:{t:ToolTranslate;language:ToolLanguage;client:LocalAgentClient;connected:boolean;onClose:()=>void}){
 const dialog=useRef<HTMLDialogElement>(null),addressInput=useRef<HTMLInputElement>(null),folderInput=useRef<HTMLInputElement>(null),alive=useRef(false),copyTimer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);
 const [browser,setBrowser]=useState<BrowserChoice>('chrome'),[folder,setFolder]=useState(''),[extensionName,setExtensionName]=useState('Bogo Tools'),[pending,setPending]=useState(false),[copied,setCopied]=useState(''),[error,setError]=useState(''),[message,setMessage]=useState(''),[isConnected,setIsConnected]=useState(connected);
 const text=extensionGuideText(language),address=`${browser}://extensions/`,browserName=browser==='chrome'?'Chrome':'Edge';
 useEffect(()=>{alive.current=true;const element=dialog.current,previous=document.activeElement instanceof HTMLElement?document.activeElement:null;if(element&&!element.open)element.showModal();void client.browserInstallInfo().then(info=>{if(alive.current){setFolder(info.folderPath);setExtensionName(info.extensionName);}}).catch(()=>{if(alive.current)setError(text.folderError);});return()=>{alive.current=false;clearTimeout(copyTimer.current);element?.close();previous?.focus();};},[client,text.folderError]);
 useEffect(()=>setIsConnected(connected),[connected]);
 async function copy(value:string,kind:'address'|'folder'){
  setError('');setMessage('');clearTimeout(copyTimer.current);setCopied('');
  try{await navigator.clipboard.writeText(value);if(!alive.current)return;setCopied(kind);copyTimer.current=setTimeout(()=>setCopied(''),2200);}
  catch{if(!alive.current)return;setError(text.copyError);const input=kind==='address'?addressInput.current:folderInput.current;input?.focus();input?.select();}
 }
 async function openFolder(){
  if(pending)return;setPending(true);setError('');setMessage('');
  try{const info=await client.installBrowser();if(alive.current){setFolder(info.folderPath);setExtensionName(info.extensionName);setMessage(text.folderOpened);}}
  catch{if(alive.current)setError(text.folderError);}
  finally{if(alive.current)setPending(false);}
 }
 async function refresh(){
  if(pending)return;setPending(true);setError('');setMessage('');
  try{const status=await client.browser();if(alive.current){setIsConnected(status.connected===true);if(!status.connected)setMessage(text.waiting);}}
  catch{if(alive.current)setError(text.checkError);}
  finally{if(alive.current)setPending(false);}
 }
 return <dialog ref={dialog} className="lt-extension-dialog kio-extension-guide" aria-labelledby="lt-extension-title" onCancel={event=>{event.preventDefault();onClose();}}>
  <header className="kio-extension-heading"><span className="kio-extension-symbol"><Puzzle size={22} aria-hidden="true"/></span><div><h2 id="lt-extension-title">{t('tools.extensionInstall')}</h2><p>{text.intro}</p></div><button className="lt-button kio-extension-close" title={t('tools.close')} aria-label={t('tools.close')} onClick={onClose}><X size={18}/></button></header>
  <div className="kio-extension-browser" role="group" aria-label={text.browserChoice}>{(['chrome','edge'] as const).map(choice=><button key={choice} className={`lt-button ${browser===choice?'active':''}`} aria-pressed={browser===choice} onClick={()=>{setBrowser(choice);setCopied('');setError('');}}><Globe size={15} aria-hidden="true"/>{choice==='chrome'?'Chrome':'Edge'}{browser===choice&&<Check size={14} aria-hidden="true"/>}</button>)}</div>
  <ol className="kio-extension-steps">
   <li><span className="kio-extension-number" aria-hidden="true">1</span><div><h3>{text.addressTitle}</h3><p>{text.addressHint.replace('{browser}',browserName)}</p><div className="kio-extension-copy-row"><input ref={addressInput} readOnly aria-label={text.addressLabel} value={address} onFocus={event=>event.currentTarget.select()}/><button className="lt-button primary" onClick={()=>void copy(address,'address')} aria-label={text.copyAddress}>{copied==='address'?<Check size={15}/>:<Copy size={15}/>} {copied==='address'?text.copied:text.copyAddress}</button></div><small>{text.addressNote}</small></div></li>
   <li><span className="kio-extension-number" aria-hidden="true">2</span><div><h3>{text.developerTitle}</h3><p>{browser==='chrome'?text.developerChrome:text.developerEdge}</p><div className="kio-extension-example" aria-hidden="true"><span>{text.developerMode}</span><span className="kio-extension-switch"><i/></span><strong>ON</strong></div></div></li>
   <li><span className="kio-extension-number" aria-hidden="true">3</span><div><h3>{text.folderTitle}</h3><p>{text.folderHint}</p><div className="kio-extension-folder-actions"><button className="lt-button" disabled={pending} onClick={()=>void openFolder()}>{pending?<LoaderCircle size={15}/>:<FolderOpen size={15}/>} {text.openFolder}</button><button className="lt-button" disabled={!folder} onClick={()=>void copy(folder,'folder')}>{copied==='folder'?<Check size={15}/>:<Copy size={15}/>} {copied==='folder'?text.copied:text.copyFolder}</button></div><input ref={folderInput} className="kio-extension-folder-path" readOnly aria-label={text.folderPath} title={folder} value={folder} placeholder={text.folderLoading} onFocus={event=>event.currentTarget.select()}/><small>{text.folderNote}</small></div></li>
   <li><span className="kio-extension-number" aria-hidden="true">4</span><div><h3>{text.connectTitle}</h3><p>{text.connectHint.replace('{name}',extensionName)}</p><small>{text.captureHint}</small></div></li>
  </ol>
  <div className={`kio-extension-status ${isConnected?'connected':''}`} role="status">{isConnected?<CheckCircle2 size={18}/>:<Puzzle size={18}/>}<div><strong>{isConnected?text.connected:text.disconnected}</strong><small>{isConnected?text.ready:text.waiting}</small></div><button className="lt-button" disabled={pending} onClick={()=>void refresh()}><RefreshCw size={14}/>{text.check}</button></div>
  {error&&<p className="lt-error" role="alert">{error}</p>}{message&&<p className="kio-extension-feedback" role="status">{message}</p>}<span className="kio-extension-sr" role="status">{copied?text.copied:''}</span>
  <footer className="kio-extension-footer"><a href={browser==='chrome'?'https://developer.chrome.com/docs/extensions/get-started/tutorial/hello-world#load-unpacked':'https://learn.microsoft.com/en-us/microsoft-edge/extensions/getting-started/extension-sideloading'} target="_blank" rel="noopener noreferrer">{text.official}<ExternalLink size={12}/></a><button className="lt-button primary" onClick={onClose}>{isConnected?text.done:t('tools.close')}</button></footer>
 </dialog>;
}
