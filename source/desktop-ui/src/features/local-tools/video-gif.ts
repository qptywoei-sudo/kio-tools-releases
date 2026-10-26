export type GifRange={start:number;end:number};
export const GIF_MAX_RANGES=30,GIF_MAX_SECONDS=120,GIF_MIN_SECONDS=.02;
const bound=(value:number,min:number,max:number)=>Math.max(min,Math.min(max,Number.isFinite(value)?value:min));
const hundredth=(value:number)=>Math.round(value*100)/100;
export function gifDuration(value:number){return Number.isFinite(value)&&value>=GIF_MIN_SECONDS&&value<=86400?Math.floor(value*100)/100:0;}
export function initialGifRange(duration:number):GifRange{return {start:0,end:Math.min(5,gifDuration(duration))};}
export function changeGifRange(range:GifRange,edge:'start'|'end',value:number,duration:number):GifRange{
 const limit=gifDuration(duration);if(!limit)return {start:0,end:0};
 if(edge==='start'){const end=bound(range.end,GIF_MIN_SECONDS,limit);return {start:hundredth(bound(value,Math.max(0,end-GIF_MAX_SECONDS),end-GIF_MIN_SECONDS)),end};}
 const start=bound(range.start,0,limit-GIF_MIN_SECONDS);return {start,end:hundredth(bound(value,start+GIF_MIN_SECONDS,Math.min(limit,start+GIF_MAX_SECONDS)))};
}
export function nextGifRange(ranges:GifRange[],duration:number):GifRange{
 const limit=gifDuration(duration),last=ranges.at(-1)?.end??0;if(!limit)return {start:0,end:0};
 const start=last<=limit-GIF_MIN_SECONDS?last:Math.max(0,limit-5);return {start:hundredth(start),end:hundredth(Math.min(limit,start+5))};
}
export function gifTimeAt(clientX:number,left:number,width:number,duration:number){return width>0?hundredth(bound((clientX-left)/width,0,1)*gifDuration(duration)):0;}
export function gifTimeLabel(value:number){const seconds=hundredth(Math.max(0,Number.isFinite(value)?value:0)),hours=Math.floor(seconds/3600),minutes=Math.floor(seconds/60)%60,rest=(seconds%60).toFixed(2).padStart(5,'0');return `${hours?hours+':':''}${String(minutes).padStart(2,'0')}:${rest}`;}
export function validGifRanges(ranges:GifRange[],duration:number){const limit=gifDuration(duration);return limit>0&&ranges.length>0&&ranges.length<=GIF_MAX_RANGES&&ranges.every(range=>Number.isFinite(range.start)&&Number.isFinite(range.end)&&range.start>=0&&range.end<=limit&&range.end-range.start>=GIF_MIN_SECONDS-1e-8&&range.end-range.start<=GIF_MAX_SECONDS+1e-8);}
