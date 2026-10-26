export type CropHandle='nw'|'n'|'ne'|'e'|'se'|'s'|'sw'|'w';
export function cropHandlePoints(crop:number[]){
 const [x,y,w,h]=crop;
 return {nw:[x,y],n:[x+w/2,y],ne:[x+w,y],e:[x+w,y+h/2],se:[x+w,y+h],s:[x+w/2,y+h],sw:[x,y+h],w:[x,y+h/2]} satisfies Record<CropHandle,number[]>;
}
/** Keep a moved or resized crop inside the original image, including reversed corner drags. */
export function changeEditorCrop(crop:number[],dx:number,dy:number,width:number,height:number,handle?:CropHandle){
 const [x,y,w,h]=crop,clamp=(n:number,max:number)=>Math.max(0,Math.min(max,n));
 if(!handle)return [clamp(x+dx,width-w),clamp(y+dy,height-h),w,h];
 let left=x,right=x+w,top=y,bottom=y+h;
 if(handle.includes('w'))left=clamp(x+dx,width);
 if(handle.includes('e'))right=clamp(x+w+dx,width);
 if(handle.includes('n'))top=clamp(y+dy,height);
 if(handle.includes('s'))bottom=clamp(y+h+dy,height);
 return [Math.min(left,right),Math.min(top,bottom),Math.max(1,Math.abs(right-left)),Math.max(1,Math.abs(bottom-top))];
}
/** Canvas and inline text share line spacing, so editing does not move text on export. */
export function editorTextSize(text:string,fontSize:number,measure:(line:string)=>number){
 const lines=text.split('\n');
 return {width:Math.max(40,...lines.map(line=>measure(line)+8)),height:Math.max(20,lines.length*fontSize*1.25+8)};
}
