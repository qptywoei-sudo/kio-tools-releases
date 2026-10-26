import {useEffect,useRef,useState,type ReactNode} from 'react';
import {ArrowUpRight,Globe2,LoaderCircle} from 'lucide-react';
import type {LocalAgentClient} from '@/services/local-agent';
import type {KIOAccountStatus} from './kio-account';
import type {ToolLanguage} from './types';
import {orderedToolLanguages} from './tool-locale';
import {BrandIcon} from './Brand';
import {accountChangedEvent,acknowledgedLogout,createAccountObserver} from './account-session';
import {loginCopy,loginLanguages,loginLanguageNames} from './login-copy';
import './kio-account.css';
import {finishToolsStartup} from './startup';

export function KIOAccountGate({client,children,language,onLanguageChange}:{client:LocalAgentClient;children:ReactNode;language:ToolLanguage;onLanguageChange:(language:ToolLanguage)=>void}){
 const [account,setAccount]=useState<KIOAccountStatus|null>(null),[error,setError]=useState<'connectionError'|'loginError'|''>(''),[busy,setBusy]=useState(false);
 const observer=useRef<ReturnType<typeof createAccountObserver>|null>(null),copy=loginCopy[language];
 useEffect(()=>{
  const watch=createAccountObserver(()=>client.accountStatus(),value=>{setAccount(value);setError('');},()=>setError('connectionError'));
  observer.current=watch;void watch.refresh();
  const accountChange=(event:Event)=>{const signedOut=acknowledgedLogout(event);if(signedOut)watch.replace(signedOut);else void watch.refresh(true);};
  const refresh=()=>void watch.refresh();
  window.addEventListener(accountChangedEvent,accountChange);window.addEventListener('galaxycontrol:shortcut',refresh);
  const timer=setInterval(refresh,2500);
  return()=>{watch.close();observer.current=null;clearInterval(timer);window.removeEventListener(accountChangedEvent,accountChange);window.removeEventListener('galaxycontrol:shortcut',refresh);};
 },[client]);
 useEffect(()=>{if(error||(account&&!account.signedIn))return finishToolsStartup();},[account,error]);
 async function login(){setBusy(true);setError('');try{observer.current?.replace(await client.accountLogin());}catch{setError('loginError');}finally{setBusy(false);}}
 async function cancel(){setBusy(true);setError('');try{observer.current?.replace(await client.accountCancel());}catch{setError('connectionError');}finally{setBusy(false);}}
 if(!client.webContext&&account?.signedIn)return <>{children}</>;
 return <section className="kio-login-gate" aria-label={copy.title}>
  <label className="kio-login-language" title={copy.language}><Globe2 size={21} aria-hidden="true"/><select aria-label={copy.language} value={language} onChange={event=>onLanguageChange(event.target.value as ToolLanguage)}>{orderedToolLanguages(language).map(item=><option key={item} value={item} lang={item}>{loginLanguageNames[item]}</option>)}</select></label>
  <div className="kio-login-card">
   <header className="kio-login-title"><BrandIcon/><h1>Bogo Tools</h1></header>
   <p className="kio-login-intro">{client.webContext?copy.installed:copy.hint}</p>
   {!client.webContext&&<>
    <button type="button" className="kio-login-continue" disabled={busy||!account||account.connecting} onClick={()=>void login()}>{busy||account?.connecting?<LoaderCircle size={18} className="kio-login-spinner" aria-hidden="true"/>:<ArrowUpRight size={18} aria-hidden="true"/>}<span>{copy.continue}</span></button>
    <div className="kio-login-feedback" aria-live="polite">{!account&&!error?<span><LoaderCircle size={15} className="kio-login-spinner" aria-hidden="true"/>{copy.checking}</span>:account?.connecting?<><span><LoaderCircle size={15} className="kio-login-spinner" aria-hidden="true"/>{copy.connecting}</span><button type="button" className="kio-login-cancel" disabled={busy} onClick={()=>void cancel()}>{copy.cancel}</button></>:<small>{copy.note}</small>}</div>
    {(error||account?.error)&&<p role="alert" className="kio-login-error">{error?copy[error]:copy.retry}</p>}
   </>}
  </div>
 </section>;
}
