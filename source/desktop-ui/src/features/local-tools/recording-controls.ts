import type {AgentHealth,AgentJob,RecordingPreferences} from './types';

export type RecordingAction='record_start'|'record_pause'|'record_resume'|'record_stop';
export type RecordingPhase='idle'|'recording'|'paused';
export function recordingPhase(health:Pick<AgentHealth,'recording'|'paused'>|null):RecordingPhase{
 return !health?.recording?'idle':health.paused?'paused':'recording';
}
export function recordingActionAllowed(action:RecordingAction,health:Pick<AgentHealth,'recording'|'paused'>|null){
 const phase=recordingPhase(health);
 return action==='record_start'?phase==='idle':action==='record_pause'?phase==='recording':action==='record_resume'?phase==='paused':phase!=='idle';
}

export function selectedRecordingMonitor(preferences:Partial<RecordingPreferences>,health:AgentHealth|null){
 const monitors=health?.monitors??[];
 if(preferences.monitorName)return monitors.find(m=>m.name===preferences.monitorName);
 if(preferences.monitor!==undefined)return monitors.find(m=>m.id===preferences.monitor);
 return monitors.find(m=>m.primary)??monitors[0];
}
export function resolveRecordingTarget(options:Record<string,unknown>,health:AgentHealth){
 const {monitorName,...result}=options;
 if(!['Windows','macOS'].includes(health.os??''))return result;
 const mode=options.mode??'full';
 const monitor=selectedRecordingMonitor(mode==='full'||health.os==='macOS'?options as Partial<RecordingPreferences>:{},health);
 if(!monitor)throw Error('recordMonitorMissing');
 return {...result,mode,monitor:monitor.id};
}

// The native shortcut and the visible buttons share one synchronous lock.
// Confirmed native state, including a failed/cancelled command, drives the UI.
export class RecordingCommandGate{
 pending=false;
 async run(action:RecordingAction|'toggle',options:Record<string,unknown>,ports:{health:()=>Promise<AgentHealth>;execute:(action:RecordingAction,options:Record<string,unknown>)=>Promise<AgentJob>;onHealth:(health:AgentHealth)=>void;onBusy:(busy:boolean)=>void}){
  if(this.pending)return null;
  this.pending=true;ports.onBusy(true);
  try{
   const before=await ports.health();ports.onHealth(before);
   const command=action==='toggle'?(before.recording?'record_stop':'record_start'):action;
   if(!recordingActionAllowed(command,before))return null;
   const job=await ports.execute(command,command==='record_start'?resolveRecordingTarget(options,before):{});
   const data=job.result?.data;
   if(typeof data?.recording==='boolean')ports.onHealth({...before,recording:data.recording,paused:data.recording&&data.paused===true});
   return job;
  }finally{
   try{ports.onHealth(await ports.health());}catch{/* Retain the last confirmed state while disconnected. */}
   this.pending=false;ports.onBusy(false);
  }
 }
}

export function recordingGifOptions(values:{start:number;duration:number;width:number;fps:number}){
 const {start,duration,width,fps}=values;
 if(![start,duration,width,fps].every(Number.isFinite)||start<0||start>86400||duration<.02||duration>120||!Number.isInteger(width)||width<64||width>1920||!Number.isInteger(fps)||fps<1||fps>30)throw Error('invalidRequest');
 return {ranges:[{start,end:start+duration}],width,fps};
}
