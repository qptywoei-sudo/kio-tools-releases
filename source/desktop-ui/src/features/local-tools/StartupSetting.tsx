import {useRef,useState} from 'react';
import {Power,RefreshCw} from 'lucide-react';
import type {AgentSettings,ToolTranslate} from './types';
import {useToolsLocale} from './tool-locale';

export function StartupSetting({settings,disabled,onChange,t}:{settings:AgentSettings;disabled:boolean;onChange:(enabled:boolean)=>Promise<boolean>;t:ToolTranslate}){
 const {ui}=useToolsLocale();
 const pending=useRef(false),[saving,setSaving]=useState(false),[failed,setFailed]=useState(false);
 const needsRepair=settings.autoStart===true&&['blocked','repair','error'].includes(settings.autoStartStatus??'');
 async function save(enabled:boolean){
  if(disabled||pending.current||settings.autoStart===undefined)return;
  pending.current=true;setSaving(true);setFailed(false);
  try{if(!await onChange(enabled))setFailed(true);}catch{setFailed(true);}finally{pending.current=false;setSaving(false);}
 }
 return <section className="kio-preference-card"><h3><Power size={17}/>{ui('프로그램 시작')}</h3>
  <label className="kio-setting-line"><span><strong>{t('tools.autoStart')}</strong><small>{ui('컴퓨터에 로그인하면 Bogo Tools 실행')}</small></span><input type="checkbox" role="switch" aria-label={t('tools.autoStart')} disabled={disabled||saving||settings.autoStart===undefined} checked={settings.autoStart===true} onChange={event=>void save(event.target.checked)}/></label>
  <p className="lt-note" aria-live="polite">{saving?ui('자동 실행 설정 저장 중…'):settings.autoStart===undefined?ui('자동 실행 상태 확인 중…'):ui('스위치를 변경하면 바로 저장됩니다.')}</p>
  {needsRepair&&<div role="status"><p className="lt-note">{settings.autoStartStatus==='blocked'?ui('Windows에서 자동 실행을 차단했습니다. 복구를 누르면 Bogo Tools 시작 항목만 다시 켭니다.'):ui('자동 실행 등록을 확인하지 못했습니다. 복구를 눌러 다시 등록해 주세요.')}</p><button type="button" className="lt-button" disabled={disabled||saving} onClick={()=>void save(true)}><RefreshCw size={15}/>{ui('자동 실행 복구')}</button></div>}
  {failed&&<p className="lt-error" role="alert">{ui('자동 실행 설정을 저장하지 못했습니다. 다시 시도해 주세요.')}</p>}
 </section>;
}
