import {useEffect,useMemo,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {ThemeProvider} from '@/contexts/ThemeContext';
import {LocalAgentClient} from '@/services/local-agent';
import {KIOAccountGate} from '@/features/local-tools/KIOAccountGate';
import {ToolsApp} from '@/features/local-tools/ToolsApp';
import {localToolsTranslator} from '@/features/local-tools/translations';
import type {ToolLanguage} from '@/features/local-tools/types';
import {normalizeToolLanguage,orderedToolLanguages,toolLanguageNames as names} from '@/features/local-tools/tool-locale';
import {initialLanguage,saveLanguage,type Language} from '@/i18n/language';
import '@/styles/globals.css';
import '@/features/local-tools/kio-theme.css';
function StandaloneTools(){
 const [client]=useState(()=>new LocalAgentClient());
 const [initial]=useState(initialLanguage);
 const [language,setLanguage]=useState<ToolLanguage>(normalizeToolLanguage(initial.language)??'en');
 const pending=useRef<Language|undefined>(initial.source==='user'?initial.language:undefined),saving=useRef(false);
 useEffect(()=>{document.documentElement.lang=language;},[language]);
 const translate=useMemo(()=>localToolsTranslator(language),[language]);
 const changeLanguage=(next:ToolLanguage)=>{const canonical=next==='zh'?'zh-CN':next;saveLanguage(canonical);pending.current=canonical;setLanguage(next);try{localStorage.setItem('focus-base.language',next);}catch{}document.documentElement.lang=canonical;void synchronize();};
 async function synchronize(){
  if(saving.current)return;saving.current=true;
  try{
   while(pending.current){const next=pending.current;await client.selectLanguage(next);if(pending.current===next)pending.current=undefined;}
   const value=await client.languagePreference();
   if(!pending.current){if(value.source==='user')saveLanguage(value.language);setLanguage(normalizeToolLanguage(value.language)??'en');}
  }catch{console.warn('Bogo i18n: nativePreferencePending');}finally{saving.current=false;}
 }
 useEffect(()=>{void synchronize();const timer=setInterval(()=>void synchronize(),2000),resume=()=>void synchronize();window.addEventListener('focus',resume);return()=>{clearInterval(timer);window.removeEventListener('focus',resume);};},[client]);
 const languages=orderedToolLanguages(language);
 return <main className="lt-standalone"><KIOAccountGate client={client} language={language} onLanguageChange={changeLanguage}><ToolsApp client={client} language={language} t={translate} standalone headerControls={<select aria-label={names[language]} value={language} onChange={event=>{changeLanguage(event.target.value as ToolLanguage);}}>{languages.map(item=><option key={item} value={item}>{names[item]}</option>)}</select>}/></KIOAccountGate></main>;
}
createRoot(document.getElementById('root')!).render(<ThemeProvider><StandaloneTools/></ThemeProvider>);
