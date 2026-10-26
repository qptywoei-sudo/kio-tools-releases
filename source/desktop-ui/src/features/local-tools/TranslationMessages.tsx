import {useToolsLocale} from './tool-locale';
import type {ReactNode} from 'react';
import type {AIMessage} from './ai-types';
export function translationSpeakerText(message:AIMessage){return [message.speaker,message.speakerTranslated&&message.speakerTranslated!==message.speaker?message.speakerTranslated:''].filter(Boolean).join(' / ');}
export function translationMessageText(message:AIMessage){return [translationSpeakerText(message),message.originalText,message.translatedText].filter(Boolean).join('\n');}
export function TranslationMessages({messages,target,replyOpen,working,onTarget,copyButton}:{messages:AIMessage[];target:number|null;replyOpen:boolean;working:boolean;onTarget:(index:number)=>void;copyButton:(text:string,key:string,title:string)=>ReactNode}){
 const {ui}=useToolsLocale();

 return <div className="kio-ai-messages">{messages.map((message,index)=><article key={index} className={target===index?'selected':''}>
  <header><div className="kio-ai-speaker"><strong>{message.speaker||(message.isMine===true?ui("나"):ui("원문"))}</strong>{message.speakerTranslated&&message.speakerTranslated!==message.speaker&&<small> / {message.speakerTranslated}</small>}</div><span className="kio-ai-language" title={ui("원문 언어")}>{message.language??ui("언어 확인 필요")}</span>{replyOpen&&message.isMine!==true&&<button className="lt-button" disabled={working||!message.language||message.confidence<.6} aria-label={ui("{v0} 답장 대상 선택",{v0:message.speaker||'메시지 '+(index+1)})} aria-pressed={target===index} onClick={()=>onTarget(index)}>{ui("답장 대상")}</button>}</header>
  <div className="kio-ai-text" aria-label={ui("원문")}><p>{message.originalText}</p>{copyButton(message.originalText,'original-'+index,ui("원문 복사 ")+(index+1))}</div>
  <div className="kio-ai-text translated" aria-label={ui("번역")}><p>{message.translatedText}</p>{copyButton(message.translatedText,'translated-'+index,ui("번역 복사 ")+(index+1))}</div>
  {(message.confidence<.8||message.isTruncated)&&<small className="kio-ai-read-warning">{[message.confidence<.8?ui("판독 확인 필요"):'',message.isTruncated?ui("일부 잘림"):''].filter(Boolean).join(' · ')}</small>}
 </article>)}</div>;
}
