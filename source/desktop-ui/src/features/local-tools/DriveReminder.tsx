import {useToolsLocale} from './tool-locale';
import {useEffect,useState} from 'react';
import {Cloud,X} from 'lucide-react';
import type {StorageStatus} from './drive-library';
const week=7*24*60*60*1000;
export function DriveReminder({status,profile,onOpen,hidden=false}:{status:StorageStatus|null;profile:string;onOpen:()=>void;hidden?:boolean}){
 const {ui}=useToolsLocale();

 const [visible,setVisible]=useState(false),key='kio-drive-reminder:'+profile;
 const connected=status?.drive.connected,connecting=status?.drive.connecting||status?.drive.checking,ready=!!status;
 useEffect(()=>{setVisible(false);if(!ready||connected||connecting||hidden)return;let last=0;try{last=Number(localStorage.getItem(key))||0;}catch{}if(last>0&&Date.now()-last<week)return;const timer=setTimeout(()=>{setVisible(true);try{localStorage.setItem(key,String(Date.now()));}catch{}},15000);return()=>clearTimeout(timer);},[connected,connecting,ready,key,hidden]);
 if(!visible||connected||hidden)return null;
 return <aside className="kio-drive-reminder" role="status"><Cloud size={21}/><div><strong>{ui("내 작업을 Google Drive에도 보관하세요")}</strong><small>{status?.drive.configured?ui("Google 계정을 연결하면 다른 기기에서도 작업 결과를 꺼낼 수 있어요."):ui("이 배포본은 Drive 연결 준비가 필요합니다. 준비되면 설정에서 연결할 수 있어요.")}</small></div><button className="lt-button primary" onClick={()=>{setVisible(false);onOpen();}}>{ui("Drive 설정")}</button><button className="lt-button lt-icon-button" title={ui("일주일 동안 닫기")} aria-label={ui("Drive 안내 일주일 동안 닫기")} onClick={()=>setVisible(false)}><X size={16}/></button></aside>;
}
