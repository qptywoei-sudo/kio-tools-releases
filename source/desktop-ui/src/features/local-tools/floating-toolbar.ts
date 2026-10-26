export type ToolbarPoint={x:number;y:number};
export type ToolbarSize={width:number;height:number};
/** Keep the whole movable toolbar reachable, even in a very small resized window. */
export function clampFloatingToolbar(point:ToolbarPoint,surface:ToolbarSize,toolbar:ToolbarSize,gap=6):ToolbarPoint{
 const dimension=(n:number)=>Number.isFinite(n)?Math.max(0,n):0;
 const axis=(value:number,space:number,size:number)=>{const available=Math.max(0,dimension(space)-dimension(size));const inset=Math.min(Math.max(0,gap),available/2);return Math.min(Math.max(inset,Number.isFinite(value)?value:inset),Math.max(inset,available-inset));};
 return {x:axis(point.x,surface.width,toolbar.width),y:axis(point.y,surface.height,toolbar.height)};
}
export function moveFloatingToolbar(point:ToolbarPoint,key:string,precise=false):ToolbarPoint|null{
 const distance=precise?1:10;
 if(key==='Home')return {x:6,y:6};
 if(key==='ArrowLeft')return {...point,x:point.x-distance};
 if(key==='ArrowRight')return {...point,x:point.x+distance};
 if(key==='ArrowUp')return {...point,y:point.y-distance};
 if(key==='ArrowDown')return {...point,y:point.y+distance};
 return null;
}
