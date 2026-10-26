import type {KIOAccountStatus} from './kio-account';
export const accountChangedEvent='kio:account-changed';
// An acknowledged logout supersedes any earlier in-flight status request.
export function createAccountObserver(read:()=>Promise<KIOAccountStatus>,onStatus:(value:KIOAccountStatus)=>void,onError:()=>void){
 let generation=0,closed=false,pending:Promise<void>|null=null;
 return {
  refresh(force=false):Promise<void>{
   if(closed)return Promise.resolve();
   if(force){generation++;pending=null;}
   if(pending)return pending;
   const revision=generation;
   const request=Promise.resolve().then(read).then(value=>{if(!closed&&revision===generation)onStatus(value);}).catch(()=>{if(!closed&&revision===generation)onError();}).finally(()=>{if(pending===request)pending=null;});
   pending=request;return request;
  },
  replace(value:KIOAccountStatus){if(closed)return;generation++;pending=null;onStatus(value);},
  close(){closed=true;generation++;pending=null;}
 };
}
export function publishAccountLogout(account:KIOAccountStatus){
 if(account.signedIn||account.user!==null)throw Error('Account logout was not acknowledged');
 window.dispatchEvent(new CustomEvent(accountChangedEvent,{detail:{signedOut:true,account}}));
}
export function acknowledgedLogout(event:Event):KIOAccountStatus|null{
 const detail=(event as CustomEvent).detail,value=detail?.account;
 return detail?.signedOut===true&&value?.signedIn===false&&value?.user===null&&typeof value?.connecting==='boolean'?value as KIOAccountStatus:null;
}
