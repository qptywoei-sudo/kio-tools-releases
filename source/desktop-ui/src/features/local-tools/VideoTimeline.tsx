import {useToolsLocale} from './tool-locale';
import {useEffect,useMemo,useRef,type PointerEvent} from 'react';
import {bound,clipLength,clockLabel,projectDuration,timelineClips,type VideoProject,type Selection} from './video-editor';
import type {MediaAsset} from './VideoEditorPreview';
type Props={project:VideoProject;assets:MediaAsset[];time:number;zoom:number;selection:Selection|null;onTime:(time:number)=>void;onZoom:(zoom:number)=>void;onSelect:(s:Selection)=>void;onCheckpoint:()=>void;onUpdate:(p:VideoProject)=>void};
export function VideoTimeline({project,assets,time,zoom,selection,onTime,onZoom,onSelect,onCheckpoint,onUpdate}:Props){
 const {ui}=useToolsLocale();

 const scroll=useRef<HTMLDivElement>(null),drag=useRef<{selection:Selection;edge:'start'|'end'|'move';x:number;original:VideoProject}|null>(null);
 const duration=projectDuration(project),span=Math.max(12,duration+3),width=Math.max(640,span*zoom),clips=timelineClips(project.clips);
 const sourceName=(id:string)=>assets.find(a=>a.id===id)?.name??ui("파일");
 useEffect(()=>{const el=scroll.current;if(!el)return;let frame=0,targetX=el.scrollLeft,targetY=el.scrollTop;
  const tick=()=>{const dx=targetX-el.scrollLeft,dy=targetY-el.scrollTop;el.scrollLeft+=dx*.3;el.scrollTop+=dy*.3;if(Math.abs(dx)>1||Math.abs(dy)>1)frame=requestAnimationFrame(tick);else{el.scrollLeft=targetX;el.scrollTop=targetY;frame=0;}};
  const wheel=(event:WheelEvent)=>{event.preventDefault();const delta=(event.deltaMode===1?16:event.deltaMode===2?el.clientWidth:1);if(event.ctrlKey||event.metaKey){const x=event.clientX-el.getBoundingClientRect().left-96,anchor=(el.scrollLeft+x)/zoom,next=bound(zoom*Math.exp(-event.deltaY*.002),12,180);onZoom(next);cancelAnimationFrame(frame);frame=0;requestAnimationFrame(()=>{el.scrollLeft=Math.max(0,anchor*next-x);});return;}
   if(!frame){targetX=el.scrollLeft;targetY=el.scrollTop;}const vertical=!event.shiftKey&&(event.target as HTMLElement).closest('.ve-track-label');
   targetX=bound(targetX+(vertical?event.deltaX:event.deltaX+event.deltaY)*delta,0,el.scrollWidth-el.clientWidth);targetY=bound(targetY+(vertical?event.deltaY:0)*delta,0,el.scrollHeight-el.clientHeight);if(!frame)frame=requestAnimationFrame(tick);
  };el.addEventListener('wheel',wheel,{passive:false});return()=>{el.removeEventListener('wheel',wheel);cancelAnimationFrame(frame);};
 },[zoom,onZoom]);
 function start(event:PointerEvent,s:Selection,edge:'start'|'end'|'move'){
  if(event.button!==0)return;event.preventDefault();event.stopPropagation();onCheckpoint();onSelect(s);event.currentTarget.setPointerCapture(event.pointerId);drag.current={selection:s,edge,x:event.clientX,original:project};
  const clip=clips.find(c=>c.id===s.id),item=s.kind==='audio'?project.audio.find(c=>c.id===s.id):s.kind==='overlay'?project.overlays.find(c=>c.id===s.id):s.kind==='text'?project.texts.find(c=>c.id===s.id):undefined;onTime(clip?.at??(item&&'at'in item?item.at:item?.start)??0);
 }
 function move(event:PointerEvent){const d=drag.current;if(!d)return;const delta=(event.clientX-d.x)/zoom,{selection:s,edge,original:p}=d;
  if(s.kind==='clip'){
   const item=timelineClips(p.clips).find(c=>c.id===s.id);if(!item)return;
   if(edge==='move'){if(Math.abs(delta)<.15)return;const others=p.clips.filter(c=>c.id!==s.id),target=Math.max(0,item.at+delta),positions=timelineClips(others);let index=positions.findIndex(c=>target<c.at+clipLength(c)/2);if(index<0)index=others.length;others.splice(index,0,p.clips.find(c=>c.id===s.id)!);onUpdate({...p,clips:others});}
   else{const max=assets.find(a=>a.id===item.source)?.duration??1800;onUpdate({...p,clips:p.clips.map(c=>c.id===s.id?{...c,[edge]:edge==='start'?bound(c.start+delta,0,c.end-.05):bound(c.end+delta,c.start+.05,c.kind==='image'?120:max)}:c)});}
  }else if(s.kind==='audio'){
   onUpdate({...p,audio:p.audio.map(c=>{if(c.id!==s.id)return c;const max=assets.find(a=>a.id===c.source)?.duration??1800;if(edge==='move')return {...c,at:bound(c.at+delta,0,1800-clipLength(c))};if(edge==='start'){const next=bound(c.start+delta,Math.max(0,c.start-c.at),c.end-.05);return {...c,start:next,at:c.at+next-c.start};}return {...c,end:bound(c.end+delta,c.start+.05,max)};})});
  }else{const key=s.kind==='overlay'?'overlays':'texts';onUpdate({...p,[key]:p[key].map(c=>{if(c.id!==s.id)return c;if(edge==='move'){const next=bound(c.start+delta,0,1800-clipLength(c));return {...c,start:next,end:next+clipLength(c)};}return {...c,[edge]:edge==='start'?bound(c.start+delta,0,c.end-.05):bound(c.end+delta,c.start+.05,1800)};})});}
 }
 function item(s:Selection,at:number,length:number,name:string,extra=''){return <div key={s.id} role="button" tabIndex={0} aria-label={name} data-item={s.id} className={`ve-timeline-item ve-${s.kind} ${selection?.id===s.id?'selected':''} ${extra}`} style={{left:at*zoom,width:Math.max(14,length*zoom)}} onPointerDown={e=>start(e,s,'move')} onPointerMove={move} onPointerUp={()=>{drag.current=null;}} onPointerCancel={()=>{drag.current=null;}} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect(s);onTime(at);}}}><span className="ve-trim ve-trim-start" title={ui("시작 구간 조절")} data-edge="start" onPointerDown={e=>start(e,s,'start')} onPointerMove={move} onPointerUp={()=>{drag.current=null;}}/><span className="ve-item-name">{name}</span><span className="ve-trim ve-trim-end" title={ui("끝 구간 조절")} data-edge="end" onPointerDown={e=>start(e,s,'end')} onPointerMove={move} onPointerUp={()=>{drag.current=null;}}/></div>;}
 const interval=zoom<25?10:zoom<70?5:1;
 const tracks=useMemo(()=><>
  <div className="ve-track"><div className="ve-track-label">{ui("시간")}</div><div className="ve-ruler" style={{width}} onPointerDown={e=>{const rect=e.currentTarget.getBoundingClientRect();onTime(bound((e.clientX-rect.left)/zoom,0,duration));e.currentTarget.setPointerCapture(e.pointerId);}} onPointerMove={e=>{if(e.buttons===1){const rect=e.currentTarget.getBoundingClientRect();onTime(bound((e.clientX-rect.left)/zoom,0,duration));}}}>{Array.from({length:Math.ceil(width/zoom/interval)},(_,i)=><span key={i} style={{left:i*interval*zoom}}>{clockLabel(i*interval)}</span>)}</div></div>
  <div className="ve-track"><div className="ve-track-label">{ui("영상 · 사진")}</div><div className="ve-track-lane" style={{width}}>{clips.map(c=>item({kind:'clip',id:c.id},c.at,clipLength(c),sourceName(c.source)))}</div></div>
  <div className="ve-track ve-sound-track"><div className="ve-track-label">{ui("원본 소리")}</div><div className="ve-track-lane" style={{width}}>{clips.filter(c=>c.kind==='video').map(c=><button key={c.id} className={`ve-source-sound ${!c.volume?'muted':''}`} style={{left:c.at*zoom,width:Math.max(14,clipLength(c)*zoom)}} title={ui("클립을 선택한 뒤 원본 소리 볼륨을 조절하세요")} onClick={()=>{onSelect({kind:'clip',id:c.id});onTime(c.at);}}>{c.volume?ui("〰 원본 소리"):ui("음소거")}</button>)}</div></div>
  {(project.overlays.length?project.overlays:[null]).map((c,index)=><div key={c?.id??'no-overlay'} className="ve-track"><div className="ve-track-label">{ui("사진")}{index+1}</div><div className="ve-track-lane" style={{width}}>{c&&item({kind:'overlay',id:c.id},c.start,clipLength(c),sourceName(c.source))}</div></div>)}
  {(project.texts.length?project.texts:[null]).map((c,index)=><div key={c?.id??'no-text'} className="ve-track"><div className="ve-track-label">{ui("자막")}{index+1}</div><div className="ve-track-lane" style={{width}}>{c&&item({kind:'text',id:c.id},c.start,clipLength(c),c.text||ui("자막"))}</div></div>)}
  {(project.audio.length?project.audio:[null]).map((c,index)=><div key={c?.id??'no-audio'} className="ve-track"><div className="ve-track-label">{ui("음악")}{index+1}</div><div className="ve-track-lane" style={{width}}>{c&&item({kind:'audio',id:c.id},c.at,clipLength(c),sourceName(c.source))}</div></div>)}
 </>,[project,assets,zoom,selection?.id,ui,width,duration]);
 return <section className="ve-timeline" aria-label={ui("영상 편집 타임라인")}><div ref={scroll} className="ve-timeline-scroll"><div className="ve-timeline-content" style={{width:width+96}}>
 {tracks}
  <div className="ve-playhead" style={{left:96+time*zoom}}><i/></div>
 </div></div><p className="ve-timeline-tip">{ui("막대 위 휠: 좌우 이동 · 왼쪽 트랙 이름 위 휠: 상하 이동 · Shift+휠: 좌우 · Ctrl+휠: 확대/축소 · 양끝 손잡이: 자르기")}</p></section>;
}
