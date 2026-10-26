import {useRef,useState} from 'react';
import {Check,CheckCircle2,Copy,Puzzle} from 'lucide-react';
import type {ToolLanguage,ToolTranslate} from './types';
import {extensionGuideText} from './extension-guide-text';
import './extension-setup.css';

export function WebCaptureGuide({language,t,connected,onSetup}:{language:ToolLanguage;t:ToolTranslate;connected:boolean;onSetup:()=>void}){
 const [browser,setBrowser]=useState('chrome'),[copied,setCopied]=useState(false),[error,setError]=useState('');
 const input=useRef<HTMLInputElement>(null),text=extensionGuideText(language),address=`${browser}://extensions/`;
 async function copy(){try{await navigator.clipboard.writeText(address);setCopied(true);setError('');}catch{input.current?.focus();input.current?.select();setError(text.copyError);}}
 return <section className="kio-web-guide" aria-label={t('tools.extensionInstall')}>
  <header><Puzzle size={23}/><div><h2>{t('tools.extensionInstall')}</h2><p>{text.intro}</p></div><button className="lt-button primary" onClick={onSetup}>{t('tools.extensionInstall')} →</button></header>
  <ol><li><b>1</b><span>{text.addressTitle}</span></li><li><b>2</b><span>{text.developerTitle} · {text.folderTitle}</span></li><li><b>3</b><span>{text.connectTitle}</span></li></ol>
  <div className="kio-web-address"><select aria-label={text.browserChoice} value={browser} onChange={event=>{setBrowser(event.target.value);setCopied(false);setError('');}}><option value="chrome">Chrome</option><option value="edge">Edge</option></select><input ref={input} readOnly aria-label={text.addressLabel} value={address} onFocus={event=>event.currentTarget.select()}/><button className="lt-button" onClick={()=>void copy()}>{copied?<Check size={15}/>:<Copy size={15}/>} {copied?text.copied:text.copyAddress}</button></div>
  <p>{text.addressHint.replace('{browser}',browser==='chrome'?'Chrome':'Edge')}</p>
  <div className={'kio-web-state'+(connected?' connected':'')} role="status">{connected?<CheckCircle2 size={16}/>:<Puzzle size={16}/>} {connected?text.connected:text.disconnected}</div>
  {error&&<p role="alert">{error}</p>}
 </section>;
}
