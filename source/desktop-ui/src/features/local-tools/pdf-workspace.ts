import type {AgentFile} from './types';
export const PDF_PAGE_BATCH_SIZE=12;
export const PDF_THUMBNAIL_CACHE_SIZE=36;
export function pdfPageOrder(count:number){if(!Number.isInteger(count)||count<1||count>10000)throw Error('invalidRequest');return Array.from({length:count},(_,index)=>index+1);}
export function pdfPageBatch(order:number[],batch:number,size=PDF_PAGE_BATCH_SIZE){
 const safeSize=Math.min(PDF_PAGE_BATCH_SIZE,Math.max(1,Math.floor(size)||PDF_PAGE_BATCH_SIZE));
 const count=Math.max(1,Math.ceil(order.length/safeSize)),index=Math.min(count-1,Math.max(0,Math.floor(batch)||0));
 return {index,count,start:index*safeSize,pages:order.slice(index*safeSize,(index+1)*safeSize)};
}
export function movePdfPage(order:number[],index:number,delta:number){const next=index+delta;if(!Number.isInteger(index)||![-1,1].includes(delta)||index<0||index>=order.length||next<0||next>=order.length)return order;const result=[...order];[result[index],result[next]]=[result[next],result[index]];return result;}
export function moveSelectedPdfPages(order:number[],selection:number[],delta:number){
 const selected=new Set(selection),positions=order.flatMap((number,index)=>selected.has(number)?[index]:[]);
 if(![-1,1].includes(delta)||!positions.length||positions.length!==selected.size||(delta<0?positions[0]===0:positions.at(-1)===order.length-1))return order;
 const result=[...order];for(const index of delta<0?positions:[...positions].reverse()){const next=index+delta;[result[index],result[next]]=[result[next],result[index]];}return result;
}
export function removeSelectedPdfPages(order:number[],selection:number[]){const selected=new Set(selection),result=order.filter(number=>!selected.has(number));return result.length&&result.length!==order.length?result:order;}
export function selectedPdfPages(order:number[],selection:number[]){const selected=new Set(selection);return order.filter(number=>selected.has(number));}
/** Serialize small native render requests and discard responses for an older file. */
export class PdfThumbnailLoader{
 private epoch=0;
 private cache=new Map<number,AgentFile>();
 private pending:Promise<unknown>=Promise.resolve();
 reset(){this.epoch++;this.cache.clear();}
 cached(pages:number[]){return Object.fromEntries(pages.flatMap(number=>{const file=this.cache.get(number);return file?[[number,file]]:[];})) as Record<number,AgentFile>;}
 get size(){return this.cache.size;}
 load(pages:number[],read:(pages:number[])=>Promise<AgentFile[]>):Promise<Record<number,AgentFile>>{
  if(!pages.length||pages.length>PDF_PAGE_BATCH_SIZE||new Set(pages).size!==pages.length||pages.some(number=>!Number.isInteger(number)||number<1||number>10000))return Promise.reject(Error('invalidRequest'));
  const epoch=this.epoch,request=this.pending.catch(()=>{}).then(async()=>{
   if(epoch!==this.epoch)return {};
   const missing=pages.filter(number=>!this.cache.has(number));
   if(missing.length){const files=await read(missing);if(epoch!==this.epoch)return {};if(files.length!==missing.length||files.some(file=>!file?.id||file.mime&&!file.mime.startsWith('image/')))throw Error('processingFailed');missing.forEach((number,index)=>this.cache.set(number,files[index]));}
   for(const number of pages){const file=this.cache.get(number);if(file){this.cache.delete(number);this.cache.set(number,file);}}
   while(this.cache.size>PDF_THUMBNAIL_CACHE_SIZE){const oldest=this.cache.keys().next().value;if(oldest===undefined)break;this.cache.delete(oldest);}
   return this.cached(pages);
  });this.pending=request;return request;
 }
}
