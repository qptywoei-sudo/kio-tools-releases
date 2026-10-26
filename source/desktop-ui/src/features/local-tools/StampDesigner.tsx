import {useToolsLocale} from './tool-locale';
import {useMemo} from 'react';
import {Plus} from 'lucide-react';
import {stampLayouts,stampImage,stampBorders,stampFonts,stampFontSize,stampDateFormats,formatStampDate,type StampDateFormat,type StampOptions} from './signature-geometry';

export function StampDesigner({stamp,url,onChange,onNew,editing,disabled}:{stamp:StampOptions;url:string;onChange:(patch:Partial<StampOptions>)=>void;onNew:()=>void;editing:boolean;disabled:boolean}){
 const {ui}=useToolsLocale();

 const templates=useMemo(()=>stampLayouts.map(([layout,label])=>({layout,label,url:stampImage({shape:stamp.shape,color:stamp.color,name:ui("홍길동"),company:'Bogo',date:'2026.10.12',layout})})),[stamp.shape,stamp.color]);
 return <fieldset className="kio-stamp-designer" disabled={disabled}>
  <div className="kio-stamp-editing"><strong>{editing?ui("선택한 도장 수정"):ui("새 도장 만들기")}</strong>{editing&&<button type="button" className="lt-button" onClick={onNew}><Plus size={14}/>{ui("새 도장")}</button>}</div>
  <div className="kio-stamp-shapes" aria-label={ui("도장 모양")}>{([['circle',ui("원형")],['oval',ui("타원형")],['square',ui("정사각")],['rect',ui("직사각")],['diamond',ui("마름모")],['hexagon',ui("육각형")]] as const).map(([shape,label])=><button type="button" className={stamp.shape===shape?'active':''} key={shape} aria-pressed={stamp.shape===shape} onClick={()=>onChange({shape})}><i className={shape}/>{ui(label)}</button>)}</div>
  <div className="kio-stamp-layouts" aria-label={ui("도장 글자 배치")}>{templates.map(item=><button type="button" key={item.layout} aria-label={ui(item.label)} aria-pressed={(stamp.layout??'stacked')===item.layout} className={(stamp.layout??'stacked')===item.layout?'active':''} onClick={()=>onChange({layout:item.layout})}><img src={item.url} alt=""/><span>{ui(item.label)}</span></button>)}</div>
  <label>{ui("테두리 스타일")}<select aria-label={ui("도장 테두리")} value={stamp.border??'double'} onChange={event=>onChange({border:event.target.value as StampOptions['border']})}>{stampBorders.map(([value,label])=><option key={value} value={value}>{ui(label)}</option>)}</select></label>
  <label>{ui("글씨체")}<select aria-label={ui("도장 글씨체")} value={stamp.font??'ko-gothic'} onChange={event=>onChange({font:event.target.value as StampOptions['font']})}>{["한국어","한자"].map(group=><optgroup key={group} label={ui("{v0} 글꼴",{v0:ui(group)})}>{stampFonts.filter(font=>font.group===group).map(font=><option key={font.id} value={font.id}>{ui(font.label)}</option>)}</optgroup>)}</select></label>
  <small>{ui("PC에 설치된 글꼴을 사용합니다. 없는 글꼴은 비슷한 기본 글꼴로 표시됩니다. 한자 이름은 직접 입력해 주세요.")}</small>
  <label>{ui("이름 / 문구")}<input aria-label={ui("도장 이름")} maxLength={30} value={stamp.name} onChange={event=>onChange({name:event.target.value})}/></label>
  <label>{ui("회사명 · 선택")}<input aria-label={ui("도장 회사명")} maxLength={40} value={stamp.company} onChange={event=>onChange({company:event.target.value})}/></label>
  <div className="kio-signature-inline"><label>{ui("날짜 · 선택")}<input aria-label={ui("도장 날짜")} type="date" value={stamp.date} onChange={event=>onChange({date:event.target.value})}/></label><label>{ui("색상")}<input aria-label={ui("도장 색상")} type="color" value={stamp.color} onChange={event=>onChange({color:event.target.value})}/></label></div>
  <button type="button" className="lt-button" onClick={()=>onChange({date:''})}>{ui("날짜 빼기")}</button>
  <label>{ui("날짜 표시 형식")}<select aria-label={ui("도장 날짜 표시 형식")} value={stamp.dateFormat??'ymd-dash'} onChange={event=>onChange({dateFormat:event.target.value as StampDateFormat})}>{stampDateFormats.map(([value,label])=><option key={value} value={value}>{ui(label)} · {formatStampDate(stamp.date||'2026-10-13',value)}</option>)}</select></label>
  <div className="kio-stamp-text-sizes">{([['nameSize',ui("이름"),100],['companySize',ui("회사명"),50],['dateSize',ui("날짜"),39]] as const).map(([key,label,fallback])=>{const value=stampFontSize(stamp[key],fallback);return <div key={key}><span>{ui(label)}</span><input type="range" aria-label={ui("{v0} 글자 크기",{v0:label})} min={12} max={180} value={value} onChange={event=>onChange({[key]:Number(event.target.value)})}/><input type="number" aria-label={ui("{v0} 글자 크기 값",{v0:label})} min={12} max={180} value={value} onChange={event=>onChange({[key]:stampFontSize(Number(event.target.value),fallback)})}/><small>px</small></div>;})}</div>
  <small className="kio-stamp-fit-hint">{ui("긴 글자는 도장 안에 맞춰집니다. 빈 항목은 표시하지 않습니다.")}</small>
  <div className="kio-stamp-preview">{url&&<img src={url} alt={ui("만든 도장 미리보기")}/>}</div>
 </fieldset>;
}
