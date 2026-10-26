import {useToolsLocale} from './tool-locale';
import {useEffect,useState,type ReactNode} from 'react';
import {Cloud,DownloadCloud,Languages,LogOut,SlidersHorizontal,UserRound} from 'lucide-react';
import type {LocalAgentClient} from '@/services/local-agent';
import type {KIOAccountStatus} from './kio-account';
import './control-settings.css';
import {publishAccountLogout} from './account-session';

const sections=[{id:'general',label:'일반',Icon:SlidersHorizontal},{id:'account',label:'계정',Icon:UserRound},{id:'storage',label:'저장 · Drive',Icon:Cloud},{id:'ai',label:'AI 연결',Icon:Languages},{id:'updates',label:'업데이트',Icon:DownloadCloud}] as const;
export type ControlSettingsSection=typeof sections[number]['id'];
export function ControlSettings({client,section,onSection,general,storage,ai,updates}:{client:LocalAgentClient;section:ControlSettingsSection;onSection:(section:ControlSettingsSection)=>void;general:ReactNode;storage:ReactNode;ai:ReactNode;updates:ReactNode}){
 const {ui}=useToolsLocale();

 const [account,setAccount]=useState<KIOAccountStatus|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{if(section!=='account')return;let live=true;void client.accountStatus().then(value=>{if(live)setAccount(value);}).catch(()=>{if(live)setError(ui("계정을 확인하지 못했습니다."));});return()=>{live=false;};},[client,section]);
 async function logout(){setBusy(true);setError('');try{publishAccountLogout(await client.accountLogout());}catch{setError(ui("로그아웃하지 못했습니다. 다시 시도해 주세요."));}finally{setBusy(false);}}
 return <section className="kio-control-settings" aria-label={ui("Bogo Tools 설정")}><nav className="kio-settings-tabs" role="tablist" aria-orientation="horizontal" aria-label={ui("설정 항목")}>{sections.map(({id,label,Icon})=><button type="button" key={id} id={'settings-tab-'+id} role="tab" aria-selected={section===id} aria-controls="settings-pane" tabIndex={section===id?0:-1} onKeyDown={event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const index=sections.findIndex(item=>item.id===section),next=event.key==='Home'?0:event.key==='End'?sections.length-1:(index+(event.key==='ArrowRight'?1:-1)+sections.length)%sections.length;onSection(sections[next].id);document.getElementById('settings-tab-'+sections[next].id)?.focus();}} onClick={()=>onSection(id)}><Icon size={16}/><span>{ui(label)}</span></button>)}</nav><div id="settings-pane" className="kio-settings-pane" role="tabpanel" aria-labelledby={'settings-tab-'+section}>{section==='general'?general:section==='storage'?storage:section==='ai'?ai:section==='updates'?updates:<section className="lt-panel kio-settings-account"><header><span className="kio-account-avatar"><UserRound size={24}/></span><div><h2>{account?.user?.name||ui("Bogo 계정")}</h2><p>{account?.user?.email||ui("계정 확인 중…")}</p></div><span className="kio-account-badge">{ui("로그인됨")}</span></header><div className="kio-account-detail"><strong>{ui("Bogo Tools에서 작업")}</strong><small>{ui("웹앱을 열거나 닫아도 모든 도구와 단축키는 이 프로그램에서 실행됩니다.")}</small></div><div className="kio-account-detail"><strong>{ui("Google Drive 공유")}</strong><small>{ui("같은 Bogo 계정에서 연결한 Drive를 이어 사용합니다. 저장 위치는 Bogo 지정 폴더입니다.")}</small></div><footer><small>{ui("로그아웃해도 저장한 파일과 단축키 설정은 유지됩니다.")}</small><button className="lt-button" disabled={busy} onClick={()=>void logout()}><LogOut size={15}/>{busy?ui("로그아웃 중…"):ui("로그아웃")}</button></footer>{error&&<p className="lt-error" role="alert">{error}</p>}</section>}</div></section>;
}
