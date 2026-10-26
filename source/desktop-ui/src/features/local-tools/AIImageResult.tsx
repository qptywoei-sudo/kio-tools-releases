import {useEffect,useRef,useState} from 'react';
import {Copy,Download,Image as ImageIcon} from 'lucide-react';
import type {LocalAgentClient} from '@/services/local-agent';
import type {AIImageTranslation} from './ai-types';
import {useToolsLocale} from './tool-locale';
import {captureImageResult} from './capture-export';

type ImageCopyClient=Pick<LocalAgentClient,'aiScanPreview'|'aiTranslatedImage'|'copyImageBlob'>;
export async function copyAIImage(client:ImageCopyClient,scanId:string,imageId:string|null,kind:'original'|'translated',current:()=>boolean=()=>true){
 if(!current()||kind==='translated'&&!imageId)throw Error('aiSessionExpired');
 // Fetch at copy time so the agent can enforce expiry and account changes.
 // Original pixels stay in memory and never need an original-image preview.
 const png=kind==='original'?await client.aiScanPreview(scanId):await client.aiTranslatedImage(imageId!);
 if(!current())throw Error('aiSessionExpired');
 await client.copyImageBlob(png);
}
type ImageSaveClient=Pick<LocalAgentClient,'upload'|'jobs'|'job'>;
export async function saveAIImage(client:ImageSaveClient,png:Blob,current:()=>boolean){
 if(!current())return;
 const file=await client.upload(new File([png],'KIO-translation-'+Date.now()+'.png',{type:'image/png'}));
 if(!current())return;
 let {job}=await client.jobs('image_process',[file.id],{format:'png',scale_percent:100,no_upscale:true});
 if(!current())return;
 const deadline=Date.now()+120000;
 while(job.status==='queued'||job.status==='running'){
  if(Date.now()>deadline)throw Error('processingFailed');
  await new Promise(resolve=>setTimeout(resolve,250));if(!current())return;
  ({job}=await client.job(job.id));if(!current())return;
 }
 if(!current())return;
 return captureImageResult(job,true);
}

export function AIImageResult({client,scanId,value}:{client:LocalAgentClient;scanId:string;value:AIImageTranslation|null}){
 const {ui}=useToolsLocale(),[blob,setBlob]=useState<Blob|null>(null),[url,setUrl]=useState(''),[original,setOriginal]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState('');
 const imageId=value?.imageId??null,live=useRef(true),locked=useRef(false),currentImage=useRef({client,scanId,imageId,epoch:0});
 if(currentImage.current.client!==client||currentImage.current.scanId!==scanId||currentImage.current.imageId!==imageId)currentImage.current={client,scanId,imageId,epoch:currentImage.current.epoch+1};
 useEffect(()=>{live.current=true;return()=>{live.current=false;};},[client,scanId]);
 useEffect(()=>{let valid=true,objectUrl='';setBlob(null);setUrl('');setError('');setMessage('');setOriginal(false);
  if(value)void client.aiTranslatedImage(value.imageId).then(result=>{if(valid){objectUrl=URL.createObjectURL(result);setUrl(objectUrl);setBlob(result);}}).catch(()=>{if(valid)setError(ui('번역 이미지를 불러오지 못했습니다. 다시 시도해 주세요.'));});
  return()=>{valid=false;if(objectUrl)URL.revokeObjectURL(objectUrl);};
 },[client,scanId,value?.imageId]);
 async function copyImage(kind:'original'|'translated'){
  if(locked.current||kind==='translated'&&!blob)return;locked.current=true;setBusy(true);setError('');setMessage('');
  const context=currentImage.current;
  try{
   await copyAIImage(client,scanId,imageId,kind,()=>live.current&&context.client===currentImage.current.client&&context.scanId===currentImage.current.scanId&&(kind==='original'||context===currentImage.current));
   if(live.current)setMessage(ui(kind==='original'?'원문 이미지를 복사했어요':'번역 이미지를 복사했어요'));
  }catch{if(live.current)setError(ui('이미지를 복사하지 못했습니다. 다시 시도해 주세요.'));}
  finally{locked.current=false;if(live.current)setBusy(false);}
 }
 async function saveImage(){
  if(!blob||!value||locked.current)return;locked.current=true;setBusy(true);setError('');setMessage('');
  const context=currentImage.current,current=()=>live.current&&context===currentImage.current;
  try{
   await saveAIImage(client,blob,current);
   if(current())setMessage(ui('번역 이미지를 저장했어요'));
  }catch{if(current())setError(ui('이미지를 저장하지 못했습니다. 저장 폴더와 연결 상태를 확인해 주세요.'));}
  finally{locked.current=false;if(live.current)setBusy(false);}
 }
 return <section className="kio-image-translation" aria-label={ui('이미지 번역 결과')}>
  <div className="kio-ai-actions kio-image-copy-actions">
   <button className="lt-button" disabled={busy} onClick={()=>void copyImage('original')}><Copy size={15}/>{ui('원문 복사')}</button>
   <button className="lt-button primary" disabled={!blob||busy} onClick={()=>void copyImage('translated')}><Copy size={15}/>{ui('번역본 복사')}</button>
  </div>
  {value&&<><small>{value.model==='gpt-6.1-sol'?'GPT-6.1 Sol':value.model}</small>
  <div className="kio-image-result-preview">{url?<img src={url} alt={ui('번역 이미지')}/>:<p role="status">{ui('이미지 준비 중…')}</p>}</div>
  {!value.regions.length&&<p role="status">{ui('번역할 글자가 없어 원본 이미지를 표시합니다.')}</p>}
  <div className="kio-ai-actions">
   <button className="lt-button" disabled={!blob||busy} onClick={()=>void saveImage()}><Download size={15}/>{ui('이미지 저장')}</button>
   <button className="lt-button" aria-expanded={original} onClick={()=>setOriginal(v=>!v)}><ImageIcon size={15}/>{ui('번역 글자 확인')}</button>
  </div>
  {original&&<div className="kio-image-text-review">{value.regions.map((row,i)=><p key={i}><small>{row.originalText}</small><br/>{row.translatedText}</p>)}</div>}</>}
  {busy&&<p role="status">{ui('처리 중…')}</p>}{message&&<p role="status">{message}</p>}{error&&<p role="alert">{error}</p>}
 </section>;
}
