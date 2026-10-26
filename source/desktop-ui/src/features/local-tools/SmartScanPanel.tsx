import {identityUi,type UiTranslate,useToolsLocale} from './tool-locale';
import {Languages,ScanText,Wrench,FileText,Table2,SpellCheck,Calculator,CalendarDays,MessageSquare,Copy,Image as ImageIcon} from 'lucide-react';
import type {AITask,AISmartResult} from './ai-types';
export const scanTools=[
 {id:'translate',name:'번역',icon:Languages},{id:'translate-image',name:'이미지 번역',icon:ImageIcon},{id:'extract',name:'글자 추출',icon:ScanText},{id:'error',name:'오류 해결',icon:Wrench},
 {id:'summary',name:'글 요약',icon:FileText},{id:'table',name:'표 추출',icon:Table2},{id:'correct',name:'문장 교정',icon:SpellCheck},
 {id:'formula',name:'수식 도움',icon:Calculator},{id:'schedule',name:'일정 추출',icon:CalendarDays},{id:'write',name:'답장·글쓰기',icon:MessageSquare},
] as const;
export function SmartScanPicker({preview,onChoose,disabled}:{preview:string;onChoose:(task:AITask)=>void;disabled:boolean}){
 const {ui}=useToolsLocale();

 return <div className="kio-scan-picker">{preview&&<div className="kio-scan-preview"><img src={preview} alt={ui("선택한 화면 영역")}/><span>{ui("이 영역에 사용할 기능을 선택하세요")}</span></div>}<div className="kio-scan-grid">{scanTools.map(({id,name,icon:Icon})=><button key={id} disabled={disabled} onClick={()=>onChoose(id)}><Icon size={19}/><span>{ui(name)}</span></button>)}</div></div>;
}
export function tableTSV(value:AISmartResult){
 const cell=(s:string)=>{const safe=/^[=+@-]/.test(s)&&!/^[-+]?\d+(\.\d+)?$/.test(s)?"'"+s:s;return /[\t\n\r"]/.test(safe)?'"'+safe.replaceAll('"','""')+'"':safe;};
 return [...(value.columns?.length?[value.columns]:[]),...(value.rows??[])].map(row=>row.map(cell).join('\t')).join('\n');
}
export function noCorrectionNeeded(value:AISmartResult){return value.task==='correct'&&typeof value.originalText==='string'&&!!value.originalText.trim()&&value.text?.trim()===value.originalText.trim()&&!value.uncertain.length;}
export function smartText(value:AISmartResult,ui:UiTranslate=identityUi){
 if(noCorrectionNeeded(value))return value.originalText+'\n\n'+ui('교정할 사항이 없습니다.');
 if(value.task==='table')return tableTSV(value);
 return [value.originalText,value.text,value.cause,...(value.steps??[]),...(value.points??[]),value.formula,value.explanation,...(value.changes??[]),...(value.events??[]).map(e=>[e.title,e.date,e.time,e.place,e.notes].filter(Boolean).join(' · ')),value.meaning,...value.uncertain].filter(Boolean).join('\n\n');
}
export function SmartScanResult({value,onCopy,onTranslate}:{value:AISmartResult;onCopy:(text:string,key:string)=>void;onTranslate:()=>void}){
 const {ui}=useToolsLocale();

 const copyButton=(text:string,key:string,label:string)=><button className="lt-button lt-icon-button" title={label+ui(" 복사")} aria-label={label+ui(" 복사")} onClick={()=>onCopy(text,key)}><Copy size={14}/></button>;
 const block=(label:string,text:string|undefined,key:string)=>text?<section className="kio-scan-block"><small>{label}</small><p>{text}</p>{copyButton(text,key,label)}</section>:null;
 return <div className="kio-scan-result">
  {block(ui("원문"),value.originalText,'smart-original')}{noCorrectionNeeded(value)?<p className="kio-ai-hint" role="status">{ui("교정할 사항이 없습니다.")}</p>:block(value.task==='write'?ui("보낼 문장"):value.task==='correct'?ui("교정된 문장"):ui("추출한 글자"),value.text,'smart-text')}{block(ui("오류 원인"),value.cause,'smart-cause')}
  {!!value.steps?.length&&<ol>{value.steps.map((text,i)=><li key={i}><div className="kio-scan-list-line"><span>{text}</span>{copyButton(text,'step-'+i,ui("조치 ")+(i+1))}</div></li>)}</ol>}
  {!!value.points?.length&&<ul>{value.points.map((text,i)=><li key={i}><div className="kio-scan-list-line"><span>{text}</span>{copyButton(text,'point-'+i,ui("요점 ")+(i+1))}</div></li>)}</ul>}
  {value.task==='table'&&<section><header className="kio-scan-inline-header"><small>{ui("표 · Excel에 붙여넣기")}</small>{copyButton(tableTSV(value),'table',ui("Excel용 표 (TSV)"))}</header><div className="kio-scan-table"><table>{!!value.columns?.length&&<thead><tr>{value.columns.map((s,i)=><th key={i}>{s}</th>)}</tr></thead>}<tbody>{value.rows?.map((row,i)=><tr key={i}>{row.map((s,j)=><td key={j} tabIndex={0}>{s}</td>)}</tr>)}</tbody></table></div></section>}
  {block(ui("수식만"),value.formula,'formula')}{block(ui("수식 설명"),value.explanation,'explanation')}
  {!noCorrectionNeeded(value)&&!!value.changes?.length&&<p className="kio-ai-hint">{value.changes.join('\n')}</p>}
  {value.events?.map((e,i)=><section className="kio-scan-event" key={i}><header className="kio-scan-inline-header"><strong>{e.title}</strong>{copyButton([e.title,e.date,e.time,e.place,e.notes].filter(Boolean).join('\n'),'event-'+i,ui("일정 ")+(i+1))}</header><dl>{[[ui("날짜"),e.date],[ui("시간"),e.time],[ui("장소"),e.place],[ui("추가 내용"),e.notes]].map(([label,text])=><div key={label}><dt>{label}</dt><dd>{text||ui("확인 필요")}</dd></div>)}</dl></section>)}
  {block(ui("내 언어로 된 뜻"),value.meaning,'smart-meaning')}
  {value.needsTarget&&<button className="lt-button primary" onClick={onTranslate}>{ui("번역에서 답장 대상 선택")}</button>}
  {!!value.uncertain.length&&<div className="kio-scan-uncertain" role="note"><strong>{ui("확인이 필요해요")}</strong>{value.uncertain.map((text,i)=><p key={i}>{text}</p>)}</div>}
 </div>;
}
