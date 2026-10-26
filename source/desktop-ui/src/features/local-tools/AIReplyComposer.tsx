import {useToolsLocale} from './tool-locale';
import {useState,type ReactNode} from 'react';
import {ChevronDown,Send,Sparkles} from 'lucide-react';
import type {AIMessage,AIReply,AITranslation} from './ai-types';

export function canReplyTo(message:AIMessage|undefined){return !!message&&message.isMine!==true&&!!message.language&&message.confidence>=.6;}
export function replyRequest(translation:AITranslation,target:number|null,intent:string,mode:'auto'|'intent'|'retranslate',edited=''){
 if(target===null||!canReplyTo(translation.messages[target]))return null;
 if(mode==='intent'&&!intent.trim()||mode==='retranslate'&&!edited.trim())return null;
 return {sessionId:translation.sessionId,target,intent:mode==='intent'?intent.trim():'',...(mode==='retranslate'?{replyText:edited}:{})};
}
type Props={messages:AIMessage[];target:number|null;working:boolean;intent:string;edited:string;reply:AIReply|null;onTarget:(index:number|null)=>void;onIntent:(text:string)=>void;onEdited:(text:string)=>void;onGenerate:(mode:'auto'|'intent'|'retranslate')=>void;copyButton:(text:string,key:string,title:string)=>ReactNode};
export function AIReplyComposer({messages,target,working,intent,edited,reply,onTarget,onIntent,onEdited,onGenerate,copyButton}:Props){
 const {ui}=useToolsLocale();

 const [custom,setCustom]=useState(false),selected=target===null?undefined:messages[target];
 const eligible=messages.map((message,index)=>({message,index})).filter(({message})=>canReplyTo(message));
 return <section className="kio-ai-reply" aria-label={ui("답장 만들기")}>
  <div className="kio-ai-reply-target"><label htmlFor="kio-reply-target">{ui("답장 대상")}</label><select id="kio-reply-target" aria-label={ui("답장 대상")} disabled={working} value={target??''} onChange={e=>onTarget(e.target.value===''?null:Number(e.target.value))}><option value="">{ui("상대방 메시지를 선택하세요")}</option>{eligible.map(({message,index})=><option value={index} key={index}>{message.speaker||ui("메시지 {v0}",{v0:index+1})} · {message.originalText.slice(0,65)}</option>)}</select></div>
  <div className="kio-ai-actions"><button className="lt-button primary" disabled={working||!canReplyTo(selected)} onClick={()=>onGenerate('auto')}><Sparkles size={15}/>{ui("자동 답장 생성")}</button><button className="lt-button" disabled={working} aria-expanded={custom} onClick={()=>setCustom(v=>!v)}><ChevronDown size={14}/>{ui("원하는 내용 지정")}</button>{selected?.language&&<small className="kio-ai-hint">{ui("답장 언어 ·")}{selected.language}</small>}</div>
  {!eligible.length&&<p className="kio-ai-hint">{ui("상대방 언어를 확인할 수 없습니다. 메시지가 보이도록 다시 스캔해 주세요.")}</p>}
  {custom&&<div className="kio-ai-intent"><textarea aria-label={ui("원하는 답장 내용")} rows={2} placeholder={ui("예: 확인했고 담당자에게 전달하겠다고 정중하게")} disabled={working} maxLength={5000} value={intent} onChange={e=>onIntent(e.target.value)}/><button className="lt-button lt-icon-button primary" title={ui("입력한 내용으로 답장 생성")} aria-label={ui("입력한 내용으로 답장 생성")} disabled={working||!canReplyTo(selected)||!intent.trim()} onClick={()=>onGenerate('intent')}><Send size={15}/></button></div>}
  {reply&&<>
   <div className="kio-ai-reply-edit"><header><label htmlFor="kio-edited-reply">{ui("상대방에게 보낼 답장")}</label>{copyButton(edited,'reply',ui("답장만 복사"))}</header><textarea id="kio-edited-reply" aria-label={ui("상대방에게 보낼 답장")} rows={2} disabled={working} value={edited} maxLength={30000} onChange={e=>onEdited(e.target.value)}/></div>
   {edited===reply.replyText?<div className="kio-ai-reply-meaning"><small>{ui("내 언어로 된 뜻")}</small><div className="kio-ai-text"><p>{reply.translatedText}</p>{copyButton(reply.translatedText,'meaning',ui("답장 뜻 복사"))}</div><div className="kio-ai-actions"><small className="kio-ai-hint">{ui("확인 후 복사해서 사용하세요")}</small>{copyButton(edited+'\n'+reply.translatedText,'reply-both',ui("답장 두 언어 함께 복사"))}</div></div>:<div className="kio-ai-actions"><p className="kio-ai-hint">{ui("답장을 수정했습니다.")}</p><button className="lt-button" disabled={working||!edited.trim()} onClick={()=>onGenerate('retranslate')}>{ui("수정한 답장 뜻 확인")}</button></div>}
  </>}
 </section>;
}
