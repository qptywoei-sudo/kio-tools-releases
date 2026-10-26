import {identityUi,type UiTranslate,useToolsLocale} from './tool-locale';
import {useEffect,useRef,useState} from 'react';
import {Download,RefreshCw} from 'lucide-react';
import type {LocalAgentClient} from '@/services/local-agent';
import type {UpdateStatus} from './update-types';
import './update-settings.css';
const messages:Record<string,string>={
 updateDriveAccess:'업데이트 파일에 접근할 수 없습니다. 잠시 후 다시 확인해 주세요.',
 updateInvalidSignature:'다운로드 검증에 실패했습니다. 현재 버전은 그대로 유지됩니다. 다시 다운로드해 주세요.',
 updateInvalidManifest:'업데이트 정보를 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.',
 updateNetwork:'인터넷 연결 또는 배포 서버를 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.',
 updateDiskSpace:'업데이트를 설치할 저장 공간이 부족합니다. 공간을 확보한 뒤 다시 시도해 주세요.',
 updateNotConfigured:'업데이트 배포 주소가 설정되지 않았습니다.',
 updateTargetInvalid:'이 위치에서는 프로그램을 교체할 수 없습니다. 쓰기 가능한 폴더로 옮긴 뒤 다시 실행해 주세요.',
 updateNotReady:'먼저 새 버전을 다운로드해 주세요.',
 updateNotAvailable:'새 버전이 있는지 먼저 확인해 주세요.',
 updateInstallFailed:'업데이트를 적용하지 못했습니다. 프로그램을 다시 열어 재시도해 주세요.',
 updateProgramBusy:'프로그램 파일이 사용 중이거나 교체 권한이 없습니다. 열린 도구를 종료한 뒤 다시 시도해 주세요.',
 updateRestartFailed:'새 프로그램을 시작하지 못했습니다. 이전 버전 복구 상태를 확인해 주세요.',
 updateCloseCancelled:'프로그램 종료가 취소되었습니다. 열린 편집 창을 저장하고 다시 시도해 주세요.',
 busy:'녹화나 진행 중인 작업을 마친 후 업데이트해 주세요.',
};
export function updateMessage(value:unknown){const key=value instanceof Error?value.message:String(value);return messages[key]??'업데이트 상태를 확인하지 못했습니다. 다시 시도해 주세요.';}
export function updateSummary(status:UpdateStatus,ui:UiTranslate=identityUi){switch(status.phase){case 'checking':return ui('새 버전을 확인하고 있습니다…');case 'current':return ui('최신 버전을 사용하고 있습니다.');case 'available':return ui('{v0} 버전을 사용할 수 있습니다.',{v0:status.latestVersion??''});case 'downloading':return ui('새 버전을 다운로드하고 있습니다…');case 'ready':return ui('다운로드 완료 · 다시 시작하면 업데이트됩니다.');case 'preparing':return ui('업데이트를 준비하고 있습니다…');case 'restarting':return ui('프로그램이 닫힌 후 업데이트하고 다시 열립니다. 잠시 기다려 주세요.');case 'error':return ui(updateMessage(status.error));default:return ui('최신 버전을 확인해 보세요.');}}
export function UpdateSettings({client,connected,expanded,onOpen}:{client:LocalAgentClient;connected:boolean;expanded:boolean;onOpen:()=>void}){
 const {ui}=useToolsLocale();

 const [status,setStatus]=useState<UpdateStatus|null>(null),[pending,setPending]=useState(false),[error,setError]=useState('');
 const alive=useRef(true),revision=useRef(0),phase=useRef('idle');
 useEffect(()=>{alive.current=true;if(!connected)return()=>{alive.current=false;};let timer:ReturnType<typeof setTimeout>;let cancelled=false;
  async function poll(){const current=revision.current;try{const next=await client.updateStatus();if(!cancelled&&current===revision.current){phase.current=next.phase;setStatus(next);}}catch{/* Preserve the restart screen while the local service is closing. */}finally{if(!cancelled)timer=setTimeout(()=>void poll(),['checking','downloading','preparing','restarting'].includes(phase.current)?1200:15000);}}
  void poll();return()=>{alive.current=false;cancelled=true;clearTimeout(timer);};
 },[client,connected]);
 async function act(action:'check'|'download'|'install'|boolean){if(pending)return;revision.current++;setPending(true);setError('');try{const next=typeof action==='boolean'?await client.updatePreferences(action):await client.updateAction(action);if(alive.current){phase.current=next.phase;setStatus(next);}}catch(e){if(alive.current)setError(updateMessage(e));}finally{if(alive.current)setPending(false);}}
 const working=pending||!!status&&['checking','downloading','preparing','restarting'].includes(status.phase);
 if(!expanded)return status?.available?<div className="kio-update-banner" role="status"><span><strong>Bogo Tools {status.latestVersion}</strong> {ui("새 버전이 준비되었습니다.")}</span><button className="lt-button" onClick={onOpen}>{ui("업데이트 보기")}</button></div>:null;
 return <section className="lt-panel kio-updates" aria-label={ui("프로그램 업데이트")}><div className="lt-row"><div><h2>{ui("업데이트")}</h2><p className="lt-note">{ui("현재 버전")}{status?.currentVersion??ui("확인 중")}</p></div><button className="lt-button" disabled={!connected||working} onClick={()=>void act('check')}><RefreshCw size={16}/> {ui("최신 버전 확인")}</button></div>
 <p role="status" className={status?.phase==='error'?'lt-error':'kio-update-status'}>{status?updateSummary(status,ui):ui("업데이트 정보를 불러오고 있습니다…")}</p>
 {status?.lastFailure&&<p role="alert" className="lt-error">{ui("이전")}{status.lastFailure.version} {ui("업데이트 실패:")}{ui(updateMessage(status.lastFailure.error))}{status.lastFailure.reopened?ui(" 기존 프로그램을 다시 열었습니다."):''}</p>}
 {status?.phase==='downloading'&&<div><progress aria-label={ui("업데이트 다운로드")} max={Math.max(1,status.total)} value={status.received}/><p className="lt-note">{Math.floor(status.received/1024/1024)} / {Math.ceil(status.total/1024/1024)} MB</p></div>}
 {status?.available&&status.notes.length>0&&<ul className="kio-update-notes">{status.notes.map((note,i)=><li key={i}>{note}</li>)}</ul>}
 <div className="lt-actions">{status?.available&&!['ready','preparing','restarting'].includes(status.phase)&&<button className="lt-button primary" disabled={working||!connected} onClick={()=>void act('download')}><Download size={16}/> {ui("새 버전 다운로드")}</button>}{status?.phase==='ready'&&<button className="lt-button primary" disabled={working||!connected} onClick={()=>void act('install')}>{ui("업데이트하고 다시 시작")}</button>}</div>
 {error&&<p role="alert" className="lt-error">{ui(error)}</p>}
 <label className="kio-update-auto"><input type="checkbox" checked={status?.autoCheck??true} disabled={!connected||!status||working} onChange={e=>void act(e.target.checked)}/><span>{ui("새 버전 자동 확인")}<small>{ui("앱을 시작할 때와 실행 중 하루에 한 번 확인합니다.")}</small></span></label>
 <p className="lt-note">{ui("다운로드 후 ‘업데이트하고 다시 시작’을 누르면 적용됩니다. 작업을 저장하고 녹화를 마친 뒤 진행해 주세요.")}</p>
 {status?.checkedAt&&<p className="lt-note">{ui("마지막 확인:")}{new Date(status.checkedAt*1000).toLocaleString()}</p>}
 </section>;
}
