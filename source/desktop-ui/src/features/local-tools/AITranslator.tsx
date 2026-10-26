import {useToolsLocale,orderedToolLanguages,toolLanguageNames,normalizeToolLanguage} from './tool-locale';
import {useEffect,useRef,useState} from 'react';
import {Check,Copy,Languages,LoaderCircle,MessageSquare,Pin,ScanLine,Send,Settings2,Unlink,X} from 'lucide-react';
import type {LocalAgentClient} from '@/services/local-agent';
import {aiError,type AIStatus,type AIJob,type AITranslation,type AIReply,type AIScan,type AITask,type AISmartResult,type AIImageTranslation} from './ai-types';
import {notifyDesktopCapture,notifyDesktopCaptureSize,notifyDesktopAIPin} from './desktop-events';
import './ai-translator.css';
import {SmartScanPicker,SmartScanResult,smartText,scanTools} from './SmartScanPanel';
import {TranslationMessages,translationMessageText} from './TranslationMessages';
import {AIImageResult} from './AIImageResult';
import {AIModelSettings} from './AIModelSettings';
import {AIReplyComposer,replyRequest} from './AIReplyComposer';
import {chatGPTConnectionAction,aiReadinessError} from './ai-connection-state';

export function AITranslator({client,connected,trigger=0,settingsOnly=false,shortcut='Control+Shift+T',onBusyChange}:{client:LocalAgentClient;connected:boolean;trigger?:number;settingsOnly?:boolean;shortcut?:string;onBusyChange?:(busy:boolean)=>void}){
 const {ui}=useToolsLocale();

 const [status,setStatus]=useState<AIStatus|null>(null),[error,setError]=useState(''),[working,setWorking]=useState(false),[job,setJob]=useState<AIJob|null>(null),[translation,setTranslation]=useState<AITranslation|null>(null),[reply,setReply]=useState<AIReply|null>(null),[replyOpen,setReplyOpen]=useState(false),[intent,setIntent]=useState(''),[target,setTarget]=useState<number|null>(null),[edited,setEdited]=useState(''),[copied,setCopied]=useState(''),[pinned,setPinned]=useState(false),[showSettings,setShowSettings]=useState(false);
 const languages=[...orderedToolLanguages(normalizeToolLanguage(status?.settings.language)??'ko').map(code=>[code,toolLanguageNames[code]]),['other',ui('기타')]];
 const [imageTranslation,setImageTranslation]=useState<AIImageTranslation|null>(null),[scan,setScan]=useState<AIScan|null>(null),[preview,setPreview]=useState(''),[task,setTask]=useState<AITask|null>(null),[smart,setSmart]=useState<AISmartResult|null>(null),[followUp,setFollowUp]=useState('');
 const lastInstruction=useRef(''),requestPending=useRef(false),statusRevision=useRef(0),accountPending=useRef(false);
 const live=useRef(true),active=useRef<string|null>(null),cancelled=useRef(false),seen=useRef(0),current=useRef(status),lastAccount=useRef(''),captureVisible=useRef(false),loadingModels=useRef(''),captureKind=useRef(false);
 current.current=status;
 useEffect(()=>{onBusyChange?.(working);return()=>onBusyChange?.(false);},[working,onBusyChange]);
 useEffect(()=>{const replace=()=>{captureVisible.current=false;};window.addEventListener('galaxycontrol:capture-replacing',replace);return()=>window.removeEventListener('galaxycontrol:capture-replacing',replace);},[]);
 useEffect(()=>{live.current=true;return()=>{live.current=false;cancelled.current=true;const id=active.current;if(id)void client.aiCancel(id).catch(()=>{});if(!settingsOnly)void client.aiClear().catch(()=>{});if(captureVisible.current)notifyDesktopCapture('captureClosed');notifyDesktopAIPin(false);};},[client,settingsOnly]);
 useEffect(()=>{if(!connected)return;let valid=true;const refresh=()=>{const revision=statusRevision.current;if(accountPending.current)return;void client.aiStatus().then(value=>{if(!valid||revision!==statusRevision.current||accountPending.current)return;setStatus(value);if(lastAccount.current&&lastAccount.current!==value.activeAccount){setTranslation(null);setReply(null);setImageTranslation(null);setScan(null);setSmart(null);setTask(null);}lastAccount.current=value.activeAccount;}).catch(()=>{});};refresh();const timer=setInterval(refresh,2000);return()=>{valid=false;clearInterval(timer);};},[client,connected]);
 useEffect(()=>{if(settingsOnly||!trigger||seen.current===trigger||!status)return;seen.current=trigger;void capture(trigger);},[trigger,status,settingsOnly]);
 useEffect(()=>{if(!status?.planApproved||!status.activeAccount||status.models.length||loadingModels.current===status.activeAccount)return;const accountId=status.activeAccount,revision=statusRevision.current;loadingModels.current=accountId;void client.aiAccount('models').then(value=>{if(live.current&&revision===statusRevision.current&&current.current?.activeAccount===accountId)setStatus(value);}).catch(e=>{if(live.current&&revision===statusRevision.current&&current.current?.activeAccount===accountId)setError(ui(aiError(e)));}).finally(()=>{if(loadingModels.current===accountId)loadingModels.current='';});},[client,status?.activeAccount,status?.planApproved,status?.models.length]);
 useEffect(()=>{if(settingsOnly)return;const selected=()=>{captureVisible.current=true;setJob(value=>value?{...value,stage:'uploading'}:value);if(active.current)void client.aiMetrics(active.current,{popupShownAt:Date.now()}).catch(()=>{});};window.addEventListener('galaxycontrol:ai-selected',selected);return()=>window.removeEventListener('galaxycontrol:ai-selected',selected);},[client,settingsOnly]);
 useEffect(()=>{let valid=true,url='';setPreview('');if(scan)void client.aiScanPreview(scan.scanId).then(blob=>{if(valid){url=URL.createObjectURL(blob);setPreview(url);}}).catch(e=>{if(valid)setError(ui(aiError(e)));});return()=>{valid=false;if(url)URL.revokeObjectURL(url);};},[client,scan]);
 async function account(action:Parameters<LocalAgentClient['aiAccount']>[0],body:Record<string,unknown>={}){if(accountPending.current)return;accountPending.current=true;const revision=++statusRevision.current;setWorking(true);setError('');try{const value=await client.aiAccount(action,body);if(live.current&&revision===statusRevision.current)setStatus(value);}catch(e){if(live.current&&revision===statusRevision.current)setError(ui(aiError(e)));}finally{accountPending.current=false;if(live.current)setWorking(false);}}
 async function copy(text:string,key:string){try{await navigator.clipboard.writeText(text);setCopied(key);setTimeout(()=>{if(live.current)setCopied('');},1400);}catch{setError(ui("복사하지 못했습니다. 글자를 선택한 뒤 Ctrl+C로 복사해 주세요."));}}
 async function run(kind:'capture'|'scan'|'analyze'|'reply'|'retranslate',body:Record<string,unknown>={}){
  if(requestPending.current)return null;requestPending.current=true;
  setError('');setWorking(true);cancelled.current=false;captureKind.current=kind==='capture'||kind==='scan';
  try{
   let value=await client.aiStart(kind,{startedAt:Date.now(),...body});active.current=value.id;
   if(cancelled.current){await client.aiCancel(value.id);return null;}
   setJob(value);
   while(value.status==='running'){
    await new Promise(resolve=>setTimeout(resolve,220));if(!live.current)return null;
    value=await client.aiJob(value.id);if(cancelled.current)return null;setJob(value);
    if((kind==='capture'||kind==='scan')&&value.stage!=='capture'&&!captureVisible.current){captureVisible.current=true;notifyDesktopCapture('captureReady');notifyDesktopCaptureSize(570,570,110);}
   }
   if(value.status==='cancelled')return null;
   if(value.status!=='complete'||!value.result)throw Error(value.error||'aiRequestFailed');
   requestAnimationFrame(()=>requestAnimationFrame(()=>{if(live.current&&!cancelled.current)void client.aiMetrics(value.id,{popupCompletedAt:Date.now()}).catch(()=>{});}));
   return value.result;
  }catch(e){if(live.current&&!cancelled.current)setError(ui(aiError(e)));return null;}
  finally{requestPending.current=false;active.current=null;if(live.current){setWorking(false);setJob(null);}}
 }
 async function capture(startedAt=Date.now()){
  if(working)return;setImageTranslation(null);setScan(null);setTask(null);setSmart(null);setFollowUp('');setTranslation(null);setReply(null);setReplyOpen(false);setIntent('');setEdited('');captureVisible.current=false;
  notifyDesktopCapture('captureStarted');
  const result=await run('scan',{startedAt}) as AIScan|null;
  if(!live.current)return;
  if(result){setScan(result);setTarget(null);setShowSettings(false);captureVisible.current=true;notifyDesktopCapture('captureReady');notifyDesktopCaptureSize(470,450,70);}
  else{notifyDesktopCapture('captureCancelled');captureVisible.current=false;}
 }
 async function cancel(){cancelled.current=true;const id=active.current;if(id)await client.aiCancel(id).catch(()=>{});if(captureKind.current){notifyDesktopCapture('captureCancelled');captureVisible.current=false;}else if(!replyOpen){setTask(null);setSmart(null);}}
 function close(){setImageTranslation(null);setScan(null);setTask(null);setSmart(null);setFollowUp('');cancelled.current=true;if(active.current)void client.aiCancel(active.current).catch(()=>{});setTranslation(null);setReply(null);setEdited('');setIntent('');setReplyOpen(false);void client.aiClear().catch(()=>{});notifyDesktopAIPin(false);setPinned(false);notifyDesktopCapture('captureClosed');captureVisible.current=false;}
 function selectReplyTarget(index:number|null){if(working)return;setTarget(index);setReply(null);setEdited('');}
 async function generate(mode:'auto'|'intent'|'retranslate'){
  if(!translation||working||requestPending.current)return;
  const body=replyRequest(translation,target,intent,mode,edited);if(!body)return;
  if(mode!=='retranslate'){setReply(null);setEdited('');}
  const value=await run(mode==='retranslate'?'retranslate':'reply',body) as AIReply|null;
  if(live.current&&value){setReply(value);setEdited(value.replyText);}
 }
 async function analyze(next:AITask,instruction='',force=false){
  if(!scan||working)return;if(!ready){setShowSettings(true);setError(ui(aiError(readinessError)));return;}lastInstruction.current=instruction;setTask(next);setSmart(null);setImageTranslation(null);setReplyOpen(false);setFollowUp('');notifyDesktopCaptureSize(570,570,110);
  const result=await run('analyze',{scanId:scan.scanId,task:next,instruction,force});
  if(!live.current||!result)return;
  if(next==='translate'){const value=result as AITranslation;setTranslation(value);setTarget(value.replyTarget);setReply(null);setEdited('');}
  else if(next==='translate-image')setImageTranslation(result as AIImageTranslation);
  else setSmart(result as AISmartResult);
 }
 function otherTools(){if(working)return;setTask(null);setSmart(null);setImageTranslation(null);setError('');setReplyOpen(false);setFollowUp('');notifyDesktopCaptureSize(470,450,70);}
 const readinessError=aiReadinessError(status),ready=!readinessError,settings=status?.settings;
 const connectionAction=chatGPTConnectionAction(status);
 const copyButton=(text:string,key:string,title:string)=><button className="lt-button lt-icon-button" title={title} aria-label={title} onClick={()=>void copy(text,key)}>{copied===key?<Check size={15}/>:<Copy size={15}/>}</button>;
 const settingsView=<div className="kio-ai-settings">
  <div className="kio-ai-account"><span className="kio-ai-symbol"><Languages size={23}/></span><div><strong>{ui("ChatGPT 연결")}</strong><small>{status?.connecting?ui("브라우저에서 연결을 완료하세요"):status?.connected?status.email:ui("내 ChatGPT 계정으로 연결하세요")}</small><small className={status?.planApproved?'approved':''}>{status?.planApproved?ui("ChatGPT 플랜 사용 승인됨"):status?.connected?ui("플랜 사용 권한 미승인"):ui("연결 안 됨")}</small></div></div>
  <div className="kio-ai-actions">{status?.connecting?<button className="lt-button" onClick={()=>void account('cancel-login')}>{ui("로그인 취소")}</button>:<><button className={connectionAction==='connect'?'kio-chatgpt-connect':'lt-button primary'} disabled={working||!connected} onClick={()=>void account(connectionAction,connectionAction==='connect'&&status?.activeAccount?{accountId:status.activeAccount}:{})}>{connectionAction==='connect'?'Continue with ChatGPT':ui('연결 확인')}</button>{status?.connected&&<button className="lt-button" disabled={working} onClick={()=>void account('disconnect')}><Unlink size={14}/>{ui("연결 해제")}</button>}<button className="lt-button" disabled={working||!connected} onClick={()=>void account('connect',{newAccount:true})}>{ui("다른 계정 추가")}</button></>}</div>
  {!!status?.accounts.length&&<label>{ui("사용할 계정")}<select aria-label={ui("ChatGPT 계정")} disabled={working||status.connecting} value={status.activeAccount} onChange={e=>void account('select-account',{accountId:e.target.value})}>{status.accounts.map(row=><option key={row.id} value={row.id}>{row.label}{!row.connected?ui(" · 다시 로그인"):''}</option>)}</select></label>}
  <details className="kio-ai-hint"><summary>{ui("회사 계정으로 로그인이 안 되나요?")}</summary><p>{ui("“조직에서 이 앱에 접근 권한을 부여하지 않았습니다” 또는 3p_delegated_access_policy_denied가 보이면 회사 조직의 접근 정책에 의해 차단된 상태입니다.")}</p><p>{ui("ChatGPT 조직 관리자에게 Bogo Tools의 외부 앱 접근 허용과 해당 계정의 ChatGPT 플랜 사용 지원 여부를 확인해 달라고 요청하세요. 허용 항목이 없으면 오류 화면의 요청 ID와 발생 시간을 OpenAI 지원에 전달해 확인해야 합니다. 허용 후 다시 연결하세요.")}</p><p>{ui("브라우저의 오류 화면에서는 결과가 앱으로 돌아오지 않을 수 있습니다. 아래 로그인 취소 버튼으로 대기를 끝낼 수 있습니다. 재설치만으로 조직 정책이 바뀌지는 않습니다.")}</p><a href="https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery" target="_blank" rel="noreferrer">{ui("공식 연결 오류 안내 ↗")}</a></details>
  <label>{ui("내 기준 언어")}<select aria-label={ui("내 기준 언어")} disabled={working||!settings} value={settings?.language??'ko'} onChange={e=>void account('settings',{language:e.target.value})}>{languages.map(([id,name])=><option value={id} key={id}>{name}</option>)}</select></label>
  <AIModelSettings status={status} disabled={working} onChange={patch=>void account('settings',patch)} onRefresh={()=>void account('models')}/>
  {settings?.language==='other'&&<label>{ui("기준 언어 이름")}<input aria-label={ui("기준 언어 이름")} maxLength={120} defaultValue={settings.customLanguage} onBlur={e=>void account('settings',{customLanguage:e.target.value.trim()})}/></label>}
  <div className="kio-ai-actions"><a href="https://chatgpt.com/settings/usage" target="_blank" rel="noreferrer">{ui("ChatGPT 사용량 관리 ↗")}</a></div>
  <label className="kio-ai-consent"><input type="checkbox" checked={settings?.consent??false} disabled={working||!settings} onChange={e=>void account('settings',{consent:e.target.checked})}/><span>{ui("선택한 화면을 OpenAI에 전송하는 것을 확인했습니다.")}<small>{ui("결과는 복사해서 사용할 수 있습니다. ChatGPT 플랜 사용량을 공유합니다.")}</small></span></label>
 </div>;
 const popup=!!(scan||translation||job);
 return <section className={'kio-ai'+(!settingsOnly?(popup?' kio-ai-popup':' kio-ai-landing'):'')} aria-label={ui("AI 스마트 스캔")}>
  <header><div>{settingsOnly||popup?<><Languages size={20}/><strong>{settingsOnly?ui("AI 스마트 스캔 설정"):(ui("AI 스마트 스캔")+(task?' · '+ui(scanTools.find(t=>t.id===task)?.name??''):''))}</strong></>:<span className={'kio-ai-connection'+(ready?' connected':'')}><span aria-hidden="true"/>{ready?ui("ChatGPT 연결됨"):ui("ChatGPT 연결 설정")}</span>}</div><div>{!settingsOnly&&<><button className={'lt-button'+(popup?' lt-icon-button':'')} title={ui("연결·언어·모델 설정")} aria-label={ui("AI 설정")} onClick={()=>setShowSettings(v=>!v)}><Settings2 size={16}/>{!popup&&ui("AI 설정")}</button>{popup&&<button className={'lt-button lt-icon-button'+(pinned?' active':'')} aria-pressed={pinned} title={ui("항상 위에 표시")} aria-label={ui("항상 위에 표시")} onClick={()=>{notifyDesktopAIPin(!pinned);setPinned(!pinned);}}><Pin size={16}/></button>}{popup&&<button className="lt-button lt-icon-button" title={ui("스캔 닫기")} aria-label={ui("스캔 닫기")} onClick={close}><X size={17}/></button>}</>}</div></header>
  {(settingsOnly||showSettings||(!ready&&!scan))&&settingsView}
  {status?.welcomeNeeded&&<div className="kio-ai-welcome" role="dialog" aria-label={ui("ChatGPT 플랜 사용 안내")}><strong>{ui("ChatGPT 플랜을 사용합니다")}</strong><p>{ui("이 기능의 AI 요청은 승인한 ChatGPT 플랜 사용량을 사용합니다. 사용량과 한도는 ChatGPT 설정에서 관리하세요.")}</p><button className="lt-button primary" onClick={()=>void account('welcome')}>{ui("확인했어요")}</button></div>}
  {(error||status?.error)&&<p className="lt-error" role="alert">{ui(error||aiError(status?.error))}</p>}
  {!settingsOnly&&<>{!scan&&!translation&&!job&&<div className="kio-ai-start"><span className="kio-ai-start-icon"><ScanLine size={30}/></span><h2>{ui("필요한 화면을 선택하세요")}</h2><p>{ui("번역, 글자 추출, 요약까지.")}<br/>{ui("화면을 캡처하고 필요한 기능을 고르면 됩니다.")}</p><button className="lt-button primary" disabled={!connected||working} onClick={()=>void capture()}><ScanLine size={18}/>{ui("화면 선택하기")}</button><div className="kio-ai-shortcut"><span>{ui("단축키로 바로 시작")}</span><kbd>{shortcut||ui("설정에서 지정")}</kbd></div><ol className="kio-ai-steps" aria-label={ui("AI 스캔 사용 순서")}><li><span>1</span>{ui("영역 선택")}</li><li><span>2</span>{ui("기능 선택")}</li><li><span>3</span>{ui("결과 복사")}</li></ol></div>}
   {job&&<div className="kio-ai-progress" role="status"><LoaderCircle size={17} className="kio-ai-spin"/><span>{job.stage==='rendering'?ui('번역 이미지를 만드는 중…'):job.stage==='capture'?ui("화면 영역을 드래그하세요 · Esc 취소"):job.stage==='reply'?ui("답장 작성 중…"):job.stage==='uploading'?(captureKind.current?ui("선택 영역 준비 중…"):ui("이미지 전송 중…")):job.received?ui("AI 응답을 받고 있습니다…"):captureKind.current?ui("선택 영역 준비 중…"):ui("AI 처리 중…")}</span><button className="lt-button" onClick={()=>void cancel()}>{ui("취소")}</button></div>}
   {scan&&!task&&!job&&<><SmartScanPicker preview={preview} disabled={working} onChoose={next=>void analyze(next)}/><button className="lt-button kio-scan-rescan" disabled={working} onClick={()=>void capture()}><ScanLine size={15}/>{ui("다시 스캔")}</button></>}
   {task==='translate-image'&&scan&&<AIImageResult key={scan.scanId} client={client} scanId={scan.scanId} value={imageTranslation}/>}
   {task&&smart&&<SmartScanResult value={smart} onCopy={(text,key)=>void copy(text,key)} onTranslate={()=>void analyze('translate')}/>}
   {task==='translate'&&translation&&<><div className="kio-ai-meta"><span>{ui("내 언어")}{languages.find(([id])=>id===translation.baseLanguage)?.[1]??translation.baseLanguage}</span><span>{ui("자동 감지")}{translation.originalLanguage??ui("확인 필요")}</span><small>{ui("ChatGPT 플랜 사용 중")}</small></div>
    <TranslationMessages messages={translation.messages} target={target} replyOpen={replyOpen} working={working} onTarget={selectReplyTarget} copyButton={copyButton}/>
    <div className="kio-ai-actions kio-ai-footer">{copyButton(translation.messages.map(m=>m.originalText).join('\n\n'),'original-all',ui("원문 전체 복사"))}{copyButton(translation.messages.map(m=>m.translatedText).join('\n\n'),'translated-all',ui("번역 전체 복사"))}<button className="lt-button" onClick={()=>void copy(translation.messages.map(translationMessageText).join('\n\n'),'all')}><Copy size={15}/>{ui("전체 복사")}</button><button className="lt-button primary" disabled={working} aria-expanded={replyOpen} onClick={()=>setReplyOpen(v=>!v)}><MessageSquare size={15}/>{ui("답장 만들기")}</button></div>
    {replyOpen&&<AIReplyComposer messages={translation.messages} target={target} working={working} intent={intent} edited={edited} reply={reply} onTarget={selectReplyTarget} onIntent={setIntent} onEdited={setEdited} onGenerate={mode=>void generate(mode)} copyButton={copyButton}/>}
   </>}
   {scan&&task&&!job&&<div className="kio-scan-bottom">
    {error&&<button className="lt-button primary" onClick={()=>void analyze(task,lastInstruction.current,true)}>{ui("다시 시도")}</button>}
    {(smart||task==='translate'&&translation)&&<><div className="kio-scan-followup"><input aria-label={ui("추가 요청")} placeholder={task==='formula'?ui("셀 범위 변경, Excel 버전 등 추가 요청"):ui("더 짧게, 더 정중하게 등 추가 요청")} maxLength={5000} value={followUp} onChange={e=>setFollowUp(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.nativeEvent.isComposing&&followUp.trim())void analyze(task,followUp.trim());}}/><button className="lt-button lt-icon-button primary" title={ui("추가 요청 적용")} aria-label={ui("추가 요청 적용")} disabled={!followUp.trim()} onClick={()=>void analyze(task,followUp.trim())}><Send size={16}/></button></div></>}
    <div className="kio-ai-actions">{smart&&<button className="lt-button" onClick={()=>void copy(smartText(smart,ui),'smart-all')}><Copy size={15}/>{ui("결과 전체 복사")}</button>}<button className="lt-button" onClick={otherTools}>{ui("다른 기능")}</button><button className="lt-button" onClick={()=>void capture()}><ScanLine size={15}/>{ui("다시 스캔")}</button></div>
   </div>}
   {!!copied&&<span className="kio-scan-copied" role="status"><Check size={13}/>{ui("복사했어요")}</span>}
  </>}
 </section>;
}
