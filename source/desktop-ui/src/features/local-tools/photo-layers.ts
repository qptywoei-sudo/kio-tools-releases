import {clamp,type PhotoRect} from './photo-studio';
export type PhotoLayer=PhotoRect&{id:string;imageId:string;name:string;opacity:number;rotation:number;flipX:boolean;annotation?:{kind:'text'|'pen';color:string;text?:string;fontSize?:number;lineWidth?:number;points?:{x:number;y:number}[];width:number;height:number}};
export type PhotoCorner='nw'|'ne'|'sw'|'se';
export function placedPhotoLayer(id:string,imageId:string,name:string,width:number,height:number,canvasWidth:number,canvasHeight:number):PhotoLayer{
 if(![width,height,canvasWidth,canvasHeight].every(n=>Number.isFinite(n)&&n>0))throw Error('invalidRequest');
 const scale=Math.min(1,canvasWidth*.55/width,canvasHeight*.55/height),w=width*scale,h=height*scale;
 return{id,imageId,name,x:(canvasWidth-w)/2,y:(canvasHeight-h)/2,width:w,height:h,rotation:0,opacity:1,flipX:false};
}
export function photoLayerPoint(layer:PhotoLayer,x:number,y:number){const angle=layer.rotation*Math.PI/180,c=Math.cos(angle),s=Math.sin(angle);return{x:layer.x+layer.width/2+x*c-y*s,y:layer.y+layer.height/2+x*s+y*c};}
export function photoLayerLocal(layer:PhotoLayer,p:{x:number;y:number}){const angle=-layer.rotation*Math.PI/180,x=p.x-layer.x-layer.width/2,y=p.y-layer.y-layer.height/2;return{x:x*Math.cos(angle)-y*Math.sin(angle),y:x*Math.sin(angle)+y*Math.cos(angle)};}
export function photoLayerContains(layer:PhotoLayer,p:{x:number;y:number}){const at=photoLayerLocal(layer,p);return Math.abs(at.x)<=layer.width/2&&Math.abs(at.y)<=layer.height/2;}
export function photoLayerCorners(layer:PhotoLayer):Record<PhotoCorner,{x:number;y:number}>{return{nw:photoLayerPoint(layer,-layer.width/2,-layer.height/2),ne:photoLayerPoint(layer,layer.width/2,-layer.height/2),sw:photoLayerPoint(layer,-layer.width/2,layer.height/2),se:photoLayerPoint(layer,layer.width/2,layer.height/2)};}
export function resizePhotoLayer(layer:PhotoLayer,corner:PhotoCorner,dx:number,dy:number,free=false):PhotoLayer{
 const angle=-layer.rotation*Math.PI/180,localX=dx*Math.cos(angle)-dy*Math.sin(angle),localY=dx*Math.sin(angle)+dy*Math.cos(angle),sx=corner.endsWith('e')?1:-1,sy=corner.startsWith('s')?1:-1;
 let width=clamp(layer.width+sx*localX,8,32768),height=clamp(layer.height+sy*localY,8,32768);
 if(!free){const change=Math.abs(localX/layer.width)>Math.abs(localY/layer.height)?sx*localX/layer.width:sy*localY/layer.height,factor=clamp(1+change,Math.max(8/layer.width,8/layer.height),Math.min(32768/layer.width,32768/layer.height));width=layer.width*factor;height=layer.height*factor;}
 const shift=photoLayerPoint(layer,sx*(width-layer.width)/2,sy*(height-layer.height)/2);
 return{...layer,width,height,x:shift.x-width/2,y:shift.y-height/2};
}
export function scalePhotoLayer(layer:PhotoLayer,factor:number):PhotoLayer{const scale=clamp(factor,Math.max(8/layer.width,8/layer.height),Math.min(32768/layer.width,32768/layer.height));const width=layer.width*scale,height=layer.height*scale;return{...layer,x:layer.x+(layer.width-width)/2,y:layer.y+(layer.height-height)/2,width,height};}
export function rotatePhotoLayers(layers:PhotoLayer[],oldHeight:number){return layers.map(l=>{const cx=oldHeight-(l.y+l.height/2),cy=l.x+l.width/2;return{...l,x:cx-l.width/2,y:cy-l.height/2,rotation:(l.rotation+90)%360};});}
export function flipPhotoLayers(layers:PhotoLayer[],width:number){return layers.map(l=>({...l,x:width-l.x-l.width,rotation:-l.rotation,flipX:!l.flipX}));}
export function drawPhotoLayers(context:CanvasRenderingContext2D,layers:PhotoLayer[],image:(id:string)=>CanvasImageSource|undefined){for(const layer of layers){const source=layer.annotation?undefined:image(layer.imageId);if(!source&&!layer.annotation)continue;context.save();context.globalAlpha=layer.opacity;context.translate(layer.x+layer.width/2,layer.y+layer.height/2);context.rotate(layer.rotation*Math.PI/180);context.scale(layer.flipX?-1:1,1);if(layer.annotation){const a=layer.annotation;context.translate(-layer.width/2,-layer.height/2);context.scale(layer.width/a.width,layer.height/a.height);context.fillStyle=a.color;context.strokeStyle=a.color;
 if(a.kind==='text'){context.font=`600 ${a.fontSize}px sans-serif`;context.textBaseline='top';(a.text??'').split('\n').forEach((line,index)=>context.fillText(line,2,2+index*(a.fontSize??48)*1.25));}
 else {context.lineWidth=a.lineWidth??8;context.lineCap='round';context.lineJoin='round';context.beginPath();a.points?.forEach((p,index)=>index?context.lineTo(p.x,p.y):context.moveTo(p.x,p.y));if(a.points?.length===1)context.lineTo(a.points[0].x+.01,a.points[0].y);context.stroke();}
 }else if(source)context.drawImage(source,-layer.width/2,-layer.height/2,layer.width,layer.height);context.restore();}}

export function textPhotoLayer(id:string,text:string,x:number,y:number,fontSize:number,width:number,color:string):PhotoLayer{
 const height=Math.max(1,text.split('\n').length)*fontSize*1.25+4;
 return{id,imageId:'',name:text,x,y,width:Math.max(8,width+4),height,opacity:1,rotation:0,flipX:false,annotation:{kind:'text',text,fontSize,color,width:Math.max(8,width+4),height}};
}
export function penPhotoLayer(id:string,name:string,points:{x:number;y:number}[],lineWidth:number,color:string):PhotoLayer{
 if(!points.length)throw Error('invalidRequest');
 const pad=lineWidth/2+1;let left=Infinity,top=Infinity,right=-Infinity,bottom=-Infinity;for(const p of points){left=Math.min(left,p.x);top=Math.min(top,p.y);right=Math.max(right,p.x);bottom=Math.max(bottom,p.y);}
 const x=left-pad,y=top-pad,width=Math.max(8,right-x+pad),height=Math.max(8,bottom-y+pad);
 return{id,imageId:'',name,x,y,width,height,opacity:1,rotation:0,flipX:false,annotation:{kind:'pen',color,lineWidth,width,height,points:points.map(p=>({x:p.x-x,y:p.y-y}))}};
}
