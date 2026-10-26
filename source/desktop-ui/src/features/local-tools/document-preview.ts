import {useEffect,useRef,useState} from 'react';
import type {LocalAgentClient} from '@/services/local-agent';
import type {AgentFile,AgentJob} from './types';

export const isPdf=(file:AgentFile)=>file.mime==='application/pdf'||/\.pdf$/i.test(file.name);
export type DocumentRunner=(operation:string,inputs:string[],options:Record<string,unknown>)=>Promise<AgentJob>;
export async function previewJob(client:LocalAgentClient,operation:string,inputs:string[],options:Record<string,unknown>):Promise<AgentJob>{
 let {job}=await client.jobs(operation,inputs,{...options,previewOnly:true});
 const deadline=Date.now()+120000;
 while(!['complete','completed','failed','cancelled'].includes(job.status)){
  if(Date.now()>deadline)throw Error('미리보기를 불러오는 데 시간이 너무 오래 걸립니다.');
  await new Promise(resolve=>setTimeout(resolve,300));
  job=(await client.job(job.id)).job;
 }
 if(!['complete','completed'].includes(job.status))throw Error('미리보기를 불러오지 못했습니다.');
 return job;
}
export function useDocumentPreview(client:LocalAgentClient,file:AgentFile|undefined,page=1,runner?:DocumentRunner){
 const [state,setState]=useState({key:'',url:'',pages:1,loading:false,error:'',width:0,height:0});
 const [retry,setRetry]=useState(0);
 const pageCounts=useRef(new Map<string,number>()),key=file?`${file.id}:${page}`:'';
 useEffect(()=>{
  let active=true,url='';
  if(!file){setState({key:'',url:'',pages:1,loading:false,error:'',width:0,height:0});return;}
  setState({key,url:'',pages:pageCounts.current.get(file.id)??1,loading:true,error:'',width:0,height:0});
  const run:DocumentRunner=runner??((operation,inputs,options)=>previewJob(client,operation,inputs,options));
  void(async()=>{
   let artifact=file,pages=1;
   if(isPdf(file)){
    const cached=pageCounts.current.get(file.id);
    if(cached)pages=cached;
    else{const info=await run('pdf_info',[file.id],{previewOnly:true});pages=Math.max(1,Number(info.result?.data?.page_count??info.data?.page_count??1));if(pageCounts.current.size>64)pageCounts.current.clear();pageCounts.current.set(file.id,pages);}
    if(!active)return;
    const result=await run('pdf_render',[file.id],{pages:String(Math.min(page,pages)),dpi:120,format:'png',previewOnly:true});
    const rendered=(result.result?.files??result.artifacts??[])[0];
    if(!rendered)throw Error('PDF 미리보기가 없습니다.');
    artifact=rendered;
   }else if(/\.(tiff?|heic|heif)$/i.test(file.name)){
    const result=await run('image_process',[file.id],{format:'png',scale:100,previewOnly:true});
    artifact=(result.result?.files??result.artifacts??[])[0]??file;
   }
   if(!active)return;const blob=await client.artifact(artifact.id);if(!active)return;
   url=URL.createObjectURL(blob);
   const image=await new Promise<HTMLImageElement>((resolve,reject)=>{const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(Error('이미지를 표시할 수 없습니다.'));img.src=url;});
   if(active)setState({key,url,pages,loading:false,error:'',width:image.naturalWidth,height:image.naturalHeight});
  })().catch(error=>{if(active)setState({key,url:'',pages:pageCounts.current.get(file.id)??1,loading:false,error:error instanceof Error?error.message:'미리보기 오류',width:0,height:0});});
  return()=>{active=false;if(url)URL.revokeObjectURL(url);};
 },[client,file?.id,page,runner,retry]);
 return {...(state.key===key?state:{key,url:'',pages:file?pageCounts.current.get(file.id)??1:1,loading:Boolean(file),error:'',width:0,height:0}),retry:()=>setRetry(value=>value+1)};
}
