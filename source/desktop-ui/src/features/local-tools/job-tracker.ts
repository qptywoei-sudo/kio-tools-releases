import type {AgentJob} from './types';
const terminal=new Set(['complete','completed','failed','cancelled']);
export class AgentJobTracker{
 private latest=new Map<string,AgentJob>();
 private waiting=new Map<string,(job:AgentJob)=>void>();
 private cleanups=new Map<string,()=>void>();
 constructor(private poll:(id:string)=>Promise<AgentJob>,private eventsConnected:()=>boolean){}
 update(job:AgentJob){this.latest.set(job.id,job);if(terminal.has(job.status))this.waiting.get(job.id)?.(job);}
 wait(job:AgentJob,timeoutMs=600000){const current=this.latest.get(job.id)??job;if(terminal.has(current.status))return this.result(current);return new Promise<AgentJob>((resolve,reject)=>{
  const finish=(value:AgentJob)=>{cleanup();void this.result(value).then(resolve,reject);};
  let polling=false;const timer=setInterval(()=>{if(this.eventsConnected()||polling)return;polling=true;void this.poll(job.id).then(value=>this.update(value)).catch(()=>{}).finally(()=>{polling=false;});},250);
  const expiry=setTimeout(()=>{cleanup();reject(Error('processingFailed'));},timeoutMs);
  const cleanup=()=>{clearInterval(timer);clearTimeout(expiry);this.waiting.delete(job.id);this.cleanups.delete(job.id);};
  this.waiting.set(job.id,finish);this.cleanups.set(job.id,()=>{cleanup();reject(Error('cancelled'));});
 });}
 private result(job:AgentJob){return job.status==='complete'||job.status==='completed'?Promise.resolve(job):Promise.reject(Error(job.errorCode||'processingFailed'));}
 dispose(){for(const cleanup of [...this.cleanups.values()])cleanup();this.latest.clear();}
}
