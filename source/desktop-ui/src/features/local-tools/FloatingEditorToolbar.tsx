import {useLayoutEffect,useRef,useState,type ReactNode} from 'react';
import {GripVertical} from 'lucide-react';
import type {ToolLanguage} from './types';
import {clampFloatingToolbar,moveFloatingToolbar,type ToolbarPoint} from './floating-toolbar';

const labels={ko:['도구 설정 이동','끌어서 이동 · 방향키 이동 · Home 원위치'],en:['Move tool options','Drag to move · Arrow keys move · Home resets'],vi:['Di chuyển tùy chọn','Kéo hoặc dùng phím mũi tên · Home đặt lại'],ja:['ツール設定を移動','ドラッグ・矢印キーで移動 · Homeで戻す'],zh:['移动工具设置','拖动或方向键移动 · Home复位'], "zh-TW":['移動工具設定','拖動或方向鍵移動 · Home復位']};
export function FloatingEditorToolbar({children,label,language,hidden=false}:{children:ReactNode;label:string;language:ToolLanguage;hidden?:boolean}){
 const toolbar=useRef<HTMLDivElement>(null),drag=useRef<{pointer:number;clientX:number;clientY:number;origin:ToolbarPoint}|null>(null),positionRef=useRef<ToolbarPoint>({x:6,y:6});
 const [position,setPosition]=useState(positionRef.current),[dragging,setDragging]=useState(false);
 function place(next:ToolbarPoint){const node=toolbar.current,parent=node?.parentElement;if(!node||!parent)return;const bounded=clampFloatingToolbar(next,{width:parent.clientWidth,height:parent.clientHeight},{width:node.offsetWidth,height:node.offsetHeight});positionRef.current=bounded;setPosition(current=>current.x===bounded.x&&current.y===bounded.y?current:bounded);}
 useLayoutEffect(()=>{const node=toolbar.current,parent=node?.parentElement;if(!node||!parent||hidden)return;const update=()=>place(positionRef.current);update();const observer=new ResizeObserver(update);observer.observe(node);observer.observe(parent);return()=>observer.disconnect();},[hidden]);
 const [moveLabel,moveHint]=labels[language]??labels.ko;
 return <div ref={toolbar} hidden={hidden} className={'gc-canvas-float'+(dragging?' dragging':'')} style={{left:position.x,top:position.y}} role="group" aria-label={label}>
  <button type="button" className="gc-float-handle" aria-label={moveLabel} title={moveHint} onPointerDown={event=>{if(event.button!==0||!event.isPrimary)return;event.preventDefault();event.stopPropagation();event.currentTarget.focus({preventScroll:true});drag.current={pointer:event.pointerId,clientX:event.clientX,clientY:event.clientY,origin:{...positionRef.current}};event.currentTarget.setPointerCapture(event.pointerId);setDragging(true);}} onPointerMove={event=>{const current=drag.current;if(!current||current.pointer!==event.pointerId)return;event.preventDefault();place({x:current.origin.x+event.clientX-current.clientX,y:current.origin.y+event.clientY-current.clientY});}} onPointerUp={event=>{if(drag.current?.pointer!==event.pointerId)return;drag.current=null;setDragging(false);if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);}} onPointerCancel={()=>{drag.current=null;setDragging(false);}} onLostPointerCapture={()=>{drag.current=null;setDragging(false);}} onKeyDown={event=>{if(event.ctrlKey||event.metaKey||event.altKey)return;const next=moveFloatingToolbar(positionRef.current,event.key,event.shiftKey);if(!next)return;event.preventDefault();event.stopPropagation();place(next);}}><GripVertical size={14}/></button>
  {children}
 </div>;
}
