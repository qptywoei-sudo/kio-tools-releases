import {useToolsLocale} from './tool-locale';
const letters=Array.from({length:26},(_,i)=>String.fromCharCode(65+i));
const functionKeys=Array.from({length:24},(_,i)=>'F'+(i+1));
export function shortcutIssue(value:string,windows=true){
 if(!value)return '';
 const parts=value.split('+'),key=parts.pop()??'',allowed=windows?['Control','Shift','Alt','Win']:['Control','Shift','Option','Command'];
 if(!parts.length||parts.some(part=>!allowed.includes(part))||new Set(parts).size!==parts.length)return '조합 버튼을 선택해 주세요.';
 if(windows&&(/^[A-Z]$/.test(key)||key==='Space')&&parts.length<2)return '영문 키는 조합 버튼을 2개 이상 선택해 주세요.';
 if(!windows&&['C','V'].includes(key)&&parts.length===1&&['Control','Command'].includes(parts[0]))return '복사·붙여넣기에 쓰이는 조합입니다. 다른 키를 선택해 주세요.';
 if(windows&&value==='Control+Shift+F10')return '이 조합은 사용할 수 없습니다. 다른 키를 선택해 주세요.';
 return '';
}
export function ShortcutPicker({label,value,onChange,windows=true}:{label:string;value:string;onChange:(value:string)=>void;windows?:boolean}){
 const {ui}=useToolsLocale();

 const parts=value.split('+'),key=value?parts.at(-1)??'A':'',selected=parts.slice(0,-1);
 const modifiers=windows?[['Control','Ctrl'],['Shift','Shift'],['Alt','Alt'],['Win','Win']]:[['Control','Ctrl'],['Shift','Shift'],['Option','Option'],['Command','⌘']];
 const change=(nextKey:string,nextModifiers=selected)=>onChange(nextKey?[...(nextModifiers.length?nextModifiers:['Control','Shift']),nextKey].join('+'):'');
 const issue=shortcutIssue(value,windows);
 return <div className="kio-shortcut-picker" role="group" aria-label={label+ui(" 단축키")}>
  <div className="kio-shortcut-title"><strong>{label}</strong><kbd>{value?value.replace('Control','Ctrl').replace('Command','⌘'):ui("사용 안 함")}</kbd></div>
  <div className="kio-shortcut-choices">{modifiers.map(([id,text])=><button key={id} type="button" className="lt-button" aria-label={label+' '+text} aria-pressed={selected.includes(id)} onClick={()=>{const next=modifiers.map(([name])=>name).filter(name=>name===id?!selected.includes(name):selected.includes(name));onChange([...next,key||'A'].join('+'));}}>{text}</button>)}<select aria-label={label+ui(" 영문 키")} value={key} onChange={event=>change(event.target.value)}><option value="">{ui("사용 안 함")}</option><optgroup label={ui("영문 키")}>{letters.map(letter=><option key={letter}>{letter}</option>)}</optgroup>{windows&&<optgroup label={ui("기능 키")}>{[...functionKeys,'PrintScreen','Space'].map(name=><option key={name}>{name}</option>)}</optgroup>}{!windows&&/^[0-9]$/.test(key)&&<option>{key}</option>}</select></div>
  {issue&&<small className="kio-shortcut-error" role="status">{issue}</small>}
 </div>;
}
