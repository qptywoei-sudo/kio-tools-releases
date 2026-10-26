import type {CanvasLayer} from './canvas-geometry';

export function canvasImageLayer(inputIndex:number,imageWidth:number,imageHeight:number,canvasWidth:number,canvasHeight:number):CanvasLayer{
 if(!Number.isInteger(inputIndex)||inputIndex<0||![imageWidth,imageHeight,canvasWidth,canvasHeight].every(value=>Number.isFinite(value)&&value>0))throw Error('invalidRequest');
 const scale=Math.min(1,canvasWidth*.5/imageWidth,canvasHeight*.5/imageHeight),width=imageWidth*scale,height=imageHeight*scale;
 return {type:'image',inputIndex,x:Math.min(20,(canvasWidth-width)/2),y:Math.min(20,(canvasHeight-height)/2),width,height,opacity:1,rotation:0};
}
