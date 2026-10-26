import {useState} from 'react';
import {Circle,Monitor,Pause,Play,Square} from 'lucide-react';
import {supportedOperation} from '@/services/local-agent';
import type {AgentHealth,AgentJob,RecordingPreferences,ToolTranslate} from './types';
import {recordingActionAllowed,recordingPhase,selectedRecordingMonitor,type RecordingAction} from './recording-controls';
import './recording-controls.css';

const buttons=[['record_start',Circle],['record_pause',Pause],['record_resume',Play],['record_stop',Square]] as const;
export function RecordingControls({health,paired,busy,t,preferences={mode:'full'},onPreferences,onRecord,onError}:{health:AgentHealth|null;paired:boolean;busy:boolean;t:ToolTranslate;preferences?:RecordingPreferences;onPreferences?:(value:RecordingPreferences)=>Promise<void>;onRecord:(action:RecordingAction,options:Record<string,unknown>)=>Promise<AgentJob|null>;onError:(error:unknown)=>void}){
 const [saving,setSaving]=useState(false),[audio,setAudio]=useState({microphone:false,systemAudio:false}),phase=recordingPhase(health),locked=!paired||busy||saving;
 const monitors=health?.monitors??[],selected=selectedRecordingMonitor(preferences,health),mode=preferences.mode;
 async function change(next:RecordingPreferences){if(locked||phase!=='idle')return;setSaving(true);try{await onPreferences?.(next);}catch(error){onError(error);}finally{setSaving(false);}}
 async function record(action:RecordingAction){try{await onRecord(action,action==='record_start'?{...preferences,...audio}:{});}catch(error){onError(error);}}
 const missing=(health?.os==='macOS'||mode==='full'&&health?.os==='Windows')&&!selected;
 return <div className="gc-recording"><section className="lt-panel gc-record-panel" aria-label={t('tools.record')} aria-busy={busy||saving}>
  <div className="gc-record-heading"><h2>{t('tools.recordTarget')}</h2><span className={'gc-record-status '+phase} role="status">{t('tools.'+(busy?'recordWorking':phase==='idle'?'recordIdle':phase==='paused'?'recordPaused':'recordActive'))}</span></div>
  <fieldset className="gc-record-options" disabled={locked||phase!=='idle'}>
   <div className="kio-record-modes">{(['full','area','window'] as const).map(value=><button type="button" className={'lt-button'+(mode===value?' primary':'')} key={value} aria-pressed={mode===value} onClick={()=>void change({...preferences,mode:value})}>{t('tools.'+value)}</button>)}</div>
   {(mode==='full'||health?.os==='macOS')&&<details className="kio-record-displays" open><summary>{t('tools.recordMonitors')} · {monitors.length}</summary>
    {monitors.length?<div className="kio-record-monitor-grid">{monitors.map((monitor,index)=><button key={monitor.name||monitor.id} type="button" aria-pressed={selected?.id===monitor.id} className={'kio-record-monitor'+(selected?.id===monitor.id?' selected':'')} onClick={()=>void change({...preferences,monitor:monitor.id,monitorName:monitor.name})}><Monitor size={30}/><strong>{t('tools.recordMonitor')} {index+1}</strong><small>{monitor.width} × {monitor.height}{monitor.primary?' · '+t('tools.primary'):''}</small></button>)}</div>:<p className="lt-note">{t('tools.recordMonitorLoading')}</p>}
    {missing&&monitors.length>0&&<p role="alert" className="lt-error">{t('tools.error.recordMonitorMissing')}</p>}
   </details>}
   {mode==='window'&&<p className="lt-note">{t('tools.recordWindowHint')}</p>}{mode==='area'&&<p className="lt-note">{t('tools.recordAreaHint')}</p>}
   <div className="lt-actions gc-record-audio">{(['microphone','systemAudio'] as const).filter(key=>health?.recordingOptions?.[key]!==false).map(key=><label className="lt-row" key={key}><input type="checkbox" checked={audio[key]} onChange={event=>setAudio(current=>({...current,[key]:event.target.checked}))}/>{t('tools.'+key)}</label>)}</div>
  </fieldset>
  <div className="gc-record-buttons">{buttons.map(([action,Icon])=><button key={action} className={'lt-button'+(action==='record_start'?' primary':'')} disabled={locked||!supportedOperation(health,action)||!recordingActionAllowed(action,health)||(action==='record_start'&&missing)} onClick={()=>void record(action)}><Icon size={18}/>{t('tools.'+action)}</button>)}</div>
  <p className="lt-note">{t('tools.recordDirectHint')}</p>
 </section></div>;
}
