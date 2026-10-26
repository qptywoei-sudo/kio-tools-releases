export type PhotoFormat='png'|'jpg'|'webp';
export type PhotoRect={x:number;y:number;width:number;height:number};
export type CollageCell={id?:string;zoom:number;panX:number;panY:number};
export const clamp=(value:number,min:number,max:number)=>Math.max(min,Math.min(max,value));
export function resizedPhotoSize(width:number,height:number,percent:number){
 if(![width,height,percent].every(Number.isFinite)||width<=0||height<=0||percent<=0)throw Error('잘못된 사진 크기입니다.');
 const result={width:Math.max(1,Math.round(width*percent/100)),height:Math.max(1,Math.round(height*percent/100))};
 if(result.width*result.height>64000000||result.width>16384||result.height>16384)throw Error('결과 사진이 너무 큽니다. 크기 비율을 낮춰 주세요.');
 return result;
}
export function collageLayout(count:number,style:string):PhotoRect[]{
 const n=clamp(Math.round(count),2,9);
 if(style==='hero'&&n>=3){const rest=n-1,rows=Math.ceil(rest/2);return [{x:0,y:0,width:.58,height:1},...Array.from({length:rest},(_,i)=>{const row=Math.floor(i/2),inRow=Math.min(2,rest-row*2);return {x:.58+(i%2)*(.42/inRow),y:row/rows,width:.42/inRow,height:1/rows};})];}
 if(style==='strips')return Array.from({length:n},(_,i)=>({x:i/n,y:0,width:1/n,height:1}));
 if(n===3)return [{x:0,y:0,width:.5,height:1},{x:.5,y:0,width:.5,height:.5},{x:.5,y:.5,width:.5,height:.5}];
 const cols=n===2?2:n===4?2:3,rows=Math.ceil(n/cols);
 return Array.from({length:n},(_,i)=>{const row=Math.floor(i/cols),inRow=Math.min(cols,n-row*cols);return {x:(i%cols)/inRow,y:row/rows,width:1/inRow,height:1/rows};});
}
export function collageBox(rect:PhotoRect,width:number,height:number,gap:number):PhotoRect{return {x:rect.x*width+gap/2,y:rect.y*height+gap/2,width:Math.max(1,rect.width*width-gap),height:Math.max(1,rect.height*height-gap)};}
export function collageImagePlacement(imageWidth:number,imageHeight:number,box:PhotoRect,cell:CollageCell):PhotoRect{
 const scale=Math.max(box.width/imageWidth,box.height/imageHeight)*clamp(cell.zoom,.2,5),width=imageWidth*scale,height=imageHeight*scale;
 return {x:box.x+(box.width-width)/2+cell.panX*box.width,y:box.y+(box.height-height)/2+cell.panY*box.height,width,height};
}
export function photoCanvas(width:number,height:number){const c=document.createElement('canvas');c.width=Math.max(1,Math.round(width));c.height=Math.max(1,Math.round(height));if(!c.getContext('2d'))throw Error('사진 편집 화면을 열 수 없습니다.');return c;}
export function photoBlob(canvas:HTMLCanvasElement,format:PhotoFormat='png',quality=90):Promise<Blob>{
 const mime={png:'image/png',jpg:'image/jpeg',webp:'image/webp'}[format];
 let result=canvas;if(format==='jpg'){result=photoCanvas(canvas.width,canvas.height);const c=result.getContext('2d')!;c.fillStyle='#ffffff';c.fillRect(0,0,result.width,result.height);c.drawImage(canvas,0,0);}
 return new Promise((resolve,reject)=>result.toBlob(blob=>blob&&blob.type===mime?resolve(blob):reject(Error('이 형식으로 저장할 수 없습니다. 다른 형식을 선택해 주세요.')),mime,quality/100));
}
export function photoName(name:string,suffix:string,format:PhotoFormat='png'){return `${name.replace(/\.[^.]+$/,'')}_${suffix}.${format}`;}
export function sizeLabel(bytes:number){return bytes<1024?`${bytes} B`:bytes<1024*1024?`${(bytes/1024).toFixed(1)} KB`:`${(bytes/1024/1024).toFixed(1)} MB`;}
