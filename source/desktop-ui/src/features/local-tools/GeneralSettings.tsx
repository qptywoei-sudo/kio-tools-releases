import {useToolsLocale} from './tool-locale';
import {useEffect,useState} from 'react';
import {Camera,Check,Command,Keyboard,ShieldCheck} from 'lucide-react';
import type {AgentSettings,ToolTranslate} from './types';
import './general-settings.css';
import {ShortcutPicker,shortcutIssue} from './ShortcutPicker';
import {StartupSetting} from './StartupSetting';

export function GeneralSettings({settings,onSettings,permissions,t,disabled,onPermission,onApply,onShortcutsChange,onStartupChange,windows=true}:{windows?:boolean;settings:AgentSettings;onSettings:(value:AgentSettings)=>void;permissions:Record<string,string>;t:ToolTranslate;disabled:boolean;onPermission:(permission:string)=>void;onApply:()=>void;onStartupChange:(enabled:boolean)=>Promise<boolean>;onShortcutsChange:(value:Record<string,string>)=>Promise<boolean>}){
 const {ui}=useToolsLocale();

 const [draft,setDraft]=useState(settings.shortcuts??{});
 useEffect(()=>setDraft(settings.shortcuts??{}),[settings.shortcuts]);
 async function changeShortcut(key:string,value:string){
  const next={...draft,[key]:value};setDraft(next);
  const values=Object.values(next).filter(Boolean) as string[];
  if(values.some(v=>shortcutIssue(v,windows))||new Set(values).size!==values.length)return;
  if(!await onShortcutsChange(next as Record<string,string>))setDraft(settings.shortcuts??{});
 }
 const chosen=Object.values(draft).filter(Boolean) as string[];
 const invalid=chosen.some(value=>shortcutIssue(value,windows))||new Set(chosen).size!==chosen.length;
 return <section className="lt-panel kio-preferences" aria-label={ui("프로그램 설정")}>
  <header><span className="kio-preferences-icon"><Command size={22}/></span><div><h2>{ui("내 작업에 맞게")}</h2><p>{ui("캡처 방식, 단축키와 프로그램 시작을 한곳에서 설정하세요.")}</p></div></header>
  <fieldset disabled={disabled} className="kio-preference-grid">
   <section className="kio-preference-card"><h3><Camera size={17}/>{t('tools.capture')}</h3><label className="kio-setting-line"><span><strong>{ui("기본 이미지 형식")}</strong><small>{ui("캡처할 때 사용할 저장 형식")}</small></span><select aria-label={ui("기본 캡처 형식")} value={settings.captureFormat??'png'} onChange={e=>onSettings({...settings,captureFormat:e.target.value as 'png'|'jpg'})}><option value="png">PNG</option><option value="jpg">JPG</option></select></label>
    <label className="kio-setting-line"><span><strong>{t('tools.openCaptureEditor')}</strong><small>{ui("캡처한 뒤 바로 편집 화면 열기")}</small></span><input type="checkbox" role="switch" checked={settings.openCaptureEditor!==false} onChange={e=>onSettings({...settings,openCaptureEditor:e.target.checked})}/></label>
    <label className="kio-setting-line"><span><strong>{ui("저장·복사 후 편집창 닫기")}</strong><small>{ui("Ctrl+C 또는 Ctrl+S 완료 후 닫습니다")}</small></span><input type="checkbox" role="switch" checked={settings.closeAfterCaptureCopy!==false} onChange={e=>onSettings({...settings,closeAfterCaptureCopy:e.target.checked})}/></label>
   </section>
   <section className="kio-preference-card"><h3><Keyboard size={17}/>{t('tools.shortcuts')}</h3><p className="lt-note">{ui("단축키는 변경하면 자동 저장됩니다. 완전히 종료하거나 업데이트한 뒤에도 유지됩니다.")}</p><div className="kio-shortcuts">{['areaCapture','fullCapture','webCapture','recordToggle','recordArea','aiTranslate'].map(key=><ShortcutPicker key={key} label={t('tools.'+key)} windows={windows} value={draft[key]??''} onChange={value=>void changeShortcut(key,value)}/>)}</div>{new Set(chosen).size!==chosen.length&&<p className="kio-shortcut-error" role="alert">{ui("같은 단축키가 있습니다. 서로 다른 조합을 선택해 주세요.")}</p>}</section>
   <StartupSetting settings={settings} disabled={disabled} onChange={onStartupChange} t={t}/>
   <section className="kio-preference-card"><h3><ShieldCheck size={17}/>{t('tools.permission')}</h3><div className="kio-permission-list">{['screenCapture','accessibility','files'].map(permission=><div key={permission}><span>{t('tools.'+permission)}<small className={permissions[permission]==='available'?'available':''}>{t(permissions[permission]==='available'?'tools.available':'tools.needsPermission')}</small></span><button type="button" className="lt-button" onClick={()=>onPermission(permission)}>{t('tools.open')}</button></div>)}</div></section>
  </fieldset><footer><span>{ui("단축키와 자동 실행은 바로 저장됩니다. 캡처 설정은 적용을 눌러 주세요.")}</span><button className="lt-button primary" disabled={disabled||invalid} onClick={onApply}><Check size={16}/>{ui("설정 적용")}</button></footer>
 </section>;
}
